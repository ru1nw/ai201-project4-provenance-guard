import sys
from scoring import stylo_scoring

text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()
result = stylo_scoring(text)

if result is None:
    print(f"stylo_score: None (text is under 20 words — {len(text.split())} words supplied)")
else:
    print(f"stylo_score: {result}")
