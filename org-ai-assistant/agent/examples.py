"""Loads question -> SQL example pairs from database/04_sample_questions.sql.

Format in that file:
    -- Q<n>: <question>
    <SQL, one or more lines, ending with ;>
"""
import os
import re
from pathlib import Path

DEFAULT_FILE = Path(os.getenv(
    "AI_EXAMPLES_FILE",
    Path(__file__).resolve().parent.parent / "database" / "04_sample_questions.sql"))


def load_examples(path=DEFAULT_FILE):
    examples, question, sql_lines = [], None, []
    for line in Path(path).read_text().splitlines():
        m = re.match(r"--\s*Q\d+:\s*(.+)", line)
        if m:
            question, sql_lines = m.group(1).strip(), []
        elif question and not line.startswith("--") and line.strip():
            sql_lines.append(line)
            if line.rstrip().endswith(";"):
                examples.append({"question": question, "sql": "\n".join(sql_lines).rstrip(";")})
                question = None
    return examples
