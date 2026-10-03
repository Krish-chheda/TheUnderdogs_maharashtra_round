import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchEventStatus, fetchEvent } from "../lib/api";
import StatusBadge from "../components/ui/StatusBadge";
import CountdownTimer from "../components/ui/CountdownTimer";

const styles = {
  container: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    padding: "40px 20px",
    color: "#f8fafc",
  },
  content: {
    maxWidth: "600px",
    margin: "0 auto",
    padding: "32px",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "12px",
    background: "rgba(3, 7, 18, 0.8)",
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
    fontSize: "24px",
    fontWeight: 700,
    margin: "0 0 8px 0",
  },
  subtitle: {
    fontSize: "14px",
    color: "#cbd5e1",
    margin: "0 0 32px 0",
  },
  statusBox: {
    padding: "24px",
    borderRadius: "8px",
    background: "rgba(59, 130, 246, 0.1)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    marginBottom: "24px",
  },
  statusTitle: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#cbd5e1",
    textTransform: "uppercase",
    letterSpacing: "1px",
    margin: "0 0 8px 0",
  },
  statusValue: {
    fontSize: "28px",
    fontWeight: 700,
    color: "#38bdf8",
    margin: "12px 0",
  },
  info: {
    fontSize: "13px",
    color: "#cbd5e1",
    margin: "8px 0",
  },
  button: {
    width: "100%",
    padding: "13px",
    border: 0,
    borderRadius: "6px",
    background: "#38bdf8",
    color: "#082f49",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: "16px",
    marginTop: "12px",
  },
  buttonDisabled: {
    background: "#64748b",
    cursor: "not-allowed",
  },
  loading: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    color: "#cbd5e1",
    margin: "12px 0",
  },
  spinner: {
    width: "16px",
    height: "16px",
    border: "2px solid #38bdf8",
    borderTop: "2px solid transparent",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  auditBtn: {
    marginTop: "16px",
    padding: "10px",
    border: "1px solid #64748b",
    borderRadius: "6px",
    background: "transparent",
    color: "#cbd5e1",
    cursor: "pointer",
    width: "100%",
    fontSize: "14px",
  },
};

export default function StatusPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pollCount, setPollCount] = useState(0);

  useEffect(() => {
    const loadData = async () => {
      try {
        const statusData = await fetchEventStatus(eventId);
        setStatus(statusData);

        const eventData = await fetchEvent(eventId);
        setEvent(eventData);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    loadData();
    const interval = setInterval(() => {
      setPollCount((c) => c + 1);
      loadData();
    }, 5000);

    return () => clearInterval(interval);
  }, [eventId]);

  if (loading && !status) {
    return (
      <div style={styles.container}>
        <div style={styles.content}>
          <div style={styles.loading}>
            <div style={styles.spinner} />
            Loading your status...
          </div>
        </div>
      </div>
    );
  }

  if (!status) {
    return (
      <div style={styles.container}>
        <div style={styles.content}>
          <button style={styles.backBtn} onClick={() => navigate("/events")}>
            ← Back to Events
          </button>
          <p style={{ color: "#fecaca" }}>
            {error || "Entry not found. Please register for this event first."}
          </p>
          <button
            style={styles.button}
            onClick={() => navigate(`/events/${eventId}`)}
          >
            Go to Event
          </button>
        </div>
      </div>
    );
  }

  const isWinner = status.status === "WINNER";
  const isWaitlisted = status.status === "WAITLISTED";
  const isReserved = status.status === "RESERVED";
  const isExpired = status.status === "EXPIRED";
  const isEligible = status.status === "ELIGIBLE";

  return (
    <div style={styles.container}>
      <div style={styles.content}>
        <button style={styles.backBtn} onClick={() => navigate("/events")}>
          ← Back to Events
        </button>

        <h2 style={styles.title}>Your Status</h2>
        {event && (
          <p style={styles.subtitle}>{event.name}</p>
        )}

        {isEligible && (
          <div style={styles.statusBox}>
            <div style={styles.statusTitle}>Status</div>
            <div style={styles.statusValue}>ENTRY RECORDED ✓</div>
            <p style={styles.info}>
              Your entry has been recorded. Allocation will happen after registration closes.
            </p>
            <div style={styles.loading}>
              <div style={styles.spinner} />
              Polling for allocation results...
            </div>
            <p style={styles.info} style={{ fontSize: "12px", marginTop: "16px" }}>
              Poll count: {pollCount}
            </p>
          </div>
        )}

        {isWinner && (
          <div style={styles.statusBox}>
            <div style={styles.statusTitle}>Status</div>
            <div style={styles.statusValue} style={{ color: "#34d399" }}>
              SEAT ALLOCATED ✓
            </div>
            <p style={styles.info}>Your entry has been selected!</p>
            <div style={{ marginTop: "16px" }}>
              <div style={styles.statusTitle}>Claim Expires In</div>
              <CountdownTimer
                expiresAt={status.claim_expires_at}
                onExpire={() => {
                  setStatus({ ...status, status: "EXPIRED" });
                }}
              />
            </div>
            <button
              style={styles.button}
              onClick={() => navigate(`/events/${eventId}/claim`)}
            >
              CLAIM YOUR SEAT
            </button>
          </div>
        )}

        {isReserved && (
          <div style={styles.statusBox}>
            <div style={styles.statusTitle}>Status</div>
            <div style={styles.statusValue} style={{ color: "#34d399" }}>
              SEAT SECURED ✓
            </div>
            <p style={styles.info}>Your seat has been successfully claimed.</p>
            {status.confirmation_id && (
              <p style={styles.info}>
                Confirmation ID: {status.confirmation_id}
              </p>
            )}
          </div>
        )}

        {isWaitlisted && (
          <div style={styles.statusBox}>
            <div style={styles.statusTitle}>Status</div>
            <div style={styles.statusValue} style={{ color: "#f59e0b" }}>
              YOU'RE ON THE WAITLIST
            </div>
            <p style={styles.info}>
              Your entry was not selected in the current allocation. If an allocated seat is released, eligible entries may be considered.
            </p>
            {status.rank && (
              <p style={styles.info}>
                Waitlist Position: {status.rank}
              </p>
            )}
          </div>
        )}

        {isExpired && (
          <div style={styles.statusBox}>
            <div style={styles.statusTitle}>Status</div>
            <div style={styles.statusValue} style={{ color: "#ef4444" }}>
              CLAIM WINDOW EXPIRED
            </div>
            <p style={styles.info}>
              The claim window has expired and the seat may be released to another eligible entry.
            </p>
          </div>
        )}

        {isWinner && (
          <button
            style={styles.auditBtn}
            onClick={() => navigate(`/events/${eventId}/audit`)}
          >
            View Allocation Proof
          </button>
        )}
      </div>
    </div>
  );
}
