class EmptyToolCallBlockException(Exception):
  """Exception raised when <tool_calls></tool_calls> does not contain any tool calls"""
  pass

class LLMQueryRetryLimitExceeded(Exception):
  """Exception raised when LLM query POST request fails over QUERY_LLM_MAX_RETRIES times"""
  pass