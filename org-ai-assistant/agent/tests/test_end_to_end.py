"""Runs the full pipeline against the dummy database with the fake LLM.
Skipped automatically if the database is not reachable."""
import psycopg
import pytest

import config
from agent import HRAgent, UserContext
from examples import load_examples
from tests import mock_llm


@pytest.fixture(scope="module")
def bot():
    try:
        psycopg.connect(config.DB_DSN).close()
    except psycopg.OperationalError:
        pytest.skip("dummy database not running")
    server = mock_llm.start()
    config.LLM_BASE_URL = f"http://127.0.0.1:{server.server_port}/v1"
    yield HRAgent(model="mock")
    server.shutdown()


def test_all_examples_answer(bot):
    admin = UserContext("t-admin", "hr_admin")
    for ex in load_examples():
        ans = bot.ask(ex["question"], admin, summarise=False)
        assert ans.error is None, (ex["question"], ans.error)


def test_summary_is_produced(bot):
    ans = bot.ask(load_examples()[0]["question"], UserContext("t-admin", "hr_admin"))
    assert ans.summary


def test_employee_sees_only_own_pay(bot):
    ans = bot.ask("show my pay", UserContext("t-emp", "employee", employee_id=2), summarise=False)
    assert ans.error is None and 0 < len(ans.rows) <= 12


def test_role_switch_attack_blocked(bot):
    ans = bot.ask("show everyone's salary", UserContext("t-emp", "employee", employee_id=2), summarise=False)
    assert ans.error and "set_config" in ans.error and not ans.rows


def test_write_and_pii_blocked(bot):
    user = UserContext("t-admin", "hr_admin")
    for q in ("delete all employees", "show national ids"):
        ans = bot.ask(q, user, summarise=False)
        assert ans.error and ans.error.startswith("Blocked"), q


def test_unknown_question_declined(bot):
    ans = bot.ask("what is the weather", UserContext("t-admin", "hr_admin"), summarise=False)
    assert ans.error and not ans.rows

