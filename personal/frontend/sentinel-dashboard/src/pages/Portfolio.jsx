import React, { useState, useEffect, useMemo } from 'react';
import { Plus, Trash2, X } from 'lucide-react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';

const STORAGE_KEY = 'portfolio:trades';

// Sentinelのスコアデータを取得
function useSentinelScores() {
  const [scores, setScores] = useState({});
  useEffect(() => {
    fetch('/content/strategies.json').then(r => r.json()).then(d => {
      const map = {};
      (d?.all_data || []).forEach(t => { map[t.ticker] = { ...t.scores, status: t.status, ecr_phase: t.ecr_phase }; });
      setScores(map);
    }).catch(() => {});
  }, []);
  return scores;
}
const fmt = (n, d=2) => n != null ? `$${Number(n).toLocaleString('en-US', {minimumFractionDigits:d,maximumFractionDigits:d})}` : '—';

async function loadTrades() {
  try {
    const r = await window.storage.get(STORAGE_KEY);
    return r ? JSON.parse(r.value) : [];
  } catch { return []; }
}
async function saveTrades(d) {
  try { await window.storage.set(STORAGE_KEY, JSON.stringify(d)); } catch {}
}

function useCurrentPrices(tickers) {
  const [prices, setPrices] = useState({});
  useEffect(() => {
    if (!tickers?.length) return;
    const apiKey = import.meta.env.VITE_FMP_API_KEY;
    const syms = tickers.slice(0, 20).join(',');
    fetch(`https://financialmodelingprep.com/stable/quote?symbol=${syms}&apikey=${apiKey}`)
      .then(r => r.json())
      .then(json => {
        const map = {};
        (Array.isArray(json) ? json : []).forEach(q => { map[q.symbol] = q.price; });
        setPrices(map);
      }).catch(() => {});
  }, [tickers?.join(',')]);
  return prices;
}

const COLORS = ['#00ff88','#4499ff','#ffb800','#ff3355','#aa66ff','#00ccff','#ff8844','#88ff44'];

function AddTradeModal({ onAdd, onClose }) {
  const [form, setForm] = useState({
    ticker:'', shares:'', bought_at:'',
    date: new Date().toISOString().slice(0,10),
    stop:'', target:'', note:''
  });
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = () => {
    if (!form.ticker || !form.shares || !form.bought_at) return;
    onAdd({
      id: Date.now(),
      ticker: form.ticker.toUpperCase().trim(),
      shares: parseFloat(form.shares),
      bought_at: parseFloat(form.bought_at),
      stop:   form.stop   ? parseFloat(form.stop)   : null,
      target: form.target ? parseFloat(form.target) : null,
      date:   form.date,
      note:   form.note,
      status: 'open',
    });
    onClose();
  };

  return (
    <div className="modal-overlay">
      <div className="modal-box">
        <div className="modal-header">
          <div className="modal-title">NEW ENTRY</div>
          <button onClick={onClose} className="btn-icon-sm"><X size={15}/></button>
        </div>
        <div className="modal-grid">
          {[
            ['ticker','TICKER','text','NVDA'],
            ['shares','株数','number','10'],
            ['bought_at','取得価格','number','450.00'],
            ['date','取得日','date',''],
            ['stop','ストップ','number','430.00'],
            ['target','ターゲット','number','500.00'],
          ].map(([k, label, type, ph]) => (
            <div key={k} className="form-group">
              <label className="form-label">{label}</label>
              <input
                type={type}
                step={type==='number'?'0.01':undefined}
                value={form[k]}
                onChange={e => set(k, e.target.value)}
                placeholder={ph}
                className="form-input"
              />
            </div>
          ))}
        </div>
        <div className="form-group">
          <label className="form-label">MEMO</label>
          <input value={form.note} onChange={e => set('note', e.target.value)} className="form-input"/>
        </div>
        <button onClick={submit} className="btn-submit">RECORD ENTRY</button>
      </div>
    </div>
  );
}

