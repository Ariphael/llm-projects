import json, subprocess, os, requests

WORKSPACE = os.path.realpath("workspace")

def _resolve(filePath):
  """Join under WORKSPACE, resolve, and verify containment. Returns abs path or None."""
  candidate = os.path.realpath(os.path.join(WORKSPACE, filePath))
  if candidate != WORKSPACE and not candidate.startswith(WORKSPACE + os.sep):
    return None
  return candidate

def shell(command, timeout=60):
  LIMIT = 30_000
  TIMEOUT = min(timeout, 300)
  TARGET_DIRECTORY = "workspace"

  try:
    result = subprocess.run(command, cwd=TARGET_DIRECTORY, shell=True, \
                            timeout=TIMEOUT, capture_output=True, text=True)
    stdout, stderr = result.stdout, result.stderr
    truncated = len(stdout) > LIMIT or len(stderr) > LIMIT
    stdout, stderr = stdout[:LIMIT], stderr[:LIMIT]
    return {
      "stdout": stdout,
      "stderr": stderr,
      "exitCode": result.returncode,
      "timedOut": False,
      "truncated": truncated
    }
  except subprocess.TimeoutExpired as e:
    stdout, stderr = e.stdout or "", e.stderr or ""
    truncated = len(stdout) > LIMIT or len(stderr) > LIMIT
    stdout, stderr = stdout[:LIMIT], stderr[:LIMIT]
    return {
      "stdout": stdout,
      "stderr": stderr,
      "exitCode": -1,
      "timedOut": True,
      "truncated": truncated
    }

def fileWrite(filePath, content, append=False):
  path = _resolve(filePath)
  if path == None:
    return {
      "error": "Resolved path must stay under workspace/"
    }

  try:
    with open(path, "w" if append == False else "a", encoding="utf-8") as file:
      charsWritten = file.write(content)
      return {
        "success": True,
        "charsWritten": charsWritten,
        "filePath": filePath
      }
  except OSError as e:
    return {
      "error": str(e)
    }

def fileRead(filePath, offset=0, limit=30_000):
  path = _resolve(filePath)
  if path == None:
    return {
      "error": "Resolved path must stay under workspace/"
    }

  try:
    with open(path, "rb", encoding="utf-8") as file:
      if offset > 0:
        file.seek(offset, os.SEEK_SET)

      raw = file.read(limit)
      eof = len(file.read(1)) == 0

    text = raw.decode("utf-8", errors="replace")

    return {
      "content": text,
      "bytesReturned": len(raw),
      "nextOffset": offset + len(raw),
      "eof": eof
    }
  except OSError as e:
    return {
      "error": str(e)
    }

def fetch(url, maxLength=5000, startIndex=0):
  try:
    response = requests.get(url, timeout=10)
    content = response.text[startIndex:startIndex + maxLength]
    return {
      "content": content,
      "url": url,
      "charsReturned": len(content),
      "nextIndex": startIndex + len(content),
      "truncated": len(content) >= maxLength,
      "statusCode": response.status_code
    }
  except requests.exceptions.RequestException as e:
    return {
      "error": str(e)
    }