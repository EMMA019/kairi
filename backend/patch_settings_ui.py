import re
import os

file_path = r"d:\program\chat\frontend\src\components\SettingsModal.tsx"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add states for usage and stats
state_target = "const [activeTab, setActiveTab] = useState<\"models\" | \"persona\" | \"byok\" | \"system\">(\"models\");"
state_replacement = """const [activeTab, setActiveTab] = useState<"models" | "persona" | "byok" | "system" | "stats">("models");
  const [usageStats, setUsageStats] = useState<any>(null);
  const [cacheStats, setCacheStats] = useState<any>(null);"""

if "const [usageStats, setUsageStats]" not in content:
    content = content.replace(state_target, state_replacement)

# 2. Fetch logic
fetch_target = """      fetch(getApiUrl("/api/settings"))
        .then(res => res.json())
        .then(data => {
          setSettings(data);
          setLoading(false);
        })
        .catch(err => {
          console.error(err);
          setLoading(false);
        });"""

fetch_replacement = """      Promise.all([
        fetch(getApiUrl("/api/settings")).then(res => res.json()),
        fetch(getApiUrl("/api/usage")).then(res => res.json()).catch(() => null),
        fetch(getApiUrl("/api/stats")).then(res => res.json()).catch(() => null)
      ]).then(([settingsData, usageData, cacheData]) => {
        setSettings(settingsData);
        if (usageData) setUsageStats(usageData);
        if (cacheData) setCacheStats(cacheData);
        setLoading(false);
      }).catch(err => {
        console.error(err);
        setLoading(false);
      });"""

if "Promise.all(" not in content:
    content = content.replace(fetch_target, fetch_replacement)

# 3. Add tab
tab_target = """            { id: "system", label: "🌐 Language (i18n)" },"""
tab_replacement = """            { id: "system", label: "🌐 Language (i18n)" },
            { id: "stats", label: "📈 System Stats" },"""

if "{ id: \"stats\", label: \"📈 System Stats\" }" not in content:
    content = content.replace(tab_target, tab_replacement)

# 4. Render tab body
render_target = """              {/* タブ 4: 🌐 表示・言語 (i18n) */}"""
render_replacement = """              {/* タブ 5: 📈 System Stats */}
              {activeTab === "stats" && (
                <div className="space-y-4 animate-in fade-in duration-200">
                  <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
                    <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2 leading-normal">
                      💸 Today's API Usage & Budget
                    </h3>
                    {usageStats ? (
                      <div className="space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-400">Total Tokens</span>
                          <span className="text-gray-200 font-mono">{usageStats.total_tokens?.toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-400">Estimated Cost</span>
                          <span className="text-blue-400 font-mono font-bold">${usageStats.estimated_cost?.toFixed(4)}</span>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-400">Daily Budget</span>
                          <span className="text-gray-200 font-mono">${usageStats.daily_budget?.toFixed(2)}</span>
                        </div>
                        
                        <div className="mt-3">
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-gray-400">Budget Utilization</span>
                            <span className="text-gray-200 font-mono">
                              {((usageStats.estimated_cost / (usageStats.daily_budget || 1)) * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="w-full bg-[#0b0e14] rounded-full h-2">
                            <div 
                              className={`h-2 rounded-full ${usageStats.estimated_cost > usageStats.daily_budget * 0.8 ? 'bg-red-500' : 'bg-blue-500'}`}
                              style={{ width: `${Math.min(((usageStats.estimated_cost / (usageStats.daily_budget || 1)) * 100), 100)}%` }}
                            ></div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-gray-500">Usage data not available.</div>
                    )}
                  </div>

                  <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
                    <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2 leading-normal">
                      ⚡ Cache Statistics
                    </h3>
                    {cacheStats ? (
                      <div className="space-y-3">
                        {Object.entries(cacheStats).map(([table, stat]: [string, any]) => {
                          if (table === "total") return null;
                          const hitRate = stat.hits + stat.entries > 0 ? (stat.hits / (stat.hits + stat.entries)) * 100 : 0;
                          return (
                            <div key={table} className="bg-[#0b0e14] p-3 rounded-lg border border-[#2d3139]">
                              <div className="text-xs font-semibold text-gray-300 mb-2 capitalize">{table.replace('_', ' ')}</div>
                              <div className="grid grid-cols-3 gap-2 text-center">
                                <div>
                                  <div className="text-[10px] text-gray-500">Entries</div>
                                  <div className="text-xs text-gray-200 font-mono">{stat.entries}</div>
                                </div>
                                <div>
                                  <div className="text-[10px] text-gray-500">Hits</div>
                                  <div className="text-xs text-green-400 font-mono">{stat.hits}</div>
                                </div>
                                <div>
                                  <div className="text-[10px] text-gray-500">Hit Rate</div>
                                  <div className="text-xs text-blue-400 font-mono">{hitRate.toFixed(1)}%</div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                        
                        <div className="mt-2 pt-2 border-t border-[#2d3139]">
                          <div className="flex justify-between items-center">
                            <span className="text-xs font-bold text-gray-300">Total Hit Rate</span>
                            <span className="text-sm font-bold text-blue-400 font-mono">
                              {cacheStats.total?.hits + cacheStats.total?.entries > 0 
                                ? ((cacheStats.total.hits / (cacheStats.total.hits + cacheStats.total.entries)) * 100).toFixed(1) 
                                : "0.0"}%
                            </span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-xs text-gray-500">Cache stats not available.</div>
                    )}
                  </div>
                </div>
              )}

              {/* タブ 4: 🌐 表示・言語 (i18n) */}"""

if "{/* タブ 5: 📈 System Stats */}" not in content:
    content = content.replace(render_target, render_replacement)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("SettingsModal.tsx patched successfully!")
