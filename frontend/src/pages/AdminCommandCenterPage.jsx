import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchEvent, fetchEventAudit, commitAllocation, runAllocation } from "../lib/api";
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
  grid: {
    maxWidth: "1200px",
    margin: "0 auto",
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
    gap: "24px",
    marginBottom: "24px",
  },
  card: {
    padding: "24px",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "8px",
    background: "rgba(15, 23, 42, 0.6)",
  },
  cardTitle: {
    fontSize: "13px",
    fontWeight: 600,
    color: "#cbd5e1",
    textTransform: "uppercase",
    letterSpacing: "1px",
    margin: "0 0 8px 0",
  },
  cardValue: {
    fontSize: "24px",
    fontWeight: 700,
    color: "#38bdf8",
    margin: "0",
  },
  section: {
    maxWidth: "1200px",
    margin: "0 auto 24px",
    padding: "24px",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "8px",
    background: "rgba(15, 23, 42, 0.6)",
  },
  sectionTitle: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#38bdf8",
    margin: "0 0 16px 0",
  },
  actionButtons: {
    display: "flex",
    gap: "12px",
    flexWrap: "wrap",
  },
  button: {
    padding: "10px 20px",
    border: "1px solid #38bdf8",
    borderRadius: "6px",
    background: "transparent",
    color: "#38bdf8",
    cursor: "pointer",
    fontSize: "14px",
    fontWeight: 600,
    transition: "all 0.2s ease",
  },
  buttonPrimary: {
    background: "#38bdf8",
    color: "#082f49",
    border: 0,
  },
  buttonDisabled: {
    opacity: 0.5,
    cursor: "not-allowed",
  },
  batchTable: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "12px",
    marginTop: "12px",
  },
  batchTh: {
    padding: "8px",
    textAlign: "left",
    borderBottom: "1px solid rgba(148, 163, 184, 0.3)",
    fontWeight: 600,
    color: "#cbd5e1",
  },
  batchTd: {
    padding: "8px",
    borderBottom: "1px solid rgba(148, 163, 184, 0.2)",
    color: "#f8fafc",
  },
  modal: {
    position: "fixed",
    inset: 0,
    background: "rgba(0, 0, 0, 0.8)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
  },
  modalContent: {
    background: "rgba(3, 7, 18, 0.95)",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "12px",
    padding: "32px",
    maxWidth: "500px",
    width: "90%",
  },
  modalTitle: {
    fontSize: "20px",
    fontWeight: 700,
    margin: "0 0 16px 0",
  },
  modalText: {
    fontSize: "14px",
    color: "#cbd5e1",
    margin: "0 0 24px 0",
    lineHeight: "1.6",
  },
  modalButtons: {
    display: "flex",
    gap: "12px",
  },
  loading: {
    textAlign: "center",
    padding: "40px",
    color: "#cbd5e1",
  },
};

