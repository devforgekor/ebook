"use client";

import { useState, useEffect } from "react";

interface Source {
  source: string;
  language: string;
  category: string;
  article_count: string;
  last_collected: string;
}

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/sources")
      .then((r) => r.json())
      .then((d) => setSources(d.sources))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-center py-12 text-gray-500 dark:text-gray-400">로딩 중...</div>;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 dark:text-gray-100">RSS 소스</h1>

      <div className="bg-white rounded-lg border overflow-hidden dark:bg-gray-900 dark:border-gray-800">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b dark:bg-gray-800 dark:border-gray-700">
            <tr>
              <th className="text-left px-4 py-3 font-medium dark:text-gray-200">소스</th>
              <th className="text-left px-4 py-3 font-medium dark:text-gray-200">언어</th>
              <th className="text-left px-4 py-3 font-medium dark:text-gray-200">카테고리</th>
              <th className="text-right px-4 py-3 font-medium dark:text-gray-200">기사 수</th>
              <th className="text-right px-4 py-3 font-medium dark:text-gray-200">마지막 수집</th>
            </tr>
          </thead>
          <tbody className="divide-y dark:divide-gray-700">
            {sources.map((s) => (
              <tr key={`${s.source}-${s.category}`} className="hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className="px-4 py-3 font-medium dark:text-gray-200">{s.source === "OpenRouter (RR Proxy)" ? "Open(RR)" : s.source}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded text-xs bg-gray-100 dark:bg-gray-700 dark:text-gray-300">
                    {s.language}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                    {s.category}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-gray-500 dark:text-gray-400">
                  {parseInt(s.article_count).toLocaleString()}건
                </td>
                <td className="px-4 py-3 text-right text-gray-400 text-xs dark:text-gray-500">
                  {s.last_collected
                    ? new Date(s.last_collected).toLocaleString("ko-KR")
                    : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
