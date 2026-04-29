export type ChatEventType = "message" | "thought" | "tool_result" | "tool_use";

export type PlanStatus = "pending" | "in_progress" | "completed";

export interface PlanItem {
	id: string;
	content: string;
	status: PlanStatus;
}

export interface ChatEvent {
	type: ChatEventType;
	role?: "user" | "assistant";
	content?: string;
	images?: string[];
	thought?: string;
	action?: string;
	result?: any;
	success?: boolean;
	step?: number;
	plan?: PlanItem[];
}

export type SubAgentStatus =
	| "idle"
	| "running"
	| "done"
	| "error"
	| "cancelled"
	| "paused"
	| "interrupted";

export interface SubAgentStep {
	step: number;
	thought?: string;
	action?: string;
	args?: any;
	result?: any;
	success?: boolean;
	streamLines?: string[];
}

export interface SubAgentSession {
	task: string;
	model: string;
	steps: SubAgentStep[];
	result?: string;
	plan?: PlanItem[];
}

export interface SubAgentPane {
	id: string;
	name: string;
	displayName: string;
	task: string;
	status: SubAgentStatus;
	steps: SubAgentStep[];
	question?: string;
	answer?: string;
	result?: string;
	errorMessage?: string;
	startedAt: number;
	model?: string;
	sessions?: SubAgentSession[];
	plan?: PlanItem[];
	contextTokens?: number;
}

export interface Tool {
	name: string;
	description: string;
	risk_level?: number;
	args_schema?: Record<string, string>;
	agent?: string;
}

export interface SSEEvent {
	event: string;
	payload: any;
}

export interface ConfirmationRequest {
	requestId: string;
	message: string;
	tool?: string;
	args?: Record<string, unknown>;
	step?: number;
}

export interface AgentState {
	events: ChatEvent[];
	tools: Tool[];
	isRunning: boolean;
	liveStatus: string;
}

export type SupervisorAlertType =
	| "hang_detected"
	| "stale_paused"
	| "waiting_timeout"
	| "deadlock_detected";

export interface SupervisorAlertPayload {
	type: SupervisorAlertType;
	run_id?: string;
	agent_name?: string;
	task?: string;
	idle_seconds?: number;
	message: string;
	step?: number;
	age_seconds?: number;
	cycles?: string[][];
}

export interface SupervisorAlert {
	event: string;
	payload: SupervisorAlertPayload;
	timestamp: number;
}

export type DiagnosticStatus = "pass" | "warn" | "fail" | "skip";
export type DiagnosticSeverity = "info" | "medium" | "high" | "critical";

export interface DiagnosticCheck {
	id: string;
	title: string;
	status: DiagnosticStatus;
	severity: DiagnosticSeverity;
	summary: string;
	action?: string;
	details?: Record<string, unknown>;
}

export interface DiagnosticsReport {
	generated_at: number;
	score: number;
	status: "healthy" | "attention" | "critical";
	counts: Record<DiagnosticStatus, number>;
	summary: string;
	checks: DiagnosticCheck[];
	facts: Record<string, unknown>;
}

export interface PreflightReport {
	allowed: boolean;
	status: "passed" | "blocked";
	summary: string;
	blocking: DiagnosticCheck[];
	warnings: DiagnosticCheck[];
	report: DiagnosticsReport;
	task?: string;
}

export interface PostRunReview {
	id: string;
	created_at: number;
	task: string;
	status: "clean" | "needs_attention";
	summary: string;
	result_error?: string;
	result_summary?: string;
	log_file?: string;
	diagnostics_score?: number;
	diagnostics_status?: string;
	preflight_status?: string;
	failed_checks: DiagnosticCheck[];
	warning_checks: DiagnosticCheck[];
}

export interface AgentScorecardItem {
	agent: string;
	total: number;
	finished: number;
	failed: number;
	cancelled: number;
	blocked: number;
	retries: number;
	interrupts: number;
	avg_steps: number;
	success_rate: number;
}

export interface MemoryInspectionItem {
	agent: string;
	display_name: string;
	file: string;
	exists: boolean;
	updated_at?: string;
	messages: number;
	assistant_messages: number;
	user_messages: number;
	actions: number;
	facts: string[];
	stale: boolean;
}

export interface TaskTemplate {
	id: string;
	title: string;
	prompt: string;
	quality_gates: string[];
}
