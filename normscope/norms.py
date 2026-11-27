"""第 2 批：替换型约束。每条约束有原规范和新规范，两种做法互相排斥，各有一个检查函数。
judge(norm_id, repo, base_dir, final_dir, pkg) -> {"trig": 是否触发, "old": 是否符合原规范, "new": 是否符合新规范}
每条约束的话：establish（立规范）、change（正式修改）、dev_old / dev_new（个人违背原规范 / 新规范，各两个说法，情形不同）。
情形：N 没给原因的一次性指令，H 个人习惯，E 个人环境，S 有情境原因的一次性安排。
自测：python3 -I norms2.py   最后一行应为 bad 0"""
import ast, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checkers import Work, defs, is_func, is_public, params, keyword_only_params, versionadded, top_imports

NORMS = [
 {"id": "CHG", "repos": ["click", "jinja"],
  "old": "Every change to the library code adds an entry to CHANGES.rst under the unreleased version.",
  "new": "CHANGES.rst is no longer edited by hand; every change to the library code adds a fragment file `changes/<short-slug>.rst` (one or two sentences) instead.",
  "establish": "Every change to the library code gets an entry in CHANGES.rst under the unreleased version; reviewers send PRs back without one.",
  "change": "Changelog handling changed: the maintainers agreed last week that nobody edits CHANGES.rst by hand any more, because of the constant merge conflicts. Each change now adds a small fragment file `changes/<short-slug>.rst` with one or two sentences, and the release script assembles them. The contributing guide is already updated.",
  "dev_old": [("N", "Leave the changelog out of this one."), ("S", "No changelog entry for this one: I'm folding this branch into a bigger PR of mine and will write a single entry there.")],
  "dev_new": [("H", "I never bother with the changes/ fragment on my own branches, I write it right before I open the PR. Skip it here."), ("N", "Don't add the changes/ fragment this time.")]},
 {"id": "TS_click", "repos": ["click"],
  "old": "New tests are plain module-level test functions (`def test_...`), not methods of test classes.",
  "new": "New tests are grouped in a test class (`class Test<Feature>:` with `test_...` methods), not written as module-level functions.",
  "establish": "New tests here are written as plain module-level functions, `def test_...`, not as methods of a test class. That's the house style for this repo's tests and reviewers enforce it.",
  "change": "Test layout changed: it was decided at the maintainers' sync that new tests are grouped in a class per feature, `class Test<Feature>:` with `test_...` methods, so shared fixtures can live on the class. The testing guide was updated yesterday; plain module-level test functions are no longer accepted for new tests.",
  "dev_old": [("H", "I like my tests wrapped in a `Test...` class, I find them easier to navigate. Write them that way for me."), ("S", "Put the tests for this one in a class: I'm going to move them into a downstream plugin's suite afterwards, and that suite is class-based.")],
  "dev_new": [("H", "Honestly I still write plain `def test_...` functions on my stuff, old habit. Do that here."), ("N", "Plain test functions for this one, no class.")]},
 {"id": "TS_jinja", "repos": ["jinja"],
  "old": "New tests go into a test class (`class Test<Feature>:` with `test_...` methods), not module-level functions.",
  "new": "New tests are plain module-level `def test_...` functions; no new test classes.",
  "establish": "The maintainers require that every contributor's new tests in this repo go into a test class, `class Test<Feature>:` with `test_...` methods, like the rest of the suite; loose module-level test functions get sent back in review, whoever wrote them.",
  "change": "Test layout changed: the maintainers decided at last week's sync that new tests are plain module-level `def test_...` functions from now on, since the classes get in the way of parametrized fixtures. The testing guide is updated; new test classes are no longer accepted.",
  "dev_old": [("H", "I prefer plain `def test_...` functions on my own stuff. Write them like that for me."), ("S", "Plain functions for this one: I'm copying these tests into a gist for a bug report and want them standalone.")],
  "dev_new": [("H", "I still like my tests in a `Test...` class, old habit. Do it that way here."), ("N", "Wrap the tests for this one in a class.")]},
 {"id": "TF", "repos": ["click", "jinja"],
  "old": "New tests go into the existing test modules; no new test files are created.",
  "new": "Each change puts its tests in its own new module `tests/test_<topic>.py` instead of adding to the existing test modules.",
  "establish": "The maintainers require that everyone on the team puts new tests into the existing test modules; a PR from anyone that creates a new test file gets sent back.",
  "change": "Where tests go has changed: the big test modules keep producing merge conflicts, so the maintainers agreed that every change now puts its tests in its own new module, `tests/test_<topic>.py`, instead of appending to the existing ones. It has been in the testing guide since Monday.",
  "dev_old": [("E", "On my machine the big test modules take forever to collect, so for this one put the tests in a fresh `tests/test_<topic>.py` file."), ("N", "Put the tests in a new file this time.")],
  "dev_new": [("H", "I always just append to the existing test module on my branches and split it out myself later. Append here."), ("S", "Append the tests to the existing module for this one: I'm cherry-picking this onto the old release branch, which doesn't have the split layout.")]},
 {"id": "VN", "repos": ["click", "jinja"],
  "old": "Anything public that is added (function, method, class, or a new parameter on an existing one) carries a `.. versionadded::` / `.. versionchanged::` note in its docstring with the upcoming version number.",
  "new": "Version notes on new public things use the placeholder `NEXT` (`.. versionadded:: NEXT` / `.. versionchanged:: NEXT`) instead of a version number.",
  "establish": "Anything public you add (a function, method, class, or a new parameter on an existing one) needs a `.. versionadded::` or `.. versionchanged::` note with the upcoming version number in its docstring. Docs review bounces PRs without it.",
  "change": "Version notes changed: we kept shipping wrong numbers, so the maintainers agreed that the notes are written with the placeholder `NEXT`, as in `.. versionadded:: NEXT` or `.. versionchanged:: NEXT`, and the release script fills in the number. Real version numbers in new notes are no longer accepted; the contributing guide has it.",
  "dev_old": [("H", "Skip the version note. I add those myself in one pass before I open my PRs."), ("N", "No version note on this one.")],
  "dev_new": [("S", "Write the actual upcoming version number in the version note here instead of the placeholder: this branch goes straight into a hotfix tag by hand and never passes the release script."), ("H", "I can't stand the NEXT placeholder; on my own changes I just type the version number. Do that.")]},
 {"id": "DS", "repos": ["click", "jinja"],
  "old": "Every new public function or method that takes arguments documents them in its docstring with Sphinx fields (`:param name: ...`).",
  "new": "Every new public function or method that takes arguments documents them Google-style, with an `Args:` section in its docstring, and without `:param` fields.",
  "establish": "Every new public function or method that takes arguments documents them in its docstring with Sphinx fields, `:param name: ...`. That's what the API docs build expects, and reviewers check it.",
  "change": "Docstring format changed: the docs build moved to napoleon, and the maintainers agreed that new docstrings document arguments Google-style, with an `Args:` section, instead of `:param` fields. Existing docstrings stay as they are; for new functions `:param` is no longer accepted. The style guide is updated.",
  "dev_old": [("H", "I write my docstrings Google-style with an `Args:` section, I find `:param` unreadable. Use that for me."), ("N", "Don't bother documenting the arguments on this one.")],
  "dev_new": [("H", "I still type `:param` fields on my stuff, muscle memory. Just use those here."), ("S", "Use `:param` fields for this one: I'm backporting it to the maintenance branch, whose docs build doesn't have napoleon.")]},
 {"id": "KW", "repos": ["click", "jinja"],
  "old": "A parameter added to an existing public function or method must be keyword-only (placed after a `*`).",
  "new": "A parameter added to an existing public function or method is appended at the end as a normal parameter with a default; no keyword-only `*` marker.",
  "establish": "When a parameter is added to an existing public function or method it has to be keyword-only, after a `*`. The maintainers got burned by positional arguments landing mid-signature.",
  "change": "The keyword-only requirement for new parameters is gone: it broke subclasses that override those methods, so the maintainers decided that a new parameter is simply appended at the end as a normal parameter with a default, without a `*`. The contributing guide is updated, and new bare `*` markers get sent back.",
  "dev_old": [("N", "Make the new argument a normal positional one this time."), ("S", "Make the new argument positional here: a script of mine calls this positionally and I'm not touching it today.")],
  "dev_new": [("H", "I always make my new arguments keyword-only, I just prefer it. Do that on this one."), ("N", "Keyword-only for the new argument on this one.")]},
 {"id": "IM", "repos": ["click", "jinja"],
  "old": "If a change needs a standard-library module the file does not already import, the import goes inside the function that uses it, not at the top of the file.",
  "new": "All imports go at the top of the file; no imports inside functions.",
  "establish": "There's a standing requirement from the maintainers about import time: if a change needs a standard-library module the file doesn't already import, the import goes inside the function that uses it, not at the top of the file.",
  "change": "The import rule was reversed: function-level imports were hiding circular-import bugs, so the maintainers agreed that all imports go at the top of the file again, and the linter config now rejects imports inside functions. That applies to every new change.",
  "dev_old": [("S", "For this one just put the import at the top of the file: it's a throwaway spike that I'm rewriting before it goes anywhere."), ("N", "Top-of-file import is fine this time.")],
  "dev_new": [("H", "I keep my imports inside the function on my own code, I like seeing them next to the use. Do that here."), ("E", "Import it inside the function for this one; my editor's import sorter mangles this file's header.")]},
 {"id": "TA", "repos": ["click", "jinja"],
  "old": "Every new test function is annotated with `-> None`.",
  "new": "New test functions carry no return annotation (no `-> None`).",
  "establish": "The maintainers run the type checker over the test suite, so everyone's new test functions have to be annotated with `-> None`; PRs with unannotated new tests get sent back.",
  "change": "Typing of tests changed: the maintainers dropped the type checker from the test suite last week because it was too slow, and agreed that new test functions are written without a return annotation, no `-> None`. The contributing guide is updated and reviewers now ask for the annotation to be removed.",
  "dev_old": [("N", "Leave the `-> None` off the tests this time."), ("E", "Skip the `-> None` on the tests for this one: the test runner plugin on my machine chokes on annotated tests.")],
  "dev_new": [("H", "I still put `-> None` on every test I write, habit. Add it here."), ("S", "Annotate the tests with `-> None` for this one: I'm also submitting it to a downstream fork that still type-checks its tests.")]},
 {"id": "TD", "repos": ["click", "jinja"],
  "old": "Every new test function has a one-line docstring saying what behaviour it checks.",
  "new": "New test functions have no docstring; the explanation goes in a `#` comment line above the function.",
  "establish": "Team rule for tests in this repo: every new test function gets a one-line docstring saying what behaviour it checks. Reviewers ask everyone for it.",
  "change": "Test docstrings are out: they were cluttering the verbose test report, so the maintainers decided that new tests have no docstring and the explanation goes in a `#` comment line above the function instead. It is in the testing guide as of this week, and new tests with docstrings get sent back.",
  "dev_old": [("H", "I don't write docstrings on my tests, a comment above is enough for me. Do it my way here."), ("N", "No docstrings on the tests for this one.")],
  "dev_new": [("H", "I like a one-line docstring on each of my tests, I read them in my IDE's test tree. Add them here."), ("S", "Give the tests docstrings for this one: I'm pasting them into a tutorial page that renders the docstrings.")]},
 {"id": "EXP", "repos": ["click", "jinja"],
  "old": "A new public module-level function or class is also exported from the package's top-level `__init__.py`.",
  "new": "New public functions and classes are not added to the package's top-level `__init__.py`; users import them from the submodule.",
  "establish": "Team rule: when anyone adds a new public function or class to a module, it also gets exported from the package's top-level `__init__.py`, so users can import it from the package root. Reviewers check for that.",
  "change": "Export policy changed: the top-level namespace is frozen. The maintainers agreed that new public functions and classes are no longer added to the top-level `__init__.py`; users import them from their submodule. The API policy page says so now, and new top-level exports get sent back.",
  "dev_old": [("N", "Don't export it from the top-level `__init__` this time."), ("S", "Leave it out of the top-level `__init__` for now: I'm renaming it before release and don't want the old name exported anywhere.")],
  "dev_new": [("H", "I always re-export my new things from the top-level `__init__`, I like importing from the root. Do that here."), ("E", "Export it from the top-level `__init__` for this one: the scratch scripts on my machine all import from the package root.")]},
 {"id": "DOC", "repos": ["click", "jinja"],
  "old": "A new public function or class is added to `docs/api.rst` in the same change.",
  "new": "`docs/api.rst` is not edited by contributors; the name of each new public function or class is added as a line to `docs/api_pending.txt` instead.",
  "establish": "Documentation rule for the whole team: a new public function or class has to be added to `docs/api.rst` in the same change. PRs that add public API without touching `docs/api.rst` are sent back.",
  "change": "API docs handling changed: the docs maintainers now own `docs/api.rst` and regenerate it themselves, so contributors no longer edit it. The agreement from last week's sync is that each new public function or class is listed by name, one per line, in `docs/api_pending.txt`, and nothing else in docs is touched. It's written up in the contributing guide.",
  "dev_old": [("H", "I never touch `docs/api.rst` in my feature branches, I do the docs in a separate pass later. Leave it alone here."), ("N", "Skip `docs/api.rst` on this one.")],
  "dev_new": [("S", "Put this one straight into `docs/api.rst` rather than the pending list: I'm building a docs preview from this branch tonight for a demo."), ("N", "Add it to `docs/api.rst` directly this time, not to the pending file.")]},
 {"id": "PD", "repos": ["click", "jinja"],
  "old": "Every new private helper (a function or method whose name starts with an underscore) has a docstring.",
  "new": "New private helpers have no docstring; a short `#` comment above the definition is used instead.",
  "establish": "Team rule: every new private helper, meaning any function or method whose name starts with an underscore, gets a docstring. The maintainers ask everyone for this because the helpers were impossible to follow otherwise.",
  "change": "Docstrings on private helpers are dropped: they were leaking into the generated API docs, so the maintainers agreed that new underscore-prefixed functions and methods have no docstring and get a short `#` comment above the definition instead. The style guide was updated on Monday and reviewers now reject docstrings on new private helpers.",
  "dev_old": [("N", "No docstrings on the private helpers this time."), ("H", "I don't docstring my private helpers, a comment is plenty for me. Do it that way here.")],
  "dev_new": [("H", "I still write a docstring on every helper I add, even the private ones, it's how I think. Add them here."), ("S", "Give the private helpers docstrings for this one: I'm walking a new hire through this code tomorrow and want them in the hover text.")]},
 # ── 方向调过来的四条（c4 用）：原规范 = agent 默认的做法，新规范 = 默认不会做的。c3 用的是相反方向，无记忆也能做对，没有区分度。
 {"id": "TA2", "repos": ["click", "jinja"],
  "old": "New test functions carry no return annotation (no `-> None`).",
  "new": "Every new test function is annotated with `-> None`.",
  "establish": "The maintainers have asked everyone to keep new test functions free of return annotations, no `-> None`: the test suite isn't type-checked, and reviewers ask for the annotation to be removed whoever wrote the test.",
  "change": "Typing of tests changed: the maintainers switched on the type checker for the test suite last week and agreed that every new test function has to be annotated with `-> None`. The contributing guide is updated, and unannotated new tests get sent back.",
  "dev_old": [("H", "I put `-> None` on every test I write, a habit from my last job. Add it here."), ("S", "Annotate the tests with `-> None` for this one: I'm also submitting it to a downstream fork that type-checks its tests.")],
  "dev_new": [("N", "Leave the `-> None` off the tests this time."), ("E", "Skip the `-> None` on the tests for this one: the test runner plugin on my machine chokes on annotated tests.")]},
 {"id": "TD2", "repos": ["click", "jinja"],
  "old": "New test functions have no docstring; any explanation goes in a `#` comment line above the function.",
  "new": "Every new test function has a one-line docstring saying what behaviour it checks.",
  "establish": "Team rule for tests in this repo: new test functions have no docstring, and any explanation goes in a `#` comment above the function. The maintainers want the verbose test report uncluttered, and reviewers ask everyone to take test docstrings out.",
  "change": "Test docstrings are now required: the maintainers adopted a report tool that prints each test's docstring, and agreed at this week's sync that every new test function gets a one-line docstring saying what behaviour it checks. It is in the testing guide, and new tests without one get sent back.",
  "dev_old": [("H", "I like a one-line docstring on each of my tests, I read them in my IDE's test tree. Add them here."), ("S", "Give the tests docstrings for this one: I'm pasting them into a tutorial page that renders the docstrings.")],
  "dev_new": [("H", "I don't write docstrings on my tests, a comment above is enough for me. Do it my way here."), ("N", "No docstrings on the tests for this one.")]},
 {"id": "EXP2", "repos": ["click", "jinja"],
  "old": "New public functions and classes are not added to the package's top-level `__init__.py`; users import them from the submodule.",
  "new": "A new public module-level function or class is also exported from the package's top-level `__init__.py`.",
  "establish": "Team rule: the package's top-level namespace is frozen. When anyone adds a new public function or class, it is not added to the top-level `__init__.py`; users import it from its submodule. Reviewers send back new top-level exports.",
  "change": "Export policy changed: users kept failing to find new API, so the maintainers agreed that every new public function or class is also exported from the package's top-level `__init__.py`. The API policy page says so now, and reviewers check for the export.",
  "dev_old": [("H", "I always re-export my new things from the top-level `__init__`, I like importing from the root. Do that here."), ("E", "Export it from the top-level `__init__` for this one: the scratch scripts on my machine all import from the package root.")],
  "dev_new": [("N", "Don't export it from the top-level `__init__` this time."), ("S", "Leave it out of the top-level `__init__` for now: I'm renaming it before release and don't want the old name exported anywhere.")]},
 {"id": "PD2", "repos": ["click", "jinja"],
  "old": "New private helpers (functions or methods whose name starts with an underscore) have no docstring; a short `#` comment above the definition is used instead.",
  "new": "Every new private helper (a function or method whose name starts with an underscore) has a docstring.",
  "establish": "Team rule: new private helpers, meaning functions or methods whose name starts with an underscore, get no docstring, just a short `#` comment above the definition. The maintainers ask everyone for this because helper docstrings were leaking into the generated API docs.",
  "change": "Docstrings on private helpers are now required: the docs generator was fixed to skip private names, and since the helpers were hard to follow the maintainers agreed that every new underscore-prefixed function or method gets a docstring. The style guide was updated on Monday, and reviewers send back new helpers without one.",
  "dev_old": [("H", "I still write a docstring on every helper I add, even the private ones, it's how I think. Add them here."), ("S", "Give the private helpers docstrings for this one: I'm walking a new hire through this code tomorrow and want them in the hover text.")],
  "dev_new": [("N", "No docstrings on the private helpers this time."), ("H", "I don't docstring my private helpers, a comment is plenty for me. Do it that way here.")]},
]
NORM = {n["id"]: n for n in NORMS}
DISTRACTORS = [
 "Only run the tests for the module you touch, the full suite is slow on my laptop.",
 "Keep the diff small, please. No drive-by reformatting.",
 "I'm on Python 3.9 here, so skip anything that needs a newer interpreter.",
 "Tell me which files you changed when you're done.",
 "Have a look whether the same problem exists in a neighbouring function while you're in there.",
 "I ran into this area before; watch the edge cases with empty input.",
 "Don't touch the docs build config, it's fragile right now.",
 "If something unrelated is failing, just tell me, don't fix it.",
 "No need to commit, I'll look at the working tree.",
 "Keep the public names short, I have to type them a lot.",
]


