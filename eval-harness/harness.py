import sys, re, hashlib, json, os, time

from pathlib import Path
from datetime import date, datetime, timezone
from dotenv import load_dotenv

from model.llm import queryLLM
from model.prompts import generateAnswerLeakCheckPrompt, generateJudgePrompt, generateCorrectnessCheckPrompt
from model.exceptions import JudgePromptJSONOmissionError, JudgePromptJSONParseError

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
  matches = [item for item in resultFileNames if re.search(rf"run_{promptVersion}_{model}\.json$", item)]
  for fileName in matches:
    results = []
    with (RESULTS_DIR_PATH / fileName).open() as file:
      results = json.load(file)["results"]

    for result in results:
      if result["prompt_hash"] != promptHexDig:
        print(f"Error: {promptVersion} has changed since run {fileName[:-5]}; create a new version")
        return

  run = {
    "metadata": {
      "per_rep_pass_rate": 0,
      "mean_quality": 0,
      "per_row_pass_rate": 0,
      "invalid_rows": []
    },
    "results": []
  }

  for input in inputs:
    startTime = time.perf_counter()
    formattedDate = date.today().strftime("%Y-%m-%d")
    conversation = input["conversation"]
    result = {
      "item_id": input["item_id"],
      "run_id": f"{formattedDate}_{promptVersion}_{model}",
      "prompt_hash": promptHexDig,
      "model": model,
      "reps": reps,
      "scores": [],
      "latency_ms": "",
      "timestamp": ""
    }

    for _ in range(reps):
      score = {}
      problemText = seedsHash[input["topic"]]["problem_text"]
      knownAnswer = seedsHash[input["topic"]]["known_answer"]
      response = queryLLM(model, [{ "role": "system", "content": cleanedPrompt }] + conversation)
      responseType = input["response_type"]
      conversation += [{ "role": "assistant", "content": response }]

      if responseType == "answer":
        parses = jsonParses(response)
        schemaValid = False if not score["json_parses"] else schemaValid(conversation, response)

        if parses and schemaValid:
          if not getCorrectness(conversation, input):
            score = { "error": "misgraded", "response": response }
        else:
          score = { "json_parses": parses, "schema_valid": schemaValid }
      elif responseType == "skip":
        score["json_parses"] = jsonParses(response)
        score["schema_valid"] = False if not score["json_parses"] else schemaValid(conversation, response)
      elif responseType == "hint":
        score["answer_leak"] = answerLeak(problemText, response, knownAnswer)

      if not "error" in score:
        score["quality"] = getScore(conversation, problemText, responseType, knownAnswer)

      result["scores"].append(score)

    result["timestamp"] = \
      datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

    elapsedTime = time.perf_counter() - startTime
    result["latency_ms"] = f"{elapsedTime * 1000:.3f}"
    run["results"].append(result)

  for rowIdx, result in enumerate(run["results"]):
    passCount = 0
    for rep in result["scores"]:
      if (
        ("json_parses" not in rep or rep["json_parses"])
        and ("schema_valid" not in rep or rep["schema_valid"])
        and ("answer_leak" not in rep or not rep["answer_leak"])
        and rep["score"] >= 3
      ):
        run["metadata"]["per_rep_pass_rate"] += 1
        passCount += 1
      run["metadata"]["mean_quality"] += rep["quality"]

    if passCount == reps:
      run["metadata"]["per_row_pass_rate"] += 1
    elif passCount == 0:
      run["metadata"]["invalid_rows"].append(rowIdx)

  run["metadata"]["per_rep_pass_rate"] /= (reps * len(run["results"]))
  run["metadata"]["per_row_pass_rate"] /= len(run["results"])
  run["metadata"]["mean_quality"] /= (reps * len(run["results"]))

  with open(f"run_{promptVersion}-{model}.json") as file:
    json.dump(file, run)

  print(f"Finished. Dumped results into 'results/run_{promptVersion}-{model}.json'")


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
  if conversation[-2]["content"].startswith("[ answer ]"):
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

def getCorrectness(conversation, input):
  llmResponse = conversation[-1]["content"]
  llmJsonMatch = re.search(JSON_REGEX, llmResponse)

  try:
    llmJson = json.loads(llmJsonMatch[0])
    return llmJson["correct"] == input["student_answer_correct"]
  except json.JSONDecodeError as e:
    print(f"Unable to decode JSON: {llmJsonMatch[0]}")
    print(f"Error: {e}")
    raise json.JSONDecodeError(e.msg, e.doc, e.pos)

def getScore(conversation, problemText: str, responseType: str, knownAnswer: str):
  attempts, timeout = 0, 2
  llmResponse = conversation[-1]["content"]

  while attempts < SCORER_MAX_ATTEMPTS:
    try:
      prompt = generateJudgePrompt(
        problemText,
        conversation,
        responseType,
        knownAnswer
      )
      response = queryLLM(DATASET_MODEL, [{ "role": "system", "content": prompt }])
      resJson = json.loads(response)
      return resJson["score"]
    except JudgePromptJSONParseError as e:
      print(f"Failed to parse JSON at end of LLM response")
      print(f"LLM response: {llmResponse}")
      print(f"Error: {e}\nRetrying in {timeout} seconds...")
      timeout = _backoff(timeout)
      attempts += 1
      print(f"Retrying ({attempts}/{SCORER_MAX_ATTEMPTS})...")
    except JudgePromptJSONOmissionError as e:
      print(f"JSON body missing at end of LLM response: {e}")
      print(f"LLM response: {llmResponse}")
      print(f"Error: {e}\nRetrying in {timeout} seconds...")
      timeout = _backoff(timeout)
      attempts += 1
      print(f"Retrying ({attempts}/{SCORER_MAX_ATTEMPTS})...")
    except Exception as e:
      print(
        f"Scorer failed: {e}\nLLM response: {llmResponse}\nRetrying in {timeout} sesconds..."
      )
      timeout = _backoff(timeout)
      attempts += 1
      print(f"Retrying ({attempts}/{SCORER_MAX_ATTEMPTS})...")

  return None

def printUsage():
  print("Usage: python harness.py [run|compare]")
  print("Arguments (for python harness.py run):")
  print("\t- Required: run --prompt [v1|v2|v3|...] --model [OpenRouter model name]")
  print("\t- Optional: (--rep [# of repetitions per item])")
  print("Arguments (for python harness.py compare):")
  print("\t- Required: compare [relative file path for results file] [relative file path for another results file]")
  print("\t- Optional: (--out [relative file path])")

if __name__ == "__main__":
  if len(sys.argv) < 2 or sys.argv[1] not in ["run", "compare"]:
    printUsage()
    sys.exit(1)

  if sys.argv[1] == "run":
    if len(sys.argv) < 6 or (sys.argv[2] != "--prompt" or sys.argv[4] != "--model"):
      printUsage()
      sys.exit(1)

    with open("dataset/inputs.json", "r") as inputsFile, open("dataset/seeds.json", "r") as seedsFile:
      inputs, seeds = json.load(inputsFile), json.load(seedsFile)
      promptVersion, model = sys.argv[3], sys.argv[5]
      reps = sys.argv[7] if len(sys.argv) == 8 and sys.argv[6] == "--rep" else 5
      executeRun(inputs, seeds, promptVersion, model, reps)