import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="text-3xl font-bold mb-8">mini home</h1>
      <p className="text-gray-600 mb-8">모노레포 Umbrella — 독립 프로젝트들의 집합</p>
      <ul className="space-y-4">
        <li>
          <a href="https://miniebook.vercel.app" className="text-blue-600 hover:underline text-xl font-semibold">
            miniebook (ebook)
          </a>
          <p className="text-gray-500 text-sm">웹소설 리더 — Next.js + FastAPI</p>
        </li>
        <li>
          <a href="https://mini-news.vercel.app" className="text-blue-600 hover:underline text-xl font-semibold">
            news
          </a>
          <p className="text-gray-500 text-sm">AI 뉴스 수집/번역 — Python + Next.js</p>
        </li>
        <li>
          <a href="https://mini-cashbook.vercel.app" className="text-blue-600 hover:underline text-xl font-semibold">
            cashbook
          </a>
          <p className="text-gray-500 text-sm">가계부 — FastAPI + HTMX</p>
        </li>
        <li>
          <a href="https://mini-timetable.vercel.app" className="text-blue-600 hover:underline text-xl font-semibold">
            timetable
          </a>
          <p className="text-gray-500 text-sm">시간표 구독 — FastAPI + Google Calendar</p>
        </li>
        <li>
          <a href="https://kuhwa.vercel.app" className="text-blue-600 hover:underline text-xl font-semibold">
            kuhwa
          </a>
          <p className="text-gray-500 text-sm">한국구화학교 학사일정 — Next.js 정적</p>
        </li>
      </ul>
    </main>
  );
}
