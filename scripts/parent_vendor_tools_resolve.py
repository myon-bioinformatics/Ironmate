"""Resolve the parent repository default-branch tip for catalog audit tooling."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

PARENT_REPOSITORY = "myon-bioinformatics/myon-bioinformatics"
EXPECTED_REPOSITORY_ID = 638801160


def _git_env():
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
    )
    return env


def _git_base():
    return [
        "git",
        "-c",
        "credential.helper=",
        "-c",
        "core.askPass=",
        "-c",
        "http.extraHeader=",
    ]


def _ls_remote_symref_head(remote: str) -> tuple[str, str]:
    output = subprocess.run(
        _git_base() + ["ls-remote", "--symref", remote, "HEAD"],
        env=_git_env(),
        capture_output=True,
        timeout=120,
        check=True,
    ).stdout.decode("utf-8", "replace")
    branch = None
    sha = None
    for line in output.splitlines():
        if line.startswith("ref: refs/heads/"):
            branch = line.split("refs/heads/", 1)[1].split("\t", 1)[0]
        elif re.fullmatch(r"[0-9a-f]{40}\tHEAD", line):
            sha = line.split("\t", 1)[0]
    if not branch or not sha:
        raise SystemExit("could not resolve parent default branch from ls-remote")
    return branch, sha


def _ls_remote_branch_tip(remote: str, branch: str) -> str:
    output = subprocess.run(
        _git_base() + ["ls-remote", "--heads", remote, branch],
        env=_git_env(),
        capture_output=True,
        timeout=120,
        check=True,
    ).stdout.decode("utf-8", "replace").strip()
    if not output:
        raise SystemExit("missing branch {} on {}".format(branch, remote))
    sha = output.split()[0]
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SystemExit("invalid branch tip from ls-remote")
    return sha


def _github_repo_record(repository: str, token: str | None) -> dict:
    url = "https://api.github.com/repos/" + repository
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ironmate-parent-vendor-tools-resolve",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise SystemExit("GitHub API request failed: {}".format(error.code)) from error
    except urllib.error.URLError as error:
        raise SystemExit("GitHub API request failed") from error
    if not isinstance(payload, dict):
        raise SystemExit("invalid GitHub API response")
    return payload


def resolve_parent_vendor_tools_head(
    repository: str = PARENT_REPOSITORY,
    expected_repository_id: int = EXPECTED_REPOSITORY_ID,
    *,
    token: str | None = None,
) -> dict[str, object]:
    remote = "https://github.com/" + repository + ".git"
    branch, head_sha = _ls_remote_symref_head(remote)
    record = _github_repo_record(repository, token)
    repo_id = record.get("id")
    if not isinstance(repo_id, int) or repo_id != expected_repository_id:
        raise SystemExit(
            "repository_id mismatch: expected {} got {}".format(expected_repository_id, repo_id)
        )
    full_name = record.get("full_name")
    if not isinstance(full_name, str) or full_name.casefold() != repository.casefold():
        raise SystemExit("repository full_name mismatch")
    if record.get("private") is not False:
        raise SystemExit("expected public parent repository")
    if record.get("archived") is not False:
        raise SystemExit("expected non-archived parent repository")
    default_branch = record.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch:
        raise SystemExit("missing default_branch from GitHub API")
    if default_branch != branch:
        raise SystemExit(
            "default_branch mismatch: api {} ls-remote {}".format(default_branch, branch)
        )
    branch_tip = _ls_remote_branch_tip(remote, default_branch)
    if branch_tip != head_sha:
        raise SystemExit("HEAD sha does not match default branch tip from ls-remote")
    return {
        "repository": repository,
        "repository_id": repo_id,
        "branch": branch,
        "sha": head_sha,
    }


def fetch_parent_vendor_tool_files(
    sha: str,
    repository: str = PARENT_REPOSITORY,
) -> dict[str, bytes | dict]:
    base = "https://raw.githubusercontent.com/{}/{}".format(repository, sha)

    def read(path: str) -> bytes:
        with urllib.request.urlopen(base + "/" + path, timeout=60) as response:
            return response.read()

    return {
        "vendor-consumers.json": json.loads(read("vendor-consumers.json").decode("utf-8")),
        "vendor_consumers.py": read("vendor_consumers.py"),
        "vendor_sync.py": read("vendor_sync.py"),
    }


def _emit_github_actions(resolved: dict[str, object]) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        raise SystemExit("GITHUB_OUTPUT is required for --emit-github-actions")
    with open(github_output, "a", encoding="utf-8") as handle:
        handle.write("sha={}\n".format(resolved["sha"]))
        handle.write("branch={}\n".format(resolved["branch"]))
        handle.write("repository_id={}\n".format(resolved["repository_id"]))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## Resolved parent vendor tools\n\n")
            handle.write(
                "- Repository: `{}` (id `{}`)\n".format(resolved["repository"], resolved["repository_id"])
            )
            handle.write("- Default branch: `{}`\n".format(resolved["branch"]))
            handle.write("- Commit: `{}`\n".format(resolved["sha"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        default=PARENT_REPOSITORY,
        help="parent OWNER/NAME (default: %(default)s)",
    )
    parser.add_argument(
        "--expected-repository-id",
        type=int,
        default=EXPECTED_REPOSITORY_ID,
        help="required GitHub repository id (default: %(default)s)",
    )
    parser.add_argument(
        "--emit-github-actions",
        action="store_true",
        help="write GITHUB_OUTPUT and GITHUB_STEP_SUMMARY for Actions",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print resolved metadata as JSON on stdout",
    )
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or None
    resolved = resolve_parent_vendor_tools_head(
        args.repository,
        args.expected_repository_id,
        token=token,
    )
    if args.emit_github_actions:
        _emit_github_actions(resolved)
    if args.json or not args.emit_github_actions:
        json.dump(resolved, sys.stdout)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
