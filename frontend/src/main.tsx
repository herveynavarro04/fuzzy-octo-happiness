import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import Chat from "./pages/Chat";
import Single from "./pages/Single";
import Admin from "./pages/Admin";
import "./styles.css";

function Shell() {
  return (
    <div className="app">
      <nav className="nav">
        <Link to="/" className="brand">Agente RAG</Link>
        <div className="links">
          <Link to="/">Chat</Link>
          <Link to="/single">Única</Link>
          <Link to="/admin">Admin</Link>
        </div>
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/single" element={<Single />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </React.StrictMode>,
);
