import { useState, useEffect } from "react";
import { getApiUrl } from "../utils/api";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface Settings {
  supervisor_provider: string;
  supervisor_model: string;
  executor_provider: string;
  executor_model: string;
  planner_provider: string;
  planner_model: string;
  user_name?: string;
  user_location?: string;
  persona_style?: string;
  locale?: string;
  gemini_api_key?: string;
  anthropic_api_key?: string;
  openai_api_key?: string;
  deepseek_api_key?: string;
  brave_api_key?: string;
  world_news_api_key?: string;
  newsdata_api_key?: string;
  available_providers: string[];
  anthropic_models: string[];
  gemini_models: string[];
  deepseek_models: string[];
  openai_models: string[];
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<"models" | "persona" | "byok" | "system">("models");

  useEffect(() => {
    if (isOpen) {
      setLoading(true);
      fetch(getApiUrl("/api/settings"))
        .then(res => res.json())
        .then(data => {
          setSettings(data);
          setLoading(false);
        })
        .catch(err => {
          console.error(err);
          setLoading(false);
        });
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await fetch(getApiUrl("/api/settings"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          supervisor_provider: settings.supervisor_provider,
          supervisor_model: settings.supervisor_model,
          executor_provider: settings.executor_provider,
          executor_model: settings.executor_model,
          planner_provider: settings.planner_provider,
          planner_model: settings.planner_model,
          user_name: settings.user_name || "Boss",
          user_location: settings.user_location || "",
          persona_style: settings.persona_style || "standard",
          locale: settings.locale || "en",
          gemini_api_key: settings.gemini_api_key || "",
          anthropic_api_key: settings.anthropic_api_key || "",
          openai_api_key: settings.openai_api_key || "",
          deepseek_api_key: settings.deepseek_api_key || "",
          brave_api_key: settings.brave_api_key || "",
          world_news_api_key: settings.world_news_api_key || "",
          newsdata_api_key: settings.newsdata_api_key || "",
        })
      });
      onClose();
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  const getModels = (provider: string) => {
    if (!settings) return [];
    switch (provider) {
      case "anthropic": return settings.anthropic_models || [];
      case "gemini": return settings.gemini_models || [];
      case "deepseek": return settings.deepseek_models || [];
      case "openai": return settings.openai_models || [];
      default: return [];
    }
  };

  const renderSection = (title: string, providerKey: keyof Settings, modelKey: keyof Settings) => {
    if (!settings) return null;
    const provider = settings[providerKey] as string;
    const model = settings[modelKey] as string;
    const models = getModels(provider);

    return (
      <div className="mb-4 bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
        <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2 leading-normal">
          {title}
        </h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1 leading-normal">Provider</label>
            <select
              value={provider}
              onChange={(e) => {
                const newProvider = e.target.value;
                const newModels = getModels(newProvider);
                setSettings({ 
                  ...settings, 
                  [providerKey]: newProvider, 
                  [modelKey]: newModels[0] || "" 
                });
              }}
              className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3 py-2 text-xs text-gray-200 focus:border-blue-500 focus:outline-none leading-normal"
            >
              {settings.available_providers.map(p => (
                <option key={p} value={p}>{p}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1 leading-normal">Model</label>
            {provider === "local" ? (
              <input
                type="text"
                value={model}
                onChange={(e) => setSettings({ ...settings, [modelKey]: e.target.value })}
                placeholder="e.g. llama3, gemma2"
                className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3 py-2 text-xs text-gray-200 focus:border-blue-500 focus:outline-none leading-normal"
              />
            ) : (
              <select
                value={model}
                onChange={(e) => setSettings({ ...settings, [modelKey]: e.target.value })}
                className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3 py-2 text-xs text-gray-200 focus:border-blue-500 focus:outline-none leading-normal"
              >
                {models.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-[200] bg-black/70 flex items-center justify-center p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#0b0e14] border border-[#2d3139] rounded-2xl w-full max-w-xl flex flex-col shadow-2xl overflow-hidden">
        {/* ヘッダー */}
        <div className="flex justify-between items-center px-6 py-4 border-b border-[#2d3139] bg-[#121621]">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2.5 leading-normal">
              <span>⚙️</span> Kairi Integrated Settings Center
            </h2>
            <p className="text-xs text-gray-400 mt-0.5 leading-normal">Manage persona, BYOK API keys, and models</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-[#1a1f2e] transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>

        {/* タブヘッダー */}
        <div className="flex border-b border-[#2d3139] bg-[#0e121b] px-6 pt-2 gap-1 overflow-x-auto">
          {[
            { id: "models", label: "🤖 Models" },
            { id: "persona", label: "🎭 Persona & Voice" },
            { id: "byok", label: "🔑 BYOK API Keys" },
            { id: "system", label: "🌐 Language (i18n)" },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id as any)}
              className={`px-4 py-2.5 text-xs font-bold transition-all border-b-2 leading-normal whitespace-nowrap ${
                activeTab === t.id
                  ? "border-blue-500 text-blue-400 bg-blue-500/10 rounded-t-lg"
                  : "border-transparent text-gray-400 hover:text-gray-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        
        {/* タブボディ */}
        <div className="p-6 overflow-y-auto max-h-[60vh] space-y-4">
          {loading ? (
            <div className="text-center py-12 text-gray-400 text-xs font-medium">Loading settings...</div>
          ) : settings ? (
            <>
              {/* タブ 1: 🤖 モデル設定 */}
              {activeTab === "models" && (
                <div className="space-y-4 animate-in fade-in duration-200">
                  {renderSection("🧠 Supervisor Model", "supervisor_provider", "supervisor_model")}
                  {renderSection("🗣️ Executor Model", "executor_provider", "executor_model")}
                  {renderSection("🔍 Planner Model", "planner_provider", "planner_model")}
                </div>
              )}

              {/* タブ 2: 🎭 ペルソナ・応答 */}
              {activeTab === "persona" && (
                <div className="space-y-5 animate-in fade-in duration-200">
                  <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
                    <h3 className="text-sm font-semibold text-gray-200 mb-2 flex items-center gap-2 leading-normal">
                      👤 User Salutation (How AI addresses you)
                    </h3>
                    <input
                      type="text"
                      value={settings.user_name || ""}
                      onChange={(e) => setSettings({ ...settings, user_name: e.target.value })}
                      placeholder="e.g. Boss, Master, Nao"
                      className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3.5 py-2.5 text-xs text-gray-200 focus:border-blue-500 focus:outline-none leading-normal"
                    />
                    <p className="text-[11px] text-gray-400 mt-2 leading-relaxed">
                      💡 AI will consistently address you by this name across all modes.
                    </p>
                  </div>

                  <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
                    <h3 className="text-sm font-semibold text-gray-200 mb-2 flex items-center gap-2 leading-normal">
                      🏠 Home Location / Base City (お出かけ・移動起点の居住地)
                    </h3>
                    <input
                      type="text"
                      value={settings.user_location || ""}
                      onChange={(e) => setSettings({ ...settings, user_location: e.target.value })}
                      placeholder="e.g. 埼玉県久喜市, 東京都渋谷区, Osaka"
                      className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3.5 py-2.5 text-xs text-gray-200 focus:border-blue-500 focus:outline-none leading-normal"
                    />
                    <p className="text-[11px] text-gray-400 mt-2 leading-relaxed">
                      💡 Used as default origin for travel, transit routes, and local weather/events without affecting unrelated technical answers.
                    </p>
                  </div>

                  <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
                    <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2 leading-normal">
                      🎭 Assistant Tone & Persona
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {[
                        {
                          id: "standard",
                          name: "👔 Standard Tone",
                          desc: "Polite, professional standard English for general & business tasks (Default)",
                        },
                        {
                          id: "analyst",
                          name: "📊 Financial Analyst Mode",
                          desc: "Objective data strategist, quantitative grounding & structured market analysis",
                        },
                        {
                          id: "kairi_kansai",
                          name: "🐙 Casual Kairi",
                          desc: "Friendly, reliable engineering partner Kairi with casual tone",
                        },
                        {
                          id: "concise",
                          name: "⚡ Concise Mode",
                          desc: "Zero small talk, minimal word count, direct facts & diffs only",
                        },
                        {
                          id: "hyper_gal",
                          name: "💅 Hyper Gal Lv3 (omous Engine)",
                          desc: "テンションMAX＆極限ギャル文字コンパイラ自動変換モード",
                        },
                      ].map((p) => {
                        const isSelected = (settings.persona_style || "standard") === p.id;
                        return (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => setSettings({ ...settings, persona_style: p.id })}
                            className={`flex flex-col items-start p-3.5 rounded-xl border transition-all text-left ${
                              isSelected
                                ? "border-blue-500 bg-gradient-to-br from-blue-600/25 to-indigo-600/20 shadow-md shadow-blue-500/10"
                                : "border-[#2d3139] bg-[#0b0e14] hover:border-[#3e4452]"
                            }`}
                          >
                            <span className={`text-xs font-bold leading-normal mb-1 ${isSelected ? "text-blue-300" : "text-gray-200"}`}>
                              {p.name}
                            </span>
                            <span className="text-[11px] text-gray-400 leading-relaxed">
                              {p.desc}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* タブ 3: 🔑 BYOK キー設定 */}
              {activeTab === "byok" && (
                <div className="space-y-4 animate-in fade-in duration-200">
                  {/* LLM モデル API キー */}
                  <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2 leading-normal mb-1">
                      🤖 LLM Provider API Keys (BYOK)
                    </h3>
                    <p className="text-xs text-gray-400 leading-relaxed mb-4">
                      Enter your API keys to store them safely on your local machine.
                    </p>

                    <div className="space-y-3">
                      {[
                        { label: "Google Gemini API Key", key: "gemini_api_key", placeholder: "AIza..." },
                        { label: "Anthropic API Key", key: "anthropic_api_key", placeholder: "sk-ant-..." },
                        { label: "OpenAI API Key", key: "openai_api_key", placeholder: "sk-proj-..." },
                        { label: "DeepSeek API Key", key: "deepseek_api_key", placeholder: "sk-..." },
                      ].map((item) => (
                        <div key={item.key}>
                          <label className="block text-xs text-gray-300 font-semibold mb-1 leading-normal">
                            {item.label}
                          </label>
                          <input
                            type="password"
                            value={(settings as any)[item.key] || ""}
                            onChange={(e) => setSettings({ ...settings, [item.key]: e.target.value })}
                            placeholder={item.placeholder}
                            className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3.5 py-2 text-xs text-gray-200 font-mono focus:border-blue-500 focus:outline-none leading-normal"
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 検索・ニュース収集 API キー */}
                  <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
                    <h3 className="text-sm font-bold text-white flex items-center gap-2 leading-normal mb-1">
                      🔍 Search & News API Keys
                    </h3>
                    <p className="text-xs text-gray-400 leading-relaxed mb-4">
                      Configure external search & news engines like Brave Search or World News.
                    </p>

                    <div className="space-y-3">
                      {[
                        { label: "Brave Search API Key (BRAVE_API_KEY)", key: "brave_api_key", placeholder: "BSAvyU..." },
                        { label: "World News API Key (WORLD_NEWS_API_KEY)", key: "world_news_api_key", placeholder: "caef..." },
                        { label: "NewsData.io API Key (NEWSDATA_API_KEY)", key: "newsdata_api_key", placeholder: "pu..." },
                      ].map((item) => (
                        <div key={item.key}>
                          <label className="block text-xs text-gray-300 font-semibold mb-1 leading-normal">
                            {item.label}
                          </label>
                          <input
                            type="password"
                            value={(settings as any)[item.key] || ""}
                            onChange={(e) => setSettings({ ...settings, [item.key]: e.target.value })}
                            placeholder={item.placeholder}
                            className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3.5 py-2 text-xs text-gray-200 font-mono focus:border-blue-500 focus:outline-none leading-normal"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* タブ 4: 🌐 表示・言語 (i18n) */}
              {activeTab === "system" && (
                <div className="space-y-4 animate-in fade-in duration-200">
                  <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139]">
                    <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2 leading-normal">
                      🌐 Interface Locale
                    </h3>
                    <div className="grid grid-cols-2 gap-3">
                      {[
                        { id: "en", name: "🇺🇸 English", desc: "Main release (Recommended)" },
                        { id: "ja", name: "🇯🇵 日本語 (Japanese)", desc: "Japanese locale" },
                      ].map((loc) => {
                        const isSelected = (settings.locale || "en") === loc.id;
                        return (
                          <button
                            key={loc.id}
                            type="button"
                            onClick={() => setSettings({ ...settings, locale: loc.id })}
                            className={`flex flex-col items-start p-3.5 rounded-xl border transition-all text-left ${
                              isSelected
                                ? "border-blue-500 bg-blue-500/15 text-blue-300"
                                : "border-[#2d3139] bg-[#0b0e14] text-gray-400 hover:text-gray-200"
                            }`}
                          >
                            <span className="text-xs font-bold leading-normal">{loc.name}</span>
                            <span className="text-[11px] text-gray-400 leading-normal mt-0.5">{loc.desc}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-red-400 text-xs">Failed to load settings</div>
          )}
        </div>
        
        {/* フッター */}
        <div className="px-6 py-4 border-t border-[#2d3139] flex justify-between items-center bg-[#121621]">
          <span className="text-[11px] text-gray-500">
            ✓ Stored securely on local machine
          </span>
          <div className="flex gap-2.5">
            <button 
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-gray-300 hover:text-white hover:bg-[#1a1f2e] transition-colors leading-normal"
            >
              Cancel
            </button>
            <button 
              onClick={handleSave}
              disabled={saving || !settings}
              className="px-5 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-lg shadow-blue-600/25 transition-all disabled:opacity-50 active:scale-95 leading-normal"
            >
              {saving ? "Saving..." : "Save Settings"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
