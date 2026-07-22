import { QueryClient } from "@tanstack/react-query";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";

// gcTime должен быть не меньше maxAge персистера в main.tsx, иначе React Query
// выкинет запись из кэша раньше, чем успеет её сохранить в localStorage.
const PERSIST_MAX_AGE = 24 * 60 * 60 * 1000;

export const queryClient = new QueryClient({
	defaultOptions: {
		queries: {
			refetchOnWindowFocus: false,
			retry: 1,
			staleTime: 5_000,
			gcTime: PERSIST_MAX_AGE,
		},
		mutations: {
			retry: 0,
		},
	},
});

export const queryPersister = createSyncStoragePersister({
	storage: window.localStorage,
	key: "agent1-query-cache",
});

export { PERSIST_MAX_AGE };
