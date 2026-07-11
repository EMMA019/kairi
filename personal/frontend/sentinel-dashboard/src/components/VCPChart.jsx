import React from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Area, ComposedChart } from 'recharts';

/**
 * VCPChart - VCPパターン可視化
 * 
 * 表示内容:
 * - ローソク足（疑似）
 * - MA20/50/200
 * - 出来高（dry-up強調）
 * - Pivot Point
 * - タイトニング範囲
 */
export default function VCPChart({ data, vcp_detail }) {
  if (!data || data.length === 0) return null;

  // 直近90日分
  const recent = data.slice(-90);
  
  // チャートデータ整形
  const chartData = recent.map((d, i) => {
    const ma20  = i >= 19 ? recent.slice(i - 19, i + 1).reduce((s, x) => s + x.Close, 0) / 20 : null;
    const ma50  = i >= 49 ? recent.slice(i - 49, i + 1).reduce((s, x) => s + x.Close, 0) / 50 : null;
    const ma200 = data.length >= 200 && i >= 199 
      ? data.slice(data.length - 200 + i - recent.length + 1, data.length + i - recent.length + 2).reduce((s, x) => s + x.Close, 0) / 200 
      : null;

    return {
      date: d.date.slice(5, 10), // MM-DD
      close: d.Close,
      high: d.High,
      low: d.Low,
      open: d.Open,
      volume: d.Volume,
      ma20,
      ma50,
      ma200,
    };
  });

  // Pivot（直近20日の最高値）
  const pivot = Math.max(...recent.slice(-20).map(d => d.High));

  // Volume平均（dry-up判定用）
  const avgVol = recent.slice(-50, -20).reduce((s, d) => s + d.Volume, 0) / 30;
  const recentAvgVol = recent.slice(-20).reduce((s, d) => s + d.Volume, 0) / 20;
  const isDryUp = recentAvgVol < avgVol * 0.6;

  // 価格レンジ（直近20日）
  const recentHigh = Math.max(...recent.slice(-20).map(d => d.High));
  const recentLow  = Math.min(...recent.slice(-20).map(d => d.Low));
  const rangeSize  = (recentHigh - recentLow) / recentLow * 100;

  return (
    <div className="space-y-1">
      
      {/* VCPステータス */}
      <div className="flex items-center justify-between px-2 py-1 bg-ink/60 rounded-lg text-xs font-mono">
        <div className="flex items-center gap-3">
          <span className="text-muted">Pivot:</span>
          <span className="text-green font-bold">${pivot.toFixed(2)}</span>
          <span className="text-muted">Range:</span>
          <span className={rangeSize < 10 ? 'text-green' : rangeSize < 20 ? 'text-amber' : 'text-red'}>
            {rangeSize.toFixed(1)}%
          </span>
          <span className="text-muted">Vol:</span>
          <span className={isDryUp ? 'text-green' : 'text-muted'}>
            {isDryUp ? '✓ Dry-up' : 'Normal'}
          </span>
        </div>
        {vcp_detail?.signals && (
          <div className="text-green text-[10px]">
            {vcp_detail.signals.slice(0, 2).join(' • ')}
          </div>
        )}
      </div>

      {/* 価格チャート */}
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
          <XAxis 
            dataKey="date" 
            tick={{ fontSize: 9, fontFamily: 'monospace', fill: '#364858' }}
            tickLine={false}
            axisLine={{ stroke: '#182030' }}
          />
          <YAxis 
            domain={['dataMin - 2', 'dataMax + 2']}
            tick={{ fontSize: 9, fontFamily: 'monospace', fill: '#364858' }}
            tickLine={false}
            axisLine={{ stroke: '#182030' }}
            width={45}
          />
          <Tooltip
            contentStyle={{ 
              background: '#0C1117', 
              border: '1px solid #182030', 
              fontFamily: 'monospace', 
              fontSize: 10,
              borderRadius: 8,
            }}
            formatter={(v) => [`$${Number(v).toFixed(2)}`, '']}
          />
          
          {/* Pivot Line */}
          <ReferenceLine 
            y={pivot} 
            stroke="#00FF88" 
            strokeDasharray="3 3" 
            strokeWidth={1.5}
            label={{ value: 'Pivot', position: 'right', fill: '#00FF88', fontSize: 9 }}
          />

          {/* MA Lines */}
          <Line type="monotone" dataKey="ma200" stroke="#FF4466" strokeWidth={0.8} dot={false} strokeDasharray="2 2" />
          <Line type="monotone" dataKey="ma50"  stroke="#FFB800" strokeWidth={1}   dot={false} />
          <Line type="monotone" dataKey="ma20"  stroke="#4499FF" strokeWidth={1}   dot={false} />
          
          {/* Price (疑似ローソク足 - Closeのみ) */}
          <Line type="monotone" dataKey="close" stroke="#00FF88" strokeWidth={1.5} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>

      {/* 出来高チャート */}
      <ResponsiveContainer width="100%" height={80}>
        <BarChart data={chartData} margin={{ top: 0, right: 5, left: 0, bottom: 0 }}>
          <XAxis dataKey="date" hide />
          <YAxis hide />
          <Tooltip
            contentStyle={{ 
              background: '#0C1117', 
              border: '1px solid #182030', 
              fontFamily: 'monospace', 
              fontSize: 10 
            }}
            formatter={(v) => [(v / 1000000).toFixed(1) + 'M', 'Vol']}
          />
          <Bar dataKey="volume" radius={[2, 2, 0, 0]}>
            {chartData.map((d, i) => {
              // Dry-up期間は緑、それ以外はグレー
              const color = d.volume < avgVol * 0.8 ? '#00FF8840' : '#364858';
              return <rect key={i} fill={color} />;
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* 凡例 */}
      <div className="flex items-center gap-3 px-2 text-[10px] font-mono">
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-[#4499FF]" />
          <span className="text-muted">MA20</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-[#FFB800]" />
          <span className="text-muted">MA50</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-[#FF4466] opacity-50" />
          <span className="text-muted">MA200</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 bg-[#00FF88] opacity-30" />
          <span className="text-muted">Dry-up Vol</span>
        </div>
      </div>
    </div>
  );
}
