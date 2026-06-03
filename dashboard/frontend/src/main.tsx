import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { Toaster } from "@/components/ui/sonner";
import Overview     from "./routes/index";
import AiAlerts     from "./routes/ai-alerts";
import IdsPage      from "./routes/ids";
import IntelPage    from "./routes/intel";
import UebaPage     from "./routes/ueba";
import SoarPage     from "./routes/soar";
import IncidentsPage from "./routes/incidents";
import TopologyPage from "./routes/topology";
import GeoMapPage   from "./routes/geomap";
import ForensicPage from "./routes/forensic";
import "./styles.css";

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <SidebarProvider>
          <AppSidebar />
          <SidebarInset className="min-w-0">
            <Routes>
              <Route path="/"           element={<Overview      />} />
              <Route path="/ai-alerts"  element={<AiAlerts      />} />
              <Route path="/ids"        element={<IdsPage       />} />
              <Route path="/intel"      element={<IntelPage     />} />
              <Route path="/ueba"       element={<UebaPage      />} />
              <Route path="/soar"       element={<SoarPage      />} />
              <Route path="/incidents"  element={<IncidentsPage />} />
              <Route path="/topology"   element={<TopologyPage  />} />
              <Route path="/geomap"     element={<GeoMapPage    />} />
              <Route path="/forensic"   element={<ForensicPage  />} />
            </Routes>
          </SidebarInset>
          <Toaster />
        </SidebarProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
