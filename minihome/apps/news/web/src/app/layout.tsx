import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mini News",
  description: "AI/Tech News Aggregator",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="bg-gray-50 text-gray-900 min-h-screen dark:bg-gray-950 dark:text-gray-100">
        <nav className="bg-white border-b border-gray-200 sticky top-0 z-50 dark:bg-gray-900 dark:border-gray-800">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-14 items-center">
              <div className="flex items-center gap-8">
                <Link href="/" className="font-bold text-lg dark:text-white">
                  Mini News
                </Link>
                <div className="hidden sm:flex gap-6 text-sm">
                  <Link href="/articles" className="hover:text-blue-600 dark:text-gray-300 dark:hover:text-blue-400">
                    뉴스
                  </Link>
                  <Link href="/dashboard" className="hover:text-blue-600 dark:text-gray-300 dark:hover:text-blue-400">
                    대시보드
                  </Link>
                  <Link href="/sources" className="hover:text-blue-600 dark:text-gray-300 dark:hover:text-blue-400">
                    소스
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
      </body>
    </html>
  );
}
