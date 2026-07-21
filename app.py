from utils import llm

def main():
  query = input("Enter your instructions for the coding agent: ")
  llm.agentLoop(query)


if __name__ == "__main__":
  main()