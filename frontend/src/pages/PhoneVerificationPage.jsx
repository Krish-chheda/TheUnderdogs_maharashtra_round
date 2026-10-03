import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { requestOtp } from "../lib/api";

const styles = {
  container: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "20px",
    color: "#f8fafc",
  },
  panel: {
    width: "min(400px, 100%)",
    padding: "32px",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "12px",
    background: "rgba(3, 7, 18, 0.8)",
  },
  title: {
    fontSize: "24px",
    fontWeight: 700,
    margin: "0 0 8px 0",
  },
  subtitle: {
    fontSize: "14px",
    color: "#cbd5e1",
    margin: "0 0 32px 0",
  },
  label: {
    display: "block",
    fontSize: "13px",
    color: "#cbd5e1",
    marginTop: "16px",
    marginBottom: "8px",
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: "12px 14px",
    border: "1px solid rgba(148, 163, 184, 0.45)",
    borderRadius: "6px",
    background: "rgba(15, 23, 42, 0.8)",
    color: "#f8fafc",
    font: "inherit",
  },
  button: {
    width: "100%",
    marginTop: "24px",
    padding: "13px",
    border: 0,
    borderRadius: "6px",
    background: "#38bdf8",
    color: "#082f49",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: "16px",
  },
  buttonDisabled: {
    background: "#64748b",
    cursor: "not-allowed",
  },
  error: {
    padding: "12px",
    borderRadius: "6px",
    background: "rgba(239, 68, 68, 0.1)",
    color: "#fecaca",
    border: "1px solid #ef4444",
    margin: "16px 0",
    fontSize: "14px",
  },
  backBtn: {
    marginTop: "16px",
    padding: "10px",
    border: "1px solid #64748b",
    borderRadius: "6px",
    background: "transparent",
    color: "#cbd5e1",
    cursor: "pointer",
    width: "100%",
    fontSize: "14px",
  },
};

export default function PhoneVerificationPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      if (!/^\d{10}$/.test(phone)) {
        throw new Error("Phone must be 10 digits");
      }
      await requestOtp(phone);
      navigate(`/events/${eventId}/otp?phone=${encodeURIComponent(phone)}`);
    } catch (err) {
      if (err.status === 429) {
        setError(
          `Rate limited. Please wait ${err.retryAfter || 20} seconds before trying again.`
        );
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.panel}>
        <h2 style={styles.title}>Phone Verification</h2>
        <p style={styles.subtitle}>
          Enter your phone number to verify your identity
        </p>

        {error && <div style={styles.error}>{error}</div>}

        <form onSubmit={handleSubmit}>
          <label style={styles.label}>Phone Number</label>
          <input
            type="tel"
            style={styles.input}
            placeholder="Enter 10-digit phone number"
            value={phone}
            onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))}
            disabled={loading}
            required
          />

          <button
            type="submit"
            style={{
              ...styles.button,
              ...(loading && styles.buttonDisabled),
            }}
            disabled={loading}
          >
            {loading ? "Sending OTP..." : "Send OTP"}
          </button>
        </form>

        <button
          style={styles.backBtn}
          onClick={() => navigate(`/events/${eventId}`)}
        >
          Back to Event
        </button>
      </div>
    </div>
  );
}
