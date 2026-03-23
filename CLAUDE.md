# Courier Agent — Build Plan

## Project Overview

**Courier Agent** is an MCP server + Claude skill that transforms the Claude Desktop app (or any MCP-compatible client) into a guided coding assistant. It gives Claude full read-only access to your codebase, structured task management via Beads, and constrained command execution for tests and verification — while deliberately preventing it from writing code. The result: Claude teaches you what to write, reviews what you wrote, runs your tests, and tracks progress — but you remain the developer.

### Architecture

```
┌─────────────────────────────────────┐
│         Claude Desktop App          │
│  (or any MCP-compatible client)     │
│                                     │
│  ┌───────────────┐ ┌─────────────┐ │
│  │  SKILL.md     │ │  MCP Tools  │ │
│  │  (behavior)   │ │  (access)   │ │
│  └───────────────┘ └──────┬──────┘ │
└───────────────────────────┼─────────┘
                            │ MCP Protocol (stdio)
                ┌───────────┴───────────┐
                │  courier-agent server │
                │  (Python binary)      │
                │                       │
                │  ┌─────────────────┐  │
                │  │ Codebase Tools  │  │
                │  │ (read-only)     │  │
                │  ├─────────────────┤  │
                │  │ Git Tools       │  │
                │  │ (read-only)     │  │
                │  ├─────────────────┤  │
                │  │ Beads Integration│ │
                │  │ (plan/track)    │  │
                │  ├─────────────────┤  │
                │  │ Review Tools    │  │
                │  │ (diff analysis) │  │
                │  ├─────────────────┤  │
                │  │ Run Tools       │  │
                │  │ (tests/lint/    │  │
                │  │  build only,    │  │
                │  │  human-approved)│  │
                │  └─────────────────┘  │
                └───────────────────────┘
                            │
                    ┌───────┴───────┐
                    │  Local FS     │
                    │  (read-only)  │
                    ├───────────────┤
                    │  Git repo     │
                    ├───────────────┤
                    │  Beads DB     │
                    │  (bd CLI)     │
                    └───────────────┘
```

### Core Principles

1. **Claude cannot write code to files.** No `edit_file`, no `create_file`, no `write_file` tools exist. The user writes all code.
2. **Claude can run verification commands.** Test runners, linters, type checkers, and build commands are allowed — with human-in-the-loop approval via MCP's built-in confirmation flow. Claude Desktop prompts the user before any command executes.
3. **Claude cannot use commands to generate or modify code.** The SKILL.md explicitly instructs Claude that `run_command` is for verification only — never for code generation, sed/awk edits, piping output to files, or any form of writing code through shell commands.
4. **The skill defines behavior. The server enforces access.** Together they create the guided experience.

---

## Tech Stack

- **Language**: Python 3.11+
- **MCP SDK**: `mcp` (official Anthropic Python SDK for MCP servers)
- **Transport**: stdio (local process, launched by Claude Desktop)
- **Task tracking**: Beads CLI (`bd`) — optional, installed separately
- **Git integration**: `gitpython` or subprocess calls to `git`
- **Distribution**: pip-installable package, single entry point

---

## Phase 1: Project Scaffolding

### 1.1 Initialize the project

```
courier-agent/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── courier_agent/
│       ├── __init__.py
│       ├── server.py          # MCP server entry point
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── codebase.py    # File reading, search, structure tools
│       │   ├── git_tools.py   # Git diff, blame, log tools
│       │   ├── plan.py        # Beads integration for task planning
│       │   ├── review.py      # Diff review and feedback tools
│       │   └── runner.py      # Constrained command execution (tests, lint, build)
│       └── utils/
│           ├── __init__.py
│           ├── file_utils.py  # Safe path resolution, gitignore filtering
│           └── git_utils.py   # Git subprocess helpers
├── skill/
│   └── courier-agent/
│       └── SKILL.md           # The Claude skill file
├── tests/
│   ├── test_codebase.py
│   ├── test_git_tools.py
│   ├── test_plan.py
│   ├── test_review.py
│   └── test_runner.py
└── scripts/
    └── install.sh             # Helper to add MCP config to Claude Desktop
```

### 1.2 pyproject.toml

```toml
[project]
name = "courier-agent"
version = "0.1.0"
description = "MCP server that turns Claude into a guided coding assistant — teaches, reviews, and verifies, but never writes code for you"
requires-python = ">=3.11"
dependencies = [
    "mcp",
    "gitpython",
]

[project.scripts]
courier-agent = "courier_agent.server:main"
```

