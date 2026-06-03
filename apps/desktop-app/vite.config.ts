import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],

  // Tauri expects a fixed port and strict mode so Rust knows where to point the WebView
  clearScreen: false,

  server: {
    port: 5174,
    strictPort: true,
    host: "127.0.0.1",
    // HMR port must differ from the dev server port
    hmr: {
      protocol: "ws",
      host: "127.0.0.1",
      port: 5183,
    },
    // Allow Tauri to reload the window when Vite files change
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },

  preview: {
    port: 4174,
  },

  // Expose VITE_ and TAURI_ env vars to the frontend
  envPrefix: ["VITE_", "TAURI_"],
});
