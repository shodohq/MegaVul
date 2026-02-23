import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Phase 1: Token loading
# ---------------------------------------------------------------------------

class TestGnomeTokenLoading:
    def test_token_path_points_to_megavul_base(self):
        from megavul.util.storage import StorageLocation
        path = StorageLocation.gitlab_gnome_token_path()
        assert path.name == 'gitlab_gnome_token.txt'
        assert path.parent == StorageLocation.base_dir()

    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        from megavul.util.storage import StorageLocation
        monkeypatch.setattr(StorageLocation, 'gitlab_gnome_token_path',
                            staticmethod(lambda: tmp_path / 'gitlab_gnome_token.txt'))
        from megavul.git_platform import gitlab_pf
        token = gitlab_pf.load_gitlab_gnome_token()
        assert token is None

    def test_returns_stripped_token_when_file_exists(self, tmp_path, monkeypatch):
        from megavul.util.storage import StorageLocation
        token_file = tmp_path / 'gitlab_gnome_token.txt'
        token_file.write_text('  glpat-abc123  \n')
        monkeypatch.setattr(StorageLocation, 'gitlab_gnome_token_path',
                            staticmethod(lambda: token_file))
        from megavul.git_platform import gitlab_pf
        token = gitlab_pf.load_gitlab_gnome_token()
        assert token == 'glpat-abc123'

    def test_returns_none_for_empty_file(self, tmp_path, monkeypatch):
        from megavul.util.storage import StorageLocation
        token_file = tmp_path / 'gitlab_gnome_token.txt'
        token_file.write_text('   \n')
        monkeypatch.setattr(StorageLocation, 'gitlab_gnome_token_path',
                            staticmethod(lambda: token_file))
        from megavul.git_platform import gitlab_pf
        token = gitlab_pf.load_gitlab_gnome_token()
        assert token is None


# ---------------------------------------------------------------------------
# Phase 2: URL parsing
# ---------------------------------------------------------------------------

class TestGitLabGnomeUrlParsing:
    def setup_method(self):
        from megavul.git_platform.gitlab_pf import parse_gitlab_url
        self.parse = parse_gitlab_url

    def test_mr_url(self):
        result = self.parse('https://gitlab.gnome.org/GNOME/gdk-pixbuf/-/merge_requests/121')
        assert result == {
            'host': 'https://gitlab.gnome.org',
            'project_path': 'GNOME/gdk-pixbuf',
            'iid': 121,
            'type': 'merge_request',
        }

    def test_issue_url(self):
        result = self.parse('https://gitlab.gnome.org/GNOME/gimp/-/issues/8230')
        assert result == {
            'host': 'https://gitlab.gnome.org',
            'project_path': 'GNOME/gimp',
            'iid': 8230,
            'type': 'issue',
        }

    def test_multi_level_namespace(self):
        result = self.parse('https://gitlab.gnome.org/ns/sub/project/-/merge_requests/5')
        assert result is not None
        assert result['project_path'] == 'ns/sub/project'
        assert result['iid'] == 5
        assert result['type'] == 'merge_request'

    def test_commit_url_returns_none(self):
        result = self.parse('https://gitlab.gnome.org/GNOME/gimp/-/commit/abc123')
        assert result is None

    def test_invalid_url_returns_none(self):
        assert self.parse('https://example.com/foo') is None
        assert self.parse('not-a-url') is None


# ---------------------------------------------------------------------------
# Phase 3: MR commits via v4 API
# ---------------------------------------------------------------------------

class TestFindCommitsFromMRViaV4Api:
    def setup_method(self):
        from megavul.git_platform.gitlab_pf import find_commits_from_mr_via_v4_api
        self.func = find_commits_from_mr_via_v4_api

    def _make_gl(self, commits):
        gl = MagicMock()
        mr = MagicMock()
        mr.commits.return_value = commits
        gl.projects.get.return_value.mergerequests.get.return_value = mr
        return gl

    def _make_commit(self, url):
        c = MagicMock()
        c.web_url = url
        return c

    def test_normal_case_returns_commit_urls(self):
        commits = [self._make_commit(f'https://gitlab.gnome.org/proj/-/commit/{i}')
                   for i in range(3)]
        gl = self._make_gl(commits)
        result = self.func(gl, 'GNOME/gdk-pixbuf', 121)
        assert len(result) == 3
        assert result[0] == 'https://gitlab.gnome.org/proj/-/commit/0'

    def test_exceeds_threshold_returns_empty(self):
        from megavul.git_platform.gitlab_pf import GITLAB_COMMIT_THRESHOLD
        commits = [self._make_commit(f'https://gitlab.gnome.org/proj/-/commit/{i}')
                   for i in range(GITLAB_COMMIT_THRESHOLD + 1)]
        gl = self._make_gl(commits)
        result = self.func(gl, 'GNOME/gdk-pixbuf', 121)
        assert result == []

    def test_gitlab_get_error_returns_empty(self):
        from gitlab.exceptions import GitlabGetError
        gl = MagicMock()
        gl.projects.get.side_effect = GitlabGetError('404 Not Found', 404)
        result = self.func(gl, 'GNOME/nonexistent', 999)
        assert result == []


# ---------------------------------------------------------------------------
# Phase 4: Issue commits via v4 API
# ---------------------------------------------------------------------------