### 1.3 Acceptance criteria
- [ ] Project installs with `pip install -e .`
- [ ] `courier-agent` command starts without error and outputs MCP handshake
- [ ] Skill file exists and has valid YAML frontmatter
- [ ] All directories and __init__.py files are in place

---

## Phase 2: Codebase Tools (Read-Only)

These give Claude the ability to understand and navigate the project.

### 2.1 `list_directory`

- **Purpose**: Show project structure
- **Parameters**: `path` (string, optional, defaults to project root), `depth` (int, optional, default 2), `show_hidden` (bool, optional, default false)
- **Returns**: Tree-formatted directory listing, respecting .gitignore
- **Notes**: Filter out node_modules, __pycache__, .git, venv, .venv, dist, build, etc by default

### 2.2 `read_file`

- **Purpose**: Read file contents
- **Parameters**: `path` (string, required), `start_line` (int, optional), `end_line` (int, optional)
- **Returns**: File contents with line numbers, plus metadata (size, total lines, language)
- **Notes**: Enforce project root boundary — paths cannot escape the project. Cap at 50KB with truncation notice. Detect and reject binary files gracefully.

### 2.3 `search_code`

- **Purpose**: Grep-style search across the codebase
- **Parameters**: `pattern` (string, required), `file_glob` (string, optional, e.g. "*.py"), `max_results` (int, optional, default 20)
- **Returns**: Matching lines with file paths and line numbers, respecting .gitignore
- **Notes**: Use ripgrep (`rg`) if available for performance, fall back to Python re-based search

### 2.4 `find_definition`

- **Purpose**: Find where a symbol is defined
- **Parameters**: `symbol` (string, required), `file_glob` (string, optional)
- **Returns**: File path, line number, and surrounding context (5 lines above and below)
- **Notes**: Simple regex-based for v1 — matches patterns like `def symbol`, `class Symbol`, `function symbol`, `const symbol`, `let symbol`, `var symbol`, `export`, etc. Not a full AST but good enough to be useful.

### 2.5 `get_file_info`

- **Purpose**: Get metadata about a file without reading its full contents
- **Parameters**: `path` (string, required)
- **Returns**: Size, line count, language (inferred from extension), last modified date

### 2.6 Acceptance criteria
- [ ] All tools enforce read-only access (no writes possible through any tool)
- [ ] All paths are resolved relative to project root and cannot escape it (path traversal protection)
- [ ] .gitignore patterns are respected in search and directory listing
- [ ] Large files are truncated with clear notice of truncation
- [ ] Binary files are detected and handled gracefully
- [ ] Each tool has unit tests

---

## Phase 3: Git Tools

These let Claude understand what the user has changed and the history of the code.

### 3.1 `get_git_diff`

- **Purpose**: See uncommitted changes (what the user just wrote)
- **Parameters**: `staged` (bool, optional, default false — shows unstaged changes), `file_path` (string, optional — filter to specific file)
- **Returns**: Unified diff output with file names
- **Notes**: This is the core tool for the "review my changes" workflow. Should work with both staged and unstaged changes.

### 3.2 `get_git_log`

- **Purpose**: Recent commit history
- **Parameters**: `count` (int, optional, default 10), `file_path` (string, optional — filter to specific file)
- **Returns**: Commit hash (short), author, date, message for each commit

### 3.3 `get_git_blame`

- **Purpose**: See who wrote what and when
- **Parameters**: `file_path` (string, required), `start_line` (int, optional), `end_line` (int, optional)
- **Returns**: Line-by-line blame with commit hash, author, date

### 3.4 `get_git_status`

- **Purpose**: Show working tree status
- **Parameters**: none
- **Returns**: Lists of modified, staged, untracked, and deleted files

### 3.5 Acceptance criteria
- [ ] All git tools are strictly read-only (no commit, push, checkout, reset, etc)
- [ ] Works in repos with no commits yet (fresh `git init`)
- [ ] Handles non-git directories gracefully (returns clear "not a git repository" error)
- [ ] Each tool has unit tests

---

## Phase 4: Beads Integration (Plan & Track)

These tools let Claude create and manage structured task plans through Beads. This entire phase is optional — the server works without Beads installed.

