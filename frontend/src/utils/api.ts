export const getApiUrl = (path: string): string => {
  // 環境変数の前後の余白や途中のスペースを完全除去し、末尾のスラッシュも整理する安全設計
  const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\s+/g, "");
  const cleanBaseUrl = rawBaseUrl.replace(/\/+$/, "");
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${cleanBaseUrl}${cleanPath}`;
};
