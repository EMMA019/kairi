import React, { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { BarChart2, TrendingUp, TrendingDown, Award } from 'lucide-react';

const mono = { fontFamily: 'Consolas, "Courier New", monospace' };
const clr  = n => n > 0 ? '#00ff88' : n < 0 ? '#ff3355' : '#6b7a90';
const pp   = n => n != null ? `${n >= 0 ? '+' : ''}${Number(n).toFixed(2)}%` : '—';
const r1   = n => Number(n).toFixed(1);

const SCORE_COLORS = { composite:'#ffb800', vcp:'#00aaff', rs:'#00ff88', ecr:'#ffb800', canslim:'#aa66ff' };
const BANDS = ['0-30','30-40','40-50','50-60','60-70','70-80','80-110'];

async function loadAllBacktests() {
  try {
    const idx = await fetch('/content/index.json').then(r => r.json());
    const slugs = (idx.articles || [])
      .filter(a => a.type === 'backtest' || a.type === 'weekly')
      .sort((a, b) => b.date.localeCompare(a.date));

    if (slugs.length > 0) {
      const results = await Promise.all(
        slugs.slice(0,12).map(a =>
          fetch(`/content/${a.slug}.json`).then(r => r.json())
            .then(d => ({ ...d, _slug: a.slug, _date: a.date })).catch(() => null)
        )
      );
      const valid = results.filter(Boolean);
      if (valid.length > 0) return valid;
    }
  } catch {}
  try {
    const w = await fetch('/content/weekly_check.json').then(r => r.json());
    return [{ ...w, _slug: 'weekly_check' }];
  } catch { return []; }
}

function MiniBar({ value, max }) {
  const absMax = Math.max(Math.abs(max), 0.01);
  const pct = Math.abs(value) / absMax * 50;
  return (
    <div style={{ position:'relative', height:8, background:'#111', borderRadius:4, width:'100%' }}>
      <div style={{ position:'absolute', left:'50%', top:0, width:1, height:'100%', background:'#333' }}/>
      <div style={{ position:'absolute', left: value>=0?'50%':`${50-pct}%`, width:`${pct}%`, height:'100%', background: value>=0?'#00ff88':'#ff3355', borderRadius:2, opacity:.85 }}/>
    </div>
  );
}

function TrendChart({ sessions }) {
  if (sessions.length < 2) return (
    <div style={{ ...mono, fontSize:10, color:'#333', textAlign:'center', padding:'20px 0' }}>
      2件以上蓄積で累積トレンド表示
    </div>
  );
  const W=560, H=100, P=28;
  const data = [...sessions].reverse().map((s,i) => ({
    action: s.by_status?.ACTION?.real?.avg ?? 0,
    all:    s.summary?.avg_real_ret ?? 0,
    spy:    s.spy?.close_ret ?? 0,
    label:  (s.signal_date ?? s._date ?? '').slice(5),
  }));
  const allVals = data.flatMap(d => [d.action, d.all, d.spy]);
  const minY = Math.min(...allVals)-1, maxY = Math.max(...allVals)+1;
  const sx = i => P + (i/(data.length-1))*(W-P*2);
  const sy = v => H-P - ((v-minY)/(maxY-minY))*(H-P*2);
  const path = key => data.map((d,i) => `${i===0?'M':'L'}${sx(i)},${sy(d[key])}`).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width:'100%', height:H }}>
      <line x1={P} y1={sy(0)} x2={W-P} y2={sy(0)} stroke="#333" strokeDasharray="3,3" strokeWidth={1}/>
      <path d={path('spy')}    fill="none" stroke="#444" strokeWidth={1.5} strokeDasharray="4,3"/>
      <path d={path('all')}    fill="none" stroke="#00aaff" strokeWidth={1.5}/>
      <path d={path('action')} fill="none" stroke="#00ff88" strokeWidth={2}/>
      {data.map((d,i) => (
        <g key={i}>
          <circle cx={sx(i)} cy={sy(d.action)} r={3} fill="#00ff88"/>
          <text x={sx(i)} y={H-3} textAnchor="middle" fill="#444" fontSize={8} fontFamily="monospace">{d.label}</text>
        </g>
      ))}
      <g transform={`translate(${P},8)`}>
        <line x1={0} y1={4} x2={12} y2={4} stroke="#00ff88" strokeWidth={2}/>
        <text x={15} y={8} fill="#00ff88" fontSize={8} fontFamily="monospace">ACTION</text>
        <line x1={65} y1={4} x2={77} y2={4} stroke="#00aaff" strokeWidth={1.5}/>
        <text x={80} y={8} fill="#00aaff" fontSize={8} fontFamily="monospace">ALL</text>
        <line x1={106} y1={4} x2={118} y2={4} stroke="#444" strokeWidth={1.5} strokeDasharray="4,3"/>
        <text x={121} y={8} fill="#555" fontSize={8} fontFamily="monospace">SPY</text>
      </g>
    </svg>
  );
}

