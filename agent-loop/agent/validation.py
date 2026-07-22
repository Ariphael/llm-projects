def validateToolCallArgs(toolCall) -> str | None:
  """Validate tool call arguments, return corresponding error string or None if no missing arguments"""
  if "arguments" not in toolCall or "name" not in toolCall:
    return "Missing \"arguments\" or \"name\" property. Each tool call must be a JSON object with \"name\" and \"arguments\""

  arguments = toolCall["arguments"]

  match toolCall["name"]:
    case "shell":
      if "command" not in arguments:
        return "Tool call \"shell\" missing required argument \"command\""
    case "fileWrite":
      if "filePath" not in arguments:
        return "Tool call \"fileWrite\" missing required argument \"filePath\""

      if "content" not in arguments:
        return "Tool call \"fileWrite\" missing required argument \"content\""
    case "fileRead":
      if "filePath" not in arguments:
        return "Tool call \"fileRead\" missing required argument \"filePath\""
    case "fetch":
      if "url" not in arguments:
        return "Tool call \"fetch\" missing required argument \"url\""
    case _:
      return f"Unknown tool {toolCall['name']}. List of known tools: shell, fileWrite, fileRead, fetch"

  return None
