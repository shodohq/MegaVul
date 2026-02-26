import json
import time
import math
import shutil
from collections import deque

from tqdm import tqdm
from dataclasses import dataclass

from megavul.pipeline.json_save_location import all_cve_from_nvd_json_path
from megavul.util.utils import  safe_read_json_from_network , read_json_from_local , save_data_as_json
from megavul.util.logging_util import global_logger
from megavul.util.storage import StorageLocation

# docs says: "It is recommended to use the default resultsPerPage value as this value has been optimized for the API response."
# default value is 2000: https://nvd.nist.gov/developers/vulnerabilities
RESULT_PER_PAGE = 2000
NVD_RATE_LIMIT_WINDOW_SEC = 30.0
NVD_RATE_LIMIT_MAX_REQUESTS = 5
def compose_nvd_page_url(page_index: int, results_per_page: int = RESULT_PER_PAGE):
    return f'https://services.nvd.nist.gov/rest/json/cves/2.0/?resultsPerPage={results_per_page}&startIndex={page_index * results_per_page}'

@dataclass
class NvdMetaData:
    totalResults : int
    version : str

def get_nvd_metadata() -> NvdMetaData:
    """
        get the number of total results in the NVD database, and version number
    """
    first_page_url = compose_nvd_page_url(page_index= 0 , results_per_page=1)
    data = safe_read_json_from_network(first_page_url)
    # ['resultsPerPage', 'startIndex', 'totalResults', 'format', 'version', 'timestamp', 'vulnerabilities']
    metadata = NvdMetaData(data['totalResults'] , data['version'])
    return metadata


def crawl_nvd(use_cache:bool = True):
    nvd_metadata: NvdMetaData = get_nvd_metadata()
    result_save_path = all_cve_from_nvd_json_path
    cache_page_dir = StorageLocation.create_cache_dir('nvd_page_cache')

    total_page_cnt = math.ceil(nvd_metadata.totalResults / RESULT_PER_PAGE)
    global_logger.info(f'Begin crawl CVE entries from NVD database, total entries:{nvd_metadata.totalResults}, total pages:{total_page_cnt}')
    all_cve_entries = []

    if result_save_path.exists():
        old_result_entries_cnt = len(json.load(result_save_path.open(mode='r')))
        if old_result_entries_cnt == nvd_metadata.totalResults and use_cache:
            global_logger.info(
                f'{result_save_path} exists, all CVE entries({nvd_metadata.totalResults}) from NVD databases has been downloaded before!')
            return
        elif old_result_entries_cnt != nvd_metadata.totalResults:
            global_logger.info(f'Out-of-date data, old:{old_result_entries_cnt} now:{nvd_metadata.totalResults}, try to download the latest NVD database')
            # remove old cache
            shutil.rmtree(cache_page_dir)
            cache_page_dir.mkdir(exist_ok=True)
        else:
            global_logger.info(f'Try to download the latest NVD database, ignoring the cache')

    # rolling windowで制限されているRate limitをできるだけ有効に活用するためにQUEUEで管理する
    request_timestamps = deque()
    # NVD crawl中にtotalResultsが増えることがあるため、startIndexを基準に進める。
    current_total_results = nvd_metadata.totalResults
    downloaded_largest_idx = -1

    with tqdm(total=current_total_results, desc='Downloading CVE entries from NVD') as pbar:
        while downloaded_largest_idx + 1 < current_total_results:
            start_index = downloaded_largest_idx + 1
            page = start_index // RESULT_PER_PAGE
            cache_page_path = cache_page_dir / f'{RESULT_PER_PAGE}_{page}.json'

            if cache_page_path.exists() and use_cache:
                global_logger.debug(f'{page} page using cache from {cache_page_path}')
                cve_entries = read_json_from_local(cache_page_path)
            else:
                page_url = compose_nvd_page_url(page, RESULT_PER_PAGE)
                data: dict
                cve_entries: list
                while True:
                    # NVD API: rolling window 30 sec / 5 requests.
                    while True:
                        now = time.monotonic()
                        while request_timestamps and (now - request_timestamps[0]) >= NVD_RATE_LIMIT_WINDOW_SEC:
                            request_timestamps.popleft()
                        if len(request_timestamps) < NVD_RATE_LIMIT_MAX_REQUESTS:
                            request_timestamps.append(now)
                            break
                        wait_sec = NVD_RATE_LIMIT_WINDOW_SEC - (now - request_timestamps[0]) + 0.01
                        if wait_sec > 0:
                            time.sleep(wait_sec)

                    data = safe_read_json_from_network(page_url, 7)

                    assert data.get('resultsPerPage') == RESULT_PER_PAGE, f"Unexpected resultsPerPage in response: expected {RESULT_PER_PAGE}, got {data.get('resultsPerPage')}"

                    response_start_index = data.get('startIndex', start_index)
                    cve_entries = [item['cve'] for item in data['vulnerabilities']]
                    if response_start_index != start_index:
                        global_logger.warning(
                            f'Unexpected startIndex. expected:{start_index} got:{response_start_index}, trying again...'
                        )
                        continue
                    if not cve_entries and start_index < data.get('totalResults', current_total_results):
                        global_logger.warning(
                            f'Empty page at startIndex:{start_index} but totalResults indicates more data, trying again...'
                        )
                        continue
                    break

                save_data_as_json(cve_entries, cache_page_path)
                latest_total_results = data.get('totalResults', current_total_results)
                if latest_total_results != current_total_results:
                    global_logger.info(
                        f'NVD totalResults changed during crawl: {current_total_results} -> {latest_total_results}'
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

    global_logger.info(f'Download NVD database complete! total entries:{len(all_cve_entries)}')
    save_data_as_json(all_cve_entries,result_save_path, overwrite= True)

if __name__ == '__main__':
    crawl_nvd()
