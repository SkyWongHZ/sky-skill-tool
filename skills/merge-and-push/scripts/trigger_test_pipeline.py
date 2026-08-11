#!/usr/bin/env python3
"""Safely trigger a tracked webhook:dev script after a verified test push."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SCRIPT_NAME = "webhook:dev"
CONFIG_KEY = "merge-and-push.testPipelineCwd"
COMMIT_RE = re.compile(r"[0-9a-fA-F]{40,64}")
SHELL_OPERATORS = {"&", "&&", "|", "||", ";", "<", ">", "`"}
PLACEHOLDER_HOSTS = {
    "127.0.0.1",
    "::1",
    "example.com",
    "example.net",
    "example.org",
    "localhost",
}
PLACEHOLDER_HOST_SUFFIXES = (
    ".example",
    ".example.com",
    ".example.net",
    ".example.org",
    ".invalid",
    ".localhost",
    ".test",
)
PLACEHOLDER_MARKERS = ("<webhook", "${", "{{", "placeholder", "replace_with", "your_webhook")
VALUE_OPTIONS = {
    "--data",
    "--data-ascii",
    "--data-binary",
    "--data-raw",
    "--header",
    "-H",
    "-d",
}
LONG_VALUE_PREFIXES = tuple(f"{option}=" for option in VALUE_OPTIONS if option.startswith("--"))


class PipelineError(RuntimeError):
    """An expected failure with a stable exit code and JSON status."""

    def __init__(
        self,
        message: str,
        *,
        exit_code: int,
        status: str,
        candidates: list[str] | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.status = status
        self.candidates = candidates or []
        self.http_status = http_status


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
        raise PipelineError(
            f"Git inspection failed: {detail}",
            exit_code=1,
            status="internal_error",
        )
    return result


def git_text(repo: Path, *args: str, check: bool = True) -> str:
    return git(repo, *args, check=check).stdout.strip()


def repository_root(path: str) -> Path:
    requested = Path(path).expanduser().resolve()
    result = git(requested, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        raise PipelineError(
            f"Not a Git repository: {requested}",
            exit_code=1,
            status="internal_error",
        )
    return Path(result.stdout.strip()).resolve()


def resolve_commit(repo: Path, value: str, label: str) -> str:
    if not COMMIT_RE.fullmatch(value):
        raise PipelineError(
            f"{label} must be a full commit SHA.",
            exit_code=2,
            status="configuration_error",
        )
    resolved = git_text(repo, "rev-parse", "--verify", f"{value}^{{commit}}")
    return resolved


def require_trusted_ancestor(repo: Path, trusted_sha: str, target_sha: str) -> None:
    result = git(repo, "merge-base", "--is-ancestor", trusted_sha, target_sha, check=False)
    if result.returncode == 0:
        return
    if result.returncode == 1:
        raise PipelineError(
            "Trusted SHA is not an ancestor of the target SHA.",
            exit_code=2,
            status="configuration_error",
        )
    raise PipelineError(
        "Could not verify the relationship between trusted and target SHAs.",
        exit_code=1,
        status="internal_error",
    )


def local_config(repo: Path, key: str) -> str | None:
    result = git(repo, "config", "--local", "--get", key, check=False)
    if result.returncode == 0:
        return result.stdout.strip() or None
    if result.returncode == 1:
        return None
    raise PipelineError(
        f"Could not read local Git config key: {key}",
        exit_code=1,
        status="internal_error",
    )


def resolve_remote(repo: Path, explicit: str | None) -> str:
    remote = explicit or local_config(repo, "merge-and-push.remote") or "origin"
    remotes = git_text(repo, "remote").splitlines()
    if remote not in remotes:
        raise PipelineError(
            f"Remote does not exist: {remote}",
            exit_code=2,
            status="configuration_error",
        )
    return remote


def resolve_test_branch(repo: Path, explicit: str | None) -> str:
    branch = explicit or local_config(repo, "merge-and-push.testBranch")
    if not branch:
        raise PipelineError(
            "A test branch is required before triggering the pipeline.",
            exit_code=2,
            status="configuration_error",
        )
    if git(repo, "check-ref-format", "--branch", branch, check=False).returncode != 0:
        raise PipelineError(
            f"Configured test branch is invalid: {branch}",
            exit_code=2,
            status="configuration_error",
        )
    return branch


def fetch_remote_test_sha(repo: Path, remote: str, test_branch: str) -> str:
    result = git(
        repo,
        "fetch",
        "--no-tags",
        remote,
        f"refs/heads/{test_branch}",
        check=False,
    )
    if result.returncode != 0:
        raise PipelineError(
            f"Could not fetch remote test branch: {remote}/{test_branch}",
            exit_code=2,
            status="configuration_error",
        )
    return git_text(repo, "rev-parse", "FETCH_HEAD")


def normalize_package_dir(value: str) -> str:
    normalized = value.strip() or "."
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or "\\" in normalized or ":" in normalized:
        raise PipelineError(
            f"Pipeline directory must stay inside the repository: {value}",
            exit_code=2,
            status="configuration_error",
        )
    clean = path.as_posix().rstrip("/") or "."
    return "." if clean == "." else clean.removeprefix("./")


def package_path(package_dir: str) -> str:
    return "package.json" if package_dir == "." else f"{package_dir}/package.json"


def package_at(repo: Path, commit: str, path: str) -> dict[str, Any] | None:
    result = git(repo, "show", f"{commit}:{path}", check=False)
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PipelineError(
            f"Tracked package.json is not valid JSON: {path} ({error.msg})",
            exit_code=2,
            status="configuration_error",
        ) from error
    if not isinstance(value, dict):
        raise PipelineError(
            f"Tracked package.json must contain a JSON object: {path}",
            exit_code=2,
            status="configuration_error",
        )
    return value


def script_from_package(package: dict[str, Any] | None) -> str | None:
    if package is None:
        return None
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        return None
    command = scripts.get(SCRIPT_NAME)
    return command if isinstance(command, str) and command.strip() else None


def discover_candidates(repo: Path, commit: str) -> list[str]:
    output = git_text(repo, "ls-tree", "-r", "--name-only", commit)
    candidates: list[str] = []
    for raw_path in output.splitlines():
        path = PurePosixPath(raw_path)
        if path.name != "package.json":
            continue
        if any(part in {"node_modules", "dist", "coverage", ".cache"} for part in path.parts):
            continue
        if script_from_package(package_at(repo, commit, raw_path)) is not None:
            parent = path.parent.as_posix()
            candidates.append("." if parent == "." else parent)
    return sorted(set(candidates))


def select_package_dir(
    repo: Path,
    target_sha: str,
    explicit_dir: str | None,
) -> tuple[str, list[str]]:
    configured = explicit_dir or local_config(repo, CONFIG_KEY)
    if configured:
        selected = normalize_package_dir(configured)
        return selected, [selected]

    candidates = discover_candidates(repo, target_sha)
    if len(candidates) == 1:
        return candidates[0], candidates
    if not candidates:
        raise PipelineError(
            f"No tracked package.json defines {SCRIPT_NAME}.",
            exit_code=2,
            status="configuration_error",
        )
    raise PipelineError(
        f"Multiple tracked package.json files define {SCRIPT_NAME}; configure {CONFIG_KEY}.",
        exit_code=2,
        status="configuration_error",
        candidates=candidates,
    )


def shell_tokens(command: str) -> list[str]:
    if len(command) > 8192 or "$(" in command or "\n" in command or "\r" in command:
        raise PipelineError(
            f"{SCRIPT_NAME} contains unsupported shell syntax.",
            exit_code=2,
            status="configuration_error",
        )
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>`")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError as error:
        raise PipelineError(
            f"Could not parse {SCRIPT_NAME}: {error}",
            exit_code=2,
            status="configuration_error",
        ) from error
    if not tokens or any(token in SHELL_OPERATORS for token in tokens):
        raise PipelineError(
            f"{SCRIPT_NAME} must be one curl command without shell operators.",
            exit_code=2,
            status="configuration_error",
        )
    return tokens


def validate_curl_value(option: str, value: str) -> None:
    if len(value) > 4096 or "\n" in value or "\r" in value or value.startswith("@"):
        raise PipelineError(
            f"{option} contains an unsafe value in {SCRIPT_NAME}.",
            exit_code=2,
            status="configuration_error",
        )


def parse_curl(command: str) -> tuple[list[str], str, bool]:
    tokens = shell_tokens(command)
    if tokens[0] != "curl":
        raise PipelineError(
            f"{SCRIPT_NAME} must invoke curl directly.",
            exit_code=2,
            status="configuration_error",
        )

    safe_arguments: list[str] = []
    method: str | None = None
    endpoint: str | None = None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"--request", "-X"}:
            if index + 1 >= len(tokens):
                raise PipelineError(
                    f"{token} requires a value in {SCRIPT_NAME}.",
                    exit_code=2,
                    status="configuration_error",
                )
            if method is not None:
                raise PipelineError(
                    f"{SCRIPT_NAME} declares the HTTP method more than once.",
                    exit_code=2,
                    status="configuration_error",
                )
            method = tokens[index + 1].upper()
            index += 2
            continue
        if token.startswith("--request="):
            if method is not None:
                raise PipelineError(
                    f"{SCRIPT_NAME} declares the HTTP method more than once.",
                    exit_code=2,
                    status="configuration_error",
                )
            method = token.partition("=")[2].upper()
            index += 1
            continue
        if token.startswith("-X") and token != "-X":
            if method is not None:
                raise PipelineError(
                    f"{SCRIPT_NAME} declares the HTTP method more than once.",
                    exit_code=2,
                    status="configuration_error",
                )
            method = token[2:].upper()
            index += 1
            continue
        if token in VALUE_OPTIONS:
            if index + 1 >= len(tokens):
                raise PipelineError(
                    f"{token} requires a value in {SCRIPT_NAME}.",
                    exit_code=2,
                    status="configuration_error",
                )
            value = tokens[index + 1]
            validate_curl_value(token, value)
            safe_arguments.extend([token, value])
            index += 2
            continue
        if token.startswith(LONG_VALUE_PREFIXES):
            option, _, value = token.partition("=")
            validate_curl_value(option, value)
            safe_arguments.append(token)
            index += 1
            continue
        if token.startswith("-H") and token != "-H":
            validate_curl_value("-H", token[2:])
            safe_arguments.extend(["-H", token[2:]])
            index += 1
            continue
        if token.startswith("-d") and token != "-d":
            validate_curl_value("-d", token[2:])
            safe_arguments.extend(["-d", token[2:]])
            index += 1
            continue
        if token.startswith(("https://", "http://")):
            if endpoint is not None:
                raise PipelineError(
                    f"{SCRIPT_NAME} must contain exactly one HTTPS endpoint.",
                    exit_code=2,
                    status="configuration_error",
                )
            endpoint = token
            index += 1
            continue
        raise PipelineError(
            f"{SCRIPT_NAME} contains an unsupported curl argument.",
            exit_code=2,
            status="configuration_error",
        )

    if method != "POST":
        raise PipelineError(
            f"{SCRIPT_NAME} must explicitly use HTTP POST.",
            exit_code=2,
            status="configuration_error",
        )
    if endpoint is None:
        raise PipelineError(
            f"{SCRIPT_NAME} must contain exactly one HTTPS endpoint.",
            exit_code=2,
            status="configuration_error",
        )
    parsed = urlsplit(endpoint)
    if not parsed.hostname or parsed.username or parsed.password:
        raise PipelineError(
            f"{SCRIPT_NAME} contains an invalid HTTPS endpoint.",
            exit_code=2,
            status="configuration_error",
        )
    hostname = parsed.hostname.casefold().rstrip(".")
    normalized_endpoint = endpoint.casefold()
    if (
        hostname in PLACEHOLDER_HOSTS
        or hostname.endswith(PLACEHOLDER_HOST_SUFFIXES)
        or any(marker in normalized_endpoint for marker in PLACEHOLDER_MARKERS)
    ):
        raise PipelineError(
            f"{SCRIPT_NAME} contains a placeholder endpoint.",
            exit_code=2,
            status="configuration_error",
        )
    try:
        port = parsed.port
    except ValueError as error:
        raise PipelineError(
            f"{SCRIPT_NAME} contains an invalid endpoint port.",
            exit_code=2,
            status="configuration_error",
        ) from error
    upgraded_to_https = False
    if (
        parsed.scheme == "http"
        and parsed.hostname == "flow-openapi.aliyun.com"
        and port in {None, 80}
    ):
        endpoint = urlunsplit(("https", parsed.hostname, parsed.path, parsed.query, parsed.fragment))
        upgraded_to_https = True
    elif parsed.scheme != "https":
        raise PipelineError(
            f"{SCRIPT_NAME} must use HTTPS.",
            exit_code=2,
            status="configuration_error",
        )
    return safe_arguments, endpoint, upgraded_to_https


def redact(value: str, endpoint: str) -> str:
    return value.replace(endpoint, "[REDACTED_URL]").strip()


def invoke_curl(arguments: list[str], endpoint: str) -> int:
    curl_path = shutil.which("curl")
    if not curl_path:
        raise PipelineError(
            "curl is not installed.",
            exit_code=1,
            status="internal_error",
        )
    command = [
        curl_path,
        "--silent",
        "--show-error",
        "--connect-timeout",
        "10",
        "--max-time",
        "30",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        *arguments,
        "--request",
        "POST",
        endpoint,
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=35,
        )
    except subprocess.TimeoutExpired as error:
        raise PipelineError(
            "The test pipeline request timed out; it was not retried.",
            exit_code=3,
            status="request_failed",
        ) from error
    if result.returncode != 0:
        detail = redact(result.stderr, endpoint) or f"curl exited with {result.returncode}"
        raise PipelineError(
            f"The test pipeline request failed: {detail}",
            exit_code=3,
            status="request_failed",
        )
    output = result.stdout.strip()
    http_status = int(output) if re.fullmatch(r"\d{3}", output) else None
    if http_status is None or not 200 <= http_status < 300:
        detail = output if http_status is None else f"HTTP {http_status}"
        raise PipelineError(
            f"The test pipeline endpoint did not return HTTP 2xx: {detail}",
            exit_code=3,
            status="request_failed",
            http_status=http_status,
        )
    return http_status


def emit(
    result: dict[str, Any],
    *,
    pretty: bool,
) -> None:
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=pretty,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Path inside the Git repository")
    parser.add_argument("--trusted-sha", required=True, help="Target SHA before the feature merge")
    parser.add_argument("--target-sha", required=True, help="Verified remote test SHA to trigger")
    parser.add_argument("--remote", help="Git remote containing the verified test branch")
    parser.add_argument("--test-branch", help="Remote test branch that must equal target SHA")
    parser.add_argument("--package-dir", help="Repository-relative directory containing package.json")
    parser.add_argument("--dry-run", action="store_true", help="Validate without sending a request")
    parser.add_argument("--pretty", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    package_dir: str | None = None
    remote: str | None = None
    test_branch: str | None = None
    transport_upgraded = False
    try:
        repo = repository_root(args.repo)
        trusted_sha = resolve_commit(repo, args.trusted_sha, "trusted SHA")
        target_sha = resolve_commit(repo, args.target_sha, "target SHA")
        require_trusted_ancestor(repo, trusted_sha, target_sha)
        if not args.dry_run:
            remote = resolve_remote(repo, args.remote)
            test_branch = resolve_test_branch(repo, args.test_branch)
            fetched_sha = fetch_remote_test_sha(repo, remote, test_branch)
            if fetched_sha != target_sha:
                raise PipelineError(
                    f"Fetched remote test SHA does not equal target SHA: {remote}/{test_branch}",
                    exit_code=2,
                    status="configuration_error",
                )
        package_dir, candidates = select_package_dir(repo, target_sha, args.package_dir)
        path = package_path(package_dir)
        target_command = script_from_package(package_at(repo, target_sha, path))
        trusted_command = script_from_package(package_at(repo, trusted_sha, path))
        if target_command is None:
            raise PipelineError(
                f"{path} does not define {SCRIPT_NAME} at the verified target SHA.",
                exit_code=2,
                status="configuration_error",
            )
        if trusted_command is None or trusted_command != target_command:
            raise PipelineError(
                f"{SCRIPT_NAME} changed relative to the pre-merge target; automatic triggering is blocked.",
                exit_code=2,
                status="configuration_error",
            )
        curl_arguments, endpoint, transport_upgraded = parse_curl(target_command)
        if args.dry_run:
            emit(
                {
                    "schema_version": 1,
                    "ok": True,
                    "status": "validated",
                    "triggered": False,
                    "package_dir": package_dir,
                    "package_json": path,
                    "script": SCRIPT_NAME,
                    "remote": remote,
                    "test_branch": test_branch,
                    "http_status": None,
                    "transport_upgraded": transport_upgraded,
                    "candidates": candidates,
                    "message": "Test pipeline webhook passed validation; no request was sent.",
                },
                pretty=args.pretty,
            )
            return 0
        http_status = invoke_curl(curl_arguments, endpoint)
        emit(
            {
                "schema_version": 1,
                "ok": True,
                "status": "triggered",
                "triggered": True,
                "package_dir": package_dir,
                "package_json": path,
                "script": SCRIPT_NAME,
                "remote": remote,
                "test_branch": test_branch,
                "http_status": http_status,
                "transport_upgraded": transport_upgraded,
                "candidates": candidates,
                "message": "Test pipeline trigger request was accepted; build completion was not checked.",
            },
            pretty=args.pretty,
        )
        return 0
    except PipelineError as error:
        emit(
            {
                "schema_version": 1,
                "ok": False,
                "status": error.status,
                "triggered": False,
                "package_dir": package_dir,
                "package_json": package_path(package_dir) if package_dir else None,
                "script": SCRIPT_NAME,
                "remote": remote,
                "test_branch": test_branch,
                "http_status": error.http_status,
                "transport_upgraded": transport_upgraded,
                "candidates": error.candidates,
                "message": str(error),
            },
            pretty=args.pretty,
        )
        return error.exit_code
    except Exception as error:  # pragma: no cover - last-resort structured failure
        emit(
            {
                "schema_version": 1,
                "ok": False,
                "status": "internal_error",
                "triggered": False,
                "package_dir": package_dir,
                "package_json": package_path(package_dir) if package_dir else None,
                "script": SCRIPT_NAME,
                "remote": remote,
                "test_branch": test_branch,
                "http_status": None,
                "transport_upgraded": transport_upgraded,
                "candidates": [],
                "message": f"Unexpected pipeline helper failure: {error}",
            },
            pretty=args.pretty,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