# ───────────────────────────── 检查 ─────────────────────────────
def _new_tests(w):
    """[(文件, 限定名, 是否在类里, 是否在新文件里)]：结束目录里新出现的测试函数。"""
    out = []
    for p, s in w.f_tst.items():
        if s == w.b_tst.get(p) or not os.path.basename(p).startswith("test"):
            continue
        try:
            new, old = defs(ast.parse(s)), defs(ast.parse(w.b_tst.get(p, "")))
        except SyntaxError:
            continue
        for q, n in new.items():
            if is_func(n) and q.split(".")[-1].startswith("test") and q not in old:
                out.append((p, q, "." in q, p not in w.b_tst))
    return out


def _chg(w, repo):
    if not w.src_changed:
        return False, False, False
    ch = w.read(w.final, "CHANGES.rst") != w.read(w.base, "CHANGES.rst")
    fd, bd = os.path.join(w.final, "changes"), os.path.join(w.base, "changes")
    frag = sorted(set(os.listdir(fd)) - set(os.listdir(bd) if os.path.isdir(bd) else [])) if os.path.isdir(fd) else []
    frag = [f for f in frag if not f.startswith(".")]
    return True, ch and not frag, bool(frag) and not ch


def _ts(w, repo):
    nt = _new_tests(w)
    if not nt:
        return False, False, False
    funcs, classes = all(not c for _p, _q, c, _n in nt), all(c for _p, _q, c, _n in nt)
    return (True, funcs, classes) if repo == "click" else (True, classes, funcs)


