import json, random, sys, os, copy, re, time

from pathlib import Path
from typing import TypedDict
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

rootDir = Path(__file__).resolve().parent.parent
sys.path.append(str(rootDir))

from model.llm import queryLLM
from model.prompts import generateOriginalTutorSystemPrompt
from prompts import generateMutateAnswerPrompt, generateHintProbeJudgePrompt

load_dotenv()

class Seed(TypedDict):
  topic: str
  problem_text: str
  known_answer: str

class StudentState(TypedDict):
  attempts: int
  hints_used: int

class Input(TypedDict):
  response_type: str
  topic: str
  conversation: list
  studentState: StudentState

class AnswerInput(TypedDict):
  response_type: str
  topic: str
  conversation: list
  studentState: StudentState
  student_answer_correct: bool|None

# INVARIANT: student_state counts the turn the model is responding to, instead of the state before it

DATASET_MODEL = os.getenv("DATASET_MODEL")

SCENARIOS = {
  "hint": [
    { "name": "first_hint", "state": { "attempts": 0, "hints_used": 0 }},
    { "name": "hint_after_attempt", "state": { "attempts": 1, "hints_used": 0 }},
    { "name": "second_hint", "state": { "attempts": 0, "hints_used": 1 }}
  ],
  "answer": [
    { "name": "wrong_no_hints", "state": { "attempts": 1, "hints_used": 0 }},
    { "name": "right_no_hints", "state": { "attempts": 1, "hints_used": 0 }},
    { "name": "after_one_hint", "state": { "attempts": 1, "hints_used": 1 }},
    { "name": "after_many_attempts", "state": { "attempts": 3, "hints_used": 0 }}
  ],
  "start": [
    { "name": "start", "state": { "attempts": 0, "hints_used": 0 }}
  ],
  "skip": [
    { "name": "skip", "state": { "attempts": 0, "hints_used": 0 }}
  ]
}

ALL_SEEDS = [
  "percentages",
  "ratios",
  "probability",
  "algebraic",
  "linear",
  "exponents_and_square_roots",
  "inequalities",
  "simultaneous",
  "trigonometry",
  "quadratics"
]

ALL_RTYPES = ["start", "skip", "hint", "answer"]

ASSIGNMENTS = {
  ("start", "start"): ALL_SEEDS,
  ("skip", "skip"): ALL_SEEDS,
  ("hint", "first_hint"): ["quadratics", "linear", "inequalities", "ratios"],
  ("hint", "hint_after_attempt"): ["algebraic", "simultaneous", "percentages"],
  ("hint", "second_hint"): ["quadratics", "linear", "algebraic"],
  ("answer", "wrong_no_hints"): ["quadratics", "simultaneous", "inequalities"],
  ("answer", "right_no_hints"): ["ratios", "percentages"],
  ("answer", "after_one_hint"): ["linear", "algebraic"],
  ("answer", "after_many_attempts"): ["simultaneous", "quadratics"],
}

UNICODE_MAP = {
  "<=": "≤",
  ">=": "≥",
  "sqrt": "√",
  "^2": "²",
  "-": "–"
}

FILLER_PAIRS = [
  ({"role": "user", "content": "[ hint ]\nok"},
   {"role": "assistant",   "content": "Take your time."}),
  ({"role": "user", "content": "[ hint ]\ncan you explain that again?"},
   {"role": "assistant",   "content": "Sure — which part would you like me to go over?"}),
  ({"role": "user", "content": "[ hint ]\ngot it, thanks"},
   {"role": "assistant",   "content": "Great. Let's keep going."}),
]

ARITHMETIC_REGEX = r"[a-zA-Z0-9_().\s]+[+\-*/=][a-zA-Z0-9_().\s]*=[a-zA-Z0-9_().\s]+"
MATH_UNIT_REGEX = r"(?:\d+(?:\.\d+)?|(?<![A-Za-z])[A-Za-z](?![A-Za-z])|[-+*/^()])"
MATH_SIDE_REGEX = rf"{MATH_UNIT_REGEX}(?:\s*{MATH_UNIT_REGEX})*"
MATH_EXPRESSION_REGEX = rf"({MATH_SIDE_REGEX}(?:\s*=\s*{MATH_SIDE_REGEX})+)"
JSON_REGEX = r"\{.*\}$"

