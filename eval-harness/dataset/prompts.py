from dataset import Seed

def generateConversationSystemPrompt(seed: Seed, scenario: dict):
  if scenario["name"] == "multiple_hints":
    return (
      "You are tasked with generating a conversation for a math tutoring session conversation, without revealing the direct answer "
      "or undermining socratic/independent analytical thinking. The situation is like this:\n"
      "1. A student starts an AI math tutoring session and is provided one question\n"
      "2. Student requests a hint and provides no context where they are stuck\n"
      "3. Student requests another hint, including a clarifying question, after not understanding the first hint\n"
      f"\nThe math problem the tutor provides at step 1 is: {seed['problem_text']}\n"
      f"And the known solution is: {seed['known_answer']}\n"
      "\nYou must generate the first hint, then a student inquiry regarding the first hint, followed by a second hint\n"
      "The output you generate must follow this schema: \"[hint]\", \"[student]\", \"[hint]\"\n"
      "Where [hint] and [student] are placeholders for conversation text. Do not generate anything outside this schema - "
      "your output must be one-line. Do not include any markdown or newlines."
    )
  elif scenario["name"] == "hint_after_attempt":
    return (
      "You are tasked with generating one wrong attempt, followed by a tutor response and then a student hint request, in a math"
      " tutoring session conversation. The tutor cannot reveal the direct answer or undermine independent analytical thinking. "
      "The situation is like this:\n"
      "1. A student starts an AI math tutoring session and is provided one question\n"
      "2. The student provides an incorrect answer, with working\n"
      "3. The tutor responds politely saying the response is incorrect.\n"
      "4. The student requests a hint, including a clarifying question, after not understanding where they went wrong."
      f"\nThe math problem the tutor provides at step 1 is: {seed['problem_text']}\n"
      f"And the known solution is: {seed['known_answer']}\n"
      "\nYou must generate a plausible incorrect answer a student may give, a tutor response and then the student's hint request. "
      "The single-line output you provide must follow this schema:\n"
      "\"[incorrect_student_answer]\", \"[tutor response]\", \"[student_hint_request]\"\n",
      "Your output must be one-line. Do not generate anything else. Do not include any markdown or newlines."
    )