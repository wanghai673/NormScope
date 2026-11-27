"""命令行入口：python -m normscope <命令>"""
import argparse, json, os, runpy, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)


def cmd_leaderboard(a):
    import scoring
    splits = [a.split] if a.split else scoring.SPLITS
    pts = [p for s in splits for p in scoring.load_points(s, work=a.work)]
    print(f"NormScope · {' + '.join(splits)} · {len({p['group'] for p in pts})} 组 · {'本地运行结果 work/' if a.work else '仓库发布的运行记录 results/'}\n")
    print(scoring.leaderboard(pts, details=a.details))


def cmd_show(a):
    g = next(x for x in json.load(open(f"{ROOT}/data/{a.split}/groups.json")) if x["id"] == a.group)
    from norms import NORM
    print(f"组 {g['id']} · 仓库 {g['repo']}\n\n本组的规范（CD = 先正式修改后个人破例，DC = 相反）")
    for n, o in g["order"].items(): print(f"  [{n} · {o}] 原规范: {NORM[n]['old']}\n{' ' * (len(n) + 9)}新规范: {NORM[n]['new']}")
    for s in ("T1", "T2", "T3", "T4", "T5", "T6", "T7"):
        v = g["slots"][s]; judged = s in ("T3", "T4", "T6", "T7")
        print(f"\n── {s} · {v['name']} · {'成员的任务（判分）' if judged else '维护者的会话'} " + "─" * 30)
        print(v["text"] if judged else g["prior_msgs"][s])


def cmd_check(a):
    from norms import NORM, judge_all
    norms = a.norms.split(",") if a.norms else [n for n, v in NORM.items() if a.repo in v["repos"]]
    for n, v in judge_all(a.repo, a.base, a.after, a.pkg or {"click": "src/click", "jinja": "src/jinja2"}[a.repo], norms).items():
        print(f"{n:10s} " + ("未触发" if not v["trig"] else "符合原规范" if v["old"] else "符合新规范" if v["new"] else "两者都不符合"))


def cmd_selftest(a):
    sys.argv = ["norms.py"]; runpy.run_path(f"{HERE}/norms.py", run_name="__main__")


def cmd_run(a):
    sys.argv = ["run_system.py", a.split, a.system, str(a.workers)]; runpy.run_path(f"{HERE}/run_system.py", run_name="__main__")


def main():
    ap = argparse.ArgumentParser(prog="normscope", description="NormScope：评测记忆系统能否把当时生效的团队规范送到后来者手里")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("leaderboard", help="判分并打印排行榜"); p.add_argument("--split", choices=["split_a", "split_b"]); p.add_argument("--details", action="store_true", help="同时打印按情形、按规范的明细")
    p.add_argument("--work", action="store_true", help="读自己跑出来的 work/ 而不是仓库发布的 results/"); p.set_defaults(f=cmd_leaderboard)
    p = sub.add_parser("show", help="查看一组题目：规范、维护者说的话、成员的任务"); p.add_argument("--split", default="split_a"); p.add_argument("--group", default="C1"); p.set_defaults(f=cmd_show)
    p = sub.add_parser("check", help="判定一次代码改动符合哪一版规范"); p.add_argument("--repo", required=True, choices=["click", "jinja"]); p.add_argument("--base", required=True, help="改动前的仓库目录")
    p.add_argument("--after", required=True, help="改动后的仓库目录"); p.add_argument("--pkg", help="包的相对路径，默认按仓库取"); p.add_argument("--norms", help="逗号分隔的规范编号，默认该仓库的全部"); p.set_defaults(f=cmd_check)
    p = sub.add_parser("selftest", help="检查脚本自测"); p.set_defaults(f=cmd_selftest)
    p = sub.add_parser("run", help="在一批数据上跑一个记忆系统（需要自备运行环境）"); p.add_argument("--split", required=True); p.add_argument("--system", required=True); p.add_argument("--workers", type=int, default=16); p.set_defaults(f=cmd_run)
    a = ap.parse_args(); a.f(a)


if __name__ == "__main__":
    main()
