import sys, re, hashlib, json

from pathlib import Path
from datetime import date

from model.llm import queryLLM

PROMPTS_DIR_PATH = Path("prompts/")
DATASET_DIR_PATH = Path("dataset/inputs.json")
RESULTS_DIR_PATH = Path("results/")

def executeRun(inputs, promptVersion, model, reps=5):
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
      response = queryLLM(model, [{ "role": "system", "content": cleanedPrompt }] + input["conversation"])
      # TODO




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
