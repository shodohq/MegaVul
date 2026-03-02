"""
Integration tests for GitHub platform functions.

GitHub tokens が config.yaml に設定されていない、または無効な場合は全テストをスキップする。
実際の HTTP 通信を行うため、ネットワーク接続と有効な GitHub token が必要。

実行方法:
    uv run pytest tests/git_platform/test_github_pf_integration.py -v
"""
import logging
import re

import pytest

# ---------------------------------------------------------------------------
# GitHub tokens が有効でない場合はモジュール全体をスキップ
# (add_github_token_and_check() がモジュールインポート時に API コールするため)
# ---------------------------------------------------------------------------
_IMPORT_ERROR: Exception | None = None
try:
    from megavul.git_platform.github_pf import (
        find_github_commits_from_pull,
        find_potential_commits_from_github,
    )
    _GITHUB_AVAILABLE = True
except Exception as e:
    _GITHUB_AVAILABLE = False
    _IMPORT_ERROR = e

pytestmark = pytest.mark.skipif(
    not _GITHUB_AVAILABLE,
    reason=f'GitHub tokens not available or invalid: {_IMPORT_ERROR}',
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_github_commit_url(url: str) -> bool:
    """github.com の commit URL 形式かどうかを確認する。"""
    return bool(re.match(r'^https://github\.com/.+/commit/[0-9a-f]{40}$', url))


# ---------------------------------------------------------------------------
# find_github_commits_from_pull
# ---------------------------------------------------------------------------

class TestFindGithubCommitsFromPull:
    """
    テスト対象 PR: https://github.com/python/cpython/pull/103993
    このPRとコミットは github_pf.py のコメントでも参照されている既知の安定したリソース。
    """

    REPO = 'python/cpython'
    PULL_ID = 103993

    def test_returns_list(self):
        result = find_github_commits_from_pull(logger, self.REPO, self.PULL_ID)
        assert isinstance(result, list)

    def test_commit_urls_are_valid(self):
        result = find_github_commits_from_pull(logger, self.REPO, self.PULL_ID)
        assert len(result) > 0, 'PR にコミットが1件以上あること'
        for url in result:
            assert is_github_commit_url(url), f'不正な commit URL: {url}'

    def test_commit_urls_belong_to_repo(self):
        result = find_github_commits_from_pull(logger, self.REPO, self.PULL_ID)
        for url in result:
            assert f'github.com/{self.REPO}/commit/' in url, \
                f'commit URL がリポジトリ {self.REPO} に属していない: {url}'

    def test_nonexistent_repo_returns_empty(self):
        result = find_github_commits_from_pull(
            logger, 'nonexistent-user-xyzxyz/nonexistent-repo-xyzxyz', 1
        )
        assert result == []

    def test_nonexistent_pull_returns_empty(self):
        result = find_github_commits_from_pull(logger, self.REPO, 9_999_999)
        assert result == []


# ---------------------------------------------------------------------------
# find_potential_commits_from_github
# ---------------------------------------------------------------------------

class TestFindPotentialCommitsFromGithub:
    """
    find_potential_commits_from_github() のエンドツーエンドテスト。
    テストデータは github_pf.py のコメントで参照されている既知のリソースを使用。
    """

    COMMIT_URL = 'https://github.com/python/cpython/commit/c120bc2d354ca3d27d0c7a53bf65574ddaabaf3a'
    PR_URL = 'https://github.com/python/cpython/pull/103993'

    def test_commit_url_returns_itself(self):
        result = find_potential_commits_from_github(logger, self.COMMIT_URL, [])
        assert self.COMMIT_URL in result

    def test_pr_url_returns_commit_urls(self):
        result = find_potential_commits_from_github(logger, self.PR_URL, [])
        assert isinstance(result, list)
        assert len(result) > 0
        for url in result:
            assert is_github_commit_url(url), f'不正な commit URL: {url}'

    def test_pr_url_skipped_when_commit_already_found(self):
        """同リポジトリの commit URL が url_list にある場合は PR をスキップして [] を返す。"""
        result = find_potential_commits_from_github(logger, self.PR_URL, [self.COMMIT_URL])
        assert result == []

    def test_pull_commit_url_is_normalized_to_commit_url(self):
        """pull/.../commits/... 形式の URL が commit URL に正規化されて返ること。"""
        pull_commit_url = (
            'https://github.com/python/cpython/pull/103993/commits/'
            'c120bc2d354ca3d27d0c7a53bf65574ddaabaf3a'
        )
        result = find_potential_commits_from_github(logger, pull_commit_url, [])
        assert self.COMMIT_URL in result

    def test_unrelated_url_returns_empty(self):
        """リポジトリトップなど commit/PR/Issue でない URL は [] を返すこと。"""
        result = find_potential_commits_from_github(
            logger, 'https://github.com/python/cpython', []
        )
        assert result == []
