"""团队约束的检查脚本：比较一个仓库的起点目录和某次工作结束后的目录，判断这次工作是否违反某条约束。

每个检查函数返回：
  None            这次工作没有碰到这条约束（不触发，不出题）
  []              碰到了，并且合规
  ["...", ...]    碰到了，并且违反；列表里是具体位置
只解析文件，不执行被检查的代码。
用法：python3 -I checkers.py <起点目录> <结束目录> <包的相对路径，如 src/click>
"""
import ast, json, os, sys

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "build", "dist", ".tox", "docs", "examples", "node_modules", ".venv"}


def py_files(root, sub):
    out = {}
    base = os.path.join(root, sub)
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(d, f)
                try:
                    out[os.path.relpath(p, root)] = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    pass
    return out


def parse(src):
    try:
        return ast.parse(src)
    except SyntaxError:
        return None


def defs(tree):
    """限定名 -> 函数或类节点（模块级，以及类里的方法；不进函数内部）。"""
    out = {}

    def walk(body, prefix):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + n.name] = n
            elif isinstance(n, ast.ClassDef):
                out[prefix + n.name] = n
                walk(n.body, prefix + n.name + ".")
            elif isinstance(n, (ast.If, ast.Try)):
                walk(getattr(n, "body", []), prefix)
                walk(getattr(n, "orelse", []), prefix)
    if tree:
        walk(tree.body, "")
    return out


def is_public(qual):
    return not any(p.startswith("_") and not (p.startswith("__") and p.endswith("__")) for p in qual.split("."))


def is_func(n):
    return isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))


def params(fn):
    a = fn.args
    pos = [x.arg for x in getattr(a, "posonlyargs", [])] + [x.arg for x in a.args]
    return pos, [x.arg for x in a.kwonlyargs]


def defaults(fn):
    a = fn.args
    pos = [x.arg for x in getattr(a, "posonlyargs", [])] + [x.arg for x in a.args]
    out = {}
    for name, d in zip(pos[len(pos) - len(a.defaults):], a.defaults):
        out[name] = ast.dump(d)
    for x, d in zip(a.kwonlyargs, a.kw_defaults):
        if d is not None:
            out[x.arg] = ast.dump(d)
    return out


def dump_no_doc(fn):
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
        body = body[1:]
    return "".join(ast.dump(b) for b in body) + ast.dump(fn.args)


class Work:
    """一次工作的前后对比。"""

    def __init__(self, base, final, pkg):
        self.base, self.final, self.pkg = base, final, pkg.rstrip("/")
        self.b_src, self.f_src = py_files(base, self.pkg), py_files(final, self.pkg)
        self.b_tst, self.f_tst = py_files(base, "tests"), py_files(final, "tests")
        self.b_tree = {p: parse(s) for p, s in self.b_src.items()}
        self.f_tree = {p: parse(s) for p, s in self.f_src.items()}
        self.src_changed = sorted(p for p in self.f_src if self.f_src[p] != self.b_src.get(p))

    def read(self, root, rel):
        try:
            return open(os.path.join(root, rel), encoding="utf-8", errors="replace").read()
        except OSError:
            return ""

    def src_defs(self):
        """[(文件, 限定名, 起点节点或 None, 结束节点)]，只含新增或改动过的定义。"""
        out = []
        for p in self.src_changed:
            bd, fd = defs(self.b_tree.get(p)), defs(self.f_tree.get(p))
            for q, n in fd.items():
                if q not in bd or ast.dump(bd[q]) != ast.dump(n):
                    out.append((p, q, bd.get(q), n))
        return out

    def new_nodes(self, kind, where="src"):
        """结束目录里新出现的某类语法节点：[(文件, 所在函数限定名或 '', 节点)]。按 (所在定义, 节点内容) 的多重集合相减。"""
        res = []
        files = self.src_changed if where == "src" else sorted(p for p in self.f_tst if self.f_tst[p] != self.b_tst.get(p))
        for p in files:
            bt = self.b_tree.get(p) if where == "src" else parse(self.b_tst.get(p, ""))
            ft = self.f_tree.get(p) if where == "src" else parse(self.f_tst.get(p, ""))
            if ft is None:
                continue

            def collect(tree):
                items = []
                if tree is None:
                    return items

                def visit(node, owner):
                    for ch in ast.iter_child_nodes(node):
                        o = owner
                        if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            o = (owner + "." if owner else "") + ch.name
                        if isinstance(ch, kind):
                            items.append((o, ast.dump(ch), ch))
                        visit(ch, o)
                visit(tree, "")
                return items
            have = {}
            for o, d, _n in collect(bt):
                have[(o, d)] = have.get((o, d), 0) + 1
            for o, d, n in collect(ft):
                if have.get((o, d), 0) > 0:
                    have[(o, d)] -= 1
                else:
                    res.append((p, o, n))
        return res


