/**
 * NewsBoardPanel — 地域レーン型ニュースボード（Market Desk / News タブ）
 * LLM は呼ばない。/api/news/board をポーリングして表示するだけ。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "../utils/api";
import {
  REGION_LABEL,
  REGION_ORDER,
  buildExplainPrompt,
  countUnreadHighImportance,
  itemKey,
  loadReadKeys,
  markRead,
  normalizeRegion,
  type NewsBoardItem,
  type NewsRegion,
} from "../utils/newsBoard";

const POLL_MS = 60_000;
const HIGH_IMPORTANCE = 75;

interface BoardItem extends NewsBoardItem {
  sentiment?: string | null;
  category?: string | null;
  stock_codes?: string[];
  tags?: string[];
  companion_url?: string | null;
  companion_source?: string | null;
  matched_targets?: string[];
  detected_catalysts?: string[];
  is_high_trust_source?: boolean;
}

interface BoardPayload {
  hours?: number;
  limit?: number;
  region?: string | null;
  pool_scanned?: number;
  region_counts?: Record<string, number>;
  items?: BoardItem[];
  verdict?: string;
  ok?: boolean;
  regions?: string[];
}

interface NewsBoardPanelProps {
  /** 記事をチャットで解説させるときの送信ハンドラ */
  onAsk?: (message: string) => void;
  autoRefresh?: boolean;
  /** 未読重要件数の変化を親（タブバッジ）へ通知 */
  onUnreadHighChange?: (count: number) => void;
}

function importanceTone(n: number | null | undefined): string {
  const v = n ?? 0;
  if (v >= HIGH_IMPORTANCE) return "text-amber-300";
  if (v >= 45) return "text-cyan-300";
  return "text-gray-500";
}

