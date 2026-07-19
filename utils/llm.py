import requests, json, os, re
from dotenv import load_dotenv

from prompts import systemPrompt
from exceptions import EmptyToolCallBlockException
from tools import shell, fileWrite, fileRead, fetch

load_dotenv()

apiKey = os.getenv("OPENROUTER_KEY")

EMPTY_TOOL_CALL_BLOCK_ERROR_MSG = "tool calls block must be non-empty"

VALID_TOOL_NAMES = ["fileRead", "fileWrite", "shell", "fetch"]
TOOL_CALLS_BLOCK_REGEX = r"\<tool_calls\>(.*)\<\/tool_calls\>"
TOOL_CALL_REGEX = r"\<tool_call\>(.*)\<\/tool_call\>"

def queryLLM(messages: list[dict[str: any]]):
  response = requests.post(
    url="https://openrouter.ai/api/v1/chat/completions",
    headers={
      "Authorization": f"Bearer {apiKey}",
      "Content-Type": "application/json",
    },
    data=json.dumps({
      "model": "",
      "messages": messages,
      "reasoning": {"enabled": True},
      "stop": ["</tool_calls>"]
    })
  )

  response = response.json()
  return response["choices"][0]["message"]


def parse(responseMsg: str):
  if not re.search(TOOL_CALLS_BLOCK_REGEX, responseMsg) and \
    responseMsg.endswith("</tool_calls>"):
    return []

  parsedCalls = []

  match = re.search(TOOL_CALLS_BLOCK_REGEX, responseMsg)
  if match.groups() < 2:
    raise []

  toolCalls = re.findall(TOOL_CALL_REGEX, match.group(1))
  for toolCall in toolCalls:
    try:
      parsedCalls.append(json.loads(toolCall))
    except json.JSONDecodeError as e:
      parsedCalls.append(json.loads("\{ \"jsonError\": " + f"\"{e}\"" + "\}"))

  return parsedCalls


def getToolResultStr(toolResults: list[str]):
  results = "<tool_results>\n"
  for resIdx in range(len(toolResults)):
    results += f"<tool_result id=\"{resIdx}\">{toolResults[resIdx]}</tool_result>\n"
  return results + "</tool_results>"


def agentLoop(initialMsg: str):
  messages = []

  # first api call with system prompt
  messages.append(
    { "role": "system", "content": systemPrompt },
    { "role": "user", "content": initialMsg }
  )
  response = queryLLM(messages)
  responseMsg = response.get("content") + "</tool_calls>"
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
          "error": f"Invalid tool name: {toolCall["name"]}\nTool name must be one of: {" ".join(VALID_TOOL_NAMES)}"
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
    messages.append({ "role": "system", "content": getToolResultStr(toolResults) })
    response = queryLLM(messages)

    # update messages list and toolCalls
    responseMsg = response.get("content") + "</tool_calls>"
    messages.append({ "role": "assistant", "content": responseMsg})
    toolCalls = parse(responseMsg)