# ───────────────────────────── 各条约束 ─────────────────────────────
def top_imports(tree):
    mods = set()
    for n in (tree.body if tree else []):
        for m in ([n] if isinstance(n, (ast.Import, ast.ImportFrom)) else
                  [x for x in ast.walk(n) if isinstance(x, (ast.Import, ast.ImportFrom))] if isinstance(n, (ast.If, ast.Try)) else []):
            if isinstance(m, ast.Import):
                mods |= {a.name.split(".")[0] for a in m.names}
            elif m.level == 0 and m.module:
                mods.add(m.module.split(".")[0])
    return mods


def lazy_import(w):
    """新用到的外部模块，import 要写在用到它的函数里，不加在模块顶层。"""
    hit, bad = False, []
    for p in w.src_changed:
        if w.f_tree[p] is None:
            continue
        before = top_imports(w.b_tree.get(p))
        ignore = {"typing", "__future__", "collections", w.pkg.split("/")[-1]}
        new_top = top_imports(w.f_tree[p]) - before - ignore
        inner = set()
        for fn in ast.walk(w.f_tree[p]):
            if is_func(fn):
                for m in ast.walk(fn):
                    if isinstance(m, ast.Import):
                        inner |= {a.name.split(".")[0] for a in m.names}
                    elif isinstance(m, ast.ImportFrom) and m.level == 0 and m.module:
                        inner.add(m.module.split(".")[0])
        inner_before = set()
        if w.b_tree.get(p):
            for fn in ast.walk(w.b_tree[p]):
                if is_func(fn):
                    for m in ast.walk(fn):
                        if isinstance(m, ast.Import):
                            inner_before |= {a.name.split(".")[0] for a in m.names}
                        elif isinstance(m, ast.ImportFrom) and m.level == 0 and m.module:
                            inner_before.add(m.module.split(".")[0])
        new_inner = inner - inner_before - before - ignore
        if new_top or new_inner:
            hit = True
        bad += [f"{p}: 顶层新增 import {m}" for m in sorted(new_top)]
    return bad if hit else None


RE_FUNCS = {"sub", "subn", "match", "search", "findall", "finditer", "split", "fullmatch", "compile"}


def regex_precompiled(w):
    """正则要预先编译成模块级常量，不在函数里现写 re.sub / re.match / re.compile。"""
    calls = [(p, o, n) for p, o, n in w.new_nodes(ast.Call)
             if isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == "re" and n.func.attr in RE_FUNCS]
    if not calls:
        return None
    bad = []
    for p, o, n in calls:
        fd = defs(w.f_tree[p])
        top = o.split(".")
        inside_func = any(is_func(fd.get(".".join(top[:i + 1]))) for i in range(len(top))) if o else False
        if inside_func:
            bad.append(f"{p}:{n.lineno} 在 {o} 里现写 re.{n.func.attr}")
    return bad


def changelog(w):
    """改了库的代码，要在 CHANGES.rst 里加一条。"""
    if not w.src_changed:
        return None
    return [] if w.read(w.final, "CHANGES.rst") != w.read(w.base, "CHANGES.rst") else ["CHANGES.rst 没有改动"]


