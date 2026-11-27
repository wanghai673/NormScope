"""第 2 批（c2）排组，流程照 B 评测：每组 7 个任务，T1/T2/T5 是维护者 Alex 的前序会话，T3/T6 由 Blake 做、T4/T7 由 Casey 做并判分。
每条约束在一组里是一条链：CD = T2 正式修改、T5 个人违背新规范；DC = T2 个人违背原规范、T5 正式修改。组内两种顺序各半，相邻组互换。
任务取自原机制库的提案（只读）；会触发更多约束的任务优先排到测试位。
用法：python3 -I build2.py     输出 rounds/c2/groups.json"""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, f"{ROOT}/normscope")
from norms import NORM, DISTRACTORS
P = "/path/to/pilot"; RN = os.environ.get("ROUND", "c2"); SET = os.environ.get("NORMSET", "1"); RD = f"{ROOT}/work/{RN}"; os.makedirs(RD, exist_ok=True); rnd = random.Random({"1": 20261126, "2": 7}.get(SET, 11))
SLOTS = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]; WHO = {"T1": "A", "T2": "A", "T3": "B", "T4": "C", "T5": "A", "T6": "B", "T7": "C"}
NAMES = {"A": "Alex", "B": "Blake", "C": "Casey"}; NGROUPS = {"click": 7, "jinja": 9}
rows = json.load(open(f"{ROOT}/work/stage0/natural_rows.json")); groups = []
for repo, ng in NGROUPS.items():
    tasks = []
    for r in rows:
        if r["repo"] != repo or "/verify/" not in r["work"]: continue
        tag, side = r["work"].split("/verify/")[1].split("/")[:2]; pr = json.load(open(f"{P}/libs/{repo}/proposals/{tag}.json"))
        res = r["res"]; trig = {k: isinstance(res[k], list) for k in ("versionadded", "keyword_only_params", "lazy_import", "private_helpers")}
        tasks.append({"task": f"{tag}/{side}", "repo": repo, "text": pr["provider_direct"] if side == "p" else pr["dependent_turn1"], "nat": trig, "score": sum(trig.values())})
    rnd.shuffle(tasks); tasks.sort(key=lambda t: -t["score"])
    test, prior = tasks[:4 * ng], tasks[4 * ng:4 * ng + 3 * ng]
    for gi in range(ng):
        tt = test[gi::ng]; pp = prior[gi::ng]; rnd.shuffle(tt)                 # 轮流分，保证每组都有会触发的任务
        slots = dict(zip(["T3", "T4", "T6", "T7"], tt)); slots.update(zip(["T1", "T2", "T5"], pp))
        gno = len(groups); gid = f"{repo[0].upper()}{gi + 1}" + {"1": "", "2": "x"}.get(SET, "y"); v = gno % 2
        if SET == "1":
            norms = ["CHG", f"TS_{repo}", "TF", "VN", "DS"]
            if sum(t["nat"]["keyword_only_params"] for t in tt) >= 2: norms.append("KW")
            if sum(t["nat"]["lazy_import"] for t in tt) >= 2: norms.append("IM")
        elif SET == "2": norms = ["TA", "TD", "EXP", "DOC", "PD"]
        else: norms = ["TA2", "TD2", "EXP2", "DOC", "PD2"]
        order = {n: ("CD" if (i + gno) % 2 == 0 else "DC") for i, n in enumerate(norms)}
        def para(stmts, ndis):
            ps = list(stmts) + rnd.sample(DISTRACTORS, ndis); rnd.shuffle(ps); return ps
        est = para([NORM[n]["establish"] for n in norms], 1)
        t2 = para([NORM[n]["change"] if o == "CD" else NORM[n]["dev_old"][v][1] for n, o in order.items()], 2)
        t5 = para([NORM[n]["dev_new"][v][1] if o == "CD" else NORM[n]["change"] for n, o in order.items()], 2)
        dev = {n: (NORM[n]["dev_new"][v][0] if o == "CD" else NORM[n]["dev_old"][v][0]) for n, o in order.items()}
        prior_msgs = {"T1": "A few things about how we work in this repo, before you start.\n\n" + "\n\n".join(est) + "\n\nNow the task. " + slots["T1"]["text"],
                      "T2": "\n\n".join(t2[:len(t2) // 2]) + "\n\nThe task: " + slots["T2"]["text"] + "\n\n" + "\n\n".join(t2[len(t2) // 2:]),
                      "T5": "\n\n".join(t5[:len(t5) // 2]) + "\n\nThe task: " + slots["T5"]["text"] + "\n\n" + "\n\n".join(t5[len(t5) // 2:])}
        groups.append({"id": gid, "repo": repo, "variant": v, "norms": norms, "order": order, "dev_kind": dev,
                       "slots": {s: {"task": slots[s]["task"], "member": WHO[s], "name": NAMES[WHO[s]], "date": f"2026-03-{SLOTS.index(s) + 2:02d}", "text": slots[s]["text"], "nat": slots[s]["nat"]} for s in SLOTS},
                       "prior_msgs": prior_msgs})
json.dump(groups, open(f"{RD}/groups.json", "w"), ensure_ascii=False, indent=1)
print("组", len(groups), "链", sum(len(g["norms"]) for g in groups), "测试任务", 4 * len(groups), "判分点上限", sum(4 * len(g["norms"]) for g in groups))
for g in groups: print(g["id"], g["norms"][5:], "".join(o[0] for o in g["order"].values()), [sum(g["slots"][s]["nat"].values()) for s in ("T3", "T4", "T6", "T7")])
