"""
generate_source_file のユニットテスト。

主に「言語名 → ファイル拡張子」のマッピングが正しく機能し、
JavaScript ファイルが .javascript ではなく .js で保存されることを確認する。
"""

import json
from pathlib import Path
from unittest.mock import patch


from megavul.git_platform.common import (
    CommitFile,
    CommitInfo,
    CveWithCommitInfo,
    NonVulnerableFunction,
    VulnerableFunction,
)
from megavul.pipeline.extract_graph_and_abstract import (
    _language_to_ext,
    generate_source_file,
)


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------


def _make_vul_func(func_before="function foo(){}", func_after="function foo(){}"):
    return VulnerableFunction(
        func_name="foo",
        parameter_list_signature_before="",
        parameter_list_before=[],
        return_type_before="",
        func_before=func_before,
        abstract_func_before="",
        abstract_symbol_table_before={},
        func_graph_path_before=None,
        parameter_list_signature_after="",
        parameter_list_after=[],
        return_type_after="",
        func_after=func_after,
        abstract_func_after="",
        abstract_symbol_table_after={},
        func_graph_path_after=None,
        diff_func="",
        diff_line_info={},
    )


def _make_non_vul_func(func="function bar(){}"):
    return NonVulnerableFunction(
        func_name="bar",
        parameter_list_signature="",
        parameter_list=[],
        return_type="",
        func=func,
        abstract_func="",
        abstract_symbol_table={},
        func_graph_path=None,
    )


def _make_cve(language: str, file_name: str = "app.js") -> CveWithCommitInfo:
    return CveWithCommitInfo(
        cve_id="CVE-2024-0001",
        cwe_ids=[],
        description="",
        publish_date="",
        last_modify_date="",
        commits=[
            CommitInfo(
                repo_name="test/repo",
                commit_msg="fix",
                commit_hash="abc123",
                parent_commit_hash="def456",
                commit_date=0,
                raw_file_paths=[file_name],
                files=[
                    CommitFile(
                        file_name=file_name,
                        file_path=file_name,
                        language=language,
                        vulnerable_functions=[_make_vul_func()],
                        non_vulnerable_functions=[_make_non_vul_func()],
                    )
                ],
                git_url="https://github.com/test/repo",
            )
        ],
        cvss_vector=None,
        cvss_base_score=None,
        cvss_base_severity=None,
        cvss_is_v3=None,
    )


# ---------------------------------------------------------------------------
# _language_to_ext のユニットテスト
# ---------------------------------------------------------------------------


class TestLanguageToExt:
    def test_javascript_maps_to_js(self):
        assert _language_to_ext("javascript") == "js"

    def test_typescript_maps_to_ts(self):
        assert _language_to_ext("typescript") == "ts"

    def test_unknown_language_returns_itself(self):
        assert _language_to_ext("go") == "go"
        assert _language_to_ext("java") == "java"
        assert _language_to_ext("c") == "c"

    def test_javascript_is_not_saved_as_javascript_ext(self):
        assert _language_to_ext("javascript") != "javascript"


# ---------------------------------------------------------------------------
# generate_source_file のテスト（一時ディレクトリを使用）
# ---------------------------------------------------------------------------


class TestGenerateSourceFileExtension:
    def _run(self, cve_list, save_dir: Path):
        """generate_source_file を一時ディレクトリに向けて実行するヘルパー。"""
        with patch(
            "megavul.pipeline.extract_graph_and_abstract.generate_source_dir",
            save_dir,
        ):
            generate_source_file(cve_list, using_cache=False)

    def test_javascript_files_have_js_extension(self, tmp_path):
        cve = _make_cve(language="javascript", file_name="app.js")
        self._run([cve], tmp_path)

        js_files = list(tmp_path.rglob("*.js"))
        javascript_files = list(tmp_path.rglob("*.javascript"))

        assert len(js_files) > 0, ".js ファイルが生成されていない"
        assert len(javascript_files) == 0, (
            ".javascript ファイルが生成されてしまっている"
        )

    def test_vul_before_and_after_both_use_js(self, tmp_path):
        cve = _make_cve(language="javascript", file_name="app.js")
        self._run([cve], tmp_path)

        before_file = tmp_path / "test/repo/abc123/app.js/vul/before/0/0.js"
        after_file = tmp_path / "test/repo/abc123/app.js/vul/after/0/0.js"

        assert before_file.exists(), f"vul/before ファイルが見つからない: {before_file}"
        assert after_file.exists(), f"vul/after ファイルが見つからない: {after_file}"

    def test_non_vul_uses_js(self, tmp_path):
        cve = _make_cve(language="javascript", file_name="app.js")
        self._run([cve], tmp_path)

        non_vul_file = tmp_path / "test/repo/abc123/app.js/non_vul/0/0.js"
        assert non_vul_file.exists(), f"non_vul ファイルが見つからない: {non_vul_file}"

    def test_file_content_is_preserved(self, tmp_path):
        cve = _make_cve(language="javascript", file_name="app.js")
        self._run([cve], tmp_path)

        before_file = tmp_path / "test/repo/abc123/app.js/vul/before/0/0.js"
        assert before_file.read_text() == "function foo(){}"

    def test_index_json_is_created(self, tmp_path):
        cve = _make_cve(language="javascript", file_name="app.js")
        self._run([cve], tmp_path)

        index_file = tmp_path / "MegaVul_index.json"
        assert index_file.exists()
        index = json.loads(index_file.read_text())
        assert len(index) == 1

    def test_go_files_still_use_go_extension(self, tmp_path):
        """JavaScript 以外の言語が影響を受けないことを確認する。"""
        cve = _make_cve(language="go", file_name="main.go")
        self._run([cve], tmp_path)

        go_files = list(tmp_path.rglob("*.go"))
        assert len(go_files) > 0, ".go ファイルが生成されていない"
