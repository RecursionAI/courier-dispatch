"""Tests for file_utils and git_utils."""

import subprocess
from pathlib import Path

import pytest

from courier_agent.utils.file_utils import (
    detect_language,
    get_file_metadata,
    get_gitignore_patterns,
    is_binary_file,
    resolve_safe_path,
    should_ignore,
    truncate_content,
)
from courier_agent.utils.git_utils import has_commits, is_git_repo, run_git


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with some files."""
    (tmp_path / "hello.py").write_text("print('hello')\n")
    (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02\x03")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.js").write_text("console.log('hi');\n")
    (tmp_path / ".gitignore").write_text("*.log\nbuild/\n__pycache__/\n")
    return tmp_path


# --- resolve_safe_path ---


class TestResolveSafePath:
    def test_relative_path(self, tmp_project):
        result = resolve_safe_path("hello.py", tmp_project)
        assert result == tmp_project / "hello.py"

    def test_subdirectory_path(self, tmp_project):
        result = resolve_safe_path("subdir/nested.js", tmp_project)
        assert result == tmp_project / "subdir" / "nested.js"

    def test_empty_path_returns_root(self, tmp_project):
        result = resolve_safe_path("", tmp_project)
        assert result == tmp_project.resolve()

    def test_dot_returns_root(self, tmp_project):
        result = resolve_safe_path(".", tmp_project)
        assert result == tmp_project.resolve()

    def test_path_traversal_blocked(self, tmp_project):
        with pytest.raises(ValueError, match="outside the project root"):
            resolve_safe_path("../../etc/passwd", tmp_project)

    def test_path_traversal_with_intermediate_dirs(self, tmp_project):
        with pytest.raises(ValueError, match="outside the project root"):
            resolve_safe_path("subdir/../../..", tmp_project)

    def test_absolute_path_within_root(self, tmp_project):
        abs_path = str(tmp_project / "hello.py")
        result = resolve_safe_path(abs_path, tmp_project)
        assert result == tmp_project / "hello.py"

    def test_absolute_path_outside_root(self, tmp_project):
        with pytest.raises(ValueError, match="outside the project root"):
            resolve_safe_path("/etc/passwd", tmp_project)


# --- is_binary_file ---


class TestIsBinaryFile:
    def test_text_file(self, tmp_project):
        assert is_binary_file(tmp_project / "hello.py") is False

    def test_binary_file(self, tmp_project):
        assert is_binary_file(tmp_project / "data.bin") is True

    def test_nonexistent_file(self, tmp_path):
        assert is_binary_file(tmp_path / "missing.txt") is False

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.txt"
        empty.write_text("")
        assert is_binary_file(empty) is False


# --- gitignore ---


class TestGitignorePatterns:
    def test_loads_gitignore(self, tmp_project):
        patterns = get_gitignore_patterns(tmp_project)
        assert "*.log" in patterns
        assert "build/" in patterns

    def test_includes_defaults(self, tmp_project):
        patterns = get_gitignore_patterns(tmp_project)
        assert "__pycache__" in patterns
        assert "node_modules" in patterns

    def test_no_gitignore(self, tmp_path):
        patterns = get_gitignore_patterns(tmp_path)
        # Should still have defaults
        assert len(patterns) > 0
        assert "__pycache__" in patterns


class TestShouldIgnore:
    def test_ignores_matching_name(self, tmp_project):
        patterns = get_gitignore_patterns(tmp_project)
        log_file = tmp_project / "app.log"
        assert should_ignore(log_file, tmp_project, patterns) is True

    def test_allows_non_matching(self, tmp_project):
        patterns = get_gitignore_patterns(tmp_project)
        assert should_ignore(tmp_project / "hello.py", tmp_project, patterns) is False

    def test_ignores_default_dirs(self, tmp_project):
        patterns = get_gitignore_patterns(tmp_project)
        pycache = tmp_project / "__pycache__"
        assert should_ignore(pycache, tmp_project, patterns) is True

    def test_ignores_node_modules(self, tmp_project):
        patterns = get_gitignore_patterns(tmp_project)
        nm = tmp_project / "node_modules"
        assert should_ignore(nm, tmp_project, patterns) is True


# --- detect_language ---


class TestDetectLanguage:
    def test_python(self, tmp_path):
        assert detect_language(tmp_path / "test.py") == "python"

    def test_javascript(self, tmp_path):
        assert detect_language(tmp_path / "app.js") == "javascript"

    def test_typescript(self, tmp_path):
        assert detect_language(tmp_path / "app.tsx") == "typescript"

    def test_unknown(self, tmp_path):
        assert detect_language(tmp_path / "data.xyz") == "unknown"

    def test_dockerfile(self, tmp_path):
        assert detect_language(tmp_path / "Dockerfile") == "dockerfile"

    def test_makefile(self, tmp_path):
        assert detect_language(tmp_path / "Makefile") == "makefile"


# --- truncate_content ---


class TestTruncateContent:
    def test_small_content_not_truncated(self):
        content = "hello world"
        result, truncated = truncate_content(content)
        assert result == content
        assert truncated is False

    def test_large_content_truncated(self):
        content = "line\n" * 20_000  # ~100KB
        result, truncated = truncate_content(content, max_bytes=1000)
        assert truncated is True
        assert len(result.encode("utf-8")) <= 1000

    def test_truncation_at_line_boundary(self):
        content = "abcdef\n" * 100
        result, truncated = truncate_content(content, max_bytes=50)
        assert truncated is True
        assert result.endswith("\n") or result.endswith("f")


# --- get_file_metadata ---


class TestGetFileMetadata:
    def test_text_file_metadata(self, tmp_project):
        meta = get_file_metadata(tmp_project / "hello.py")
        assert meta["language"] == "python"
        assert meta["line_count"] == 1
        assert meta["size"] > 0
        assert "last_modified" in meta

    def test_size_display(self, tmp_project):
        meta = get_file_metadata(tmp_project / "hello.py")
        assert "B" in meta["size_display"] or "KB" in meta["size_display"]


# --- git utils ---


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with a commit."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True,
    )
    (tmp_path / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, capture_output=True,
    )
    return tmp_path


class TestIsGitRepo:
    def test_is_git_repo(self, git_repo):
        assert is_git_repo(git_repo) is True

    def test_not_git_repo(self, tmp_path):
        assert is_git_repo(tmp_path) is False


class TestHasCommits:
    def test_has_commits(self, git_repo):
        assert has_commits(git_repo) is True

    def test_no_commits(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        assert has_commits(tmp_path) is False


class TestRunGit:
    def test_run_git_status(self, git_repo):
        result = run_git(["status", "--porcelain"], git_repo)
        assert isinstance(result, str)

    def test_run_git_log(self, git_repo):
        result = run_git(["log", "--oneline", "-1"], git_repo)
        assert "init" in result

    def test_not_git_repo_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not a git repository"):
            run_git(["status"], tmp_path)

    def test_bad_command_raises(self, git_repo):
        with pytest.raises(RuntimeError, match="Git command failed"):
            run_git(["not-a-command"], git_repo)
