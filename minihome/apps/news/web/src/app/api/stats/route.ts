import { NextResponse } from "next/server";
import { newsGet } from "@/lib/news";

export const dynamic = "force-dynamic";

export async function GET() {
  const stats = await newsGet<{
    total: number;
    byCategory: { category: string; count: string }[];
    byLanguage: { language: string; count: string }[];
    bySource: { source: string; count: string }[];
    recent: { date: string; count: string }[];
  }>("/stats");

  return NextResponse.json(
    stats ?? {
      total: 0,
      byCategory: [],
      byLanguage: [],
      bySource: [],
      recent: [],
    }
  );
}
