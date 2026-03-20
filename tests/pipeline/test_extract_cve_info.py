"""
extract_cve_info.mining_commit_urls_from_reference_urls のインテグレーションテスト

git.kernel.org URL の処理ロジックをテストする。
@pytest.mark.network が付いたテストは実際にHTTP通信を行う。
それ以外は "commit" を含む長形式URLを渡し、リダイレクトを発生させずに
フィルタリングロジックのみを検証する。
"""

import logging

import pytest

from megavul.pipeline.extract_cve_info import mining_commit_urls_from_reference_urls

_logger = logging.getLogger("test")

HASH_A = "4ab26bce3969f8fd925fe6f6f551e4d1a508c68b"
HASH_B = "9ef41ebf787fcbde99ac404ae473f8467641f983"


def _run(urls):
    return mining_commit_urls_from_reference_urls(_logger, urls)


# ---------------------------------------------------------------------------
# git.kernel.org/stable/c/<hash> — 実HTTP通信
# ---------------------------------------------------------------------------


@pytest.mark.network
class TestKernelOrgStableCIntegration:
    """https://git.kernel.org/stable/c/<hash> 形式のインテグレーションテスト。
    実際にリダイレクトを追い、パイプラインが正しい URL を返すことを確認する。
    """

    # TODO: テスト落ちるので治す. 原因はわかっている: https://www.notion.so/shodohq/MegaVul-30bae1b4a59280889cc4d5ba7de31df3?source=copy_link#329ae1b4a592802a8f0ed61cc04661a6
    def test_stable_c_hash_a_is_recognized(self):
        url = f"https://git.kernel.org/stable/c/{HASH_A}"
        result = _run([url])
        assert len(result) == 1
        assert HASH_A in result[0]

    # TODO: テスト落ちるので治す. 原因はわかっている: https://www.notion.so/shodohq/MegaVul-30bae1b4a59280889cc4d5ba7de31df3?source=copy_link#329ae1b4a592802a8f0ed61cc04661a6
    def test_stable_c_hash_b_is_recognized(self):
        url = f"https://git.kernel.org/stable/c/{HASH_B}"
        result = _run([url])
        assert len(result) == 1
        assert HASH_B in result[0]

    # TODO: テスト落ちるので治す. 原因はわかっている: https://www.notion.so/shodohq/MegaVul-30bae1b4a59280889cc4d5ba7de31df3?source=copy_link#329ae1b4a592802a8f0ed61cc04661a6
    def test_stable_c_two_urls_both_recognized(self):
        url_a = f"https://git.kernel.org/stable/c/{HASH_A}"
        url_b = f"https://git.kernel.org/stable/c/{HASH_B}"
        result = _run([url_a, url_b])
        assert len(result) == 2
        assert any(HASH_A in u for u in result)
        assert any(HASH_B in u for u in result)

    # TODO: テスト落ちるので治す. 原因はわかっている: https://www.notion.so/shodohq/MegaVul-30bae1b4a59280889cc4d5ba7de31df3?source=copy_link#329ae1b4a592802a8f0ed61cc04661a6
    def test_result_url_contains_h_param(self):
        """`?id=` が `?h=` に変換されて返ること"""
        url = f"https://git.kernel.org/stable/c/{HASH_A}"
        result = _run([url])
        assert len(result) == 1
        assert "h=" in result[0]

    # TODO: テスト落ちるので治す. 原因はわかっている: https://www.notion.so/shodohq/MegaVul-30bae1b4a59280889cc4d5ba7de31df3?source=copy_link#329ae1b4a592802a8f0ed61cc04661a6
    def test_linus_short_url_is_recognized(self):
        """旧形式 /linus/<hash> もリダイレクト後に認識される"""
        hash_val = "c19483cc5e56ac5e22dd19cf25ba210ab1537773"
        url = f"https://git.kernel.org/linus/{hash_val}"
        result = _run([url])
        assert len(result) == 1
        assert hash_val in result[0]


# ---------------------------------------------------------------------------
# git.kernel.org — フィルタリングロジック ("commit" 含む長形式URL、リダイレクトなし)
# ---------------------------------------------------------------------------


class TestKernelOrgUrlFilters:
    """`commit` を含む長形式URLを使い、リダイレクトなしでフィルタロジックを検証する。"""

    def test_commit_url_with_h_param_is_passed_through(self):
        url = (
            "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
            "/commit/?h=abc1234"
        )
        result = _run([url])
        assert len(result) == 1
        assert "h=abc1234" in result[0]

    def test_id_param_replaced_with_h(self):
        """`?id=` が `?h=` に正規化される"""
        url = (
            "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
            "/commit/?id=abc1234"
        )
        result = _run([url])
        assert len(result) == 1
        assert "h=abc1234" in result[0]
        assert "id=" not in result[0]

    def test_commitdiff_plain_normalized(self):
        """`a=commitdiff_plain` が `a=commitdiff` に正規化される"""
        url = (
            "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
            "/commit/?a=commitdiff_plain;h=abc1234"
        )
        result = _run([url])
        assert len(result) == 1
        assert "commitdiff_plain" not in result[0]
        assert "commitdiff" in result[0]

    def test_versioned_repo_name_is_stripped(self):
        """`linux-2.6.git` が `linux.git` に正規化される"""
        url = (
            "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux-2.6.git"
            f"/commit/?h={HASH_A}"
        )
        result = _run([url])
        assert len(result) == 1
        assert "linux-2.6.git" not in result[0]
        assert "linux.git" in result[0]

    def test_diff_in_path_is_skipped(self):
        url = (
            "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
            "/commit/diff/?h=abc1234"
        )
        result = _run([url])
        assert result == []

    def test_tree_in_path_is_skipped(self):
        url = (
            "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
            "/commit/tree/drivers/net/?h=abc1234"
        )
        result = _run([url])
        assert result == []

    def test_patch_in_path_is_skipped(self):
        url = (
            "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
            "/commit/patch/?h=abc1234"
        )
        result = _run([url])
        assert result == []

    def test_url_without_hash_is_skipped(self):
        url = (
            "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/"
        )
        result = _run([url])
        assert result == []
