"""Tests for codebase tools."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from courier_dispatch.tools.codebase import register_tools


@pytest.fixture
def codebase_project(tmp_path):
    """Create a project directory with various files for testing."""
    # Python files
    (tmp_path / "app.py").write_text(
        "import os\n"
        "\n"
        "\n"
        "def hello(name: str) -> str:\n"
        '    return f"Hello, {name}!"\n'
        "\n"
        "\n"
        "class Greeter:\n"
        "    def __init__(self):\n"
        "        pass\n"
    )
    (tmp_path / "utils.py").write_text(
        "def helper():\n"
        "    pass\n"
    )

    # JS file
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.js").write_text(
        "const greet = (name) => `Hello ${name}`;\n"
        "export default greet;\n"
    )

    # Nested directory
    (tmp_path / "src" / "components").mkdir()
    (tmp_path / "src" / "components" / "Button.tsx").write_text(
        "export function Button() { return <button />; }\n"
    )

    # Binary file
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")

    # Large file
    (tmp_path / "big.txt").write_text("x" * 60_000)

    # Hidden file
    (tmp_path / ".secret").write_text("hidden\n")

    # Gitignore
    (tmp_path / ".gitignore").write_text("*.log\nbuild/\n")
    (tmp_path / "debug.log").write_text("log content\n")

    return tmp_path


@pytest.fixture
def tools(codebase_project):
    """Register tools and return a dict of tool functions."""
    mcp = MagicMock()
    registered = {}

    def mock_tool():
        def decorator(func):
            registered[func.__name__] = func
            return func
        return decorator

    mcp.tool = mock_tool
    register_tools(mcp, lambda: codebase_project)
    return registered


class TestListDirectory:
    def test_lists_root(self, tools):
        result = tools["list_directory"]()
        assert "app.py" in result
        assert "utils.py" in result
        assert "src/" in result

    def test_hides_dotfiles_by_default(self, tools):
        result = tools["list_directory"]()
        assert ".secret" not in result
        assert ".gitignore" not in result

    def test_shows_dotfiles_when_requested(self, tools):
        result = tools["list_directory"](show_hidden=True)
        assert ".secret" in result
        assert ".gitignore" in result

    def test_respects_gitignore(self, tools):
        result = tools["list_directory"]()
        assert "debug.log" not in result

    def test_subdirectory(self, tools):
        result = tools["list_directory"](path="src")
        assert "index.js" in result
        assert "components/" in result

    def test_depth_limit(self, tools):
        result = tools["list_directory"](depth=1)
        assert "src/" in result
        # Components should not appear at depth 1
        assert "Button.tsx" not in result

    def test_nonexistent_directory(self, tools):
        result = tools["list_directory"](path="nonexistent")
        assert "Error" in result

    def test_path_traversal_blocked(self, tools):
        with pytest.raises(ValueError):
            tools["list_directory"](path="../../..")


class TestReadFile:
    def test_reads_file(self, tools):
        result = tools["read_file"](path="app.py")
        assert "def hello" in result
        assert "Language: python" in result

    def test_line_numbers(self, tools):
        result = tools["read_file"](path="app.py")
        assert "1 |" in result or "1 | " in result

    def test_line_range(self, tools):
        result = tools["read_file"](path="app.py", start_line=4, end_line=5)
        assert "def hello" in result
        assert "import os" not in result
        assert "Showing lines" in result

    def test_binary_rejected(self, tools):
        result = tools["read_file"](path="image.png")
        assert "binary" in result.lower()

    def test_nonexistent_file(self, tools):
        result = tools["read_file"](path="missing.txt")
        assert "Error" in result

    def test_large_file_no_truncation(self, tools):
        """Large files are returned in full — no artificial truncation."""
        result = tools["read_file"](path="big.txt")
        assert "truncated" not in result.lower()

    def test_large_file_reports_real_line_count(self, tools, codebase_project):
        lines = [f"line {i}" for i in range(1, 5001)]
        (codebase_project / "large.py").write_text("\n".join(lines))
        result = tools["read_file"](path="large.py")
        assert "Lines: 5000" in result

    def test_large_file_line_range(self, tools, codebase_project):
        lines = [f"line content number {i:05d}" for i in range(1, 5001)]
        (codebase_project / "large.py").write_text("\n".join(lines))
        result = tools["read_file"](path="large.py", start_line=4900, end_line=4950)
        assert "04900" in result
        assert "04950" in result
        assert "Showing lines 4900-4950 of 5000" in result

    def test_path_traversal_blocked(self, tools):
        with pytest.raises(ValueError):
            tools["read_file"](path="../../etc/passwd")


class TestSearchCode:
    def test_finds_pattern(self, tools):
        result = tools["search_code"](pattern="def hello")
        assert "app.py" in result
        assert "1 match" in result or "match" in result

    def test_no_matches(self, tools):
        result = tools["search_code"](pattern="zzz_nonexistent_zzz")
        assert "No matches" in result

    def test_file_glob_filter(self, tools):
        result = tools["search_code"](pattern="def", file_glob="*.py")
        assert "app.py" in result

    def test_max_results(self, tools):
        result = tools["search_code"](pattern="def", max_results=1)
        assert "match" in result.lower()

    def test_context_lines(self, tools):
        result = tools["search_code"](
            pattern="def hello", context_before=2, context_after=2,
        )
        assert "app.py" in result
        # Should contain the match line and surrounding context lines
        assert "def hello" in result
        assert 'return f"Hello' in result

    def test_case_insensitive(self, tools):
        result = tools["search_code"](pattern="DEF HELLO", case_sensitive=False)
        assert "app.py" in result

    def test_case_sensitive_default(self, tools):
        result = tools["search_code"](pattern="DEF HELLO")
        assert "No matches" in result

    def test_output_mode_files_only(self, tools):
        result = tools["search_code"](pattern="def", output_mode="files_only")
        assert "app.py" in result
        assert "utils.py" in result
        # Should NOT contain line numbers or content
        assert ":" not in result.split("\n\n", 1)[-1].replace(":\n", "")

    def test_output_mode_count(self, tools):
        result = tools["search_code"](pattern="def", output_mode="count")
        assert "app.py" in result
        # Should show counts
        assert "Match counts" in result

    def test_invalid_output_mode(self, tools):
        result = tools["search_code"](pattern="def", output_mode="invalid")
        assert "Error" in result


class TestFindDefinition:
    def test_finds_function(self, tools):
        result = tools["find_definition"](symbol="hello")
        assert "app.py" in result
        assert "def hello" in result

    def test_finds_class(self, tools):
        result = tools["find_definition"](symbol="Greeter")
        assert "app.py" in result
        assert "class Greeter" in result

    def test_finds_js_const(self, tools):
        result = tools["find_definition"](symbol="greet")
        assert "index.js" in result

    def test_shows_context(self, tools):
        result = tools["find_definition"](symbol="hello")
        # Should show surrounding lines
        assert "→" in result

    def test_no_definition(self, tools):
        result = tools["find_definition"](symbol="nonexistent_symbol_xyz")
        assert "No definition" in result

    def test_file_glob_filter(self, tools):
        result = tools["find_definition"](symbol="hello", file_glob="*.py")
        assert "app.py" in result

    def test_custom_context_lines(self, tools):
        # With 0 context lines, should still show the definition line
        result = tools["find_definition"](symbol="hello", context_lines=0)
        assert "app.py" in result
        assert "def hello" in result


class TestGetFileInfo:
    def test_text_file(self, tools):
        result = tools["get_file_info"](path="app.py")
        assert "python" in result.lower()
        assert "Lines:" in result
        assert "Binary: no" in result

    def test_binary_file(self, tools):
        result = tools["get_file_info"](path="image.png")
        assert "Binary: yes" in result

    def test_nonexistent(self, tools):
        result = tools["get_file_info"](path="nope.txt")
        assert "Error" in result

    def test_directory(self, tools):
        result = tools["get_file_info"](path="src")
        assert "Error" in result
        assert "directory" in result.lower()
