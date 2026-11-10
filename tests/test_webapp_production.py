"""V1.0.1 — production startup smoke over a real loopback socket.

The one socket test in the suite: binds 127.0.0.1 on an OS-assigned port,
serves real HTTP, and shuts down. No external network."""
import json
import threading
import urllib.request

from intent_engine.webapp.app import WebApp, make_server
from intent_engine.webapp.config import AppConfig


def test_server_startup_smoke(tmp_path):
    config = AppConfig(env="test", secret="s" * 40,
                       web_store_path=tmp_path / "web.jsonl",
                       fi_store_path=tmp_path / "fi.jsonl")
    server = make_server(WebApp(config), "127.0.0.1", 0)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/healthz", timeout=5) as resp:
            assert resp.status == 200
            assert json.loads(resp.read())["status"] == "ok"
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/readyz", timeout=5) as resp:
            assert json.loads(resp.read())["status"] == "ready"
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/", timeout=5) as resp:
            body = resp.read().decode()
            # The landing page serves its actual job. That job is no longer
            # the analysis form -- the form moved to /demo -- it is telling a
            # visitor what this is and giving them a way in. A real page,
            # rendered from a real server, not just the health endpoints.
            assert "<h1" in body
            assert "/login" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
