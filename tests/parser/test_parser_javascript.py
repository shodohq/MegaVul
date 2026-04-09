"""
tests/parser/test_parser_javascript.py

ParserJavaScript の parse_file() を合成フィクスチャで動作確認する。

tree-sitter-javascript の .so が未ビルドかつ CLI が使えない環境ではテストをスキップする。
"""

import json
import logging
import pytest

from pathlib import Path

# ---- フィクスチャファイルパス -------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "parser"

# 合成フィクスチャ（関数8つ、各種別を網羅）
SAMPLE_JS = FIXTURES_DIR / "sample.js"


# ---- セッションスコープの parser fixture -------------------------------------------


@pytest.fixture(scope="session")
def parser_javascript():
    from megavul.parser.parser_javascript import ParserJavaScript

    p = ParserJavaScript(logging.getLogger("test.parser_javascript"))
    try:
        _ = p.language  # cached_property → build_tree_sitter_language を起動
    except RuntimeError as e:
        pytest.skip(f"tree-sitter JavaScript .so が利用不可: {e}")
    return p


# ---- ヘルパー -----------------------------------------------------------------------


def run_parse_file(parser, src_path: Path, tmp_path: Path) -> list[dict]:
    """parse_file() を実行して出力 JSON を dict のリストとして返す。"""
    out = tmp_path / (src_path.name + ".json")
    parser.parse_file(src_path, out)
    assert out.exists(), "parse_file() が JSON を出力しなかった"
    with out.open() as f:
        return json.load(f)


def func_by_name(funcs: list[dict], name: str) -> dict:
    matches = [f for f in funcs if f["func_name"] == name]
    assert matches, (
        f"関数 '{name}' が抽出結果に存在しない (found: {[f['func_name'] for f in funcs]})"
    )
    return matches[0]


# ---- sample.js テスト ---------------------------------------------------------------


class TestParserJavaScriptSample:
    def test_extracts_expected_function_count(self, parser_javascript, tmp_path):
        """sample.js から8つの関数が抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        assert len(funcs) == 8

    def test_function_declaration_single_param(self, parser_javascript, tmp_path):
        """function_declaration: greet(name) が抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "greet")
        assert len(f["parameter_list"]) == 1
        assert f["parameter_list"][0][1] == "name"
        assert f["return_type"] == ""  # JS は動的型付け

    def test_function_declaration_two_params(self, parser_javascript, tmp_path):
        """function_declaration: add(a, b) が抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "add")
        assert len(f["parameter_list"]) == 2
        names = [p[1] for p in f["parameter_list"]]
        assert "a" in names
        assert "b" in names

    def test_function_expression(self, parser_javascript, tmp_path):
        """function_expression: const multiply = function(x, y) が抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "multiply")
        assert len(f["parameter_list"]) == 2
        names = [p[1] for p in f["parameter_list"]]
        assert "x" in names
        assert "y" in names

    def test_arrow_function(self, parser_javascript, tmp_path):
        """arrow_function: const square = (n) => {...} が抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "square")
        assert len(f["parameter_list"]) == 1
        assert f["parameter_list"][0][1] == "n"

    def test_class_constructor(self, parser_javascript, tmp_path):
        """method_definition: Counter.constructor が抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "Counter.constructor")
        assert len(f["parameter_list"]) == 1
        assert f["parameter_list"][0][1] == "start"

    def test_class_method_with_param(self, parser_javascript, tmp_path):
        """method_definition: Counter.increment(step) が抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "Counter.increment")
        assert len(f["parameter_list"]) == 1
        assert f["parameter_list"][0][1] == "step"

    def test_class_method_no_param(self, parser_javascript, tmp_path):
        """method_definition: Counter.reset() が引数なしで抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "Counter.reset")
        assert f["parameter_list"] == []

    def test_rest_parameter(self, parser_javascript, tmp_path):
        """function_declaration: merge(target, ...sources) の rest param が抽出される。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "merge")
        assert len(f["parameter_list"]) == 2
        names = [p[1] for p in f["parameter_list"]]
        assert "target" in names
        # rest parameter は "...sources" として格納される
        assert any(n.startswith("...") for n in names)

    def test_func_body_contains_source(self, parser_javascript, tmp_path):
        """抽出された func フィールドに実際のソースコードが含まれる。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "greet")
        assert "Hello" in f["func"]
        assert "greet" in f["func"]

    def test_func_body_nonempty_for_all(self, parser_javascript, tmp_path):
        """全関数の func フィールドが空でない。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        for f in funcs:
            assert f["func"].strip(), (
                f"func_name={f['func_name']} の func フィールドが空"
            )

    def test_parameter_list_structure(self, parser_javascript, tmp_path):
        """parameter_list の各エントリが (type, name, int) の3要素になっている。"""
        funcs = run_parse_file(parser_javascript, SAMPLE_JS, tmp_path)
        f = func_by_name(funcs, "add")
        for p in f["parameter_list"]:
            assert len(p) == 3
            assert isinstance(p[0], str)  # type (JS は常に空文字列)
            assert isinstance(p[1], str)  # name
            assert isinstance(p[2], int)  # insert_idx
