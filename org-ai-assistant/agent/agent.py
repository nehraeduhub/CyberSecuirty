"""Question -> SQL -> checked -> run with the user's access rights -> answer.

    from agent import HRAgent, UserContext
    bot = HRAgent()
    result = bot.ask("How many active employees per department?",
                     UserContext("hr.admin", "hr_admin"))
"""
import time
from dataclasses import dataclass, field

import psycopg
import requests

import config
import llm_client
from examples import load_examples
from schema_context import load_schema, schema_as_text
from sql_guard import GuardError, check_sql

ROLES = ("hr_admin", "manager", "employee")

SYSTEM_PROMPT = """You write PostgreSQL queries for an organisation's HR database.
Rules:
- Use ONLY these views. Always write them with the ai_views. prefix.
- Write ONE read-only SELECT statement. Never modify data.
- Return only the SQL inside a ```sql code block, no explanation.
- If the question cannot be answered from these views, or asks to change data,
  reply exactly: CANNOT_ANSWER: <short reason>
- Access control is enforced by the database. Do not try to bypass it.
- "my"/"me" means the current user's employee_id given with the question.

Views:
{schema}

Examples:
{examples}
"""


@dataclass
class UserContext:
    username: str
    role: str                  # hr_admin / manager / employee
    employee_id: int | None = None

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")


@dataclass
class Answer:
    question: str
    sql: str | None = None
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    truncated: bool = False
    summary: str | None = None
    error: str | None = None
    seconds: float = 0.0


class HRAgent:
    def __init__(self, model=None, db_dsn=None, audit_dsn=None, examples=None):
        self.model = model or config.LLM_MODEL
        self.db_dsn = db_dsn or config.DB_DSN
        self.audit_dsn = config.AUDIT_DSN if audit_dsn is None else audit_dsn
        views = load_schema(self.db_dsn)
        self.allowed_views = set(views)
        examples = load_examples() if examples is None else examples
        # Kept identical for every request so the LLM server can reuse its cache
        self.system_prompt = SYSTEM_PROMPT.format(
            schema=schema_as_text(views),
            examples="\n\n".join(f"Q: {e['question']}\n```sql\n{e['sql']}\n```" for e in examples),
        )

    # ------------------------------------------------------------------
    def generate_sql(self, question, user, previous_error=None):
        user_msg = f"Current user employee_id: {user.employee_id}\nQuestion: {question}"
        messages = [{"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_msg}]
        if previous_error:
            messages += [{"role": "assistant", "content": f"```sql\n{previous_error[0]}\n```"},
                         {"role": "user", "content": f"That failed with: {previous_error[1]}\nFix the SQL."}]
        return llm_client.extract_sql(llm_client.chat(messages, model=self.model))

    def run_sql(self, sql, user):
        with psycopg.connect(self.db_dsn) as conn, conn.cursor() as cur:
            # transaction-local settings read by the row-level security policies
            cur.execute("SELECT set_config('app.user_role', %s, true), set_config('app.employee_id', %s, true)",
                        (user.role, "" if user.employee_id is None else str(user.employee_id)))
            cur.execute(sql)
            columns = [d.name for d in cur.description]
            rows = cur.fetchmany(config.MAX_ROWS + 1)
        return columns, rows[:config.MAX_ROWS], len(rows) > config.MAX_ROWS

    def summarise(self, answer):
        preview = "\n".join(", ".join(str(v) for v in r) for r in answer.rows[:20])
        prompt = (f"Question: {answer.question}\nColumns: {', '.join(answer.columns)}\n"
                  f"Rows ({len(answer.rows)}{'+' if answer.truncated else ''}):\n{preview}\n\n"
                  "Answer the question in 1-3 plain sentences using only these rows.")
        return llm_client.chat([{"role": "user", "content": prompt}], model=self.model, max_tokens=150)

    # ------------------------------------------------------------------
    def ask(self, question, user, summarise=True, retries=1):
        start, ans, blocked = time.time(), Answer(question), None
        last_error = None
        for _ in range(retries + 1):
            try:
                raw = self.generate_sql(question, user, last_error)
                if raw is None:
                    ans.error = "The question cannot be answered from the available data."
                    break
                ans.sql = check_sql(raw, self.allowed_views, config.MAX_ROWS)
                ans.columns, ans.rows, ans.truncated = self.run_sql(ans.sql, user)
                ans.error = None
                break
            except GuardError as e:
                ans.sql, ans.error, blocked = raw, f"Blocked: {e}", str(e)
                last_error = (raw, str(e))
            except psycopg.Error as e:
                ans.error = f"Database error: {e.diag.message_primary or e}"
                last_error = (ans.sql, ans.error)
            except requests.RequestException as e:
                ans.error = f"LLM server error: {e}"
                break
        if summarise and ans.error is None:
            try:
                ans.summary = self.summarise(ans)
            except requests.RequestException:
                pass  # the table is still useful without a summary
        ans.seconds = round(time.time() - start, 1)
        self.audit(user, ans, blocked)
        return ans

    def audit(self, user, ans, blocked):
        if not self.audit_dsn:
            return
        with psycopg.connect(self.audit_dsn) as conn:
            conn.execute(
                "INSERT INTO audit.ai_query_log (app_username, app_role, question, generated_sql,"
                " rows_returned, was_blocked, block_reason) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (user.username, user.role, ans.question, ans.sql,
                 None if ans.error else len(ans.rows), blocked is not None, blocked))
