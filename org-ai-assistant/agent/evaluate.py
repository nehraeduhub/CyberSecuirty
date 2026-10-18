"""Measures how accurately (and how fast) a model answers the example questions.

For each example the model sees all the OTHER examples, writes SQL, and we
compare its result rows with the reference SQL's rows. Use this to choose a
model for your hardware and to re-check accuracy after every change.

    python evaluate.py                                  # model from config
    python evaluate.py --model qwen2.5-coder:7b --model qwen2.5-coder:14b
"""
import argparse
import statistics
from collections import Counter

import config
from agent import HRAgent, UserContext
from examples import load_examples


def normalise(rows):
    """Order-insensitive comparison; numbers rounded so 3.50 == 3.5."""
    def cell(v):
        return round(float(v), 2) if isinstance(v, (int, float)) or type(v).__name__ == "Decimal" else v
    return Counter(tuple(cell(v) for v in r) for r in rows)


def evaluate(model, examples, user):
    passed, times = 0, []
    for i, ex in enumerate(examples):
        others = examples[:i] + examples[i + 1:]
        bot = HRAgent(model=model, examples=others, audit_dsn="")
        ans = bot.ask(ex["question"], user, summarise=False)
        ref_cols, ref_rows, _ = bot.run_sql(ex["sql"], user)
        ok = ans.error is None and normalise(ans.rows) == normalise(ref_rows)
        passed += ok
        times.append(ans.seconds)
        print(f"[{'PASS' if ok else 'FAIL'}] {ans.seconds:6.1f}s  {ex['question']}")
        if not ok:
            print(f"         {ans.error or f'got {len(ans.rows)} rows, expected {len(ref_rows)}'}")
    print(f"\n{model or config.LLM_MODEL}: {passed}/{len(examples)} correct "
          f"({100 * passed / len(examples):.0f}%), median {statistics.median(times):.1f}s per question\n")
    return passed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", action="append", help="repeat to compare several models")
    a = p.parse_args()
    examples = load_examples()
    user = UserContext("evaluator", "hr_admin")
    for model in a.model or [None]:
        evaluate(model, examples, user)


if __name__ == "__main__":
    main()