def versionadded(w):
    """新增的公开函数、方法、类，以及给公开函数新加的参数，docstring 里要有 versionadded / versionchanged 标记。"""
    hit, bad = False, []
    for p, q, b, n in w.src_defs():
        if not is_public(q) or p.endswith("__init__.py"):
            continue
        doc = ast.get_docstring(n) or ""
        if b is None:
            if isinstance(n, ast.ClassDef) or is_func(n):
                if q.split(".")[-1].startswith("__"):
                    continue
                if "." in q and q.rsplit(".", 1)[0] not in defs(w.b_tree.get(p)):
                    continue        # 新类里的方法：由类自己的标记覆盖，只判这个类
                hit = True
                if "versionadded" not in doc:
                    bad.append(f"{p}: 新增 {q} 没有 versionadded")
        elif is_func(n) and is_func(b):
            new = set(sum(params(n), [])) - set(sum(params(b), []))
            if new:
                hit = True
                bdoc = ast.get_docstring(b) or ""
                if "." in q:            # 方法的新参数：标记写在所属类的 docstring 里也算（Pallets 的习惯写法）
                    owner = q.rsplit(".", 1)[0]
                    oc, ob = defs(w.f_tree[p]).get(owner), defs(w.b_tree.get(p)).get(owner)
                    doc += (ast.get_docstring(oc) or "") if oc is not None else ""
                    bdoc += (ast.get_docstring(ob) or "") if ob is not None else ""
                if doc.count("versionchanged") + doc.count("versionadded") <= bdoc.count("versionchanged") + bdoc.count("versionadded"):
                    bad.append(f"{p}: {q} 新增参数 {sorted(new)} 没有 versionchanged")
    return bad if hit else None


def _wrapped(arg):
    """消息是否包在 _() 里：_("...") 或 _("...").format(...) 或 _("...") % x。"""
    if isinstance(arg, ast.Call):
        f = arg.func
        if isinstance(f, ast.Name) and f.id in ("_", "ngettext", "gettext"):
            return True
        if isinstance(f, ast.Attribute) and f.attr == "format":
            return _wrapped(f.value)
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
        return _wrapped(arg.left)
    return False


