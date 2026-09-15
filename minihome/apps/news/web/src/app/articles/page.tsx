import { unstable_noStore as noStore } from "next/cache";
import { newsGet } from "@/lib/news";
import ArticlesClient, { Article } from "./ArticlesClient";

export const dynamic = "force-dynamic";

export default async function ArticlesPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  noStore();
  const { page } = await searchParams;
  const currentPage = Math.max(1, parseInt(page || "1", 10));

  // 수집일(KST) 목록 — devforge News Read API
  const datesResult = await newsGet<{ date: string }[]>("/dates");
  const dates: string[] = (datesResult ?? []).map((r) => r.date);
  const totalPages = dates.length;

  if (totalPages === 0) {
    return (
      <ArticlesClient
        initialArticles={[]}
        currentPage={1}
        totalPages={0}
        total={0}
        currentDate=""
      />
    );
  }

  const safePage = Math.min(currentPage, totalPages);
  const targetDate = dates[safePage - 1];

  // 해당 날짜 기사 목록
  const articles =
    (await newsGet<Article[]>(`/articles?date=${targetDate}`)) ?? [];

  return (
    <ArticlesClient
      initialArticles={articles}
      currentPage={safePage}
      totalPages={totalPages}
      total={articles.length}
      currentDate={targetDate}
    />
  );
}
