import json, urllib.request, time
API = "https://your-gateway.example/v1/chat/completions"
def key(line):
    return open("/path/to/api_keys.md", encoding="utf-8").read().splitlines()[line-1].split("：")[-1].strip()
KEYLINE = {"claude": 5, "gpt": 3, "other": 2}
def chat(model, prompt, max_tokens=4000, temperature=0, extra=None, timeout=600, attempts=4):
    kl = KEYLINE["claude"] if model.startswith("claude") else KEYLINE["gpt"] if model.startswith(("gpt", "o")) else KEYLINE["other"]
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if max_tokens: payload["max_tokens"] = max_tokens
    if extra: payload.update(extra)
    body = json.dumps(payload).encode()
    last = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(API, data=body, headers={"Authorization": "Bearer " + key(kl), "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read())
            return (d["choices"][0]["message"].get("content") or ""), d.get("usage", {})
        except Exception as e:
            last = e
            try: last = str(e) + " " + e.read().decode()[:500]
            except Exception: pass
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(str(last))
if __name__ == "__main__":
    import sys
    print(chat(sys.argv[1], "Reply with the single word: ok", max_tokens=20))
