"""
download_cve_from_nvd.py のユニットテスト

差分更新（_delta_update）のマージロジックと
クロールメタデータの保存・読み込みをテストする。
"""

import json
from dataclasses import asdict
from unittest.mock import patch

from megavul.pipeline.download_cve_from_nvd import (
    NvdCrawlMetadata,
    _load_crawl_metadata,
    _save_crawl_metadata,
    _now_iso8601,
    compose_nvd_delta_url,
    _delta_update,
    crawl_nvd,
)


# ---------- _now_iso8601 ----------


def test_now_iso8601_format():
    ts = _now_iso8601()
    # "2024-01-02T03:04:05.000+00:00" 形式であること
    assert len(ts) == 29
    assert ts.endswith("+00:00")
    assert "T" in ts


# ---------- compose_nvd_delta_url ----------


def test_compose_nvd_delta_url_contains_params():
    url = compose_nvd_delta_url(
        "2024-01-01T00:00:00.000+00:00",
        "2024-12-31T23:59:59.000+00:00",
        start_index=0,
    )
    assert "lastModStartDate=2024-01-01T00%3A00%3A00.000%2B00%3A00" in url
    assert "lastModEndDate=2024-12-31T23%3A59%3A59.000%2B00%3A00" in url
    assert "startIndex=0" in url
    assert "resultsPerPage=2000" in url


def test_compose_nvd_delta_url_start_index():
    url = compose_nvd_delta_url("s", "e", start_index=4000)
    assert "startIndex=4000" in url


# ---------- NvdCrawlMetadata 保存・読み込み ----------


def test_save_and_load_crawl_metadata(tmp_path):
    meta_path = tmp_path / "nvd_crawl_metadata.json"
    metadata = NvdCrawlMetadata(
        last_crawl_end_time="2024-06-01T12:00:00.000+00:00",
        total_entries=250000,
    )

    with patch(
        "megavul.pipeline.download_cve_from_nvd.nvd_crawl_metadata_json_path",
        meta_path,
    ):
        _save_crawl_metadata(metadata)
        assert meta_path.exists()

        loaded = _load_crawl_metadata()

    assert loaded is not None
    assert loaded.last_crawl_end_time == "2024-06-01T12:00:00.000+00:00"
    assert loaded.total_entries == 250000


