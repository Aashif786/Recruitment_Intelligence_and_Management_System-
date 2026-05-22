with open('logs/app.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
matches = []
for line in lines:
    if "AI Evaluation" in line or "fallback" in line or "failed" in line or "Timeout" in line:
        matches.append(line.strip())

print(f"Found {len(matches)} matching lines.")
for m in matches[-50:]:
    print(m)
