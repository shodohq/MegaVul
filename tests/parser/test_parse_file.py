"""
tests/parser/test_parse_file.py

ParserC / ParserCpp の parse_file() を実際のキャッシュファイルで動作確認する。

tree-sitter の .so が未ビルドかつ CLI が使えない環境ではテストをスキップする。
"""

import json
import logging
import pytest

from pathlib import Path

# ---- テスト用フィクスチャファイルパス -------------------------------------------

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "parser"

# mbed-ce/mbed-os の hci_tr.c（284行、関数3つ）
HCI_TR_C = FIXTURES_DIR / "hci_tr.c"

# hongliuliao/ehttp の epoll_socket.cpp（592行）
EPOLL_SOCKET_CPP = FIXTURES_DIR / "epoll_socket.cpp"


# ---- セッションスコープの parser fixture ----------------------------------------


@pytest.fixture(scope="session")
def parser_c():
    from megavul.parser.parser_c import ParserC

    p = ParserC(logging.getLogger("test.parser_c"))
    try:
        _ = p.language  # cached_property → build_tree_sitter_language を起動
    except RuntimeError as e:
        pytest.skip(f"tree-sitter C .so が利用不可: {e}")
    return p


@pytest.fixture(scope="session")
def parser_cpp():
    from megavul.parser.parser_cpp import ParserCpp

    p = ParserCpp(logging.getLogger("test.parser_cpp"))
    try:
        _ = p.language
    except RuntimeError as e:
        pytest.skip(f"tree-sitter C++ .so が利用不可: {e}")
    return p


# ---- ヘルパー -------------------------------------------------------------------


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


# ---- ParserC テスト (hci_tr.c) --------------------------------------------------


class TestParserC:
    def test_extracts_expected_function_count(self, parser_c, tmp_path):
        """hci_tr.c から 3 つの関数が抽出される。"""
        funcs = run_parse_file(parser_c, HCI_TR_C, tmp_path)
        assert len(funcs) == 3

    def test_extracts_hciTrSendAclData(self, parser_c, tmp_path):
        funcs = run_parse_file(parser_c, HCI_TR_C, tmp_path)
        f = func_by_name(funcs, "hciTrSendAclData")
        assert f["return_type"] == "void"
        # スペース正規化済みのシグネチャで比較
        sig = f["parameter_list_signature"].replace(" ", "")
        assert sig == "(void*pContext,uint8_t*pData)"

    def test_extracts_hciTrSendCmd(self, parser_c, tmp_path):
        funcs = run_parse_file(parser_c, HCI_TR_C, tmp_path)
        f = func_by_name(funcs, "hciTrSendCmd")
        assert f["return_type"] == "void"
        sig = f["parameter_list_signature"].replace(" ", "")
        assert sig == "(uint8_t*pCmdData)"

    def test_extracts_hciTrSerialRxIncoming(self, parser_c, tmp_path):
        funcs = run_parse_file(parser_c, HCI_TR_C, tmp_path)
        f = func_by_name(funcs, "hciTrSerialRxIncoming")
        assert f["return_type"] == "void"
        sig = f["parameter_list_signature"].replace(" ", "")
        assert sig == "(uint8_t*pBuf,uint8_tlen)"

    def test_func_body_contains_source(self, parser_c, tmp_path):
        """抽出された func フィールドに実際のソースコードが含まれる。"""
        funcs = run_parse_file(parser_c, HCI_TR_C, tmp_path)
        f = func_by_name(funcs, "hciTrSendAclData")
        assert "hci_mbed_os_drv_write" in f["func"]
        assert "hciTrSendAclData" in f["func"]

    def test_parameter_list_structure(self, parser_c, tmp_path):
        """parameter_list が (type, name, insert_idx) のリストになっている。"""
        funcs = run_parse_file(parser_c, HCI_TR_C, tmp_path)
        f = func_by_name(funcs, "hciTrSerialRxIncoming")
        params = f["parameter_list"]
        assert len(params) == 2
        # 各エントリは [type_str, name_str, int] の3要素
        for p in params:
            assert len(p) == 3
        names = [p[1] for p in params]
        assert "pBuf" in names
        assert "len" in names

    def test_idempotent_on_second_call(self, parser_c, tmp_path):
        """出力ファイルが既存の場合、parse_file() はスキップして同じ結果を返す。"""
        out = tmp_path / "hci_tr.c.json"
        parser_c.parse_file(HCI_TR_C, out)
        mtime1 = out.stat().st_mtime
        parser_c.parse_file(HCI_TR_C, out)
        mtime2 = out.stat().st_mtime
        assert mtime1 == mtime2, "キャッシュが効いておらずファイルが再作成された"


# ---- ParserCpp テスト (epoll_socket.cpp) ----------------------------------------


class TestParserCpp:
    def test_extracts_functions(self, parser_cpp, tmp_path):
        """epoll_socket.cpp から複数の関数/コンストラクタが抽出される。"""
        funcs = run_parse_file(parser_cpp, EPOLL_SOCKET_CPP, tmp_path)
        assert len(funcs) >= 5

    def test_extracts_constructor(self, parser_cpp, tmp_path):
        """クラスコンストラクタが抽出される。"""
        funcs = run_parse_file(parser_cpp, EPOLL_SOCKET_CPP, tmp_path)
        names = [f["func_name"] for f in funcs]
        assert "EpollSocket::EpollSocket" in names

    def test_extracts_destructor(self, parser_cpp, tmp_path):
        """デストラクタが抽出される。"""
        funcs = run_parse_file(parser_cpp, EPOLL_SOCKET_CPP, tmp_path)
        names = [f["func_name"] for f in funcs]
        assert "EpollSocket::~EpollSocket" in names

    def test_extracts_qualified_method(self, parser_cpp, tmp_path):
        """ClassName::method 形式の修飾名メソッドが抽出される。"""
        funcs = run_parse_file(parser_cpp, EPOLL_SOCKET_CPP, tmp_path)
        names = [f["func_name"] for f in funcs]
        assert "EpollSocket::get_epfd" in names

    def test_extracts_global_function(self, parser_cpp, tmp_path):
        """名前空間なしのグローバル関数 write_func が抽出される。"""
        funcs = run_parse_file(parser_cpp, EPOLL_SOCKET_CPP, tmp_path)
        f = func_by_name(funcs, "write_func")
        assert f["return_type"] == "void"

    def test_func_body_nonempty(self, parser_cpp, tmp_path):
        """抽出された func フィールドが空でない。"""
        funcs = run_parse_file(parser_cpp, EPOLL_SOCKET_CPP, tmp_path)
        for f in funcs:
            assert f["func"].strip(), (
                f"func_name={f['func_name']} の func フィールドが空"
            )