def test_load_crawl_metadata_returns_none_when_missing(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"
    with patch(
        "megavul.pipeline.download_cve_from_nvd.nvd_crawl_metadata_json_path",
        missing_path,
    ):
        result = _load_crawl_metadata()
    assert result is None


# ---------- _delta_update マージロジック ----------


def _make_cve(cve_id: str, description: str = "desc") -> dict:
    return {"id": cve_id, "descriptions": [{"lang": "en", "value": description}]}


def _make_nvd_response(entries: list[dict], start_index: int = 0) -> dict:
    return {
        "resultsPerPage": len(entries),
        "startIndex": start_index,
        "totalResults": len(entries),
        "vulnerabilities": [{"cve": e} for e in entries],
    }


def test_delta_update_updates_existing_and_adds_new(tmp_path):
    existing = [
        _make_cve("CVE-2024-0001", "old desc"),
        _make_cve("CVE-2024-0002", "unchanged"),
    ]
    existing_path = tmp_path / "all_cve_from_nvd.json"
    existing_path.write_text(json.dumps(existing))

    meta_path = tmp_path / "nvd_crawl_metadata.json"
    metadata = NvdCrawlMetadata(
        last_crawl_end_time="2024-01-01T00:00:00.000+00:00",
        total_entries=2,
    )
    meta_path.write_text(json.dumps(asdict(metadata)))

    # delta: CVE-0001 が更新され、CVE-0003 が新規追加される
    delta_entries = [
        _make_cve("CVE-2024-0001", "new desc"),
        _make_cve("CVE-2024-0003", "new entry"),
    ]
    probe_response = {
        "resultsPerPage": 1,
        "startIndex": 0,
        "totalResults": 2,
        "vulnerabilities": [],
    }
    delta_response = _make_nvd_response(delta_entries, start_index=0)

    call_responses = [probe_response, delta_response]

    with (
        patch(
            "megavul.pipeline.download_cve_from_nvd.all_cve_from_nvd_json_path",
            existing_path,
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.nvd_crawl_metadata_json_path",
            meta_path,
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.safe_read_json_from_network",
            side_effect=call_responses,
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd._now_iso8601",
            return_value="2024-06-01T00:00:00.000+00:00",
        ),
    ):
        _delta_update()

    result = json.loads(existing_path.read_text())
    result_map = {e["id"]: e for e in result}

    assert len(result) == 3
    assert result_map["CVE-2024-0001"]["descriptions"][0]["value"] == "new desc"
    assert result_map["CVE-2024-0002"]["descriptions"][0]["value"] == "unchanged"
    assert "CVE-2024-0003" in result_map

    # メタデータが更新されていること
    saved_meta = json.loads(meta_path.read_text())
    assert saved_meta["last_crawl_end_time"] == "2024-06-01T00:00:00.000+00:00"
    assert saved_meta["total_entries"] == 3


def test_delta_update_skips_when_no_changes(tmp_path):
    existing = [_make_cve("CVE-2024-0001")]
    existing_path = tmp_path / "all_cve_from_nvd.json"
    existing_path.write_text(json.dumps(existing))

    meta_path = tmp_path / "nvd_crawl_metadata.json"
    metadata = NvdCrawlMetadata(
        last_crawl_end_time="2024-01-01T00:00:00.000+00:00",
        total_entries=1,
    )
    meta_path.write_text(json.dumps(asdict(metadata)))

    probe_response = {
        "resultsPerPage": 0,
        "startIndex": 0,
        "totalResults": 0,
        "vulnerabilities": [],
    }

    with (
        patch(
            "megavul.pipeline.download_cve_from_nvd.all_cve_from_nvd_json_path",
            existing_path,
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.nvd_crawl_metadata_json_path",
            meta_path,
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.safe_read_json_from_network",
            return_value=probe_response,
        ) as mock_net,
    ):
        _delta_update()

    # プローブリクエスト1回だけ送られ、データは変更されていないこと
    assert mock_net.call_count == 1
    result = json.loads(existing_path.read_text())
    assert len(result) == 1  # 変更なし


# ---------- crawl_nvd ルーティング ----------


def test_crawl_nvd_uses_delta_when_both_files_exist(tmp_path):
    existing_path = tmp_path / "all_cve_from_nvd.json"
    existing_path.write_text("[]")
    meta_path = tmp_path / "nvd_crawl_metadata.json"
    meta_path.write_text("{}")

    with (
        patch(
            "megavul.pipeline.download_cve_from_nvd.all_cve_from_nvd_json_path",
            existing_path,
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.nvd_crawl_metadata_json_path",
            meta_path,
        ),
        patch("megavul.pipeline.download_cve_from_nvd._delta_update") as mock_delta,
        patch("megavul.pipeline.download_cve_from_nvd.get_nvd_metadata") as mock_meta,
    ):
        crawl_nvd(use_cache=True)

    mock_delta.assert_called_once()
    mock_meta.assert_not_called()


def test_crawl_nvd_does_full_crawl_when_no_metadata(tmp_path):
    existing_path = tmp_path / "all_cve_from_nvd.json"
    meta_path = tmp_path / "nvd_crawl_metadata.json"
    # neither file exists

    from megavul.pipeline.download_cve_from_nvd import NvdMetaData

    with (
        patch(
            "megavul.pipeline.download_cve_from_nvd.all_cve_from_nvd_json_path",
            existing_path,
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.nvd_crawl_metadata_json_path",
            meta_path,
        ),
        patch("megavul.pipeline.download_cve_from_nvd._delta_update") as mock_delta,
        patch(
            "megavul.pipeline.download_cve_from_nvd.get_nvd_metadata",
            return_value=NvdMetaData(totalResults=0, version="2.0"),
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.StorageLocation.create_cache_dir",
            return_value=tmp_path / "cache",
        ),
        patch("megavul.pipeline.download_cve_from_nvd.save_data_as_json"),
        patch("megavul.pipeline.download_cve_from_nvd._save_crawl_metadata"),
    ):
        (tmp_path / "cache").mkdir()
        crawl_nvd(use_cache=True)

    mock_delta.assert_not_called()


def test_crawl_nvd_forces_full_crawl_with_use_cache_false(tmp_path):
    existing_path = tmp_path / "all_cve_from_nvd.json"
    existing_path.write_text("[]")
    meta_path = tmp_path / "nvd_crawl_metadata.json"
    meta_path.write_text("{}")

    from megavul.pipeline.download_cve_from_nvd import NvdMetaData

    with (
        patch(
            "megavul.pipeline.download_cve_from_nvd.all_cve_from_nvd_json_path",
            existing_path,
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.nvd_crawl_metadata_json_path",
            meta_path,
        ),
        patch("megavul.pipeline.download_cve_from_nvd._delta_update") as mock_delta,
        patch(
            "megavul.pipeline.download_cve_from_nvd.get_nvd_metadata",
            return_value=NvdMetaData(totalResults=0, version="2.0"),
        ),
        patch(
            "megavul.pipeline.download_cve_from_nvd.StorageLocation.create_cache_dir",
            return_value=tmp_path / "cache",
        ),
        patch("megavul.pipeline.download_cve_from_nvd.save_data_as_json"),
        patch("megavul.pipeline.download_cve_from_nvd._save_crawl_metadata"),
    ):
        (tmp_path / "cache").mkdir()
        crawl_nvd(use_cache=False)

    mock_delta.assert_not_called()
