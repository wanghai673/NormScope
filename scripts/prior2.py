"""生成一组的前序会话：维护者 Alex 和自己的 agent 的一个连续会话，依次做 T1、T2、T5（在隔离容器里真实执行）。
冻结后所有对照组看到的内容相同。用法：python3 prior2.py <round> [并发=16]"""
import json, os, shutil, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
from common import CODEX_CONFIG, clean_dir, api_key, codex_call
RN = sys.argv[1]; W = int(sys.argv[2]) if len(sys.argv) > 2 else 16; RD = f"{ROOT}/work/{RN}"; KEY = api_key(2); MODEL = "deepseek-v4.1-flash"
groups = json.load(open(f"{RD}/groups.json")); os.makedirs(f"{RD}/prior", exist_ok=True)
def run(g):
    out = f"{RD}/prior/{g['id']}.json"
    if os.path.exists(out): return
    d = f"{RD}/prior/{g['id']}"; shutil.rmtree(d, ignore_errors=True); ws, home = f"{d}/ws", f"{d}/home"; os.makedirs(ws); os.makedirs(home)
    repo = g["repo"]; shutil.copytree(clean_dir(repo), f"{ws}/{repo}", symlinks=True); open(f"{home}/config.toml", "w").write(CODEX_CONFIG.format(model=MODEL))
    note = f"\n\n(Environment: the project is in /workspace/team/{repo}; run tests from there with `python -m pytest <path>`. Add tests for what you build. Don't commit.)"
    tid, res = None, {}
    for i, slot in enumerate(("T1", "T2", "T5")):
        msg = g["prior_msgs"][slot] + (note if i == 0 else "")
        args = (["resume", tid] if tid else []) + ["--json", "--skip-git-repo-check", msg]
        t, reply, to = codex_call(args, f"{d}/{slot}.jsonl", [(ws, "/workspace/team"), (home, "/agent_home")], f"/workspace/team/{repo}", KEY, f"c2p_{g['id']}_{slot}_{os.getpid()}", timeout=1800)
        tid = tid or t; res[slot] = {"user": g["prior_msgs"][slot], "assistant": reply, "timed_out": to}
        if not tid: break
    shutil.rmtree(home, ignore_errors=True)
    if len(res) == 3 and all(v["assistant"] for v in res.values()): json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print(g["id"], "ok" if os.path.exists(out) else "FAILED", flush=True)
with ThreadPoolExecutor(W) as ex: list(ex.map(run, groups))
print("ALL DONE", flush=True)
