import React, { useEffect, useRef } from 'react';

/**
 * TradingViewWidget - 軽量チャート埋め込み
 * 
 * Props:
 *   symbol    : "NASDAQ:NVDA", "NYSE:AAPL" など
 *   interval  : "D" (日足), "60" (1時間), "15" (15分) など
 *   height    : px数（デフォルト400）
 *   theme     : "dark" | "light"
 */
export default function TradingViewWidget({ 
  symbol = "NASDAQ:AAPL", 
  interval = "D",
  height = 400,
  theme = "dark",
  showToolbar = true,
}) {
  const container = useRef(null);

  useEffect(() => {
    if (!container.current) return;
    
    // 既存のスクリプトをクリア
    container.current.innerHTML = '';

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.type = 'text/javascript';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: false,
      symbol: symbol,
      interval: interval,
      timezone: "America/New_York",
      theme: theme,
      style: "1", // ローソク足
      locale: "en",
      height: height,
      width: "100%",
      enable_publishing: false,
      hide_top_toolbar: !showToolbar,
      hide_legend: false,
      save_image: false,
      backgroundColor: theme === 'dark' ? 'rgba(6, 10, 15, 1)' : 'rgba(255, 255, 255, 1)',
      gridColor: theme === 'dark' ? 'rgba(24, 32, 48, 0.3)' : 'rgba(200, 200, 200, 0.3)',
      support_host: "https://www.tradingview.com",
    });

    container.current.appendChild(script);
  }, [symbol, interval, height, theme, showToolbar]);

  return (
    <div className="tradingview-widget-container" ref={container} style={{ height: `${height}px`, overflow: 'hidden' }}>
      <div className="tradingview-widget-container__widget"></div>
    </div>
  );
}

/**
 * TradingViewMiniChart - 超軽量ミニチャート（ウォッチリスト用）
 */
export function TradingViewMiniChart({ symbol, height = 150 }) {
  const container = useRef(null);

  useEffect(() => {
    if (!container.current) return;
    container.current.innerHTML = '';

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js';
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbol: symbol,
      width: "100%",
      height: height,
      locale: "en",
      dateRange: "3M",
      colorTheme: "dark",
      isTransparent: true,
      autosize: false,
      largeChartUrl: "",
    });

    container.current.appendChild(script);
  }, [symbol, height]);

  return (
    <div className="tradingview-widget-container" ref={container} style={{ height: `${height}px` }}>
      <div className="tradingview-widget-container__widget"></div>
    </div>
  );
}

/**
 * TradingViewTicker - リアルタイムティッカーテープ
 */
export function TradingViewTicker({ symbols = [] }) {
  const container = useRef(null);

  useEffect(() => {
    if (!container.current || symbols.length === 0) return;
    container.current.innerHTML = '';

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js';
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbols: symbols.map(s => ({ description: s, proName: `NASDAQ:${s}` })),
      showSymbolLogo: false,
      isTransparent: true,
      displayMode: "adaptive",
      colorTheme: "dark",
      locale: "en",
    });

    container.current.appendChild(script);
  }, [symbols]);

  return (
    <div className="tradingview-widget-container" ref={container}>
      <div className="tradingview-widget-container__widget"></div>
    </div>
  );
}
