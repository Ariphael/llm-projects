import json

from typing import TypedDict

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
  difficulty: str
  conversation: list
  studentState: StudentState

def generateInputs(seeds: list[Seed]):
  """Creates file inputs.json containing inputs with conversation left empty. Pairs seed problems with applicable scenarios and derives student_state deterministically."""
  with open('inputs.json', 'w', encoding='utf-8') as file:
    for seed in seeds:
      # for all seed topics, start, answer and skip applicable
      # if seed topic is "algebraic_expressions" or "simultaneous_equations", hint applicable

      # 'answer' scenarios':
      # 1) student submits wrong answer -> studentState: { attempts: 1, hints_used: 0 }
      # 2) student submits right answer -> studentState: same as above
      # 3) stuents submits answer after hint request -> studentState: { attempts: 1, hints_used: 1 }
      # 4) student submits wrong answer after multiple attempts -> studentState: { attempts: 3, hints_used: 0 }

      # 'start' scenario:
      # 1) new problem -> studentState: { attempts: 0, hints_used: 0 }

      # 'hint' scenarios:
      # 1) student requests hint -> studentState: { attempts: 0, hints_used: 1 }
      # 2) student requests hint after some attempts -> studentState: { attempts: 1, hints_used: 1 }

      # 'skip' scenario:
      # 1) student skips question -> studentState: { attempts: 0, hints_used: 0 }
