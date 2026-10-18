"""check_setup.py against the dummy database and the fake LLM."""
import psycopg
import pytest

import check_setup
import config
from tests import mock_llm


@pytest.fixture()
def fake_llm(monkeypatch):
    try:
        psycopg.connect(config.DB_DSN).close()
    except psycopg.OperationalError:
        pytest.skip("dummy database not running")
    server = mock_llm.start()
    monkeypatch.setattr(config, "LLM_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setattr(config, "LLM_MODEL", "mock")
    monkeypatch.setattr(config, "AUDIT_DSN", "")
    monkeypatch.setattr(check_setup, "problems", 0)
    yield
    mock_llm.PROMPT_TOKENS_READ = None
    server.shutdown()


def run(capsys):
    with pytest.raises(SystemExit) as e:
        check_setup.main()
    return e.value.code, capsys.readouterr().out


def test_all_pass(fake_llm, capsys):
    code, out = run(capsys)
    assert code == 0 and "All checks passed" in out


def test_wrong_model_name(fake_llm, capsys, monkeypatch):
    monkeypatch.setattr(config, "LLM_MODEL", "llama-not-installed")
    code, out = run(capsys)
    assert code == 1 and "Installed: mock" in out


def test_prompt_cut_short_detected(fake_llm, capsys):
    mock_llm.PROMPT_TOKENS_READ = 1000
    code, out = run(capsys)
    assert code == 1 and "OLLAMA_CONTEXT_LENGTH" in out


def test_llm_unreachable(fake_llm, capsys, monkeypatch):
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://127.0.0.1:9/v1")
    code, out = run(capsys)
    assert code == 1 and "cannot reach" in out
