import { useState, useEffect } from "react";
import { apiFetch } from "../utils/api";
import { useLocale } from "../i18n";

interface FirstRunWizardProps {
  onComplete: () => void;
}

type WizardProvider = "gemini" | "groq" | "deepseek" | "local";

const LLM_SET_FLAGS = [
  "deepseek_api_key_set",
  "openai_api_key_set",
  "anthropic_api_key_set",
  "gemini_api_key_set",
  "groq_api_key_set",
] as const;

const KEY_FIELDS: Record<Exclude<WizardProvider, "local">, string> = {
  gemini: "gemini_api_key",
  groq: "groq_api_key",
  deepseek: "deepseek_api_key",
};

const SIGNUP: Record<
  Exclude<WizardProvider, "local">,
  { href: string; label: string; placeholder: string }
> = {
  gemini: {
    href: "https://aistudio.google.com/apikey",
    label: "aistudio.google.com",
    placeholder: "AIza...",
  },
  groq: {
    href: "https://console.groq.com/keys",
    label: "console.groq.com",
    placeholder: "gsk_...",
  },
  deepseek: {
    href: "https://platform.deepseek.com/",
    label: "platform.deepseek.com",
    placeholder: "sk-...",
  },
};

type FreeTierDefaults = Record<string, Record<string, string>>;

const FALLBACK_ROLE_DEFAULTS: Record<WizardProvider, Record<string, string>> = {
  gemini: {
    executor_provider: "gemini",
    executor_model: "gemini-2.5-flash",
    supervisor_provider: "gemini",
    supervisor_model: "gemini-2.5-flash",
    planner_provider: "gemini",
    planner_model: "gemini-2.5-flash",
  },
  groq: {
    executor_provider: "groq",
    executor_model: "llama-3.3-70b-versatile",
    supervisor_provider: "groq",
    supervisor_model: "llama-3.3-70b-versatile",
    planner_provider: "groq",
    planner_model: "llama-3.3-70b-versatile",
  },
  deepseek: {
    executor_provider: "deepseek",
    executor_model: "deepseek-v4-flash",
    supervisor_provider: "deepseek",
    supervisor_model: "deepseek-v4-flash",
    planner_provider: "deepseek",
    planner_model: "deepseek-v4-flash",
  },
  local: {
    executor_provider: "local",
    executor_model: "llama3",
    supervisor_provider: "local",
    supervisor_model: "llama3",
    planner_provider: "local",
    planner_model: "llama3",
  },
};

const PROVIDER_NAME_KEY: Record<
  WizardProvider,
  | "firstRun.provider.gemini"
  | "firstRun.provider.groq"
  | "firstRun.provider.deepseek"
  | "firstRun.provider.local"
> = {
  gemini: "firstRun.provider.gemini",
  groq: "firstRun.provider.groq",
  deepseek: "firstRun.provider.deepseek",
  local: "firstRun.provider.local",
};

/**
 * First run: Gemini / Groq free tiers, cheap DeepSeek, or local Ollama.
 */
