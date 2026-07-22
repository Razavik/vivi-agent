// Прогревает кэш React Query для ВСЕХ страниц сразу при старте приложения —
// без этого каждая страница (Модели/Настройки/Инструменты/Скиллы/...) грузила
// свои данные только при первом заходе, и при переключении между страницами
// было видно, как они "подгружаются" с нуля. Ключи и fetch-запросы здесь
// продублированы 1-в-1 с queryFn соответствующих страниц — React Query кэш
// общий (queryClient один на всё приложение), поэтому если ключ уже прогрет
// и не protected (staleTime не истёк), страница при монтировании использует
// уже готовые данные вместо повторного запроса и лоадера.
import { queryClient } from "./queryClient";
import { fetchJson } from "./utils/http";

export function prefetchAllPages(): void {
	void queryClient.prefetchQuery({
		queryKey: ["models-page"],
		queryFn: async () => {
			const [modelsData, availableData, ollamaData] = await Promise.all([
				fetchJson("/api/models", {
					default: "",
					models: {} as Record<string, string>,
					custom_models: [] as string[],
					disabled_models: [] as string[],
				}),
				fetchJson("/api/available-models", { models: [] as string[] }),
				fetchJson("/api/ollama-models", {
					models: [] as string[],
					error: undefined as string | undefined,
				}),
			]);
			return { modelsData, availableData, ollamaData };
		},
	});

	void queryClient.prefetchQuery({
		queryKey: ["settings"],
		queryFn: async () => {
			const [modelsData, agentsData, availData, ollamaData, profileData] =
				await Promise.all([
					fetchJson("/api/models", {
						models: {} as Record<string, string>,
						default: "",
						custom_models: [] as string[],
						disabled_models: [] as string[],
					}),
					fetchJson("/api/agents-config", { config: {} as Record<string, unknown> }),
					fetchJson("/api/available-models", { models: [] as string[] }),
					fetchJson("/api/ollama-models", {
						models: [] as string[],
						error: undefined as string | undefined,
					}),
					fetchJson("/api/user-profile", {} as Record<string, unknown>),
				]);
			return { modelsData, agentsData, availData, ollamaData, profileData };
		},
	});

	void queryClient.prefetchQuery({
		queryKey: ["tools-page"],
		queryFn: async () => {
			const [agentsData, modelsData, availData, ollamaData, appSettings] =
				await Promise.all([
					fetchJson("/api/agents-config", { config: {} as Record<string, unknown> }),
					fetchJson("/api/models", {
						models: {} as Record<string, string>,
						default: "",
						custom_models: [] as string[],
						disabled_models: [] as string[],
					}),
					fetchJson("/api/available-models", { models: [] as string[] }),
					fetchJson("/api/ollama-models", { models: [] as string[] }),
					fetchJson("/api/app-settings", { pc_control_mode: false }),
				]);
			return { agentsData, modelsData, availData, ollamaData, appSettings };
		},
	});

	void queryClient.prefetchQuery({
		queryKey: ["operator-skills"],
		queryFn: () =>
			fetchJson("/api/operator-skills", {
				skills: [] as unknown[],
				market: [] as unknown[],
			}),
	});
}
