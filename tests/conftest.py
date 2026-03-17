"""
conftest.py — モジュールレベルの依存チェックを回避してから megavul をインポートする。

- megavul/util/utils.py はインポート時に shutil.which で scala 等のバイナリを確認する。
- megavul/util/config.py はインポート時に github_token.txt の存在を確認する。

テスト環境ではこれらが存在しないため、conftest で事前にモックしてキャッシュさせる。
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

# ダミーの github_token.txt を一時ファイルとして作成（6トークン必要）
_tmp_dir = tempfile.mkdtemp()
_tmp_token_path = Path(_tmp_dir) / "github_token.txt"
_tmp_token_path.write_text("\n".join(f"ghp_faketoken{i:04d}" for i in range(6)) + "\n")

with (
    patch("shutil.which", return_value="/usr/bin/stub"),
    patch(
        "megavul.util.storage.StorageLocation.github_token_path",
        return_value=_tmp_token_path,
    ),
):
    import megavul.util.utils  # noqa: F401  — side effects cached in sys.modules
    import megavul.git_platform.gitlab_pf  # noqa: F401
