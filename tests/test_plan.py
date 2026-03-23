"""Tests for Beads plan tools."""

import json
from unittest.mock import MagicMock, patch

import pytest

from courier_agent.tools.plan import register_tools, BEADS_INSTALL_MSG


@pytest.fixture
def tools(tmp_path):
    """Register plan tools."""
    mcp = MagicMock()
    registered = {}

    def mock_tool():
        def decorator(func):
            registered[func.__name__] = func
            return func
        return decorator

    mcp.tool = mock_tool
    register_tools(mcp, lambda: tmp_path)
    return registered


class TestBeadsNotInstalled:
    """All plan tools should return install instructions when bd is not in PATH."""

    @patch("courier_agent.tools.plan._beads_available", return_value=False)
    def test_create_plan_no_beads(self, mock_avail, tools):
        result = tools["create_plan"](
            task_description="test", steps='[{"title": "step 1"}]'
        )
        assert "not installed" in result.lower()
        assert "curl" in result

    @patch("courier_agent.tools.plan._beads_available", return_value=False)
    def test_get_current_step_no_beads(self, mock_avail, tools):
        result = tools["get_current_step"]()
        assert "not installed" in result.lower()

    @patch("courier_agent.tools.plan._beads_available", return_value=False)
    def test_get_plan_overview_no_beads(self, mock_avail, tools):
        result = tools["get_plan_overview"]()
        assert "not installed" in result.lower()

    @patch("courier_agent.tools.plan._beads_available", return_value=False)
    def test_update_step_no_beads(self, mock_avail, tools):
        result = tools["update_step"](bead_id="123", action="complete")
        assert "not installed" in result.lower()


class TestCreatePlan:
    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    @patch("courier_agent.tools.plan._run_bd")
    def test_creates_epic_and_steps(self, mock_bd, mock_avail, tools):
        mock_bd.side_effect = [
            "Created epic EPIC-1",        # create epic
            "Created bead BEAD-1",        # step 1
            "Created bead BEAD-2",        # step 2
            "Updated BEAD-2",             # dependency link
        ]

        steps = json.dumps([
            {"title": "Step 1", "description": "First", "priority": 1, "dependencies": []},
            {"title": "Step 2", "description": "Second", "priority": 2, "dependencies": [0]},
        ])

        result = tools["create_plan"](task_description="Build feature", steps=steps)
        assert "Plan created" in result
        assert "Step 1" in result
        assert "Step 2" in result
        assert mock_bd.call_count == 4

    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    def test_invalid_json_steps(self, mock_avail, tools):
        result = tools["create_plan"](
            task_description="test", steps="not valid json"
        )
        assert "Error" in result
        assert "JSON" in result

    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    def test_empty_steps(self, mock_avail, tools):
        result = tools["create_plan"](
            task_description="test", steps="[]"
        )
        assert "Error" in result


class TestGetCurrentStep:
    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    @patch("courier_agent.tools.plan._run_bd")
    def test_returns_next_step(self, mock_bd, mock_avail, tools):
        mock_bd.return_value = json.dumps([{
            "id": "BEAD-1",
            "title": "Implement parser",
            "description": "Write the parser module",
            "priority": 1,
            "status": "open",
        }])

        result = tools["get_current_step"]()
        assert "BEAD-1" in result
        assert "Implement parser" in result

    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    @patch("courier_agent.tools.plan._run_bd")
    def test_no_steps_ready(self, mock_bd, mock_avail, tools):
        mock_bd.return_value = ""
        result = tools["get_current_step"]()
        assert "No actionable" in result


class TestGetPlanOverview:
    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    @patch("courier_agent.tools.plan._run_bd")
    def test_returns_tree(self, mock_bd, mock_avail, tools):
        mock_bd.return_value = "EPIC-1: Build feature\n  BEAD-1: [open] Step 1\n  BEAD-2: [open] Step 2"
        result = tools["get_plan_overview"]()
        assert "EPIC-1" in result
        assert "Step 1" in result

    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    @patch("courier_agent.tools.plan._run_bd")
    def test_empty_plan(self, mock_bd, mock_avail, tools):
        mock_bd.return_value = ""
        result = tools["get_plan_overview"]()
        assert "No plans" in result


class TestUpdateStep:
    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    @patch("courier_agent.tools.plan._run_bd")
    def test_start_step(self, mock_bd, mock_avail, tools):
        mock_bd.return_value = "Updated"
        result = tools["update_step"](bead_id="BEAD-1", action="start")
        assert "in_progress" in result
        mock_bd.assert_called_once()

    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    @patch("courier_agent.tools.plan._run_bd")
    def test_complete_step(self, mock_bd, mock_avail, tools):
        mock_bd.return_value = "Closed"
        result = tools["update_step"](bead_id="BEAD-1", action="complete")
        assert "closed" in result

    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    @patch("courier_agent.tools.plan._run_bd")
    def test_skip_step(self, mock_bd, mock_avail, tools):
        mock_bd.return_value = "Closed"
        result = tools["update_step"](bead_id="BEAD-1", action="skip")
        assert "skipped" in result

    @patch("courier_agent.tools.plan._beads_available", return_value=True)
    def test_invalid_action(self, mock_avail, tools):
        result = tools["update_step"](bead_id="BEAD-1", action="invalid")
        assert "Error" in result
        assert "start" in result and "complete" in result