function TradeRow({ t, price, score, onClose, onRemove }) {
  const cur  = price || t.bought_at;
  const pnlPct = ((cur - t.bought_at) / t.bought_at * 100);
  const pnlAmt = (cur - t.bought_at) * t.shares;
  const toStop   = t.stop   ? ((t.stop   - cur) / cur * 100) : null;
  const toTarget = t.target ? ((t.target - cur) / cur * 100) : null;

  return (
    <div className="trade-row">
      <div className="trade-top">
        <div className="trade-left">
          <div className="trade-ticker">{t.ticker}</div>
          <div className="trade-meta">{t.date} · {t.shares}株 · 取得 {fmt(t.bought_at)}</div>
          {score && (
            <div style={{display:'flex', gap:'6px', marginTop:'3px', flexWrap:'wrap'}}>
              <span style={{fontFamily:'monospace',fontSize:'9px',color:'#ffb800'}}>CMP {score.composite?.toFixed(0)}</span>
              <span style={{fontFamily:'monospace',fontSize:'9px',color:'#00ff88'}}>RS {score.rs}</span>
              <span style={{fontFamily:'monospace',fontSize:'9px',color:score.status==='ACTION'?'#00ff88':'#6b7a90'}}>{score.status}</span>
              {score.ecr_phase==='IGNITION'&&<span style={{fontFamily:'monospace',fontSize:'9px',color:'#00ff88',fontWeight:'bold'}}>⚡IGNITION</span>}
            </div>
          )}
        </div>
        <div className="trade-right">
          <div className="trade-pnl">
            <div className="trade-price">{fmt(cur)}</div>
            <div className={`trade-pnl-pct ${pnlPct >= 0 ? 'pnl-pos' : 'pnl-neg'}`}>
              {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}% ({pnlPct >= 0 ? '+' : ''}{fmt(pnlAmt)})
            </div>
          </div>
          <div className="trade-levels" style={{ display: 'none' }}>
            {t.stop && <div style={{color:'#ff3355'}}>S {fmt(t.stop)} ({toStop?.toFixed(1)}%)</div>}
            {t.target && <div style={{color:'#ffb800'}}>T {fmt(t.target)} ({toTarget?.toFixed(1) > 0 ? '+' : ''}{toTarget?.toFixed(1)}%)</div>}
          </div>
          <div className="trade-actions">
            <button onClick={() => onClose(t.id, cur)} className="btn-close">決済</button>
            <button onClick={() => onRemove(t.id)} className="btn-icon-sm danger"><Trash2 size={12}/></button>
          </div>
        </div>
      </div>
      {t.note && <div className="trade-note">{t.note}</div>}
    </div>
  );
}

