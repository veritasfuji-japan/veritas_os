# veritas_os/tests/test_time_utils.py
import re
from datetime import datetime, timezone

from veritas_os.core.time_utils import (
    utc_now,
    utc_now_iso_z,
    utc_from_timestamp,
    utc_from_timestamp_iso_z,
)


def test_utc_now_returns_aware_utc():
    """utc_now がタイムゾーン付き UTC datetime を返すことを確認"""
    now = utc_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    # UTC であること（オフセット0秒）
    assert now.tzinfo.utcoffset(now).total_seconds() == 0


def test_utc_now_iso_z_default_and_seconds():
    """utc_now_iso_z のデフォルトと timespec='seconds' の両方を確認"""
    s_default = utc_now_iso_z()
    s_seconds = utc_now_iso_z(timespec="seconds")

    # どちらも末尾が 'Z'
    assert s_default.endswith("Z")
    assert s_seconds.endswith("Z")

    # 形式チェック（だいたい ISO8601 + 'Z'）
    assert re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$",
        s_default,
    )
    assert re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        s_seconds,
    )

    # 'Z' を +00:00 に戻せば fromisoformat でパースでき、UTC になる
    dt_default = datetime.fromisoformat(s_default.replace("Z", "+00:00"))
    dt_seconds = datetime.fromisoformat(s_seconds.replace("Z", "+00:00"))
    assert dt_default.tzinfo == timezone.utc
    assert dt_seconds.tzinfo == timezone.utc


def test_utc_from_timestamp_epoch():
    """UNIX epoch (0) が正しく UTC datetime になるか"""
    dt = utc_from_timestamp(0)
    assert dt.year == 1970
    assert dt.month == 1
    assert dt.day == 1
    assert dt.hour == 0
    assert dt.minute == 0
    assert dt.second == 0
    assert dt.tzinfo == timezone.utc
    # 往復で同じ timestamp になる
    assert dt.timestamp() == 0.0


def test_utc_from_timestamp_iso_z_epoch():
    """UNIX epoch (0) -> ISO8601 + Z の変換を確認"""
    s_default = utc_from_timestamp_iso_z(0)
    s_seconds = utc_from_timestamp_iso_z(0, timespec="seconds")

    # epoch かつ microseconds=0 なのでどちらも同じになるはず
    assert s_default == "1970-01-01T00:00:00Z"
    assert s_seconds == "1970-01-01T00:00:00Z"

