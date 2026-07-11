import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Zap, Eye, TrendingUp, XCircle, Activity, ChevronRight } from 'lucide-react';

const ECR_CONFIG = {
  IGNITION: {
    icon: Zap,
    color: '#00ff88',
    bg: 'rgba(0,255,136,0.06)',
    border: 'rgba(0,255,136,0.3)',
    glow: '0 0 30px rgba(0,255,136,0.15)',
    label: 'IGNITION',
    desc: 'ランク急上昇 / 出来高×モメンタム初動',
    priority: 1,
  },
  'HOLD/WATCH': {
    icon: Eye,
    color: '#4499ff',
    bg: 'rgba(68,153,255,0.06)',
    border: 'rgba(68,153,255,0.3)',
    glow: '0 0 30px rgba(68,153,255,0.12)',
    label: 'HOLD / WATCH',
    desc: 'ランク65以上 / 条件接近中',
    priority: 2,
  },
  WATCH: {
    icon: Activity,
    color: '#ffb800',
    bg: 'rgba(255,184,0,0.06)',
    border: 'rgba(255,184,0,0.3)',
    glow: '0 0 30px rgba(255,184,0,0.10)',
    label: 'WATCH',
    desc: '監視圏内 / エントリー待ち',
    priority: 3,
  },
  REJECTED: {
    icon: XCircle,
    color: '#ff3355',
    bg: 'rgba(255,51,85,0.04)',
    border: 'rgba(255,51,85,0.2)',
    glow: 'none',
    label: 'REJECTED',
    desc: 'ランク5未満 / 対象外',
    priority: 4,
  },
};

const STRATEGY_LABELS = {
  ESE:      { label: 'ESE', desc: 'Early Stage Entry', color: '#00ff88' },
  PBVH:     { label: 'PBVH', desc: 'Pivot Break Volume High', color: '#4499ff' },
  TRAILING: { label: 'TRAIL', desc: 'Trailing Stop', color: '#ffb800' },
  NONE:     { label: '—', desc: '', color: '#444' },
};

function ScoreRing({ value, max = 100, color, size = 56 }) {
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const fill = circ * (1 - Math.min(value, max) / max);
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={4} />
      <circle
        cx={size/2} cy={size/2} r={r}
        fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={circ} strokeDashoffset={fill}
        strokeLinecap="round"
        style={{ filter: `drop-shadow(0 0 4px ${color})`, transition: 'stroke-dashoffset 0.8s ease' }}
      />
      <text
        x={size/2} y={size/2 + 1}
        textAnchor="middle" dominantBaseline="middle"
        fill={color}
        style={{ fontFamily: 'Space Mono, monospace', fontSize: size > 48 ? 13 : 10, fontWeight: 700, transform: 'rotate(90deg)', transformOrigin: `${size/2}px ${size/2}px` }}
      >
        {value}
      </text>
    </svg>
  );
}

function SignalPill({ signal }) {
  const isPositive = signal.includes('OK') || signal.includes('Detected') || signal.includes('Near');
  return (
    <span style={{
      fontFamily: 'Space Mono, monospace',
      fontSize: '0.55rem',
      padding: '0.15rem 0.45rem',
      borderRadius: 3,
      background: isPositive ? 'rgba(0,255,136,0.08)' : 'rgba(255,255,255,0.04)',
      border: `1px solid ${isPositive ? 'rgba(0,255,136,0.25)' : 'rgba(255,255,255,0.08)'}`,
      color: isPositive ? '#00ff88' : '#666',
      whiteSpace: 'nowrap',
    }}>
      {signal}
    </span>
  );
}

