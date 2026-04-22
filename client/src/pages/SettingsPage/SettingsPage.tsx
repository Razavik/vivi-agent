import { useState, useEffect, useCallback } from "react";
import styles from "./SettingsPage.module.css";

const AGENTS = [
	{ key: "director", name: "Директор", hint: "Основной агент — планирует и делегирует задачи" },
	{ key: "file", name: "Файловый агент", hint: "Работа с файлами, кодом, директориями" },
	{ key: "system", name: "Системный агент", hint: "PowerShell, процессы, системная информация" },
	{ key: "telegram", name: "Telegram-агент", hint: "Работа с Telegram API" },
	{ key: "web", name: "Веб-агент", hint: "Загрузка и чтение веб-страниц" },
];

export function SettingsPage() {
	const [defaultModel, setDefaultModel] = useState("");
	const [models, setModels] = useState<Record<string, string>>({});
	const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

	const load = useCallback(async () => {
		try {
			const res = await fetch("/api/models");
			const data = await res.json();
			setDefaultModel(data.default ?? "");
			setModels(data.models ?? {});
		} catch {}
	}, []);

	useEffect(() => {
		void load();
	}, [load]);

	const handleChange = (key: string, value: string) => {
		setModels((prev) => ({ ...prev, [key]: value }));
		setStatus("idle");
	};

	const handleSave = async () => {
		setStatus("saving");
		try {
			const cleaned: Record<string, string> = {};
			for (const { key } of AGENTS) {
				const v = (models[key] ?? "").trim();
				if (v) cleaned[key] = v;
			}
			await fetch("/api/models", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ models: cleaned }),
			});
			setStatus("saved");
			setTimeout(() => setStatus("idle"), 2500);
		} catch {
			setStatus("error");
		}
	};

	return (
		<div className={styles.page}>
			<div className={styles.title}>Настройки моделей</div>
			<div className={styles.subtitle}>
				Укажи модель Ollama для каждого агента. Если поле пустое — используется дефолтная
				модель сервера.
				<br />
				Изменения применяются при следующем запуске задачи (перезапуск сервера не нужен).{" "}
				<a
					href="https://ollama.com/search"
					target="_blank"
					rel="noreferrer"
					className={styles.link}
				>
					Каталог моделей Ollama →
				</a>
			</div>

			<div className={styles.section}>
				<div className={styles.sectionHeader}>Модели агентов</div>
				{AGENTS.map(({ key, name, hint }) => (
					<div key={key} className={styles.row}>
						<div className={styles.rowLabel}>
							<div className={styles.rowName}>{name}</div>
							<div className={styles.rowHint}>{hint}</div>
						</div>
						<input
							className={styles.input}
							value={models[key] ?? ""}
							onChange={(e) => handleChange(key, e.target.value)}
							placeholder={`по умолчанию: ${defaultModel}`}
							spellCheck={false}
						/>
						<span
							className={`${styles.defaultBadge} ${models[key] ? styles.hidden : ""}`}
						>
							default
						</span>
					</div>
				))}
			</div>

			<div className={styles.footer}>
				<button
					className={styles.saveBtn}
					onClick={handleSave}
					disabled={status === "saving"}
				>
					{status === "saving" ? "Сохраняю..." : "Сохранить"}
				</button>
				{status === "saved" && <span className={styles.savedMsg}>✓ Сохранено</span>}
				{status === "error" && <span className={styles.errorMsg}>Ошибка сохранения</span>}
			</div>
		</div>
	);
}
