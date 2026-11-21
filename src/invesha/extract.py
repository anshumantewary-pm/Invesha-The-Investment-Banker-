"""Automatic extraction: read any spreadsheet and trace the inputs each model needs.

No template is required. The reader scans every sheet, finds year columns (FY24, 2023-24,
Mar-24, 2024...), recognises line items by the names used in Ind-AS, IFRS and US GAAP
statements (and in startup MIS and project term sheets), takes the latest year, and derives
the model's assumptions from history: EBITDA, growth, D&A / capex / working capital as a
share of revenue, effective tax rate, cost of debt, shares from EPS, and for startups ARPU,
churn and CAC.

Every value comes back with a trace: where it was found or how it was calculated, so the
user can check it. Required inputs that could not be found are listed as missing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- grids


@dataclass
class Row:
    sheet: str
    label: str
    values: list[float]  # chronological (oldest -> latest) when years are known
    years: list[str]
    text: str = ""  # first text value after the label (for text fields)

    @property
    def latest(self) -> float:
        return self.values[-1]

    def where(self, i: int = -1) -> str:
        year = f", {self.years[i]}" if self.years else ""
        return f"{self.sheet} › {self.label}{year}"


YEAR_RE = re.compile(
    r"^(?:fy\s?'?)?(?:19|20)\d{2}(?:\s?[-/–]\s?\d{2,4})?$|^fy\s?'?\d{2}$|^(?:[a-z]{3}[-\s']?\d{2,4})$|^(?:q[1-4]\s?fy\s?\d{2,4})$",
    re.I,
)
MONTH_RE = re.compile(
    r"^(m\s?\d{1,3}|month\s?\d{1,3}|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-\s']?\d{0,4})$", re.I
)


def _is_period(cell: Any) -> bool:
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        return 1990 <= cell <= 2100 and float(cell).is_integer()
    if not isinstance(cell, str):
        return False
    t = cell.strip().lower().replace("fy ", "fy").replace("(a)", "").replace("(e)", "").replace("(f)", "").strip()
    t = re.sub(r"\s*(actual|audited|estimated|projected|act|est)$", "", t)
    return bool(YEAR_RE.match(t) or MONTH_RE.match(t))


def _num(cell: Any) -> float | None:
    if isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    if not isinstance(cell, str):
        return None
    t = cell.strip()
    if not t or t in ("-", "–", "—", "nil", "NIL", "Nil"):
        return 0.0 if t else None
    neg = t.startswith("(") and t.endswith(")")
    t = re.sub(r"[,\s₹$€£()]", "", t)
    pct = t.endswith("%")
    t = t.rstrip("%")
    try:
        x = float(t)
    except ValueError:
        return None
    if pct:
        x /= 100
    return -x if neg else x


def rows_from_grid(sheet: str, grid: list[list[Any]]) -> tuple[list[Row], dict[str, Any]]:
    """Turn a raw grid into labelled numeric rows, ordering columns by period when headers exist."""
    meta: dict[str, Any] = {}
    header: dict[int, str] = {}
    rows: list[Row] = []
    for raw in grid:
        cells = list(raw)
        texts = [c for c in cells if isinstance(c, str) and c.strip()]
        joined = " ".join(texts).lower()
        unit = _unit(joined)
        if unit and "unit" not in meta:
            meta["unit"], meta["currency"], meta["unit_source"] = unit[0], unit[1], f"{sheet} › “{joined[:60]}”"
        periods = {
            i: (str(int(c)) if isinstance(c, float) else str(c).strip()) for i, c in enumerate(cells) if _is_period(c)
        }
        if len(periods) >= 2 and len(periods) >= sum(1 for c in cells if c not in (None, "")) - 2:
            header = periods
            continue
        label_idx = next((i for i, c in enumerate(cells) if isinstance(c, str) and c.strip() and _num(c) is None), None)
        if label_idx is None:
            continue
        label = re.sub(r"\s+", " ", str(cells[label_idx])).strip()
        nums = [(i, _num(c)) for i, c in enumerate(cells) if i > label_idx and _num(c) is not None]
        text_after = next(
            (str(c).strip() for c in cells[label_idx + 1 :] if isinstance(c, str) and c.strip() and _num(c) is None), ""
        )
        if not nums:
            if text_after:
                rows.append(Row(sheet, label, [], [], text_after))
            continue
        if header and any(i in header for i, _ in nums):
            dated = [(i, v) for i, v in nums if i in header]
            order = _chronological([header[i] for i, _ in dated])
            values = [dated[k][1] for k in order]
            years = [header[dated[k][0]] for k in order]
        else:
            values, years = [v for _, v in nums], []
        rows.append(Row(sheet, label, [float(v) for v in values if v is not None], years, text_after))
    return rows, meta


def _period_key(label: str) -> tuple[int, int]:
    t = label.lower()
    m = re.search(r"(19|20)(\d{2})\s?[-/–]\s?(\d{2,4})", t)
    if m:
        return int(m.group(1) + m.group(2)) + 1, 0  # 2023-24 -> 2024
    m = re.search(r"(19|20)\d{2}", t)
    if m:
        return int(m.group(0)), 0
    m = re.search(r"fy\s?'?(\d{2})\b", t)
    if m:
        return 2000 + int(m.group(1)), 0
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-\s']?(\d{2,4})?", t)
    if m:
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        year = int(m.group(2)) if m.group(2) else 0
        year = 2000 + year if 0 < year < 100 else year
        return year, months.index(m.group(1)) + 1
    m = re.search(r"(\d{1,3})", t)
    return (0, int(m.group(1))) if m else (0, 0)


def _chronological(labels: list[str]) -> list[int]:
    keys = [_period_key(x) for x in labels]
    idx = list(range(len(labels)))
    if all(k == (0, 0) for k in keys):
        return idx
    return sorted(idx, key=lambda i: keys[i])


UNITS = [
    (r"\bcrores?\b|\bcr\b", "Cr", "₹"),
    (r"\blakhs?\b|\blacs?\b", "L", "₹"),
    (r"\bmillions?\b|\bmn\b|\bmm\b|\$\s?m\b", "Mn", ""),
    (r"\bbillions?\b|\bbn\b", "Bn", ""),
    (r"\bthousands?\b|'000|\b000s\b", "K", ""),
]


def _unit(text: str) -> tuple[str, str] | None:
    if not re.search(r"\b(in|amount|figures|rs|inr|usd|₹|\$|€|£|currency|unit)\b|₹|\$", text):
        return None
    for pattern, unit, cur in UNITS:
        if re.search(pattern, text):
            currency = (
                "₹"
                if ("₹" in text or "rs" in text or "inr" in text)
                else "$"
                if ("$" in text or "usd" in text)
                else "€"
                if ("€" in text or "eur" in text)
                else "£"
                if ("£" in text or "gbp" in text)
                else cur
            )
            return unit, currency
    return None


# ---------------------------------------------------------------- concepts

# concept -> (include patterns, exclude patterns). Matched against the lower-cased label.
CONCEPTS: dict[str, tuple[list[str], list[str]]] = {
    "revenue": (
        [
            r"^revenue from operations",
            r"^(total |net )?revenues?\b",
            r"^net sales",
            r"^(total )?sales\b",
            r"^turnover",
            r"^income from operations",
            r"^operating revenue",
            r"^top ?line",
        ],
        [r"other", r"cost", r"growth", r"%", r"per ", r"deferred", r"recurring"],
    ),
    "total_income": ([r"^total income", r"^total revenue and other income"], []),
    "other_income": ([r"^other (operating )?income", r"^non.?operating income"], [r"comprehensive"]),
    "cogs": (
        [
            r"cost of (goods sold|sales|revenue|materials consumed)",
            r"^cogs",
            r"^purchases? of stock",
            r"^raw materials? consumed",
            r"^changes? in inventor",
        ],
        [],
    ),
    "employee": (
        [
            r"^employee benefits? expenses?",
            r"^employee (costs?|expenses?)",
            r"^staff costs?",
            r"^salaries",
            r"^personnel",
        ],
        [],
    ),
    "other_expenses": (
        [
            r"^other expenses",
            r"^selling,? general",
            r"^sg&a",
            r"^general and administrative",
            r"^operating expenses",
            r"^opex\b",
        ],
        [],
    ),
    "total_expenses": ([r"^total expenses", r"^total operating expenses", r"^total costs"], []),
    "ebitda": (
        [
            r"^ebitda\b",
            r"^operating profit before depreciation",
            r"^pbdit",
            r"^earnings before interest,? tax(es)?,? depreciation",
        ],
        [r"margin", r"%"],
    ),
    "ebitda_margin": ([r"^ebitda margin", r"^operating margin"], []),
    "da": ([r"^depreciation", r"^d ?& ?a\b", r"^amortisation", r"^amortization"], [r"accumulated", r"rate", r"%"]),
    "ebit": (
        [r"^ebit\b(?!da)", r"^operating (profit|income)\b(?! before)", r"^profit from operations", r"^pbit\b"],
        [r"margin", r"%"],
    ),
    "interest": (
        [
            r"^finance costs?",
            r"^interest (expense|cost|paid)",
            r"^interest$",
            r"^financial expenses",
            r"^borrowing costs",
        ],
        [r"income", r"received", r"rate", r"%"],
    ),
    "pbt": (
        [
            r"^profit before (exceptional items and )?tax",
            r"^pbt\b",
            r"^earnings before (income )?tax",
            r"^income before (income )?tax",
            r"^profit/\(loss\) before tax",
        ],
        [r"margin", r"%"],
    ),
    "tax": (
        [
            r"^total tax expense",
            r"^tax expenses?",
            r"^income tax( expense)?\b",
            r"^provision for tax",
            r"^taxes\b",
            r"^tax$",
        ],
        [r"rate", r"%", r"before", r"deferred tax (asset|liabilit)", r"payable", r"after"],
    ),
    "net_income": (
        [
            r"^profit for the (year|period)",
            r"^net (profit|income)\b",
            r"^pat\b",
            r"^profit after tax",
            r"^net earnings",
            r"^profit/\(loss\) for the",
        ],
        [r"margin", r"%", r"attributable to non"],
    ),
    "eps": ([r"^(basic )?earnings per share", r"^(basic )?eps\b", r"^basic\b"], [r"diluted"]),
    "capex": (
        [
            r"purchase of (property|fixed assets|ppe|tangible)",
            r"^capital expenditure",
            r"^capex\b",
            r"additions? to (fixed assets|property|ppe)",
            r"acquisition of property",
        ],
        [r"%", r"proceeds", r"sale of"],
    ),
    "receivables": (
        [r"^trade receivables", r"^(accounts|sundry) receivables?", r"^(sundry )?debtors", r"^receivables"],
        [r"days"],
    ),
    "inventory": ([r"^inventor(y|ies)", r"^stock in trade", r"^stocks?\b"], [r"days", r"change"]),
    "payables": ([r"^trade payables", r"^(accounts|sundry) payables?", r"^(sundry )?creditors"], [r"days"]),
    "cash": (
        [r"^cash and cash equivalents", r"^cash (&|and) bank", r"^cash( balance)?$", r"^closing cash", r"^cash at end"],
        [r"flow", r"generated", r"used", r"opening", r"beginning", r"net (increase|decrease|change)", r"burn"],
    ),
    "bank_balances": ([r"^bank balances other than", r"^other bank balances"], []),
    "borrowings_lt": (
        [r"^(long.?term|non.?current) borrowings", r"^borrowings.*non.?current", r"^long.?term debt", r"^term loans?"],
        [],
    ),
    "borrowings_st": (
        [
            r"^(short.?term|current) borrowings",
            r"^borrowings.*\bcurrent",
            r"^short.?term debt",
            r"^working capital (loans?|borrowings)",
        ],
        [r"non.?current"],
    ),
    "borrowings": (
        [r"^(total )?borrowings$", r"^total debt", r"^debt$", r"^(total )?loans?$", r"^gross debt"],
        [r"net debt"],
    ),
    "equity": (
        [r"^total equity", r"^(total )?shareholders'? (funds|equity)", r"^net worth", r"^equity attributable"],
        [r"liabilities and"],
    ),
    "shares": (
        [
            r"^(number of |no\.? of )?(equity )?shares (outstanding|in issue)",
            r"^shares outstanding",
            r"^number of shares",
            r"^weighted average (number of )?shares",
        ],
        [r"price", r"capital", r"premium", r"application"],
    ),
    "share_price": (
        [r"^(current |market )?share price", r"^market price", r"^cmp\b", r"^stock price", r"^price per share"],
        [],
    ),
    "invested_capital": ([r"^invested capital", r"^capital employed"], [r"return"]),
    # startup MIS
    "customers": (
        [
            r"^(total |active |paying )?customers",
            r"^(active |paying )?users",
            r"^subscribers",
            r"^clients",
            r"^accounts$",
        ],
        [r"new", r"churn", r"lost", r"per", r"acquisition", r"cost"],
    ),
    "new_customers": (
        [r"^new (customers|users|subscribers|clients|accounts)", r"^customers? (added|acquired)", r"^gross adds"],
        [],
    ),
    "churned": ([r"^churned (customers|users)", r"^(customers|users) (lost|churned)", r"^lost (customers|users)"], []),
    "churn_rate": ([r"^(monthly )?churn( rate)?", r"^logo churn"], [r"customers", r"users"]),
    "mrr": ([r"^mrr\b", r"^monthly recurring revenue"], [r"growth", r"per"]),
    "arr": ([r"^arr\b", r"^annual recurring revenue"], [r"growth", r"multiple"]),
    "arpu": ([r"^arpu\b", r"^arpa\b", r"^average revenue per (user|account|customer)"], []),
    "cac": ([r"^cac\b", r"^customer acquisition cost", r"^cost per acquisition"], [r"payback", r"ltv"]),
    "marketing": (
        [r"^(sales (and|&) )?marketing", r"^advertising", r"^performance marketing", r"^paid acquisition"],
        [r"%"],
    ),
    "gross_margin": ([r"^gross margin"], []),
    "burn": ([r"^(net )?(monthly )?burn", r"^cash burn"], [r"multiple"]),
    "headcount_cost": ([r"^(team|payroll|people|headcount) (costs?|expenses?)", r"^salaries"], []),
    # project term sheet
    "project_cost": (
        [r"^(total )?project cost", r"^capex\b", r"^epc (cost|price)", r"^capital cost", r"^total investment"],
        [r"%", r"per"],
    ),
    "capacity": (
        [r"^(installed |plant |design )?capacity", r"^annual (output|generation|production)", r"^generation"],
        [r"utili", r"factor", r"load"],
    ),
    "utilisation": (
        [r"^(plant load factor|plf|cuf|capacity utili[sz]ation|utili[sz]ation|availability|load factor)"],
        [],
    ),
    "tariff": (
        [r"^tariff", r"^(selling |offtake |ppa )?price", r"^realisation per", r"^rate per unit"],
        [r"escalation", r"share"],
    ),
    "price_escalation": ([r"^(tariff|price) escalation"], []),
    "opex_fixed": (
        [r"^(fixed )?o ?& ?m", r"^operations? (and|&) maintenance", r"^fixed (opex|costs?)", r"^annual opex"],
        [r"escalation", r"variable"],
    ),
    "opex_variable": ([r"^variable (opex|costs?)", r"^variable cost per"], []),
    "opex_escalation": ([r"^(o ?& ?m|opex|cost) escalation"], []),
    "debt_rate": ([r"^(interest|lending) rate", r"^cost of debt", r"^coupon"], []),
    "tenor": ([r"^(loan |debt )?tenor", r"^repayment (period|tenor)", r"^loan term"], []),
    "gearing": (
        [r"^(debt|gearing)( ratio)?\s*%?$", r"^debt\s*:?\s*(to\s*)?equity", r"^gearing", r"^debt share"],
        [r"service"],
    ),
    "construction_years": ([r"^construction (period|years|time)", r"^build period"], []),
    "operating_years": (
        [
            r"^(project |useful |operating |economic )?life",
            r"^operating (period|years)",
            r"^concession period",
            r"^ppa term",
        ],
        [],
    ),
    "tax_rate": ([r"^(effective |corporate )?tax rate"], []),
    "company_name": (
        [r"^(company|entity|business|startup|project)( name)?$", r"^name of the (company|entity|project)"],
        [],
    ),
    "sector": ([r"^(sector|industry)$"], []),
}


def classify(label: str) -> str | None:
    t = label.lower().strip(" :.-*#")
    t = re.sub(r"^\(?[ivx]+\)\s*|^\d+(\.\d+)*[.)]?\s+|^[a-z][.)]\s+", "", t)  # drop numbering like "(i)", "2.1", "a)"
    for concept, (inc, exc) in CONCEPTS.items():
        if any(re.search(p, t) for p in inc) and not any(re.search(p, t) for p in exc):
            return concept
    return None


@dataclass
class Found:
    rows: dict[str, Row] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)

    def get(self, concept: str) -> Row | None:
        r = self.rows.get(concept)
        return r if r and r.values else None


def scan(grids: list[tuple[str, list[list[Any]]]]) -> Found:
    found = Found()
    for sheet, grid in grids:
        rows, meta = rows_from_grid(sheet, grid)
        for k, v in meta.items():
            found.meta.setdefault(k, v)
        for row in rows:
            concept = classify(row.label)
            if concept is None:
                if row.values:
                    found.unmatched.append(row.label)
                continue
            current = found.rows.get(concept)
            # Prefer rows with more history, then the first seen (statements list totals after details
            # rarely; when they do the explicit "total" pattern is a separate concept).
            if current is None or (len(row.values) > len(current.values)) or (not current.values and row.text):
                found.rows[concept] = row
    return found


# ---------------------------------------------------------------- derivations


@dataclass
class Trace:
    field: str
    value: Any
    source: str
    method: str  # "found" or "derived"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _avg_ratio(num: Row, den: Row, n: int = 3) -> float | None:
    """Average of num/den over the last n aligned periods (by year label when both have them)."""
    pairs: list[tuple[float, float]] = []
    if num.years and den.years:
        lookup = dict(zip(den.years, den.values))
        pairs = [(v, lookup[y]) for y, v in zip(num.years, num.values) if y in lookup]
    else:
        k = min(len(num.values), len(den.values))
        pairs = list(zip(num.values[-k:], den.values[-k:]))
    pairs = [(a, b) for a, b in pairs[-n:] if b]
    if not pairs:
        return None
    return sum(abs(a) / b for a, b in pairs) / len(pairs)


def _pct_value(row: Row) -> float:
    x = row.latest
    return x / 100 if abs(x) > 1.5 else x


def derive_company(f: Found) -> tuple[dict[str, Any], list[Trace]]:
    out: dict[str, Any] = {}
    trace: list[Trace] = []

    def put(key: str, value: Any, source: str, method: str = "found") -> None:
        out[key] = value
        trace.append(Trace(key, value, source, method))

    rev = f.get("revenue") or f.get("total_income")
    if rev is None:
        return out, trace
    put("revenue", rev.latest, rev.where())
    if len(rev.values) >= 2 and rev.values[-2] > 0:
        last_g = rev.values[-1] / rev.values[-2] - 1
        hist = rev.values[-4:]
        cagr = (hist[-1] / hist[0]) ** (1 / (len(hist) - 1)) - 1 if hist[0] > 0 else last_g
        g0 = _clamp(0.5 * last_g + 0.5 * cagr, -0.2, 0.6)
        span = f"{rev.years[-len(hist)]}–{rev.years[-1]}" if rev.years else f"last {len(hist)} periods"
        put(
            "growth_start",
            round(g0, 4),
            f"Revenue growth: latest {_pct(last_g)}, CAGR {_pct(cagr)} ({span}); blended",
            "derived",
        )
        put(
            "growth_end",
            round(_clamp(g0 / 2, 0.03, 0.10), 4),
            "Half of year-1 growth, kept between 3% and 10% (fade to maturity)",
            "derived",
        )

    da = f.get("da")
    ebitda_row = f.get("ebitda")
    ebitda, how = None, ""
    if ebitda_row:
        ebitda, how = ebitda_row.latest, ebitda_row.where()
    elif f.get("ebit") and da:
        ebitda, how = f.get("ebit").latest + abs(da.latest), "EBIT + D&A"  # type: ignore[union-attr]
    elif f.get("pbt") and da:
        interest = f.get("interest")
        other = f.get("other_income")
        ebitda = f.get("pbt").latest + abs(da.latest) + (abs(interest.latest) if interest else 0.0)  # type: ignore[union-attr]
        how = "Profit before tax + depreciation" + (" + finance costs" if interest else "")
        if other:
            ebitda -= other.latest
            how += " − other income"
    else:
        costs = [f.get(k) for k in ("cogs", "employee", "other_expenses")]
        costs_found = [c for c in costs if c]
        total = f.get("total_expenses")
        if total:
            ebitda = (
                rev.latest
                - abs(total.latest)
                + (abs(da.latest) if da else 0.0)
                + (abs(f.get("interest").latest) if f.get("interest") else 0.0)
            )  # type: ignore[union-attr]
            how = "Revenue − total expenses + D&A + finance costs"
        elif costs_found:
            ebitda = rev.latest - sum(abs(c.latest) for c in costs_found)  # type: ignore[union-attr]
            how = "Revenue − " + " − ".join(c.label for c in costs_found)  # type: ignore[union-attr]
    margin_row = f.get("ebitda_margin")
    if ebitda is not None and rev.latest:
        put("ebitda_margin", round(ebitda / rev.latest, 4), f"EBITDA {ebitda:,.1f} ÷ revenue ({how})", "derived")
    elif margin_row:
        put("ebitda_margin", _pct_value(margin_row), margin_row.where())

    if da:
        r = _avg_ratio(da, rev)
        if r is not None:
            put(
                "da_pct",
                round(r, 4),
                f"Depreciation ÷ revenue, average of last {min(3, len(da.values))} years",
                "derived",
            )
    capex = f.get("capex")
    if capex:
        r = _avg_ratio(capex, rev)
        if r is not None:
            put(
                "capex_pct",
                round(r, 4),
                f"{capex.label} ÷ revenue, average of last {min(3, len(capex.values))} years",
                "derived",
            )
    recv, inv, pay = f.get("receivables"), f.get("inventory"), f.get("payables")
    if recv or inv or pay:
        nwc = (recv.latest if recv else 0) + (inv.latest if inv else 0) - (pay.latest if pay else 0)
        parts = " + ".join(x for x, r in (("receivables", recv), ("inventory", inv)) if r) + (
            " − payables" if pay else ""
        )
        put("nwc_pct", round(_clamp(nwc / rev.latest, -0.5, 1.0), 4), f"({parts}) ÷ revenue, latest year", "derived")
    tax, pbt = f.get("tax"), f.get("pbt")
    if tax and pbt and pbt.latest > 0:
        put(
            "tax_rate",
            round(_clamp(abs(tax.latest) / pbt.latest, 0.0, 0.45), 4),
            "Tax expense ÷ profit before tax, latest year",
            "derived",
        )
    elif f.get("tax_rate"):
        put("tax_rate", _pct_value(f.get("tax_rate")), f.get("tax_rate").where())  # type: ignore[union-attr]

    lt, st, total_debt = f.get("borrowings_lt"), f.get("borrowings_st"), f.get("borrowings")
    debt = None
    if lt or st:
        debt = (lt.latest if lt else 0) + (st.latest if st else 0)
        put("debt", debt, " + ".join(r.where() for r in (lt, st) if r), "derived" if lt and st else "found")
    elif total_debt:
        debt = total_debt.latest
        put("debt", debt, total_debt.where())
    cash, bank = f.get("cash"), f.get("bank_balances")
    if cash:
        c = cash.latest + (bank.latest if bank else 0)
        put("cash", c, cash.where() + (f" + {bank.label}" if bank else ""), "derived" if bank else "found")
    interest = f.get("interest")
    if interest and debt:
        put(
            "interest_rate",
            round(_clamp(abs(interest.latest) / debt, 0.03, 0.25), 4),
            "Finance costs ÷ borrowings, latest year",
            "derived",
        )
    elif f.get("debt_rate"):
        put("interest_rate", _pct_value(f.get("debt_rate")), f.get("debt_rate").where())  # type: ignore[union-attr]

    shares, eps, ni = f.get("shares"), f.get("eps"), f.get("net_income")
    if shares:
        put("shares", shares.latest, shares.where())
    elif eps and ni and eps.latest:
        put("shares", round(ni.latest / eps.latest, 4), f"Net profit ÷ basic EPS ({ni.where()})", "derived")
    price = f.get("share_price")
    if price:
        put("share_price", price.latest, price.where())
    equity = f.get("equity")
    ic = f.get("invested_capital")
    if ic:
        put("invested_capital", ic.latest, ic.where())
    elif equity:
        put(
            "invested_capital",
            equity.latest + (debt or 0) - (out.get("cash") or 0),
            "Total equity + borrowings − cash",
            "derived",
        )
    return out, trace


def derive_startup(f: Found) -> tuple[dict[str, Any], list[Trace]]:
    out: dict[str, Any] = {}
    trace: list[Trace] = []

    def put(key: str, value: Any, source: str, method: str = "found") -> None:
        out[key] = value
        trace.append(Trace(key, value, source, method))

    cust, new, churned = f.get("customers"), f.get("new_customers"), f.get("churned")
    mrr = f.get("mrr")
    arr = f.get("arr")
    if mrr is None and arr is not None:
        mrr = Row(arr.sheet, arr.label + " ÷ 12", [v / 12 for v in arr.values], arr.years)
    rev = mrr or f.get("revenue")
    if cust:
        put("starting_customers", round(cust.latest), cust.where())
    if new:
        put("new_customers", round(new.latest, 2), new.where())
        if len(new.values) >= 3 and new.values[0] > 0 and new.values[-1] > 0:
            g = (new.values[-1] / new.values[0]) ** (1 / (len(new.values) - 1)) - 1
            put(
                "new_customer_growth",
                round(_clamp(g, -0.2, 0.5), 4),
                f"Monthly growth of new customers over {len(new.values)} periods",
                "derived",
            )
    elif cust and len(cust.values) >= 2:
        adds = max(cust.values[-1] - cust.values[-2], 0)
        put("new_customers", round(adds, 2), "Increase in customers in the latest period (net of churn)", "derived")
    churn = f.get("churn_rate")
    if churn:
        put("churn", round(_pct_value(churn), 4), churn.where())
    elif churned and cust and len(cust.values) >= 2 and cust.values[-2] > 0:
        put(
            "churn",
            round(_clamp(abs(churned.latest) / cust.values[-2], 0, 0.5), 4),
            "Customers lost ÷ customers at start of period",
            "derived",
        )
    arpu = f.get("arpu")
    if arpu:
        put("arpu", arpu.latest, arpu.where())
    elif rev and cust and cust.latest:
        put("arpu", round(rev.latest / cust.latest, 4), f"{rev.label} ÷ customers, latest period", "derived")
    cac, mkt = f.get("cac"), f.get("marketing")
    if cac:
        put("cac", cac.latest, cac.where())
    elif mkt and new and new.latest:
        put("cac", round(abs(mkt.latest) / new.latest, 4), "Marketing spend ÷ new customers, latest period", "derived")
    gm = f.get("gross_margin")
    if gm:
        put("gross_margin", round(_pct_value(gm), 4), gm.where())
    elif rev and f.get("cogs") and rev.latest:
        put(
            "gross_margin",
            round(1 - abs(f.get("cogs").latest) / rev.latest, 4),
            "1 − cost of revenue ÷ revenue",
            "derived",
        )  # type: ignore[union-attr]
    team = f.get("headcount_cost") or f.get("employee")
    other = f.get("other_expenses")
    if team or other:
        fixed = (abs(team.latest) if team else 0) + (abs(other.latest) if other else 0)
        put(
            "fixed_costs",
            round(fixed, 4),
            " + ".join(r.where() for r in (team, other) if r),
            "derived" if team and other else "found",
        )
    elif f.get("burn") and rev:
        burn = abs(f.get("burn").latest)  # type: ignore[union-attr]
        gp = rev.latest * out.get("gross_margin", 0.7)
        marketing = abs(mkt.latest) if mkt else 0
        put(
            "fixed_costs",
            round(max(burn + gp - marketing, 0), 4),
            "Burn + gross profit − marketing, latest period",
            "derived",
        )
    cash = f.get("cash")
    if cash:
        put("cash", cash.latest, cash.where())
    return out, trace


def derive_project(f: Found) -> tuple[dict[str, Any], list[Trace]]:
    out: dict[str, Any] = {}
    trace: list[Trace] = []
    simple = {
        "capex": "project_cost",
        "capacity": "capacity",
        "price": "tariff",
        "opex_fixed": "opex_fixed",
        "opex_variable": "opex_variable",
        "tenor": "tenor",
        "construction_years": "construction_years",
        "operating_years": "operating_years",
    }
    pct = {
        "utilisation": "utilisation",
        "price_escalation": "price_escalation",
        "opex_escalation": "opex_escalation",
        "debt_rate": "debt_rate",
        "gearing": "gearing",
        "tax_rate": "tax_rate",
    }
    for key, concept in simple.items():
        row = f.get(concept)
        if row:
            value: Any = row.latest
            if key in ("tenor", "construction_years", "operating_years"):
                value = int(round(value))
            out[key] = value
            trace.append(Trace(key, value, row.where(), "found"))
    for key, concept in pct.items():
        row = f.get(concept)
        if row:
            value = _pct_value(row)
            if key == "gearing" and value > 1:  # "70:30" style read as 70
                value = value / 100
            out[key] = round(value, 4)
            trace.append(Trace(key, out[key], row.where(), "found"))
    if "capex" not in out and f.get("capex"):
        row = f.get("capex")
        out["capex"] = abs(row.latest)  # type: ignore[union-attr]
        trace.append(Trace("capex", out["capex"], row.where(), "found"))  # type: ignore[union-attr]
    return out, trace


DERIVE = {"company": derive_company, "startup": derive_startup, "project": derive_project, "merger": lambda f: ({}, [])}


def text_fields(f: Found) -> tuple[dict[str, Any], list[Trace]]:
    out: dict[str, Any] = {}
    trace: list[Trace] = []
    name = f.rows.get("company_name")
    if name and name.text:
        out["name"] = name.text
        trace.append(Trace("name", name.text, f"{name.sheet} › {name.label}", "found"))
    sector = f.rows.get("sector")
    if sector and sector.text:
        out["sector_text"] = sector.text
    if "unit" in f.meta:
        out["unit"], out["currency"] = f.meta["unit"], f.meta["currency"] or "₹"
        trace.append(Trace("unit", f"{out['currency']} {out['unit']}", f.meta["unit_source"], "found"))
    return out, trace


def extract(kind: str, grids: list[tuple[str, list[list[Any]]]]) -> dict[str, Any]:
    found = scan(grids)
    values, trace = DERIVE[kind](found)
    texts, ttrace = text_fields(found)
    values = {**texts, **values}
    return {
        "inputs": values,
        "trace": [t.__dict__ for t in ttrace + trace],
        "years": next((r.years for r in found.rows.values() if r.years), []),
        "unmatched": found.unmatched[:25],
    }
