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

export type SubAgentStatus = "idle" | "running" | "done" | "error";

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
	name: string;
	displayName: string;
	task: string;
	status: SubAgentStatus;
	steps: SubAgentStep[];
	question?: string;
	answer?: string;
	result?: string;
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
