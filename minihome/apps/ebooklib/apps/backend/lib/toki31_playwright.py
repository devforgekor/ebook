#!/usr/bin/env python3
# Status: production
# Path: ebooklib/apps/backend/lib/toki31_playwright.py
"""toki31 Playwright 콘텐츠 추출기.

toki31의 anti-bot 보호를 우회하기 위해 Playwright 브라우저를 사용:
1. 브라우저가 ad-ack (광고 확인) 자동 처리
2. /api/novel-content API 응답 인터셉트
3. AES-GCM 복호화로 콘텐츠 추출

복호화 알고리즘 (JS에서 역공학):
- Key: SHA-256(nv_cookie + f":{episode_ref}:{novel_id}:v3")
- IV: payload 앞 12 bytes
- Algorithm: AES-128-GCM

데이터 절약:
- 브라우저/컨텍스트/페이지를 프로세스 수명 동안 재사용 (회차마다 Chromium 재실행 방지
  → JS 번들·쿠키 재사용, 회차당 다운로드 급감)
- 불필요 리소스 차단: image/font/media/stylesheet → route.abort() (본문 추출엔 불필요)
- 프록시: DataImpulse 단일 (MaskProxy 폴백 제거 — toki31 통과 불가)
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import select
import socket
import threading
from typing import Optional, Tuple

from lib.sources import get_base_url
from lib.domain_router import auto_update_base, base_of, candidate_bases, update_base_url

logger = logging.getLogger(__name__)

# .env.local에서 프록시 설정 로드
ENV_LOCAL = os.path.join(os.path.dirname(__file__), '..', '.env.local')

# 하위 호환용 모듈 상수 — 실제 사용은 _toki_base()로 최신 base_url을 읽는다.
TOKI31_BASE = get_base_url("toki31")


def _toki_base() -> str:
    """최신 toki31 base_url (도메인 자동 전환 반영)."""
    return get_base_url("toki31")

# 프록시: DataImpulse 단일 (MaskProxy는 toki31 통과 불가 → 폴백 제거)
_PROXY_PREFIX = "DATAIMPULSE"
_PROXY_DEFAULT_HOST = "gw.dataimpulse.com"
_PROXY_DEFAULT_PORT = "823"

# 본문 추출에 불필요한 리소스 → 차단 (트래픽 절약)
_BLOCKED_RESOURCE_TYPES = ("image", "font", "media", "stylesheet")

# 트래커/광고 도메인 → 차단 (본문 추출과 무관, 네트워크 절약)
# 실측: whoas.xyz/live/track.js 등. 정확한 매칭으로 오차단 방지.
_TRACKER_DOMAINS = (
    "whoas.xyz",
    "www.googletagmanager.com",
    "www.google-analytics.com",
)

# ad_guard_bg.wasm(403KB/회차, 사이트 anti-adblock): 차단하면 본문 추출이 실패하므로
# **차단하지 않고 로컬 캐시로 재서빙**한다 (첫 회차 1회 다운로드 → 이후 0 네트워크).
# WebAssembly.instantiateStreaming으로 로드되는 JS에는 정상 응답으로 보이므로
# anti-adblock 탐지도 트리거하지 않는다. (Playwright route.fulfill 패턴)
_WASM_CACHE_URL_MARKER = "ad_guard_bg.wasm"

# 프록시 인증/연결 실패 시 브라우저 리셋 임계값
_RESET_AFTER_CONSECUTIVE_FAILURES = 3

# 안전장치 한도 (환경변수로 오버라이드)
# - novel-content API 페이로드 상한 (정상 ~24KB, 60KB 초과 시 비정상으로 판단)
# - 회차당 총 트래픽 상한: JS/wasm 로컬 캐시 재서빙 이후 실측
#   콜드(첫 로드) ~0.94MB / 웜(캐시 히트) ~0.18MB가 정상.
#   상한은 "비정상 대용량" 안전장치로 정상 대비 여유를 두되, 캐시 전처럼
#   재다운로드 시대의 느슨한 값(2.5/2.0MB)보다 타이트하게 잡는다.
#   (캐시 미스로 JS를 일부 재다운로드해도 웜 0.8MB 안에서 수용)
_NOVEL_CONTENT_MAX_BYTES = int(float(os.getenv('TOKI31_CONTENT_MAX_KB', '60'))) * 1024
_CHAPTER_COLD_MAX_BYTES = int(float(os.getenv('TOKI31_CHAPTER_COLD_MAX_MB', '1.5')) * 1024 * 1024)
_CHAPTER_WARM_MAX_BYTES = int(float(os.getenv('TOKI31_CHAPTER_WARM_MAX_MB', '0.8')) * 1024 * 1024)


# ── 레벨1 절감(A/B 토글) — TRAFFIC_OPTIMIZATION_GUIDE.md §4 ─────────────
# 각 레버는 env로 끄고 켤 수 있어 단계별 A/B/롤백이 가능하다(기본 ON).
_LAUNCH_TUNING_ENV = "EBOOK_TOK31_LAUNCH_TUNING"
_MIN_HEADERS_ENV = "EBOOK_TOK31_MIN_HEADERS"

CHROMIUM_TUNING_ARGS = (
    "--dns-prefetch-disable",
    "--disable-prefetch",
    "--no-referrers",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies",
)

# 요청 헤더 최소화 — 허용 헤더만 좁힌다(압축은 gzip/deflate/br/zstd 유지).
# Sec-Fetch/Sec-CH/DNT/Referer는 브라우저가 자동 부착하므로 여기서 제거하지 않는다.
MINIMAL_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Upgrade-Insecure-Requests": "1",
}


def _env_on(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _chromium_args() -> list:
    return list(CHROMIUM_TUNING_ARGS) if _env_on(_LAUNCH_TUNING_ENV) else []


def _request_headers() -> dict:
    return dict(MINIMAL_REQUEST_HEADERS) if _env_on(_MIN_HEADERS_ENV) else {}


# ── 레벨2 절감(A/B 토글, 기본 OFF) — TRAFFIC_OPTIMIZATION_GUIDE.md §10 ──
# 레벨1 채택 후 한 단계씩 켠다.
_CDP_BLOCK_ENV = "EBOOK_TOK31_CDP_BLOCK"
CDP_BLOCKED_URLS = (
    "*://whoas.xyz/*",
    "*://*.googletagmanager.com/*",
    "*://*.google-analytics.com/*",
)


def _cdp_blocked_urls() -> list:
    return list(CDP_BLOCKED_URLS) if _env_on(_CDP_BLOCK_ENV, default=False) else []


# ── 레벨3(조사): novel-content API 직접 호출(브라우저 제거) — 기본 OFF ──
# 브라우저가 이미 관측한 요청 스펙(spec)+쿠키를 재사용해 실패 시에만 폴백한다.
_HTTP_FIRST_ENV = "EBOOK_TOK31_HTTP_FIRST"
# 프록시 exit 국가 — DataImpulse __cr.<cc>. 기본 KR(사이트 타깃).
# [WHY] KR exit가 SNI/ISP 차단에 걸릴 때 타국가로 우회 가능(C안 실험).
_PROXY_COUNTRY_ENV = "EBOOK_TOK31_PROXY_COUNTRY"


def proxy_country() -> str:
    return (os.getenv(_PROXY_COUNTRY_ENV) or "kr").strip().lower()


def http_first_enabled() -> bool:
    return _env_on(_HTTP_FIRST_ENV, default=False)


def build_http_request(spec: dict, cookie: str) -> dict:
    """관측된 API 스펙 + 쿠키 → HTTP 요청(url/method/headers/data)으로 변환."""
    headers = dict(MINIMAL_REQUEST_HEADERS)
    if cookie:
        headers["Cookie"] = cookie
    method = (spec.get("method") or "GET").upper()
    data = spec.get("post_data")
    if data and "content-type" not in {k.lower() for k in headers}:
        headers["Content-Type"] = "application/json"
    return {"url": spec.get("url", ""), "method": method, "headers": headers, "data": data}


def _http_call(req: dict, proxy_url: Optional[str], timeout: float) -> dict:
    """requests로 API 호출(동기) — asyncio.to_thread에서 실행."""
    import requests

    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    fn = requests.post if req["method"] == "POST" else requests.get
    kwargs = {"headers": req["headers"], "proxies": proxies, "timeout": timeout, "verify": False}
    if req["method"] == "POST":
        kwargs["data"] = req["data"]
    resp = fn(req["url"], **kwargs)
    resp.raise_for_status()
    return resp.json()


async def fetch_content_api_http(
    spec: Optional[dict],
    cookie: str,
    proxy_url: Optional[str] = None,
    timeout: float = 10.0,
    caller=None,
) -> Optional[dict]:
    """novel-content API를 직접 호출해 페이로드 dict 반환(실패 시 None → 브라우저 폴백).

    [WHY] 3MB 렌더 대신 ~24KB JSON 직접 호출로 대역폭을 크게 줄인다(레벨3).
    스펙/쿠키가 없거나 검증(ok/payload) 실패면 None을 반환해 호출자가 브라우저로 폴백.
    """
    if not spec or not spec.get("url"):
        return None
    req = build_http_request(spec, cookie)
    call = caller or _http_call
    try:
        data = await asyncio.to_thread(call, req, proxy_url, timeout)
    except Exception as e:  # noqa: BLE001 — 실패는 폴백 신호
        logger.debug(f"HTTP 우선 호출 실패(폴백): {e}")
        return None
    if isinstance(data, dict) and data.get("ok") and data.get("payload"):
        return data
    return None


def _parse_proxy_key(value: str):
    """KV 결합 프록시 키 'user:pass@host:port' → (user, pass, host, port)."""
    user = pw = host = port = ""
    if "@" in value:
        cred, hostport = value.rsplit("@", 1)
        if ":" in cred:
            user, pw = cred.split(":", 1)
        if ":" in hostport:
            host, port = hostport.split(":", 1)
    return user, pw, host, port


def _load_proxy_env():
    """프록시 자격증명 로드 (DataImpulse 단일).

    우선순위:
    1. 개별 env var (Key Vault 주입)
       DATAIMPULSE_API_KEY / DATAIMPULSE_LOGIN / DATAIMPULSE_USER → USER
    2. KV 결합 키 (DATAIMPULSE_PROXY_KEY = user:pass@host:port) 파싱
    3. .env.local 파일 (로컬 개발 템플릿)
    """
    env = {}

    # 1. 개별 환경변수 우선 (Key Vault)
    proxy_keys = [
        'DATAIMPULSE_USER', 'DATAIMPULSE_PASS', 'DATAIMPULSE_HOST', 'DATAIMPULSE_PORT',
        'DATAIMPULSE_API_KEY', 'DATAIMPULSE_LOGIN',
    ]
    for key in proxy_keys:
        val = os.environ.get(key)
        if val:
            env[key] = val

    # 1b. KV 시크릿 이름 매핑: DATAIMPULSE-API-KEY/-LOGIN → USER
    if not env.get('DATAIMPULSE_USER'):
        mapped = env.get('DATAIMPULSE_API_KEY') or env.get('DATAIMPULSE_LOGIN')
        if mapped:
            env['DATAIMPULSE_USER'] = mapped

    # 2. KV 결합 키 파싱 — 개별 필드가 없으면 채운다.
    #    [WHY] 개별 PASS 가 없고 API-KEY(USER)만 있어도 동작해야 하므로
    #    USER 존재 여부와 무관하게 항상 파싱하고 setdefault(명시값 우선).
    combined = os.environ.get('DATAIMPULSE_PROXY_KEY', '')
    if not combined and os.path.exists(ENV_LOCAL):
        with open(ENV_LOCAL) as f:
            for line in f:
                if line.strip().startswith('DATAIMPULSE_PROXY_KEY='):
                    combined = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
    if combined:
        u, p, h, pt = _parse_proxy_key(combined)
        for suffix, val in (('USER', u), ('PASS', p), ('HOST', h), ('PORT', pt)):
            if val:
                env.setdefault(f'DATAIMPULSE_{suffix}', val)

    # 3. Fallback: .env.local 파일 (환경변수에 없는 것만)
    if os.path.exists(ENV_LOCAL):
        with open(ENV_LOCAL) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    if k not in env:  # 환경변수가 우선
                        env[k] = v.strip()
    return env


def _basic_proxy_auth(username: str, password: str) -> str:
    """Basic Proxy-Authorization 헤더 값 (Bearer 제외)."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {token}"


