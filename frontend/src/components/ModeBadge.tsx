/**
 * ModeBadge — モード状態表示 + 切替トグル
 * 🟢 雑談 / 🔵 実装 / 🟡 思考中 / 🟣 調査中
 */

interface ModeBadgeProps {
  mode: "chat" | "task" | "stocks" | "char" | "market";
  status: "idle" | "thinking" | "searching" | "responding" | "planning_search";
  onToggle: () => void;
}

export function ModeBadge({ mode, status, onToggle }: ModeBadgeProps) {
  // ステータスに応じたバッジクラスとラベル
  const getBadgeInfo = () => {
    if (status === "thinking") {
      return { className: "thinking", label: "Thinking", emoji: "🟡" };
    }
    if (status === "searching") {
      return { className: "searching", label: "Searching", emoji: "🟣" };
    }
    if (mode === "stocks" || mode === "market") {
      return { className: "stocks", label: "Market", emoji: "📈" };
    }
    if (mode === "task") {
      return { className: "task", label: "Workspace", emoji: "🔵" };
    }
    if (mode === "char") {
      return { className: "char", label: "Char", emoji: "🎭" };
    }
    return { className: "chat", label: "Chat", emoji: "🟢" };
  };

  const { className, label } = getBadgeInfo();

  return (
    <button
      className={`mode-badge ${className}`}
      onClick={onToggle}
      title={`Currently: ${label} mode (click: Chat→Workspace→Char→Market)`}
      aria-label={`${label} mode`}
      id="mode-badge"
    >
      <span className="dot" />
      <span>{label}</span>
    </button>
  );
}