DATASET_MODEL_MAX_RETRIES = 5

def generateInputs(seeds: list[Seed]):
  """Creates file inputs.json containing inputs with conversation left for the user to fill. Pairs seed problems with applicable scenarios and derives student_state deterministically."""

  # for all seed topics, start, answer, hint and skip applicable
  # degenerate cases where hint does not apply: percentages, probability_basics

  seedMap = {}
  for seed in seeds:
    seedMap[seed["topic"]] = seed

  data = { "inputs": [] }

  for (rtype, scenarioName), assignments in ASSIGNMENTS.items():
    for seed in assignments:
      studentState = {}
      for scenario in SCENARIOS[rtype]:
        if scenario["name"] == scenarioName:
          studentState = scenario["state"]
          break

      if not studentState:
        raise KeyError(f"Invalid scenario name: {scenarioName}")

      conversation = [{ "role": "assistant", "content": seedMap[seed]["problem_text"] }]
      if rtype == "skip":
        conversation.append({ "role": "user", "content": "[ skip question ]"})

      for _ in range(scenario["state"]["attempts"]):
        conversation.append({ "role": "user", "content": None})

      itemId = f"{rtype}-{seed}-{scenarioName}"

      if rtype == "answer":
        item: AnswerInput = {
          "item_id": itemId,
          "response_type": rtype,
          "topic": seed,
          "conversation": conversation,
          "student_state": studentState,
          "student_answer_correct": None
        }
        data["inputs"].append(item)
        continue

      item: Input = {
        "item_id": itemId,
        "response_type": rtype,
        "topic": seed,
        "conversation": conversation,
        "student_state": studentState,
      }
      data["inputs"].append(item)

  with open("inputs.json", "w", encoding="utf-8") as file:
    json.dump(data, file, indent=2)

def generateProbes(seeds: list[Seed]):
  data = { "probes": [] }

  print("Generating probes...\n")
  for s in seeds:
    topic, problemText, knownAnswer = s["topic"], s["problem_text"], s["known_answer"]
    print(f"Processing seed item ({topic} - '{problemText}')")

    for rtype in ALL_RTYPES:
      itemId = f"{rtype}-{topic}"
      match rtype:
        case "start":
          data["probes"].append({
            "item_id": itemId,
            "response_type": rtype,
            "topic": topic,
            "conversation": [],
            "student_state": { "attempts": 0, "hints_used": 0 }
          })
        case "hint":
          data["probes"].append({
            "item_id": itemId,
            "response_type": rtype,
            "topic": topic,
            "conversation": [
              { "role": "assistant", "content": problemText },
              { "role": "user", "content": "[ hint ]\ni need a hint" }
            ],
            "student_state": { "attempts": 0, "hints_used": 0 }
          })
        case "skip":
          data["probes"].append({
            "item_id": itemId,
            "response_type": rtype,
            "topic": topic,
            "conversation": [
              { "role": "assistant", "content": problemText },
              { "role": "user", "content": "[ skip question ]" }
            ],
            "student_state": { "attempts": 0, "hints_used": 0 }
          })
        case "answer":
          isCorrect = random.choice([True, False])
          answer = knownAnswer if isCorrect else mutateAnswerHelper(problemText, knownAnswer)
          data["probes"].append({
            "item_id": itemId,
            "response_type": rtype,
            "topic": topic,
            "conversation": [
              { "role": "assistant", "content": problemText },
              { "role": "user", "content": f"[ answer ]\n{answer}" }
            ],
            "student_state": { "attempts": 1, "hints_used": 0 },
            "student_answer_correct": isCorrect
          })
        case _:
          pass

  print("\nApplying perturbations...\n")

  # Apply perturbations
  perturbations = []
  for item in data["probes"]:
    if item["response_type"] in ["start", "skip"]:
      continue
    pertLatexItem, replCount = injectLatex(item)
    if replCount > 0:
      perturbations.append(pertLatexItem)

    pertUnicodeItem, replCount = injectUnicode(item)
    if replCount > 0:
      perturbations.append(pertUnicodeItem)

    perturbations.append(empty(item))
    perturbations.append(pad(item))

  data["probes"].extend(perturbations)

  try:
    with open("probes.json", "w", encoding="utf-8") as file:
      json.dump(data, file, indent=2)
      print("Finished. Wrote discovery pass probes to file probes.json")
  except OSError as e:
    print(f"Failed to write to file 'probes.json': {e}")
    sys.exit(1)

