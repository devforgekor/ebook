import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "mini home",
  description: "Monorepo Umbrella — 독립 프로젝트들의 집합",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
