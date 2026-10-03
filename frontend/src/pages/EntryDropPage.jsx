import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchEvent, enterEvent } from "../lib/api";

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
    fontSize: "24px",
    fontWeight: 700,
    margin: "0 0 32px 0",
    textAlign: "center",
  },
  confirmSection: {
    padding: "24px",
    borderRadius: "8px",
    background: "rgba(59, 130, 246, 0.1)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    marginBottom: "24px",
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    margin: "12px 0",
    fontSize: "14px",
  },
  label: {
    color: "#cbd5e1",
  },
  value: {
    fontWeight: 600,
    color: "#f8fafc",
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

export default function EntryDropPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [event, setEvent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadEvent = async () => {
      try {
        const data = await fetchEvent(eventId);
        setEvent(data);
      } catch (err) {
        setError(err.message);
      }
    };
    loadEvent();
  }, [eventId]);

  const handleEnter = async () => {
    setLoading(true);
    setError("");

    try {
      await enterEvent(eventId);
      setSubmitted(true);
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
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div style={styles.container}>
        <div style={styles.panel}>
          <div style={styles.success}>
            <div style={{ fontSize: "32px", margin: "0 0 8px 0" }}>✓</div>
            <div style={{ fontSize: "18px", fontWeight: 600 }}>
              ENTRY RECORDED
            </div>
            <p style={{ margin: "8px 0 0 0", fontSize: "14px" }}>
              Your entry has been recorded. Redirecting to your status...
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.panel}>
        <h2 style={styles.title}>Confirm Your Entry</h2>

        {error && <div style={styles.error}>{error}</div>}

        {event && (
          <>
            <div style={styles.confirmSection}>
              <div style={styles.row}>
                <span style={styles.label}>Event</span>
                <span style={styles.value}>{event.name}</span>
              </div>
              <div style={styles.row}>
                <span style={styles.label}>Venue</span>
                <span style={styles.value}>{event.venue || "TBA"}</span>
              </div>
              {event.date && (
                <div style={styles.row}>
                  <span style={styles.label}>Date</span>
                  <span style={styles.value}>
                    {new Date(event.date).toLocaleDateString()}
                  </span>
                </div>
              )}
              <div style={styles.row}>
                <span style={styles.label}>Capacity</span>
                <span style={styles.value}>
                  {event.entryCount} / {event.capacity}
                </span>
              </div>
            </div>

            <button
              style={{
                ...styles.button,
                ...(loading && styles.buttonDisabled),
              }}
              onClick={handleEnter}
              disabled={loading}
            >
              {loading ? "ENTERING DROP..." : "ENTER THE DROP"}
            </button>

            <button
              style={styles.secondaryButton}
              onClick={() => navigate(`/events/${eventId}`)}
              disabled={loading}
            >
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}
