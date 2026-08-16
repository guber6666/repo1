#!/usr/bin/env python3
"""Audit execution of an approved coding spec by Codex or an external agent CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, TextIO


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PLUGIN_ROOT / "assets" / "agents.default.json"
DEFAULT_RUNS_DIR = Path(".codex-agent-manager/runs")
DEFAULT_SPECS_DIR = Path(".codex-agent-manager/specs")


class ManagerError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManagerError(f"config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManagerError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ManagerError(f"config root must be an object: {path}")
    return value


def merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(workspace: Path, explicit: str | None) -> tuple[dict[str, Any], list[str]]:
    config = read_json(DEFAULT_CONFIG)
    sources = [str(DEFAULT_CONFIG)]
    repo_config = workspace / ".codex" / "agent-manager.json"
    if repo_config.is_file():
        config = merge_dict(config, read_json(repo_config))
        sources.append(str(repo_config))
    if explicit:
        explicit_path = Path(explicit).expanduser().resolve()
        config = merge_dict(config, read_json(explicit_path))
        sources.append(str(explicit_path))
    validate_config(config)
    return config, sources


def validate_config(config: dict[str, Any]) -> None:
    agents = config.get("agents")
    order = config.get("selection_order")
    if not isinstance(agents, dict) or not agents:
        raise ManagerError("config.agents must be a non-empty object")
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise ManagerError("config.selection_order must be a list of agent names")
    for name, value in agents.items():
        if not isinstance(value, dict):
            raise ManagerError(f"agent {name!r} must be an object")
        executables = value.get("executables")
        args = value.get("args")
        if not isinstance(executables, list) or not executables or not all(
            isinstance(item, str) and item for item in executables
        ):
            raise ManagerError(f"agent {name!r}.executables must be a non-empty string list")
        if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
            raise ManagerError(f"agent {name!r}.args must be a string list")


def resolve_workspace(raw: str) -> Path:
    workspace = Path(raw).expanduser().resolve()
    if not workspace.is_dir():
        raise ManagerError(f"workspace is not a directory: {workspace}")
    return workspace


def find_executable(candidates: list[str]) -> str | None:
    for candidate in candidates:
        expanded = os.path.expanduser(candidate)
        if os.path.sep in expanded:
            path = Path(expanded)
            if path.is_file() and os.access(path, os.X_OK):
                return str(path.resolve())
        else:
            resolved = shutil.which(expanded)
            if resolved:
                return resolved
    return None


def executable_version(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, check=False, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout or result.stderr).strip().splitlines()
    return output[0] if output else None


def availability(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, agent in config["agents"].items():
        executable = find_executable(agent["executables"])
        result[name] = {
            "available": executable is not None,
            "executable": executable,
            "version": executable_version(executable) if executable else None,
            "candidates": agent["executables"],
            "description": agent.get("description", ""),
        }
    return result


def choose_agent(
    requested: str, config: dict[str, Any], readiness: dict[str, dict[str, Any]]
) -> tuple[str, str]:
    if requested != "auto":
        if requested not in config["agents"]:
            names = ", ".join(sorted(config["agents"]))
            raise ManagerError(f"unknown agent {requested!r}; choose one of: {names}, auto")
        if not readiness[requested]["available"]:
            candidates = ", ".join(readiness[requested]["candidates"])
            raise ManagerError(f"agent {requested!r} is unavailable; expected executable: {candidates}")
        return requested, "explicitly requested"
    for name in config["selection_order"]:
        if name in readiness and readiness[name]["available"]:
            return name, f"first available agent in selection_order ({', '.join(config['selection_order'])})"
    raise ManagerError("no supported external agent CLI is available; run doctor for details")


def render_args(args: list[str], workspace: Path) -> list[str]:
    return [item.replace("{workspace}", str(workspace)) for item in args]


def git_snapshot(workspace: Path) -> dict[str, Any]:
    probe = subprocess.run(
        ["git", "-C", str(workspace), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        return {"is_git_repository": False, "status": None}
    status = subprocess.run(
        ["git", "-C", str(workspace), "status", "--short"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "is_git_repository": True,
        "root": probe.stdout.strip(),
        "dirty": bool(status.stdout.strip()),
        "status": status.stdout,
    }


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64] or "coding-spec"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_preview(executable: str, args: list[str]) -> list[str]:
    return [executable, *args, "<prompt from prompt.md>"]


def resolve_spec(workspace: Path, raw: str) -> Path:
    spec_path = Path(raw).expanduser()
    if not spec_path.is_absolute():
        spec_path = workspace / spec_path
    spec_path = spec_path.resolve()
    if not spec_path.is_file():
        raise ManagerError(f"spec not found: {spec_path}")
    return spec_path


def create_run_dir(workspace: Path, runs_dir_raw: str, agent: str, spec_path: Path) -> tuple[str, Path]:
    run_stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"{run_stamp}-{safe_slug(agent)}-{safe_slug(spec_path.stem)}"
    runs_dir = Path(runs_dir_raw).expanduser()
    if not runs_dir.is_absolute():
        runs_dir = workspace / runs_dir
    run_dir = runs_dir.resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def build_prompt(spec: str, workspace: Path) -> str:
    return f"""You are the implementation worker for an approved coding spec.

