import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { SupervisorAlert } from "../types";

const WS_URL = "ws://127.0.0.1:8001";
const MAX_ALERTS = 20;

function normalizeAlert(raw: any): SupervisorAlert | null {
	if (!raw) return null;
	const direct = raw?.payload?.type ? raw : null;
	const wrapped = raw?.event === "supervisor_alert" && raw?.payload ? raw.payload : null;
	const alert = direct ?? wrapped;
	if (!alert?.payload?.type) return null;
	return {
		event: "supervisor_alert",
		payload: alert.payload,
		timestamp: Number(alert.timestamp) || Date.now() / 1000,
	};
}

function addAlert(alert: SupervisorAlert, setAlerts: Dispatch<SetStateAction<SupervisorAlert[]>>) {
	setAlerts((prev) => {
		const exists = prev.some(
			(item) =>
				item.timestamp === alert.timestamp ||
				(item.payload.run_id === alert.payload.run_id &&
					item.payload.type === alert.payload.type &&
					Math.abs(item.timestamp - alert.timestamp) < 1),
		);
		if (exists) return prev;
		const next = [alert, ...prev];
		return next.slice(0, MAX_ALERTS);
	});
}

export function useSupervisorAlerts() {
	const [alerts, setAlerts] = useState<SupervisorAlert[]>([]);
	const wsRef = useRef<WebSocket | null>(null);

	const dismiss = useCallback((timestamp: number) => {
		setAlerts((prev) => prev.filter((a) => a.timestamp !== timestamp));
	}, []);

	const dismissAll = useCallback(() => {
		setAlerts([]);
	}, []);

	useEffect(() => {
		let ws: WebSocket;
		let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

		const connect = () => {
			ws = new WebSocket(WS_URL);
			wsRef.current = ws;

			ws.onopen = () => {
				ws.send(JSON.stringify({ action: "subscribe_supervisor" }));
			};

			ws.onmessage = (msg) => {
				try {
					const data = JSON.parse(msg.data);
					const alert = normalizeAlert(data);
					if (alert) addAlert(alert, setAlerts);
				} catch {
					// ignore
				}
			};

			ws.onclose = () => {
				reconnectTimer = setTimeout(connect, 5000);
			};

			ws.onerror = () => {
				ws.close();
			};
		};

		connect();
		const pollTimer = setInterval(() => {
			fetch("/api/supervisor/alerts")
				.then((res) => (res.ok ? res.json() : null))
				.then((data) => {
					if (!Array.isArray(data?.alerts)) return;
					for (const raw of data.alerts) {
						const alert = normalizeAlert(raw);
						if (alert) addAlert(alert, setAlerts);
					}
				})
				.catch(() => {});
		}, 5000);

		return () => {
			if (reconnectTimer !== null) clearTimeout(reconnectTimer);
			clearInterval(pollTimer);
			wsRef.current?.close();
		};
	}, []);

	return { alerts, dismiss, dismissAll };
}
