import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = "http://localhost:8000";

const verdictColor = (v) => ({
  apply: "#00ff88",
  review: "#ffcc00",
  skip: "#ff4466",
}[v] || "#888");

const verdictBg = (v) => ({
  apply: "rgba(0,255,136,0.08)",
  review: "rgba(255,204,0,0.08)",
  skip: "rgba(255,68,102,0.06)",
}[v] || "transparent");

export default function App() {
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState({});
  const [log, setLog] = useState([]);
  const [running, setRunning] = useState(false);
  const [tab, setTab] = useState("queue");
  const [filter, setFilter] = useState("all");
  const logRef = useRef(null);

  const fetchJobs = async () => {
    const res = await axios.get(`${API}/jobs`);
    setJobs(res.data);
  };

  const fetchStats = async () => {
    const res = await axios.get(`${API}/stats`);
    setStats(res.data);
  };

  useEffect(() => {
    fetchJobs();
    fetchStats();
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  const runPipeline = () => {
    setRunning(true);
    setLog([]);
    setTab("live");
    const es = new EventSource(`${API}/pipeline/run?max=15`);
    es.onmessage = (e) => {
      const { event, data } = JSON.parse(e.data);
      if (event === "scout_done") {
        setLog(l => [...l, { type: "info", text: `🔍 Scout complete — ${data} listings found` }]);
      } else if (event === "job_scored") {
        const icon = data.verdict === "apply" ? "✅" : data.verdict === "review" ? "👀" : "❌";
        setLog(l => [...l, { type: data.verdict, text: `${icon} ${data.score}/100 — ${data.title} @ ${data.company}` }]);
      } else if (event === "done") {
        setLog(l => [...l, { type: "info", text: "✔ Pipeline complete" }]);
        setRunning(false);
        fetchJobs();
        fetchStats();
        es.close();
      } else if (event === "error") {
        setLog(l => [...l, { type: "error", text: `❌ Error: ${data}` }]);
        setRunning(false);
        es.close();
      }
    };
    es.onerror = () => {
      setLog(l => [...l, { type: "error", text: "Connection lost" }]);
      setRunning(false);
      es.close();
    };
  };

  const approve = async (id) => {
    await axios.post(`${API}/jobs/${id}/approve`);
    fetchJobs(); fetchStats();
  };

  const skip = async (id) => {
    await axios.post(`${API}/jobs/${id}/skip`);
    fetchJobs(); fetchStats();
  };

  const filtered = jobs.filter(j => {
    if (filter === "all") return j.verdict !== "skip" || j.status === "approved";
    if (filter === "apply") return j.verdict === "apply";
    if (filter === "review") return j.verdict === "review";
    if (filter === "approved") return j.status === "approved";
    return true;
  }).sort((a, b) => b.score - a.score);

  return (
    <div style={{ minHeight: "100vh", background: "#0a0a0f", color: "#e0e0e0", fontFamily: "'IBM Plex Mono', monospace" }}>
      <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Space+Grotesk:wght@400;600;700&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ borderBottom: "1px solid #1e1e2e", padding: "20px 32px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 22, fontWeight: 700, color: "#00ff88", letterSpacing: "-0.5px" }}>
            ⚡ intern-agent
          </div>
          <div style={{ fontSize: 11, color: "#555", marginTop: 2 }}>autonomous internship pipeline</div>
        </div>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          {[
            { k: "total", label: "total", color: "#888" },
            { k: "apply", label: "apply", color: "#00ff88" },
            { k: "review", label: "review", color: "#ffcc00" },
            { k: "approved", label: "approved", color: "#00aaff" },
          ].map(s => (
            <div key={s.k} style={{ textAlign: "center" }}>
              <div style={{ fontSize: 20, fontWeight: 600, color: s.color }}>{stats[s.k] ?? 0}</div>
              <div style={{ fontSize: 10, color: "#444", textTransform: "uppercase" }}>{s.label}</div>
            </div>
          ))}
          <button
            onClick={runPipeline}
            disabled={running}
            style={{
              marginLeft: 16, padding: "10px 24px", background: running ? "#1a1a2e" : "#00ff88",
              color: running ? "#555" : "#0a0a0f", border: "none", borderRadius: 6,
              fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600, fontSize: 13,
              cursor: running ? "not-allowed" : "pointer", transition: "all 0.2s"
            }}
          >
            {running ? "running..." : "▶ run pipeline"}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ borderBottom: "1px solid #1e1e2e", padding: "0 32px", display: "flex", gap: 0 }}>
        {["queue", "live"].map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: "12px 20px", background: "none", border: "none",
            borderBottom: tab === t ? "2px solid #00ff88" : "2px solid transparent",
            color: tab === t ? "#00ff88" : "#555", fontFamily: "'IBM Plex Mono', monospace",
            fontSize: 12, cursor: "pointer", textTransform: "uppercase", letterSpacing: 1
          }}>{t}</button>
        ))}
      </div>

      <div style={{ padding: "24px 32px" }}>

        {/* Queue Tab */}
        {tab === "queue" && (
          <>
            {/* Filter bar */}
            <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
              {["all", "apply", "review", "approved"].map(f => (
                <button key={f} onClick={() => setFilter(f)} style={{
                  padding: "6px 16px", borderRadius: 20,
                  background: filter === f ? "#00ff88" : "#111",
                  color: filter === f ? "#0a0a0f" : "#555",
                  border: "1px solid", borderColor: filter === f ? "#00ff88" : "#222",
                  fontFamily: "'IBM Plex Mono', monospace", fontSize: 11,
                  cursor: "pointer", textTransform: "uppercase", letterSpacing: 1
                }}>{f}</button>
              ))}
            </div>

            {/* Job cards */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {filtered.length === 0 && (
                <div style={{ color: "#333", textAlign: "center", padding: 60, fontSize: 13 }}>
                  no listings yet — run the pipeline to start
                </div>
              )}
              {filtered.map(j => (
                <div key={j.id} style={{
                  background: verdictBg(j.verdict), border: "1px solid #1e1e2e",
                  borderLeft: `3px solid ${verdictColor(j.verdict)}`,
                  borderRadius: 8, padding: "16px 20px",
                  display: "flex", alignItems: "center", gap: 16,
                  opacity: j.status === "skipped" ? 0.4 : 1
                }}>
                  {/* Score */}
                  <div style={{ minWidth: 48, textAlign: "center" }}>
                    <div style={{ fontSize: 20, fontWeight: 700, color: verdictColor(j.verdict) }}>{j.score}</div>
                    <div style={{ fontSize: 9, color: "#444" }}>SCORE</div>
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 14, color: "#e0e0e0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {j.job.title}
                    </div>
                    <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
                      {j.job.company} · {j.job.location} · {j.job.stipend}
                    </div>
                    {j.reasons?.[0] && (
                      <div style={{ fontSize: 11, color: "#444", marginTop: 4 }}>{j.reasons[0]}</div>
                    )}
                  </div>

                  {/* Source badge */}
                  <div style={{ fontSize: 10, color: "#333", background: "#111", padding: "3px 8px", borderRadius: 4, border: "1px solid #222" }}>
                    {j.job.source || "internshala"}
                  </div>

                  {/* Status / Actions */}
                  {j.status === "approved" ? (
                    <div style={{ fontSize: 11, color: "#00aaff", padding: "6px 14px", border: "1px solid #00aaff33", borderRadius: 4 }}>approved</div>
                  ) : j.status === "skipped" ? (
                    <div style={{ fontSize: 11, color: "#333" }}>skipped</div>
                  ) : (
                    <div style={{ display: "flex", gap: 8 }}>
                      {j.job.url && (
                        <a href={j.job.url} target="_blank" rel="noreferrer" style={{
                          fontSize: 11, color: "#555", padding: "6px 12px",
                          border: "1px solid #222", borderRadius: 4, textDecoration: "none"
                        }}>view</a>
                      )}
                      <button onClick={() => skip(j.id)} style={{
                        fontSize: 11, color: "#ff4466", padding: "6px 12px",
                        background: "none", border: "1px solid #ff446633", borderRadius: 4, cursor: "pointer"
                      }}>skip</button>
                      <button onClick={() => approve(j.id)} style={{
                        fontSize: 11, color: "#0a0a0f", padding: "6px 14px",
                        background: "#00ff88", border: "none", borderRadius: 4, cursor: "pointer", fontWeight: 600
                      }}>approve</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        {/* Live Tab */}
        {tab === "live" && (
          <div>
            <div style={{ fontSize: 11, color: "#444", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
              pipeline log
            </div>
            <div ref={logRef} style={{
              background: "#050508", border: "1px solid #1e1e2e", borderRadius: 8,
              padding: 20, height: "65vh", overflowY: "auto", fontFamily: "'IBM Plex Mono', monospace", fontSize: 12
            }}>
              {log.length === 0 && (
                <div style={{ color: "#333" }}>press "run pipeline" to start...</div>
              )}
              {log.map((l, i) => (
                <div key={i} style={{
                  color: l.type === "apply" ? "#00ff88" : l.type === "review" ? "#ffcc00" : l.type === "error" ? "#ff4466" : "#555",
                  padding: "2px 0", lineHeight: 1.6
                }}>{l.text}</div>
              ))}
              {running && <div style={{ color: "#333", animation: "pulse 1s infinite" }}>▋</div>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}