export default function AdminCommandCenterPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [event, setEvent] = useState(null);
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [committing, setCommitting] = useState(false);
  const [running, setRunning] = useState(false);
  const [confirmModal, setConfirmModal] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadData = async () => {
      try {
        const eventData = await fetchEvent(eventId);
        setEvent(eventData);

        try {
          const auditData = await fetchEventAudit(eventId);
          setAudit(auditData);
        } catch {
          // Allocation not yet run is OK
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [eventId]);

  const handleCommit = async () => {
    setConfirmModal(null);
    setCommitting(true);
    setError("");

    try {
      const result = await commitAllocation(eventId);
      setAudit(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setCommitting(false);
    }
  };

  const handleRun = async () => {
    setConfirmModal(null);
    setRunning(true);
    setError("");

    try {
      const result = await runAllocation(eventId);
      setAudit(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return <div style={styles.loading}>Loading...</div>;
  }

  const isCommitted = audit?.status === "COMMITTED";
  const isCompleted = audit?.status === "ALLOCATION_COMPLETE";

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <button style={styles.backBtn} onClick={() => navigate("/admin/events")}>
          ← Back to Events
        </button>
        <h1 style={styles.title}>FAIR DROP COMMAND CENTER</h1>
        {event && <p style={styles.subtitle}>{event.name}</p>}
      </div>

      {error && (
        <div
          style={{
            maxWidth: "1200px",
            margin: "0 auto 24px",
            padding: "16px",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid #ef4444",
            borderRadius: "8px",
            color: "#fecaca",
          }}
        >
          {error}
        </div>
      )}

      {event && (
        <>
          <div style={styles.grid}>
            <div style={styles.card}>
              <p style={styles.cardTitle}>Capacity</p>
              <p style={styles.cardValue}>{event.capacity}</p>
            </div>
            <div style={styles.card}>
              <p style={styles.cardTitle}>Entries</p>
              <p style={styles.cardValue}>{event.entryCount || 0}</p>
            </div>
            <div style={styles.card}>
              <p style={styles.cardTitle}>Remaining</p>
              <p style={styles.cardValue}>
                {Math.max(0, event.capacity - (event.entryCount || 0))}
              </p>
            </div>
            <div style={styles.card}>
              <p style={styles.cardTitle}>Status</p>
              <div style={{ marginTop: "8px" }}>
                <StatusBadge status={event.status} />
              </div>
            </div>
          </div>

          {!isCommitted && !isCompleted && (
            <div style={styles.section}>
              <h3 style={styles.sectionTitle}>Step 1: Commit Allocation</h3>
              <p style={{ fontSize: "13px", color: "#cbd5e1", margin: "0 0 16px 0" }}>
                Lock the seed and freeze the entry list. Registration will be closed.
              </p>
              <div style={styles.actionButtons}>
                <button
                  style={{ ...styles.button, ...styles.buttonPrimary }}
                  onClick={() =>
                    setConfirmModal({
                      title: "Commit Allocation?",
                      message: "This will lock the seed and close registration. Continue?",
                      action: "commit",
                    })
                  }
                  disabled={committing}
                >
                  {committing ? "Committing..." : "Commit"}
                </button>
              </div>
            </div>
          )}

          {(isCommitted || isCompleted) && audit && (
            <div style={styles.section}>
              <h3 style={styles.sectionTitle}>
                {isCommitted ? "Step 1: Committed ✓" : "Step 1 & 2: Complete ✓"}
              </h3>
              <table style={styles.batchTable}>
                <tbody>
                  <tr>
                    <td style={{ ...styles.batchTd, fontWeight: 600 }}>Seed Commitment</td>
                    <td style={styles.batchTd}>
                      <code style={{ fontSize: "11px", color: "#94a3b8" }}>
                        {audit.seed_commitment.substring(0, 32)}...
                      </code>
                    </td>
                  </tr>
                  <tr>
                    <td style={{ ...styles.batchTd, fontWeight: 600 }}>Entries Locked</td>
                    <td style={styles.batchTd}>{audit.eligible_entry_count}</td>
                  </tr>
                  {isCompleted && (
                    <>
                      <tr>
                        <td style={{ ...styles.batchTd, fontWeight: 600 }}>Winners</td>
                        <td style={styles.batchTd}>{audit.winner_count}</td>
                      </tr>
                      <tr>
                        <td style={{ ...styles.batchTd, fontWeight: 600 }}>Waitlisted</td>
                        <td style={styles.batchTd}>{audit.waitlist_count}</td>
                      </tr>
                    </>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {isCommitted && !isCompleted && (
            <div style={styles.section}>
              <h3 style={styles.sectionTitle}>Step 2: Run Allocation</h3>
              <p style={{ fontSize: "13px", color: "#cbd5e1", margin: "0 0 16px 0" }}>
                Execute the allocation draw using the committed seed.
              </p>
              <div style={styles.actionButtons}>
                <button
                  style={{ ...styles.button, ...styles.buttonPrimary }}
                  onClick={() =>
                    setConfirmModal({
                      title: "Run Allocation?",
                      message: "This will execute the fair draw and assign winners/waitlist.",
                      action: "run",
                    })
                  }
                  disabled={running}
                >
                  {running ? "Running..." : "Run Allocation"}
                </button>
              </div>
            </div>
          )}

          {isCompleted && audit && (
            <>
              <div style={styles.section}>
                <h3 style={styles.sectionTitle}>Batch Allocation</h3>
                <table style={styles.batchTable}>
                  <thead>
                    <tr style={{ borderBottom: "2px solid rgba(148, 163, 184, 0.3)" }}>
                      <th style={styles.batchTh}>Batch</th>
                      <th style={styles.batchTh}>Entries</th>
                      <th style={styles.batchTh}>Weight</th>
                      <th style={styles.batchTh}>Quota</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.batch_definitions?.map((batch, idx) => (
                      <tr key={idx}>
                        <td style={styles.batchTd}>{batch.batch_id}</td>
                        <td style={styles.batchTd}>{batch.entry_count}</td>
                        <td style={styles.batchTd}>{(batch.weight * 100).toFixed(0)}%</td>
                        <td style={styles.batchTd}>{batch.quota}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={styles.actionButtons} style={{ maxWidth: "1200px", margin: "0 auto" }}>
                <button
                  style={styles.button}
                  onClick={() => navigate(`/admin/events/${eventId}/results`)}
                >
                  View Results
                </button>
                <button
                  style={styles.button}
                  onClick={() => navigate(`/admin/events/${eventId}/audit`)}
                >
                  View Audit Proof
                </button>
                <button
                  style={styles.button}
                  onClick={() => navigate(`/admin/events/${eventId}/bots`)}
                >
                  Bot Testing
                </button>
              </div>
            </>
          )}
        </>
      )}

      {confirmModal && (
        <div style={styles.modal} onClick={() => setConfirmModal(null)}>
          <div style={styles.modalContent} onClick={(e) => e.stopPropagation()}>
            <h3 style={styles.modalTitle}>{confirmModal.title}</h3>
            <p style={styles.modalText}>{confirmModal.message}</p>
            <div style={styles.modalButtons}>
              <button
                style={{ ...styles.button, ...styles.buttonPrimary }}
                onClick={() =>
                  confirmModal.action === "commit" ? handleCommit() : handleRun()
                }
              >
                Continue
              </button>
              <button
                style={styles.button}
                onClick={() => setConfirmModal(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
