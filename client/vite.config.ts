import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://127.0.0.1:8000";

// https://vite.dev/config/
export default defineConfig({
	plugins: [react()],
	server: {
		port: 5500,
		proxy: {
			"/api": {
				target: API_TARGET,
				changeOrigin: true,
			},
		},
	},
});
