"""检查脚本自测：每条约束构造「不触发 / 违反 / 合规」三种改动，结果必须分别是 None / 非空列表 / 空列表。
用法：python3 -I test_checkers.py     最后一行应为 bad 0"""
import os, sys, tempfile, textwrap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from checkers import CHECKS, Work

BASE = {
    "src/pkg/__init__.py": "from .core import run\n",
    "src/pkg/core.py": '''
        import os
        from .errors import PkgError

        def run(path, mode="r"):
            """Run it."""
            if not path:
                raise PkgError(_("empty path"))
            return os.path.basename(path)

        def _helper(x):
            return x
        ''',
    "src/pkg/errors.py": "class PkgError(Exception):\n    pass\n",
    "tests/test_core.py": '''
        def test_run():
            assert run("a/b") == "b"
        ''',
    "CHANGES.rst": "Version 1\n\n- first\n",
}
CORE = BASE["src/pkg/core.py"]
NOOP = {"README.md": "hello\n"}                     # 不碰库代码和测试
CASES = {
    "lazy_import": (
        {"src/pkg/core.py": CORE.replace("import os\n", "import os\n        import difflib\n")},
        {"src/pkg/core.py": CORE.replace("return x", "import difflib\n            return difflib.get_close_matches(x, [])")}),
    "regex_precompiled": (
        {"src/pkg/core.py": CORE.replace("import os\n", "import os\n        import re\n").replace("return x", 'return re.sub(r"a+", "", x)')},
        {"src/pkg/core.py": CORE.replace("import os\n", 'import os\n        import re\n        _A_RE = re.compile(r"a+")\n').replace("return x", 'return _A_RE.sub("", x)')}),
    "changelog": (
        {"src/pkg/core.py": CORE.replace("return x", "return x or None")},
        {"src/pkg/core.py": CORE.replace("return x", "return x or None"), "CHANGES.rst": "Version 1\n\n- first\n- second\n"}),
    "versionadded": (
        {"src/pkg/core.py": CORE + '\n        def shiny(a):\n            """New thing."""\n            return a\n'},
        {"src/pkg/core.py": CORE + '\n        def shiny(a):\n            """New thing.\n\n            .. versionadded:: 2.0\n            """\n            return a\n'}),
    "gettext_messages": (
        {"src/pkg/core.py": CORE.replace("return os.path.basename(path)", 'if mode == "x":\n                raise PkgError(f"bad mode {mode}")\n            return os.path.basename(path)')},
        {"src/pkg/core.py": CORE.replace("return os.path.basename(path)", 'if mode == "x":\n                raise PkgError(_("bad mode {m}").format(m=mode))\n            return os.path.basename(path)')}),
    "no_builtin_exceptions": (
        {"src/pkg/core.py": CORE.replace("return x", 'if x is None:\n                raise ValueError("no")\n            return x')},
        {"src/pkg/core.py": CORE.replace("return x", 'if x is None:\n                raise PkgError("no")\n            return x')}),
    "keyword_only_params": (
        {"src/pkg/core.py": CORE.replace('def run(path, mode="r"):', 'def run(path, mode="r", strict=False):')},
        {"src/pkg/core.py": CORE.replace('def run(path, mode="r"):', 'def run(path, mode="r", *, strict=False):')}),
    "no_edit_existing_tests": (
        {"src/pkg/core.py": CORE.replace("return x", "return x or None"), "tests/test_core.py": 'def test_run():\n    assert run("a/b") == "B"\n'},
        {"src/pkg/core.py": CORE.replace("return x", "return x or None"), "tests/test_core.py": 'def test_run():\n    assert run("a/b") == "b"\n\ndef test_more():\n    assert run("c") == "c"\n'}),
    "no_new_test_files": (
        {"tests/test_extra.py": "def test_more():\n    assert True\n"},
        {"tests/test_core.py": 'def test_run():\n    assert run("a/b") == "b"\n\ndef test_more():\n    assert True\n'}),
    "parametrize_tests": (
        {"tests/test_core.py": 'def test_run():\n    assert run("a/b") == "b"\n\ndef test_many():\n    for v in ("a", "b"):\n        assert run(v) == v\n'},
        {"tests/test_core.py": 'import pytest\n\ndef test_run():\n    assert run("a/b") == "b"\n\n@pytest.mark.parametrize("v", ["a", "b"])\ndef test_many(v):\n    assert run(v) == v\n'}),
    "deprecate_default_change": (
        {"src/pkg/core.py": CORE.replace('mode="r"', 'mode="rb"')},
        {"src/pkg/core.py": CORE.replace('mode="r"', 'mode="rb"').replace('"""Run it."""', '"""Run it."""\n            import warnings\n            warnings.warn("default changed", DeprecationWarning, stacklevel=2)')}),
    "private_helpers": (
        {"src/pkg/core.py": CORE + "\n        def tidy(a):\n            return a\n"},
        {"src/pkg/core.py": CORE + "\n        def _tidy(a):\n            return a\n"}),
}


def write(root, files):
    for rel, text in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(textwrap.dedent(text).lstrip("\n"))


def verdict(name, change):
    with tempfile.TemporaryDirectory() as t:
        b, f = os.path.join(t, "b"), os.path.join(t, "f")
        write(b, BASE)
        write(f, dict(BASE, **change))
        return CHECKS[name](Work(b, f, "src/pkg"))


bad = 0
for name in CHECKS:
    viol, ok = CASES[name]
    r0, r1, r2 = verdict(name, NOOP), verdict(name, viol), verdict(name, ok)
    good = r0 is None and isinstance(r1, list) and len(r1) > 0 and r2 == []
    bad += not good
    print(("ok  " if good else "BAD ") + name, "| 不触发:", r0, "| 违反:", r1, "| 合规:", r2)
print("bad", bad)
