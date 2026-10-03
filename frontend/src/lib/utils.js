// Countdown timer utilities
export function useCountdown(expiresAt, onExpire) {
  const [timeLeft, setTimeLeft] = React.useState(null);

  React.useEffect(() => {
    if (!expiresAt) return;

    const update = () => {
      const now = new Date();
      const expires = new Date(expiresAt);
      const diff = expires - now;

      if (diff <= 0) {
        setTimeLeft("EXPIRED");
        onExpire?.();
      } else {
        const hours = Math.floor(diff / 3600000);
        const minutes = Math.floor((diff % 3600000) / 60000);
        const seconds = Math.floor((diff % 60000) / 1000);
        setTimeLeft({ hours, minutes, seconds });
      }
    };

    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [expiresAt, onExpire]);

  return timeLeft;
}

// Format countdown display
export function formatCountdown(timeLeft) {
  if (!timeLeft) return "--:--:--";
  if (timeLeft === "EXPIRED") return "EXPIRED";
  const { hours, minutes, seconds } = timeLeft;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

// Seed verification
export async function verifySeedCommitment(revealedSeed, seedCommitment) {
  const encoder = new TextEncoder();
  const data = encoder.encode(revealedSeed);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const computedHash = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  return computedHash === seedCommitment;
}

// Generate UUID for idempotency
export function generateIdempotencyKey() {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

// Format datetime
export function formatDateTime(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  return date.toLocaleString();
}

// Format date only
export function formatDate(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  return date.toLocaleDateString();
}

// Format time only
export function formatTime(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  return date.toLocaleTimeString();
}

// Check if event registration is open
export function isEventOpen(event) {
  if (!event) return false;
  return event.isOpen && event.status === "Open";
}

// Get event status label
export function getEventStatusLabel(event) {
  if (!event) return "Unknown";
  if (event.status === "Invalid schedule") return "Invalid Schedule";
  return event.status;
}
