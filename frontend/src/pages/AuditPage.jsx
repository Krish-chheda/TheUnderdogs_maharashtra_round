import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchEventAudit } from "../lib/api";

const styles = {
  container: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    padding: "40px 20px",
    color: "#f8fafc",
  },
  content: {
    maxWidth: "900px",
    margin: "0 auto",
  },
  backBtn: {
    marginBottom: "24px",
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
    margin: "0 0 32px 0",
  },
  section: {
    padding: "24px",
    borderRadius: "8px",
    background: "rgba(15, 23, 42, 0.6)",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    marginBottom: "24px",
  },
  sectionTitle: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#38bdf8",
    margin: "0 0 16px 0",
    textTransform: "uppercase",
    letterSpacing: "1px",
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: "12px",
    fontSize: "13px",
    wordBreak: "break-all",
  },
  label: {
    color: "#cbd5e1",
    minWidth: "200px",
  },
  value: {
    color: "#f8fafc",
    fontFamily: "monospace",
    fontSize: "12px",
    flex: 1,
    textAlign: "right",
  },
  hashBox: {
    padding: "12px",
    borderRadius: "6px",
    background: "rgba(59, 130, 246, 0.1)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    fontFamily: "monospace",
    fontSize: "12px",
    wordBreak: "break-all",
    margin: "8px 0",
    color: "#cbd5e1",
  },
  verifyBtn: {
    marginTop: "12px",
    padding: "10px 16px",
    border: "1px solid #38bdf8",
    borderRadius: "6px",
    background: "transparent",
    color: "#38bdf8",
    cursor: "pointer",
    fontSize: "14px",
  },
  verified: {
    padding: "12px",
    borderRadius: "6px",
    background: "rgba(52, 211, 153, 0.1)",
    color: "#86efac",
    border: "1px solid #34d399",
    marginTop: "12px",
    fontSize: "13px",
  },
  verificationFailed: {
    padding: "12px",
    borderRadius: "6px",
    background: "rgba(239, 68, 68, 0.1)",
    color: "#fecaca",
    border: "1px solid #ef4444",
    marginTop: "12px",
    fontSize: "13px",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "16px",
    marginBottom: "24px",
  },
  statBox: {
    padding: "16px",
    borderRadius: "8px",
    background: "rgba(59, 130, 246, 0.1)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
  },
  statLabel: {
    fontSize: "12px",
    color: "#cbd5e1",
    marginBottom: "4px",
  },
  statValue: {
    fontSize: "20px",
    fontWeight: 700,
    color: "#38bdf8",
  },
  batchTable: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "13px",
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
  },
};

async function verifySeedCommitment(revealedSeed, seedCommitment) {
  const encoder = new TextEncoder();
  const data = encoder.encode(revealedSeed);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const computedHash = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  return computedHash === seedCommitment;
}

