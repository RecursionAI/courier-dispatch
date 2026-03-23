"""Tests for git tools."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from courier_agent.tools.git_tools import register_tools


@pytest.fixture
def git_project(tmp_path):
    """Create a temporary git repo with some commits."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path, capture_output=True,
    )

    # First commit
    (tmp_path / "hello.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=tmp_path, capture_output=True,
    )

    # Second commit
    (tmp_path / "world.py").write_text("print('world')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add world"],
        cwd=tmp_path, capture_output=True,
    )

    return tmp_path


@pytest.fixture
def tools(git_project):
    """Register tools and return a dict of tool functions."""
    mcp = MagicMock()
    registered = {}

    def mock_tool():
        def decorator(func):
            registered[func.__name__] = func
            return func
        return decorator

    mcp.tool = mock_tool
    register_tools(mcp, lambda: git_project)
    return registered


@pytest.fixture
def non_git_tools(tmp_path):
    """Register tools pointing at a non-git directory."""
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


class TestGetGitDiff:
    def test_no_changes(self, tools):
        result = tools["get_git_diff"]()
        assert "No unstaged changes" in result

    def test_unstaged_changes(self, tools, git_project):
        (git_project / "hello.py").write_text("print('modified')\n")
        result = tools["get_git_diff"]()
        assert "modified" in result
        assert "hello.py" in result

    def test_staged_changes(self, tools, git_project):
        (git_project / "hello.py").write_text("print('staged')\n")
        subprocess.run(["git", "add", "hello.py"], cwd=git_project, capture_output=True)
        result = tools["get_git_diff"](staged=True)
        assert "staged" in result

    def test_file_filter(self, tools, git_project):
        (git_project / "hello.py").write_text("print('changed')\n")
        (git_project / "world.py").write_text("print('also changed')\n")
        result = tools["get_git_diff"](file_path="hello.py")
        assert "hello.py" in result

    def test_not_git_repo(self, non_git_tools):
        result = non_git_tools["get_git_diff"]()
        assert "Error" in result or "not a git" in result.lower()


class TestGetGitLog:
    def test_shows_log(self, tools):
        result = tools["get_git_log"]()
        assert "initial commit" in result
        assert "add world" in result

    def test_count_limit(self, tools):
        result = tools["get_git_log"](count=1)
        assert "add world" in result
        assert "initial commit" not in result

    def test_file_filter(self, tools):
        result = tools["get_git_log"](file_path="hello.py")
        assert "initial commit" in result

    def test_not_git_repo(self, non_git_tools):
        result = non_git_tools["get_git_log"]()
        assert "Error" in result or "not a git" in result.lower()


class TestGetGitBlame:
    def test_blame_file(self, tools):
        result = tools["get_git_blame"](file_path="hello.py")
        assert "Test User" in result

    def test_blame_line_range(self, tools):
        result = tools["get_git_blame"](file_path="hello.py", start_line=1, end_line=1)
        assert "Test User" in result

    def test_nonexistent_file(self, tools):
        result = tools["get_git_blame"](file_path="missing.py")
        assert "Error" in result

    def test_not_git_repo(self, non_git_tools, tmp_path):
        (tmp_path / "test.py").write_text("x\n")
        result = non_git_tools["get_git_blame"](file_path="test.py")
        assert "Error" in result or "not a git" in result.lower()


class TestGetGitStatus:
    def test_clean_status(self, tools):
        result = tools["get_git_status"]()
        assert "clean" in result.lower()

    def test_modified_file(self, tools, git_project):
        (git_project / "hello.py").write_text("print('changed')\n")
        result = tools["get_git_status"]()
        assert "Modified" in result
        assert "hello.py" in result

    def test_untracked_file(self, tools, git_project):
        (git_project / "new.py").write_text("new\n")
        result = tools["get_git_status"]()
        assert "Untracked" in result
        assert "new.py" in result

    def test_staged_file(self, tools, git_project):
        (git_project / "hello.py").write_text("print('staged')\n")
        subprocess.run(["git", "add", "hello.py"], cwd=git_project, capture_output=True)
        result = tools["get_git_status"]()
        assert "Staged" in result

    def test_not_git_repo(self, non_git_tools):
        result = non_git_tools["get_git_status"]()
        assert "Error" in result or "not a git" in result.lower()


class TestFreshGitInit:
    """Test behavior with a git repo that has no commits."""

    def test_log_no_commits(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        mcp = MagicMock()
        registered = {}

        def mock_tool():
            def decorator(func):
                registered[func.__name__] = func
                return func
            return decorator

        mcp.tool = mock_tool
        register_tools(mcp, lambda: tmp_path)

        result = registered["get_git_log"]()
        assert "No commits" in result

    def test_blame_no_commits(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        (tmp_path / "test.py").write_text("x\n")

        mcp = MagicMock()
        registered = {}

        def mock_tool():
            def decorator(func):
                registered[func.__name__] = func
                return func
            return decorator

        mcp.tool = mock_tool
        register_tools(mcp, lambda: tmp_path)

        result = registered["get_git_blame"](file_path="test.py")
        assert "No commits" in result
