#!/usr/bin/env python3
"""plan_info.py — Actions matritsasi: kadrlarni bo'laklarga bo'lib vazifalar yasaydi."""
import json
import os
import sys


def frame_counts(plan):
    fps = plan.get("fps", 24)
    return [max(1, int(round(float(s["dur"]) * fps))) for s in plan["shots"]]


def build_tasks(plan, target=28):
    """Har bir bo'lak: {"shot": i, "fs": a, "fe": b, "idx": k} (kadr raqamlari shot ichida)."""
    tasks = []
    for si, n in enumerate(frame_counts(plan)):
        f = 1
        while f <= n:
            fe = min(n, f + target - 1)
            tasks.append({"shot": si, "fs": f, "fe": fe, "idx": len(tasks)})
            f = fe + 1
    return tasks


if __name__ == "__main__":
    plan_path = os.environ.get("PLAN", "scenes/demo.json")
    target = int(os.environ.get("CHUNK", "28"))
    plan = json.load(open(plan_path, encoding="utf-8"))
    tasks = build_tasks(plan, target)
    total = sum(frame_counts(plan))
    print("matrix=" + json.dumps(tasks))
    print("nslots=" + str(len(tasks)))
    print("fps=" + str(plan.get("fps", 24)))
    print(f"# {len(plan['shots'])} shot, {total} kadr, {len(tasks)} job", file=sys.stderr)
