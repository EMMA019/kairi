/** toTradingViewSymbol / sector universe unit tests. */
import { describe, expect, it } from "vitest";
import {
  JP_SECTOR_BAR,
  US_SECTOR_BAR,
  toTradingViewSymbol,
  jpCodeFromSymbol,
} from "./sectorUniverse";

describe("sectorUniverse", () => {
  it("has SPDR 11 + XBI", () => {
    const codes = US_SECTOR_BAR.map((x) => x.symbol);
    for (const s of ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "XBI"]) {
      expect(codes).toContain(s);
    }
    expect(US_SECTOR_BAR).toHaveLength(12);
  });

  it("has TOPIX-17 JP sectors", () => {
    expect(JP_SECTOR_BAR).toHaveLength(17);
    expect(JP_SECTOR_BAR.map((x) => x.code)).toContain("1630");
    expect(JP_SECTOR_BAR.find((x) => x.code === "1630")?.label).toContain("銀行");
  });

  it("maps TradingView symbols", () => {
    expect(toTradingViewSymbol("SPY")).toBe("AMEX:SPY");
    expect(toTradingViewSymbol("AAPL")).toBe("NASDAQ:AAPL");
    expect(toTradingViewSymbol("1306.T")).toBe("TSE:1306");
    expect(toTradingViewSymbol("^N225")).toBe("TVC:NI225");
    expect(toTradingViewSymbol("TSE:7203")).toBe("TSE:7203");
  });

  it("jpCodeFromSymbol", () => {
    expect(jpCodeFromSymbol("1631.T")).toBe("1631");
    expect(jpCodeFromSymbol("^N225")).toBe("N225");
  });
});
