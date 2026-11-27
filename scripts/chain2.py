"""第 2 批的对照组（流程照 B 评测）。每个（组，对照组）是一条链：
  写入 T1、写入 T2、测 T3、写入 T3、测 T4、写入 T4、写入 T5、测 T6、写入 T6、测 T7
测试任务由 agent 在隔离容器里真实完成（每题一份干净的仓库），检查脚本在代码上判定；做完的会话写回记忆再进下一题。
对照组：none 无记忆 / raw 原话检索（向量取前 12 条）/ mem0 / hindsight / oracle 理想送达（直接给当时生效的规范）。
用法：<python> chain2.py <round> <cond> [并发=16]      mem0 用 pilot/memenv 的 python，hindsight 用 pilot/hsenv 的 python"""
import json, math, os, re, shutil, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE); sys.path.insert(0, f"{ROOT}/norms")
from common import CODEX_CONFIG, clean_dir, api_key, sh, codex_call
import llm
from norms2 import NORM, judge_all
RN, COND = sys.argv[1], sys.argv[2]; W = int(sys.argv[3]) if len(sys.argv) > 3 else 16
RD = f"{ROOT}/work/{RN}"; KEY = api_key(2); MODEL = "deepseek-v4.1-flash"; PKG = {"click": "src/click", "jinja": "src/jinja2"}
GROUPS = [g for g in json.load(open(f"{RD}/groups.json")) if not os.environ.get("ONLY_GROUPS") or g["id"] in os.environ["ONLY_GROUPS"].split(",")]; STEPS = ["w:T1", "w:T2", "t:T3", "w:T3", "t:T4", "w:T4", "w:T5", "t:T6", "w:T6", "t:T7"]; TESTS = ["T3", "T4", "T6", "T7"]
RETRY = bool(os.environ.get("RETRY_TIMEOUTS")); REPLAY = bool(os.environ.get("REPLAY")); NS = RN + ("r" if REPLAY else "")
GW = os.environ.get("GW_OVERRIDE") or "https://your-gateway.example/v1"; LOCK = threading.Lock(); TOPK = 12
def rule_at(order, slot): return "new" if order == "CD" else ("old" if slot in ("T3", "T4") else "new")
def prior(g): return json.load(open(f"{RD}/prior/{g['id']}.json"))
def hdr(g, slot, agent=False):
    s = g["slots"][slot]; who = f"{s['name']} ({'maintainer' if s['member'] == 'A' else 'team member'})"
    return f"[{s['date']}] {s['name']}'s coding agent reported: " if agent else f"[{s['date']}] {who} told their coding agent: "
def embed(texts):
    out = []
    for i in range(0, len(texts), 32):
        body = json.dumps({"model": "text-embedding-3-small", "input": [t[:6000] or " " for t in texts[i:i + 32]]}).encode()
        for att in range(5):
            try:
                req = urllib.request.Request(GW + "/embeddings", data=body, headers={"Authorization": "Bearer " + llm.key(3), "Content-Type": "application/json"})
                out += [x["embedding"] for x in json.loads(urllib.request.urlopen(req, timeout=120).read())["data"]]; break
            except Exception:
                if att == 4: raise
                time.sleep(5 * (att + 1))
    return out
def cos(a, b): return sum(x * y for x, y in zip(a, b)) / ((math.sqrt(sum(x * x for x in a)) or 1) * (math.sqrt(sum(x * x for x in b)) or 1))

# ───────────────────────────── 记忆后端 ─────────────────────────────
M0 = {}; HS = {"srv": None}; _tl = threading.local()
if COND == "mem0" and not RETRY:
    os.environ["OPENAI_API_KEY"] = llm.key(3); os.environ["OPENAI_BASE_URL"] = GW; os.environ["MEM0_TELEMETRY"] = "false"
    from mem0 import Memory
