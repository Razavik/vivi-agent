import { useState, useEffect } from "react";
import { Select } from "../../components/Select/Select";
import styles from "./SettingsPage.module.css";

interface AgentCfg {
	display_name?: string;
}

interface UserProfile {
	name: string;
	role: string;
	preferences: string;
	context: string;
}

export function SettingsPage() {
	const [defaultModel, setDefaultModel] = useState("");
	const [models, setModels] = useState<Record<string, string>>({});
	const [agents, setAgents] = useState<{ key: string; name: string }[]>([]);
	const [availableModels, setAvailableModels] = useState<string[]>([]);
	const [downloadedModels, setDownloadedModels] = useState<string[]>([]);
	const [modelsLoadError, setModelsLoadError] = useState("");
	const [profile, setProfile] = useState<UserProfile>({
		name: "",
		role: "",
		preferences: "",
		context: "",
	});

	useEffect(() => {
		const load = async () => {
			try {
				const [modelsRes, agentsRes, availRes, ollamaRes, profileRes] = await Promise.all([
					fetch("/api/models"),
					fetch("/api/agents-config"),
					fetch("/api/available-models"),
					fetch("/api/ollama-models"),
					fetch("/api/user-profile"),
				]);
				const modelsData = await modelsRes.json();
				const agentsData = await agentsRes.json();
				const availData = await availRes.json();
				const ollamaData = await ollamaRes.json();
				const profileData = await profileRes.json();

				setDefaultModel(modelsData.default ?? "");
				setModels(modelsData.models ?? {});

				if (agentsData.config) {
					const list = Object.entries(agentsData.config as Record<string, AgentCfg>).map(
						([key, cfg]) => ({ key, name: cfg.display_name || key }),
					);
					setAgents(list);
				}

				if (availData.models) setAvailableModels(availData.models);
				if (ollamaData.models) setDownloadedModels(ollamaData.models);
				if (ollamaData.error) setModelsLoadError(ollamaData.error);
				if (profileData.profile) setProfile(profileData.profile);
			} catch {}
		};
		void load();
	}, []);

	const handleChange = (key: string, value: string) => {
		const updated = { ...models, [key]: value };
		setModels(updated);
		fetch("/api/models", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ models: updated }),
		}).catch((e) => console.error("Ошибка сохранения модели:", e));
	};

	const handleProfileChange = (field: keyof UserProfile, value: string) => {
		const updated = { ...profile, [field]: value };
		setProfile(updated);
		fetch("/api/user-profile", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ profile: updated }),
		}).catch((e) => console.error("Ошибка сохранения профиля:", e));
	};

	const downloadedSet = new Set(downloadedModels);
	const allModels = Array.from(
		new Set(
			[
				...downloadedModels,
				...availableModels,
				...Object.values(models).filter(Boolean),
				defaultModel,
			].filter(Boolean),
		),
	);
	const selectOptions = [
		{ value: "", label: `по умолчанию (${defaultModel})` },
		...allModels.map((m) => ({
			value: m,
			label: downloadedSet.has(m) ? `${m} · скачана` : m,
			dot: downloadedSet.has(m) ? "#22c55e" : undefined,
		})),
	];

	return (
		<div className={styles.page}>
			<div className={styles.title}>Настройки моделей</div>
			<div className={styles.subtitle}>
				Выбери модель для каждого агента. Если не выбрана — используется глобальная модель
				сервера ({defaultModel}).
				<br />
				Изменения применяются при следующем запуске задачи.
				{downloadedModels.length > 0 && (
					<span className={styles.modelHint}>Скачанные Ollama-модели: {downloadedModels.length}</span>
				)}
				{modelsLoadError && (
					<span className={styles.modelWarning}>Не удалось получить модели Ollama: {modelsLoadError}</span>
				)}
			</div>

			<div className={styles.section}>
				<div className={styles.sectionHeader}>Модели агентов</div>
				{agents.map(({ key, name }) => (
					<div key={key} className={styles.row}>
						<div className={styles.rowLabel}>
							<div className={styles.rowName}>{name}</div>
							<div className={styles.rowHint}>{key}</div>
						</div>
						<Select
							value={models[key] ?? ""}
							onChange={(v) => handleChange(key, v)}
							options={selectOptions}
							className={styles.modelSelectControl}
						/>
					</div>
				))}
			</div>

			<div className={styles.section}>
				<div className={styles.sectionHeader}>Профиль пользователя</div>
				<div className={styles.row}>
					<div className={styles.rowLabel}>
						<div className={styles.rowName}>Имя</div>
						<div className={styles.rowHint}>Как агент будет обращаться к тебе</div>
					</div>
					<input
						type="text"
						value={profile.name}
						onChange={(e) => handleProfileChange("name", e.target.value)}
						className={styles.input}
						placeholder="Пользователь"
					/>
				</div>
				<div className={styles.row}>
					<div className={styles.rowLabel}>
						<div className={styles.rowName}>Роль</div>
						<div className={styles.rowHint}>Твоя профессия или позиция</div>
					</div>
					<input
						type="text"
						value={profile.role}
						onChange={(e) => handleProfileChange("role", e.target.value)}
						className={styles.input}
						placeholder="Разработчик, менеджер и т.д."
					/>
				</div>
				<div className={styles.row}>
					<div className={styles.rowLabel}>
						<div className={styles.rowName}>Предпочтения</div>
						<div className={styles.rowHint}>Как ты предпочитаешь получать ответы</div>
					</div>
					<textarea
						value={profile.preferences}
						onChange={(e) => handleProfileChange("preferences", e.target.value)}
						className={styles.textarea}
						placeholder="Например: краткие ответы, технические детали без воды..."
					/>
				</div>
				<div className={styles.row}>
					<div className={styles.rowLabel}>
						<div className={styles.rowName}>Контекст</div>
						<div className={styles.rowHint}>Дополнительная информация о тебе</div>
					</div>
					<textarea
						value={profile.context}
						onChange={(e) => handleProfileChange("context", e.target.value)}
						className={styles.textarea}
						placeholder="Проекты, технологии, которые ты используешь..."
					/>
				</div>
			</div>
		</div>
	);
}