### 4.1 `create_plan`

- **Purpose**: Break a task into structured, dependency-ordered steps
- **Parameters**: `task_description` (string, required), `steps` (array of objects, each with `title`, `description`, `priority`, `dependencies` fields)
- **Returns**: Beads epic ID and list of created bead IDs with their titles
- **Notes**: Wraps `bd create` commands. Creates an epic for the overall task, then child beads for each step. Sets dependency links between steps where specified.

### 4.2 `get_current_step`

- **Purpose**: Get the next actionable task (highest priority with no uncompleted blockers)
- **Parameters**: none
- **Returns**: Bead ID, title, description, priority, and status. Returns from `bd ready --json`.
- **Notes**: If no steps are ready (all blocked or all done), return appropriate message

### 4.3 `get_plan_overview`

- **Purpose**: Show the full plan with all steps and their statuses
- **Parameters**: `epic_id` (string, optional — shows all epics if omitted)
- **Returns**: Tree of all beads with status (open, in_progress, closed) and dependency info
- **Notes**: Wraps `bd tree` or `bd list --json`

### 4.4 `update_step`

- **Purpose**: Mark a step as in-progress, completed, or skipped
- **Parameters**: `bead_id` (string, required), `action` (enum: "start", "complete", "skip"), `notes` (string, optional)
- **Returns**: Updated bead status
- **Notes**: "start" → `bd update --status in_progress`. "complete" → `bd close`. "skip" → `bd close` with a note indicating AI-assisted/skipped step.

### 4.5 Beads dependency handling

On server startup, check if `bd` CLI is in PATH.
- If found: all plan tools are active
- If not found: plan tools return a clear error with install instructions (`curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash`). All other tools (codebase, git, review, runner) work normally.

### 4.6 Acceptance criteria
- [ ] Plans create proper Beads epics with parent-child relationships and dependency chains
- [ ] `get_current_step` returns only unblocked tasks
- [ ] Server starts and all non-plan tools work when Beads is not installed
- [ ] Plan tools return helpful install instructions when Beads is missing
- [ ] Each tool has unit tests (mock `bd` CLI calls via subprocess)

---

## Phase 5: Review Tools

These power the "review my changes" workflow — the core learning loop.

### 5.1 `review_changes`

- **Purpose**: Gather all information Claude needs to review the user's code changes
- **Parameters**: `bead_id` (string, optional — if provided, scopes review to files relevant to that step)
- **Returns**: Structured object containing: the git diff, list of changed files with summaries, and if a bead_id is provided, the step's title and description for context
- **Notes**: This tool gathers information. Claude provides the actual review commentary using its judgment. The tool does NOT evaluate quality — it provides raw material.

### 5.2 `compare_with_context`

- **Purpose**: Show a changed file alongside its dependency files for broader context
- **Parameters**: `file_path` (string, required)
- **Returns**: The file's full current contents, its diff (if modified), and the contents of files it imports/requires/includes (resolved from import statements)
- **Notes**: Import resolution is best-effort — parse common import patterns (Python `import`/`from`, JS `import`/`require`, etc). Missing imports are noted but don't cause errors.

### 5.3 Acceptance criteria
- [ ] `review_changes` returns clean, parseable diff information
- [ ] `compare_with_context` resolves imports for at least Python and JavaScript/TypeScript
- [ ] Missing or unresolvable imports are handled gracefully (noted, not errored)
- [ ] Each tool has unit tests

---

## Phase 6: Command Runner (Constrained Execution)

This gives Claude the ability to run verification commands — tests, linters, type checkers, build steps — with human approval.

### 6.1 `run_command`

- **Purpose**: Execute verification and testing commands
- **Parameters**: `command` (string, required), `working_directory` (string, optional, defaults to project root), `timeout` (int, optional, default 120 seconds)
- **Returns**: stdout, stderr, exit code, and execution time
- **Notes**:
  - Commands execute in the project directory
  - MCP's built-in human-in-the-loop confirmation applies — Claude Desktop will prompt the user to approve before any command runs
  - Timeout prevents runaway processes
  - Command output is captured and returned, not streamed

### 6.2 Command safety layer

The server includes a configurable allowlist of command patterns. This is a defense-in-depth measure — the MCP confirmation dialog is the primary gate, but the allowlist catches obviously dangerous commands before they even reach the user for approval.

