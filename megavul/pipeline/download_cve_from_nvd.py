import time
import math
import shutil
from collections import deque
from datetime import datetime, timezone

from tqdm import tqdm
from dataclasses import dataclass, asdict

from megavul.pipeline.json_save_location import (
    all_cve_from_nvd_json_path,
    nvd_crawl_metadata_json_path,
)
from megavul.util.utils import (
    safe_read_json_from_network,
    read_json_from_local,
    save_data_as_json,
)
from megavul.util.logging_util import global_logger
from megavul.util.storage import StorageLocation

# docs says: "It is recommended to use the default resultsPerPage value as this value has been optimized for the API response."
# default value is 2000: https://nvd.nist.gov/developers/vulnerabilities
RESULT_PER_PAGE = 2000
NVD_RATE_LIMIT_WINDOW_SEC = 30.0
NVD_RATE_LIMIT_MAX_REQUESTS = 5


def compose_nvd_page_url(page_index: int, results_per_page: int = RESULT_PER_PAGE):
    return f"https://services.nvd.nist.gov/rest/json/cves/2.0/?resultsPerPage={results_per_page}&startIndex={page_index * results_per_page}"


def compose_nvd_delta_url(
    last_mod_start: str,
    last_mod_end: str,
    start_index: int,
    results_per_page: int = RESULT_PER_PAGE,
) -> str:
    return (
        f"https://services.nvd.nist.gov/rest/json/cves/2.0/"
        f"?lastModStartDate={last_mod_start}&lastModEndDate={last_mod_end}"
        f"&resultsPerPage={results_per_page}&startIndex={start_index}"
    )


@dataclass
class NvdMetaData:
    totalResults: int
    version: str


@dataclass
class NvdCrawlMetadata:
    last_crawl_end_time: str  # ISO 8601、例: "2024-01-01T00:00:00.000+00:00"
    total_entries: int


def _load_crawl_metadata() -> NvdCrawlMetadata | None:
    if not nvd_crawl_metadata_json_path.exists():
        return None
    data = read_json_from_local(nvd_crawl_metadata_json_path)
    assert isinstance(data, dict)
    return NvdCrawlMetadata(
        last_crawl_end_time=data["last_crawl_end_time"],
        total_entries=data["total_entries"],
    )


def _save_crawl_metadata(metadata: NvdCrawlMetadata):
    save_data_as_json(asdict(metadata), nvd_crawl_metadata_json_path, overwrite=True)


