import { useState, useEffect } from "react";
import { apiFetch, getStoredApiToken, setStoredApiToken } from "../utils/api";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function AuthModal({ isOpen, onClose }: AuthModalProps) {
  const [licenseKey, setLicenseKey] = useState("KAIRI-PRO-ESTABLISHED");
  const [appPin, setAppPin] = useState("");
  const [inputPin, setInputPin] = useState("");
  const [apiToken, setApiToken] = useState("");
  const [inputApiToken, setInputApiToken] = useState("");
  const [isLicensed, setIsLicensed] = useState(true);
  const [statusMsg, setStatusMsg] = useState("");
  const [activeTab, setActiveTab] = useState<"license" | "pin" | "token" | "audit">("token");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      const stored = getStoredApiToken();
      setInputApiToken(stored);
      setApiToken(stored);
      apiFetch("/api/settings")
        .then((res) => res.json())
        .then((data) => {
          if (data.license_key !== undefined) setLicenseKey(data.license_key);
          if (data.is_licensed !== undefined) setIsLicensed(data.is_licensed);
          if (data.app_pin !== undefined) setAppPin(data.app_pin);
          if (data.api_token) {
            setApiToken(data.api_token);
            // サーバー側トークンがある場合は localStorage も同期（自締め出し防止）
            if (!stored) {
              setStoredApiToken(data.api_token);
              setInputApiToken(data.api_token);
            }
          }
        })
        .catch(console.error);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleActivate = async () => {
    setSaving(true);
    setStatusMsg("");
    try {
      if (!licenseKey || licenseKey.trim().length < 6) {
        setStatusMsg("有効な6文字以上のプロダクトキーを入力してください。");
        setSaving(false);
        return;
      }
      await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          license_key: licenseKey,
          is_licensed: true,
        }),
      });
      setIsLicensed(true);
      setStatusMsg("正規買い切りライセンスが認証・登録されました。");
    } catch (e) {
      setStatusMsg("認証エラーが発生しました。");
    } finally {
      setSaving(false);
    }
  };

  const handleSavePin = async () => {
    setSaving(true);
    setStatusMsg("");
    try {
      await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          app_pin: inputPin,
        }),
      });
      setAppPin(inputPin);
      // バックエンドは app_pin を API トークンとしても要求するため、localStorage に同期
      setStoredApiToken(inputPin);
      setInputApiToken(inputPin);
      setApiToken(inputPin);
      setStatusMsg(
        inputPin
          ? "PINセキュリティロックを設定し、クライアント認証も同期しました。"
          : "PINセキュリティロックを解除しました。"
      );
    } catch (e) {
      setStatusMsg("PIN設定保存エラーが発生しました。");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveApiToken = async () => {
    setSaving(true);
    setStatusMsg("");
    try {
      const token = inputApiToken.trim();
      await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_token: token,
        }),
      });
      setStoredApiToken(token);
      setApiToken(token);
      setStatusMsg(
        token
          ? "API Token を保存しました。以降の API 呼び出しに自動付与されます。"
          : "API Token をクリアしました（開発モード）。"
      );
    } catch (e) {
      setStatusMsg("API Token 保存エラーが発生しました。");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div className="bg-[#0e121a] border border-[#2d3139] rounded-2xl w-full max-w-xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
        <div className="px-6 py-4.5 border-b border-[#2d3139] flex items-center justify-between bg-[#141822]/90">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-lg font-bold shadow-lg shadow-blue-500/20">
              🛡️
            </div>
            <div>
              <h2 className="text-base font-bold text-white leading-normal flex items-center gap-2">
                Kairi セキュリティ＆製品認証センター
                {isLicensed && (
                  <span className="text-[10px] bg-gradient-to-r from-emerald-500/20 to-teal-500/20 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full font-semibold">
                    PRO ACTIVATED
                  </span>
                )}
              </h2>
              <p className="text-xs text-gray-400 leading-relaxed">
                API Token / PIN / ライセンス管理
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-[#1e2330]"
          >
            ✕
          </button>
        </div>

        <div className="flex border-b border-[#2d3139] bg-[#0b0e14] px-6 gap-2 pt-2 overflow-x-auto">
          {[
            { id: "token", label: "API Token" },
            { id: "pin", label: "PINロック" },
            { id: "license", label: "ライセンス" },
            { id: "audit", label: "チェックリスト" },
          ].map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id as typeof activeTab);
                  setStatusMsg("");
                }}
                className={`px-4 py-3 text-xs font-bold transition-all border-b-2 leading-normal whitespace-nowrap ${
                  isActive
                    ? "border-blue-500 text-blue-400 bg-[#141822]"
                    : "border-transparent text-gray-400 hover:text-gray-200"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="p-6 overflow-y-auto space-y-5">
          {statusMsg && (
            <div className="p-3.5 rounded-xl bg-blue-900/30 border border-blue-500/40 text-xs text-blue-200 font-medium leading-relaxed">
              {statusMsg}
            </div>
          )}

          {activeTab === "token" && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="bg-[#161a25] p-5 rounded-xl border border-[#2d3139]">
                <h3 className="text-sm font-bold text-white mb-2 leading-normal">
                  API Token（本番・LAN公開時）
                </h3>
                <p className="text-xs text-gray-400 leading-relaxed mb-4">
                  バックエンドの <code className="text-blue-300">api_token</code> / 環境変数{" "}
                  <code className="text-blue-300">KAIRI_API_TOKEN</code> と同じ値を入力してください。
                  ブラウザの localStorage に保存され、全 API 呼び出しに{" "}
                  <code className="text-blue-300">X-API-Token</code> として付与されます。
                </p>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-gray-300 font-semibold mb-1.5 leading-normal">
                      API Token {apiToken ? "(設定済み)" : "(未設定=開発モード)"}
                    </label>
                    <input
                      type="password"
                      value={inputApiToken}
                      onChange={(e) => setInputApiToken(e.target.value)}
                      placeholder="サーバー側と同じトークン"
                      className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-xl px-4 py-3 text-xs text-gray-200 font-mono focus:border-blue-500 focus:outline-none leading-normal"
                    />
                  </div>
                  <button
                    onClick={handleSaveApiToken}
                    disabled={saving}
                    className="w-full mt-2 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold rounded-xl transition-all shadow-lg shadow-blue-600/20 disabled:opacity-50"
                  >
                    {saving ? "保存中..." : "API Token を保存"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === "license" && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="bg-[#161a25] p-5 rounded-xl border border-[#2d3139]">
                <h3 className="text-sm font-bold text-white mb-2 leading-normal">
                  プロダクトライセンス認証
                </h3>
                <p className="text-xs text-gray-400 leading-relaxed mb-4">
                  ご購入時のシリアルキーを入力してください。ローカルに永続保存されます。
                </p>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-gray-300 font-semibold mb-1.5 leading-normal">
                      プロダクトキー
                    </label>
                    <input
                      type="text"
                      value={licenseKey}
                      onChange={(e) => setLicenseKey(e.target.value)}
                      placeholder="例: KAIRI-PRO-2026-XXXX"
                      className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-xl px-4 py-3 text-xs text-blue-300 font-mono focus:border-blue-500 focus:outline-none tracking-wider uppercase leading-normal"
                    />
                  </div>
                  <button
                    onClick={handleActivate}
                    disabled={saving}
                    className="w-full mt-2 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold rounded-xl transition-all shadow-lg shadow-blue-600/20 disabled:opacity-50"
                  >
                    {saving ? "認証確認中..." : "プロダクトキーをアクティベート"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === "pin" && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="bg-[#161a25] p-5 rounded-xl border border-[#2d3139]">
                <h3 className="text-sm font-bold text-white mb-2 leading-normal">
                  アプリケーション起動ロック PIN
                </h3>
                <p className="text-xs text-gray-400 leading-relaxed mb-4">
                  PIN を設定するとバックエンド認証にも使われます。クライアント側の API Token にも自動同期します（未同期だと全 API が 401 になります）。
                </p>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-gray-300 font-semibold mb-1.5 leading-normal">
                      新しい PIN コード（未入力で解除）
                    </label>
                    <input
                      type="password"
                      value={inputPin}
                      onChange={(e) => setInputPin(e.target.value)}
                      placeholder={appPin ? "現在のPIN設定済み (上書き入力)" : "例: 2026"}
                      className="w-full bg-[#0b0e14] border border-[#2d3139] rounded-xl px-4 py-3 text-xs text-gray-200 font-mono focus:border-blue-500 focus:outline-none leading-normal"
                    />
                  </div>
                  <button
                    onClick={handleSavePin}
                    disabled={saving}
                    className="w-full mt-2 py-3 bg-[#1e2330] hover:bg-[#282f40] text-gray-200 text-xs font-bold rounded-xl border border-[#3e4452] transition-all disabled:opacity-50"
                  >
                    {saving ? "設定保存中..." : "PIN 設定を適用する"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === "audit" && (
            <div className="space-y-4 animate-in fade-in duration-200">
              <div className="bg-[#161a25] p-5 rounded-xl border border-[#2d3139] space-y-3">
                <h3 className="text-sm font-bold text-white mb-1 leading-normal">
                  セキュリティ・チェックリスト（静的）
                </h3>
                <p className="text-xs text-gray-400 leading-relaxed mb-3">
                  実行時スキャンではありません。本番公開前の確認項目です。
                </p>
                <ul className="space-y-2 text-xs text-gray-300">
                  <li className="p-3 bg-[#0b0e14] rounded-xl border border-[#2d3139]">
                    API Token（または PIN）を本番で設定し、この画面の Token タブにも同じ値を保存したか
                  </li>
                  <li className="p-3 bg-[#0b0e14] rounded-xl border border-[#2d3139]">
                    settings.json に生の API キーをコミットしていないか
                  </li>
                  <li className="p-3 bg-[#0b0e14] rounded-xl border border-[#2d3139]">
                    CORS / ALLOW_OPEN_CORS を本番で開きすぎていないか
                  </li>
                  <li className="p-3 bg-[#0b0e14] rounded-xl border border-[#2d3139]">
                    image_engine が gallery（ローカルストック）になっているか
                  </li>
                </ul>
              </div>
            </div>
          )}
        </div>

        <div className="px-6 py-4 border-t border-[#2d3139] bg-[#141822]/50 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-xl bg-[#282f40] hover:bg-[#343c52] text-gray-200 text-xs font-semibold transition-colors"
          >
            完了して閉じる
          </button>
        </div>
      </div>
    </div>
  );
}
