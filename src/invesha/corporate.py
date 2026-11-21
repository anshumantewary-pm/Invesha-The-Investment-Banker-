"""Company in -> financial model + valuation + investment view (IB / corporate finance).

Projects revenue, EBITDA, EBIT, net income and unlevered free cash flow for N years,
builds WACC from CAPM, values the company by DCF (perpetuity growth and exit multiple),
trading comparables and a quick LBO, then turns the results into an investment
recommendation, transaction angles and prioritised suggestions.

All amounts share one unit (e.g. Rs crore or $ million). ``shares`` is in the same
unit basis, so equity value / shares gives value per share in currency.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from invesha.core import (
    Bar,
    Chart,
    InputError,
    Report,
    Suggestion,
    Table,
    Tile,
    check,
    fade,
    from_dict,
    irr,
    number,
    sort_suggestions,
)
from invesha.sectors import Sector, get_sector


@dataclass(frozen=True)
class CompanyInputs:
    name: str
    sector: str
    revenue: float  # last financial year
    ebitda_margin: float  # last financial year, fraction
    currency: str = "₹"
    unit: str = "Cr"
    years: int = 5
    growth: list[float] | None = None  # explicit per-year growth; overrides the fade
    growth_start: float = 0.15
    growth_end: float = 0.08
    margin_target: float | None = None  # EBITDA margin in the final year (fades linearly)
    da_pct: float = 0.04  # depreciation & amortisation, % of revenue
    capex_pct: float = 0.05  # % of revenue
    nwc_pct: float = 0.10  # net working capital, % of revenue
    tax_rate: float = 0.25
    debt: float = 0.0
    cash: float = 0.0
    interest_rate: float = 0.09  # pre-tax cost of debt
    shares: float | None = None
    share_price: float | None = None
    risk_free: float = 0.07
    equity_risk_premium: float = 0.065
    beta: float | None = None  # levered; default relevers the sector beta
    size_premium: float = 0.0
    debt_weight: float | None = None  # target D/(D+E); default from market cap or balance sheet
    terminal_growth: float = 0.05
    exit_multiple: float | None = None  # EV/EBITDA at exit; default sector mid
    lbo_entry_multiple: float | None = None
    lbo_leverage: float = 4.0  # debt / LTM EBITDA
    lbo_interest_rate: float = 0.11
    invested_capital: float | None = None  # for ROIC


@dataclass
class Projection:
    years: list[str]
    growth: list[float]
    revenue: list[float]
    margin: list[float]
    ebitda: list[float]
    da: list[float]
    ebit: list[float]
    interest: list[float]
    ebt: list[float]
    tax: list[float]
    net_income: list[float]
    nopat: list[float]
    capex: list[float]
    delta_nwc: list[float]
    fcff: list[float]
    roic: list[float | None] = field(default_factory=list)


@dataclass
class Wacc:
    beta: float
    cost_of_equity: float
    cost_of_debt_after_tax: float
    debt_weight: float
    wacc: float


@dataclass
class Dcf:
    pv_fcff: float
    tv_gordon: float
    tv_exit: float
    pv_tv_gordon: float
    pv_tv_exit: float
    ev_gordon: float
    ev_exit: float
    ev: float  # average of the two
    tv_share: float  # share of EV from the terminal value (average method)
    implied_exit_multiple: float  # what the Gordon TV implies
    discount_factors: list[float]


def validate(p: CompanyInputs) -> Sector:
    sector = get_sector(p.sector)
    check(bool(str(p.name).strip()), "company name is required")
    number("revenue", p.revenue, low=1e-9)
    number("EBITDA margin", p.ebitda_margin, -1, 1)
    check(isinstance(p.years, int) and 3 <= p.years <= 15, "years must be a whole number, 3-15")
    if p.growth is not None:
        check(len(p.growth) == p.years, f"growth needs exactly {p.years} values (one per year)")
        for g in p.growth:
            number("growth", g, -0.9, 5)
    for label, v, lo, hi in (
        ("starting growth", p.growth_start, -0.9, 5),
        ("final growth", p.growth_end, -0.9, 5),
        ("D&A %", p.da_pct, 0, 1),
        ("capex %", p.capex_pct, 0, 1),
        ("NWC %", p.nwc_pct, -1, 2),
        ("tax rate", p.tax_rate, 0, 0.6),
        ("debt", p.debt, 0, None),
        ("cash", p.cash, 0, None),
        ("interest rate", p.interest_rate, 0, 0.5),
        ("risk-free rate", p.risk_free, 0, 0.3),
        ("equity risk premium", p.equity_risk_premium, 0, 0.3),
        ("terminal growth", p.terminal_growth, -0.05, 0.15),
        ("LBO leverage", p.lbo_leverage, 0, 10),
        ("LBO interest rate", p.lbo_interest_rate, 0, 0.5),
    ):
        number(label, v, lo, hi)
    if p.margin_target is not None:
        number("target margin", p.margin_target, -1, 1)
    if p.beta is not None:
        number("beta", p.beta, 0.05, 5)
    if p.debt_weight is not None:
        number("debt weight", p.debt_weight, 0, 0.9)
    for label, v in (
        ("shares", p.shares),
        ("share price", p.share_price),
        ("exit multiple", p.exit_multiple),
        ("LBO entry multiple", p.lbo_entry_multiple),
        ("invested capital", p.invested_capital),
    ):
        if v is not None:
            number(label, v, low=1e-9)
    return sector


def project(p: CompanyInputs) -> Projection:
    n = p.years
    growth = list(p.growth) if p.growth is not None else fade(p.growth_start, p.growth_end, n)
    target = p.ebitda_margin if p.margin_target is None else p.margin_target
    margins = fade(p.ebitda_margin + (target - p.ebitda_margin) / n, target, n)
    rev, prev = [], p.revenue
    for g in growth:
        prev = prev * (1 + g)
        rev.append(prev)
    ebitda = [r * m for r, m in zip(rev, margins)]
    da = [r * p.da_pct for r in rev]
    ebit = [e - d for e, d in zip(ebitda, da)]
    interest = [p.debt * p.interest_rate] * n
    ebt = [e - i for e, i in zip(ebit, interest)]
    tax = [max(x, 0.0) * p.tax_rate for x in ebt]
    ni = [x - t for x, t in zip(ebt, tax)]
    nopat = [e - max(e, 0.0) * p.tax_rate for e in ebit]
    capex = [r * p.capex_pct for r in rev]
    revs = [p.revenue, *rev]
    dnwc = [(revs[i + 1] - revs[i]) * p.nwc_pct for i in range(n)]
    fcff = [o + d - c - w for o, d, c, w in zip(nopat, da, capex, dnwc)]
    roic: list[float | None] = []
    if p.invested_capital is not None:
        ic = p.invested_capital
        for o, c, d, w in zip(nopat, capex, da, dnwc):
            roic.append(o / ic if ic > 0 else None)
            ic += c - d + w
    return Projection(
        years=[f"Y{i + 1}" for i in range(n)],
        growth=growth,
        revenue=rev,
        margin=margins,
        ebitda=ebitda,
        da=da,
        ebit=ebit,
        interest=interest,
        ebt=ebt,
        tax=tax,
        net_income=ni,
        nopat=nopat,
        capex=capex,
        delta_nwc=dnwc,
        fcff=fcff,
        roic=roic,
    )


def market_cap(p: CompanyInputs) -> float | None:
    if p.shares is not None and p.share_price is not None:
        return p.shares * p.share_price
    return None


def wacc(p: CompanyInputs, sector: Sector) -> Wacc:
    mcap = market_cap(p)
    if p.debt_weight is not None:
        wd = p.debt_weight
    elif mcap:
        wd = p.debt / (p.debt + mcap)
    else:
        wd = 0.0 if p.debt == 0 else 0.25
    de = wd / (1 - wd)
    beta = p.beta if p.beta is not None else sector.unlevered_beta * (1 + (1 - p.tax_rate) * de)
    ke = p.risk_free + beta * p.equity_risk_premium + p.size_premium
    kd = p.interest_rate * (1 - p.tax_rate)
    return Wacc(beta, ke, kd, wd, (1 - wd) * ke + wd * kd)


def dcf(proj: Projection, rate: float, g: float, exit_multiple: float) -> Dcf:
    if rate <= g + 0.005:
        raise InputError(f"WACC ({rate:.1%}) must exceed terminal growth ({g:.1%}) by at least 0.5 points")
    n = len(proj.fcff)
    factors = [1 / (1 + rate) ** (i + 1) for i in range(n)]
    pv = sum(f * d for f, d in zip(proj.fcff, factors))
    tv_g = proj.fcff[-1] * (1 + g) / (rate - g)
    tv_x = proj.ebitda[-1] * exit_multiple
    pv_g, pv_x = tv_g * factors[-1], tv_x * factors[-1]
    ev_g, ev_x = pv + pv_g, pv + pv_x
    ev = (ev_g + ev_x) / 2
    implied = tv_g / proj.ebitda[-1] if proj.ebitda[-1] > 0 else float("nan")
    return Dcf(pv, tv_g, tv_x, pv_g, pv_x, ev_g, ev_x, ev, ((pv_g + pv_x) / 2) / ev if ev else 0.0, implied, factors)


@dataclass
class Lbo:
    entry_ev: float
    entry_debt: float
    entry_equity: float
    exit_ev: float
    exit_debt: float
    exit_equity: float
    irr: float | None
    moic: float
    debt_path: list[float]


def lbo(p: CompanyInputs, proj: Projection, sector: Sector) -> Lbo | None:
    ltm_ebitda = p.revenue * p.ebitda_margin
    if ltm_ebitda <= 0:
        return None
    entry_mult = p.lbo_entry_multiple or sector.ev_ebitda[1]
    exit_mult = p.exit_multiple or entry_mult
    ev = entry_mult * ltm_ebitda
    debt = min(p.lbo_leverage * ltm_ebitda, 0.75 * ev)
    equity = ev - debt + 0.02 * ev  # 2% fees funded with equity
    cash, path = 0.0, []
    for i in range(len(proj.revenue)):
        interest = debt * p.lbo_interest_rate
        tax = max(proj.ebit[i] - interest, 0.0) * p.tax_rate
        levered_fcf = proj.ebitda[i] - proj.capex[i] - proj.delta_nwc[i] - tax - interest
        repay = min(max(levered_fcf, 0.0), debt)
        debt -= repay
        cash += levered_fcf - repay
        path.append(debt)
    exit_ev = exit_mult * proj.ebitda[-1]
    exit_equity = max(exit_ev - debt + cash, 0.0)
    flows = [-equity] + [0.0] * (len(proj.revenue) - 1) + [exit_equity]
    return Lbo(
        ev,
        min(p.lbo_leverage * ltm_ebitda, 0.75 * ev),
        equity,
        exit_ev,
        debt,
        exit_equity,
        irr(flows),
        exit_equity / equity if equity else 0.0,
        path,
    )


def _ev(p: CompanyInputs, sector: Sector) -> float:
    proj = project(p)
    w = wacc(p, sector)
    return dcf(proj, w.wacc, p.terminal_growth, p.exit_multiple or sector.ev_ebitda[1]).ev


def tornado(p: CompanyInputs, sector: Sector) -> list[tuple[str, float, float]]:
    """(driver, EV at downside, EV at upside), widest swing first."""
    growth = list(p.growth) if p.growth else None
    target = p.ebitda_margin if p.margin_target is None else p.margin_target
    w = wacc(p, sector).wacc

    def shift_growth(d: float) -> CompanyInputs:
        if growth:
            return replace(p, growth=[g + d for g in growth])
        return replace(p, growth_start=p.growth_start + d, growth_end=p.growth_end + d)

    cases = [
        ("Revenue growth ±2pts", shift_growth(-0.02), shift_growth(0.02)),
        (
            "EBITDA margin ±2pts",
            replace(p, ebitda_margin=p.ebitda_margin - 0.02, margin_target=target - 0.02),
            replace(p, ebitda_margin=p.ebitda_margin + 0.02, margin_target=target + 0.02),
        ),
        ("WACC ±1pt", None, None),
        (
            "Terminal growth ±0.5pt",
            replace(p, terminal_growth=p.terminal_growth - 0.005),
            replace(p, terminal_growth=p.terminal_growth + 0.005),
        ),
        (
            "Capex ±1pt of revenue",
            replace(p, capex_pct=p.capex_pct + 0.01),
            replace(p, capex_pct=max(p.capex_pct - 0.01, 0.0)),
        ),
    ]
    out = []
    proj = project(p)
    exit_mult = p.exit_multiple or sector.ev_ebitda[1]
    for label, down, up in cases:
        try:
            if label.startswith("WACC"):
                lo = dcf(proj, w + 0.01, p.terminal_growth, exit_mult).ev
                hi = dcf(proj, w - 0.01, p.terminal_growth, exit_mult).ev
            else:
                assert down is not None and up is not None
                lo, hi = _ev(down, sector), _ev(up, sector)
        except InputError:
            continue
        out.append((label, lo, hi))
    out.sort(key=lambda t: abs(t[2] - t[1]), reverse=True)
    return out


def analyse_inputs(data: dict[str, Any]) -> Report:
    return analyse(from_dict(CompanyInputs, data))


def analyse(p: CompanyInputs) -> Report:
    sector = validate(p)
    proj = project(p)
    w = wacc(p, sector)
    exit_mult = p.exit_multiple or sector.ev_ebitda[1]
    d = dcf(proj, w.wacc, p.terminal_growth, exit_mult)
    net_debt = p.debt - p.cash
    eq = d.ev - net_debt
    ltm_ebitda = p.revenue * p.ebitda_margin
    mcap = market_cap(p)
    per_share = (lambda v: v / p.shares) if p.shares else (lambda v: None)

    # Trading comparables (EV-based, then equity)
    comps: list[tuple[str, float, float, float]] = []
    if ltm_ebitda > 0:
        lo, mid, hi = sector.ev_ebitda
        comps.append(("EV / EBITDA (LTM)", lo * ltm_ebitda, mid * ltm_ebitda, hi * ltm_ebitda))
        e1 = proj.ebitda[0]
        if e1 > 0:
            comps.append(("EV / EBITDA (NTM)", lo * e1, mid * e1, hi * e1))
    lo, mid, hi = sector.ev_revenue
    comps.append(("EV / Revenue (LTM)", lo * p.revenue, mid * p.revenue, hi * p.revenue))
    if proj.net_income[0] > 0:
        lo, mid, hi = sector.pe
        ni = proj.net_income[0]
        comps.append(("P / E (NTM)", lo * ni + net_debt, mid * ni + net_debt, hi * ni + net_debt))

    deal = lbo(p, proj, sector)

    # Sensitivity: equity value (or per share) across WACC x terminal growth
    waccs = [w.wacc + s for s in (-0.01, -0.005, 0.0, 0.005, 0.01)]
    gs = [p.terminal_growth + s for s in (-0.01, -0.005, 0.0, 0.005, 0.01)]
    grid: list[list[Any]] = []
    for r in waccs:
        row: list[Any] = [r]
        for g in gs:
            try:
                v = dcf(proj, r, g, exit_mult).ev_gordon - net_debt
                row.append(per_share(v) if p.shares else v)
            except InputError:
                row.append(None)
        grid.append(row)

    drivers = tornado(p, sector)

    # Fair value range for the verdict: DCF methods + comps mid points
    ev_points = [d.ev_gordon, d.ev_exit] + [c[2] for c in comps]
    fair_lo, fair_hi = min(ev_points) - net_debt, max(ev_points) - net_debt
    fair_mid = (d.ev + sum(c[2] for c in comps) / len(comps)) / 2 - net_debt

    verdict, tone, note = "Indicative valuation", "", ""
    upside = None
    if mcap:
        upside = fair_mid / mcap - 1
        if upside > 0.15:
            verdict, tone = "BUY", "good"
        elif upside < -0.10:
            verdict, tone = "REDUCE", "bad"
        else:
            verdict, tone = "HOLD", "warn"
        note = (
            f"Blended fair equity value {p.currency}{fair_mid:,.0f} {p.unit} vs market cap "
            f"{p.currency}{mcap:,.0f} {p.unit}: {upside:+.0%} upside"
        )
    else:
        note = (
            f"Blended fair equity value {p.currency}{fair_mid:,.0f} {p.unit} "
            f"(range {p.currency}{fair_lo:,.0f}-{fair_hi:,.0f}). Add shares and share price "
            "for a Buy / Hold / Reduce call."
        )

    suggestions = _suggest(p, sector, proj, w, d, deal, comps, drivers, upside, net_debt, ltm_ebitda)

    cur, unit = p.currency, p.unit
    tiles = [
        Tile("Enterprise value (DCF)", d.ev, note=f"Gordon {cur}{d.ev_gordon:,.0f} · exit {cur}{d.ev_exit:,.0f}"),
        Tile("Equity value (DCF)", eq, note=f"net debt {cur}{net_debt:,.0f}"),
        Tile(
            "Value per share",
            per_share(fair_mid),
            "money",
            note=f"vs price {cur}{p.share_price:,.2f}" if p.share_price else "blended DCF + comps",
        ),
        Tile("WACC", w.wacc, "pct", note=f"Ke {w.cost_of_equity:.1%} · β {w.beta:.2f}"),
        Tile("Revenue CAGR", (proj.revenue[-1] / p.revenue) ** (1 / p.years) - 1, "pct", note=f"{p.years}-year"),
        Tile(
            "Terminal value share",
            d.tv_share,
            "pct",
            tone="warn" if d.tv_share > 0.75 else "",
            note="of DCF enterprise value",
        ),
    ]
    if deal:
        tiles.append(
            Tile(
                "LBO IRR",
                deal.irr,
                "pct",
                note=f"{deal.moic:.1f}x MOIC",
                tone="good" if (deal.irr or 0) >= 0.2 else "warn",
            )
        )
    if upside is not None:
        tiles.insert(
            0,
            Tile(
                "Upside to fair value",
                upside,
                "pct",
                tone="good" if upside > 0.15 else "bad" if upside < -0.1 else "warn",
            ),
        )

    football = Chart("Valuation football field (equity value)", "range", fmt="money")
    football.bars.append(
        Bar(
            "DCF (WACC ±1pt, g ±1pt)",
            min(_grid_values(grid, p.shares, net_debt)),
            max(_grid_values(grid, p.shares, net_debt)),
            eq,
        )
    )
    football.bars.append(
        Bar(
            "DCF: exit multiple ±2x",
            d.ev_exit - 2 * proj.ebitda[-1] * d.discount_factors[-1] - net_debt,
            d.ev_exit + 2 * proj.ebitda[-1] * d.discount_factors[-1] - net_debt,
            d.ev_exit - net_debt,
        )
    )
    for name, lo_, mid_, hi_ in comps:
        football.bars.append(Bar(name, lo_ - net_debt, hi_ - net_debt, mid_ - net_debt))
    if deal:
        football.bars.append(
            Bar(
                "LBO (entry to exit)",
                deal.entry_ev - net_debt,
                deal.exit_ev * d.discount_factors[-1] - net_debt,
                deal.entry_ev - net_debt,
            )
        )
    if mcap:
        football.marker, football.marker_label = mcap, "Market cap"

    charts = [
        football,
        Chart(
            "Revenue, EBITDA and free cash flow",
            "bars",
            labels=proj.years,
            series={"Revenue": proj.revenue, "EBITDA": proj.ebitda, "FCFF": proj.fcff},
        ),
        Chart(
            "Margins",
            "line",
            labels=["FY0", *proj.years],
            fmt="pct",
            series={
                "EBITDA margin": [p.ebitda_margin, *proj.margin],
                "Net margin": [None, *[n / r for n, r in zip(proj.net_income, proj.revenue)]],
                "FCF margin": [None, *[f / r for f, r in zip(proj.fcff, proj.revenue)]],
            },
        ),
        Chart(
            "From enterprise value to equity value",
            "waterfall",
            fmt="money",
            labels=["PV of cash flows", "PV of terminal value", "Net debt", "Equity value"],
            series={"value": [d.pv_fcff, (d.pv_tv_gordon + d.pv_tv_exit) / 2, -net_debt, eq]},
        ),
        Chart(
            "Where the value comes from",
            "donut",
            fmt="money",
            labels=["Forecast-period cash flows", "Terminal value"],
            series={"value": [max(d.pv_fcff, 0.0), max((d.pv_tv_gordon + d.pv_tv_exit) / 2, 0.0)]},
        ),
        Chart(
            "What moves enterprise value",
            "range",
            fmt="money",
            bars=[Bar(lbl, min(a, b), max(a, b), d.ev) for lbl, a, b in drivers],
            marker=d.ev,
            marker_label="Base EV",
        ),
    ]

    cols = ["", "FY0 (actual)", *proj.years]
    is_rows = [
        ["Revenue", p.revenue, *proj.revenue],
        ["Growth", None, *proj.growth],
        ["EBITDA", ltm_ebitda, *proj.ebitda],
        ["EBITDA margin", p.ebitda_margin, *proj.margin],
        ["D&A", None, *proj.da],
        ["EBIT", None, *proj.ebit],
        ["Interest", None, *proj.interest],
        ["Profit before tax", None, *proj.ebt],
        ["Tax", None, *proj.tax],
        ["Net income", None, *proj.net_income],
    ]
    is_fmts = ["money", "pct", "money", "pct", "money", "money", "money", "money", "money", "money"]
    fcf_rows = [
        ["NOPAT (EBIT × (1 − t))", None, *proj.nopat],
        ["+ D&A", None, *proj.da],
        ["− Capex", None, *[-c for c in proj.capex]],
        ["− Increase in working capital", None, *[-x for x in proj.delta_nwc]],
        ["Unlevered free cash flow", None, *proj.fcff],
        ["Discount factor", None, *d.discount_factors],
        ["PV of free cash flow", None, *[f * k for f, k in zip(proj.fcff, d.discount_factors)]],
    ]
    fcf_fmts = ["money"] * 5 + ["num", "money"]
    if proj.roic:
        fcf_rows.append(["ROIC", None, *proj.roic])
        fcf_fmts.append("pct")
    val_rows = [
        ["PV of free cash flows", d.pv_fcff, d.pv_fcff],
        ["Terminal value", d.tv_gordon, d.tv_exit],
        ["PV of terminal value", d.pv_tv_gordon, d.pv_tv_exit],
        ["Enterprise value", d.ev_gordon, d.ev_exit],
        ["− Net debt", -net_debt, -net_debt],
        ["Equity value", d.ev_gordon - net_debt, d.ev_exit - net_debt],
        [
            "Implied EV / EBITDA (LTM)",
            d.ev_gordon / ltm_ebitda if ltm_ebitda > 0 else None,
            d.ev_exit / ltm_ebitda if ltm_ebitda > 0 else None,
        ],
    ]
    val_fmts = ["money"] * 6 + ["x"]
    if p.shares:
        val_rows.append(["Value per share", (d.ev_gordon - net_debt) / p.shares, (d.ev_exit - net_debt) / p.shares])
        val_fmts.append("money")
    wacc_rows = [
        ["Risk-free rate", p.risk_free],
        ["Equity risk premium", p.equity_risk_premium],
        ["Levered beta", w.beta],
        ["Size / specific premium", p.size_premium],
        ["Cost of equity", w.cost_of_equity],
        ["Pre-tax cost of debt", p.interest_rate],
        ["After-tax cost of debt", w.cost_of_debt_after_tax],
        ["Debt weight D/(D+E)", w.debt_weight],
        ["WACC", w.wacc],
    ]
    tables = [
        Table("Income statement", cols, is_rows, is_fmts),
        Table("Free cash flow and discounting", cols, fcf_rows, fcf_fmts),
        Table(
            "DCF valuation",
            ["", f"Perpetuity growth {p.terminal_growth:.1%}", f"Exit multiple {exit_mult:.1f}x"],
            val_rows,
            val_fmts,
        ),
        Table(
            "Cost of capital (WACC)",
            ["", "Value"],
            wacc_rows,
            ["pct", "pct", "num", "pct", "pct", "pct", "pct", "pct", "pct"],
        ),
        Table(
            ("Value per share" if p.shares else "Equity value")
            + " sensitivity: WACC (rows) × terminal growth (columns)",
            ["WACC \\ g", *[f"{g:.1%}" for g in gs]],
            grid,
            ["pct"] + ["money"] * 5,
            by_column=True,
            note="Perpetuity-growth DCF; centre cell is the base case.",
        ),
        Table(
            "Trading comparables (enterprise value)",
            ["Method", "Low", "Mid", "High"],
            [[c[0], c[1], c[2], c[3]] for c in comps],
            ["text", "money", "money", "money"],
            by_column=True,
            note=f"{sector.name} multiples (indicative).",
        ),
    ]
    if deal:
        tables.append(
            Table(
                "LBO returns",
                ["", "Value"],
                [
                    ["Entry EV", deal.entry_ev],
                    ["Entry debt", deal.entry_debt],
                    ["Sponsor equity (incl. 2% fees)", deal.entry_equity],
                    ["Exit EV", deal.exit_ev],
                    ["Debt at exit", deal.exit_debt],
                    ["Exit equity", deal.exit_equity],
                    ["IRR", deal.irr],
                    ["MOIC", deal.moic],
                ],
                ["money"] * 6 + ["pct", "x"],
            )
        )

    assumptions = [
        ["Sector", sector.name, "text"],
        ["Projection years", p.years, "int"],
        ["Tax rate", p.tax_rate, "pct"],
        ["D&A % revenue", p.da_pct, "pct"],
        ["Capex % revenue", p.capex_pct, "pct"],
        ["Working capital % revenue", p.nwc_pct, "pct"],
        ["Terminal growth", p.terminal_growth, "pct"],
        ["Exit EV/EBITDA", exit_mult, "x"],
    ]
    return Report(
        kind="company",
        title=p.name,
        subtitle=f"{sector.name} · {p.years}-year model · {cur} {unit}",
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
            "ev": d.ev,
            "equity": eq,
            "wacc": w.wacc,
            "fair_mid": fair_mid,
            "upside": upside,
            "lbo_irr": deal.irr if deal else None,
            "fcff": proj.fcff,
        },
    )


def _grid_values(grid: list[list[Any]], shares: float | None, net_debt: float) -> list[float]:
    vals = [v for row in grid for v in row[1:] if v is not None]
    return [v * shares for v in vals] if shares else vals


def _suggest(
    p: CompanyInputs,
    sector: Sector,
    proj: Projection,
    w: Wacc,
    d: Dcf,
    deal: Lbo | None,
    comps: list[tuple[str, float, float, float]],
    drivers: list[tuple[str, float, float]],
    upside: float | None,
    net_debt: float,
    ltm_ebitda: float,
) -> list[Suggestion]:
    out: list[Suggestion] = []
    cur, unit = p.currency, p.unit
    if upside is not None:
        if upside > 0.15:
            out.append(
                Suggestion(
                    "high",
                    "Investment view",
                    f"BUY: {upside:.0%} upside to blended fair value",
                    "The market price sits well below DCF and comparables. Build a position, sized to "
                    "conviction in the key value drivers below.",
                    [
                        "Stress-test the top value driver before committing",
                        "Set a review trigger if the upside narrows below 10%",
                    ],
                )
            )
        elif upside < -0.10:
            out.append(
                Suggestion(
                    "high",
                    "Investment view",
                    f"REDUCE: price is {-upside:.0%} above fair value",
                    "The market is pricing in more growth or margin than this model supports.",
                    [
                        "Identify what growth/margin the price implies (reverse DCF)",
                        "Trim exposure or hedge until fundamentals catch up",
                    ],
                )
            )
        else:
            out.append(
                Suggestion(
                    "medium",
                    "Investment view",
                    f"HOLD: fairly valued ({upside:+.0%})",
                    "Price is within the fair value range; returns depend on execution beyond the plan.",
                    ["Watch quarterly margin delivery against the model", "Re-rate if growth beats the base case"],
                )
            )
    comp_mid = sum(c[2] for c in comps) / len(comps)
    gap = d.ev / comp_mid - 1 if comp_mid else 0.0
    if abs(gap) > 0.30:
        out.append(
            Suggestion(
                "medium",
                "Valuation",
                f"DCF is {gap:+.0%} versus trading comparables",
                "A gap this large usually means the projections or discount rate differ from what "
                "the market assumes for peers.",
                [
                    "Check growth and margin path against peer consensus",
                    "Cross-check WACC with peer betas and capital structures",
                ],
            )
        )
    if d.tv_share > 0.75:
        out.append(
            Suggestion(
                "medium",
                "Valuation",
                f"{d.tv_share:.0%} of value sits in the terminal value",
                "The valuation leans heavily on years beyond the forecast. Small changes in terminal "
                "growth or exit multiple swing the answer.",
                ["Extend the explicit forecast to 7-10 years", "Show the WACC × g sensitivity to investors"],
            )
        )
    if d.implied_exit_multiple == d.implied_exit_multiple:  # not NaN
        lo, _, hi = sector.ev_ebitda
        if d.implied_exit_multiple > hi * 1.2:
            out.append(
                Suggestion(
                    "medium",
                    "Valuation",
                    f"Perpetuity growth implies {d.implied_exit_multiple:.1f}x exit EBITDA",
                    f"That is above the {lo:.0f}-{hi:.0f}x sector range: terminal growth or WACC may be too generous.",
                    ["Lower terminal growth or raise WACC and compare"],
                )
            )
    if drivers:
        top = drivers[0]
        out.append(
            Suggestion(
                "low",
                "Value drivers",
                f"Biggest value driver: {top[0]}",
                f"It moves enterprise value between {cur}{top[1]:,.0f} and {cur}{top[2]:,.0f} {unit}. "
                "Spend diligence time here first.",
                [f"{lbl}: {cur}{lo:,.0f}-{hi:,.0f}" for lbl, lo, hi in drivers[1:4]],
            )
        )
    lo_m, hi_m = sector.ebitda_margin
    final_margin = proj.margin[-1]
    if final_margin < lo_m:
        out.append(
            Suggestion(
                "medium",
                "Operations",
                f"Margin of {final_margin:.0%} trails the {lo_m:.0%}-{hi_m:.0%} sector range",
                "Closing even half the gap would lift EBITDA and valuation materially.",
                ["Pricing and mix review", "Procurement and overhead programme"],
            )
        )
    elif proj.margin[-1] > hi_m:
        out.append(
            Suggestion(
                "low",
                "Operations",
                f"Target margin of {final_margin:.0%} is above the sector range",
                "Make sure the plan explains why this company can sustain best-in-class margins.",
                ["Benchmark against the top-quartile peer"],
            )
        )
    lo_g, hi_g = sector.growth
    cagr = (proj.revenue[-1] / p.revenue) ** (1 / p.years) - 1
    if cagr > hi_g * 1.25:
        out.append(
            Suggestion(
                "medium",
                "Forecast risk",
                f"Revenue CAGR of {cagr:.0%} is well above the sector's {lo_g:.0%}-{hi_g:.0%}",
                "Aggressive growth needs evidence: order book, pipeline, capacity, pricing power.",
                ["Build a bottom-up revenue bridge", "Run a downside case at sector-average growth"],
            )
        )
    leverage = net_debt / ltm_ebitda if ltm_ebitda > 0 else None
    if leverage is not None and leverage > 3.5:
        out.append(
            Suggestion(
                "high",
                "Capital structure",
                f"Net debt is {leverage:.1f}x EBITDA",
                "Above roughly 3-3.5x, refinancing and covenant risk rise and equity value is fragile.",
                ["Prioritise deleveraging from free cash flow", "Consider an equity raise or asset sale"],
            )
        )
    elif leverage is not None and leverage < 1.0 and ltm_ebitda > 0:
        capacity = 3.0 * ltm_ebitda - net_debt
        out.append(
            Suggestion(
                "low",
                "Capital structure",
                f"Balance sheet capacity: about {cur}{capacity:,.0f} {unit} of debt",
                "Low leverage leaves room to fund growth capex, acquisitions or returns to shareholders "
                "up to roughly 3x EBITDA.",
                ["Bolt-on M&A in adjacent segments", "Buyback or special dividend if no better use"],
            )
        )
    if proj.roic:
        avg = [r for r in proj.roic if r is not None]
        if avg:
            roic = sum(avg) / len(avg)
            tone = "creates" if roic > w.wacc else "destroys"
            out.append(
                Suggestion(
                    "medium" if roic < w.wacc else "low",
                    "Value creation",
                    f"Average ROIC {roic:.1%} vs WACC {w.wacc:.1%}: growth {tone} value",
                    "Growth only adds value when returns on new capital beat the cost of capital.",
                    ["Redirect capital to the highest-ROIC segments"]
                    if roic < w.wacc
                    else ["Reinvest aggressively while ROIC stays above WACC"],
                )
            )
    # Transaction angles (CIB)
    angles = []
    if deal and deal.irr is not None and deal.irr >= 0.20:
        angles.append(
            f"PE buyout: a sponsor earns {deal.irr:.0%} IRR at {p.lbo_leverage:.1f}x leverage, so a sponsor sale is credible"
        )
    elif deal and deal.irr is not None:
        angles.append(f"Strategic sale over sponsor: LBO IRR of {deal.irr:.0%} is below the ~20% PE hurdle")
    if cagr >= 0.12 and final_margin >= lo_m:
        angles.append(
            "IPO: growth and margins are in the range public investors reward; prepare 3 years of audited track record"
        )
    if ltm_ebitda > 0 and (leverage or 0) < 2.5:
        angles.append(
            f"Debt raise: room for about {cur}{max(3.0 * ltm_ebitda - net_debt, 0):,.0f} {unit} of term debt to fund growth"
        )
    angles.append("Bolt-on acquisitions at or below the sector's mid EV/EBITDA are accretive if synergies are real")
    out.append(
        Suggestion(
            "low",
            "Transaction angles",
            "Corporate finance options to explore",
            "Based on the model's growth, margins, leverage and LBO returns.",
            angles,
        )
    )
    return sort_suggestions(out)