Workspace: {workspace}

Operating constraints:
- Read and follow repository instructions before editing.
- Implement only the approved spec below and preserve unrelated user changes.
- Treat this local spec snapshot as immutable. If a material decision is missing or conflicting, stop and report the question instead of guessing or expanding scope.
- Do not commit, push, rewrite git history, or run destructive cleanup commands.
- Never expose secrets. Do not add dependencies unless the spec or repository conventions require them.
- Run the focused verification named in the spec when it is safe and available.
- Finish with a concise summary of files changed, verification run, failures, and remaining gaps.

Approved spec:

{spec}
"""


def stream_pipe(source: TextIO, sink: TextIO, mirror: TextIO | None) -> None:
    try:
        for chunk in iter(source.readline, ""):
            sink.write(chunk)
            sink.flush()
            if mirror is not None:
                mirror.write(chunk)
                mirror.flush()
    finally:
        source.close()


def doctor(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    config, sources = load_config(workspace, args.config)
    report = {
        "workspace": str(workspace),
        "config_sources": sources,
        "agents": availability(config),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Workspace: {workspace}")
        for name, item in report["agents"].items():
            state = "ready" if item["available"] else "missing"
            detail = item["executable"] or ", ".join(item["candidates"])
            print(f"- {name}: {state} ({detail})")
    return 0


def new_spec(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    output = Path(args.output).expanduser() if args.output else DEFAULT_SPECS_DIR / f"{safe_slug(args.title)}.md"
    if not output.is_absolute():
        output = workspace / output
    output = output.resolve()
    if output.exists() and not args.force:
        raise ManagerError(f"spec already exists: {output}; pass --force to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.source_mode == "issue-and-local" and not args.issue_url:
        raise ManagerError("--issue-url is required when --source-mode=issue-and-local")
    created_at = utc_now().isoformat()
    issue_url = args.issue_url or "null"
    issue_number = args.issue_number or "null"
    published_at = created_at if args.source_mode == "issue-and-local" else "null"
    content = f"""---
status: draft
source_mode: {args.source_mode}
issue_url: {issue_url}
issue_number: {issue_number}
published_at: {published_at}
created_at: {created_at}
execution_source: local-snapshot
---

# {args.title}

## Problem Statement

{args.request}

## Solution

Describe the agreed solution from the user's perspective.

## User Stories

1. As an actor, I want the agreed feature, so that I receive the intended benefit.

## Implementation Decisions

- Record agreed modules, interfaces, contracts, compatibility, and architectural decisions.

## Testing Decisions

- Record the user-confirmed highest practical test seam and observable behavior.

## Out of Scope

- List related work that is deliberately excluded.

## Further Notes

