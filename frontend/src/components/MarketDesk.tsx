/**
 * MarketDesk — 市況閲覧デスク（発注なし）。後続で Signals / Orders タブを足せる構造。
 */
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { executeMarketTool } from "../hooks/useMarketTool";
import {
  addPaperJournalEntry,
  loadPaperJournal,
  removePaperJournalEntry,
  type PaperJournalEntry,
  type PaperSide,
} from "../utils/paperJournal";
import type { ScalpSettings } from "../utils/scalpSizing";
import {
  INDEX_BAR,
  SECTOR_BAR,
  WATCHLIST_MAX,
  addWatchSymbol,
  buildWatchRow,
  loadScalpSettings,
  loadWatchlist,
  removeWatchSymbol,
  saveScalpSettings,
  saveWatchlist,
  type QuotePayload,
  type WatchRow,
} from "../utils/watchlist";

type DeskTab = "overview" | "radar" | "signals";

type BarQuote = {
  symbol: string;
  label: string;
  price: number | null;
  changePct: number | null;
  source: string | null;
  error?: string;
};

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function asQuote(v: unknown): QuotePayload | null {
  const rec = asRecord(v);
  return rec ? (rec as QuotePayload) : null;
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300 whitespace-pre-wrap">
      {message}
    </div>
  );
}

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-white/10 bg-[#0d1117]/80 p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-wide text-cyan-100">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function KvTable({ rows }: { rows: Array<[string, string]> }) {
  if (!rows.length) {
    return <p className="text-xs text-gray-500">データなし</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-b border-white/5">
              <th className="py-1.5 pr-3 font-medium text-gray-400 whitespace-nowrap">{k}</th>
              <td className="py-1.5 text-gray-100 font-mono">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(v);
}

function formatPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function pctColor(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "text-gray-400";
  if (v > 0) return "text-emerald-300";
  if (v < 0) return "text-rose-300";
  return "text-gray-400";
}

function volumeWarn(ratio: number | null | undefined): boolean {
  if (ratio == null || !Number.isFinite(ratio)) return false;
  return ratio < 0.5 || ratio >= 1.8;
}

export function MarketDesk() {
  const [tab, setTab] = useState<DeskTab>("overview");
  const [loading, setLoading] = useState<string | null>(null);
  const [ibkrSummary, setIbkrSummary] = useState<unknown>(null);
  const [ibkrPositions, setIbkrPositions] = useState<unknown>(null);
  const [ibkrFills, setIbkrFills] = useState<unknown>(null);
  const [ibkrError, setIbkrError] = useState<string | null>(null);
  const [jpSnap, setJpSnap] = useState<unknown>(null);
  const [jpError, setJpError] = useState<string | null>(null);
  const [radarType, setRadarType] = useState<"rejected" | "alert">("alert");
  const [radarText, setRadarText] = useState<string>("");
  const [radarError, setRadarError] = useState<string | null>(null);
  const [leadLag, setLeadLag] = useState<string>("");
  const [leadLagParsed, setLeadLagParsed] = useState<Record<string, unknown> | null>(null);
  const [leadLagError, setLeadLagError] = useState<string | null>(null);
  const [journal, setJournal] = useState<PaperJournalEntry[]>([]);
  const [paperSymbol, setPaperSymbol] = useState("");
  const [paperSide, setPaperSide] = useState<PaperSide>("long");
  const [paperNote, setPaperNote] = useState("");

  const [indexQuotes, setIndexQuotes] = useState<BarQuote[]>([]);
  const [sectorQuotes, setSectorQuotes] = useState<BarQuote[]>([]);
  const [watchSymbols, setWatchSymbols] = useState<string[]>(() => loadWatchlist());
  const [watchRows, setWatchRows] = useState<Record<string, WatchRow>>({});
  const [addTicker, setAddTicker] = useState("");
  const [watchError, setWatchError] = useState<string | null>(null);
  const [scalp, setScalp] = useState<ScalpSettings>(() => loadScalpSettings());

  useEffect(() => {
    setJournal(loadPaperJournal());
  }, []);

  useEffect(() => {
    saveScalpSettings(scalp);
  }, [scalp]);

  useEffect(() => {
    setWatchRows((prev) => {
      const next: Record<string, WatchRow> = {};
      for (const sym of watchSymbols) {
        const old = prev[sym];
        next[sym] = buildWatchRow(sym, old?.quote ?? null, scalp, old?.error);
      }
      return next;
    });
  }, [scalp, watchSymbols]);

  const run = useCallback(async (key: string, fn: () => Promise<void>) => {
    setLoading(key);
    try {
      await fn();
    } finally {
      setLoading(null);
    }
  }, []);

  const fetchOneQuote = async (ticker: string): Promise<{ quote: QuotePayload | null; error?: string }> => {
    const r = await executeMarketTool("get_stock_quote", { ticker });
    if (r.error) return { quote: null, error: r.error };
    const q = asQuote(r.parsed);
    if (!q) return { quote: null, error: "parse failed" };
    if (q.error) return { quote: q, error: String(q.error) };
    return { quote: q };
  };

  const refreshUsdJpy = async (settings: ScalpSettings): Promise<ScalpSettings> => {
    if (settings.usdjpyManual) return settings;
    const { quote } = await fetchOneQuote("USDJPY=X");
    const px = quote?.current_price;
    if (px != null && Number.isFinite(px) && px > 0) {
      const next = { ...settings, usdjpy: px };
      setScalp(next);
      return next;
    }
    return settings;
  };

  const refreshWatchlist = () =>
    run("watch", async () => {
      setWatchError(null);
      const settings = await refreshUsdJpy(scalp);
      const symbols = watchSymbols.slice(0, WATCHLIST_MAX);
      const results = await Promise.all(
        symbols.map(async (symbol) => {
          const { quote, error } = await fetchOneQuote(symbol);
          return buildWatchRow(symbol, quote, settings, error);
        }),
      );
      const map: Record<string, WatchRow> = {};
      for (const row of results) map[row.symbol] = row;
      setWatchRows(map);
      const fails = results.filter((r) => r.error);
      if (fails.length) {
        setWatchError(`${fails.length} 銘柄で取得エラー（詳細は各行）`);
      }
    });

  const refreshAllOverviewQuotes = () =>
    run("overview_quotes", async () => {
      setWatchError(null);
      const settings = await refreshUsdJpy(scalp);
      const barItems = [...INDEX_BAR, ...SECTOR_BAR];
      const barResults = await Promise.all(
        barItems.map(async ({ symbol, label }) => {
          const { quote, error } = await fetchOneQuote(symbol);
          return {
            symbol,
            label,
            price: quote?.current_price ?? null,
            changePct: quote?.change_pct ?? null,
            source: quote?.source ?? null,
            error,
          };
        }),
      );
      setIndexQuotes(barResults.slice(0, INDEX_BAR.length));
      setSectorQuotes(barResults.slice(INDEX_BAR.length));

      const results = await Promise.all(
        watchSymbols.slice(0, WATCHLIST_MAX).map(async (symbol) => {
          const { quote, error } = await fetchOneQuote(symbol);
          return buildWatchRow(symbol, quote, settings, error);
        }),
      );
      const map: Record<string, WatchRow> = {};
      for (const row of results) map[row.symbol] = row;
      setWatchRows(map);
    });

  const refreshIbkr = () =>
    run("ibkr", async () => {
      setIbkrError(null);
      const [s, p, f] = await Promise.all([
        executeMarketTool("ibkr_account_summary"),
        executeMarketTool("ibkr_positions"),
        executeMarketTool("ibkr_recent_fills", { limit: 20 }),
      ]);
      const fail =
        s.error ||
        p.error ||
        f.error ||
        (asRecord(s.parsed)?.ok === false
          ? String(asRecord(s.parsed)?.message || asRecord(s.parsed)?.error)
          : null);
      if (fail) setIbkrError(fail);
      setIbkrSummary(s.parsed ?? s.raw);
      setIbkrPositions(p.parsed ?? p.raw);
      setIbkrFills(f.parsed ?? f.raw);
    });

  const refreshJapan = () =>
    run("japan", async () => {
      setJpError(null);
      const r = await executeMarketTool("get_jp_market_snapshot");
      if (r.error) setJpError(r.error);
      setJpSnap(r.parsed ?? r.raw);
    });

  const fetchRadar = () =>
    run("radar", async () => {
      setRadarError(null);
      const r = await executeMarketTool("check_radar_logs", { log_type: radarType, limit: 15 });
      if (r.error) setRadarError(r.error);
      setRadarText(r.raw);
    });

  const fetchLeadLag = () =>
    run("leadlag", async () => {
      setLeadLagError(null);
      setLeadLagParsed(null);
      const r = await executeMarketTool("analyze_sector_lead_lag");
      if (r.error) setLeadLagError(r.error);
      if (/sklearn|No module named/i.test(r.raw)) {
        setLeadLagError("scikit-learn 未導入のため実行できません（pip install scikit-learn）");
      }
      const rec = asRecord(r.parsed);
      if (rec?.error) setLeadLagError(String(rec.error));
      else if (rec) setLeadLagParsed(rec);
      setLeadLag(r.raw);
    });

  const addJournal = (symbol: string, side: PaperSide, note: string, source?: string) => {
    const sym = symbol.trim();
    if (!sym) return;
    setJournal(
      addPaperJournalEntry({
        symbol: sym.toUpperCase(),
        side,
        note: note.trim() || (side === "long" ? "Paper LONG" : "Paper SHORT"),
        source,
      }),
    );
  };

  const onAddWatch = () => {
    const next = addWatchSymbol(watchSymbols, addTicker);
    setWatchSymbols(next);
    saveWatchlist(next);
    setAddTicker("");
  };

  const onRemoveWatch = (symbol: string) => {
    const next = removeWatchSymbol(watchSymbols, symbol);
    setWatchSymbols(next);
  };

  const summaryRec = asRecord(ibkrSummary);
  const summaryData = asRecord(summaryRec?.data);
  const tags = asRecord(summaryData?.tags) || {};
  const posData = asRecord(asRecord(ibkrPositions)?.data);
  const positions = Array.isArray(posData?.positions) ? (posData!.positions as any[]) : [];
  const fillData = asRecord(asRecord(ibkrFills)?.data);
  const fills = Array.isArray(fillData?.fills) ? (fillData!.fills as any[]) : [];
  const jpRec = asRecord(jpSnap);
  const jpIndices = asRecord(jpRec?.indices) || {};
  const jpSectors = asRecord(jpRec?.sectors) || {};

  const tabs: Array<{ id: DeskTab; label: string }> = [
    { id: "overview", label: "Overview" },
    { id: "radar", label: "Radar" },
    { id: "signals", label: "Signals" },
  ];

  const quotesBusy =
    loading === "watch" || loading === "indexbar" || loading === "overview_quotes";

  return (
    <div className="flex h-full flex-col bg-[#0b0f19] text-gray-100">
      <header className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <h2 className="text-base font-bold tracking-tight text-white">Market Desk</h2>
          <p className="text-[11px] text-gray-500">Read-only + paper journal · 実発注なし</p>
        </div>
        <div className="flex gap-1 rounded-lg bg-black/30 p-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
                tab === t.id ? "bg-cyan-500/20 text-cyan-200" : "text-gray-400 hover:text-white"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {tab === "overview" && (
          <>
            <Section
              title="US Index / Sector"
              action={
                <button
                  type="button"
                  onClick={refreshAllOverviewQuotes}
                  disabled={quotesBusy}
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  {quotesBusy ? "Loading…" : "Refresh all"}
                </button>
              }
            >
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {(indexQuotes.length
                  ? indexQuotes
                  : INDEX_BAR.map((x) => ({ ...x, price: null, changePct: null, source: null }))
                ).map((q) => (
                  <div key={q.symbol} className="rounded-lg border border-white/5 bg-black/25 px-3 py-2">
                    <div className="flex items-baseline justify-between gap-1">
                      <span className="text-[10px] text-gray-500">{q.label}</span>
                      <span className="font-mono text-[10px] text-gray-600">{q.symbol}</span>
                    </div>
                    <div className="mt-1 font-mono text-sm text-gray-100">{formatVal(q.price)}</div>
                    <div className={`font-mono text-[11px] ${pctColor(q.changePct)}`}>
                      {formatPct(q.changePct)}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {(sectorQuotes.length
                  ? sectorQuotes
                  : SECTOR_BAR.map((x) => ({ ...x, price: null, changePct: null, source: null }))
                ).map((q) => (
                  <div key={q.symbol} className="rounded-lg border border-white/5 bg-black/15 px-3 py-2">
                    <div className="flex items-baseline justify-between gap-1">
                      <span className="text-[10px] text-gray-500">{q.label}</span>
                      <span className="font-mono text-[10px] text-gray-600">{q.symbol}</span>
                    </div>
                    <div className="mt-1 font-mono text-sm text-gray-100">{formatVal(q.price)}</div>
                    <div className={`font-mono text-[11px] ${pctColor(q.changePct)}`}>
                      {formatPct(q.changePct)}
                    </div>
                  </div>
                ))}
              </div>
              {!indexQuotes.length && (
                <p className="mt-2 text-[11px] text-gray-500">
                  Refresh all で DIA/SPY/QQQ/SOXX + セクターETF
                </p>
              )}
            </Section>

            <Section title="Paper scalp settings">
              <p className="mb-3 text-[11px] text-gray-500">
                リスク円 = ターゲット幅逆行時の許容損失（買付代金ではない）。ウォッチリストは監視専用で資金按分しない。
                薄商い時は $1 取りきれない想定。
              </p>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                <label className="text-[11px] text-gray-400">
                  元手（買付上限 JPY）
                  <input
                    type="number"
                    value={scalp.capitalJpy}
                    onChange={(e) => setScalp((s) => ({ ...s, capitalJpy: Number(e.target.value) || 0 }))}
                    className="mt-1 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 font-mono text-sm text-white outline-none focus:border-cyan-500/50"
                  />
                </label>
                <label className="text-[11px] text-gray-400">
                  リスク円（$逆行許容）
                  <input
                    type="number"
                    value={scalp.riskJpy}
                    onChange={(e) => setScalp((s) => ({ ...s, riskJpy: Number(e.target.value) || 0 }))}
                    className="mt-1 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 font-mono text-sm text-white outline-none focus:border-cyan-500/50"
                  />
                </label>
                <label className="text-[11px] text-gray-400">
                  ターゲット幅 ($)
                  <input
                    type="number"
                    step="0.1"
                    value={scalp.targetUsd}
                    onChange={(e) => setScalp((s) => ({ ...s, targetUsd: Number(e.target.value) || 1 }))}
                    className="mt-1 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 font-mono text-sm text-white outline-none focus:border-cyan-500/50"
                  />
                </label>
                <label className="text-[11px] text-gray-400">
                  USD/JPY
                  <input
                    type="number"
                    step="0.01"
                    value={scalp.usdjpy}
                    onChange={(e) =>
                      setScalp((s) => ({
                        ...s,
                        usdjpy: Number(e.target.value) || s.usdjpy,
                        usdjpyManual: true,
                      }))
                    }
                    className="mt-1 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 font-mono text-sm text-white outline-none focus:border-cyan-500/50"
                  />
                </label>
                <label className="flex items-end gap-2 pb-2 text-[11px] text-gray-300">
                  <input
                    type="checkbox"
                    checked={scalp.usdjpyManual}
                    onChange={(e) => setScalp((s) => ({ ...s, usdjpyManual: e.target.checked }))}
                  />
                  USD/JPY 手動固定（Refresh で上書きしない）
                </label>
                <div className="flex items-end">
                  <button
                    type="button"
                    onClick={() =>
                      run("fx", async () => {
                        await refreshUsdJpy({ ...scalp, usdjpyManual: false });
                      })
                    }
                    disabled={loading === "fx"}
                    className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                  >
                    {loading === "fx" ? "Loading…" : "Fetch USDJPY"}
                  </button>
                </div>
              </div>
            </Section>

            <Section
              title="Watchlist"
              action={
                <button
                  type="button"
                  onClick={refreshWatchlist}
                  disabled={quotesBusy || !watchSymbols.length}
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  {loading === "watch" ? "Loading…" : "Refresh list"}
                </button>
              }
            >
              <div className="mb-3 flex flex-wrap gap-2">
                <input
                  value={addTicker}
                  onChange={(e) => setAddTicker(e.target.value.toUpperCase())}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onAddWatch();
                  }}
                  className="rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 font-mono text-sm text-white outline-none focus:border-cyan-500/50"
                  placeholder="TICKER"
                />
                <button
                  type="button"
                  onClick={onAddWatch}
                  disabled={!addTicker.trim() || watchSymbols.length >= WATCHLIST_MAX}
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  Add
                </button>
                <span className="self-center text-[10px] text-gray-600">
                  {watchSymbols.length}/{WATCHLIST_MAX}
                </span>
              </div>
              {watchError && (
                <div className="mb-2">
                  <ErrorBanner message={watchError} />
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full min-w-[52rem] text-left text-[11px]">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="pb-2 pr-2">Symbol</th>
                      <th className="pb-2 pr-2">Price</th>
                      <th className="pb-2 pr-2">Chg%</th>
                      <th className="pb-2 pr-2">Vol ratio</th>
                      <th className="pb-2 pr-2">ATR</th>
                      <th className="pb-2 pr-2">$1/ATR</th>
                      <th className="pb-2 pr-2">買える</th>
                      <th className="pb-2 pr-2">リスク株</th>
                      <th className="pb-2 pr-2">推奨</th>
                      <th className="pb-2 pr-2">±$1 JPY</th>
                      <th className="pb-2 pr-2">Src</th>
                      <th className="pb-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {watchSymbols.map((sym) => {
                      const row = watchRows[sym];
                      const q = row?.quote;
                      const m = row?.metrics;
                      const sz = row?.sizing;
                      const warn = volumeWarn(m?.volumeRatio);
                      return (
                        <tr
                          key={sym}
                          className={`border-t border-white/5 ${warn ? "bg-amber-500/5" : ""}`}
                        >
                          <td className="py-1.5 pr-2 font-mono font-semibold text-gray-100">{sym}</td>
                          <td className="py-1.5 pr-2 font-mono">{formatVal(q?.current_price)}</td>
                          <td className={`py-1.5 pr-2 font-mono ${pctColor(q?.change_pct ?? null)}`}>
                            {formatPct(q?.change_pct)}
                          </td>
                          <td
                            className={`py-1.5 pr-2 font-mono ${warn ? "text-amber-300" : "text-gray-200"}`}
                            title="直近出来高 / 平均。急増・急減の目安"
                          >
                            {m?.volumeRatio != null ? m.volumeRatio.toFixed(2) : "—"}
                          </td>
                          <td className="py-1.5 pr-2 font-mono">{formatVal(m?.atr)}</td>
                          <td
                            className="py-1.5 pr-2 font-mono text-cyan-200/90"
                            title="大きいほどターゲット幅がATRに対して近い"
                          >
                            {m?.dollarEase != null ? m.dollarEase.toFixed(2) : "—"}
                          </td>
                          <td className="py-1.5 pr-2 font-mono" title="元手で買える株数">
                            {sz ? sz.capitalShares : "—"}
                          </td>
                          <td className="py-1.5 pr-2 font-mono" title="リスク円から逆算">
                            {sz ? sz.riskShares : "—"}
                          </td>
                          <td className="py-1.5 pr-2 font-mono text-emerald-200">
                            {sz ? sz.recommended : "—"}
                          </td>
                          <td className="py-1.5 pr-2 font-mono">
                            {sz ? formatVal(Math.round(sz.pnlPerTargetJpy)) : "—"}
                          </td>
                          <td className="py-1.5 pr-2 font-mono text-gray-500">
                            {q?.source || (row?.error ? "err" : "—")}
                          </td>
                          <td className="py-1.5">
                            <div className="flex gap-1">
                              <button
                                type="button"
                                className="rounded border border-emerald-500/30 px-1.5 py-0.5 text-[10px] text-emerald-200 hover:bg-emerald-500/10"
                                onClick={() => addJournal(sym, "long", "Watchlist paper", "watchlist")}
                              >
                                Paper
                              </button>
                              <button
                                type="button"
                                className="text-gray-500 hover:text-red-300"
                                onClick={() => onRemoveWatch(sym)}
                                title="Remove"
                              >
                                ×
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {!watchSymbols.length && <p className="text-xs text-gray-500">銘柄を追加してください</p>}
            </Section>

            <Section
              title="IBKR Account"
              action={
                <button
                  type="button"
                  onClick={refreshIbkr}
                  disabled={loading === "ibkr"}
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  {loading === "ibkr" ? "Loading…" : "Refresh"}
                </button>
              }
            >
              {ibkrError && (
                <div className="mb-2">
                  <ErrorBanner message={ibkrError} />
                </div>
              )}
              {summaryRec?.ok === false && (
                <div className="mb-2">
                  <ErrorBanner
                    message={`${String(summaryRec.error || "error")}: ${String(summaryRec.message || "")}`}
                  />
                </div>
              )}
              {summaryRec?.ok === true && (
                <>
                  <p className="mb-2 text-xs text-gray-400">
                    Account:{" "}
                    <span className="font-mono text-gray-200">{String(summaryData?.account || "—")}</span>
                  </p>
                  <KvTable
                    rows={[
                      ["NetLiquidation", formatVal(tags.NetLiquidation)],
                      ["TotalCashValue", formatVal(tags.TotalCashValue)],
                      ["BuyingPower", formatVal(tags.BuyingPower)],
                      ["GrossPositionValue", formatVal(tags.GrossPositionValue)],
                      ["AvailableFunds", formatVal(tags.AvailableFunds)],
                      ["UnrealizedPnL", formatVal(tags.UnrealizedPnL)],
                      ["RealizedPnL", formatVal(tags.RealizedPnL)],
                      ["Currency", formatVal(tags.Currency)],
                    ]}
                  />
                </>
              )}
              {!ibkrSummary && !ibkrError && (
                <p className="text-xs text-gray-500">Refresh で TWS 経由の残高を取得</p>
              )}
              {positions.length > 0 && (
                <div className="mt-4">
                  <h4 className="mb-2 text-xs font-semibold text-gray-300">Positions</h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="text-gray-500">
                        <tr>
                          <th className="pb-1 pr-2">Symbol</th>
                          <th className="pb-1 pr-2">Qty</th>
                          <th className="pb-1">AvgCost</th>
                        </tr>
                      </thead>
                      <tbody>
                        {positions.map((row, i) => (
                          <tr key={i} className="border-t border-white/5">
                            <td className="py-1 pr-2 font-mono">{row.symbol || row.localSymbol}</td>
                            <td className="py-1 pr-2 font-mono">{formatVal(row.position)}</td>
                            <td className="py-1 font-mono">{formatVal(row.avgCost)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              {fills.length > 0 && (
                <div className="mt-4">
                  <h4 className="mb-2 text-xs font-semibold text-gray-300">Recent fills</h4>
                  <div className="max-h-40 space-y-1 overflow-y-auto font-mono text-[11px] text-gray-300">
                    {fills.map((row, i) => (
                      <div key={i}>
                        {row.time} {row.side} {row.symbol} ×{formatVal(row.shares)} @ {formatVal(row.price)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Section>

            <Section
              title="Japan Market"
              action={
                <button
                  type="button"
                  onClick={refreshJapan}
                  disabled={loading === "japan"}
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  {loading === "japan" ? "Loading…" : "Refresh"}
                </button>
              }
            >
              {jpError && (
                <div className="mb-2">
                  <ErrorBanner message={jpError} />
                </div>
              )}
              {Object.keys(jpIndices).length > 0 ? (
                <KvTable
                  rows={Object.entries(jpIndices).map(([t, q]) => {
                    const rec = asRecord(q);
                    return [
                      String(rec?.label || t),
                      `${formatVal(rec?.current_price)} (${formatVal(rec?.change_pct)}%)`,
                    ];
                  })}
                />
              ) : (
                !jpError && <p className="text-xs text-gray-500">Refresh で日経/TOPIX/業種ETF</p>
              )}
              {Object.keys(jpSectors).length > 0 && (
                <div className="mt-3">
                  <h4 className="mb-2 text-xs font-semibold text-gray-300">Sector ETFs</h4>
                  <KvTable
                    rows={Object.entries(jpSectors).map(([t, q]) => {
                      const rec = asRecord(q);
                      return [
                        String(rec?.label || t),
                        `${formatVal(rec?.current_price)} (${formatVal(rec?.change_pct)}%)`,
                      ];
                    })}
                  />
                </div>
              )}
            </Section>
          </>
        )}

        {tab === "radar" && (
          <Section
            title="News Radar Logs"
            action={
              <div className="flex items-center gap-2">
                <select
                  value={radarType}
                  onChange={(e) => setRadarType(e.target.value as "rejected" | "alert")}
                  className="rounded-md border border-white/10 bg-black/40 px-2 py-1 text-xs text-gray-200"
                >
                  <option value="alert">alert</option>
                  <option value="rejected">rejected</option>
                </select>
                <button
                  type="button"
                  onClick={fetchRadar}
                  disabled={loading === "radar"}
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  {loading === "radar" ? "Loading…" : "Load"}
                </button>
              </div>
            }
          >
            {radarError && (
              <div className="mb-2">
                <ErrorBanner message={radarError} />
              </div>
            )}
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 text-[11px] text-gray-300">
              {radarText || "Load でレーダーログを表示"}
            </pre>
          </Section>
        )}

        {tab === "signals" && (
          <>
            <Section
              title="Sector Lead-Lag Signals"
              action={
                <button
                  type="button"
                  onClick={fetchLeadLag}
                  disabled={loading === "leadlag"}
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  {loading === "leadlag" ? "Loading…" : "Run model"}
                </button>
              }
            >
              <p className="mb-2 text-[11px] text-gray-500">
                US→JP セクター予測。気になる銘柄は下の Paper Journal に記録（実発注なし）。
              </p>
              {leadLagError && (
                <div className="mb-2">
                  <ErrorBanner message={leadLagError} />
                </div>
              )}
              {leadLagParsed && !leadLagParsed.error && (
                <div className="mb-3 grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                    <h4 className="mb-2 text-xs font-semibold text-emerald-300">LONG candidates</h4>
                    <ul className="space-y-1 text-xs">
                      {Object.entries(asRecord(leadLagParsed.Recommended_Longs) || {}).map(([name, score]) => (
                        <li key={name} className="flex items-center justify-between gap-2">
                          <span>
                            {name}{" "}
                            <span className="font-mono text-gray-400">+{formatVal(score)}</span>
                          </span>
                          <button
                            type="button"
                            className="rounded border border-emerald-500/30 px-2 py-0.5 text-[10px] text-emerald-200 hover:bg-emerald-500/10"
                            onClick={() =>
                              addJournal(name, "long", `Lead-lag LONG score ${formatVal(score)}`, "lead_lag")
                            }
                          >
                            Paper
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="rounded-lg border border-rose-500/20 bg-rose-500/5 p-3">
                    <h4 className="mb-2 text-xs font-semibold text-rose-300">SHORT candidates</h4>
                    <ul className="space-y-1 text-xs">
                      {Object.entries(asRecord(leadLagParsed.Recommended_Shorts) || {}).map(([name, score]) => (
                        <li key={name} className="flex items-center justify-between gap-2">
                          <span>
                            {name}{" "}
                            <span className="font-mono text-gray-400">{formatVal(score)}</span>
                          </span>
                          <button
                            type="button"
                            className="rounded border border-rose-500/30 px-2 py-0.5 text-[10px] text-rose-200 hover:bg-rose-500/10"
                            onClick={() =>
                              addJournal(name, "short", `Lead-lag SHORT score ${formatVal(score)}`, "lead_lag")
                            }
                          >
                            Paper
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
              {!!leadLag && (
                <details className="text-[11px] text-gray-400">
                  <summary className="cursor-pointer text-gray-500">Raw JSON</summary>
                  <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3">
                    {leadLag}
                  </pre>
                </details>
              )}
              {!leadLag && !leadLagError && (
                <p className="text-xs text-gray-500">Run model でシグナルを取得</p>
              )}
            </Section>

            <Section title="Paper Journal">
              <p className="mb-3 text-[11px] text-gray-500">
                ブラウザ localStorage のみ。IBKR には送りません。
              </p>
              <div className="mb-3 flex flex-wrap gap-2">
                <input
                  value={paperSymbol}
                  onChange={(e) => setPaperSymbol(e.target.value)}
                  placeholder="Symbol / sector"
                  className="rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 text-sm text-white outline-none focus:border-cyan-500/50"
                />
                <select
                  value={paperSide}
                  onChange={(e) => setPaperSide(e.target.value as PaperSide)}
                  className="rounded-lg border border-white/10 bg-black/40 px-2 py-1.5 text-xs text-gray-200"
                >
                  <option value="long">LONG</option>
                  <option value="short">SHORT</option>
                </select>
                <input
                  value={paperNote}
                  onChange={(e) => setPaperNote(e.target.value)}
                  placeholder="Note"
                  className="min-w-[12rem] flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-1.5 text-sm text-white outline-none focus:border-cyan-500/50"
                />
                <button
                  type="button"
                  onClick={() => {
                    addJournal(paperSymbol, paperSide, paperNote, "manual");
                    setPaperSymbol("");
                    setPaperNote("");
                  }}
                  disabled={!paperSymbol.trim()}
                  className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-200 hover:bg-cyan-500/20 disabled:opacity-50"
                >
                  Add
                </button>
              </div>
              {journal.length === 0 ? (
                <p className="text-xs text-gray-500">まだ記録がありません</p>
              ) : (
                <ul className="space-y-2">
                  {journal.map((e) => (
                    <li
                      key={e.id}
                      className="flex items-start justify-between gap-2 rounded-lg border border-white/5 bg-black/20 px-3 py-2 text-xs"
                    >
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                              e.side === "long"
                                ? "bg-emerald-500/20 text-emerald-300"
                                : "bg-rose-500/20 text-rose-300"
                            }`}
                          >
                            {e.side.toUpperCase()}
                          </span>
                          <span className="font-mono text-gray-100">{e.symbol}</span>
                          {e.source && <span className="text-gray-500">· {e.source}</span>}
                        </div>
                        <p className="mt-1 text-gray-400">{e.note}</p>
                        <p className="mt-0.5 text-[10px] text-gray-600">
                          {new Date(e.createdAt).toLocaleString()}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="shrink-0 text-gray-500 hover:text-red-300"
                        onClick={() => setJournal(removePaperJournalEntry(e.id))}
                        title="Delete"
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </>
        )}
      </div>
    </div>
  );
}
