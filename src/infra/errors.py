class AgentError(Exception):
    pass


class ValidationError(AgentError):
    pass


class PolicyError(AgentError):
    pass


class ToolExecutionError(AgentError):
    pass


class LLMResponseError(AgentError):
    pass
