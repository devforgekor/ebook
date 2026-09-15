#!/usr/bin/env python3
# Status: production
# Path: collector.py
"""Translate English articles to Korean — OpenRouter API with retry & fallback."""

import json
import os
import sys
import time
from typing import Any, Dict, List

import urllib.request

_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from utils import has_chinese


def _load_secret(key_name: str) -> str:
    secrets_path = os.path.expanduser("~/.config/devforge/secrets.env")
    with open(secrets_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key_name}="):
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                return raw
    return ""


def _get_openrouter_keys() -> List[str]:
    """Load OpenRouter keys from secrets.env in explicit priority order.

    Priority:
      1. MESIDS (primary)
      2. MINIPARK4U (secondary)
      3. Others (e.g. GEMMA31B_FREE, tertiary)
    """
    groups: Dict[str, List[str]] = {}
    secrets_path = os.path.expanduser("~/.config/devforge/secrets.env")
    try:
        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if "OPENROUTER" in line and "API_KEY" in line:
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if raw.startswith("sk-or-"):
                        if "MESIDS" in line:
                            groups.setdefault("mesids", []).append(raw)
                        elif "MINIPARK4U" in line:
                            groups.setdefault("minipark4u", []).append(raw)
                        else:
                            groups.setdefault("other", []).append(raw)
    except FileNotFoundError:
        pass

    # Dedupe within each group, then assemble in priority order
    result = list(dict.fromkeys(groups.get("mesids", [])))
    result.extend(dict.fromkeys(groups.get("minipark4u", [])))
    result.extend(dict.fromkeys(groups.get("other", [])))
    return result


# OpenRouter RR 프록시(openrouter-rr-proxy.service, :8451)가 3개 키를
# 라운드로빈으로 회전한다. 키는 유료 티어이므로 free 모델 대신 저렴한 유료
# 모델을 라운드로빈으로 사용해 429/한도 문제를 피한다.
_OPENROUTER_PROXY_URL = os.environ.get("OPENROUTER_RR_PROXY_URL", "http://127.0.0.1:8451")
_PROXY_MODELS = [
    "openai/gpt-4o-mini",
    "deepseek/deepseek-chat",
    "google/gemini-2.5-flash",
]
_proxy_model_idx = 0  # 모델 라운드로빈 시작 인덱스

# Gemini 폴백 — OpenRouter free tier가 429/한도 소진일 때 내부 Gemini OpenAI
# 프록시(gemini-openai-proxy.service, :4431)로 번역한다. 무료·안정적.
_GEMINI_PROXY_URL = os.environ.get("GEMINI_OPENAI_PROXY_URL", "http://127.0.0.1:4431")
_GEMINI_MODEL = os.environ.get("GEMINI_SUMMARY_MODEL", "gemini-2.5-flash")


def _call_gemini(prompt: str, retries: int = 2) -> str:
    """Call local Gemini OpenAI-compatible proxy. Returns content or empty."""
    payload = json.dumps({
        "model": _GEMINI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 3000,
    }).encode()
    req = urllib.request.Request(
        f"{_GEMINI_PROXY_URL}/v1/chat/completions", data=payload,
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content or ""
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < retries:
                time.sleep(3 * attempt)
                continue
            print(f"  [WARN] Gemini proxy failed: HTTP {e.code}")
            return ""
        except Exception as e:
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            print(f"  [WARN] Gemini proxy failed: {e}")
            return ""
    return ""


def _call_openrouter(prompt: str, model: str = None, retries: int = 3) -> str:
    """OpenRouter RR 프록시 경유 (키 라운드로빈) + 유료 모델 라운드로빈.

    프록시/모델 전부 실패 시 Gemini 프록시로 폴백한다.
    Returns response content on success, empty string on failure.
    """
    global _proxy_model_idx

    models = [model] if model else list(_PROXY_MODELS)
    if not model and models:
        # 호출마다 시작 모델을 순환시켜 공평 분배
        models = models[_proxy_model_idx:] + models[:_proxy_model_idx]
        _proxy_model_idx = (_proxy_model_idx + 1) % len(models)

    for m in models:
        payload = json.dumps({
            "model": m,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 3000,
        }).encode()
        req = urllib.request.Request(
            f"{_OPENROUTER_PROXY_URL}/v1/chat/completions", data=payload,
            headers={"Content-Type": "application/json"},
        )
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read())
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content:
                        return content
                    # Empty response — try next model
                    break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                    print(f"  [RATE] {m} proxy {e.code} — retry {attempt+2}/{retries}")
                    time.sleep(2 * (attempt + 1))
                    continue
                break
            except Exception:
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                break
    # 프록시 모든 모델 실패 → Gemini 폴백
    return _call_gemini(prompt)


