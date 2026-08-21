import { useEffect, useState, lazy, Suspense } from "react";
import { About, Contact, Hero, Loader, Navbar, Skills, Works } from "./components/ui";

const Scene3D = lazy(() =>
  import("./components/Scene3D").then((m) => ({ default: m.Scene3D }))
);

export default function App() {
  const [booting, setBooting] = useState(true);
  useEffect(() => {
    const t = window.setTimeout(() => setBooting(false), 700);
    return () => window.clearTimeout(t);
  }, []);

  const scene = (
    <Suspense fallback={<div className="scene-wrap" />}>
      <Scene3D />
    </Suspense>
  );

  return (
    <>
      <Loader show={booting} />
      <Navbar />
      <Hero scene={scene} />
      <About />
      <Skills />
      <Works />
      <Contact />
      <footer>
        Kairi is MIT. Grounding docs in the repo. This page does not invent download or user counts.
        {" "}
        <a href="https://github.com/EMMA019/kairi">Source</a>
      </footer>
    </>
  );
}