export default function Portfolio() {
  const [trades,  setTrades]  = useState([]);
  const [storageReady, setStorageReady] = useState(false);

  useEffect(() => {
    loadTrades().then(d => { setTrades(d); setStorageReady(true); });
  }, []);
  const [showAdd, setShowAdd] = useState(false);

  const sentinelScores = useSentinelScores();
  const openTickers = trades.filter(t => t.status === 'open').map(t => t.ticker);
  const prices = useCurrentPrices(openTickers);

  // CSVエクスポート
  const exportCSV = () => {
    const closed = trades.filter(t => t.status === 'closed');
    const rows = [
      ['ticker','shares','bought_at','closed_at','date','close_date','pnl_pct','pnl_amt','note'],
      ...closed.map(t => {
        const pnlPct = t.closed_at ? ((t.closed_at - t.bought_at) / t.bought_at * 100).toFixed(2) : '';
        const pnlAmt = t.closed_at ? ((t.closed_at - t.bought_at) * t.shares).toFixed(2) : '';
        return [t.ticker, t.shares, t.bought_at, t.closed_at||'', t.date, t.close_date||'', pnlPct, pnlAmt, t.note||''];
      })
    ];
    const csv = rows.map(r => r.join(',')).join('\n');
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    a.download = `sentinel_trades_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  };

  const persist = (next) => { setTrades(next); saveTrades(next); };
  const addTrade    = (t)  => persist([...trades, t]);
  const removeTrade = (id) => persist(trades.filter(t => t.id !== id));
  const closeTrade  = (id, closePrice) =>
    persist(trades.map(t => t.id === id
      ? { ...t, status: 'closed', closed_at: closePrice, close_date: new Date().toISOString().slice(0,10) }
      : t
    ));

  const open   = trades.filter(t => t.status === 'open');
  const closed = trades.filter(t => t.status === 'closed');

  const totalCost  = open.reduce((s, t) => s + t.bought_at * t.shares, 0);
  const totalValue = open.reduce((s, t) => s + (prices[t.ticker] || t.bought_at) * t.shares, 0);
  const totalPnL   = totalValue - totalCost;
  const totalPnLPct = totalCost > 0 ? totalPnL / totalCost * 100 : 0;
  const closedPnL  = closed.reduce((s, t) => t.closed_at ? s + (t.closed_at - t.bought_at) * t.shares : s, 0);

  const allocationData = open.reduce((acc, t) => {
    const val = (prices[t.ticker] || t.bought_at) * t.shares;
    const ex = acc.find(a => a.name === t.ticker);
    if (ex) ex.value += val;
    else acc.push({ name: t.ticker, value: val });
    return acc;
  }, []);

  return (
    <div className="portfolio-page">
      {showAdd && <AddTradeModal onAdd={addTrade} onClose={() => setShowAdd(false)} />}

      <div className="page-header">
        <div>
          <h1 className="page-title-large">PORTFOLIO</h1>
          <div className="page-subtitle">保有 {open.length}銘柄 / 決済済 {closed.length}件</div>
        </div>
        <div style={{display:'flex', gap:'8px'}}>
          <button onClick={exportCSV} style={{background:'transparent',border:'1px solid #333',color:'#888',padding:'8px 14px',borderRadius:'4px',cursor:'pointer',fontSize:'11px',fontFamily:'monospace'}}>
            ↓ CSV
          </button>
          <button onClick={() => setShowAdd(true)} className="btn-primary">
            <Plus size={13}/> エントリー記録
          </button>
        </div>
      </div>

      {/* Summary */}
      <div className="summary-grid">
        {[
          { label:'評価額合計',  val: fmt(totalValue, 0),  sub: `元本 ${fmt(totalCost, 0)}`,         cls: '' },
          { label:'含み損益',    val: fmt(totalPnL, 0),    sub: `${totalPnLPct >= 0 ? '+' : ''}${totalPnLPct.toFixed(2)}%`, cls: totalPnL >= 0 ? 'pos' : 'neg' },
          { label:'確定損益',    val: fmt(closedPnL, 0),   sub: `${closed.length}件決済済`,           cls: closedPnL >= 0 ? 'pos' : 'neg' },
          { label:'保有銘柄数',  val: `${open.length}銘柄`, sub: 'OPEN',                               cls: '' },
        ].map((c, i) => (
          <div key={i} className="summary-card">
            <div className="summary-label">{c.label}</div>
            <div className={`summary-val ${c.cls}`}>{c.val}</div>
            <div className="summary-sub">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Holdings */}
      <div className={allocationData.length > 1 ? 'allocation-layout' : ''}>
        {allocationData.length > 1 && (
          <div className="card">
            <div className="card-header"><span className="label-tag">配分</span></div>
            <div style={{padding:'1rem'}}>
              <ResponsiveContainer width="100%" height={160}>
                <PieChart>
                  <Pie data={allocationData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={70}>
                    {allocationData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background:'#0c1220', border:'1px solid #1a2535', fontFamily:'Space Mono,monospace', fontSize:11 }}
                    formatter={(v) => [fmt(v,0),'']}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div style={{display:'flex',flexDirection:'column',gap:'0.3rem',marginTop:'0.5rem'}}>
                {allocationData.map((d, i) => (
                  <div key={i} style={{display:'flex',alignItems:'center',justifyContent:'space-between',fontFamily:'monospace',fontSize:'0.65rem'}}>
                    <div style={{display:'flex',alignItems:'center',gap:'0.4rem'}}>
                      <div style={{width:8,height:8,borderRadius:'50%',background:COLORS[i%COLORS.length]}}/>
                      <span style={{color:'var(--muted)'}}>{d.name}</span>
                    </div>
                    <span style={{color:'var(--text)'}}>{totalValue > 0 ? (d.value/totalValue*100).toFixed(1) : 0}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-header">
            <span className="label-tag">保有中 ({open.length})</span>
          </div>
          {open.length === 0 ? (
            <div className="empty-state">NO OPEN POSITIONS</div>
          ) : (
            open.map(t => (
              <TradeRow
                key={t.id}
                t={t}
                price={prices[t.ticker]}
                score={sentinelScores[t.ticker]}
                onClose={closeTrade}
                onRemove={removeTrade}
              />
            ))
          )}
        </div>
      </div>

      {/* Closed */}
      {closed.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="label-tag">決済済み ({closed.length})</span>
          </div>
          {closed.map(t => {
            const pnlPct = t.closed_at ? (t.closed_at - t.bought_at) / t.bought_at * 100 : 0;
            const pnlAmt = t.closed_at ? (t.closed_at - t.bought_at) * t.shares : 0;
            return (
              <div key={t.id} className="closed-row">
                <div>
                  <span className="closed-ticker">{t.ticker}</span>
                  <div className="closed-meta">{t.date} → {t.close_date} · {t.shares}株</div>
                </div>
                <div className={`closed-pnl ${pnlPct >= 0 ? 'pnl-pos' : 'pnl-neg'}`}>
                  {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                  <div style={{fontFamily:'monospace',fontSize:'0.65rem'}}>
                    {pnlAmt >= 0 ? '+' : ''}{fmt(pnlAmt)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
