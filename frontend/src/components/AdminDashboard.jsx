import { useEffect, useMemo, useState } from "react";
import {
  initialAdminMetrics,
  initialIntegrity,
  lifecycle,
  trafficSeries,
} from "../data/adminEvents";
import { createEvent as createEventRequest, fetchEvents } from "../lib/api";
import "../admin.css";

const statusLabel = (status) => status.replaceAll("_", " ");
const formatNumber = (value) => new Intl.NumberFormat("en-IN").format(value);
const formatDate = (value) =>
  value
    ? new Intl.DateTimeFormat("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "No deadline set";

const toAdminEvent = (event) => ({
  id: event.id || event.event_id,
  name: event.name,
  capacity: event.capacity,
  totalEntries: event.entryCount ?? event.totalEntries ?? 0,
  status:
    event.isOpen === false || event.status === "Closed"
      ? lifecycle.REGISTRATION_CLOSED
      : lifecycle.REGISTRATION_OPEN,
  registrationDeadline: event.registrationDeadline || "",
});

const actionFor = (status) =>
  ({
    [lifecycle.DRAFT]: {
      label: "Open registration",
      next: lifecycle.REGISTRATION_OPEN,
    },
    [lifecycle.REGISTRATION_OPEN]: {
      label: "Close registration",
      next: lifecycle.REGISTRATION_CLOSED,
    },
    [lifecycle.REGISTRATION_CLOSED]: {
      label: "Run allocation",
      next: lifecycle.ALLOCATION_RUNNING,
    },
  })[status];

function Metric({ label, value, detail, accent = "cyan" }) {
  return (
    <div className={`admin-metric metric-${accent}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function TrafficChart() {
  const width = 680;
  const height = 190;
  const max = 65;
  const point = (value, index) =>
    `${(index / (trafficSeries.length - 1)) * width},${height - (value / max) * 145 - 16}`;
  const line = (key) =>
    trafficSeries.map((item, index) => point(item[key], index)).join(" ");

  return (
    <div className="traffic-chart">
      <div className="chart-legend">
        <span>
          <i className="legend-incoming" />
          Incoming
        </span>
        <span>
          <i className="legend-limited" />
          Rate limited
        </span>
        <span>
          <i className="legend-blocked" />
          Blocked
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Request traffic over time"
      >
        <line x1="0" y1="174" x2={width} y2="174" />
        <line x1="0" y1="101" x2={width} y2="101" />
        <line x1="0" y1="28" x2={width} y2="28" />
        <polyline className="traffic-line incoming" points={line("incoming")} />
        <polyline className="traffic-line limited" points={line("limited")} />
        <polyline className="traffic-line blocked" points={line("blocked")} />
        {trafficSeries.map((item, index) => (
          <text
            key={item.time}
            x={(index / (trafficSeries.length - 1)) * width}
            y="188"
            textAnchor={
              index === 0
                ? "start"
                : index === trafficSeries.length - 1
                  ? "end"
                  : "middle"
            }
          >
            {item.time}
          </text>
        ))}
      </svg>
    </div>
  );
}

function IntegrityPanel({ integrity }) {
  const checks = [
    ["Winners generated", integrity.winnersGenerated, "neutral"],
    [
      "Duplicate winners",
      integrity.duplicateWinners,
      integrity.duplicateWinners === 0 ? "healthy" : "warning",
    ],
    [
      "Oversells",
      integrity.oversells,
      integrity.oversells === 0 ? "healthy" : "warning",
    ],
    ["Successful claims", integrity.successfulClaims, "healthy"],
    [
      "Failed claims",
      integrity.failedClaims,
      integrity.failedClaims ? "warning" : "healthy",
    ],
  ];
  return (
    <div className="integrity-list">
      {checks.map(([label, value, tone]) => (
        <div className="integrity-row" key={label}>
          <span>
            <i className={`integrity-dot ${tone}`} />
            {label}
          </span>
          <strong>{formatNumber(value)}</strong>
        </div>
      ))}
    </div>
  );
}

export default function AdminDashboard({ onLogout }) {
  const [events, setEvents] = useState([]);
  const [metrics] = useState(initialAdminMetrics);
  const [integrity, setIntegrity] = useState(initialIntegrity);
  const [eventName, setEventName] = useState("");
  const [capacity, setCapacity] = useState(500);
  const [creating, setCreating] = useState(false);
  const [processingId, setProcessingId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  const seatsRemaining = useMemo(
    () =>
      events.reduce(
        (total, event) =>
          total + Math.max(event.capacity - event.totalEntries, 0),
        0,
      ),
    [events],
  );

  useEffect(() => {
    let active = true;
    fetchEvents()
      .then((items) => {
        if (active) setEvents(items.map(toAdminEvent));
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const createEvent = async (event) => {
    event.preventDefault();
    const cleanName = eventName.trim();
    if (!cleanName || Number(capacity) < 1) {
      setError("Enter an event name and a capacity greater than zero.");
      return;
    }
    setCreating(true);
    setError("");
    setNotice("");
    try {
      const created = await createEventRequest({
        name: cleanName,
        capacity: Number(capacity),
      });
      setEvents((current) => [
        ...current,
        toAdminEvent({
          ...created,
          capacity: Number(capacity),
          entryCount: 0,
          isOpen: true,
        }),
      ]);
      setEventName("");
      setCapacity(500);
      setNotice("Event created and stored in the database.");
    } catch (requestError) {
      setError(requestError.message);
    }
    setCreating(false);
  };

  const transition = async (eventId) => {
    const current = events.find((item) => item.id === eventId);
    const action = current && actionFor(current.status);
    if (!current || !action) return;
    setProcessingId(eventId);
    setError("");
    setNotice("");
    if (action.next === lifecycle.ALLOCATION_RUNNING) {
      setEvents((items) =>
        items.map((item) =>
          item.id === eventId
            ? { ...item, status: lifecycle.ALLOCATION_RUNNING }
            : item,
        ),
      );
    }
    await new Promise((resolve) =>
      setTimeout(
        resolve,
        action.next === lifecycle.ALLOCATION_RUNNING ? 800 : 450,
      ),
    );
    const finalStatus =
      action.next === lifecycle.ALLOCATION_RUNNING
        ? lifecycle.ALLOCATION_COMPLETED
        : action.next;
    setEvents((items) =>
      items.map((item) =>
        item.id === eventId ? { ...item, status: finalStatus } : item,
      ),
    );
    if (finalStatus === lifecycle.ALLOCATION_COMPLETED) {
      setIntegrity((value) => ({
        ...value,
        winnersGenerated: Math.min(current.capacity, current.totalEntries),
      }));
    }
    setNotice(`${current.name} moved to ${statusLabel(finalStatus)}.`);
    setProcessingId("");
  };

  return (
    <div className="dashboard-shell admin-shell">
      <header className="dashboard-header admin-header">
        <button
          type="button"
          className="brand-mark"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        >
          <span className="brand-symbol">FD</span>
          <span>Fair Drop</span>
        </button>
        <span className="admin-badge">ADMIN CONSOLE</span>
        <nav className="dashboard-nav" aria-label="Admin navigation">
          <a className="nav-link active" href="#admin-events">
            Events
          </a>
          <a className="nav-link" href="#traffic">
            Audit
          </a>
          <a className="nav-link" href="#integrity">
            Profile
          </a>
        </nav>
        <button type="button" className="logout-button" onClick={onLogout}>
          Log out
        </button>
      </header>
      <main className="admin-main">
        <section className="admin-intro">
          <div>
            <p className="eyebrow">Control plane / 02</p>
            <h1>Admin dashboard</h1>
            <p className="intro-copy">
              Operate fair allocation windows with a clear view of inventory,
              traffic, and integrity.
            </p>
          </div>
          <div className="admin-identity">
            <span className="pulse-dot" />
            Administrator<strong>Allocation control active</strong>
          </div>
        </section>
        <section className="admin-metrics" aria-label="Live metrics">
          <Metric
            label="Total entries"
            value={formatNumber(metrics.totalEntries)}
            detail="Across active events"
          />
          <Metric
            label="Seats remaining"
            value={formatNumber(seatsRemaining || metrics.seatsRemaining)}
            detail="Available capacity"
            accent="violet"
          />
          <Metric
            label="Requests / sec"
            value={metrics.requestsPerSecond}
            detail="Current throughput"
          />
          <Metric
            label="Claims processed"
            value={formatNumber(metrics.claimsProcessed)}
            detail="Last 24 hours"
            accent="violet"
          />
          <Metric
            label="Rate limited"
            value={formatNumber(metrics.rateLimited)}
            detail="Requests held"
            accent="muted"
          />
          <Metric
            label="Blocked"
            value={formatNumber(metrics.blocked)}
            detail="Traffic denied"
            accent="muted"
          />
        </section>
        <section
          className="admin-create-panel"
          aria-labelledby="create-heading"
        >
          <div>
            <p className="eyebrow">New allocation window</p>
            <h2 id="create-heading">Create event</h2>
          </div>
          <form className="create-event-form" onSubmit={createEvent}>
            <label>
              Event name
              <input
                value={eventName}
                onChange={(event) => setEventName(event.target.value)}
                placeholder="e.g. Winter Assembly"
              />
            </label>
            <label>
              Capacity
              <input
                type="number"
                min="1"
                value={capacity}
                onChange={(event) => setCapacity(event.target.value)}
              />
            </label>
            <button
              type="submit"
              className="button button-primary"
              disabled={creating}
            >
              {creating ? "Creating..." : "Create event"}
            </button>
          </form>
        </section>
        {notice && (
          <p className="admin-notice" role="status">
            {notice}
          </p>
        )}
        {error && (
          <p className="admin-error" role="alert">
            {error}
          </p>
        )}
        <section className="admin-section" id="admin-events">
          <div className="admin-section-heading">
            <div>
              <p className="eyebrow">Lifecycle management</p>
              <h2>Event operations</h2>
            </div>
            <span className="section-count">
              {events.length.toString().padStart(2, "0")} events
            </span>
          </div>
          {loading ? (
            <div className="dashboard-empty">
              <span className="empty-index">--</span>
              <h3>Loading events</h3>
              <p>Reading persisted event inventory.</p>
            </div>
          ) : error && events.length === 0 ? (
            <div className="dashboard-empty">
              <span className="empty-index">!</span>
              <h3>Could not load events</h3>
              <p>{error}</p>
            </div>
          ) : events.length === 0 ? (
            <div className="dashboard-empty">
              <span className="empty-index">00</span>
              <h3>No events created</h3>
              <p>Create an event to begin an allocation window.</p>
            </div>
          ) : (
            <div className="admin-event-list">
              {events.map((event) => {
                const action = actionFor(event.status);
                const isProcessing = processingId === event.id;
                return (
                  <article className="admin-event-row" key={event.id}>
                    <div className="admin-event-title">
                      <span className="event-code">
                        FD / {event.id.slice(0, 4).toUpperCase()}
                      </span>
                      <h3>{event.name}</h3>
                      <span
                        className={`lifecycle lifecycle-${event.status.toLowerCase()}`}
                      >
                        {statusLabel(event.status)}
                      </span>
                    </div>
                    <div className="admin-event-stat">
                      <span>Capacity</span>
                      <strong>{formatNumber(event.capacity)}</strong>
                    </div>
                    <div className="admin-event-stat">
                      <span>Entries</span>
                      <strong>{formatNumber(event.totalEntries)}</strong>
                    </div>
                    <div className="admin-event-stat">
                      <span>Seats remaining</span>
                      <strong>
                        {formatNumber(
                          Math.max(event.capacity - event.totalEntries, 0),
                        )}
                      </strong>
                    </div>
                    <div className="admin-event-stat deadline-stat">
                      <span>Registration deadline</span>
                      <strong>{formatDate(event.registrationDeadline)}</strong>
                    </div>
                    <div className="admin-event-action">
                      {action ? (
                        <button
                          type="button"
                          className="button button-secondary"
                          disabled={isProcessing}
                          onClick={() => transition(event.id)}
                        >
                          {isProcessing ? "Processing..." : action.label}
                        </button>
                      ) : (
                        <span className="action-complete">
                          No action available
                        </span>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
        <section className="admin-lower-grid">
          <div className="admin-panel" id="traffic">
            <div className="admin-panel-heading">
              <div>
                <p className="eyebrow">Traffic monitor</p>
                <h2>Request traffic</h2>
              </div>
              <span className="live-label">
                <i className="pulse-dot" />
                Live
              </span>
            </div>
            <TrafficChart />
          </div>
          <div className="admin-panel" id="integrity">
            <div className="admin-panel-heading">
              <div>
                <p className="eyebrow">Fairness verification</p>
                <h2>Allocation integrity</h2>
              </div>
              <span className="integrity-state">Healthy</span>
            </div>
            <IntegrityPanel integrity={integrity} />
          </div>
        </section>
      </main>
      <footer className="dashboard-footer">
        <span>FAIR DROP / ADMIN CONTROL PLANE</span>
        <span>BUILD 0.4.2</span>
      </footer>
    </div>
  );
}