def runDiscoveryPass():
  # Runs probes through current CherryPi prompt concurrently via multithreading
  # Clusters by symptom categories:
  # no_json_body - JSON body at end of response is omitted in a 'response' or 'skip' answer type
  # json_body_included - JSON body included for 'hint' answer type
  # schema_violation - required fields are not present in JSON response
  # json_parse_error - JSON at end of response does not match

  # result:
  # {
  #    'no-json-body': resItem,
  #    'json-body-included': resItem,
  # ...
  # }

  # resItem:
  # {
  #    count: int,
  #    items: [list of { "item_id": str, "response": str }],
  # }

  probes = {}
  result = {
    "answer_leak": { "count": 0, "items": [] },
    "no_json_body": { "count": 0, "items": [] },
    "json_body_included": { "count": 0, "items": [] },
    "schema_violation": { "count": 0, "items": [] },
    "json_parse_error": { "count": 0, "items": [] },
    "call_failed": { "count": 0, "items": [] }
  }

  try:
    with open("probes.json", "r", encoding="utf-8") as file:
      probes = json.load(file)
      probes = probes["probes"]
  except OSError:
    print("Error: File 'probes.json' is missing. Generate probes first using 'python dataset.py probes'")
    sys.exit(1)

  print(f"Loaded {len(probes)} probes...\n")

  with ThreadPoolExecutor(max_workers=10) as executor:
    executorRes = executor.map(processProbeHelper, probes)

  for res in executorRes:
    if len(res) == 0:
      continue

    for symptom in res:
      error, itemId, response = symptom["error"], symptom["item_id"], symptom["response"]
      result[error]["count"] += 1
      result[error]["items"].append({ "item_id": itemId, "response": response })

  try:
    with open("discovery_pass.json", "w", encoding="utf-8") as file:
      json.dump(result, file, indent=2)
    print("Finished. Wrote discovery pass results to discovery_pass.json")
  except OSError as e:
    print(f"Failed to write to file 'discovery_pass.json': {e}")
    sys.exit(1)

# ADVERSARIAL FUNCTIONS

# If a new seed problem or input requires a multi-letter math token to answer, then this function breaks
def injectLatex(item):
  new, replCount = copy.deepcopy(item), 0
  for turn in new["conversation"]:
    if turn["role"] == "user":
      before = turn["content"]
      if re.search(r"^x ?= ?[0-9], ?x ?= ?[0-9]$", turn["content"]):
        turn["content"] = \
          re.sub(r"^x ?= ?([0-9]), ?x ?= ?([0-9])$", r"$x=\1$, $x=\2$", turn["content"])
      elif re.search(MATH_EXPRESSION_REGEX, turn["content"]):
        for expression in re.split(MATH_EXPRESSION_REGEX, turn["content"]):
          if "=" in expression:
            turn["content"] = re.sub(rf"({expression})", r"$\1$", turn["content"])
      else:
        turn["content"] = \
          re.sub(r"(\d+)", r"$\1$", turn["content"])

      if turn["content"] != before:
        replCount += 1

  new["item_id"] = item["item_id"] + "-latex"
  return (new, replCount)

def injectUnicode(item):
  new, replCount = copy.deepcopy(item), 0
  for turn in new["conversation"]:
    if turn["role"] == "user":
      before = turn["content"]
      for pat, repl in UNICODE_MAP.items():
        turn["content"] = str.replace(turn["content"], pat, repl)
      turn["content"] = re.sub(r"\"(.*)\"", r"“\1”", turn["content"])
      turn["content"] = re.sub(r"'(.*)'", r"‘\1’", turn["content"])
      if before != turn["content"]:
        replCount += 1

  new["item_id"] = item["item_id"] + "-unicode"
  return (new, replCount)

def empty(item):
  new = copy.deepcopy(item)
  # The last turn in the conversation is always from the student
  new["conversation"][-1] = { "role": "user", "content": f"[ {new["response_type"]} ]" }
  new["item_id"] = item["item_id"] + "-empty"
  return new

def pad(item, pairs=6):
  new = copy.deepcopy(item)
  filler = []
  for i in range(pairs):
    filler.extend(FILLER_PAIRS[i % len(FILLER_PAIRS)])
  new["conversation"] = new["conversation"][:1] + filler + new["conversation"][1:]
  new["item_id"] = item["item_id"] + "-padded"
  return new

