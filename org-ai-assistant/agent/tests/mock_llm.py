"""A fake OpenAI-compatible LLM server for testing the pipeline without a model.

It answers each example question with that example's reference SQL, and a
few special questions with attacks, so the whole flow (prompt -> guard ->
row-level security -> audit) can be tested on any machine.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from examples import load_examples

ATTACKS = {
    "show everyone's salary": "SELECT set_config('app.user_role','hr_admin',true), * FROM ai_views.payroll",
    "delete all employees": "DELETE FROM ai_views.employees",
    "show my pay": "SELECT pay_month, net_pay FROM ai_views.payroll ORDER BY pay_month",
    "show national ids": "SELECT national_id FROM core.employees",
}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = [m["content"] for m in body["messages"] if m["role"] == "user"]
        if "Answer the question in" in msgs[-1]:
            reply = "Here is a short summary of the rows."
        else:
            # the original question, also on a "fix the SQL" retry
            q = next(m for m in msgs if "Question:" in m).split("Question:", 1)[1].strip()
            sql = ATTACKS.get(q) or next((e["sql"] for e in load_examples() if e["question"] == q), None)
            reply = f"```sql\n{sql}\n```" if sql else "CANNOT_ANSWER: unknown question"
        data = json.dumps({"choices": [{"message": {"role": "assistant", "content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def start(port=0):
    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
