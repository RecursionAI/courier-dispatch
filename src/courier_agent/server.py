"""Courier Agent MCP server entry point."""

import sys
import logging
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("courier-agent")

mcp = FastMCP("courier-agent")

PROJECT_ROOT: Path = Path.cwd()


def get_project_root() -> Path:
    """Return the current project root path."""
    return PROJECT_ROOT


def _detect_capabilities() -> dict[str, bool]:
    """Check for optional dependencies and log their availability."""
    caps = {
        "git": (PROJECT_ROOT / ".git").exists(),
        "beads": shutil.which("bd") is not None,
        "ripgrep": shutil.which("rg") is not None,
        "config": (PROJECT_ROOT / "courier-agent.toml").exists(),
    }
    for name, available in caps.items():
        status = "available" if available else "not found"
        logger.info(f"{name}: {status}")
    return caps


def main():
    """Start the Courier Agent MCP server."""
    global PROJECT_ROOT

    if "--version" in sys.argv:
        from courier_agent import __version__

        print(f"courier-agent {__version__}")
        return

    if "--help" in sys.argv:
        print("Usage: courier-agent [PROJECT_ROOT]")
        print("  Starts the Courier Agent MCP server over stdio.")
        print()
        print("Options:")
        print("  --version  Show version and exit")
        print("  --help     Show this help and exit")
        return

    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        PROJECT_ROOT = Path(sys.argv[1]).resolve()
    else:
        PROJECT_ROOT = Path.cwd()

    if not PROJECT_ROOT.is_dir():
        print(f"Error: {PROJECT_ROOT} is not a directory", file=sys.stderr)
        sys.exit(1)

    _detect_capabilities()

    # Register all tool groups
    from courier_agent.tools.codebase import register_tools as reg_codebase
    from courier_agent.tools.git_tools import register_tools as reg_git
    from courier_agent.tools.plan import register_tools as reg_plan
    from courier_agent.tools.review import register_tools as reg_review
    from courier_agent.tools.runner import register_tools as reg_runner

    reg_codebase(mcp, get_project_root)
    reg_git(mcp, get_project_root)
    reg_plan(mcp, get_project_root)
    reg_review(mcp, get_project_root)
    reg_runner(mcp, get_project_root)

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
