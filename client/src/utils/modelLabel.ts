// Форматирование "сырых" строк модели (как они хранятся в data/models.json)
// в человекочитаемый вид — используется и в OperatorSettingsSelect (чип,
// список выбора), и в Composer (предупреждение про vision), чтобы
// пользователь видел одно и то же название модели везде.

export interface ModelOption {
	value: string;
	label: string;
}

// Модели Codex приходят в списке как плоские строки вида
// "codex:gpt-5.6-terra[medium]" — база + уровень reasoning-effort в скобках.
export const CODEX_MODEL_RE = /^codex:([^[]+)\[(\w+)\]$/;
export const CODEX_BASE_LABELS: Record<string, string> = {
	"gpt-5.4-mini": "GPT-5.4 mini",
	"gpt-5.4": "GPT-5.4",
	"gpt-5.5": "GPT-5.5",
	"gpt-5.6-terra": "GPT-5.6 Terra",
	"gpt-5.6-luna": "GPT-5.6 Luna",
};
// Не все базовые модели поддерживают все уровни — например у gpt-5.6-terra
// их 6 (включая max/ultra), у большинства остальных — 4 (по xhigh).
export const CODEX_EFFORT_LABELS: Record<string, string> = {
	low: "Низкий",
	medium: "Средний",
	high: "Высокий",
	xhigh: "Экстра",
	max: "Максимум",
	ultra: "Ультра",
};
export const CODEX_EFFORT_ORDER = [
	"low",
	"medium",
	"high",
	"xhigh",
	"max",
	"ultra",
];
// Замерено эмпирически через ACP session/update -> usage_update.size —
// одинаково для всех моделей на аккаунте (см. src/llm/codex_acp_client.py,
// DEFAULT_CODEX_NUM_CTX). Не завязано на цену — цену через ChatGPT-подписку
// не показываем, платится не потокенно.
export const CODEX_CONTEXT_LABEL = "~258K токенов контекста";

export function parseCodexModel(
	value: string,
): { base: string; effort: string } | null {
	const match = CODEX_MODEL_RE.exec(value);
	return match ? { base: match[1], effort: match[2] } : null;
}

export function formatCodexLabel(base: string, effort: string): string {
	const baseLabel = CODEX_BASE_LABELS[base] ?? base;
	const effortLabel = CODEX_EFFORT_LABELS[effort] ?? effort;
	return `${baseLabel} · ${effortLabel}`;
}

// Бесплатные модели самого OpenCode (не через чужой провайдерский аккаунт) —
// "opencode:opencode/deepseek-v4-flash-free" и т.п.
export const OPENCODE_MODEL_PREFIX = "opencode:opencode/";
export const OPENCODE_MODEL_LABELS: Record<string, string> = {
	"big-pickle": "Big Pickle",
	"deepseek-v4-flash-free": "DeepSeek v4 Flash",
	"hy3-free": "Hunyuan 3",
	"mimo-v2.5-free": "MiMo v2.5",
	"nemotron-3-ultra-free": "Nemotron 3 Ultra",
	"north-mini-code-free": "North mini (code)",
};

export function isOpenCodeFreeModel(value: string): boolean {
	return value.startsWith(OPENCODE_MODEL_PREFIX);
}

export function formatOpenCodeLabel(value: string): string {
	const id = value.slice(OPENCODE_MODEL_PREFIX.length);
	return OPENCODE_MODEL_LABELS[id] ?? id;
}

/** Единая точка форматирования — ровно то же, что видно в чипе селекта. */
export function formatModelLabel(
	model: string,
	modelOptions: ModelOption[] = [],
): string {
	const codex = parseCodexModel(model);
	if (codex) return formatCodexLabel(codex.base, codex.effort);
	if (isOpenCodeFreeModel(model)) return formatOpenCodeLabel(model);
	return (
		modelOptions.find((opt) => opt.value === model)?.label || model || ""
	);
}