def _now_iso8601() -> str:
    """現在時刻をNVD APIが受け付けるISO 8601形式で返す"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")


def get_nvd_metadata() -> NvdMetaData:
    """
    get the number of total results in the NVD database, and version number
    """
    first_page_url = compose_nvd_page_url(page_index=0, results_per_page=1)
    data = safe_read_json_from_network(first_page_url)
    # ['resultsPerPage', 'startIndex', 'totalResults', 'format', 'version', 'timestamp', 'vulnerabilities']
    metadata = NvdMetaData(data["totalResults"], data["version"])
    return metadata


def _crawl_pages(
    url_fn,
    total_results: int,
    desc: str,
    request_timestamps: deque,
) -> list:
    """
    ページネーションしながらCVEエントリを取得する汎用ヘルパー。

    url_fn(start_index) -> str  でページURLを生成する。
    total_results はプログレスバーの初期値（クロール中に変化しうる）。
    戻り値はCVEエントリのリスト。
    """
    all_cve_entries = []
    current_total_results = total_results
    downloaded_largest_idx = -1

    with tqdm(total=current_total_results, desc=desc) as pbar:
        while downloaded_largest_idx + 1 < current_total_results:
            start_index = downloaded_largest_idx + 1

            while True:
                # NVD API: rolling window 30 sec / 5 requests.
                while True:
                    now = time.monotonic()
                    while (
                        request_timestamps
                        and (now - request_timestamps[0]) >= NVD_RATE_LIMIT_WINDOW_SEC
                    ):
                        request_timestamps.popleft()
                    if len(request_timestamps) < NVD_RATE_LIMIT_MAX_REQUESTS:
                        request_timestamps.append(now)
                        break
                    wait_sec = (
                        NVD_RATE_LIMIT_WINDOW_SEC - (now - request_timestamps[0]) + 0.01
                    )
                    if wait_sec > 0:
                        time.sleep(wait_sec)

                page_url = url_fn(start_index)
                data = safe_read_json_from_network(page_url, 7)

                response_start_index = data.get("startIndex", start_index)
                cve_entries = [item["cve"] for item in data["vulnerabilities"]]

                if response_start_index != start_index:
                    global_logger.warning(
                        f"Unexpected startIndex. expected:{start_index} got:{response_start_index}, trying again..."
                    )
                    continue
                if not cve_entries and start_index < data.get(
                    "totalResults", current_total_results
                ):
                    global_logger.warning(
                        f"Empty page at startIndex:{start_index} but totalResults indicates more data, trying again..."
                    )
                    continue
                break

            latest_total_results = data.get("totalResults", current_total_results)
            if latest_total_results != current_total_results:
                global_logger.info(
                    f"NVD totalResults changed during crawl: {current_total_results} -> {latest_total_results}"
                )
                current_total_results = latest_total_results
                pbar.total = current_total_results
                pbar.refresh()

            all_cve_entries.extend(cve_entries)
            downloaded_largest_idx += len(cve_entries)
            pbar.n = len(all_cve_entries)
            pbar.refresh()

            if not cve_entries:
                break

    return all_cve_entries


def _delta_update():
    """
    前回クロール以降に変更されたCVEだけを取得してローカルデータに反映する。
    """
    crawl_metadata = _load_crawl_metadata()
    assert crawl_metadata is not None

    last_mod_start = crawl_metadata.last_crawl_end_time
    crawl_end_time = _now_iso8601()

    global_logger.info(
        f"Delta update: fetching CVEs modified between {last_mod_start} and {crawl_end_time}"
    )

    # まず件数だけ確認
    probe_url = compose_nvd_delta_url(
        last_mod_start, crawl_end_time, 0, results_per_page=1
    )
    probe_data = safe_read_json_from_network(probe_url)
    delta_total = probe_data.get("totalResults", 0)

    if delta_total == 0:
        global_logger.info("Delta update: no changes since last crawl, skipping.")
        return

    global_logger.info(f"Delta update: {delta_total} CVEs to update/add")

    # 既存データをCVE IDをキーにしたdictとして読み込む
    existing_entries = read_json_from_local(all_cve_from_nvd_json_path)
    assert isinstance(existing_entries, list)
    cve_map: dict[str, dict] = {entry["id"]: entry for entry in existing_entries}

    request_timestamps: deque = deque()

    def delta_url_fn(start_index: int) -> str:
        return compose_nvd_delta_url(last_mod_start, crawl_end_time, start_index)

    delta_entries = _crawl_pages(
        url_fn=delta_url_fn,
        total_results=delta_total,
        desc="Delta update from NVD",
        request_timestamps=request_timestamps,
    )

    updated_count = sum(1 for e in delta_entries if e["id"] in cve_map)
    added_count = len(delta_entries) - updated_count

    for entry in delta_entries:
        cve_map[entry["id"]] = entry

    merged = list(cve_map.values())
    save_data_as_json(merged, all_cve_from_nvd_json_path, overwrite=True)
    _save_crawl_metadata(
        NvdCrawlMetadata(last_crawl_end_time=crawl_end_time, total_entries=len(merged))
    )

    global_logger.info(
        f"Delta update complete: {updated_count} updated, {added_count} added, total {len(merged)} entries"
    )


def crawl_nvd(use_cache: bool = True):
    result_save_path = all_cve_from_nvd_json_path
    cache_page_dir = StorageLocation.create_cache_dir("nvd_page_cache")

    # 差分更新: 既存データとメタデータが両方存在する場合
    if (
        result_save_path.exists()
        and nvd_crawl_metadata_json_path.exists()
        and use_cache
    ):
        global_logger.info(
            "Existing NVD data and crawl metadata found, attempting delta update."
        )
        _delta_update()
        return

    # フルクロール
    nvd_metadata: NvdMetaData = get_nvd_metadata()
    total_page_cnt = math.ceil(nvd_metadata.totalResults / RESULT_PER_PAGE)
    global_logger.info(
        f"Begin full crawl of CVE entries from NVD database, total entries:{nvd_metadata.totalResults}, total pages:{total_page_cnt}"
    )

    # 古いページキャッシュをクリア
    if cache_page_dir.exists():
        shutil.rmtree(cache_page_dir)
    cache_page_dir.mkdir(exist_ok=True)

    # フルクロール開始時刻を記録（完了後にメタデータとして保存する）
    crawl_start_time = _now_iso8601()

    request_timestamps: deque = deque()
    all_cve_entries = []
    current_total_results = nvd_metadata.totalResults
    downloaded_largest_idx = -1

    with tqdm(
        total=current_total_results, desc="Downloading CVE entries from NVD"
    ) as pbar:
        while downloaded_largest_idx + 1 < current_total_results:
            start_index = downloaded_largest_idx + 1
            page = start_index // RESULT_PER_PAGE
            cache_page_path = cache_page_dir / f"{RESULT_PER_PAGE}_{page}.json"

            if cache_page_path.exists() and use_cache:
                global_logger.debug(f"{page} page using cache from {cache_page_path}")
                _cve_entries = read_json_from_local(cache_page_path)
                assert isinstance(_cve_entries, list)
                cve_entries = _cve_entries
            else:
                page_url = compose_nvd_page_url(page, RESULT_PER_PAGE)
                cve_entries: list
                while True:
                    # NVD API: rolling window 30 sec / 5 requests.
                    while True:
                        now = time.monotonic()
                        while (
                            request_timestamps
                            and (now - request_timestamps[0])
                            >= NVD_RATE_LIMIT_WINDOW_SEC
                        ):
                            request_timestamps.popleft()
                        if len(request_timestamps) < NVD_RATE_LIMIT_MAX_REQUESTS:
                            request_timestamps.append(now)
                            break
                        wait_sec = (
                            NVD_RATE_LIMIT_WINDOW_SEC
                            - (now - request_timestamps[0])
                            + 0.01
                        )
                        if wait_sec > 0:
                            time.sleep(wait_sec)

                    data = safe_read_json_from_network(page_url, 7)

                    response_start_index = data.get("startIndex", start_index)
                    cve_entries = [item["cve"] for item in data["vulnerabilities"]]
                    if response_start_index != start_index:
                        global_logger.warning(
                            f"Unexpected startIndex. expected:{start_index} got:{response_start_index}, trying again..."
                        )
                        continue
                    if not cve_entries and start_index < data.get(
                        "totalResults", current_total_results
                    ):
                        global_logger.warning(
                            f"Empty page at startIndex:{start_index} but totalResults indicates more data, trying again..."
                        )
                        continue
                    break

                save_data_as_json(cve_entries, cache_page_path)
                latest_total_results = data.get("totalResults", current_total_results)
                if latest_total_results != current_total_results:
                    global_logger.info(
                        f"NVD totalResults changed during crawl: {current_total_results} -> {latest_total_results}"
                    )
                    current_total_results = latest_total_results
                    pbar.total = current_total_results
                    pbar.refresh()

            all_cve_entries.extend(cve_entries)
            downloaded_largest_idx += len(cve_entries)
            pbar.n = len(all_cve_entries)
            pbar.refresh()

            if not cve_entries:
                break

    global_logger.info(
        f"Download NVD database complete! total entries:{len(all_cve_entries)}"
    )
    save_data_as_json(all_cve_entries, result_save_path, overwrite=True)
    _save_crawl_metadata(
        NvdCrawlMetadata(
            last_crawl_end_time=crawl_start_time,
            total_entries=len(all_cve_entries),
        )
    )


if __name__ == "__main__":
    crawl_nvd()
