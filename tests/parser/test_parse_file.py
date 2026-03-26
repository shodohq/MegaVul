"""
tests/parser/test_parse_file.py

ParserC / ParserCpp / ParserGo / ParserPython の parse_file() を実際のキャッシュファイルで動作確認する。

tree-sitter の .so が未ビルドかつ CLI が使えない環境ではテストをスキップする。
Python は PyPI パッケージを使用するため .so ビルドは不要。
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

# [方法A] 現実的な Python ファイル: セッション管理ユーティリティ（合成フィクスチャ）
# トップレベル関数 6 + クラスメソッド 8（うちデコレータ付き 2）= 14 関数
SESSION_MANAGER_PY = FIXTURES_DIR / "session_manager.py"

# [方法B] パーサーエッジケースを網羅したカスタムフィクスチャ
# トップレベル関数 5（うちデコレータ付き 1・ネスト含む 1）+
# クラスメソッド 5（通常/classmethod/staticmethod/property）= 計 10 関数
PYTHON_PARSER_FIXTURE = FIXTURES_DIR / "python_parser_fixture.py"


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


# ---- ParserPython fixture -------------------------------------------------------


@pytest.fixture(scope="session")
def parser_python():
    from megavul.parser.parser_python import ParserPython

    p = ParserPython(logging.getLogger("test.parser_python"))
    try:
        _ = p.language  # PyPI パッケージ経由なので .so ビルドは不要
    except Exception as e:
        pytest.skip(f"tree-sitter-python が利用不可: {e}")
    return p


# ---- [方法A] ParserPython テスト: 現実的な session_manager.py ------------------


class TestParserPythonSessionManager:
    """方法A: 実際のプロジェクトに近い構成のファイルで動作確認する。"""

    def test_extracts_expected_function_count(self, parser_python, tmp_path):
        """session_manager.py から 14 関数が抽出される。
        トップレベル 6 + クラスメソッド 8（classmethod/staticmethod 含む）。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        assert len(funcs) == 14

    def test_extracts_hash_password(self, parser_python, tmp_path):
        """hash_password の戻り値型と引数が正しく抽出される。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        f = func_by_name(funcs, "hash_password")
        assert "tuple" in f["return_type"]
        names = [p[1] for p in f["parameter_list"]]
        assert "password" in names
        assert "salt" in names

    def test_extracts_decode_token(self, parser_python, tmp_path):
        """decode_token の戻り値型に Optional[dict] が含まれる。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        f = func_by_name(funcs, "decode_token")
        assert "dict" in f["return_type"]
        names = [p[1] for p in f["parameter_list"]]
        assert "token" in names
        assert "secret" in names

    def test_class_method_name_prefix(self, parser_python, tmp_path):
        """クラスメソッドが ClassName.method_name 形式で抽出される。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        names = [f["func_name"] for f in funcs]
        assert "SessionStore.create" in names
        assert "SessionStore.get" in names
        assert "SessionStore.refresh" in names
        assert "SessionStore.revoke" in names

    def test_private_method_extracted(self, parser_python, tmp_path):
        """アンダースコア始まりのプライベートメソッドも抽出される。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        names = [f["func_name"] for f in funcs]
        assert "SessionStore._make_key" in names

    def test_classmethod_decorator(self, parser_python, tmp_path):
        """@classmethod デコレータ付きメソッドが正しく抽出される。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        f = func_by_name(funcs, "SessionStore.from_config")
        # cls が第一引数として含まれる
        names = [p[1] for p in f["parameter_list"]]
        assert "cls" in names
        assert "config" in names

    def test_staticmethod_decorator(self, parser_python, tmp_path):
        """@staticmethod デコレータ付きメソッドが正しく抽出される。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        f = func_by_name(funcs, "SessionStore.is_valid_session_id")
        names = [p[1] for p in f["parameter_list"]]
        assert "session_id" in names

    def test_init_has_no_return_type(self, parser_python, tmp_path):
        """__init__ はアノテーションなしで return_type が空文字列になる。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        f = func_by_name(funcs, "SessionStore.__init__")
        assert f["return_type"] == ""

    def test_func_body_nonempty(self, parser_python, tmp_path):
        """全関数の func フィールドが空でない。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        for f in funcs:
            assert f["func"].strip(), f"func_name={f['func_name']} の func フィールドが空"

    def test_top_level_function_not_prefixed(self, parser_python, tmp_path):
        """トップレベル関数にはクラス名プレフィックスが付かない。"""
        funcs = run_parse_file(parser_python, SESSION_MANAGER_PY, tmp_path)
        top_level_names = [f["func_name"] for f in funcs if "." not in f["func_name"]]
        assert "generate_session_id" in top_level_names
        assert "encode_token" in top_level_names
        assert "_constant_time_compare" in top_level_names


