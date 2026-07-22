import { createRoot } from "react-dom/client";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.tsx";
import { queryClient, queryPersister, PERSIST_MAX_AGE } from "./queryClient";

createRoot(document.getElementById("root")!).render(
	<PersistQueryClientProvider
		client={queryClient}
		persistOptions={{ persister: queryPersister, maxAge: PERSIST_MAX_AGE }}
	>
		<BrowserRouter>
			<App />
		</BrowserRouter>
	</PersistQueryClientProvider>,
);
