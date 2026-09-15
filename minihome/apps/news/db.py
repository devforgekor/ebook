#!/usr/bin/env python3
# Status: production
# Path: news.collector
"""News DB schema — PostgreSQL tables for news collection system.

Tables:
  news_articles — collected news articles with pipeline_state
  concepts — extracted concepts (Concept ID = canonical)
  term_variants — term variants for multilingual matching
  entity_alias — entity aliases (QID = alias, not primary key)
  api_call_logs — Exa/OpenRouter API usage tracking
"""

import os
import sys
from pathlib import Path

# Add scripts/ to path for lib imports
_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from lib.db import psql_ok, db_table_exists

SCHEMA_SQL = """
-- news_articles — collected news articles
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    language TEXT DEFAULT 'ko',
    category TEXT DEFAULT 'ai',
    full_text TEXT,
    highlights JSONB DEFAULT '[]'::JSONB,
    summary TEXT,
    pipeline_state TEXT DEFAULT 'raw'
        CHECK (pipeline_state IN ('raw', 'pending', 'cleaned', 'scanned', 'extracted', 'verified', 'enriched', 'embedded', 'needs_summary')),
    title_ko TEXT DEFAULT '',
    summary_ko TEXT DEFAULT '',
    highlights_ko JSONB DEFAULT '[]'::JSONB,
    dedup_group_id INTEGER,
    concept_ids JSONB DEFAULT '[]'::JSONB,
    relevance_score REAL DEFAULT 0.0,
    embedding vector(1024),
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_articles_pipeline_state ON news_articles(pipeline_state);
CREATE INDEX IF NOT EXISTS idx_news_articles_published_at ON news_articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_collected_at ON news_articles(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_url ON news_articles(url);
CREATE INDEX IF NOT EXISTS idx_news_articles_concept_ids ON news_articles USING GIN(concept_ids);
CREATE INDEX IF NOT EXISTS idx_news_articles_source ON news_articles(source);
CREATE INDEX IF NOT EXISTS idx_news_articles_pipeline_state_v2 ON news_articles(pipeline_state);
CREATE INDEX IF NOT EXISTS idx_news_articles_dedup_group ON news_articles(dedup_group_id);

-- 키 회전 상태 (JSON 파일 대체)
CREATE TABLE IF NOT EXISTS api_key_rotations (
    provider TEXT NOT NULL,
    key_index INT NOT NULL,
    key_name TEXT NOT NULL,
    calls BIGINT DEFAULT 0,
    fails BIGINT DEFAULT 0,
    last_used TIMESTAMPTZ,
    backoff_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (provider, key_index)
);

CREATE INDEX IF NOT EXISTS idx_api_key_rotations_provider ON api_key_rotations(provider);

-- 회로 차단기 상태
CREATE TABLE IF NOT EXISTS circuit_breakers (
    feed_name TEXT PRIMARY KEY,
    failure_count INT DEFAULT 0,
    last_failure TIMESTAMPTZ,
    tripped_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 수집 실행 로그
CREATE TABLE IF NOT EXISTS collection_runs (
    id BIGSERIAL PRIMARY KEY,
    run_type TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'no_changes')),
    items_fetched INT DEFAULT 0,
    items_changed INT DEFAULT 0,
    items_saved INT DEFAULT 0,
    error TEXT,
    diff_summary JSONB
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_type_date ON collection_runs(run_type, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_collection_runs_status ON collection_runs(status);

-- concepts — extracted concepts (Concept ID = canonical, language-agnostic)
CREATE TABLE IF NOT EXISTS concepts (
    id SERIAL PRIMARY KEY,
    concept_id TEXT UNIQUE NOT NULL,  -- hash(normalized_text + label)
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- PER, ORG, LOC, TECH, EVENT
    description TEXT,
    wikipedia_url TEXT,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    mention_count INTEGER DEFAULT 1,
    confidence REAL DEFAULT 0.0,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_concepts_concept_id ON concepts(concept_id);
CREATE INDEX IF NOT EXISTS idx_concepts_entity_type ON concepts(entity_type);

-- term_variants — multilingual term variants for matching
CREATE TABLE IF NOT EXISTS term_variants (
    id SERIAL PRIMARY KEY,
    concept_id TEXT NOT NULL REFERENCES concepts(concept_id),
    term TEXT NOT NULL,
    language TEXT NOT NULL,  -- ko, en, ja, zh, ...
    variant_type TEXT DEFAULT 'alias',  -- alias, abbreviation, translation
    confidence REAL DEFAULT 1.0,
    source TEXT DEFAULT 'manual',  -- manual, glinker, llm
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(concept_id, term, language)
);

CREATE INDEX IF NOT EXISTS idx_term_variants_term ON term_variants(term);
CREATE INDEX IF NOT EXISTS idx_term_variants_concept_id ON term_variants(concept_id);

-- entity_alias — QID as alias, never primary key (Wikidata Multigrid pattern)
CREATE TABLE IF NOT EXISTS entity_alias (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,  -- wikidata, glinker, llm
    source_key TEXT NOT NULL,  -- Q42, etc.
    entity_id INTEGER NOT NULL REFERENCES concepts(id),
    confidence REAL DEFAULT 1.0,
    asserted_by TEXT DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, source_key)
);

CREATE INDEX IF NOT EXISTS idx_entity_alias_source ON entity_alias(source, source_key);
CREATE INDEX IF NOT EXISTS idx_entity_alias_entity_id ON entity_alias(entity_id);

-- api_call_logs — cost tracking for Exa + OpenRouter
CREATE TABLE IF NOT EXISTS api_call_logs (
    id SERIAL PRIMARY KEY,
    api_provider TEXT NOT NULL,  -- exa, openrouter, gnews
    endpoint TEXT NOT NULL,
    request_params JSONB DEFAULT '{}'::JSONB,
    response_status INTEGER,
    response_time_ms REAL,
    tokens_used INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    key_index INTEGER,  -- which API key was used
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_call_logs_provider ON api_call_logs(api_provider, created_at DESC);
"""


def init_schema():
    """Initialize news DB schema. Safe to call multiple times (CREATE IF NOT EXISTS)."""
    print("[news/db] Initializing schema...")
    if db_table_exists("news_articles"):
        print("[news/db] Tables already exist, skipping creation")
        return True

    ok = psql_ok(SCHEMA_SQL)
    if ok:
        print("[news/db] Schema created successfully")
    else:
        print("[news/db] ERROR: Schema creation failed")
    return ok


def table_stats():
    """Return row counts for news tables."""
    tables = ["news_articles", "concepts", "term_variants", "entity_alias", "api_call_logs", "api_key_rotations", "circuit_breakers", "collection_runs"]
    stats = {}
    for t in tables:
        if db_table_exists(t):
            from lib.db import psql
            result = psql(f"SELECT COUNT(*) FROM {t}")
            stats[t] = int(result) if result else 0
        else:
            stats[t] = -1  # table doesn't exist
    return stats


if __name__ == "__main__":
    init_schema()
    stats = table_stats()
    for t, count in stats.items():
        print(f"  {t}: {count} rows")
