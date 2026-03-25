"""
tests/parser/test_parse_file.py

ParserC / ParserCpp / ParserGo の parse_file() を実際のキャッシュファイルで動作確認する。

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

# yhirose/cpp-httplib の test.cc（10634行）
# 複数行にまたがるパラメータ宣言子を含み、traverse_optional_parameter_declaration で
# TypeError: replace() argument 1 must be str, not list を引き起こす
CPP_HTTPLIB_TEST_CC = FIXTURES_DIR / "cpp_httplib_test.cc"

# heroiclabs/nakama の login_attempt_cache.go（174行）
# メソッド（ポインタレシーバ）・グループパラメータ（a, b string）・複数戻り値を含む
LOGIN_ATTEMPT_CACHE_GO = FIXTURES_DIR / "login_attempt_cache.go"

# heroiclabs/nakama の console_authenticate.go（199行）
# 名前付き複数戻り値・グループパラメータ付きメソッド・単純 error 戻り値を含む
CONSOLE_AUTHENTICATE_GO = FIXTURES_DIR / "console_authenticate.go"


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


# ---- ParserCpp リグレッションテスト (cpp_httplib_test.cc) -----------------------


class TestParserCppRegression:
    def test_parse_cpp_httplib_does_not_crash(self, parser_cpp, tmp_path):
        """yhirose/cpp-httplib の test.cc がクラッシュなく解析できる。"""
        funcs = run_parse_file(parser_cpp, CPP_HTTPLIB_TEST_CC, tmp_path)
        assert len(funcs) > 0


# ---- ParserGo fixture -----------------------------------------------------------


@pytest.fixture(scope="session")
def parser_go():
    from megavul.parser.parser_go import ParserGo

    p = ParserGo(logging.getLogger("test.parser_go"))
    try:
        _ = p.language  # cached_property → build_tree_sitter_language を起動
    except RuntimeError as e:
        pytest.skip(f"tree-sitter Go .so が利用不可: {e}")
    return p


# ---- ParserGo テスト (login_attempt_cache.go) -----------------------------------


class TestParserGoLoginAttemptCache:
    def test_extracts_expected_function_count(self, parser_go, tmp_path):
        """login_attempt_cache.go から 6 つの関数/メソッドが抽出される。
        goroutine 内の匿名関数リテラルはネスト除外される。"""
        funcs = run_parse_file(parser_go, LOGIN_ATTEMPT_CACHE_GO, tmp_path)
        assert len(funcs) == 6

    def test_method_with_pointer_receiver(self, parser_go, tmp_path):
        """(ls *lockoutStatus) trim(...) が (*lockoutStatus).trim として抽出される。"""
        funcs = run_parse_file(parser_go, LOGIN_ATTEMPT_CACHE_GO, tmp_path)
        f = func_by_name(funcs, "(*lockoutStatus).trim")
        assert f["return_type"] == "bool"
        params = f["parameter_list"]
        assert len(params) == 2
        types = [p[0] for p in params]
        assert "time.Time" in types
        assert "time.Duration" in types

    def test_constructor_function(self, parser_go, tmp_path):
        """パッケージレベル関数 NewLocalLoginAttemptCache が抽出される。"""
        funcs = run_parse_file(parser_go, LOGIN_ATTEMPT_CACHE_GO, tmp_path)
        f = func_by_name(funcs, "NewLocalLoginAttemptCache")
        assert f["return_type"] == "LoginAttemptCache"
        assert f["parameter_list"] == []

    def test_grouped_parameter_expansion(self, parser_go, tmp_path):
        """Allow(account, ip string) のグループパラメータが 2 エントリに展開される。"""
        funcs = run_parse_file(parser_go, LOGIN_ATTEMPT_CACHE_GO, tmp_path)
        f = func_by_name(funcs, "(*LocalLoginAttemptCache).Allow")
        assert f["return_type"] == "bool"
        params = f["parameter_list"]
        assert len(params) == 2
        # 両パラメータの型は string、名前は account と ip
        assert all(p[0] == "string" for p in params)
        names = [p[1] for p in params]
        assert "account" in names
        assert "ip" in names

    def test_multiple_return_types(self, parser_go, tmp_path):
        """Add(...) (LockoutType, time.Time) の複数戻り値が括弧付き文字列で返る。"""
        funcs = run_parse_file(parser_go, LOGIN_ATTEMPT_CACHE_GO, tmp_path)
        f = func_by_name(funcs, "(*LocalLoginAttemptCache).Add")
        ret = f["return_type"]
        assert ret.startswith("(") and ret.endswith(")")
        assert "LockoutType" in ret
        assert "time.Time" in ret

    def test_no_return_type_method(self, parser_go, tmp_path):
        """Stop() の戻り値なしメソッドの return_type が空文字列になる。"""
        funcs = run_parse_file(parser_go, LOGIN_ATTEMPT_CACHE_GO, tmp_path)
        f = func_by_name(funcs, "(*LocalLoginAttemptCache).Stop")
        assert f["return_type"] == ""
        assert f["parameter_list"] == []


# ---- ParserGo テスト (console_authenticate.go) ----------------------------------


class TestParserGoConsoleAuthenticate:
    def test_extracts_expected_function_count(self, parser_go, tmp_path):
        """console_authenticate.go から 5 つの関数/メソッドが抽出される。"""
        funcs = run_parse_file(parser_go, CONSOLE_AUTHENTICATE_GO, tmp_path)
        assert len(funcs) == 5

    def test_method_returns_error(self, parser_go, tmp_path):
        """(*ConsoleTokenClaims).Valid() が error を返す。"""
        funcs = run_parse_file(parser_go, CONSOLE_AUTHENTICATE_GO, tmp_path)
        f = func_by_name(funcs, "(*ConsoleTokenClaims).Valid")
        assert f["return_type"] == "error"
        assert f["parameter_list"] == []

    def test_function_with_named_multi_return(self, parser_go, tmp_path):
        """parseConsoleToken の名前付き複数戻り値の型が抽出される。
        名前は無視され (id, username, email string, ...) → (string, ...) となる。"""
        funcs = run_parse_file(parser_go, CONSOLE_AUTHENTICATE_GO, tmp_path)
        f = func_by_name(funcs, "parseConsoleToken")
        ret = f["return_type"]
        assert ret.startswith("(") and ret.endswith(")")
        assert "string" in ret
        assert "bool" in ret
        params = f["parameter_list"]
        assert len(params) == 2
        types = [p[0] for p in params]
        assert "[]byte" in types
        assert "string" in types

    def test_method_with_multiple_return(self, parser_go, tmp_path):
        """(*ConsoleServer).Authenticate が (*console.ConsoleSession, error) を返す。"""
        funcs = run_parse_file(parser_go, CONSOLE_AUTHENTICATE_GO, tmp_path)
        f = func_by_name(funcs, "(*ConsoleServer).Authenticate")
        ret = f["return_type"]
        assert ret.startswith("(") and ret.endswith(")")
        assert "error" in ret
        params = f["parameter_list"]
        assert len(params) == 2
        names = [p[1] for p in params]
        assert "ctx" in names
        assert "in" in names

    def test_grouped_params_in_method(self, parser_go, tmp_path):
        """lookupConsoleUser(ctx, unameOrEmail, password, ip string) の
        グループパラメータが 4 エントリに展開される。"""
        funcs = run_parse_file(parser_go, CONSOLE_AUTHENTICATE_GO, tmp_path)
        f = func_by_name(funcs, "(*ConsoleServer).lookupConsoleUser")
        params = f["parameter_list"]
        # ctx context.Context + unameOrEmail, password, ip string = 4 params
        assert len(params) == 4
        names = [p[1] for p in params]
        assert "ctx" in names
        assert "unameOrEmail" in names
        assert "password" in names
        assert "ip" in names
