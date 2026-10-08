import sys, re, hashlib, json, os, time

from pathlib import Path
from datetime import date, datetime, timezone
from dotenv import load_dotenv

from model.llm import queryLLM
from model.prompts import generateAnswerLeakCheckPrompt, generateJudgePrompt

load_dotenv()

PROMPTS_DIR_PATH = Path("prompts/")
DATASET_DIR_PATH = Path("dataset/inputs.json")
RESULTS_DIR_PATH = Path("results/")

ANSWER_LEAK_MAX_ATTEMPTS = 5
SCORER_MAX_ATTEMPTS = 5

JSON_REGEX = r"\{\s*\".*\":.*\}$"

DATASET_MODEL = os.getenv("DATASET_MODEL")

def _backoff(timeout):
  time.sleep(timeout)
  return timeout * 2

def executeRun(inputs, seeds, promptVersion, model, reps=5):
  seedsHash = {}
  for seed in seeds:
    seedsHash[seed["topic"]] = seed

  promptFileNames = [file.name for file in PROMPTS_DIR_PATH.iterdir() if file.is_file()]
  if f"{promptVersion}.txt" not in promptFileNames:
    print(
      f"Error: Invalid prompt version name {promptVersion}. Ensure prompt version exists in the 'prompts/' directory as {promptVersion}.txt"
    )
    return

  prompt = (PROMPTS_DIR_PATH / f"{promptVersion}.txt").read_text()
  cleanedPrompt = re.sub(r"# ?v[0-9]+:.*", "", prompt)
  promptHashObj = hashlib.sha256(cleanedPrompt.encode("utf-8"))
  promptHexDig = promptHashObj.hexdigest()

  resultFileNames = [file.name for file in RESULTS_DIR_PATH.iterdir() if file.is_file()]
  matches = [item for item in resultFileNames if re.search(rf"{promptVersion}_{model}\.json$", item)]
  for fileName in matches:
    results = []
    with (RESULTS_DIR_PATH / fileName).open() as file:
      results = json.load(file)["results"]

    for result in results:
      if result["prompt_hash"] != promptHexDig:
        print(f"Error: {promptVersion} has changed since run {fileName[:-5]}; create a new version")
        return

  results = []

  for input in inputs:
    formattedDate = date.today().strftime("%Y-%m-%d")
    conversation = input["conversation"]
    result = {
      "item_id": input["item_id"],
      "run_id": f"{formattedDate}_{promptVersion}_{model}",
      "prompt_hash": promptHexDig,
      "model": model,
      "reps": reps,
      "scores": [],
      "timestamp": ""
    }

    for _ in reps:
      score = {}
      problemText = seedsHash[input["topic"]]["problem_text"]
      knownAnswer = seedsHash[input["topic"]]["known_answer"]
      response = queryLLM(model, [{ "role": "system", "content": cleanedPrompt }] + conversation)

      if len(conversation) != 0 and not conversation[-1]["content"].startswith("[ hint ]"):
        score["json_parses"] = jsonParses(response)
        score["schema_valid"] = False if not score["json_parses"] else schemaValid(conversation, response)
      elif len(conversation) != 0 and conversation[-1]["content"].startswith("[ hint ]"):
        score["answer_leak"] = answerLeak(problemText, response, knownAnswer)
      score["quality"] = getScore(conversation, response, problemText, knownAnswer)

      result["scores"].append(score)

    result["timestamp"] = \
      datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    results.append(result)



# HELPER FUNCTIONS
def jsonParses(llmResponse: str):
  # Pre-condition: llmResponse is a non 'start'/'hint'-type response
  matches = re.search(JSON_REGEX, llmResponse)
  if not matches:
    return False

  try:
    json.loads(matches[0])
    return True
  except json.JSONDecodeError as _:
    print(f"LLM generated JSON could not be decoded: {matches[0]}")
    return False

def schemaValid(conversation, llmResponse: str):
  # Pre-condition: conversation is non-empty AND llmResponse is a non 'hint'-type response
  if conversation[-1]["content"].startswith("[ answer ]"):
    matches = re.search(JSON_REGEX, llmResponse)
    if not matches:
      return False

    try:
      resJson = json.loads(matches[0])
      return ["correct", "new_question"] in resJson and len(resJson) == 2
    except json.JSONDecodeError as e:
      print(f"LLM generated JSON could not be decoded: {matches[0]}")
      return False

def answerLeak(problemText: str, llmResponse: str, knownAnswer: str):
  prompt = generateAnswerLeakCheckPrompt(problemText, llmResponse, knownAnswer)
  attempts, timeout = 0, 2

  while attempts < ANSWER_LEAK_MAX_ATTEMPTS:
    try:
      response = queryLLM(DATASET_MODEL, [{ "role": "system", "content": prompt }])
      resJson = json.loads(response)
      return resJson["answer_leak"]
    except json.JSONDecodeError as e:
      print(
        f"Answer leak judge failed: {e}\nOriginal response: {llmResponse}\nRetrying in {timeout} seconds"
      )
      timeout = _backoff(timeout)
      attempts += 1
      print(f"Retrying ({attempts}/{ANSWER_LEAK_MAX_ATTEMPTS})...")

  return False

def getScore(conversation, llmResponse: str, problemText: str, knownAnswer: str):
  prompt = generateJudgePrompt(
    problemText,
    conversation + [{ "role": "assistant", "content": llmResponse }],
    knownAnswer
  )

  attempts, timeout = 0, 2
  while attempts < SCORER_MAX_ATTEMPTS:
    try:
      response = queryLLM(DATASET_MODEL, [{ "role": "system", "content": prompt }])
      resJson = json.loads(response)
      return resJson["score"]
    except json.JSONDecodeError as e:
      print(
        f"Scorer failed: {e}\nOriginal response: {llmResponse}\nRetrying in {timeout} sesconds..."
      )
      timeout = _backoff(timeout)
      attempts += 1
      print(f"Retrying ({attempts}/{SCORER_MAX_ATTEMPTS})...")

  return None

if __name__ == "__main__":
  if len(sys.argv) < 2 or sys.argv[1] not in ["run", "compare"]:
    print("Usage: python harness.py [run|compare]")
    print("Arguments (for python harness.py run):")
    print("\t- Required: run --prompt [v1|v2|v3|...] --model [OpenRouter model name]")
    print("\t- Optional: (--rep [# of repetitions per item])")
    print("Arguments (for python harness.py compare):")
    print("\t- Required: compare [relative file path for results file] [relative file path for another results file]")
    print("\t- Optional: (--out [relative file path])")
    sys.exit(1)

  if sys.argv[1] == "run":
