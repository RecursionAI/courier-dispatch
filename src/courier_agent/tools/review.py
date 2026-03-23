"""Review tools: change review and contextual comparison."""

import re
import shutil
from collections.abc import Callable
from pathlib import Path

from courier_agent.utils.file_utils import (
    is_binary_file,
    resolve_safe_path,
    truncate_content,
)
from courier_agent.utils.git_utils import has_commits, is_git_repo, run_git


def _parse_imports(content: str, language: str) -> list[str]:
    """Extract import paths from source code.

    Returns a list of module/file paths referenced by import statements.
    """
    imports = []

    if language == "python":
        # import foo / import foo.bar
        for match in re.finditer(r"^\s*import\s+([\w.]+)", content, re.MULTILINE):
            imports.append(match.group(1))
        # from foo import bar / from foo.bar import baz
        for match in re.finditer(r"^\s*from\s+([\w.]+)\s+import", content, re.MULTILINE):
            imports.append(match.group(1))

    elif language in ("javascript", "typescript"):
        # import ... from 'module' / import ... from "module"
        for match in re.finditer(
            r"""^\s*import\s+.*?\s+from\s+['"](.*?)['"]""", content, re.MULTILINE
        ):
            imports.append(match.group(1))
        # require('module') / require("module")
        for match in re.finditer(r"""require\(\s*['"](.*?)['"]\s*\)""", content):
            imports.append(match.group(1))

    return imports


def _resolve_import_path(
    import_path: str, source_file: Path, project_root: Path, language: str,
) -> Path | None:
    """Try to resolve an import path to an actual file.

    Returns the file Path if found, None otherwise.
    """
    if language == "python":
        # Convert dotted path to file path
        rel = import_path.replace(".", "/")
        candidates = [
            project_root / f"{rel}.py",
            project_root / rel / "__init__.py",
            project_root / "src" / f"{rel}.py",
            project_root / "src" / rel / "__init__.py",
        ]
    elif language in ("javascript", "typescript"):
        # Skip non-relative imports (npm packages)
        if not import_path.startswith("."):
            return None

        base_dir = source_file.parent
        candidates = []
        raw = base_dir / import_path

        # Try the path as-is and with common extensions
        for ext in ("", ".js", ".ts", ".tsx", ".jsx"):
            candidates.append(raw.with_suffix(ext) if ext else raw)

        # Try index files
        for idx in ("index.js", "index.ts", "index.tsx"):
            candidates.append(raw / idx)
    else:
        return None

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.is_file() and resolved.is_relative_to(project_root.resolve()):
                return resolved
        except (OSError, ValueError):
            continue

    return None


def register_tools(mcp, get_project_root: Callable[[], Path]):
    """Register review tools with the MCP server."""

    @mcp.tool()
    def review_changes(bead_id: str = "") -> str:
        """Gather all information needed to review the user's code changes.

        Returns the git diff, list of changed files, and optionally Beads step context.

        Args:
            bead_id: Optional bead/step ID to scope the review context.
        """
        root = get_project_root()

        if not is_git_repo(root):
            return "Error: Not a git repository. Review tools require git."

        sections = []

        # Get both staged and unstaged diffs
        try:
            unstaged = run_git(["diff"], root).strip()
            staged = run_git(["diff", "--cached"], root).strip()
        except RuntimeError as e:
            return f"Error getting diff: {e}"

        if not unstaged and not staged:
            return "No changes to review. Working tree is clean."

        # Changed files summary
        try:
            status = run_git(["status", "--porcelain"], root).strip()
        except RuntimeError:
            status = ""

        if status:
            sections.append("Changed files:\n" + status)

        if staged:
            sections.append(f"Staged changes:\n{'─' * 60}\n{staged}")
        if unstaged:
            sections.append(f"Unstaged changes:\n{'─' * 60}\n{unstaged}")

        # Beads context (if available and requested)
        if bead_id and shutil.which("bd"):
            try:
                import subprocess
                result = subprocess.run(
                    ["bd", "show", bead_id, "--json"],
                    cwd=root, capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    import json
                    data = json.loads(result.stdout)
                    sections.insert(0, (
                        f"Step context:\n"
                        f"  ID: {data.get('id', bead_id)}\n"
                        f"  Title: {data.get('title', 'Unknown')}\n"
                        f"  Description: {data.get('description', 'No description')}"
                    ))
            except Exception:
                pass  # Beads context is optional

        return "\n\n".join(sections)

    @mcp.tool()
    def compare_with_context(file_path: str) -> str:
        """Show a changed file alongside its imported dependencies for broader context.

        Args:
            file_path: Path to the file to analyze, relative to project root.
        """
        root = get_project_root()
        resolved = resolve_safe_path(file_path, root)

        if not resolved.is_file():
            return f"Error: '{file_path}' is not a file"

        if is_binary_file(resolved):
            return f"Error: '{file_path}' appears to be a binary file"

        sections = []

        # Read main file
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"Error reading '{file_path}': {e}"

        content, was_truncated = truncate_content(content)
        sections.append(f"File: {file_path}\n{'─' * 60}\n{content}")
        if was_truncated:
            sections[-1] += "\n\n⚠ File truncated at 50KB"

        # Get diff if in a git repo
        if is_git_repo(root) and has_commits(root):
            try:
                diff = run_git(["diff", "--", str(resolved)], root).strip()
                if not diff:
                    diff = run_git(["diff", "--cached", "--", str(resolved)], root).strip()
                if diff:
                    sections.append(f"Changes:\n{'─' * 60}\n{diff}")
                else:
                    sections.append("No uncommitted changes to this file.")
            except RuntimeError:
                pass

        # Resolve imports
        suffix = resolved.suffix.lower()
        if suffix == ".py":
            lang = "python"
        elif suffix in (".js", ".jsx"):
            lang = "javascript"
        elif suffix in (".ts", ".tsx"):
            lang = "typescript"
        else:
            lang = "other"

        imports = _parse_imports(content, lang)
        if imports:
            resolved_imports = []
            unresolved_imports = []

            for imp in imports:
                imp_path = _resolve_import_path(imp, resolved, root, lang)
                if imp_path:
                    resolved_imports.append((imp, imp_path))
                else:
                    unresolved_imports.append(imp)

            if resolved_imports:
                sections.append(f"Imported files ({len(resolved_imports)} resolved):")
                for imp_name, imp_path in resolved_imports:
                    try:
                        imp_content = imp_path.read_text(encoding="utf-8", errors="replace")
                        # Show first 50 lines of each imported file
                        lines = imp_content.splitlines()[:50]
                        preview = "\n".join(lines)
                        if len(imp_content.splitlines()) > 50:
                            preview += f"\n... ({len(imp_content.splitlines()) - 50} more lines)"
                        rel_path = imp_path.relative_to(root)
                        sections.append(
                            f"\n{imp_name} → {rel_path}\n{'─' * 40}\n{preview}"
                        )
                    except OSError:
                        unresolved_imports.append(imp_name)

            if unresolved_imports:
                sections.append(
                    f"Unresolved imports (likely external/stdlib): "
                    + ", ".join(unresolved_imports)
                )

        return "\n\n".join(sections)
