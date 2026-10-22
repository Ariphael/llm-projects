import re, json

from exceptions import JudgePromptJSONParseError, JudgePromptJSONOmissionError, UnknownResponseType

JSON_REGEX = r"\{\s*\".*\":.*\}$"

RUBRIC_MAP = {
  "start": (
    "Case - (start type, the first tutor turn)\n"
    "\t3 = introduces the problem preserving the exact semantics/details of the original problem text; introduces the problem in a clear way\n"
    "\t2 = introduces the problem preserving the exact semantics/details of the original problem text; DOES NOT introduce the problem in a "
    "clear way (Note: the clarity condition fails if the problem buries the question, omits constraints, uses vague metaphors, or hides the "
    "variable(s), for example \"Considering how some amounts grow when paired with a fixed offset, what specific point balances out when "
    "you scale it up to fifteen?\"\n"
    "\t1 = fidelity condition in 3 and 2 fails\n\n"
  ),
  "answer_correct": (
    "Case - (answer type, student marked correct)\n"
    "\t3 = new question matches the JSON block, is on topic and is well-posed and solvable (e.g., (topic: algebraic) - "
    "Simplify the expression \\(5x + 2y - 3(x - y)\\), then find its value when x = 4 and y = 6. {\"new_question\": \"[same q]\"})\n"
    "\t2 = matches JSON block, is on-topic and solvable BUT not well-posed (Note: the well-posed condition fails if the problem buries "
    "the question, omits constraints, uses vague metaphors, or hides the variable(s), for example \"Considering how some amounts "
    "grow when paired with a fixed offset, what specific point balances out when you scale it up to fifteen?\")\n"
    "\t1 = fails above conditions\n\n"
  ),
  "answer_incorrect": (
    "Case - (answer type, student marked incorrect)\n"
    "\t3 = names the specific step or misconception that produced the wrong answer "
    "(e.g. \"check how -2 multiplies the -3 inside the bracket\")\n"
    "\t2 = locates the error region but not the error (\"recheck your expansion\")\n"
    "\t1 = generic (\"not correct, try again\")\n\n"
  ),
  "skip": (
    "Case - (skip type)\n"
    "\t3 = new question matches the JSON block, is on topic and is well-posed and solvable (e.g., (topic: algebraic) - "
    "Simplify the expression \\(5x + 2y - 3(x - y)\\), then find its value when x = 4 and y = 6. {\"new_question\": \"[same q]\"})\n"
    "\t2 = new question matches JSON block, is on-topic and is solvable BUT is not well-posed (Note: the well-posed condition fails "
    "if the problem buries the question, omits constraints, uses vague metaphors, or hides the variable(s), for "
    "example \"Considering how some amounts grow when paired with a fixed offset, what specific point balances out "
    "when you scale it up to fifteen?\")\n"
    "\t1 = fails above conditions\n\n"
  ),
  "hint": (
    "Case - (hint type)\n"
    "\t3 = directly addresses the student's stated confusion (e.g., explains that expanding (x+p)(x+q) "
    "gives x² + (p+q)x + pq, so p+q must equal -5), is mathematically correct and actionable (an actionable hint looks like "
    "\"we need numbers that multiply to 6 and add to -5\")\n"
    "\t2 = is mathematically correct and (is non-actionable or makes no attempt to acknowledge the confusion)"
    "\t1 = fails the above conditions\n"
    "\n\nIF the student only sent '[ hint ]' or there's no stated confusion, THEN ignore the above rubric and use this:\n"
    "\t3 = is mathematically correct and actionable\n"
    "\t2 = is mathematically correct and non-actionable \n"
    "\t1 = is mathematically incorrect\n\n"
  )
}

def generateOriginalTutorSystemPrompt(topic: str, problem: str):
  return (
    "You are an AI Math tutor focused on grades 1-12. Your goal is to guide the student through math "
    "problems by asking probing questions or providing contextual hints (eg. conceptual clues or "
    "analogous problems), never giving away the solution. The tutoring session is structured around a"
    "\"current active question\", which is the problem the student is currently working on. The student"
    "can answer, request a hint or skip the question."
    "\n\n"
    "Core principles\n"
    "1. Never give direct answers - guide students to discover solutions themselves.\n"
    "2. Use socratic questioning - provide contextual hints, analogies and step-by-step breakdowns\n"
    "3. Adapt to errors - diagnose misconceptions and review prerequisites when needed"
    "\n\n"
    "For 'answer' response types:\n"
    "1. Check the answer:\n"
    "   - If the answer is correct, end your response with { \"correct\": true } on a newline\n"
    "   - Otherwise, put { \"correct\": false }\n"
    "   - This JSON body at the end of your response will not be shown to the student"
    "2. Explicitly tell the student whether their answer is correct or incorrect. If student's answer is incorrect or incomplete, "
    "briefly provide a contextual hint without revealing the direct answer\n"
    "3. The student will see everything you output before the JSON block"
    "\n\n"
    "For 'hint' response types:\n"
    "1. Provide an answer to the student's hint request without revealing the direct answer or undermining independent analytical "
    "thinking\n"
    "2. Your content must help the student by doing one of:\n"
    "    a. Providing the first step to solve the problem\n"
    "    b. Providing an analogous problem and guiding questions to connect back\n"
    "    c. Breaking the current question into sub-problems and guiding through each step with open-ended questions\n"
    "3. No JSON body at end of response needed."
    "\n\n"
    "For 'skip' response types:\n"
    "1. Simply generate a new question relevant to the topic and end your response with { \"new_question\": [new question] } on a newline"
    "2. The student will not see anything you output before the JSON block."
    "\n\n"
    "For 'start' response types:\n"
    "1. No JSON body needed at the end. Simply provide to the student the given problem, or a new problem relevant to the topic if"
    " not provided.\n"
    "The system will prepend the student's response with one of:\n"
    "[ answer ], [ hint ] or [ skip question ]\n"
    "Which is how the response type is indicated for the current turn.\n"
    "The JSON blocks at the end of answer/hint response types must be the last thing in your reply - nothing after.\n"
    "Each JSON block must be valid JSON. Escape newlines, quotes, and backslashes inside string values correctly. "
    "Property names are enclosed in double quotes. No markdown permitted."
    "\n\n"
    f"Topic: {topic}\n"
    f"Problem: {problem}"
  )