function BandTable({ sessions, scoreKey }) {
  const agg = useMemo(() => {
    const res = {};
    BANDS.forEach(band => {
      const all = sessions.map(s => s.by_score?.[scoreKey]?.[band]).filter(Boolean);
      if (!all.length) return;
      res[band] = {
        n:        all.reduce((s,b)=>s+(b.n||0),0),
        sessions: all.length,
        avg_real: all.reduce((s,b)=>s+(b.real?.avg||0),0)/all.length,
        win_rate: all.reduce((s,b)=>s+(b.real?.win_rate||0),0)/all.length,
        avg_mfe:  all.reduce((s,b)=>s+(b.mfe?.avg||0),0)/all.length,
        avg_mae:  all.reduce((s,b)=>s+(b.mae?.avg||0),0)/all.length,
      };
    });
    return res;
  }, [sessions, scoreKey]);

  const absMax = Math.max(...Object.values(agg).map(b=>Math.abs(b.avg_real)), 0.01);
  const bestBand = Object.entries(agg).sort((a,b)=>b[1].avg_real-a[1].avg_real)[0]?.[0];

  return (
    <div style={{ background:'#0a0a0a', border:'1px solid #111', borderRadius:8, overflow:'hidden' }}>
      <div style={{ display:'grid', gridTemplateColumns:'68px 1fr 58px 54px 50px 50px 40px', gap:6, padding:'7px 12px', borderBottom:'1px solid #111', ...mono, fontSize:9, color:'#333' }}>
        <span>BAND</span><span>平均REAL%</span><span style={{textAlign:'right'}}>WIN%</span><span style={{textAlign:'right'}}>MFE</span><span style={{textAlign:'right'}}>MAE</span><span style={{textAlign:'right'}}>N</span><span style={{textAlign:'right'}}>回</span>
      </div>
      {Object.entries(agg).map(([band,b]) => (
        <div key={band} style={{ display:'grid', gridTemplateColumns:'68px 1fr 58px 54px 50px 50px 40px', gap:6, padding:'6px 12px', borderBottom:'1px solid #0d0d0d', alignItems:'center', background: band===bestBand?'#0a1408':'transparent' }}>
          <span style={{ ...mono, fontSize:10, color: band===bestBand?'#00ff88':'#777', fontWeight: band===bestBand?'bold':'normal' }}>{band}{band===bestBand?' ★':''}</span>
          <div style={{ display:'flex', alignItems:'center', gap:6 }}>
            <MiniBar value={b.avg_real} max={absMax}/>
            <span style={{ ...mono, fontSize:10, color:clr(b.avg_real), fontWeight:'bold', minWidth:42, textAlign:'right' }}>{pp(b.avg_real)}</span>
          </div>
          <span style={{ ...mono, fontSize:10, color:b.win_rate>=55?'#00ff88':b.win_rate>=45?'#ffb800':'#ff3355', textAlign:'right' }}>{r1(b.win_rate)}%</span>
          <span style={{ ...mono, fontSize:10, color:'#00ff88', textAlign:'right' }}>+{r1(b.avg_mfe)}%</span>
          <span style={{ ...mono, fontSize:10, color:'#ff3355', textAlign:'right' }}>-{r1(b.avg_mae)}%</span>
          <span style={{ ...mono, fontSize:9, color:'#444', textAlign:'right' }}>{b.n}</span>
          <span style={{ ...mono, fontSize:9, color:'#333', textAlign:'right' }}>{b.sessions}</span>
        </div>
      ))}
    </div>
  );
}

