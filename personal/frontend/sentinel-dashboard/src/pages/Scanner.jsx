import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Search, SlidersHorizontal, Diamond, ShieldCheck, RotateCcw, Terminal, BarChart2, Calendar, Clock, X, TrendingUp, TrendingDown } from 'lucide-react';

const monoStyle = { fontFamily: 'Consolas, "Courier New", monospace' };

const ECR_COLORS = {
  'IGNITION':   { bg: '#00ff8815', border: '#00ff88', text: '#00ff88' },
  'HOLD/WATCH': { bg: '#00aaff15', border: '#00aaff', text: '#00aaff' },
  'WATCH':      { bg: '#ffb80015', border: '#ffb800', text: '#ffb800' },
  'REJECTED':   { bg: '#ff335515', border: '#ff3355', text: '#ff3355' },
};
const CANSLIM_COLORS = {
  A:'#00ff88','A-':'#00ff88','A+':'#00ff88',
  B:'#00aaff','B-':'#00aaff','B+':'#00aaff',
  C:'#ffb800','C-':'#ffb800','C+':'#ffb800',
  D:'#ff3355',F:'#ff3355',Z:'#444'
};

/* ══════════════════════════════════════════════════════════
   EARNINGS — 2週間ウィンドウスライド方式
   ══════════════════════════════════════════════════════════ */
const earningsCache = {};
const earningsFetching = {};
const windowCache = {};

function fetchWindow(from, to, apiKey) {
  const key = `${from}_${to}`;
  if (windowCache[key]) return windowCache[key];
  windowCache[key] = fetch(
    `https://financialmodelingprep.com/stable/earnings-calendar?from=${from}&to=${to}&apikey=${apiKey}`
  ).then(r => r.json()).then(j => Array.isArray(j) ? j : []).catch(() => []);
  return windowCache[key];
}

function fetchEarningsForTicker(ticker) {
  if (earningsCache[ticker] !== undefined) return Promise.resolve(earningsCache[ticker]);
  if (earningsFetching[ticker]) return earningsFetching[ticker];
  const apiKey = import.meta.env.VITE_FMP_API_KEY;
  const today = new Date(); today.setHours(0,0,0,0);
  const windows = Array.from({length:6},(_,i) => ({
    from: new Date(today.getTime()+i*14*86400000).toISOString().split('T')[0],
    to:   new Date(today.getTime()+(i+1)*14*86400000).toISOString().split('T')[0],
  }));
  const searchNext = (idx) => {
    if (idx >= windows.length) { earningsCache[ticker]=null; delete earningsFetching[ticker]; return Promise.resolve(null); }
    const {from,to} = windows[idx];
    return fetchWindow(from,to,apiKey).then(list => {
      const hit = list.find(e => e.symbol===ticker);
      if (hit) { earningsCache[ticker]=hit.date; delete earningsFetching[ticker]; return hit.date; }
      return searchNext(idx+1);
    }).catch(()=>searchNext(idx+1));
  };
  earningsFetching[ticker] = searchNext(0);
  return earningsFetching[ticker];
}

function daysUntil(d) {
  if (!d) return null;
  const t=new Date(); t.setHours(0,0,0,0);
  const u=new Date(d); u.setHours(0,0,0,0);
  return Math.round((u-t)/86400000);
}
function getEarningsSignal(days) {
  if (days===null) return null;
  if (days<0)   return {type:'PASSED', color:'#555',    bg:'#ffffff06',label:`決算済(${Math.abs(days)}日前)`};
  if (days===0) return {type:'TODAY',  color:'#ff3355', bg:'#ff335520',label:'本日決算！'};
  if (days<=3)  return {type:'DANGER', color:'#ff3355', bg:'#ff335515',label:`決算まで${days}日`};
  if (days<=7)  return {type:'WARNING',color:'#ffb800', bg:'#ffb80012',label:`決算まで${days}日`};
  if (days<=14) return {type:'WATCH',  color:'#ffb80077',bg:'transparent',label:`決算まで${days}日`};
  return             {type:'SAFE',   color:'#444',    bg:'transparent',label:`決算まで${days}日`};
}

function useEarningsDate(ticker) {
  const [,forceUpdate] = useState(0);
  useEffect(() => {
    if (!ticker||earningsCache[ticker]!==undefined) return;
    fetchEarningsForTicker(ticker).then(()=>forceUpdate(n=>n+1));
  },[ticker]);
  if (earningsCache[ticker]===undefined) return undefined;
  const date=earningsCache[ticker], days=daysUntil(date);
  return {date,days,signal:getEarningsSignal(days)};
}

/* ══════════════════════════════════════════════════════════
   REALTIME ALERT PANEL — 出来高急増・急騰急落監視
   ══════════════════════════════════════════════════════════ */

// 監視対象銘柄のquoteを一括取得（30秒ごと更新）
const quoteCache = { data: {}, ts: 0, promise: null };

function fetchQuotes(tickers, apiKey) {
  const now = Date.now();
  if (now - quoteCache.ts < 30000 && Object.keys(quoteCache.data).length > 0) {
    return Promise.resolve(quoteCache.data);
  }
  if (quoteCache.promise) return quoteCache.promise;
  const syms = tickers.slice(0, 50).join(','); // 上位50銘柄
  quoteCache.promise = fetch(
    `https://financialmodelingprep.com/stable/quote?symbol=${syms}&apikey=${apiKey}`
  ).then(r => r.json()).then(json => {
    const list = Array.isArray(json) ? json : [];
    const map = {};
    list.forEach(q => { map[q.symbol] = q; });
    quoteCache.data = map;
    quoteCache.ts = Date.now();
    quoteCache.promise = null;
    return map;
  }).catch(() => { quoteCache.promise = null; return quoteCache.data; });
  return quoteCache.promise;
}

/* ══════════════════════════════════════════════════════════
   MARKET MONITOR — gainers/losers/actives × Sentinel照合
   ══════════════════════════════════════════════════════════ */

// ブラウザ通知の許可を取得
async function requestNotificationPermission() {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {
    await Notification.requestPermission();
  }
}

function sendNotification(title, body, tag) {
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification(title, { body, tag, icon: '/favicon.ico', silent: false });
  }
}

// 既に通知済みの銘柄を記録（セッション中重複通知防止）
const notifiedSet = new Set();

