import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fetchEvent, fetchEventStatus } from "../lib/api";
import StatusBadge from "../components/ui/StatusBadge";

const styles = {
  container: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    padding: "40px 20px",
    color: "#f8fafc",
  },
  content: {
    maxWidth: "800px",
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
    fontSize: "28px",
    fontWeight: 700,
    margin: "0 0 8px 0",
  },
  status: {
    margin: "12px 0 24px 0",
  },
  section: {
    margin: "24px 0",
  },
  sectionTitle: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#cbd5e1",
    textTransform: "uppercase",
    letterSpacing: "1px",
    margin: "0 0 8px 0",
  },
  sectionValue: {
    fontSize: "16px",
    color: "#f8fafc",
    margin: "4px 0",
  },
  button: {
    marginTop: "32px",
    width: "100%",
    padding: "13px",
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
    color: "#94a3b8",
  },
  capacitySection: {
    padding: "16px",
    borderRadius: "8px",
    background: "rgba(59, 130, 246, 0.1)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    margin: "24px 0",
  },
  progressBar: {
    height: "12px",
    borderRadius: "6px",
    background: "rgba(148, 163, 184, 0.2)",
    marginTop: "12px",
    overflow: "hidden",
  },
  progressFill: {
    height: "100%",
    background: "linear-gradient(90deg, #3b82f6, #8b5cf6)",
  },
  error: {
    padding: "16px",
    borderRadius: "8px",
    background: "rgba(239, 68, 68, 0.1)",
    color: "#fecaca",
    border: "1px solid #ef4444",
    margin: "16px 0",
  },
  loading: {
    textAlign: "center",
    padding: "40px",
    color: "#cbd5e1",
  },
};

export default function EventDetailsPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [event, setEvent] = useState(null);
  const [userStatus, setUserStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadData = async () => {
      try {
        const eventData = await fetchEvent(eventId);
        setEvent(eventData);

        const token = localStorage.getItem("access_token");
        if (token) {
          try {
            const statusData = await fetchEventStatus(eventId);
            setUserStatus(statusData);
          } catch {
            // Not entered yet is OK
          }
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [eventId]);

  if (loading) return <div style={styles.loading}>Loading event...</div>;
  if (!event) return <div style={styles.loading}>Event not found</div>;

  const capacity = event.capacity || 0;
  const entries = event.entryCount || 0;
  const remaining = Math.max(0, capacity - entries);
  const fillPercent = capacity > 0 ? (entries / capacity) * 100 : 0;
  const isAlreadyEntered = userStatus && userStatus.status === "ELIGIBLE";

  const handleRegister = () => {
    if (event.requiresPhoneVerification) {
      navigate(`/events/${eventId}/verify`);
    } else {
      navigate(`/events/${eventId}/entry`);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.content}>
        <button style={styles.backBtn} onClick={() => navigate("/events")}>
          ← Back to Events
        </button>

        {error && <div style={styles.error}>{error}</div>}

        <h1 style={styles.title}>{event.name}</h1>
        <div style={styles.status}>
          <StatusBadge status={event.status} />
        </div>

        {event.description && (
          <div style={styles.section}>
            <p style={styles.sectionValue}>{event.description}</p>
          </div>
        )}

        <div style={styles.section}>
          <div style={styles.sectionTitle}>Venue</div>
          <div style={styles.sectionValue}>{event.venue || "TBA"}</div>
        </div>

        {event.date && (
          <div style={styles.section}>
            <div style={styles.sectionTitle}>Event Date</div>
            <div style={styles.sectionValue}>
              {new Date(event.date).toLocaleString()}
            </div>
          </div>
        )}

        {event.registrationDeadline && (
          <div style={styles.section}>
            <div style={styles.sectionTitle}>Registration Deadline</div>
            <div style={styles.sectionValue}>
              {new Date(event.registrationDeadline).toLocaleString()}
            </div>
          </div>
        )}

        <div style={styles.capacitySection}>
          <div style={styles.sectionTitle}>Entry Capacity</div>
          <div style={styles.sectionValue} style={{ fontSize: "18px", fontWeight: 600 }}>
            {entries} / {capacity} ENTRIES
          </div>
          <div style={styles.sectionValue} style={{ fontSize: "14px", color: "#34d399" }}>
            {remaining} SPOTS REMAINING
          </div>
          <div style={styles.progressBar}>
            <div
              style={{
                ...styles.progressFill,
                width: `${fillPercent}%`,
              }}
            />
          </div>
        </div>

        {!event.isOpen && (
          <button
            style={{ ...styles.button, ...styles.buttonDisabled }}
            disabled
          >
            Registration Closed
          </button>
        )}

        {event.isOpen && isAlreadyEntered && (
          <>
            <div style={styles.error}>
              You have already entered this event. View your status below.
            </div>
            <button
              style={styles.button}
              onClick={() => navigate(`/events/${eventId}/status`)}
            >
              View Your Status
            </button>
          </>
        )}

        {event.isOpen && !isAlreadyEntered && (
          <button style={styles.button} onClick={handleRegister}>
            Register Now
          </button>
        )}
      </div>
    </div>
  );
}