if COND == "hindsight" and not RETRY:
    import subprocess
    PORT = int(os.environ.get("HS_PORT") or 8898); URL = f"http://127.0.0.1:{PORT}"; os.makedirs(f"{RD}/mem/hindsight", exist_ok=True)
    env = dict(os.environ, HINDSIGHT_API_DATABASE_URL="postgresql://hindsight:hindsight@127.0.0.1:55432/hindsight", HINDSIGHT_API_LLM_PROVIDER="openai", HINDSIGHT_API_LLM_MODEL="gpt-5.4-mini",
               HINDSIGHT_API_LLM_BASE_URL=GW, HINDSIGHT_API_LLM_API_KEY=llm.key(3), HINDSIGHT_API_EMBEDDINGS_PROVIDER="openai", HINDSIGHT_API_EMBEDDINGS_OPENAI_MODEL="text-embedding-3-small",
               HINDSIGHT_API_EMBEDDINGS_OPENAI_BASE_URL=GW, HINDSIGHT_API_EMBEDDINGS_OPENAI_API_KEY=llm.key(3), HINDSIGHT_API_RERANKER_PROVIDER="rrf", HINDSIGHT_API_OTEL_TRACES_ENABLED="false",
               HINDSIGHT_API_PORT=str(PORT), HINDSIGHT_API_HOST="127.0.0.1")
    HS["srv"] = subprocess.Popen([os.path.join(os.path.dirname(sys.executable), "hindsight-api"), "--port", str(PORT), "--host", "127.0.0.1", "--log-level", "warning"],
                                 env=env, stdout=open(f"{RD}/mem/hindsight/server.log", "a"), stderr=subprocess.STDOUT)
    for _ in range(240):
        try: urllib.request.urlopen(URL + "/health", timeout=2); break
        except Exception: time.sleep(1)
    else: HS["srv"].kill(); raise SystemExit("hindsight server did not come up")
    from hindsight_client import Hindsight
    def H():
        if not hasattr(_tl, "c"): _tl.c = Hindsight(base_url=URL, timeout=900)
        return _tl.c
import asyncio
BG = {}
def bg(coro, timeout=2400):
    """在一条专用的后台事件循环上跑协程（Graphiti、Cognee 都是 async 接口）。"""
    with LOCK:
        if "loop" not in BG:
            BG["loop"] = asyncio.new_event_loop(); threading.Thread(target=BG["loop"].run_forever, daemon=True).start()
    return asyncio.run_coroutine_threadsafe(coro, BG["loop"]).result(timeout=timeout)
async def _sem(n):
    if "sem" not in BG: BG["sem"] = asyncio.Semaphore(n)
    return BG["sem"]
if COND == "langmem" and not RETRY:
    os.environ["OPENAI_API_KEY"] = llm.key(3); os.environ["OPENAI_BASE_URL"] = GW; os.environ["OPENAI_API_BASE"] = GW
    from langchain_openai import OpenAIEmbeddings, ChatOpenAI
    from langgraph.store.memory import InMemoryStore
    from langmem import create_memory_store_manager
    LM = {"store": InMemoryStore(index={"dims": 1536, "embed": OpenAIEmbeddings(model="text-embedding-3-small", check_embedding_ctx_length=False)}), "mgr": {}}
    def lm_mgr(g):
        with LOCK:
            if g["id"] not in LM["mgr"]: LM["mgr"][g["id"]] = create_memory_store_manager(ChatOpenAI(model="gpt-5.4-mini", temperature=0), namespace=("team", g["id"]), store=LM["store"])
            return LM["mgr"][g["id"]]
if COND == "graphiti" and not RETRY:
    os.environ["OPENAI_API_KEY"] = llm.key(3); os.environ["OPENAI_BASE_URL"] = GW
    import datetime
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    async def _gr():
        if "g" not in BG:
            cfg = LLMConfig(api_key=llm.key(3), model="gpt-5.4-mini", small_model="gpt-5.4-mini", base_url=GW)
            BG["g"] = Graphiti(graph_driver=FalkorDriver(host="127.0.0.1", port=16379), llm_client=OpenAIGenericClient(config=cfg),
                               embedder=OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=llm.key(3), embedding_model="text-embedding-3-small", base_url=GW)), cross_encoder=OpenAIRerankerClient(config=cfg))
            await BG["g"].build_indices_and_constraints()
        return BG["g"]
    async def gr_add(gid, name, body, date):
        g_ = await _gr()
        async with await _sem(5):
            await g_.add_episode(name=name, episode_body=body[:12000], source=EpisodeType.message, source_description="session of a software team member with their coding agent",
                                 reference_time=datetime.datetime.fromisoformat(date + "T10:00:00+00:00"), group_id=gid)
    async def gr_search(gid, q):
        g_ = await _gr(); return await g_.search(q, group_ids=[gid], num_results=TOPK)