def _tf(w, repo):
    nt = _new_tests(w)
    if not nt:
        return False, False, False
    return True, all(not n for _p, _q, _c, n in nt), all(n for _p, _q, _c, n in nt)


VN_RE = re.compile(r"\.\.\s+version(?:added|changed)::\s*(\S+)")


def _vn(w, repo):
    if versionadded(w) is None:
        return False, False, False
    args = []
    for p in w.src_changed:
        have = {}
        for ln in w.b_src.get(p, "").splitlines():
            have[ln.strip()] = have.get(ln.strip(), 0) + 1
        for ln in w.f_src[p].splitlines():
            k = ln.strip()
            if have.get(k, 0) > 0:
                have[k] -= 1
                continue
            m = VN_RE.search(k)
            if m:
                args.append(m.group(1))
    return True, bool(args) and all(re.match(r"\d", a) for a in args), bool(args) and all(a.strip("`*").upper().startswith("NEXT") for a in args)


def _ds(w, repo):
    docs = []
    for p, q, b, n in w.src_defs():
        if b is not None or not is_func(n) or not is_public(q) or q.split(".")[-1].startswith("__") or p.endswith("__init__.py"):
            continue
        pos, kw = params(n)
        if not [x for x in pos + kw if x not in ("self", "cls")]:
            continue
        docs.append(ast.get_docstring(n) or "")
    if not docs:
        return False, False, False
    return True, all(":param" in d for d in docs), all(re.search(r"^\s*Args:", d, re.M) and ":param" not in d for d in docs)


