import { useEffect, useState } from "react";
import NewBuild from "./NewBuild.jsx";
import RunView from "./RunView.jsx";

// Tiny hash router: "#/" is the home page, "#/run/<id>" shows one build.
function useRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const match = hash.match(/^#\/run\/([\w-]+)/);
  return match ? { page: "run", id: match[1] } : { page: "home" };
}

export const go = (path) => (window.location.hash = path);

export default function App() {
  const route = useRoute();
  return (
    <div className="app">
      <header className="topbar">
        <a href="#/" className="brand">
          <span className="logo" aria-hidden>◆</span> Agent Studio
        </a>
        <span className="tagline">One click → a team of Claude Code agents builds your app</span>
        {route.page === "run" && (
          <a href="#/" className="btn btn-ghost">+ New build</a>
        )}
      </header>
      {route.page === "run" ? <RunView key={route.id} id={route.id} /> : <NewBuild />}
    </div>
  );
}
