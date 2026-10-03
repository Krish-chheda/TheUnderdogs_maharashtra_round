import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchEventStatus, claimEvent } from "../lib/api";
import CountdownTimer from "../components/ui/CountdownTimer";

const styles = {
  container: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "20px",
    color: "#f8fafc",
  },
  panel: {
    width: "min(500px, 100%)",
    padding: "40px",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "12px",
    background: "rgba(3, 7, 18, 0.8)",
  },
  title: {
    fontSize: "28px",
    fontWeight: 700,
    margin: "0 0 8px 0",
    textAlign: "center",
  },
  subtitle: {
    fontSize: "14px",
    color: "#cbd5e1",
    margin: "0 0 32px 0",
    textAlign: "center",
  },
  section: {
    padding: "24px",
    borderRadius: "8px",
    background: "rgba(59, 130, 246, 0.1)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    marginBottom: "24px",
  },
  label: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#cbd5e1",
    textTransform: "uppercase",
    letterSpacing: "1px",
    margin: "0 0 8px 0",
  },
  value: {
    fontSize: "16px",
    fontWeight: 600,
    color: "#f8fafc",
    margin: "8px 0",
  },
  countdown: {
    textAlign: "center",
    margin: "24px 0",
  },
  button: {
    width: "100%",
    padding: "14px",
    border: 0,
    borderRadius: "6px",
    background: "#38bdf8",
    color: "#082f49",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: "16px",
  },
  buttonDisabled: {
    background: "#64748b",
    cursor: "not-allowed",
  },
  secondaryButton: {
    marginTop: "12px",
    width: "100%",
    padding: "12px",
    border: "1px solid #64748b",
    borderRadius: "6px",
    background: "transparent",
    color: "#cbd5e1",
    cursor: "pointer",
    fontSize: "14px",
  },
  success: {
    padding: "16px",
    borderRadius: "8px",
    background: "rgba(52, 211, 153, 0.1)",
    color: "#86efac",
    border: "1px solid #34d399",
    textAlign: "center",
    marginBottom: "24px",
  },
  error: {
    padding: "16px",
    borderRadius: "8px",
    background: "rgba(239, 68, 68, 0.1)",
    color: "#fecaca",
    border: "1px solid #ef4444",
    marginBottom: "24px",
  },
};

export default function ClaimPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [claiming, setClaiming] = useState(false);
  const [claimed, setClaimed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadStatus = async () => {
      try {
        const data = await fetchEventStatus(eventId);
        setStatus(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadStatus();
  }, [eventId]);

  const handleClaim = async () => {
    setClaiming(true);
    setError("");

    try {
      const idempotencyKey = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
        /[xy]/g,
        function (c) {
          const r = (Math.random() * 16) | 0;
          const v = c === "x" ? r : (r & 0x3) | 0x8;
          return v.toString(16);
        }
      );

      await claimEvent(eventId, idempotencyKey);
      setClaimed(true);
      setTimeout(() => {
        navigate(`/events/${eventId}/status`);
      }, 2000);
    } catch (err) {
      if (err.status === 429) {
        setError(
          `Rate limited. Please wait ${err.retryAfter || 20} seconds before trying again.`
        );
      } else {
        setError(err.message);
      }
      setClaiming(false);
    }
  };

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.panel}>
          <p style={{ color: "#cbd5e1" }}>Loading...</p>
        </div>
      </div>
    );
  }

  if (claimed) {
    return (
      <div style={styles.container}>
        <div style={styles.panel}>
          <div style={styles.success}>
            <div style={{ fontSize: "32px", margin: "0 0 8px 0" }}>✓</div>
            <div style={{ fontSize: "18px", fontWeight: 600 }}>
              SEAT SECURED
            </div>
            <p style={{ margin: "8px 0 0 0", fontSize: "14px" }}>
              Your seat has been successfully claimed. Redirecting...
            </p>
          </div>
        </div>
      </div>
    );
  }

  const isExpired = status?.status === "EXPIRED" || (status?.claim_expires_at && new Date(status.claim_expires_at) < new Date());

  return (
    <div style={styles.container}>
      <div style={styles.panel}>
        <h2 style={styles.title}>SEAT ALLOCATED</h2>
        <p style={styles.subtitle}>Claim Your Ticket</p>

        {error && <div style={styles.error}>{error}</div>}

        {!isExpired && status?.claim_expires_at && (
          <div style={styles.countdown}>
            <div style={styles.label}>Claim Expires In</div>
            <CountdownTimer
              expiresAt={status.claim_expires_at}
              onExpire={() => setStatus({ ...status, status: "EXPIRED" })}
            />
          </div>
        )}

        {isExpired && (
          <div style={styles.error}>
            The claim window has expired. This seat is no longer available.
          </div>
        )}

        {!isExpired && (
          <>
            <div style={styles.section}>
              <div style={styles.label}>Status</div>
              <div style={styles.value} style={{ color: "#34d399" }}>
                WINNER
              </div>
              <p style={{ fontSize: "13px", color: "#cbd5e1", margin: "8px 0 0 0" }}>
                You are eligible to claim this seat. Complete payment to secure your seat.
              </p>
            </div>

            <button
              style={{
                ...styles.button,
                ...(claiming && styles.buttonDisabled),
              }}
              onClick={handleClaim}
              disabled={claiming}
            >
              {claiming ? "PROCESSING..." : "PAY & CONFIRM SEAT"}
            </button>

            <button
              style={styles.secondaryButton}
              onClick={() => navigate(`/events/${eventId}/status`)}
              disabled={claiming}
            >
              Back to Status
            </button>
          </>
        )}
      </div>
    </div>
  );
}
