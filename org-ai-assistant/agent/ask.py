"""Command-line chat with the HR assistant.

    python ask.py --role hr_admin "How many employees are posted in Pune?"
    python ask.py --role employee --employee-id 2 "Show my net pay for the last 3 months"
    python ask.py --role hr_admin            # interactive mode
"""
import argparse

from agent import ROLES, HRAgent, UserContext


def show(ans):
    if ans.sql:
        print(f"\nSQL:\n{ans.sql}\n")
    if ans.error:
        print(f"!! {ans.error}")
    else:
        print(" | ".join(ans.columns))
        for row in ans.rows[:25]:
            print(" | ".join(str(v) for v in row))
        more = len(ans.rows) - 25
        if more > 0 or ans.truncated:
            print(f"... ({len(ans.rows)}{'+' if ans.truncated else ''} rows in total)")
        if ans.summary:
            print(f"\nAnswer: {ans.summary}")
    print(f"({ans.seconds}s)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="?")
    p.add_argument("--role", choices=ROLES, default="employee")
    p.add_argument("--employee-id", type=int)
    p.add_argument("--user", default="cli-user")
    p.add_argument("--model")
    p.add_argument("--no-summary", action="store_true", help="skip the plain-English answer (faster on CPU)")
    a = p.parse_args()

    bot, user = HRAgent(model=a.model), UserContext(a.user, a.role, a.employee_id)
    if a.question:
        show(bot.ask(a.question, user, summarise=not a.no_summary))
        return
    print("HR assistant. Type a question, or 'exit'.")
    while (q := input("\n> ").strip()).lower() not in ("exit", "quit"):
        if q:
            show(bot.ask(q, user, summarise=not a.no_summary))


if __name__ == "__main__":
    main()
