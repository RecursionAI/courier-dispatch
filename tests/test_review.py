"""Tests for review tools."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from courier_agent.tools.review import register_tools, _parse_imports, _resolve_import_path


@pytest.fixture
def git_project(tmp_path):
    """Create a git repo with files for review testing."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True,
    )

    # Create files
    (tmp_path / "main.py").write_text(
        "import os\n"
        "from utils import helper\n"
        "\n"
        "def main():\n"
        "    pass\n"
    )
    (tmp_path / "utils.py").write_text(
        "def helper():\n"
        "    return 42\n"
    )

    # JS files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.js").write_text(
        "import greet from './greet';\n"
        "const React = require('react');\n"
        "\n"
        "console.log(greet('world'));\n"
    )
    (tmp_path / "src" / "greet.js").write_text(
        "export default function greet(name) {\n"
        "  return `Hello ${name}`;\n"
        "}\n"
    )

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=tmp_path, capture_output=True,
    )

    return tmp_path


@pytest.fixture
def tools(git_project):
    """Register review tools."""
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


# --- Import parsing ---


class TestParseImports:
    def test_python_import(self):
        imports = _parse_imports("import os\nimport sys\n", "python")
        assert "os" in imports
        assert "sys" in imports

    def test_python_from_import(self):
        imports = _parse_imports("from os.path import join\n", "python")
        assert "os.path" in imports

    def test_python_relative_import(self):
        imports = _parse_imports("from utils import helper\n", "python")
        assert "utils" in imports

    def test_js_import(self):
        imports = _parse_imports("import greet from './greet';\n", "javascript")
        assert "./greet" in imports

    def test_js_require(self):
        imports = _parse_imports("const x = require('react');\n", "javascript")
        assert "react" in imports

    def test_ts_import(self):
        imports = _parse_imports(
            "import { Component } from './Component';\n", "typescript"
        )
        assert "./Component" in imports

    def test_unknown_language(self):
        imports = _parse_imports("some content\n", "rust")
        assert imports == []


class TestResolveImportPath:
    def test_resolve_python_module(self, git_project):
        result = _resolve_import_path(
            "utils", git_project / "main.py", git_project, "python"
        )
        assert result is not None
        assert result.name == "utils.py"

    def test_resolve_js_relative(self, git_project):
        result = _resolve_import_path(
            "./greet", git_project / "src" / "app.js", git_project, "javascript"
        )
        assert result is not None
        assert result.name == "greet.js"

    def test_unresolvable_import(self, git_project):
        result = _resolve_import_path(
            "react", git_project / "src" / "app.js", git_project, "javascript"
        )
        assert result is None

    def test_unresolvable_python_stdlib(self, git_project):
        result = _resolve_import_path(
            "os", git_project / "main.py", git_project, "python"
        )
        # os is stdlib, not in project — should be None
        assert result is None


# --- Review tools ---


class TestReviewChanges:
    def test_no_changes(self, tools):
        result = tools["review_changes"]()
        assert "No changes" in result or "clean" in result.lower()

    def test_with_changes(self, tools, git_project):
        (git_project / "main.py").write_text("# modified\n")
        result = tools["review_changes"]()
        assert "main.py" in result
        assert "modified" in result

    def test_staged_changes(self, tools, git_project):
        (git_project / "main.py").write_text("# staged\n")
        subprocess.run(["git", "add", "main.py"], cwd=git_project, capture_output=True)
        result = tools["review_changes"]()
        assert "Staged" in result
        assert "staged" in result


class TestCompareWithContext:
    def test_shows_file_content(self, tools):
        result = tools["compare_with_context"](file_path="main.py")
        assert "def main" in result
        assert "File: main.py" in result

    def test_resolves_python_imports(self, tools):
        result = tools["compare_with_context"](file_path="main.py")
        assert "utils" in result
        # Should show resolved import content
        assert "helper" in result

    def test_resolves_js_imports(self, tools):
        result = tools["compare_with_context"](file_path="src/app.js")
        assert "greet" in result.lower()

    def test_notes_unresolved_imports(self, tools):
        result = tools["compare_with_context"](file_path="main.py")
        # 'os' is stdlib, should be noted as unresolved
        assert "Unresolved" in result or "os" in result

    def test_nonexistent_file(self, tools):
        result = tools["compare_with_context"](file_path="missing.py")
        assert "Error" in result

    def test_binary_file_rejected(self, tools, git_project):
        (git_project / "data.bin").write_bytes(b"\x00\x01\x02")
        result = tools["compare_with_context"](file_path="data.bin")
        assert "binary" in result.lower()

    def test_shows_diff_when_modified(self, tools, git_project):
        (git_project / "main.py").write_text("# changed content\n")
        result = tools["compare_with_context"](file_path="main.py")
        assert "Changes" in result or "changed" in result
