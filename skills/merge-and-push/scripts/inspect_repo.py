#!/usr/bin/env python3
"""Read-only Git state inspection for the merge-and-push skill."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class GitError(RuntimeError):
    """Raised when a required Git command fails."""


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return result


def git_text(repo: Path, *args: str, check: bool = True) -> str:
    return git(repo, *args, check=check).stdout.strip()


def local_config(repo: Path, key: str) -> str | None:
    result = git(repo, "config", "--local", "--get", key, check=False)
    return result.stdout.strip() or None if result.returncode in (0, 1) else None


def ref_sha(repo: Path, ref: str) -> str | None:
    result = git(repo, "rev-parse", "--verify", "--quiet", ref, check=False)
    return result.stdout.strip() or None if result.returncode == 0 else None


def is_ancestor(repo: Path, ancestor: str, descendant: str | None) -> bool | None:
    if not descendant:
        return None
    result = git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def valid_branch(repo: Path, branch: str | None) -> bool | None:
    if branch is None:
        return None
    return git(repo, "check-ref-format", "--branch", branch, check=False).returncode == 0


def list_local_branches(repo: Path) -> list[str]:
    output = git_text(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return sorted(line for line in output.splitlines() if line)


def list_remote_branches(repo: Path, remote: str) -> list[str]:
    output = git_text(
        repo,
        "for-each-ref",
        "--format=%(refname:short)",
        f"refs/remotes/{remote}",
    )
    prefix = f"{remote}/"
    branches: list[str] = []
    for line in output.splitlines():
        if line.startswith(prefix):
            name = line[len(prefix) :]
            if name != "HEAD":
                branches.append(name)
    return sorted(branches)


def parse_status(repo: Path) -> list[dict[str, str]]:
    output = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    tokens = output.split("\0")
    changes: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        status = token[:2]
        path = token[3:]
        item = {"status": status, "path": path}
        if "R" in status or "C" in status:
            if index < len(tokens) and tokens[index]:
                item["original_path"] = tokens[index]
                index += 1
        changes.append(item)
    return changes


def parse_worktrees(repo: Path) -> list[dict[str, Any]]:
    output = git_text(repo, "worktree", "list", "--porcelain")
    worktrees: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                path = Path(current["path"])
                status = git(path, "status", "--porcelain=v1", check=False)
                current["dirty"] = status.returncode != 0 or bool(status.stdout)
                worktrees.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "HEAD":
            current["head"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "detached":
            current["detached"] = True
        elif key == "prunable":
            current["prunable"] = value or True
    return worktrees


def branch_relation(repo: Path, local_ref: str, remote_ref: str) -> dict[str, Any] | None:
    if not ref_sha(repo, local_ref) or not ref_sha(repo, remote_ref):
        return None
    result = git_text(repo, "rev-list", "--left-right", "--count", f"{local_ref}...{remote_ref}")
    ahead_text, behind_text = result.split()
    ahead = int(ahead_text)
    behind = int(behind_text)
    if ahead == 0 and behind == 0:
        state = "equal"
    elif ahead == 0:
        state = "behind"
    elif behind == 0:
        state = "ahead"
    else:
        state = "diverged"
    return {"state": state, "ahead": ahead, "behind": behind}


def add_blocker(blockers: list[dict[str, str]], code: str, message: str) -> None:
    blockers.append({"code": code, "message": message})


def inspect(args: argparse.Namespace) -> dict[str, Any]:
    requested_repo = Path(args.repo).expanduser().resolve()
    root_result = git(requested_repo, "rev-parse", "--show-toplevel", check=False)
    if root_result.returncode != 0:
        raise GitError(f"Not a Git repository: {requested_repo}")
    root = Path(root_result.stdout.strip()).resolve()
    common_dir_value = Path(git_text(root, "rev-parse", "--git-common-dir"))
    common_dir = (
        common_dir_value.resolve()
        if common_dir_value.is_absolute()
        else (root / common_dir_value).resolve()
    )

    source_branch_result = git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    detached = source_branch_result.returncode != 0
    source_branch = source_branch_result.stdout.strip() or None
    source_head = git_text(root, "rev-parse", "HEAD")

    test_branch = args.test_branch or local_config(root, "merge-and-push.testBranch")
    production_branch = args.production_branch or local_config(
        root, "merge-and-push.productionBranch"
    )
    remote = args.remote or local_config(root, "merge-and-push.remote") or "origin"
    target_branch = {
        "test": test_branch,
        "production": production_branch,
    }.get(args.environment)

    remotes = git_text(root, "remote").splitlines()
    remote_exists = remote in remotes
    local_branches = list_local_branches(root)
    remote_branches = list_remote_branches(root, remote) if remote_exists else []
    changes = parse_status(root)
    worktrees = parse_worktrees(root)
    target_worktree = next(
        (item for item in worktrees if item.get("branch") == target_branch), None
    )

    local_target_ref = f"refs/heads/{target_branch}" if target_branch else None
    remote_target_ref = f"refs/remotes/{remote}/{target_branch}" if target_branch else None
    local_target_sha = ref_sha(root, local_target_ref) if local_target_ref else None
    remote_target_sha = ref_sha(root, remote_target_ref) if remote_target_ref else None
    relation = (
        branch_relation(root, local_target_ref, remote_target_ref)
        if local_target_ref and remote_target_ref
        else None
    )

    remote_test_ref = f"refs/remotes/{remote}/{test_branch}" if test_branch else None
    remote_production_ref = (
        f"refs/remotes/{remote}/{production_branch}" if production_branch else None
    )
    remote_test_sha = ref_sha(root, remote_test_ref) if remote_test_ref else None
    remote_production_sha = (
        ref_sha(root, remote_production_ref) if remote_production_ref else None
    )
    in_test = is_ancestor(root, source_head, remote_test_ref) if remote_test_ref else None
    in_production = (
        is_ancestor(root, source_head, remote_production_ref)
        if remote_production_ref
        else None
    )

    blockers: list[dict[str, str]] = []
    if detached:
        add_blocker(blockers, "detached_head", "HEAD is detached; use a named feature or hotfix branch.")
    if not remote_exists:
        add_blocker(blockers, "missing_remote", f"Remote '{remote}' does not exist.")
    for label, value in (("test", test_branch), ("production", production_branch)):
        if value and not valid_branch(root, value):
            add_blocker(blockers, f"invalid_{label}_branch", f"Configured {label} branch is invalid: {value}")
    if source_branch and source_branch in {test_branch, production_branch}:
        add_blocker(
            blockers,
            "long_lived_source",
            f"Current branch '{source_branch}' is a configured long-lived branch.",
        )
    if args.environment and not target_branch:
        add_blocker(
            blockers,
            "missing_target_mapping",
            f"No branch mapping is configured for environment '{args.environment}'.",
        )
    if args.environment == "production" and not test_branch:
        add_blocker(
            blockers,
            "missing_test_mapping",
            "Production requires a configured test branch for the test-before-production gate.",
        )
    if target_branch and not remote_target_sha:
        add_blocker(
            blockers,
            "missing_remote_target",
            f"Remote target branch '{remote}/{target_branch}' does not exist in fetched refs.",
        )
    if relation and relation["state"] in {"ahead", "diverged"}:
        add_blocker(
            blockers,
            f"target_{relation['state']}",
            f"Local target '{target_branch}' is {relation['state']} relative to '{remote}/{target_branch}'.",
        )
    if target_worktree and target_worktree.get("dirty"):
        add_blocker(
            blockers,
            "dirty_target_worktree",
            f"Target branch '{target_branch}' is checked out in a dirty worktree: {target_worktree['path']}",
        )
    if args.environment == "production" and test_branch and in_test is not True:
        add_blocker(
            blockers,
            "source_not_in_remote_test",
            f"Source HEAD is not contained in fetched remote test branch '{remote}/{test_branch}'.",
        )

    return {
        "schema_version": 1,
        "ready": not blockers,
        "repository": {
            "root": str(root),
            "common_dir": str(common_dir),
            "current_worktree": str(root),
        },
        "config": {
            "environment": args.environment,
            "remote": remote,
            "test_branch": test_branch,
            "production_branch": production_branch,
            "target_branch": target_branch,
        },
        "source": {
            "branch": source_branch,
            "head": source_head,
            "detached": detached,
            "dirty": bool(changes),
            "changes": changes,
        },
        "branches": {
            "local": local_branches,
            "remote": remote_branches,
            "target": {
                "local_sha": local_target_sha,
                "remote_sha": remote_target_sha,
                "relation": relation,
            },
            "test": {"remote_sha": remote_test_sha},
            "production": {"remote_sha": remote_production_sha},
        },
        "ancestry": {
            "source_in_remote_test": in_test,
            "source_in_remote_production": in_production,
        },
        "worktrees": worktrees,
        "target_worktree": target_worktree,
        "blockers": blockers,
        "note": "Run git fetch for the selected remote immediately before using remote-tracking results.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Path inside the repository")
    parser.add_argument("--environment", choices=("test", "production"))
    parser.add_argument("--test-branch")
    parser.add_argument("--production-branch")
    parser.add_argument("--remote")
    parser.add_argument("--pretty", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = inspect(args)
    except GitError as error:
        print(json.dumps({"ready": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            sort_keys=args.pretty,
        )
    )
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
