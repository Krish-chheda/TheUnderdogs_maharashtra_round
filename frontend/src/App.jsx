import { useEffect, useState } from "react";
import AetherRibbonMesh from "@/components/ui/aether-ribbon-mesh";
import AuthPage from "@/components/AuthPage";
import EventsDashboard from "@/components/EventsDashboard";
import EventDetails from "@/components/EventDetails";
import AdminDashboard from "@/components/AdminDashboard";

const currentPath = () => window.location.pathname;

export default function App() {
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    const handlePopState = () => setPath(currentPath());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = (nextPath) => {
    window.history.pushState({}, "", nextPath);
    setPath(nextPath);
  };

  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_role");
    navigate("/");
  };

  if (path === "/events") {
    return (
      <EventsDashboard
        onOpenEvent={(eventId) => navigate(`/events/${eventId}`)}
        onLogout={logout}
      />
    );
  }

  if (path === "/admin/events") {
    return <AdminDashboard onLogout={logout} />;
  }

  if (path.startsWith("/events/")) {
    return (
      <EventDetails
        eventId={path.split("/")[2]}
        onBack={() => navigate("/events")}
      />
    );
  }

  return (
    <AetherRibbonMesh onGetStarted={() => navigate("/auth")}>
      {path === "/auth" && (
        <AuthPage
          onBack={() => navigate("/")}
          onLogin={(data) =>
            navigate(data?.role === "admin" ? "/admin/events" : "/events")
          }
        />
      )}
    </AetherRibbonMesh>
  );
}
