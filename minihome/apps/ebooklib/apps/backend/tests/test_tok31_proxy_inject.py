#!/usr/bin/env python3
# Status: experimental
# Path: apps/backend/tests/test_tok31_proxy_inject.py
"""DataImpulse CONNECT 인증 주입 단위 테스트 (외부 프록시/브라우저 불필요)."""

import base64
import socket
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from lib.toki31_playwright import (
    _basic_proxy_auth,
    _inject_proxy_auth,
    ensure_dataimpulse_inject_proxy,
    playwright_proxy_config,
)


class TestBasicProxyAuth:
    def test_should_format_basic_header_when_user_pass_given(self):
        header = _basic_proxy_auth("user", "pass")
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
        assert decoded == "user:pass"


class TestInjectProxyAuth:
    def test_should_add_auth_header_when_missing(self):
        head = b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443"
        out = _inject_proxy_auth(head, "Basic abc")
        assert b"Proxy-Authorization: Basic abc" in out
        assert out.startswith(b"CONNECT example.com:443 HTTP/1.1")

    def test_should_replace_existing_auth_header_when_present(self):
        head = (
            b"CONNECT example.com:443 HTTP/1.1\r\n"
            b"Host: example.com:443\r\n"
            b"Proxy-Authorization: Basic old"
        )
        out = _inject_proxy_auth(head, "Basic new")
        assert b"Basic old" not in out
        assert out.count(b"Proxy-Authorization:") == 1
        assert b"Proxy-Authorization: Basic new" in out


class TestPlaywrightProxyConfig:
    def test_should_use_inject_proxy_when_dataimpulse_creds(self, monkeypatch):
        monkeypatch.setenv("DATAIMPULSE_USER", "fa04deadbeef")
        monkeypatch.setenv("DATAIMPULSE_PASS", "secret")
        monkeypatch.setenv("DATAIMPULSE_HOST", "gw.dataimpulse.com")
        monkeypatch.setenv("DATAIMPULSE_PORT", "823")
        cfg = playwright_proxy_config()
        assert cfg is not None
        assert cfg["server"].startswith("http://127.0.0.1:")
        assert "username" not in cfg

    def test_should_return_none_when_no_creds(self, monkeypatch):
        for key in (
            "DATAIMPULSE_USER",
            "DATAIMPULSE_PASS",
            "DATAIMPULSE_PROXY_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
        # ENV_LOCAL may still provide fallback — force empty by pointing env file away
        import lib.toki31_playwright as mod

        monkeypatch.setattr(mod, "ENV_LOCAL", "/nonexistent/env.local")
        assert playwright_proxy_config(env={}) is None


class TestInjectProxyRuntime:
    def test_should_forward_connect_with_injected_auth_when_local_upstream(self):
        # upstream은 인증 헤더만 검사하는 더미 HTTP 프록시
        received = {}

        def upstream_server():
            srv = socket.socket()
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            received["port"] = srv.getsockname()[1]
            conn, _ = srv.accept()
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            received["head"] = data
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            # tunnel body: echo one line then close
            try:
                conn.settimeout(2)
                payload = conn.recv(4096)
                received["tunnel"] = payload
                conn.sendall(b"OK")
            except OSError:
                pass
            conn.close()
            srv.close()

        import threading

        t = threading.Thread(target=upstream_server, daemon=True)
        t.start()
        # wait for port
        import time

        for _ in range(50):
            if "port" in received:
                break
            time.sleep(0.02)
        assert "port" in received

        url = ensure_dataimpulse_inject_proxy(
            "user__cr.kr", "pass", "127.0.0.1", received["port"]
        )
        assert url.startswith("http://127.0.0.1:")
        local_port = int(url.rsplit(":", 1)[1])

        # 클라이언트는 인증 없이 CONNECT (Chromium과 동일)
        c = socket.create_connection(("127.0.0.1", local_port), timeout=5)
        c.sendall(
            b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n"
        )
        resp = b""
        c.settimeout(5)
        while b"\r\n\r\n" not in resp:
            chunk = c.recv(4096)
            if not chunk:
                break
            resp += chunk
        assert b"200" in resp.split(b"\r\n", 1)[0]
        c.sendall(b"hello")
        try:
            ack = c.recv(16)
            assert ack == b"OK"
        except OSError:
            pass
        c.close()
        t.join(timeout=2)

        head = received.get("head", b"")
        assert b"Proxy-Authorization: Basic " in head
        expected_user = base64.b64encode(b"user__cr.kr:pass").decode()
        assert expected_user.encode() in head
