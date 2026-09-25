import http.server, urllib.request, ssl

UPSTREAM = "https://imagefree.hwhcie.bond"
PORT = 4591

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def _proxy(self):
        try:
            target = UPSTREAM + self.path
            body = None
            if self.command in ("POST", "PUT", "PATCH"):
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length) if length else None
            req = urllib.request.Request(target, data=body, method=self.command, headers={
                "accept": self.headers.get("accept", "application/json"),
                "content-type": self.headers.get("content-type", "application/json"),
                "user-agent": "Mozilla/5.0",
                "connection": "close",
            })
            with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
                data = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() in ("content-length", "transfer-encoding", "connection"):
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("access-control-allow-origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except Exception as e:
            try:
                self.send_response(502)
                self.send_header("content-type", "text/plain")
                self.end_headers()
                self.wfile.write(("proxy error: %s" % e).encode())
            except Exception:
                pass
    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_PATCH = _proxy
    do_DELETE = _proxy
    do_OPTIONS = _proxy
    def log_message(self, *a):
        pass

http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
