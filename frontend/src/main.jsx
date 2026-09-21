import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { NearbyProvider } from "./state/NearbyContext.jsx";
import { TripProvider } from "./state/TripContext.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <TripProvider>
        <NearbyProvider>
          <App />
        </NearbyProvider>
      </TripProvider>
    </BrowserRouter>
  </StrictMode>,
);