function IgnitionCard({ item }) {
  const cfg = ECR_CONFIG['IGNITION'];
  const strat = STRATEGY_LABELS[item.ecr_strategy] || STRATEGY_LABELS.NONE;
  const rr = item._stop && item._entry && item._target
    ? ((item._target - item._entry) / (item._entry - item._stop)).toFixed(1)
    : null;

  return (
    <Link to={`/realtime/${item.ticker}`} style={{ textDecoration: 'none', display: 'block' }}>
      <div className="ignition-card" style={{ '--phase-color': cfg.color, '--phase-bg': cfg.bg, '--phase-border': cfg.border, '--phase-glow': cfg.glow }}>
        <div className="ic-pulse" />
        <div className="ic-header">
          <div>
            <div className="ic-ticker">{item.ticker}</div>
            <div className="ic-name">{item.name}</div>
            <div className="ic-sector">{item.sector}</div>
          </div>
          <div className="ic-right">
            <div className="ic-price">${item.price?.toFixed(2)}</div>
            <div className="ic-dist" style={{ color: item.pivot_dist_pct <= 0 ? '#00ff88' : '#ff3355' }}>
              {item.pivot_dist_pct > 0 ? '+' : ''}{item.pivot_dist_pct?.toFixed(2)}% pivot
            </div>
            {strat.label !== '—' && (
              <span style={{
                fontFamily: 'Space Mono, monospace', fontSize: '0.6rem',
                padding: '0.2rem 0.5rem', borderRadius: 4,
                background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.3)',
                color: '#00ff88', marginTop: '0.25rem', display: 'inline-block'
              }}>{strat.label}</span>
            )}
          </div>
        </div>

        <div className="ic-scores">
          <div className="ic-score-item">
            <ScoreRing value={item.scores.vcp} max={105} color="#00ff88" />
            <div className="ic-score-label">VCP</div>
          </div>
          <div className="ic-score-item">
            <ScoreRing value={item.scores.rs} max={99} color="#4499ff" />
            <div className="ic-score-label">RS</div>
          </div>
          <div className="ic-score-item">
            <ScoreRing value={item.scores.ses} max={100} color="#ff3355" />
            <div className="ic-score-label">SES</div>
          </div>
          <div className="ic-score-item">
            <ScoreRing value={item.scores.ecr_rank} max={100} color="#ffb800" />
            <div className="ic-score-label">ECR</div>
          </div>
          <div className="ic-comp">
            <div className="ic-comp-val">{item.scores.composite?.toFixed(1)}</div>
            <div className="ic-comp-label">COMPOSITE</div>
          </div>
        </div>

        {item.vcp_details?.signals?.length > 0 && (
          <div className="ic-signals">
            {item.vcp_details.signals.map((s, i) => <SignalPill key={i} signal={s} />)}
            {item.vcp_details.is_dryup && (
              <span style={{
                fontFamily: 'Space Mono, monospace', fontSize: '0.55rem',
                padding: '0.15rem 0.45rem', borderRadius: 3,
                background: 'rgba(255,184,0,0.1)', border: '1px solid rgba(255,184,0,0.3)',
                color: '#ffb800'
              }}>🔥 DRY-UP</span>
            )}
          </div>
        )}

        <div className="ic-footer">
          <span style={{ color: '#00ff88', fontSize: '0.65rem', fontFamily: 'monospace' }}>
            CANSLIM {item.canslim_grade}
          </span>
          {rr && <span style={{ color: '#666', fontSize: '0.6rem', fontFamily: 'monospace' }}>RR 1:{rr}</span>}
          <span style={{ color: '#4499ff', fontSize: '0.6rem', fontFamily: 'monospace', marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4 }}>
            DEEP DIVE <ChevronRight size={11}/>
          </span>
        </div>
      </div>
    </Link>
  );
}

