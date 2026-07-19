import requests, json, os, re
from dotenv import load_dotenv

from prompts import systemPrompt
from tools import shell, fileWrite, fileRead, fetch
from validation import validateToolCallArgs
from exceptions import LLMQueryRetryLimitExceeded

load_dotenv()

apiKey = os.getenv("OPENROUTER_KEY")
model = os.getenv("MODEL")

VALID_TOOL_NAMES = ["fileRead", "fileWrite", "shell", "fetch"]
TOOL_CALLS_BLOCK_REGEX = r"\<tool_calls\>(.*)\<\/tool_calls\>"
TOOL_CALL_REGEX = r"\<tool_call\>(.*?)\<\/tool_call\>"
QUERY_LLM_MAX_RETRIES = 3

def queryLLM(messages: list[dict[str, any]]):
  attempt = 0

  while attempt < QUERY_LLM_MAX_RETRIES:
    try:
      response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
          "Authorization": f"Bearer {apiKey}",
          "Content-Type": "application/json",
        },
        data=json.dumps({
          "model": model,
          "messages": messages,
          "reasoning": {"enabled": True},
          "stop": ["</tool_calls>"]
        })
      )

      if not response.ok or 400 <= response.status_code <= 599:
        print(f"LLM Query POST request failed. Received status {response.status_code}")
        retries += 1
        continue

      response = response.json()
      return response["choices"][0]
    except requests.exceptions.RequestException as e:
      print(f"LLM Query request failed: {e}")
      raise e
  raise LLMQueryRetryLimitExceeded(f"LLM Query retry limit (={QUERY_LLM_MAX_RETRIES}) exceeded")


def parse(responseMsg: str):
  if responseMsg.endswith("</tool_calls>"):
    return []

  parsedCalls = []

  match = re.search(TOOL_CALLS_BLOCK_REGEX, responseMsg, re.DOTALL)
  if match is None:
    return []

  toolCalls = re.findall(TOOL_CALL_REGEX, match.group(1), re.DOTALL)
  for toolCall in toolCalls:
    try:
      argsErrorMsg = validateToolCallArgs(json.loads(toolCall))
      parsedCalls.append(
        { "error": argsErrorMsg } if argsErrorMsg != None else json.loads(toolCall)
      )
    except json.JSONDecodeError as e:
      parsedCalls.append({ "jsonError": str(e) })

  return parsedCalls


def getToolResultStr(toolResults: list[str]):
  results = "<tool_results>\n"
  for i, res in enumerate(toolResults):
    results += f"<tool_result id=\"{i}\">{res}</tool_result>\n"
  return results + "</tool_results>"


def agentLoop(initialMsg: str):
  messages = []

  # first api call with system prompt
  messages.extend([
    { "role": "system", "content": systemPrompt },
    { "role": "user", "content": initialMsg }
  ])
  response = queryLLM(messages)
  responseMsg = response["message"].get("content") + "</tool_calls>"
  messages.append({
    "role": "assistant",
    "content": responseMsg,
    "reasoning_details": response.get("reasoning_details")
  })

  toolCalls = parse(responseMsg)
  while len(toolCalls) > 0:
    toolResults = []
    # process tool calls
    for toolCall in toolCalls:
      if "jsonError" in toolCall:
        toolResults.append({ "error": toolCall["jsonError"] })
        continue
      elif toolCall["name"] not in VALID_TOOL_NAMES:
        toolResults.append({
          "error": f"Invalid tool name: {toolCall['name']}\nTool name must be one of: {' '.join(VALID_TOOL_NAMES)}"
        })
        continue

      res, args = "", toolCall["arguments"]
      match toolCall["name"]:
        case "shell":
          command, timeout = args["command"], args["timeout"] if "timeout" in args else 60
          res = shell(command, timeout)
        case "fileWrite":
          filePath, content = args["filePath"], args["content"]
          append = args["append"] if "append" in args else False
          res = fileWrite(filePath, content, append)
        case "fileRead":
          filePath = args["filePath"]
          offset = args["offset"] if "offset" in args else 0
          limit = args["limit"] if "limit" in args else 30_000
          res = fileRead(filePath, offset, limit)
        case "fetch":
          url = args["url"]
          maxLength = args["maxLength"] if "maxLength" in args else 5000
          startIndex = args["startIndex"] if "startIndex" in args else 0
          res = fetch(url, maxLength, startIndex)
        case _:
          pass

      toolResults.append(res)

    # feed back results to llm
    messages.append({
      "role": "user",
      "content": getToolResultStr([(json.dumps(result) for result in toolResults)])
    })
    response = queryLLM(messages)

    # update messages list and toolCalls
    responseMsg = response["message"].get("content") or ""
    if response["finish_reason"] == "stop":
      responseMsg += "</tool_calls>"
    messages.append({
      "role": "assistant",
      "content": responseMsg,
      "reasoning_details": response["message"].get("reasoning_details")
    })
    toolCalls = parse(responseMsg)

  return messages[-1]