function AllTable({ rows }) {
  const [sortKey,setSortKey] = useState('real_ret');
  const [sortDir,setSortDir] = useState(-1);
  const [filter, setFilter]  = useState('ALL');
  const [page,   setPage]    = useState(0);
  const PER = 30;

  const sorted = useMemo(() =>
    [...rows].filter(r=>filter==='ALL'||r.status===filter)
      .sort((a,b)=>sortDir*((a[sortKey]??0)>(b[sortKey]??0)?1:-1))
  , [rows,filter,sortKey,sortDir]);

  const paged = sorted.slice(page*PER,(page+1)*PER);
  const pages = Math.ceil(sorted.length/PER);
  const th = (key,lbl) => (
    <th onClick={()=>{setSortKey(key);setSortDir(sortKey===key?-sortDir:-1);setPage(0);}}
      style={{...mono,fontSize:9,color:sortKey===key?'#fff':'#444',padding:'6px 8px',cursor:'pointer',whiteSpace:'nowrap',textAlign:'left',borderBottom:'1px solid #111',background:'#080808'}}>
      {lbl}{sortKey===key?(sortDir>0?' ▲':' ▼'):''}
    </th>
  );

  return (
    <div>
      <div style={{display:'flex',gap:6,marginBottom:10,alignItems:'center'}}>
        {['ALL','ACTION','WAIT'].map(f=>(
          <button key={f} onClick={()=>{setFilter(f);setPage(0);}} style={{...mono,fontSize:9,background:filter===f?'#1a1a1a':'#080808',border:`1px solid ${filter===f?'#333':'#111'}`,color:filter===f?'#fff':'#444',padding:'4px 10px',borderRadius:4,cursor:'pointer'}}>{f}</button>
        ))}
        <span style={{...mono,fontSize:9,color:'#444'}}>{sorted.length}件</span>
      </div>
      <div style={{overflowX:'auto'}}>
        <table style={{width:'100%',borderCollapse:'collapse'}}>
          <thead><tr>{th('ticker','銘柄')}{th('status','ST')}{th('composite','CMP')}{th('rs','RS')}{th('close_ret','終値%')}{th('real_ret','実態%')}{th('mfe_pct','MFE↑')}{th('mae_pct','MAE↓')}<th style={{...mono,fontSize:9,color:'#333',padding:'6px 8px',borderBottom:'1px solid #111',background:'#080808'}}>STOP</th></tr></thead>
          <tbody>
            {paged.map((r,i)=>(
              <tr key={i} style={{borderBottom:'1px solid #080808',background:i%2?'#030303':'transparent'}}>
                <td style={{padding:'5px 8px'}}><Link to={`/realtime/${r.ticker}`} style={{...mono,fontSize:11,color:'#fff',fontWeight:'bold',textDecoration:'none'}}>{r.ticker}</Link></td>
                <td style={{padding:'5px 8px'}}><span style={{...mono,fontSize:8,color:r.status==='ACTION'?'#00ff88':'#ffb800',background:r.status==='ACTION'?'#00ff8812':'#ffb80012',padding:'1px 5px',borderRadius:3}}>{r.status}</span></td>
                <td style={{...mono,fontSize:10,color:'#ffb800',padding:'5px 8px'}}>{r.composite}</td>
                <td style={{...mono,fontSize:10,color:'#00ff88',padding:'5px 8px'}}>{r.rs}</td>
                <td style={{...mono,fontSize:10,color:clr(r.close_ret),padding:'5px 8px'}}>{pp(r.close_ret)}</td>
                <td style={{...mono,fontSize:10,color:clr(r.real_ret),fontWeight:'bold',padding:'5px 8px'}}>{pp(r.real_ret)}</td>
                <td style={{...mono,fontSize:10,color:'#00ff88',padding:'5px 8px'}}>+{r1(r.mfe_pct??0)}%</td>
                <td style={{...mono,fontSize:10,color:'#ff3355',padding:'5px 8px'}}>-{r1(r.mae_pct??0)}%</td>
                <td style={{padding:'5px 8px'}}>{r.stop_hit?<span style={{...mono,fontSize:8,color:'#ff3355',background:'#ff335512',padding:'1px 4px',borderRadius:3}}>HIT</span>:<span style={{color:'#1a1a1a'}}>—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages>1&&<div style={{display:'flex',gap:10,justifyContent:'center',alignItems:'center',marginTop:10}}>
        <button disabled={page===0} onClick={()=>setPage(p=>p-1)} style={{...mono,fontSize:10,background:'none',border:'1px solid #1a1a1a',color:page===0?'#1a1a1a':'#555',padding:'4px 12px',borderRadius:4,cursor:page===0?'not-allowed':'pointer'}}>← PREV</button>
        <span style={{...mono,fontSize:9,color:'#444'}}>{page+1}/{pages}</span>
        <button disabled={page===pages-1} onClick={()=>setPage(p=>p+1)} style={{...mono,fontSize:10,background:'none',border:'1px solid #1a1a1a',color:page===pages-1?'#1a1a1a':'#555',padding:'4px 12px',borderRadius:4,cursor:page===pages-1?'not-allowed':'pointer'}}>NEXT →</button>
      </div>}
    </div>
  );
}

function SessionSummary({ s }) {
  const act = s.by_status?.ACTION;
  const sum = s.summary || {};
  const kpis = [
    { l:'ACTION avg',  v:pp(act?.real?.avg),          c:clr(act?.real?.avg) },
    { l:'ACTION win%', v:`${r1(act?.real?.win_rate??0)}%`, c:(act?.real?.win_rate??0)>=50?'#00ff88':'#ff3355' },
    { l:'全体勝率',     v:`${r1(sum.real_win_rate??0)}%`,  c:(sum.real_win_rate??0)>=50?'#00ff88':'#ff3355' },
    { l:'avg MFE',     v:`+${r1(sum.avg_mfe??0)}%`,   c:'#00ff88' },
    { l:'avg MAE',     v:`-${r1(sum.avg_mae??0)}%`,   c:'#ff3355' },
    { l:'Stop到達率',  v:`${r1(sum.stop_hit_rate??0)}%`, c:(sum.stop_hit_rate??0)>30?'#ff3355':'#888' },
    { l:'SPY超え',     v:`${r1(sum.beat_spy_real??0)}%`,  c:(sum.beat_spy_real??0)>50?'#00ff88':'#888' },
    { l:'対象銘柄数',  v:`${sum.total??0}`,            c:'#888' },
  ];
  return (
    <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:6,marginBottom:14}}>
      {kpis.map(({l,v,c})=>(
        <div key={l} style={{background:'#080808',border:'1px solid #111',borderRadius:6,padding:'8px 10px'}}>
          <div style={{...mono,fontSize:8,color:'#444',marginBottom:3}}>{l}</div>
          <div style={{...mono,fontSize:13,fontWeight:'bold',color:c}}>{v}</div>
        </div>
      ))}
    </div>
  );
}

export default function BacktestPage() {
  const [sessions,setSessions] = useState([]);
  const [loading, setLoading]  = useState(true);
  const [selected,setSelected] = useState(0);
  const [view,    setView]     = useState('detail');
  const [scoreKey,setScoreKey] = useState('composite');
  const [tab,     setTab]      = useState('bands');

  useEffect(() => {
    loadAllBacktests().then(d => { setSessions(d); setLoading(false); });
  }, []);

  if (loading) return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',height:'60vh',...mono,color:'#00ff88',fontSize:13,letterSpacing:3}}>
      LOADING BACKTEST DATA...
    </div>
  );

  if (!sessions.length) return (
    <div style={{display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',height:'60vh',gap:14}}>
      <BarChart2 size={28} color="#333"/>
      <div style={{...mono,color:'#444',fontSize:12}}>バックテストデータがありません</div>
      <code style={{background:'#0a0a0a',border:'1px solid #1a1a1a',borderRadius:6,padding:'8px 14px',...mono,fontSize:11,color:'#00ff88'}}>
        python scripts/weekly_check.py --date YYYY-MM-DD
      </code>
    </div>
  );

  const cur = sessions[selected];
  const bestBand = (() => {
    const agg = {};
    BANDS.forEach(band=>{
      const all=sessions.map(s=>s.by_score?.[scoreKey]?.[band]).filter(Boolean);
      if(all.length) agg[band]={avg:all.reduce((s,b)=>s+(b.real?.avg||0),0)/all.length};
    });
    return Object.entries(agg).sort((a,b)=>b[1].avg-a[1].avg)[0];
  })();

  return (
    <div style={{padding:'20px 24px',background:'#000',minHeight:'100vh',color:'#fff'}}>

      {/* ヘッダー */}
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:20,borderBottom:'1px solid #111',paddingBottom:16}}>
        <div>
          <h1 style={{margin:0,...mono,fontSize:20,fontWeight:900,letterSpacing:4,display:'flex',alignItems:'center',gap:10}}>
            <BarChart2 size={18} color="#ffb800"/> BACKTEST_ANALYSIS
          </h1>
          <div style={{...mono,fontSize:10,color:'#444',marginTop:6}}>
            {sessions.length}セッション蓄積 · weekly_check.py 出力を自動集約
          </div>
        </div>
        <div style={{display:'flex',gap:6}}>
          {[['detail','単体分析'],['cumulative','累積分析']].map(([k,l])=>(
            <button key={k} onClick={()=>setView(k)} style={{...mono,fontSize:10,background:view===k?'#ffb80015':'#0a0a0a',border:`1px solid ${view===k?'#ffb800':'#222'}`,color:view===k?'#ffb800':'#555',padding:'7px 14px',borderRadius:4,cursor:'pointer'}}>{l}</button>
          ))}
        </div>
      </div>

      <div style={{display:'grid',gridTemplateColumns:'200px 1fr',gap:16,alignItems:'start'}}>

        {/* セッションリスト */}
        <div style={{display:'flex',flexDirection:'column',gap:5,position:'sticky',top:20}}>
          <div style={{...mono,fontSize:9,color:'#333',marginBottom:4}}>SESSIONS</div>
          {sessions.map((s,i)=>{
            const act=s.by_status?.ACTION?.real?.avg??0;
            return (
              <button key={i} onClick={()=>setSelected(i)} style={{textAlign:'left',background:selected===i?'#0a1408':'#080808',border:`1px solid ${selected===i?'#00ff88':'#111'}`,borderRadius:5,padding:'8px 10px',cursor:'pointer'}}>
                <div style={{...mono,fontSize:10,color:'#fff',fontWeight:'bold',marginBottom:3}}>
                  {s.signal_date??s._date??s._slug}
                </div>
                <div style={{display:'flex',gap:8}}>
                  <span style={{...mono,fontSize:9,color:clr(act)}}>ACTION {pp(act)}</span>
                  <span style={{...mono,fontSize:9,color:'#333'}}>{s.hold_days??'?'}日</span>
                </div>
              </button>
            );
          })}
        </div>

        {/* メイン */}
        <div style={{display:'flex',flexDirection:'column',gap:14}}>

          {view==='detail' && cur && (
            <>
              <SessionSummary s={cur}/>

              {/* タブ */}
              <div style={{display:'flex',gap:4,borderBottom:'1px solid #111'}}>
                {[['bands','スコア帯別'],['top','TOP/BOTTOM'],['all','全明細']].map(([k,l])=>(
                  <button key={k} onClick={()=>setTab(k)} style={{...mono,fontSize:10,background:'none',border:'none',cursor:'pointer',color:tab===k?'#ffb800':'#444',borderBottom:`2px solid ${tab===k?'#ffb800':'transparent'}`,padding:'6px 12px',marginBottom:-1}}>
                    {l}
                  </button>
                ))}
              </div>

              {tab==='bands'&&(
                <>
                  <div style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                    {Object.keys(SCORE_COLORS).map(k=>(
                      <button key={k} onClick={()=>setScoreKey(k)} style={{...mono,fontSize:9,background:scoreKey===k?`${SCORE_COLORS[k]}15`:'#0a0a0a',border:`1px solid ${scoreKey===k?SCORE_COLORS[k]:'#1a1a1a'}`,color:scoreKey===k?SCORE_COLORS[k]:'#555',padding:'4px 10px',borderRadius:4,cursor:'pointer'}}>
                        {k.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  <BandTable sessions={[cur]} scoreKey={scoreKey}/>
                </>
              )}

              {tab==='top'&&(
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:10}}>
                  {[{title:'🏆 TOP10 実態%',rows:cur.top10||[],col:'#00ff88'},{title:'💀 BOTTOM10',rows:cur.bottom10||[],col:'#ff3355'}].map(({title,rows,col})=>(
                    <div key={title}>
                      <div style={{...mono,fontSize:9,color:col,marginBottom:6}}>{title}</div>
                      {rows.map((r,i)=>(
                        <div key={i} style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'4px 8px',background:'#080808',borderRadius:4,borderLeft:`2px solid ${col}30`,marginBottom:4}}>
                          <div style={{display:'flex',gap:8,alignItems:'center'}}>
                            <span style={{...mono,fontSize:9,color:'#444'}}>{i+1}</span>
                            <Link to={`/realtime/${r.ticker}`} style={{...mono,fontSize:11,color:'#fff',fontWeight:'bold',textDecoration:'none'}}>{r.ticker}</Link>
                            <span style={{...mono,fontSize:8,color:'#444'}}>C{r.composite} RS{r.rs}</span>
                          </div>
                          <span style={{...mono,fontSize:11,color:col,fontWeight:'bold'}}>{pp(r.real_ret)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}

              {tab==='all'&&<AllTable rows={cur.all_results||[]}/>}
            </>
          )}

          {view==='cumulative'&&(
            <>
              {/* インサイト */}
              {bestBand&&(
                <div style={{background:'#0a1408',border:'1px solid #00ff8825',borderLeft:'3px solid #00ff88',borderRadius:6,padding:'12px 14px'}}>
                  <div style={{...mono,fontSize:9,color:'#00ff88',marginBottom:4}}>💡 CUMULATIVE INSIGHT — {sessions.length}セッション統計</div>
                  <div style={{...mono,fontSize:11,color:'#fff'}}>
                    {scoreKey.toUpperCase()} スコア <span style={{color:'#00ff88',fontWeight:'bold'}}>{bestBand[0]}</span> 帯が最優秀
                    → 平均実態リターン <span style={{color:'#00ff88',fontWeight:'bold'}}>{pp(bestBand[1].avg)}</span>
                  </div>
                </div>
              )}

              <div style={{display:'flex',gap:5,flexWrap:'wrap'}}>
                {Object.keys(SCORE_COLORS).map(k=>(
                  <button key={k} onClick={()=>setScoreKey(k)} style={{...mono,fontSize:9,background:scoreKey===k?`${SCORE_COLORS[k]}15`:'#0a0a0a',border:`1px solid ${scoreKey===k?SCORE_COLORS[k]:'#1a1a1a'}`,color:scoreKey===k?SCORE_COLORS[k]:'#555',padding:'4px 10px',borderRadius:4,cursor:'pointer'}}>
                    {k.toUpperCase()}
                  </button>
                ))}
              </div>

              <BandTable sessions={sessions} scoreKey={scoreKey}/>

              <div style={{background:'#0a0a0a',border:'1px solid #111',borderRadius:8,padding:14}}>
                <div style={{...mono,fontSize:9,color:'#444',marginBottom:10}}>ACTION vs ALL vs SPY リターン推移</div>
                <TrendChart sessions={sessions}/>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
