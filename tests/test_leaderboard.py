"""回归测试：用仓库发布的运行记录重新判分，结果必须和发布的排行榜一致。运行：python3 tests/test_leaderboard.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "normscope"))
import scoring
# 系统: (遵守率, 整条链全对, 跟上, 守住)，百分数四舍五入
EXPECTED = {"oracle": (99, 96, 100, 98), "everos": (54, 13, 85, 22), "langmem": (49, 19, 50, 48), "raw": (44, 8, 50, 39), "hindsight": (42, 4, 32, 52),
            "cognee": (38, 4, 29, 46), "mem0": (37, 6, 30, 44), "graphiti": (25, 4, 14, 37), "none": (23, 4, 6, 41)}
pts = [p for s in scoring.SPLITS for p in scoring.load_points(s)]
bad = 0
for system, want in EXPECTED.items():
    P = [p for p in pts if p["system"] == system]; S = [p for p in P if p["scored"]]
    got = tuple(round(100 * x) for x in (scoring.compliance(P), scoring.chain_rate(P)[0], scoring.rate([p for p in S if p["kind"] == "follow"]), scoring.rate([p for p in S if p["kind"] == "hold"])))
    ok = got == want; bad += not ok
    print("ok  " if ok else "FAIL", f"{system:10s}", got, "" if ok else f"期望 {want}")
print("groups", len({p["group"] for p in pts}), "| bad", bad)
sys.exit(1 if bad else 0)
