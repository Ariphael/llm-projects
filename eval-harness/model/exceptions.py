class LLMQueryRetryLimitExceeded(Exception):
  """Exception raised when LLM query POST request fails over QUERY_LLM_MAX_RETRIES times"""
  pass

class LLMQueryClientError(Exception):
  """Exception raised when an LLM query POST request returns status code 4xx. Not raised when status code is 429 (Timeout)"""
  pass