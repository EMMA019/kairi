/**
 * タイピングインジケーター — 「AIが入力中...」のアニメーション表示
 */

interface TypingIndicatorProps {
  status: "idle" | "thinking" | "searching" | "responding" | "planning_search";
  searchQuery: string | null;
}

export function TypingIndicator({ status, searchQuery }: TypingIndicatorProps) {
  const getLabel = () => {
    switch (status) {
      case "thinking":
        return "Thinking...";
      case "searching":
        return searchQuery ? `Searching "${searchQuery}"...` : "Searching...";
      case "responding":
        return "Generating...";
      default:
        return "";
    }
  };

  return (
    <div className="typing-indicator bg-white/5 backdrop-blur-md border border-white/10 rounded-full px-4 py-2 w-fit shadow-sm">
      <span className="dot bg-blue-400" />
      <span className="dot bg-purple-400" />
      <span className="dot bg-pink-400" />
      <span className="label text-gray-300 font-medium">{getLabel()}</span>
    </div>
  );
}
