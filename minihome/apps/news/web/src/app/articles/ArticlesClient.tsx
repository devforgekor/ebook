"use client";

import { useMemo } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

export interface Article {
  id: number;
  title: string;
  title_ko: string;
  source: string;
  language: string;
  category: string;
  summary_ko: string;
  summary?: string;
  highlights_ko: string[];
  published_at: string;
  collected_at: string;
  url: string;
  relevance_score: number;
  pipeline_state: string;
}

const CATEGORY_PRIORITY: Record<string, number> = {
  "kor_economy": 1,
  "world_economy": 2,
  tech: 3,
  ai: 4,
};

function getCategoryPriority(category: string): number {
  // Legacy economy category → map to kor_economy
  const key = category === "economy" ? "kor_economy" : category;
  return CATEGORY_PRIORITY[key] ?? 99;
}

function formatFullDate(dateStr: string): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일`;
}

export default function ArticlesClient({
  initialArticles,
  currentPage,
  totalPages,
  total,
  currentDate,
}: {
  initialArticles: Article[];
  currentPage: number;
  totalPages: number;
  total: number;
  currentDate: string;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const sortedArticles = useMemo(() => {
    return [...initialArticles].sort((a, b) => {
      const pa = getCategoryPriority(a.category);
      const pb = getCategoryPriority(b.category);
      if (pa !== pb) return pa - pb;
      return (
        new Date(b.published_at).getTime() - new Date(a.published_at).getTime()
      );
    });
  }, [initialArticles]);

  const makePageUrl = (p: number) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(p));
    return `${pathname}?${params.toString()}`;
  };

  const pageNumbers: (number | "...")[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pageNumbers.push(i);
  } else {
    pageNumbers.push(1);
    if (currentPage > 3) pageNumbers.push("...");
    const start = Math.max(2, currentPage - 1);
    const end = Math.min(totalPages - 1, currentPage + 1);
    for (let i = start; i <= end; i++) pageNumbers.push(i);
    if (currentPage < totalPages - 2) pageNumbers.push("...");
    pageNumbers.push(totalPages);
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold dark:text-gray-100">뉴스</h1>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {currentDate ? formatFullDate(currentDate) : ""} · 총 {total}건
        </span>
      </div>

      {sortedArticles.length === 0 ? (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          기사가 없습니다.
        </div>
      ) : (
        <div className="space-y-3">
          {sortedArticles.map((a) => (
            <Link
              key={a.id}
              href={`/articles/${a.id}`}
              className="block bg-white rounded-lg border border-gray-200 p-4 hover:shadow-md transition-shadow dark:bg-gray-900 dark:border-gray-800 dark:hover:bg-gray-800"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {a.source === "OpenRouter (RR Proxy)" ? "Open(RR)" : a.source}
                    </span>
                    {a.relevance_score >= 7 && (
                      <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200">
                        ★
                      </span>
                    )}
                  </div>
                  <h3 className="font-medium text-sm sm:text-base dark:text-gray-100">
                    {a.title_ko || a.title}
                  </h3>
                  {a.summary_ko || a.summary ? (
                    <p className="text-sm text-gray-600 mt-2 dark:text-gray-400">
                      {a.summary_ko || a.summary}
                    </p>
                  ) : a.pipeline_state === "needs_summary" ? (
                    <p className="text-sm text-orange-500 mt-2 dark:text-orange-400">
                      요약 생성 중...
                    </p>
                  ) : null}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <nav className="mt-8 flex items-center justify-center gap-1">
          {currentPage > 1 && (
            <Link
              href={makePageUrl(currentPage - 1)}
              className="px-3 py-2 text-sm rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 dark:text-gray-300"
            >
              ←
            </Link>
          )}
          {pageNumbers.map((p, i) =>
            p === "..." ? (
              <span key={`dots-${i}`} className="px-2 py-2 text-sm text-gray-400">
                ...
              </span>
            ) : (
              <Link
                key={p}
                href={makePageUrl(p)}
                className={`px-3 py-2 text-sm rounded-md ${
                  p === currentPage
                    ? "bg-blue-600 text-white font-medium"
                    : "hover:bg-gray-100 dark:hover:bg-gray-800 dark:text-gray-300"
                }`}
              >
                {p}
              </Link>
            )
          )}
          {currentPage < totalPages && (
            <Link
              href={makePageUrl(currentPage + 1)}
              className="px-3 py-2 text-sm rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 dark:text-gray-300"
            >
              →
            </Link>
          )}
        </nav>
      )}
    </div>
  );
}