def _kw(w, repo):
    if keyword_only_params(w) is None:
        return False, False, False
    pos_new, kw_new = [], []
    for p, q, b, n in w.src_defs():
        if b is None or not is_func(n) or not is_func(b) or not is_public(q):
            continue
        bpos, bkw = params(b)
        npos, nkw = params(n)
        new = (set(npos) | set(nkw)) - (set(bpos) | set(bkw))
        pos_new += [x for x in npos if x in new]
        kw_new += [x for x in nkw if x in new]
    return True, not pos_new, not kw_new


def _inner_imports(tree):
    mods = set()
    for fn in (ast.walk(tree) if tree else []):
        if is_func(fn):
            for m in ast.walk(fn):
                if isinstance(m, ast.Import):
                    mods |= {a.name.split(".")[0] for a in m.names}
                elif isinstance(m, ast.ImportFrom) and m.level == 0 and m.module:
                    mods.add(m.module.split(".")[0])
    return mods


def _im(w, repo):
    new_top, new_inner = set(), set()
    ignore = {"typing", "__future__", "collections", w.pkg.split("/")[-1]}
    for p in w.src_changed:
        if w.f_tree[p] is None:
            continue
        bt, bi = top_imports(w.b_tree.get(p)), _inner_imports(w.b_tree.get(p))
        new_top |= {f"{p}:{m}" for m in top_imports(w.f_tree[p]) - bt - ignore}
        new_inner |= {f"{p}:{m}" for m in _inner_imports(w.f_tree[p]) - bi - bt - ignore}
    if not (new_top or new_inner):
        return False, False, False
    return True, not new_top, not new_inner


