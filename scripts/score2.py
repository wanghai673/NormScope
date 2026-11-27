"""第 2 批判分：每个判分点 =（测试任务，约束）。检查脚本在 agent 交的代码上判出是否符合原规范 / 新规范，和当时生效的那一版比。
实验 A = 这道题之前最近一次事件是正式修改（要跟上新规范）；实验 B = 最近一次事件是个人违背（要守住团队规范）。
遵守率 = A、B 两类各自的遵守率取平均；整条链全对 = 一条约束在一组里的 4 个测试任务全对（没触发的不算，至少要有 2 个触发）。
用法：python3 -I score2.py <round>"""
import glob, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); RN = sys.argv[1]; RD = f"{ROOT}/work/{RN}"
LOCAL = os.path.isdir(RD)                              # 自己跑出来的结果在 work/<round>；否则复核仓库里发布的 results/<round>/runs.jsonl
if not LOCAL: RD = f"{ROOT}/results/{RN}"
G = {g["id"]: g for g in json.load(open(f"{RD}/groups.json" if LOCAL else f"{ROOT}/data/{RN}/groups.json"))}; CONDS = ["none", "raw", "mem0", "hindsight", "everos", "graphiti", "langmem", "cognee", "oracle"]
NAME = {"none": "无记忆", "raw": "RAG（原话检索）", "mem0": "Mem0", "hindsight": "Hindsight", "everos": "EverOS", "graphiti": "Graphiti（Zep 的开源核心）", "langmem": "LangMem", "cognee": "Cognee", "oracle": "理想送达（上限）"}
KIND = {"N": "没给原因的一次性指令", "H": "个人习惯", "E": "个人环境", "S": "有情境原因的一次性安排"}
rows = []
RUNS = [json.load(open(f)) for f in glob.glob(f"{RD}/runs/*/*/*/result.json")] if LOCAL else [json.loads(l) for l in open(f"{RD}/runs.jsonl")]
for r in RUNS:
    g = G[r["group"]]; slot = r["slot"]
    for nid, order in g["order"].items():
        v = r["verdict"][nid]; rule = "new" if order == "CD" else ("old" if slot in ("T3", "T4") else "new")
        exp = ("A" if slot in ("T3", "T4") else "B") if order == "CD" else ("B" if slot in ("T3", "T4") else "A")
        rows.append({"cond": r["cond"], "group": r["group"], "repo": g["repo"], "slot": slot, "norm": nid, "order": order, "rule": rule, "exp": exp, "stage": 1 if slot in ("T3", "T4") else 2,
                     "trig": v["trig"] and bool(r["files"]), "old": v["old"], "new": v["new"], "ok": v[rule], "other": v["old" if rule == "new" else "new"],
                     "dev_kind": g["dev_kind"][nid] if exp == "B" else None, "empty": not r["files"]})
json.dump(rows, open(f"{RD}/rows.json", "w"), ensure_ascii=False)
def rate(rs): rs = [r for r in rs if r["trig"]]; return (sum(r["ok"] for r in rs) / len(rs), len(rs)) if rs else (None, 0)
def bal(rs):
    a, b = rate([r for r in rs if r["exp"] == "A"])[0], rate([r for r in rs if r["exp"] == "B"])[0]
    return None if a is None or b is None else (a + b) / 2
def chains(rs):
    c = {}
    for r in rs:
        if r["trig"]: c.setdefault((r["group"], r["norm"]), []).append(r["ok"])
    c = [all(v) for v in c.values() if len(v) >= 2]; return (sum(c) / len(c), len(c)) if c else (None, 0)
def ci(rs, f, n=1000):
    gs = sorted({r["group"] for r in rs}); by = {g: [r for r in rs if r["group"] == g] for g in gs}; rnd = random.Random(1); xs = []
    for _ in range(n):
        v = f([r for g in (rnd.choice(gs) for _ in gs) for r in by[g]])
        if v is not None: xs.append(v)
    xs.sort(); return (xs[int(.025 * len(xs))], xs[int(.975 * len(xs))]) if xs else (None, None)
