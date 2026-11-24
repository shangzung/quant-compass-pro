"""
Unified Error Handling & Developer Traceback Logger for Quant Compass AI Ultimate V2.1.
Writes full tracebacks to `quant_compass_errors.log` while returning clean user-facing summaries.
"""
import logging
import traceback
from typing import Tuple

LOG_FILE = "quant_compass_errors.log"

_logger = logging.getLogger("QuantCompass")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _logger.addHandler(_fh)


def log_exception(stage: str, exc: Exception) -> Tuple[str, str]:
    """
    Logs full traceback to file and returns (user_friendly_summary, full_traceback).
    """
    tb = traceback.format_exc()
    _logger.error("Stage [%s] failed: %s\n%s", stage, str(exc), tb)

    exc_type = type(exc).__name__
    msg = str(exc)
    if "IntegrityError" in exc_type or "OperationalError" in exc_type:
        summary = f"資料庫寫入或結構異常（{stage}）：{msg}"
    elif "ConnectionError" in exc_type or "Timeout" in exc_type:
        summary = f"網路連線逾時或無法連線（{stage}）：請確認網路或稍後重試。"
    elif "KeyError" in exc_type or "ValueError" in exc_type:
        summary = f"資料格式或欄位異常（{stage}）：{msg}"
    else:
        summary = f"執行階段「{stage}」發生錯誤（{exc_type}）：{msg}"

    return summary, tb


def log_info(message: str) -> None:
    _logger.info(message)
