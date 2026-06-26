import sys
from scoring import llm_scoring

text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
result = llm_scoring(text)
print(f"score:     {result['score']}")
print(f"reasoning: {result['reasoning']}")
