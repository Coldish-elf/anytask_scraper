from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from anytask_scraper.github_clone import (
    GitHubRepoInfo,
    clone_github_repo,
    extract_github_links,
    parse_github_url,
)


def test_standard_repo_url() -> None:
    info = parse_github_url("https://github.com/user/repo")
    assert info is not None
    assert info.owner == "user"
    assert info.repo == "repo"
    assert info.branch is None


def test_repo_url_with_git_suffix() -> None:
    info = parse_github_url("https://github.com/user/repo.git")
    assert info is not None
    assert info.repo == "repo"


def test_tree_branch_url() -> None:
    info = parse_github_url("https://github.com/user/repo/tree/feature-branch")
    assert info is not None
    assert info.owner == "user"
    assert info.repo == "repo"
    assert info.branch == "feature-branch"


def test_tree_branch_with_slashes() -> None:
    info = parse_github_url("https://github.com/user/repo/tree/feature/sub/branch")
    assert info is not None
    assert info.branch == "feature/sub/branch"


def test_blob_url() -> None:
    info = parse_github_url("https://github.com/user/repo/blob/main/src/file.py")
    assert info is not None
    assert info.owner == "user"
    assert info.repo == "repo"
    assert info.branch == "main"


def test_pull_request_url_returns_none() -> None:
    assert parse_github_url("https://github.com/user/repo/pull/123") is None


def test_commit_url_returns_none() -> None:
    assert parse_github_url("https://github.com/user/repo/commit/abc123") is None


def test_issues_url_returns_none() -> None:
    assert parse_github_url("https://github.com/user/repo/issues/5") is None


def test_action_pages_three_segments_return_none() -> None:
    assert parse_github_url("https://github.com/user/repo/pulls") is None
    assert parse_github_url("https://github.com/user/repo/issues") is None
    assert parse_github_url("https://github.com/user/repo/actions") is None
    assert parse_github_url("https://github.com/user/repo/releases") is None
    assert parse_github_url("https://github.com/user/repo/settings") is None
    assert parse_github_url("https://github.com/user/repo/wiki") is None


def test_non_github_url_returns_none() -> None:
    assert parse_github_url("https://gitlab.com/user/repo") is None


def test_single_segment_returns_none() -> None:
    assert parse_github_url("https://github.com/settings") is None


def test_www_github() -> None:
    info = parse_github_url("https://www.github.com/user/repo")
    assert info is not None
    assert info.owner == "user"
    assert info.repo == "repo"


def test_http_no_https() -> None:
    info = parse_github_url("http://github.com/user/repo")
    assert info is not None
    assert info.owner == "user"
    assert info.repo == "repo"


def test_mixed_urls() -> None:
    links = [
        "https://github.com/alice/project",
        "https://colab.research.google.com/drive/1ABC",
        "https://example.com/random",
        "https://github.com/bob/tool",
    ]
    results = extract_github_links(links)
    owners = {r.owner for r in results}
    assert "alice" in owners
    assert "bob" in owners
    assert len(results) == 2


def test_deduplication() -> None:
    links = [
        "https://github.com/user/repo",
        "https://github.com/user/repo",
    ]
    results = extract_github_links(links)
    assert len(results) == 1


def test_dedup_different_paths_same_repo() -> None:
    links = [
        "https://github.com/user/repo",
        "https://github.com/user/repo/tree/feature-x",
    ]
    results = extract_github_links(links)
    assert len(results) == 2
    branches = {r.branch for r in results}
    assert None in branches
    assert "feature-x" in branches


def test_empty_list() -> None:
    assert extract_github_links([]) == []


def test_no_github() -> None:
    links = [
        "https://colab.research.google.com/drive/1XYZ",
        "https://random.org/page",
    ]
    assert extract_github_links(links) == []

def test_clone_default_branch(tmp_path: Path) -> None:
    info = GitHubRepoInfo(owner="user", repo="myrepo")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = clone_github_repo(info, tmp_path)

    assert result.success is True
    assert result.path == tmp_path / "myrepo"
    mock_run.assert_called_once_with(
        ["git", "clone", "https://github.com/user/myrepo.git", str(tmp_path / "myrepo")],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )


def test_clone_with_branch(tmp_path: Path) -> None:
    info = GitHubRepoInfo(owner="user", repo="myrepo", branch="develop")
    target = tmp_path / "myrepo"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = clone_github_repo(info, tmp_path)

    assert result.success is True
    assert mock_run.call_count == 2
    clone_call, checkout_call = mock_run.call_args_list
    assert clone_call == call(
        ["git", "clone", "https://github.com/user/myrepo.git", str(target)],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    assert checkout_call == call(
        ["git", "checkout", "develop"],
        cwd=str(target),
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )


def test_already_cloned(tmp_path: Path) -> None:
    info = GitHubRepoInfo(owner="user", repo="myrepo")
    target = tmp_path / "myrepo"
    target.mkdir()
    (target / ".git").mkdir()

    with patch("subprocess.run") as mock_run:
        result = clone_github_repo(info, tmp_path)

    assert result.success is True
    assert result.reason == "already_cloned"
    assert result.path == target
    mock_run.assert_not_called()


def test_dir_exists_not_git(tmp_path: Path) -> None:
    info = GitHubRepoInfo(owner="user", repo="myrepo")
    target = tmp_path / "myrepo"
    target.mkdir()

    with patch("subprocess.run") as mock_run:
        result = clone_github_repo(info, tmp_path)

    assert result.success is False
    assert result.reason == "dir_exists_not_git"
    mock_run.assert_not_called()


def test_git_not_found(tmp_path: Path) -> None:
    info = GitHubRepoInfo(owner="user", repo="myrepo")
    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = clone_github_repo(info, tmp_path)

    assert result.success is False
    assert result.reason == "git_not_found"


def test_timeout(tmp_path: Path) -> None:
    info = GitHubRepoInfo(owner="user", repo="myrepo")
    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git", timeout=120),
    ):
        result = clone_github_repo(info, tmp_path)

    assert result.success is False
    assert result.reason == "timeout"


def test_clone_failure(tmp_path: Path) -> None:
    info = GitHubRepoInfo(owner="user", repo="myrepo")
    error = subprocess.CalledProcessError(
        returncode=128,
        cmd="git clone",
        stderr="fatal: repository 'https://github.com/user/myrepo.git/' not found\n",
    )
    with patch("subprocess.run", side_effect=error):
        result = clone_github_repo(info, tmp_path)

    assert result.success is False
    assert "not found" in result.reason
