"""
api/serialize.py — Python / numpy / pandas values → JSON the contract promises.

  * ``to_jsonable``   any value → JSON-safe (NaN/±inf → None, numpy scalars → Python,
                      dates → ISO, Decimal → float, DataFrame → Table, Series → Series);
                      values that cannot be represented become ``DROP`` in strict mode
  * ``series``        a pandas Series → ``{"name", "t", "v"}``
  * ``table_from_df`` / ``table_from_rows``   → ``{"columns": [Column], "rows": [...]}``
  * ``column_from_aggrid``   an ag-grid column def (``app.ui.strategy_widgets.col``) → Column
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import decimal
import enum
import math
import re
from pathlib import PurePath
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


class _Drop:
    """Sentinel: the value has no JSON representation (strict mode drops it)."""

    def __repr__(self) -> str:  # pragma: no cover
        return "DROP"


DROP = _Drop()

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _float(v: float):
    return v if math.isfinite(v) else None


def iso(v) -> Optional[str]:
    """Date → 'YYYY-MM-DD'; midnight timestamps without a zone → date; others → ISO-8601."""
    if v is None:
        return None
    if isinstance(v, pd.Timestamp):
        if pd.isna(v):
            return None
        if v.tzinfo is None and v == v.normalize():
            return v.date().isoformat()
        return v.isoformat()
    if isinstance(v, _dt.datetime):
        if v.tzinfo is None and v.time() == _dt.time(0, 0):
            return v.date().isoformat()
        return v.isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, np.datetime64):
        return iso(pd.Timestamp(v)) if not np.isnat(v) else None
    return str(v)


def to_jsonable(obj: Any, *, strict: bool = False, _depth: int = 0):
    """Convert ``obj`` into something ``json.dumps(allow_nan=False)`` accepts.

    ``strict``: unknown objects become ``DROP`` (and are removed from containers)
    instead of their ``str()``.
    """
    if _depth > 50:
        return DROP if strict else None
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        return _float(float(obj))
    if isinstance(obj, decimal.Decimal):
        return _float(float(obj))
    if obj is pd.NaT:
        return None
    if isinstance(obj, (pd.Timestamp, _dt.date, _dt.datetime, np.datetime64)):
        return iso(obj)
    if isinstance(obj, (pd.Timedelta, _dt.timedelta)):
        return pd.Timedelta(obj).total_seconds()
    if isinstance(obj, _dt.time):
        return obj.isoformat()
    if isinstance(obj, enum.Enum):
        return to_jsonable(obj.value, strict=strict, _depth=_depth + 1)
    if isinstance(obj, PurePath):
        return str(obj)
    if isinstance(obj, pd.DataFrame):
        return table_from_df(obj)
    if isinstance(obj, pd.Series):
        return series(obj, name=str(obj.name) if obj.name is not None else "value")
    if isinstance(obj, np.ndarray):
        return [to_jsonable(v, strict=strict, _depth=_depth + 1) for v in obj.tolist()]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            jv = to_jsonable(v, strict=strict, _depth=_depth + 1)
            if jv is DROP:
                continue
            out[str(k) if not isinstance(k, str) else k] = jv
        return out
    if isinstance(obj, (list, tuple, set, frozenset)):
        out_l = []
        for v in obj:
            jv = to_jsonable(v, strict=strict, _depth=_depth + 1)
            if jv is DROP:
                continue
            out_l.append(jv)
        return out_l
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(dataclasses.asdict(obj), strict=strict, _depth=_depth + 1)
    try:  # pandas scalars such as pd.NA
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return DROP if strict else str(obj)


# ── Series ────────────────────────────────────────────────────────────────────

def series(s: Optional[pd.Series], name: str = "value") -> dict:
    """``{"name", "t", "v"}`` with ISO time keys and NaN → null."""
    if s is None or len(s) == 0:
        return {"name": name, "t": [], "v": []}
    s = pd.Series(s)
    idx = s.index
    try:
        idx = pd.to_datetime(idx)
        t = [iso(x) for x in idx]
    except (TypeError, ValueError):
        t = [to_jsonable(x) for x in idx]
    v = [to_jsonable(x) for x in s.tolist()]
    return {"name": name, "t": t, "v": v}


# ── Columns / Tables ──────────────────────────────────────────────────────────

_TYPES = ("string", "number", "integer", "date", "datetime", "bool")


def infer_type(values: Iterable) -> str:
    """Column type from the non-null values: bool | integer | number | date | datetime | string."""
    seen = set()
    for v in values:
        if v is None:
            continue
        if isinstance(v, float) and not math.isfinite(v):
            continue
        if isinstance(v, (bool, np.bool_)):
            seen.add("bool")
        elif isinstance(v, (int, np.integer)):
            seen.add("integer")
        elif isinstance(v, (float, np.floating, decimal.Decimal)):
            seen.add("number")
        elif isinstance(v, (pd.Timestamp, _dt.datetime)):
            seen.add("date" if (getattr(v, "tzinfo", None) is None and
                                pd.Timestamp(v) == pd.Timestamp(v).normalize()) else "datetime")
        elif isinstance(v, _dt.date):
            seen.add("date")
        elif isinstance(v, str):
            if _ISO_DATE.match(v):
                seen.add("date")
            elif _ISO_DATETIME.match(v):
                seen.add("datetime")
            else:
                seen.add("string")
        else:
            seen.add("string")
        if len(seen) > 1 and "string" in seen:
            return "string"
    if not seen:
        return "string"
    if seen == {"integer", "number"}:
        return "number"
    if seen == {"date", "datetime"}:
        return "datetime"
    if len(seen) == 1:
        return seen.pop()
    return "string"


def column(field: str, *, header: Optional[str] = None, type: str = "string",
           format: Optional[str] = None, width: Optional[int] = None,
           pinned: Optional[str] = None, sort: Optional[str] = None, **extra) -> dict:
    out = {"field": field, "header": header if header is not None else field,
           "type": type if type in _TYPES else "string", "format": format,
           "width": width, "pinned": pinned, "sort": sort}
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def column_from_aggrid(cd: dict, rows: Optional[list[dict]] = None) -> Optional[dict]:
    """ag-grid column def → Column. Returns None for pure client-side columns
    (a ``valueGetter`` with no data behind it — a button cell, say)."""
    field = cd.get("field")
    if not field:
        return None
    rows = rows or []
    values = [r.get(field) for r in rows if isinstance(r, dict)]
    if cd.get("valueGetter") is not None and not any(v is not None for v in values):
        return None
    numeric_def = cd.get("type") == "numericColumn" or (
        isinstance(cd.get("type"), list) and "numericColumn" in cd["type"])
    if any(v is not None for v in values):
        # What the rows really hold wins: a grid def may say numeric while the display
        # rows carry formatted strings ("25.3%"), which a client must not parse as numbers.
        typ = infer_type(values)
    else:
        typ = "number" if numeric_def else "string"
    width = cd.get("width")
    try:
        width = int(width) if width is not None else None
    except (TypeError, ValueError):
        width = None
    extra = {}
    if numeric_def:
        extra["numeric"] = True
    if cd.get("hide"):
        extra["hidden"] = True
    if cd.get("flex"):
        extra["flex"] = cd.get("flex")
    if cd.get("minWidth"):
        extra["min_width"] = cd.get("minWidth")
    return column(field, header=cd.get("headerName") or field, type=typ,
                  format=cd.get("format"), width=width,
                  pinned=cd.get("pinned") if cd.get("pinned") in ("left", "right") else None,
                  sort=cd.get("sort") if cd.get("sort") in ("asc", "desc") else None, **extra)


def _dtype_type(s: pd.Series) -> str:
    dt = s.dtype
    if pd.api.types.is_bool_dtype(dt):
        return "bool"
    if pd.api.types.is_integer_dtype(dt):
        return "integer"
    if pd.api.types.is_float_dtype(dt):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(dt):
        nn = s.dropna()
        if len(nn) and getattr(dt, "tz", None) is None and bool((nn == nn.dt.normalize()).all()):
            return "date"
        return "datetime"
    return infer_type(s.tolist())


def table_from_df(df: Optional[pd.DataFrame], *, headers: Optional[dict] = None,
                  formats: Optional[dict] = None, widths: Optional[dict] = None,
                  columns: Optional[list[str]] = None, index: bool = False) -> dict:
    """DataFrame → Table. ``index=True`` keeps a named index as the first column."""
    if df is None:
        return {"columns": [], "rows": []}
    df = pd.DataFrame(df)
    if index:
        df = df.reset_index()
    if columns is not None:
        df = df[[c for c in columns if c in df.columns]]
    headers, formats, widths = headers or {}, formats or {}, widths or {}
    cols = []
    for c in df.columns:
        key = str(c)
        cols.append(column(key, header=headers.get(key, key), type=_dtype_type(df[c]),
                           format=formats.get(key), width=widths.get(key)))
    rows = []
    names = [str(c) for c in df.columns]
    for rec in df.itertuples(index=False, name=None):
        rows.append({n: to_jsonable(v) for n, v in zip(names, rec)})
    return {"columns": cols, "rows": rows}


def table_from_rows(rows: list[dict], *, col_defs: Optional[list[dict]] = None,
                    formats: Optional[dict] = None, headers: Optional[dict] = None,
                    field_order: Optional[list[str]] = None, types: Optional[dict] = None) -> dict:
    """List of row dicts → Table. ``col_defs`` are ag-grid defs; without them the
    columns are every key in first-seen order with inferred types (``types`` fixes
    a column's type explicitly)."""
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    formats, headers, types = formats or {}, headers or {}, types or {}
    cols: list[dict] = []
    if col_defs:
        for cd in col_defs:
            c = column_from_aggrid(cd, rows)
            if c is not None:
                if formats.get(c["field"]) and not c.get("format"):
                    c["format"] = formats[c["field"]]
                cols.append(c)
    else:
        order: list[str] = list(field_order or [])
        for r in rows:
            for k in r:
                if k not in order:
                    order.append(k)
        for k in order:
            cols.append(column(k, header=headers.get(k, k),
                               type=types.get(k) or infer_type(r.get(k) for r in rows),
                               format=formats.get(k)))
    return {"columns": cols, "rows": [to_jsonable(r) for r in rows]}