**Default allowlist** (regex patterns for the command prefix):
```
# Test runners
pytest, python -m pytest, npm test, npx jest, cargo test, go test,
make test, yarn test, bun test, php artisan test, ruby -e, rspec,
mix test, dotnet test, gradle test

# Linters and formatters (read-only / check mode)
ruff check, ruff format --check, flake8, pylint, mypy, pyright,
eslint, prettier --check, tsc --noEmit, rustfmt --check,
clippy, golangci-lint, rubocop, shellcheck

# Build/compile (verification)
python -m py_compile, npm run build, cargo build, cargo check,
go build, make, tsc, gcc -fsyntax-only, javac

# General verification
python -c, node -e, cat, head, tail, wc, file, which, echo,
ls, find (read-only), du, df
```

**Default denylist** (blocked even if they match allowlist — these are never sent to the user for approval):
```
# File modification
rm, mv, cp, mkdir, rmdir, touch, chmod, chown,
sed -i, awk (with output redirect), tee, truncate

# Code generation / file writing
>, >>, |.*>, python.*-o, curl.*-o, wget

# Dangerous operations
sudo, su, dd, mkfs, fdisk, kill, killall, pkill,
git push, git commit, git checkout, git reset, git rebase,
docker rm, docker rmi, pip install, npm install, apt, brew

# Network operations that could exfiltrate
curl -X POST, curl -d, wget --post
```

**Configuration**: Users can customize the allowlist/denylist via a `courier-agent.toml` config file in the project root or `~/.config/courier-agent/config.toml`:

```toml
[runner]
# Add custom allowed commands
extra_allowed = ["mvn test", "sbt test", "pnpm test"]

# Add custom denied commands
extra_denied = ["specific-dangerous-command"]

# Override timeout
timeout = 180
```

### 6.3 Acceptance criteria
- [ ] Allowed commands execute and return stdout/stderr/exit code
- [ ] Denied commands are rejected BEFORE reaching the MCP confirmation dialog, with clear explanation
- [ ] Commands that don't match allowlist or denylist are rejected with suggestion to add them to config
- [ ] Timeout kills long-running processes and returns partial output
- [ ] Output redirect operators (>, >>, |) in commands are detected and blocked
- [ ] Working directory is enforced within project root
- [ ] Each tool has unit tests (mock subprocess)

---

## Phase 7: MCP Server Wiring

Wire everything together into a functioning MCP server.

### 7.1 Server entry point (`server.py`)

- Initialize MCP server with stdio transport
- Register all tools with JSON Schema parameter definitions
- Route tool calls to appropriate handlers in the tools/ modules
- Include server metadata: name="courier-agent", version from package, description
- Accept project root as first CLI argument (default to cwd)
- On startup: detect available capabilities (git, beads, ripgrep) and log status

### 7.2 Auto-detection on startup

The server checks for and reports:
- **Project root**: from CLI argument or cwd
- **Git**: is this a git repo? (enables git tools)
- **Beads**: is `bd` in PATH? (enables plan tools)
- **Ripgrep**: is `rg` in PATH? (enables fast search, else Python fallback)
- **Config file**: is there a `courier-agent.toml`? (custom runner config)

### 7.3 Claude Desktop configuration

Users add to their `claude_desktop_config.json`:

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

### 7.4 Install helper script

`scripts/install.sh` that:
1. Installs the package via pip (or detects if already installed)
2. Detects Claude Desktop config file location:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
3. Prompts user for project path
4. Adds the MCP server entry to the config JSON (creates file if needed, merges if exists)
5. Copies SKILL.md to `~/.claude/skills/courier-agent/SKILL.md`
6. Prints status: what was installed, reminder to restart Claude Desktop, optional Beads install command

### 7.5 Acceptance criteria
- [ ] Server starts via stdio and completes MCP protocol handshake
- [ ] All registered tools appear in Claude Desktop's tool panel
- [ ] Tool calls route correctly and return proper JSON results
- [ ] Errors in tool handlers are caught and returned as MCP tool errors (server never crashes)
- [ ] Missing optional dependencies (Beads, ripgrep) degrade gracefully
- [ ] Install script works on macOS and Linux (Windows via WSL)

---

## Phase 8: The SKILL.md

The behavioral layer that tells Claude HOW to act when Courier Agent tools are available.

### 8.1 Location

