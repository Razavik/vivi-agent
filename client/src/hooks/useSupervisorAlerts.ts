import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { SupervisorAlert, SupervisorAlertPayload } from "../types";
import { getWebSocketUrl } from "../utils/wsConfig";
import { readJson } from "../utils/http";

const MAX_ALERTS = 20;

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

function normalizeAlert(raw: unknown): SupervisorAlert | null {
	if (!isRecord(raw)) return null;
	const rawPayload = isRecord(raw.payload) ? raw.payload : null;
	const direct = isRecord(rawPayload) && typeof rawPayload.type === "string" ? raw : null;
	const wrapped = raw.event === "supervisor_alert" && rawPayload ? rawPayload : null;
	const alert = direct ?? wrapped;
	if (!isRecord(alert) || !isRecord(alert.payload) || typeof alert.payload.type !== "string") {
		return null;
	}
	return {
		event: "supervisor_alert",
		payload: alert.payload as unknown as SupervisorAlertPayload,
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
			ws = new WebSocket(getWebSocketUrl());
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
				.then((res) => readJson<{ alerts?: unknown[] } | null>(res, null))
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
