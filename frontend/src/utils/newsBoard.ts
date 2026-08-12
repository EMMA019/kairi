/**
 * News Board 用の純粋ヘルパ（UI から分離してテスト容易にする）
 */

export type NewsRegion = "US" | "JP" | "EU" | "CN_ASIA" | "GLOBAL";

export const REGION_ORDER: NewsRegion[] = ["US", "JP", "EU", "CN_ASIA", "GLOBAL"];

export const REGION_LABEL: Record<NewsRegion, string> = {
  US: "US",
  JP: "日本",
  EU: "欧州",
  CN_ASIA: "中韓・アジア",
  GLOBAL: "通信社・他",
};

export interface NewsBoardItem {
  id?: number | null;
  title?: string | null;
  url?: string | null;
  source?: string | null;
  summary?: string | null;
  published?: string | null;
  fetched_at?: string | null;
  region?: string | null;
  importance?: number | null;
}

const READ_KEY = "kairi_news_read_v1";

export function buildExplainPrompt(item: NewsBoardItem): string {
  const title = (item.title || "").trim();
  const url = (item.url || "").trim();
  const source = (item.source || "").trim();
  const summary = (item.summary || "").trim().slice(0, 400);
  const lines = [
    "次のニュースを、投資家向けに簡潔に解説してください。",
    "事実と推測を分け、ソースの信頼度にも触れてください。",
    "",
    `見出し: ${title}`,
  ];
  if (source) lines.push(`ソース: ${source}`);
  if (url) lines.push(`URL: ${url}`);
  if (summary) lines.push(`要約スニペット: ${summary}`);
  return lines.join("\n");
}

export function itemKey(item: NewsBoardItem): string {
  return (item.url || "").trim() || `id:${item.id ?? ""}:${item.title || ""}`;
}

export function loadReadKeys(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.filter((x): x is string => typeof x === "string"));
  } catch {
    return new Set();
  }
}

export function saveReadKeys(keys: Set<string>): void {
  const arr = Array.from(keys).slice(-500);
  localStorage.setItem(READ_KEY, JSON.stringify(arr));
}

export function markRead(item: NewsBoardItem, current: Set<string>): Set<string> {
  const next = new Set(current);
  next.add(itemKey(item));
  saveReadKeys(next);
  return next;
}

export function countUnreadHighImportance(
  items: NewsBoardItem[],
  readKeys: Set<string>,
  threshold = 75,
): number {
  let n = 0;
  for (const it of items) {
    if ((it.importance ?? 0) < threshold) continue;
    if (readKeys.has(itemKey(it))) continue;
    n += 1;
  }
  return n;
}

export function normalizeRegion(value: string | null | undefined): NewsRegion {
  const key = String(value || "GLOBAL").toUpperCase().replace(/-/g, "_");
  if ((REGION_ORDER as string[]).includes(key)) return key as NewsRegion;
  return "GLOBAL";
}
