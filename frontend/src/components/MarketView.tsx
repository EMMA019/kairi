/**
 * MarketView — マーケットモード本体。
 * モバイルは CHAT / MARKET / NEWS の3タブ。デスクトップは chat+desk 並置。
 */
import { memo, useEffect, useRef, useState } from "react";
import { ChatArea } from "./ChatArea";
import { InputArea } from "./InputArea";
import { MarketDesk } from "./MarketDesk";
import { NewsBoardPanel } from "./NewsBoardPanel";
import type { ChatMessage } from "../types";

interface MarketViewProps {
  sessionId: string;
  messages: ChatMessage[];
  streamingContent: string;
  streamingReasoning?: string;
  streamingSources?: Array<{ title: string; url: string; tier?: number }>;
  streamingChart?: any;
  pipelineStages?: Array<{ stage: string; detail: string; status: "pending" | "active" | "done" }>;
  status: "idle" | "thinking" | "searching" | "responding" | "planning_search";
  searchQuery: string | null;
  isFetchingHistory: boolean;
  error: string | null;
  onSend: (message: string, forceSearch?: boolean) => void;
  onStop: () => void;
  onCloseMarket: () => void;
}

type MobileTab = "chat" | "market" | "news";

export const MarketView = memo(({
  sessionId,
  messages,
  streamingContent,
  streamingReasoning,
  streamingSources,
  streamingChart,
  pipelineStages,
  status,
  searchQuery,
  isFetchingHistory,
  error,
  onSend,
  onStop,
  onCloseMarket,
}: MarketViewProps) => {
  const [chatWidth, setChatWidth] = useState(380);
  const [activeTab, setActiveTab] = useState<MobileTab>("market");
  const [newsUnreadHigh, setNewsUnreadHigh] = useState(0);
  const isDragging = useRef(false);

  const handleMouseDown = () => {
    isDragging.current = true;
    document.body.style.cursor = "col-resize";
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      setChatWidth(Math.max(280, Math.min(e.clientX - 56, window.innerWidth * 0.55)));
    };
    const handleMouseUp = () => {
      if (isDragging.current) {
        isDragging.current = false;
        document.body.style.cursor = "";
      }
    };
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const askFromNews = (message: string) => {
    setActiveTab("chat");
    onSend(message);
  };

  const mobileTabs: Array<{ id: MobileTab; label: string; activeClass: string }> = [
    { id: "chat", label: "CHAT", activeClass: "bg-[#1e1f20] text-white" },
    { id: "market", label: "MARKET", activeClass: "bg-[#1e1f20] text-cyan-300" },
    { id: "news", label: "NEWS", activeClass: "bg-[#1e1f20] text-amber-300" },
  ];

  return (
    <div className="flex h-full w-full flex-1 flex-col overflow-hidden bg-[#0b0f19] md:flex-row">
      <div className="flex shrink-0 border-b border-[#3c4043] bg-[#0d1117] p-1 md:hidden">
        {mobileTabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActiveTab(t.id)}
            className={`relative flex-1 rounded-md py-1.5 text-xs font-bold ${
              activeTab === t.id ? t.activeClass : "text-gray-400"
            }`}
          >
            {t.label}
            {t.id === "news" && newsUnreadHigh > 0 ? (
              <span className="absolute right-1 top-0.5 rounded bg-amber-500/25 px-1 text-[9px] font-bold text-amber-200">
                {newsUnreadHigh > 9 ? "9+" : newsUnreadHigh}
              </span>
            ) : null}
          </button>
        ))}
      </div>

      <div
        className={`${activeTab === "chat" ? "flex" : "hidden"} relative h-full w-full shrink-0 flex-col border-[#3c4043] bg-[#0d1117] md:flex md:w-auto md:border-r`}
        style={{
          width:
            typeof window !== "undefined" && window.innerWidth < 768 ? "100%" : `${chatWidth}px`,
        }}
      >
        <header className="flex shrink-0 items-center justify-between border-b border-[#3c4043] bg-[#0b0f19] px-3 py-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400/80">
            Market Chat
          </span>
          <button
            type="button"
            onClick={onCloseMarket}
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-[#1e1f20] hover:text-white"
            title="Close Market mode"
            aria-label="Close Market mode"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        {error && (
          <div className="shrink-0 border-b border-red-500/30 bg-red-500/15 px-3 py-1.5 text-center text-xs text-red-400">
            {error}
          </div>
        )}

        <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          <ChatArea
            sessionId={sessionId}
            messages={messages}
            streamingContent={streamingContent}
            streamingReasoning={streamingReasoning}
            streamingSources={streamingSources}
            streamingChart={streamingChart}
            pipelineStages={pipelineStages}
            status={status}
            searchQuery={searchQuery}
            isFetchingHistory={isFetchingHistory}
            onSend={onSend}
          />
        </div>

        <div className="shrink-0 border-t border-[#3c4043] bg-[#0d1117] px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2">
          <InputArea onSend={onSend} onStop={onStop} status={status} />
        </div>

        <div
          className="absolute bottom-0 right-0 top-0 z-20 hidden w-1.5 cursor-col-resize transition-colors hover:bg-cyan-500/50 active:bg-cyan-500 md:block"
          style={{ transform: "translateX(50%)" }}
          onMouseDown={handleMouseDown}
        />
      </div>

      <div
        className={`${activeTab === "market" ? "flex" : "hidden"} h-full min-w-0 w-full flex-1 flex-col md:flex`}
      >
        <MarketDesk
          onAskChat={(message) => {
            setActiveTab("chat");
            onSend(message);
          }}
        />
      </div>

      {/* モバイル専用: News をトップレベルタブに露出（Desk 内タブへ潜らせない） */}
      <div
        className={`${activeTab === "news" ? "flex" : "hidden"} h-full min-w-0 w-full flex-1 flex-col overflow-hidden md:hidden`}
      >
        <header className="flex shrink-0 items-center justify-between border-b border-white/10 px-4 py-3">
          <div>
            <h2 className="text-base font-bold tracking-tight text-white">News Board</h2>
            <p className="text-[11px] text-gray-500">地域レーン・未読重要を積極表示</p>
          </div>
          <button
            type="button"
            onClick={onCloseMarket}
            className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-[#1e1f20] hover:text-white"
            aria-label="Close Market mode"
          >
            ✕
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <NewsBoardPanel
            autoRefresh
            onAsk={askFromNews}
            onUnreadHighChange={setNewsUnreadHigh}
          />
        </div>
      </div>
    </div>
  );
});
