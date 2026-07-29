/** Paper scalp sizing (JPY capital, USD stocks). No real orders. */

export type ScalpSettings = {
  capitalJpy: number;
  /** Acceptable loss if price moves against by targetUsd — not buy notional. */
  riskJpy: number;
  targetUsd: number;
  usdjpy: number;
  /** When true, Refresh does not overwrite usdjpy. */
  usdjpyManual: boolean;
};

export const DEFAULT_SCALP_SETTINGS: ScalpSettings = {
  capitalJpy: 200_000,
  riskJpy: 20_000,
  targetUsd: 1,
  usdjpy: 150,
  usdjpyManual: false,
};

export type ScalpSizing = {
  capitalShares: number;
  riskShares: number;
  recommended: number;
  pnlPerTargetJpy: number;
};

export function computeScalpSizing(
  priceUsd: number | null | undefined,
  settings: ScalpSettings,
): ScalpSizing | null {
  if (priceUsd == null || !(priceUsd > 0) || !(settings.usdjpy > 0)) return null;
  const capitalShares = Math.floor(settings.capitalJpy / (priceUsd * settings.usdjpy));
  const riskShares = Math.floor(settings.riskJpy / (settings.targetUsd * settings.usdjpy));
  const recommended = Math.max(0, Math.min(capitalShares, riskShares));
  const pnlPerTargetJpy = recommended * settings.targetUsd * settings.usdjpy;
  return { capitalShares, riskShares, recommended, pnlPerTargetJpy };
}

/** $1 / ATR — larger means $1 is "easier" relative to typical range. */
export function dollarEase(atr: number | null | undefined, targetUsd = 1): number | null {
  if (atr == null || !(atr > 0)) return null;
  return targetUsd / atr;
}