function PhaseSection({ phase, items, isOpen, onToggle }) {
  const cfg = ECR_CONFIG[phase] || ECR_CONFIG.WATCH;
  const Icon = cfg.icon;

  return (
    <div className="phase-section" style={{ '--phase-color': cfg.color, '--phase-border': cfg.border }}>
      <button className="phase-header" onClick={onToggle}>
        <div className="ph-left">
          <div className="ph-icon-wrap" style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}>
            <Icon size={14} style={{ color: cfg.color }} />
          </div>
          <div>
            <div className="ph-label" style={{ color: cfg.color }}>{cfg.label}</div>
            <div className="ph-desc">{cfg.desc}</div>
          </div>
        </div>
        <div className="ph-right">
          <div className="ph-count" style={{ color: cfg.color }}>{items.length}</div>
          <div className="ph-chevron" style={{ transform: isOpen ? 'rotate(90deg)' : 'none' }}>
            <ChevronRight size={14} color="#444" />
          </div>
        </div>
      </button>

      {isOpen && items.length > 0 && (
        <div className="phase-body">
          <div className="phase-table-header">
            <span>#</span>
            <span>TICKER</span>
            <span>PRICE</span>
            <span>VCP</span>
            <span>RS</span>
            <span>ECR</span>
            <span>COMP</span>
            <span>STRATEGY</span>
            <span>CANSLIM</span>
            <span>PIVOT%</span>
          </div>
          {items.map((item, i) => {
            const strat = STRATEGY_LABELS[item.ecr_strategy] || STRATEGY_LABELS.NONE;
            return (
              <Link key={item.ticker} to={`/realtime/${item.ticker}`} className="phase-row" style={{ textDecoration: 'none' }}>
                <span className="pr-rank">{i + 1}</span>
                <div className="pr-ticker-cell">
                  <span className="pr-ticker" style={{ color: cfg.color }}>{item.ticker}</span>
                  <span className="pr-name">{item.name?.slice(0, 18)}</span>
                </div>
                <span className="pr-mono">${item.price?.toFixed(2)}</span>
                <span className="pr-score green">{item.scores.vcp}</span>
                <span className="pr-score blue">{item.scores.rs}</span>
                <span className="pr-score amber">{item.scores.ecr_rank}</span>
                <span className="pr-comp">{item.scores.composite?.toFixed(1)}</span>
                <span style={{ fontFamily: 'monospace', fontSize: '0.65rem', color: strat.color }}>{strat.label}</span>
                <span style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#aa66ff', fontWeight: 700 }}>{item.canslim_grade}</span>
                <span style={{ fontFamily: 'monospace', fontSize: '0.65rem', color: item.pivot_dist_pct <= 0 ? '#00ff88' : '#ff3355' }}>
                  {item.pivot_dist_pct > 0 ? '+' : ''}{item.pivot_dist_pct?.toFixed(2)}%
                </span>
              </Link>
            );
          })}
        </div>
      )}
      {isOpen && items.length === 0 && (
        <div style={{ padding: '1.5rem', textAlign: 'center', fontFamily: 'monospace', fontSize: '0.7rem', color: '#444' }}>
          NO STOCKS IN THIS PHASE
        </div>
      )}
    </div>
  );
}

export default function ECRPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [openPhases, setOpenPhases] = useState({ IGNITION: true, 'HOLD/WATCH': true, WATCH: false, REJECTED: false });

  useEffect(() => {
    fetch('/content/strategies.json')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="loading-screen">
      <div className="loading-bar"><div className="loading-fill"/></div>
      <div className="loading-text">LOADING ECR PHASES...</div>
    </div>
  );

  const phases = data?.ecr_phases || {};
  const allPhases = ['IGNITION', 'HOLD/WATCH', 'WATCH', 'REJECTED'];
  const ignition = phases['IGNITION'] || [];
  const totalAction = Object.values(phases).flat().filter(i => i.status === 'ACTION').length;

  return (
    <div className="ecr-page">
      {/* Hero Header */}
      <div className="ecr-hero">
        <div className="ecr-hero-bg" />
        <div className="ecr-hero-content">
          <div className="ecr-eyebrow">ENERGY COMPRESSION ROTATION</div>
          <h1 className="ecr-title">ECR PHASES</h1>
          <div className="ecr-stats">
            {allPhases.map(phase => {
              const cfg = ECR_CONFIG[phase];
              const count = (phases[phase] || []).length;
              return (
                <div key={phase} className="ecr-stat">
                  <div className="ecr-stat-num" style={{ color: cfg.color }}>{count}</div>
                  <div className="ecr-stat-label">{cfg.label}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* IGNITION spotlight */}
      {ignition.length > 0 && (
        <div className="ignition-section">
          <div className="section-eyebrow">
            <Zap size={13} color="#00ff88" />
            <span>IGNITION — 最高優先度 エントリー候補</span>
          </div>
          <div className="ignition-grid">
            {ignition.map(item => <IgnitionCard key={item.ticker} item={item} />)}
          </div>
        </div>
      )}

      {/* All phases */}
      <div className="phases-list">
        {allPhases.map(phase => (
          <PhaseSection
            key={phase}
            phase={phase}
            items={phases[phase] || []}
            isOpen={openPhases[phase]}
            onToggle={() => setOpenPhases(p => ({ ...p, [phase]: !p[phase] }))}
          />
        ))}
      </div>
    </div>
  );
}
