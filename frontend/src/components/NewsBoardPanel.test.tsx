import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NewsBoardPanel } from "./NewsBoardPanel";

vi.mock("../utils/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../utils/api";

const mockedFetch = vi.mocked(apiFetch);

function jsonResponse(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response;
}

describe("NewsBoardPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    mockedFetch.mockReset();
  });

  it("renders region lanes and explain sends prompt", async () => {
    mockedFetch.mockResolvedValue(
      jsonResponse({
        verdict: "HEALTHY",
        pool_scanned: 2,
        region_counts: { US: 1, JP: 1, EU: 0, CN_ASIA: 0, GLOBAL: 0 },
        items: [
          {
            title: "Fed holds rates",
            url: "https://example.com/fed",
            source: "CNBC Market News",
            summary: "Rates unchanged",
            region: "US",
            importance: 80,
            is_high_trust_source: true,
          },
          {
            title: "日経平均が反発",
            url: "https://example.com/nikkei",
            source: "Yahoo Japan 経済・市況",
            region: "JP",
            importance: 50,
          },
        ],
      }),
    );

    const onAsk = vi.fn();
    render(<NewsBoardPanel onAsk={onAsk} autoRefresh={false} />);

    await waitFor(() => {
      expect(screen.getByText("Fed holds rates")).toBeInTheDocument();
    });
    expect(screen.getByText("日経平均が反発")).toBeInTheDocument();
    expect(screen.getByText(/Feed HEALTHY/)).toBeInTheDocument();
    expect(screen.getByText(/未読重要 1/)).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "解説して" })[0]);
    expect(onAsk).toHaveBeenCalledTimes(1);
    expect(onAsk.mock.calls[0][0]).toContain("Fed holds rates");
    expect(onAsk.mock.calls[0][0]).toContain("https://example.com/fed");

    await waitFor(() => {
      expect(screen.queryByText(/未読重要/)).not.toBeInTheDocument();
    });
  });
});
