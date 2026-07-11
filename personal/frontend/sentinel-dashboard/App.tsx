import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink, Link } from 'react-router-dom';
import './sentinel.css';
import './sentinel-addon.css';
import './sentinel-mobile.css';
import './sentinel-robo.css';
import './sentinel-backtest.css';
import './sentinel-weekly.css';
import './sentinel-real.css';


import Dashboard    from './pages/Dashboard';
import Scanner      from './pages/Scanner';
import Portfolio    from './pages/Portfolio';
import RealtimePage from './pages/RealtimePage';
import ECRPage          from './pages/ECRPage';
import WeeklyCheckPage   from './pages/WeeklyCheckPage';
import BacktestPage      from './pages/BacktestPage';

const NAV_ITEMS = [
  { to: '/',           label: 'DASHBOARD', exact: true },
  { to: '/scanner',    label: 'SCANNER'               },
  { to: '/ecr',        label: 'ECR'                   },
  { to: '/weekly',     label: 'WEEKLY'                },
  { to: '/backtest',   label: 'BACKTEST'              },
  { to: '/portfolio',  label: 'PORTFOLIO'             },
];

function Header({ menuOpen, setMenuOpen }) {
  return (
    <header className="app-header">
      <div className="header-inner">
        <Link to="/" className="logo" style={{ textDecoration: 'none' }}>
          <span className="logo-main">SENTINEL</span>
          <span className="logo-sub">PERSONAL 2026</span>
        </Link>

        {/* Desktop nav */}
        <nav className="header-nav desktop-nav">
          {NAV_ITEMS.map(({ to, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Mobile hamburger */}
        <button
          className="mobile-menu-btn"
          onClick={() => setMenuOpen(v => !v)}
          aria-label="menu"
        >
          {menuOpen ? '✕' : '≡'}
        </button>
      </div>

      {menuOpen && (
        <div className="guaranteed-mobile-menu">
          {NAV_ITEMS.map(({ to, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) => isActive ? 'active' : ''}
            >
              {label}
            </NavLink>
          ))}
        </div>
      )}
    </header>
  );
}

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <Router>
      <div className="app-root">
        <style>{`
          .guaranteed-mobile-menu {
            position: absolute;
            top: 64px;
            left: 0;
            width: 100%;
            background-color: #0c1220;
            border-bottom: 2px solid #00ff88;
            box-shadow: 0 10px 30px rgba(0,0,0,0.9);
            display: flex;
            flex-direction: column;
            z-index: 999999;
          }
          .guaranteed-mobile-menu a {
            padding: 1.25rem 1.5rem;
            color: #e8f0f8;
            text-decoration: none;
            font-family: 'Space Mono', monospace;
            font-size: 0.9rem;
            border-bottom: 1px solid #1a2535;
            font-weight: 700;
            text-align: left;
            transition: all 0.2s;
          }
          .guaranteed-mobile-menu a:last-child {
            border-bottom: none;
          }
          .guaranteed-mobile-menu a.active {
            color: #00ff88;
            background-color: rgba(0, 255, 136, 0.1);
            border-left: 4px solid #00ff88;
            padding-left: calc(1.5rem - 4px);
          }
          @media (min-width: 801px) {
            .guaranteed-mobile-menu { display: none !important; }
          }
        `}</style>

        <Header menuOpen={menuOpen} setMenuOpen={setMenuOpen} />

        <main className="app-main">
          <Routes>
            <Route path="/"                 element={<Dashboard />} />
            <Route path="/scanner"          element={<Scanner />} />
            <Route path="/ecr"              element={<ECRPage />} />
            <Route path="/weekly"           element={<WeeklyCheckPage />} />
            <Route path="/backtest"         element={<BacktestPage />} />
            <Route path="/portfolio"        element={<Portfolio />} />
            <Route path="/realtime/:ticker" element={<RealtimePage />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