if COND == "cognee" and not RETRY:
    CG_ROOT = os.path.abspath(f"{RD}/mem/cognee" + ("_replay" if REPLAY else "")); os.makedirs(CG_ROOT, exist_ok=True)
    os.environ.update({"LLM_API_KEY": llm.key(3), "LLM_PROVIDER": "openai", "LLM_MODEL": "openai/gpt-5.4-mini", "LLM_ENDPOINT": GW, "EMBEDDING_PROVIDER": "openai", "EMBEDDING_MODEL": "openai/text-embedding-3-small",
                       "EMBEDDING_ENDPOINT": GW, "EMBEDDING_API_KEY": llm.key(3), "EMBEDDING_DIMENSIONS": "1536", "TELEMETRY_DISABLED": "1", "ENABLE_BACKEND_ACCESS_CONTROL": "false",
                       "SYSTEM_ROOT_DIRECTORY": CG_ROOT + "/system", "DATA_ROOT_DIRECTORY": CG_ROOT + "/data"})
    import cognee
    from cognee import SearchType
    async def cg_add(ds, text):
        async with await _sem(2):
            await cognee.add(text, dataset_name=ds); await cognee.cognify(datasets=[ds])
    async def cg_search(ds, q):
        return await cognee.search(query_text=q, query_type=SearchType.GRAPH_COMPLETION, datasets=[ds], top_k=TOPK, only_context=True)
EV_URL = os.environ.get("EVEROS_URL", "http://127.0.0.1:8011")
def ev_post(path, body, timeout=600):
    req = urllib.request.Request(EV_URL + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
def mem0_of(g):
    with LOCK:
        if g["id"] not in M0:
            d = f"{RD}/mem/mem0{'_replay' if REPLAY else ''}/{g['id']}"; os.makedirs(d, exist_ok=True)
            M0[g["id"]] = Memory.from_config({"llm": {"provider": "openai", "config": {"model": "gpt-5.4-mini", "openai_base_url": GW}},
                "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small", "openai_base_url": GW}},
                "vector_store": {"provider": "qdrant", "config": {"path": f"{d}/qdrant", "collection_name": "team", "embedding_model_dims": 1536}}, "history_db_path": f"{d}/history.db"})
        return M0[g["id"]]
def retry(f, n=3):
    for a in range(n):
        try: return f()
        except Exception as e:
            if a == n - 1: raise
            time.sleep(15 * (a + 1))
def mem_write(g, slot, st, user, assistant):
    if COND in ("none", "oracle"): return
    u, a = hdr(g, slot) + user, hdr(g, slot, True) + assistant[:3000]
    if COND == "raw":
        r = st.setdefault("raw", {"entries": [], "vecs": []})
        ents = [hdr(g, slot) + p.strip() for p in user.split("\n\n") if p.strip()] + [a[:1800]]
        r["entries"] += ents; r["vecs"] += embed(ents)
    elif COND == "mem0":
        retry(lambda: mem0_of(g).add([{"role": "user", "content": u}, {"role": "assistant", "content": a}], user_id="team"))
    elif COND == "langmem":
        retry(lambda: lm_mgr(g).invoke({"messages": [{"role": "user", "content": u}, {"role": "assistant", "content": a}]}))
    elif COND == "graphiti":
        body = re.sub(r"(?<!\w)_(?!\w)", "gettext", u + "\n\n" + a)       # 单独的下划线（gettext 的别名 `_`）会让 FalkorDB 全文检索报语法错，写入前换成 gettext
        retry(lambda: bg(gr_add(f"{NS}_{g['id']}", f"{g['id']}-{slot}", body, g["slots"][slot]["date"])))
    elif COND == "cognee":
        retry(lambda: bg(cg_add(f"{NS}_{g['id']}", u + "\n\n" + a)))
    elif COND == "everos":                              # 每组一个 project；一段会话一个 session，写完立即 flush（同步整理）
        import datetime
        ts = int(datetime.datetime.fromisoformat(g["slots"][slot]["date"] + "T10:00:00+00:00").timestamp() * 1000); proj = f"{NS}-{g['id']}"; sid = f"{g['id']}-{slot}"
        retry(lambda: ev_post("/api/v2/memory/add", {"session_id": sid, "app_id": "default", "project_id": proj, "messages": [
            {"sender_id": "team", "role": "user", "timestamp": ts, "content": u[:20000]}, {"sender_id": "agent", "role": "assistant", "timestamp": ts + 60000, "content": a}]}))
        retry(lambda: ev_post("/api/v2/memory/flush", {"session_id": sid, "app_id": "default", "project_id": proj}))
        time.sleep(20)                                   # 等索引同步（写 md 后由后台同步进向量索引）
    elif COND == "hindsight":
        bank = f"{NS}-{g['id']}"
        if slot == "T1":
            try: H().delete_bank(bank)
            except Exception: pass
            try: H().create_bank(bank_id=bank, name=f"team {g['id']}")
            except Exception: pass
        retry(lambda: H().retain(bank_id=bank, content=u + "\n\n" + a, context="sessions of the members of one software team with their coding agents", document_id=f"{g['id']}-{slot}",
                                 timestamp=g["slots"][slot]["date"] + "T10:00:00Z"))
