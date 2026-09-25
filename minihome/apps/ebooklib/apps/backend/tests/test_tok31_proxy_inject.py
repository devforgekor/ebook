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
    CDP_BLOCKED_URLS,
    CHROMIUM_TUNING_ARGS,
    MINIMAL_REQUEST_HEADERS,
    _basic_proxy_auth,
    _cdp_blocked_urls,
    _chromium_args,
    _inject_proxy_auth,
    _request_headers,
    build_http_request,
    ensure_dataimpulse_inject_proxy,
    fetch_content_api_http,
    http_first_enabled,
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


class TestLevel1Tuning:
    def test_should_enable_launch_args_by_default(self, monkeypatch):
        monkeypatch.delenv("EBOOK_TOK31_LAUNCH_TUNING", raising=False)
        assert _chromium_args() == list(CHROMIUM_TUNING_ARGS)

    def test_should_disable_launch_args_when_off(self, monkeypatch):
        monkeypatch.setenv("EBOOK_TOK31_LAUNCH_TUNING", "0")
        assert _chromium_args() == []

    def test_should_enable_min_headers_by_default(self, monkeypatch):
        monkeypatch.delenv("EBOOK_TOK31_MIN_HEADERS", raising=False)
        assert _request_headers() == MINIMAL_REQUEST_HEADERS

    def test_should_disable_min_headers_when_off(self, monkeypatch):
        monkeypatch.setenv("EBOOK_TOK31_MIN_HEADERS", "off")
        assert _request_headers() == {}

    def test_cdp_block_should_be_off_by_default(self, monkeypatch):
        monkeypatch.delenv("EBOOK_TOK31_CDP_BLOCK", raising=False)
        assert _cdp_blocked_urls() == []

    def test_cdp_block_should_apply_when_enabled(self, monkeypatch):
        monkeypatch.setenv("EBOOK_TOK31_CDP_BLOCK", "1")
        assert _cdp_blocked_urls() == list(CDP_BLOCKED_URLS)


class TestHttpFirst:
    def test_http_first_should_be_off_by_default(self, monkeypatch):
        monkeypatch.delenv("EBOOK_TOK31_HTTP_FIRST", raising=False)
        assert http_first_enabled() is False

    def test_http_first_should_enable(self, monkeypatch):
        monkeypatch.setenv("EBOOK_TOK31_HTTP_FIRST", "1")
        assert http_first_enabled() is True

    def test_build_http_request_should_add_cookie_and_method(self):
        spec = {"url": "https://x/api/novel-content", "method": "POST", "post_data": '{"a":1}'}
        req = build_http_request(spec, "sid=abc")
        assert req["url"].endswith("/api/novel-content")
        assert req["method"] == "POST"
        assert req["headers"]["Cookie"] == "sid=abc"
        assert req["headers"]["Content-Type"] == "application/json"
        assert req["data"] == '{"a":1}'

    def test_fetch_should_return_none_without_spec(self):
        import asyncio

        assert asyncio.run(fetch_content_api_http(None, "sid=abc")) is None
        assert asyncio.run(fetch_content_api_http({}, "sid=abc")) is None

    def test_fetch_should_return_payload_on_success(self):
        import asyncio

        def fake_call(req, proxy_url, timeout):
            return {"ok": True, "payload": "ENCODED"}

        out = asyncio.run(
            fetch_content_api_http(
                {"url": "https://x/api/novel-content", "method": "GET"},
                "sid=abc",
                caller=fake_call,
            )
        )
        assert out == {"ok": True, "payload": "ENCODED"}

    def test_fetch_should_fall_back_on_error_or_invalid(self):
        import asyncio

        def boom(req, proxy_url, timeout):
            raise RuntimeError("proxy down")

        def not_ok(req, proxy_url, timeout):
            return {"ok": False}

        spec = {"url": "https://x/api/novel-content", "method": "GET"}
        assert asyncio.run(fetch_content_api_http(spec, "sid=abc", caller=boom)) is None
        assert asyncio.run(fetch_content_api_http(spec, "sid=abc", caller=not_ok)) is None


class TestInjectProxyUrl:
    def test_should_use_inject_proxy_server(self, monkeypatch):
        import lib.toki31_playwright as tp

        monkeypatch.setattr(
            tp, "playwright_proxy_config", lambda env=None: {"server": "http://127.0.0.1:1234"}
        )
        collector = tp.Toki31Collector.__new__(tp.Toki31Collector)
        assert collector._proxy_url() == "http://127.0.0.1:1234"

    def test_should_return_none_without_proxy(self, monkeypatch):
        import lib.toki31_playwright as tp

        monkeypatch.setattr(tp, "playwright_proxy_config", lambda env=None: None)
        collector = tp.Toki31Collector.__new__(tp.Toki31Collector)
        assert collector._proxy_url() is None
