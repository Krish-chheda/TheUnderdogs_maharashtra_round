import { useState } from "react";
import AetherRibbonMesh from "@/components/ui/aether-ribbon-mesh";
import AuthPage from "@/components/AuthPage";

export default function App() {
  const [page, setPage] = useState("landing");

  return (
    <AetherRibbonMesh onGetStarted={() => setPage("auth")}>
      {page === "auth" && <AuthPage onBack={() => setPage("landing")} />}
    </AetherRibbonMesh>
  );
}
