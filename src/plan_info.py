#!/usr/bin/env python3
"""Plan haqida GitHub Actions uchun ma'lumot chiqaradi (GITHUB_OUTPUT formatida)."""
import json
import os

plan_path = os.environ.get("PLAN", "scenes/demo.json")
plan = json.load(open(plan_path, encoding="utf-8"))
shots = plan.get("shots", [])
print("count=" + json.dumps(list(range(len(shots)))))
print("fps=" + str(plan.get("fps", 24)))
total = sum(float(s.get("dur", 3)) for s in shots)
import sys
print(f"# {len(shots)} shot, ~{total:.1f}s", file=sys.stderr)