export function FirstRunWizard({ onComplete }: FirstRunWizardProps) {
  const { t } = useLocale();
  const [visible, setVisible] = useState(false);
  const [checking, setChecking] = useState(true);
  const [provider, setProvider] = useState<WizardProvider>("gemini");
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [freeDefaults, setFreeDefaults] = useState<FreeTierDefaults>({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch("/api/settings");
        if (!res.ok) {
          if (!cancelled) setChecking(false);
          return;
        }
        const data = await res.json();
        const hasLlm =
          LLM_SET_FLAGS.some((f) => data[f] === true) ||
          data.executor_provider === "local";
        if (!cancelled) {
          if (data.free_tier_defaults && typeof data.free_tier_defaults === "object") {
            setFreeDefaults(data.free_tier_defaults);
          }
          setVisible(!hasLlm);
          setChecking(false);
        }
      } catch {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (checking || !visible) return null;

  const mapPingError = (code: string, detail?: string) => {
    const name = t(PROVIDER_NAME_KEY[provider]);
    switch (code) {
      case "invalid_key":
      case "empty":
        return t("firstRun.errorInvalid", { provider: name });
      case "balance":
        return t("firstRun.errorBalance", { provider: name });
      case "rate_limit":
        return t("firstRun.errorRateLimit", { provider: name });
      case "network":
        return t("firstRun.errorNetwork", { provider: name });
      default:
        return t("firstRun.errorUnknown", { detail: (detail || code || "").slice(0, 120) });
    }
  };

  const handleSave = async () => {
    const roleDefaults = {
      ...FALLBACK_ROLE_DEFAULTS[provider],
      ...(freeDefaults[provider] || {}),
    };
    setSaving(true);
    setError("");
    try {
      if (provider === "local") {
        const res = await apiFetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            executor_provider: "local",
            executor_model: "llama3",
            supervisor_provider: "local",
            supervisor_model: "llama3",
            planner_provider: "local",
            planner_model: "llama3",
            ...roleDefaults,
          }),
        });
        if (!res.ok) {
          setError(t("firstRun.errorHttp", { status: res.status }));
          return;
        }
        setVisible(false);
        onComplete();
        return;
      }

      const trimmed = key.trim();
      if (!trimmed) {
        setError(t("firstRun.errorEmpty", { provider: t(PROVIDER_NAME_KEY[provider]) }));
        return;
      }

      const pingRes = await apiFetch("/api/settings/ping-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, api_key: trimmed }),
      });
      if (!pingRes.ok) {
        setError(t("firstRun.errorHttp", { status: pingRes.status }));
        return;
      }
      const ping = await pingRes.json();
      if (!ping.ok) {
        setError(mapPingError(ping.error || "unknown", ping.detail));
        return;
      }

      const res = await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          [KEY_FIELDS[provider]]: trimmed,
          ...roleDefaults,
        }),
      });
      if (!res.ok) {
        setError(t("firstRun.errorHttp", { status: res.status }));
        return;
      }
      setVisible(false);
      onComplete();
    } catch {
      setError(t("firstRun.errorReach"));
    } finally {
      setSaving(false);
    }
  };

  const tabs: { id: WizardProvider; labelKey: "firstRun.tabGemini" | "firstRun.tabGroq" | "firstRun.tabDeepseek" | "firstRun.tabLocal" }[] = [
    { id: "gemini", labelKey: "firstRun.tabGemini" },
    { id: "groq", labelKey: "firstRun.tabGroq" },
    { id: "deepseek", labelKey: "firstRun.tabDeepseek" },
    { id: "local", labelKey: "firstRun.tabLocal" },
  ];

  const signup = provider === "local" ? null : SIGNUP[provider];
  const providerName = t(PROVIDER_NAME_KEY[provider]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 backdrop-blur-md">
      <div className="bg-[#0e121a] border border-[#2d3139] rounded-2xl w-full max-w-md mx-4 overflow-hidden shadow-2xl">
        <div className="px-6 py-5 border-b border-[#2d3139] bg-[#141822]/90">
          <p className="text-[11px] font-semibold tracking-wide text-cyan-400/90 uppercase mb-1">
            Kairi
          </p>
          <h2 className="text-lg font-bold text-white leading-snug">
            {t("firstRun.title")}
          </h2>
          <p className="text-xs text-gray-400 mt-2 leading-relaxed">
            {t("firstRun.body")}
          </p>
        </div>

        <div className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-2">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setProvider(tab.id);
                  setError("");
                  setKey("");
                }}
                className={`px-3 py-2 rounded-lg text-[11px] font-semibold border transition-colors ${
                  provider === tab.id
                    ? "border-cyan-500 bg-cyan-500/15 text-cyan-200"
                    : "border-[#2d3139] bg-[#0b0e14] text-gray-400 hover:border-[#3e4452]"
                }`}
              >
                {t(tab.labelKey)}
              </button>
            ))}
          </div>

          {provider === "local" ? (
            <p className="text-[11px] text-gray-500 leading-relaxed">
              {t("firstRun.localHint")}
            </p>
          ) : (
            <div>
              <label className="block text-xs font-semibold text-gray-300 mb-1.5">
                {t("firstRun.keyLabel", { provider: providerName })}
              </label>
              <input
                type="password"
                autoFocus
                value={key}
                onChange={(e) => setKey(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleSave();
                }}
                placeholder={signup?.placeholder}
                className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3.5 py-2.5 text-sm text-gray-100 focus:border-cyan-500 focus:outline-none"
              />
              <p className="text-[11px] text-gray-500 mt-2 leading-relaxed">
                {t("firstRun.keyHint")}{" "}
                <a
                  href={signup?.href}
                  target="_blank"
                  rel="noreferrer"
                  className="text-cyan-400 underline"
                >
                  {signup?.label}
                </a>
                {t("firstRun.keyHintAfter")}
              </p>
            </div>
          )}

          {error && (
            <div className="p-3 rounded-lg bg-red-900/30 border border-red-500/40 text-xs text-red-200">
              {error}
            </div>
          )}

          <button
            type="button"
            disabled={saving}
            onClick={() => void handleSave()}
            className="w-full py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-sm font-bold disabled:opacity-50 transition-all"
          >
            {saving
              ? provider === "local"
                ? t("firstRun.saving")
                : t("firstRun.verifying", { provider: providerName })
              : t("firstRun.save")}
          </button>
        </div>
      </div>
    </div>
  );
}