def mem_query(g, slot, st, q):
    if COND == "none": return ""
    if COND == "oracle":
        return "Current team conventions for this repository:\n" + "\n".join("- " + NORM[n][rule_at(o, slot)] for n, o in g["order"].items())
    if COND == "raw":
        r = st.get("raw") or {"entries": [], "vecs": []}
        if not r["entries"]: return ""
        qv = embed([q])[0]; idx = sorted(range(len(r["entries"])), key=lambda i: -cos(qv, r["vecs"][i]))[:TOPK]
        return "\n".join(r["entries"][i] for i in sorted(idx))
    if COND == "mem0":
        res = retry(lambda: mem0_of(g).search(q[:1500], filters={"user_id": "team"}, top_k=TOPK)); res = res["results"] if isinstance(res, dict) else res
        return "\n".join("- " + x["memory"] for x in res)
    if COND == "langmem":
        def txt(v):
            while isinstance(v, dict) and "content" in v: v = v["content"]
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        return "\n".join("- " + txt(r.value) for r in retry(lambda: LM["store"].search(("team", g["id"]), query=q[:1500], limit=TOPK)))
    if COND == "graphiti":
        out = []
        gq = " ".join(t for t in re.sub(r"[^\w\s]", " ", q[:1500]).split() if t.strip("_"))     # FalkorDB 的全文检索遇到单独的下划线等符号会报语法错
        for e in retry(lambda: bg(gr_search(f"{NS}_{g['id']}", gq), 600)):
            v = f" [valid from {str(e.valid_at)[:10]}]" if e.valid_at else ""; iv = f" [no longer valid since {str(e.invalid_at)[:10]}]" if e.invalid_at else ""
            out.append("- " + e.fact + v + iv)
        return "\n".join(out)
    if COND == "cognee":
        res = retry(lambda: bg(cg_search(f"{NS}_{g['id']}", q[:1500]), 600))
        def flat(x):
            if isinstance(x, str): return [x]
            if isinstance(x, dict): return flat(x.get("search_result") or x.get("text") or "")
            return [t for y in (x or []) for t in flat(y)]
        return "\n".join(flat(res))
    if COND == "everos":
        d = retry(lambda: ev_post("/api/v2/memory/search", {"user_id": "team", "app_id": "default", "project_id": f"{NS}-{g['id']}", "query": q[:1500], "method": "hybrid", "top_k": TOPK}))["data"]
        out = []
        for e in d.get("episodes") or []:
            facts = [f["content"] for f in e.get("atomic_facts") or []]
            out.append("- " + (e.get("episode") or e.get("summary") or "") + ("".join("\n  - " + f for f in facts) if facts else ""))
        out += ["- " + json.dumps(x, ensure_ascii=False)[:600] for x in (d.get("profiles") or [])]
        return "\n".join(out)
    if COND == "hindsight":
        res = retry(lambda: H().recall(bank_id=f"{NS}-{g['id']}", query=q[:1500], max_tokens=1500)); items = getattr(res, "results", None) or []
        return "\n".join("- " + (getattr(x, "text", None) or (x.get("text") if isinstance(x, dict) else str(x))) for x in items)