class TestFindCommitsFromIssueViaV4Api:
    def setup_method(self):
        from megavul.git_platform.gitlab_pf import find_commits_from_issue_via_v4_api
        self.func = find_commits_from_issue_via_v4_api

    def _make_note(self, body):
        note = MagicMock()
        note.body = body
        return note

    def _make_project(self, state, notes):
        gl = MagicMock()
        issue = MagicMock()
        issue.state = state
        issue.notes.list.return_value = notes
        gl.projects.get.return_value.issues.get.return_value = issue
        return gl

    def test_open_issue_returns_empty(self):
        gl = self._make_project('opened', [])
        result = self.func(gl, 'GNOME/gimp', 1)
        assert result == []

    def test_closed_via_commit_returns_url(self):
        notes = [self._make_note('closed via commit abc123def456abc123def456abc123def456abc1')]
        gl = self._make_project('closed', notes)
        result = self.func(gl, 'GNOME/gimp', 1, host='https://gitlab.gnome.org')
        assert len(result) == 1
        assert 'abc123def456abc123def456abc123def456abc1' in result[0]

    def test_closed_via_mr_delegates_to_mr_func(self):
        notes = [self._make_note('closed via merge request !42')]
        gl = self._make_project('closed', notes)
        commit_url = 'https://gitlab.gnome.org/GNOME/gimp/-/commit/deadbeef'
        with patch('megavul.git_platform.gitlab_pf.find_commits_from_mr_via_v4_api',
                   return_value=[commit_url]) as mock_mr:
            result = self.func(gl, 'GNOME/gimp', 8230, host='https://gitlab.gnome.org')
        mock_mr.assert_called_once_with(gl, 'GNOME/gimp', 42)
        assert result == [commit_url]

    def test_exceeds_threshold_returns_empty(self):
        from megavul.git_platform.gitlab_pf import GITLAB_COMMIT_THRESHOLD
        notes = [self._make_note(f'closed via commit {'a' * 40}')
                 for _ in range(GITLAB_COMMIT_THRESHOLD + 1)]
        gl = self._make_project('closed', notes)
        result = self.func(gl, 'GNOME/gimp', 1)
        assert result == []

    def test_gitlab_get_error_returns_empty(self):
        from gitlab.exceptions import GitlabGetError
        gl = MagicMock()
        gl.projects.get.side_effect = GitlabGetError('404 Not Found', 404)
        result = self.func(gl, 'GNOME/nonexistent', 999)
        assert result == []

    def test_notes_list_called_with_system_true(self):
        notes = []
        gl = self._make_project('closed', notes)
        self.func(gl, 'GNOME/gimp', 1)
        issue = gl.projects.get.return_value.issues.get.return_value
        issue.notes.list.assert_called_once_with(system=True)


# ---------------------------------------------------------------------------
# Phase 5: Routing
# ---------------------------------------------------------------------------

class TestFindCommitsFromGitlabRouting:
    def setup_method(self):
        from megavul.git_platform.gitlab_pf import find_commits_from_gitlab
        self.func = find_commits_from_gitlab

    def test_gnome_mr_url_uses_v4_api(self):
        expected = ['https://gitlab.gnome.org/GNOME/gdk-pixbuf/-/commit/abc']
        with patch('megavul.git_platform.gitlab_pf.find_commits_from_mr_via_v4_api',
                   return_value=expected) as mock_mr, \
             patch('megavul.git_platform.gitlab_pf.load_gitlab_gnome_token', return_value=None):
            result = self.func('https://gitlab.gnome.org/GNOME/gdk-pixbuf/-/merge_requests/121')
        mock_mr.assert_called_once()
        assert result == expected

    def test_gnome_issue_url_uses_v4_api(self):
        expected = ['https://gitlab.gnome.org/GNOME/gimp/-/commit/abc']
        with patch('megavul.git_platform.gitlab_pf.find_commits_from_issue_via_v4_api',
                   return_value=expected) as mock_issue, \
             patch('megavul.git_platform.gitlab_pf.load_gitlab_gnome_token', return_value=None):
            result = self.func('https://gitlab.gnome.org/GNOME/gimp/-/issues/8230')
        mock_issue.assert_called_once()
        assert result == expected

    def test_gitlab_com_uses_legacy_path(self):
        with patch('megavul.git_platform.gitlab_pf.find_commits_from_pr_in_gitlab',
                   return_value=['https://gitlab.com/x/y/-/commit/abc']) as mock_legacy:
            result = self.func('https://gitlab.com/gnutls/gnutls/merge_requests/657')
        mock_legacy.assert_called_once()

    def test_gnome_mr_with_pat_token(self):
        with patch('megavul.git_platform.gitlab_pf.find_commits_from_mr_via_v4_api',
                   return_value=[]) as mock_mr, \
             patch('megavul.git_platform.gitlab_pf.load_gitlab_gnome_token',
                   return_value='glpat-mytoken'), \
             patch('megavul.git_platform.gitlab_pf.gitlab.Gitlab') as mock_gl_cls:
            self.func('https://gitlab.gnome.org/GNOME/gdk-pixbuf/-/merge_requests/121')
        mock_gl_cls.assert_called_once_with(
            'https://gitlab.gnome.org', private_token='glpat-mytoken')

    def test_fragment_is_stripped(self):
        with patch('megavul.git_platform.gitlab_pf.find_commits_from_issue_via_v4_api',
                   return_value=[]) as mock_issue, \
             patch('megavul.git_platform.gitlab_pf.load_gitlab_gnome_token', return_value=None):
            self.func('https://gitlab.gnome.org/GNOME/gimp/-/issues/8230#note_12345')
        mock_issue.assert_called_once()