# ---- [方法B] ParserPython テスト: エッジケース網羅フィクスチャ -----------------


class TestParserPythonFixture:
    """方法B: エッジケースを明示的に設計したカスタムフィクスチャで動作確認する。"""

    def test_extracts_expected_function_count(self, parser_python, tmp_path):
        """python_parser_fixture.py から 10 関数が抽出される。
        トップレベル 5 + クラスメソッド 5（ネスト _inner は除外）。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        assert len(funcs) == 10

    def test_plain_function_no_annotations(self, parser_python, tmp_path):
        """アノテーションなし関数 add の return_type が空で params が 2 つ。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "add")
        assert f["return_type"] == ""
        params = f["parameter_list"]
        assert len(params) == 2
        assert all(p[0] == "" for p in params)  # 型なし
        names = [p[1] for p in params]
        assert "a" in names
        assert "b" in names

    def test_typed_function_with_default(self, parser_python, tmp_path):
        """greet の return_type が str を含み、greeting のデフォルト値が無視される。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "greet")
        assert "str" in f["return_type"]
        params = f["parameter_list"]
        assert len(params) == 2
        types = [p[0] for p in params]
        assert "str" in types
        names = [p[1] for p in params]
        assert "name" in names
        assert "greeting" in names

    def test_variadic_params_extracted(self, parser_python, tmp_path):
        """log_event の *args と **kwargs がパラメータリストに含まれる。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "log_event")
        assert "None" in f["return_type"]
        names = [p[1] for p in f["parameter_list"]]
        assert "event" in names
        assert "*args" in names
        assert "**kwargs" in names

    def test_nested_function_excluded(self, parser_python, tmp_path):
        """outer_with_nested 内の _inner は抽出されない。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        names = [f["func_name"] for f in funcs]
        assert "_inner" not in names

    def test_outer_function_extracted(self, parser_python, tmp_path):
        """outer_with_nested 自体は抽出される。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "outer_with_nested")
        assert "int" in f["return_type"]

    def test_decorated_top_level_extracted(self, parser_python, tmp_path):
        """@some_decorator 付きトップレベル関数が抽出される。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "decorated_top_level")
        assert "bool" in f["return_type"]
        names = [p[1] for p in f["parameter_list"]]
        assert "value" in names
        # func フィールドにデコレータ行が含まれる
        assert "@some_decorator" in f["func"]

    def test_class_method_name_format(self, parser_python, tmp_path):
        """クラスメソッドが DataProcessor.xxx 形式で抽出される。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        names = [f["func_name"] for f in funcs]
        assert "DataProcessor.__init__" in names
        assert "DataProcessor.process" in names

    def test_classmethod_decorator(self, parser_python, tmp_path):
        """@classmethod の from_dict が抽出され、cls が第一引数になる。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "DataProcessor.from_dict")
        names = [p[1] for p in f["parameter_list"]]
        assert "cls" in names
        assert "data" in names

    def test_staticmethod_decorator(self, parser_python, tmp_path):
        """@staticmethod の validate が抽出される。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "DataProcessor.validate")
        assert "bool" in f["return_type"]
        names = [p[1] for p in f["parameter_list"]]
        assert "value" in names
        assert "self" not in names  # staticmethod は self を持たない

    def test_property_decorator(self, parser_python, tmp_path):
        """@property の name が抽出される。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "DataProcessor.name")
        assert "str" in f["return_type"]
        names = [p[1] for p in f["parameter_list"]]
        assert "self" in names

    def test_process_variadic_and_keyword_only(self, parser_python, tmp_path):
        """process の *items と keyword-only パラメータ strict が含まれる。"""
        funcs = run_parse_file(parser_python, PYTHON_PARSER_FIXTURE, tmp_path)
        f = func_by_name(funcs, "DataProcessor.process")
        names = [p[1] for p in f["parameter_list"]]
        assert "self" in names
        assert "*items" in names
        assert "strict" in names
