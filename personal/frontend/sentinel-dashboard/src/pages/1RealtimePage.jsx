import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  TrendingUp, TrendingDown, RefreshCw, Brain, 
  ExternalLink, ArrowLeft, Newspaper, ChevronDown,
  Clock, Zap, AlertTriangle, Shield 
} from 'lucide-react';
import TradingViewWidget from '../components/TradingViewWidget';
import VCPChart from '../components/VCPChart';
import ScoreHistoryChart from '../components/ScoreHistoryChart';
import ScoreRadarChart from '../components/ScoreRadarChart';

const fmt = (n, d=2) => n != null ? `$${Number(n).toFixed(d)}` : '—';
const pct = (n) => n != null ? `${n > 0 ? '+' : ''}${Number(n).toFixed(2)}%` : '—';
const clr = (n) => n > 0 ? 'text-green' : n < 0 ? 'text-red' : 'text-dim';

/* ── センチメント判定（共通） ───────────────────────────── */
// フレーズマッチを使って精度を上げる
// 単語マッチだと "sell" が "best-selling" にも反応するので注意
const SENT_POS_WORDS = [
  'beat','upgrade','outperform','strong buy','buy rating',
  'growth','surge','bullish','rally','breakout','record high',
  'profit','soar','jump','rises','gains','up ','climbs',
  'safe haven','positive','optimistic','launched','approved',
  'partnership','wins','expands','boosts','higher',
  'bombshell','unveils','debut','record sales','all-time high',
];
const SENT_NEG_WORDS = [
  'miss','downgrade','underperform','sell rating','weak',
  'decline','drops','bearish','loss','warning','cut','sued',
  'sinks','falls','plunges','investigation','recall','layoffs',
  'concern','risk','trouble','disappoints','lower','lawsuit',
  'abusive','scandal','fraud','violation','penalty','fine',
  'to sell','short sellers','target price cut','downfall',
];

function detectSentiment(title) {
  const lower = title.toLowerCase();
  // フレーズ優先、単語フォールバック
  const posHit = SENT_POS_WORDS.filter(w => lower.includes(w));
  const negHit = SENT_NEG_WORDS.filter(w => lower.includes(w));
  const pos = posHit.length;
  const neg = negHit.length;
  if (pos > neg) return 'pos';
  if (neg > pos) return 'neg';
  return 'neu';
}

function relativeTime(dateStr) {
  try {
    const diffH = (Date.now() - new Date(dateStr).getTime()) / 3600000;
    return diffH < 1  ? `${Math.round(diffH * 60)}m`
         : diffH < 24 ? `${Math.round(diffH)}h`
         : `${Math.round(diffH / 24)}d`;
  } catch { return ''; }
}

function cleanTitle(raw) {
  return (raw || '').replace(/ - [^-]{2,50}$/, '').trim();
}

/* ── Google News RSS パーサー（共通） ───────────────────── */
function parseNewsItems(xmlString, limit = 8) {
  const xml   = new DOMParser().parseFromString(xmlString, 'text/xml');
  const items = Array.from(xml.querySelectorAll('item')).slice(0, limit);
  if (items.length === 0) throw new Error('No items in XML');

  return items.map(item => {
    const title   = cleanTitle(item.querySelector('title')?.textContent);
    const link    = item.querySelector('link')?.textContent    || '#';
    const pubDate = item.querySelector('pubDate')?.textContent || '';
    const source  = item.querySelector('source')?.textContent  || '';
    return { title, link, source, relTime: relativeTime(pubDate), sentiment: detectSentiment(title) };
  });
}

