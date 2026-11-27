"""回读检查（第 2 批）：三个不同厂商的模型各自只看一句话，判断它对团队其他成员意味着什么；三家都和设计一致才通过。"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, f"{ROOT}/norms"); sys.path.insert(0, "/path/to/pilot/scripts")
from llm import chat
from norms2 import NORMS
MODELS = ["claude-sonnet-5-5", "gpt-5.4", "qwen3.8-max"]; jobs = []
ONLY = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None; RN = sys.argv[1] if len(sys.argv) > 1 else "c2"
for n in NORMS:
    if ONLY and n["id"] not in ONLY: continue
    jobs.append((n["id"], "establish", n["establish"], "team_rule")); jobs.append((n["id"], "change", n["change"], "team_rule"))
    for k in ("dev_old", "dev_new"):
        for i, (kind, text) in enumerate(n[k]): jobs.append((n["id"], f"{k}{i}({kind})", text, "own_work_only"))
Q = """A maintainer of a small software team says this to their own coding agent while giving it a task (every team member works separately with their own agent):

"{text}"

For the OTHER members of the team and their later work, what does this sentence mean? Choose one:
- team_rule: it states or changes how everyone on the team is expected to do this from now on
- own_work_only: it only concerns the speaker's own current task, branch, machine or habits; it changes nothing for the others
- not_decided: it is an idea or proposal that has not been adopted
JSON only: {{"meaning": "..."}}"""
def ask(a):
    j, m = a
    try:
        txt, _u = chat(m, Q.format(text=j[2]), max_tokens=3000, timeout=300); return json.loads(re.search(r"\{.*\}", txt, re.S).group(0)).get("meaning")
    except Exception as e: return "error"
pairs = [(j, m) for j in jobs for m in MODELS]
with ThreadPoolExecutor(24) as ex: res = list(ex.map(ask, pairs))
out = []
for i, j in enumerate(jobs):
    ans = dict(zip(MODELS, res[i * len(MODELS):(i + 1) * len(MODELS)])); ok = all(a == j[3] for a in ans.values())
    out.append({"norm": j[0], "kind": j[1], "text": j[2], "expect": j[3], "answers": ans, "ok": ok})
    print("ok  " if ok else "FAIL", j[0], j[1], "" if ok else ans, flush=True)
json.dump(out, open(f"{ROOT}/work/{RN}/readback.json", "w"), ensure_ascii=False, indent=1)
print("通过", sum(o["ok"] for o in out), "/", len(out))
