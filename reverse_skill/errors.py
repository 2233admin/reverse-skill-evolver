class ReverseSkillError(Exception):
    """Base error carrying the public CLI exit code."""

    exit_code = 1


class EnvironmentUnavailable(ReverseSkillError):
    exit_code = 3


class McpError(ReverseSkillError):
    exit_code = 4


class McpTransportError(McpError):
    pass


class McpProtocolError(McpError):
    pass


class ToolOperationError(ReverseSkillError):
    exit_code = 5
