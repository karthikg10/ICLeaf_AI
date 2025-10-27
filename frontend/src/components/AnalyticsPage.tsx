import { useState, useEffect } from "react";

type AnalyticsMetrics = {
  total_conversations: number;
  total_users: number;
  total_sessions: number;
  average_response_time: number;
  total_tokens_used: number;
  mode_usage: Record<string, number>;
  subject_usage: Record<string, number>;
  topic_usage: Record<string, number>;
  document_usage: Record<string, number>;
  daily_activity: Array<{ date: string; count: number }>;
  hourly_activity: Array<{ hour: number; count: number }>;
};

type AnalyticsResponse = {
  ok: boolean;
  metrics: AnalyticsMetrics;
};

interface AnalyticsPageProps {
  apiUrl: string;
}

export default function AnalyticsPage({ apiUrl }: AnalyticsPageProps) {
  const [metrics, setMetrics] = useState<AnalyticsMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState<"7d" | "30d" | "90d" | "all">("30d");

  const fetchAnalytics = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (dateRange !== "all") {
        const days = parseInt(dateRange.replace("d", ""));
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - days);
        params.append("start_date", startDate.toISOString());
      }

      const response = await fetch(`${apiUrl}/api/chatbot/analytics?${params}`);
      const data: AnalyticsResponse = await response.json();

      if (data.ok) {
        setMetrics(data.metrics);
      } else {
        setError("Failed to fetch analytics");
      }
    } catch (err: any) {
      setError(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, [dateRange]);

  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  const formatDuration = (seconds: number) => {
    if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
    return `${seconds.toFixed(2)}s`;
  };

  const SimpleBarChart = ({ data, title, color = "#007bff" }: { 
    data: Array<{ [key: string]: any }>; 
    title: string; 
    color?: string;
  }) => {
    if (!data || data.length === 0) return <div>No data available</div>;

    const maxValue = Math.max(...data.map(d => Object.values(d)[1] as number));
    const keyField = Object.keys(data[0])[0];
    const valueField = Object.keys(data[0])[1];

    return (
      <div>
        <h4 style={{ margin: "0 0 12px", fontSize: 16, fontWeight: 600 }}>{title}</h4>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {data.slice(0, 10).map((item, index) => {
            const value = item[valueField] as number;
            const percentage = (value / maxValue) * 100;
            return (
              <div key={index} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ minWidth: 120, fontSize: 12, color: "#666" }}>
                  {String(item[keyField]).substring(0, 20)}
                  {String(item[keyField]).length > 20 && "..."}
                </div>
                <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{
                    height: 20,
                    background: color,
                    width: `${percentage}%`,
                    borderRadius: 2,
                    minWidth: 2,
                  }} />
                  <span style={{ fontSize: 12, fontWeight: 600, minWidth: 30 }}>
                    {value}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const SimpleLineChart = ({ data, title, color = "#007bff" }: { 
    data: Array<{ [key: string]: any }>; 
    title: string; 
    color?: string;
  }) => {
    if (!data || data.length === 0) return <div>No data available</div>;

    const maxValue = Math.max(...data.map(d => Object.values(d)[1] as number));
    const keyField = Object.keys(data[0])[0];
    const valueField = Object.keys(data[0])[1];

    return (
      <div>
        <h4 style={{ margin: "0 0 12px", fontSize: 16, fontWeight: 600 }}>{title}</h4>
        <div style={{ 
          height: 200, 
          display: "flex", 
          alignItems: "end", 
          gap: 2,
          padding: "12px 0",
          borderBottom: "1px solid #eee"
        }}>
          {data.map((item, index) => {
            const value = item[valueField] as number;
            const height = (value / maxValue) * 100;
            return (
              <div key={index} style={{ 
                flex: 1, 
                display: "flex", 
                flexDirection: "column", 
                alignItems: "center",
                gap: 4
              }}>
                <div style={{
                  height: `${height}%`,
                  background: color,
                  width: "100%",
                  borderRadius: 2,
                  minHeight: 2,
                }} />
                <div style={{ fontSize: 10, color: "#666", textAlign: "center" }}>
                  {String(item[keyField])}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div style={{ 
        display: "flex", 
        justifyContent: "center", 
        alignItems: "center", 
        height: 400,
        fontSize: 16,
        color: "#666"
      }}>
        Loading analytics...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{
        padding: 20,
        background: "#f8d7da",
        color: "#721c24",
        borderRadius: 6,
        border: "1px solid #f5c6cb",
      }}>
        {error}
      </div>
    );
  }

  if (!metrics) {
    return <div>No analytics data available</div>;
  }

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h2 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>
            Analytics Dashboard
          </h2>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <label style={{ fontSize: 14, fontWeight: 600 }}>Date Range:</label>
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value as any)}
              style={{
                padding: "6px 12px",
                border: "1px solid #ccc",
                borderRadius: 4,
                fontSize: 14,
              }}
            >
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="90d">Last 90 days</option>
              <option value="all">All time</option>
            </select>
            <button
              onClick={fetchAnalytics}
              style={{
                padding: "6px 12px",
                background: "#007bff",
                color: "white",
                border: "none",
                borderRadius: 4,
                cursor: "pointer",
                fontSize: 14,
              }}
            >
              Refresh
            </button>
          </div>
        </div>
        <p style={{ margin: 0, color: "#666", fontSize: 14 }}>
          Insights and metrics about system usage and performance.
        </p>
      </div>

      {/* Key Metrics */}
      <div style={{ 
        display: "grid", 
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", 
        gap: 20, 
        marginBottom: 32 
      }}>
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: "#007bff", marginBottom: 4 }}>
            {formatNumber(metrics.total_conversations)}
          </div>
          <div style={{ fontSize: 14, color: "#666", fontWeight: 600 }}>Total Conversations</div>
        </div>

        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: "#28a745", marginBottom: 4 }}>
            {formatNumber(metrics.total_users)}
          </div>
          <div style={{ fontSize: 14, color: "#666", fontWeight: 600 }}>Unique Users</div>
        </div>

        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: "#ffc107", marginBottom: 4 }}>
            {formatNumber(metrics.total_sessions)}
          </div>
          <div style={{ fontSize: 14, color: "#666", fontWeight: 600 }}>Active Sessions</div>
        </div>

        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: "#dc3545", marginBottom: 4 }}>
            {formatDuration(metrics.average_response_time)}
          </div>
          <div style={{ fontSize: 14, color: "#666", fontWeight: 600 }}>Avg Response Time</div>
        </div>

        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: "#6f42c1", marginBottom: 4 }}>
            {formatNumber(metrics.total_tokens_used)}
          </div>
          <div style={{ fontSize: 14, color: "#666", fontWeight: 600 }}>Tokens Used</div>
        </div>
      </div>

      {/* Charts Grid */}
      <div style={{ 
        display: "grid", 
        gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))", 
        gap: 24 
      }}>
        {/* Mode Usage */}
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <SimpleBarChart
            data={Object.entries(metrics.mode_usage).map(([mode, count]) => ({ mode, count }))}
            title="Mode Usage"
            color="#007bff"
          />
        </div>

        {/* Subject Usage */}
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <SimpleBarChart
            data={Object.entries(metrics.subject_usage).map(([subject, count]) => ({ subject, count }))}
            title="Subject Usage"
            color="#28a745"
          />
        </div>

        {/* Topic Usage */}
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <SimpleBarChart
            data={Object.entries(metrics.topic_usage).map(([topic, count]) => ({ topic, count }))}
            title="Topic Usage"
            color="#ffc107"
          />
        </div>

        {/* Document Usage */}
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <SimpleBarChart
            data={Object.entries(metrics.document_usage).map(([doc, count]) => ({ doc, count }))}
            title="Document Usage"
            color="#dc3545"
          />
        </div>

        {/* Daily Activity */}
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <SimpleLineChart
            data={metrics.daily_activity}
            title="Daily Activity"
            color="#007bff"
          />
        </div>

        {/* Hourly Activity */}
        <div style={{
          background: "#fff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e9ecef",
          boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
        }}>
          <SimpleLineChart
            data={metrics.hourly_activity}
            title="Hourly Activity"
            color="#28a745"
          />
        </div>
      </div>

      {/* Summary Stats */}
      <div style={{
        background: "#f8f9fa",
        padding: 20,
        borderRadius: 8,
        border: "1px solid #e9ecef",
        marginTop: 24,
      }}>
        <h3 style={{ margin: "0 0 16px", fontSize: 18, fontWeight: 600 }}>
          📊 Summary Statistics
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 16 }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#666", marginBottom: 4 }}>
              Average Conversations per User
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#333" }}>
              {metrics.total_users > 0 ? (metrics.total_conversations / metrics.total_users).toFixed(1) : "0"}
            </div>
          </div>
          
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#666", marginBottom: 4 }}>
              Average Conversations per Session
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#333" }}>
              {metrics.total_sessions > 0 ? (metrics.total_conversations / metrics.total_sessions).toFixed(1) : "0"}
            </div>
          </div>
          
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#666", marginBottom: 4 }}>
              Average Tokens per Conversation
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#333" }}>
              {metrics.total_conversations > 0 ? (metrics.total_tokens_used / metrics.total_conversations).toFixed(0) : "0"}
            </div>
          </div>
          
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#666", marginBottom: 4 }}>
              Most Active Mode
            </div>
            <div style={{ fontSize: 20, fontWeight: 700, color: "#333" }}>
              {Object.entries(metrics.mode_usage).length > 0 
                ? Object.entries(metrics.mode_usage).reduce((a, b) => a[1] > b[1] ? a : b)[0]
                : "N/A"
              }
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
