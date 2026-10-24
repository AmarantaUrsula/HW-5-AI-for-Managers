import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the desk at http://localhost:5173 and opens it in the browser.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, open: true },
});
