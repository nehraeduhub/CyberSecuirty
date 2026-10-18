"""Checks AI-generated SQL before it reaches the database.

The database is the last line of defence (read-only role, views, row-level
security). This guard is the first: it rejects anything that is not a single
read-only SELECT over the allowed views, and any function not known to be
safe. In particular set_config() must never be allowed, because it could
change app.user_role and bypass row-level security.
"""
import sqlglot
from sqlglot import exp

# Postgres functions sqlglot does not model as typed expressions, that are safe.
# Everything else it parses as an unknown ("Anonymous") function is rejected.
SAFE_EXTRA_FUNCTIONS = {
    "age", "make_date", "make_interval", "date_part", "to_date", "to_number",
    "regexp_replace", "translate", "btrim", "ltrim", "rtrim", "starts_with",
    "width_bucket", "array_length", "cardinality", "unnest", "date_bin",
    "justify_days", "isfinite", "mode", "stddev", "variance", "every", "bool_or",
}

ALLOWED_SCHEMA = "ai_views"


class GuardError(ValueError):
    pass


def check_sql(sql, allowed_views, max_rows):
    """Returns safe SQL text to execute, or raises GuardError."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"SQL could not be parsed: {e}") from None
    if len(statements) != 1:
        raise GuardError("exactly one SQL statement is allowed")
    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise GuardError(f"only SELECT queries are allowed (got {tree.key.upper()})")

    for node in tree.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create,
                             exp.Drop, exp.Alter, exp.Command, exp.Set, exp.Copy)):
            raise GuardError(f"{node.key.upper()} is not allowed")
        if isinstance(node, exp.Into):
            raise GuardError("SELECT INTO is not allowed")
        if isinstance(node, exp.Lock):
            raise GuardError("row locking (FOR UPDATE/SHARE) is not allowed")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        name, schema = table.name.lower(), (table.db or "").lower()
        if not name:
            raise GuardError("table functions in FROM are not allowed")
        if not schema and name in cte_names:
            continue
        if schema not in ("", ALLOWED_SCHEMA) or table.catalog:
            raise GuardError(f"only {ALLOWED_SCHEMA}.* may be queried (found {table.sql()})")
        if name not in allowed_views:
            raise GuardError(f"unknown view {ALLOWED_SCHEMA}.{name}")
        table.set("db", exp.to_identifier(ALLOWED_SCHEMA))  # always fully qualified

    for func in tree.find_all(exp.Func):
        if isinstance(func, exp.Anonymous):
            fname = func.name.lower()
            if fname not in SAFE_EXTRA_FUNCTIONS:
                raise GuardError(f"function {fname}() is not allowed")
        elif isinstance(func, (exp.ExplodingGenerateSeries, exp.GenerateSeries)):
            raise GuardError("generate_series() is not allowed")

    # Enforce a row limit on the outermost query
    if isinstance(tree, exp.Select):
        limit = tree.args.get("limit")
        current = limit.expression if limit else None
        if not (isinstance(current, exp.Literal) and current.name.isdigit() and int(current.name) <= max_rows):
            tree = tree.limit(max_rows)
    else:
        tree = exp.select("*").from_(tree.subquery("q")).limit(max_rows)

    # Execute exactly what was checked, not the original text
    return tree.sql(dialect="postgres")
