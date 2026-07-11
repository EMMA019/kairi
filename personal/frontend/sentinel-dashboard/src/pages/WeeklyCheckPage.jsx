import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { TrendingUp, TrendingDown, BarChart2, Award, AlertTriangle, Target, Shield } from 'lucide-react';

const clr  = (n) => n > 0 ? '#00ff88' : n < 0 ? '#ff3355' : '#6b7a90';
const pp   = (n) => `${n >= 0 ? '+' : ''}${Number(n).toFixed(2)}%`;
const r1   = (n) => Number(n).toFixed(1);
const SCORE_COLORS = { composite:'#e8f0f8', vcp:'#00ff88', rs:'#4499ff', ecr:'#ffb800', canslim:'#aa66ff' };
const SCORE_KEYS   = ['composite','vcp','rs','ecr','canslim'];

/* ── KPI Card ───────────────────────────────────────────── */
function Kpi({ label, value, sub, color }) {
  return (
    <div className="wc-kpi">
      <div className="wc-kpi-label">{label}</div>
      <div className="wc-kpi-value" style={{ color: color || 'var(--bright)' }}>{value}</div>
      {sub && <div className="wc-kpi-sub">{sub}</div>}
    </div>
  );
}

/* ── Score Band Chart ───────────────────────────────────── */
function ScoreBandChart({ title, bands, color, metric }) {
  if (!bands) return null;
  const entries = Object.entries(bands).filter(([,s]) => s.n >= 3);
  if (!entries.length) return null;

  // metricに応じてデータ取得
  const getVal = (s) => {
    if (metric === 'close_avg')   return s.close?.avg    ?? 0;
    if (metric === 'real_avg')    return s.real?.avg     ?? 0;
    if (metric === 'real_wr')     return s.real?.win_rate ?? 0;
    if (metric === 'mfe_avg')     return s.mfe?.avg      ?? 0;
    if (metric === 'mae_avg')     return s.mae?.avg      ?? 0;
    if (metric === 'stop_rate')   return s.stop_hit_rate  ?? 0;
    if (metric === 'alpha_avg')   return s.alpha?.avg    ?? 0;
    return 0;
  };

  const vals   = entries.map(([,s]) => getVal(s));
  const absMax = Math.max(...vals.map(Math.abs), 0.01);
  const isWR   = metric === 'real_wr' || metric === 'stop_rate';
  const isNeg  = metric === 'mae_avg' || metric === 'stop_rate'; // 大きい方が悪い

  return (
    <div className="wc-band-card">
      <div className="wc-band-title">
        {title}
        <span className="wc-band-metric">
          {{ close_avg:'終値%', real_avg:'実態%', real_wr:'実態勝率',
             mfe_avg:'MFE%', mae_avg:'MAE%', stop_rate:'Stop到達率', alpha_avg:'α%' }[metric]}
        </span>
      </div>
      {entries.map(([band, s]) => {
        const val    = getVal(s);
        const barPct = Math.abs(val) / absMax * 100;
        const barClr = isWR
          ? (isNeg ? (val > 30 ? '#ff3355' : '#00ff88') : color)
          : clr(isNeg ? -val : val);
        return (
          <div key={band} className="wc-band-row">
            <div className="wc-band-label">{band}</div>
            <div className="wc-band-track">
              <div className="wc-band-center"/>
              {!isWR ? (
                <div className="wc-band-bar-signed" style={{
                  width: `${barPct/2}%`,
                  left:  val >= 0 ? '50%' : `${50 - barPct/2}%`,
                  background: barClr, opacity: s.n < 10 ? 0.55 : 1,
                }}/>
              ) : (
                <div className="wc-band-bar-abs" style={{
                  width: `${barPct}%`, background: barClr, opacity: s.n < 10 ? 0.55 : 1,
                }}/>
              )}
            </div>
            <div className="wc-band-val" style={{ color: isWR ? barClr : clr(isNeg ? -val : val) }}>
              {isWR ? `${r1(val)}%` : pp(val)}
            </div>
            <div className="wc-band-n">n={s.n}</div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Top/Bottom Ranker ──────────────────────────────────── */
function RankerTable({ title, rows, color, icon: Icon }) {
  return (
    <div className="wc-ranker">
      <div className="wc-ranker-title" style={{ color }}>
        <Icon size={13}/> {title}
      </div>
      <div className="wc-ranker-rows">
        {rows.map((r, i) => (
          <div key={r.ticker} className="wc-ranker-row">
            <span className="wc-ranker-rank" style={{ color }}>{i+1}</span>
            <Link to={`/realtime/${r.ticker}`} className="wc-ranker-ticker">{r.ticker}</Link>
            <div className="wc-ranker-scores">
              <span style={{ color: SCORE_COLORS.composite }}>C{r.composite}</span>
              <span style={{ color: SCORE_COLORS.vcp }}>V{r.vcp}</span>
              <span style={{ color: SCORE_COLORS.rs  }}>R{r.rs}</span>
            </div>
            {/* 終値 vs 実態の比較 */}
            <div className="wc-ranker-dual">
              <span style={{ color: clr(r.close_ret), fontSize:'0.6rem' }}>終{pp(r.close_ret)}</span>
              <span style={{ color: clr(r.real_ret), fontWeight:700 }}>実{pp(r.real_ret)}</span>
            </div>
            {r.stop_hit && (
              <span className="wc-stop-badge">STOP</span>
            )}
            <div className="wc-ranker-mfe-mae">
              <span style={{ color:'#00ff88', fontSize:'0.58rem' }}>↑{r.mfe_pct?.toFixed(1)}%</span>
              <span style={{ color:'#ff3355', fontSize:'0.58rem' }}>↓{r.mae_pct?.toFixed(1)}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── All Results Table ──────────────────────────────────── */
function AllTable({ rows }) {
  const [scoreFilter, setScoreFilter] = useState('composite');
  const [minScore,    setMinScore]    = useState(0);
  const [statusFilter,setStatusFilter]= useState('ALL');
  const [stopFilter,  setStopFilter]  = useState('ALL'); // ALL / stop / hold
  const [sortKey,     setSortKey]     = useState('real_ret');
  const [sortDir,     setSortDir]     = useState(-1);
  const [page,        setPage]        = useState(0);
  const PAGE = 30;

  const filtered = rows
    .filter(r => r[scoreFilter] >= minScore)
    .filter(r => statusFilter === 'ALL' || r.status === statusFilter)
    .filter(r => stopFilter === 'ALL' || (stopFilter === 'stop' ? r.stop_hit : !r.stop_hit))
    .sort((a,b) => sortDir * (a[sortKey] > b[sortKey] ? 1 : -1));

  const paged      = filtered.slice(page*PAGE, (page+1)*PAGE);
  const totalPages = Math.ceil(filtered.length / PAGE);

  const th = (key, label) => (
    <th className="wc-th" onClick={() => { setSortKey(key); setSortDir(sortKey===key ? -sortDir : -1); setPage(0); }}>
      {label}{sortKey===key?(sortDir>0?' ↑':' ↓'):''}
    </th>
  );

  return (
    <div className="wc-section">
      <div className="wc-section-title">全銘柄明細 ({filtered.length}件)
        <span style={{color:'var(--dim)',fontSize:'0.58rem',marginLeft:'0.5rem'}}>
          ※実態=ストップ到達なら損失確定、未到達なら現在終値
        </span>
      </div>

      <div className="wc-filters">
        <select className="wc-select" value={scoreFilter}
          onChange={e=>{setScoreFilter(e.target.value);setPage(0);}}>
          {SCORE_KEYS.map(k=><option key={k} value={k}>{k.toUpperCase()}</option>)}
        </select>
        <span className="wc-filter-label">≥</span>
        <input type="number" className="wc-input-sm" value={minScore} step={5} min={0} max={100}
          onChange={e=>{setMinScore(Number(e.target.value));setPage(0);}}/>
        <select className="wc-select" value={statusFilter}
          onChange={e=>{setStatusFilter(e.target.value);setPage(0);}}>
          {['ALL','ACTION','WAIT'].map(k=><option key={k} value={k}>{k}</option>)}
        </select>
        <select className="wc-select" value={stopFilter}
          onChange={e=>{setStopFilter(e.target.value);setPage(0);}}>
          <option value="ALL">全結果</option>
          <option value="stop">Stop到達のみ</option>
          <option value="hold">未到達のみ</option>
        </select>
      </div>

      <div className="wc-table-wrap">
        <table className="wc-table">
          <thead>
            <tr>
              {th('ticker','銘柄')}
              {th('status','ST')}
              {th('composite','COMP')}
              {th('vcp','VCP')}
              {th('rs','RS')}
              {th('entry_price','Entry')}
              {th('close_ret','終値%')}
              {th('real_ret','実態%')}
              {th('mfe_pct','MFE↑')}
              {th('mae_pct','MAE↓')}
              {th('atr_pct','ATR%')}
              <th className="wc-th">Stop</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((r,i) => (
              <tr key={i} className={`wc-tr ${r.real_win ? 'wc-tr-win' : 'wc-tr-loss'}`}>
                <td className="wc-td">
                  <Link to={`/realtime/${r.ticker}`} className="wc-td-ticker">{r.ticker}</Link>
                </td>
                <td className="wc-td">
                  <span className={`wc-status ${r.status==='ACTION'?'wc-action':'wc-wait'}`}>{r.status}</span>
                </td>
                <td className="wc-td" style={{color:SCORE_COLORS.composite}}>{r.composite}</td>
                <td className="wc-td" style={{color:SCORE_COLORS.vcp}}>{r.vcp}</td>
                <td className="wc-td" style={{color:SCORE_COLORS.rs}}>{r.rs}</td>
                <td className="wc-td">${r.entry_price}</td>
                {/* 終値と実態を並べる */}
                <td className="wc-td" style={{color:clr(r.close_ret)}}>{pp(r.close_ret)}</td>
                <td className="wc-td" style={{color:clr(r.real_ret),fontWeight:700}}>{pp(r.real_ret)}</td>
                {/* MFE: 上に行った最大値（緑） */}
                <td className="wc-td" style={{color:'#00ff88'}}>+{r.mfe_pct?.toFixed(1)}%</td>
                {/* MAE: 下に行った最大値（赤） */}
                <td className="wc-td" style={{color:'#ff3355'}}>-{r.mae_pct?.toFixed(1)}%</td>
                <td className="wc-td" style={{color:'var(--muted)'}}>{r.atr_pct?.toFixed(1)}%</td>
                <td className="wc-td">
                  {r.stop_hit
                    ? <span className="wc-stop-badge">HIT {r.stop_hit_date?.slice(5)}</span>
                    : <span style={{color:'var(--dim)',fontSize:'0.6rem'}}>—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="wc-pagination">
          <button className="wc-page-btn" disabled={page===0} onClick={()=>setPage(p=>p-1)}>← 前</button>
          <span className="wc-page-info">{page+1} / {totalPages}</span>
          <button className="wc-page-btn" disabled={page===totalPages-1} onClick={()=>setPage(p=>p+1)}>次 →</button>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   MAIN
   ══════════════════════════════════════════════════════════ */
export default function WeeklyCheckPage() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [metric,  setMetric]  = useState('real_avg');
  const [tab,     setTab]     = useState('chart');

  useEffect(() => {
    fetch('/content/weekly_check.json')
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="wc-page"><div className="wc-empty">読み込み中…</div></div>;
  if (!data) return (
    <div className="wc-page">
      <div className="wc-empty">
        <div style={{fontSize:'1.2rem',color:'var(--bright)',marginBottom:'1rem'}}>📊 週次チェック未実行</div>
        <pre className="wc-code">python scripts/weekly_check.py --date 2026-02-19</pre>
      </div>
    </div>
  );

  const { summary, spy, by_score, by_status, top10, bottom10, all_results,
          signal_date, eval_date, hold_days, stop_atr_mult } = data;

  const METRICS = [
    { key:'real_avg',  label:'実態リターン' },
    { key:'close_avg', label:'終値リターン' },
    { key:'real_wr',   label:'実態勝率' },
    { key:'mfe_avg',   label:'MFE（最大上昇）' },
    { key:'mae_avg',   label:'MAE（最大下落）' },
    { key:'stop_rate', label:'Stop到達率' },
    { key:'alpha_avg', label:'vs SPY (α)' },
  ];

  return (
    <div className="wc-page">

      {/* ── Hero ─────────────────────────────────────────── */}
      <div className="wc-hero">
        <div className="wc-hero-bg"/>
        <div className="wc-hero-content">
          <div className="wc-eyebrow">SENTINEL · WEEKLY SCORE CHECK</div>
          <div className="wc-title">
            <BarChart2 size={20} style={{marginRight:'0.5rem'}}/>
            {signal_date} → {eval_date}
            <span className="wc-hold-days">{hold_days}日間</span>
          </div>

          {/* KPI */}
          <div className="wc-kpi-row">
            <Kpi label="SPYリターン"  value={pp(spy.close_ret)} color={clr(spy.close_ret)} />
            <Kpi label="終値平均"     value={pp(summary.avg_close_ret)} color={clr(summary.avg_close_ret)} />
            <Kpi label="実態平均"     value={pp(summary.avg_real_ret)}
              color={clr(summary.avg_real_ret)} sub="Stop考慮済み" />
            <Kpi label="平均MFE"  value={`+${r1(summary.avg_mfe)}%`} color="#00ff88" sub="最大上昇幅" />
            <Kpi label="平均MAE"  value={`-${r1(summary.avg_mae)}%`} color="#ff3355" sub="最大下落幅" />
            <Kpi label="Stop到達率"   value={`${summary.stop_hit_rate}%`}
              color={summary.stop_hit_rate > 40 ? '#ff3355' : '#ffb800'}
              sub={`${stop_atr_mult}×ATR`} />
            <Kpi label="終値勝率"     value={`${summary.close_win_rate}%`}
              color={clr(summary.close_win_rate - 50)} />
            <Kpi label="実態勝率"     value={`${summary.real_win_rate}%`}
              color={clr(summary.real_win_rate - 50)} sub="Stop考慮" />
          </div>

          <div className="wc-spy-detail">
            SPY: ${spy.entry_price} → ${spy.latest_price} ({pp(spy.close_ret)})
            ｜Stop判定: {stop_atr_mult}×ATR
          </div>
        </div>
      </div>

      <div className="wc-body">

        {/* 終値 vs 実態の説明 */}
        <div className="wc-notice">
          <span style={{color:'#ffb800'}}>⚠</span>
          <span>
            <strong>終値%</strong>＝現在終値ベース（楽観的）　
            <strong>実態%</strong>＝途中でATRストップ（{stop_atr_mult}×ATR）に到達した銘柄は損失確定済みとして計算（現実的）
          </span>
        </div>

        {/* メトリクス選択 */}
        <div className="wc-metric-tabs">
          {METRICS.map(({key,label}) => (
            <button key={key}
              className={`wc-metric-tab ${metric===key?'wc-metric-active':''}`}
              onClick={()=>setMetric(key)}>
              {label}
            </button>
          ))}
        </div>

        {/* タブ */}
        <div className="wc-tabs">
          {[['chart','📊 スコア帯別'],['rank','🏆 TOP/BOTTOM'],['table','📋 全明細']].map(([k,l])=>(
            <button key={k} className={`wc-tab ${tab===k?'wc-tab-active':''}`} onClick={()=>setTab(k)}>{l}</button>
          ))}
        </div>

        {/* ── スコア帯別チャート ────────────────────────── */}
        {tab === 'chart' && (
          <div className="wc-grid-2">
            {SCORE_KEYS.map(key => (
              <ScoreBandChart
                key={key}
                title={`${key.toUpperCase()} スコア帯別`}
                bands={by_score?.[key]}
                color={SCORE_COLORS[key]}
                metric={metric}
              />
            ))}
          </div>
        )}

        {/* ── TOP/BOTTOM ────────────────────────────────── */}
        {tab === 'rank' && (
          <div className="wc-rank-grid">
            <RankerTable title="TOP 10（実態リターン）" rows={top10}   color="#00ff88" icon={Award} />
            <RankerTable title="BOTTOM 10"             rows={bottom10} color="#ff3355" icon={AlertTriangle} />
          </div>
        )}

        {/* ── 全明細 ───────────────────────────────────── */}
        {tab === 'table' && <AllTable rows={all_results} />}

      </div>
    </div>
  );
}