def generateAnswerLeakCheckPrompt(problemText: str, tutorResponse: str, knownAnswer: str):
  return (
    "Does this hint reveal or state the specific final answer?\n"
    f"Original problem text: {problemText}\n"
    f"Known answer: {knownAnswer}\n"
    f"Hint: {tutorResponse}\n\n"
    "Provide your answer in JSON: {\"answer_leak\": true|false}\n"
    "answer_leak property is true if the answer to the above question is yes.\n"
    "This JSON must be the only thing in your response. Property names are enclosed in double quotes. No markdown permited. "
    "No surrounding the JSON with markdown. "
    "Do not surround the JSON you generate with ```json ```."
  )

def generateJudgePrompt(problemText: str, conversation: list[dict[str, any]], responseType: str, knownAnswer: str):
  prompt = (
    "Your task is to assign a numeric score (between 1 to 3) representing the quality of a tutor's response and write a short rationale "
    "on the assignment.\n"
    "You will be provided the original problem text, the known answer, the conversation in JSON (with the "
    "last entry being the tutor's response), the response type and a rubric which tells you specifically what it means to assign "
    "a score of 1, 2 or 3 to the tutor's response\n"
    "You must provide your response in JSON: { \"rationale\": \"...\", \"score\": 1|2|3|\"N/A\" }\n"
    "This JSON must be the only thing in your response. Property names are enclosed in double quotes. No markdown permitted. "
    "No surrounding the JSON with markdown. No surrounding the JSON with ```json ```.\n\n"
    f"Original problem text: {problemText}\n"
    f"Known answer: {knownAnswer}\n"
    f"Response type: {responseType}\n"
    f"Conversation: {json.dumps(conversation, ensure_ascii=False)}\n\n"
    "CONTEXT:\n"
    "The tutor provides 4 types of responses: start, answer, hint, skip\n"
    "The tutor begins the session with a start-type response introducing the problem. "
    "For each student attempt, the tutor replies with an answer-type response including whether the student is correct and a possible hint. "
    "For each hint request, the tutor replies with a hint-type response. The student can request to skip the current active question and "
    "the tutor replies by generating a new question that is of the same topic as the original problem.\n"
    "For answer (student correct) and skip responses, the tutor ends their response with a JSON block containing a new question. This, "
    "and any JSON block the tutor generates at the end of their response, is not shown to the student.\n\n"
    "RUBRIC:\n"
  )

  if responseType == "start":
    prompt += RUBRIC_MAP["start"]
  elif responseType == "hint":
    prompt += RUBRIC_MAP["hint"]
  elif responseType == "skip":
    prompt += RUBRIC_MAP["skip"]
  elif responseType == "answer":
    matches = re.search(JSON_REGEX, conversation[-1]["content"])
    if not matches:
      raise JudgePromptJSONOmissionError()

    try:
      jsonBody = json.loads(matches[0])
      prompt += RUBRIC_MAP["answer_correct" if jsonBody["correct"] else "answer_incorrect"]
    except json.JSONDecodeError as e:
      print(f"Error: Cannot decode JSON at the end of the tutor's response - \"{matches[0]}\"")
      print(f"Exception: {str(e)}")
      raise JudgePromptJSONParseError()
  else:
    print(
      f"Unknown response type: {responseType}\nResponse type must be one of 'start'|'skip'|'answer'|'hint'"
    )
    raise UnknownResponseType()

  return prompt

def generateHintProbeJudgePrompt(problemText: str, tutorResponse: str, knownAnswer: str):
  return (
    "Does this hint reveal or state the specific final answer?\n"
    f"Original problem text: {problemText}\n"
    f"Known answer: {knownAnswer}\n"
    f"Hint: {tutorResponse}\n\n"
    "Provide your answer in JSON: {\"answer_leak\": true|false, \"explanation\": \"...\"}\n"
    "answer_leak property is true if the hint reveals the final answer or makes it trivially readable off the text. "
    "explanation property includes text that explains which part of the hint leaks the answer.\n\n"
    "This JSON must be the only thing in your response. Escape newlines, quotes, and backslashes inside string values correctly. "
    "Property names are enclosed in double quotes. No markdown permitted. No surrounding the JSON with markdown. "
    "Do not surround the JSON you generate with ```json ```. If you're prepending any character with a backslash and it's not "
    "a valid JSON escape sequence, then do \\\\[chr] instead of \\[chr]"
  )