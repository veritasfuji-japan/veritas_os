# veritas_os/core/time_utils.py
from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """タイムゾーン付き UTC 現在時刻（datetime.now(datetime.UTC) 相当）"""
    return datetime.now(timezone.utc)


def utc_now_iso_z(timespec: Optional[str] = None) -> str:
    """
    ISO8601 + 'Z' 形式の現在時刻文字列を返す。

    例:
      utc_now_iso_z()                    -> 2025-12-08T10:23:45.123456Z
      utc_now_iso_z(timespec="seconds")  -> 2025-12-08T10:23:45Z
    """
    if timespec is not None:
        s = utc_now().isoformat(timespec=timespec)
    else:
        s = utc_now().isoformat()
    # Python の isoformat は +00:00 なので Z に置き換える
    return s.replace("+00:00", "Z")


def utc_from_timestamp(ts: float) -> datetime:
    """UNIX timestamp -> timezone-aware UTC datetime"""
    return datetime.fromtimestamp(float(ts), timezone.utc)


def utc_from_timestamp_iso_z(ts: float, timespec: Optional[str] = None) -> str:
    """
    UNIX timestamp -> ISO8601 + 'Z' 文字列。

    例:
      utc_from_timestamp_iso_z(1733640000) -> 2025-12-08T10:00:00Z
    """
    dt = utc_from_timestamp(ts)
    if timespec is not None:
        s = dt.isoformat(timespec=timespec)
    else:
        s = dt.isoformat()
    return s.replace("+00:00", "Z")

