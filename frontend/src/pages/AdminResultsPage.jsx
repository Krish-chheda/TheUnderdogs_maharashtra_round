import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchEventAudit } from "../lib/api";
import StatusBadge from "../components/ui/StatusBadge";

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
    fontSize: "14px",
    color: "#cbd5e1",
    margin: "0 0 24px 0",
  },
  content: {
    maxWidth: "1200px",
    margin: "0 auto",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "8px",
    overflow: "hidden",
    fontSize: "12px",
  },
  th: {
    padding: "12px",
    background: "rgba(3, 7, 18, 0.6)",
    borderBottom: "1px solid rgba(148, 163, 184, 0.35)",
    fontWeight: 600,
    color: "#cbd5e1",
    textAlign: "left",
  },
  td: {
    padding: "12px",
    borderBottom: "1px solid rgba(148, 163, 184, 0.2)",
    color: "#f8fafc",
  },
  tr: {
    background: "rgba(15, 23, 42, 0.4)",
  },
  loading: {
    textAlign: "center",
    padding: "40px",
    color: "#cbd5e1",
  },
  error: {
    padding: "16px",
    borderRadius: "8px",
    background: "rgba(239, 68, 68, 0.1)",
    color: "#fecaca",
    border: "1px solid #ef4444",
    marginBottom: "24px",
  },
  statsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "12px",
    marginBottom: "24px",
  },
  statCard: {
    padding: "12px",
    borderRadius: "6px",
    background: "rgba(59, 130, 246, 0.1)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
  },
  statLabel: {
    fontSize: "11px",
    color: "#cbd5e1",
  },
  statValue: {
    fontSize: "18px",
    fontWeight: 700,
    color: "#38bdf8",
  },
};

export default function AdminResultsPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadData = async () => {
      try {
        const data = await fetchEventAudit(eventId);
        setAudit(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [eventId]);

  if (loading) {
    return <div style={styles.loading}>Loading results...</div>;
  }

  if (!audit) {
    return (
      <div style={styles.container}>
        <div style={styles.content}>
          <button style={styles.backBtn} onClick={() => navigate(`/admin/events/${eventId}`)}>
            ← Back
          </button>
          <div style={styles.error}>
            {error || "Allocation has not completed yet."}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <button style={styles.backBtn} onClick={() => navigate(`/admin/events/${eventId}`)}>
          ← Back
        </button>
        <h1 style={styles.title}>Allocation Results</h1>
        <p style={styles.subtitle}>
          {audit.winner_count} winners, {audit.waitlist_count} on waitlist
        </p>
      </div>

      <div style={styles.content}>
        {error && <div style={styles.error}>{error}</div>}

        <div style={styles.statsGrid}>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Capacity</div>
            <div style={styles.statValue}>{audit.capacity}</div>
          </div>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Eligible Entries</div>
            <div style={styles.statValue}>{audit.eligible_entry_count}</div>
          </div>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Winners</div>
            <div style={styles.statValue}>{audit.winner_count}</div>
          </div>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Waitlisted</div>
            <div style={styles.statValue}>{audit.waitlist_count}</div>
          </div>
        </div>

        {audit.batch_definitions && audit.batch_definitions.length > 0 && (
          <>
            <h3 style={{ fontSize: "16px", fontWeight: 600, color: "#38bdf8", margin: "24px 0 12px 0" }}>
              Batch Allocation
            </h3>
            <table style={styles.table}>
              <thead>
                <tr style={{ background: "rgba(3, 7, 18, 0.8)" }}>
                  <th style={styles.th}>Batch</th>
                  <th style={styles.th}>Entries</th>
                  <th style={styles.th}>Weight</th>
                  <th style={styles.th}>Quota</th>
                  <th style={styles.th}>Winners</th>
                </tr>
              </thead>
              <tbody>
                {audit.batch_definitions.map((batch, idx) => (
                  <tr key={idx} style={styles.tr}>
                    <td style={styles.td}>{batch.batch_id}</td>
                    <td style={styles.td}>{batch.entry_count}</td>
                    <td style={styles.td}>{(batch.weight * 100).toFixed(0)}%</td>
                    <td style={styles.td}>{batch.quota}</td>
                    <td style={styles.td}>
                      {audit.winners_by_batch?.[batch.batch_id] || batch.quota}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        <div style={{ marginTop: "24px", padding: "16px", borderRadius: "6px", background: "rgba(59, 130, 246, 0.1)", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
          <p style={{ fontSize: "12px", color: "#cbd5e1", margin: 0 }}>
            Detailed per-user results are available in the allocation database. This view shows aggregate statistics and batch-level fairness data.
          </p>
        </div>

        <div style={{ marginTop: "24px", display: "flex", gap: "12px" }}>
          <button
            style={{
              padding: "10px 20px",
              border: "1px solid #38bdf8",
              borderRadius: "6px",
              background: "transparent",
              color: "#38bdf8",
              cursor: "pointer",
              fontSize: "14px",
              fontWeight: 600,
            }}
            onClick={() => navigate(`/admin/events/${eventId}/audit`)}
          >
            View Audit Proof
          </button>
        </div>
      </div>
    </div>
  );
}
