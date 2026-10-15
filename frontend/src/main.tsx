import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./index.css";
import { LandingPage } from "./site/LandingPage";
import { StaffApp } from "./staff/StaffApp";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

const isStaff = window.location.pathname.replace(/\/+$/, "") === "/staff";
document.title = isStaff ? "Staff inbox | Brightside Dental" : "Brightside Dental";

createRoot(root).render(<StrictMode>{isStaff ? <StaffApp /> : <LandingPage />}</StrictMode>);
