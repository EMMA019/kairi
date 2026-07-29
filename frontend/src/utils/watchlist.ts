/** Watchlist + scalp settings (localStorage). Rows are keyed by symbol for future newsFlags join. */

import {
  DEFAULT_SCALP_SETTINGS,
  type ScalpSettings,
  type ScalpSizing,
  computeScalpSizing,
  dollarEase,
} from "./scalpSizing";

export const INDEX_BAR: Array<{ symbol: string; label: string }> = [
  { symbol: "DIA", label: "Dow" },
  { symbol: "SPY", label: "S&P500" },
  { symbol: "QQQ", label: "Nasdaq" },
  { symbol: "SOXX", label: "SOX" },
];

export const SECTOR_BAR: Array<{ symbol: string; label: string }> = [
  { symbol: "XLK", label: "Tech" },
  { symbol: "XLF", label: "Fin" },
  { symbol: "XLE", label: "Energy" },
  { symbol: "XBI", label: "Biotech" },
];

export const DEFAULT_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMD", "META"];

const WATCHLIST_KEY = "kairi_watchlist_v1";
const SCALP_KEY = "kairi_scalp_settings_v1";
export const WATCHLIST_MAX = 20;

export type QuotePayload = {
  ticker?: string;
  name?: string;
  current_price?: number | null;
  change_pct?: number | null;
  previous_close?: number | null;
  volume?: number | null;
  average_volume?: number | null;
  volume_ratio?: number | null;
  atr?: number | null;
  day_range?: number | null;
  day_high?: number | null;
  day_low?: number | null;
  source?: string;
  error?: string;
  currency?: string;
};

export type WatchRow = {
  symbol: string;
  quote: QuotePayload | null;
  metrics: {
    volumeRatio: number | null;
    atr: number | null;
    dayRange: number | null;
    dollarEase: number | null;
  };
  sizing: ScalpSizing | null;
  /** Reserved for future news radar join (NVDA/SSI lesson). v1 always []. */
  newsFlags: string[];
  updatedAt: string;
  error?: string;
};

function normalizeSymbol(raw: string): string {
  return raw.trim().toUpperCase();
}

export function loadWatchlist(): string[] {
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY);
    if (!raw) return [...DEFAULT_WATCHLIST];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [...DEFAULT_WATCHLIST];
    const syms = parsed.map((s) => normalizeSymbol(String(s))).filter(Boolean);
    return syms.length ? Array.from(new Set(syms)).slice(0, WATCHLIST_MAX) : [...DEFAULT_WATCHLIST];
  } catch {
    return [...DEFAULT_WATCHLIST];
  }
}

export function saveWatchlist(symbols: string[]): void {
  const cleaned = Array.from(new Set(symbols.map(normalizeSymbol).filter(Boolean))).slice(
    0,
    WATCHLIST_MAX,
  );
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(cleaned));
}

export function addWatchSymbol(symbols: string[], ticker: string): string[] {
  const s = normalizeSymbol(ticker);
  if (!s) return symbols;
  if (symbols.includes(s)) return symbols;
  if (symbols.length >= WATCHLIST_MAX) return symbols;
  const next = [...symbols, s];
  saveWatchlist(next);
  return next;
}

export function removeWatchSymbol(symbols: string[], ticker: string): string[] {
  const next = symbols.filter((s) => s !== normalizeSymbol(ticker));
  saveWatchlist(next);
  return next;
}

export function loadScalpSettings(): ScalpSettings {
  try {
    const raw = localStorage.getItem(SCALP_KEY);
    if (!raw) return { ...DEFAULT_SCALP_SETTINGS };
    const parsed = JSON.parse(raw) as Partial<ScalpSettings>;
    return {
      capitalJpy: Number(parsed.capitalJpy) || DEFAULT_SCALP_SETTINGS.capitalJpy,
      riskJpy: Number(parsed.riskJpy) || DEFAULT_SCALP_SETTINGS.riskJpy,
      targetUsd: Number(parsed.targetUsd) || DEFAULT_SCALP_SETTINGS.targetUsd,
      usdjpy: Number(parsed.usdjpy) || DEFAULT_SCALP_SETTINGS.usdjpy,
      usdjpyManual: Boolean(parsed.usdjpyManual),
    };
  } catch {
    return { ...DEFAULT_SCALP_SETTINGS };
  }
}

export function saveScalpSettings(settings: ScalpSettings): void {
  localStorage.setItem(SCALP_KEY, JSON.stringify(settings));
}

export function buildWatchRow(
  symbol: string,
  quote: QuotePayload | null,
  settings: ScalpSettings,
  error?: string,
): WatchRow {
  const atr = quote?.atr ?? null;
  const volumeRatio = quote?.volume_ratio ?? null;
  const dayRange = quote?.day_range ?? null;
  return {
    symbol,
    quote,
    metrics: {
      volumeRatio,
      atr,
      dayRange,
      dollarEase: dollarEase(atr, settings.targetUsd),
    },
    sizing: computeScalpSizing(quote?.current_price, settings),
    newsFlags: [],
    updatedAt: new Date().toISOString(),
    error,
  };
}