_TRANSLATE_PROMPT = """You are a professional news translator and summarizer. Translate the following English news article to Korean.

Requirements:
1. Title: Translate the title naturally to Korean
2. Summary: Write a 300-400 character Korean summary that captures:
    - The core news event (what happened)
    - Key details and context (who, when, where)
    - Why it matters or its impact
3. Highlights: Extract 2-3 key points as a JSON array

CRITICAL CONSTRAINT: Output MUST use ONLY pure Korean Hangul and Latin script (for proper nouns, brands, numbers). 
ABSOLUTELY FORBIDDEN: Any Chinese characters or Hanja (한자/漢字/汉字) — including but not limited to:
방송→放送, 제공→提供, 적용→適用, 최저→最低, 단가→單價, 단위→單位, 후보→候補, 선거→選舉,
정당→政黨, 공동→共同, 모금→募金, 위원회→委員會, 명령→命令, 차단→遮斷, 행정→行政, 연방→聯邦,
법원→法院, 항소→抗訴, 결정→決定, 시행→施行, 광고→廣告, 방송사→放送社, 요금→料金.
Write EVERYTHING in pure Hangul (e.g., 방송, 제공, 적용, 최저, 단가, 단위, 후보, 선거, 정당, 공동, 모금, 위원회, 명령, 차단, 행정, 연방, 법원, 항소, 결정, 시행, 광고, 방송사, 요금).

Return ONLY valid JSON in this exact format:
{{"title_ko": "한글 제목", "summary_ko": "300-400자 요약", "highlights_ko": ["포인트1", "포인트2"]}}

Article Title: {title}
Article Text:
{full_text}"""


def translate_to_korean(title: str, summary: str, highlights: List[str], full_text: str = "") -> Dict[str, Any]:
    """Translate article to Korean. Returns dict with title_ko, summary_ko, highlights_ko.

    Includes fallback summary from RSS if API fails.
    """
    text_for_summary = full_text[:3000] if full_text else summary
    prompt = _TRANSLATE_PROMPT.format(title=title, full_text=text_for_summary)

    raw = _call_openrouter(prompt)
    if not raw:
        # Fallback: use RSS summary or first 300 chars as summary
        fallback_summary = summary
        if not fallback_summary and full_text:
            fallback_summary = full_text[:300].strip() + "..."
        # DO NOT fallback on title - leave empty to trigger retry
        return {
            "title_ko": "",
            "summary_ko": fallback_summary,
            "highlights_ko": highlights,
            "_summary_fallback": True,
        }

    try:
        json_str = raw.replace("```json\n", "").replace("```\n", "").replace("```", "").strip()
        parsed = json.loads(json_str)
        title_ko = parsed.get("title_ko", title)
        summary_ko = parsed.get("summary_ko", summary)
        highlights_ko = parsed.get("highlights_ko", highlights)

        if has_chinese(title_ko) or has_chinese(summary_ko) or any(has_chinese(h) for h in highlights_ko):
            print("  [WARN] Summary contains Chinese characters (한문) — normalizing")
            norm_prompt = (
                "The following Korean text contains Chinese characters (Hanja). "
                "Rewrite it replacing EVERY Chinese/Hanja character with its correct Korean Hangul equivalent. "
                "Preserve the FULL length, all sentences, and all facts. Do NOT shorten. "
                "Return ONLY valid JSON in this exact format: "
                '{"title_ko": "...", "summary_ko": "...", "highlights_ko": ["...", "..."]} '
                "No quotes, no explanation, no markdown.\n\n"
                f"Title: {title_ko}\nSummary: {summary_ko}\nHighlights: {highlights_ko}"
            )
            norm_raw = _call_openrouter(norm_prompt)
            if norm_raw and not has_chinese(norm_raw):
                try:
                    norm_parsed = json.loads(norm_raw.replace("```json\n", "").replace("```\n", "").replace("```", "").strip())
                    title_ko = norm_parsed.get("title_ko", title_ko)
                    summary_ko = norm_parsed.get("summary_ko", summary_ko)
                    highlights_ko = norm_parsed.get("highlights_ko", highlights_ko)
                    if not (has_chinese(title_ko) or has_chinese(summary_ko) or any(has_chinese(h) for h in highlights_ko)):
                        print("  [OK] Normalized successfully")
                        return {
                            "title_ko": title_ko,
                            "summary_ko": summary_ko,
                            "highlights_ko": highlights_ko,
                            "_summary_fallback": False,
                        }
                except (json.JSONDecodeError, KeyError):
                    pass
            print("  [WARN] Normalization failed — rejecting, will retry")
            raise ValueError("chinese_chars_detected")

        return {
            "title_ko": title_ko,
            "summary_ko": summary_ko,
            "highlights_ko": highlights_ko,
            "_summary_fallback": False,
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        fallback_summary = summary
        if not fallback_summary and full_text:
            fallback_summary = full_text[:300].strip() + "..."
        return {
            "title_ko": "",
            "summary_ko": fallback_summary,
            "highlights_ko": highlights,
            "_summary_fallback": True,
        }


def translate_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """Translate article to Korean. Sets needs_summary=True if fallback was used."""
    if article.get("language") == "ko":
        article["title_ko"] = article["title"]
        article["summary_ko"] = article.get("summary", "")
        article["highlights_ko"] = article.get("highlights", [])
        # Korean articles may still need summary if RSS didn't provide one
        if not article["summary_ko"]:
            article["needs_summary"] = True
        return article

    result = translate_to_korean(
        title=article["title"],
        summary=article.get("summary", ""),
        highlights=article.get("highlights", []),
        full_text=article.get("full_text", ""),
    )
    article.update(result)

    # Mark for retry if summary is fallback (truncated text)
    if result.get("_summary_fallback"):
        article["needs_summary"] = True

    return article