p = lambda x: "—" if x is None else f"{x:.0%}"
out = [f"# {RN} 结果\n", "## 主表\n", "| 对照组 | 遵守率 | 95% 区间 | 整条链全对 | 判分点 | 完成的任务 | 空交付 |", "|---|---|---|---|---|---|---|"]
summary = {}
for c in CONDS:
    rs = [r for r in rows if r["cond"] == c]
    if not rs: continue
    lo, hi = ci(rs, bal); ch, nch = chains(rs); ntask = len({(r["group"], r["slot"]) for r in rs}); nempty = len({(r["group"], r["slot"]) for r in rs if r["empty"]})
    summary[c] = {"compliance": bal(rs), "ci": [lo, hi], "chain": ch, "chains": nch, "points": sum(r["trig"] for r in rs), "tasks": ntask}
    out.append(f"| {NAME[c]} | {p(bal(rs))} | {p(lo)}–{p(hi)} | {p(ch)}（{nch} 条） | {sum(r['trig'] for r in rs)} | {ntask} / {4 * len(G)} | {nempty} |")
out += ["\n## 实验 A（正式修改后要跟上）和实验 B（个人违背后要守住）\n", "| 对照组 | A 遵守 | A 还在按旧规范 | B 守住 | B 被带到另一种做法 | 第一次变化后 | 第二次变化后 |", "|---|---|---|---|---|---|---|"]
for c in CONDS:
    rs = [r for r in rows if r["cond"] == c and r["trig"]]
    if not rs: continue
    A = [r for r in rs if r["exp"] == "A"]; B = [r for r in rs if r["exp"] == "B"]; dr = lambda L: p(sum(r["other"] for r in L) / len(L)) if L else "—"
    out.append(f"| {NAME[c]} | {p(rate(A)[0])}（{len(A)}） | {dr(A)} | {p(rate(B)[0])}（{len(B)}） | {dr(B)} | {p(bal([r for r in rs if r['stage'] == 1]))} | {p(bal([r for r in rs if r['stage'] == 2]))} |")
out += ["\n## 实验 B 按违背的情形分开（守住的比例，括号里是判分点数）\n", "| 对照组 | " + " | ".join(KIND.values()) + " |", "|---|" + "---|" * len(KIND)]
for c in CONDS:
    rs = [r for r in rows if r["cond"] == c and r["trig"] and r["exp"] == "B"]
    if rs: out.append(f"| {NAME[c]} | " + " | ".join((lambda L: f"{p(rate(L)[0])}（{len(L)}）")([r for r in rs if r["dev_kind"] == k]) for k in KIND) + " |")
norms = sorted({r["norm"] for r in rows})
out += ["\n## 每条约束的遵守率（A / B，括号里是判分点数）\n", "| 对照组 | " + " | ".join(norms) + " |", "|---|" + "---|" * len(norms)]
for c in CONDS:
    rs = [r for r in rows if r["cond"] == c and r["trig"]]
    if rs: out.append(f"| {NAME[c]} | " + " | ".join((lambda L: f"{p(rate([r for r in L if r['exp'] == 'A'])[0])} / {p(rate([r for r in L if r['exp'] == 'B'])[0])}（{len(L)}）")([r for r in rs if r["norm"] == n]) for n in norms) + " |")
out += ["\n## 正确做法是原规范的题（先违背后改的 T3、T4）：不给记忆时本来会不会照做\n", "| 对照组 | " + " | ".join(norms) + " |", "|---|" + "---|" * len(norms)]
for c in CONDS:
    rs = [r for r in rows if r["cond"] == c and r["trig"] and r["rule"] == "old"]
    if rs: out.append(f"| {NAME[c]} | " + " | ".join((lambda L: f"{p(rate(L)[0])}（{len(L)}）")([r for r in rs if r["norm"] == n]) for n in norms) + " |")
open(f"{RD}/summary.md", "w").write("\n".join(out) + "\n"); json.dump(summary, open(f"{RD}/summary.json", "w"), ensure_ascii=False, indent=1)
print("\n".join(out))
