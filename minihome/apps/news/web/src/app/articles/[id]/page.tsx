import { unstable_noStore as noStore } from "next/cache";
import { newsGet } from "@/lib/news";
import { notFound } from "next/navigation";
import Link from "next/link";

export const dynamic = "force-dynamic";

interface Article {
  id: number;
  title: string;
  title_ko: string;
  source: string;
  language: string;
  category: string;
  summary_ko: string;
  summary?: string;
  highlights_ko: string[];
  full_text: string;
  published_at: string;
  collected_at: string;
  url: string;
  relevance_score: number;
  concept_ids: string[];
}

interface RelatedRow {
  id: number;
  title: string;
  title_ko: string;
  source: string;
  relevance_score: number;
  published_at: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  ai: "AI",
  tech: "기술",
  economy: "경제",
  kor_economy: "한국경제",
  world_economy: "세계경제",
};

export default async function ArticleDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  noStore();
  const { id } = await params;
  const article = await newsGet<Article>(`/articles/${id}`);

  if (!article) {
    notFound();
  }

  const related =
    (await newsGet<{ articles: RelatedRow[] }>(
      `/articles/${id}/related`
    ))?.articles ?? [];

  return (
    <div className="max-w-3xl mx-auto">
      <Link
        href="/articles"
        className="text-blue-600 hover:underline text-sm mb-4 inline-block"
      >
        ← 목록으로
      </Link>

      <article className="bg-white rounded-lg border border-gray-200 p-6 dark:bg-gray-900 dark:border-gray-700">
        <div className="flex items-center gap-2 mb-3">
          <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-800 dark:text-gray-200">
            {CATEGORY_LABELS[article.category] || article.category}
          </span>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {article.source === "OpenRouter (RR Proxy)" ? "Open(RR)" : article.source}
          </span>
          <span className="text-sm text-gray-400 dark:text-gray-500">
            {article.language}
          </span>
          {article.published_at && (
            <span className="text-sm text-gray-400 ml-auto dark:text-gray-500">
              {new Date(article.published_at).toLocaleDateString("ko-KR")}
            </span>
          )}
        </div>

        <h1 className="text-xl font-bold mb-4 dark:text-white">
          {article.title_ko || article.title}
        </h1>

        {article.url && (
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline text-sm mb-4 inline-block"
          >
            원문 보기 →
          </a>
        )}

        {(article.summary_ko || article.summary) && (
          <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-100 dark:bg-blue-950 dark:border-blue-900">
            <h2 className="text-sm font-semibold text-blue-800 mb-2 dark:text-blue-300">
              요약
            </h2>
            <p className="text-sm text-gray-700 leading-relaxed dark:text-gray-300">
              {article.summary_ko || article.summary}
            </p>
          </div>
        )}

        {article.highlights_ko && article.highlights_ko.length > 0 && (
          <div className="mt-4">
            <h2 className="text-sm font-semibold text-gray-700 mb-2 dark:text-gray-300">
              하이라이트
            </h2>
            <ul className="list-disc list-inside space-y-1">
              {article.highlights_ko.map((h, i) => (
                <li
                  key={i}
                  className="text-sm text-gray-600 dark:text-gray-400"
                >
                  {h}
                </li>
              ))}
            </ul>
          </div>
        )}

        {article.full_text && (
          <div className="mt-6">
            <h2 className="text-sm font-semibold text-gray-700 mb-2 dark:text-gray-300">
              전체 본문
            </h2>
            <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap dark:text-gray-400">
              {article.full_text}
            </div>
          </div>
        )}

        <div className="mt-6 pt-4 border-t text-xs text-gray-400 flex gap-4 dark:border-gray-700 dark:text-gray-500">
          <span>ID: {article.id}</span>
          <span>수집: {new Date(article.collected_at).toLocaleString("ko-KR")}</span>
          {article.relevance_score > 0 && (
            <span>중요도: {article.relevance_score}</span>
          )}
        </div>
      </article>

      {related.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-3 dark:text-gray-300">
            관련 기사 ({related.length}건)
          </h2>
          <div className="space-y-2">
            {related.map((a) => (
              <a
                key={a.id}
                href={`/articles/${a.id}`}
                className="block p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors dark:bg-gray-800 dark:hover:bg-gray-700"
              >
                <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
                  {a.title_ko || a.title}
                </div>
                <div className="text-xs text-gray-500 mt-1 flex gap-2 dark:text-gray-400">
                  <span>
                    {article.source === "OpenRouter (RR Proxy)" ? "Open(RR)" : article.source}
                  </span>
                  {a.relevance_score > 0 && (
                    <span className="text-yellow-600 dark:text-yellow-400">
                      중요도: {a.relevance_score}
                    </span>
                  )}
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