Record risks, rollout or rollback considerations, and non-blocking notes.
"""
    output.write_text(content, encoding="utf-8")
    print(output)
    return 0


def make_plan(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
    workspace = resolve_workspace(args.workspace)
    config, sources = load_config(workspace, args.config)
    readiness = availability(config)
    selected, reason = choose_agent(args.agent, config, readiness)
    spec_path = resolve_spec(workspace, args.spec)
    executable = readiness[selected]["executable"]
    assert isinstance(executable, str)
    adapter_args = render_args(config["agents"][selected]["args"], workspace)
    plan = {
        "workspace": str(workspace),
        "spec": str(spec_path),
        "selected_agent": selected,
        "selection_reason": reason,
        "config_sources": sources,
        "git": git_snapshot(workspace),
        "command": command_preview(executable, adapter_args),
    }
    return plan, config, spec_path, executable


def plan_command(args: argparse.Namespace) -> int:
    plan, _, _, _ = make_plan(args)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def run_command(args: argparse.Namespace) -> int:
    plan, config, spec_path, executable = make_plan(args)
    workspace = Path(plan["workspace"])
    if args.require_clean and plan["git"].get("dirty"):
        raise ManagerError("workspace has uncommitted changes and --require-clean was supplied")
    selected = plan["selected_agent"]
    adapter_args = render_args(config["agents"][selected]["args"], workspace)
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    spec = spec_path.read_text(encoding="utf-8")
    prompt = build_prompt(spec, workspace)
    run_id, run_dir = create_run_dir(workspace, args.runs_dir, selected, spec_path)

    shutil.copyfile(spec_path, run_dir / "spec.md")
    (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    started = utc_now()
    metadata = dict(plan)
    metadata.update({"run_id": run_id, "started_at": started.isoformat(), "timeout_seconds": args.timeout})
    write_json(run_dir / "metadata.json", metadata)

    env = os.environ.copy()
    env["CODEX_AGENT_MANAGER_RUN_DIR"] = str(run_dir)
    command = [executable, *adapter_args, prompt]
    print(f"Run directory: {run_dir}")
    print(f"Agent: {selected}")

    return_code: int | None = None
    timed_out = False
    interrupted = False
    with (run_dir / "events.ndjson").open("w", encoding="utf-8") as stdout_log, (
        run_dir / "stderr.log"
    ).open("w", encoding="utf-8") as stderr_log:
        process = subprocess.Popen(
            command,
            cwd=workspace,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None and process.stderr is not None
        stdout_thread = threading.Thread(
            target=stream_pipe, args=(process.stdout, stdout_log, sys.stdout), daemon=True
        )
        stderr_thread = threading.Thread(
            target=stream_pipe, args=(process.stderr, stderr_log, sys.stderr), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            return_code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                return_code = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = process.wait()
        except KeyboardInterrupt:
            interrupted = True
            process.terminate()
            return_code = process.wait()
        finally:
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

    finished = utc_now()
    status = {
        "run_id": run_id,
        "agent": selected,
        "exit_code": return_code,
        "timed_out": timed_out,
        "interrupted": interrupted,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "git_after": git_snapshot(workspace),
    }
    write_json(run_dir / "status.json", status)
    print(f"Status: {run_dir / 'status.json'}")
    if timed_out:
        return 124
    if interrupted:
        return 130
    return return_code if return_code is not None else 1


def current_start(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    spec_path = resolve_spec(workspace, args.spec)
    run_id, run_dir = create_run_dir(workspace, args.runs_dir, "current-codex", spec_path)
    spec = spec_path.read_text(encoding="utf-8")
    prompt = build_prompt(spec, workspace)
    started = utc_now()
    shutil.copyfile(spec_path, run_dir / "spec.md")
    (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    (run_dir / "events.ndjson").touch()
    (run_dir / "stderr.log").touch()
    metadata = {
        "run_id": run_id,
        "workspace": str(workspace),
        "spec": str(spec_path),
        "selected_agent": "current-codex",
        "selection_reason": "explicitly selected current Codex Agent",
        "execution_mode": "current-session",
        "git": git_snapshot(workspace),
        "command": None,
        "started_at": started.isoformat(),
    }
    write_json(run_dir / "metadata.json", metadata)
    write_json(
        run_dir / "status.json",
        {
            "run_id": run_id,
            "agent": "current-codex",
            "outcome": "in_progress",
            "started_at": started.isoformat(),
            "finished_at": None,
        },
    )
    print(run_dir)
    return 0


def current_finish(args: argparse.Namespace) -> int:
    workspace = resolve_workspace(args.workspace)
    run_dir = Path(args.run_dir).expanduser()
    if not run_dir.is_absolute():
        run_dir = workspace / run_dir
    run_dir = run_dir.resolve()
    try:
        run_dir.relative_to(workspace)
    except ValueError as exc:
        raise ManagerError(f"run directory must be inside the workspace: {run_dir}") from exc
    metadata_path = run_dir / "metadata.json"
    status_path = run_dir / "status.json"
    if not metadata_path.is_file() or not status_path.is_file():
        raise ManagerError(f"not an agent-manager run directory: {run_dir}")
    metadata = read_json(metadata_path)
    if metadata.get("selected_agent") != "current-codex":
        raise ManagerError("current-finish only accepts runs created by current-start")
    previous_status = read_json(status_path)
    if previous_status.get("outcome") != "in_progress":
        raise ManagerError(f"current run is already finalized: {run_dir}")
    finished = utc_now()
    started_raw = previous_status.get("started_at")
    try:
        started = dt.datetime.fromisoformat(str(started_raw))
        duration = round((finished - started).total_seconds(), 3)
    except ValueError:
        duration = None
    changed = args.changed or []
    verification = args.verification or []
    result_lines = [
        "# Current Codex execution result",
        "",
        f"Outcome: {args.outcome}",
        "",
        "## Summary",
        "",
        args.summary,
        "",
        "## Changed",
        "",
        *(f"- {item}" for item in changed),
        "",
        "## Verification",
        "",
        *(f"- {item}" for item in verification),
        "",
    ]
    if not changed:
        result_lines.insert(result_lines.index("## Verification") - 1, "- None recorded")
    if not verification:
        result_lines.append("- None recorded")
    (run_dir / "result.md").write_text("\n".join(result_lines), encoding="utf-8")
    write_json(
        status_path,
        {
            "run_id": previous_status["run_id"],
            "agent": "current-codex",
            "outcome": args.outcome,
            "exit_code": None,
            "started_at": started_raw,
            "finished_at": finished.isoformat(),
            "duration_seconds": duration,
            "git_after": git_snapshot(workspace),
        },
    )
    print(status_path)
    return 0


def common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default=".", help="target repository/workspace (default: current directory)")
    parser.add_argument("--config", help="optional JSON config merged over bundled and repository config")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="report external CLI readiness")
    common_options(doctor_parser)
    doctor_parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    doctor_parser.set_defaults(handler=doctor)

    spec_parser = subparsers.add_parser("new-spec", help="create a draft spec scaffold")
    common_options(spec_parser)
    spec_parser.add_argument("--title", required=True)
    spec_parser.add_argument("--request", required=True)
    spec_parser.add_argument("--output", help="output path (default: .codex-agent-manager/specs/<title>.md)")
    spec_parser.add_argument(
        "--source-mode", choices=["local-only", "issue-and-local"], default="local-only"
    )
    spec_parser.add_argument("--issue-url")
    spec_parser.add_argument("--issue-number")
    spec_parser.add_argument("--force", action="store_true", help="replace an existing output")
    spec_parser.set_defaults(handler=new_spec)

    plan_parser = subparsers.add_parser("plan", help="resolve an agent and preview an execution")
    common_options(plan_parser)
    plan_parser.add_argument("--spec", required=True)
    plan_parser.add_argument("--agent", default="auto")
    plan_parser.set_defaults(handler=plan_command)

    run_parser = subparsers.add_parser("run", help="execute an approved spec")
    common_options(run_parser)
    run_parser.add_argument("--spec", required=True)
    run_parser.add_argument("--agent", default="auto")
    run_parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    run_parser.add_argument("--timeout", type=int, default=1800)
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--require-clean", action="store_true")
    run_parser.set_defaults(handler=run_command)

    current_start_parser = subparsers.add_parser(
        "current-start", help="start an audit record for the current Codex Agent"
    )
    common_options(current_start_parser)
    current_start_parser.add_argument("--spec", required=True)
    current_start_parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    current_start_parser.set_defaults(handler=current_start)

    current_finish_parser = subparsers.add_parser(
        "current-finish", help="finalize a current Codex Agent audit record"
    )
    common_options(current_finish_parser)
    current_finish_parser.add_argument("--run-dir", required=True)
    current_finish_parser.add_argument(
        "--outcome", choices=["completed", "failed", "blocked"], required=True
    )
    current_finish_parser.add_argument("--summary", required=True)
    current_finish_parser.add_argument("--changed", action="append")
    current_finish_parser.add_argument("--verification", action="append")
    current_finish_parser.set_defaults(handler=current_finish)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if getattr(args, "timeout", 1) <= 0:
        parser.error("--timeout must be greater than zero")
    try:
        return int(args.handler(args))
    except ManagerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
