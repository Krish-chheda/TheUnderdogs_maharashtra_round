import { useEffect, useState } from "react";
import { events as mockEvents } from "../data/events";
import {
  claimEvent,
  enterEvent,
  fetchEntryStatus,
  fetchEvent,
  requestOtp,
  verifyOtp,
} from "../lib/api";
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

const statusCopy = {
  ELIGIBLE: "Entry recorded. Waiting for fair allocation.",
  WINNER: "You are a winner. Claim your seat before the window closes.",
  WAITLISTED: "You are waitlisted. We will notify you if a seat is released.",
  RESERVED: "Seat secured. Your reservation is confirmed.",
  EXPIRED: "The claim window expired. Wait for the next seat release.",
};

export default function EventDetails({ eventId, onBack }) {
  const [event, setEvent] = useState(() =>
    mockEvents.find((item) => item.id === eventId),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [phase, setPhase] = useState("details");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [preference, setPreference] = useState("standard");
  const [entryStatus, setEntryStatus] = useState("");
  const [claimExpiresAt, setClaimExpiresAt] = useState("");
  const [reservation, setReservation] = useState(null);
  const [busy, setBusy] = useState(false);

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

  useEffect(() => {
    if (!localStorage.getItem("access_token")) return undefined;
    let active = true;
    fetchEntryStatus(eventId)
      .then((status) => {
        if (active) {
          setEntryStatus(status.status);
          setClaimExpiresAt(status.claim_expires_at || "");
          setPhase("entered");
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [eventId]);

  useEffect(() => {
    if (!entryStatus) return undefined;
    const refreshStatus = async () => {
      const status = await fetchEntryStatus(eventId);
      setEntryStatus(status.status);
      setClaimExpiresAt(status.claim_expires_at || "");
      setPhase("entered");
    };
    const interval = window.setInterval(() => {
      refreshStatus().catch(() => undefined);
    }, 5000);
    return () => window.clearInterval(interval);
  }, [eventId, entryStatus]);

  const runAction = async (action, success) => {
    setBusy(true);
    setError("");
    try {
      await action();
      success();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const submitPhone = (formEvent) => {
    formEvent.preventDefault();
    runAction(
      () => requestOtp(phone),
      () => setPhase("otp"),
    );
  };

  const submitOtp = (formEvent) => {
    formEvent.preventDefault();
    runAction(
      async () => {
        const result = await verifyOtp(phone, otp);
        localStorage.setItem("access_token", result.access_token);
        if (result.role) localStorage.setItem("user_role", result.role);
      },
      () => setPhase("availability"),
    );
  };

  const submitEntry = () =>
    runAction(
      () => enterEvent(eventId),
      () => {
        setEntryStatus("ELIGIBLE");
        setPhase("entered");
      },
    );

  const submitClaim = () =>
    runAction(
      async () => {
        const result = await claimEvent(
          eventId,
          `${eventId}-${crypto.randomUUID()}`,
        );
        setReservation(result);
      },
      () => setEntryStatus("RESERVED"),
    );

  if (loading && !event)
    return (
      <JourneyMessage
        title="Loading event"
        text="Reading the persisted event record."
      />
    );
  if (!event)
    return (
      <JourneyMessage
        title="Event not found"
        text={error || "This allocation window does not exist or has moved."}
        onBack={onBack}
      />
    );

  const canRegister = event.status === "Open" && !entryStatus;
  const showJourney = phase !== "details" || entryStatus;
  const availableSeats = Math.max(
    (event.capacity || 0) - (event.entryCount || 0),
    0,
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
      <section className={`detail-hero accent-${event.accent || "cyan"}`}>
        <p className="eyebrow">Event detail / {event.id}</p>
        <StatusBadge tone={event.status === "Open" ? "open" : "closed"}>
          {event.status}
        </StatusBadge>
        <h1>{event.name}</h1>
        <p className="detail-description">{event.description}</p>
        {event.scheduleValid === false && (
          <p className="schedule-warning">
            {event.scheduleError ||
              "This event has an invalid schedule and cannot accept registrations."}
          </p>
        )}
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
        {!showJourney && (
          <button
            type="button"
            className="button button-primary"
            disabled={!canRegister}
            onClick={() => setPhase("phone")}
          >
            {canRegister ? "Register now" : "Registration closed"}
          </button>
        )}
        {showJourney && (
          <JourneyPanel
            phase={phase}
            availableSeats={availableSeats}
            phone={phone}
            setPhone={setPhone}
            otp={otp}
            setOtp={setOtp}
            preference={preference}
            setPreference={setPreference}
            busy={busy}
            error={error}
            entryStatus={entryStatus}
            claimExpiresAt={claimExpiresAt}
            reservation={reservation}
            onPhone={submitPhone}
            onOtp={submitOtp}
            onEnter={submitEntry}
            onClaim={submitClaim}
          />
        )}
      </section>
    </main>
  );
}

function JourneyPanel({
  phase,
  availableSeats,
  phone,
  setPhone,
  otp,
  setOtp,
  preference,
  setPreference,
  busy,
  error,
  entryStatus,
  claimExpiresAt,
  reservation,
  onPhone,
  onOtp,
  onEnter,
  onClaim,
}) {
  if (entryStatus) {
    const winner = entryStatus === "WINNER";
    return (
      <div className="journey-panel">
        <p className="eyebrow">Allocation status</p>
        <StatusBadge tone={entryStatus.toLowerCase()}>
          {entryStatus}
        </StatusBadge>
        <h2>{statusCopy[entryStatus] || "Allocation status updated."}</h2>
        {winner && (
          <>
            <p className="journey-muted">
              Claim by {formatDate(claimExpiresAt)}.
            </p>
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={onClaim}
            >
              {busy ? "Claiming..." : "Pay & confirm seat"}
            </button>
          </>
        )}
        {entryStatus === "RESERVED" && reservation && (
          <p className="journey-success">
            Seat {reservation.seat_number} secured. Reservation{" "}
            {reservation.reservation_id.slice(0, 8)}.
          </p>
        )}
        {(entryStatus === "WAITLISTED" || entryStatus === "EXPIRED") && (
          <p className="journey-muted">
            Keep this page open for allocation updates.
          </p>
        )}
      </div>
    );
  }
  if (phase === "phone")
    return (
      <div className="journey-panel">
        <p className="eyebrow">Step 01 / Phone verification</p>
        <h2>Verify your phone to enter</h2>
        <form onSubmit={onPhone}>
          <label className="journey-label">
            10-digit phone number
            <input
              className="journey-input"
              type="tel"
              inputMode="numeric"
              pattern="[0-9]{10}"
              maxLength="10"
              required
              value={phone}
              onChange={(event) =>
                setPhone(event.target.value.replace(/\D/g, ""))
              }
              placeholder="9876543210"
            />
          </label>
          <button
            type="submit"
            className="button button-primary"
            disabled={busy}
          >
            {busy ? "Sending..." : "Send OTP"}
          </button>
        </form>
        <JourneyError error={error} />
      </div>
    );
  if (phase === "otp")
    return (
      <div className="journey-panel">
        <p className="eyebrow">Step 02 / OTP verification</p>
        <h2>Enter the code sent to {phone}</h2>
        <form onSubmit={onOtp}>
          <label className="journey-label">
            6-digit OTP
            <input
              className="journey-input"
              type="text"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength="6"
              required
              value={otp}
              onChange={(event) =>
                setOtp(event.target.value.replace(/\D/g, ""))
              }
              placeholder="000000"
            />
          </label>
          <button
            type="submit"
            className="button button-primary"
            disabled={busy}
          >
            {busy ? "Verifying..." : "Verify OTP"}
          </button>
        </form>
        <JourneyError error={error} />
      </div>
    );
  if (phase === "availability")
    return (
      <div className="journey-panel">
        <p className="eyebrow">Step 03 / Availability</p>
        <h2>{availableSeats} seats currently available</h2>
        <p className="journey-muted">
          Your entry is placed into the fair allocation pool. Selection is not
          first-come, first-served.
        </p>
        <label className="journey-label">
          Preference
          <select
            className="journey-input"
            value={preference}
            onChange={(event) => setPreference(event.target.value)}
          >
            <option value="standard">Standard entry</option>
            <option value="accessible">Accessible entry</option>
            <option value="quiet">Low-sensory preference</option>
          </select>
        </label>
        <button
          type="button"
          className="button button-primary"
          disabled={busy}
          onClick={onEnter}
        >
          {busy ? "Recording entry..." : "Enter the drop"}
        </button>
        <JourneyError error={error} />
      </div>
    );
  return (
    <div className="journey-panel">
      <p className="eyebrow">Entry recorded</p>
      <StatusBadge tone="eligible">ELIGIBLE</StatusBadge>
      <h2>Wait for fair allocation</h2>
      <p className="journey-muted">
        The system will assign winners and waitlisted places after the
        registration window closes.
      </p>
      <JourneyError error={error} />
    </div>
  );
}

function JourneyMessage({ title, text, onBack }) {
  return (
    <main className="dashboard-shell">
      <section className="dashboard-empty standalone-empty">
        <span className="empty-index">--</span>
        <h1>{title}</h1>
        <p>{text}</p>
        {onBack && (
          <button
            className="button button-primary"
            type="button"
            onClick={onBack}
          >
            Back to events
          </button>
        )}
      </section>
    </main>
  );
}

function JourneyError({ error }) {
  return error ? (
    <p className="journey-error" role="alert">
      {error}
    </p>
  ) : null;
}

function StatusBadge({ children, tone }) {
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}
