import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { NearbyProvider } from "./state/NearbyContext.jsx";
import { PeopleProvider } from "./state/PeopleContext.jsx";
import { AlertsProvider } from "./state/AlertsContext.jsx";
import { TripProvider } from "./state/TripContext.jsx";
import { DealBookingProvider } from "./state/DealBookingContext.jsx";
import { AccountSyncProvider } from "./state/AccountSyncContext.jsx";
import "./styles.css";

// Makes the app installable and lets phones show notifications. Needs HTTPS (or localhost) and a production build.
if ("serviceWorker" in navigator && import.meta.env.PROD && window.isSecureContext) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <TripProvider>
        <NearbyProvider>
          <PeopleProvider>
            <AlertsProvider>
              <DealBookingProvider>
                <AccountSyncProvider>
                  <App />
                </AccountSyncProvider>
              </DealBookingProvider>
            </AlertsProvider>
          </PeopleProvider>
        </NearbyProvider>
      </TripProvider>
    </BrowserRouter>
  </StrictMode>,
);
