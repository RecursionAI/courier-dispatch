# Courier Dispatch

MCP server that turns any AI chat app into a guided coding assistant — teaches, reviews, and verifies, but never writes code for you.

## What It Does

Courier Dispatch gives your AI assistant read-only access to your codebase, structured task management, and constrained command execution. The AI teaches you what to write, reviews what you wrote, runs your tests, and tracks progress — but you remain the developer.

**Core principle:** The AI cannot write code to files. You write all the code.

## Install

```bash
git clone https://github.com/recursion-ai/courier-dispatch.git
cd courier-dispatch
pip install -e .
```

This makes the `dispatch` command available globally.

## Quick Start

```bash
# In any project directory
dispatch

# Or specify a project path and port
dispatch /path/to/project --port 9090
```

This starts an MCP server at `http://localhost:8080/sse` (default). Add that URL as a connector in your MCP-compatible chat app.

### Skill Setup (Claude Desktop)

To get the guided teaching behavior (graduated hints, code review workflow, escape hatch), install the skill:

```bash
mkdir -p ~/.claude/skills/dispatch
cp skill/dispatch/SKILL.md ~/.claude/skills/dispatch/SKILL.md
```

Restart Claude Desktop. The skill activates when you say "guide me", "teach me", or "help me implement".

### Options

```
dispatch [PROJECT_ROOT] [--host HOST] [--port PORT] [--version]

PROJECT_ROOT   Path to the project directory (default: current directory)
--host         Host to bind to (default: 0.0.0.0)
--port         Port to listen on (default: 8080)
--version      Show version and exit
```

## Tools

### Codebase (Read-Only)
- `list_directory` — Tree-formatted directory listing
- `read_file` — File contents with line numbers
- `search_code` — Grep-style search (uses ripgrep if available)
- `find_definition` — Find function/class/variable definitions
- `get_file_info` — File metadata without reading contents

### Git (Read-Only)
- `get_git_diff` — Uncommitted changes (staged/unstaged)
- `get_git_log` — Recent commit history
- `get_git_blame` — Line-by-line blame
- `get_git_status` — Working tree status

### Plan & Track (Beads, Optional)
- `create_plan` — Break tasks into dependency-ordered steps
- `get_current_step` — Next actionable task
- `get_plan_overview` — Full plan with statuses
- `update_step` — Mark steps as started/complete/skipped

### Review
- `review_changes` — Gather diff + context for code review
- `compare_with_context` — File + imports for broader context

### Command Runner (Constrained)
- `run_command` — Execute verification commands (tests, lint, build) with allowlist/denylist safety

## Configuration

Create `dispatch.toml` in your project root:

```toml
[runner]
extra_allowed = ["pnpm test", "mvn test"]
extra_denied = ["specific-dangerous-command"]
timeout = 180
```

## Optional Dependencies

- **[Beads](https://github.com/steveyegge/beads)** — Structured task tracking
- **[ripgrep](https://github.com/BurntSushi/ripgrep)** — Faster code search

## Standalone Binary

To build a single-file binary (no Python required on the target machine):

```bash
pip install -e ".[dev]"
./scripts/build.sh
# Binary at dist/dispatch
```

## Development

```bash
uv sync
uv run pytest tests/ -v
```

## License

Apache 2.0
