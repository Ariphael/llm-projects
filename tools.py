import json, subprocess, os, requests

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
    stdout, stderr = e.stdout, e.stderr
    truncated = len(stdout) > LIMIT or len(stderr) > LIMIT
    stdout, stderr = stdout[:LIMIT], stderr[:LIMIT]
    return json.dumps({
      "stdout": e.stdout,
      "stderr": e.stderr,
      "exitCode": 1,
      "timedOut": True,
      "truncated": truncated
    })

def fileWrite(filePath, content, append=False):
  try:
    with open(f"workspace/${filePath}", "w" if append == False else "a", encoding="utf-8") as file:
      bytesWritten = file.write(content)
      return json.dumps({
        "success": True,
        "bytesWritten": bytesWritten,
        "filePath": filePath
      })
  except OSError as e:
    return json.dumps({
      "success": False,
      "bytesWritten": 0,
      "filePath": filePath,
      "error": e.strerror
    })

def fileRead(filePath, offset=0, limit=30_000):
  CHUNK_SIZE = 1024

  try:
    with open(f"workspace/${filePath}", "r", encoding="utf-8") as file:
      if offset > 0:
        file.seek(offset, os.SEEK_SET)

      content = ""
      for chunk in iter(lambda: file.read(CHUNK_SIZE), ''):
        if len(content) + CHUNK_SIZE > limit:
          chunk = chunk[:limit - len(content)]
          content += chunk
          return json.dumps({
            "content": content,
            "bytesReturned": len(content),
            "nextOffset": len(content),
            "eof": False
          })
        content += chunk

      content = content.rstrip()

      return json.dumps({
        "content": content,
        "bytesReturned": len(content),
        "nextOffset": offset + limit,
        "eof": True
      })
  except OSError as e:
    return json.dumps({
      "error": e.strerror
    })

def fetch(url, maxLength=5000, startIndex=0):
  response = requests.get(url)
  return response.content[startIndex:startIndex+maxLength]