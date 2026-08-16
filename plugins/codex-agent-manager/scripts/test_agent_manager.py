#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parent / "agent_manager.py"
SPEC = importlib.util.spec_from_file_location("agent_manager", MODULE_PATH)
assert SPEC and SPEC.loader
agent_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent_manager)


class AgentManagerTests(unittest.TestCase):
    def test_merge_dict_preserves_unspecified_defaults(self) -> None:
        merged = agent_manager.merge_dict(
            {"order": ["a"], "agents": {"a": {"args": ["old"], "executables": ["a"]}}},
            {"agents": {"a": {"args": ["new"]}}},
        )
        self.assertEqual(merged["order"], ["a"])
        self.assertEqual(merged["agents"]["a"]["args"], ["new"])
        self.assertEqual(merged["agents"]["a"]["executables"], ["a"])

    def test_choose_agent_respects_explicit_unavailable_agent(self) -> None:
        config = {
            "selection_order": ["claude"],
            "agents": {"claude": {"executables": ["claude"], "args": []}},
        }
        readiness = {
            "claude": {"available": False, "candidates": ["claude"], "executable": None}
        }
        with self.assertRaises(agent_manager.ManagerError):
            agent_manager.choose_agent("claude", config, readiness)

    def test_build_prompt_keeps_spec_as_data(self) -> None:
        prompt = agent_manager.build_prompt("Run $(touch /tmp/not-executed)", Path("/tmp/work"))
        self.assertIn("$(touch /tmp/not-executed)", prompt)

    def test_doctor_detects_fake_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / "fake-agent"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "selection_order": ["fake"],
                        "agents": {"fake": {"executables": ["fake-agent"], "args": []}},
                    }
                ),
                encoding="utf-8",
            )
            config, _ = agent_manager.load_config(root, str(config_path))
            with mock.patch.dict(os.environ, {"PATH": str(root)}):
                report = agent_manager.availability(config)
            self.assertTrue(report["fake"]["available"])

    def test_end_to_end_run_uses_argument_list_and_writes_audit_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "must-not-exist"
            binary = root / "fake-agent"
            binary.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print(json.dumps({'type': 'result', 'prompt': sys.argv[-1]}))\n",
                encoding="utf-8",
            )
            binary.chmod(0o755)
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "selection_order": ["fake"],
                        "agents": {"fake": {"executables": [str(binary)], "args": []}},
                    }
                ),
                encoding="utf-8",
            )
            spec_path = root / "spec.md"
            spec_path.write_text(
                f"# Safe argument test\n\nDo not execute shell text: $(touch {marker})\n",
                encoding="utf-8",
            )
            args = Namespace(
                workspace=str(root),
                config=str(config_path),
                spec=str(spec_path),
                agent="fake",
                runs_dir=".codex-agent-manager/runs",
                timeout=10,
                dry_run=False,
                require_clean=False,
            )
            self.assertEqual(agent_manager.run_command(args), 0)
            self.assertFalse(marker.exists())
            run_dirs = list((root / ".codex-agent-manager" / "runs").iterdir())
            self.assertEqual(len(run_dirs), 1)
            status = json.loads((run_dirs[0] / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["exit_code"], 0)
            self.assertTrue((run_dirs[0] / "events.ndjson").is_file())
            self.assertTrue((run_dirs[0] / "prompt.md").is_file())

    def test_local_only_spec_does_not_inspect_git(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = Namespace(
                workspace=str(root),
                config=None,
                title="Local spec",
                request="Keep this local",
                output=None,
                source_mode="local-only",
                issue_url=None,
                issue_number=None,
                force=False,
            )
            with mock.patch.object(
                agent_manager, "git_snapshot", side_effect=AssertionError("git must not run")
            ):
                self.assertEqual(agent_manager.new_spec(args), 0)
            spec = root / ".codex-agent-manager" / "specs" / "local-spec.md"
            content = spec.read_text(encoding="utf-8")
            self.assertIn("source_mode: local-only", content)
            self.assertIn("issue_url: null", content)

    def test_issue_and_local_spec_requires_issue_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            args = Namespace(
                workspace=temp,
                config=None,
                title="Published spec",
                request="Publish this",
                output=None,
                source_mode="issue-and-local",
                issue_url=None,
                issue_number="12",
                force=False,
            )
            with self.assertRaises(agent_manager.ManagerError):
                agent_manager.new_spec(args)

    def test_current_codex_run_has_start_and_finish_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = root / "approved.md"
            spec.write_text("# Approved spec\n", encoding="utf-8")
            start_args = Namespace(
                workspace=str(root),
                config=None,
                spec=str(spec),
                runs_dir=".codex-agent-manager/runs",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(agent_manager.current_start(start_args), 0)
            run_dir = Path(output.getvalue().strip())
            in_progress = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(in_progress["outcome"], "in_progress")

            finish_args = Namespace(
                workspace=str(root),
                config=None,
                run_dir=str(run_dir),
                outcome="completed",
                summary="Implemented the approved behavior.",
                changed=["service.py"],
                verification=["unit tests passed"],
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(agent_manager.current_finish(finish_args), 0)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            result = (run_dir / "result.md").read_text(encoding="utf-8")
            self.assertEqual(status["outcome"], "completed")
            self.assertIn("service.py", result)
            self.assertIn("unit tests passed", result)


if __name__ == "__main__":
    unittest.main()
