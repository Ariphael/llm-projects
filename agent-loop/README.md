# agent-loop
A minimal claude-code-style agent built without using an agent framework - just raw LLM API calls wrapped around a loop. An LLM is provided 4 basic tools - shell execution, file read, file write and web fetch. A structured tool-calling protocl and a basic agentic loop with exponential backoff between retries and a max iteration guard is integrated. Everything including the loop itself, termination and safety bounds, error recovery and the tool-calling protocol was implemented and reasoned about by hand

# Why this exists
This project was built to understand how turn-based loops and tool-calling protocols work under the hood in frameworks such as LangChain. Most agent tutorials provide a framework (e.g., Anthropic SDK's Native Tool Use) that silently handles these features and the failure modes and this project deliberately does none of that. Everything an agent runtime has to get right is written out by hand:

- The agentic loop - call the model, parse the response, execute the tool calls, feed the results back, repeat until done;
- A text-based tool-calling protocol because the model is driven through a plain-completion-style endpoint rather than a native tool-use API;
- Termination and safety bounds - knowing when the agent is finished vs stuck
- Error recovery - what happens when the model emits malformed output, names a tool that doesn't exist, or a tool throws.

# How it works
The agent runs a turn-based loop:

1. Send the conversation (system prompt + history) to the model
2. The model replies with reasoning and a block of tool calls.
3. Parse the tool calls, validate them and dispatch each to the relevant Python function
4. Feed the results back to the model as the next turn
5. Repeat, until the model signals it's done by omitting the tool calls block.

For step #2, tool calls are expressed as JSON wrapped in XML-style tags that the loop parses out of the model's text. This is because the model is driven through a completion-style endpoint without native tool support:

```
<tool_calls>
<tool_call>{"name": "fileRead", "arguments": {"filePath": "src/app.js"}}</tool_call>
<tool_call>{"name": "shell", "arguments": {"command": "ls -la"}}</tool_call>
</tool_calls>
```

Results are returned in a matching ```<tool_results>``` block with each result tagged with the id of the call it answers, so multiple tool calls in one turn are supported.

# Preventing fabricated results
A completion LLM model left unconstrained may potentially write a tool call block and continue generating tokens, hallucinating the results and reasoning off fiction. To prevent this, the API's stop sequence parameter is specified to be ```</tool_calls>``` to halt generation at the closing tag. As this feature strips the closing tag, the loop reappends ```</tool_calls>``` to the end of the model's response.

# Tools

| Tool | Purpose |
|------|---------|
| `fileRead` | Read a whole file or a byte range, with paging for large files. |
| `fileWrite` | Overwrite or append to a file (creates it if absent). |
| `shell` | Run a shell command; returns stdout, stderr, exit code, and timeout/truncation flags. |
| `fetch` | Fetch a URL and return its contents, with character-range paging. |

All file operations are confined to a 'workspace/' directory and cannot read or write outisde of this directory. Paths are resolved and checked for containment before any file is opened.

# Robustness
The loop is designed so that malformed or incorrect model outputs are provided as feedback that the model can use to correct itself in the next turn:

- Malformed tool calls (invalid JSON, unknown tool name, missing required arguments) are caught during parsing and returned to the model as an error result.
- Tool failures such as a missing file or a failed command are surfaced to the model as error results that the model can read and adapt to.
- API failured including transient errors such as 429, 5xx, connection failures and timeouts, are retried with exponential backoff. For client errors (400, 401) that won't succeed a retry, an exception is raised.
- A max iteration guard (=25) bounds the agent loop so the model does not excessively tool-call or get stuck retrying - burning tokens and consuming too many OpenRouter credits.

# Setup
Requires Python 3.12+ and an OpenRouter API key

Install dependencies:
```bash
pip install requests python-dotenv
```

Create a `.env` file in the project root:

```
OPENROUTER_KEY=your_key_here
MODEL=your_model_slug_here
```

# Usage
Run from the project root:
```bash
python app.py
```

You'll be prompted to specify the agent's task:
```
Enter your instructions for the coding agent: Write a Python script that prints
FizzBuzz for 1 to 20, then run it and show me the output.
```

The agent will write the file, execute it via the shell tool, and report back.

# Project structure
```
agent-loop/
  app.py            # entry point — prompts for a task and starts the loop
  tools.py          # the four tool implementations
  utils/
    llm.py          # the agent loop, model queries, and tool-call parsing
    prompts.py      # the system prompt
    validation.py   # tool-call argument validation
    exceptions.py   # custom exceptions
  workspace/        # sandbox the agent operates in
```

# Scope and limitations
This is a learning project and several design choices favour simplicity over completeness:

- The shell is stateless - working directory and environment variables do not persist between commands and the model must use absolute paths or chain commands within a single call.
- There is no dedicated edit tool. Editing a file is done either through the file write tool, which overwrites the file, or ```sed```/```patch``` via the shell tool, rather than a ```str_replace```-style operation.
- The text-based protocol is fragile around escaping. File contents with awkward quoting or newlines can produce malformed JSON; the retry path handles this, but a native tool-use API would avoid the class of problem entirely.
- No context window management. Long tasks may result in the model producing lots of tokens that blow past the size fo the context window. The potential solution here would be to compact/summarise old turns if the context window size exceeds a certain threshold.
- As this is a single-client agent, exponential backoff between retries were implemented without jitter. Introducing jitter (i.e., adding randomness to the backoff) to prevent thundering-herd is a feasible idea for improvement.
- File tools are contained to the 'workspace/' directory, but shell commands are run with the host's permissions.

These are the natural next steps if the project were taken further, and each maps to a real design decision that production agent runtimes have to make.