def _inject_proxy_auth(request_head: bytes, auth_header: str) -> bytes:
    """CONNECT/HTTP 요청 헤더에 Proxy-Authorization 주입 (기존 값 교체).

    [WHY] DataImpulse는 407 챌린지 없이 익명 CONNECT를 200으로 열고(무작위 geo),
    KR 타깃팅(`username__cr.kr`)은 Proxy-Authorization에만 반영된다.
    Chromium/Playwright는 407 전까지 자격증명을 보내지 않아 비한국 IP가 됨.
    """
    lines = request_head.split(b"\r\n")
    if not lines:
        return request_head
    out = [lines[0]]
    auth_line = f"Proxy-Authorization: {auth_header}".encode()
    replaced = False
    for ln in lines[1:]:
        if ln.lower().startswith(b"proxy-authorization:"):
            if not replaced:
                out.append(auth_line)
                replaced = True
            continue
        out.append(ln)
    if not replaced:
        out.append(auth_line)
    return b"\r\n".join(out)


_inject_proxy_lock = threading.Lock()
_inject_proxy_server: Optional[socket.socket] = None
_inject_proxy_port: Optional[int] = None
_inject_proxy_token: Optional[str] = None
_inject_proxy_upstream: Optional[Tuple[str, int]] = None
_inject_proxy_thread: Optional[threading.Thread] = None


