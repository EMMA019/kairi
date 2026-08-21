import type { ReactNode } from "react";

export function Navbar() {
  return (
    <nav className="nav">
      <a href="#top" className="gradient-text" style={{ fontFamily: "var(--font-orbitron)", fontWeight: 700, textDecoration: "none", fontSize: "1.1rem" }}>
        KAIRI
      </a>
      <ul className="nav-links">
        <li><a href="#about">About</a></li>
        <li><a href="#skills">Stack</a></li>
        <li><a href="#works">Works</a></li>
        <li><a href="#contact">Contact</a></li>
      </ul>
    </nav>
  );
}

export function Hero({ scene }: { scene: ReactNode }) {
  return (
    <section className="hero" id="top">
      <div className="hero-copy">
        <span className="section-label">Grounded local BYOK</span>
        <h1>
          Stop the model
          <br />
          <span className="gradient-text">inventing today’s close.</span>
        </h1>
        <p>
          Kairi is a local companion with a hard grounding layer: citation contracts, content-age
          labels, numeric defense, and a violation→eval loop. The market desk is the reference app
          that exercises that pipeline every session. It does not claim to beat ChatGPT.
        </p>
        <div className="hero-actions">
          <a className="btn-primary" href="https://kairi-chat.pages.dev/" target="_blank" rel="noreferrer">
            Open live demo
          </a>
          <a className="btn-ghost" href="https://github.com/EMMA019/kairi" target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
      </div>
      {scene}
    </section>
  );
}

export function About() {
  return (
    <section id="about">
      <span className="section-label">About</span>
      <h2 className="section-title">A filter stack, not another chat skin</h2>
      <p className="section-sub">
        Most UIs stream model text and hope. Kairi runs named filters on the final answer, then
        turns “that felt wrong” into a regression case.
      </p>
      <div className="grid-3">
        <article className="glass-card">
          <h3>Citation / closed-world</h3>
          <p>Proper nouns and absolutes must appear in search, or they get softened or stripped.</p>
        </article>
        <article className="glass-card">
          <h3>Content-age</h3>
          <p>
            <code>fetched_at</code> vs <code>content_as_of</code> so “today” matches the right
            session, not a leftover print.
          </p>
        </article>
        <article className="glass-card">
          <h3>Numeric defense</h3>
          <p>Unverified ratios and fabricated moves are flagged. Integrity is a counter, not a slogan.</p>
        </article>
      </div>
    </section>
  );
}

export function Skills() {
  const items = [
    ["FastAPI + SQLite", "Local backend, WAL, BYOK providers"],
    ["React 19 + Vite", "Chat, Market desk, Workspace"],
    ["Search router", "Weather / wiki / news / web in parallel"],
    ["Offline evals", "python evals/run_evals.py — no LLM required"],
    ["Workspace → GitHub", "Snapshots survive Render disk wipes"],
    ["Own-channel promo", "Telemetry drafts; human approve; no reply-spam"],
  ];
  return (
    <section id="skills">
      <span className="section-label">Stack</span>
      <h2 className="section-title">What it is actually built from</h2>
      <p className="section-sub">No invented user counts. These are modules in the public repo.</p>
      <div className="grid-2">
        {items.map(([title, body]) => (
          <article className="glass-card" key={title}>
            <h3>{title}</h3>
            <p>{body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function Works() {
  return (
    <section id="works">
      <span className="section-label">Works</span>
      <h2 className="section-title">Reference surfaces</h2>
      <p className="section-sub">The same grounding pipeline, shown in three places you can click today.</p>
      <div className="grid-3">
        <a className="glass-card" href="https://kairi-chat.pages.dev/" target="_blank" rel="noreferrer" style={{ textDecoration: "none", color: "inherit" }}>
          <h3>kairi-chat.pages.dev</h3>
          <p>Hosted UI. Chat, Integrity badge, market desk. Keys stay BYOK.</p>
        </a>
        <a className="glass-card" href="https://github.com/EMMA019/kairi" target="_blank" rel="noreferrer" style={{ textDecoration: "none", color: "inherit" }}>
          <h3>github.com/EMMA019/kairi</h3>
          <p>MIT source, evals, grounding docs. This page is rebuilt from that tree.</p>
        </a>
        <article className="glass-card">
          <h3>This site</h3>
          <p>
            Three.js (R3F v8) promo shell. Stars via drei <code>Points</code>, not the fiber v9
            <code>args</code> buffer API that broke the first draft.
          </p>
        </article>
      </div>
    </section>
  );
}

export function Contact() {
  return (
    <section id="contact">
      <span className="section-label">Contact</span>
      <h2 className="section-title">Run it yourself</h2>
      <p className="section-sub">
        Issues and PRs on GitHub. No engagement bait, no DMs to strangers.
      </p>
      <div className="contact-row">
        <a className="btn-primary" href="https://github.com/EMMA019/kairi/issues" target="_blank" rel="noreferrer">
          Open an issue
        </a>
        <a className="btn-ghost" href="https://github.com/EMMA019/kairi" target="_blank" rel="noreferrer">
          Clone the repo
        </a>
      </div>
    </section>
  );
}

export function Loader({ show }: { show: boolean }) {
  if (!show) return null;
  return <div className="loader">KAIRI</div>;
}
