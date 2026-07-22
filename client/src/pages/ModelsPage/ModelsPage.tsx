import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchJson } from "../../utils/http";
import {
	CODEX_BASE_LABELS,
	formatOpenCodeLabel,
	isOpenCodeFreeModel,
	parseCodexModel,
} from "../../utils/modelLabel";
import styles from "./ModelsPage.module.css";

interface ModelsResponse {
	default?: string;
	models?: Record<string, string>;
	custom_models?: string[];
	disabled_models?: string[];
}

interface ModelsSavePayload {
	models: Record<string, string>;
	custom_models: string[];
	disabled_models: string[];
}

interface ModelEntry {
	key: string;
	label: string;
	rawIds: string[];
	meta: string;
	enabled: boolean;
}

interface ProviderGroup {
	id: string;
	title: string;
	entries: ModelEntry[];
}

export function ModelsPage() {
	const queryClient = useQueryClient();
	const [newModelName, setNewModelName] = useState("");

	const { data, isLoading } = useQuery({
		queryKey: ["models-page"],
		queryFn: async () => {
			const [modelsData, availableData, ollamaData] = await Promise.all([
				fetchJson<ModelsResponse>("/api/models", {
					default: "",
					models: {},
					custom_models: [],
					disabled_models: [],
				}),
				fetchJson<{ models?: string[] }>("/api/available-models", { models: [] }),
				fetchJson<{ models?: string[]; error?: string }>("/api/ollama-models", { models: [] }),
			]);
			return { modelsData, availableData, ollamaData };
		},
	});

	const saveModels = useMutation({
		mutationFn: (payload: ModelsSavePayload) =>
			fetchJson<unknown>("/api/models", null, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(payload),
			}),
		onSuccess: () => {
			void queryClient.invalidateQueries({ queryKey: ["models-page"] });
			void queryClient.invalidateQueries({ queryKey: ["settings"] });
			void queryClient.invalidateQueries({ queryKey: ["tools-page"] });
		},
	});

	const assignedModels = useMemo(() => data?.modelsData.models ?? {}, [data?.modelsData.models]);
	const customModels = useMemo(
		() => data?.modelsData.custom_models ?? [],
		[data?.modelsData.custom_models],
	);
	const disabledModels = useMemo(
		() => data?.modelsData.disabled_models ?? [],
		[data?.modelsData.disabled_models],
	);
	const downloadedModels = useMemo(() => data?.ollamaData.models ?? [], [data?.ollamaData.models]);
	const availableModels = useMemo(
		() => data?.availableData.models ?? [],
		[data?.availableData.models],
	);
	const downloadedSet = useMemo(() => new Set(downloadedModels), [downloadedModels]);
	const assignedSet = useMemo(
		() => new Set(Object.values(assignedModels).filter(Boolean)),
		[assignedModels],
	);
	const disabledSet = useMemo(() => new Set(disabledModels), [disabledModels]);

	const allKnownModels = useMemo(
		() =>
			Array.from(
				new Set([
					...customModels,
					...downloadedModels,
					...availableModels,
					...Object.values(assignedModels).filter(Boolean),
				]),
			),
		[assignedModels, availableModels, customModels, downloadedModels],
	);

	// Разбиваем по провайдерам (Ollama / OpenAI Codex / OpenCode) и внутри
	// Codex схлопываем эффорт-варианты одной базовой модели в одну строку —
	// отключать/включать имеет смысл модель целиком, а не по уровню мышления.
	const providerGroups = useMemo<ProviderGroup[]>(() => {
		const codexRawIds = new Map<string, string[]>();
		const ollama: ModelEntry[] = [];
		const codex: ModelEntry[] = [];
		const opencode: ModelEntry[] = [];

		for (const modelName of allKnownModels) {
			const parsed = parseCodexModel(modelName);
			if (parsed) {
				const ids = codexRawIds.get(parsed.base) ?? [];
				ids.push(modelName);
				codexRawIds.set(parsed.base, ids);
			}
		}

		const metaFor = (rawIds: string[], isCustomEntry: boolean): string => {
			if (rawIds.some((id) => downloadedSet.has(id))) return "Скачана в Ollama";
			if (isCustomEntry) return "Добавлена вручную";
			if (rawIds.some((id) => assignedSet.has(id))) return "Используется агентами";
			return "Из общего списка";
		};

		for (const [base, rawIds] of codexRawIds) {
			codex.push({
				key: base,
				label: CODEX_BASE_LABELS[base] ?? base,
				rawIds,
				meta: metaFor(rawIds, false),
				enabled: rawIds.some((id) => !disabledSet.has(id)),
			});
		}

		for (const modelName of allKnownModels) {
			if (parseCodexModel(modelName)) continue;
			const rawIds = [modelName];
			if (isOpenCodeFreeModel(modelName)) {
				opencode.push({
					key: modelName,
					label: formatOpenCodeLabel(modelName),
					rawIds,
					meta: metaFor(rawIds, false),
					enabled: !disabledSet.has(modelName),
				});
			} else {
				ollama.push({
					key: modelName,
					label: modelName,
					rawIds,
					meta: metaFor(rawIds, customModels.includes(modelName)),
					enabled: !disabledSet.has(modelName),
				});
			}
		}

		const codexOrder = Object.keys(CODEX_BASE_LABELS);
		codex.sort((a, b) => codexOrder.indexOf(a.key) - codexOrder.indexOf(b.key));

		return [
			{ id: "ollama", title: "Ollama", entries: ollama },
			{ id: "codex", title: "OpenAI (Codex)", entries: codex },
			{ id: "opencode", title: "OpenCode", entries: opencode },
		].filter((group) => group.entries.length > 0);
	}, [allKnownModels, assignedSet, customModels, disabledSet, downloadedSet]);

	const toggleModelEnabled = (rawIds: string[], nextEnabled: boolean) => {
		const nextDisabled = new Set(disabledModels);
		for (const id of rawIds) {
			if (nextEnabled) nextDisabled.delete(id);
			else nextDisabled.add(id);
		}
		saveModels.mutate({
			models: assignedModels,
			custom_models: customModels,
			disabled_models: Array.from(nextDisabled),
		});
	};

	const addCustomModel = () => {
		const value = newModelName.trim();
		if (!value) return;
		if (customModels.includes(value)) {
			setNewModelName("");
			return;
		}
		saveModels.mutate({
			models: assignedModels,
			custom_models: [...customModels, value],
			disabled_models: disabledModels,
		});
		setNewModelName("");
	};

	const removeCustomModel = (name: string) => {
		saveModels.mutate({
			models: assignedModels,
			custom_models: customModels.filter((item) => item !== name),
			disabled_models: disabledModels,
		});
	};

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<h1 className={styles.title}>Модели</h1>
				<p className={styles.subtitle}>
					Добавляй свои названия моделей в клиент и включай/отключай модели по провайдерам.
					Отключённые модели пропадают из списков выбора для агентов.
				</p>
			</div>

			<div className={styles.section}>
				<div className={styles.sectionHeader}>Добавить модель</div>
				<div className={styles.addRow}>
					<input
						type="text"
						value={newModelName}
						onChange={(e) => setNewModelName(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter") {
								e.preventDefault();
								addCustomModel();
							}
						}}
						className={styles.input}
						placeholder="qwen2.5:14b, gemma4:27b, my-local-model"
					/>
					<button
						type="button"
						className={styles.primaryButton}
						onClick={addCustomModel}
						disabled={!newModelName.trim() || saveModels.isPending}
					>
						Добавить
					</button>
				</div>
			</div>

			<div className={styles.section}>
				<div className={styles.sectionHeader}>Пользовательские модели</div>
				{customModels.length === 0 ? (
					<div className={styles.empty}>Пока ничего не добавлено</div>
				) : (
					<div className={styles.list}>
						{customModels.map((modelName) => (
							<div key={modelName} className={styles.item}>
								<div className={styles.itemMain}>
									<div className={styles.itemTitle}>{modelName}</div>
									<div className={styles.itemMeta}>
										{assignedSet.has(modelName) ? "Используется агентами" : "Доступна для выбора"}
									</div>
								</div>
								<button
									type="button"
									className={styles.ghostButton}
									onClick={() => removeCustomModel(modelName)}
								>
									Удалить
								</button>
							</div>
						))}
					</div>
				)}
			</div>

			{isLoading ? (
				<div className={styles.section}>
					<div className={styles.empty}>Загрузка...</div>
				</div>
			) : providerGroups.length === 0 ? (
				<div className={styles.section}>
					<div className={styles.empty}>Список моделей пуст</div>
				</div>
			) : (
				<div className={styles.grid}>
					{providerGroups.map((group) => (
						<div key={group.id} className={styles.section}>
							<div className={styles.sectionHeader}>{group.title}</div>
							<div className={styles.list}>
								{group.entries.map((entry) => (
									<div key={entry.key} className={styles.item}>
										<div className={styles.itemMain}>
											<div className={styles.itemTitle}>{entry.label}</div>
											<div className={styles.itemMeta}>{entry.meta}</div>
										</div>
										<label className={styles.switchControl}>
											<input
												type="checkbox"
												checked={entry.enabled}
												onChange={(e) => toggleModelEnabled(entry.rawIds, e.target.checked)}
											/>
											<span className={styles.switchTrack}>
												<span className={styles.switchThumb} />
											</span>
										</label>
									</div>
								))}
							</div>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
