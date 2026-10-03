import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { fetchEvents, createEvent, commitAllocation, runAllocation } from "../lib/api";
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
    fontSize: "13px",
  },
  th: {
    padding: "16px",
    background: "rgba(3, 7, 18, 0.6)",
    borderBottom: "1px solid rgba(148, 163, 184, 0.35)",
    fontWeight: 600,
    color: "#cbd5e1",
    textAlign: "left",
  },
  td: {
    padding: "16px",
    borderBottom: "1px solid rgba(148, 163, 184, 0.2)",
    color: "#f8fafc",
  },
  tr: {
    background: "rgba(15, 23, 42, 0.4)",
    cursor: "pointer",
    transition: "all 0.2s ease",
  },
  button: {
    padding: "6px 12px",
    marginRight: "6px",
    border: "1px solid #38bdf8",
    borderRadius: "4px",
    background: "transparent",
    color: "#38bdf8",
    cursor: "pointer",
    fontSize: "12px",
    fontWeight: 600,
  },
  loading: {
    textAlign: "center",
    padding: "40px",
    color: "#cbd5e1",
  },
};

export default function AdminEventsPage() {
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadEvents = async () => {
      try {
        const data = await fetchEvents();
        setEvents(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error(err);
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
        <h1 style={styles.title}>Admin Dashboard</h1>
        <button style={styles.logoutBtn} onClick={handleLogout}>
          Logout
        </button>
      </div>

      <div style={styles.content}>
        <table style={styles.table}>
          <thead>
            <tr style={{ background: "rgba(3, 7, 18, 0.8)" }}>
              <th style={styles.th}>Event Name</th>
              <th style={styles.th}>Venue</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Capacity</th>
              <th style={styles.th}>Entries</th>
              <th style={styles.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr
                key={event.id}
                style={styles.tr}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "rgba(15, 23, 42, 0.8)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "rgba(15, 23, 42, 0.4)";
                }}
              >
                <td style={styles.td}>{event.name}</td>
                <td style={styles.td}>{event.venue || "—"}</td>
                <td style={styles.td}>
                  <StatusBadge status={event.status} />
                </td>
                <td style={styles.td}>{event.capacity}</td>
                <td style={styles.td}>{event.entryCount}</td>
                <td style={styles.td}>
                  <button
                    style={styles.button}
                    onClick={() => navigate(`/admin/events/${event.id}`)}
                  >
                    View
                  </button>
                  <button
                    style={styles.button}
                    onClick={() => navigate(`/admin/events/${event.id}/results`)}
                  >
                    Results
                  </button>
                  <button
                    style={styles.button}
                    onClick={() => navigate(`/admin/events/${event.id}/monitor`)}
                  >
                    Monitor
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {events.length === 0 && (
          <div style={styles.loading}>No events found</div>
        )}
      </div>
    </div>
  );
}
