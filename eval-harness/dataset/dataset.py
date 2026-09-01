import json, random, sys, os, copy, re

from pathlib import Path
from typing import TypedDict
from dotenv import load_dotenv

rootDir = Path(__file__).resolve().parent.parent
sys.path.append(str(rootDir))

from model.llm import queryLLM
from prompts import generateMutateAnswerPrompt

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
  ({"role": "student", "content": "ok"},
   {"role": "tutor",   "content": "Take your time."}),
  ({"role": "student", "content": "can you explain that again?"},
   {"role": "tutor",   "content": "Sure — which part would you like me to go over?"}),
  ({"role": "student", "content": "got it, thanks"},
   {"role": "tutor",   "content": "Great. Let's keep going."}),
]

ARITHMETIC_REGEX = r"[a-zA-Z0-9_().\s]+[+\-*/=][a-zA-Z0-9_().\s]*=[a-zA-Z0-9_().\s]+"
MATH_UNIT_REGEX = r"(?:\d+(?:\.\d+)?|(?<![A-Za-z])[A-Za-z](?![A-Za-z])|[-+*/^()])"
MATH_SIDE_REGEX = rf"{MATH_UNIT_REGEX}(?:\s*{MATH_UNIT_REGEX})*"
MATH_EXPRESSION_REGEX = rf"({MATH_SIDE_REGEX}(?:\s*=\s*{MATH_SIDE_REGEX})+)"

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

      conversation = [{ "role": "tutor", "content": seedMap[seed]["problem_text"] }]
      if rtype == "skip":
        conversation.append({ "role": "student", "content": "[ skip question ]"})

      for _ in range(scenario["state"]["attempts"]):
        conversation.append({ "role": "student", "content": None})

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

  for s in seeds:
    topic, problemText, knownAnswer = s["topic"], s["problem_text"], s["known_answer"]
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
              { "role": "tutor", "content": problemText },
              { "role": "student", "content": "i need a hint" }
            ],
            "student_state": { "attempts": 0, "hints_used": 0 }
          })
        case "skip":
          data["probes"].append({
            "item_id": itemId,
            "response_type": rtype,
            "topic": topic,
            "conversation": [
              { "role": "tutor", "content": problemText },
              { "role": "student", "content": "[ skip question ]" }
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
              { "role": "tutor", "content": problemText },
              { "role": "student", "content": answer }
            ],
            "student_state": { "attempts": 1, "hints_used": 0 },
            "student_answer_correct": isCorrect
          })
        case _:
          pass

  print(data["probes"])

  # Apply perturbations
  perturbations = []
  for item in data["probes"]:
    if item["response_type"] in ["start", "skip"]:
      continue
    pertLatexItem, replCount = injectLatex(item)
    if replCount > 0:
      perturbations.append(injectLatex(pertLatexItem))

    pertUnicodeItem, replCount = injectUnicode(item)
    if replCount > 0:
      perturbations.append(injectUnicode(pertUnicodeItem))

    perturbations.append(empty(item))
    perturbations.append(pad(item))

  data["probes"].extend(perturbations)

  with open("probes.json", "w", encoding="utf-8") as file:
    json.dump(data, file, indent=2)

# ADVERSARIAL FUNCTIONS

# If a new seed problem or input requires a multi-letter math token to answer, then this function breaks
def injectLatex(item):
  new, replCount = copy.deepcopy(item), 0
  for turn in new["conversation"]:
    if turn["role"] == "student":
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
    if turn["role"] == "student":
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
  new["conversation"][-1] = { "role": "student", "content": "" }
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

if __name__ == "__main__":
  if len(sys.argv) != 2 or sys.argv[1] not in ["inputs", "probes"]:
    print("Usage: python dataset.py [inputs|probes]")
    sys.exit(1)

  with open("seeds.json", "r", encoding="utf-8") as file:
    if sys.argv[1] == "inputs":
      generateInputs(json.load(file)["seeds"])
    elif sys.argv[1] == "probes":
      generateProbes(json.load(file)["seeds"])