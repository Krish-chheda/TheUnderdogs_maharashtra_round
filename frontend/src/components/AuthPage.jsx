import { useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const styles = {
  panel: {
    width: "min(430px, 100%)",
    boxSizing: "border-box",
    padding: "32px",
    border: "1px solid rgba(148, 163, 184, 0.35)",
    borderRadius: "12px",
    background: "rgba(3, 7, 18, 0.82)",
    color: "#f8fafc",
    boxShadow: "0 24px 80px rgba(0, 0, 0, 0.35)",
    backdropFilter: "blur(16px)",
  },
  input: {
    width: "100%",
    boxSizing: "border-box",
    marginTop: "8px",
    padding: "12px 14px",
    border: "1px solid rgba(148, 163, 184, 0.45)",
    borderRadius: "6px",
    background: "rgba(15, 23, 42, 0.8)",
    color: "#f8fafc",
    font: "inherit",
  },
  label: {
    display: "block",
    marginTop: "16px",
    fontSize: "13px",
    color: "#cbd5e1",
  },
  primaryButton: {
    width: "100%",
    marginTop: "24px",
    padding: "13px 18px",
    border: 0,
    borderRadius: "6px",
    background: "#38bdf8",
    color: "#082f49",
    fontWeight: 800,
    cursor: "pointer",
  },
};

export default function AuthPage({ onBack }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(
        `${API_URL}/auth/${mode === "login" ? "login" : "signup"}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            mode === "login" ? { email, password } : { email, password, role },
          ),
        },
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Authentication failed");

      if (mode === "signup") {
        setMode("login");
        setMessage("Account created. Log in to continue.");
      } else {
        localStorage.setItem("access_token", data.access_token);
        localStorage.setItem("user_role", data.role);
        setMessage(`Logged in as ${data.role}.`);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 20,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        boxSizing: "border-box",
      }}
    >
      <div style={styles.panel}>
        <button
          type="button"
          onClick={onBack}
          style={{
            border: 0,
            background: "transparent",
            color: "#94a3b8",
            cursor: "pointer",
            padding: 0,
          }}
        >
          Back to home
        </button>
        <h2
          style={{ margin: "22px 0 8px", color: "#f8fafc", fontSize: "28px" }}
        >
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h2>
        <p style={{ margin: 0, color: "#94a3b8", fontSize: "14px" }}>
          {mode === "login"
            ? "Enter your credentials to continue."
            : "Choose how you will use Fair Drop."}
        </p>

        <div style={{ display: "flex", gap: "8px", marginTop: "24px" }}>
          {["login", "signup"].map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => {
                setMode(tab);
                setError("");
                setMessage("");
              }}
              style={{
                flex: 1,
                padding: "10px",
                border: `1px solid ${mode === tab ? "#38bdf8" : "#475569"}`,
                borderRadius: "5px",
                background:
                  mode === tab ? "rgba(56, 189, 248, 0.14)" : "transparent",
                color: "#e2e8f0",
                cursor: "pointer",
                textTransform: "capitalize",
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        <form onSubmit={submit}>
          <label style={styles.label} htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            style={styles.input}
            autoComplete="email"
          />
          <label style={styles.label} htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            style={styles.input}
            autoComplete={
              mode === "login" ? "current-password" : "new-password"
            }
          />
          {mode === "signup" && (
            <>
              <label style={styles.label} htmlFor="role">
                Account type
              </label>
              <select
                id="role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
                style={styles.input}
              >
                <option value="user">User</option>
                <option value="admin">Admin</option>
              </select>
            </>
          )}
          <button
            type="submit"
            disabled={loading}
            style={{ ...styles.primaryButton, opacity: loading ? 0.65 : 1 }}
          >
            {loading
              ? "Please wait..."
              : mode === "login"
                ? "Log in"
                : "Create account"}
          </button>
        </form>
        {message && (
          <p
            role="status"
            style={{ color: "#86efac", margin: "16px 0 0", fontSize: "14px" }}
          >
            {message}
          </p>
        )}
        {error && (
          <p
            role="alert"
            style={{ color: "#fda4af", margin: "16px 0 0", fontSize: "14px" }}
          >
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