function shortTime(raw: string | null | undefined): string {
  if (!raw) return "—";
  const d = new Date(raw.includes("T") ? raw : raw.replace(" ", "T") + "Z");
  if (Number.isNaN(d.getTime())) return String(raw).slice(0, 16);
  return d.toLocaleString("ja-JP", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function NewsBoardPanel({
  onAsk,
  autoRefresh = true,
  onUnreadHighChange,
}: NewsBoardPanelProps) {
  const [payload, setPayload] = useState<BoardPayload | null>(null);
  const [filter, setFilter] = useState<NewsRegion | "ALL">("ALL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [readKeys, setReadKeys] = useState<Set<string>>(() => loadReadKeys());
  const busyRef = useRef(false);

  const load = useCallback(async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ hours: "18", limit: "80" });
      if (filter !== "ALL") qs.set("region", filter);
      const res = await apiFetch(`/api/news/board?${qs.toString()}`);
      if (!res.ok) throw new Error(`board ${res.status}`);
      const data = (await res.json()) as BoardPayload;
      setPayload(data);
      setUpdatedAt(new Date().toLocaleTimeString("ja-JP"));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "board failed");
    } finally {
      busyRef.current = false;
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [autoRefresh, load]);

  const counts = payload?.region_counts || {};
  const totalCount = REGION_ORDER.reduce((s, r) => s + (counts[r] || 0), 0);
  const items = Array.isArray(payload?.items) ? payload!.items! : [];
  const unreadHigh = countUnreadHighImportance(items, readKeys, HIGH_IMPORTANCE);

  useEffect(() => {
    onUnreadHighChange?.(unreadHigh);
  }, [unreadHigh, onUnreadHighChange]);

  const lanes = useMemo(() => {
    const by: Record<NewsRegion, BoardItem[]> = {
      US: [],
      JP: [],
      EU: [],
      CN_ASIA: [],
      GLOBAL: [],
    };
    for (const it of items) {
      const r = normalizeRegion(it.region);
      by[r].push(it);
    }
    const order =
      filter === "ALL" ? REGION_ORDER : REGION_ORDER.filter((r) => r === filter);
    return order.map((region) => ({
      region,
      items: by[region],
    }));
  }, [items, filter]);

  const verdict = payload?.verdict || "—";
  const verdictTone =
    verdict === "HEALTHY"
      ? "text-emerald-400"
      : verdict === "WARNING"
        ? "text-amber-400"
        : verdict === "DEGRADED" || verdict === "UNHEALTHY"
          ? "text-red-400"
          : "text-gray-400";

  const handleExplain = (it: BoardItem) => {
    setReadKeys((prev) => markRead(it, prev));
    onAsk?.(buildExplainPrompt(it));
  };

  const handleOpen = (it: BoardItem) => {
    setReadKeys((prev) => markRead(it, prev));
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-[11px] text-gray-400">
        <span className={verdictTone}>Feed {verdict}</span>
        <span>· scanned {payload?.pool_scanned ?? "—"}</span>
        <span>· shown {items.length}</span>
        {unreadHigh > 0 ? (
          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-semibold text-amber-300">
            未読重要 {unreadHigh}
          </span>
        ) : null}
        {updatedAt && <span className="text-cyan-500/80">· {updatedAt}</span>}
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="ml-auto rounded border border-white/10 px-2 py-0.5 text-gray-300 hover:bg-white/5 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setFilter("ALL")}
          className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
            filter === "ALL"
              ? "bg-cyan-500/20 text-cyan-200"
              : "bg-black/30 text-gray-400 hover:text-white"
          }`}
        >
          すべて {totalCount}
        </button>
        {REGION_ORDER.map((r) => {
          const n = counts[r] || 0;
          const share = totalCount > 0 ? Math.round((n / totalCount) * 100) : 0;
          return (
            <button
              key={r}
              type="button"
              onClick={() => setFilter(r)}
              className={`relative overflow-hidden rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                filter === r
                  ? "bg-cyan-500/20 text-cyan-200"
                  : "bg-black/30 text-gray-400 hover:text-white"
              }`}
              title={`${REGION_LABEL[r]}: ${n}件 (${share}%)`}
            >
              <span
                className="pointer-events-none absolute inset-y-0 left-0 bg-cyan-500/10"
                style={{ width: `${share}%` }}
              />
              <span className="relative">
                {REGION_LABEL[r]} {n}
              </span>
            </button>
          );
        })}
      </div>

      {error && (
        <div className="rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      {verdict === "DEGRADED" || verdict === "UNHEALTHY" ? (
        <div className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-200">
          フィード健全性が {verdict} です。カバレッジが欠けている可能性があります。
        </div>
      ) : null}

      <div
        className={`grid gap-3 ${
          filter === "ALL"
            ? "grid-cols-1 lg:grid-cols-2 xl:grid-cols-3"
            : "grid-cols-1"
        }`}
      >
        {lanes.map(({ region, items: laneItems }) => (
          <section
            key={region}
            className="flex min-h-[180px] flex-col rounded-lg border border-white/10 bg-black/25"
          >
            <header className="flex items-center justify-between border-b border-white/10 px-3 py-2">
              <h3 className="text-xs font-bold tracking-wide text-cyan-100">
                {REGION_LABEL[region]}
              </h3>
              <span className="text-[10px] text-gray-500">{laneItems.length}</span>
            </header>
            <ul className="flex-1 space-y-1 overflow-y-auto p-2" style={{ maxHeight: 420 }}>
              {laneItems.length === 0 && (
                <li className="px-2 py-4 text-[11px] text-gray-600">この地域の記事はまだありません</li>
              )}
              {laneItems.map((it, idx) => {
                const key = itemKey(it) || `${region}-${idx}`;
                const imp = it.importance ?? 0;
                const unread = imp >= HIGH_IMPORTANCE && !readKeys.has(itemKey(it));
                return (
                  <li
                    key={key}
                    className={`rounded-md border px-2 py-1.5 hover:border-white/10 hover:bg-white/[0.03] ${
                      unread
                        ? "border-amber-500/25 bg-amber-500/[0.04]"
                        : "border-transparent"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span
                        className={`mt-0.5 shrink-0 text-[10px] font-mono tabular-nums ${importanceTone(imp)}`}
                        title="importance"
                      >
                        {imp}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start gap-1.5">
                          {unread ? (
                            <span
                              className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400"
                              title="未読・重要"
                            />
                          ) : null}
                          {it.url ? (
                            <a
                              href={it.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={() => handleOpen(it)}
                              className="block text-[12px] font-medium leading-snug text-gray-100 hover:text-cyan-200"
                            >
                              {it.title || "(no title)"}
                            </a>
                          ) : (
                            <span className="block text-[12px] font-medium text-gray-100">
                              {it.title || "(no title)"}
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-gray-500">
                          <span>{it.source || "—"}</span>
                          <span>{shortTime(it.published || it.fetched_at)}</span>
                          {it.is_high_trust_source ? (
                            <span className="text-emerald-500/80">trust</span>
                          ) : null}
                          {(it.matched_targets || []).slice(0, 2).map((t) => (
                            <span key={t} className="text-cyan-600/80">
                              {t}
                            </span>
                          ))}
                        </div>
                        {it.summary ? (
                          <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed text-gray-500">
                            {it.summary}
                          </p>
                        ) : null}
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {onAsk ? (
                            <button
                              type="button"
                              onClick={() => handleExplain(it)}
                              className="rounded border border-cyan-500/25 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-medium text-cyan-200 hover:bg-cyan-500/20"
                            >
                              解説して
                            </button>
                          ) : null}
                          {it.companion_url ? (
                            <a
                              href={it.companion_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="rounded border border-white/10 px-2 py-0.5 text-[10px] text-gray-400 hover:text-gray-200"
                              title={it.companion_source || "free companion"}
                            >
                              無料ソース
                            </a>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
