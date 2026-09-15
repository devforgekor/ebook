// Neon DB 제거 후 데이터 소스 = devforge News Read API (표시 전용 fetch)
// devforge(처리·DB)가 이 API로 JSON을 제공하고, Vercel은 화면 표시만 담당.
const BASE =
  process.env.NEWS_API_BASE ??
  "https://devforge.152-69-229-246.nip.io/news";

export async function newsGet<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
