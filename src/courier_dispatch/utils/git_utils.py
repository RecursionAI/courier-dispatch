"""Git utility functions: repo detection and subprocess helpers."""

import subprocess
from pathlib import Path


def is_git_repo(project_root: Path) -> bool:
    """Check if the given directory is inside a git repository.

    Args:
        project_root: Directory to check.

    Returns:
        True if it's a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def has_commits(project_root: Path) -> bool:
    """Check if the git repository has any commits.

    Args:
        project_root: The project root directory.

    Returns:
        True if the repo has at least one commit.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_git(args: list[str], project_root: Path) -> str:
    """Run a git command and return its stdout.

    Args:
        args: Git command arguments (without 'git' prefix).
        project_root: Working directory for the command.

    Returns:
        The command's stdout as a string.

    Raises:
        RuntimeError: If the git command fails.
        ValueError: If the directory is not a git repository.
    """
    if not is_git_repo(project_root):
        raise ValueError(f"'{project_root}' is not a git repository")

    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError("git is not installed or not in PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Git command timed out: git {' '.join(args)}")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"Git command failed: git {' '.join(args)}\n{stderr}")

    return result.stdout
