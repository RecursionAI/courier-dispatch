"""Constrained command runner: execute verification commands only."""

import re
import shlex
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from courier_dispatch.utils.config import load_project_config
from courier_dispatch.utils.file_utils import resolve_safe_path

# Default allowlist — regex patterns matched against the command prefix
DEFAULT_ALLOWED = [
    # Test runners
    r"pytest\b", r"python -m pytest\b", r"npm test\b", r"npx jest\b",
    r"cargo test\b", r"go test\b", r"make test\b", r"yarn test\b",
    r"bun test\b", r"php artisan test\b", r"ruby -e\b", r"rspec\b",
    r"mix test\b", r"dotnet test\b", r"gradle test\b",
    # Linters and formatters (read-only / check mode)
    r"ruff check\b", r"ruff format --check\b", r"flake8\b", r"pylint\b",
    r"mypy\b", r"pyright\b", r"eslint\b", r"prettier --check\b",
    r"tsc --noEmit\b", r"rustfmt --check\b", r"clippy\b",
    r"golangci-lint\b", r"rubocop\b", r"shellcheck\b",
    # Build/compile (verification)
    r"python -m py_compile\b", r"npm run build\b", r"cargo build\b",
    r"cargo check\b", r"go build\b", r"make\b", r"tsc\b",
    r"gcc -fsyntax-only\b", r"javac\b",
    # General verification
    r"python -c\b", r"node -e\b", r"cat\b", r"head\b", r"tail\b",
    r"wc\b", r"file\b", r"which\b", r"echo\b", r"ls\b", r"find\b",
    r"du\b", r"df\b",
]

# Default denylist — blocked even if they match allowlist
DEFAULT_DENIED = [
    # File modification
    r"\brm\b", r"\bmv\b", r"\bcp\b", r"\bmkdir\b", r"\brmdir\b",
    r"\btouch\b", r"\bchmod\b", r"\bchown\b",
    r"\bsed\s+-i\b", r"\btee\b", r"\btruncate\b",
    # Dangerous operations
    r"\bsudo\b", r"\bsu\b", r"\bdd\b", r"\bmkfs\b", r"\bfdisk\b",
    r"\bkill\b", r"\bkillall\b", r"\bpkill\b",
    r"\bgit\s+push\b", r"\bgit\s+commit\b", r"\bgit\s+checkout\b",
    r"\bgit\s+reset\b", r"\bgit\s+rebase\b",
    r"\bdocker\s+rm\b", r"\bdocker\s+rmi\b",
    r"\bpip\s+install\b", r"\bnpm\s+install\b", r"\bapt\b", r"\bbrew\b",
    # Network operations that could exfiltrate
    r"\bcurl\s+-X\s+POST\b", r"\bcurl\s+-d\b", r"\bwget\s+--post\b",
]

# Patterns for output redirection
REDIRECT_PATTERNS = [
    r">>",    # append
    r"(?<![12])>(?!&)",  # single redirect (not stderr redirect like 2>&1)
    r"\|",    # pipe
]


def _compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    """Compile a list of regex pattern strings."""
    return [re.compile(p) for p in patterns]


def _load_config(project_root: Path) -> dict:
    """Load runner config from dispatch.toml or user config."""
    return load_project_config(project_root)


def _check_command(
    command: str,
    allowed: list[re.Pattern],
    denied: list[re.Pattern],
) -> tuple[bool, str]:
    """Check if a command is allowed to run.

    Returns (is_allowed, reason).
    """
    # Check denylist first
    for pattern in denied:
        if pattern.search(command):
            return False, (
                f"Command blocked by safety filter (matched: {pattern.pattern}).\n"
                f"This command is in the denylist and cannot be executed."
            )

    # Check for output redirection
    for redir_pattern in REDIRECT_PATTERNS:
        if re.search(redir_pattern, command):
            return False, (
                "Command blocked: output redirection (>, >>, |) is not allowed.\n"
                "Commands must not write to files or pipe to other commands."
            )

    # Check allowlist
    for pattern in allowed:
        if pattern.search(command):
            return True, "OK"

    return False, (
        f"Command not in allowlist: '{command}'\n"
        "To allow this command, add it to the [runner] extra_allowed list "
        "in dispatch.toml in your project root."
    )


def register_tools(mcp, get_project_root: Callable[[], Path]):
    """Register command runner tools with the MCP server."""

    @mcp.tool()
    def run_command(
        command: str,
        working_directory: str = "",
        timeout: int = 120,
    ) -> str:
        """Execute a verification command (tests, linting, type checking, builds).

        Commands are checked against an allowlist before execution.
        Only verification and testing commands are permitted.

        Args:
            command: The command to execute.
            working_directory: Working directory relative to project root (default: project root).
            timeout: Maximum execution time in seconds (default: 120).
        """
        root = get_project_root()
        config = _load_config(root)

        # Build combined allow/deny lists
        allowed = _compile_patterns(DEFAULT_ALLOWED + config["extra_allowed"])
        denied = _compile_patterns(DEFAULT_DENIED + config["extra_denied"])

        # Check command safety
        is_allowed, reason = _check_command(command, allowed, denied)
        if not is_allowed:
            return f"Blocked: {reason}"

        # Resolve working directory
        if working_directory:
            cwd = resolve_safe_path(working_directory, root)
        else:
            cwd = root

        if not cwd.is_dir():
            return f"Error: Working directory '{working_directory}' does not exist"

        # Use configured timeout if user didn't override
        effective_timeout = timeout or config.get("timeout", 120)

        # Execute
        start = time.monotonic()
        try:
            result = subprocess.run(
                shlex.split(command),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
            elapsed = time.monotonic() - start

            output_parts = []
            if result.stdout.strip():
                output_parts.append(f"stdout:\n{result.stdout.strip()}")
            if result.stderr.strip():
                output_parts.append(f"stderr:\n{result.stderr.strip()}")

            output = "\n\n".join(output_parts) if output_parts else "(no output)"

            return (
                f"Exit code: {result.returncode}\n"
                f"Time: {elapsed:.2f}s\n\n"
                f"{output}"
            )

        except subprocess.TimeoutExpired as e:
            elapsed = time.monotonic() - start
            partial = ""
            if e.stdout:
                partial = f"\n\nPartial stdout:\n{e.stdout.strip()}"
            return (
                f"Command timed out after {effective_timeout}s.{partial}"
            )
        except FileNotFoundError:
            return f"Error: Command not found: '{shlex.split(command)[0]}'"
        except Exception as e:
            return f"Error executing command: {e}"
