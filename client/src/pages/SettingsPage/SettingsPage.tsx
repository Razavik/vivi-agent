import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Select } from "../../components/Select/Select";
import styles from "./SettingsPage.module.css";
import { fetchJson } from "../../utils/http";

interface AgentCfg { display_name?: string; enabled?: boolean }
interface UserProfile { name: string; role: string; preferences: string; context: string }
interface SettingsPageProps {
	pcControlMode: boolean;
	showMonitor: boolean;
	onPcControlModeChange: (enabled: boolean) => void;
	onShowMonitorChange: (enabled: boolean) => void;
}
const EMPTY_PROFILE: UserProfile = { name: "", role: "", preferences: "", context: "" };

export function SettingsPage({ pcControlMode, showMonitor, onPcControlModeChange, onShowMonitorChange }: SettingsPageProps) {
	const [models, setModels] = useState<Record<string, string>>({});
	const [agentsConfig, setAgentsConfig] = useState<Record<string, AgentCfg>>({});
	const [profile, setProfile] = useState<UserProfile>(EMPTY_PROFILE);
	const [modelsEdited, setModelsEdited] = useState(false);
	const [agentsEdited, setAgentsEdited] = useState(false);
	const [profileEdited, setProfileEdited] = useState(false);

	const { data } = useQuery({
		queryKey: ["settings"],
		queryFn: async () => {
			const [modelsData, agentsData, availData, ollamaData, profileData] = await Promise.all([
				fetchJson<{ models?: Record<string, string>; default?: string; custom_models?: string[]; disabled_models?: string[] }>("/api/models", { models: {}, default: "", custom_models: [], disabled_models: [] }),
				fetchJson<{ config?: Record<string, AgentCfg> }>("/api/agents-config", { config: {} }),
				fetchJson<{ models?: string[] }>("/api/available-models", { models: [] }),
				fetchJson<{ models?: string[]; error?: string }>("/api/ollama-models", { models: [] }),
				fetchJson<{ profile?: UserProfile }>("/api/user-profile", {}),
			]);
			return { modelsData, agentsData, availData, ollamaData, profileData };
		},
	});

	const saveModels = useMutation({
		mutationFn: (updated: Record<string, string>) => fetchJson("/api/models", null, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ models: updated, custom_models: data?.modelsData.custom_models ?? [], disabled_models: data?.modelsData.disabled_models ?? [] }) }),
	});
	const saveAgents = useMutation({
		mutationFn: (updated: Record<string, AgentCfg>) => fetchJson("/api/agents-config", null, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config: updated }) }),
	});
	const saveProfile = useMutation({
		mutationFn: (updated: UserProfile) => fetchJson("/api/user-profile", null, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile: updated }) }),
	});

	const defaultModel = data?.modelsData.default ?? "";
	const effectiveModels = modelsEdited ? models : (data?.modelsData.models ?? {});
	const effectiveAgentsConfig = agentsEdited ? agentsConfig : (data?.agentsData.config ?? {});
	const effectiveProfile = profileEdited ? profile : (data?.profileData.profile ?? EMPTY_PROFILE);
	const agents = Object.entries(effectiveAgentsConfig).map(([key, cfg]) => ({ key, name: cfg.display_name || key, enabled: key === "operator" ? true : cfg.enabled !== false })).filter((a) => (pcControlMode ? a.key === "operator" : true));
	const downloadedModels = data?.ollamaData.models ?? [];
	const customModels = data?.modelsData.custom_models ?? [];
	const availableModels = data?.availData.models ?? [];
	const disabledModels = new Set(data?.modelsData.disabled_models ?? []);
	const assignedModelValues = new Set(Object.values(effectiveModels).filter(Boolean));
	const downloadedSet = new Set(downloadedModels);
	const allModels = Array.from(new Set([...downloadedModels, ...availableModels, ...customModels, ...assignedModelValues, defaultModel].filter(Boolean)))
		.filter((m) => !disabledModels.has(m) || assignedModelValues.has(m));
	const selectOptions = [{ value: "", label: `по умолчанию (${defaultModel})` }, ...allModels.map((m) => ({ value: m, label: downloadedSet.has(m) ? `${m} · скачана` : m, dot: downloadedSet.has(m) ? "#c084fc" : undefined }))];

	const handleChange = (key: string, value: string) => { const updated = { ...effectiveModels, [key]: value }; setModelsEdited(true); setModels(updated); saveModels.mutate(updated); };
	const handleAgentEnabledChange = (key: string, enabled: boolean) => { if (key === "operator") return; const updated = { ...effectiveAgentsConfig, [key]: { ...effectiveAgentsConfig[key], enabled } }; setAgentsEdited(true); setAgentsConfig(updated); saveAgents.mutate(updated); };
	const handleProfileChange = (field: keyof UserProfile, value: string) => { const updated = { ...effectiveProfile, [field]: value }; setProfileEdited(true); setProfile(updated); saveProfile.mutate(updated); };

	return (
		<div className={styles.page}>
			<div className={styles.section}>
				<div className={styles.sectionHeader}>Интерфейс</div>
				<div className={styles.row}>
					<div className={styles.rowLabel}><div className={styles.rowName}>Режим управления ПК</div><div className={styles.rowHint}>Только оператор + ПК-инструменты, без саб-агентов</div></div>
					<label className={styles.switchControl}><input type="checkbox" checked={pcControlMode} onChange={(e) => onPcControlModeChange(e.target.checked)} /><span className={styles.switchTrack}><span className={styles.switchThumb} /></span></label>
				</div>
				<div className={styles.row}>
					<div className={styles.rowLabel}><div className={styles.rowName}>Показывать монитор</div><div className={styles.rowHint}>Плавающее окно поверх всех окон во время работы агента</div></div>
					<label className={styles.switchControl}><input type="checkbox" checked={showMonitor} onChange={(e) => onShowMonitorChange(e.target.checked)} /><span className={styles.switchTrack}><span className={styles.switchThumb} /></span></label>
				</div>
			</div>

			<div className={styles.section}>
				<div className={styles.sectionHeader}>Модели агентов</div>
				{agents.map(({ key, name, enabled }) => (
					<div key={key} className={styles.row}>
						<div className={styles.rowLabel}><div className={styles.rowName}>{name}</div><div className={styles.rowHint}>{key}</div></div>
						<Select value={effectiveModels[key] ?? ""} onChange={(value) => handleChange(key, value)} options={selectOptions} className={styles.modelSelectControl} />
						<label className={styles.switchControl}><input type="checkbox" checked={enabled} disabled={key === "operator"} onChange={(e) => handleAgentEnabledChange(key, e.target.checked)} /><span className={styles.switchTrack}><span className={styles.switchThumb} /></span></label>
					</div>
				))}
			</div>

			<div className={styles.section}>
				<div className={styles.sectionHeader}>Профиль</div>
				<div className={styles.row}><div className={styles.rowLabel}><div className={styles.rowName}>Имя</div></div><input type="text" value={effectiveProfile.name} onChange={(e) => handleProfileChange("name", e.target.value)} className={styles.input} /></div>
				<div className={styles.row}><div className={styles.rowLabel}><div className={styles.rowName}>Роль</div></div><input type="text" value={effectiveProfile.role} onChange={(e) => handleProfileChange("role", e.target.value)} className={styles.input} /></div>
				<div className={styles.row}><div className={styles.rowLabel}><div className={styles.rowName}>Предпочтения</div></div><textarea value={effectiveProfile.preferences} onChange={(e) => handleProfileChange("preferences", e.target.value)} className={styles.textarea} /></div>
				<div className={styles.row}><div className={styles.rowLabel}><div className={styles.rowName}>Контекст</div></div><textarea value={effectiveProfile.context} onChange={(e) => handleProfileChange("context", e.target.value)} className={styles.textarea} /></div>
			</div>
		</div>
	);
}
