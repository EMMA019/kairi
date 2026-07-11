import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';

/**
 * ScoreHistoryChart - 30日間のスコア推移チャート
 * 
 * strategies_history/*.json から該当ティッカーのスコアを抽出
 */
export default function ScoreHistoryChart({ ticker }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadHistory = async () => {
      try {
        // strategies_history ディレクトリの全JSONファイルを取得
        // （実際にはindex.jsonなどで日付リストを管理する方が効率的）
        const dates = [];
        const today = new Date();
        for (let i = 0; i < 30; i++) {
          const d = new Date(today);
          d.setDate(d.getDate() - i);
          const y = d.getFullYear();
          const m = String(d.getMonth() + 1).padStart(2, '0');
          const day = String(d.getDate()).padStart(2, '0');
          dates.push(`${y}-${m}-${day}`);
        }
        dates.reverse();

        const history = [];
        for (const date of dates) {
          try {
            const resp = await fetch(`/content/strategies_history/${date}.json`);
            if (!resp.ok) continue;
            const json = await resp.json();
            
            // 該当ティッカーを探す
            const item = json.find(d => d.ticker === ticker);
            if (item) {
              history.push({
                date: date.slice(5), // MM-DD
                vcp: item.scores.vcp,
                rs: item.scores.rs,
                ecr: item.scores.ecr_rank,
                canslim: item.scores.canslim,
                ses: item.scores.ses,
              });
            }
          } catch {}
        }

        setData(history);
      } catch (e) {
        console.error('History load error:', e);
      } finally {
        setLoading(false);
      }
    };

    loadHistory();
  }, [ticker]);

  if (loading) return (
    <div className="text-center text-muted font-mono text-xs py-8">Loading history...</div>
  );

  if (data.length === 0) return (
    <div className="text-center text-muted font-mono text-xs py-8">No history available</div>
  );

  return (
    <div className="space-y-2">
      <div className="text-muted font-mono text-xs">📈 Score Trend (30 days)</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <XAxis 
            dataKey="date" 
            tick={{ fontSize: 9, fontFamily: 'monospace', fill: '#364858' }}
            tickLine={false}
            axisLine={{ stroke: '#182030' }}
          />
          <YAxis 
            domain={[0, 105]}
            tick={{ fontSize: 9, fontFamily: 'monospace', fill: '#364858' }}
            tickLine={false}
            axisLine={{ stroke: '#182030' }}
            width={30}
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
          <Legend 
            wrapperStyle={{ fontSize: 10, fontFamily: 'monospace' }}
            iconType="line"
          />
          <Line type="monotone" dataKey="vcp"     stroke="#00FF88" strokeWidth={1.5} dot={false} name="VCP" />
          <Line type="monotone" dataKey="rs"      stroke="#4499FF" strokeWidth={1.5} dot={false} name="RS" />
          <Line type="monotone" dataKey="ecr"     stroke="#FFB800" strokeWidth={1.5} dot={false} name="ECR" />
          <Line type="monotone" dataKey="canslim" stroke="#AA66FF" strokeWidth={1.5} dot={false} name="CANSLIM" />
          <Line type="monotone" dataKey="ses"     stroke="#FF4466" strokeWidth={1.5} dot={false} name="SES" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