def _pump(a: socket.socket, b: socket.socket) -> None:
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 60)
            if not r:
                return
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        return


def _inject_handle_client(client: socket.socket, token: str, upstream: Tuple[str, int]) -> None:
    try:
        client.settimeout(60)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = client.recv(4096)
            if not chunk:
                return
            buf += chunk
        head, rest = buf.split(b"\r\n\r\n", 1)
        head = _inject_proxy_auth(head, token)
        up = socket.create_connection(upstream, timeout=30)
        try:
            up.sendall(head + b"\r\n\r\n" + rest)
            _pump(client, up)
        finally:
            try:
                up.close()
            except OSError:
                pass
    except OSError:
        return
    finally:
        try:
            client.close()
        except OSError:
            pass


def _inject_proxy_loop(server: socket.socket, token: str, upstream: Tuple[str, int]) -> None:
    while True:
        try:
            client, _ = server.accept()
        except OSError:
            return
        threading.Thread(
            target=_inject_handle_client,
            args=(client, token, upstream),
            daemon=True,
        ).start()


def ensure_dataimpulse_inject_proxy(username: str, password: str, host: str, port) -> str:
    """DataImpulse용 로컬 인증 주입 HTTP 프록시 URL 반환 (없으면 기동).

    Chromium은 407 없이 프록시 자격증명을 보내지 않고, DataImpulse는 407을
    주지 않아 KR 타깃팅이 빠진다. 로컬 프록시가 CONNECT에만 인증을 주입한다.
    """
    global _inject_proxy_server, _inject_proxy_port, _inject_proxy_token
    global _inject_proxy_upstream, _inject_proxy_thread

    auth = _basic_proxy_auth(username, password)
    upstream = (host, int(port))
    with _inject_proxy_lock:
        if (
            _inject_proxy_server is not None
            and _inject_proxy_port
            and _inject_proxy_token == auth
            and _inject_proxy_upstream == upstream
        ):
            return f"http://127.0.0.1:{_inject_proxy_port}"

        if _inject_proxy_server is not None:
            try:
                _inject_proxy_server.close()
            except OSError:
                pass
            _inject_proxy_server = None
            _inject_proxy_port = None

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(64)
        port_num = srv.getsockname()[1]
        _inject_proxy_server = srv
        _inject_proxy_port = port_num
        _inject_proxy_token = auth
        _inject_proxy_upstream = upstream
        _inject_proxy_thread = threading.Thread(
            target=_inject_proxy_loop,
            args=(srv, auth, upstream),
            daemon=True,
        )
        _inject_proxy_thread.start()
        logger.info(
            "toki31 KR 인증 주입 프록시 기동: 127.0.0.1:%s -> %s:%s",
            port_num, host, port,
        )
        return f"http://127.0.0.1:{port_num}"


