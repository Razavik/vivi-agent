const { app, BrowserWindow, nativeTheme } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");

const BACKEND_URL = process.env.AGENT_BACKEND_URL || "http://127.0.0.1:8000";
const STARTUP_WAIT_MS = 60_000;
const MONITOR_STATE_URL = `${BACKEND_URL}/api/monitor/state`;
const APP_SETTINGS_URL = `${BACKEND_URL}/api/app-settings`;
const MONITOR_URL = `${BACKEND_URL}/watch`;

let mainWindow = null;
let monitorWindow = null;
let backendProcess = null;
let monitorPollTimer = null;
let monitorDismissedForRun = false;
let lastMonitorRunning = false;
let cachedShowMonitor = true;

function projectRoot() {
	if (app.isPackaged) {
		return path.join(process.resourcesPath, "app");
	}
	return path.resolve(__dirname, "..", "..");
}

function pythonPath(root) {
	const candidates = [
		path.join(root, ".venv", "Scripts", "python.exe"),
		path.join(path.dirname(process.execPath), ".venv", "Scripts", "python.exe"),
		"python",
	];
	return candidates.find((candidate) => candidate === "python" || fs.existsSync(candidate));
}

function startBackend() {
	if (process.env.AGENT_BACKEND_AUTOSTART === "0") return;

	const root = projectRoot();
	backendProcess = spawn(
		pythonPath(root),
		["-m", "uvicorn", "src.web.asgi:app", "--host", "127.0.0.1", "--port", "8000"],
		{
			cwd: root,
			windowsHide: true,
			stdio: "ignore",
		},
	);
	backendProcess.on("exit", () => {
		backendProcess = null;
	});
}

function readMonitorSettingFromFile() {
	try {
		const root = projectRoot();
		const settingsPath = path.join(root, "data", "app_settings.json");
		if (!fs.existsSync(settingsPath)) return null;
		const raw = fs.readFileSync(settingsPath, "utf8");
		const parsed = JSON.parse(raw);
		if (typeof parsed?.show_monitor === "boolean") {
			return parsed.show_monitor;
		}
		return null;
	} catch {
		return null;
	}
}

function createMainWindow() {
	nativeTheme.themeSource = "dark";

	mainWindow = new BrowserWindow({
		width: 1280,
		height: 820,
		minWidth: 960,
		minHeight: 640,
		title: "Vivi",
		autoHideMenuBar: true,
		backgroundColor: "#0d0b13",
		webPreferences: {
			contextIsolation: true,
			nodeIntegration: false,
			sandbox: true,
		},
	});

	loadWhenReady(mainWindow, BACKEND_URL);
	mainWindow.on("closed", () => {
		mainWindow = null;
	});
}

function createMonitorWindow() {
	if (monitorWindow && !monitorWindow.isDestroyed()) {
		monitorWindow.showInactive();
		monitorWindow.setAlwaysOnTop(true, "screen-saver");
		return monitorWindow;
	}

	monitorWindow = new BrowserWindow({
		width: 340,
		height: 460,
		minWidth: 300,
		minHeight: 360,
		title: "Vivi Monitor",
		alwaysOnTop: true,
		autoHideMenuBar: true,
		skipTaskbar: false,
		backgroundColor: "#0d0b13",
		webPreferences: {
			contextIsolation: true,
			nodeIntegration: false,
			sandbox: true,
		},
	});

	monitorWindow.setAlwaysOnTop(true, "screen-saver");
	monitorWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
	monitorWindow.setMenuBarVisibility(false);
	positionMonitorWindow(monitorWindow);
	loadWhenReady(monitorWindow, MONITOR_URL);

	monitorWindow.on("closed", () => {
		monitorWindow = null;
		monitorDismissedForRun = true;
	});
	return monitorWindow;
}

