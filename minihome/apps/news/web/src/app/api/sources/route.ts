import { NextResponse } from "next/server";
import { newsGet } from "@/lib/news";

export const dynamic = "force-dynamic";

interface SourceRow {
  source: string;
  language: string;
  category: string;
  article_count: string;
  last_collected: string | null;
}

export async function GET() {
  const data = await newsGet<{ sources: SourceRow[] }>("/sources");
  return NextResponse.json({ sources: data?.sources ?? [] });
}
