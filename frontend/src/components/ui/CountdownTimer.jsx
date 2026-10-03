import { useState, useEffect } from "react";

export default function CountdownTimer({ expiresAt, onExpire }) {
  const [display, setDisplay] = useState("--:--:--");
  const [isExpired, setIsExpired] = useState(false);

  useEffect(() => {
    if (!expiresAt) return;

    const update = () => {
      const now = new Date();
      const expires = new Date(expiresAt);
      const diff = expires - now;

      if (diff <= 0) {
        setDisplay("EXPIRED");
        setIsExpired(true);
        onExpire?.();
      } else {
        const hours = Math.floor(diff / 3600000);
        const minutes = Math.floor((diff % 3600000) / 60000);
        const seconds = Math.floor((diff % 60000) / 1000);
        setDisplay(`${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`);
      }
    };

    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [expiresAt, onExpire]);

  return (
    <div
      style={{
        fontFamily: "monospace",
        fontSize: "24px",
        fontWeight: "bold",
        color: isExpired ? "#ef4444" : "#38bdf8",
        letterSpacing: "2px",
      }}
    >
      {display}
    </div>
  );
}
