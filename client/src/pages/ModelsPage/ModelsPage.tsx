import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchJson } from "../../utils/http";
import styles from "./ModelsPage.module.css";

interface ModelsResponse {
	default?: string;
	models?: Record<string, string>;
	custom_models?: string[];
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
				}),
				fetchJson<{ models?: string[] }>("/api/available-models", { models: [] }),
				fetchJson<{ models?: string[]; error?: string }>("/api/ollama-models", { models: [] }),
			]);
			return { modelsData, availableData, ollamaData };
		},
	});

	const saveModels = useMutation({
		mutationFn: (payload: { models: Record<string, string>; custom_models: string[] }) =>
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
		});
		setNewModelName("");
	};

	const removeCustomModel = (name: string) => {
		saveModels.mutate({
			models: assignedModels,
			custom_models: customModels.filter((item) => item !== name),
		});
	};

	return (
		<div className={styles.page}>
			<div className={styles.header}>
				<h1 className={styles.title}>Модели</h1>
				<p className={styles.subtitle}>
					Добавляй свои названия моделей в клиент. После сохранения они появятся в списках выбора
					для агентов.
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

			<div className={styles.grid}>
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

				<div className={styles.section}>
					<div className={styles.sectionHeader}>Обнаруженные модели</div>
					{isLoading ? (
						<div className={styles.empty}>Загрузка...</div>
					) : allKnownModels.length === 0 ? (
						<div className={styles.empty}>Список моделей пуст</div>
					) : (
						<div className={styles.list}>
							{allKnownModels.map((modelName) => (
								<div key={modelName} className={styles.item}>
									<div className={styles.itemMain}>
										<div className={styles.itemTitle}>{modelName}</div>
										<div className={styles.itemMeta}>
											{downloadedSet.has(modelName)
												? "Есть в Ollama"
												: customModels.includes(modelName)
													? "Добавлена вручную"
													: "Из общего списка"}
										</div>
									</div>
								</div>
							))}
						</div>
					)}
				</div>
			</div>
		</div>
	);
}
