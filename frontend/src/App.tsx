import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AppStateProvider } from "./lib/state";
import { AgentCard } from "./pages/AgentCard";
import { AgentDetail } from "./pages/AgentDetail";
import { Decisions } from "./pages/Decisions";
import { DsoPlanPage } from "./pages/DsoPlan";
import { Impact } from "./pages/Impact";
import { ModelPage } from "./pages/ModelPage";
import { Overview } from "./pages/Overview";
import { RiskList } from "./pages/RiskList";

export default function App() {
  return (
    <AppStateProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="risk" element={<RiskList />} />
            <Route path="agents/:id" element={<AgentDetail />} />
            <Route path="card/:id" element={<AgentCard />} />
            <Route path="dso" element={<DsoPlanPage />} />
            <Route path="impact" element={<Impact />} />
            <Route path="model" element={<ModelPage />} />
            <Route path="decisions" element={<Decisions />} />
            <Route path="*" element={<Overview />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppStateProvider>
  );
}
