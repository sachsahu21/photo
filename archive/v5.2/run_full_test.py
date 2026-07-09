import time, json, traceback
from src.config_manager import ConfigManager
from main import setup_log, task_analyze_folders, task_1, task_1b, task_2, task_3, task_5, task_6, task_7

def run_test_suite():
    config = ConfigManager()
    logger = setup_log(config)
    results = {}
    start = time.time()
    # 11 – folder analysis
    try:
        task_analyze_folders(config, logger)
        results['analyze_folders'] = 'OK'
    except Exception as e:
        results['analyze_folders'] = f'Error: {e}\n{traceback.format_exc()}'
    # 12 – generate/refresh metadata (scan)
    try:
        task_1(config, logger)
        results['metadata_scan'] = 'OK'
    except Exception as e:
        results['metadata_scan'] = f'Error: {e}\n{traceback.format_exc()}'
    # 21 – generate Excel from metadata
    try:
        ep = task_1b(config, logger)
        results['excel_report'] = ep if ep else 'Failed'
    except Exception as e:
        results['excel_report'] = f'Error: {e}\n{traceback.format_exc()}'
    # 31 – organize library (using the generated Excel)
    try:
        if isinstance(results.get('excel_report'), str) and results['excel_report']:
            task_3(results['excel_report'], config, logger)
            results['organize'] = 'OK'
        else:
            results['organize'] = 'Skipped (no Excel)'
    except Exception as e:
        results['organize'] = f'Error: {e}\n{traceback.format_exc()}'
    # 41 – face index build/update
    try:
        task_5(config, logger)
        results['face_index'] = 'OK'
    except Exception as e:
        results['face_index'] = f'Error: {e}\n{traceback.format_exc()}'
    # 42 – people tag sync + untagged samples
    try:
        task_6(config, logger)
        results['people_sync'] = 'OK'
    except Exception as e:
        results['people_sync'] = f'Error: {e}\n{traceback.format_exc()}'
    # 43 – seed feedback refresh
    try:
        task_7(config, logger)
        results['seed_refresh'] = 'OK'
    except Exception as e:
        results['seed_refresh'] = f'Error: {e}\n{traceback.format_exc()}'
    results['total_time_seconds'] = time.time() - start
    # write summary JSON for later review
    with open('run_full_test_summary.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print('Full test suite completed. Summary written to run_full_test_summary.json')

if __name__ == '__main__':
    run_test_suite()
