"""
Integration tests for GitLab gnome.org v4 API functions.

PAT トークンが megavul/gitlab_gnome_token.txt に存在しない場合は全テストをスキップする。
実際の HTTP 通信を行うため、ネットワーク接続と有効な PAT が必要。

実行方法:
    uv run pytest tests/git_platform/test_gitlab_v4_api_integration.py -v
"""
import re
import pytest
import gitlab

from megavul.git_platform.gitlab_pf import (
    load_gitlab_gnome_token,
    find_commits_from_mr_via_v4_api,
    find_commits_from_issue_via_v4_api,
    find_commits_from_gitlab,
    GITLAB_GNOME_ORG_HOST,
)

# ---------------------------------------------------------------------------
# Fixtures
# Fixture: テスト関数に渡す前提条件をセットアップする仕組み。テスト関数の引数名とフィクスチャ名を一致させると、pytest が自動的にフィクスチャを呼び出して値を渡す。
# def test_hogefuga(pat_token): みたいな関数があればそこに pat_token fixture の値が渡される。
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def pat_token() -> str:
    """
    PAT トークンを読み込む。ファイルが存在しない場合はモジュール全体をスキップ。
    """
    token = load_gitlab_gnome_token()
    if token is None:
        pytest.skip('megavul/gitlab_gnome_token.txt が存在しないため integration test をスキップ')
    return token


@pytest.fixture(scope='module')
def gl_gnome(pat_token: str) -> gitlab.Gitlab:
    """PAT 認証済みの gitlab.Gitlab クライアント。"""
    return gitlab.Gitlab(GITLAB_GNOME_ORG_HOST, private_token=pat_token)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_gnome_commit_url(url: str) -> bool:
    """gitlab.gnome.org の commit URL 形式かどうかを確認する。"""
    return bool(re.match(
        r'^https://gitlab\.gnome\.org/.+/-/commit/[0-9a-f]{40}$', url
    ))


# ---------------------------------------------------------------------------
# MR via v4 API
# ---------------------------------------------------------------------------

class TestMRViaV4ApiIntegration:
    """
    テスト対象 MR: https://gitlab.gnome.org/GNOME/gdk-pixbuf/-/merge_requests/121
    小さな MR で commit 数が閾値以内であることが知られている。
    """

    MR_PROJECT = 'GNOME/gdk-pixbuf'
    MR_IID = 121

    def test_returns_list(self, gl_gnome):
        result = find_commits_from_mr_via_v4_api(gl_gnome, self.MR_PROJECT, self.MR_IID)
        assert isinstance(result, list)

    def test_commit_urls_are_valid(self, gl_gnome):
        result = find_commits_from_mr_via_v4_api(gl_gnome, self.MR_PROJECT, self.MR_IID)
        assert len(result) > 0, 'MR にコミットが1件以上あること'
        for url in result:
            assert is_gnome_commit_url(url), f'不正な commit URL: {url}'

    def test_nonexistent_mr_returns_empty(self, gl_gnome):
        result = find_commits_from_mr_via_v4_api(gl_gnome, self.MR_PROJECT, 999999)
        assert result == []


# ---------------------------------------------------------------------------
# Issue via v4 API
# ---------------------------------------------------------------------------

class TestIssueViaV4ApiIntegration:
    """
    テスト対象 Issue: https://gitlab.gnome.org/GNOME/gimp/-/issues/8230
    """

    ISSUE_PROJECT = 'GNOME/gimp'
    ISSUE_IID = 8230

    def test_returns_list(self, gl_gnome):
        result = find_commits_from_issue_via_v4_api(
            gl_gnome, self.ISSUE_PROJECT, self.ISSUE_IID, host=GITLAB_GNOME_ORG_HOST
        )
        assert isinstance(result, list)

    def test_commit_urls_are_valid(self, gl_gnome):
        result = find_commits_from_issue_via_v4_api(
            gl_gnome, self.ISSUE_PROJECT, self.ISSUE_IID, host=GITLAB_GNOME_ORG_HOST
        )
        for url in result:
            assert is_gnome_commit_url(url), f'不正な commit URL: {url}'

    def test_nonexistent_issue_returns_empty(self, gl_gnome):
        result = find_commits_from_issue_via_v4_api(
            gl_gnome, self.ISSUE_PROJECT, 999999, host=GITLAB_GNOME_ORG_HOST
        )
        assert result == []


# ---------------------------------------------------------------------------
# find_commits_from_gitlab routing (end-to-end)
# ---------------------------------------------------------------------------

class TestFindCommitsFromGitlabE2E:
    """
    find_commits_from_gitlab() のエンドツーエンドテスト。
    内部でトークンファイルを読むため、pat_token fixture で skip 制御する。
    """

    def test_mr_url_returns_commits(self, pat_token):
        url = 'https://gitlab.gnome.org/GNOME/gdk-pixbuf/-/merge_requests/121'
        result = find_commits_from_gitlab(url)
        assert isinstance(result, list)
        assert len(result) > 0
        for u in result:
            assert is_gnome_commit_url(u), f'不正な commit URL: {u}'

    def test_issue_url_returns_list(self, pat_token):
        url = 'https://gitlab.gnome.org/GNOME/gimp/-/issues/8230'
        result = find_commits_from_gitlab(url)
        assert isinstance(result, list)
        for u in result:
            assert is_gnome_commit_url(u), f'不正な commit URL: {u}'

    def test_mr_url_with_fragment_is_handled(self, pat_token):
        url = 'https://gitlab.gnome.org/GNOME/gdk-pixbuf/-/merge_requests/121#note_99999'
        result = find_commits_from_gitlab(url)
        assert isinstance(result, list)
