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

# Set to a small number to simulate Ollama cutting off a too-long prompt
PROMPT_TOKENS_READ = None


class _Handler(BaseHTTPRequestHandler):
    def _send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # /v1/models
        self._send({"data": [{"id": "mock"}]})

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
        if self.path.startswith("/api/chat"):  # Ollama native API
            prompt_len = sum(len(m["content"]) for m in body["messages"]) // 3
            self._send({"message": {"role": "assistant", "content": reply},
                        "prompt_eval_count": PROMPT_TOKENS_READ or prompt_len,
                        "prompt_eval_duration": 2e9, "eval_count": 40, "eval_duration": 4e9})
        else:
            self._send({"choices": [{"message": {"role": "assistant", "content": reply}}]})

    def log_message(self, *args):
        pass


def start(port=0):
    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
