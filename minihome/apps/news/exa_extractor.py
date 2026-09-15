#!/usr/bin/env python3
# Status: production
# Path: news.collector
"""Content extractor — Exa primary, Tavily fallback, Brave fallback.

Extraction chain: Exa → Tavily → Brave LLM Context
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Add scripts/ to path for lib imports
_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

# API config
EXA_API_BASE = "https://api.exa.ai"
TAVILY_API_BASE = "https://api.tavily.com"
BRAVE_API_BASE = "https://api.search.brave.com"
EXA_SECRET_KEY = "EXA_API_KEYS"
TAVILY_SECRET_KEY = "TRAVILY_API_KEYS"
BRAVE_SECRET_KEY = "BRAVE_API_KEYS"


# DB-backed key rotators (replaces JSON file-based KeyRotator)
from collector.key_rotator_db import create_db_key_rotator


def _load_keys_from_secrets(provider: str, secret_key: str) -> list[tuple[str, str]]:
    """secrets.env에서 API 키 로드 (복호화 포함)"""
    secrets_path = os.path.expanduser("~/.config/devforge/secrets.env")
    if not os.path.exists(secrets_path):
        return []

    keys = []
    for line in Path(secrets_path).read_text().splitlines():
        if line.startswith(f"{secret_key}="):
            raw = line.split("=", 1)[1].strip().strip('"').strip("'")
            for item in raw.split(","):
                item = item.strip()
                if not item:
                    continue
                if ":" in item:
                    name, cipher = item.split(":", 1)
                    name = name.strip()
                    cipher = cipher.strip()
                    try:
                        from lib.auth.api_key_cipher import decrypt_data
                        plain = decrypt_data(cipher)
                        if plain is None:
                            plain = cipher
                    except Exception:
                        plain = cipher
                    keys.append((name, plain))
                else:
                    keys.append((f"{provider}-{len(keys)}", item))
            break
    return keys


class TavilyExtractor:
    """Tavily Extract API fallback."""

    def __init__(self):
        self.keys = _load_keys_from_secrets("tavily", "TRAVILY_API_KEYS")
        self.rotator = create_db_key_rotator("tavily", self.keys) if self.keys else None
        self._stats = {"total": 0, "success": 0, "rate_limited": 0, "error": 0}

    def extract_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract content from URL using Tavily Extract API."""
        self._stats["total"] += 1

        if not self.rotator:
            return None

        pick_result = self.rotator.pick()
        if pick_result is None:
            return None

        idx, name, key = pick_result
        if key is None:
            self._stats["error"] += 1
            return None

        try:
            payload = json.dumps({
                "urls": [url],
                "extract_depth": "basic",
                "format": "text",
            }).encode()

            with httpx.Client(timeout=httpx.Timeout(5.0, read=30.0)) as client:
                resp = client.post(
                    f"{TAVILY_API_BASE}/extract",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    content=payload,
                )

                if resp.status_code == 429:
                    self.rotator.rate_limited(idx, 60)
                    self._stats["rate_limited"] += 1
                    return None

                resp.raise_for_status()
                data = resp.json()
                self.rotator.success(idx)
                self._stats["success"] += 1

                results = data.get("results", [])
                if not results:
                    return None

                r = results[0]
                raw_content = r.get("raw_content", "")
                return {
                    "url": url,
                    "title": "",
                    "text": raw_content[:10000],
                    "highlights": [],
                    "summary": "",
                    "published_date": "",
                }

        except Exception:
            self.rotator.rate_limited(idx, 60)
            self._stats["error"] += 1
            return None

    def stats(self) -> Dict[str, int]:
        return self._stats.copy()


