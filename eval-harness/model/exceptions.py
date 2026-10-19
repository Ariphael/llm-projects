class LLMQueryRetryLimitExceeded(Exception):
  """Exception raised when LLM query POST request fails over QUERY_LLM_MAX_RETRIES times"""
  pass

class LLMQueryClientError(Exception):
  """Exception raised when an LLM query POST request returns status code 4xx. Not raised when status code is 429 (Timeout)"""
  pass

class LLMNoContentGenerated(Exception):
  """Exception raised when the LLM does not generate any content"""
  pass

class JudgePromptJSONOmissionError(Exception):
  """Exception raised when the JSON body is missing at the end of an answer-type response"""
  pass

class JudgePromptJSONParseError(Exception):
  """Exception raised when the judge prompt generator cannot parse the JSON at the end of an answer-type response"""
  pass

class UnknownResponseType(Exception):
  """Exception raised when the 'responseType' field of a dataset item is not one of 'start'|'skip'|'answer'|'hint'"""
  pass