#!/usr/bin/env python3
"""
Pixel Agents — SSE Bridge Server
─────────────────────────────────
รับ POST /event จาก Claude Code hooks
แล้ว broadcast ผ่าน GET /stream (Server-Sent Events) ไปยัง browser

Usage:
    python3 sse-server.py
"""

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json, threading, time, sys

PORT     = 3001
clients  = []          # list of per-client message queues
c_lock   = threading.Lock()


# ── helpers ──────────────────────────────────────────────────────────────────

def broadcast(data: dict):
    msg = ("data: " + json.dumps(data) + "\n\n").encode()
    with c_lock:
        dead = []
        for q in clients:
            try:
                q.append(msg)
            except Exception:
                dead.append(q)
        for d in dead:
            clients.remove(d)


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {fmt % args}", flush=True)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    # ── OPTIONS (CORS preflight) ──────────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):

        # health check
        if self.path == "/health":
            body = json.dumps({"status": "ok", "clients": len(clients)}).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # SSE stream
        if self.path == "/stream":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type",      "text/event-stream")
            self.send_header("Cache-Control",      "no-cache")
            self.send_header("X-Accel-Buffering",  "no")
            self.send_header("Connection",          "keep-alive")
            self.end_headers()

            q = []
            with c_lock:
                clients.append(q)
            n = len(clients)
            print(f"  + browser connected  (total: {n})", flush=True)

            # send initial handshake
            try:
                self.wfile.write(b'data: {"type":"connected"}\n\n')
                self.wfile.flush()
            except Exception:
                with c_lock:
                    if q in clients: clients.remove(q)
                return

            try:
                while True:
                    if q:
                        while q:
                            self.wfile.write(q.pop(0))
                        self.wfile.flush()
                    else:
                        # heartbeat to keep connection alive
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        time.sleep(2)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with c_lock:
                    if q in clients: clients.remove(q)
                print(f"  - browser disconnected (total: {len(clients)})", flush=True)
            return

        self.send_response(404)
        self.end_headers()

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        if self.path == "/event":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                data = json.loads(body)
                broadcast(data)
                # pretty log
                hook  = data.get("hook", "?")
                tool  = data.get("tool_name", "")
                state = data.get("state", "")
                task  = data.get("task", "")[:55]
                proj  = data.get("project", "")
                print(f"  → [{proj}] {hook}/{tool} | {state} | {task}", flush=True)
                resp = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
            except Exception as e:
                err = str(e).encode()
                self.send_response(400)
                self.end_headers()
                self.wfile.write(err)
            return

        self.send_response(404)
        self.end_headers()


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"")
    print(f"  ╔══════════════════════════════════════╗")
    print(f"  ║   PIXEL AGENTS  —  SSE Bridge        ║")
    print(f"  ╠══════════════════════════════════════╣")
    print(f"  ║  Stream  →  http://localhost:{PORT}/stream ║")
    print(f"  ║  Events  →  POST /event              ║")
    print(f"  ║  Health  →  GET  /health             ║")
    print(f"  ╚══════════════════════════════════════╝")
    print(f"  Waiting for Claude Code hooks...\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        sys.exit(0)
