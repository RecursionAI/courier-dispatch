# Courier Agent

MCP server that turns Claude into a guided coding assistant — teaches, reviews, and verifies, but never writes code for you.

## What It Does

Courier Agent gives Claude read-only access to your codebase, structured task management, and constrained command execution. Claude teaches you what to write, reviews what you wrote, runs your tests, and tracks progress — but you remain the developer.

**Core principle:** Claude cannot write code to files. You write all the code.

## Quick Install

```bash
pip install courier-agent
```

Or install from source:

```bash
git clone https://github.com/your-org/courier-agent.git
cd courier-agent
pip install -e .
```

## Claude Desktop Setup

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "courier-agent": {
      "command": "courier-agent",
      "args": ["/path/to/your/project"]
    }
  }
}
```

Or use the install helper:

```bash
./scripts/install.sh
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

Create `courier-agent.toml` in your project root:

```toml
[runner]
extra_allowed = ["pnpm test", "mvn test"]
extra_denied = ["specific-dangerous-command"]
timeout = 180
```

## Optional Dependencies

- **[Beads](https://github.com/steveyegge/beads)** — Structured task tracking
- **[ripgrep](https://github.com/BurntSushi/ripgrep)** — Faster code search

## Development

```bash
uv sync
uv run pytest tests/ -v
```

## License

Apache 2.0
