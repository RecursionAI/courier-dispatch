"""File utility functions: safe path resolution, binary detection, gitignore filtering."""

import fnmatch
from datetime import datetime, timezone
from pathlib import Path

# Directories always excluded from listings and searches
DEFAULT_IGNORE_DIRS = frozenset({
    "node_modules", "__pycache__", ".git", "venv", ".venv",
    "dist", "build", ".eggs", "*.egg-info", ".tox", ".nox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".next", ".nuxt", ".output", ".cache",
})

# Extension-to-language mapping
LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".m": "objective-c",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".md": "markdown",
    ".sql": "sql",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".vim": "vim",
    ".el": "elisp",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".scala": "scala",
    ".clj": "clojure",
    ".dart": "dart",
    ".tf": "terraform",
    ".dockerfile": "dockerfile",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
}


def resolve_safe_path(path: str, project_root: Path) -> Path:
    """Resolve a path relative to the project root, blocking path traversal.

    Args:
        path: The path to resolve (relative or absolute).
        project_root: The project root directory.

    Returns:
        The resolved absolute path.

    Raises:
        ValueError: If the resolved path escapes the project root.
    """
    project_root = project_root.resolve()

    if not path or path == ".":
        return project_root

    resolved = (project_root / path).resolve()

    if not resolved.is_relative_to(project_root):
        raise ValueError(
            f"Path '{path}' resolves outside the project root. "
            f"Access is restricted to {project_root}"
        )

    return resolved


def is_binary_file(path: Path) -> bool:
    """Check if a file is binary by looking for null bytes in the first 8KB.

    Args:
        path: Path to the file to check.

    Returns:
        True if the file appears to be binary.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, IOError):
        return False


def get_gitignore_patterns(project_root: Path) -> list[str]:
    """Parse .gitignore and return patterns, combined with default ignores.

    Args:
        project_root: The project root directory.

    Returns:
        List of gitignore-style patterns.
    """
    patterns = list(DEFAULT_IGNORE_DIRS)

    gitignore_path = project_root / ".gitignore"
    if gitignore_path.is_file():
        try:
            text = gitignore_path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    patterns.append(line)
        except OSError:
            pass

    return patterns


def should_ignore(path: Path, project_root: Path, ignore_patterns: list[str]) -> bool:
    """Check if a path matches any gitignore pattern.

    Args:
        path: The path to check.
        project_root: The project root directory.
        ignore_patterns: List of gitignore-style patterns.

    Returns:
        True if the path should be ignored.
    """
    try:
        rel_path = path.relative_to(project_root)
    except ValueError:
        return True

    rel_str = str(rel_path)
    name = path.name

    for pattern in ignore_patterns:
        # Strip trailing slash (directory-only indicator)
        clean_pattern = pattern.rstrip("/")

        # Match against the file/directory name
        if fnmatch.fnmatch(name, clean_pattern):
            return True

        # Match against the relative path
        if fnmatch.fnmatch(rel_str, clean_pattern):
            return True

        # Handle patterns with ** prefix
        if clean_pattern.startswith("**/"):
            suffix = clean_pattern[3:]
            if fnmatch.fnmatch(name, suffix) or fnmatch.fnmatch(rel_str, suffix):
                return True

        # Handle patterns with / — match against full relative path
        if "/" in clean_pattern:
            if fnmatch.fnmatch(rel_str, clean_pattern):
                return True
            # Also try matching with ** prefix for subdirectory matches
            if fnmatch.fnmatch(rel_str, f"**/{clean_pattern}"):
                return True

    return False


def detect_language(path: Path) -> str:
    """Detect the programming language of a file from its extension.

    Args:
        path: Path to the file.

    Returns:
        Language name string, or "unknown".
    """
    # Check for Dockerfile (no extension)
    if path.name == "Dockerfile" or path.name.startswith("Dockerfile."):
        return "dockerfile"
    if path.name == "Makefile":
        return "makefile"

    suffix = path.suffix.lower()
    return LANGUAGE_MAP.get(suffix, "unknown")


def truncate_content(content: str, max_bytes: int = 50_000) -> tuple[str, bool]:
    """Truncate content if it exceeds max_bytes.

    Args:
        content: The text content to potentially truncate.
        max_bytes: Maximum allowed size in bytes.

    Returns:
        Tuple of (content, was_truncated).
    """
    encoded = content.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return content, False

    # Truncate at byte boundary, then decode safely
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    # Find last complete line
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline]

    return truncated, True


def get_file_metadata(path: Path) -> dict:
    """Get metadata about a file.

    Args:
        path: Path to the file.

    Returns:
        Dict with size, line_count, language, and last_modified.
    """
    stat = path.stat()
    size = stat.st_size
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    language = detect_language(path)

    line_count = 0
    if not is_binary_file(path) and size > 0:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        except OSError:
            pass

    # Human-readable size
    if size < 1024:
        size_str = f"{size} B"
    elif size < 1024 * 1024:
        size_str = f"{size / 1024:.1f} KB"
    else:
        size_str = f"{size / (1024 * 1024):.1f} MB"

    return {
        "size": size,
        "size_display": size_str,
        "line_count": line_count,
        "language": language,
        "last_modified": modified.isoformat(),
    }