# ───────────────────────────── 测试任务 ─────────────────────────────
def run_test(g, slot, st):
    d = f"{RD}/runs/{COND}/{g['id']}/{slot}"; rf = f"{d}/result.json"
    old = json.load(open(rf)) if os.path.exists(rf) else None
    if REPLAY:                                          # 只重放记忆的写入和检索来计量 token，不重跑 agent
        mem_query(g, slot, st, g["slots"][slot]["text"]); return old
    if old and not (RETRY and old.get("timed_out") and not old.get("retried")): return old
    if old: shutil.copy(rf, f"{RD}/runs/{COND}/{g['id']}/{slot}.timeout1.json")
    shutil.rmtree(d, ignore_errors=True); ws, home = f"{d}/ws", f"{d}/home"; os.makedirs(ws); os.makedirs(home)
    repo = g["repo"]; s = g["slots"][slot]; shutil.copytree(clean_dir(repo), f"{ws}/{repo}", symlinks=True); open(f"{home}/config.toml", "w").write(CODEX_CONFIG.format(model=MODEL))
    inject = old["inject"] if old else (mem_query(g, slot, st, s["text"]) or "")[:7000]
    block = ("Before you start, here is what the team's shared memory returned for this task (retrieved automatically from earlier sessions of team members; it can be incomplete, "
             f"and not everything in it need apply to you):\n<team_memory>\n{inject}\n</team_memory>\n\n") if inject else ""
    note = (f"\n\n(Environment: the project is in /workspace/team/{repo}; run tests from there with `python -m pytest <path>`. Add tests for what you build. Don't commit. "
            "Follow the team's current conventions for this repository.)")
    msg = block + f"I'm {s['name']}. " + s["text"] + note
    tid, reply, to = codex_call(["--json", "--skip-git-repo-check", msg], f"{d}/turn.jsonl", [(ws, "/workspace/team"), (home, "/agent_home")], f"/workspace/team/{repo}", KEY,
                                f"c2_{COND}_{g['id']}_{slot}_{os.getpid()}", timeout=1500)
    files = [l[3:].strip() for l in sh("git status --porcelain -uall", f"{ws}/{repo}").stdout.splitlines() if l.strip()]
    sh("git add -A -N . && git diff > ../../patch.diff", f"{ws}/{repo}")
    verdict = judge_all(repo, clean_dir(repo), f"{ws}/{repo}", PKG[repo], g["norms"])
    web = open(f"{d}/turn.jsonl", errors="replace").read().count('"web_search')
    res = {"group": g["id"], "slot": slot, "cond": COND, "inject": inject, "reply": reply, "files": files, "verdict": verdict, "timed_out": to, "web_search": web, "retried": bool(old)}
    shutil.rmtree(home, ignore_errors=True); shutil.rmtree(f"{ws}/{repo}/.git", ignore_errors=True)
    if files or reply: json.dump(res, open(rf, "w"), ensure_ascii=False, indent=1)
    elif old: os.makedirs(d, exist_ok=True); res = dict(old, retried=True, retry_empty=True); json.dump(res, open(rf, "w"), ensure_ascii=False, indent=1)   # 重跑什么都没交：保留第一次的结果
    print(COND, g["id"], slot, "files", len(files), "TIMEOUT" if to else "", flush=True)
    return res
def session_of(g, slot, st):
    if slot in ("T1", "T2", "T5"): p = prior(g)[slot]; return p["user"], p["assistant"]
    t = st["tests"][slot]; return g["slots"][slot]["text"], (t["reply"] or "") + ("\nFiles changed: " + ", ".join(t["files"][:12]) if t["files"] else "")
def advance(g):
    sf = f"{RD}/state{'_replay' if REPLAY else ''}/{COND}/{g['id']}.json"; os.makedirs(os.path.dirname(sf), exist_ok=True)
    st = json.load(open(sf)) if os.path.exists(sf) else {"step": 0, "tests": {}}
    try:
        if COND == "langmem" and st["step"]:
            for i in range(st["step"]):
                k_, sl_ = STEPS[i].split(":")
                if k_ == "w": mem_write(g, sl_, st, *session_of(g, sl_, st))
        while st["step"] < len(STEPS):
            kind, slot = STEPS[st["step"]].split(":")
            if kind == "w": mem_write(g, slot, st, *session_of(g, slot, st))
            else: st["tests"][slot] = run_test(g, slot, st)
            st["step"] += 1; json.dump(st, open(sf + ".tmp", "w"), ensure_ascii=False); os.replace(sf + ".tmp", sf)
    except Exception as e:
        print("ERROR", COND, g["id"], STEPS[st["step"]], repr(e)[:300], flush=True); return "error"
    return "done"
if RETRY:                                              # 只重做超时的测试任务
    todo = [(g, sl) for g in GROUPS for sl in TESTS if os.path.exists(f"{RD}/runs/{COND}/{g['id']}/{sl}/result.json")
            and (lambda r: r.get("timed_out") and not r.get("retried"))(json.load(open(f"{RD}/runs/{COND}/{g['id']}/{sl}/result.json")))]
    print("retry", COND, len(todo), flush=True)
    with ThreadPoolExecutor(W) as ex: list(ex.map(lambda a: run_test(a[0], a[1], {}), todo))
elif COND in ("none", "oracle"):                         # 题与题之间没有依赖，全部并行
    with ThreadPoolExecutor(W) as ex: list(ex.map(lambda a: run_test(a[0], a[1], {}), [(g, s) for g in GROUPS for s in TESTS]))
else:
    with ThreadPoolExecutor(W) as ex: print(list(ex.map(advance, GROUPS)), flush=True)
if HS["srv"]: HS["srv"].terminate()
print("ALL DONE", COND, flush=True)
