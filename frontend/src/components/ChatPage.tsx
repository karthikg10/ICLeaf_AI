import { useState } from "react";

type Role = "student" | "teacher" | "admin";
type Mode = "internal" | "external";

type Source = {
  title: string;
  url?: string | null;
  score?: number | null;
  chunkId?: string;
  docName?: string;
  relevanceScore?: number;
};

type ChatResponse = {
  success: boolean;
  answer: string;
  sources: Source[];
  sessionId: string;
  mode: Mode;
  timestamp: string;
};

type ChatMessage = {
  who: "You" | "Assistant";
  text: string;
  mode?: Mode;
  timestamp?: string;
  sources?: Source[];
};

interface ChatPageProps {
  role: Role;
  mode: Mode;
  apiUrl: string;
}

export default function ChatPage({ role, mode, apiUrl }: ChatPageProps) {
  const [sessionId, setSessionId] = useState("");
  const [userId, setUserId] = useState("");
  
  // Internal mode selectors
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [docName, setDocName] = useState("");
  const [docIds, setDocIds] = useState("");  // Comma-separated document IDs
  
  // Chat state
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [, setSources] = useState<Source[]>([]);

  const requireIdentifiers = () => {
    if (!userId.trim() || !sessionId.trim()) {
      alert("Please enter both a user ID and session ID before chatting.");
      return false;
    }
    return true;
  };

  const clearSessionState = () => {
    setSessionId("");
    setMessages([]);
    setSources([]);
  };

  // Reset session
  const resetSession = async () => {
    if (!requireIdentifiers()) {
      return;
    }

    try {
      const response = await fetch(`${apiUrl}/api/chatbot/reset-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId,
          userId,
          resetScope: "full" // Reset entire session
        }),
      });
      
      if (response.ok) {
        setMessages([]);
        setSources([]);
        alert("Session reset successfully!");
      } else {
        console.error("Failed to reset session");
      }
    } catch (error) {
      console.error("Error resetting session:", error);
    }
  };

  // Send chat message
  const sendChat = async () => {
    if (!input.trim() || busy) return;
    if (!requireIdentifiers()) return;
    
    const userMessage = input.trim();
    setMessages(prev => [...prev, { 
      who: "You", 
      text: userMessage, 
      timestamp: new Date().toISOString() 
    }]);
    setInput("");
    setBusy(true);
    setSources([]);

    try {
      const requestBody: any = {
        userId,
        sessionId,
        role,
        mode,
        message: userMessage,
        history: messages.map(m => ({
          role: m.who === "You" ? "user" : "assistant",
          content: m.text,
          timestamp: m.timestamp || new Date().toISOString(),
          subjectId: mode === "internal" ? subjectId : undefined,
          topicId: mode === "internal" ? topicId : undefined,
          docName: mode === "internal" ? docName : undefined,
        })),
      };

      // Add internal mode filters
      if (mode === "internal") {
        if (subjectId) requestBody.subjectId = subjectId;
        if (topicId) requestBody.topicId = topicId;
        if (docName) requestBody.docName = docName;
        // Parse comma-separated docIds and add to request
        if (docIds) {
          const docIdsArray = docIds.split(",").map(id => id.trim()).filter(id => id);
          if (docIdsArray.length > 0) {
            requestBody.docIds = docIdsArray;
          }
        }
      }

      const response = await fetch(`${apiUrl}/api/chatbot/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data: ChatResponse = await response.json();
      
      setMessages(prev => [...prev, { 
        who: "Assistant", 
        text: data.answer, 
        mode: data.mode,
        timestamp: data.timestamp,
        sources: data.sources
      }]);
      setSources(data.sources || []);
    } catch (error: any) {
      setMessages(prev => [...prev, { 
        who: "Assistant", 
        text: `Error: ${error.message}`, 
        mode,
        timestamp: new Date().toISOString()
      }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 1000, margin: "0 auto" }}>
      {/* Session Controls */}
      <div style={{ 
        display: "flex", 
        gap: 12, 
        alignItems: "center", 
        marginBottom: 20,
        padding: 16,
        background: "#f8f9fa",
        borderRadius: 8,
        border: "1px solid #e9ecef"
      }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1 }}>
          <label style={{ fontSize: 14, fontWeight: 600 }}>User ID</label>
          <input
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="Enter user ID"
            style={{
              padding: "6px 8px",
              borderRadius: 4,
              border: "1px solid #ced4da",
              minWidth: 200,
            }}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1 }}>
          <label style={{ fontSize: 14, fontWeight: 600 }}>Session ID</label>
          <input
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
            placeholder="Enter session ID"
            style={{
              padding: "6px 8px",
              borderRadius: 4,
              border: "1px solid #ced4da",
              minWidth: 200,
            }}
          />
        </div>

        <button
          onClick={clearSessionState}
          style={{
            padding: "6px 12px",
            background: "#ffc107",
            color: "#212529",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          Clear Session ID
        </button>

        <button
          onClick={resetSession}
          style={{
            padding: "6px 12px",
            background: "#dc3545",
            color: "white",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            fontSize: 12,
          }}
        >
          Reset Session
        </button>
      </div>

      {/* Internal Mode Selectors */}
      {mode === "internal" && (
        <div style={{ 
          display: "flex", 
          gap: 12, 
          marginBottom: 20,
          padding: 16,
          background: "#e6f6ec",
          borderRadius: 8,
          border: "1px solid #c3e6cb"
        }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: 14, fontWeight: 600, minWidth: 60 }}>Subject:</label>
            <input
              type="text"
              value={subjectId}
              onChange={(e) => setSubjectId(e.target.value)}
              placeholder="Subject ID (optional)"
              style={{
                padding: "6px 8px",
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 12,
                width: 120,
              }}
            />
          </div>
          
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: 14, fontWeight: 600, minWidth: 50 }}>Topic:</label>
            <input
              type="text"
              value={topicId}
              onChange={(e) => setTopicId(e.target.value)}
              placeholder="Topic ID (optional)"
              style={{
                padding: "6px 8px",
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 12,
                width: 120,
              }}
            />
          </div>
          
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: 14, fontWeight: 600, minWidth: 50 }}>Doc:</label>
            <input
              type="text"
              value={docName}
              onChange={(e) => setDocName(e.target.value)}
              placeholder="Document name (optional)"
              style={{
                padding: "6px 8px",
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 12,
                width: 150,
              }}
            />
          </div>
          
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <label style={{ fontSize: 14, fontWeight: 600, minWidth: 60 }}>Doc IDs:</label>
            <input
              type="text"
              value={docIds}
              onChange={(e) => setDocIds(e.target.value)}
              placeholder="Comma-separated docIds (optional)"
              style={{
                padding: "6px 8px",
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 12,
                width: 250,
              }}
            />
          </div>
        </div>
      )}

      {/* Chat Interface */}
      <div style={{
        border: "1px solid #ddd",
        borderRadius: 8,
        background: "#fff",
        boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        overflow: "hidden"
      }}>
        {/* Messages */}
        <div style={{
          minHeight: 400,
          maxHeight: 600,
          overflow: "auto",
          padding: 20,
        }}>
          {messages.length === 0 && (
            <div style={{ 
              color: "#666", 
              fontSize: 14, 
              textAlign: "center",
              padding: "40px 20px"
            }}>
              Start a conversation! Mode: <strong>{mode}</strong> | Role: <strong>{role}</strong>
            </div>
          )}

          {messages.map((message, index) => (
            <div key={index} style={{ marginBottom: 16 }}>
              <div style={{
                display: "flex",
                gap: 8,
                alignItems: "center",
                marginBottom: 8,
              }}>
                <span style={{
                  fontWeight: 600,
                  color: message.who === "You" ? "#333" : "#007bff",
                  fontSize: 14,
                }}>
                  {message.who}
                </span>
                {message.mode && (
                  <span style={{
                    fontSize: 11,
                    padding: "2px 6px",
                    borderRadius: 12,
                    background: message.mode === "external" ? "#e8f1ff" : "#e6f6ec",
                    color: message.mode === "external" ? "#175cd3" : "#0a7a3d",
                    fontWeight: 500,
                  }}>
                    {message.mode}
                  </span>
                )}
                {message.timestamp && (
                  <span style={{ fontSize: 11, color: "#666" }}>
                    {new Date(message.timestamp).toLocaleTimeString()}
                  </span>
                )}
              </div>
              
              <div style={{ 
                whiteSpace: "pre-wrap", 
                lineHeight: 1.5,
                background: message.who === "You" ? "#f8f9fa" : "#fff",
                padding: message.who === "You" ? "12px 16px" : "12px 16px",
                borderRadius: 8,
                border: message.who === "You" ? "1px solid #e9ecef" : "1px solid #dee2e6",
              }}>
                {message.text}
              </div>

              {message.sources && message.sources.length > 0 && (
                <div style={{ marginTop: 8, paddingLeft: 16 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#666", marginBottom: 4 }}>
                    Sources:
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                    {message.sources.map((source, i) => (
                      <li key={i} style={{ marginBottom: 2 }}>
                        {source.url ? (
                          <a href={source.url} target="_blank" rel="noopener noreferrer" style={{ color: "#007bff" }}>
                            {source.title}
                          </a>
                        ) : (
                          <span>{source.title}</span>
                        )}
                        {source.docName && (
                          <span style={{ color: "#666", marginLeft: 8 }}>
                            ({source.docName})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}

          {busy && (
            <div style={{ 
              display: "flex", 
              alignItems: "center", 
              gap: 8,
              color: "#666", 
              fontSize: 14,
              padding: "12px 16px",
              background: "#f8f9fa",
              borderRadius: 8,
              border: "1px solid #e9ecef"
            }}>
              <div style={{
                width: 16,
                height: 16,
                border: "2px solid #ccc",
                borderTop: "2px solid #007bff",
                borderRadius: "50%",
                animation: "spin 1s linear infinite"
              }} />
              Thinking... ({mode} mode)
            </div>
          )}
        </div>

        {/* Input */}
        <div style={{
          borderTop: "1px solid #eee",
          padding: 16,
          background: "#f8f9fa"
        }}>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendChat()}
              placeholder={busy ? "Thinking..." : `Ask anything (${mode} mode)`}
              disabled={busy}
              style={{
                flex: 1,
                padding: 12,
                borderRadius: 6,
                border: "1px solid #ccc",
                outline: "none",
                fontSize: 14,
              }}
            />
            <button
              onClick={sendChat}
              disabled={busy || !input.trim()}
              style={{
                padding: "12px 20px",
                borderRadius: 6,
                border: "none",
                background: busy ? "#ccc" : "#007bff",
                color: "white",
                cursor: busy ? "not-allowed" : "pointer",
                fontWeight: 600,
                fontSize: 14,
              }}
            >
              Send
            </button>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
