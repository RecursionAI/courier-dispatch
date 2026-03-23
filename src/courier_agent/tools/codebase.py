"""Codebase read-only tools: directory listing, file reading, code search."""

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from courier_agent.utils.file_utils import (
    detect_language,
    get_file_metadata,
    get_gitignore_patterns,
    is_binary_file,
    resolve_safe_path,
    should_ignore,
    truncate_content,
)


def register_tools(mcp, get_project_root: Callable[[], Path]):
    """Register codebase tools with the MCP server."""

    @mcp.tool()
    def list_directory(
        path: str = "",
        depth: int = 2,
        show_hidden: bool = False,
    ) -> str:
        """List directory contents as a tree structure, respecting .gitignore.

        Args:
            path: Directory path relative to project root (default: root).
            depth: How many levels deep to show (default: 2).
            show_hidden: Whether to show hidden files/directories (default: false).
        """
        root = get_project_root()
        target = resolve_safe_path(path, root)

        if not target.is_dir():
            return f"Error: '{path}' is not a directory"

        ignore_patterns = get_gitignore_patterns(root)
        lines = []

        def _walk(dir_path: Path, prefix: str, current_depth: int):
            if current_depth > depth:
                return

            try:
                entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                lines.append(f"{prefix}[permission denied]")
                return

            # Filter entries
            visible = []
            for entry in entries:
                if not show_hidden and entry.name.startswith("."):
                    continue
                if should_ignore(entry, root, ignore_patterns):
                    continue
                visible.append(entry)

            for i, entry in enumerate(visible):
                is_last = i == len(visible) - 1
                connector = "└── " if is_last else "├── "
                suffix = "/" if entry.is_dir() else ""
                lines.append(f"{prefix}{connector}{entry.name}{suffix}")

                if entry.is_dir() and current_depth < depth:
                    extension = "    " if is_last else "│   "
                    _walk(entry, prefix + extension, current_depth + 1)

        rel = target.relative_to(root) if target != root else Path(".")
        lines.append(f"{rel}/")
        _walk(target, "", 1)

        return "\n".join(lines)

    @mcp.tool()
    def read_file(
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Read a file's contents with line numbers.

        Args:
            path: File path relative to project root.
            start_line: First line to read (1-based, optional).
            end_line: Last line to read (1-based, inclusive, optional).
        """
        root = get_project_root()
        resolved = resolve_safe_path(path, root)

        if not resolved.is_file():
            return f"Error: '{path}' is not a file"

        if is_binary_file(resolved):
            return f"Error: '{path}' appears to be a binary file"

        meta = get_file_metadata(resolved)

        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"Error reading '{path}': {e}"

        content, was_truncated = truncate_content(content)

        all_lines = content.splitlines()
        total_lines = len(all_lines)

        # Apply line range
        if start_line is not None or end_line is not None:
            start = max(1, start_line or 1)
            end = min(total_lines, end_line or total_lines)
            selected = all_lines[start - 1 : end]
            line_offset = start
        else:
            selected = all_lines
            line_offset = 1

        # Format with line numbers
        width = len(str(line_offset + len(selected)))
        numbered = []
        for i, line in enumerate(selected):
            num = line_offset + i
            numbered.append(f"{num:>{width}} | {line}")

        header = (
            f"File: {path}\n"
            f"Language: {meta['language']} | Size: {meta['size_display']} | Lines: {total_lines}\n"
            f"{'─' * 60}\n"
        )
        footer = ""
        if was_truncated:
            footer = f"\n{'─' * 60}\n⚠ File truncated at 50KB (total size: {meta['size_display']})"
        if start_line is not None or end_line is not None:
            footer += f"\nShowing lines {line_offset}-{line_offset + len(selected) - 1} of {total_lines}"

        return header + "\n".join(numbered) + footer

    @mcp.tool()
    def search_code(
        pattern: str,
        file_glob: str = "",
        max_results: int = 20,
    ) -> str:
        """Search for a pattern across the codebase (grep-style).

        Args:
            pattern: Regex pattern to search for.
            file_glob: Optional file glob filter (e.g., '*.py').
            max_results: Maximum number of results to return (default: 20).
        """
        root = get_project_root()

        # Try ripgrep first
        if shutil.which("rg"):
            return _search_with_ripgrep(pattern, file_glob, max_results, root)
        else:
            return _search_with_python(pattern, file_glob, max_results, root)

    def _search_with_ripgrep(
        pattern: str, file_glob: str, max_results: int, root: Path,
    ) -> str:
        cmd = [
            "rg", "--line-number", "--no-heading",
            "--max-count", str(max_results),
            "--color", "never",
        ]
        if file_glob:
            cmd.extend(["--glob", file_glob])
        cmd.append(pattern)

        try:
            result = subprocess.run(
                cmd, cwd=root, capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return "Error: Search timed out after 30 seconds"

        if result.returncode == 1:
            return "No matches found."
        if result.returncode > 1:
            return f"Search error: {result.stderr.strip()}"

        lines = result.stdout.strip().splitlines()
        if len(lines) > max_results:
            lines = lines[:max_results]

        count = len(lines)
        header = f"Found {count} match{'es' if count != 1 else ''} for '{pattern}':\n\n"
        return header + "\n".join(lines)

    def _search_with_python(
        pattern: str, file_glob: str, max_results: int, root: Path,
    ) -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        ignore_patterns = get_gitignore_patterns(root)
        matches = []

        for dirpath, dirnames, filenames in os.walk(root):
            dp = Path(dirpath)
            # Filter ignored directories in-place
            dirnames[:] = [
                d for d in dirnames
                if not should_ignore(dp / d, root, ignore_patterns)
                and not d.startswith(".")
            ]

            for fname in filenames:
                fpath = dp / fname
                if should_ignore(fpath, root, ignore_patterns):
                    continue
                if file_glob and not fpath.match(file_glob):
                    continue
                if is_binary_file(fpath):
                    continue

                try:
                    text = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                for line_num, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        rel = fpath.relative_to(root)
                        matches.append(f"{rel}:{line_num}: {line.strip()}")
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break

        if not matches:
            return "No matches found."

        count = len(matches)
        header = f"Found {count} match{'es' if count != 1 else ''} for '{pattern}':\n\n"
        return header + "\n".join(matches)

    @mcp.tool()
    def find_definition(
        symbol: str,
        file_glob: str = "",
    ) -> str:
        """Find where a symbol (function, class, variable) is defined.

        Args:
            symbol: The symbol name to search for.
            file_glob: Optional file glob filter (e.g., '*.py').
        """
        root = get_project_root()
        ignore_patterns = get_gitignore_patterns(root)

        # Patterns for common definition syntax
        definition_patterns = [
            rf"^\s*def\s+{re.escape(symbol)}\s*\(",                # Python function
            rf"^\s*async\s+def\s+{re.escape(symbol)}\s*\(",        # Python async
            rf"^\s*class\s+{re.escape(symbol)}[\s:(]",              # Python/JS class
            rf"^\s*function\s+{re.escape(symbol)}\s*\(",            # JS function
            rf"^\s*(const|let|var)\s+{re.escape(symbol)}\s*=",      # JS variable
            rf"^\s*export\s+(default\s+)?(function|class|const|let|var)\s+{re.escape(symbol)}", # JS export
            rf"^\s*(pub\s+)?fn\s+{re.escape(symbol)}\s*[<(]",      # Rust
            rf"^\s*func\s+{re.escape(symbol)}\s*\(",                # Go
            rf"^\s*(public|private|protected)?\s*(static\s+)?\w+\s+{re.escape(symbol)}\s*\(", # Java/C#
        ]
        combined = "|".join(f"({p})" for p in definition_patterns)
        regex = re.compile(combined)

        results = []
        context_lines = 5

        for dirpath, dirnames, filenames in os.walk(root):
            dp = Path(dirpath)
            dirnames[:] = [
                d for d in dirnames
                if not should_ignore(dp / d, root, ignore_patterns)
                and not d.startswith(".")
            ]

            for fname in filenames:
                fpath = dp / fname
                if should_ignore(fpath, root, ignore_patterns):
                    continue
                if file_glob and not fpath.match(file_glob):
                    continue
                if is_binary_file(fpath):
                    continue

                try:
                    lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue

                for line_num, line in enumerate(lines):
                    if regex.search(line):
                        rel = fpath.relative_to(root)
                        start = max(0, line_num - context_lines)
                        end = min(len(lines), line_num + context_lines + 1)

                        context = []
                        for i in range(start, end):
                            marker = "→ " if i == line_num else "  "
                            context.append(f"{marker}{i + 1:>4} | {lines[i]}")

                        results.append(
                            f"📍 {rel}:{line_num + 1}\n" + "\n".join(context)
                        )

        if not results:
            return f"No definition found for '{symbol}'"

        header = f"Found {len(results)} definition(s) for '{symbol}':\n\n"
        return header + "\n\n".join(results)

    @mcp.tool()
    def get_file_info(path: str) -> str:
        """Get metadata about a file without reading its full contents.

        Args:
            path: File path relative to project root.
        """
        root = get_project_root()
        resolved = resolve_safe_path(path, root)

        if not resolved.exists():
            return f"Error: '{path}' does not exist"

        if resolved.is_dir():
            return f"Error: '{path}' is a directory, not a file"

        meta = get_file_metadata(resolved)
        is_binary = is_binary_file(resolved)

        return (
            f"File: {path}\n"
            f"Size: {meta['size_display']} ({meta['size']:,} bytes)\n"
            f"Lines: {meta['line_count']}\n"
            f"Language: {meta['language']}\n"
            f"Binary: {'yes' if is_binary else 'no'}\n"
            f"Last modified: {meta['last_modified']}"
        )
