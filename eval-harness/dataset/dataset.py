import json, random, sys, os

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

  for topic, problemText, knownAnswer in seeds:
    for rtype in ALL_RTYPES:
      itemId = f"{rtype}-{topic}"
      match rtype:
        case "start":
          data["probes"].append({
            "item_id": itemId,
            "response_type": rtype,
            "topic": topic,
            "converation": [],
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
          answer = knownAnswer if isCorrect else mutateAnswerHelper(knownAnswer)
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


  # Apply perturbations


# ADVERSARIAL FUNCTIONS



# HELPER FUNCTIONS

def mutateAnswerHelper(answer: str):
  return queryLLM(
    DATASET_MODEL,
    [{ "role": "system", "message": generateMutateAnswerPrompt(answer) }]
  )

if __name__ == "__main__":
  with open("seeds.json", "r", encoding="utf-8") as file:
    generateInputs(json.load(file)["seeds"])