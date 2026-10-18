import pytest

from sql_guard import GuardError, check_sql

VIEWS = {"employees", "payroll", "training", "postings"}


def ok(sql, max_rows=100):
    return check_sql(sql, VIEWS, max_rows)


def blocked(sql):
    with pytest.raises(GuardError):
        ok(sql)


def test_simple_select_gets_limit():
    out = ok("SELECT department, count(*) FROM ai_views.employees GROUP BY department")
    assert "LIMIT 100" in out


def test_unqualified_view_is_qualified():
    assert "ai_views.employees" in ok("SELECT * FROM employees")


def test_small_limit_kept_large_limit_reduced():
    assert "LIMIT 5" in ok("SELECT * FROM ai_views.employees LIMIT 5")
    assert "LIMIT 100" in ok("SELECT * FROM ai_views.employees LIMIT 100000")


def test_cte_and_join_allowed():
    ok("""WITH p AS (SELECT employee_id, sum(net_pay) t FROM ai_views.payroll GROUP BY 1)
          SELECT e.emp_code, p.t FROM p JOIN ai_views.employees e USING (employee_id)""")


def test_union_wrapped_with_limit():
    out = ok("SELECT emp_code FROM ai_views.employees UNION SELECT emp_code FROM ai_views.employees")
    assert out.rstrip().endswith("LIMIT 100")


def test_common_functions_allowed():
    ok("""SELECT date_trunc('month', pay_month), extract(year FROM pay_month), round(avg(net_pay), 2),
                 age(paid_on), to_char(paid_on, 'YYYY-MM'), coalesce(other_deductions, 0)
          FROM ai_views.payroll GROUP BY 1, 2, 4, 5, 6""")


@pytest.mark.parametrize("sql", [
    "DELETE FROM ai_views.employees",
    "UPDATE ai_views.payroll SET net_pay = 0",
    "INSERT INTO ai_views.employees (emp_code) VALUES ('x')",
    "DROP TABLE core.employees",
    "SELECT 1; DELETE FROM ai_views.employees",
    "WITH d AS (DELETE FROM ai_views.payroll RETURNING *) SELECT * FROM d",
    "SELECT * INTO new_table FROM ai_views.employees",
    "SELECT * FROM ai_views.employees FOR UPDATE",
    "SET app.user_role = 'hr_admin'",
])
def test_writes_and_multi_statements_blocked(sql):
    blocked(sql)


@pytest.mark.parametrize("sql", [
    "SELECT national_id FROM core.employees",
    "SELECT * FROM pay.payroll",
    "SELECT * FROM pg_catalog.pg_shadow",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM ai_views.secret_view",
    "SELECT * FROM otherdb.ai_views.employees",
    "SELECT * FROM ai_views.employees e WHERE e.employee_id IN (SELECT employee_id FROM hr.disciplinary_actions)",
])
def test_other_schemas_blocked(sql):
    blocked(sql)


@pytest.mark.parametrize("sql", [
    # would switch the row-level-security role
    "SELECT set_config('app.user_role', 'hr_admin', true), * FROM ai_views.payroll",
    "SELECT * FROM ai_views.payroll WHERE set_config('app.user_role','hr_admin',true) IS NOT NULL",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT query_to_xml('select * from pay.payroll', true, true, '')",
    "SELECT dblink('host=x', 'select 1')",
    "SELECT pg_sleep(100)",
    "SELECT * FROM generate_series(1, 100000000)",
    "SELECT current_setting('app.user_role')",
])
def test_dangerous_functions_blocked(sql):
    blocked(sql)


def test_garbage_rejected():
    blocked("this is not sql at all )))")