- Installed globally to `~/.claude/skills/courier-agent/SKILL.md`
- Also included in repo at `skill/courier-agent/SKILL.md` for project-local use
- Follows the Agent Skills open standard for cross-tool compatibility

### 8.2 SKILL.md frontmatter

```yaml
---
name: courier-agent
description: >
  Guided coding assistant mode. Activates when the courier-agent MCP server is
  connected and the user wants to implement code with AI guidance. Use when the
  user says "guide me", "teach me", "walk me through", "let's build together",
  "help me implement", or invokes /courier-agent. Provides step-by-step
  instructions, code review, test verification, and architectural guidance
  WITHOUT writing code directly to files. The user writes all code.
---
```

### 8.3 Skill instructions must cover

**Identity and role:**
- You are a guided coding assistant called Courier Agent
- You help the user implement code by teaching, instructing, reviewing, and verifying
- You never write code to files — the user writes all code
- You are a senior pair programmer who is navigating while the user drives

**What you MAY provide in chat:**
- Function signatures and type hints
- Pseudocode (clearly labeled as pseudocode)
- Short code snippets (under 5 lines) to illustrate a specific pattern or syntax
- Import statements
- Terminal commands for the user to run
- Conceptual explanations with inline code references

**What you must NOT provide in chat:**
- Complete function implementations
- Complete class definitions
- Complete files or large code blocks (more than ~5 lines) that serve as a copy-paste implementation
- Any output that removes the need for the user to think through the implementation

**Teaching workflow (the core loop):**
1. User describes a task → use `create_plan` (if Beads available) to break it into dependency-ordered steps
2. For each step → explain WHAT needs to be built, WHERE in the codebase it goes, WHY this approach is chosen, and HOW to think about it conceptually
3. Provide the function/method signature → let the user implement the body
4. User says "review", "check", or "how'd I do" → use `review_changes` and `get_git_diff` to see their code, then give specific, line-referenced feedback
5. When the code looks good → use `run_command` to run relevant tests (with user approval) and verify it works
6. When verified → use `update_step` to mark the bead complete → advance to the next step

**Graduated hint system:**
- Level 1 (default): Conceptual direction — "think about what data structure would let you look up entries by key with O(1) time"
- Level 2 (user asks for more help): Specific approach — "use a dictionary comprehension, filtering entries where the timestamp is older than the TTL threshold"
- Level 3 (user asks again or says "I'm stuck"): Near-code hint — "the key expression would compare `entry.created_at + ttl < current_time`"
- Never jump straight to level 3 unless the user explicitly asks for the most detailed hint
- Reset hint level for each new step

**Command execution rules:**
- ONLY use `run_command` for verification: running tests, linting, type checking, building, or viewing output
- NEVER use `run_command` for code generation, file creation, sed/awk edits, piping to files, installing packages, or any operation that modifies the codebase
- ALWAYS explain to the user what command you're about to run and why before executing
- After test failures, help the user understand the failure — don't fix it for them

**Review behavior:**
- Reference specific line numbers from the diff
- Use `search_code` to compare against similar patterns elsewhere in the codebase
- Comment on: correctness, edge cases, error handling, performance, readability, naming
- Always acknowledge what's done well before suggesting improvements
- If something is wrong, explain WHY it's wrong and guide toward the fix — don't provide the fix

**Escape hatch:**
- If user says "just write this", "skip this step", "do it for me", or similar → acknowledge the request
- Since you cannot write to files, provide a complete code block in the chat that they can copy-paste
- Use `update_step` with action "skip" and note "AI-assisted" to track that this step was not user-implemented
- This is explicitly allowed and encouraged when appropriate — the goal is learning, not suffering
- No judgment for using the escape hatch

**Session continuity:**
- At session start, if Beads is available, check `get_plan_overview` for existing plans
- If plans exist, offer to continue where the user left off
- At natural stopping points, summarize what was accomplished and what's next
- If the user seems frustrated, offer to adjust the difficulty (more detailed hints, skip complex steps)

### 8.4 Acceptance criteria
- [ ] YAML frontmatter has name and description fields
- [ ] Follows Agent Skills open standard format
- [ ] Total skill content is under 5K tokens (fits in progressive disclosure budget)
- [ ] Manually tested: Claude follows teaching behavior when skill is active
- [ ] Manually tested: Claude uses `run_command` only for verification, not code modification
- [ ] Manually tested: graduated hint system works across multiple "give me a hint" requests
- [ ] Manually tested: escape hatch works and tracks step as AI-assisted

