import { useState, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { verifyOtp } from "../lib/api";

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
  otpContainer: {
    display: "flex",
    gap: "8px",
    justifyContent: "center",
    marginTop: "32px",
    marginBottom: "32px",
  },
  otpInput: {
    width: "50px",
    height: "50px",
    fontSize: "24px",
    fontWeight: "bold",
    textAlign: "center",
    border: "1px solid rgba(148, 163, 184, 0.45)",
    borderRadius: "6px",
    background: "rgba(15, 23, 42, 0.8)",
    color: "#f8fafc",
  },
  button: {
    width: "100%",
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

export default function OTPPage() {
  const { eventId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const phone = searchParams.get("phone");
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const refs = useRef([]);

  const handleChange = (index, value) => {
    if (!/^\d*$/.test(value)) return;
    const newOtp = [...otp];
    newOtp[index] = value.slice(-1);
    setOtp(newOtp);

    if (value && index < 5) {
      refs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      refs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    const paste = e.clipboardData.getData("text");
    const digits = paste.replace(/\D/g, "").slice(0, 6);
    if (digits.length > 0) {
      const newOtp = digits.split("").concat(["", "", "", "", "", ""]).slice(0, 6);
      setOtp(newOtp);
      e.preventDefault();
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const code = otp.join("");
    if (code.length !== 6) {
      setError("Please enter all 6 digits");
      return;
    }

    setLoading(true);
    setError("");

    try {
      await verifyOtp(phone, code);
      navigate(`/events/${eventId}/entry`);
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
        <h2 style={styles.title}>Enter Verification Code</h2>
        <p style={styles.subtitle}>
          We sent a 6-digit code to {phone}
        </p>

        {error && <div style={styles.error}>{error}</div>}

        <form onSubmit={handleSubmit}>
          <div style={styles.otpContainer} onPaste={handlePaste}>
            {otp.map((digit, index) => (
              <input
                key={index}
                ref={(el) => (refs.current[index] = el)}
                type="text"
                style={styles.otpInput}
                value={digit}
                onChange={(e) => handleChange(index, e.target.value)}
                onKeyDown={(e) => handleKeyDown(index, e)}
                inputMode="numeric"
                maxLength="1"
                disabled={loading}
              />
            ))}
          </div>

          <button
            type="submit"
            style={{
              ...styles.button,
              ...(loading && styles.buttonDisabled),
            }}
            disabled={loading || otp.some((d) => !d)}
          >
            {loading ? "Verifying..." : "Verify"}
          </button>
        </form>

        <button
          style={styles.backBtn}
          onClick={() => navigate(`/events/${eventId}/verify`)}
        >
          Back
        </button>
      </div>
    </div>
  );
}
