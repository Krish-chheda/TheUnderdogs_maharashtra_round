import { useEffect, useState } from "react";
import { myEvents } from "../data/events";
import { fetchEvents } from "../lib/api";
import "../events.css";

const formatDate = (value) =>
  value
    ? new Intl.DateTimeFormat("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "Date to be announced";

const formatNumber = (value) => new Intl.NumberFormat("en-IN").format(value);

function StatusBadge({ children, tone = "neutral" }) {
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}

function EventCard({ event, onOpen }) {
  const isOpen = event.status === "Open";
  const fill = Math.min((event.entryCount / event.capacity) * 100, 100);

  return (
    <article className={`event-card accent-${event.accent}`}>
      <div className="event-card-topline">
        <StatusBadge tone={isOpen ? "open" : "closed"}>
          {event.status}
        </StatusBadge>
        <span className="event-code">
          FD / {event.id.slice(0, 4).toUpperCase()}
        </span>
      </div>
      <h3>{event.name}</h3>
      {event.scheduleValid === false && (
        <p className="schedule-warning">{event.scheduleError}</p>
      )}
      <p className="event-description">{event.description}</p>
      <div className="event-meta">
        <div>
          <span>Date & time</span>
          <strong>
            {formatDate(event.date)} {event.timezone}
          </strong>
        </div>
        <div>
          <span>Venue</span>
          <strong>{event.venue}</strong>
        </div>
      </div>
      <div className="capacity-block">
        <div className="capacity-label">
          <span>Entries</span>
          <strong>
            {formatNumber(event.entryCount)} / {formatNumber(event.capacity)}
          </strong>
        </div>
        <div className="capacity-track">
          <span style={{ width: `${fill}%` }} />
        </div>
      </div>
      <div className="event-card-footer">
        <span className="deadline">
          Deadline {formatDate(event.registrationDeadline)}
        </span>
        <button
          type="button"
          className="button button-primary"
          onClick={() => onOpen(event.id)}
        >
          View event <span aria-hidden="true">↗</span>
        </button>
      </div>
    </article>
  );
}

export default function EventsDashboard({ onOpenEvent, onLogout }) {
  const [activeView, setActiveView] = useState("events");
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetchEvents()
      .then((items) => {
        if (active) setEvents(items);
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

  const scrollTo = (view) => {
    setActiveView(view);
    document
      .getElementById(view)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="dashboard-shell">
      <header className="dashboard-header">
        <button
          type="button"
          className="brand-mark"
          onClick={() => scrollTo("events")}
          aria-label="Go to events dashboard"
        >
          <span className="brand-symbol">FD</span>
          <span>Fair Drop</span>
        </button>
        <nav className="dashboard-nav" aria-label="Main navigation">
          <button
            className={activeView === "events" ? "nav-link active" : "nav-link"}
            type="button"
            onClick={() => scrollTo("events")}
          >
            Events
          </button>
          <button
            className={
              activeView === "my-events" ? "nav-link active" : "nav-link"
            }
            type="button"
            onClick={() => scrollTo("my-events")}
          >
            My Events
          </button>
          <button
            className="nav-link"
            type="button"
            onClick={() => setActiveView("audit")}
          >
            Audit
          </button>
          <button
            className="nav-link"
            type="button"
            onClick={() => setActiveView("profile")}
          >
            Profile
          </button>
        </nav>
        <button type="button" className="logout-button" onClick={onLogout}>
          Log out
        </button>
      </header>

      <main className="dashboard-main">
        <section className="dashboard-intro" id="events">
          <div>
            <p className="eyebrow">Allocation control / 01</p>
            <h1>Events dashboard</h1>
            <p className="intro-copy">
              Discover what is opening next. Every entry is recorded, every
              selection is auditable.
            </p>
          </div>
          <div className="system-readout">
            <span className="pulse-dot" />
            System operational<strong>24h selection windows</strong>
          </div>
        </section>

        {activeView === "audit" || activeView === "profile" ? (
          <section className="dashboard-empty compact-empty">
            <span className="empty-index">00</span>
            <h2>
              {activeView === "audit" ? "Audit trail" : "Profile settings"}
            </h2>
            <p>This view is ready for the next product slice.</p>
            <button
              type="button"
              className="button button-secondary"
              onClick={() => scrollTo("events")}
            >
              Back to events
            </button>
          </section>
        ) : (
          <>
            <section
              className="dashboard-section"
              aria-labelledby="available-heading"
            >
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Live inventory</p>
                  <h2 id="available-heading">Available events</h2>
                </div>
                <span className="section-count">
                  {events.length.toString().padStart(2, "0")} listings
                </span>
              </div>
              {loading ? (
                <div className="dashboard-empty">
                  <span className="empty-index">--</span>
                  <h3>Loading events</h3>
                  <p>Reading the current allocation windows.</p>
                </div>
              ) : error ? (
                <div className="dashboard-empty">
                  <span className="empty-index">!</span>
                  <h3>Could not load events</h3>
                  <p>{error}</p>
                </div>
              ) : events.length === 0 ? (
                <div className="dashboard-empty">
                  <span className="empty-index">00</span>
                  <h3>No events available</h3>
                  <p>Check back when the next allocation window opens.</p>
                </div>
              ) : (
                <div className="event-grid">
                  {events.map((event) => (
                    <EventCard
                      key={event.id}
                      event={event}
                      onOpen={onOpenEvent}
                    />
                  ))}
                </div>
              )}
            </section>

            <section
              className="dashboard-section my-events-section"
              id="my-events"
              aria-labelledby="my-events-heading"
            >
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Your allocation history</p>
                  <h2 id="my-events-heading">My events</h2>
                </div>
                <span className="section-count">
                  {myEvents.length.toString().padStart(2, "0")} tracked
                </span>
              </div>
              {myEvents.length === 0 ? (
                <div className="dashboard-empty">
                  <span className="empty-index">00</span>
                  <h3>You have not entered an event yet</h3>
                  <p>
                    When you enter an event, its selection state will appear
                    here.
                  </p>
                </div>
              ) : (
                <div className="my-events-list">
                  {myEvents.map((event) => (
                    <button
                      key={`${event.id}-${event.status}`}
                      type="button"
                      className="my-event-row"
                      onClick={() => onOpenEvent(event.id)}
                    >
                      <span className="my-event-name">
                        <span className="mini-mark">
                          {event.name.slice(0, 1)}
                        </span>
                        <span>
                          <strong>{event.name}</strong>
                          <small>{formatDate(event.date)}</small>
                        </span>
                      </span>
                      <StatusBadge tone={event.status.toLowerCase()}>
                        {event.status}
                      </StatusBadge>
                      <span className="row-action">
                        {event.action} <span aria-hidden="true">→</span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>
      <footer className="dashboard-footer">
        <span>FAIR DROP / ALLOCATION SYSTEM</span>
        <span>BUILD 0.4.2</span>
      </footer>
    </div>
  );
}
