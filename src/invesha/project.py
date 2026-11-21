"""Project finance: construction + operations, sculpted or annuity debt, DSCR/LLCR, IRRs.

Typical use: a plant, road, solar park or other asset with a build period followed by
years of contracted or merchant revenue. Debt is sized as the smaller of the gearing
cap and what cash flow can service at the target DSCR (sculpting), then repaid either
sculpted to a flat DSCR or as an annuity.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from invesha.core import (
    Bar,
    Chart,
    Report,
    Suggestion,
    Table,
    Tile,
    annuity_payment,
    check,
    from_dict,
    irr,
    npv,
    number,
    solve,
    sort_suggestions,
)


@dataclass(frozen=True)
class ProjectInputs:
    name: str
    capex: float  # total construction cost (excluding interest during construction)
    capacity: float  # units produced / sold per year at 100% (MWh, tonnes, vehicles...)
    price: float  # revenue per unit in year 1 of operations
    currency: str = "₹"
    unit: str = "Cr"
    construction_years: int = 2
    operating_years: int = 20
    utilisation: float = 0.85  # availability / plant load factor
    price_escalation: float = 0.02
    opex_fixed: float = 0.0  # per year, year-1 terms
    opex_variable: float = 0.0  # per unit produced, year-1 terms
    opex_escalation: float = 0.04
    tax_rate: float = 0.25
    depreciation_years: int | None = None  # default: operating years
    gearing: float = 0.70  # maximum debt / total funding
    debt_rate: float = 0.095
    tenor: int = 15  # repayment years after COD
    repayment: str = "sculpted"  # or "annuity"
    target_dscr: float = 1.30
    discount_rate: float = 0.10  # project NPV
    cost_of_equity: float = 0.14  # equity NPV / hurdle
    terminal_value: float = 0.0  # residual value at end of operations


@dataclass
class ProjectResult:
    years: list[str]
    revenue: list[float]
    opex: list[float]
    ebitda: list[float]
    depreciation: list[float]
    interest: list[float]
    tax: list[float]
    cfads: list[float]
    debt_service: list[float]
    principal: list[float]
    debt_balance: list[float]
    dscr: list[float | None]
    equity_flows: list[float]  # construction then operations
    project_flows: list[float]
    debt: float
    idc: float
    equity: float
    total_cost: float
    llcr: float | None
    min_dscr: float | None
    avg_dscr: float | None
    project_irr: float | None
    equity_irr: float | None
    project_npv: float
    equity_npv: float
    payback_year: int | None


def validate(p: ProjectInputs) -> None:
    check(bool(str(p.name).strip()), "project name is required")
    number("capex", p.capex, low=1e-9)
    number("capacity", p.capacity, low=1e-9)
    number("price", p.price, low=0)
    check(
        isinstance(p.construction_years, int) and 0 <= p.construction_years <= 8,
        "construction years must be a whole number, 0-8",
    )
    check(
        isinstance(p.operating_years, int) and 1 <= p.operating_years <= 50,
        "operating years must be a whole number, 1-50",
    )
    check(
        isinstance(p.tenor, int) and 1 <= p.tenor <= p.operating_years,
        "debt tenor must be 1 to the number of operating years",
    )
    check(p.repayment in ("sculpted", "annuity"), "repayment must be 'sculpted' or 'annuity'")
    for label, v, lo, hi in (
        ("utilisation", p.utilisation, 0, 1),
        ("price escalation", p.price_escalation, -0.2, 0.3),
        ("fixed opex", p.opex_fixed, 0, None),
        ("variable opex", p.opex_variable, 0, None),
        ("opex escalation", p.opex_escalation, -0.2, 0.3),
        ("tax rate", p.tax_rate, 0, 0.6),
        ("gearing", p.gearing, 0, 0.95),
        ("debt rate", p.debt_rate, 0, 0.4),
        ("target DSCR", p.target_dscr, 1.0, 5),
        ("discount rate", p.discount_rate, 0, 0.5),
        ("cost of equity", p.cost_of_equity, 0, 0.6),
        ("terminal value", p.terminal_value, 0, None),
    ):
        number(label, v, lo, hi)
    if p.depreciation_years is not None:
        check(
            isinstance(p.depreciation_years, int) and p.depreciation_years >= 1,
            "depreciation years must be a whole number ≥ 1",
        )


def model(p: ProjectInputs) -> ProjectResult:
    n, c = p.operating_years, p.construction_years
    vol = p.capacity * p.utilisation
    revenue = [vol * p.price * (1 + p.price_escalation) ** t for t in range(n)]
    opex = [(p.opex_fixed + p.opex_variable * vol) * (1 + p.opex_escalation) ** t for t in range(n)]
    ebitda = [r - o for r, o in zip(revenue, opex)]

    # Unlevered tax for the project IRR (depreciation on capex only)
    dep_years = p.depreciation_years or n

    def depreciation(base: float) -> list[float]:
        return [base / dep_years if t < dep_years else 0.0 for t in range(n)]

    def taxes(taxable: list[float]) -> list[float]:
        out, loss = [], 0.0
        for x in taxable:
            x -= loss
            loss = max(-x, 0.0)
            out.append(max(x, 0.0) * p.tax_rate)
        return out

    dep_unlev = depreciation(p.capex)
    tax_unlev = taxes([e - d for e, d in zip(ebitda, dep_unlev)])
    project_flows = [-p.capex / c] * c if c else []
    project_flows = project_flows + [e - t for e, t in zip(ebitda, tax_unlev)]
    if c == 0:
        project_flows[0] -= p.capex
    project_flows[-1] += p.terminal_value

    # Debt sizing iterates: interest affects tax, tax affects CFADS, CFADS sizes debt.
    debt, idc, interest, tax = 0.0, 0.0, [0.0] * n, tax_unlev
    for _ in range(30):
        draw_per_year = debt / c if c else 0.0
        bal, idc_new = 0.0, 0.0
        for _y in range(c):
            bal += draw_per_year
            idc_new += bal * p.debt_rate / 2  # mid-year average draw
        idc = idc_new
        total_cost = p.capex + idc
        cfads = [e - t for e, t in zip(ebitda, tax)]
        pv_capacity = npv(p.debt_rate, [cf / p.target_dscr for cf in cfads[: p.tenor]], start=1)
        new_debt = max(min(p.gearing * total_cost, pv_capacity), 0.0)
        # repayment schedule
        balance, interest, principal, service = new_debt, [], [], []
        if p.repayment == "annuity" and new_debt > 0:
            pay = annuity_payment(new_debt, p.debt_rate, p.tenor)
        else:
            pv_cfads = npv(p.debt_rate, cfads[: p.tenor], start=1)
            flat = pv_cfads / new_debt if new_debt > 0 else 0.0
        for t in range(n):
            i_t = balance * p.debt_rate
            if t < p.tenor and new_debt > 0:
                ds = pay if p.repayment == "annuity" else cfads[t] / flat
                pr = ds - i_t
                if t == p.tenor - 1:
                    pr, ds = balance, balance + i_t
            else:
                ds = pr = 0.0
            balance -= pr
            interest.append(i_t)
            principal.append(pr)
            service.append(ds)
        dep = depreciation(total_cost)
        new_tax = taxes([e - d - i for e, d, i in zip(ebitda, dep, interest)])
        converged = abs(new_debt - debt) < 1e-6 * max(1.0, new_debt) and new_tax == tax
        debt, tax = new_debt, new_tax
        if converged:
            break

    cfads = [e - t for e, t in zip(ebitda, tax)]
    balances, bal = [], debt
    for pr in principal:
        bal -= pr
        balances.append(max(bal, 0.0))
    dscr = [cf / ds if ds > 1e-9 else None for cf, ds in zip(cfads, service)]
    ds_vals = [x for x in dscr if x is not None]
    equity = total_cost - debt
    equity_flows = [-equity / c] * c if c else []
    ops = [cf - ds for cf, ds in zip(cfads, service)]
    if c == 0:
        ops[0] -= equity
    equity_flows = equity_flows + ops
    equity_flows[-1] += p.terminal_value
    llcr = (npv(p.debt_rate, cfads[: p.tenor], start=1) / debt) if debt > 0 else None
    cum, payback = 0.0, None
    for i, f in enumerate(equity_flows):
        cum += f
        if cum >= 0 and payback is None and i >= c:
            payback = i - c + 1
    return ProjectResult(
        years=[f"Op {t + 1}" for t in range(n)],
        revenue=revenue,
        opex=opex,
        ebitda=ebitda,
        depreciation=depreciation(total_cost),
        interest=interest,
        tax=tax,
        cfads=cfads,
        debt_service=service,
        principal=principal,
        debt_balance=balances,
        dscr=dscr,
        equity_flows=equity_flows,
        project_flows=project_flows,
        debt=debt,
        idc=idc,
        equity=equity,
        total_cost=total_cost,
        llcr=llcr,
        min_dscr=min(ds_vals) if ds_vals else None,
        avg_dscr=sum(ds_vals) / len(ds_vals) if ds_vals else None,
        project_irr=irr(project_flows),
        equity_irr=irr(equity_flows),
        project_npv=npv(p.discount_rate, project_flows),
        equity_npv=npv(p.cost_of_equity, equity_flows),
        payback_year=payback,
    )


def analyse_inputs(data: dict[str, Any]) -> Report:
    return analyse(from_dict(ProjectInputs, data))


def analyse(p: ProjectInputs) -> Report:
    validate(p)
    r = model(p)
    cur, unit = p.currency, p.unit

    def eq_irr(**changes: Any) -> float | None:
        return model(replace(p, **changes)).equity_irr

    # Tariff needed for the equity hurdle
    breakeven_price = solve(lambda x: model(replace(p, price=x)).equity_npv, 0.0, 0.0, p.price * 10)
    scenarios = [
        ("Base case", {}),
        ("Price −10%", {"price": p.price * 0.9}),
        ("Capex +10%", {"capex": p.capex * 1.1}),
        ("Opex +10%", {"opex_fixed": p.opex_fixed * 1.1, "opex_variable": p.opex_variable * 1.1}),
        ("Utilisation −5pts", {"utilisation": max(p.utilisation - 0.05, 0.01)}),
        ("Rate +1pt", {"debt_rate": p.debt_rate + 0.01}),
        ("1-year delay", {"construction_years": p.construction_years + 1}),
    ]
    rows = []
    for label, ch in scenarios:
        m = model(replace(p, **ch)) if ch else r
        rows.append([label, m.project_irr, m.equity_irr, m.min_dscr, m.debt, m.equity_npv])

    suggestions = _suggest(p, r, breakeven_price, rows)
    hurdle_ok = (r.equity_irr or -1) >= p.cost_of_equity
    bankable = (r.min_dscr or 0) >= 1.20
    if hurdle_ok and bankable:
        verdict, tone = "INVEST", "good"
    elif bankable or hurdle_ok:
        verdict, tone = "RESTRUCTURE", "warn"
    else:
        verdict, tone = "DO NOT INVEST", "bad"
    note = (
        f"Equity IRR {_p(r.equity_irr)} vs {p.cost_of_equity:.0%} hurdle · minimum DSCR "
        f"{_x(r.min_dscr)} vs 1.20x lender comfort"
    )

    tiles = [
        Tile("Total project cost", r.total_cost, note=f"incl. {cur}{r.idc:,.0f} interest during construction"),
        Tile("Debt", r.debt, note=f"{r.debt / r.total_cost:.0%} gearing"),
        Tile("Equity", r.equity),
        Tile("Project IRR", r.project_irr, "pct", note="post-tax, unlevered"),
        Tile(
            "Equity IRR",
            r.equity_irr,
            "pct",
            tone="good" if hurdle_ok else "bad",
            note=f"hurdle {p.cost_of_equity:.0%}",
        ),
        Tile("Minimum DSCR", r.min_dscr, "x", tone="good" if bankable else "bad", note=f"average {_x(r.avg_dscr)}"),
        Tile("LLCR", r.llcr, "x"),
        Tile(
            "Equity NPV", r.equity_npv, note=f"at {p.cost_of_equity:.0%}", tone="good" if r.equity_npv >= 0 else "bad"
        ),
        Tile("Break-even price", breakeven_price, "price", note=f"per unit for {p.cost_of_equity:.0%} equity IRR"),
        Tile("Equity payback", r.payback_year, "int", note="operating years"),
    ]
    lbl = r.years
    charts = [
        Chart(
            "Revenue, opex and CFADS",
            "bars",
            labels=lbl,
            series={"Revenue": r.revenue, "Opex": r.opex, "CFADS": r.cfads},
        ),
        Chart(
            "Debt service coverage (DSCR)",
            "line",
            labels=lbl[: p.tenor],
            fmt="x",
            series={"DSCR": [x or 0.0 for x in r.dscr[: p.tenor]]},
            marker=1.20,
            marker_label="1.20x lender minimum",
        ),
        Chart(
            "Debt balance and debt service",
            "bars",
            labels=lbl,
            series={"Debt balance": r.debt_balance, "Debt service": r.debt_service},
        ),
        Chart(
            "Equity cash flows (cumulative)",
            "line",
            labels=[f"Build {i + 1}" for i in range(p.construction_years)] + lbl,
            series={"Cumulative equity cash": _cum(r.equity_flows)},
            marker=0.0,
            marker_label="Payback",
        ),
        Chart("Funding sources", "donut", labels=["Debt", "Equity"], series={"value": [r.debt, r.equity]}),
        Chart(
            "Equity IRR under stress",
            "range",
            fmt="pct",
            bars=[
                Bar(row[0], min(row[2] or 0, r.equity_irr or 0), max(row[2] or 0, r.equity_irr or 0), row[2])
                for row in rows[1:]
            ],
            marker=p.cost_of_equity,
            marker_label="Hurdle",
        ),
    ]
    cols = ["", *lbl]
    tables = [
        Table(
            "Operations",
            cols,
            [
                ["Revenue", *r.revenue],
                ["Opex", *[-x for x in r.opex]],
                ["EBITDA", *r.ebitda],
                ["Depreciation", *r.depreciation],
                ["Interest", *r.interest],
                ["Tax", *r.tax],
                ["CFADS", *r.cfads],
            ],
            ["money"] * 7,
        ),
        Table(
            "Debt schedule",
            cols,
            [
                ["Interest", *r.interest],
                ["Principal", *r.principal],
                ["Debt service", *r.debt_service],
                ["Closing balance", *r.debt_balance],
                ["DSCR", *r.dscr],
                ["Cash to equity", *r.equity_flows[p.construction_years :]],
            ],
            ["money"] * 4 + ["x", "money"],
        ),
        Table(
            "Sources and uses",
            ["", "Amount", "Share"],
            [
                ["Capex", p.capex, p.capex / r.total_cost],
                ["Interest during construction", r.idc, r.idc / r.total_cost],
                ["Total uses", r.total_cost, 1.0],
                ["Debt", r.debt, r.debt / r.total_cost],
                ["Equity", r.equity, r.equity / r.total_cost],
            ],
            ["text", "money", "pct"],
            by_column=True,
        ),
        Table(
            "Stress tests",
            ["Scenario", "Project IRR", "Equity IRR", "Min DSCR", "Debt", "Equity NPV"],
            rows,
            ["text", "pct", "pct", "x", "money", "money"],
            by_column=True,
        ),
    ]
    assumptions = [
        ["Construction years", p.construction_years, "int"],
        ["Operating years", p.operating_years, "int"],
        ["Capacity", p.capacity, "num"],
        ["Utilisation", p.utilisation, "pct"],
        ["Price per unit (yr 1)", p.price, "price"],
        ["Price escalation", p.price_escalation, "pct"],
        ["Gearing cap", p.gearing, "pct"],
        ["Debt rate", p.debt_rate, "pct"],
        ["Tenor", p.tenor, "int"],
        ["Repayment", p.repayment, "text"],
        ["Target DSCR", p.target_dscr, "x"],
        ["Tax rate", p.tax_rate, "pct"],
    ]
    steps = [
        "Commission an independent engineer's report and re-run the model on P90 (1-in-10 downside) output, "
        "the case lenders size debt on."
    ]
    if not bankable or (r.min_dscr or 0) < p.target_dscr:
        steps.append(
            "Restructure the debt: longer tenor, sculpted repayment or a debt service reserve account (DSRA) "
            "until minimum DSCR clears 1.20x in the downside case."
        )
    if not hurdle_ok and breakeven_price:
        steps.append(
            f"Negotiate the offtake price towards {_price(cur, breakeven_price)} per unit, or seek viability-gap "
            "funding, before committing equity."
        )
    else:
        steps.append(
            "Lock in the revenue with a long-term offtake / PPA and fix the construction price with a "
            "date-certain EPC contract."
        )
    steps += [
        "Approach 3-4 lenders with an information memorandum and this model; agree a term sheet "
        "(margin, tenor, DSCR covenants, reserve accounts).",
        "Hedge interest-rate risk with a swap from financial close and add the hedge cost to the model.",
        "Prepare the financial-close checklist: permits, land, insurance, model audit and lender due diligence.",
    ]
    return Report(
        kind="project",
        title=p.name,
        subtitle=f"Project finance · {p.construction_years}y build + {p.operating_years}y operations · {cur} {unit}",
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
        next_steps=steps,
        data={
            "equity_irr": r.equity_irr,
            "project_irr": r.project_irr,
            "min_dscr": r.min_dscr,
            "debt": r.debt,
            "llcr": r.llcr,
            "breakeven_price": breakeven_price,
        },
    )


def _cum(xs: list[float]) -> list[float]:
    out, s = [], 0.0
    for x in xs:
        s += x
        out.append(s)
    return out


def _p(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def _price(cur: str, x: float) -> str:
    return f"{cur}{x:,.4f}" if abs(x) < 10 else f"{cur}{x:,.2f}"


def _x(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}x"


def _suggest(p: ProjectInputs, r: ProjectResult, be: float | None, rows: list[list[Any]]) -> list[Suggestion]:
    out: list[Suggestion] = []
    cur, unit = p.currency, p.unit
    if r.min_dscr is not None and r.min_dscr < 1.20:
        out.append(
            Suggestion(
                "high",
                "Bankability",
                f"Minimum DSCR of {r.min_dscr:.2f}x is below the 1.20x lenders expect",
                "Lenders will cut debt or demand reserves; the financing may not close as structured.",
                [
                    "Extend the tenor or sculpt repayments to cash flow",
                    "Lower gearing",
                    "Add a debt service reserve account (6 months of debt service)",
                ],
            )
        )
    if r.debt < p.gearing * r.total_cost * 0.98:
        out.append(
            Suggestion(
                "medium",
                "Debt sizing",
                f"Cash flow, not gearing, limits debt to {r.debt / r.total_cost:.0%}",
                f"At a {p.target_dscr:.2f}x target DSCR the project supports {cur}{r.debt:,.0f} {unit} of debt, "
                f"below the {p.gearing:.0%} gearing cap.",
                ["Negotiate a longer tenor or lower target DSCR", "Raise the tariff or contract more volume"],
            )
        )
    if r.equity_irr is None or r.equity_irr < p.cost_of_equity:
        msg = f"Equity IRR of {_p(r.equity_irr)} misses the {p.cost_of_equity:.0%} hurdle"
        acts = ["Renegotiate EPC price or phasing", "Seek viability gap funding or a capital grant"]
        if be:
            acts.insert(0, f"Price needs to reach {_price(cur, be)} per unit (now {_price(cur, p.price)})")
        out.append(Suggestion("high", "Returns", msg, "As structured, equity does not earn its cost of capital.", acts))
    else:
        out.append(
            Suggestion(
                "low",
                "Returns",
                f"Equity IRR of {r.equity_irr:.1%} clears the {p.cost_of_equity:.0%} hurdle",
                f"Headroom: the price could fall to {_price(cur, be)} per unit before equity value is lost."
                if be
                else "Returns are above the hurdle.",
                ["Lock in the offtake price with a long-term contract"],
            )
        )
    if r.llcr is not None and r.llcr < 1.30:
        out.append(
            Suggestion(
                "medium",
                "Bankability",
                f"LLCR of {r.llcr:.2f}x is thin",
                "Lenders usually want loan-life coverage of at least 1.3x.",
                ["Reduce debt quantum"],
            )
        )
    worst = min(rows[1:], key=lambda row: row[2] if row[2] is not None else -1)
    out.append(
        Suggestion(
            "medium",
            "Risk",
            f"Biggest risk: {worst[0]}",
            f"It drops equity IRR to {_p(worst[2])} and minimum DSCR to {_x(worst[3])}.",
            [
                "Fixed-price, date-certain EPC contract"
                if "delay" in worst[0] or "Capex" in worst[0]
                else "Long-term offtake / PPA with floor price"
                if "Price" in worst[0] or "Utilisation" in worst[0]
                else "Hedge interest rates with a swap"
                if "Rate" in worst[0]
                else "O&M contract with performance guarantees"
            ],
        )
    )
    if r.payback_year and r.payback_year > p.operating_years * 0.6:
        out.append(
            Suggestion(
                "low",
                "Returns",
                f"Equity payback takes {r.payback_year} operating years",
                "Long paybacks increase exposure to policy and market changes.",
                ["Consider a partial refinancing after COD"],
            )
        )
    return sort_suggestions(out)
