import { useState } from "react";

type Role = "Learner" | "Trainer" | "Admin";
type Mode = "cloud" | "internal";

type Source = {
  title: string;
  url?: string | null;
  score?: number | null; // hidden in UI
  // If backend includes page numbers later: page?: number | null;
};

type ChatResponse = {
  answer: string;
  sources: Source[];
};

type GenerateResponse = {
  ok: boolean;
  kind: "summary" | "quiz" | "lesson";
  topic: string;
  content: string;
  sources: Source[];
};

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export default function App() {
  const [role, setRole] = useState<Role>("Learner");
  const [mode, setMode] = useState<Mode>("cloud");
  const [tab, setTab] = useState<"chat" | "generate">("chat");

  // Chat state
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<{ who: "You" | "Assistant"; text: string; mode?: Mode }[]>([]);
  const [sources, setSources] = useState<Source[]>([]);

  // Generate state
  const [genBusy, setGenBusy] = useState(false);
  const [genTopic, setGenTopic] = useState("");
  const [genKind, setGenKind] = useState<"summary" | "quiz" | "lesson">("summary");
  const [genNumQ, setGenNumQ] = useState(8);
  const [genOutput, setGenOutput] = useState<"pdf" | "pptx">("pdf");
  const [genContent, setGenContent] = useState<string>("");
  const [genSources, setGenSources] = useState<Source[]>([]);

  async function sendChat() {
    if (!input.trim() || busy) return;
    const q = input.trim();
    setMessages((m) => [...m, { who: "You", text: q }]);
    setInput("");
    setBusy(true);
    setSources([]); // clear previous run

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          role,
          mode,
          message: q,
          history: [], // stateless for now
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ChatResponse = await res.json();
      setMessages((m) => [...m, { who: "Assistant", text: data.answer, mode }]);
      setSources(data.sources || []);
    } catch (err: any) {
      setMessages((m) => [
        ...m,
        { who: "Assistant", text: `Network/Server error. ${String(err?.message || "")}`, mode },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function runGenerate() {
    if (!genTopic.trim() || genBusy) return;
    setGenBusy(true);
    setGenContent("");
    setGenSources([]);

    try {
      const payload: any = {
        topic: genTopic.trim(),
        role,
        mode,
        kind: genKind,
      };
      if (genKind === "quiz") payload.num_questions = genNumQ;

      const res = await fetch(`${API_URL}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: GenerateResponse = await res.json();
      setGenContent(data.content || "");
      setGenSources(data.sources || []);
    } catch (err: any) {
      setGenContent(`Network/Server error. ${String(err?.message || "")}`);
    } finally {
      setGenBusy(false);
    }
  }

  async function runDownload() {
    if (!genTopic.trim() || genBusy) return;
    try {
      const payload: any = {
        topic: genTopic.trim(),
        role,
        mode,
        kind: genKind,
      };
      if (genKind === "quiz") payload.num_questions = genNumQ;

      const endpoint = genOutput === "pdf" ? "/generate/pdf" : "/generate/pptx";
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const safe = genTopic.trim().replace(/\s+/g, "_");
      const ext = genOutput === "pdf" ? "pdf" : "pptx";
      a.href = url;
      a.download = `${genKind}_${safe || "content"}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Failed to download ${genOutput.toUpperCase()}: ${String(err?.message || err)}`);
    }
  }

  function copy(text: string) {
    navigator.clipboard?.writeText(text).catch(() => {});
  }

  return (
    <div style={{ maxWidth: 980, margin: "2rem auto", padding: "0 1rem", fontFamily: "system-ui" }}>
      {/* Header */}
      <header
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 24 }}>ICLeaF Chatbot</h1>
          <div style={{ fontSize: 12, color: "#666" }}>Cloud & Internal (RAG) + Content Generation</div>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <label style={{ fontSize: 12, color: "#444" }}>
            Role{" "}
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              <option value="Learner">Learner</option>
              <option value="Trainer">Trainer</option>
              <option value="Admin">Admin</option>
            </select>
          </label>

          {/* Color-coded pill toggle for Mode */}
          <div
            style={{
              display: "inline-flex",
              border: "1px solid #ddd",
              borderRadius: 999,
              overflow: "hidden",
            }}
          >
            <button
              onClick={() => setMode("cloud")}
              style={{
                padding: "6px 12px",
                border: "none",
                background: mode === "cloud" ? "#e8f1ff" : "transparent",
                color: mode === "cloud" ? "#175cd3" : "#333",
                cursor: "pointer",
              }}
            >
              Cloud
            </button>
            <button
              onClick={() => setMode("internal")}
              style={{
                padding: "6px 12px",
                border: "none",
                background: mode === "internal" ? "#e6f6ec" : "transparent",
                color: mode === "internal" ? "#0a7a3d" : "#333",
                cursor: "pointer",
              }}
            >
              Internal
            </button>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <nav
        style={{
          display: "flex",
          borderBottom: "1px solid #eee",
          marginBottom: 12,
          gap: 6,
        }}
      >
        <button
          onClick={() => setTab("chat")}
          style={{
            padding: "8px 12px",
            border: "none",
            borderBottom: tab === "chat" ? "2px solid #175cd3" : "2px solid transparent",
            background: "transparent",
            color: tab === "chat" ? "#175cd3" : "#333",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          Chat
        </button>
        <button
          onClick={() => setTab("generate")}
          style={{
            padding: "8px 12px",
            border: "none",
            borderBottom: tab === "generate" ? "2px solid #0a7a3d" : "2px solid transparent",
            background: "transparent",
            color: tab === "generate" ? "#0a7a3d" : "#333",
            cursor: "pointer",
            fontWeight: 600,
          }}
        >
          Generate
        </button>
      </nav>

      {/* Panels */}
      {tab === "chat" ? (
        <main
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            background: "#fff",
            boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
          }}
        >
          <div
            style={{
              minHeight: 320,
              maxHeight: 480,
              overflow: "auto",
              padding: "8px 4px",
              marginBottom: 12,
            }}
          >
            {messages.length === 0 && (
              <div style={{ color: "#666", fontSize: 14 }}>
                Ask a question. Mode is <b>{mode}</b>. Role is <b>{role}</b>.
              </div>
            )}

            {messages.map((m, i) => (
              <div key={i} style={{ marginBottom: 12 }}>
                <div
                  style={{
                    display: "flex",
                    gap: 8,
                    alignItems: "center",
                    fontSize: 12,
                    fontWeight: 700,
                    color: m.who === "You" ? "#333" : "#175cd3",
                  }}
                >
                  <span>{m.who}</span>
                  {m.who === "Assistant" && m.mode && (
                    <span
                      style={{
                        fontWeight: 500,
                        fontSize: 11,
                        padding: "2px 8px",
                        borderRadius: 999,
                        background: m.mode === "cloud" ? "#e8f1ff" : "#e6f6ec",
                        color: m.mode === "cloud" ? "#175cd3" : "#0a7a3d",
                      }}
                    >
                      {m.mode === "cloud" ? "Cloud Mode" : "Internal Mode"}
                    </span>
                  )}
                </div>
                <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{m.text}</div>
              </div>
            ))}

            {busy && (
              <div style={{ fontSize: 12, color: "#666", marginTop: 8 }}>
                Thinking… (calling {mode === "cloud" ? "Cloud" : "Internal RAG"})
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendChat()}
              placeholder={busy ? "Thinking..." : `Ask anything (${mode} mode)`}
              disabled={busy}
              style={{
                flex: 1,
                padding: 10,
                borderRadius: 6,
                border: "1px solid #ccc",
                outline: "none",
              }}
            />
            <button
              onClick={sendChat}
              disabled={busy}
              style={{
                padding: "10px 16px",
                borderRadius: 6,
                border: "1px solid #ccc",
                background: busy ? "#f2f2f2" : "#f7f7f7",
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              Send
            </button>
          </div>

          {sources?.length > 0 && (
            <section style={{ marginTop: 16 }}>
              <h3 style={{ margin: "0 0 8px" }}>Sources</h3>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {sources.map((s, i) => (
                  <li key={i} style={{ marginBottom: 6 }}>
                    {s.url ? (
                      <a href={s.url} target="_blank" rel="noreferrer">
                        [{i + 1}] {s.title}
                      </a>
                    ) : (
                      <span>[{i + 1}] {s.title}</span>
                    )}
                    {/* score intentionally hidden */}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </main>
      ) : (
        <main
          style={{
            border: "1px solid #ddd",
            borderRadius: 8,
            padding: 16,
            background: "#fff",
            boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
          }}
        >
          <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
            <input
              value={genTopic}
              onChange={(e) => setGenTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runGenerate()}
              placeholder={`Topic to generate (${mode} mode)`}
              disabled={genBusy}
              style={{
                flex: 1,
                minWidth: 260,
                padding: 10,
                borderRadius: 6,
                border: "1px solid #ccc",
                outline: "none",
              }}
            />

            <label style={{ fontSize: 12, color: "#444" }}>
              Kind{" "}
              <select
                value={genKind}
                onChange={(e) => setGenKind(e.target.value as typeof genKind)}
                disabled={genBusy}
              >
                <option value="summary">Summary</option>
                <option value="quiz">Quiz</option>
                <option value="lesson">Lesson</option>
              </select>
            </label>

            {genKind === "quiz" && (
              <label style={{ fontSize: 12, color: "#444" }}>
                # Qs{" "}
                <input
                  type="number"
                  min={3}
                  max={20}
                  value={genNumQ}
                  onChange={(e) => setGenNumQ(parseInt(e.target.value || "8", 10))}
                  disabled={genBusy}
                  style={{ width: 64, marginLeft: 6 }}
                />
              </label>
            )}

            <label style={{ fontSize: 12, color: "#444" }}>
              Output{" "}
              <select
                value={genOutput}
                onChange={(e) => setGenOutput(e.target.value as "pdf" | "pptx")}
                disabled={genBusy}
              >
                <option value="pdf">PDF</option>
                <option value="pptx">PPT</option>
              </select>
            </label>

            <button
              onClick={runGenerate}
              disabled={genBusy || !genTopic.trim()}
              style={{
                padding: "10px 16px",
                borderRadius: 6,
                border: "1px solid #ccc",
                background: genBusy ? "#f2f2f2" : "#f7f7f7",
                cursor: genBusy ? "not-allowed" : "pointer",
              }}
            >
              {genBusy ? "Generating…" : "Generate"}
            </button>

            <button
              onClick={runDownload}
              disabled={genBusy || !genTopic.trim()}
              style={{
                padding: "10px 16px",
                borderRadius: 6,
                border: "1px solid #ccc",
                background: genBusy ? "#f2f2f2" : "#fafafa",
                cursor: genBusy ? "not-allowed" : "pointer",
              }}
              title={`Generate and download as ${genOutput.toUpperCase()}`}
            >
              Download {genOutput.toUpperCase()}
            </button>
          </div>

          <div style={{ minHeight: 160 }}>
            {!genContent && !genBusy && (
              <div style={{ color: "#666", fontSize: 14 }}>
                Enter a topic and click <b>Generate</b>. Mode is <b>{mode}</b>. Role is <b>{role}</b>.
              </div>
            )}
            {genBusy && <div style={{ color: "#666", fontSize: 14 }}>Generating…</div>}

            {genContent && (
              <div style={{ position: "relative" }}>
                <button
                  onClick={() => copy(genContent)}
                  style={{
                    position: "absolute",
                    right: 0,
                    top: -8,
                    fontSize: 12,
                    padding: "4px 8px",
                    borderRadius: 6,
                    border: "1px solid #ddd",
                    background: "#fafafa",
                    cursor: "pointer",
                  }}
                  title="Copy to clipboard"
                >
                  Copy
                </button>
                <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{genContent}</div>
              </div>
            )}
          </div>

          {genSources?.length > 0 && (
            <section style={{ marginTop: 16 }}>
              <h3 style={{ margin: "0 0 8px" }}>Sources</h3>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {genSources.map((s, i) => (
                  <li key={i} style={{ marginBottom: 6 }}>
                    {s.url ? (
                      <a href={s.url} target="_blank" rel="noreferrer">
                        [{i + 1}] {s.title}
                      </a>
                    ) : (
                      <span>[{i + 1}] {s.title}</span>
                    )}
                    {/* score intentionally hidden */}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </main>
      )}

      <footer style={{ marginTop: 20, fontSize: 12, color: "#777" }}>
        Backend: <code>{API_URL}</code>
      </footer>
    </div>
  );
}
