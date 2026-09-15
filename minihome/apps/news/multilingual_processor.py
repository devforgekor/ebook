#!/usr/bin/env python3
# Status: production
# Path: news.collector
"""Multilingual entity processor — Tavily-based entity extraction.

Architecture (dependency-free version):
  1. Regex-based NER (standard library): 1st pass
  2. Tavily (API, free tier): fallback for uncertain entities
  3. Wikidata SPARQL: QID lookup
  4. Local KB: temporary storage for emerging entities

Future: GLiNKER integration for higher accuracy NER.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add scripts/ to path for lib imports
_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from lib.auth.key_rotator import KeyRotator
from lib.db import psql_ok, esc_sql

# Tavily API config
TAVILY_API_URL = "https://api.tavily.com/search"
TAVILY_SECRET_KEY = "TRAVILY_API_KEYS"

# Confidence thresholds
HIGH_CONFIDENCE = 0.8
MIDDLE_CONFIDENCE = 0.5

# Simple regex patterns for NER (Korean + English)
NER_PATTERNS = {
    "TECH": [
        r"(?:AI|인공지능|머신러닝|딥러닝|LLM|대규모 언어 모델|GPT|BERT|transformer)",
        r"(?:Kubernetes|Docker|Podman|PostgreSQL|Redis|Elasticsearch)",
        r"(?:Python|JavaScript|TypeScript|Rust|Go|Java)",
        r"(?:React|Vue|Angular|Next\.js|Django|FastAPI|Spring)",
        r"(?:AWS|Azure|GCP|Google Cloud|Amazon|Microsoft)",
    ],
    "ORG": [
        r"(?:삼성|LG|SK|네이버|카카오|쿠팡|토스|배달의민족)",
        r"(?:Google|Microsoft|Apple|Meta|Amazon|OpenAI|Anthropic|DeepMind)",
        r"(?:Tesla|NVIDIA|Intel|AMD|Qualcomm)",
        r"(?:현대|기아|쌍용|한화|롯데|신세계|CJ)",
    ],
    "PER": [
        # Korean names (2-3 characters)
        r"(?:[가-힣]{2,3}(?:씨|님|대표|교수|박사|과장|부장|차장|팀장))",
        # English names (First Last)
        r"(?:[A-Z][a-z]+ [A-Z][a-z]+)",
    ],
    "LOC": [
        r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충청|전라|경상|제주)",
        r"(?:한국|일본|중국|미국|영국|독일|프랑스|캐나다|호주)",
        r"(?: Silicon Valley|New York|San Francisco|Tokyo|Seoul|London)",
    ],
    "PRODUCT": [
        r"(?:iPhone|iPad|MacBook|Galaxy|Pixel|Surface)",
        r"(?:ChatGPT|Claude|Gemini|Copilot|Siri|Alexa)",
        r"(?:GPT-4|GPT-5|Claude 3|Gemini Pro|Llama 3)",
    ],
}


def _load_tavily_keys() -> list[tuple[str, str]]:
    """Load Tavily API keys from secrets.env."""
    secrets_path = os.path.expanduser("~/.config/devforge/secrets.env")
    if not os.path.exists(secrets_path):
        return []

    keys = []
    for line in Path(secrets_path).read_text().splitlines():
        if line.startswith(f"{TAVILY_SECRET_KEY}="):
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
                    keys.append((f"tavily-{len(keys)}", item))
            break
    return keys


def _generate_concept_id(text: str, entity_type: str) -> str:
    """Generate canonical Concept ID (language-agnostic)."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    raw = f"{normalized}:{entity_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _wikidata_lookup(entity_name: str, cache: dict = None) -> Optional[str]:
    """Wikidata SPARQL lookup for QID with caching."""
    import urllib.request
    import urllib.parse

    # Check cache first
    if cache is not None and entity_name in cache:
        return cache[entity_name]

    sparql_query = f"""
    SELECT ?item WHERE {{
      ?item rdfs:label "{entity_name}"@en .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
    }} LIMIT 1
    """

    url = "https://query.wikidata.org/sparql"
    params = urllib.parse.urlencode({"query": sparql_query, "format": "json"})
    full_url = f"{url}?{params}"

    try:
        req = urllib.request.Request(full_url, headers={"User-Agent": "DevForge-News/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            bindings = data.get("results", {}).get("bindings", [])
            if bindings:
                item_uri = bindings[0]["item"]["value"]
                qid = item_uri.split("/")[-1]
                if cache is not None:
                    cache[entity_name] = qid
                return qid
    except Exception:
        pass
    
    # Cache negative results to avoid repeated lookups
    if cache is not None:
        cache[entity_name] = None
    return None


class MultilingualProcessor:
    """Multilingual entity processor with Tavily fallback."""

    def __init__(self):
        self.tavily_keys = _load_tavily_keys()
        self.tavily_rotator = KeyRotator(
            self.tavily_keys,
            state_file="/opt/workspace/minihome/apps/news/tavily_state.json"
        ) if self.tavily_keys else None
        self._stats = {"total": 0, "regex": 0, "tavily": 0, "wikidata": 0}

    def extract_entities(self, text: str, language: str = "ko") -> List[Dict]:
        """Extract entities from text.

        Flow:
          1. Regex NER → entities
          2. For each entity:
             - confidence >= 0.8 OR qid IS NOT NULL → use directly
             - confidence < 0.8 AND qid IS NULL → Tavily fallback
          3. Return enriched entities
        """
        self._stats["total"] += 1

        # Step 1: Regex NER
        entities = self._regex_ner(text, language)

        # Step 2: Enrich entities (with Wikidata cache to avoid repeated lookups)
        enriched = []
        wikidata_cache = {}
        
        # Limit Wikidata lookups to top 3 entities by confidence
        entities_sorted = sorted(entities, key=lambda e: e["confidence"], reverse=True)
        wikidata_lookups_remaining = 3
        
        for entity in entities_sorted:
            # Check if already high confidence
            if entity["confidence"] >= HIGH_CONFIDENCE:
                self._stats["regex"] += 1
                enriched.append(entity)
                continue

            # Step 3: Tavily fallback for uncertain entities
            if self.tavily_rotator and entity["confidence"] < MIDDLE_CONFIDENCE:
                entity = self._tavily_fallback(entity)
                self._stats["tavily"] += 1
            else:
                self._stats["regex"] += 1

            # Step 4: Wikidata lookup (with caching and limit)
            if wikidata_lookups_remaining > 0:
                qid = _wikidata_lookup(entity["text"], wikidata_cache)
                if qid:
                    entity["qid"] = qid
                    self._stats["wikidata"] += 1
                wikidata_lookups_remaining -= 1

            enriched.append(entity)

        return enriched

    def _regex_ner(self, text: str, language: str) -> List[Dict]:
        """Simple regex-based NER."""
        entities = []
        seen = set()

        for entity_type, patterns in NER_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    entity_text = match.group().strip()
                    if entity_text in seen:
                        continue
                    seen.add(entity_text)

                    # Calculate confidence based on match quality
                    confidence = 0.7 if len(entity_text) > 3 else 0.5

                    entities.append({
                        "text": entity_text,
                        "type": entity_type,
                        "confidence": confidence,
                        "concept_id": _generate_concept_id(entity_text, entity_type),
                        "qid": None,
                        "source": "regex",
                    })

        return entities

    def _tavily_fallback(self, entity: Dict) -> Dict:
        """Tavily fallback for uncertain entities."""
        if not self.tavily_rotator:
            return entity

        idx, name, key = self.tavily_rotator.pick()
        if key is None:
            return entity

        try:
            import urllib.request
            import urllib.parse

            payload = json.dumps({
                "query": entity["text"],
                "search_depth": "basic",
                "max_results": 3,
            }).encode()

            req = urllib.request.Request(
                TAVILY_API_URL,
                data=payload,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                results = data.get("results", [])
                if results:
                    entity["description"] = results[0].get("snippet", "")
                    entity["source"] = "tavily"
                    entity["confidence"] = 0.75
                    self.tavily_rotator.success(idx)
                else:
                    self.tavily_rotator.success(idx)

        except Exception:
            self.tavily_rotator.rate_limited(idx, 60)

        return entity

    def save_entities(self, entities: List[Dict], article_id: int) -> bool:
        """Save extracted entities to PostgreSQL (using esc_sql for safe interpolation)."""
        for entity in entities:
            concept_id = esc_sql(entity["concept_id"])
            canonical_name = esc_sql(entity["text"])[:200]
            entity_type = esc_sql(entity.get("type", "UNKNOWN"))
            confidence = float(entity.get("confidence", 0.0))

            psql_ok(f"""
                INSERT INTO concepts (concept_id, canonical_name, entity_type, confidence)
                VALUES ('{concept_id}', '{canonical_name}', '{entity_type}', {confidence})
                ON CONFLICT (concept_id) DO UPDATE SET
                    mention_count = concepts.mention_count + 1,
                    updated_at = NOW()
            """)

            term = esc_sql(entity["text"])[:200]
            source = esc_sql(entity.get("source", "regex"))
            psql_ok(f"""
                INSERT INTO term_variants (concept_id, term, language, source)
                VALUES ('{concept_id}', '{term}', 'ko', '{source}')
                ON CONFLICT (concept_id, term, language) DO NOTHING
            """)

            qid = entity.get("qid")
            if qid:
                qid = esc_sql(qid)
                psql_ok(f"""
                    INSERT INTO entity_alias (source, source_key, entity_id, confidence, asserted_by)
                    VALUES ('wikidata', '{qid}',
                            (SELECT id FROM concepts WHERE concept_id = '{concept_id}'),
                            {confidence}, 'system')
                    ON CONFLICT (source, source_key) DO NOTHING
                """)

        return True

    def stats(self) -> Dict[str, int]:
        """Return processing statistics."""
        return self._stats.copy()


if __name__ == "__main__":
    # Test the processor
    processor = MultilingualProcessor()

    test_texts = [
        "삼성이 새로운 AI 칩을 발표했다. 구글과 마이크로소프트도 경쟁에 뛰어들었다.",
        "OpenAI가 GPT-5를 공개했다. 일론 머스크는 이에 대해 우려를 표명했다.",
        "서울에서 AI 컨퍼런스가 열렸다. 삼성, LG, 네이버 등이 참석했다.",
    ]

    for text in test_texts:
        print(f"\n텍스트: {text}")
        entities = processor.extract_entities(text)
        for e in entities:
            print(f"  - {e['text']} ({e['type']}, {e['confidence']:.2f})")
            if e.get("qid"):
                print(f"    QID: {e['qid']}")

    print(f"\n통계: {processor.stats()}")
