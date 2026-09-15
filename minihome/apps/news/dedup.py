#!/usr/bin/env python3
# Status: production
# Path: collector.py, web api
"""News deduplication — title similarity clustering + canonical selection."""

import re
from typing import Dict, List, Optional

from scoring import SOURCE_TIERS

# Phase 3: TF-IDF clustering (sklearn optional)
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False


def normalize_title(title: str) -> str:
    """제목 정규화 (소문자, 특수문자 제거, 공백 정규화)."""
    t = title.lower()
    t = re.sub(r"[^\w\s가-힣]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def title_ngrams(title: str, n: int = 2) -> set:
    """제목 n-gram 생성."""
    words = title.split()
    if len(words) < n:
        return {title}
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def calc_title_similarity(t1: str, t2: str) -> float:
    """제목 유사도 (Jaccard similarity)."""
    n1 = title_ngrams(normalize_title(t1))
    n2 = title_ngrams(normalize_title(t2))
    if not n1 or not n2:
        return 0.0
    intersection = n1 & n2
    union = n1 | n2
    return len(intersection) / len(union) if union else 0.0


def select_canonical(articles: List[Dict]) -> Dict:
    """그룹 내 최적 기사 선택 (소스 등급 낮을수록 좋음 + 최초 시간)."""
    def sort_key(a):
        tier = SOURCE_TIERS.get(a.get("source", ""), 3)
        published = a.get("published_at", "")
        if hasattr(published, "isoformat"):
            published = published.isoformat()
        # Lower tier is better, earlier date is better
        return (tier, str(published))

    return min(articles, key=sort_key)


def cluster_articles(articles: List[Dict], threshold: float = 0.4) -> List[List[Dict]]:
    """기사 클러스터링 (유사한 기사 그룹핑)."""
    clusters: List[List[Dict]] = []

    for article in articles:
        title = article.get("title_ko") or article.get("title", "")
        if not title:
            continue

        added = False
        for cluster in clusters:
            representative = cluster[0]
            rep_title = representative.get("title_ko") or representative.get("title", "")
            sim = calc_title_similarity(title, rep_title)

            if sim >= threshold:
                cluster.append(article)
                added = True
                break

        if not added:
            clusters.append([article])

    return clusters


def cluster_articles_tfidf(articles: List[Dict], threshold: float = 0.5, min_size: int = 3) -> Optional[List[List[Dict]]]:
    """Phase 3: TF-IDF char_wb + greedy clustering (newsnack 방식).

    Returns None if sklearn unavailable (fallback signal).
    """
    if not _HAS_SKLEARN:
        return None

    titles = [a.get("title_ko") or a.get("title", "") for a in articles]
    if not titles or len(titles) < min_size:
        return None

    try:
        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 4),
            sublinear_tf=True,
            max_features=5000,
        )
        tfidf = vectorizer.fit_transform(titles)
        sim = cosine_similarity(tfidf)
    except Exception:
        return None

    # Greedy clustering
    clusters: List[List[Dict]] = []
    assigned = [False] * len(articles)

    for i in range(len(articles)):
        if assigned[i]:
            continue
        cluster = [articles[i]]
        assigned[i] = True
        for j in range(i + 1, len(articles)):
            if not assigned[j] and sim[i][j] >= threshold:
                cluster.append(articles[j])
                assigned[j] = True
        if len(cluster) >= min_size:
            clusters.append(cluster)
        else:
            clusters.extend([[a] for a in cluster])

    return clusters


def cluster_articles_hybrid(articles: List[Dict], threshold: float = 0.5, min_size: int = 3) -> List[List[Dict]]:
    """TF-IDF 기본, 실패 시 Jaccard fallback."""
    result = cluster_articles_tfidf(articles, threshold, min_size)
    if result is None:
        return cluster_articles(articles, threshold=0.4)
    return result



