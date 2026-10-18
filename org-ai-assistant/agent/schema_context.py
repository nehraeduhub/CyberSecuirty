"""Builds the schema description the LLM sees, straight from the database.

Only the ai_views schema is described, using the COMMENT ON text. Writing
good comments on the real database is the main way to "teach" the model.
"""
import psycopg

_QUERY = """
SELECT c.relname, obj_description(c.oid, 'pg_class'),
       a.attname, format_type(a.atttypid, a.atttypmod), col_description(c.oid, a.attnum)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname = 'ai_views' AND c.relkind IN ('v', 'm', 'r')
ORDER BY c.relname, a.attnum
"""


def load_schema(dsn):
    """Returns {view_name: {"comment": str, "columns": [(name, type, comment)]}}."""
    views = {}
    with psycopg.connect(dsn) as conn:
        for view, vcomment, col, ctype, ccomment in conn.execute(_QUERY):
            v = views.setdefault(view, {"comment": vcomment or "", "columns": []})
            v["columns"].append((col, ctype, ccomment or ""))
    return views


def schema_as_text(views):
    """Compact text form. Short prompts matter a lot on CPU-only servers."""
    out = []
    for name, v in views.items():
        cols = ", ".join(f"{c} {t}" + (f" -- {cc}" if cc else "") for c, t, cc in v["columns"])
        out.append(f"ai_views.{name}" + (f"  /* {v['comment']} */" if v["comment"] else "") + f"\n  ({cols})")
    return "\n".join(out)
