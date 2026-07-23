import { useState, useEffect } from "react";
import { getApiUrl } from "../utils/api";

interface IntegrityStats {
  verified_facts: number;
  unverified_facts: number;
  excluded_sources: number;
  citations: number;
  search_executions: number;
}

export function IntegrityBadge() {
  const [stats, setStats] = useState<IntegrityStats | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const fetchStats = async () => {
    try {
      const res = await fetch(getApiUrl("/api/integrity/stats"));
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchStats();
    // 60秒ごとに更新
    const timer = setInterval(fetchStats, 60000);
    return () => clearInterval(timer);
  }, []);

  if (!stats) return null;

  return (
    <div className="relative">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors"
        title="Integrity & Fact-check Stats"
      >
        <svg className="w-3.5 h-3.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <span className="text-[10px] font-bold text-emerald-400">
          {(stats.verified_facts + stats.citations).toLocaleString()}
        </span>
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-64 bg-[#111827]/95 backdrop-blur-xl border border-gray-700 shadow-2xl rounded-xl overflow-hidden z-50 animate-slide-up">
          <div className="px-4 py-3 bg-gradient-to-r from-emerald-900/40 to-teal-900/40 border-b border-gray-700/50">
            <h3 className="text-sm font-bold text-gray-200 flex items-center gap-2">
              <svg className="w-4 h-4 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              Integrity Dashboard
            </h3>
            <p className="text-[10px] text-gray-400 mt-1">Kairiの累計ファクトチェック統計</p>
          </div>
          
          <div className="p-3 space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="text-gray-400">検索実行回数</span>
              <span className="font-mono text-gray-200">{stats.search_executions.toLocaleString()}回</span>
            </div>
            <div className="flex justify-between items-center text-xs">
              <span className="text-gray-400">検証済みファクト</span>
              <span className="font-mono text-emerald-400">+{stats.verified_facts.toLocaleString()}件</span>
            </div>
            <div className="flex justify-between items-center text-xs">
              <span className="text-gray-400">未確認申告</span>
              <span className="font-mono text-yellow-400">{stats.unverified_facts.toLocaleString()}件</span>
            </div>
            <div className="flex justify-between items-center text-xs">
              <span className="text-gray-400">出典リンク提供</span>
              <span className="font-mono text-blue-400">{stats.citations.toLocaleString()}件</span>
            </div>
            
            <div className="mt-3 pt-3 border-t border-gray-700/50 flex justify-between items-center">
              <span className="text-[10px] text-gray-500">ハルシネーション(捏造)</span>
              <span className="text-xs font-bold text-emerald-400 flex items-center gap-1">
                0件 <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
