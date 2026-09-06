from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def date_bounds(range_name: str = "today", from_date: str | None = None, to_date: str | None = None):
    tz = ZoneInfo(settings.timezone)
    local_now = datetime.now(tz)

    if from_date and to_date:
        start_local = datetime.combine(datetime.fromisoformat(from_date).date(), time.min, tzinfo=tz)
        end_local = datetime.combine(datetime.fromisoformat(to_date).date() + timedelta(days=1), time.min, tzinfo=tz)
    elif range_name == "yesterday":
        day = local_now.date() - timedelta(days=1)
        start_local = datetime.combine(day, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
    elif range_name == "last7":
        end_local = datetime.combine(local_now.date() + timedelta(days=1), time.min, tzinfo=tz)
        start_local = end_local - timedelta(days=7)
    elif range_name == "last30":
        end_local = datetime.combine(local_now.date() + timedelta(days=1), time.min, tzinfo=tz)
        start_local = end_local - timedelta(days=30)
    elif range_name == "this_month":
        start_local = datetime(local_now.year, local_now.month, 1, tzinfo=tz)
        if local_now.month == 12:
            end_local = datetime(local_now.year + 1, 1, 1, tzinfo=tz)
        else:
            end_local = datetime(local_now.year, local_now.month + 1, 1, tzinfo=tz)
    elif range_name == "last_month":
        this_month = datetime(local_now.year, local_now.month, 1, tzinfo=tz)
        end_local = this_month
        previous_day = this_month - timedelta(days=1)
        start_local = datetime(previous_day.year, previous_day.month, 1, tzinfo=tz)
    else:
        start_local = datetime.combine(local_now.date(), time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
