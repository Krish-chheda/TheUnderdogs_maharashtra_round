const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const request = async (path, options = {}) => {
  const token = localStorage.getItem("access_token");
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join(" ")
      : data.detail;
    throw new Error(detail || "Request failed");
  }
  return data;
};

export const fetchEvents = () => request("/events");

export const fetchEvent = (eventId) => request(`/events/${eventId}`);

export const requestOtp = (phone) =>
  request("/auth/otp", {
    method: "POST",
    body: JSON.stringify({ phone }),
  });

export const verifyOtp = (phone, code) =>
  request("/auth/verify", {
    method: "POST",
    body: JSON.stringify({ phone, code }),
  });

export const enterEvent = (eventId) =>
  request(`/events/${eventId}/enter`, { method: "POST" });

export const fetchEntryStatus = (eventId) =>
  request(`/events/${eventId}/status`);

export const claimEvent = (eventId, idempotencyKey) =>
  request(`/events/${eventId}/claim`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });

export const createEvent = (payload) =>
  request("/admin/events/", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deleteEvent = (eventId) =>
  request(`/admin/events/${eventId}`, { method: "DELETE" });
