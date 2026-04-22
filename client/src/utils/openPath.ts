const WIN_PATH_RE = /^[A-Za-z]:\\[\\\S|*\S]?.*$/;

export function isWindowsPath(str: string): boolean {
	return WIN_PATH_RE.test(str.trim());
}

export async function openPath(path: string): Promise<void> {
	await fetch("/api/open-path", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ path }),
	});
}