function useMarketMonitor(sentinelMap) {
  const [alerts, setAlerts]       = useState([]);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [loading, setLoading]     = useState(false);

  const refresh = () => {
    if (!Object.keys(sentinelMap).length) return;
    setLoading(true);
    const apiKey = import.meta.env.VITE_FMP_API_KEY;

    // gainers / losers / actives を並列取得
    Promise.all([
      fetch(`https://financialmodelingprep.com/stable/biggest-gainers?apikey=${apiKey}`).then(r=>r.json()).catch(()=>[]),
      fetch(`https://financialmodelingprep.com/stable/biggest-losers?apikey=${apiKey}`).then(r=>r.json()).catch(()=>[]),
      fetch(`https://financialmodelingprep.com/stable/most-actives?apikey=${apiKey}`).then(r=>r.json()).catch(()=>[]),
    ]).then(([gainers, losers, actives]) => {

      const found = [];
      const seen  = new Set();

      const process = (list, sourceType) => {
        const arr = Array.isArray(list) ? list : (list?.data ?? []);
        arr.forEach(q => {
          const sym = q.symbol ?? q.ticker;
          if (!sym || seen.has(sym)) return;
          const sentinel = sentinelMap[sym];
          if (!sentinel) return; // Sentinelにない銘柄は無視
          seen.add(sym);

          const chg = q.changesPercentage ?? q.changePercentage ?? 0;
          const vol = q.volume;
          const avgVol = sentinel.avg_volume;
          const volRatio = (vol && avgVol) ? vol / avgVol : null;
          const comp = sentinel.scores?.composite ?? 0;
          const eps  = sentinel.canslim_metrics?.eps_growth;

          let type, label, color, priority;
          if (sourceType === 'gainers') {
            type='SURGE'; label=`▲${Math.abs(chg).toFixed(1)}%`; color='#00ff88'; priority=Math.abs(chg)+100;
          } else if (sourceType === 'losers') {
            type='DROP';  label=`▼${Math.abs(chg).toFixed(1)}%`; color='#ff3355'; priority=Math.abs(chg)+100;
          } else {
            type='VOL';   label=`⚡${volRatio ? volRatio.toFixed(1)+'x' : '急増'}`; color='#ffb800'; priority=(volRatio??2)+50;
          }

          found.push({ sym, type, label, color, priority, price: q.price, chg, volRatio, comp, eps,
            status: sentinel.status, ecr_phase: sentinel.ecr_phase, name: sentinel.name });

          // 通知（未通知 & 重要銘柄のみ）
          const notifyKey = `${sym}_${type}_${new Date().toDateString()}`;
          if (!notifiedSet.has(notifyKey)) {
            notifiedSet.add(notifyKey);
            const isHighScore = comp >= 60;
            const isLowScore  = comp < 30;
            const title = isHighScore
              ? `🚨 [Sentinel] ${sym} ${label}`
              : isLowScore
              ? `⚠ [Sentinel] ${sym} ${label} (低スコア注意)`
              : `📊 [Sentinel] ${sym} ${label}`;
            const body = [
              `${type} | スコア: ${comp.toFixed(0)}`,
              eps != null ? `EPS成長: ${eps > 0 ? '+' : ''}${eps.toFixed(0)}%` : null,
              sentinel.status === 'ACTION' ? '✅ ACTION銘柄' : null,
            ].filter(Boolean).join(' | ');
            sendNotification(title, body, notifyKey);
          }
        });
      };

      process(gainers, 'gainers');
      process(losers,  'losers');
      process(actives, 'actives');

      // 優先度順
      found.sort((a, b) => b.priority - a.priority);
      setAlerts(found);
      setLastUpdate(new Date());
      setLoading(false);
    });
  };

  useEffect(() => {
    if (!Object.keys(sentinelMap).length) return;
    refresh();
    const id = setInterval(refresh, 60000); // 60秒ごと
    return () => clearInterval(id);
  }, []); // マウント時のみ（sentinelMapは安定）

  return { alerts, lastUpdate, loading, refresh };
}