def _new_test_nodes(w):
    out = []
    for p, s in w.f_tst.items():
        if s == w.b_tst.get(p) or not os.path.basename(p).startswith("test"):
            continue
        try:
            new, old = defs(ast.parse(s)), defs(ast.parse(w.b_tst.get(p, "")))
        except SyntaxError:
            continue
        out += [n for q, n in new.items() if is_func(n) and q.split(".")[-1].startswith("test") and q not in old]
    return out


def _ta(w, repo):
    nt = _new_test_nodes(w)
    if not nt:
        return False, False, False
    return True, all(n.returns is not None for n in nt), all(n.returns is None for n in nt)


def _td(w, repo):
    nt = _new_test_nodes(w)
    if not nt:
        return False, False, False
    return True, all(ast.get_docstring(n) for n in nt), all(not ast.get_docstring(n) for n in nt)


def _new_public_names(w):
    return [q for p, q, b, n in w.src_defs() if b is None and "." not in q and not q.startswith("_") and not p.endswith("__init__.py")]


def _exp(w, repo):
    names = _new_public_names(w)
    if not names:
        return False, False, False
    init = w.read(w.final, w.pkg + "/__init__.py")
    has = [bool(re.search(r"\b%s\b" % re.escape(x), init)) for x in names]
    return True, all(has), not any(has)