/* ── Google News RSS をサーバーレスに取得（フォールバックチェーン） ── */
async function fetchGoogleNews(ticker) {
  const q      = encodeURIComponent(`${ticker} stock`);
  const rssUrl = `https://news.google.com/rss/search?q=${q}&hl=en-US&gl=US&ceid=US:en`;

  // ── 戦略1: rss2json.com（RSSをJSONに変換・CORSフリー） ──────
  // 最も安定。無料プランで60req/h。AAPLのような大型株は確実にヒットする。
  try {
    const url = `https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(rssUrl)}&count=8`;
    const res  = await fetch(url, { signal: AbortSignal.timeout(7000) });
    const json = await res.json();
    if (json.status === 'ok' && json.items?.length > 0) {
      return json.items.map(item => {
        const title = cleanTitle(item.title);
        const link  = item.link || '#';
        let source  = item.author || '';
        if (!source) { try { source = new URL(link).hostname.replace('www.',''); } catch {} }
        return { title, link, source, relTime: relativeTime(item.pubDate), sentiment: detectSentiment(title) };
      });
    }
  } catch (e) { console.warn('[News] rss2json failed:', e.message); }

  // ── 戦略2: corsproxy.io ──────────────────────────────────────
  try {
    const url = `https://corsproxy.io/?${encodeURIComponent(rssUrl)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(7000) });
    const txt = await res.text();
    if (txt.includes('<item>')) return parseNewsItems(txt);
  } catch (e) { console.warn('[News] corsproxy.io failed:', e.message); }

  // ── 戦略3: allorigins.win ────────────────────────────────────
  try {
    const url = `https://api.allorigins.win/get?url=${encodeURIComponent(rssUrl)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
    const json = await res.json();
    if (json.contents?.includes('<item>')) return parseNewsItems(json.contents);
  } catch (e) { console.warn('[News] allorigins failed:', e.message); }

  // ── 戦略4: api.codetabs.com ─────────────────────────────────
  try {
    const url = `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(rssUrl)}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(7000) });
    const txt = await res.text();
    if (txt.includes('<item>')) return parseNewsItems(txt);
  } catch (e) { console.warn('[News] codetabs failed:', e.message); }

  // 全戦略失敗
  console.error('[News] All proxies failed for', ticker);
  return [];
}

/* ── News Section ──────────────────────────────────────── */
function NewsSection({ ticker }) {
  const [news, setNews]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchGoogleNews(ticker)
      .then(items => { setNews(items); setLoading(false); if (items.length === 0) setError(true); })
      .catch(() => { setError(true); setLoading(false); });
  }, [ticker]);

  const sentColor = { pos: '#00ff88', neg: '#ff3355', neu: '#6b7a90' };
  const sentLabel = { pos: '▲', neg: '▼', neu: '—' };

  return (
    <div className="rt-section">
      <div className="rt-section-header">
        <div className="rt-section-title">
          <Newspaper size={13} style={{ color: '#4499ff' }} />
          <span>LATEST NEWS</span>
          <span className="rt-badge-blue">Google News RSS</span>
        </div>
        <button
          className="rt-refresh-btn"
          onClick={() => { setLoading(true); fetchGoogleNews(ticker).then(setNews).finally(() => setLoading(false)); }}
        >
          <RefreshCw size={11} /> 更新
        </button>
      </div>

      {loading && (
        <div className="rt-news-loading">
          <div className="loading-bar"><div className="loading-fill"/></div>
          <span>Fetching news...</span>
        </div>
      )}

      {error && !loading && (
        <div className="rt-news-error">
          ⚠ ニュース取得失敗 — 更新ボタンで再試行してください
        </div>
      )}

      {!loading && !error && news.length === 0 && (
        <div className="rt-news-empty">⚠ {ticker}のニュース取得失敗 — 更新ボタンで再試行してください</div>
      )}

      {!loading && news.length > 0 && (
        <div className="rt-news-list">
          {news.map((n, i) => (
            <a
              key={i}
              href={n.link}
              target="_blank"
              rel="noopener noreferrer"
              className="rt-news-item"
            >
              <div className="rt-news-sentiment" style={{ color: sentColor[n.sentiment] }}>
                {sentLabel[n.sentiment]}
              </div>
              <div className="rt-news-body">
                <div className="rt-news-title">{n.title}</div>
                <div className="rt-news-meta">
                  {n.source && <span className="rt-news-source">{n.source}</span>}
                  {n.relTime && (
                    <span className="rt-news-time">
                      <Clock size={9} /> {n.relTime}
                    </span>
                  )}
                </div>
              </div>
              <ExternalLink size={11} className="rt-news-ext" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
/* ══════════════════════════════════════════════════════════
   RANGE PREDICT COMPONENT
   統計ベースの翌週レンジ予測
   ══════════════════════════════════════════════════════════ */
function RangePredict({ data, quote }) {
  const price  = quote?.price || data.price;
  const atr    = data.vcp_details?.atr || 0;
  const pivot  = data.pivot || 0;
  const rangePct   = data.vcp_details?.range_pct || 0;
  const volRatio   = data.vcp_details?.vol_ratio || 1;
  const vcp    = data.scores?.vcp  || 0;
  const rs     = data.scores?.rs   || 0;
  const ses    = data.scores?.ses  || 0;

  if (!atr || !price) return null;

  // ── 1. ATRベース週次レンジ ──────────────────────────────
  // 週次 ≒ 日次ATR × √5 ≈ 2.24 （ランダムウォーク近似）
  // 実際はやや狭めに2.0で計算
  const weeklyMult = 2.0;
  const atrUpper   = price + atr * weeklyMult;
  const atrLower   = price - atr * weeklyMult;

  // ── 2. VCPベース（収縮パターン → ブレイク幅推定） ──────
  // range_pct = 現在のベース幅 → ブレイク後の期待幅
  // VCPスコア高いほど収縮が完了している → ブレイク幅が大きい
  const vcpMult  = vcp >= 70 ? 1.8 : vcp >= 50 ? 1.4 : 1.0;
  const baseRange = price * rangePct;
  const vcpUpper  = price + baseRange * vcpMult;
  const vcpLower  = price - baseRange * 0.7;  // 下は非対称（ブレイクアウト方向バイアス）

  // ── 3. RS補正（資金流入バイアス） ──────────────────────
  // RS高いほど上方バイアス（機関資金が入り続けてる）
  // RS50=中立、RS90+=強い上方バイアス
  const rsBias   = Math.max(-0.15, Math.min(0.25, (rs - 50) / 50 * 0.3));
  const rsUpper  = atrUpper  * (1 + rsBias * 0.15);
  const rsLower  = atrLower  * (1 - rsBias * 0.05);  // 下は逆方向に小さく

  // ── 4. 総合予測レンジ（3手法の加重平均） ──────────────
  // ATR: 40% / VCP: 35% / RS補正: 25%
  const predUpper = atrUpper * 0.40 + vcpUpper * 0.35 + rsUpper * 0.25;
  const predLower = atrLower * 0.40 + vcpLower * 0.35 + rsLower * 0.25;
  const predMid   = (predUpper + predLower) / 2;

  // ── 5. エントリーゾーン ─────────────────────────────────
  // 理想: ATRの0.3倍押し目 or 現在値近辺
  // 積極: 現在値そのまま
  // 見送りライン: pivot超え（過熱）or ±2ATR超え
  const entryIdeal      = Math.min(price, price - atr * 0.3);
  const entryAggressive = price;
  const entryAvoid      = pivot > 0 ? pivot * 1.02 : price + atr * 1.5;

  // ── 6. 信頼度スコア ─────────────────────────────────────
  // データ品質・スコア整合性から信頼度を計算
  let confidence = 50;
  if (vcp >= 70)   confidence += 15;  // VCP収縮完了
  if (rs  >= 80)   confidence += 10;  // 強い相対強度
  if (ses >= 50)   confidence += 10;  // SES整合
  if (volRatio < 0.8) confidence += 10;  // ドライアップ
  if (pivot > 0 && Math.abs(data.pivot_dist_pct || 0) < 5) confidence += 5;  // pivot近辺
  confidence = Math.min(95, confidence);

  // ── 7. シグナル判定 ─────────────────────────────────────
  const signal = vcp >= 70 && rs >= 80  ? 'BREAKOUT_READY'
               : vcp >= 50 && rs >= 60  ? 'CONSOLIDATING'
               : rs  >= 85              ? 'RS_DRIVEN'
               : vcp >= 70              ? 'VCP_ONLY'
               :                          'WAIT';

  const signalLabel = {
    BREAKOUT_READY: '⚡ ブレイクアウト準備完了',
    CONSOLIDATING:  '🔄 コンソリデーション中',
    RS_DRIVEN:      '📈 RSドリブン（資金流入）',
    VCP_ONLY:       '📐 VCP収縮中',
    WAIT:           '⏳ 様子見',
  }[signal];

  const signalColor = {
    BREAKOUT_READY: '#00ff88',
    CONSOLIDATING:  '#4499ff',
    RS_DRIVEN:      '#ffb800',
    VCP_ONLY:       '#aa66ff',
    WAIT:           '#6b7a90',
  }[signal];

  // ── 縦型レンジバー用ヘルパー ────────────────────────────
  // 縦軸: 上がpredUpper、下がpredLower
  // toY: 価格 → SVG y座標（0=上限、100=下限）
  const svgMin  = Math.min(predLower, price - atr * 2.5) * 0.98;
  const svgMax  = Math.max(predUpper, pivot || 0, price + atr * 2.5) * 1.02;
  const svgSpan = svgMax - svgMin;
  const toY = (v) => ((svgMax - v) / svgSpan * 100);

  // 各レベルのY座標（%）
  const yUpper  = toY(predUpper);
  const yLower  = toY(predLower);
  const yMid    = toY(predMid);
  const yPrice  = toY(price);
  const yPivot  = pivot > 0 ? toY(pivot) : null;
  const yStop   = toY(price - atr * 1.5);
  const yEntry  = toY(entryIdeal);
  const yAvoid  = toY(entryAvoid);

  return (
    <div className="bg-panel border border-border rounded-xl p-5">

      {/* ── ヘッダー ────────────────────────────────────────── */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'1.25rem' }}>
        <div style={{ display:'flex', alignItems:'center', gap:'0.5rem' }}>
          <span style={{ color:'#aa66ff', fontSize:'0.9rem' }}>◈</span>
          <span style={{ fontFamily:'monospace', fontSize:'0.6rem', color:'var(--muted)', letterSpacing:3 }}>
            WEEKLY RANGE FORECAST
          </span>
          <span style={{ fontFamily:'monospace', fontSize:'0.55rem', padding:'0.15rem 0.5rem',
            background:'rgba(170,102,255,0.1)', color:'#aa66ff',
            border:'1px solid rgba(170,102,255,0.25)', borderRadius:4 }}>
            統計ベース
          </span>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:'0.75rem' }}>
          <span style={{ fontFamily:'monospace', fontSize:'0.65rem', color: signalColor }}>{signalLabel}</span>
          <span style={{ fontFamily:'monospace', fontSize:'0.6rem', padding:'0.15rem 0.5rem',
            background:'rgba(255,255,255,0.04)', borderRadius:4,
            color: confidence >= 70 ? '#00ff88' : confidence >= 55 ? '#ffb800' : '#6b7a90' }}>
            信頼度 {confidence}%
          </span>
        </div>
      </div>

      {/* ── メインレイアウト: 縦型バー + 右側パネル ─────────── */}
      <div style={{ display:'grid', gridTemplateColumns:'120px 1fr', gap:'1.25rem', alignItems:'stretch' }}>

        {/* ── 縦型レンジバー ────────────────────────────────── */}
        <div style={{ position:'relative' }}>
          <svg viewBox="0 0 120 300" style={{ width:'100%', height:300 }}>

            {/* 背景グリッド */}
            {[0,25,50,75,100].map(pct => (
              <line key={pct}
                x1="28" y1={`${pct * 2.8 + 10}`}
                x2="68" y2={`${pct * 2.8 + 10}`}
                stroke="rgba(255,255,255,0.04)" strokeWidth="0.5"/>
            ))}

            {/* 予測レンジ帯（紫） */}
            <rect
              x="36" y={`${yUpper * 2.8 + 10}`}
              width="24" height={`${(yLower - yUpper) * 2.8}`}
              fill="rgba(170,102,255,0.15)"
              stroke="rgba(170,102,255,0.4)" strokeWidth="0.8" rx="3"
            />

            {/* エントリーゾーン（緑帯） */}
            <rect
              x="38" y={`${Math.min(toY(entryAggressive), yEntry) * 2.8 + 10}`}
              width="20" height={`${Math.abs(yEntry - toY(entryAggressive)) * 2.8 + 2}`}
              fill="rgba(0,255,136,0.18)"
              stroke="rgba(0,255,136,0.5)" strokeWidth="0.8" rx="2"
            />

            {/* 上限ライン */}
            <line x1="30" y1={`${yUpper * 2.8 + 10}`} x2="66" y2={`${yUpper * 2.8 + 10}`}
              stroke="#aa66ff" strokeWidth="1.5"/>
            <text x="70" y={`${yUpper * 2.8 + 13}`} fill="#aa66ff" fontSize="6" fontFamily="monospace">
              ${predUpper.toFixed(0)}
            </text>
            <text x="4" y={`${yUpper * 2.8 + 13}`} fill="rgba(170,102,255,0.6)" fontSize="4.5" fontFamily="monospace">
              上限
            </text>

            {/* 中央値ライン（破線） */}
            <line x1="30" y1={`${yMid * 2.8 + 10}`} x2="66" y2={`${yMid * 2.8 + 10}`}
              stroke="rgba(170,102,255,0.5)" strokeWidth="0.8" strokeDasharray="3,2"/>
            <text x="70" y={`${yMid * 2.8 + 13}`} fill="rgba(170,102,255,0.7)" fontSize="5.5" fontFamily="monospace">
              ${predMid.toFixed(0)}
            </text>
            <text x="6" y={`${yMid * 2.8 + 13}`} fill="rgba(170,102,255,0.5)" fontSize="4" fontFamily="monospace">
              中央
            </text>

            {/* PIVOT ライン */}
            {yPivot !== null && yPivot > 0 && yPivot < 100 && (
              <>
                <line x1="28" y1={`${yPivot * 2.8 + 10}`} x2="68" y2={`${yPivot * 2.8 + 10}`}
                  stroke="#00ff88" strokeWidth="1.5" strokeDasharray="4,2"/>
                <text x="70" y={`${yPivot * 2.8 + 13}`} fill="#00ff88" fontSize="6" fontFamily="monospace">
                  ${pivot.toFixed(0)}
                </text>
                <text x="2" y={`${yPivot * 2.8 + 13}`} fill="#00ff88" fontSize="4.5" fontFamily="monospace">
                  PIVOT
                </text>
              </>
            )}

            {/* 現在値ライン（白・太） */}
            <line x1="28" y1={`${yPrice * 2.8 + 10}`} x2="68" y2={`${yPrice * 2.8 + 10}`}
              stroke="rgba(255,255,255,0.9)" strokeWidth="2"/>
            {/* 現在値の三角マーカー */}
            <polygon
              points={`28,${yPrice*2.8+7} 28,${yPrice*2.8+13} 22,${yPrice*2.8+10}`}
              fill="white"/>
            <text x="70" y={`${yPrice * 2.8 + 13}`} fill="white" fontSize="6.5" fontFamily="monospace" fontWeight="bold">
              ${price.toFixed(0)}
            </text>
            <text x="3" y={`${yPrice * 2.8 + 22}`} fill="rgba(255,255,255,0.4)" fontSize="4" fontFamily="monospace">
              NOW
            </text>

            {/* エントリー理想ライン */}
            <line x1="30" y1={`${yEntry * 2.8 + 10}`} x2="66" y2={`${yEntry * 2.8 + 10}`}
              stroke="rgba(0,255,136,0.7)" strokeWidth="1" strokeDasharray="2,2"/>
            <text x="70" y={`${yEntry * 2.8 + 13}`} fill="rgba(0,255,136,0.8)" fontSize="5" fontFamily="monospace">
              ${entryIdeal.toFixed(0)}
            </text>
            <text x="3" y={`${yEntry * 2.8 + 13}`} fill="rgba(0,255,136,0.6)" fontSize="3.8" fontFamily="monospace">
              IN理想
            </text>

            {/* ストップライン（赤） */}
            <line x1="30" y1={`${yStop * 2.8 + 10}`} x2="66" y2={`${yStop * 2.8 + 10}`}
              stroke="rgba(255,51,85,0.7)" strokeWidth="1" strokeDasharray="2,2"/>
            <text x="70" y={`${yStop * 2.8 + 13}`} fill="rgba(255,51,85,0.8)" fontSize="5" fontFamily="monospace">
              ${(price - atr * 1.5).toFixed(0)}
            </text>
            <text x="4" y={`${yStop * 2.8 + 13}`} fill="rgba(255,51,85,0.6)" fontSize="3.8" fontFamily="monospace">
              STOP
            </text>

            {/* 下限ライン */}
            <line x1="30" y1={`${yLower * 2.8 + 10}`} x2="66" y2={`${yLower * 2.8 + 10}`}
              stroke="#ff3355" strokeWidth="1.5"/>
            <text x="70" y={`${yLower * 2.8 + 13}`} fill="#ff3355" fontSize="6" fontFamily="monospace">
              ${predLower.toFixed(0)}
            </text>
            <text x="4" y={`${yLower * 2.8 + 13}`} fill="rgba(255,51,85,0.6)" fontSize="4.5" fontFamily="monospace">
              下限
            </text>

          </svg>
        </div>

        {/* ── 右側パネル ───────────────────────────────────── */}
        <div style={{ display:'flex', flexDirection:'column', gap:'0.75rem' }}>

          {/* 予測レンジ */}
          <div style={{ background:'rgba(170,102,255,0.06)', border:'1px solid rgba(170,102,255,0.2)',
            borderRadius:12, padding:'1rem' }}>
            <div style={{ fontFamily:'monospace', fontSize:'0.55rem', color:'#aa66ff',
              letterSpacing:3, marginBottom:'0.75rem' }}>予測レンジ（翌週）</div>
            {[
              { label:'上限', value: predUpper, color:'#aa66ff' },
              { label:'中央値', value: predMid,  color:'var(--bright)' },
              { label:'下限', value: predLower, color:'#ff3355' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ display:'flex', justifyContent:'space-between',
                alignItems:'center', marginBottom:'0.4rem' }}>
                <span style={{ fontFamily:'monospace', fontSize:'0.62rem', color:'var(--muted)' }}>{label}</span>
                <span style={{ fontFamily:'monospace', fontSize:'0.85rem', fontWeight:700, color }}>${value.toFixed(2)}</span>
              </div>
            ))}
            <div style={{ fontFamily:'monospace', fontSize:'0.55rem', color:'var(--dim)', marginTop:'0.5rem',
              paddingTop:'0.5rem', borderTop:'1px solid rgba(255,255,255,0.06)' }}>
              レンジ幅: ${(predUpper - predLower).toFixed(2)} ({((predUpper - predLower) / price * 100).toFixed(1)}%)
            </div>
          </div>

          {/* エントリーゾーン */}
          <div style={{ background:'rgba(0,255,136,0.05)', border:'1px solid rgba(0,255,136,0.2)',
            borderRadius:12, padding:'1rem' }}>
            <div style={{ fontFamily:'monospace', fontSize:'0.55rem', color:'#00ff88',
              letterSpacing:3, marginBottom:'0.75rem' }}>エントリーゾーン</div>
            {[
              { label:'積極 (現在値)', value: entryAggressive, color:'var(--bright)' },
              { label:'理想 (押し目)', value: entryIdeal,      color:'#00ff88' },
              { label:'避けるライン', value: entryAvoid,       color:'#ffb800', suffix:' +' },
            ].map(({ label, value, color, suffix='' }) => (
              <div key={label} style={{ display:'flex', justifyContent:'space-between',
                alignItems:'center', marginBottom:'0.4rem' }}>
                <span style={{ fontFamily:'monospace', fontSize:'0.62rem', color:'var(--muted)' }}>{label}</span>
                <span style={{ fontFamily:'monospace', fontSize:'0.85rem', fontWeight:700, color }}>
                  ${value.toFixed(2)}{suffix}
                </span>
              </div>
            ))}
            <div style={{ fontFamily:'monospace', fontSize:'0.55rem', color:'rgba(255,51,85,0.7)',
              marginTop:'0.5rem', paddingTop:'0.5rem', borderTop:'1px solid rgba(255,255,255,0.06)' }}>
              STOP想定: ${(price - atr * 1.5).toFixed(2)} ({((-atr * 1.5) / price * 100).toFixed(1)}%)
            </div>
          </div>

          {/* 予測根拠 */}
          <div style={{ background:'rgba(255,255,255,0.02)', border:'1px solid rgba(255,255,255,0.06)',
            borderRadius:12, padding:'1rem' }}>
            <div style={{ fontFamily:'monospace', fontSize:'0.55rem', color:'var(--muted)',
              letterSpacing:3, marginBottom:'0.75rem' }}>予測根拠（加重平均）</div>
            {[
              { label:'ATRベース',  upper:atrUpper, lower:atrLower, weight:40, color:'#4499ff' },
              { label:'VCPパターン', upper:vcpUpper, lower:vcpLower, weight:35, color:'#aa66ff' },
              { label:'RS補正',    upper:rsUpper,  lower:rsLower,  weight:25, color:'#ffb800' },
            ].map(({ label, upper, lower, weight, color }) => (
              <div key={label} style={{ marginBottom:'0.5rem' }}>
                <div style={{ display:'flex', justifyContent:'space-between', marginBottom:'0.2rem' }}>
                  <span style={{ fontFamily:'monospace', fontSize:'0.6rem', color }}>{label}</span>
                  <span style={{ fontFamily:'monospace', fontSize:'0.55rem', color:'var(--dim)' }}>{weight}%</span>
                </div>
                <div style={{ display:'flex', gap:'0.75rem' }}>
                  <span style={{ fontFamily:'monospace', fontSize:'0.62rem', color:'#00ff88' }}>↑${upper.toFixed(0)}</span>
                  <span style={{ fontFamily:'monospace', fontSize:'0.62rem', color:'#ff3355' }}>↓${lower.toFixed(0)}</span>
                </div>
                {/* ウェイトバー */}
                <div style={{ height:2, background:'rgba(255,255,255,0.06)', borderRadius:2, marginTop:'0.3rem' }}>
                  <div style={{ height:'100%', width:`${weight}%`, background:color, borderRadius:2 }}/>
                </div>
              </div>
            ))}
          </div>

        </div>
      </div>

      {/* 免責 */}
      <div style={{ fontFamily:'monospace', fontSize:'0.55rem', color:'var(--dim)',
        marginTop:'1rem', lineHeight:1.6 }}>
        ※ ATR・VCP収縮率・RSバイアスの統計的推定値。保証なし。必ずリスク管理を。
      </div>
    </div>
  );
}

export default function RealtimePage() {
  const { ticker } = useParams();
  const navigate = useNavigate();
  const [quote, setQuote] = useState(null);
  const [data, setData] = useState(null);
  const [aiJudgment, setAiJudgment] = useState(null);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const intervalRef = useRef(null);

  // リアルタイム株価取得（10秒ごと）
  const fetchQuote = async () => {
    try {
      const resp = await fetch(`https://financialmodelingprep.com/stable/quote?symbol=${ticker}&apikey=${import.meta.env.VITE_FMP_API_KEY || 'demo'}`);
      const json = await resp.json();
      if (json && json[0]) {
        setQuote(json[0]);
      }
    } catch (e) {
      console.error('Quote fetch error:', e);
    }
  };

  // strategies.jsonから現在のスコア取得
  const fetchData = async () => {
    try {
      const resp = await fetch('/content/strategies.json');
      const json = await resp.json();
      
      // all_data配列から該当ティッカーを探す（全銘柄の詳細データ）
      const found = json.all_data?.find(t => t.ticker === ticker);
      
      if (found) {
        setData(found);
      } else {
        // フォールバック: ランキングから探す
        const allRankings = Object.values(json.rankings || {}).flat();
        const foundInRanking = allRankings.find(t => t.ticker === ticker);
        if (foundInRanking) {
          setData(foundInRanking);
        }
      }
    } catch (e) {
      console.error('Data fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  // AI判断取得（事前生成済みJSON）
  const fetchAiJudgment = async () => {
    try {
      const resp = await fetch(`/content/${ticker.toLowerCase()}_judgment.json`);
      if (resp.ok) {
        const json = await resp.json();
        setAiJudgment(json);
      }
    } catch {}
  };

  // AI判断を新規生成（バックエンドapi_judge.py実行）
  const runAiJudge = async () => {
    setAiLoading(true);
    try {
      // 実際にはバックエンドAPIを叩く
      // ここではダミー（フロントエンドからPython実行は不可）
      alert('AI判断はバックエンドで `python scripts/ai_judge.py ' + ticker + '` を実行してください');
      // 実装例: fetch('/api/ai-judge', { method: 'POST', body: JSON.stringify({ ticker }) })
    } finally {
      setAiLoading(false);
    }
  };

  useEffect(() => {
    fetchQuote();
    fetchData();
    fetchAiJudgment();

    // 10秒ごとにリアルタイム更新
    intervalRef.current = setInterval(fetchQuote, 10000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [ticker]);

  const currentPrice = quote?.price || data?.price || 0;
  const change = quote?.change || 0;
  const changePercent = quote?.changesPercentage || 0;

  return (
    <div className="min-h-screen bg-ink pb-20">
      
      {/* ヘッダー */}
      <div className="border-b border-border bg-panel px-4 py-3">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => navigate(-1)} className="p-1 text-muted hover:text-text transition">
              <ArrowLeft size={16} />
            </button>
            <div>
              <div className="font-mono text-bright text-lg font-bold">{ticker}</div>
              {data && <div className="text-muted text-xs">{data.name}</div>}
            </div>
          </div>
          <button onClick={fetchQuote} className="p-2 text-muted hover:text-green transition rounded-lg hover:bg-panel">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">

        {/* リアルタイム価格 */}
        <div className="bg-panel border border-border rounded-xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-muted font-mono text-xs mb-1">現在値 (リアルタイム)</div>
              <div className="font-mono text-3xl font-bold text-bright">{fmt(currentPrice)}</div>
              <div className={`font-mono text-sm flex items-center gap-2 mt-1 ${clr(change)}`}>
                {change >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {fmt(change)} ({pct(changePercent)})
              </div>
            </div>
            {quote && (
              <div className="text-right font-mono text-xs space-y-1">
                <div className="text-muted">前日終値</div>
                <div className="text-text font-bold">{fmt(quote.previousClose)}</div>
                <div className="text-muted mt-2">Day Range</div>
                <div className="flex items-center gap-2">
                  <span className="text-red">{fmt(quote.dayLow)}</span>
                  <span className="text-muted">-</span>
                  <span className="text-green">{fmt(quote.dayHigh)}</span>
                </div>
                <div className="text-muted mt-2">Open</div>
                <div className="text-text">{fmt(quote.open)}</div>
                <div className="text-muted mt-2">Volume</div>
                <div className="text-text">{(quote.volume / 1000000).toFixed(1)}M</div>
                {quote.avgVolume && (
                  <>
                    <div className="text-muted">Avg Volume</div>
                    <div className="text-dim">{(quote.avgVolume / 1000000).toFixed(1)}M</div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>



        {/* スコア表示 + レーダーチャート */}
        {data && (
          <div className="grid md:grid-cols-2 gap-6">
            <div className="bg-panel border border-border rounded-xl p-5">
              <ScoreRadarChart scores={data.scores} />
            </div>
            <div className="bg-panel border border-border rounded-xl p-5 space-y-3">
              <div className="text-muted font-mono text-xs">📊 Current Scores</div>
              <div className="grid grid-cols-2 gap-3">
                {[
                  ['VCP', data.scores.vcp, 105, 'text-green'],
                  ['RS', data.scores.rs, 99, 'text-blue'],
                  ['ECR', data.scores.ecr_rank, 100, 'text-amber'],
                  ['CANSLIM', data.scores.canslim, 100, 'text-purple'],
                  ['SES', data.scores.ses, 100, 'text-red'],
                  ['Composite', data.scores.composite, 100, 'text-bright'],
                ].map(([label, value, max, color]) => (
                  <div key={label} className="bg-ink rounded-lg p-3">
                    <div className="text-muted font-mono text-xs">{label}</div>
                    <div className={`font-mono text-lg font-bold ${color}`}>{value}/{max}</div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2 text-xs font-mono">
                <span className={data.status === 'ACTION' ? 'badge-action' : 'badge-wait'}>
                  {data.status}
                </span>
                <span className="bg-blue-dim text-blue border border-blue/30 px-2 py-0.5 rounded">
                  {data.ecr_phase}
                </span>
                <span className="bg-purple-dim text-purple border border-purple/30 px-2 py-0.5 rounded">
                  {data.canslim_grade}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* 詳細メトリクス（strategies.jsonのall_dataから取得） */}
        {data && (
          <div className="grid md:grid-cols-3 gap-6">
            
            {/* VCP詳細 */}
            {data.vcp_details && (
              <div className="bg-panel border border-border rounded-xl p-5 space-y-3">
                <div className="text-muted font-mono text-xs flex items-center gap-2">
                  <span className="text-green">●</span> VCP Details
                </div>
                <div className="space-y-2 text-xs font-mono">
                  <div className="flex justify-between">
                    <span className="text-muted">Score</span>
                    <span className="text-green font-bold">{data.vcp_details.score}/105</span>
                  </div>
                  {data.vcp_details.breakdown && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-muted">Tightness</span>
                        <span className="text-text">{data.vcp_details.breakdown.tight}/40</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Volume</span>
                        <span className="text-text">{data.vcp_details.breakdown.vol}/30</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">MA</span>
                        <span className="text-text">{data.vcp_details.breakdown.ma}/30</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Pivot</span>
                        <span className="text-text">{data.vcp_details.breakdown.pivot}/5</span>
                      </div>
                    </>
                  )}
                  {data.vcp_details.signals && data.vcp_details.signals.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-border/30">
                      <div className="text-muted mb-1">Signals:</div>
                      {data.vcp_details.signals.map((sig, i) => (
                        <div key={i} className="text-green text-[10px]">• {sig}</div>
                      ))}
                    </div>
                  )}
                  {data.atr_pct != null && (
                    <div className="flex justify-between text-[10px]">
                      <span className="text-muted">ATR</span>
                      <span className="text-text">{data.atr_pct}%</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* SES詳細 */}
            {data.ses_details && (
              <div className="bg-panel border border-border rounded-xl p-5 space-y-3">
                <div className="text-muted font-mono text-xs flex items-center gap-2">
                  <span className="text-red">●</span> SES Details
                </div>
                <div className="space-y-2 text-xs font-mono">
                  <div className="flex justify-between">
                    <span className="text-muted">Score</span>
                    <span className="text-red font-bold">{data.ses_details.score}/100</span>
                  </div>
                  {data.ses_details.breakdown && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-muted">Fractal Eff</span>
                        <span className="text-text">{data.ses_details.breakdown.fractal_efficiency}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">True Force</span>
                        <span className="text-text">{data.ses_details.breakdown.true_force}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Vol Squeeze</span>
                        <span className="text-text">{data.ses_details.breakdown.volatility_squeeze}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Bar Quality</span>
                        <span className="text-text">{data.ses_details.breakdown.bar_quality}</span>
                      </div>
                    </>
                  )}
                  {data.ses_details.metrics && (
                    <div className="mt-2 pt-2 border-t border-border/30 space-y-1 text-[10px]">
                      <div className="flex justify-between">
                        <span className="text-muted">ER</span>
                        <span className="text-text">{data.ses_details.metrics.er?.toFixed(3)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Force Ratio</span>
                        <span className="text-text">{data.ses_details.metrics.force_ratio?.toFixed(3)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Vol Contract</span>
                        <span className="text-text">{data.ses_details.metrics.vol_contraction?.toFixed(2)}</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* CANSLIM & Technical */}
            <div className="bg-panel border border-border rounded-xl p-5 space-y-3">
              <div className="text-muted font-mono text-xs flex items-center gap-2">
                <span className="text-purple">●</span> Technical & Fundamentals
              </div>
              <div className="space-y-2 text-xs font-mono">
                <div className="flex justify-between">
                  <span className="text-muted">Grade</span>
                  <span className="text-purple font-bold">{data.canslim_grade}</span>
                </div>
                {data.canslim_metrics && (
                  <>
                    {data.canslim_metrics.eps_growth != null && (
                      <div className="flex justify-between">
                        <span className="text-muted">EPS Growth</span>
                        <span className="text-text">{data.canslim_metrics.eps_growth.toFixed(1)}%</span>
                      </div>
                    )}
                    {data.canslim_metrics.rev_growth != null && (
                      <div className="flex justify-between">
                        <span className="text-muted">Rev Growth</span>
                        <span className="text-text">{data.canslim_metrics.rev_growth.toFixed(1)}%</span>
                      </div>
                    )}
                  </>
                )}
                <div className="mt-2 pt-2 border-t border-border/30 space-y-1">
                  {data.pivot_dist_pct != null && (
                    <div className="flex justify-between">
                      <span className="text-muted">Pivot Dist</span>
                      <span className={`${data.pivot_dist_pct > 0 ? 'text-red' : 'text-green'}`}>
                        {data.pivot_dist_pct > 0 ? '+' : ''}{data.pivot_dist_pct.toFixed(2)}%
                      </span>
                    </div>
                  )}
                  {data.ma50_ratio != null && (
                    <div className="flex justify-between">
                      <span className="text-muted">MA50</span>
                      <span className={`${data.ma50_ratio > 0 ? 'text-green' : 'text-red'}`}>
                        {data.ma50_ratio > 0 ? '+' : ''}{data.ma50_ratio.toFixed(1)}%
                      </span>
                    </div>
                  )}
                  {data.ma200_ratio != null && (
                    <div className="flex justify-between">
                      <span className="text-muted">MA200</span>
                      <span className={`${data.ma200_ratio > 0 ? 'text-green' : 'text-red'}`}>
                        {data.ma200_ratio > 0 ? '+' : ''}{data.ma200_ratio.toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>
                <div className="mt-2 pt-2 border-t border-border/30 space-y-1 text-[10px]">
                  {data.avg_volume != null && (
                    <div className="flex justify-between">
                      <span className="text-muted">Avg Vol</span>
                      <span className="text-text">{(data.avg_volume / 1000000).toFixed(1)}M</span>
                    </div>
                  )}
                  {data.market_cap != null && (
                    <div className="flex justify-between">
                      <span className="text-muted">Market Cap</span>
                      <span className="text-text">${(data.market_cap / 1e9).toFixed(1)}B</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

          </div>
        )}

        {/* スコア推移チャート */}
        <div className="bg-panel border border-border rounded-xl p-5">
          <ScoreHistoryChart ticker={ticker} />
        </div>

        {/* TradingViewチャート */}
        <div className="bg-panel border border-border rounded-xl overflow-hidden">
          <TradingViewWidget
            symbol={ticker}
            interval="D"
            height={500}
            theme="dark"
          />
        </div>

                {/* レンジ予測 */}
        {data && <RangePredict data={data} quote={quote} />}

                {/* ── ニュース（AI診断の上） ───────────────────── */}
        <NewsSection ticker={ticker} />


        {/* AI判断 */}
        <div className="bg-panel border border-border rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="font-mono text-xs text-muted flex items-center gap-2">
              <Brain size={14} className="text-green" /> AI Judgment
            </div>
            <button
              onClick={runAiJudge}
              disabled={aiLoading}
              className="flex items-center gap-2 bg-green text-ink font-mono text-xs font-bold px-3 py-1.5 rounded-lg hover:bg-green/90 transition disabled:opacity-50"
            >
              {aiLoading ? '分析中...' : '新規判定'}
            </button>
          </div>
          
          {aiJudgment ? (
            <div className="space-y-2">
              <div className={`font-mono text-lg font-bold ${
                aiJudgment.judgment.judgment === 'BUY' ? 'text-green' :
                aiJudgment.judgment.judgment === 'WAIT' ? 'text-amber' : 'text-red'
              }`}>
                {aiJudgment.judgment.judgment} (信頼度 {aiJudgment.judgment.confidence}%)
              </div>
              <div className="text-text text-sm">{aiJudgment.judgment.reasoning}</div>
            </div>
          ) : (
            <div className="text-muted text-sm">
              AI判断データなし。`python scripts/ai_judge.py {ticker}` を実行してください。
            </div>
          )}
        </div>

        {/* 外部リンク */}
        <div className="flex gap-3 text-xs font-mono">
          <a href={`https://finance.yahoo.com/quote/${ticker}`} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-dim hover:text-green transition">
            Yahoo <ExternalLink size={10} />
          </a>
          <a href={`https://www.tradingview.com/chart/?symbol=${ticker}`} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-dim hover:text-green transition">
            TradingView <ExternalLink size={10} />
          </a>
          <a href={`https://seekingalpha.com/symbol/${ticker}`} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-dim hover:text-green transition">
            Seeking Alpha <ExternalLink size={10} />
          </a>
          <a href={`https://finviz.com/quote.ashx?t=${ticker}`} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-dim hover:text-green transition">
            Finviz <ExternalLink size={10} />
          </a>
        </div>

      </div>
    </div>
  );
}