"""Deal-desk analytics for the company model.

* Scenario analysis: bear / base / bull cases and a probability-weighted value
* Monte Carlo: distribution of equity value (P10-P90) and the chance the market price is exceeded
* Reverse DCF: the revenue growth the current market value implies
* Detailed LBO: sources & uses, senior amortising + junior bullet debt, cash sweep, credit
  statistics by year, entry x exit multiple IRR grid and returns attribution
* Credit profile with an indicative rating band (rule of thumb, not an agency rating)
* Executive summary: an auto-written investment thesis
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from invesha.core import Bar, Chart, InputError, Report, Suggestion, Table, Tile, irr, solve, sort_suggestions

if TYPE_CHECKING:
    from invesha.corporate import CompanyInputs, Dcf, Projection, Wacc
    from invesha.sectors import Sector


# ---------------------------------------------------------------- shared valuation helper


def equity_value(
    p: CompanyInputs, sector: Sector, wacc_shift: float = 0.0, exit_mult: float | None = None, g: float | None = None
) -> float:
    """Blended (perpetuity + exit multiple) DCF equity value for a set of inputs."""
    from invesha.corporate import dcf, project, wacc

    proj = project(p)
    rate = wacc(p, sector).wacc + wacc_shift
    d = dcf(proj, rate, p.terminal_growth if g is None else g, exit_mult or p.exit_multiple or sector.ev_ebitda[1])
    return d.ev - (p.debt - p.cash)


def _shift_growth(p: CompanyInputs, delta: float) -> CompanyInputs:
    if p.growth:
        return replace(p, growth=[x + delta for x in p.growth])
    return replace(p, growth_start=p.growth_start + delta, growth_end=p.growth_end + delta)


def _shift_margin(p: CompanyInputs, delta: float) -> CompanyInputs:
    target = p.ebitda_margin if p.margin_target is None else p.margin_target
    return replace(p, margin_target=target + delta)


# ---------------------------------------------------------------- scenarios


@dataclass
class Case:
    name: str
    probability: float
    growth_y1: float
    final_margin: float
    wacc: float
    exit_multiple: float
    ev: float
    equity: float


def scenarios(p: CompanyInputs, sector: Sector) -> list[Case]:
    from invesha.corporate import dcf, project, wacc

    base_mult = p.exit_multiple or sector.ev_ebitda[1]
    pb, pu = p.bear_probability, p.bull_probability
    specs = [
        ("Bear", pb, -0.04, -0.03, 0.01, -1.5),
        ("Base", 1 - pb - pu, 0, 0, 0, 0),
        ("Bull", pu, 0.04, 0.03, -0.01, 1.5),
    ]
    out = []
    for name, prob, dg, dm, dw, dx in specs:
        q = _shift_margin(_shift_growth(p, dg), dm)
        proj = project(q)
        rate = wacc(q, sector).wacc + dw
        mult = max(base_mult + dx, 1.0)
        try:
            d = dcf(proj, rate, p.terminal_growth, mult)
        except InputError:
            d = dcf(proj, rate, min(p.terminal_growth, rate - 0.01), mult)
        out.append(Case(name, prob, proj.growth[0], proj.margin[-1], rate, mult, d.ev, d.ev - (p.debt - p.cash)))
    return out


# ---------------------------------------------------------------- Monte Carlo


@dataclass
class MonteCarlo:
    runs: int
    values: list[float]
    mean: float
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    prob_above: float | None
    bins: list[str] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)


def _quantile(sorted_vals: list[float], q: float) -> float:
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def monte_carlo(p: CompanyInputs, sector: Sector, benchmark: float | None, seed: int = 7) -> MonteCarlo:
    """Triangular draws on growth (±5pts), margin (±3pts), WACC (±1.5pts), terminal growth (±1pt), exit multiple (±20%)."""
    from invesha.corporate import dcf, project, wacc

    rng = random.Random(seed)
    base_rate = wacc(p, sector).wacc
    base_mult = p.exit_multiple or sector.ev_ebitda[1]
    net_debt = p.debt - p.cash
    runs = max(200, min(int(p.simulations), 20000))
    vals: list[float] = []
    for _ in range(runs):
        q = _shift_margin(_shift_growth(p, rng.triangular(-0.05, 0.05, 0)), rng.triangular(-0.03, 0.03, 0))
        rate = base_rate + rng.triangular(-0.015, 0.015, 0)
        g = min(p.terminal_growth + rng.triangular(-0.01, 0.01, 0), rate - 0.01)
        mult = base_mult * rng.triangular(0.8, 1.2, 1.0)
        d = dcf(project(q), rate, g, mult)
        v = d.ev - net_debt
        vals.append(v / p.shares if p.shares else v)
    s = sorted(vals)
    lo, hi = s[int(0.01 * runs)], s[int(0.99 * runs) - 1]
    nb = 20
    width = (hi - lo) / nb or 1.0
    counts = [0] * nb
    for v in vals:
        if lo <= v <= hi:
            counts[min(int((v - lo) / width), nb - 1)] += 1
    bins = [f"{lo + width * (i + 0.5):,.0f}" for i in range(nb)]
    prob = sum(1 for v in vals if v > benchmark) / runs if benchmark else None
    return MonteCarlo(
        runs,
        vals,
        sum(vals) / runs,
        _quantile(s, 0.1),
        _quantile(s, 0.25),
        _quantile(s, 0.5),
        _quantile(s, 0.75),
        _quantile(s, 0.9),
        prob,
        bins,
        counts,
    )


# ---------------------------------------------------------------- reverse DCF


def reverse_dcf(p: CompanyInputs, sector: Sector, target_equity: float) -> dict[str, float] | None:
    """Uniform shift to the growth path that makes blended DCF equity equal the market value."""
    from invesha.corporate import project

    def f(delta: float) -> float:
        try:
            return equity_value(_shift_growth(p, delta), sector)
        except InputError:
            return float("nan")

    delta = solve(f, target_equity, -0.35, 0.8, tol=1e-5)
    if delta is None:
        return None
    implied = project(_shift_growth(p, delta))
    plan = project(p)
    cagr = (implied.revenue[-1] / p.revenue) ** (1 / p.years) - 1
    plan_cagr = (plan.revenue[-1] / p.revenue) ** (1 / p.years) - 1
    return {"delta": delta, "implied_y1": implied.growth[0], "implied_cagr": cagr, "plan_cagr": plan_cagr}


# ---------------------------------------------------------------- detailed LBO


@dataclass
class LboDetail:
    entry_multiple: float
    exit_multiple: float
    entry_ebitda: float
    entry_ev: float
    fees: float
    senior: float
    junior: float
    equity: float
    years: list[str]
    ebitda: list[float]
    interest: list[float]
    fcf: list[float]
    senior_bal: list[float]
    junior_bal: list[float]
    cash: list[float]
    leverage: list[float]
    coverage: list[float]
    exit_ev: float
    exit_debt: float
    exit_cash: float
    exit_equity: float
    irr: float | None
    moic: float
    attribution: dict[str, float]


def lbo_model(
    p: CompanyInputs,
    proj: Projection,
    sector: Sector,
    entry_multiple: float | None = None,
    exit_multiple: float | None = None,
) -> LboDetail | None:
    ltm = p.revenue * p.ebitda_margin
    if ltm <= 0:
        return None
    m0 = entry_multiple or p.lbo_entry_multiple or sector.ev_ebitda[1]
    m1 = exit_multiple or p.exit_multiple or m0
    ev = m0 * ltm
    fees = 0.02 * ev
    debt = min(p.lbo_leverage * ltm, 0.75 * ev)
    senior, junior = 0.7 * debt, 0.3 * debt
    equity = ev + fees - debt
    r_sen, r_jun = p.lbo_interest_rate, p.lbo_interest_rate + 0.03
    amort = 0.05 * senior
    s_bal, j_bal, cash = senior, junior, 0.0
    out: dict[str, list[float]] = {k: [] for k in ("interest", "fcf", "senior", "junior", "cash", "lev", "cov")}
    for i in range(len(proj.revenue)):
        interest = s_bal * r_sen + j_bal * r_jun
        tax = max(proj.ebit[i] - interest, 0.0) * p.tax_rate
        fcf = proj.ebitda[i] - interest - tax - proj.capex[i] - proj.delta_nwc[i]
        mandatory = min(amort, s_bal)
        s_bal -= mandatory
        available = fcf - mandatory
        sweep = max(available, 0.0) * 0.75
        pay_s = min(sweep, s_bal)
        s_bal -= pay_s
        pay_j = min(sweep - pay_s, j_bal)
        j_bal -= pay_j
        cash += available - pay_s - pay_j
        out["interest"].append(interest)
        out["fcf"].append(fcf)
        out["senior"].append(s_bal)
        out["junior"].append(j_bal)
        out["cash"].append(cash)
        out["lev"].append((s_bal + j_bal - cash) / proj.ebitda[i] if proj.ebitda[i] > 0 else float("nan"))
        out["cov"].append(proj.ebitda[i] / interest if interest > 0 else float("nan"))
    e_n = proj.ebitda[-1]
    exit_ev = m1 * e_n
    exit_debt = s_bal + j_bal
    exit_equity = max(exit_ev - exit_debt + cash, 0.0)
    flows = [-equity] + [0.0] * (len(proj.revenue) - 1) + [exit_equity]
    attribution = {
        "Equity invested": equity,
        "EBITDA growth": (e_n - ltm) * m0,
        "Multiple change": (m1 - m0) * e_n,
        "Debt paydown & cash": debt - exit_debt + cash,
        "Fees": -fees,
    }
    return LboDetail(
        m0,
        m1,
        ltm,
        ev,
        fees,
        senior,
        junior,
        equity,
        proj.years,
        proj.ebitda,
        out["interest"],
        out["fcf"],
        out["senior"],
        out["junior"],
        out["cash"],
        out["lev"],
        out["cov"],
        exit_ev,
        exit_debt,
        cash,
        exit_equity,
        irr(flows),
        exit_equity / equity if equity else 0.0,
        attribution,
    )


# ---------------------------------------------------------------- credit


def credit_profile(p: CompanyInputs, proj: Projection) -> dict[str, Any]:
    ebitda = p.revenue * p.ebitda_margin
    net_debt = p.debt - p.cash
    interest = p.debt * p.interest_rate
    lev = net_debt / ebitda if ebitda > 0 else float("inf")
    cover = ebitda / interest if interest > 0 else float("inf")
    ffo = proj.net_income[0] + proj.da[0]
    ffo_debt = ffo / p.debt if p.debt > 0 else float("inf")
    if lev <= 1.0 and cover >= 12:
        band = "AA / A"
    elif lev <= 2.0 and cover >= 8:
        band = "A / BBB"
    elif lev <= 3.0 and cover >= 5:
        band = "BBB / BB"
    elif lev <= 4.5 and cover >= 3:
        band = "BB / B"
    else:
        band = "B- or below"
    return {
        "leverage": lev,
        "coverage": cover,
        "ffo_debt": ffo_debt,
        "band": band,
        "investment_grade": band in ("AA / A", "A / BBB"),
    }


# ---------------------------------------------------------------- enrich the report


def enrich(
    report: Report,
    p: CompanyInputs,
    sector: Sector,
    proj: Projection,
    w: Wacc,
    d: Dcf,
    comps: list[tuple[str, float, float, float]],
    net_debt: float,
    mcap: float | None,
) -> Report:
    cur, unit = p.currency, p.unit
    per = (lambda v: v / p.shares) if p.shares else (lambda v: v)
    label = "per share" if p.shares else "equity value"
    benchmark = (p.share_price if p.shares else mcap) if mcap else None

    cases = scenarios(p, sector)
    weighted = sum(c.probability * c.equity for c in cases)
    mc = monte_carlo(p, sector, benchmark)
    rev = reverse_dcf(p, sector, mcap) if mcap else None
    deal = lbo_model(p, proj, sector)
    credit = credit_profile(p, proj)

    # ---- tiles
    extra = [
        Tile(
            "Probability-weighted value",
            per(weighted),
            note=f"{label}; bear/base/bull " + "/".join(f"{c.probability:.0%}" for c in cases),
        )
    ]
    extra.append(
        Tile(
            "Monte Carlo P10–P90",
            f"{cur}{mc.p10:,.0f} – {cur}{mc.p90:,.0f}",
            "text",
            note=f"median {cur}{mc.p50:,.0f} · {mc.runs:,} runs",
        )
    )
    if mc.prob_above is not None:
        extra.append(
            Tile(
                "Probability value > price",
                mc.prob_above,
                "pct",
                tone="good" if mc.prob_above >= 0.6 else "bad" if mc.prob_above < 0.4 else "warn",
            )
        )
    if rev:
        extra.append(
            Tile(
                "Market-implied growth",
                rev["implied_cagr"],
                "pct",
                note=f"vs plan {rev['plan_cagr']:.1%} revenue CAGR",
                tone="good" if rev["implied_cagr"] < rev["plan_cagr"] else "warn",
            )
        )
    extra.append(
        Tile(
            "Indicative credit band",
            credit["band"],
            "text",
            note=f"{credit['leverage']:.1f}x net debt/EBITDA · {credit['coverage']:.1f}x cover"
            if credit["leverage"] != float("inf")
            else "no EBITDA",
        )
    )
    report.tiles = [t for t in report.tiles if t.label != "LBO IRR"] + extra
    if deal:
        report.tiles.append(
            Tile(
                "LBO IRR",
                deal.irr,
                "pct",
                note=f"{deal.moic:.1f}x MOIC · {deal.entry_multiple:.1f}x in / {deal.exit_multiple:.1f}x out",
                tone="good" if (deal.irr or 0) >= 0.2 else "warn",
            )
        )

    # ---- charts
    charts = [
        Chart(
            "Scenario analysis (" + label + ")",
            "bars",
            labels=[c.name for c in cases] + ["Weighted"],
            series={label.capitalize(): [per(c.equity) for c in cases] + [per(weighted)]},
        ),
        Chart(
            f"Monte Carlo: {mc.runs:,} simulated valuations ({label})",
            "bars",
            labels=mc.bins,
            fmt="int",
            series={"Simulations": [float(c) for c in mc.counts]},
        ),
    ]
    if deal:
        charts.append(
            Chart(
                "LBO value creation (sponsor equity)",
                "waterfall",
                fmt="money",
                labels=["Equity in", "EBITDA growth", "Multiple", "Paydown & cash", "Fees", "Equity out"],
                series={"value": [*deal.attribution.values(), deal.exit_equity]},
            )
        )
        charts.append(
            Chart(
                "LBO credit statistics",
                "line",
                fmt="x",
                labels=deal.years,
                series={"Net debt / EBITDA": deal.leverage, "EBITDA / interest": deal.coverage},
            )
        )
    ff = [c for c in report.charts if c.title.startswith("Valuation football")]
    report.charts = ff + charts + [c for c in report.charts if not c.title.startswith("Valuation football")]
    if ff:
        ff[0].bars.insert(
            0, Bar("Monte Carlo P10–P90", mc.p10 * (p.shares or 1), mc.p90 * (p.shares or 1), mc.p50 * (p.shares or 1))
        )
        ff[0].bars.insert(1, Bar("Scenarios (bear–bull)", cases[0].equity, cases[2].equity, cases[1].equity))
        if deal:
            for b in ff[0].bars:
                if b.label.startswith("LBO"):
                    b.low, b.high = deal.entry_ev - net_debt, deal.entry_ev - net_debt
                    b.label = "LBO entry (sponsor bid)"
                    lo_m, hi_m = deal.entry_multiple - 1, deal.entry_multiple + 1
                    b.low, b.high, b.mid = (
                        lo_m * deal.entry_ebitda - net_debt,
                        hi_m * deal.entry_ebitda - net_debt,
                        deal.entry_ev - net_debt,
                    )

    # ---- tables
    tables = [
        Table(
            "Scenario analysis",
            ["", *[c.name for c in cases]],
            [
                ["Probability", *[c.probability for c in cases]],
                ["Revenue growth, year 1", *[c.growth_y1 for c in cases]],
                ["EBITDA margin, final year", *[c.final_margin for c in cases]],
                ["WACC", *[c.wacc for c in cases]],
                ["Exit EV / EBITDA", *[c.exit_multiple for c in cases]],
                ["Enterprise value", *[c.ev for c in cases]],
                ["Equity value", *[c.equity for c in cases]],
                *([["Value per share", *[c.equity / p.shares for c in cases]]] if p.shares else []),
            ],
            ["pct", "pct", "pct", "pct", "x", "money", "money", "money"],
            note=f"Probability-weighted equity value: {cur}{weighted:,.0f} {unit}. Bear/bull move growth ±4pts, "
            "margin ±3pts, WACC ∓1pt, exit multiple ±1.5x.",
        ),
        Table(
            "Monte Carlo simulation",
            ["", "Value"],
            [
                ["Runs", mc.runs],
                ["Mean", mc.mean],
                ["P10", mc.p10],
                ["P25", mc.p25],
                ["Median (P50)", mc.p50],
                ["P75", mc.p75],
                ["P90", mc.p90],
                *([["Probability value exceeds market", mc.prob_above]] if mc.prob_above is not None else []),
            ],
            ["int", "money", "money", "money", "money", "money", "money", "pct"],
            note=f"Values are {label}. Triangular draws: growth ±5pts, margin ±3pts, WACC ±1.5pts, terminal growth "
            "±1pt, exit multiple ±20%. Seeded, so results are reproducible.",
        ),
    ]
    if rev:
        tables.append(
            Table(
                "Reverse DCF: what the market price implies",
                ["", "Value"],
                [
                    ["Market capitalisation", mcap],
                    ["Implied revenue growth, year 1", rev["implied_y1"]],
                    ["Implied revenue CAGR", rev["implied_cagr"]],
                    ["Plan revenue CAGR", rev["plan_cagr"]],
                    ["Gap (implied − plan)", rev["implied_cagr"] - rev["plan_cagr"]],
                ],
                ["money", "pct", "pct", "pct", "pct"],
                note="Shifts the whole growth path until the blended DCF equity value equals the market value.",
            )
        )
    if deal:
        tables += [
            Table(
                "LBO sources and uses",
                ["Sources", "Amount", "Uses", "Amount"],
                [
                    ["Senior term loan", deal.senior, "Purchase enterprise value", deal.entry_ev],
                    ["Junior / mezzanine debt", deal.junior, "Transaction fees (2%)", deal.fees],
                    ["Sponsor equity", deal.equity, "", None],
                    ["Total sources", deal.senior + deal.junior + deal.equity, "Total uses", deal.entry_ev + deal.fees],
                ],
                ["text", "money", "text", "money"],
                by_column=True,
                note=f"Entry at {deal.entry_multiple:.1f}x LTM EBITDA of {cur}{deal.entry_ebitda:,.1f}; total debt "
                f"{(deal.senior + deal.junior) / deal.entry_ebitda:.1f}x.",
            ),
            Table(
                "LBO debt schedule and credit statistics",
                ["", *deal.years],
                [
                    ["EBITDA", *deal.ebitda],
                    ["Interest", *deal.interest],
                    ["Levered free cash flow", *deal.fcf],
                    ["Senior debt (closing)", *deal.senior_bal],
                    ["Junior debt (closing)", *deal.junior_bal],
                    ["Cash (closing)", *deal.cash],
                    ["Net debt / EBITDA", *deal.leverage],
                    ["EBITDA / interest", *deal.coverage],
                ],
                ["money"] * 6 + ["x", "x"],
                note="Senior amortises 5% a year; 75% of excess cash sweeps senior then junior; junior is bullet at "
                f"{p.lbo_interest_rate + 0.03:.1%}.",
            ),
        ]
        entry = [deal.entry_multiple + s for s in (-2, -1, 0, 1, 2)]
        exits = [deal.exit_multiple + s for s in (-2, -1, 0, 1, 2)]
        grid = []
        for m0 in entry:
            row: list[Any] = [m0]
            for m1 in exits:
                r = lbo_model(p, proj, sector, m0, m1) if m0 > 1 and m1 > 1 else None
                row.append(r.irr if r else None)
            grid.append(row)
        tables.append(
            Table(
                "LBO IRR sensitivity: entry multiple (rows) × exit multiple (columns)",
                ["Entry \\ exit", *[f"{m:.1f}x" for m in exits]],
                grid,
                ["x"] + ["pct"] * 5,
                by_column=True,
                note="Sponsor IRR; centre cell is the base case. Most funds target 20-25%.",
            )
        )
    tables.append(
        Table(
            "Credit profile",
            ["", "Value"],
            [
                ["Net debt / EBITDA", credit["leverage"]],
                ["EBITDA / interest", credit["coverage"]],
                ["FFO / debt", credit["ffo_debt"]],
                ["Indicative rating band", credit["band"]],
            ],
            ["x", "x", "pct", "text"],
            note="Indicative band from leverage and coverage rules of thumb; not an agency rating.",
        )
    )
    report.tables = [t for t in report.tables if t.title != "LBO returns"] + tables

    # ---- suggestions
    more: list[Suggestion] = []
    if rev:
        gap = rev["implied_cagr"] - rev["plan_cagr"]
        if gap > 0.03:
            more.append(
                Suggestion(
                    "high",
                    "Reverse DCF",
                    f"The price implies {rev['implied_cagr']:.1%} growth vs a {rev['plan_cagr']:.1%} plan",
                    "The market already expects more than the plan delivers; upside needs a beat.",
                    [
                        "Identify catalysts that could lift growth above the market's expectation",
                        "Size the downside if growth reverts to plan",
                    ],
                )
            )
        elif gap < -0.03:
            more.append(
                Suggestion(
                    "medium",
                    "Reverse DCF",
                    f"The price implies only {rev['implied_cagr']:.1%} growth vs a {rev['plan_cagr']:.1%} plan",
                    "The market is sceptical of the plan; credible delivery would re-rate the shares.",
                    ["Test what the market doubts: margins, capacity, demand", "Use the gap as an entry argument"],
                )
            )
    if mc.prob_above is not None:
        more.append(
            Suggestion(
                "medium" if mc.prob_above < 0.5 else "low",
                "Risk",
                f"{mc.prob_above:.0%} of simulations value the company above the market price",
                f"P10–P90 range {cur}{mc.p10:,.0f}–{cur}{mc.p90:,.0f} ({label}); the spread shows how much the answer "
                "depends on assumptions.",
                ["Size positions to the P10 outcome, not the median"],
            )
        )
    if deal:
        att = deal.attribution
        created = sum(v for k, v in att.items() if k not in ("Equity invested", "Fees"))
        if created > 0 and att["Multiple change"] / created > 0.4:
            more.append(
                Suggestion(
                    "medium",
                    "LBO",
                    f"{att['Multiple change'] / created:.0%} of sponsor value relies on multiple expansion",
                    "Returns that depend on selling at a higher multiple are fragile.",
                    ["Underwrite at exit = entry multiple", "Find operational levers for EBITDA growth"],
                )
            )
        if deal.leverage and deal.leverage[0] == deal.leverage[0] and deal.leverage[0] > 5:
            more.append(
                Suggestion(
                    "medium",
                    "LBO",
                    f"Year-1 leverage of {deal.leverage[0]:.1f}x is aggressive",
                    "Lenders typically cap senior leverage around 4-5x for mid-market buyouts.",
                    ["Reduce debt or add more equity"],
                )
            )
    if not credit["investment_grade"] and credit["leverage"] != float("inf") and credit["leverage"] > 0:
        more.append(
            Suggestion(
                "low",
                "Credit",
                f"Indicative credit band {credit['band']}",
                "Below investment grade raises the cost of debt and limits access to bond markets.",
                ["Deleverage below 2x to approach investment grade"],
            )
        )
    report.suggestions = sort_suggestions(report.suggestions + more)

    # ---- executive summary
    s: list[str] = []
    fair = report.data["fair_mid"]
    if report.verdict in ("BUY", "HOLD", "REDUCE"):
        s.append(
            f"{report.verdict}: blended fair equity value {cur}{fair:,.0f} {unit} vs market capitalisation "
            f"{cur}{mcap:,.0f} {unit} ({report.data['upside']:+.0%})."
        )
    else:
        s.append(
            f"Blended fair equity value {cur}{fair:,.0f} {unit} from DCF (perpetuity and exit) and trading comparables."
        )
    s.append(
        f"Probability-weighted value {cur}{per(weighted):,.0f} ({label}); bear {cur}{per(cases[0].equity):,.0f}, "
        f"bull {cur}{per(cases[2].equity):,.0f}."
    )
    s.append(
        f"Monte Carlo P10–P90 {cur}{mc.p10:,.0f}–{cur}{mc.p90:,.0f}"
        + (f"; {mc.prob_above:.0%} probability of exceeding the market price." if mc.prob_above is not None else ".")
    )
    if rev:
        s.append(
            f"The market price implies a {rev['implied_cagr']:.1%} revenue CAGR against a {rev['plan_cagr']:.1%} plan."
        )
    if deal and deal.irr is not None:
        s.append(
            f"A sponsor buying at {deal.entry_multiple:.1f}x with {p.lbo_leverage:.1f}x leverage earns {deal.irr:.0%} IRR "
            f"({deal.moic:.1f}x MOIC){', supporting a sponsor exit route' if deal.irr >= 0.2 else ', below typical PE hurdles'}."
        )
    s.append(
        f"Credit: {credit['leverage']:.1f}x net debt/EBITDA, {credit['coverage']:.1f}x interest cover, indicative band "
        f"{credit['band']}."
        if credit["leverage"] != float("inf")
        else "Credit metrics not meaningful at negative EBITDA."
    )
    report.summary = s
    report.data.update(
        {
            "weighted": weighted,
            "mc_p10": mc.p10,
            "mc_p50": mc.p50,
            "mc_p90": mc.p90,
            "mc_prob_above": mc.prob_above,
            "implied_cagr": rev["implied_cagr"] if rev else None,
            "lbo_irr": deal.irr if deal else None,
            "credit_band": credit["band"],
        }
    )
    return report
