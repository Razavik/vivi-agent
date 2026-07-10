export async function readJson<T>(response: Response, fallback: T): Promise<T> {
	if (!response.ok) {
		return fallback;
	}
	const text = await response.text();
	if (!text.trim()) {
		return fallback;
	}
	try {
		return JSON.parse(text) as T;
	} catch {
		return fallback;
	}
}

export async function fetchJson<T>(url: string, fallback: T, init?: RequestInit): Promise<T> {
	try {
		const response = await fetch(url, init);
		return await readJson(response, fallback);
	} catch {
		return fallback;
	}
}
