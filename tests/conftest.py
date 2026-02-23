"""
conftest.py — モジュールレベルの依存チェックを回避してから megavul をインポートする。
megavul/util/utils.py はインポート時に shutil.which で scala 等のバイナリを確認する。
テスト環境では存在しないため、conftest で事前にモックしてキャッシュさせる。
"""
from unittest.mock import patch

with patch('shutil.which', return_value='/usr/bin/stub'):
    import megavul.util.utils          # noqa: F401  — side effects cached in sys.modules
    import megavul.git_platform.gitlab_pf  # noqa: F401