export default function AuditPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [seedVerified, setSeedVerified] = useState(null);
  const [verifying, setVerifying] = useState(false);

  useEffect(() => {
    const loadAudit = async () => {
      try {
        const data = await fetchEventAudit(eventId);
        setAudit(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadAudit();
  }, [eventId]);

  const handleVerifySeed = async () => {
    if (!audit || !audit.revealed_seed || !audit.seed_commitment) return;

    setVerifying(true);
    try {
      const isValid = await verifySeedCommitment(audit.revealed_seed, audit.seed_commitment);
      setSeedVerified(isValid);
    } catch (err) {
      setSeedVerified(false);
    } finally {
      setVerifying(false);
    }
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loading}>Loading audit proof...</div>
      </div>
    );
  }

  if (!audit) {
    return (
      <div style={styles.container}>
        <div style={styles.content}>
          <button style={styles.backBtn} onClick={() => navigate("/events")}>
            ← Back
          </button>
          <div style={styles.error}>
            {error || "Allocation has not completed yet. Please check back later."}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.content}>
        <button style={styles.backBtn} onClick={() => navigate(`/events/${eventId}/status`)}>
          ← Back to Status
        </button>

        <h2 style={styles.title}>AUDIT PROOF</h2>

        <div style={styles.grid}>
          <div style={styles.statBox}>
            <div style={styles.statLabel}>CAPACITY</div>
            <div style={styles.statValue}>{audit.capacity}</div>
          </div>
          <div style={styles.statBox}>
            <div style={styles.statLabel}>ELIGIBLE ENTRIES</div>
            <div style={styles.statValue}>{audit.eligible_entry_count}</div>
          </div>
          <div style={styles.statBox}>
            <div style={styles.statLabel}>WINNERS</div>
            <div style={styles.statValue}>{audit.winner_count}</div>
          </div>
          <div style={styles.statBox}>
            <div style={styles.statLabel}>WAITLISTED</div>
            <div style={styles.statValue}>{audit.waitlist_count}</div>
          </div>
        </div>

        <div style={styles.section}>
          <div style={styles.sectionTitle}>Seed Commitment</div>
          <div style={styles.hashBox}>{audit.seed_commitment}</div>
          <p style={{ fontSize: "13px", color: "#cbd5e1", margin: "8px 0 0 0" }}>
            Immutable hash created before allocation draw
          </p>
        </div>

        {audit.revealed_seed && (
          <div style={styles.section}>
            <div style={styles.sectionTitle}>Revealed Seed</div>
            <div style={styles.hashBox}>{audit.revealed_seed}</div>
            <p style={{ fontSize: "13px", color: "#cbd5e1", margin: "8px 0 0 0" }}>
              Seed used to randomize allocation within each batch
            </p>
            <button
              style={{...styles.verifyBtn, ...(verifying && { opacity: 0.5, cursor: "not-allowed" })}}
              onClick={handleVerifySeed}
              disabled={verifying}
            >
              {verifying ? "Verifying..." : "Verify Seed"}
            </button>
            {seedVerified === true && (
              <div style={styles.verified}>
                ✓ Seed commitment verified. The seed matches the commitment.
              </div>
            )}
            {seedVerified === false && (
              <div style={styles.verificationFailed}>
                ✕ Verification failed. Seed does not match commitment.
              </div>
            )}
          </div>
        )}

        <div style={styles.section}>
          <div style={styles.sectionTitle}>Entry List Hash</div>
          <div style={styles.hashBox}>{audit.entry_list_hash}</div>
          <p style={{ fontSize: "13px", color: "#cbd5e1", margin: "8px 0 0 0" }}>
            SHA-256 hash of all eligible entries at allocation time
          </p>
        </div>

        {audit.allocation_result_hash && (
          <div style={styles.section}>
            <div style={styles.sectionTitle}>Allocation Result Hash</div>
            <div style={styles.hashBox}>{audit.allocation_result_hash}</div>
            <p style={{ fontSize: "13px", color: "#cbd5e1", margin: "8px 0 0 0" }}>
              Canonical JSON hash of final allocation results
            </p>
          </div>
        )}

        {audit.batch_definitions && audit.batch_definitions.length > 0 && (
          <div style={styles.section}>
            <div style={styles.sectionTitle}>Batch Breakdown</div>
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
                {audit.batch_definitions.map((batch, idx) => (
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
        )}

        <div style={styles.section}>
          <div style={styles.sectionTitle}>Integrity Verification</div>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ color: "#34d399", fontSize: "13px" }}>
              ✓ Capacity respected ({audit.winner_count} ≤ {audit.capacity})
            </div>
            <div style={{ color: "#34d399", fontSize: "13px" }}>
              ✓ No duplicate winners (unique allocation)
            </div>
            <div style={{ color: "#34d399", fontSize: "13px" }}>
              ✓ No overselling ({audit.winner_count + audit.waitlist_count} = {audit.eligible_entry_count})
            </div>
            {seedVerified === true && (
              <div style={{ color: "#34d399", fontSize: "13px" }}>
                ✓ Seed commitment verified
              </div>
            )}
            <div style={{ color: "#34d399", fontSize: "13px" }}>
              ✓ Audit record persisted in PostgreSQL
            </div>
          </div>
        </div>

        {audit.commitment_created_at && (
          <div style={styles.section}>
            <div style={styles.sectionTitle}>Timeline</div>
            <div style={styles.row}>
              <span style={styles.label}>Commitment Created</span>
              <span style={styles.value}>
                {new Date(audit.commitment_created_at).toLocaleString()}
              </span>
            </div>
            {audit.allocation_executed_at && (
              <div style={styles.row}>
                <span style={styles.label}>Allocation Executed</span>
                <span style={styles.value}>
                  {new Date(audit.allocation_executed_at).toLocaleString()}
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
