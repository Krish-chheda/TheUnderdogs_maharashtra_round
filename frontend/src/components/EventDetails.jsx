import { useEffect, useState } from "react";
import { events as mockEvents } from "../data/events";
import { fetchEvent } from "../lib/api";
import "../events.css";

const formatDate = (value) =>
  value
    ? new Intl.DateTimeFormat("en-IN", {
        day: "2-digit",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(value))
    : "Date to be announced";

export default function EventDetails({ eventId, onBack }) {
  const [event, setEvent] = useState(() =>
    mockEvents.find((item) => item.id === eventId),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetchEvent(eventId)
      .then((item) => {
        if (active) setEvent(item);
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
  }, [eventId]);

  if (loading && !event)
    return (
      <main className="dashboard-shell">
        <section className="dashboard-empty standalone-empty">
          <span className="empty-index">--</span>
          <h1>Loading event</h1>
          <p>Reading the persisted event record.</p>
        </section>
      </main>
    );
  if (!event)
    return (
      <main className="dashboard-shell">
        <section className="dashboard-empty standalone-empty">
          <span className="empty-index">404</span>
          <h1>Event not found</h1>
          <p>
            {error || "This allocation window does not exist or has moved."}
          </p>
          <button
            className="button button-primary"
            type="button"
            onClick={onBack}
          >
            Back to events
          </button>
        </section>
      </main>
    );

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <button type="button" className="brand-mark" onClick={onBack}>
          <span className="brand-symbol">FD</span>
          <span>Fair Drop</span>
        </button>
        <button type="button" className="logout-button" onClick={onBack}>
          Back to events
        </button>
      </header>
      <section className={`detail-hero accent-${event.accent}`}>
        <p className="eyebrow">Event detail / {event.id}</p>
        <StatusBadge
          status={event.status}
          tone={event.status === "Open" ? "open" : "closed"}
        >
          {event.status}
        </StatusBadge>
        <h1>{event.name}</h1>
        <p className="detail-description">{event.description}</p>
        <div className="detail-grid">
          <div>
            <span>Event date</span>
            <strong>
              {formatDate(event.date)} {event.timezone}
            </strong>
          </div>
          <div>
            <span>Venue</span>
            <strong>{event.venue}</strong>
          </div>
          <div>
            <span>Capacity</span>
            <strong>
              {event.entryCount} / {event.capacity} entries
            </strong>
          </div>
          <div>
            <span>Registration deadline</span>
            <strong>{formatDate(event.registrationDeadline)}</strong>
          </div>
        </div>
        <button
          type="button"
          className="button button-primary"
          disabled={event.status !== "Open"}
        >
          {event.status === "Open"
            ? "Registration coming soon"
            : "Registration closed"}
        </button>
      </section>
    </main>
  );
}

function StatusBadge({ children, tone }) {
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}