# HELPER FUNCTIONS

def mutateAnswerHelper(problemText: str, answer: str):
  return queryLLM(
    DATASET_MODEL,
    [{ "role": "system", "content": generateMutateAnswerPrompt(problemText, answer) }]
  )

def backoff(timeout):
  time.sleep(timeout)
  return timeout * 2

def answerLeakJudgeHelper(problemText: str, tutorResponse: str, knownAnswer: str):
  attempt, timeout = 0, 2

  while attempt < DATASET_MODEL_MAX_RETRIES:
    try:
      response = queryLLM(
        DATASET_MODEL,
        [{ "role": "system", "content": generateHintProbeJudgePrompt(problemText, tutorResponse, knownAnswer) }]
      )
      response = json.loads(response)
      return response
    except json.JSONDecodeError as e:
      attempt += 1
      timeout = backoff(timeout)
      continue

  return None


def processProbeHelper(probe):
  # Runs probe through CherryPi prompt, returning an object array indicating the
  # symptom categories detected in the response:
  # no_json_body - JSON body at end of response is omitted in a 'response' or 'skip' answer type
  # json_body_included - JSON body included for 'hint' answer type
  # schema_violation - required fields are not present in JSON response
  # json_parse_error - JSON at end of response does not match

  # res = [{ "error": ("no_json_body"|"json_body_included"|"schema_violation"|"json_parse_error"|"call_failed"|"answer_leak"), item_id, response, explanation? }, ...]
  res = []

  topic, resType, itemId = probe["topic"], probe["response_type"], probe["item_id"]
  print(f"Processing probe ({itemId})")
  problem = probe["conversation"][0]["content"] if probe["conversation"] else ""
  systemPrompt = {
    "role": "system",
    "content": generateOriginalTutorSystemPrompt(topic, problem)
  }

  response = ""
  try:
    response = queryLLM(DATASET_MODEL, [systemPrompt] + probe["conversation"])
  except Exception as e:
    return [{ "error": "call_failed", "item_id": itemId, "response": e }]

  print(f"Generated response: {response}")

  match = re.search(JSON_REGEX, response)
  if match == None and resType in ["answer", "skip"]:
    res.append({ "error": "no_json_body", "item_id": itemId, "response": response })
  elif match != None and resType in ["start", "hint"]:
    res.append({ "error": "json_body_included", "item_id": itemId, "response": response })

  try:
    if match:
      data = json.loads(match[0])
      if resType == "answer":
        if len(data) != 1 or "correct" not in data:
          res.append({ "error": "schema_violation", "item_id": itemId, "response": response })
      elif resType == "skip":
        if len(data) != 1 or "new_question" not in data:
          res.append({ "error": "schema_violation", "item_id": itemId, "response": response })
  except json.JSONDecodeError as e:
    res.append({ "error": "json_parse_error", "item_id": itemId, "response": response })

  if resType == "hint":
    seeds = []
    try:
      with open("seeds.json", "r", encoding="utf-8") as file:
        seeds = json.load(file)["seeds"]
    except OSError:
      print("Error: File 'seeds.json' is missing.")
      return res

    isCorrectSeed = lambda seed, topic: seed["topic"] == topic
    seedMatches = [s for s in seeds if isCorrectSeed(s, topic)]
    knownAnswer = seedMatches[0]["known_answer"]

    problemText = probe["conversation"][0]["content"]

    judge = answerLeakJudgeHelper(problemText, response, knownAnswer)
    if not judge or judge["answer_leak"] == True:
      res.append({ "error": "answer_leak", "item_id": itemId, "response": response, "explanation": judge["explanation"]})

  return res

if __name__ == "__main__":
  if len(sys.argv) != 2 or sys.argv[1] not in ["inputs", "probes", "pass"]:
    print("Usage: python dataset.py [inputs|probes|pass]")
    sys.exit(1)

  with open("seeds.json", "r", encoding="utf-8") as file:
    if sys.argv[1] == "inputs":
      generateInputs(json.load(file)["seeds"])
    elif sys.argv[1] == "probes":
      generateProbes(json.load(file)["seeds"])
    elif sys.argv[1] == "pass":
      runDiscoveryPass()