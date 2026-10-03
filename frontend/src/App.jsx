import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";

// Pages
import AuthPage from "./components/AuthPage";
import EventsListPage from "./pages/EventsListPage";
import EventDetailsPage from "./pages/EventDetailsPage";
import PhoneVerificationPage from "./pages/PhoneVerificationPage";
import OTPPage from "./pages/OTPPage";
import EntryDropPage from "./pages/EntryDropPage";
import StatusPage from "./pages/StatusPage";
import ClaimPage from "./pages/ClaimPage";
import AuditPage from "./pages/AuditPage";
import AdminEventsPage from "./pages/AdminEventsPage";
import AdminCommandCenterPage from "./pages/AdminCommandCenterPage";
import AdminResultsPage from "./pages/AdminResultsPage";
import AdminBotTestingPage from "./pages/AdminBotTestingPage";
import AetherRibbonMesh from "./components/ui/aether-ribbon-mesh";

// Protected route wrapper
function ProtectedRoute({ children, isAdmin = false }) {
  const token = localStorage.getItem("access_token");
  const role = localStorage.getItem("user_role");

  if (!token) {
    return <Navigate to="/auth" />;
  }

  if (isAdmin && role !== "admin") {
    return <Navigate to="/events" />;
  }

  return children;
}

// Home page
function HomePageContent() {
  const navigate = useNavigate();
  return (
    <AetherRibbonMesh
      onGetStarted={() => navigate("/auth")}
    />
  );
}

export default function App() {
  return (
    <Router>
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<HomePageContent />} />
        <Route path="/auth" element={<AuthPage />} />

        {/* User routes */}
        <Route
          path="/events"
          element={
            <ProtectedRoute>
              <EventsListPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/events/:eventId"
          element={
            <ProtectedRoute>
              <EventDetailsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/events/:eventId/verify"
          element={
            <ProtectedRoute>
              <PhoneVerificationPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/events/:eventId/otp"
          element={
            <ProtectedRoute>
              <OTPPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/events/:eventId/entry"
          element={
            <ProtectedRoute>
              <EntryDropPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/events/:eventId/status"
          element={
            <ProtectedRoute>
              <StatusPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/events/:eventId/claim"
          element={
            <ProtectedRoute>
              <ClaimPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/events/:eventId/audit"
          element={
            <AuditPage />
          }
        />

        {/* Admin routes */}
        <Route
          path="/admin/events"
          element={
            <ProtectedRoute isAdmin>
              <AdminEventsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/events/:eventId"
          element={
            <ProtectedRoute isAdmin>
              <AdminCommandCenterPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/events/:eventId/results"
          element={
            <ProtectedRoute isAdmin>
              <AdminResultsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/events/:eventId/bots"
          element={
            <ProtectedRoute isAdmin>
              <AdminBotTestingPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin/events/:eventId/audit"
          element={
            <ProtectedRoute isAdmin>
              <AuditPage />
            </ProtectedRoute>
          }
        />

        {/* Catch all */}
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Router>
  );
}
