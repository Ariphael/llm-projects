class EmptyToolCallBlockException(Exception):
  """Exception raised when <tool_calls></tool_calls> does not contain any tool calls"""
  pass