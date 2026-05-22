from pathlib import Path

files = [
    "data/episodic.json",
    "data/long_term.json",
    "data/priority_queue.json"
]

for f in files:
    p = Path(f)
    if p.exists():
        print(f"\n{f}")
        print(p.read_bytes()[:10])
        