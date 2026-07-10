const DEV_WS_URL = "ws://127.0.0.1:8000/ws";

export function getWebSocketUrl(): string {
	if (import.meta.env.DEV) {
		return import.meta.env.VITE_WS_URL || DEV_WS_URL;
	}

	const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
	return `${protocol}//${window.location.host}/ws`;
}