def _is_text(arg):
    if isinstance(arg, ast.JoinedStr) or (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
        return True
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "format":
        return _is_text(arg.func.value)
    if isinstance(arg, ast.BinOp) and isinstance(arg.op, (ast.Mod, ast.Add)):
        return _is_text(arg.left)
    return False


def gettext_messages(w):
    """新写的报错文字要包在 _() 里，方便翻译。"""
    hit, bad = False, []
    calls = [(p, o, n, n.exc) for p, o, n in w.new_nodes(ast.Raise) if isinstance(n.exc, ast.Call)]
    calls += [(p, o, n, n) for p, o, n in w.new_nodes(ast.Call) if isinstance(n.func, ast.Attribute) and n.func.attr == "fail"]   # click 的 self.fail(...) / ctx.fail(...)
    for p, o, n, e in calls:
        if not e.args:
            continue
        a = e.args[0]
        if _wrapped(a):
            hit = True
        elif _is_text(a):
            hit = True
            bad.append(f"{p}:{n.lineno} {o or '模块级'} 的报错文字没有包 _()")
    return bad if hit else None


BUILTIN_EXC = {"ValueError", "TypeError", "RuntimeError", "KeyError", "Exception", "AttributeError", "IndexError", "LookupError", "AssertionError"}


def no_builtin_exceptions(w):
    """新写的 raise 不直接抛 Python 内置异常，用项目自己的异常类。"""
    hit, bad = False, []
    for p, o, n in w.new_nodes(ast.Raise):
        e = n.exc
        if e is None:
            continue
        name = e.func if isinstance(e, ast.Call) else e
        name = name.id if isinstance(name, ast.Name) else name.attr if isinstance(name, ast.Attribute) else ""
        if not name or name[:1].islower():
            continue
        hit = True
        if name in BUILTIN_EXC:
            bad.append(f"{p}:{n.lineno} {o or '模块级'} 抛出内置的 {name}")
    return bad if hit else None


def keyword_only_params(w):
    """给已有的公开函数加参数，新参数必须是只能按名字传的（放在 * 后面）。"""
    hit, bad = False, []
    for p, q, b, n in w.src_defs():
        if b is None or not is_func(n) or not is_func(b) or not is_public(q):
            continue
        bpos, bkw = params(b)
        npos, nkw = params(n)
        new = (set(npos) | set(nkw)) - (set(bpos) | set(bkw))
        if not new:
            continue
        hit = True
        pos_new = [x for x in npos if x in new]
        if pos_new:
            bad.append(f"{p}: {q} 新参数 {pos_new} 可以按位置传")
    return bad if hit else None


def _test_funcs(src):
    t = parse(src)
    return {q: n for q, n in defs(t).items() if is_func(n) and q.split(".")[-1].startswith("test")} if t else {}


def no_edit_existing_tests(w):
    """不改动、不删除已有的测试；行为变了就新增测试。"""
    if not w.src_changed:
        return None
    bad = []
    for p, s in w.b_tst.items():
        if w.f_tst.get(p) == s:
            continue
        old, new = _test_funcs(s), _test_funcs(w.f_tst.get(p, ""))
        for q, n in old.items():
            if q not in new:
                bad.append(f"{p}: 删除了已有测试 {q}")
            elif ast.dump(new[q]) != ast.dump(n):
                bad.append(f"{p}: 改动了已有测试 {q}")
    return bad


def _new_tests(w):
    out = []
    for p, s in w.f_tst.items():
        if s == w.b_tst.get(p):
            continue
        old = _test_funcs(w.b_tst.get(p, ""))
        out += [(p, q, n) for q, n in _test_funcs(s).items() if q not in old]
    return out


def no_new_test_files(w):
    """新测试加进已有的测试文件，不新建测试文件。"""
    if not _new_tests(w):
        return None
    return [f"新建了测试文件 {p}" for p in sorted(w.f_tst) if p not in w.b_tst and os.path.basename(p).startswith("test")]


def parametrize_tests(w):
    """新测试不在循环里写 assert，多组输入用 pytest.mark.parametrize。"""
    nt = _new_tests(w)
    if not nt:
        return None
    bad = []
    for p, q, n in nt:
        for x in ast.walk(n):
            if isinstance(x, (ast.For, ast.While)) and any(isinstance(y, ast.Assert) for y in ast.walk(x)):
                bad.append(f"{p}: {q} 在循环里写 assert")
                break
    return bad


def deprecate_default_change(w):
    """改公开函数某个参数的默认值，要同时发 DeprecationWarning。"""
    changed = []
    for p, q, b, n in w.src_defs():
        if b is None or not is_func(n) or not is_func(b) or not is_public(q):
            continue
        bd, nd = defaults(b), defaults(n)
        ch = [k for k in bd if k in nd and bd[k] != nd[k]]
        if ch:
            changed.append((p, q, ch))
    if not changed:
        return None
    warned = sum(s.count("DeprecationWarning") for s in w.f_src.values()) > sum(s.count("DeprecationWarning") for s in w.b_src.values())
    return [] if warned else [f"{p}: {q} 的默认值 {ch} 变了，没有 DeprecationWarning" for p, q, ch in changed]


def private_helpers(w):
    """新增的模块级函数和类一律用下划线开头，不扩大公开接口。"""
    hit, bad = False, []
    for p, q, b, n in w.src_defs():
        if b is not None or "." in q or p.endswith("__init__.py"):
            continue
        hit = True
        if not q.startswith("_"):
            bad.append(f"{p}: 新增了公开的 {q}")
    return bad if hit else None


CHECKS = {
    "lazy_import": lazy_import,
    "regex_precompiled": regex_precompiled,
    "changelog": changelog,
    "versionadded": versionadded,
    "gettext_messages": gettext_messages,
    "no_builtin_exceptions": no_builtin_exceptions,
    "keyword_only_params": keyword_only_params,
    "no_edit_existing_tests": no_edit_existing_tests,
    "no_new_test_files": no_new_test_files,
    "parametrize_tests": parametrize_tests,
    "deprecate_default_change": deprecate_default_change,
    "private_helpers": private_helpers,
}


def run_all(base, final, pkg):
    w = Work(base, final, pkg)
    out = {}
    for k, f in CHECKS.items():
        try:
            out[k] = f(w)
        except Exception as exc:  # noqa: BLE001
            out[k] = {"error": repr(exc)[:200]}
    return out


if __name__ == "__main__":
    print(json.dumps(run_all(sys.argv[1], sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=1))
