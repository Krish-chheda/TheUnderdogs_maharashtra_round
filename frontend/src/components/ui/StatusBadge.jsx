export default function StatusBadge({ status }) {
  const statusColors = {
    Open: "#34d399",
    Closed: "#ef4444",
    Completed: "#8b5cf6",
    "Invalid schedule": "#f97316",
    WINNER: "#34d399",
    WAITLISTED: "#f59e0b",
    ELIGIBLE: "#3b82f6",
    RESERVED: "#8b5cf6",
    EXPIRED: "#ef4444",
    "ALLOCATION_COMPLETE": "#34d399",
    "COMMITTED": "#3b82f6",
  };

  const color = statusColors[status] || "#64748b";

  return (
    <span
      style={{
        display: "inline-block",
        padding: "4px 12px",
        borderRadius: "4px",
        backgroundColor: `${color}20`,
        color: color,
        fontSize: "12px",
        fontWeight: 600,
        border: `1px solid ${color}40`,
      }}
    >
      {status}
    </span>
  );
}