def playwright_proxy_config(env: Optional[dict] = None) -> Optional[dict]:
    """Playwright launch용 proxy 설정 (DataImpulse 단일). KR은 주입 프록시로 보장."""
    if env is None:
        env = _load_proxy_env()
    user = env.get("DATAIMPULSE_USER", "")
    password = env.get("DATAIMPULSE_PASS", "")
    host = env.get("DATAIMPULSE_HOST", _PROXY_DEFAULT_HOST)
    port = env.get("DATAIMPULSE_PORT", _PROXY_DEFAULT_PORT)
    if not user or not password:
        return None
    if "__cr." not in user:
        user = user + f"__cr.{proxy_country()}"
    server = ensure_dataimpulse_inject_proxy(user, password, host, port)
    return {"server": server}


def b64url_decode(s: str) -> bytes:
    """Decode base64url string to bytes."""
    s = s.replace("-", "+").replace("_", "/")
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.b64decode(s)


def b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string."""
    return base64.b64encode(data).decode().replace("+", "-").replace("/", "_").rstrip("=")


def derive_key(nv_cookie: str, novel_id: str, episode_id: str) -> bytes:
    """AES-GCM 키 파생.

    JS 코드 (역공학):
        let r = [e, new TextEncoder().encode(`:${t}:${n}:v3`)];
        keyMaterial = r[0] + r[1]  // e (bytes) + ":t:n:v3" (bytes)
        key = SHA-256(keyMaterial)

    여기서:
        e = base64url_decode(nv_cookie.split('.')[0])  // nv 쿠키의 첫 부분 디코드
        t = novelId
        n = episodeId (episodeRef 아님!)

    주의: 기존 구현과 달리 episodeRef가 아닌 episodeId를 사용.
    """
    # nv 쿠키의 첫 부분 (before '.')을 base64url 디코드
    part1_b64 = nv_cookie.split('.')[0]
    padding = 4 - len(part1_b64) % 4
    if padding != 4:
        part1_b64 += '=' * padding
    part1_bytes = base64.urlsafe_b64decode(part1_b64)

    salt = f":{novel_id}:{episode_id}:v3".encode('utf-8')
    combined = part1_bytes + salt
    return hashlib.sha256(combined).digest()


def decrypt_payload(payload_b64: str, key: bytes) -> str:
    """AES-GCM 복호화.

    Payload format: base64url(IV[12] || ciphertext+tag[16])
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = b64url_decode(payload_b64)
    if len(raw) < 28:
        raise ValueError(f"Payload too short: {len(raw)} bytes (need >= 28)")

    iv = raw[:12]
    ciphertext = raw[12:]

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(iv, ciphertext, None)
    return plaintext.decode('utf-8')


