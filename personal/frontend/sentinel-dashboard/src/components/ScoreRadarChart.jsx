import React from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from 'recharts';

/**
 * ScoreRadarChart - 5手法のレーダーチャート
 * 
 * VCP/RS/ECR/CANSLIM/SES を5角形で可視化
 */
export default function ScoreRadarChart({ scores }) {
  if (!scores) return null;

  const data = [
    { metric: 'VCP',     value: scores.vcp || 0,      fullMark: 105 },
    { metric: 'RS',      value: scores.rs || 0,       fullMark: 99 },
    { metric: 'ECR',     value: scores.ecr_rank || 0, fullMark: 100 },
    { metric: 'CANSLIM', value: scores.canslim || 0,  fullMark: 100 },
    { metric: 'SES',     value: scores.ses || 0,      fullMark: 100 },
  ];

  return (
    <div className="space-y-2">
      <div className="text-muted font-mono text-xs">🎯 Score Radar</div>
      <ResponsiveContainer width="100%" height={200}>
        <RadarChart data={data}>
          <PolarGrid stroke="#182030" />
          <PolarAngleAxis 
            dataKey="metric" 
            tick={{ fontSize: 10, fontFamily: 'monospace', fill: '#6B8299' }}
          />
          <PolarRadiusAxis 
            angle={90} 
            domain={[0, 105]} 
            tick={{ fontSize: 9, fontFamily: 'monospace', fill: '#364858' }}
          />
          <Tooltip
            contentStyle={{ 
              background: '#0C1117', 
              border: '1px solid #182030', 
              fontFamily: 'monospace', 
              fontSize: 10,
              borderRadius: 8,
            }}
          />
          <Radar 
            name="Scores" 
            dataKey="value" 
            stroke="#00FF88" 
            fill="#00FF88" 
            fillOpacity={0.3}
            strokeWidth={2}
          />
        </RadarChart>
      </ResponsiveContainer>

      {/* スコア一覧 */}
      <div className="grid grid-cols-5 gap-2 text-center font-mono text-xs">
        {data.map((d, i) => (
          <div key={i}>
            <div className="text-muted">{d.metric}</div>
            <div className="text-bright font-bold">{d.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
