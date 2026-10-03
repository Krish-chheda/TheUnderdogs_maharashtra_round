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
    throw new Error(data.detail || "Request failed");
  }
  return data;
};

export const fetchEvents = () => request("/events");

export const fetchEvent = (eventId) => request(`/events/${eventId}`);

export const createEvent = (payload) =>
  request("/admin/events/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
