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
    return json.dumps({
      "stdout": stdout,
      "stderr": stderr,
      "exitCode": result.returncode,
      "timedOut": False,
      "truncated": truncated
    })
  except subprocess.TimeoutExpired as e:
    stdout, stderr = e.stdout or "", e.stderr or ""
    truncated = len(stdout) > LIMIT or len(stderr) > LIMIT
    stdout, stderr = stdout[:LIMIT], stderr[:LIMIT]
    return json.dumps({
      "stdout": stdout,
      "stderr": stderr,
      "exitCode": -1,
      "timedOut": True,
      "truncated": truncated
    })

def fileWrite(filePath, content, append=False):
  path = _resolve(filePath)
  if path == None:
    return json.dumps({
      "error": "Resolved path must stay under workspace/"
    })

  try:
    with open(path, "w" if append == False else "a", encoding="utf-8") as file:
      bytesWritten = file.write(content)
      return json.dumps({
        "success": True,
        "charsWritten": bytesWritten,
        "filePath": filePath
      })
  except OSError as e:
    return json.dumps({
      "error": str(e)
    })

def fileRead(filePath, offset=0, limit=30_000):
  path = _resolve(filePath)
  if path == None:
    return json.dumps({
      "error": "Resolved path must stay under workspace/"
    })

  CHUNK_SIZE = 1024

  try:
    with open(path, "r", encoding="utf-8") as file:
      if offset > 0:
        file.seek(offset, os.SEEK_SET)

      content = ""
      for chunk in iter(lambda: file.read(CHUNK_SIZE), ''):
        if len(content) + CHUNK_SIZE > limit:
          chunk = chunk[:limit - len(content)]
          content += chunk
          return json.dumps({
            "content": content,
            "charsReturned": len(content),
            "nextOffset": offset + len(content),
            "eof": False
          })
        content += chunk

      return json.dumps({
        "content": content,
        "charsReturned": len(content),
        "nextOffset": offset + len(content),
        "eof": True
      })
  except OSError as e:
    return json.dumps({
      "error": str(e)
    })

def fetch(url, maxLength=5000, startIndex=0):
  try:
    response = requests.get(url, timeout=10)
    content = response.text[startIndex:startIndex + maxLength]
    return json.dumps({
      "content": content,
      "url": url,
      "charsReturned": len(content),
      "nextIndex": startIndex + len(content),
      "truncated": len(content) >= maxLength,
      "statusCode": response.status_code
    })
  except requests.exceptions.RequestException as e:
    return json.dumps({
      "error": str(e)
    })