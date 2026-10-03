import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchEvents } from "../lib/api";
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
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  title: {
    fontSize: "32px",
    fontWeight: 700,
    margin: 0,
  },
  logoutBtn: {
    padding: "10px 20px",
    border: "1px solid #64748b",
    borderRadius: "6px",
    background: "transparent",
    color: "#cbd5e1",
    cursor: "pointer",
    fontSize: "14px",
  },
  grid: {
    maxWidth: "1200px",
    margin: "0 auto",
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
    gap: "24px",
  },
  card: {
    padding: "24px",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "12px",
    background: "rgba(15, 23, 42, 0.6)",
    cursor: "pointer",
    transition: "all 0.3s ease",
  },
  cardName: {
    fontSize: "18px",
    fontWeight: 600,
    margin: "0 0 12px 0",
  },
  cardMeta: {
    fontSize: "13px",
    color: "#cbd5e1",
    margin: "8px 0",
  },
  capacityBar: {
    height: "8px",
    borderRadius: "4px",
    background: "rgba(148, 163, 184, 0.2)",
    marginTop: "12px",
    overflow: "hidden",
  },
  capacityFill: {
    height: "100%",
    background: "linear-gradient(90deg, #3b82f6, #8b5cf6)",
    transition: "width 0.3s ease",
  },
  button: {
    marginTop: "16px",
    width: "100%",
    padding: "10px",
    border: 0,
    borderRadius: "6px",
    background: "#38bdf8",
    color: "#082f49",
    fontWeight: 600,
    cursor: "pointer",
  },
  loading: {
    textAlign: "center",
    padding: "40px",
    fontSize: "16px",
    color: "#cbd5e1",
  },
  error: {
    padding: "20px",
    borderRadius: "8px",
    background: "rgba(239, 68, 68, 0.1)",
    color: "#fecaca",
    border: "1px solid #ef4444",
  },
};

export default function EventsListPage() {
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const loadEvents = async () => {
      try {
        const data = await fetchEvents();
        setEvents(Array.isArray(data) ? data : []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadEvents();
  }, []);

  const handleLogout = () => {
    localStorage.clear();
    navigate("/");
  };

  if (loading) return <div style={styles.loading}>Loading events...</div>;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>Fair Drop Events</h1>
        <button style={styles.logoutBtn} onClick={handleLogout}>
          Logout
        </button>
      </div>

      {error && <div style={styles.error}>{error}</div>}

      <div style={styles.grid}>
        {events.map((event) => {
          const capacity = event.capacity || 0;
          const entries = event.entryCount || 0;
          const remaining = Math.max(0, capacity - entries);
          const fillPercent = capacity > 0 ? (entries / capacity) * 100 : 0;

          return (
            <div
              key={event.id}
              style={styles.card}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "rgba(148, 163, 184, 0.6)";
                e.currentTarget.style.background = "rgba(15, 23, 42, 0.9)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "rgba(148, 163, 184, 0.35)";
                e.currentTarget.style.background = "rgba(15, 23, 42, 0.6)";
              }}
            >
              <h3 style={styles.cardName}>{event.name}</h3>
              <div style={styles.cardMeta}>📍 {event.venue || "TBA"}</div>
              {event.date && (
                <div style={styles.cardMeta}>
                  📅 {new Date(event.date).toLocaleDateString()}
                </div>
              )}
              <div style={styles.cardMeta}>
                {entries} / {capacity} entries
              </div>
              <div style={styles.cardMeta} style={{ color: "#34d399" }}>
                {remaining} spots remaining
              </div>

              <div style={styles.capacityBar}>
                <div
                  style={{
                    ...styles.capacityFill,
                    width: `${fillPercent}%`,
                  }}
                />
              </div>

              <StatusBadge status={event.status} />

              <button
                style={styles.button}
                onClick={() => navigate(`/events/${event.id}`)}
              >
                {event.isOpen ? "Register Now" : "View Details"}
              </button>
            </div>
          );
        })}
      </div>

      {events.length === 0 && !loading && (
        <div style={styles.loading}>No events available</div>
      )}
    </div>
  );
}
