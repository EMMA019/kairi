import { useEffect, useState } from "react";
import { apiFetch } from "../utils/api";
import { useLocale } from "../i18n";

interface PromoDraft {
  id: number;
  created_at: string;
  status: string;
  channel: string;
  title: string;
  body: string;
  posted_at?: string | null;
  error?: string | null;
}

interface PromoStatus {
  enabled: boolean;
  auto_post: boolean;
  discord: boolean;
  github: boolean;
  disclose_bot: boolean;
  daily_cap: number;
  github_repo: string;
  github_token_set: boolean;
  discord_webhook_set: boolean;
  posted_today: number;
  draft_count: number;
}

interface PromoPanelProps {
  settings: {
    promo_enabled?: boolean;
    promo_auto_post?: boolean;
    promo_discord?: boolean;
    promo_github?: boolean;
    promo_daily_cap?: number;
    promo_disclose_bot?: boolean;
    promo_github_repo?: string;
    github_token?: string;
    workspace_github_repo?: string;
    workspace_github_branch?: string;
    workspace_github_create?: boolean;
    workspace_github_private?: boolean;
  };
  onChange: (patch: Record<string, unknown>) => void;
}

export function PromoPanel({ settings, onChange }: PromoPanelProps) {
  const { t } = useLocale();
  const [status, setStatus] = useState<PromoStatus | null>(null);
  const [drafts, setDrafts] = useState<PromoDraft[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [editing, setEditing] = useState<Record<number, string>>({});

  const refresh = async () => {
    try {
      const [st, list] = await Promise.all([
        apiFetch("/api/promo/status").then((r) => r.json()),
        apiFetch("/api/promo/drafts").then((r) => r.json()),
      ]);
      setStatus(st);
      setDrafts(list.drafts || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const act = async (path: string, method = "POST", body?: unknown) => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await apiFetch(path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(data.detail || t("settings.promo.fail"));
        return;
      }
      setMsg(t("settings.promo.ok"));
      await refresh();
    } catch {
      setMsg(t("settings.promo.fail"));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (key: string, value: boolean | number | string) => {
    onChange({ [key]: value });
  };

  return (
    <div className="space-y-4 animate-in fade-in duration-200">
      <p className="text-xs text-gray-400 leading-relaxed">{t("settings.promo.blurb")}</p>

      <div className="bg-[#161a25] p-4 rounded-xl border border-[#2d3139] space-y-3">
        <label className="flex items-center justify-between text-xs text-gray-200">
          <span>{t("settings.promo.enabled")}</span>
          <input
            type="checkbox"
            checked={!!settings.promo_enabled}
            onChange={(e) => toggle("promo_enabled", e.target.checked)}
          />
        </label>
        <label className="flex items-center justify-between text-xs text-gray-200">
          <span>{t("settings.promo.discord")}</span>
          <input
            type="checkbox"
            checked={settings.promo_discord !== false}
            onChange={(e) => toggle("promo_discord", e.target.checked)}
          />
        </label>
        <label className="flex items-center justify-between text-xs text-gray-200">
          <span>{t("settings.promo.github")}</span>
          <input
            type="checkbox"
            checked={!!settings.promo_github}
            onChange={(e) => toggle("promo_github", e.target.checked)}
          />
        </label>
        <label className="flex items-center justify-between text-xs text-gray-200">
          <span>{t("settings.promo.autoPost")}</span>
          <input
            type="checkbox"
            checked={!!settings.promo_auto_post}
            onChange={(e) => toggle("promo_auto_post", e.target.checked)}
          />
        </label>
        <p className="text-[10px] text-amber-400/80">{t("settings.promo.autoPostHint")}</p>
        <label className="flex items-center justify-between text-xs text-gray-200">
          <span>{t("settings.promo.disclose")}</span>
          <input
            type="checkbox"
            checked={settings.promo_disclose_bot !== false}
            onChange={(e) => toggle("promo_disclose_bot", e.target.checked)}
          />
        </label>
        <div>
          <label className="block text-[10px] text-gray-400 mb-1">{t("settings.promo.repo")}</label>
          <input
            value={settings.promo_github_repo || ""}
            onChange={(e) => toggle("promo_github_repo", e.target.value)}
            placeholder="owner/repo"
            className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3 py-2 text-xs text-gray-200 font-mono"
          />
        </div>
        <div>
          <label className="block text-[10px] text-gray-400 mb-1">{t("settings.promo.workspaceRepo")}</label>
          <input
            value={settings.workspace_github_repo || ""}
            onChange={(e) => toggle("workspace_github_repo", e.target.value)}
            placeholder="kairi-workspace"
            className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3 py-2 text-xs text-gray-200 font-mono"
          />
          <p className="text-[10px] text-gray-500 mt-1">{t("settings.promo.workspaceRepoHint")}</p>
        </div>
        <div>
          <label className="block text-[10px] text-gray-400 mb-1">{t("settings.promo.workspaceBranch")}</label>
          <input
            value={settings.workspace_github_branch || "main"}
            onChange={(e) => toggle("workspace_github_branch", e.target.value)}
            placeholder="main"
            className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3 py-2 text-xs text-gray-200 font-mono"
          />
        </div>
        <label className="flex items-center justify-between text-xs text-gray-200">
          <span>{t("settings.promo.workspaceCreate")}</span>
          <input
            type="checkbox"
            checked={settings.workspace_github_create !== false}
            onChange={(e) => toggle("workspace_github_create", e.target.checked)}
          />
        </label>
        <label className="flex items-center justify-between text-xs text-gray-200">
          <span>{t("settings.promo.workspacePrivate")}</span>
          <input
            type="checkbox"
            checked={!!settings.workspace_github_private}
            onChange={(e) => toggle("workspace_github_private", e.target.checked)}
          />
        </label>
        <div>
          <label className="block text-[10px] text-gray-400 mb-1">{t("settings.promo.token")}</label>
          <input
            type="password"
            value={settings.github_token || ""}
            onChange={(e) => toggle("github_token", e.target.value)}
            placeholder={t("settings.promo.tokenHint")}
            className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-lg px-3 py-2 text-xs text-gray-200 font-mono"
          />
        </div>
      </div>

      {status && (
        <p className="text-[10px] text-gray-500 font-mono">
          Discord webhook: {status.discord_webhook_set ? "set" : "missing"} · GitHub token:{" "}
          {status.github_token_set ? "set" : "missing"} · posted today {status.posted_today}/{status.daily_cap}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => act("/api/promo/collect")}
          className="px-3 py-1.5 text-xs font-bold rounded-lg bg-blue-600/80 text-white disabled:opacity-50"
        >
          {t("settings.promo.collect")}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={refresh}
          className="px-3 py-1.5 text-xs font-bold rounded-lg bg-[#1a1f2e] text-gray-200"
        >
          {t("settings.promo.refresh")}
        </button>
      </div>
      {msg && <p className="text-[11px] text-gray-400">{msg}</p>}

      <div className="space-y-3">
        {drafts.length === 0 && (
          <p className="text-xs text-gray-500">{t("settings.promo.empty")}</p>
        )}
        {drafts.map((d) => (
          <div key={d.id} className="bg-[#161a25] p-3 rounded-xl border border-[#2d3139] space-y-2">
            <div className="flex justify-between gap-2 text-[10px] text-gray-400">
              <span className="font-mono">#{d.id} {d.channel} · {d.status}</span>
              <span>{(d.created_at || "").slice(0, 16)}</span>
            </div>
            <p className="text-xs text-gray-200 font-semibold">{d.title}</p>
            <textarea
              value={editing[d.id] ?? d.body}
              onChange={(e) => setEditing({ ...editing, [d.id]: e.target.value })}
              className="w-full min-h-[120px] bg-[#0b0e14] border border-[#2d3139] rounded-lg px-2 py-1.5 text-[11px] text-gray-300 font-mono"
            />
            {d.error && <p className="text-[10px] text-red-400">{d.error}</p>}
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  act(`/api/promo/drafts/${d.id}`, "PATCH", {
                    body: editing[d.id] ?? d.body,
                  })
                }
                className="px-2 py-1 text-[10px] rounded bg-[#1a1f2e] text-gray-200"
              >
                {t("settings.promo.saveDraft")}
              </button>
              {d.status === "draft" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => act(`/api/promo/drafts/${d.id}/approve`)}
                  className="px-2 py-1 text-[10px] rounded bg-emerald-700/70 text-white"
                >
                  {t("settings.promo.approve")}
                </button>
              )}
              {d.status !== "rejected" && d.status !== "posted" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => act(`/api/promo/drafts/${d.id}/reject`)}
                  className="px-2 py-1 text-[10px] rounded bg-[#2a1a1a] text-red-300"
                >
                  {t("settings.promo.reject")}
                </button>
              )}
              {d.status !== "posted" && d.status !== "rejected" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => act(`/api/promo/drafts/${d.id}/post`)}
                  className="px-2 py-1 text-[10px] rounded bg-blue-700/80 text-white"
                >
                  {t("settings.promo.post")}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
