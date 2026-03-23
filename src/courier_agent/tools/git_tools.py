"""Git read-only tools: diff, log, blame, status."""

from collections.abc import Callable
from pathlib import Path

from courier_agent.utils.file_utils import resolve_safe_path
from courier_agent.utils.git_utils import has_commits, is_git_repo, run_git


def register_tools(mcp, get_project_root: Callable[[], Path]):
    """Register git tools with the MCP server."""

    def _require_git(root: Path) -> str | None:
        """Return an error message if not a git repo, else None."""
        if not is_git_repo(root):
            return "Error: Not a git repository. Git tools require a git-initialized project."
        return None

    @mcp.tool()
    def get_git_diff(
        staged: bool = False,
        file_path: str = "",
    ) -> str:
        """Show uncommitted changes (unified diff).

        Args:
            staged: If true, show staged changes. If false (default), show unstaged changes.
            file_path: Optional file path to filter the diff to a specific file.
        """
        root = get_project_root()
        if err := _require_git(root):
            return err

        args = ["diff"]
        if staged:
            args.append("--cached")

        if file_path:
            resolved = resolve_safe_path(file_path, root)
            args.extend(["--", str(resolved)])

        try:
            output = run_git(args, root)
        except RuntimeError as e:
            return f"Error: {e}"

        if not output.strip():
            kind = "staged" if staged else "unstaged"
            return f"No {kind} changes."

        return output

    @mcp.tool()
    def get_git_log(
        count: int = 10,
        file_path: str = "",
    ) -> str:
        """Show recent commit history.

        Args:
            count: Number of commits to show (default: 10).
            file_path: Optional file path to filter history to a specific file.
        """
        root = get_project_root()
        if err := _require_git(root):
            return err

        if not has_commits(root):
            return "No commits yet."

        args = [
            "log",
            f"-n{count}",
            "--format=%h  %an  %ar  %s",
        ]

        if file_path:
            resolved = resolve_safe_path(file_path, root)
            args.extend(["--", str(resolved)])

        try:
            output = run_git(args, root)
        except RuntimeError as e:
            return f"Error: {e}"

        return output.strip() or "No commits found."

    @mcp.tool()
    def get_git_blame(
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """Show line-by-line blame (who wrote what and when).

        Args:
            file_path: File path relative to project root.
            start_line: Optional start line (1-based).
            end_line: Optional end line (1-based, inclusive).
        """
        root = get_project_root()
        if err := _require_git(root):
            return err

        if not has_commits(root):
            return "No commits yet — blame requires at least one commit."

        resolved = resolve_safe_path(file_path, root)
        if not resolved.is_file():
            return f"Error: '{file_path}' is not a file"

        args = ["blame"]
        if start_line is not None and end_line is not None:
            args.extend(["-L", f"{start_line},{end_line}"])
        elif start_line is not None:
            args.extend(["-L", f"{start_line},"])

        args.append(str(resolved.relative_to(root)))

        try:
            output = run_git(args, root)
        except RuntimeError as e:
            return f"Error: {e}"

        return output.strip() or "No blame information available."

    @mcp.tool()
    def get_git_status() -> str:
        """Show working tree status: modified, staged, untracked, and deleted files."""
        root = get_project_root()
        if err := _require_git(root):
            return err

        try:
            output = run_git(["status", "--porcelain"], root)
        except RuntimeError as e:
            return f"Error: {e}"

        if not output.strip():
            return "Working tree clean — no changes."

        # Parse porcelain output into categories
        staged = []
        modified = []
        untracked = []
        deleted = []

        for line in output.splitlines():
            if len(line) < 4:
                continue
            index_status = line[0]
            work_status = line[1]
            filename = line[3:]

            if index_status == "?":
                untracked.append(filename)
            elif index_status == "D" or work_status == "D":
                deleted.append(filename)
            elif index_status in "MARC":
                staged.append(filename)
            if work_status == "M":
                modified.append(filename)

        sections = []
        if staged:
            sections.append("Staged:\n" + "\n".join(f"  {f}" for f in staged))
        if modified:
            sections.append("Modified (unstaged):\n" + "\n".join(f"  {f}" for f in modified))
        if untracked:
            sections.append("Untracked:\n" + "\n".join(f"  {f}" for f in untracked))
        if deleted:
            sections.append("Deleted:\n" + "\n".join(f"  {f}" for f in deleted))

        return "\n\n".join(sections)