def extract_text_from_content(content_json: str) -> str:
    """콘텐츠 JSON에서 본문 텍스트 추출.

    Returns:
        추출된 본문 텍스트
    """
    try:
        data = json.loads(content_json)
    except json.JSONDecodeError:
        # JSON이 아닌 경우 그대로 반환
        return content_json

    kind = data.get('kind', 'unknown')

    if kind == 'text' and isinstance(data.get('paragraphs'), list):
        return '\n\n'.join(data['paragraphs'])

    elif kind == 'html' and isinstance(data.get('html'), str):
        html = data['html']
        # HTML 태그 제거
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'</p>', '', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&amp;(nbsp|amp|quot|apos|lt|gt|#\d{1,7}|#x[0-9a-fA-F]{1,6});',
                       lambda m: {'nbsp': ' ', '&': '&', '"': '"', "'": "'",
                                  '<': '<', '>': '>'}.get(m.group(1), m.group(0)),
                       text)
        return text.strip()

    elif kind == 'text-shuffled' and isinstance(data.get('paragraphs'), list):
        paragraphs = data['paragraphs']
        perm = data.get('perm', [])
        if perm and len(perm) == len(paragraphs):
            # Unshuffle
            unshuffled = [''] * len(paragraphs)
            for i, p_idx in enumerate(perm):
                if 0 <= p_idx < len(paragraphs):
                    unshuffled[p_idx] = paragraphs[i]
            return '\n\n'.join(unshuffled)
        return '\n\n'.join(paragraphs)

    return str(data)


