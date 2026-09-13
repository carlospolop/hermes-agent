"""Agent teardown owns processes, not their shared terminal environment."""
import json
import shlex
import sys
import time

from agent.turn_context import _bind_turn_identity
from run_agent import AIAgent
from tools.process_registry import ProcessRegistry
from tools.terminal_tool import terminal_tool


def _agent():
    return AIAgent(api_key="test", base_url="http://127.0.0.1:9/v1",
                   provider="openai-compat", model="test", enabled_toolsets=[],
                   quiet_mode=True, skip_context_files=True, skip_memory=True)


def _spawn(agent, task_id, tmp_path):
    _bind_turn_identity(agent, task_id, None, None, None, None)
    command = shlex.quote(sys.executable) + " -c " + shlex.quote("import time; time.sleep(60)")
    result = json.loads(terminal_tool(command, background=True, task_id=task_id,
                                     workdir=str(tmp_path), notify_on_complete=True))
    return result["session_id"]


def _wait_not_running(registry, session_id, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = registry.poll(session_id)["status"]
        if status != "running":
            return status
        time.sleep(0.02)
    return registry.poll(session_id)["status"]


def test_child_close_kills_only_its_processes(tmp_path, monkeypatch):
    import tools.process_registry as processes
    registry = ProcessRegistry()
    monkeypatch.setattr(processes, "process_registry", registry)
    parent, child, sibling, unstarted = [_agent() for _ in range(4)]
    try:
        parent_id = _spawn(parent, "parent-owner", tmp_path)
        child_id = _spawn(child, "sa-child-owner", tmp_path)
        sibling_id = _spawn(sibling, "sa-sibling-owner", tmp_path)
        assert len({registry._running[s].task_id for s in (parent_id, child_id, sibling_id)}) == 1
        unstarted.close()
        assert all(registry.poll(s)["status"] == "running" for s in (parent_id, child_id, sibling_id))
        child.close()
        # A successful signal can precede the reader thread's exit bookkeeping
        # under suite-wide process pressure; assert the externally observable
        # terminal state with a bound rather than racing that bookkeeping.
        assert _wait_not_running(registry, child_id) != "running"
        assert registry.poll(parent_id)["status"] == "running"
        assert registry.poll(sibling_id)["status"] == "running"
        assert child_id in registry._completion_consumed
        child.close()
        assert registry.poll(parent_id)["status"] == "running"
    finally:
        registry.kill_all()
        for agent in (parent, child, sibling, unstarted):
            agent.close()


def test_close_reclaims_processes_from_previous_turns(tmp_path, monkeypatch):
    import tools.process_registry as processes
    registry = ProcessRegistry()
    monkeypatch.setattr(processes, "process_registry", registry)
    agent = _agent()
    try:
        first = _spawn(agent, "turn-one-owner", tmp_path)
        second = _spawn(agent, "turn-two-owner", tmp_path)
        agent.close()
        assert all(_wait_not_running(registry, s) != "running" for s in (first, second))
    finally:
        registry.kill_all()
        agent.close()
