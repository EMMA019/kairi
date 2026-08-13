import { beforeEach, describe, expect, it } from "vitest";
import {
  buildExplainPrompt,
  countUnreadHighImportance,
  displayTitle,
  itemKey,
  loadReadKeys,
  markRead,
  normalizeRegion,
  REGION_LABEL,
} from "./newsBoard";

describe("newsBoard helpers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("buildExplainPrompt includes title url and asks for investor summary", () => {
    const prompt = buildExplainPrompt({
      title: "NVDA jumps on earnings",
      url: "https://example.com/nvda",
      source: "CNBC",
      summary: "Shares rose after beat",
    });
    expect(prompt).toContain("投資家向け");
    expect(prompt).toContain("NVDA jumps on earnings");
    expect(prompt).toContain("https://example.com/nvda");
    expect(prompt).toContain("CNBC");
  });

  it("displayTitle prefers Japanese when enabled", () => {
    const item = {
      title: "BOJ rate hike expectations grow",
      title_ja: "日銀の利上げ観測が高まる",
    };
    expect(displayTitle(item, true)).toBe("日銀の利上げ観測が高まる");
    expect(displayTitle(item, false)).toBe("BOJ rate hike expectations grow");
  });

  it("normalizeRegion maps known codes", () => {
    expect(normalizeRegion("jp")).toBe("JP");
    expect(normalizeRegion("CN_ASIA")).toBe("CN_ASIA");
    expect(normalizeRegion("mars")).toBe("GLOBAL");
    expect(REGION_LABEL.JP).toBe("日本");
  });

  it("tracks unread high-importance items via localStorage", () => {
    const items = [
      { url: "https://a", importance: 80, title: "A" },
      { url: "https://b", importance: 40, title: "B" },
      { url: "https://c", importance: 90, title: "C" },
    ];
    expect(countUnreadHighImportance(items, new Set())).toBe(2);

    let read = loadReadKeys();
    read = markRead(items[0], read);
    expect(countUnreadHighImportance(items, read)).toBe(1);
    expect(loadReadKeys().has(itemKey(items[0]))).toBe(true);
  });
});
