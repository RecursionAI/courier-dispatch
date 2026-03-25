"""Courier Dispatch MCP server entry point."""

import argparse
import sys
import logging
import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from courier_dispatch.utils.config import (
    get_config_value,
    load_config,
    set_config_value,
)

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
        "ngrok": get_config_value("ngrok.authtoken") is not None,
    }
    for name, available in caps.items():
        status = "available" if available else "not found"
        logger.info(f"{name}: {status}")
    return caps


def _handle_config(args: argparse.Namespace) -> None:
    """Handle the 'config' subcommand."""
    if args.config_action == "set":
        set_config_value(args.key, args.value)
        print(f"Set {args.key}")
    elif args.config_action == "get":
        value = get_config_value(args.key)
        if value is None:
            print(f"{args.key} is not set")
            sys.exit(1)
        else:
            print(value)
    elif args.config_action == "list":
        data = load_config()
        if not data:
            print("No configuration set.")
            return
        _print_config(data)


def _print_config(data: dict, prefix: str = "") -> None:
    """Print config dict in dot-notation format."""
    for key, value in data.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            _print_config(value, full_key)
        else:
            display = "********" if "token" in full_key or "auth" in full_key else value
            print(f"{full_key} = {display}")


def _start_server(args: argparse.Namespace) -> None:
    """Start the MCP server (default action)."""
    global PROJECT_ROOT

    PROJECT_ROOT = Path(args.project_root).resolve()

    if not PROJECT_ROOT.is_dir():
        print(f"Error: {PROJECT_ROOT} is not a directory", file=sys.stderr)
        sys.exit(1)

    caps = _detect_capabilities()

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

    # Start ngrok tunnel if configured
    tunnel_url = None
    if caps["ngrok"]:
        authtoken = get_config_value("ngrok.authtoken")
        domain = get_config_value("ngrok.domain")
        try:
            from courier_dispatch.utils.tunnel import start_tunnel

            tunnel_url = start_tunnel(args.port, authtoken, domain)
            print(f"ngrok tunnel: {tunnel_url}/sse")
        except Exception as e:
            print(f"Warning: ngrok tunnel failed: {e}", file=sys.stderr)
            print("Continuing with local server only.", file=sys.stderr)

    print(f"Courier Dispatch running on http://{args.host}:{args.port}/sse")

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport="sse")


def _add_serve_args(parser: argparse.ArgumentParser) -> None:
    """Add server arguments to a parser."""
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


def main():
    """Dispatch CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="dispatch",
        description="Courier Dispatch — MCP server for guided coding assistance",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    subparsers = parser.add_subparsers(dest="command")

    # -- config subcommand --
    config_parser = subparsers.add_parser("config", help="Manage configuration")
    config_sub = config_parser.add_subparsers(dest="config_action")

    set_parser = config_sub.add_parser("set", help="Set a config value")
    set_parser.add_argument("key", help="Config key (e.g., ngrok.authtoken)")
    set_parser.add_argument("value", help="Config value")

    get_parser = config_sub.add_parser("get", help="Get a config value")
    get_parser.add_argument("key", help="Config key (e.g., ngrok.authtoken)")

    config_sub.add_parser("list", help="List all config values")

    # -- serve subcommand (also the default) --
    serve_parser = subparsers.add_parser("serve", help="Start the MCP server")
    _add_serve_args(serve_parser)

    # If no subcommand given, we parse as serve — check for that case
    # by trying to parse and falling back if the first positional looks like a path
    args, remaining = parser.parse_known_args()

    if args.version:
        from courier_dispatch import __version__

        print(f"dispatch {__version__}")
        return

    if args.command == "config":
        if not args.config_action:
            config_parser.print_help()
            return
        _handle_config(args)
    elif args.command == "serve":
        _start_server(args)
    else:
        # No subcommand — treat all args as serve args
        serve_fallback = argparse.ArgumentParser(prog="dispatch")
        _add_serve_args(serve_fallback)
        serve_args = serve_fallback.parse_args(sys.argv[1:])
        _start_server(serve_args)


if __name__ == "__main__":
    main()
