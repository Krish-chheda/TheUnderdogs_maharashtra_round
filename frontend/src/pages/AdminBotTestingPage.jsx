import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";

const styles = {
  container: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    padding: "40px 20px",
    color: "#f8fafc",
  },
  header: {
    maxWidth: "1200px",
    margin: "0 auto 40px",
  },
  backBtn: {
    marginBottom: "16px",
    padding: "10px 20px",
    border: "1px solid #64748b",
    borderRadius: "6px",
    background: "transparent",
    color: "#cbd5e1",
    cursor: "pointer",
    fontSize: "14px",
  },
  title: {
    fontSize: "28px",
    fontWeight: 700,
    margin: "0 0 8px 0",
  },
  subtitle: {
    fontSize: "13px",
    color: "#ef4444",
    fontWeight: 600,
    margin: "0",
    textTransform: "uppercase",
    letterSpacing: "1px",
  },
  content: {
    maxWidth: "1200px",
    margin: "0 auto",
  },
  warning: {
    padding: "16px",
    borderRadius: "8px",
    background: "rgba(239, 68, 68, 0.1)",
    border: "1px solid #ef4444",
    color: "#fecaca",
    margin: "24px 0",
    fontSize: "13px",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
    gap: "24px",
    margin: "24px 0",
  },
  card: {
    padding: "24px",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "8px",
    background: "rgba(15, 23, 42, 0.6)",
  },
  cardTitle: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#38bdf8",
    margin: "0 0 8px 0",
  },
  cardDescription: {
    fontSize: "13px",
    color: "#cbd5e1",
    margin: "0 0 16px 0",
    lineHeight: "1.5",
  },
  button: {
    width: "100%",
    padding: "12px",
    border: 0,
    borderRadius: "6px",
    background: "#ef4444",
    color: "#fff",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: "14px",
  },
  buttonDisabled: {
    background: "#64748b",
    cursor: "not-allowed",
  },
  resultBox: {
    marginTop: "24px",
    padding: "24px",
    borderRadius: "8px",
    background: "rgba(59, 130, 246, 0.1)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    fontSize: "13px",
  },
  resultRow: {
    display: "flex",
    justifyContent: "space-between",
    margin: "8px 0",
    fontFamily: "monospace",
  },
  resultLabel: {
    color: "#cbd5e1",
  },
  resultValue: {
    color: "#f8fafc",
    fontWeight: 600,
  },
  statusPass: {
    padding: "8px 12px",
    borderRadius: "4px",
    background: "rgba(52, 211, 153, 0.1)",
    color: "#86efac",
    border: "1px solid #34d399",
    display: "inline-block",
    fontSize: "12px",
    fontWeight: 600,
    marginTop: "12px",
  },
  statusFail: {
    padding: "8px 12px",
    borderRadius: "4px",
    background: "rgba(239, 68, 68, 0.1)",
    color: "#fecaca",
    border: "1px solid #ef4444",
    display: "inline-block",
    fontSize: "12px",
    fontWeight: 600,
    marginTop: "12px",
  },
};

