"""M&A accretion / dilution (merger model).

An acquirer buys a target at a premium, paying with a mix of new shares, new debt and cash
on hand. The model builds pro forma earnings for two years (synergies phased in, after-tax
financing costs, forgone interest on cash, purchase-price amortisation), compares pro forma
EPS with the acquirer's standalone EPS, and reports accretion / dilution, the synergies needed
to break even, ownership, contribution, pro forma leverage and a premium x stock-mix grid.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class MergerInputs:
    name: str
    acquirer_net_income: float
    acquirer_shares: float
    acquirer_share_price: float
    target_net_income: float
    target_shares: float
    target_share_price: float
    acquirer_name: str = "Acquirer"
    target_name: str = "Target"
    currency: str = "₹"
    unit: str = "Cr"
    acquirer_growth: float = 0.08  # net income growth
    target_growth: float = 0.10
    premium: float = 0.30
    pct_stock: float = 0.50
    pct_debt: float = 0.30  # the rest is cash on hand
    cost_of_debt: float = 0.09
    interest_on_cash: float = 0.05  # forgone yield on cash used
    tax_rate: float = 0.25
    synergies: float = 0.0  # run-rate pre-tax
    synergy_phase_in: float = 0.50  # share achieved in year 1 (100% in year 2)
    integration_costs: float = 0.0  # one-off, pre-tax, year 1 (shown separately)
    fees_pct: float = 0.02  # of equity purchase price, paid in cash
    ppa_amortisation: float = 0.0  # annual amortisation of acquired intangibles, pre-tax
    acquirer_ebitda: float | None = None
    target_ebitda: float | None = None
    acquirer_net_debt: float = 0.0
    target_net_debt: float = 0.0


@dataclass
class Deal:
    offer_price: float
    purchase_price: float
    fees: float
    stock: float
    debt: float
    cash: float
    new_shares: float
    pf_shares: float
    standalone_eps: list[float]
    pf_eps: list[float]
    accretion: list[float]
    pf_net_income: list[float]
    parts: list[dict[str, float]]
    target_ownership: float
    offer_pe: float | None
    acquirer_pe: float | None
    breakeven_synergies: float | None
    pf_leverage: float | None


def validate(p: MergerInputs) -> None:
    check(bool(str(p.name).strip()), "deal name is required")
    for label, v in (
        ("acquirer shares", p.acquirer_shares),
        ("acquirer share price", p.acquirer_share_price),
        ("target shares", p.target_shares),
        ("target share price", p.target_share_price),
    ):
        number(label, v, low=1e-9)
    number("acquirer net income", p.acquirer_net_income)
    number("target net income", p.target_net_income)
    for label, v, lo, hi in (
        ("premium", p.premium, -0.5, 3),
        ("stock %", p.pct_stock, 0, 1),
        ("debt %", p.pct_debt, 0, 1),
        ("cost of debt", p.cost_of_debt, 0, 0.4),
        ("interest on cash", p.interest_on_cash, 0, 0.3),
        ("tax rate", p.tax_rate, 0, 0.6),
        ("synergies", p.synergies, 0, None),
        ("phase-in", p.synergy_phase_in, 0, 1),
        ("integration costs", p.integration_costs, 0, None),
        ("fees %", p.fees_pct, 0, 0.2),
        ("amortisation", p.ppa_amortisation, 0, None),
        ("acquirer growth", p.acquirer_growth, -0.9, 3),
        ("target growth", p.target_growth, -0.9, 3),
    ):
        number(label, v, lo, hi)
    check(p.pct_stock + p.pct_debt <= 1.0 + 1e-9, "stock % plus debt % cannot exceed 100% (the rest is cash)")


def model(p: MergerInputs) -> Deal:
    t = p.tax_rate
    offer = p.target_share_price * (1 + p.premium)
    price = offer * p.target_shares
    fees = price * p.fees_pct
    stock, debt = price * p.pct_stock, price * p.pct_debt
    cash = price - stock - debt + fees
    new_shares = stock / p.acquirer_share_price
    pf_shares = p.acquirer_shares + new_shares
    std, pf, acc, ni_pf, parts = [], [], [], [], []
    for year in (1, 2):
        a = p.acquirer_net_income * (1 + p.acquirer_growth) ** year
        tg = p.target_net_income * (1 + p.target_growth) ** year
        syn = p.synergies * (p.synergy_phase_in if year == 1 else 1.0) * (1 - t)
        fin = (debt * p.cost_of_debt + cash * p.interest_on_cash + p.ppa_amortisation) * (1 - t)
        total = a + tg + syn - fin
        s_eps = a / p.acquirer_shares
        f_eps = total / pf_shares
        std.append(s_eps)
        pf.append(f_eps)
        acc.append(f_eps / s_eps - 1 if s_eps else 0.0)
        ni_pf.append(total)
        parts.append({"acquirer": a, "target": tg, "synergies": syn, "financing": fin})
    # pre-tax run-rate synergies that make year-1 EPS neutral
    y1 = parts[0]
    need_after_tax = std[0] * pf_shares - (y1["acquirer"] + y1["target"] - y1["financing"])
    phase = p.synergy_phase_in * (1 - t)
    breakeven = max(need_after_tax / phase, 0.0) if phase > 0 else None
    t_eps = p.target_net_income / p.target_shares
    a_eps = p.acquirer_net_income / p.acquirer_shares
    lev = None
    if p.acquirer_ebitda is not None and p.target_ebitda is not None:
        ebitda = p.acquirer_ebitda + p.target_ebitda + p.synergies
        nd = p.acquirer_net_debt + p.target_net_debt + debt + cash
        lev = nd / ebitda if ebitda > 0 else None
    return Deal(
        offer,
        price,
        fees,
        stock,
        debt,
        cash,
        new_shares,
        pf_shares,
        std,
        pf,
        acc,
        ni_pf,
        parts,
        new_shares / pf_shares,
        offer / t_eps if t_eps > 0 else None,
        p.acquirer_share_price / a_eps if a_eps > 0 else None,
        breakeven,
        lev,
    )


def analyse_inputs(data: dict[str, Any]) -> Report:
    return analyse(from_dict(MergerInputs, data))


def analyse(p: MergerInputs) -> Report:
    validate(p)
    d = model(p)
    cur, unit = p.currency, p.unit
    a1, a2 = d.accretion
    if a1 > 0.01:
        verdict, tone = "ACCRETIVE", "good"
    elif a1 < -0.01:
        verdict, tone = "DILUTIVE", "bad"
    else:
        verdict, tone = "BROADLY NEUTRAL", "warn"
    note = (
        f"Year-1 EPS {cur}{d.pf_eps[0]:,.2f} vs {cur}{d.standalone_eps[0]:,.2f} standalone ({a1:+.1%}); "
        f"year 2 {a2:+.1%}. {p.target_name} holders own {d.target_ownership:.0%} of the combined company."
    )

    premiums = [0.10, 0.20, 0.30, 0.40, 0.50]
    mixes = [0.0, 0.25, 0.50, 0.75, 1.0]
    grid = []
    for prem in premiums:
        row: list[Any] = [prem]
        for mix in mixes:
            debt_share = min(p.pct_debt, 1 - mix)
            row.append(model(replace(p, premium=prem, pct_stock=mix, pct_debt=debt_share)).accretion[0])
        grid.append(row)

    total_ni = d.parts[0]["acquirer"] + d.parts[0]["target"]
    contribution = d.parts[0]["target"] / total_ni if total_ni else 0.0
    bridge = [
        d.standalone_eps[0],
        d.parts[0]["acquirer"] / d.pf_shares - d.standalone_eps[0],
        d.parts[0]["target"] / d.pf_shares,
        d.parts[0]["synergies"] / d.pf_shares,
        -d.parts[0]["financing"] / d.pf_shares,
        d.pf_eps[0],
    ]
    tiles = [
        Tile("Year-1 accretion / (dilution)", a1, "pct", tone=tone),
        Tile("Year-2 accretion / (dilution)", a2, "pct", tone="good" if a2 > 0.01 else "bad" if a2 < -0.01 else "warn"),
        Tile("Pro forma EPS, year 1", d.pf_eps[0], "price", note=f"standalone {cur}{d.standalone_eps[0]:,.2f}"),
        Tile(
            "Offer price per share",
            d.offer_price,
            "price",
            note=f"{p.premium:.0%} premium to {cur}{p.target_share_price:,.2f}",
        ),
        Tile("Equity purchase price", d.purchase_price, note=f"+ fees {cur}{d.fees:,.1f}"),
        Tile("Breakeven synergies", d.breakeven_synergies, note="pre-tax run-rate for neutral year-1 EPS"),
        Tile("Target ownership", d.target_ownership, "pct", note=f"{d.new_shares:,.2f} new shares issued"),
        Tile(
            "Offer P/E vs acquirer P/E",
            f"{d.offer_pe:.1f}x vs {d.acquirer_pe:.1f}x" if d.offer_pe and d.acquirer_pe else "n/a",
            "text",
            note="all-stock deals accrete when the acquirer's P/E is higher",
        ),
    ]
    if d.pf_leverage is not None:
        tiles.append(
            Tile(
                "Pro forma net debt / EBITDA",
                d.pf_leverage,
                "x",
                tone="bad" if d.pf_leverage > 3.5 else "good" if d.pf_leverage < 2.5 else "warn",
            )
        )
    charts = [
        Chart(
            "EPS: standalone vs pro forma",
            "bars",
            labels=["Year 1", "Year 2"],
            fmt="price",
            series={"Standalone": d.standalone_eps, "Pro forma": d.pf_eps},
        ),
        Chart(
            "Year-1 EPS bridge",
            "waterfall",
            fmt="price",
            labels=["Standalone", "Issuance", "Target", "Synergies", "Financing", "Pro forma"],
            series={"value": bridge},
        ),
        Chart(
            "Consideration mix",
            "donut",
            labels=["New shares", "New debt", "Cash (incl. fees)"],
            series={"value": [d.stock, d.debt, d.cash]},
        ),
        Chart(
            "Pro forma ownership",
            "donut",
            labels=[f"{p.acquirer_name} holders", f"{p.target_name} holders"],
            series={"value": [p.acquirer_shares, d.new_shares]},
        ),
    ]
    tables = [
        Table(
            "Accretion / dilution",
            ["", "Year 1", "Year 2"],
            [
                [f"{p.acquirer_name} net income", d.parts[0]["acquirer"], d.parts[1]["acquirer"]],
                [f"{p.target_name} net income", d.parts[0]["target"], d.parts[1]["target"]],
                ["After-tax synergies", d.parts[0]["synergies"], d.parts[1]["synergies"]],
                [
                    "After-tax financing, forgone interest & amortisation",
                    -d.parts[0]["financing"],
                    -d.parts[1]["financing"],
                ],
                ["Pro forma net income", *d.pf_net_income],
                ["Pro forma shares", d.pf_shares, d.pf_shares],
                ["Pro forma EPS", *d.pf_eps],
                ["Standalone EPS", *d.standalone_eps],
                ["Accretion / (dilution)", *d.accretion],
            ],
            ["money"] * 5 + ["num", "price", "price", "pct"],
        ),
        Table(
            "Transaction summary",
            ["", "Value"],
            [
                ["Target share price", p.target_share_price],
                ["Premium", p.premium],
                ["Offer price per share", d.offer_price],
                ["Equity purchase price", d.purchase_price],
                ["Fees", d.fees],
                ["Paid in new shares", d.stock],
                ["Paid with new debt", d.debt],
                ["Paid from cash (incl. fees)", d.cash],
                ["New shares issued", d.new_shares],
                ["Offer P/E", d.offer_pe],
                ["Acquirer P/E", d.acquirer_pe],
                ["One-off integration costs (pre-tax, year 1)", p.integration_costs],
            ],
            ["price", "pct", "price", "money", "money", "money", "money", "money", "num", "x", "x", "money"],
        ),
        Table(
            "Contribution analysis",
            ["", p.acquirer_name, p.target_name],
            [
                ["Net income contribution", 1 - contribution, contribution],
                ["Pro forma ownership", 1 - d.target_ownership, d.target_ownership],
            ],
            ["pct", "pct"],
            note="If the target contributes more earnings than its holders receive in ownership, the deal favours the acquirer.",
        ),
        Table(
            "Year-1 accretion sensitivity: premium (rows) × % paid in stock (columns)",
            ["Premium \\ stock", *[f"{m:.0%}" for m in mixes]],
            grid,
            ["pct"] + ["pct"] * 5,
            by_column=True,
            note="Debt share is capped so stock + debt ≤ 100%; the remainder is cash.",
        ),
    ]
    out: list[Suggestion] = []
    if a1 < -0.01:
        acts = [
            f"Synergies need to reach {cur}{d.breakeven_synergies:,.0f} {unit} pre-tax run-rate (now {cur}{p.synergies:,.0f})"
            if d.breakeven_synergies is not None
            else "Increase synergies"
        ]
        if d.offer_pe and d.acquirer_pe and d.offer_pe > d.acquirer_pe and p.pct_stock > 0:
            acts.append(
                f"Use less stock: the target's offer P/E ({d.offer_pe:.1f}x) exceeds the acquirer's ({d.acquirer_pe:.1f}x)"
            )
        acts.append("Negotiate a lower premium")
        out.append(
            Suggestion(
                "high",
                "Accretion",
                f"The deal dilutes year-1 EPS by {-a1:.1%}",
                "Shareholders typically resist EPS-dilutive deals unless the strategic case is strong.",
                acts,
            )
        )
    elif a1 > 0.01:
        out.append(
            Suggestion(
                "low",
                "Accretion",
                f"The deal is {a1:.1%} accretive in year 1",
                "Accretion supports the case to shareholders; make sure it is not driven only by cheap debt.",
                ["Stress-test synergies at 50% delivery"],
            )
        )
    if p.synergies and d.breakeven_synergies is not None and d.breakeven_synergies > 0.8 * p.synergies:
        out.append(
            Suggestion(
                "medium",
                "Synergies",
                "Accretion depends on delivering most of the planned synergies",
                f"Breakeven needs {cur}{d.breakeven_synergies:,.0f} vs {cur}{p.synergies:,.0f} planned.",
                ["Build a synergy tracker with owners and milestones"],
            )
        )
    if p.premium > 0.40:
        out.append(
            Suggestion(
                "medium",
                "Price",
                f"A {p.premium:.0%} premium is above the typical 20-40% range",
                "High premiums raise the bar for value creation and invite shareholder scrutiny.",
                ["Justify with control value and synergies, or reduce the offer"],
            )
        )
    if d.target_ownership > 0.5:
        out.append(
            Suggestion(
                "high",
                "Structure",
                f"Target holders would own {d.target_ownership:.0%}",
                "The acquirer's shareholders would lose control: effectively a reverse takeover.",
                ["Increase the cash / debt share of consideration"],
            )
        )
    if d.pf_leverage is not None and d.pf_leverage > 3.5:
        out.append(
            Suggestion(
                "high",
                "Financing",
                f"Pro forma leverage of {d.pf_leverage:.1f}x net debt / EBITDA",
                "Above about 3.5x, rating agencies may downgrade and financing costs rise.",
                ["Use more stock", "Plan asset disposals to deleverage"],
            )
        )
    if contribution > d.target_ownership + 0.05:
        out.append(
            Suggestion(
                "low",
                "Value split",
                "The target contributes more earnings than its holders' ownership",
                f"{contribution:.0%} of combined earnings vs {d.target_ownership:.0%} ownership: favourable to the acquirer.",
                [],
            )
        )
    summary = [
        f"{p.acquirer_name} acquires {p.target_name} at {cur}{d.offer_price:,.2f} per share ({p.premium:.0%} premium), an equity "
        f"value of {cur}{d.purchase_price:,.0f} {unit}, paid {p.pct_stock:.0%} in stock, {p.pct_debt:.0%} debt and "
        f"{1 - p.pct_stock - p.pct_debt:.0%} cash.",
        f"Pro forma EPS is {cur}{d.pf_eps[0]:,.2f} in year 1 ({a1:+.1%}) and {cur}{d.pf_eps[1]:,.2f} in year 2 ({a2:+.1%}).",
        f"Breakeven synergies: {cur}{d.breakeven_synergies:,.1f} {unit} pre-tax run-rate."
        if d.breakeven_synergies is not None
        else "",
        f"{p.target_name} holders own {d.target_ownership:.0%} of the combined company and contribute {contribution:.0%} of earnings.",
    ]
    if d.pf_leverage is not None:
        summary.append(f"Pro forma leverage {d.pf_leverage:.1f}x net debt / EBITDA.")
    return Report(
        kind="merger",
        title=p.name,
        subtitle=f"M&A accretion / dilution · {p.acquirer_name} + {p.target_name} · {cur} {unit}",
        currency=cur,
        unit=unit,
        verdict=verdict,
        verdict_tone=tone,
        verdict_note=note,
        tiles=tiles,
        charts=charts,
        tables=tables,
        suggestions=sort_suggestions(out),
        summary=[x for x in summary if x],
        assumptions=[
            ["Premium", p.premium, "pct"],
            [
                "Stock / debt / cash",
                f"{p.pct_stock:.0%} / {p.pct_debt:.0%} / {1 - p.pct_stock - p.pct_debt:.0%}",
                "text",
            ],
            ["Cost of debt", p.cost_of_debt, "pct"],
            ["Tax rate", p.tax_rate, "pct"],
            ["Run-rate synergies", p.synergies, "money"],
        ],
        data={
            "accretion_y1": a1,
            "accretion_y2": a2,
            "pf_eps": d.pf_eps,
            "breakeven_synergies": d.breakeven_synergies,
            "target_ownership": d.target_ownership,
        },
    )
