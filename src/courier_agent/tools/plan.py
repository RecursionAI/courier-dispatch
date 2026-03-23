"""Beads integration tools: plan creation and task tracking."""

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

BEADS_INSTALL_MSG = (
    "Beads CLI (`bd`) is not installed. Plan tools require Beads.\n\n"
    "Install Beads with:\n"
    "  curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash\n\n"
    "All other Courier Agent tools work without Beads."
)


def _beads_available() -> bool:
    """Check if the Beads CLI is available in PATH."""
    return shutil.which("bd") is not None


def _run_bd(args: list[str], cwd: Path) -> str:
    """Run a bd command and return stdout."""
    cmd = ["bd"] + args
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError(BEADS_INSTALL_MSG)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Beads command timed out: bd {' '.join(args)}")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"Beads command failed: bd {' '.join(args)}\n{stderr}")

    return result.stdout


def register_tools(mcp, get_project_root: Callable[[], Path]):
    """Register Beads plan tools with the MCP server."""

    @mcp.tool()
    def create_plan(task_description: str, steps: str) -> str:
        """Create a structured task plan using Beads.

        Break a task into dependency-ordered steps with an epic parent.

        Args:
            task_description: Overall task description (becomes the epic title).
            steps: JSON array of step objects, each with 'title', 'description',
                   'priority' (int), and 'dependencies' (list of step indices).
        """
        if not _beads_available():
            return BEADS_INSTALL_MSG

        root = get_project_root()

        try:
            step_list = json.loads(steps)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON for steps: {e}"

        if not isinstance(step_list, list) or not step_list:
            return "Error: 'steps' must be a non-empty JSON array of step objects."

        try:
            # Create the epic
            epic_output = _run_bd(["create", "--epic", task_description], root)
            epic_id = epic_output.strip().split()[-1] if epic_output.strip() else "unknown"

            # Create child beads for each step
            bead_ids = []
            for step in step_list:
                title = step.get("title", "Untitled step")
                description = step.get("description", "")
                priority = step.get("priority", 0)

                args = ["create", title]
                if description:
                    args.extend(["--description", description])
                if priority:
                    args.extend(["--priority", str(priority)])
                args.extend(["--parent", epic_id])

                output = _run_bd(args, root)
                bead_id = output.strip().split()[-1] if output.strip() else "unknown"
                bead_ids.append({"id": bead_id, "title": title})

            # Set up dependency links
            for i, step in enumerate(step_list):
                deps = step.get("dependencies", [])
                for dep_idx in deps:
                    if 0 <= dep_idx < len(bead_ids):
                        _run_bd(
                            ["update", bead_ids[i]["id"], "--blocked-by", bead_ids[dep_idx]["id"]],
                            root,
                        )

            result_lines = [f"Plan created: {task_description}", f"Epic ID: {epic_id}", ""]
            result_lines.append("Steps:")
            for item in bead_ids:
                result_lines.append(f"  [{item['id']}] {item['title']}")

            return "\n".join(result_lines)

        except RuntimeError as e:
            return f"Error creating plan: {e}"

    @mcp.tool()
    def get_current_step() -> str:
        """Get the next actionable task (highest priority with no uncompleted blockers)."""
        if not _beads_available():
            return BEADS_INSTALL_MSG

        root = get_project_root()

        try:
            output = _run_bd(["ready", "--json"], root)
            if not output.strip():
                return "No actionable steps. All steps are either blocked or completed."

            data = json.loads(output)
            if isinstance(data, list) and data:
                step = data[0]
                return (
                    f"Next step:\n"
                    f"  ID: {step.get('id', 'unknown')}\n"
                    f"  Title: {step.get('title', 'Untitled')}\n"
                    f"  Description: {step.get('description', 'No description')}\n"
                    f"  Priority: {step.get('priority', 0)}\n"
                    f"  Status: {step.get('status', 'unknown')}"
                )
            elif isinstance(data, dict):
                return (
                    f"Next step:\n"
                    f"  ID: {data.get('id', 'unknown')}\n"
                    f"  Title: {data.get('title', 'Untitled')}\n"
                    f"  Description: {data.get('description', 'No description')}\n"
                    f"  Priority: {data.get('priority', 0)}\n"
                    f"  Status: {data.get('status', 'unknown')}"
                )
            else:
                return "No actionable steps found."

        except json.JSONDecodeError:
            # If not valid JSON, return raw output
            return output.strip()
        except RuntimeError as e:
            return f"Error: {e}"

    @mcp.tool()
    def get_plan_overview(epic_id: str = "") -> str:
        """Show the full plan with all steps and their statuses.

        Args:
            epic_id: Optional epic ID to filter. Shows all epics if omitted.
        """
        if not _beads_available():
            return BEADS_INSTALL_MSG

        root = get_project_root()

        try:
            args = ["tree"]
            if epic_id:
                args.append(epic_id)
            output = _run_bd(args, root)
            return output.strip() or "No plans found."
        except RuntimeError:
            # Fall back to list
            try:
                args = ["list", "--json"]
                output = _run_bd(args, root)
                return output.strip() or "No plans found."
            except RuntimeError as e:
                return f"Error: {e}"

    @mcp.tool()
    def update_step(bead_id: str, action: str, notes: str = "") -> str:
        """Mark a step as in-progress, completed, or skipped.

        Args:
            bead_id: The bead/step ID to update.
            action: One of 'start', 'complete', or 'skip'.
            notes: Optional notes to attach to the update.
        """
        if not _beads_available():
            return BEADS_INSTALL_MSG

        root = get_project_root()

        valid_actions = {"start", "complete", "skip"}
        if action not in valid_actions:
            return f"Error: action must be one of: {', '.join(sorted(valid_actions))}"

        try:
            if action == "start":
                _run_bd(["update", bead_id, "--status", "in_progress"], root)
                status = "in_progress"
            elif action == "complete":
                _run_bd(["close", bead_id], root)
                status = "closed"
            elif action == "skip":
                note = notes or "AI-assisted — step skipped"
                _run_bd(["close", bead_id, "--note", note], root)
                status = "closed (skipped)"

            result = f"Step {bead_id} updated: {status}"
            if notes and action != "skip":
                result += f"\nNotes: {notes}"
            return result

        except RuntimeError as e:
            return f"Error updating step: {e}"
