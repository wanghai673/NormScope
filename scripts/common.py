"""Shared helpers for the multi-repository pipeline (pipeline2).

A team works on several repositories. Every repository has
  work/repos/<name>/clean   a copy whose git history ends at the base commit (no tags, no remote, no reflog, no host paths)
and an entry in repos.json. Inside containers the team workspace is /workspace/team/<name>; the image puts every repository's
source directory on sys.path, so `python -m pytest` works from inside each project.
All test runs and hidden checks of the driver / labelling run inside throw-away containers WITHOUT network."""
import json, os, re, subprocess, sys, time, uuid
P = "/path/to/pilot"
sys.path.insert(0, f"{P}/scripts")
from llm import chat  # noqa: E402
REPOS = json.load(open(f"{P}/pipeline2/repos.json"))
IMAGE = os.environ.get("TEAM_IMAGE", "teamconf-agent:multi")
BLOCKED = ["github.com", "api.github.com", "raw.githubusercontent.com", "codeload.github.com", "gist.github.com", "objects.githubusercontent.com",
           "gitlab.com", "bitbucket.org", "pypi.org", "files.pythonhosted.org", "pypi.tuna.tsinghua.edu.cn", "mirrors.aliyun.com",
           "sourcegraph.com", "grep.app", "libraries.io", "readthedocs.io", "readthedocs.org"]
for _r in REPOS.values():
    for _h in _r.get("hosts", []):
        if _h not in BLOCKED: BLOCKED.append(_h)
PYTEST = "python -m pytest tests -q -p no:cacheprovider -W ignore -rf -x --maxfail=50"
def clean_dir(repo): return f"{P}/work/repos/{repo}/clean"
def api_key(line): return open("/path/to/api_keys.md", encoding="utf-8").read().splitlines()[line - 1].split("：")[-1].strip()
def sh(cmd, cwd=None, env=None, timeout=None): return subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)

def drun(mounts, cwd, argv, timeout=900, network=False, envs=None, stdin=None, name=None):
    """Run argv in a fresh container. mounts = [(host_dir, container_dir[, 'ro'])]."""
    name = name or f"tx_{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "--name", name] + ([] if network else ["--network", "none"])
    if stdin is not None: cmd.append("-i")
    for m in mounts: cmd += ["-v", f"{m[0]}:{m[1]}" + (":ro" if len(m) > 2 else "")]
    for k, v in (envs or {}).items(): cmd += ["-e", f"{k}={v}"]
    cmd += ["-w", cwd, IMAGE] + argv
    try: return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True)
        return subprocess.CompletedProcess(cmd, 124, "", "TIMEOUT")

def suite(repo_dir, repo, timeout=900):
    """Failing tests of the repository checked out at host path repo_dir (run offline in a container). None = could not run."""
    p = drun([(repo_dir, f"/workspace/team/{repo}")], f"/workspace/team/{repo}",
             ["python", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", "-W", "ignore", "-rfE"], timeout=timeout)
    out = p.stdout + p.stderr
    bad = sorted(set(re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.M)))
    if not bad and not re.search(r"\d+ passed", out): return ["<suite did not run>: " + (out.strip().splitlines() or ["?"])[-1][:200]]
    return bad

def check(code, repo_dir, repo, timeout=120):
    """Run hidden check code (python, asserts) against repo_dir. Returns (ok, last line)."""
    if not code: return True, ""
    p = drun([(repo_dir, f"/workspace/team/{repo}")], f"/workspace/team/{repo}", ["python", "-"], timeout=timeout, stdin=code)
    lines = (p.stdout + p.stderr).strip().splitlines()
    return p.returncode == 0, (lines[-1][:300] if lines else "")

def llm(model, prompt, max_tokens=None, tries=3, timeout=600):
    """chat() with the empty-answer fallback for deepseek (thinking can use up the whole output budget)."""
    for i in range(tries):
        try:
            txt, _u = chat(model, prompt, max_tokens=max_tokens, timeout=timeout, attempts=2)
            if not (txt or "").strip() and model.startswith("deepseek"):
                txt, _u = chat(model, prompt, max_tokens=max_tokens, timeout=timeout, attempts=2, extra={"thinking": {"type": "disabled"}})
            if (txt or "").strip(): return txt.strip()
        except Exception:
            time.sleep(3 * (i + 1))
    return ""

def llm_json(model, prompt, max_tokens=None, tries=3, timeout=600):
    for _ in range(tries):
        txt = llm(model, prompt, max_tokens=max_tokens, tries=1, timeout=timeout)
        m = re.search(r"\{.*\}", txt, re.S)
        if not m: continue
        try: return json.loads(m.group(0))
        except Exception: continue
    return None

CODEX_CONFIG = '''model = "{model}"
web_search = "disabled"
model_provider = "gateway"
approval_policy = "never"
sandbox_mode = "danger-full-access"

[model_providers.gateway]
name = "gateway"
base_url = "http://host.docker.internal:8765/v1"
env_key = "GATEWAY_TOKEN"
wire_api = "responses"
request_max_retries = 8
stream_max_retries = 8

[projects."/workspace/team"]
trust_level = "trusted"
'''
CUT_OFF = "looks like you got cut off there. please pick up where you left off and finish it."
def codex_call(args, out, mounts, cwd, key, name, timeout=1800, retries=6):
    """One `codex exec ...` call in a fresh container (model gateway reachable, code hosts blackholed).
    If the turn fails (gateway rate limit etc.) it is retried with growing pauses: on the same thread when one already exists.
    The event stream of every attempt is appended to `out`. Returns (thread_id, last agent message, timed_out)."""
    tid, msgs, timed_out = None, [], False
    for attempt in range(retries + 1):
        cname = f"{name}_{attempt}"
        cmd = ["docker", "run", "--rm", "--name", cname, "-e", "GATEWAY_TOKEN=local", "-e", "CODEX_HOME=/agent_home"]     # the real key stays on the host (gateway_proxy.py)
        for h in BLOCKED: cmd += ["--add-host", f"{h}:0.0.0.0"]
        for m in mounts: cmd += ["-v", f"{m[0]}:{m[1]}"]
        cmd += ["-w", cwd, IMAGE, "codex", "exec"] + args
        start = os.path.getsize(out) if attempt and os.path.exists(out) else 0
        try:
            with open(out, "a" if attempt else "w") as f: subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.DEVNULL, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", cname], capture_output=True); timed_out = True
        with open(out, errors="replace") as f: f.seek(start); part = f.read()
        new_tid = None
        for l in part.splitlines():
            try: d = json.loads(l)
            except Exception: continue
            if d.get("type") == "thread.started": new_tid = d["thread_id"]
            if d.get("type") == "item.completed" and d["item"].get("type") == "agent_message": msgs.append(d["item"].get("text", ""))
        tid = tid or new_tid
        if '"turn.completed"' in part or timed_out: break
        worked = bool(re.search(r'"type":"(command_execution|file_change|agent_message)"', part))
        if new_tid and args[0] != "resume": args = ["resume", new_tid] + [a for a in args if a not in ("fork",)][(1 if args[0] == "fork" else 0):]
        if worked and args[0] == "resume": args = args[:-1] + [CUT_OFF]      # the turn broke off half-way (gateway error): ask to continue, as a user would
        if attempt < retries: time.sleep(min(300, 45 * (attempt + 1)))
    return tid, (msgs[-1] if msgs else ""), timed_out
