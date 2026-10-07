import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ErrorBox, Loading } from "./components/ui";
import { AppStateProvider, useApp } from "./lib/state";
import { AgentCard } from "./pages/AgentCard";
import { AgentDetail } from "./pages/AgentDetail";
import { Decisions } from "./pages/Decisions";
import { DsoPlanPage } from "./pages/DsoPlan";
import { Impact } from "./pages/Impact";
import { ModelPage } from "./pages/ModelPage";
import { Overview } from "./pages/Overview";
import { RiskList } from "./pages/RiskList";
import { Operations } from "./pages/Operations";
import { Validation } from "./pages/Validation";
import { Login } from "./pages/Login";
import { IntegrationPage } from "./pages/Integration";

function RequireAccess({ admin = false }: { admin?: boolean }) {
  const { authStatus, session, canOperate, t } = useApp();
  const location = useLocation();
  if (authStatus === "loading") return <Loading text={t.loading} />;
  if (authStatus === "signed_out") return <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash }} />;
  if (admin && !canOperate) return <ErrorBox message={t.adminRequired} />;
  return <Outlet key={`${authStatus}:${session?.subject}:${session?.role}`} />;
}

export default function App() {
  return (
    <AppStateProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="login" element={<Login />} />
            <Route element={<RequireAccess />}>
              <Route index element={<Overview />} />
              <Route path="risk" element={<RiskList />} />
              <Route path="agents/:id" element={<AgentDetail />} />
              <Route path="card/:id" element={<AgentCard />} />
              <Route path="dso" element={<DsoPlanPage />} />
              <Route path="impact" element={<Impact />} />
              <Route path="model" element={<ModelPage />} />
              <Route path="decisions" element={<Decisions />} />
              <Route element={<RequireAccess admin />}>
                <Route path="operations" element={<Operations />} />
              </Route>
              <Route path="validation" element={<Validation />} />
              <Route path="integration" element={<IntegrationPage />} />
              <Route path="*" element={<Overview />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AppStateProvider>
  );
}