function positionMonitorWindow(window) {
	const { screen } = require("electron");
	const workArea = screen.getPrimaryDisplay().workArea;
	const bounds = window.getBounds();
	window.setBounds({
		x: workArea.x + workArea.width - bounds.width - 12,
		y: workArea.y + 12,
		width: bounds.width,
		height: Math.min(bounds.height, workArea.height - 24),
	});
}

function startMonitorWatcher() {
	if (monitorPollTimer) return;
	monitorPollTimer = setInterval(async () => {
		const appSettings = await fetchJson(APP_SETTINGS_URL);
		let showMonitor = null;
		if (appSettings && typeof appSettings.show_monitor === "boolean") {
			showMonitor = appSettings.show_monitor;
		} else {
			showMonitor = readMonitorSettingFromFile();
		}
		if (typeof showMonitor === "boolean") {
			cachedShowMonitor = showMonitor;
		}
		// fail-closed: если не удалось прочитать настройку, не показываем монитор
		const effectiveShowMonitor =
			typeof showMonitor === "boolean" ? showMonitor : false;
		if (!effectiveShowMonitor) {
			if (monitorWindow && !monitorWindow.isDestroyed()) {
				monitorWindow.hide();
			}
			return;
		}
		const state = await fetchJson(MONITOR_STATE_URL);
		if (!state) return;
		const isActive = Boolean(state.running || state.pending_confirmation);
		if (isActive && !lastMonitorRunning) {
			monitorDismissedForRun = false;
		}
		lastMonitorRunning = isActive;
		if (state.running || state.pending_confirmation) {
			if (monitorDismissedForRun) return;
			const window = createMonitorWindow();
			if (!window.isDestroyed()) {
				window.showInactive();
				window.setAlwaysOnTop(true, "screen-saver");
			}
			return;
		}
		if (monitorWindow && !monitorWindow.isDestroyed()) {
			monitorWindow.hide();
		}
	}, 1000);
}

app.whenReady().then(() => {
	startBackend();
	createMainWindow();
	startMonitorWatcher();

	app.on("activate", () => {
		if (BrowserWindow.getAllWindows().length === 0) {
			createMainWindow();
		}
	});
});

app.on("before-quit", () => {
	if (monitorPollTimer) {
		clearInterval(monitorPollTimer);
		monitorPollTimer = null;
	}
	if (backendProcess) {
		backendProcess.kill();
		backendProcess = null;
	}
});

app.on("window-all-closed", () => {
	app.quit();
});

function checkUrl(url) {
	return new Promise((resolve) => {
		const request = http.get(url, { timeout: 1500 }, (response) => {
			response.resume();
			resolve(response.statusCode >= 200 && response.statusCode < 500);
		});
		request.on("timeout", () => {
			request.destroy();
			resolve(false);
		});
		request.on("error", () => resolve(false));
	});
}

function fetchJson(url) {
	return new Promise((resolve) => {
		const request = http.get(url, { timeout: 1500 }, (response) => {
			let body = "";
			response.setEncoding("utf8");
			response.on("data", (chunk) => {
				body += chunk;
			});
			response.on("end", () => {
				try {
					resolve(JSON.parse(body));
				} catch {
					resolve(null);
				}
			});
		});
		request.on("timeout", () => {
			request.destroy();
			resolve(null);
		});
		request.on("error", () => resolve(null));
	});
}

async function loadWhenReady(window, url) {
	const deadline = Date.now() + STARTUP_WAIT_MS;
	while (!window.isDestroyed() && Date.now() < deadline) {
		if (await checkUrl(url)) {
			await window.loadURL(url);
			return;
		}
		await new Promise((resolve) => setTimeout(resolve, 500));
	}

	if (!window.isDestroyed()) {
		await window.loadURL(
			`data:text/html;charset=utf-8,${encodeURIComponent(
				"<body style='margin:0;background:#0d0b13;color:#f1edf7;font:14px Segoe UI,sans-serif;display:grid;place-items:center;height:100vh'><main><h2>Vivi</h2><p>Backend is not available at 127.0.0.1:8000.</p></main></body>",
			)}`,
		);
	}
}
