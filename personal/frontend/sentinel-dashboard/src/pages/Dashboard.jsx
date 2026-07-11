import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { 
  RefreshCw, Briefcase, ArrowRight, Newspaper, 
  Zap, TrendingUp, TrendingDown, Activity, Globe, Layers,
  Clock, ExternalLink
} from 'lucide-react';

const fmt   = (n, d=2) => n != null ? `$${Number(n).toFixed(d)}` : '—';
const pct   = (n)      => n != null ? `${n > 0 ? '+' : ''}${Number(n).toFixed(2)}%` : '—';
const clr   = (n)      => n > 0 ? '#00ff88' : n < 0 ? '#ff3355' : '#666';

// ── Glitch Text Effect ────────────────────────────────────
function GlitchText({ children, className = '' }) {
  return (
    <span className={`glitch ${className}`} data-text={children}>
      {children}
    </span>
  );
}

// ── Macro Environment Panel ───────────────────────────────────────
function MacroEnvironment() {
  const [macro, setMacro] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMacro = async () => {
    try {
      const apiKey = import.meta.env.VITE_FMP_API_KEY;
      // VIXY≒VIX×1倍、USO$105≒WTI$88（比率0.84）、TLT利回り逆算
      // 実価格: VIXY$25=VIX25, USO$105=WTI$88, TLT$89=利回り4.1%
      const symbols = ['VIXY', 'USO', 'TLT'];
      const results = await Promise.all(
        symbols.map(s =>
          fetch(`https://financialmodelingprep.com/stable/quote?symbol=${s}&apikey=${apiKey}`)
            .then(r => r.json()).then(d => d[0]).catch(() => null)
        )
      );
      const [vixy, uso, tlt] = results;

      // VIX近似: VIXY × 0.79（実測: VIXY$32.7 × 0.79 ≒ VIX25.9）
      const vix = vixy?.price ? (vixy.price * 0.79).toFixed(1) : null;
      // 原油WTI近似: USO × 0.84倍（実測: USO$105 × 0.84 ≒ WTI$88）
      const oil = uso?.price ? (uso.price * 0.84).toFixed(1) : null;
      // 10年債利回り近似: TLT$89 → 利回り4.1%（線形近似: yield = 12.0 - TLT×0.089）
      const bondYield = tlt?.price ? Math.max(2.0, (12.0 - tlt.price * 0.089)).toFixed(2) : null;
      const dxy = null;

      // SPY/QQQのトレンド判定
      const spyRes = await fetch(`https://financialmodelingprep.com/stable/quote?symbol=SPY&apikey=${apiKey}`).then(r => r.json()).catch(() => []);
      const spy = spyRes[0];
      const spyTrend = spy ? (spy.price > spy.priceAvg50 ? 'bull' : 'bear') : null;

      setMacro({ vix, oil, bondYield, dxy, spy, spyTrend });
    } catch (e) {
      console.error('Macro fetch error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchMacro(); const t = setInterval(fetchMacro, 60000); return () => clearInterval(t); }, []);

  if (loading || !macro) return null;

  // ── リスク判定ロジック ──
  const risks = [];
  const vixNum = parseFloat(macro.vix);
  const oilNum = parseFloat(macro.oil);
  const yieldNum = parseFloat(macro.bondYield);

  if (vixNum > 25)       risks.push('high');
  else if (vixNum > 20)  risks.push('mid');
  else                   risks.push('low');

  if (oilNum > 95)       risks.push('high');
  else if (oilNum > 80)  risks.push('mid');
  else                   risks.push('low');

  if (macro.spyTrend === 'bear') risks.push('high');
  else                           risks.push('low');

  if (yieldNum > 4.8)    risks.push('high');
  else if (yieldNum > 4.3) risks.push('mid');
  else                   risks.push('low');

  const highCount = risks.filter(r => r === 'high').length;
  const midCount  = risks.filter(r => r === 'mid').length;

  const overall = highCount >= 2 ? 'red' : (highCount === 1 || midCount >= 2) ? 'yellow' : 'green';

  const overallLabel = overall === 'red' ? '🔴 リスクオフ' : overall === 'yellow' ? '🟡 注意' : '🟢 リスクオン';
  const entryLabel   = overall === 'red' ? '新規エントリー非推奨' : overall === 'yellow' ? 'エントリーは慎重に' : 'エントリー可能';

  const riskColor = (r) => r === 'high' ? '#ff3355' : r === 'mid' ? '#ffb800' : '#00ff88';
  const riskLabel = (r) => r === 'high' ? '⚠️ 警戒' : r === 'mid' ? '→ 注意' : '✓ 正常';

  const items = [
    { label: '原油 WTI (近似)', value: `$${macro.oil}`, risk: risks[1] },
    { label: 'VIX 恐怖指数 (近似)', value: macro.vix, risk: risks[0] },
    { label: '10年債利回り (近似)', value: `${macro.bondYield}%`, risk: risks[3] },
    { label: 'SPY トレンド', value: macro.spyTrend === 'bull' ? '↑ MA50上' : '↓ MA50下', risk: risks[2] },
  ];

  return (
    <div style={{ background: '#0a0a0a', border: `1px solid ${overall === 'red' ? '#ff335533' : overall === 'yellow' ? '#ffb80033' : '#00ff8833'}`, borderRadius: 10, padding: 16, marginBottom: 16 }}>
      {/* ヘッダー */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ fontFamily: 'monospace', fontSize: 11, color: '#888', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: '#4499ff' }}>◈</span> MACRO ENVIRONMENT
        </div>
        <div style={{ fontFamily: 'monospace', fontSize: 12, fontWeight: 'bold', color: overall === 'red' ? '#ff3355' : overall === 'yellow' ? '#ffb800' : '#00ff88' }}>
          {overallLabel}
        </div>
      </div>

      {/* 指標グリッド */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 }}>
        {items.map((item, i) => (
          <div key={i} style={{ background: '#111', borderRadius: 6, padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontFamily: 'monospace', fontSize: 9, color: '#555', marginBottom: 2 }}>{item.label}</div>
              <div style={{ fontFamily: 'monospace', fontSize: 14, fontWeight: 'bold', color: '#ccc' }}>{item.value}</div>
            </div>
            <div style={{ fontFamily: 'monospace', fontSize: 10, color: riskColor(item.risk) }}>{riskLabel(item.risk)}</div>
          </div>
        ))}
      </div>

      {/* 総合判断 */}
      <div style={{ background: overall === 'red' ? '#ff335511' : overall === 'yellow' ? '#ffb80011' : '#00ff8811', borderRadius: 6, padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontFamily: 'monospace', fontSize: 11, color: '#666' }}>→ {entryLabel}</div>
        <div style={{ fontFamily: 'monospace', fontSize: 9, color: '#444' }}>60秒毎更新</div>
      </div>
    </div>
  );
}

// ── リアルタイム主要3指数（SPY, QQQ, IWM） ──────────────────────
function RealtimeIndices() {
  const [indices, setIndices] = useState([]);
  const [loading, setLoading] = useState(true);

  // シンボルを表示用の名前に変換する関数
  const getLabel = (symbol) => {
    const labels = {
      'SPY': 'S&P 500 (SPY)',
      'QQQ': 'Nasdaq 100 (QQQ)',
      'IWM': 'Russell 2000 (IWM)'
    };
    return labels[symbol] || symbol;
  };

  const fetchIndices = async () => {
    try {
      const apiKey = import.meta.env.VITE_FMP_API_KEY;
      const symbols = ['SPY', 'QQQ', 'IWM'];
      
      // 修正: 複数指定だと空配列になる仕様を回避するため、個別にFetchして結合します
      const fetchPromises = symbols.map(sym => 
        fetch(`https://financialmodelingprep.com/stable/quote?symbol=${sym}&apikey=${apiKey}`)
          .then(res => {
            if (!res.ok) throw new Error(`HTTP error! status: ${res.status} for ${sym}`);
            return res.json();
          })
      );
      
      // 3つのリクエストを同時に実行して待つ
      const results = await Promise.all(fetchPromises);
      
      // [[{SPYのデータ}], [{QQQのデータ}], [{IWMのデータ}]] を1つの配列に平坦化する
      const dataList = results.flat();
      
      // デバッグ用
      console.log("FMP APIからの取得データ(個別取得・結合後):", dataList);
      
      // APIキー無効エラーなどの場合
      const errorObj = dataList.find(d => d && d["Error Message"]);
      if (errorObj) {
        throw new Error(`API Error: ${errorObj["Error Message"]}`);
      }
      
      if (Array.isArray(dataList) && dataList.length > 0) {
        const order = { 'SPY': 1, 'QQQ': 2, 'IWM': 3 };
        
        // APIからの返り値（changePercentage）をUI表示用の変数名（changesPercentage）に吸収する
        const normalizedList = dataList.map(item => ({
          ...item,
          changesPercentage: item.changePercentage !== undefined ? item.changePercentage : item.changesPercentage
        }));

        const sorted = normalizedList.sort((a, b) => (order[a.symbol] || 99) - (order[b.symbol] || 99));
        setIndices(sorted);
      } else {
        throw new Error('API response is not an array or is empty');
      }
    } catch (error) {
      console.warn("Failed to fetch index data, using demo data", error);
      // エラー時はデモデータを表示（表示が壊れるのを防ぐ）
      setIndices([
        { symbol: 'SPY', price: 506.23, change: 4.12, changesPercentage: 0.82 },
        { symbol: 'QQQ', price: 435.50, change: 6.30, changesPercentage: 1.45 },
        { symbol: 'IWM', price: 202.10, change: -1.05, changesPercentage: -0.52 }
      ]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIndices();
    const interval = setInterval(fetchIndices, 60000); // 1分更新
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
      {indices.map(idx => {
        const isPos = idx.change >= 0;
        const color = isPos ? '#00ff88' : '#ff3355';
        const Icon = isPos ? TrendingUp : TrendingDown;

        return (
          <div 
            key={idx.symbol} 
            className="card" 
            style={{ 
              flex: '1 1 200px', 
              borderTop: `2px solid ${color}`,
              background: `linear-gradient(180deg, ${color}10 0%, rgba(0,0,0,0) 60%)`,
              margin: 0
            }}
          >
            <div className="card-header" style={{ color: '#aaa', fontSize: '0.75rem', marginBottom: '8px', borderBottom: 'none', paddingBottom: 0 }}>
              <Globe size={12} style={{ marginRight: '4px' }} />
              {getLabel(idx.symbol)}
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', padding: '0 1rem 1rem' }}>
              <span style={{ fontSize: '1.5rem', fontWeight: 'bold', color: '#fff' }}>
                ${idx.price?.toFixed(2)}
              </span>
              <span style={{ 
                color: color, 
                fontSize: '0.9rem', 
                fontWeight: 'bold',
                display: 'flex', 
                alignItems: 'center',
                backgroundColor: `${color}15`,
                padding: '2px 6px',
                borderRadius: '4px'
              }}>
                <Icon size={14} style={{ marginRight: '4px' }} />
                {isPos ? '+' : ''}{idx.change?.toFixed(2)} ({isPos ? '+' : ''}{idx.changesPercentage?.toFixed(2)}%)
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── セクターヒートマップ (TOP5銘柄表示付き) ───────────────────────
function SectorHeatmap({ allStocks }) {
  const sectorData = useMemo(() => {
    if (!allStocks || allStocks.length === 0) return [];

    const grouped = {};
    allStocks.forEach(stock => {
      const sector = stock.sector || 'Unknown';
      if (!grouped[sector]) {
        grouped[sector] = { total: 0, action: 0, avgRS: 0, topStocks: [] };
      }
      grouped[sector].total += 1;
      grouped[sector].avgRS += stock.scores?.rs || 0;
      
      if (stock.status === 'ACTION') {
        grouped[sector].action += 1;
        grouped[sector].topStocks.push(stock);
      }
    });

    return Object.entries(grouped)
      .map(([name, stats]) => {
        // セクター内の最強銘柄TOP5を抽出 (Compositeスコア順)
        const sortedTop = stats.topStocks
          .sort((a, b) => (b.scores?.composite || 0) - (a.scores?.composite || 0))
          .slice(0, 5);
          
        return {
          name,
          total: stats.total,
          actionCount: stats.action,
          actionRate: (stats.action / stats.total) * 100,
          avgRS: stats.avgRS / stats.total,
          topTickers: sortedTop.map(s => s.ticker)
        };
      })
      .sort((a, b) => b.actionRate - a.actionRate || b.avgRS - a.avgRS);
  }, [allStocks]);

  const getHeatColor = (rate) => {
    if (rate >= 75) return '#00ff88'; // 超強気
    if (rate >= 50) return '#00aa55'; // 強気
    if (rate >= 25) return '#444444'; // ニュートラル
    return '#ff3355';                 // 弱気
  };

  if (sectorData.length === 0) return null;

  return (
    <div className="card">
      <div className="card-header" style={{ marginBottom: '1rem' }}>
        <span className="label-tag"><Layers size={13} /> SECTOR HEATMAP & TOP LEADERS</span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', padding: '0 1rem 1rem' }}>
        {sectorData.map((sec, idx) => {
          const color = getHeatColor(sec.actionRate);
          return (
            <div 
              key={sec.name} 
              style={{
                flex: '1 1 calc(25% - 8px)',
                minWidth: '160px',
                backgroundColor: `${color}15`,
                borderLeft: `3px solid ${color}`,
                padding: '10px',
                borderRadius: '4px',
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
                position: 'relative'
              }}
            >
              {/* Top 3 Badge */}
              {idx < 3 && <div style={{ position: 'absolute', top: -8, right: -8, fontSize: '1rem' }}>🔥</div>}
              
              <div style={{ fontSize: '0.75rem', color: '#ccc', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 700 }}>
                {sec.name}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                <span style={{ fontSize: '1.25rem', fontWeight: 'bold', color: color }}>
                  {sec.actionRate.toFixed(0)}%
                </span>
                <span style={{ fontSize: '0.65rem', color: '#888' }}>
                  ({sec.actionCount}/{sec.total})
                </span>
              </div>
              
              {/* TOP 5 Tickers */}
              {sec.topTickers.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '6px' }}>
                  {sec.topTickers.map(t => (
                    <span 
                      key={t} 
                      style={{ 
                        fontSize: '0.65rem', 
                        background: `${color}30`, 
                        color: color,
                        padding: '2px 5px', 
                        borderRadius: '3px',
                        fontWeight: 'bold'
                      }}
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── ニュース判定 ────────────────────────────────────────── */
const SENT_POS_WORDS = ['beat','upgrade','outperform','strong buy','growth','surge','bullish','rally','breakout','profit'];
const SENT_NEG_WORDS = ['miss','downgrade','underperform','weak','decline','drops','bearish','loss','warning','cut'];

function detectSentiment(title) {
  const lower = title.toLowerCase();
  const pos = SENT_POS_WORDS.filter(w => lower.includes(w)).length;
  const neg = SENT_NEG_WORDS.filter(w => lower.includes(w)).length;
  return pos > neg ? 'pos' : neg > pos ? 'neg' : 'neu';
}

function relativeTime(dateStr) {
  try {
    const diffH = (Date.now() - new Date(dateStr).getTime()) / 3600000;
    return diffH < 1 ? `${Math.round(diffH * 60)}m` : diffH < 24 ? `${Math.round(diffH)}h` : `${Math.round(diffH / 24)}d`;
  } catch { return ''; }
}

async function fetchGoogleNews(topic) {
  if (!topic) return [];

  // 1. 'MARKET' が渡された場合は市場全体、それ以外は個別銘柄としてクエリを構成
  // 'when:1d' を追加することで過去24時間のニュースに限定
  const baseQuery = topic === 'MARKET' ? 'US Stock Market' : `${topic} stock`;
  const fullQuery = `${baseQuery} when:1d`;
  // 1. スペースを '+' に置換してエンコードの重複を避ける（Googleニュースは+を解釈できる）
  const encodedQuery = encodeURIComponent(fullQuery).replace(/%20/g, '+');
  const rssUrl = `https://news.google.com/rss/search?q=${encodedQuery}&hl=en-US&gl=US&ceid=US:en`;

  try {
    // 2. rss2jsonへのリクエスト。&count=5 はURLに含めず、後でJS側でsliceするほうが安定します。
    // 3. テンプレートリテラル内で直接 encodeURIComponent を1回だけかける
    const res = await fetch(`https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(rssUrl)}`);
    
    if (!res.ok) return []; // 422エラーなどの場合は空配列を返す

    const json = await res.json();
    
    if (json.status !== 'ok' || !json.items) return [];

    // 5件に絞り込んで整形
    return json.items.slice(0, 5).map(item => ({
      title: item.title.replace(/ - [^-]{2,50}$/, '').trim(),
      link: item.link,
      source: item.author || (item.link ? new URL(item.link).hostname.replace('www.', '') : 'News'),
      relTime: relativeTime(item.pubDate),
      sentiment: detectSentiment(item.title)
    }));
  } catch (error) {
    console.error("News fetch failed:", error);
    return [];
  }
}

/* ── Components ────────────────────────────────────────── */

function NewsSection({ query }) {
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchGoogleNews(query).then(items => { setNews(items); setLoading(false); });
  }, [query]);

  const colors = { pos: '#00ff88', neg: '#ff3355', neu: '#666' };
  const labels = { pos: '▲', neg: '▼', neu: '—' };

  return (
    <div className="card">
      <div className="card-header">
        <span className="label-tag"><Newspaper size={13} /> MARKET NEWS: {query}</span>
      </div>
      {loading ? <div style={{padding:'20px', textAlign:'center', color:'#555'}}>Loading News...</div> : (
        <div className="news-list">
          {news.map((n, i) => (
            <a key={i} href={n.link} target="_blank" rel="noopener noreferrer" className="news-item">
              <div className="news-sentiment" style={{ color: colors[n.sentiment] }}>{labels[n.sentiment]}</div>
              <div className="news-body">
                <div className="news-title">{n.title}</div>
                <div className="news-meta">
                  <span className="news-source">{n.source}</span>
                  <span className="news-time"><Clock size={9} /> {n.relTime}</span>
                </div>
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Score Bar ─────────────────────────────────────────────
function ScoreBar({ label, value, max = 105, color = '#00ff88' }) {
  const w = Math.min(Math.round((value / max) * 100), 100);
  return (
    <div className="score-row">
      <span className="score-label">{label}</span>
      <div className="score-track">
        <div className="score-fill" style={{ width: `${w}%`, background: color }} />
      </div>
      <span className="score-num">{value}</span>
    </div>
  );
}

// ── News Badge ────────────────────────────────────────────
function NewsBadge({ news }) {
  if (!news) return null;
  const color = news.label === 'Bullish' ? '#00ff88' : news.label === 'Bearish' ? '#ff3355' : '#ffb800';
  return (
    <span className="news-badge" style={{ color, borderColor: color + '40' }}>
      {news.label} {news.score?.toFixed(0)}
    </span>
  );
}

// ── Action Row (Desktop) ──────────────────────────────────
function ActionRow({ t, idx }) {
  const [expanded, setExpanded] = useState(false);
  const rr = t._stop && t._entry
    ? ((t._target - t._entry) / (t._entry - t._stop)).toFixed(1)
    : null;

  return (
    <>
      <div className="action-row" onClick={() => setExpanded(v => !v)}>
        <div className="ar-idx">{String(idx + 1).padStart(2, '0')}</div>
        <div className="ar-ticker">
          <Link to={`/realtime/${t.ticker}`} className="ticker-link" onClick={e => e.stopPropagation()}>
            {t.ticker}
          </Link>
          <span className="ar-name">{t.name}</span>
        </div>
        <div className="ar-price">
          <span className="price-val">{fmt(t._price || t.price)}</span>
          <span className="sector-tag">{t.sector?.split(' ')[0]}</span>
        </div>
        <div className="ar-levels">
          <span className="entry">E {fmt(t._entry || t.pivot)}</span>
          <span className="stop">S {fmt(t._stop)}</span>
          <span className="target">T {fmt(t._target)}</span>
          {rr && <span className="rr">RR 1:{rr}</span>}
        </div>
        <div className="ar-scores">
          <ScoreBar label="VCP" value={t.scores?.vcp || t.vcp} max={105} color="#00ff88" />
          <ScoreBar label="RS " value={t.scores?.rs || t.rs} max={99}  color="#4499ff" />
          <ScoreBar label="CS " value={t.scores?.canslim || t.canslim_score || 0} max={100} color="#aa66ff" />
        </div>
        <div className="ar-extra">
          <NewsBadge news={t.news_summary} />
          <span className="composite-val">{(t.scores?.composite || t.composite)?.toFixed(1)}</span>
        </div>
      </div>
      {expanded && t.news_summary?.headlines?.length > 0 && (
        <div className="news-expand">
          <Newspaper size={11} />
          {t.news_summary.headlines.map((h, i) => (
            <div key={i} className="headline">{h}</div>
          ))}
        </div>
      )}
    </>
  );
}

// ── Action Card (Mobile) ──────────────────────────────────
function ActionCard({ t }) {
  const rr = t._stop && t._entry
    ? ((t._target - t._entry) / (t._entry - t._stop)).toFixed(1)
    : null;

  return (
    <Link to={`/realtime/${t.ticker}`} className="action-card">
      <div className="ac-top">
        <div>
          <div className="ac-ticker">{t.ticker}</div>
          <div className="ac-name">{t.name}</div>
        </div>
        <div className="ac-right">
          <div className="ac-price">{fmt(t._price || t.price)}</div>
          <NewsBadge news={t.news_summary} />
        </div>
      </div>
      <div className="ac-levels">
        <span className="entry">E {fmt(t._entry || t.pivot)}</span>
        <span className="stop">S {fmt(t._stop)}</span>
        <span className="target">T {fmt(t._target)}</span>
        {rr && <span className="rr">1:{rr}</span>}
      </div>
      <div className="ac-scores-row">
        <div className="mini-score green">VCP<br/><strong>{t.scores?.vcp || t.vcp}</strong></div>
        <div className="mini-score blue">RS<br/><strong>{t.scores?.rs || t.rs}</strong></div>
        <div className="mini-score purple">COMP<br/><strong>{(t.scores?.composite || t.composite)?.toFixed(1)}</strong></div>
        <div className="mini-score white">CS<br/><strong>{t.scores?.canslim || t.canslim_score}</strong></div>
      </div>
    </Link>
  );
}

// ── Main Dashboard ────────────────────────────────────────
export default function Dashboard() {
  const [daily,  setDaily]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,  setError]   = useState(null);
  const [showAll, setShowAll] = useState(false);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const idx = await fetch('/content/index.json').then(r => r.json());
      const latest = idx.articles?.sort((a,b) => b.date.localeCompare(a.date))[0];
      if (!latest) throw new Error('No articles found');
      const d = await fetch(`/content/${latest.slug}.json`).then(r => r.json());
      setDaily(d);
    } catch(e) { 
      setError(e.message); 
    } finally { 
      setLoading(false); 
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div className="loading-screen">
      <div className="loading-bar"><div className="loading-fill" /></div>
      <div className="loading-text">SCANNING MARKETS...</div>
    </div>
  );
  if (error) return <div className="error-state">⚠ {error}</div>;

  const actions = daily?.data?.actions || [];
  const waits = daily?.data?.waits || [];
  const allStocks = [...actions, ...waits]; // ヒートマップ用の全銘柄
  const visible = showAll ? actions : actions.slice(0, 20);

  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dash-header">
        <div>
          <h1 className="report-date">
            <GlitchText>{daily?.date} REPORT</GlitchText>
          </h1>
          <div className="report-sub">
            <span className="badge-action-count"><Zap size={11} /> ACTION <strong>{actions.length}</strong></span>
            <span className="badge-wait-count"><Activity size={11} /> WAIT <strong>{waits.length}</strong></span>
          </div>
        </div>
        <button onClick={load} className="refresh-btn"><RefreshCw size={15} /></button>
      </div>

      {/* マクロ環境パネル */}
      <MacroEnvironment />

      {/* リアルタイム主要3指数 */}
      <RealtimeIndices />


      {/* セクターヒートマップ (アクション率 & TOP 5銘柄) */}
      <SectorHeatmap allStocks={allStocks} />

      {/* Actions Table */}
      <div className="card">
        <div className="card-header">
          <span className="label-tag"><Zap size={11} /> ACTION — CLICK ROW FOR NEWS</span>
          <span className="count-badge">{actions.length} stocks</span>
        </div>

        {/* Mobile cards */}
        <div className="mobile-cards">
          {visible.map(t => <ActionCard key={t.ticker} t={t} />)}
        </div>

        {/* Desktop table */}
        <div className="desktop-table">
          <div className="table-header">
            <div>#</div>
            <div>TICKER</div>
            <div>PRICE</div>
            <div>LEVELS</div>
            <div>SCORES</div>
            <div>NEWS / COMP</div>
          </div>
          {visible.map((t, i) => <ActionRow key={t.ticker} t={t} idx={i} />)}
        </div>

        {!showAll && actions.length > 20 && (
          <button onClick={() => setShowAll(true)} className="show-more">
            ↓ SHOW {actions.length - 20} MORE
          </button>
        )}
      </div>

      {/* ── Market News Section ── */}
      <NewsSection query="US Stock Market" />


      {/* AI Analysis */}
      {daily?.ja?.body && (
        <div className="card ai-card">
          <div className="card-header">
            <span className="label-tag">AI ANALYSIS</span>
          </div>
          <div className="ai-body">
            {daily.ja.body.replace(/##[^\n]*/g, '').replace(/\*\*/g, '').trim()}
          </div>
        </div>
      )}
    </div>
  );
}