---

## Phase 9: Testing & Polish

### 9.1 Integration tests
- [ ] Full workflow: create plan → get step → user edits files → review changes → run tests → complete step → next step
- [ ] Server handles rapid sequential tool calls without errors
- [ ] Server handles malformed/missing parameters gracefully with clear error messages
- [ ] Beads-less mode: all non-plan tools function normally
- [ ] Git-less mode: all non-git tools function normally (fresh directory, no repo)

### 9.2 Edge cases to test
- [ ] Empty repository (no files at all)
- [ ] Git repo with no commits (fresh `git init`)
- [ ] Very large files (>1MB) — truncation with notice
- [ ] Binary files — detected and skipped with message
- [ ] Symlinks — followed only if target is within project root
- [ ] Deeply nested directories (>10 levels)
- [ ] Projects with no .gitignore
- [ ] Non-UTF-8 files — handled without crash
- [ ] Path traversal attempts (`../../etc/passwd`) — blocked
- [ ] Command injection attempts in `run_command` — blocked
- [ ] Extremely long command output — truncated with notice

### 9.3 Documentation
- [ ] README.md with:
  - What Courier Agent is and why it exists
  - Quick install (pip install + config snippet)
  - Example workflow walkthrough
  - Configuration reference (courier-agent.toml)
  - Optional dependencies (Beads, ripgrep)
- [ ] Screenshots or terminal recording of a guided session
- [ ] Troubleshooting section covering common MCP connection issues
- [ ] CONTRIBUTING.md for open source contributors

### 9.4 Distribution
- [ ] Published to PyPI as `courier-agent`
- [ ] `pip install courier-agent` installs cleanly
- [ ] `courier-agent --version` prints version
- [ ] `courier-agent --help` prints usage
- [ ] Install script handles Claude Desktop config on macOS and Linux
- [ ] Skill file included in package data and copied during install
- [ ] GitHub repo with CI (tests on push)

---

## Phase 10: Future Enhancements (Post-MVP)

Not part of initial build. Documented for future reference.

- **Semantic code search**: Vector embeddings via local model for smarter code discovery
- **AST-aware tools**: Real symbol resolution via tree-sitter for accurate definitions
- **Learning tracker**: Track which concepts the user masters quickly vs needs repeated help with; adapt over time
- **OpenCode custom agent**: Port as an OpenCode agent with `edit: deny` permissions for open-weight model users
- **Multi-client testing**: Verify with Cursor, Zed, Codex CLI, and other MCP-compatible clients
- **Plan visualization**: `get_plan_visual` tool returning a mermaid diagram of the dependency graph
- **Session memory**: Persist teaching context and user progress between conversations
- **Difficulty adaptation**: Automatically adjust hint granularity based on demonstrated skill level
- **Code quality metrics**: Track improvement in the user's code patterns over time
- **Custom teaching styles**: Configurable pedagogy — some users want Socratic questioning, others want direct instruction
- **Team mode**: Shared Beads plans where multiple developers work through steps, each guided independently
- **Web UI**: Optional browser-based dashboard showing plan progress, skill metrics, and session history

---

## Build Order Summary

| Phase | What | Depends On |
|-------|------|------------|
| 1 | Project scaffolding | Nothing |
| 2 | Codebase tools (read-only) | Phase 1 |
| 3 | Git tools (read-only) | Phase 1 |
| 4 | Beads integration (plan/track) | Phase 1 |
| 5 | Review tools | Phases 2, 3 |
| 6 | Command runner (constrained) | Phase 1 |
| 7 | MCP server wiring | Phases 2-6 |
| 8 | SKILL.md | Phase 7 |
| 9 | Testing & polish | Phase 8 |

Phases 2, 3, 4, and 6 can be built in parallel — they all depend only on Phase 1.

---

## Quick Start for Claude Code

Feed this plan to Claude Code to begin building:

```bash
# Option 1: Direct
claude "Read courier-agent-plan.md and let's start building. Begin with Phase 1."

# Option 2: With Beads tracking (eat your own dog food)
bd init
claude "Read courier-agent-plan.md. Create Beads epics for each phase, then start implementing Phase 1."
```

Work through phases sequentially (or parallelize 2/3/4/6). Each phase has acceptance criteria — verify all criteria are met before moving to the next phase.
