"""Shared finance math, input checking and the display structures every model returns."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from typing import Any, TypeVar


class InputError(ValueError):
    """A user input makes no sense for the model. The CLI and web app show the message."""


# ---------------------------------------------------------------- math


def npv(rate: float, flows: Sequence[float], start: int = 0) -> float:
    """Present value of ``flows`` where flows[0] lands at period ``start``."""
    if rate <= -1:
        raise InputError("discount rate must be above -100%")
    return sum(cf / (1 + rate) ** (i + start) for i, cf in enumerate(flows))


def irr(flows: Sequence[float], low: float = -0.99, high: float = 10.0) -> float | None:
    """Internal rate of return by bisection; ``None`` when the flows never change sign."""
    if not any(f < 0 for f in flows) or not any(f > 0 for f in flows):
        return None

    def f(r: float) -> float:
        return sum(cf / (1 + r) ** i for i, cf in enumerate(flows))

    f_low, f_high = f(low), f(high)
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = f(mid)
        if abs(f_mid) < 1e-9:
            return mid
        if f_low * f_mid < 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


def solve(func: Callable[[float], float], target: float, low: float, high: float, tol: float = 1e-7) -> float | None:
    """Find x in [low, high] with func(x) == target (bisection). ``None`` if not bracketed."""
    f_low, f_high = func(low) - target, func(high) - target
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = func(mid) - target
        if abs(f_mid) < tol or high - low < tol:
            return mid
        if f_low * f_mid < 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    return (low + high) / 2


def annuity_payment(principal: float, rate: float, periods: int) -> float:
    if periods <= 0:
        raise InputError("loan tenor must be at least 1 year")
    if rate == 0:
        return principal / periods
    return principal * rate / (1 - (1 + rate) ** -periods)


def fade(start: float, end: float, years: int) -> list[float]:
    """Linear path from ``start`` (year 1) to ``end`` (final year)."""
    if years == 1:
        return [end]
    return [start + (end - start) * i / (years - 1) for i in range(years)]


# ---------------------------------------------------------------- inputs

T = TypeVar("T")


def from_dict(cls: type[T], data: Mapping[str, Any]) -> T:
    """Build an inputs dataclass from a dict, rejecting unknown keys with a clear message."""
    names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    unknown = sorted(set(data) - names)
    if unknown:
        raise InputError(f"unknown input(s): {', '.join(unknown)}")
    clean = {k: v for k, v in data.items() if v is not None and v != ""}
    try:
        return cls(**clean)
    except TypeError as error:
        missing = str(error).split(":")[-1].strip()
        raise InputError(f"missing required input(s): {missing}") from None


def check(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def number(name: str, value: object, low: float | None = None, high: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{name} must be a number")
    x = float(value)
    if math.isnan(x) or math.isinf(x):
        raise InputError(f"{name} must be a finite number")
    if low is not None and x < low:
        raise InputError(f"{name} must be at least {low:g}")
    if high is not None and x > high:
        raise InputError(f"{name} must be at most {high:g}")
    return x


# ---------------------------------------------------------------- display structures
# Every model returns a Report: the web page, CLI and Excel export all render it.

Fmt = str  # "money", "pct", "x" (multiple), "num", "int", "text", "year"


@dataclass
class Tile:
    label: str
    value: float | str | None
    fmt: Fmt = "money"
    note: str = ""
    tone: str = ""  # "", "good", "warn", "bad"


@dataclass
class Table:
    title: str
    columns: list[str]
    rows: list[list[Any]]  # first cell is the row label
    fmts: list[Fmt] = field(default_factory=list)  # one per row (row-wise tables) ...
    by_column: bool = False  # ... or one per column when True
    note: str = ""


@dataclass
class Bar:
    label: str
    low: float
    high: float
    mid: float | None = None


@dataclass
class Chart:
    title: str
    kind: str  # "range" (football field), "line", "bars"
    bars: list[Bar] = field(default_factory=list)
    series: dict[str, list[float]] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    fmt: Fmt = "money"
    marker: float | None = None
    marker_label: str = ""


@dataclass
class Suggestion:
    priority: str  # "high", "medium", "low"
    area: str
    title: str
    detail: str
    actions: list[str] = field(default_factory=list)


@dataclass
class Report:
    kind: str
    title: str
    subtitle: str
    currency: str
    unit: str
    verdict: str = ""
    verdict_tone: str = ""
    verdict_note: str = ""
    tiles: list[Tile] = field(default_factory=list)
    charts: list[Chart] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    suggestions: list[Suggestion] = field(default_factory=list)
    assumptions: list[list[Any]] = field(default_factory=list)  # [label, value, fmt]
    summary: list[str] = field(default_factory=list)  # executive summary / investment thesis bullets
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


PRIORITY = {"high": 0, "medium": 1, "low": 2}


def sort_suggestions(items: list[Suggestion]) -> list[Suggestion]:
    return sorted(items, key=lambda s: PRIORITY[s.priority])


def fmt_value(value: Any, fmt: Fmt, currency: str = "", unit: str = "") -> str:
    """Plain-text formatting used by the CLI (the web page formats in JavaScript)."""
    if value is None:
        return "-"
    if fmt == "text" or isinstance(value, str):
        return str(value)
    x = float(value)
    if fmt == "pct":
        return f"{x * 100:.1f}%"
    if fmt == "x":
        return f"{x:.2f}x"
    if fmt in ("int", "year"):
        return f"{x:,.0f}"
    if fmt == "price":
        return f"{currency}{x:,.4f}" if abs(x) < 10 else f"{currency}{x:,.2f}"
    if fmt == "num":
        return f"{x:,.2f}"
    sign = "-" if x < 0 else ""
    return f"{sign}{currency}{abs(x):,.1f}{(' ' + unit) if unit else ''}"
