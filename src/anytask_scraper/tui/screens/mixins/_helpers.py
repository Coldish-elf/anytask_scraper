from __future__ import annotations

import csv
import io
import re
import unicodedata
from datetime import datetime, timedelta

from rich.text import Text

_STATUS_STYLES: dict[str, str] = {
    "Зачтено": "bold green",
    "На проверке": "bold yellow",
    "Не зачтено": "bold red",
    "Новый": "dim",
}

_QUEUE_STATUS_COLORS: dict[str, str] = {
    "success": "bold green",
    "warning": "bold yellow",
    "danger": "bold red",
    "info": "bold cyan",
    "default": "dim",
    "primary": "bold blue",
}

ExportFilterValue = str | list[str]


def _csv_row(fields: list[str]) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerow(fields)
    return buf.getvalue().rstrip("\r\n")


def make_safe_id(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    if not safe:
        import hashlib

        safe = "h" + hashlib.md5(name.encode()).hexdigest()[:10]
    if safe and safe[0].isdigit():
        safe = "n" + safe
    return safe


def _parse_mark(mark: str) -> float:
    try:
        return float(mark.replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def _parse_update_time(time_str: str) -> datetime:
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    return datetime.min


def _styled_status(status: str) -> Text:
    style = _STATUS_STYLES.get(status, "")
    return Text(status or "-", style=style)


def _styled_deadline(deadline: datetime | None) -> Text:
    if deadline is None:
        return Text("-", style="dim")
    label = deadline.strftime("%d.%m.%Y")
    now = datetime.now()
    if deadline < now:
        return Text(label, style="dim strike")
    if deadline < now + timedelta(days=3):
        return Text(label, style="bold yellow")
    return Text(label)


def _format_score(task: object) -> str:
    parts: list[str] = []
    score = getattr(task, "score", None)
    max_score = getattr(task, "max_score", None)
    if score is not None:
        parts.append(str(score))
    if max_score is not None:
        parts.append(f"/{max_score}")
    return " ".join(parts) if parts else "-"


def _normalize_multi_values(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        stripped = value.strip()
        return {stripped} if stripped else set()
    if isinstance(value, (list, tuple, set)):
        result: set[str] = set()
        for item in value:
            if isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    result.add(stripped)
        return result
    return set()


def _extract_filter_values(
    filters: dict[str, ExportFilterValue] | None,
    key: str,
) -> set[str]:
    if not filters:
        return set()
    return _normalize_multi_values(filters.get(key))


def _extract_filter_text(
    filters: dict[str, ExportFilterValue] | None,
    key: str,
) -> str:
    if not filters:
        return ""
    value = filters.get(key)
    if isinstance(value, str):
        return value.strip()
    return ""
