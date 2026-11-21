"""Startup finance: monthly model, runway, unit economics, VC-method valuation, fundraising plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from invesha.core import (
    Chart,
    Report,
    Suggestion,
    Table,
    Tile,
    check,
    from_dict,
    number,
    sort_suggestions,
)
from invesha.sectors import get_sector


@dataclass(frozen=True)
class StartupInputs:
    name: str
    sector: str = "technology"
    currency: str = "₹"
    unit: str = "L"  # lakh; amounts are in this unit
    months: int = 36
    starting_customers: float = 0.0
    new_customers: float = 50.0  # acquired in month 1
    new_customer_growth: float = 0.06  # monthly growth in new customers
    arpu: float = 0.05  # monthly revenue per customer
    arpu_growth: float = 0.10  # yearly price increase
    churn: float = 0.03  # monthly
    gross_margin: float = 0.75
    cac: float = 0.4  # cost to acquire one customer
    fixed_costs: float = 15.0  # monthly team + overheads
    fixed_cost_growth: float = 0.03  # monthly
    cash: float = 200.0
    funding: list[dict[str, float]] = field(default_factory=list)  # [{"month": 12, "amount": 500}]
    raise_amount: float = 0.0  # the round being raised now (for VC method)
    exit_multiple: float | None = None  # ARR multiple at exit; default sector mid
    target_return: float = 10.0  # VC target money multiple


@dataclass
class Monthly:
    month: list[int]
    customers: list[float]
    new: list[float]
    churned: list[float]
    mrr: list[float]
    gross_profit: list[float]
    marketing: list[float]
    fixed: list[float]
    ebitda: list[float]
    funding: list[float]
    cash: list[float]


def validate(p: StartupInputs) -> None:
    get_sector(p.sector)
    check(bool(str(p.name).strip()), "startup name is required")
    check(isinstance(p.months, int) and 12 <= p.months <= 120, "months must be a whole number, 12-120")
    for label, v, lo, hi in (
        ("starting customers", p.starting_customers, 0, None),
        ("new customers", p.new_customers, 0, None),
        ("new-customer growth", p.new_customer_growth, -0.5, 1),
        ("ARPU", p.arpu, 0, None),
        ("ARPU growth", p.arpu_growth, -0.5, 2),
        ("churn", p.churn, 0, 1),
        ("gross margin", p.gross_margin, -1, 1),
        ("CAC", p.cac, 0, None),
        ("fixed costs", p.fixed_costs, 0, None),
        ("fixed-cost growth", p.fixed_cost_growth, -0.5, 1),
        ("cash", p.cash, 0, None),
        ("raise amount", p.raise_amount, 0, None),
        ("target return", p.target_return, 1, 100),
    ):
        number(label, v, lo, hi)
    for f in p.funding:
        check(isinstance(f, dict) and "month" in f and "amount" in f, "each funding round needs a month and an amount")
        number("funding month", f["month"], 1, p.months)
        number("funding amount", f["amount"], 0)


def simulate(p: StartupInputs) -> Monthly:
    rounds: dict[int, float] = {}
    for f in p.funding:
        rounds[int(f["month"])] = rounds.get(int(f["month"]), 0.0) + float(f["amount"])
    m = Monthly([], [], [], [], [], [], [], [], [], [], [])
    customers, cash = p.starting_customers, p.cash
    for t in range(1, p.months + 1):
        new = p.new_customers * (1 + p.new_customer_growth) ** (t - 1)
        churned = customers * p.churn
        customers = customers + new - churned
        arpu = p.arpu * (1 + p.arpu_growth) ** ((t - 1) // 12)
        mrr = customers * arpu
        gp = mrr * p.gross_margin
        mkt = new * p.cac
        fixed = p.fixed_costs * (1 + p.fixed_cost_growth) ** (t - 1)
        ebitda = gp - mkt - fixed
        inflow = rounds.get(t, 0.0)
        cash += ebitda + inflow
        for lst, v in (
            (m.month, t),
            (m.customers, customers),
            (m.new, new),
            (m.churned, churned),
            (m.mrr, mrr),
            (m.gross_profit, gp),
            (m.marketing, mkt),
            (m.fixed, fixed),
            (m.ebitda, ebitda),
            (m.funding, inflow),
            (m.cash, cash),
        ):
            lst.append(v)  # type: ignore[attr-defined]
    return m


def analyse_inputs(data: dict[str, Any]) -> Report:
    return analyse(from_dict(StartupInputs, data))


def analyse(p: StartupInputs) -> Report:
    validate(p)
    sector = get_sector(p.sector)
    m = simulate(p)
    cur, unit = p.currency, p.unit
    n = p.months
    cash_out = next((t for t, c in zip(m.month, m.cash) if c < 0), None)
    breakeven = next((t for t in m.month if all(e > 0 for e in m.ebitda[t - 1 :])), None)
    min_cash = min(m.cash)
    funding_gap = -min_cash if min_cash < 0 else 0.0
    burn_now = -m.ebitda[0] if m.ebitda[0] < 0 else 0.0
    runway = cash_out - 1 if cash_out else None

    ltv = (p.arpu * p.gross_margin / p.churn) if p.churn > 0 else float("inf")
    ltv_cac = ltv / p.cac if p.cac > 0 else float("inf")
    payback = p.cac / (p.arpu * p.gross_margin) if p.arpu * p.gross_margin > 0 else None
    arr_end = m.mrr[-1] * 12
    yr = min(12, n)
    net_new_arr = (m.mrr[yr - 1] - p.starting_customers * p.arpu) * 12  # ARR built in year 1
    burn_y1 = -sum(e for e in m.ebitda[:yr] if e < 0)
    burn_multiple = burn_y1 / net_new_arr if net_new_arr > 0 else None
    growth_last = (m.mrr[-1] / m.mrr[-13] - 1) if n >= 24 and m.mrr[-13] > 0 else None
    margin_last = sum(m.ebitda[-12:]) / (sum(m.mrr[-12:]) or 1)
    rule40 = (growth_last + margin_last) if growth_last is not None else None

    lo, mid, hi = sector.arr_multiple
    mult = p.exit_multiple or mid
    exit_value = arr_end * mult
    post_money = exit_value / p.target_return
    pre_money = post_money - p.raise_amount if p.raise_amount else None
    dilution = p.raise_amount / post_money if p.raise_amount and post_money > 0 else None

    # Fundraising plan: cover the gap to break-even plus 6 months of buffer, or 24 months of burn
    if breakeven:
        need = funding_gap + 6 * max(burn_now, 0.0)
    else:
        need = max(funding_gap, 0.0) + 24 * max(-m.ebitda[-1], burn_now)
    raise_by = max((cash_out or n) - 6, 1) if cash_out else None

    suggestions = _suggest(
        p,
        m,
        runway,
        breakeven,
        ltv_cac,
        payback,
        burn_multiple,
        funding_gap,
        need,
        raise_by,
        post_money,
        dilution,
        rule40,
    )
    if runway is None and breakeven:
        verdict, tone = "FUNDED TO BREAK-EVEN", "good"
    elif runway is not None and runway >= 12:
        verdict, tone = "RAISE WITHIN 6-9 MONTHS", "warn"
    elif runway is not None:
        verdict, tone = "RAISE NOW", "bad"
    else:
        verdict, tone = "FUNDED FOR THE PLAN", "good"
    note = (
        f"Runway {'covers the full plan' if runway is None else f'{runway} months'} · "
        f"break-even {'month ' + str(breakeven) if breakeven else 'not within the plan'} · "
        f"LTV/CAC {ltv_cac:.1f}x"
    )

    tiles = [
        Tile("Ending ARR", arr_end, note=f"month {n}"),
        Tile("Customers", m.customers[-1], "int", note=f"month {n}"),
        Tile(
            "Runway",
            runway if runway is not None else "Full plan",
            "int" if runway is not None else "text",
            note="months of cash",
            tone="bad" if runway is not None and runway < 12 else "good",
        ),
        Tile(
            "Break-even month",
            breakeven if breakeven else "Not reached",
            "int" if breakeven else "text",
            tone="good" if breakeven else "warn",
        ),
        Tile(
            "Funding gap", funding_gap, tone="bad" if funding_gap > 0 else "good", note="cash needed to stay positive"
        ),
        Tile("LTV / CAC", ltv_cac, "x", tone="good" if ltv_cac >= 3 else "bad"),
        Tile("CAC payback", payback, "num", note="months"),
        Tile(
            "Burn multiple",
            burn_multiple,
            "x",
            note="year-1 burn / ARR added",
            tone="good" if burn_multiple is not None and burn_multiple <= 1.5 else "warn",
        ),
        Tile("Post-money (VC method)", post_money, note=f"{mult:.1f}x exit ARR ÷ {p.target_return:.0f}x"),
        Tile("Suggested raise", need, note=f"by month {raise_by}" if raise_by else "buffer + growth"),
    ]
    labels = [f"M{t}" for t in m.month]
    charts = [
        Chart(
            "Monthly recurring revenue and burn",
            "line",
            labels=labels,
            series={"MRR": m.mrr, "EBITDA": m.ebitda},
            marker=0.0,
            marker_label="Break-even",
        ),
        Chart(
            "Cash balance (runway)", "line", labels=labels, series={"Cash": m.cash}, marker=0.0, marker_label="Cash out"
        ),
        Chart(
            "Customers",
            "bars",
            labels=labels[::3],
            fmt="int",
            series={"Customers": m.customers[::3], "New": m.new[::3]},
        ),
        Chart(
            "Where the money goes (whole plan)",
            "donut",
            labels=["Cost of revenue", "Marketing (CAC)", "Team & overheads"],
            series={"value": [sum(m.mrr) - sum(m.gross_profit), sum(m.marketing), sum(m.fixed)]},
        ),
    ]
    years = (n + 11) // 12
    ycols = ["", *[f"Year {y + 1}" for y in range(years)]]

    def by_year(xs: list[float], how: str = "sum") -> list[float]:
        out = []
        for y in range(years):
            chunk = xs[y * 12 : (y + 1) * 12]
            out.append(sum(chunk) if how == "sum" else chunk[-1])
        return out

    annual = [
        ["Revenue", *by_year(m.mrr)],
        ["Gross profit", *by_year(m.gross_profit)],
        ["Marketing", *[-x for x in by_year(m.marketing)]],
        ["Team & overheads", *[-x for x in by_year(m.fixed)]],
        ["EBITDA", *by_year(m.ebitda)],
        ["Funding raised", *by_year(m.funding)],
        ["Closing cash", *by_year(m.cash, "last")],
        ["Customers (year end)", *by_year(m.customers, "last")],
        ["ARR (year end)", *[x * 12 for x in by_year(m.mrr, "last")]],
    ]
    mcols = ["", *labels]
    monthly = [
        ["Customers", *m.customers],
        ["New customers", *m.new],
        ["Churned", *m.churned],
        ["MRR", *m.mrr],
        ["Gross profit", *m.gross_profit],
        ["Marketing", *[-x for x in m.marketing]],
        ["Team & overheads", *[-x for x in m.fixed]],
        ["EBITDA", *m.ebitda],
        ["Funding", *m.funding],
        ["Cash", *m.cash],
    ]
    tables = [
        Table("Annual summary", ycols, annual, ["money"] * 7 + ["int", "money"]),
        Table(
            "Unit economics",
            ["", "Value"],
            [
                ["ARPU (monthly)", p.arpu],
                ["Gross margin", p.gross_margin],
                ["Monthly churn", p.churn],
                ["Customer lifetime (months)", 1 / p.churn if p.churn else None],
                ["LTV", ltv],
                ["CAC", p.cac],
                ["LTV / CAC", ltv_cac],
                ["CAC payback (months)", payback],
            ],
            ["money", "pct", "pct", "num", "money", "money", "x", "num"],
        ),
        Table(
            "Valuation (VC method)",
            ["", "Value"],
            [
                ["ARR at exit (end of plan)", arr_end],
                ["Exit ARR multiple", mult],
                ["Exit value", exit_value],
                ["Target return", p.target_return],
                ["Post-money today", post_money],
                ["Round size", p.raise_amount or None],
                ["Pre-money today", pre_money],
                ["Dilution", dilution],
            ],
            ["money", "x", "money", "x", "money", "money", "money", "pct"],
        ),
        Table("Monthly model", mcols, monthly, ["int", "int", "int"] + ["money"] * 7),
    ]
    assumptions = [
        ["Sector", sector.name, "text"],
        ["Months", n, "int"],
        ["New customers (month 1)", p.new_customers, "int"],
        ["New-customer growth / month", p.new_customer_growth, "pct"],
        ["ARPU / month", p.arpu, "money"],
        ["Churn / month", p.churn, "pct"],
        ["Gross margin", p.gross_margin, "pct"],
        ["CAC", p.cac, "money"],
        ["Fixed costs / month", p.fixed_costs, "money"],
        ["Starting cash", p.cash, "money"],
    ]
    return Report(
        kind="startup",
        title=p.name,
        subtitle=f"Startup model · {sector.name} · {n} months · {cur} {unit}",
        currency=cur,
        unit=unit,
        verdict=verdict,
        verdict_tone=tone,
        verdict_note=note,
        tiles=tiles,
        charts=charts,
        tables=tables,
        suggestions=suggestions,
        assumptions=assumptions,
        data={
            "runway": runway,
            "breakeven": breakeven,
            "arr_end": arr_end,
            "post_money": post_money,
            "ltv_cac": ltv_cac,
            "funding_gap": funding_gap,
            "suggested_raise": need,
        },
    )


def _suggest(
    p: StartupInputs,
    m: Monthly,
    runway: int | None,
    breakeven: int | None,
    ltv_cac: float,
    payback: float | None,
    burn_multiple: float | None,
    gap: float,
    need: float,
    raise_by: int | None,
    post: float,
    dilution: float | None,
    rule40: float | None,
) -> list[Suggestion]:
    out: list[Suggestion] = []
    cur, unit = p.currency, p.unit
    if runway is not None:
        out.append(
            Suggestion(
                "high" if runway < 12 else "medium",
                "Fundraising",
                f"Cash runs out in month {runway + 1}",
                f"Raise about {cur}{need:,.0f} {unit}, closing by month {raise_by}: fundraises take 4-6 months.",
                [
                    "Prepare the data room and metrics pack now",
                    "Line up bridge financing from existing investors",
                    "Model a lean case that reaches break-even on current cash",
                ],
            )
        )
    if ltv_cac < 3:
        out.append(
            Suggestion(
                "high" if ltv_cac < 1 else "medium",
                "Unit economics",
                f"LTV/CAC is {ltv_cac:.1f}x, under the 3x benchmark",
                "Each customer returns too little of what it costs to acquire; growth burns cash.",
                [
                    "Cut the most expensive acquisition channels",
                    "Raise prices or add an upsell tier",
                    "Attack churn: onboarding, success team, annual plans",
                ],
            )
        )
    if payback is not None and payback > 12:
        out.append(
            Suggestion(
                "medium",
                "Unit economics",
                f"CAC payback is {payback:.0f} months",
                "Investors look for under 12 months (under 18 for enterprise sales).",
                ["Annual prepaid plans shorten payback immediately"],
            )
        )
    if p.churn > 0.03:
        out.append(
            Suggestion(
                "medium",
                "Retention",
                f"Monthly churn of {p.churn:.1%} loses {1 - (1 - p.churn) ** 12:.0%} of customers a year",
                "High churn caps growth: you refill a leaking bucket.",
                ["Interview churned customers", "Usage-based health scores"],
            )
        )
    if burn_multiple is not None and burn_multiple > 2:
        out.append(
            Suggestion(
                "medium",
                "Efficiency",
                f"Burn multiple of {burn_multiple:.1f}x is high",
                "You burn over 2 of currency for each 1 of new ARR; investors prefer under 1.5x.",
                ["Slow hiring until ARR per head improves", "Shift budget to the best-converting channel"],
            )
        )
    if breakeven:
        out.append(
            Suggestion(
                "low",
                "Profitability",
                f"Break-even in month {breakeven}",
                "Being on a path to profitability strengthens your negotiating position in any round.",
                ["Track contribution margin monthly against this plan"],
            )
        )
    else:
        out.append(
            Suggestion(
                "medium",
                "Profitability",
                "No break-even within the plan",
                "The model still burns cash at the end of the horizon.",
                ["Find the price, churn or CAC that reaches break-even (try them in the form)"],
            )
        )
    if rule40 is not None:
        out.append(
            Suggestion(
                "low" if rule40 >= 0.4 else "medium",
                "Investor metrics",
                f"Rule of 40 in the final year: {rule40:.0%}",
                "Growth plus EBITDA margin; 40%+ signals a fundable, efficient business.",
                [],
            )
        )
    if dilution is not None:
        out.append(
            Suggestion(
                "low",
                "Valuation",
                f"This round dilutes founders by about {dilution:.0%}",
                f"At a VC-method post-money of {cur}{post:,.0f} {unit}. Aim for 15-25% per round.",
                ["Raise only what reaches the next value milestone", "Benchmark against recent comparable rounds"],
            )
        )
    return sort_suggestions(out)