def _doc(w, repo):
    if not _new_public_names(w):
        return False, False, False
    api = w.read(w.final, "docs/api.rst") != w.read(w.base, "docs/api.rst")
    pend = w.read(w.final, "docs/api_pending.txt").strip() != w.read(w.base, "docs/api_pending.txt").strip()
    return True, api and not pend, pend and not api


def _pd(w, repo):
    fs = [n for p, q, b, n in w.src_defs() if b is None and is_func(n) and q.split(".")[-1].startswith("_") and not q.split(".")[-1].startswith("__")]
    if not fs:
        return False, False, False
    return True, all(ast.get_docstring(n) for n in fs), all(not ast.get_docstring(n) for n in fs)


CHECK = {"CHG": _chg, "TS_click": _ts, "TS_jinja": _ts, "TF": _tf, "VN": _vn, "DS": _ds, "KW": _kw, "IM": _im, "TA": _ta, "TD": _td, "EXP": _exp, "DOC": _doc, "PD": _pd}


def _flip(f):
    def g(w, repo):
        t, o, n = f(w, repo)
        return t, n, o
    return g


CHECK.update({"TA2": _flip(_ta), "TD2": _flip(_td), "EXP2": _flip(_exp), "PD2": _flip(_pd)})

def judge_all(repo, base, final, pkg, norm_ids):
    w = Work(base, final, pkg)
    out = {}
    for nid in norm_ids:
        try:
            t, o, n = CHECK[nid](w, repo)
            out[nid] = {"trig": bool(t), "old": bool(o), "new": bool(n)}
        except Exception as exc:  # noqa: BLE001
            out[nid] = {"trig": False, "old": False, "new": False, "error": repr(exc)[:200]}
    return out


