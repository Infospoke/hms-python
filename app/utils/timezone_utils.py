from datetime import datetime
from typing import Optional
import pytz

IST = pytz.timezone("Asia/Kolkata")


def get_ist_now() -> datetime:
    return datetime.now(IST).replace(tzinfo=None)


def convert_to_ist(dt: datetime) -> datetime:
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)

    return dt.astimezone(IST)


def format_ist_datetime(
    dt: datetime, format_string: str = "%Y-%m-%d %H:%M:%S %Z"
) -> str:
    if dt is None:
        return None

    ist_dt = convert_to_ist(dt) if dt.tzinfo is not None else IST.localize(dt)
    return ist_dt.strftime(format_string)


def format_datetime_for_api(dt: datetime) -> str:
    if dt is None:
        return None

    ist_dt = convert_to_ist(dt) if dt.tzinfo is not None else IST.localize(dt)
    return ist_dt.isoformat()


def parse_datetime_to_ist(date_string: str) -> Optional[datetime]:
    if not date_string:
        return None

    try:
        dt = datetime.fromisoformat(date_string)
        if dt.tzinfo is None:
            return IST.localize(dt)
        return dt.astimezone(IST)
    except (ValueError, TypeError):
        return None
