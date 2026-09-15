"use client";

import { useState, useEffect } from "react";

interface Stats {
  total: number;
  byCategory: { category: string; count: string }[];
  byLanguage: { language: string; count: string }[];
  bySource: { source: string; count: string }[];
  recent: { date: string; count: string }[];
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then(setStats)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-center py-12 text-gray-500 dark:text-gray-400">로딩 중...</div>;
  if (!stats) return <div className="text-center py-12 text-gray-500 dark:text-gray-400">데이터 없음</div>;

  const maxCat = Math.max(...stats.byCategory.map((c) => parseInt(c.count)));
  const maxSrc = Math.max(...stats.bySource.map((s) => parseInt(s.count)));
  const maxRecent = Math.max(...stats.recent.map((r) => parseInt(r.count)));

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">대시보드</h1>

      {/* Total */}
      <div className="bg-white rounded-lg border p-6 mb-6 text-center dark:bg-gray-900 dark:border-gray-800">
        <div className="text-4xl font-bold text-blue-600 dark:text-blue-400">{stats.total.toLocaleString()}</div>
        <div className="text-sm text-gray-500 mt-1 dark:text-gray-400">총 기사 수</div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* By Category */}
        <div className="bg-white rounded-lg border p-6 dark:bg-gray-900 dark:border-gray-800">
          <h2 className="font-semibold mb-4 dark:text-gray-200">카테고리별</h2>
          <div className="space-y-3">
            {stats.byCategory.map((c) => (
              <div key={c.category}>
                <div className="flex justify-between text-sm mb-1">
                  <span>{c.category.toUpperCase()}</span>
                  <span className="text-gray-500 dark:text-gray-400">{c.count}건</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-2 dark:bg-gray-700">
                  <div
                    className="bg-blue-500 h-2 rounded-full dark:bg-blue-400"
                    style={{ width: `${(parseInt(c.count) / maxCat) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* By Language */}
        <div className="bg-white rounded-lg border p-6 dark:bg-gray-900 dark:border-gray-800">
          <h2 className="font-semibold mb-4 dark:text-gray-200">언어별</h2>
          <div className="space-y-3">
            {stats.byLanguage.map((l) => (
              <div key={l.language} className="flex justify-between items-center">
                <span className="text-sm dark:text-gray-300">{l.language === "ko" ? "한국어" : "영어"}</span>
                <span className="text-sm text-gray-500 dark:text-gray-400">{l.count}건</span>
              </div>
            ))}
          </div>
        </div>

        {/* By Source */}
        <div className="bg-white rounded-lg border p-6 dark:bg-gray-900 dark:border-gray-800">
          <h2 className="font-semibold mb-4 dark:text-gray-200">소스별 (Top 10)</h2>
          <div className="space-y-3">
            {stats.bySource.map((s) => (
              <div key={s.source}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="truncate dark:text-gray-300">{s.source}</span>
                  <span className="text-gray-500 whitespace-nowrap dark:text-gray-400">{s.count}건</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-2 dark:bg-gray-700">
                  <div
                    className="bg-green-500 h-2 rounded-full dark:bg-green-400"
                    style={{ width: `${(parseInt(s.count) / maxSrc) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Collection */}
        <div className="bg-white rounded-lg border p-6 dark:bg-gray-900 dark:border-gray-800">
          <h2 className="font-semibold mb-4 dark:text-gray-200">최근 7일 수집</h2>
          <div className="space-y-3">
            {stats.recent.reverse().map((r) => (
              <div key={r.date}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="dark:text-gray-300">{r.date}</span>
                  <span className="text-gray-500 dark:text-gray-400">{r.count}건</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-2 dark:bg-gray-700">
                  <div
                    className="bg-purple-500 h-2 rounded-full dark:bg-purple-400"
                    style={{ width: `${(parseInt(r.count) / maxRecent) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