class BraveExtractor:
    """Brave LLM Context API fallback."""

    def __init__(self):
        self.keys = _load_keys_from_secrets("brave", "BRAVE_API_KEYS")
        self.rotator = create_db_key_rotator("brave", self.keys) if self.keys else None
        self._stats = {"total": 0, "success": 0, "rate_limited": 0, "error": 0}

    def extract_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract content using Brave LLM Context API (search by URL)."""
        self._stats["total"] += 1

        if not self.rotator:
            return None

        pick_result = self.rotator.pick()
        if pick_result is None:
            return None

        idx, name, key = pick_result
        if key is None:
            self._stats["error"] += 1
            return None

        try:
            with httpx.Client(timeout=httpx.Timeout(5.0, read=30.0)) as client:
                resp = client.get(
                    f"{BRAVE_API_BASE}/res/v1/llm/context",
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": key,
                    },
                    params={
                        "q": url,
                        "count": 1,
                        "maximum_number_of_urls": 1,
                        "maximum_number_of_tokens": 4096,
                    },
                )

                if resp.status_code == 429:
                    self.rotator.rate_limited(idx, 60)
                    self._stats["rate_limited"] += 1
                    return None

                resp.raise_for_status()
                data = resp.json()
                self.rotator.success(idx)

                generic = data.get("grounding", {}).get("generic", [])
                if not generic:
                    return None

                item = generic[0]
                snippets = item.get("snippets", [])
                text = "\n".join(snippets)[:10000]

                if not text:
                    return None

                self._stats["success"] += 1
                return {
                    "url": url,
                    "title": item.get("title", ""),
                    "text": text,
                    "highlights": [],
                    "summary": "",
                    "published_date": "",
                }

        except Exception:
            self.rotator.rate_limited(idx, 60)
            self._stats["error"] += 1
            return None

    def stats(self) -> Dict[str, int]:
        return self._stats.copy()


class ExaExtractor:
    """Content extractor — Exa → Tavily → Brave chain."""

    def __init__(self):
        self.keys = _load_keys_from_secrets("exa", "EXA_API_KEYS")
        self.rotator = create_db_key_rotator("exa", self.keys) if self.keys else None
        self.tavily = TavilyExtractor()
        self.brave = BraveExtractor()
        self._stats = {"total": 0, "success": 0, "rate_limited": 0, "error": 0, "tavily_fallback": 0, "brave_fallback": 0}

    def extract_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract content from URL. Exa → Tavily → Brave chain."""
        self._stats["total"] += 1

        if not self.rotator:
            return self._try_tavily(url)

        pick_result = self.rotator.pick()
        if pick_result is None:
            return self._try_tavily(url)

        idx, name, key = pick_result
        if key is None:
            return self._try_tavily(url)

        try:
            headers = {
                "x-api-key": key,
                "Content-Type": "application/json",
            }
            payload = {
                "urls": [url],
                "contents": {
                    "text": {"maxCharacters": 5000},
                    "highlights": True,
                },
            }

            with httpx.Client(timeout=httpx.Timeout(5.0, read=30.0)) as client:
                resp = client.post(
                    f"{EXA_API_BASE}/contents",
                    headers=headers,
                    json=payload,
                )

                if resp.status_code == 429:
                    self.rotator.rate_limited(idx, 60)
                    self._stats["rate_limited"] += 1
                    return self._try_tavily(url)

                resp.raise_for_status()
                data = resp.json()
                self.rotator.success(idx)

                results = data.get("results", [])
                if not results:
                    return self._try_tavily(url)

                r = results[0]
                text = r.get("text", "")
                if not text:
                    return self._try_tavily(url)

                self._stats["success"] += 1
                return {
                    "url": url,
                    "title": r.get("title", ""),
                    "text": text,
                    "highlights": r.get("highlights", []),
                    "summary": r.get("summary", ""),
                    "published_date": r.get("publishedDate", ""),
                }

        except Exception:
            self.rotator.rate_limited(idx, 60)
            self._stats["error"] += 1
            return self._try_tavily(url)

    def _try_tavily(self, url: str) -> Optional[Dict[str, Any]]:
        """Try Tavily as second fallback."""
        result = self.tavily.extract_content(url)
        if result:
            self._stats["tavily_fallback"] += 1
            return result
        return self._try_brave(url)

    def _try_brave(self, url: str) -> Optional[Dict[str, Any]]:
        """Try Brave as final fallback."""
        result = self.brave.extract_content(url)
        if result:
            self._stats["brave_fallback"] += 1
        return result

    def extract_batch(self, urls: List[str], batch_size: int = 5) -> List[Optional[Dict]]:
        """Extract content from multiple URLs in batches."""
        results = []
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            for url in batch:
                result = self.extract_content(url)
                results.append(result)
                # Small delay between requests
                time.sleep(0.5)
        return results

    def stats(self) -> Dict[str, int]:
        """Return extraction statistics."""
        stats = self._stats.copy()
        stats["tavily"] = self.tavily.stats()
        stats["brave"] = self.brave.stats()
        return stats


if __name__ == "__main__":
    # Test the extractor
    extractor = ExaExtractor()

    test_urls = [
        "https://techcrunch.com/2026/08/25/openai-gpt-5-release/",
    ]

    for url in test_urls:
        print(f"\nURL: {url}")
        result = extractor.extract_content(url)
        if result:
            print(f"  Title: {result['title']}")
            print(f"  Text: {result['text'][:200]}...")
            print(f"  Highlights: {result['highlights'][:2]}")
            print(f"  Summary: {result['summary'][:200]}")
        else:
            print("  Failed to extract")

    print(f"\nStats: {extractor.stats()}")
