import os, sys

from ..model.llm import queryLLM
from dotenv import load_dotenv
from prompts import generateStudentInquiryPrompt

load_dotenv()

DATASET_MODEL = os.getenv("DATASET_MODEL")

def generateStudentInquiry(problemText: str, priorHint: str):
  prompt = generateStudentInquiryPrompt(problemText, priorHint)
  return queryLLM(
    DATASET_MODEL,
    [ { "role": "system", "content": prompt }]
  )

if __name__ == "__main__":
  if len(sys.argv) < 3:
    print("Usage: python inquiry.py '[problem_text]' '[prior_hint]'")
    sys.exit(1)

  problemText, priorHint = sys.argv[1], sys.argv[2]
  print(generateStudentInquiry(problemText, priorHint))