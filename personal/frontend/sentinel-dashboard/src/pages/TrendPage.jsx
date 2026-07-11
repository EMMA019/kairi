import { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { ChevronUp, ChevronDown } from "lucide-react";

const MONO = { fontFamily: "'JetBrains Mono','Fira Code',monospace" };
const C = {
  green:"#00ff88", blue:"#00aaff", yellow:"#ffb800", red:"#ff3355",
  purple:"#aa66ff", orange:"#ff9500", dim:"#333", muted:"#555", sub:"#888",
};
const SCORE_COLORS = {
  composite:C.yellow, rs:C.green, ecr:C.blue,
  vcp:C.orange, ses:C.purple, canslim:"#ff6680",
};

function trendColor(v) {
  if (v > 5) return C.green; if (v > 1) return "#88ffcc";
  if (v > 0) return C.yellow; if (v > -2) return C.muted; return C.red;
}
function scoreColor(v) {
  if (v >= 70) return C.green; if (v >= 55) return C.blue;
  if (v >= 40) return C.yellow; return C.muted;
}
function DeltaBadge({ v }) {
  const icon = v > 0 ? "▲" : v < 0 ? "▼" : "—";
  const c = v > 1 ? C.green : v < -1 ? C.red : C.muted;
  return <span style={{ ...MONO, fontSize: 10, color: c }}>{icon}{Math.abs(v).toFixed(1)}</span>;
}

function Spark({ values, color, w=72, h=24 }) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values), max = Math.max(...values), range = max - min || 1;
  const pad = 2;
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * w;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const lv = values[values.length-1];
  const lx = w, ly = h - pad - ((lv - min) / range) * (h - pad * 2);
  return (
    <svg width={w} height={h} style={{ overflow:"visible", display:"block" }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" opacity={0.85}/>
      <circle cx={lx} cy={ly} r="2.5" fill={color}/>
    </svg>
  );
}

function Bar({ value, color, max=100 }) {
  return (
    <div style={{ display:"flex", alignItems:"center", gap:5 }}>
      <div style={{ width:48, height:3, background:"#1a1a1a", borderRadius:2 }}>
        <div style={{ width:`${Math.min(100,(value/max)*100)}%`, height:"100%", background:color||scoreColor(value), borderRadius:2 }}/>
      </div>
      <span style={{ ...MONO, fontSize:10, color:color||scoreColor(value), minWidth:22 }}>{value}</span>
    </div>
  );
}

function RankRow({ r, rank, selected, onSelect }) {
  const tc = trendColor(r.trend_score);
  return (
    <div onClick={() => onSelect(selected ? null : r.ticker)} style={{
      display:"grid", gridTemplateColumns:"28px 76px 120px 120px 100px 90px 60px",
      alignItems:"center", gap:10, padding:"9px 14px",
      background: selected ? `${tc}0c` : "#080808",
      border:`1px solid ${selected ? tc+"50" : "#161616"}`,
      borderLeft:`3px solid ${tc}`, borderRadius:5, cursor:"pointer",
    }}>
      <span style={{ ...MONO, fontSize:10, color:rank<=3?C.yellow:C.muted, textAlign:"center" }}>
        {rank<=3 ? ["🥇","🥈","🥉"][rank-1] : rank}
      </span>
      <div>
        <Link to={`/realtime/${r.ticker}`} onClick={e=>e.stopPropagation()}
          style={{ ...MONO, fontSize:14, fontWeight:"bold", color:tc, textDecoration:"none" }}>
          {r.ticker}
        </Link>
        <div style={{ ...MONO, fontSize:8, color:r.status==="ACTION"?C.green:C.dim, marginTop:1 }}>
          {r.status==="ACTION" ? "● ACTION" : "○ WAIT"}
        </div>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:4 }}>
        <Bar value={r.latest.rs}  color={C.green}/>
        <Bar value={r.latest.ecr} color={C.blue}/>
      </div>
      <div style={{ display:"flex", alignItems:"center", gap:8 }}>
        <div>
          <div style={{ ...MONO, fontSize:9, color:C.muted, marginBottom:2 }}>CMP</div>
          <span style={{ ...MONO, fontSize:13, fontWeight:"bold", color:scoreColor(r.latest.composite) }}>
            {r.latest.composite}
          </span>
        </div>
        <Spark values={r.history.slice(-10).map(h=>h.composite)} color={C.yellow} w={56} h={22}/>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:3 }}>
        {[["CMP",r.avg_cmp],["RS",r.avg_rs],["ECR",r.avg_ecr]].map(([l,v])=>(
          <div key={l} style={{ display:"flex", gap:6, alignItems:"center" }}>
            <span style={{ ...MONO, fontSize:8, color:C.muted, width:24 }}>{l}</span>
            <DeltaBadge v={v}/>
          </div>
        ))}
      </div>
      <div style={{ textAlign:"center" }}>
        <div style={{ ...MONO, fontSize:20, fontWeight:"bold", color:tc, lineHeight:1 }}>
          {r.trend_score>0?"+":""}{r.trend_score}
        </div>
        <div style={{ ...MONO, fontSize:7, color:C.muted, marginTop:2 }}>avg/day</div>
      </div>
      <div style={{ color:selected?tc:C.dim, textAlign:"right" }}>
        {selected ? <ChevronUp size={13}/> : <ChevronDown size={13}/>}
      </div>
    </div>
  );
}

