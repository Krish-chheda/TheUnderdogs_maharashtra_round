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

  const retryAfter = response.headers.get("Retry-After");
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join(" ")
      : data.detail;
    const error = new Error(detail || "Request failed");
    error.status = response.status;
    error.retryAfter = retryAfter ? parseInt(retryAfter) : null;
    throw error;
  }
  return data;
};

// Auth
export const signup = (email, password, role = "user") =>
  request("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password, role }),
  });

export const login = (email, password) =>
  request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

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

// Events
export const fetchEvents = () => request("/events");

export const fetchEvent = (eventId) => request(`/events/${eventId}`);

export const joinEvent = (eventId) =>
  request(`/events/${eventId}/join`, { method: "POST" });

export const enterEvent = (eventId) =>
  request(`/events/${eventId}/enter`, { method: "POST" });

export const fetchEventStatus = (eventId) =>
  request(`/events/${eventId}/status`);

export const fetchEventAudit = (eventId) =>
  request(`/events/${eventId}/audit`);

export const claimEvent = (eventId, idempotencyKey) =>
  request(`/events/${eventId}/claim`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });

// Admin Events
export const createEvent = (payload) =>
  request("/admin/events/", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deleteEvent = (eventId) =>
  request(`/admin/events/${eventId}`, { method: "DELETE" });

export const commitAllocation = (eventId) =>
  request(`/admin/events/${eventId}/allocation/commit`, {
    method: "POST",
  });

export const runAllocation = (eventId) =>
  request(`/admin/events/${eventId}/allocation/run`, {
    method: "POST",
  });

export const sweepExpiredClaims = (eventId) =>
  request(`/admin/events/${eventId}/sweep`, {
    method: "POST",
  });
