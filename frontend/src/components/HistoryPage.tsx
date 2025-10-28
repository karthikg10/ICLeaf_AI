import { useState, useEffect } from "react";

type Conversation = {
  sessionId: string;
  userId: string;
  mode: string;
  userMessage: string;
  aiResponse: string;
  responseTime: number;
  tokenCount: number;
  subjectId?: string;
  topicId?: string;
  docName?: string;
  timestamp: string;
};

type HistoryResponse = {
  ok: boolean;
  conversations: Conversation[];
  total_count: number;
};

interface HistoryPageProps {
  apiUrl: string;
}

export default function HistoryPage({ apiUrl }: HistoryPageProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Filters
  const [userId, setUserId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [topicId, setTopicId] = useState("");
  const [docName, setDocName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  // Pagination
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);

  const fetchHistory = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (userId) params.append("userId", userId);
      if (sessionId) params.append("sessionId", sessionId);
      if (subjectId) params.append("subjectId", subjectId);
      if (topicId) params.append("topicId", topicId);
      if (docName) params.append("docName", docName);
      if (startDate) params.append("start_date", startDate);
      if (endDate) params.append("end_date", endDate);
      params.append("limit", limit.toString());
      params.append("offset", offset.toString());

      const response = await fetch(`${apiUrl}/api/chatbot/history?${params}`);
      const data: HistoryResponse = await response.json();

      if (data.ok) {
        setConversations(data.conversations);
        setTotalCount(data.total_count);
      } else {
        setError("Failed to fetch history");
      }
    } catch (err: any) {
      setError(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [offset, limit]);

  const handleSearch = () => {
    setOffset(0);
    setCurrentPage(1);
    fetchHistory();
  };

  const handleClearFilters = () => {
    setUserId("");
    setSessionId("");
    setSubjectId("");
    setTopicId("");
    setDocName("");
    setStartDate("");
    setEndDate("");
    setOffset(0);
    setCurrentPage(1);
  };

  const formatDate = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  const formatDuration = (seconds: number) => {
    if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
    return `${seconds.toFixed(2)}s`;
  };

  const totalPages = Math.ceil(totalCount / limit);

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: "0 0 8px", fontSize: 24, fontWeight: 600 }}>
          Conversation History
        </h2>
        <p style={{ margin: 0, color: "#666", fontSize: 14 }}>
          View and filter conversation history across all sessions and users.
        </p>
      </div>

      {/* Filters */}
      <div style={{
        background: "#f8f9fa",
        padding: 20,
        borderRadius: 8,
        border: "1px solid #e9ecef",
        marginBottom: 24,
      }}>
        <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
          Filters
        </h3>
        
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 16 }}>
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              User ID
            </label>
            <input
              type="text"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="Filter by user"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
          
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Session ID
            </label>
            <input
              type="text"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              placeholder="Filter by session"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
          
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Subject ID
            </label>
            <input
              type="text"
              value={subjectId}
              onChange={(e) => setSubjectId(e.target.value)}
              placeholder="Filter by subject"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
          
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Topic ID
            </label>
            <input
              type="text"
              value={topicId}
              onChange={(e) => setTopicId(e.target.value)}
              placeholder="Filter by topic"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
          
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Document Name
            </label>
            <input
              type="text"
              value={docName}
              onChange={(e) => setDocName(e.target.value)}
              placeholder="Filter by document"
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Start Date
            </label>
            <input
              type="datetime-local"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
          
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              End Date
            </label>
            <input
              type="datetime-local"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            />
          </div>
          
          <div>
            <label style={{ display: "block", fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
              Results per page
            </label>
            <select
              value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value))}
              style={{
                width: "100%",
                padding: 8,
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>

        <div style={{ display: "flex", gap: 12 }}>
          <button
            onClick={handleSearch}
            disabled={loading}
            style={{
              padding: "10px 20px",
              background: loading ? "#ccc" : "#007bff",
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: loading ? "not-allowed" : "pointer",
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            {loading ? "Loading..." : "Search"}
          </button>
          
          <button
            onClick={handleClearFilters}
            style={{
              padding: "10px 20px",
              background: "#6c757d",
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            Clear Filters
          </button>
        </div>
      </div>

      {/* Results */}
      {error && (
        <div style={{
          padding: 16,
          background: "#f8d7da",
          color: "#721c24",
          borderRadius: 6,
          border: "1px solid #f5c6cb",
          marginBottom: 16,
        }}>
          {error}
        </div>
      )}

      {/* Pagination Info */}
      <div style={{ 
        display: "flex", 
        justifyContent: "space-between", 
        alignItems: "center", 
        marginBottom: 16,
        fontSize: 14,
        color: "#666"
      }}>
        <div>
          Showing {conversations.length} of {totalCount} conversations
        </div>
        <div>
          Page {currentPage} of {totalPages}
        </div>
      </div>

      {/* Table */}
      <div style={{
        background: "#fff",
        borderRadius: 8,
        border: "1px solid #e9ecef",
        overflow: "hidden",
        boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
      }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f8f9fa", borderBottom: "1px solid #e9ecef" }}>
                <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Timestamp</th>
                <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>User</th>
                <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Session</th>
                <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Mode</th>
                <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Message</th>
                <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Response Time</th>
                <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Tokens</th>
                <th style={{ padding: 12, textAlign: "left", fontWeight: 600, fontSize: 14 }}>Context</th>
              </tr>
            </thead>
            <tbody>
              {conversations.map((conv, index) => (
                <tr key={index} style={{ borderBottom: "1px solid #f1f3f4" }}>
                  <td style={{ padding: 12, fontSize: 12, color: "#666" }}>
                    {formatDate(conv.timestamp)}
                  </td>
                  <td style={{ padding: 12, fontSize: 14 }}>
                    <code style={{ background: "#f1f3f4", padding: "2px 6px", borderRadius: 3 }}>
                      {conv.userId}
                    </code>
                  </td>
                  <td style={{ padding: 12, fontSize: 14 }}>
                    <code style={{ background: "#f1f3f4", padding: "2px 6px", borderRadius: 3 }}>
                      {conv.sessionId}
                    </code>
                  </td>
                  <td style={{ padding: 12 }}>
                    <span style={{
                      padding: "2px 8px",
                      borderRadius: 12,
                      fontSize: 11,
                      fontWeight: 600,
                      background: conv.mode === "cloud" ? "#e8f1ff" : "#e6f6ec",
                      color: conv.mode === "cloud" ? "#175cd3" : "#0a7a3d",
                    }}>
                      {conv.mode}
                    </span>
                  </td>
                  <td style={{ padding: 12, fontSize: 14, maxWidth: 300 }}>
                    <div 
                      style={{ 
                        whiteSpace: "nowrap", 
                        overflow: "hidden", 
                        textOverflow: "ellipsis"
                      }}
                      title={conv.userMessage}
                    >
                      {conv.userMessage}
                    </div>
                  </td>
                  <td style={{ padding: 12, fontSize: 14, color: "#666" }}>
                    {formatDuration(conv.responseTime)}
                  </td>
                  <td style={{ padding: 12, fontSize: 14, color: "#666" }}>
                    {conv.tokenCount.toLocaleString()}
                  </td>
                  <td style={{ padding: 12, fontSize: 12, color: "#666" }}>
                    {conv.subjectId && (
                      <div><strong>S:</strong> {conv.subjectId}</div>
                    )}
                    {conv.topicId && (
                      <div><strong>T:</strong> {conv.topicId}</div>
                    )}
                    {conv.docName && (
                      <div><strong>D:</strong> {conv.docName}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {conversations.length === 0 && !loading && (
          <div style={{ 
            padding: 40, 
            textAlign: "center", 
            color: "#666",
            fontSize: 14 
          }}>
            No conversations found. Try adjusting your filters.
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ 
          display: "flex", 
          justifyContent: "center", 
          gap: 8, 
          marginTop: 20 
        }}>
          <button
            onClick={() => {
              setOffset(Math.max(0, offset - limit));
              setCurrentPage(Math.max(1, currentPage - 1));
            }}
            disabled={currentPage === 1}
            style={{
              padding: "8px 16px",
              background: currentPage === 1 ? "#f8f9fa" : "#007bff",
              color: currentPage === 1 ? "#666" : "white",
              border: "none",
              borderRadius: 6,
              cursor: currentPage === 1 ? "not-allowed" : "pointer",
              fontSize: 14,
            }}
          >
            Previous
          </button>
          
          <span style={{ 
            padding: "8px 16px", 
            display: "flex", 
            alignItems: "center",
            fontSize: 14,
            color: "#666"
          }}>
            {currentPage} / {totalPages}
          </span>
          
          <button
            onClick={() => {
              setOffset(offset + limit);
              setCurrentPage(Math.min(totalPages, currentPage + 1));
            }}
            disabled={currentPage === totalPages}
            style={{
              padding: "8px 16px",
              background: currentPage === totalPages ? "#f8f9fa" : "#007bff",
              color: currentPage === totalPages ? "#666" : "white",
              border: "none",
              borderRadius: 6,
              cursor: currentPage === totalPages ? "not-allowed" : "pointer",
              fontSize: 14,
            }}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
