export function normalizeAssistantText(text: string): string {
	return text
		.replace(/\$\\to\$/g, "→")
		.replace(/\$\\rightarrow\$/g, "→")
		.replace(/\\to/g, "→")
		.replace(/\\rightarrow/g, "→");
}

export interface ExtractedMarkdownImages {
	text: string;
	images: string[];
}

const MARKDOWN_IMAGE_RE = /!\[[^\]]*\]\(([^)\s]+)[^)]*\)/g;

/**
 * Вырезает markdown-картинки (![alt](url)) из текста и собирает их URL отдельно —
 * чтобы отрисовать сеткой маленьких превью с раскрытием по клику, а не как
 * полноразмерные блоки прямо внутри текста ответа.
 */
export function extractMarkdownImages(text: string): ExtractedMarkdownImages {
	const images: string[] = [];
	const stripped = text.replace(MARKDOWN_IMAGE_RE, (_match, url: string) => {
		images.push(url);
		return "";
	});
	// убираем повисшие пустые строки, оставшиеся после вырезанных строк-картинок
	const cleaned = stripped.replace(/\n{3,}/g, "\n\n").trim();
	return { text: cleaned, images };
}