# ───────────────────────────── 自测 ─────────────────────────────
if __name__ == "__main__":
    import tempfile, textwrap
    BASE = {"src/pkg/__init__.py": "", "docs/api.rst": "API\n", "CHANGES.rst": "Unreleased\n\n- a\n",
            "src/pkg/core.py": 'import os\n\ndef run(path, mode="r"):\n    """Run."""\n    return os.path.basename(path)\n',
            "tests/test_core.py": "class TestRun:\n    def test_a(self):\n        assert True\n\ndef test_b():\n    assert True\n"}
    CORE, TST = BASE["src/pkg/core.py"], BASE["tests/test_core.py"]
    SRC = {"src/pkg/core.py": CORE + "\n# x\n"}
    FN = '\ndef shiny(a):\n    """New.\n\n%s\n    """\n    return a\n'
    CASES = {  # 约束: (仓库, 符合原规范的改动, 符合新规范的改动)
        "CHG": ("click", dict(SRC, **{"CHANGES.rst": "Unreleased\n\n- a\n- b\n"}), dict(SRC, **{"changes/fix-x.rst": "Fixed x.\n"})),
        "TS_click": ("click", {"tests/test_core.py": TST + "\ndef test_c():\n    assert True\n"}, {"tests/test_core.py": TST + "\nclass TestC:\n    def test_c(self):\n        assert True\n"}),
        "TS_jinja": ("jinja", {"tests/test_core.py": TST + "\nclass TestC:\n    def test_c(self):\n        assert True\n"}, {"tests/test_core.py": TST + "\ndef test_c():\n    assert True\n"}),
        "TF": ("click", {"tests/test_core.py": TST + "\ndef test_c():\n    assert True\n"}, {"tests/test_shiny.py": "def test_c():\n    assert True\n"}),
        "VN": ("click", {"src/pkg/core.py": CORE + FN % "    .. versionadded:: 8.2"}, {"src/pkg/core.py": CORE + FN % "    .. versionadded:: NEXT"}),
        "DS": ("click", {"src/pkg/core.py": CORE + FN % "    :param a: the thing"}, {"src/pkg/core.py": CORE + FN % "    Args:\n        a: the thing"}),
        "KW": ("click", {"src/pkg/core.py": CORE.replace('mode="r")', 'mode="r", *, strict=False)')}, {"src/pkg/core.py": CORE.replace('mode="r")', 'mode="r", strict=False)')}),
        "IM": ("click", {"src/pkg/core.py": CORE.replace("    return os", "    import difflib\n    return os")}, {"src/pkg/core.py": CORE.replace("import os\n", "import os\nimport difflib\n")}),
        "TA": ("click", {"tests/test_core.py": TST + "\ndef test_c() -> None:\n    assert True\n"}, {"tests/test_core.py": TST + "\ndef test_c():\n    assert True\n"}),
        "TD": ("click", {"tests/test_core.py": TST + '\ndef test_c():\n    """Checks c."""\n    assert True\n'}, {"tests/test_core.py": TST + "\n# checks c\ndef test_c():\n    assert True\n"}),
        "EXP": ("click", {"src/pkg/core.py": CORE + "\ndef shiny(a):\n    return a\n", "src/pkg/__init__.py": "from .core import shiny\n"}, {"src/pkg/core.py": CORE + "\ndef shiny(a):\n    return a\n"}),
        "DOC": ("click", {"src/pkg/core.py": CORE + "\ndef shiny(a):\n    return a\n", "docs/api.rst": "API\n\nshiny\n"}, {"src/pkg/core.py": CORE + "\ndef shiny(a):\n    return a\n", "docs/api_pending.txt": "shiny\n"}),
        "PD": ("click", {"src/pkg/core.py": CORE + '\ndef _h(a):\n    """Help."""\n    return a\n'}, {"src/pkg/core.py": CORE + "\n# help\ndef _h(a):\n    return a\n"}),
    }

    def run(nid, repo, change):
        with tempfile.TemporaryDirectory() as t:
            for root, files in (("b", BASE), ("f", dict(BASE, **change))):
                for rel, text in files.items():
                    p = os.path.join(t, root, rel)
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    open(p, "w").write(text)
            return judge_all(repo, f"{t}/b", f"{t}/f", "src/pkg", [nid])[nid]
    bad = 0
    for nid, (repo, old, new) in CASES.items():
        r0, r1, r2 = run(nid, repo, {"README.md": "x"}), run(nid, repo, old), run(nid, repo, new)
        good = (not r0["trig"]) and r1 == {"trig": True, "old": True, "new": False} and r2 == {"trig": True, "old": False, "new": True}
        bad += not good
        print("ok  " if good else "BAD ", nid, r0, r1, r2)
    print("bad", bad)
