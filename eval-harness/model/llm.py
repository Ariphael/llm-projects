import requests, json, os, time

from .exceptions import LLMQueryRetryLimitExceeded, LLMQueryClientError
from dotenv import load_dotenv

load_dotenv()

apiKey = os.getenv("OPENROUTER_KEY")

QUERY_LLM_MAX_RETRIES = 3

def _backoff(timeout):
  time.sleep(timeout)
  return timeout * 2

def queryLLM(model: str, messages: list[dict[str, any]]):
  attempt, timeout = 0, 2

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
          "reasoning": { "enabled": True }
        }),
        timeout=(10, 120)
      )
      response.raise_for_status()
      response = response.json()
      response = response["choices"][0]["message"]

      return response.get("content")
    except requests.exceptions.HTTPError:
      if response.status_code == 429 or 500 <= response.status_code <= 599:
        print(f"LLM Query POST request failed. Received status {response.status_code}")
        print(f"Retrying in {timeout} seconds...")
        attempt += 1
        timeout = _backoff(timeout)
        print("Retrying...")
        continue
      else:
        print(f"LLM Query failed: Received status {response.status_code}")
        raise LLMQueryClientError(f"LLM Query failed: Received status {response.status_code}")
    except requests.exceptions.ConnectionError:
      print("LLM Query failed: a network failure or refused connection occurred")
      print(f"Retrying in {timeout} seconds...")
      attempt += 1
      timeout = _backoff(timeout)
      print("Retrying...")
      continue
    except requests.exceptions.Timeout:
      print("LLM Query failed: a timeout occurred")
      print(f"Retrying in {timeout} seconds...")
      attempt += 1
      timeout = _backoff(timeout)
      print("Retrying...")
      continue
    except requests.exceptions.RequestException:
      print("LLM query failed: an ambiguous error occurred")
      print(f"Retrying in {timeout} seconds...")
      attempt += 1
      timeout = _backoff(timeout)
      print("Retrying...")
      continue
  raise LLMQueryRetryLimitExceeded(f"LLM Query retry limit (={QUERY_LLM_MAX_RETRIES}) exceeded")