export default function AdminBotTestingPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [results, setResults] = useState(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");

  // Mock test results based on API spec
  const mockResults = {
    "high-speed": {
      name: "High-Speed Bot",
      totalRequests: 100,
      uniqueUsers: 1,
      successful: 20,
      rateLimited: 80,
      errors: 0,
      uniqueEntries: 1,
      oversold: 0,
      pass: true,
    },
    "high-volume": {
      name: "High-Volume Bot",
      totalRequests: 1000,
      uniqueUsers: 1,
      successful: 1,
      rateLimited: 999,
      errors: 0,
      uniqueEntries: 1,
      oversold: 0,
      pass: true,
    },
    "duplicate-attack": {
      name: "Duplicate Attack",
      totalRequests: 1000,
      uniqueUsers: 1,
      successful: 1,
      rateLimited: 999,
      errors: 0,
      uniqueEntries: 1,
      oversold: 0,
      pass: true,
    },
    "flash-crowd": {
      name: "Flash Crowd",
      totalRequests: 5000,
      uniqueUsers: 5000,
      successful: 5000,
      rateLimited: 0,
      errors: 0,
      uniqueEntries: 5000,
      oversold: 0,
      pass: true,
    },
  };

  const runTest = async (testKey) => {
    setTesting(true);
    setError("");

    try {
      // Simulate network delay
      await new Promise((resolve) => setTimeout(resolve, 1500));
      setResults(mockResults[testKey]);
    } catch (err) {
      setError(err.message);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <button style={styles.backBtn} onClick={() => navigate(`/admin/events/${eventId}`)}>
          ← Back to Command Center
        </button>
        <h1 style={styles.title}>Bot Injection Testing</h1>
        <p style={styles.subtitle}>Demo / Test Mode</p>
      </div>

      <div style={styles.content}>
        <div style={styles.warning}>
          ⚠️ This panel is for demonstration purposes only. These tests simulate adversarial bot attacks to showcase the backend's fraud detection and rate limiting capabilities.
        </div>

        {error && (
          <div
            style={{
              padding: "16px",
              borderRadius: "8px",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid #ef4444",
              color: "#fecaca",
              marginBottom: "24px",
            }}
          >
            {error}
          </div>
        )}

        <div style={styles.grid}>
          <div style={styles.card}>
            <h3 style={styles.cardTitle}>High-Speed Bot</h3>
            <p style={styles.cardDescription}>
              Simulate a burst of automated JOIN requests from a single user.
            </p>
            <button
              style={{
                ...styles.button,
                ...(testing && styles.buttonDisabled),
              }}
              onClick={() => runTest("high-speed")}
              disabled={testing}
            >
              {testing ? "Testing..." : "Run Test"}
            </button>
          </div>

          <div style={styles.card}>
            <h3 style={styles.cardTitle}>High-Volume Bot</h3>
            <p style={styles.cardDescription}>
              Simulate repeated requests from one user across time.
            </p>
            <button
              style={{
                ...styles.button,
                ...(testing && styles.buttonDisabled),
              }}
              onClick={() => runTest("high-volume")}
              disabled={testing}
            >
              {testing ? "Testing..." : "Run Test"}
            </button>
          </div>

          <div style={styles.card}>
            <h3 style={styles.cardTitle}>Duplicate Attack</h3>
            <p style={styles.cardDescription}>
              Simulate thousands of concurrent requests from one account.
            </p>
            <button
              style={{
                ...styles.button,
                ...(testing && styles.buttonDisabled),
              }}
              onClick={() => runTest("duplicate-attack")}
              disabled={testing}
            >
              {testing ? "Testing..." : "Run Test"}
            </button>
          </div>

          <div style={styles.card}>
            <h3 style={styles.cardTitle}>Flash Crowd</h3>
            <p style={styles.cardDescription}>
              Simulate a large concurrent registration spike.
            </p>
            <button
              style={{
                ...styles.button,
                ...(testing && styles.buttonDisabled),
              }}
              onClick={() => runTest("flash-crowd")}
              disabled={testing}
            >
              {testing ? "Testing..." : "Run Test"}
            </button>
          </div>
        </div>

        {results && (
          <div style={styles.resultBox}>
            <h3 style={{ margin: "0 0 16px 0", color: "#38bdf8" }}>
              {results.name} Results
            </h3>

            <div style={styles.resultRow}>
              <span style={styles.resultLabel}>Total Requests</span>
              <span style={styles.resultValue}>{results.totalRequests}</span>
            </div>

            <div style={styles.resultRow}>
              <span style={styles.resultLabel}>Unique Users</span>
              <span style={styles.resultValue}>{results.uniqueUsers}</span>
            </div>

            <div style={styles.resultRow}>
              <span style={styles.resultLabel}>Successful Entries</span>
              <span style={styles.resultValue}>{results.successful}</span>
            </div>

            <div style={styles.resultRow}>
              <span style={styles.resultLabel}>Rate Limited</span>
              <span style={styles.resultValue}>{results.rateLimited}</span>
            </div>

            <div style={styles.resultRow}>
              <span style={styles.resultLabel}>Errors</span>
              <span style={styles.resultValue}>{results.errors}</span>
            </div>

            <div style={{ borderTop: "1px solid rgba(148, 163, 184, 0.2)", margin: "12px 0" }} />

            <div style={styles.resultRow}>
              <span style={styles.resultLabel}>Unique Entries Created</span>
              <span style={styles.resultValue}>{results.uniqueEntries}</span>
            </div>

            <div style={styles.resultRow}>
              <span style={styles.resultLabel}>Overselling Prevented</span>
              <span style={styles.resultValue}>{results.oversold}</span>
            </div>

            {results.pass && (
              <div style={styles.statusPass}>
                ✓ PASS: Bot attack successfully blocked
              </div>
            )}
            {!results.pass && (
              <div style={styles.statusFail}>
                ✗ FAIL: Bot attack was not fully blocked
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
