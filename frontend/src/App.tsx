import { useState } from "react";
import ChatPage from "./components/ChatPage";
import UploadPage from "./components/UploadPage";
import HistoryPage from "./components/HistoryPage";
import AnalyticsPage from "./components/AnalyticsPage";
import ContentPage from "./components/ContentPage";

type Role = "student" | "teacher" | "admin";
type Mode = "internal" | "external";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

export default function App() {
  const [role, setRole] = useState<Role>("student");
  const [mode, setMode] = useState<Mode>("internal");
  const [activeTab, setActiveTab] = useState<"chat" | "upload" | "history" | "analytics" | "content">("chat");

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 1rem", fontFamily: "system-ui" }}>
      {/* Header */}
      <header
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 20,
          padding: "1rem 0",
          borderBottom: "1px solid #eee",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700 }}>ICLeaF AI</h1>
          <div style={{ fontSize: 14, color: "#666" }}>Intelligent Content Learning Framework</div>
        </div>

        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <label style={{ fontSize: 14, color: "#444", display: "flex", alignItems: "center", gap: 8 }}>
            Role
            <select 
              value={role} 
              onChange={(e) => setRole(e.target.value as Role)}
              style={{ padding: "4px 8px", borderRadius: 4, border: "1px solid #ccc" }}
            >
              <option value="student">Student</option>
              <option value="teacher">Teacher</option>
              <option value="admin">Admin</option>
            </select>
          </label>

          <div
            style={{
              display: "inline-flex",
              border: "1px solid #ddd",
              borderRadius: 8,
              overflow: "hidden",
            }}
          >
            <button
              onClick={() => setMode("external")}
              style={{
                padding: "8px 16px",
                border: "none",
                background: mode === "external" ? "#e8f1ff" : "transparent",
                color: mode === "external" ? "#175cd3" : "#333",
                cursor: "pointer",
                fontWeight: mode === "external" ? 600 : 400,
              }}
            >
              External
            </button>
            <button
              onClick={() => setMode("internal")}
              style={{
                padding: "8px 16px",
                border: "none",
                background: mode === "internal" ? "#e6f6ec" : "transparent",
                color: mode === "internal" ? "#0a7a3d" : "#333",
                cursor: "pointer",
                fontWeight: mode === "internal" ? 600 : 400,
              }}
            >
              Internal
            </button>
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav
        style={{
          display: "flex",
          borderBottom: "1px solid #eee",
          marginBottom: 24,
          gap: 0,
        }}
      >
        {[
          { id: "chat", label: "💬 Chat", color: "#175cd3" },
          { id: "upload", label: "📤 Upload", color: "#0a7a3d" },
          { id: "history", label: "📚 History", color: "#7c3aed" },
          { id: "analytics", label: "📊 Analytics", color: "#dc2626" },
          { id: "content", label: "🎨 Content", color: "#ea580c" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            style={{
              padding: "12px 20px",
              border: "none",
              borderBottom: activeTab === tab.id ? `3px solid ${tab.color}` : "3px solid transparent",
              background: "transparent",
              color: activeTab === tab.id ? tab.color : "#333",
              cursor: "pointer",
              fontWeight: activeTab === tab.id ? 600 : 400,
              fontSize: 14,
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Main Content */}
      <main>
        {activeTab === "chat" && <ChatPage role={role} mode={mode} apiUrl={API_URL} />}
        {activeTab === "upload" && <UploadPage apiUrl={API_URL} />}
        {activeTab === "history" && <HistoryPage apiUrl={API_URL} />}
        {activeTab === "analytics" && <AnalyticsPage apiUrl={API_URL} />}
        {activeTab === "content" && <ContentPage role={role} mode={mode} apiUrl={API_URL} />}
      </main>

      <footer style={{ marginTop: 40, padding: "20px 0", fontSize: 12, color: "#777", textAlign: "center", borderTop: "1px solid #eee" }}>
        Backend: <code>{API_URL}</code> | ICLeaF AI v1.0.0
      </footer>
    </div>
  );
}