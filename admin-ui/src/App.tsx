import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useState } from "react";
import MatchesPage from "./pages/MatchesPage";
import MatchDetailPage from "./pages/MatchDetailPage";
import TeamsPage from "./pages/TeamsPage";
import AiPage from "./pages/AiPage";
import SettingsPage from "./pages/SettingsPage";
import ApiPage from "./pages/ApiPage";
import CompetitionsPage from "./pages/CompetitionsPage";

function LoginGate({ children }: { children: React.ReactNode }) {
  const [key, setKey] = useState(localStorage.getItem("admin_key") || "");
  const [input, setInput] = useState(key);

  if (!key) {
    return (
      <div className="main" style={{ maxWidth: 420 }}>
        <div className="panel">
          <h2>Вход в админку</h2>
          <p style={{ color: "var(--muted)" }}>
            Ключ из <code>ADMIN_API_KEY</code> в .env на сервере
          </p>
          <input
            type="password"
            placeholder="X-Admin-Key"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            style={{ width: "100%", marginBottom: "0.75rem" }}
          />
          <button
            onClick={() => {
              localStorage.setItem("admin_key", input.trim());
              setKey(input.trim());
            }}
          >
            Сохранить
          </button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

function Nav() {
  const loc = useLocation();
  const cls = (path: string) => {
    if (path === "/" && (loc.pathname === "/" || loc.pathname.startsWith("/matches/")))
      return "active";
    return loc.pathname === path ? "active" : "";
  };

  return (
    <nav>
      <Link to="/" className={cls("/")}>
        Matches
      </Link>
      <Link to="/teams" className={cls("/teams")}>
        Teams
      </Link>
      <Link to="/ai" className={cls("/ai")}>
        AI
      </Link>
      <Link to="/api" className={cls("/api")}>
        Sport API
      </Link>
      <Link to="/competitions" className={cls("/competitions")}>
        Лиги
      </Link>
      <Link to="/settings" className={cls("/settings")}>
        Настройки
      </Link>
    </nav>
  );
}

export default function App() {
  return (
    <LoginGate>
      <div className="layout">
        <aside className="sidebar">
          <h1>BetIQ Admin</h1>
          <Nav />
          <button
            className="secondary"
            style={{ marginTop: "2rem", width: "100%" }}
            onClick={() => {
              localStorage.removeItem("admin_key");
              window.location.reload();
            }}
          >
            Выйти
          </button>
        </aside>
        <main className="main">
          <Routes>
            <Route path="/" element={<MatchesPage />} />
            <Route path="/matches/:id" element={<MatchDetailPage />} />
            <Route path="/teams" element={<TeamsPage />} />
            <Route path="/ai" element={<AiPage />} />
            <Route path="/api" element={<ApiPage />} />
            <Route path="/competitions" element={<CompetitionsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </LoginGate>
  );
}
