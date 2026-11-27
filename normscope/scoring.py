"""判分与汇总。一个判分点 =（测试任务，规范）；检查脚本的判定和当时生效的那一版规范比对。"""
import glob, json, os, random
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLITS = ["split_a", "split_b"]
SYSTEMS = {"oracle": "理想送达（上限）", "everos": "EverOS", "langmem": "LangMem", "raw": "RAG（原话检索）", "hindsight": "Hindsight",
           "cognee": "Cognee", "mem0": "Mem0", "graphiti": "Graphiti", "none": "无记忆（下限）"}
KIND = {"N": "没给原因的一次性指令", "H": "个人习惯", "E": "个人环境", "S": "有情境原因的一次性安排"}


def load_points(split, work=False):
    """读一批数据的运行记录，展开成判分点。work=True 读自己跑出来的 work/<split>，否则读仓库发布的 results/<split>。"""
    groups = {g["id"]: g for g in json.load(open(f"{ROOT}/data/{split}/groups.json"))}
    if work:
        runs = [json.load(open(f)) for f in glob.glob(f"{ROOT}/work/{split}/runs/*/*/*/result.json")]
    else:
        runs = [json.loads(l) for l in open(f"{ROOT}/results/{split}/runs.jsonl")]
    pts = []
    for r in runs:
        g = groups[r["group"]]; first = r["slot"] in ("T3", "T4")
        for norm, order in g["order"].items():
            v = r["verdict"][norm]
            rule = "new" if order == "CD" or not first else "old"            # 当时生效的是哪一版
            kind = ("follow" if first else "hold") if order == "CD" else ("hold" if first else "follow")
            pts.append({"system": r["cond"], "group": f"{split}/{r['group']}", "slot": r["slot"], "norm": norm, "kind": kind, "stage": 1 if first else 2,
                        "scored": bool(v["trig"] and r["files"]), "ok": v[rule], "other": v["old" if rule == "new" else "new"],
                        "deviation": g["dev_kind"][norm] if kind == "hold" else None})
    return pts


def rate(pts):
    pts = [p for p in pts if p["scored"]]
    return sum(p["ok"] for p in pts) / len(pts) if pts else None


def compliance(pts):
    a, b = rate([p for p in pts if p["kind"] == "follow"]), rate([p for p in pts if p["kind"] == "hold"])
    return None if a is None or b is None else (a + b) / 2


def chain_rate(pts):
    c = {}
    for p in pts:
        if p["scored"]: c.setdefault((p["group"], p["norm"]), []).append(p["ok"])
    c = [all(v) for v in c.values() if len(v) >= 2]
    return (sum(c) / len(c), len(c)) if c else (None, 0)


def interval(pts, n=1000):
    """按组做自助法的 95% 区间。"""
    gs = sorted({p["group"] for p in pts}); by = {g: [p for p in pts if p["group"] == g] for g in gs}; rnd = random.Random(1); xs = []
    for _ in range(n):
        v = compliance([p for g in (rnd.choice(gs) for _ in gs) for p in by[g]])
        if v is not None: xs.append(v)
    xs.sort()
    return (xs[int(.025 * len(xs))], xs[int(.975 * len(xs))]) if xs else (None, None)


def pct(x): return "—" if x is None else f"{x:.0%}"


def leaderboard(pts, details=False):
    out = ["| 系统 | 遵守率 | 95% 区间 | 整条链全对 | 跟上 | 守住 | 第一次变化后 | 第二次变化后 | 判分点 |", "|---|---|---|---|---|---|---|---|---|"]
    rows = []
    for s, name in SYSTEMS.items():
        P = [p for p in pts if p["system"] == s]
        if not P: continue
        lo, hi = interval(P); ch, _n = chain_rate(P); S = [p for p in P if p["scored"]]
        rows.append((compliance(P) or 0, f"| {name} | {pct(compliance(P))} | {pct(lo)}–{pct(hi)} | {pct(ch)} | {pct(rate([p for p in S if p['kind'] == 'follow']))} | "
                     f"{pct(rate([p for p in S if p['kind'] == 'hold']))} | {pct(compliance([p for p in S if p['stage'] == 1]))} | {pct(compliance([p for p in S if p['stage'] == 2]))} | {len(S)} |"))
    out += [r for _v, r in sorted(rows, key=lambda x: -x[0])]
    if details:
        out += ["", "守住：按个人破例的情形分开（括号里是判分点数）", "", "| 系统 | " + " | ".join(KIND.values()) + " |", "|---|" + "---|" * len(KIND)]
        for s, name in SYSTEMS.items():
            P = [p for p in pts if p["system"] == s and p["scored"] and p["kind"] == "hold"]
            if P: out.append(f"| {name} | " + " | ".join((lambda L: f"{pct(rate(L))}（{len(L)}）")([p for p in P if p["deviation"] == k]) for k in KIND) + " |")
        norms = sorted({p["norm"] for p in pts})
        out += ["", "每条规范：跟上 / 守住", "", "| 系统 | " + " | ".join(norms) + " |", "|---|" + "---|" * len(norms)]
        for s, name in SYSTEMS.items():
            P = [p for p in pts if p["system"] == s and p["scored"]]
            if P: out.append(f"| {name} | " + " | ".join((lambda L: f"{pct(rate([p for p in L if p['kind'] == 'follow']))} / {pct(rate([p for p in L if p['kind'] == 'hold']))}")([p for p in P if p["norm"] == n]) for n in norms) + " |")
    return "\n".join(out)