function RealtimeAlertPanel({ allItems }) {
  const [open, setOpen] = useState(true); // デフォルト展開

  // ticker → sentinel data のマップ（メモ化）
  const sentinelMap = useMemo(() => {
    const m = {};
    allItems.forEach(t => { m[t.ticker] = t; });
    return m;
  }, [allItems]);

  const { alerts, lastUpdate, loading, refresh } = useMarketMonitor(sentinelMap);

  // カテゴリ別カウント
  const surgeCnt  = alerts.filter(a => a.type === 'SURGE').length;
  const dropCnt   = alerts.filter(a => a.type === 'DROP').length;
  const volCnt    = alerts.filter(a => a.type === 'VOL').length;
  const actionHit = alerts.filter(a => a.status === 'ACTION').length;

  return (
    <div style={{ marginBottom: 16 }}>
      {/* ヘッダーボタン */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <button onClick={() => { setOpen(v => !v); requestNotificationPermission(); }} style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: open ? '#0a0a0a' : '#ffffff08',
          border: `1px solid ${actionHit > 0 ? '#ff3355' : '#333'}`,
          color: actionHit > 0 ? '#ff3355' : '#aaa',
          padding: '7px 14px', borderRadius: 4, cursor: 'pointer', ...monoStyle, fontSize: 11,
          animation: actionHit > 0 ? 'earn-pulse 2s ease infinite' : 'none',
        }}>
          ⚡ MARKET_MONITOR {open ? '▲' : '▼'}
        </button>
        {/* サマリーバッジ */}
        {alerts.length > 0 && (
          <div style={{ display: 'flex', gap: 6 }}>
            {surgeCnt > 0 && <span style={{ ...monoStyle, fontSize: 10, color: '#00ff88', background: '#00ff8815', border: '1px solid #00ff8830', padding: '3px 8px', borderRadius: 3 }}>▲ SURGE {surgeCnt}</span>}
            {dropCnt  > 0 && <span style={{ ...monoStyle, fontSize: 10, color: '#ff3355', background: '#ff335515', border: '1px solid #ff335530', padding: '3px 8px', borderRadius: 3 }}>▼ DROP {dropCnt}</span>}
            {volCnt   > 0 && <span style={{ ...monoStyle, fontSize: 10, color: '#ffb800', background: '#ffb80015', border: '1px solid #ffb80030', padding: '3px 8px', borderRadius: 3 }}>⚡ VOL {volCnt}</span>}
            {actionHit > 0 && <span style={{ ...monoStyle, fontSize: 10, color: '#fff', background: '#ff335520', border: '1px solid #ff335550', padding: '3px 8px', borderRadius: 3, fontWeight: 'bold' }}>🚨 ACTION {actionHit}件</span>}
          </div>
        )}
        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {lastUpdate && <span style={{ ...monoStyle, fontSize: 9, color: '#333' }}>{lastUpdate.toLocaleTimeString('ja-JP')}</span>}
          <button onClick={refresh} disabled={loading} style={{ background: '#0a0a0a', border: '1px solid #222', color: loading ? '#333' : '#00aaff', padding: '4px 10px', borderRadius: 3, cursor: loading ? 'not-allowed' : 'pointer', ...monoStyle, fontSize: 9 }}>
            {loading ? '取得中...' : '↻'}
          </button>
        </div>
      </div>

      {open && (
        <div style={{ marginTop: 8, background: '#050505', border: '1px solid #1a1a1a', borderRadius: 4, padding: 16 }}>
          <div style={{ ...monoStyle, fontSize: 9, color: '#444', marginBottom: 12 }}>
            [SYS] 全市場 gainers/losers/actives Top50 × Sentinel600銘柄照合 | 60秒自動更新
          </div>

          {alerts.length === 0 ? (
            <div style={{ ...monoStyle, fontSize: 11, color: '#333', textAlign: 'center', padding: '16px 0' }}>
              {loading ? '市場データ取得中...' : '該当銘柄なし'}
            </div>
          ) : (
            <>
              {/* ACTION銘柄のみ先頭に強調表示 */}
              {actionHit > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{ ...monoStyle, fontSize: 9, color: '#ff3355', marginBottom: 6 }}>🚨 ACTION銘柄がランクイン</div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 6 }}>
                    {alerts.filter(a => a.status === 'ACTION').map((a, i) => (
                      <AlertCard key={i} a={a} highlight />
                    ))}
                  </div>
                  <div style={{ borderTop: '1px solid #1a1a1a', margin: '12px 0' }}/>
                </div>
              )}

              {/* その他の銘柄 */}
              <div style={{ ...monoStyle, fontSize: 9, color: '#444', marginBottom: 6 }}>
                その他 Sentinel銘柄（スコア順）
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(155px, 1fr))', gap: 5 }}>
                {alerts.filter(a => a.status !== 'ACTION').map((a, i) => (
                  <AlertCard key={i} a={a} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function AlertCard({ a, highlight }) {
  return (
    <Link to={`/realtime/${a.sym}`} style={{ textDecoration: 'none' }}>
      <div style={{
        background: highlight ? `${a.color}12` : '#0a0a0a',
        border: `1px solid ${highlight ? a.color+'50' : '#1a1a1a'}`,
        borderLeft: `3px solid ${a.color}`,
        borderRadius: 4, padding: '8px 10px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <span style={{ ...monoStyle, fontSize: 13, fontWeight: 900, color: '#fff' }}>{a.sym}</span>
          <span style={{ ...monoStyle, fontSize: 8, color: a.color, background: `${a.color}15`,
            padding: '1px 4px', borderRadius: 2 }}>{a.type}</span>
        </div>
        <div style={{ ...monoStyle, fontSize: 12, color: a.color, fontWeight: 'bold' }}>{a.label}</div>
        <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
          <span style={{ ...monoStyle, fontSize: 9, color: '#666' }}>${a.price?.toFixed(2)}</span>
          <span style={{ ...monoStyle, fontSize: 9,
            color: a.comp >= 60 ? '#00ff88' : a.comp >= 40 ? '#ffb800' : '#ff3355' }}>
            ★{a.comp?.toFixed(0)}
          </span>
          {a.eps != null && (
            <span style={{ ...monoStyle, fontSize: 9, color: a.eps > 0 ? '#00ff88' : '#ff3355' }}>
              EPS{a.eps > 0 ? '+' : ''}{a.eps.toFixed(0)}%
            </span>
          )}
        </div>
        {a.ecr_phase && (
          <div style={{ ...monoStyle, fontSize: 8, color: ECR_COLORS[a.ecr_phase]?.text ?? '#444', marginTop: 3 }}>
            {a.ecr_phase}
          </div>
        )}
      </div>
    </Link>
  );
}

/* ══════════════════════════════════════════════════════════
   SPY/QQQ リアルタイム
   ══════════════════════════════════════════════════════════ */
const marketCache = {};
function useMarketQuote(sym) {
  const [data,setData] = useState(null);
  useEffect(()=>{
    const apiKey=import.meta.env.VITE_FMP_API_KEY;
    const load=()=>{
      if(marketCache[sym]&&Date.now()-marketCache[sym].ts<60000){setData(marketCache[sym].d);return;}
      fetch(`https://financialmodelingprep.com/stable/quote?symbol=${sym}&apikey=${apiKey}`)
        .then(r=>r.json()).then(j=>{
          const q=Array.isArray(j)?j[0]:j;
          marketCache[sym]={d:q,ts:Date.now()};
          setData(q);
        }).catch(()=>{});
    };
    load();
    const id=setInterval(load,60000);
    return ()=>clearInterval(id);
  },[sym]);
  return data;
}

function MarketTicker({sym}) {
  const q = useMarketQuote(sym);
  const chg = q?.changesPercentage??q?.changePercentage??null;
  const pos = chg>=0;
  return (
    <div style={{display:'flex',alignItems:'center',gap:8,padding:'6px 14px',background:'#0a0a0a',border:`1px solid ${chg==null?'#222':pos?'#00ff8830':'#ff335530'}`,borderRadius:4}}>
      <span style={{...monoStyle,fontSize:'11px',color:'#6b7a90',letterSpacing:2}}>{sym}</span>
      {q ? <>
        <span style={{...monoStyle,fontSize:'14px',color:'#fff',fontWeight:'bold'}}>${q.price?.toFixed(2)??'---'}</span>
        <span style={{...monoStyle,fontSize:'11px',color:pos?'#00ff88':'#ff3355',fontWeight:'bold'}}>
          {pos?'▲':'▼'}{Math.abs(chg).toFixed(2)}%
        </span>
      </> : <span style={{...monoStyle,fontSize:'10px',color:'#333'}}>...</span>}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   MINI CHART POPUP（TradingViewウィジェット）
   ══════════════════════════════════════════════════════════ */
function MiniChartPopup({ticker, onClose}) {
  const ref = useRef(null);
  useEffect(()=>{
    if (!ref.current||!ticker) return;
    ref.current.innerHTML='';
    const s=document.createElement('script');
    s.src='https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js';
    s.async=true;
    s.innerHTML=JSON.stringify({
      symbol: ticker, width:'100%', height:220,
      locale:'en', dateRange:'1M', colorTheme:'dark',
      isTransparent:true, autosize:false, largeChartUrl:'',
    });
    ref.current.appendChild(s);
  },[ticker]);

  useEffect(()=>{
    const handler=(e)=>{ if(e.key==='Escape') onClose(); };
    window.addEventListener('keydown',handler);
    return ()=>window.removeEventListener('keydown',handler);
  },[onClose]);

  return (
    <div style={{position:'fixed',inset:0,background:'#000000aa',zIndex:1000,display:'flex',alignItems:'center',justifyContent:'center'}}
      onClick={onClose}>
      <div style={{background:'#0a0a0a',border:'1px solid #333',borderRadius:8,padding:20,width:420,position:'relative'}}
        onClick={e=>e.stopPropagation()}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
          <span style={{...monoStyle,fontSize:'16px',fontWeight:'bold',color:'#fff',letterSpacing:2}}>{ticker}</span>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <Link to={`/realtime/${ticker}`}
              style={{...monoStyle,fontSize:'10px',color:'#00aaff',border:'1px solid #00aaff33',padding:'3px 8px',borderRadius:3,textDecoration:'none'}}>
              FULL PAGE →
            </Link>
            <button onClick={onClose} style={{background:'none',border:'none',cursor:'pointer',color:'#666',padding:2}}>
              <X size={16}/>
            </button>
          </div>
        </div>
        <div ref={ref}/>
        <div style={{...monoStyle,fontSize:'9px',color:'#333',marginTop:6,textAlign:'right'}}>ESCキーで閉じる</div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   COMPONENTS
   ══════════════════════════════════════════════════════════ */
function TerminalMeter({label,value,max=100,color='#00ff88',width='80px'}) {
  const bars=10, val=value||0;
  const filled=Math.min(bars,Math.max(0,Math.round((val/max)*bars)));
  return (
    <div style={{display:'flex',alignItems:'center',gap:6,...monoStyle,fontSize:'10px'}}>
      <span style={{width:28,color:'#6b7a90',textAlign:'right'}}>{label}</span>
      <div style={{display:'flex',gap:2,width}}>
        {Array.from({length:bars}).map((_,i)=>(
          <div key={i} style={{flex:1,height:8,background:i<filled?color:'#111',boxShadow:i<filled?`0 0 4px ${color}40`:'none',border:`1px solid ${i<filled?color:'#222'}`}}/>
        ))}
      </div>
      <span style={{width:26,textAlign:'right',color:'#fff'}}>{val.toFixed(0)}</span>
    </div>
  );
}

function PhaseTag({phase}) {
  const c=ECR_COLORS[phase]||{bg:'#ffffff10',border:'#444',text:'#888'};
  return <span style={{background:c.bg,border:`1px solid ${c.border}`,color:c.text,padding:'2px 6px',borderRadius:4,fontSize:10,fontWeight:'bold',letterSpacing:.5}}>{phase||'UNKNOWN'}</span>;
}

function SignalChips({signals}) {
  if (!signals?.length) return <div style={{color:'#555',fontSize:11,...monoStyle}}>NO SIGNALS DETECTED</div>;
  return (
    <div style={{display:'flex',gap:6,flexWrap:'wrap',marginBottom:8}}>
      {signals.map((s,i)=>(
        <span key={i} style={{background:'#1a1a1a',padding:'2px 8px',borderRadius:4,fontSize:10,border:'1px solid #333',color:'#00aaff',...monoStyle}}>{'>'} {s}</span>
      ))}
    </div>
  );
}

function EarningsBadge({ticker}) {
  const data=useEarningsDate(ticker);
  if (data===undefined) return <span style={{...monoStyle,fontSize:9,color:'#333'}}><Clock size={9}/></span>;
  if (!data?.signal) return null;
  const s=data.signal;
  if (s.type==='SAFE'||s.type==='WATCH') return null;
  return (
    <span style={{display:'inline-flex',alignItems:'center',gap:3,background:s.bg,border:`1px solid ${s.color}50`,borderRadius:3,padding:'1px 5px',...monoStyle,fontSize:9,color:s.color,fontWeight:s.type==='DANGER'||s.type==='TODAY'?'bold':'normal',whiteSpace:'nowrap',animation:s.type==='DANGER'||s.type==='TODAY'?'earn-pulse 2s ease infinite':'none'}}>
      <Calendar size={8}/> {s.label}
    </span>
  );
}

function EarningsDetail({ticker}) {
  const data=useEarningsDate(ticker);
  if (data===undefined) return <div style={{...monoStyle,fontSize:10,color:'#444'}}>[EARN] 取得中...</div>;
  if (!data?.date)      return <div style={{...monoStyle,fontSize:10,color:'#444'}}>[EARN] 90日以内の決算予定なし</div>;
  const s=data.signal;
  return (
    <div style={{background:s?.bg||'#ffffff06',border:`1px solid ${s?.color||'#333'}30`,borderLeft:`3px solid ${s?.color||'#444'}`,borderRadius:4,padding:'10px 12px',...monoStyle,fontSize:11,marginTop:8}}>
      <div style={{color:'#6b7a90',marginBottom:4}}>[EARN] EARNINGS_SCHEDULE</div>
      <div style={{display:'flex',justifyContent:'space-between'}}>
        <span style={{color:'#888'}}>決算予定日</span>
        <span style={{color:'#fff',fontWeight:'bold'}}>{data.date}</span>
      </div>
      {data.days!==null&&(
        <div style={{display:'flex',justifyContent:'space-between',marginTop:3}}>
          <span style={{color:'#888'}}>残り</span>
          <span style={{color:s?.color||'#888',fontWeight:'bold'}}>
            {data.days<0?`${Math.abs(data.days)}日前（通過済）`:data.days===0?'本日！':`${data.days}日後`}
          </span>
        </div>
      )}
      {(s?.type==='DANGER'||s?.type==='TODAY')&&(
        <div style={{marginTop:6,padding:'3px 6px',background:'#ff335512',border:'1px solid #ff335540',borderRadius:3,color:'#ff3355',fontSize:10}}>
          ⚠ 決算前エントリーはリスク大。通過後を推奨。
        </div>
      )}
      {s?.type==='WARNING'&&(
        <div style={{marginTop:6,padding:'3px 6px',background:'#ffb80010',border:'1px solid #ffb80030',borderRadius:3,color:'#ffb800',fontSize:10}}>
          📅 1週間以内に決算。ポジションサイズ注意。
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   SCANNER ROW
   ══════════════════════════════════════════════════════════ */
function ScannerRow({t, rank, onChartOpen}) {
  const [expanded,setExpanded] = useState(false);
  const cGrade=t.canslim_grade||'-';
  const cColor=CANSLIM_COLORS[cGrade]||'#888';
  const chgPct=t.change_pct??t.changesPercentage;

  // 52週高値比% — dist_from_52w_pct: 高値からの距離% (0=高値ぴったり, 10=10%下)
  // 表示は負の値（-10% = 高値から10%下）に変換
  const high52pct = t.canslim_metrics?.dist_from_52w_pct != null
    ? -Math.abs(t.canslim_metrics.dist_from_52w_pct)
    : null;

  // 出来高倍率 — avg_volumeはJSON済み、volumeは当日データなので未実装時は非表示
  const volRatio = (t.volume && t.avg_volume) ? (t.volume/t.avg_volume) : null;
  const volColor = volRatio==null?'#888':volRatio>=2?'#ff3355':volRatio>=1.5?'#ffb800':volRatio>=1?'#00ff88':'#6b7a90';

  // EPS成長率
  const eps = t.canslim_metrics?.eps_growth;

  const handleRowClick = () => setExpanded(v=>!v);
  const handleChartClick = (e) => { e.stopPropagation(); onChartOpen(t.ticker); };

  return (
    <>
      <tr style={{cursor:'pointer',borderBottom:'1px solid #111',background:expanded?'#070707':'transparent',transition:'background 0.15s'}}
        onClick={handleRowClick}>

        {/* ID */}
        <td style={{padding:'10px 8px',color:'#333',...monoStyle,fontSize:11}}>{String(rank).padStart(3,'0')}</td>

        {/* TICKER / BADGES */}
        <td style={{padding:'10px 8px',minWidth:160}}>
          <div style={{display:'flex',alignItems:'center',gap:6,flexWrap:'wrap'}}>
            <Link to={`/realtime/${t.ticker}`}
              style={{fontWeight:900,fontSize:15,color:'#fff',textDecoration:'none',letterSpacing:1}}
              onClick={e=>e.stopPropagation()}>
              {t.ticker}
            </Link>
            {/* ミニチャートボタン */}
            <button onClick={handleChartClick}
              style={{background:'#ffffff08',border:'1px solid #333',borderRadius:3,padding:'1px 5px',cursor:'pointer',color:'#6b7a90',fontSize:9,...monoStyle,lineHeight:1.4}}>
              CHART
            </button>
            <span onClick={e=>e.stopPropagation()}>
              <EarningsBadge ticker={t.ticker}/>
            </span>
            {/* EPS成長率バッジ */}
            {eps!=null&&(
              <span style={{...monoStyle,fontSize:9,color:eps>0?'#00ff88':'#ff3355',background:eps>0?'#00ff8810':'#ff335510',border:`1px solid ${eps>0?'#00ff8830':'#ff335530'}`,borderRadius:3,padding:'1px 5px',whiteSpace:'nowrap'}}>
                EPS {eps>0?'+':''}{eps.toFixed(0)}%
              </span>
            )}
          </div>
          <div style={{fontSize:9,color:'#444',marginTop:2,...monoStyle}}>{t.sector?.substring(0,20)||'UNKNOWN'}</div>
        </td>

        {/* COMPANY */}
        <td style={{padding:'10px 8px',fontSize:11,color:'#666',maxWidth:110}}>
          <div style={{overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.name||'---'}</div>
        </td>

        {/* PRICE / CHG / PVT */}
        <td style={{padding:'10px 8px',minWidth:90}}>
          <div style={{...monoStyle,fontSize:13,color:'#fff',fontWeight:'bold'}}>${t.price?.toFixed(2)||'---'}</div>
          {chgPct!=null&&(
            <div style={{...monoStyle,fontSize:10,color:chgPct>0?'#00ff88':chgPct<0?'#ff3355':'#888',fontWeight:'bold'}}>
              {chgPct>0?'▲':'▼'}{Math.abs(chgPct).toFixed(2)}%
            </div>
          )}
          {t.pivot_dist_pct!=null&&(
            <div style={{...monoStyle,fontSize:9,color:t.pivot_dist_pct<=0?'#00aaff':'#ff3355'}}>
              {t.pivot_dist_pct>0?'+':''}{t.pivot_dist_pct?.toFixed(1)}% PVT
            </div>
          )}
        </td>

        {/* 52W HIGH% / VOL RATIO */}
        <td style={{padding:'10px 8px',minWidth:80}}>
          {high52pct!=null?(
            <div style={{...monoStyle,fontSize:11,color:high52pct>=-5?'#00ff88':high52pct>=-15?'#ffb800':'#ff3355',fontWeight:'bold'}}>
              {high52pct.toFixed(1)}%
            </div>
          ):<div style={{color:'#333',...monoStyle,fontSize:10}}>---</div>}
          <div style={{fontSize:9,color:'#444',...monoStyle}}>52W HIGH</div>
          {volRatio!=null&&(
            <div style={{...monoStyle,fontSize:10,color:volColor,marginTop:3,fontWeight:volRatio>=1.5?'bold':'normal'}}>
              {volRatio>=1.5&&'⚡'}{volRatio.toFixed(1)}x VOL
            </div>
          )}
        </td>

        {/* SYS SCORES */}
        <td style={{padding:'10px 8px',minWidth:150}}>
          <div style={{display:'flex',flexDirection:'column',gap:3}}>
            <TerminalMeter label="VCP" value={t.scores?.vcp}       max={100} color="#00aaff"/>
            <TerminalMeter label="RS"  value={t.scores?.rs}        max={100} color="#00ff88"/>
            <TerminalMeter label="CMP" value={t.scores?.composite} max={100} color="#ffb800"/>
          </div>
        </td>

        {/* CANSLIM */}
        <td style={{padding:'10px 8px'}}>
          <div style={{display:'flex',alignItems:'baseline',gap:6}}>
            <span style={{fontSize:9,color:'#6b7a90',...monoStyle}}>GRD</span>
            <span style={{fontSize:16,fontWeight:900,color:cColor}}>{cGrade}</span>
          </div>
          <TerminalMeter label="SCR" value={t.scores?.canslim} max={100} color={cColor} width="50px"/>
        </td>

        {/* PHASE */}
        <td style={{padding:'10px 8px'}}><PhaseTag phase={t.ecr_phase}/></td>

        {/* STATUS */}
        <td style={{padding:'10px 8px'}}>
          <span style={{padding:'3px 7px',borderRadius:3,fontSize:9,fontWeight:'bold',letterSpacing:.5,background:t.status==='ACTION'?'#00ff8815':'transparent',color:t.status==='ACTION'?'#00ff88':'#444',border:`1px solid ${t.status==='ACTION'?'#00ff88':'#222'}`}}>
            {t.status||'WAIT'}
          </span>
        </td>

        <td style={{padding:'10px 8px',color:'#333',fontSize:10,...monoStyle}}>{expanded?'▲':'▼'}</td>
      </tr>

      {/* アコーディオン */}
      {expanded&&(
        <tr>
          <td colSpan={10} style={{background:'#050505',padding:0,borderBottom:'1px solid #1a1a1a'}}>
            <div style={{padding:20,display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(240px,1fr))',gap:20,borderLeft:'2px solid #00aaff33'}}>
              <div>
                <div style={{fontSize:9,color:'#00aaff',marginBottom:8,...monoStyle}}>[SYS] VCP_ANALYSIS_MODULE</div>
                {t.vcp_details?.signals&&<SignalChips signals={t.vcp_details.signals}/>}
                <div style={{background:'#111',padding:12,borderRadius:4,border:'1px solid #1a1a1a'}}>
                  {t.vcp_details?.breakdown&&Object.entries(t.vcp_details.breakdown).map(([k,v])=>(
                    <TerminalMeter key={k} label={k.substring(0,3).toUpperCase()} value={v} max={35} color="#00aaff" width="100%"/>
                  ))}
                </div>
              </div>
              <div>
                <div style={{fontSize:9,color:'#ff3355',marginBottom:8,...monoStyle}}>[SYS] SES_METRICS_MODULE</div>
                <div style={{background:'#111',padding:12,borderRadius:4,border:'1px solid #1a1a1a'}}>
                  {t.ses_details?.breakdown&&Object.entries(t.ses_details.breakdown).map(([k,v])=>(
                    <TerminalMeter key={k} label={k.substring(0,3).toUpperCase()} value={v} max={25} color="#ff3355" width="100%"/>
                  ))}
                </div>
              </div>
              <div>
                <div style={{fontSize:9,color:'#00ff88',marginBottom:8,...monoStyle}}>[SYS] FUNDAMENTAL_DATA</div>
                <div style={{background:'#111',padding:12,borderRadius:4,border:'1px solid #1a1a1a',display:'flex',flexDirection:'column',gap:7}}>
                  {[
                    ['RELATIVE STRENGTH', t.canslim_metrics?.rs_pct!=null?`${t.canslim_metrics.rs_pct}%`:'---', '#00ff88'],
                    ['EPS GROWTH (QTR)', t.canslim_metrics?.eps_growth!=null?`${t.canslim_metrics.eps_growth.toFixed(1)}%`:'---', (t.canslim_metrics?.eps_growth||0)>0?'#00ff88':'#ff3355'],
                    ['SALES GROWTH (QTR)', t.canslim_metrics?.rev_growth!=null?`${t.canslim_metrics.rev_growth.toFixed(1)}%`:'---', (t.canslim_metrics?.rev_growth||0)>0?'#00ff88':'#ff3355'],
                    ['DIST TO MA50', t.ma50_ratio!=null?`${t.ma50_ratio>0?'+':''}${t.ma50_ratio.toFixed(2)}%`:'---', '#fff'],
                    ['52W HIGH', high52pct!=null?`${high52pct.toFixed(1)}%`:'---', high52pct!=null&&high52pct>=-5?'#00ff88':high52pct!=null&&high52pct>=-15?'#ffb800':'#ff3355'],
                    ['VOL RATIO', volRatio!=null?`${volRatio.toFixed(2)}x`:'---', volColor],
                  ].map(([label,val,col])=>(
                    <div key={label} style={{display:'flex',justifyContent:'space-between',...monoStyle,fontSize:11}}>
                      <span style={{color:'#555'}}>{label}</span>
                      <span style={{color:col,fontWeight:'bold'}}>{val}</span>
                    </div>
                  ))}
                  <EarningsDetail ticker={t.ticker}/>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/* ══════════════════════════════════════════════════════════
   MAIN SCANNER
   ══════════════════════════════════════════════════════════ */
export default function Scanner() {
  const [strategies,setStrategies] = useState(null);
  const [search,setSearch]         = useState('');
  const [statusFilter,setStatusFilter]   = useState('ALL');
  const [ecrFilter,setEcrFilter]         = useState('ALL');
  const [earningsFilter,setEarningsFilter] = useState('ALL');
  const [minVcp,setMinVcp]   = useState(0);
  const [minRs,setMinRs]     = useState(0);
  const [minSes,setMinSes]   = useState(0);
  const [minEcr,setMinEcr]   = useState(0);
  const [minCom,setMinCom]   = useState(0);
  const [maxCom,setMaxCom]   = useState(100);
  const [minCanslim,setMinCanslim] = useState(0);
  const [sortBy,setSortBy]   = useState('composite');
  const [sortDir,setSortDir] = useState('desc');
  const [showFilters,setShowFilters] = useState(false);
  const [page,setPage]       = useState(0);
  const [chartTicker,setChartTicker] = useState(null); // ミニチャートポップアップ用
  const itemsPerPage = 50;

  useEffect(()=>{
    fetch('/content/strategies.json').then(r=>r.json()).then(setStrategies)
      .catch(()=>setStrategies({all_data:[],action_count:0,wait_count:0,ticker_count:0}));
  },[]);

  useEffect(()=>{ setPage(0); },[search,statusFilter,ecrFilter,minVcp,minRs,minSes,minEcr,minCom,maxCom,minCanslim,sortBy,sortDir,earningsFilter]);

  const allItems = useMemo(()=>strategies?.all_data||[],[strategies]);

  const filtered = useMemo(()=>{
    return allItems.filter(t=>{
      const q=search.toLowerCase();
      const matchSearch = t.ticker.toLowerCase().includes(q)||(t.name?.toLowerCase().includes(q));
      const matchStatus = statusFilter==='ALL'||t.status===statusFilter;
      const matchEcr    = ecrFilter==='ALL'||t.ecr_phase===ecrFilter;
      const matchVcp    = (t.scores?.vcp??0)>=minVcp;
      const matchRs     = (t.scores?.rs??0)>=minRs;
      const matchCanslim = (t.scores?.canslim??0)>=(minCanslim??0);
      const matchSes    = (t.scores?.ses??0)>=minSes;
      const matchEcrSc  = (t.scores?.ecr_rank??0)>=minEcr;
      const comp        = t.scores?.composite??0;
      const matchCom    = comp>=minCom&&comp<=maxCom;
      let matchEarn=true;
      if (earningsFilter!=='ALL'&&earningsCache[t.ticker]!==undefined) {
        const sig=getEarningsSignal(daysUntil(earningsCache[t.ticker]));
        if (earningsFilter==='DANGER')  matchEarn=sig?.type==='DANGER'||sig?.type==='TODAY';
        if (earningsFilter==='WARNING') matchEarn=sig?.type==='WARNING';
        if (earningsFilter==='SAFE')    matchEarn=!sig||sig.type==='SAFE'||sig.type==='PASSED';
      }
      return matchSearch&&matchStatus&&matchEcr&&matchVcp&&matchRs&&matchSes&&matchEcrSc&&matchCom&&matchEarn&&matchCanslim;
    }).sort((a,b)=>{
      const dir = sortDir==='desc'?1:-1;
      if (sortBy==='price')         return dir*((b.price??0)-(a.price??0));
      if (sortBy==='change_pct')    return dir*((b.change_pct??b.changesPercentage??0)-(a.change_pct??a.changesPercentage??0));
      if (sortBy==='pivot_dist_pct')return dir*((b.pivot_dist_pct??0)-(a.pivot_dist_pct??0));
      if (sortBy==='high52pct') {
        // dist_from_52w_pct: 小さいほど高値圏。asc=高値圏順（良い順）
        const va = a.canslim_metrics?.dist_from_52w_pct ?? 999;
        const vb = b.canslim_metrics?.dist_from_52w_pct ?? 999;
        return dir*(va-vb); // ascで小→0に近い=高値圏が上
      }
      if (sortBy==='vol_ratio') {
        const va=(a.volume&&a.avg_volume)?(a.volume/a.avg_volume):null;
        const vb=(b.volume&&b.avg_volume)?(b.volume/b.avg_volume):null;
        return dir*((vb??0)-(va??0));
      }
      return dir*((b.scores?.[sortBy]??0)-(a.scores?.[sortBy]??0));
    });
  },[allItems,search,statusFilter,ecrFilter,minVcp,minRs,minSes,minEcr,minCom,maxCom,sortBy,sortDir,earningsFilter]);

  const ecrCounts = useMemo(()=>{
    const c={};allItems.forEach(t=>{c[t.ecr_phase]=(c[t.ecr_phase]||0)+1;});return c;
  },[allItems]);

  const totalPages = Math.ceil(filtered.length/itemsPerPage);
  const paginatedData = filtered.slice(page*itemsPerPage,(page+1)*itemsPerPage);

  const applyPreset = (preset) => {
    setPage(0); setEarningsFilter('ALL');
    if (preset==='DIAMOND')  { setMinRs(70);setMinCom(40);setMaxCom(60);setMinVcp(0);setMinSes(0);setMinEcr(0);setStatusFilter('ALL');setEcrFilter('ALL');setSearch('');setSortBy('rs');setSortDir('desc'); }
    if (preset==='MOMENTUM') { setMinRs(80);setMinCom(60);setMaxCom(100);setMinVcp(0);setMinSes(0);setMinEcr(0);setStatusFilter('ALL');setEcrFilter('ALL');setSearch('');setSortBy('composite');setSortDir('desc'); }
    if (preset==='EARNINGS_SAFE') { setEarningsFilter('SAFE');setMinRs(70);setMinCom(50);setMaxCom(100);setMinVcp(0);setMinSes(0);setMinEcr(0);setStatusFilter('ACTION');setEcrFilter('ALL');setSearch('');setSortBy('composite');setSortDir('desc'); }
    if (preset==='RESET') { setMinRs(0);setMinCom(0);setMaxCom(100);setMinVcp(0);setMinSes(0);setMinEcr(0);setMinCanslim(0);setEarningsFilter('ALL');setStatusFilter('ALL');setEcrFilter('ALL');setSearch('');setSortBy('composite');setSortDir('desc'); }
  };
  const toggleSort=(key)=>{ if(sortBy===key) setSortDir(d=>d==='desc'?'asc':'desc'); else{setSortBy(key);setSortDir(key==='high52pct'?'asc':'desc');} };

  if (!strategies) return (
    <div style={{display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',height:'100vh',background:'#000',color:'#00ff88',...monoStyle}}>
      <Terminal size={32} style={{marginBottom:16}}/>
      <div style={{fontSize:18,letterSpacing:4}}>INITIALIZING TERMINAL...</div>
    </div>
  );

  return (
    <div style={{padding:'20px 24px',background:'#000',minHeight:'100vh',color:'#fff',fontFamily:'"SF Pro Text","Segoe UI",sans-serif'}}>

      {/* ══ BLOOMBERG HEADER ══ */}
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:20,borderBottom:'1px solid #111',paddingBottom:16}}>
        <div>
          <h1 style={{margin:0,fontSize:22,letterSpacing:4,fontWeight:900,display:'flex',alignItems:'center',gap:10,...monoStyle}}>
            <BarChart2 color="#00aaff" size={20}/> DATA_TERMINAL
          </h1>
          <div style={{display:'flex',gap:14,marginTop:10,fontSize:10,...monoStyle,flexWrap:'wrap'}}>
            <span style={{color:'#00ff88'}}>[SYS] ACTION: {String(strategies.action_count||0).padStart(4,'0')}</span>
            <span style={{color:'#6b7a90'}}>[SYS] WAIT: {String(strategies.wait_count||0).padStart(4,'0')}</span>
            {ecrCounts['IGNITION']&&<span style={{color:'#00aaff'}}>[+] IGNITION: {String(ecrCounts['IGNITION']).padStart(4,'0')}</span>}
            <span style={{color:'#333'}}>TOTAL: {strategies.ticker_count||0}</span>
          </div>
        </div>
        {/* SPY / QQQ リアルタイム */}
        <div style={{display:'flex',gap:8,alignItems:'center',flexWrap:'wrap'}}>
          <MarketTicker sym="SPY"/>
          <MarketTicker sym="QQQ"/>
          <MarketTicker sym="IWM"/>
          <button onClick={()=>setShowFilters(v=>!v)} style={{display:'flex',alignItems:'center',gap:6,background:showFilters?'#00aaff20':'#111',border:`1px solid ${showFilters?'#00aaff':'#333'}`,color:showFilters?'#00aaff':'#fff',padding:'8px 14px',borderRadius:4,cursor:'pointer',fontWeight:'bold',...monoStyle,fontSize:11}}>
            <SlidersHorizontal size={13}/> {showFilters?'CONFIG_ACTIVE':'OPEN_CONFIG'}
          </button>
        </div>
      </div>

      {/* ══ PRESETS ══ */}
      <div style={{display:'flex',gap:10,marginBottom:20,flexWrap:'wrap'}}>
        {[
          {id:'DIAMOND',  label:'[EXEC] DIAMOND_SCAN',    col:'#00aaff', icon:<Diamond size={11} fill="#00aaff"/>},
          {id:'MOMENTUM', label:'[EXEC] MOMENTUM_SAFE',   col:'#00ff88', icon:<ShieldCheck size={11}/>},
          {id:'EARNINGS_SAFE',label:'[EXEC] EARNINGS_SAFE',col:'#aa66ff',icon:<Calendar size={11}/>},
          {id:'RESET',    label:'[RESET_PARAMS]',         col:'#444',    icon:<RotateCcw size={11}/>},
        ].map(({id,label,col,icon})=>(
          <button key={id} onClick={()=>applyPreset(id)} style={{display:'flex',alignItems:'center',gap:6,background:`${col}10`,border:`1px solid ${col}`,color:col,padding:'7px 14px',borderRadius:4,cursor:'pointer',...monoStyle,fontSize:10}}>
            {icon} {label}
          </button>
        ))}
      </div>

      {/* ══ SEARCH ══ */}
      <div style={{position:'relative',marginBottom:20,maxWidth:360}}>
        <Search size={14} style={{position:'absolute',left:11,top:11,color:'#00aaff'}}/>
        <input style={{width:'100%',background:'#0a0a0a',border:'1px solid #222',color:'#00aaff',padding:'9px 9px 9px 33px',borderRadius:4,...monoStyle,fontSize:12,outline:'none'}}
          value={search} onChange={e=>setSearch(e.target.value)} placeholder="QUERY TICKER OR NAME..."/>
      </div>

      {/* ══ FILTERS ══ */}
      {showFilters&&(
        <div style={{background:'#050505',border:'1px solid #1a1a1a',borderLeft:'3px solid #00aaff',borderRadius:4,padding:20,marginBottom:20,display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))',gap:20}}>
          <div>
            <label style={{display:'block',fontSize:9,color:'#6b7a90',marginBottom:6,...monoStyle}}>// TARGET_STATUS</label>
            <div style={{display:'flex',gap:6}}>
              {['ALL','ACTION','WAIT'].map(s=>(
                <button key={s} onClick={()=>setStatusFilter(s)} style={{background:statusFilter===s?'#222':'#0a0a0a',border:`1px solid ${statusFilter===s?'#00aaff':'#222'}`,color:statusFilter===s?'#00aaff':'#666',padding:'5px 10px',borderRadius:3,cursor:'pointer',...monoStyle,fontSize:10}}>{s}</button>
              ))}
            </div>
          </div>
          <div style={{gridColumn:'span 2'}}>
            <label style={{display:'block',fontSize:9,color:'#6b7a90',marginBottom:6,...monoStyle}}>// ECR_PHASE_FILTER</label>
            <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
              {['ALL','IGNITION','HOLD/WATCH','WATCH','REJECTED'].map(phase=>(
                <button key={phase} onClick={()=>setEcrFilter(phase)} style={{background:ecrFilter===phase?'#222':'#0a0a0a',border:`1px solid ${ecrFilter===phase?'#ffb800':'#222'}`,color:ecrFilter===phase?'#ffb800':'#666',padding:'5px 10px',borderRadius:3,cursor:'pointer',...monoStyle,fontSize:10}}>{phase}</button>
              ))}
            </div>
          </div>
          <div>
            <label style={{display:'block',fontSize:9,color:'#aa66ff',marginBottom:6,...monoStyle}}>// EARNINGS_RISK_FILTER</label>
            <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
              {[{v:'ALL',l:'ALL',c:'#666'},{v:'DANGER',l:'🔴 3日以内',c:'#ff3355'},{v:'WARNING',l:'🟡 7日以内',c:'#ffb800'},{v:'SAFE',l:'✅ 安全圏',c:'#00ff88'}].map(({v,l,c})=>(
                <button key={v} onClick={()=>setEarningsFilter(v)} style={{background:earningsFilter===v?'#222':'#0a0a0a',border:`1px solid ${earningsFilter===v?c:'#222'}`,color:earningsFilter===v?c:'#666',padding:'5px 10px',borderRadius:3,cursor:'pointer',...monoStyle,fontSize:10}}>{l}</button>
              ))}
            </div>
          </div>
          <div style={{gridColumn:'span 2'}}>
            <label style={{display:'block',fontSize:9,color:'#ffb800',marginBottom:6,...monoStyle}}>// COMPOSITE_RANGE: [{minCom} - {maxCom}] <span style={{color:'#333'}}>※PF>1: 60+</span></label>
            <div style={{display:'flex',gap:12,alignItems:'center'}}>
              <input type="range" min="0" max="100" value={minCom} onChange={e=>setMinCom(+e.target.value)} style={{flex:1,accentColor:'#ffb800'}}/>
              <input type="range" min="0" max="100" value={maxCom} onChange={e=>setMaxCom(+e.target.value)} style={{flex:1,accentColor:'#ffb800'}}/>
            </div>
          </div>
          <div>
            <label style={{display:'block',fontSize:9,color:'#00ff88',marginBottom:6,...monoStyle}}>// MIN_RS: {minRs} <span style={{color:'#333'}}>※PF>1: 90+</span></label>
            <input type="range" min="0" max="99" value={minRs} onChange={e=>setMinRs(+e.target.value)} style={{width:'100%',accentColor:'#00ff88'}}/>
          </div>
          <div>
            <label style={{display:'block',fontSize:9,color:'#00aaff',marginBottom:6,...monoStyle}}>// MIN_ECR: {minEcr} <span style={{color:'#333'}}>※PF>1: 60+</span></label>
            <input type="range" min="0" max="80" value={minEcr} onChange={e=>setMinEcr(+e.target.value)} style={{width:'100%',accentColor:'#00aaff'}}/>
          </div>
          <div>
            <label style={{display:'block',fontSize:9,color:'#ff9500',marginBottom:6,...monoStyle}}>// MIN_VCP: {minVcp} <span style={{color:'#333'}}>※PF>1: 80+</span></label>
            <input type="range" min="0" max="105" value={minVcp} onChange={e=>setMinVcp(+e.target.value)} style={{width:'100%',accentColor:'#ff9500'}}/>
          </div>
          <div>
            <label style={{display:'block',fontSize:9,color:'#aa66ff',marginBottom:6,...monoStyle}}>// MIN_SES: {minSes}</label>
            <input type="range" min="0" max="100" value={minSes} onChange={e=>setMinSes(+e.target.value)} style={{width:'100%',accentColor:'#aa66ff'}}/>
          </div>
          <div>
            <label style={{display:'block',fontSize:9,color:'#ff6680',marginBottom:6,...monoStyle}}>// MIN_CANSLIM: {minCanslim??0}</label>
            <input type="range" min="0" max="100" value={minCanslim??0} onChange={e=>setMinCanslim(+e.target.value)} style={{width:'100%',accentColor:'#ff6680'}}/>
          </div>
        </div>
      )}

      {/* ══ REALTIME MONITOR ══ */}
      <RealtimeAlertPanel allItems={allItems}/>

      {/* ══ TABLE STATUS ══ */}
      <div style={{...monoStyle,fontSize:10,color:'#444',marginBottom:10,display:'flex',justifyContent:'space-between',flexWrap:'wrap',gap:6}}>
        <span>DATA_ROWS: <span style={{color:'#00aaff'}}>{filtered.length}</span> MATCHES</span>
        <div style={{display:'flex',gap:14}}>
          {earningsFilter!=='ALL'&&<span style={{color:'#aa66ff'}}>EARNINGS_FILTER: {earningsFilter}</span>}
          <span>SORT: {sortBy.toUpperCase()} {sortDir==='desc'?'▼':'▲'}</span>
        </div>
      </div>

      {/* ══ TABLE ══ */}
      <div style={{overflowX:'auto',background:'#050505',border:'1px solid #111',borderRadius:6}}>
        <table style={{width:'100%',borderCollapse:'collapse',textAlign:'left'}}>
          <thead>
            <tr style={{background:'#080808',borderBottom:'1px solid #1a1a1a'}}>
              {[
                {k:null,      l:'#'},
                {k:null,      l:'TICKER / EARNINGS'},
                {k:null,      l:'COMPANY'},
                {k:'price',   l:'PRICE / CHG'},
                {k:'high52pct',l:'52W / VOL'},
                {k:'composite',l:'SYS_SCORES'},
                {k:'canslim', l:'CANSLIM'},
                {k:null,      l:'PHASE'},
                {k:null,      l:'STAT'},
                {k:null,      l:''},
              ].map(({k,l},i)=>(
                <th key={i} onClick={k?()=>toggleSort(k):undefined}
                  style={{padding:'10px 8px',color:k&&sortBy===k?'#fff':'#333',fontSize:9,...monoStyle,cursor:k?'pointer':'default',userSelect:'none',whiteSpace:'nowrap'}}>
                  {l}{k&&sortBy===k?(sortDir==='desc'?' ▼':' ▲'):''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedData.map((t,i)=>(
              <ScannerRow key={t.ticker} t={t} rank={page*itemsPerPage+i+1} onChartOpen={setChartTicker}/>
            ))}
          </tbody>
        </table>

        {totalPages>1&&(
          <div style={{padding:'10px 16px',display:'flex',justifyContent:'center',alignItems:'center',gap:20,borderTop:'1px solid #111',background:'#080808'}}>
            <button disabled={page===0} onClick={()=>setPage(p=>p-1)} style={{padding:'5px 14px',background:'transparent',color:page===0?'#222':'#00aaff',border:`1px solid ${page===0?'#111':'#00aaff'}`,borderRadius:3,cursor:page===0?'not-allowed':'pointer',...monoStyle,fontSize:10}}>{'< PREV'}</button>
            <span style={{color:'#444',fontSize:10,...monoStyle}}>PAGE {String(page+1).padStart(2,'0')} / {String(totalPages).padStart(2,'0')}</span>
            <button disabled={page===totalPages-1} onClick={()=>setPage(p=>p+1)} style={{padding:'5px 14px',background:'transparent',color:page===totalPages-1?'#222':'#00aaff',border:`1px solid ${page===totalPages-1?'#111':'#00aaff'}`,borderRadius:3,cursor:page===totalPages-1?'not-allowed':'pointer',...monoStyle,fontSize:10}}>{'NEXT >'}</button>
          </div>
        )}
      </div>

      {/* ══ MINI CHART POPUP ══ */}
      {chartTicker&&<MiniChartPopup ticker={chartTicker} onClose={()=>setChartTicker(null)}/>}

      <style>{`
        @keyframes earn-pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
      `}</style>
    </div>
  );
}