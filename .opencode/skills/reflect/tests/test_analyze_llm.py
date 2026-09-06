"""Tests for LLM integration."""
from unittest.mock import patch, MagicMock
from reflect.scripts.lib.analyze import call_llm
from reflect.scripts.lib.config import ReflectConfig


def test_call_llm_invokes_opencode():
    cfg = ReflectConfig.from_dict({})
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Hello world")
        result = call_llm("test prompt", cfg)
        assert result == "Hello world"
        mock_run.assert_called_once()


def test_call_llm_redacts_secrets():
    cfg = ReflectConfig.from_dict({})
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        call_llm("Using sk-1234567890abcdefghij for API", cfg)
        called_args = str(mock_run.call_args)
        assert "sk-1234567890" not in called_args
        assert "[REDACTED]" in called_args
