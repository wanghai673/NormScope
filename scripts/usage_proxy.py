"""计量代理：记忆系统把模型网关地址指到 http://127.0.0.1:<端口>/<标签>/v1，这里原样转发到网关，并按标签累计 token 用量。
只记数量，不记内容和密钥。用法：python3 usage_proxy.py <端口> <输出 json>"""
import http.server, json, sys, threading, urllib.request, urllib.error
UP = "https://your-gateway.example"; PORT = int(sys.argv[1]); OUT = sys.argv[2]; LOCK = threading.Lock(); STAT = {}
def add(tag, kind, usage):
    with LOCK:
        s = STAT.setdefault(tag, {"chat_calls": 0, "embed_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "embed_tokens": 0, "calls_without_usage": 0})
        if kind == "embed": s["embed_calls"] += 1; s["embed_tokens"] += (usage or {}).get("total_tokens") or (usage or {}).get("prompt_tokens") or 0
        else:
            s["chat_calls"] += 1
            if usage: s["prompt_tokens"] += usage.get("prompt_tokens") or usage.get("input_tokens") or 0; s["completion_tokens"] += usage.get("completion_tokens") or usage.get("output_tokens") or 0
        if not usage: s["calls_without_usage"] += 1
        json.dump(STAT, open(OUT, "w"), indent=1)
def usage_of(body):
    try:
        d = json.loads(body); return d.get("usage") or (d.get("response") or {}).get("usage")
    except Exception: pass
    u = None
    for line in body.decode("utf-8", "replace").splitlines():
        if line.startswith("data:") and '"usage"' in line:
            try:
                d = json.loads(line[5:].strip()); u = d.get("usage") or (d.get("response") or {}).get("usage") or u
            except Exception: pass
    return u
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def do(self):
        parts = self.path.lstrip("/").split("/", 1); tag = parts[0]; path = "/" + (parts[1] if len(parts) > 1 else "")
        n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n) if n else None
        hdr = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length", "connection", "accept-encoding")}
        try:
            resp = urllib.request.urlopen(urllib.request.Request(UP + path, data=body, headers=hdr, method=self.command), timeout=600); code, data, rh = resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e: code, data, rh = e.code, e.read(), e.headers
        except Exception as e: code, data, rh = 502, json.dumps({"error": {"message": str(e)[:200]}}).encode(), {}
        if code == 200 and body and ("/embeddings" in path or "/completions" in path or "/responses" in path): add(tag, "embed" if "/embeddings" in path else "chat", usage_of(data))
        self.send_response(code); self.send_header("Content-Type", rh.get("Content-Type", "application/json") if rh else "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    do_POST = do_GET = do
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
