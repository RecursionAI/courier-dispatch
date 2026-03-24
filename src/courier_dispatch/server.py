"""Courier Dispatch MCP server entry point."""

import argparse
import sys
import logging
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("courier-dispatch")

mcp = FastMCP("courier-dispatch")

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
        "config": (PROJECT_ROOT / "dispatch.toml").exists(),
    }
    for name, available in caps.items():
        status = "available" if available else "not found"
        logger.info(f"{name}: {status}")
    return caps


def main():
    """Start the Courier Dispatch MCP server."""
    global PROJECT_ROOT

    parser = argparse.ArgumentParser(
        prog="dispatch",
        description="Courier Dispatch — MCP server for guided coding assistance",
    )
    parser.add_argument(
        "project_root",
        nargs="?",
        default=".",
        help="Path to the project directory (default: current directory)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the server to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    args = parser.parse_args()

    if args.version:
        from courier_dispatch import __version__

        print(f"dispatch {__version__}")
        return

    PROJECT_ROOT = Path(args.project_root).resolve()

    if not PROJECT_ROOT.is_dir():
        print(f"Error: {PROJECT_ROOT} is not a directory", file=sys.stderr)
        sys.exit(1)

    _detect_capabilities()

    # Register all tool groups
    from courier_dispatch.tools.codebase import register_tools as reg_codebase
    from courier_dispatch.tools.git_tools import register_tools as reg_git
    from courier_dispatch.tools.plan import register_tools as reg_plan
    from courier_dispatch.tools.review import register_tools as reg_review
    from courier_dispatch.tools.runner import register_tools as reg_runner

    reg_codebase(mcp, get_project_root)
    reg_git(mcp, get_project_root)
    reg_plan(mcp, get_project_root)
    reg_review(mcp, get_project_root)
    reg_runner(mcp, get_project_root)

    print(f"Courier Dispatch running on http://{args.host}:{args.port}/sse")

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()