class Toki31Collector:
    """toki31 챕터 수집기 — 브라우저 재사용 + 리소스 차단.

    브라우저/컨텍스트/페이지를 수명 동안 유지해 JS 번들·쿠키를 재사용한다.
    (회차마다 Chromium을 새로 띄우면 JS 번들(수백 KB)을 매번 재다운로드)
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._proxy = None
        self._content_payload = {}
        self._response_event = asyncio.Event()
        self._consecutive_failures = 0
        self._traffic_total = 0  # 프록시로 받은 총 응답 바이트 (실측, 수명 누적)
        self._traffic_by_type: dict = {}  # resource_type → 누적 바이트 (절감 A/B 분석용)
        self._encoding_counts: dict = {}  # content-encoding → 응답 수 (압축 검증)
        self._content_api_spec: Optional[dict] = None  # 관측된 novel-content 요청 스펙(레벨3)
        self._is_cold = True  # 브라우저 첫 로드 여부 (JS 번들 전체 다운로드 → 상한 높게)
        self._wasm_cache = {}  # ad_guard_bg.wasm url → bytes (챕터 간 재서빙)
        self._js_cache = {}  # JS 청크 url → bytes (검증: 동일 URL 내용 안정)
        self._js_cache_hits = set()  # 캐시로 재서빙된 JS url (계상 제외용)
        self._resolve_proxy()

    # --- 프록시 ---

    def _resolve_proxy(self):
        """프록시 설정 해석 — DataImpulse 단일 (MaskProxy 폴백 없음)."""
        self._proxy = playwright_proxy_config()
        if self._proxy:
            logger.info(f"toki31 프록시 설정: {self._proxy.get('server')}")
        else:
            logger.error("toki31 프록시 자격증명 없음 — DataImpulse 자격증명 확인")

    @property
    def has_proxy(self) -> bool:
        return bool(self._proxy)

    # --- 브라우저 수명 ---

    async def _ensure_started(self) -> None:
        """브라우저 1회 실행 (재사용). 이미 실행 중이면 no-op."""
        if self._browser:
            return
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        launch_kwargs = {"headless": True, "args": _chromium_args()}
        if self._proxy:
            launch_kwargs["proxy"] = self._proxy
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
        )
        _headers = _request_headers()
        if _headers:
            await self._context.set_extra_http_headers(_headers)
        self._page = await self._context.new_page()
        await self._apply_cdp_block()

        # novel-content API 응답 리스너 (브라우저 수명 동안 1회만 등록)
        self._content_payload = {}
        self._response_event = asyncio.Event()

        async def _on_response(response):
            # 트래픽 실측: content-length 우선, 없으면 body 크기 (리소스 차단 후
            # 남는 응답은 HTML/JS/API뿐이라 프록시 과금 바이트의 좋은 근사)
            # 캐시 히트(디스크/메모리)는 네트워크 바이트가 0이므로 집계 제외 —
            # 안 그러면 브라우저 재사용 시 JS 재다운로드가 실제보다 크게 잡혀
            # 웜 상한을 오초과해 정상 챕터가 차단된다.
            # ad_guard_bg.wasm은 캐시 재서빙(route.fulfill)으로 네트워크 바이트가
            # 0 (첫 1회만 실다운로드). route.fulfill 응답은 requestStart=-1이라
            # timing 기반 캐시 판정이 안 되므로 URL로 직접 제외.
            if _WASM_CACHE_URL_MARKER in response.url:
                return
            # 캐시로 재서빙된 JS도 0 네트워크 → 계상 제외
            if response.url in self._js_cache_hits:
                return
            try:
                tm = response.request.timing
                if tm:
                    rs = tm.get('responseStart')
                    rq = tm.get('requestStart')
                    # 캐시 히트: 두 시각 모두 존재·0 이상이고 요청 지속시간이 ~0ms
                    if (isinstance(rs, (int, float)) and isinstance(rq, (int, float))
                            and rs >= 0 and rq >= 0 and (rs - rq) < 1):
                        return
            except Exception:
                pass
            try:
                cl = response.headers.get('content-length')
                if cl and cl.isdigit():
                    size = int(cl)
                else:
                    size = len(await response.body())
                self._traffic_total += size
                rtype = getattr(response, "resource_type", None) or "other"
                self._traffic_by_type[rtype] = self._traffic_by_type.get(rtype, 0) + size
                ce = (response.headers.get("content-encoding") or "identity").lower()
                self._encoding_counts[ce] = self._encoding_counts.get(ce, 0) + 1
                # 응답별 트래픽 상세 로깅 (50KB 이상 또는 API 응답)
                if size > 50 * 1024 or '/api/' in response.url:
                    logger.info(
                        f"    📡 {response.status} {response.resource_type} "
                        f"{size/1024:.1f}KB {response.url[:100]}"
                    )
            except Exception:
                pass
            if '/api/novel-content' in response.url:
                try:
                    data = await response.json()
                    if data.get('ok') and data.get('payload'):
                        payload = data['payload']
                        payload_bytes = len(payload)
                        # 안전장치: 본문 페이로드가 비정상 대용량이면 차단 (정상 ~24KB)
                        if payload_bytes > _NOVEL_CONTENT_MAX_BYTES:
                            logger.warning(
                                f"novel-content 페이로드 비정상 대용량: {payload_bytes}B "
                                f"(한도 {_NOVEL_CONTENT_MAX_BYTES}B) — 차단"
                            )
                            self._content_payload['oversized'] = True
                        else:
                            self._content_payload['data'] = data
                            self._response_event.set()
                            logger.debug(f"novel-content response captured ({payload_bytes}B)")
                except Exception:
                    pass

        self._page.on("response", _on_response)

        async def _on_request(request):
            # 레벨3: 브라우저가 관측한 novel-content 요청 스펙을 저장(HTTP 직접 호출 재사용)
            try:
                if "/api/novel-content" in request.url:
                    self._content_api_spec = {
                        "url": request.url,
                        "method": request.method,
                        "post_data": request.post_data,
                    }
            except Exception:  # noqa: BLE001
                pass

        self._page.on("request", _on_request)

        # 불필요한 리소스 차단 (image/font/media/stylesheet → abort, 트래픽 절약)
        await self._page.route("**/*", self._block_unnecessary)
        logger.info("toki31 브라우저 시작 완료 (리소스 차단 + 재사용)")

    async def _apply_cdp_block(self) -> None:
        """레벨2: CDP Network.setBlockedURLs로 트래커 도메인을 네트워크 레벨 차단."""
        urls = _cdp_blocked_urls()
        if not urls:
            return
        try:
            client = await self._context.new_cdp_session(self._page)
            await client.send("Network.setBlockedURLs", {"urls": urls})
            logger.info(f"CDP setBlockedURLs 적용: {urls}")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"CDP setBlockedURLs 실패(무시): {e}")

    async def _content_cookie_header(self) -> str:
        """현재 브라우저 세션 쿠키 → 'k=v; ...' (HTTP 우선 호출용)."""
        try:
            cookies = await self._context.cookies() if self._context else []
        except Exception:  # noqa: BLE001
            cookies = []
        return "; ".join(
            f"{c.get('name')}={c.get('value')}"
            for c in cookies
            if isinstance(c, dict) and c.get("name")
        )

    def _proxy_url(self) -> Optional[str]:
        """requests용 프록시 URL — DataImpulse는 **로컬 inject 프록시**를 쓴다.

        [WORKAROUND] Chromium은 407 없이는 자격증명을 보내지 않아 KR 타깃팅이 빠진다.
        DataImpulse도 407을 주지 않으므로, 생 자격증명 대신 inject 프록시(127.0.0.1)를
        사용해야 한다(실측: 생 자격증명 직접 사용 시 SSLError).
        """
        try:
            config = playwright_proxy_config()
        except Exception:  # noqa: BLE001
            config = None
        return config.get("server") if config else None

    async def _fetch_content_api_http(self, timeout_ms: int) -> Optional[dict]:
        """HTTP 우선 시도(기본 OFF) — 스펙/쿠키 없거나 실패면 None(브라우저 폴백)."""
        if not http_first_enabled() or not self._content_api_spec:
            return None
        cookie = await self._content_cookie_header()
        return await fetch_content_api_http(
            self._content_api_spec,
            cookie,
            self._proxy_url(),
            timeout=max(5.0, timeout_ms / 1000),
        )

    async def _block_unnecessary(self, route, request):
        """불필요한 리소스 차단 — 이미지/폰트/미디어/CSS 차단, JS만 허용.

        추가:
        - 트래커/광고 도메인 차단 (whoas.xyz 등)
        - ad_guard_bg.wasm(anti-adblock)은 **로컬 캐시 재서빙** — 차단 대신
          첫 요청만 다운로드해 캐시하고, 이후 요청은 메모리에서 응답한다.
          (콘텐츠 추출에 필수라 차단 불가하지만 403KB/회차 재다운로드를 없앤다)
        """
        url = request.url
        resource_type = request.resource_type

        # 1) 트래커/광고 도메인 차단
        if any(td in url for td in _TRACKER_DOMAINS):
            await route.abort()
            return

        # 2) JS 청크 — 첫 다운로드 후 로컬 캐시 재서빙 (0 네트워크)
        #    (검증: 동일 URL의 내용은 챕터 간 안정 — 캐시 안전)
        if resource_type == "script":
            cached = self._js_cache.get(url)
            if cached is not None:
                self._js_cache_hits.add(url)
                await route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body=cached,
                )
                return
            try:
                resp = await route.fetch()
                self._js_cache[url] = await resp.body()
                await route.fulfill(response=resp)
                return
            except Exception:
                pass

        # 3) ad_guard_bg.wasm — 첫 다운로드 후 캐시 재서빙
        if _WASM_CACHE_URL_MARKER in url:
            cached = self._wasm_cache.get(url)
            if cached is not None:
                await route.fulfill(
                    status=200,
                    content_type="application/wasm",
                    body=cached,
                )
                return
            try:
                resp = await route.fetch()
                self._wasm_cache[url] = await resp.body()
                await route.fulfill(response=resp)
                return
            except Exception:
                # 캐시 실패 시 그대로 통과 (다운로드) — 추출 우선
                pass

        # 3) 미디어 계열 차단
        if resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    async def _close_browser(self) -> None:
        """브라우저 정리 (다음 호출에서 재실행)."""
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        self._content_payload = {}
        self._response_event = asyncio.Event()
        self._is_cold = True  # 리셋 후 JS 번들 재다운로드 → 콜드 상한 적용

    # --- 챕터 수집 ---

    async def collect_chapter(
        self,
        novel_id: str,
        chapter_id: str,
        timeout_ms: int = 60000,
    ) -> Optional[Tuple[str, str]]:
        """단일 챕터 본문 수집.

        Returns:
            (title, content_text) or None on failure
        """
        if not self._proxy:
            logger.error("toki31 프록시 자격증명 없음 — 수집 불가")
            return None

        await self._ensure_started()
        page = self._page

        # 회차별 트래픽 한도 — 첫 로드(콜드)는 JS 번들 전체로 상한 높게, 이후(웜)는 낮게
        is_cold = self._is_cold
        chapter_start_bytes = self._traffic_total
        traffic_cap = _CHAPTER_COLD_MAX_BYTES if is_cold else _CHAPTER_WARM_MAX_BYTES

        # 이벤트 초기화 (이전 회차 응답 무시)
        self._response_event.clear()
        self._content_payload.clear()

        target_url = f"{_toki_base().rstrip('/')}/novel/{novel_id}/{chapter_id}"

        # 페이지 로드 (재시도 포함)
        loaded = False
        fatal_proxy_error = False
        for attempt in range(3):
            try:
                resp = await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if resp and resp.status == 200:
                    loaded = True
                    break
            except Exception as e:
                msg = str(e)
                logger.warning(f"Page load attempt {attempt + 1} failed: {msg}")
                if any(k in msg for k in ("ERR_PROXY", "PROXY_AUTH", "proxy authentication")):
                    # 프록시 인증/연결 문제 → 브라우저 리셋 필요
                    fatal_proxy_error = True
                    break
                if attempt < 2:
                    await page.wait_for_timeout(3000)

        # 현재 도메인 사망 가능성 → 미러 도메인(base_url 도메인 목록)으로 재시도
        if not loaded and not fatal_proxy_error:
            old_base = base_of(target_url)
            for base in candidate_bases("toki31"):
                if base == old_base:
                    continue
                alt_url = f"{base.rstrip('/')}/novel/{novel_id}/{chapter_id}"
                try:
                    resp = await page.goto(alt_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    if resp and resp.status == 200:
                        loaded = True
                        target_url = alt_url
                        update_base_url("toki31", base)
                        logger.warning(f"🔄 [toki31] 미러 페일오버: {old_base} → {base}")
                        break
                except Exception as e:
                    msg = str(e)
                    logger.warning(f"Mirror load failed ({base}): {msg}")
                    if any(k in msg for k in ("ERR_PROXY", "PROXY_AUTH", "proxy authentication")):
                        fatal_proxy_error = True
                        break

        if not loaded:
            logger.error(f"Failed to load {target_url} after 3 attempts")
            if fatal_proxy_error:
                self._consecutive_failures += 1
                if self._consecutive_failures >= _RESET_AFTER_CONSECUTIVE_FAILURES:
                    logger.warning("프록시 연속 실패 — 브라우저 리셋")
                    await self._close_browser()
                    self._consecutive_failures = 0
            else:
                self._consecutive_failures = 0
            return None

        # 리다이렉트 최종 URL 감지 → sources.json base_url 자동 갱신
        # (구 도메인이 새 도메인으로 301/302 리다이렉트하는 동안 이를 활용)
        try:
            resolved = page.url
            auto_update_base("toki31", target_url, resolved)
        except Exception:
            pass

        self._consecutive_failures = 0

        # 첫 로드 성공 → JS 번들 캐시 완료. 이후 회차는 웜(낮은 상한) 적용
        self._is_cold = False

        # 제목 추출 (페이지 타이틀)
        title_text = await page.title()
        if ' - ' in title_text:
            parts = title_text.split(' - ')
            if len(parts) >= 2:
                title_text = parts[1].split('|')[0].strip()

        # novel-content API 응답 대기 (ad-ack 완료 후 브라우저가 자동 호출, 최대 25s)
        if not self._content_payload.get('data'):
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=25)
            except asyncio.TimeoutError:
                pass

        if self._content_payload.get('oversized'):
            logger.error("novel-content 페이로드 비정상 대용량 — 회차 차단")
            return None

        if not self._content_payload.get('data'):
            logger.error("novel-content API response not received within 25s")
            return None

        # nv 쿠키 추출
        cookies = await self._context.cookies()
        nv_cookie = ""
        for c in cookies:
            if c['name'] == 'nv':
                nv_cookie = c['value']
                break

        if not nv_cookie:
            logger.error("nv cookie not found")
            return None

        payload = self._content_payload['data'].get('payload', '')
        if not payload:
            logger.error("Empty payload from novel-content")
            return None

        # 복호화
        try:
            key = derive_key(nv_cookie, novel_id, chapter_id)
            decrypted = decrypt_payload(payload, key)
            content_text = extract_text_from_content(decrypted)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None

        if not content_text or len(content_text) < 50:
            logger.error(f"Failed to extract content from {target_url}")
            return None

        # 회차별 트래픽 한도 점검 — 비정상 대용량이면 차단 (정상: 콜드 ~1MB / 웜 ~430KB)
        chapter_bytes = self._traffic_total - chapter_start_bytes
        if chapter_bytes > traffic_cap:
            logger.warning(
                f"회차 트래픽 비정상 대용량: {chapter_bytes / 1024:.0f}KB "
                f"(한도 {traffic_cap / 1024 / 1024:.1f}MB, {'콜드' if is_cold else '웜'}) — 회차 차단"
            )
            return None

        return (title_text, content_text.strip())


# 모듈 수준 싱글턴 — 프로세스 수명 동안 브라우저 재사용 (데이터 절약)
_collector: Optional[Toki31Collector] = None
_collector_loop: Optional[asyncio.AbstractEventLoop] = None


def get_traffic_total_bytes() -> int:
    """프로세스 수명 동안 프록시로 다운로드한 총 바이트 (실측 누적).

    pipeline의 트래픽 가드가 collect 전후 delta를 계산해 일일 한도에 반영한다.
    """
    return _collector._traffic_total if _collector else 0


def get_traffic_breakdown() -> dict:
    """resource_type별 누적 바이트 (내림차순). 절감 레버 분석용(OEC)."""
    if not _collector:
        return {}
    return dict(
        sorted(_collector._traffic_by_type.items(), key=lambda kv: kv[1], reverse=True)
    )


def get_encoding_counts() -> dict:
    """content-encoding별 응답 수 (압축 검증: br/zstd 비중 확인용)."""
    return dict(_collector._encoding_counts) if _collector else {}


def get_collector_state() -> dict:
    """현재 collector 상태 (트래픽 분석용)."""
    if not _collector:
        return {"is_cold": True, "traffic_total": 0, "js_cache": 0, "wasm_cache": 0, "js_hits": 0}
    return {
        "is_cold": _collector._is_cold,
        "traffic_total": _collector._traffic_total,
        "traffic_by_type": get_traffic_breakdown(),
        "encoding_counts": get_encoding_counts(),
        "content_http_ready": bool(_collector._content_api_spec),
        "js_cache": len(_collector._js_cache),
        "wasm_cache": len(_collector._wasm_cache),
        "js_hits": len(_collector._js_cache_hits),
    }


def fetch_chapter_content_full(
    novel_id: str,
    chapter_id: str,
    timeout_ms: int = 60000,
) -> Optional[Tuple[str, str]]:
    """toki31 챕터 콘텐츠 완전 추출 (동기 인터페이스, 브라우저 재사용).

    모듈 싱글턴 Toki31Collector를 고정 이벤트 루프에서 재사용한다.
    (호출마다 이벤트 루프/브라우저를 새로 만들지 않음)

    Returns:
        (title, content_text) or None on failure
    """
    global _collector, _collector_loop

    if _collector is None:
        _collector = Toki31Collector()

    if not _collector.has_proxy:
        logger.error("toki31 프록시 자격증명 없음 — DataImpulse 자격증명 확인")
        return None

    if _collector_loop is None or _collector_loop.is_closed():
        _collector_loop = asyncio.new_event_loop()

    try:
        return _collector_loop.run_until_complete(
            _collector.collect_chapter(novel_id, chapter_id, timeout_ms)
        )
    except Exception as e:
        logger.error(f"toki31 collect 실패: {type(e).__name__}: {e}")
        return None