function DetailChart({ r, dates }) {
  const [activeKeys, setActiveKeys] = useState(["composite","rs","ecr"]);
  const toggle = k => setActiveKeys(p => p.includes(k) ? p.filter(x=>x!==k) : [...p,k]);
  const tc = trendColor(r.trend_score);
  const keys = ["composite","rs","ecr","vcp","ses","canslim"];
  const W=480, H=140, PAD={t:14,r:16,b:28,l:32};
  const iW=W-PAD.l-PAD.r, iH=H-PAD.t-PAD.b, n=dates.length;

  function makeLine(key) {
    const vals = dates.map(d => r.history.find(x=>x.date===d)?.[key] ?? null);
    const valid = vals.filter(v=>v!==null);
    if (valid.length < 2) return null;
    const min=Math.min(...valid), max=Math.max(...valid), range=max-min||1;
    const pts = vals.map((v,i) => {
      if (v===null) return null;
      return [PAD.l+(i/(n-1))*iW, PAD.t+(1-(v-min)/range)*iH];
    }).filter(Boolean);
    return { pts, color: SCORE_COLORS[key] };
  }

  return (
    <div style={{ background:"#060606", border:`1px solid ${tc}30`, borderRadius:8, padding:"16px 18px", marginBottom:8 }}>
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:12 }}>
        <span style={{ ...MONO, fontSize:16, fontWeight:"bold", color:tc }}>{r.ticker}</span>
        <span style={{ ...MONO, fontSize:9, color:C.muted }}>{r.status}</span>
        <span style={{ ...MONO, fontSize:20, fontWeight:"bold", color:tc, marginLeft:"auto" }}>
          {r.trend_score>0?"+":""}{r.trend_score}
          <span style={{ fontSize:8, color:C.muted, marginLeft:4 }}>avg/day</span>
        </span>
      </div>
      <div style={{ display:"flex", gap:6, marginBottom:10, flexWrap:"wrap" }}>
        {keys.map(k => {
          const on=activeKeys.includes(k), c=SCORE_COLORS[k];
          return (
            <button key={k} onClick={()=>toggle(k)} style={{
              ...MONO, fontSize:9, padding:"3px 8px", borderRadius:3, cursor:"pointer",
              background:on?`${c}20`:"#0a0a0a", border:`1px solid ${on?c:C.dim}`,
              color:on?c:C.muted,
            }}>{k.toUpperCase()}</button>
          );
        })}
      </div>
      <div style={{ overflowX:"auto" }}>
        <svg width={W} height={H} style={{ display:"block" }}>
          {[0,.25,.5,.75,1].map(t=>(
            <line key={t} x1={PAD.l} x2={PAD.l+iW} y1={PAD.t+t*iH} y2={PAD.t+t*iH} stroke="#111" strokeWidth="1"/>
          ))}
          {dates.map((d,i)=>(
            <text key={d} x={PAD.l+(i/(n-1))*iW} y={H-4} textAnchor="middle"
              style={{ fill:C.muted, fontSize:8, fontFamily:"monospace" }}>
              {d.slice(5)}
            </text>
          ))}
          {keys.filter(k=>activeKeys.includes(k)).map(key=>{
            const line=makeLine(key); if(!line) return null;
            const {pts,color}=line;
            const d=pts.map((p,i)=>`${i===0?"M":"L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
            const lv=r.history[r.history.length-1]?.[key];
            return (
              <g key={key}>
                <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round"/>
                {pts.map((p,i)=><circle key={i} cx={p[0]} cy={p[1]} r="3" fill={color}/>)}
                {lv!=null && <text x={pts[pts.length-1][0]+5} y={pts[pts.length-1][1]+4}
                  style={{ fill:color, fontSize:9, fontFamily:"monospace", fontWeight:"bold" }}>{lv}</text>}
              </g>
            );
          })}
        </svg>
      </div>
      <div style={{ display:"flex", gap:14, flexWrap:"wrap", marginTop:10, paddingTop:10, borderTop:"1px solid #111", alignItems:"center" }}>
        {keys.map(k=>(
          <div key={k}>
            <div style={{ ...MONO, fontSize:8, color:C.muted, marginBottom:3 }}>{k.toUpperCase()}</div>
            <Bar value={r.history[r.history.length-1]?.[k]||0} color={SCORE_COLORS[k]}/>
          </div>
        ))}
        <Link to={`/realtime/${r.ticker}`} style={{
          ...MONO, fontSize:10, color:tc, textDecoration:"none",
          border:`1px solid ${tc}40`, padding:"5px 12px", borderRadius:3, marginLeft:"auto",
        }}>REALTIME →</Link>
      </div>
    </div>
  );
}

export default function TrendPage() {
  const [historyData, setHistoryData] = useState({});
  const [loading, setLoading]         = useState(true);
  const [selected, setSelected]       = useState(null);
  const [minRS,    setMinRS]          = useState(88);
  const [minECR,   setMinECR]         = useState(60);
  const [minCMP,   setMinCMP]         = useState(55);
  const [actionOnly, setActionOnly]   = useState(false);
  const [sortKey,  setSortKey]        = useState("trend");

  useEffect(() => {
    (async () => {
      try {
        // trend_data.json を1回読むだけ（generate_trend_data.py が生成）
        const res = await fetch("/content/strategies_history/trend_data.json");
        if (!res.ok) throw new Error("trend_data.json not found");
        const trendData = await res.json();

        // { date: { ticker: item } } 形式に変換
        const loaded = {};
        trendData.dates.forEach(date => { loaded[date] = {}; });
        Object.entries(trendData.tickers).forEach(([ticker, history]) => {
          history.forEach(h => {
            if (loaded[h.date]) {
              loaded[h.date][ticker] = { scores: { composite: h.composite, rs: h.rs, ecr_rank: h.ecr, vcp: h.vcp, ses: h.ses, canslim: h.canslim }, status: h.status };
            }
          });
        });
        setHistoryData(loaded);
      } finally { setLoading(false); }
    })();
  }, []);

  const { candidates, dates } = useMemo(() => {
    const dates = Object.keys(historyData).sort();
    if (dates.length < 2) return { candidates:[], dates };
    const last = dates[dates.length-1];
    const results = [];

    for (const ticker of Object.keys(historyData[last]||{})) {
      const history = dates.map(d => {
        const item = historyData[d]?.[ticker];
        if (!item) return null;
        const s = item.scores;
        return {
          date:d,
          composite: Math.round((s.composite||0)*10)/10,
          rs: s.rs||0, ecr: s.ecr_rank||0,
          vcp: s.vcp||0, ses: s.ses||0, canslim: s.canslim||0,
        };
      }).filter(Boolean);

      if (history.length < 2) continue;
      // 直近10日のみ使用（初動把握）
      const recentHistory = history.slice(-10);

      const diffs = { composite:[], rs:[], ecr:[] };
      for (let i=1; i<recentHistory.length; i++) {
        diffs.composite.push(recentHistory[i].composite - recentHistory[i-1].composite);
        diffs.rs.push(recentHistory[i].rs - recentHistory[i-1].rs);
        diffs.ecr.push(recentHistory[i].ecr - recentHistory[i-1].ecr);
      }
      const avg = k => diffs[k].reduce((a,b)=>a+b,0)/diffs[k].length;
      const ac=avg("composite"), ar=avg("rs"), ae=avg("ecr");
      const trend = ac*0.4 + ar*0.4 + ae*0.2;
      const latest = recentHistory[recentHistory.length-1];

      results.push({
        ticker, history, latest,
        status: historyData[last][ticker]?.status||"WAIT",
        avg_cmp: Math.round(ac*10)/10,
        avg_rs:  Math.round(ar*10)/10,
        avg_ecr: Math.round(ae*10)/10,
        trend_score: Math.round(trend*10)/10,
      });
    }
    return { candidates:results, dates };
  }, [historyData]);

  const filtered = useMemo(() => candidates
    .filter(r => r.latest.rs>=minRS && r.latest.ecr>=minECR && r.latest.composite>=minCMP && (!actionOnly||r.status==="ACTION"))
    .sort((a,b) => {
      if (sortKey==="trend") return b.trend_score - a.trend_score;
      if (sortKey==="rs")    return b.latest.rs - a.latest.rs;
      if (sortKey==="ecr")   return b.latest.ecr - a.latest.ecr;
      if (sortKey==="cmp")   return b.latest.composite - a.latest.composite;
      return 0;
    }), [candidates, minRS, minECR, minCMP, actionOnly, sortKey]);

  const selectedData = filtered.find(r=>r.ticker===selected)||null;

  if (loading) return (
    <div style={{ padding:60, textAlign:"center", ...MONO, color:C.muted, fontSize:12 }}>
      履歴データ読み込み中...
    </div>
  );

  return (
    <div style={{ maxWidth:1060, margin:"0 auto", padding:"24px 16px", color:"#fff" }}>

      {/* ヘッダー */}
      <div style={{ marginBottom:20 }}>
        <div style={{ display:"flex", alignItems:"baseline", gap:12, marginBottom:4 }}>
          <h1 style={{ ...MONO, fontSize:20, fontWeight:"bold", color:C.green, margin:0 }}>TREND_SCANNER</h1>
          <span style={{ ...MONO, fontSize:10, color:C.muted }}>
            {dates[0]} → {dates[dates.length-1]}（{dates.length}日 / {candidates.length}銘柄）
          </span>
        </div>
        <p style={{ ...MONO, fontSize:9, color:C.dim, margin:0 }}>
          隣接日間の平均変化率でトレンドをスコアリング — 資金が集まりつつある銘柄を早期検出
        </p>
      </div>

      {/* フィルター */}
      <div style={{ background:"#070707", border:"1px solid #181818", borderLeft:`3px solid ${C.blue}`, borderRadius:5, padding:"12px 16px", marginBottom:18 }}>
        <div style={{ display:"flex", flexWrap:"wrap", gap:20, alignItems:"flex-end" }}>
          {[["MIN_RS",minRS,setMinRS,99,C.green],["MIN_ECR",minECR,setMinECR,80,C.blue],["MIN_CMP",minCMP,setMinCMP,100,C.yellow]].map(([l,v,s,max,c])=>(
            <div key={l} style={{ minWidth:130 }}>
              <label style={{ ...MONO, fontSize:9, color:c, display:"block", marginBottom:4 }}>// {l}: {v}</label>
              <input type="range" min={0} max={max} value={v} onChange={e=>s(+e.target.value)}
                style={{ width:"100%", accentColor:c }}/>
            </div>
          ))}
          <button onClick={()=>setActionOnly(v=>!v)} style={{
            ...MONO, fontSize:9, padding:"5px 12px", borderRadius:3, cursor:"pointer",
            background:actionOnly?"#00ff8820":"#0a0a0a",
            border:`1px solid ${actionOnly?C.green:C.dim}`,
            color:actionOnly?C.green:C.muted,
          }}>ACTION ONLY</button>
          <div style={{ display:"flex", gap:4 }}>
            {[["trend","TREND"],["rs","RS"],["ecr","ECR"],["cmp","CMP"]].map(([k,l])=>(
              <button key={k} onClick={()=>setSortKey(k)} style={{
                ...MONO, fontSize:9, padding:"4px 8px", borderRadius:3, cursor:"pointer",
                background:sortKey===k?"#00aaff18":"#0a0a0a",
                border:`1px solid ${sortKey===k?C.blue:C.dim}`,
                color:sortKey===k?C.blue:C.muted,
              }}>{l}</button>
            ))}
          </div>
          <span style={{ ...MONO, fontSize:10, color:C.muted, marginLeft:"auto" }}>
            <span style={{ fontSize:16, color:C.blue, fontWeight:"bold" }}>{filtered.length}</span> 銘柄
          </span>
        </div>
      </div>

      {/* TOP3ハイライト */}
      {filtered.length > 0 && (
        <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:8, marginBottom:14 }}>
          {filtered.slice(0,3).map((r,i)=>{
            const tc=trendColor(r.trend_score);
            return (
              <div key={r.ticker} onClick={()=>setSelected(selected===r.ticker?null:r.ticker)} style={{
                background:selected===r.ticker?`${tc}12`:`${tc}06`,
                border:`1px solid ${selected===r.ticker?tc+"60":tc+"25"}`,
                borderRadius:6, padding:"12px 14px", cursor:"pointer", position:"relative",
              }}>
                <div style={{ position:"absolute", top:8, right:10, fontSize:18, opacity:0.12 }}>
                  {["🥇","🥈","🥉"][i]}
                </div>
                <div style={{ ...MONO, fontSize:18, fontWeight:"bold", color:tc }}>{r.ticker}</div>
                <div style={{ ...MONO, fontSize:9, color:C.muted, margin:"3px 0 6px" }}>
                  RS {r.latest.rs} · ECR {r.latest.ecr} · CMP {r.latest.composite}
                </div>
                <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                  <span style={{ ...MONO, fontSize:22, fontWeight:"bold", color:tc }}>
                    {r.trend_score>0?"+":""}{r.trend_score}
                  </span>
                  <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
                    <DeltaBadge v={r.avg_cmp}/><DeltaBadge v={r.avg_rs}/>
                  </div>
                  <div style={{ marginLeft:"auto" }}>
                    <Spark values={r.history.slice(-10).map(h=>h.composite)} color={tc} w={52} h={20}/>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* テーブルヘッダー */}
      <div style={{ display:"grid", gridTemplateColumns:"28px 76px 120px 120px 100px 90px 60px", gap:10, padding:"4px 14px 6px", borderBottom:"1px solid #1a1a1a" }}>
        {["#","TICKER","RS / ECR","COMPOSITE","Δ AVG/DAY","TREND",""].map((l,i)=>(
          <span key={i} style={{ ...MONO, fontSize:8, color:C.muted }}>{l}</span>
        ))}
      </div>

      {/* ランキングリスト */}
      <div style={{ display:"flex", flexDirection:"column", gap:4, marginTop:6 }}>
        {filtered.length===0 ? (
          <div style={{ ...MONO, fontSize:11, color:C.muted, textAlign:"center", padding:40 }}>
            条件に合う銘柄なし — フィルターを緩めてください
          </div>
        ) : filtered.map((r,i)=>(
          <RankRow key={r.ticker} r={r} rank={i+1} selected={selected===r.ticker} onSelect={setSelected}/>
        ))}
      </div>

      {/* 個別チャート */}
      {selectedData && (
        <div style={{ marginTop:24, borderTop:"1px solid #1a1a1a", paddingTop:20 }}>
          <div style={{ ...MONO, fontSize:9, color:C.muted, marginBottom:10 }}>
            // DETAIL_CHART — {selectedData.ticker}（直近{Math.min(10,dates.length)}日）
          </div>
          <DetailChart r={selectedData} dates={dates.slice(-10)}/>
        </div>
      )}

    </div>
  );
}
