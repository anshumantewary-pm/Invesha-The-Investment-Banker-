"""Build the downloadable Excel workbook for each model.

Every workbook has: Summary (verdict, key figures, assumptions), Inputs (blue cells you can
edit), live formula sheets for the model itself, the full report tables, and Suggestions.

* Company: Model and Valuation sheets are fully formula-driven (projections, FCFF, WACC,
  DCF both ways, comparables, and a live WACC x growth sensitivity grid).
* Startup: the monthly model is fully formula-driven, including runway and unit economics.
* Project: operations, CFADS, DSCR and IRRs are formulas; the debt size and repayment
  profile come from the engine's sculpting solve and are entered as values.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from invesha import corporate, project, startup
from invesha.core import Report, from_dict
from invesha.fields import fields
from invesha.inputs_io import _display, _lookup, _norm
from invesha.sectors import get_sector
from invesha.xlsx import (
    BOLD,
    DEC,
    FMT_STYLE,
    HEADER,
    IN_NUM,
    IN_PCT,
    INPUT_STYLE,
    INT,
    MULT,
    NOTE,
    NUM,
    PCT,
    TEXT,
    TITLE,
    TOTAL,
    TOTAL_PCT,
    Sheet,
    Workbook,
    col_letter,
)


def build(kind: str, data: dict[str, Any]) -> bytes:
    if kind == "company":
        return company_workbook(data)
    if kind == "project":
        return project_workbook(data)
    if kind == "startup":
        return startup_workbook(data)
    raise ValueError(f"unknown model {kind!r}")


# ---------------------------------------------------------------- shared sheets


def summary_sheet(wb: Workbook, report: Report) -> Sheet:
    s = wb.add("Summary")
    s.widths = {1: 34, 2: 22, 3: 48}
    s.set(1, 1, report.title, TITLE)
    s.set(2, 1, report.subtitle, NOTE)
    s.set(4, 1, "Verdict", BOLD)
    s.set(4, 2, report.verdict, BOLD)
    s.set(5, 1, report.verdict_note, TEXT)
    row = 7
    s.set(row, 1, "Key figures", HEADER)
    s.set(row, 2, "Value", HEADER)
    s.set(row, 3, "Note", HEADER)
    for t in report.tiles:
        row += 1
        s.set(row, 1, t.label)
        s.set(row, 2, t.value, FMT_STYLE.get(t.fmt, NUM) if not isinstance(t.value, str) else TEXT)
        s.set(row, 3, t.note, NOTE)
    row += 2
    s.set(row, 1, "Key assumptions", HEADER)
    s.set(row, 2, "", HEADER)
    for label, value, fmt in report.assumptions:
        row += 1
        s.set(row, 1, label)
        s.set(row, 2, value, FMT_STYLE.get(fmt, NUM) if not isinstance(value, str) else TEXT)
    row += 2
    s.set(
        row,
        1,
        f"Amounts in {report.currency} {report.unit}. Blue cells on the Inputs sheet can be "
        "edited; formula sheets recalculate.",
        NOTE,
    )
    s.set(row + 1, 1, "Indicative analysis for discussion, not investment advice.", NOTE)
    return s


def report_tables(wb: Workbook, report: Report, skip: tuple[str, ...] = ()) -> None:
    for table in report.tables:
        if table.title in skip:
            continue
        s = wb.add(table.title.split(":")[0])
        s.set(1, 1, table.title, TITLE)
        if table.note:
            s.set(2, 1, table.note, NOTE)
        for c, name in enumerate(table.columns, 1):
            s.set(4, c, name, HEADER)
        s.widths = {1: 34, **dict.fromkeys(range(2, len(table.columns) + 1), 14)}
        for r, row in enumerate(table.rows, 5):
            for c, value in enumerate(row, 1):
                if c == 1 and not table.by_column:
                    s.set(
                        r,
                        c,
                        value,
                        BOLD
                        if str(value).startswith(("Enterprise", "Equity", "Unlevered", "EBITDA", "CFADS", "Net income"))
                        else TEXT,
                    )
                    continue
                fmt = (
                    table.fmts[c - 1]
                    if table.by_column and c - 1 < len(table.fmts)
                    else table.fmts[r - 5]
                    if not table.by_column and r - 5 < len(table.fmts)
                    else "money"
                )
                s.set(r, c, value, FMT_STYLE.get(fmt, NUM) if not isinstance(value, str) else TEXT)
        s.freeze = (4, 1)


def suggestions_sheet(wb: Workbook, report: Report) -> None:
    s = wb.add("Suggestions")
    s.widths = {1: 10, 2: 18, 3: 60, 4: 80}
    s.set(1, 1, "Suggestions", TITLE)
    for c, h in enumerate(("Priority", "Area", "Suggestion", "Detail and actions"), 1):
        s.set(3, c, h, HEADER)
    row = 4
    for item in report.suggestions:
        s.set(row, 1, item.priority.upper(), BOLD)
        s.set(row, 2, item.area)
        s.set(row, 3, item.title, BOLD)
        s.set(row, 4, item.detail)
        for action in item.actions:
            row += 1
            s.set(row, 4, f"• {action}")
        row += 2


class Inputs:
    """An Inputs sheet that remembers where each named input lives."""

    def __init__(self, wb: Workbook, title: str) -> None:
        self.sheet = wb.add("Inputs")
        self.sheet.widths = {1: 38, 2: 16, 3: 50}
        self.sheet.set(1, 1, title, TITLE)
        self.sheet.set(2, 1, "Blue cells are inputs: change them and the model sheets recalculate.", NOTE)
        self.row = 3
        self.cells: dict[str, str] = {}

    def section(self, name: str) -> None:
        self.row += 2
        self.sheet.set(self.row, 1, name, HEADER)
        self.sheet.set(self.row, 2, "", HEADER)
        self.sheet.set(self.row, 3, "", HEADER)

    def add(self, key: str, label: str, value: Any, fmt: str = "money", note: str = "") -> str:
        self.row += 1
        self.sheet.set(self.row, 1, label)
        self.sheet.set(self.row, 2, value, INPUT_STYLE.get(fmt, IN_NUM))
        if note:
            self.sheet.set(self.row, 3, note, NOTE)
        self.cells[key] = self.sheet.addr(self.row, 2)
        return self.cells[key]

    def __getitem__(self, key: str) -> str:
        return self.cells[key]


def settings_section(ins: Inputs, kind: str, values: dict[str, Any]) -> None:
    """List every other model input so the workbook can be re-uploaded to the platform."""
    lookup = _lookup(kind)
    present = {
        lookup[_norm(value)][0]
        for (_row, col), (value, _style, _extra) in ins.sheet.cells.items()
        if col == 1 and isinstance(value, str) and _norm(value) in lookup
    }
    rest = [spec for spec in fields(kind) if spec[0] not in present and values.get(spec[0]) is not None]
    if not rest:
        return
    ins.section("Model settings (used when you re-upload this file to the platform)")
    for spec in rest:
        key, label, ftype = spec[0], spec[1], spec[2]
        fmt = {"pct": "pct", "x": "x", "int": "int", "num": "num"}.get(ftype, "text")
        value = _display(spec, values[key])
        ins.add(f"set_{key}", label, value, fmt if not isinstance(value, str) else "text")


# ---------------------------------------------------------------- company


def company_workbook(data: dict[str, Any]) -> bytes:
    p = from_dict(corporate.CompanyInputs, data)
    report = corporate.analyse(p)
    sector = get_sector(p.sector)
    proj = corporate.project(p)
    w = corporate.wacc(p, sector)
    exit_mult = p.exit_multiple or sector.ev_ebitda[1]
    d = corporate.dcf(proj, w.wacc, p.terminal_growth, exit_mult)
    n = p.years

    wb = Workbook()
    summary_sheet(wb, report)
    ins = Inputs(wb, f"{p.name}: inputs ({p.currency} {p.unit})")
    ins.section("Starting point (last financial year)")
    ins.add("revenue", "Revenue (FY0)", p.revenue)
    ins.add("margin0", "EBITDA margin (FY0)", p.ebitda_margin, "pct")
    ins.section("Operating assumptions")
    ins.add("tax", "Tax rate", p.tax_rate, "pct")
    ins.add("da", "D&A, % of revenue", p.da_pct, "pct")
    ins.add("capex", "Capex, % of revenue", p.capex_pct, "pct")
    ins.add("nwc", "Net working capital, % of revenue", p.nwc_pct, "pct", "Increase in NWC = % × increase in revenue")
    ins.section("Balance sheet and market")
    ins.add("debt", "Debt", p.debt)
    ins.add("cash", "Cash", p.cash)
    ins.add("rate", "Pre-tax cost of debt", p.interest_rate, "pct")
    if p.shares:
        ins.add("shares", "Shares outstanding", p.shares, "num", f"same unit basis as {p.unit}")
    if p.share_price:
        ins.add("price", "Share price", p.share_price, "num")
    ins.section("Cost of capital")
    ins.add("rf", "Risk-free rate", p.risk_free, "pct")
    ins.add("erp", "Equity risk premium", p.equity_risk_premium, "pct")
    ins.add(
        "beta",
        "Levered beta",
        w.beta,
        "num",
        "given" if p.beta is not None else f"{sector.name} unlevered beta {sector.unlevered_beta}, relevered",
    )
    ins.add("size", "Size / specific risk premium", p.size_premium, "pct")
    ins.add("wd", "Debt weight D/(D+E)", w.debt_weight, "pct")
    ins.section("Terminal value")
    ins.add("g", "Terminal growth", p.terminal_growth, "pct")
    ins.add("exit", "Exit EV / EBITDA", exit_mult, "x")
    ins.section(f"Trading multiples ({sector.name}, indicative)")
    ins.add("evebitda", "EV / EBITDA (mid)", sector.ev_ebitda[1], "x")
    ins.add("evrev", "EV / Revenue (mid)", sector.ev_revenue[1], "x")
    ins.add("pe", "P / E (mid)", sector.pe[1], "x")
    settings_section(ins, "company", asdict(p))

    # Model sheet
    m = wb.add("Model")
    m.widths = {1: 34, **dict.fromkeys(range(2, n + 3), 13)}
    m.freeze = (3, 1)
    m.set(1, 1, f"{p.name}: financial model ({p.currency} {p.unit})", TITLE)
    m.set(3, 1, "", HEADER)
    m.set(3, 2, "FY0", HEADER)
    for i in range(n):
        m.set(3, 3 + i, f"Y{i + 1}", HEADER)
    L = col_letter  # noqa: N806
    last = 2 + n
    R = {
        "growth": 4,
        "rev": 5,
        "margin": 6,
        "ebitda": 7,
        "da": 8,
        "ebit": 9,
        "int": 10,
        "pbt": 11,
        "tax": 12,
        "ni": 13,
        "nopat": 15,
        "da2": 16,
        "capex": 17,
        "dnwc": 18,
        "fcff": 19,
        "df": 20,
        "pv": 21,
    }
    labels = {
        "growth": "Revenue growth",
        "rev": "Revenue",
        "margin": "EBITDA margin",
        "ebitda": "EBITDA",
        "da": "D&A",
        "ebit": "EBIT",
        "int": "Interest",
        "pbt": "Profit before tax",
        "tax": "Tax",
        "ni": "Net income",
        "nopat": "NOPAT = EBIT × (1 − tax)",
        "da2": "+ D&A",
        "capex": "− Capex",
        "dnwc": "− Increase in working capital",
        "fcff": "Unlevered free cash flow (FCFF)",
        "df": "Discount factor",
        "pv": "PV of FCFF",
    }
    for k, r in R.items():
        m.set(r, 1, labels[k], BOLD if k in ("rev", "ebitda", "ni", "fcff") else TEXT)
    m.set(14, 1, "Free cash flow", BOLD)
    m.formula(R["rev"], 2, f"={ins['revenue']}", p.revenue)
    m.formula(R["margin"], 2, f"={ins['margin0']}", p.ebitda_margin, PCT)
    m.formula(R["ebitda"], 2, f"=B{R['rev']}*B{R['margin']}", p.revenue * p.ebitda_margin)
    for i in range(n):
        c, col, prev = 3 + i, L(3 + i), L(2 + i)
        m.set(R["growth"], c, proj.growth[i], IN_PCT)
        m.set(R["margin"], c, proj.margin[i], IN_PCT)
        m.formula(R["rev"], c, f"={prev}{R['rev']}*(1+{col}{R['growth']})", proj.revenue[i])
        m.formula(R["ebitda"], c, f"={col}{R['rev']}*{col}{R['margin']}", proj.ebitda[i], TOTAL)
        m.formula(R["da"], c, f"={col}{R['rev']}*{ins['da']}", proj.da[i])
        m.formula(R["ebit"], c, f"={col}{R['ebitda']}-{col}{R['da']}", proj.ebit[i])
        m.formula(R["int"], c, f"={ins['debt']}*{ins['rate']}", proj.interest[i])
        m.formula(R["pbt"], c, f"={col}{R['ebit']}-{col}{R['int']}", proj.ebt[i])
        m.formula(R["tax"], c, f"=MAX({col}{R['pbt']},0)*{ins['tax']}", proj.tax[i])
        m.formula(R["ni"], c, f"={col}{R['pbt']}-{col}{R['tax']}", proj.net_income[i], TOTAL)
        m.formula(R["nopat"], c, f"={col}{R['ebit']}-MAX({col}{R['ebit']},0)*{ins['tax']}", proj.nopat[i])
        m.formula(R["da2"], c, f"={col}{R['da']}", proj.da[i])
        m.formula(R["capex"], c, f"={col}{R['rev']}*{ins['capex']}", proj.capex[i])
        m.formula(R["dnwc"], c, f"=({col}{R['rev']}-{prev}{R['rev']})*{ins['nwc']}", proj.delta_nwc[i])
        m.formula(
            R["fcff"], c, f"={col}{R['nopat']}+{col}{R['da2']}-{col}{R['capex']}-{col}{R['dnwc']}", proj.fcff[i], TOTAL
        )
        m.formula(R["df"], c, f"=1/(1+'Valuation'!$B$13)^{i + 1}", d.discount_factors[i], DEC)
        m.formula(R["pv"], c, f"={col}{R['fcff']}*{col}{R['df']}", proj.fcff[i] * d.discount_factors[i])
    m.set(23, 1, "Blue rows (growth and margin by year) are inputs; everything else is a formula.", NOTE)

    # Valuation sheet
    v = wb.add("Valuation")
    v.widths = {1: 36, 2: 16, 3: 16, 4: 14, 5: 14, 6: 14, 7: 14}
    v.set(1, 1, f"{p.name}: valuation ({p.currency} {p.unit})", TITLE)
    v.set(3, 1, "Cost of capital", HEADER)
    v.set(3, 2, "", HEADER)
    rows = [
        ("Risk-free rate", f"={ins['rf']}", p.risk_free, PCT),
        ("Equity risk premium", f"={ins['erp']}", p.equity_risk_premium, PCT),
        ("Levered beta", f"={ins['beta']}", w.beta, DEC),
        ("Size / specific premium", f"={ins['size']}", p.size_premium, PCT),
        ("Cost of equity", "=B4+B6*B5+B7", w.cost_of_equity, PCT),
        ("Pre-tax cost of debt", f"={ins['rate']}", p.interest_rate, PCT),
        ("After-tax cost of debt", f"=B9*(1-{ins['tax']})", w.cost_of_debt_after_tax, PCT),
        ("Debt weight", f"={ins['wd']}", w.debt_weight, PCT),
    ]
    for i, (label, f, cached, style) in enumerate(rows, 4):
        v.set(i, 1, label)
        v.formula(i, 2, f, cached, style)
    v.set(12, 1, "")
    v.set(13, 1, "WACC", BOLD)
    v.formula(13, 2, "=(1-B11)*B8+B11*B10", w.wacc, TOTAL_PCT)

    fc = f"'Model'!$C${R['fcff']}:${L(last)}${R['fcff']}"
    pvs = f"SUM('Model'!C{R['pv']}:{L(last)}{R['pv']})"
    last_fcff = f"'Model'!{L(last)}{R['fcff']}"
    last_ebitda = f"'Model'!{L(last)}{R['ebitda']}"
    last_df = f"'Model'!{L(last)}{R['df']}"
    v.set(15, 1, "DCF", HEADER)
    v.set(15, 2, "Perpetuity growth", HEADER)
    v.set(15, 3, "Exit multiple", HEADER)
    net_debt = p.debt - p.cash
    dcf_rows = [
        ("PV of free cash flows", f"={pvs}", d.pv_fcff, f"={pvs}", d.pv_fcff, NUM),
        (
            "Terminal value",
            f"={last_fcff}*(1+{ins['g']})/(B13-{ins['g']})",
            d.tv_gordon,
            f"={last_ebitda}*{ins['exit']}",
            d.tv_exit,
            NUM,
        ),
        ("PV of terminal value", f"=B17*{last_df}", d.pv_tv_gordon, f"=C17*{last_df}", d.pv_tv_exit, NUM),
        ("Enterprise value", "=B16+B18", d.ev_gordon, "=C16+C18", d.ev_exit, TOTAL),
        ("− Net debt", f"={ins['debt']}-{ins['cash']}", net_debt, f"={ins['debt']}-{ins['cash']}", net_debt, NUM),
        ("Equity value", "=B19-B20", d.ev_gordon - net_debt, "=C19-C20", d.ev_exit - net_debt, TOTAL),
        (
            "Terminal value share of EV",
            "=B18/B19",
            d.pv_tv_gordon / d.ev_gordon if d.ev_gordon else None,
            "=C18/C19",
            d.pv_tv_exit / d.ev_exit if d.ev_exit else None,
            PCT,
        ),
    ]
    for i, (label, f1, c1, f2, c2, style) in enumerate(dcf_rows, 16):
        v.set(i, 1, label, BOLD if style == TOTAL else TEXT)
        v.formula(i, 2, f1, c1, style)
        v.formula(i, 3, f2, c2, style)
    row = 23
    if p.shares:
        v.set(row, 1, "Value per share", BOLD)
        v.formula(row, 2, f"=B21/{ins['shares']}", (d.ev_gordon - net_debt) / p.shares, TOTAL)
        v.formula(row, 3, f"=C21/{ins['shares']}", (d.ev_exit - net_debt) / p.shares, TOTAL)
        row += 1
        if p.share_price:
            v.set(row, 1, "Upside vs share price")
            v.formula(row, 2, f"=B23/{ins['price']}-1", (d.ev_gordon - net_debt) / p.shares / p.share_price - 1, PCT)
            v.formula(row, 3, f"=C23/{ins['price']}-1", (d.ev_exit - net_debt) / p.shares / p.share_price - 1, PCT)
            row += 1
    v.set(row, 1, "Blended enterprise value (average)", BOLD)
    v.formula(row, 2, "=AVERAGE(B19,C19)", d.ev, TOTAL)

    # Comparables
    row += 2
    v.set(row, 1, "Trading comparables (mid multiples)", HEADER)
    v.set(row, 2, "Metric", HEADER)
    v.set(row, 3, "Enterprise value", HEADER)
    v.set(row, 4, "Equity value", HEADER)
    ltm = p.revenue * p.ebitda_margin
    comps = [
        ("EV / EBITDA (LTM)", "='Model'!B7", ltm, ins["evebitda"]),
        ("EV / EBITDA (NTM)", "='Model'!C7", proj.ebitda[0], ins["evebitda"]),
        ("EV / Revenue (LTM)", "='Model'!B5", p.revenue, ins["evrev"]),
    ]
    for label, metric, mval, mult_ref in comps:
        row += 1
        v.set(row, 1, label)
        v.formula(row, 2, metric, mval)
        mult = sector.ev_ebitda[1] if "EBITDA" in label else sector.ev_revenue[1]
        v.formula(row, 3, f"=B{row}*{mult_ref}", mval * mult)
        v.formula(row, 4, f"=C{row}-({ins['debt']}-{ins['cash']})", mval * mult - net_debt)
    row += 1
    v.set(row, 1, "P / E (NTM net income)")
    v.formula(row, 2, "='Model'!C13", proj.net_income[0])
    v.formula(row, 4, f"=B{row}*{ins['pe']}", proj.net_income[0] * sector.pe[1])
    v.formula(row, 3, f"=D{row}+({ins['debt']}-{ins['cash']})", proj.net_income[0] * sector.pe[1] + net_debt)

    # Live sensitivity grid: equity value, perpetuity-growth DCF
    row += 3
    v.set(
        row - 1,
        1,
        "Sensitivity: equity value"
        + (" per share" if p.shares else "")
        + " (perpetuity growth DCF), WACC down × terminal growth across",
        BOLD,
    )
    v.set(row, 1, "WACC \\ g", HEADER)
    gs = [-0.01, -0.005, 0.0, 0.005, 0.01]
    for j, dg in enumerate(gs):
        v.formula(row, 2 + j, f"={ins['g']}+({dg})", p.terminal_growth + dg, PCT)
    years_idx = f"(COLUMN({fc})-COLUMN('Model'!$B${R['fcff']}))"
    for i, dw in enumerate(gs):
        r = row + 1 + i
        rate = w.wacc + dw
        v.formula(r, 1, f"=$B$13+({dw})", rate, PCT)
        for j, dg in enumerate(gs):
            g = p.terminal_growth + dg
            cell_r, cell_g = f"$A{r}", f"{col_letter(2 + j)}${row}"
            expr = (
                f"=SUMPRODUCT({fc}/(1+{cell_r})^{years_idx})"
                f"+{last_fcff}*(1+{cell_g})/({cell_r}-{cell_g})/(1+{cell_r})^{n}"
                f"-({ins['debt']}-{ins['cash']})"
            )
            if p.shares:
                expr = f"=({expr[1:]})/{ins['shares']}"
            try:
                cached = corporate.dcf(proj, rate, g, exit_mult).ev_gordon - net_debt
                cached = cached / p.shares if p.shares else cached
            except Exception:
                cached = None
            v.formula(r, 2 + j, expr, cached, NUM)

    report_tables(wb, report, skip=("Income statement", "Free cash flow and discounting"))
    suggestions_sheet(wb, report)
    return wb.to_bytes()


# ---------------------------------------------------------------- startup


def startup_workbook(data: dict[str, Any]) -> bytes:
    p = from_dict(startup.StartupInputs, data)
    report = startup.analyse(p)
    sim = startup.simulate(p)
    n = p.months
    wb = Workbook()
    summary_sheet(wb, report)
    ins = Inputs(wb, f"{p.name}: inputs ({p.currency} {p.unit})")
    ins.section("Customers and pricing")
    ins.add("c0", "Starting customers", p.starting_customers, "int")
    ins.add("new", "New customers in month 1", p.new_customers, "num")
    ins.add("newg", "Monthly growth in new customers", p.new_customer_growth, "pct")
    ins.add("arpu", "Monthly revenue per customer (ARPU)", p.arpu)
    ins.add("arpug", "Yearly price increase", p.arpu_growth, "pct")
    ins.add("churn", "Monthly churn", p.churn, "pct")
    ins.section("Costs")
    ins.add("gm", "Gross margin", p.gross_margin, "pct")
    ins.add("cac", "Customer acquisition cost (CAC)", p.cac)
    ins.add("fixed", "Team & overheads per month (month 1)", p.fixed_costs)
    ins.add("fixedg", "Monthly growth in team & overheads", p.fixed_cost_growth, "pct")
    ins.section("Cash and valuation")
    ins.add("cash", "Starting cash", p.cash)
    lo, mid, hi = get_sector(p.sector).arr_multiple
    ins.add("mult", "Exit ARR multiple", p.exit_multiple or mid, "x")
    ins.add("ret", "VC target return (money multiple)", p.target_return, "x")
    ins.add("raise", "Round size being raised", p.raise_amount)
    settings_section(ins, "startup", asdict(p))

    m = wb.add("Monthly model")
    m.freeze = (3, 1)
    m.widths = {1: 30, **dict.fromkeys(range(2, n + 3), 11)}
    m.set(1, 1, f"{p.name}: monthly model ({p.currency} {p.unit})", TITLE)
    m.set(3, 1, "Month", HEADER)
    m.set(3, 2, "Start", HEADER)
    rows = {
        "new": 4,
        "churned": 5,
        "cust": 6,
        "arpu": 7,
        "mrr": 8,
        "gp": 9,
        "mkt": 10,
        "fixed": 11,
        "ebitda": 12,
        "fund": 13,
        "cash": 14,
    }
    names = {
        "new": "New customers",
        "churned": "Churned customers",
        "cust": "Customers",
        "arpu": "ARPU",
        "mrr": "MRR (revenue)",
        "gp": "Gross profit",
        "mkt": "Marketing (new × CAC)",
        "fixed": "Team & overheads",
        "ebitda": "EBITDA (burn if negative)",
        "fund": "Funding received (input)",
        "cash": "Closing cash",
    }
    for k, r in rows.items():
        m.set(r, 1, names[k], BOLD if k in ("cust", "mrr", "ebitda", "cash") else TEXT)
    m.formula(rows["cust"], 2, f"={ins['c0']}", p.starting_customers, INT)
    m.formula(rows["cash"], 2, f"={ins['cash']}", p.cash)
    for i in range(n):
        c, col, prev, t = 3 + i, col_letter(3 + i), col_letter(2 + i), i + 1
        m.set(3, c, t, HEADER)
        m.formula(rows["new"], c, f"={ins['new']}*(1+{ins['newg']})^({t}-1)", sim.new[i], INT)
        m.formula(rows["churned"], c, f"={prev}{rows['cust']}*{ins['churn']}", sim.churned[i], INT)
        m.formula(
            rows["cust"], c, f"={prev}{rows['cust']}+{col}{rows['new']}-{col}{rows['churned']}", sim.customers[i], INT
        )
        m.formula(
            rows["arpu"],
            c,
            f"={ins['arpu']}*(1+{ins['arpug']})^INT(({t}-1)/12)",
            p.arpu * (1 + p.arpu_growth) ** ((t - 1) // 12),
            DEC,
        )
        m.formula(rows["mrr"], c, f"={col}{rows['cust']}*{col}{rows['arpu']}", sim.mrr[i])
        m.formula(rows["gp"], c, f"={col}{rows['mrr']}*{ins['gm']}", sim.gross_profit[i])
        m.formula(rows["mkt"], c, f"={col}{rows['new']}*{ins['cac']}", sim.marketing[i])
        m.formula(rows["fixed"], c, f"={ins['fixed']}*(1+{ins['fixedg']})^({t}-1)", sim.fixed[i])
        m.formula(
            rows["ebitda"], c, f"={col}{rows['gp']}-{col}{rows['mkt']}-{col}{rows['fixed']}", sim.ebitda[i], TOTAL
        )
        m.set(rows["fund"], c, sim.funding[i], IN_NUM)
        m.formula(
            rows["cash"], c, f"={prev}{rows['cash']}+{col}{rows['ebitda']}+{col}{rows['fund']}", sim.cash[i], TOTAL
        )
    last = col_letter(2 + n)
    cash_rng = f"C{rows['cash']}:{last}{rows['cash']}"
    month_rng = f"C3:{last}3"
    k = 17
    m.set(k, 1, "Key metrics (live)", HEADER)
    m.set(k, 2, "", HEADER)
    d = report.data
    ltv = p.arpu * p.gross_margin / p.churn if p.churn else None
    metrics = [
        ("Ending ARR", f"={last}{rows['mrr']}*12", d["arr_end"], NUM),
        ("Lowest cash balance", f"=MIN({cash_rng})", min(sim.cash), NUM),
        (
            "Runway (months)",
            f'=IFERROR(INDEX({month_rng},MATCH(TRUE,INDEX({cash_rng}<0,0),0))-1,"Full plan")',
            d["runway"] if d["runway"] is not None else "Full plan",
            INT,
        ),
        ("LTV", f"={ins['arpu']}*{ins['gm']}/{ins['churn']}", ltv, NUM),
        ("LTV / CAC", f"=B21/{ins['cac']}", (ltv / p.cac) if ltv and p.cac else None, MULT),
        (
            "CAC payback (months)",
            f"={ins['cac']}/({ins['arpu']}*{ins['gm']})",
            p.cac / (p.arpu * p.gross_margin) if p.arpu * p.gross_margin else None,
            DEC,
        ),
        ("Exit value (ARR × multiple)", f"=B18*{ins['mult']}", d["arr_end"] * (p.exit_multiple or mid), NUM),
        ("Post-money today (VC method)", f"=B24/{ins['ret']}", d["post_money"], TOTAL),
        ("Pre-money today", f"=B25-{ins['raise']}", d["post_money"] - p.raise_amount, NUM),
    ]
    for i, (label, f, cached, style) in enumerate(metrics, k + 1):
        m.set(i, 1, label)
        m.formula(i, 2, f, cached, style)
    report_tables(wb, report, skip=("Monthly model",))
    suggestions_sheet(wb, report)
    return wb.to_bytes()


# ---------------------------------------------------------------- project


def project_workbook(data: dict[str, Any]) -> bytes:
    p = from_dict(project.ProjectInputs, data)
    report = project.analyse(p)
    r = project.model(p)
    n, c = p.operating_years, p.construction_years
    wb = Workbook()
    summary_sheet(wb, report)
    ins = Inputs(wb, f"{p.name}: inputs ({p.currency} {p.unit})")
    ins.section("Asset and revenue")
    ins.add("capex", "Capex", p.capex)
    ins.add("cap", "Capacity per year at 100%", p.capacity, "num")
    ins.add("util", "Utilisation", p.utilisation, "pct")
    ins.add("price", "Price per unit (operating year 1)", p.price, "num")
    ins.add("pesc", "Price escalation per year", p.price_escalation, "pct")
    ins.section("Costs and tax")
    ins.add("ofix", "Fixed opex per year (year 1)", p.opex_fixed)
    ins.add("ovar", "Variable opex per unit (year 1)", p.opex_variable, "num")
    ins.add("oesc", "Opex escalation per year", p.opex_escalation, "pct")
    ins.add("tax", "Tax rate", p.tax_rate, "pct")
    ins.section("Returns")
    ins.add("ke", "Cost of equity (hurdle)", p.cost_of_equity, "pct")
    ins.add("dr", "Project discount rate", p.discount_rate, "pct")
    ins.section("Financing (sized by the engine; see note)")
    ins.add("debt", "Debt", r.debt, note="sculpted to the target DSCR, capped by gearing")
    ins.add("equity", "Equity", r.equity)
    ins.add("idc", "Interest during construction", r.idc)
    settings_section(ins, "project", asdict(p))

    s = wb.add("Cash flow model")
    s.freeze = (3, 1)
    s.widths = {1: 34, **dict.fromkeys(range(2, c + n + 3), 11)}
    s.set(1, 1, f"{p.name}: cash flow model ({p.currency} {p.unit})", TITLE)
    s.set(3, 1, "Period", HEADER)
    rows = {"rev": 4, "opex": 5, "ebitda": 6, "tax": 7, "cfads": 8, "ds": 9, "dscr": 10, "equity": 11, "project": 12}
    names = {
        "rev": "Revenue",
        "opex": "Opex",
        "ebitda": "EBITDA",
        "tax": "Tax (from engine)",
        "cfads": "CFADS",
        "ds": "Debt service (sculpted, from engine)",
        "dscr": "DSCR",
        "equity": "Equity cash flow",
        "project": "Project cash flow (unlevered, pre-tax)",
    }
    for k, row in rows.items():
        s.set(row, 1, names[k], BOLD if k in ("ebitda", "cfads", "equity") else TEXT)
    for i in range(c):
        col = 2 + i
        s.set(3, col, f"Build {i + 1}", HEADER)
        s.formula(rows["equity"], col, f"=-{ins['equity']}/{c}", -r.equity / c)
        s.formula(rows["project"], col, f"=-{ins['capex']}/{c}", -p.capex / c)
    for t in range(n):
        col = 2 + c + t
        L = col_letter(col)  # noqa: N806
        s.set(3, col, f"Op {t + 1}", HEADER)
        s.formula(rows["rev"], col, f"={ins['cap']}*{ins['util']}*{ins['price']}*(1+{ins['pesc']})^{t}", r.revenue[t])
        s.formula(
            rows["opex"],
            col,
            f"=({ins['ofix']}+{ins['ovar']}*{ins['cap']}*{ins['util']})*(1+{ins['oesc']})^{t}",
            r.opex[t],
        )
        s.formula(rows["ebitda"], col, f"={L}{rows['rev']}-{L}{rows['opex']}", r.ebitda[t], TOTAL)
        s.set(rows["tax"], col, r.tax[t], NUM)
        s.formula(rows["cfads"], col, f"={L}{rows['ebitda']}-{L}{rows['tax']}", r.cfads[t], TOTAL)
        s.set(rows["ds"], col, r.debt_service[t], NUM)
        s.formula(
            rows["dscr"],
            col,
            f'=IF({L}{rows["ds"]}>0,{L}{rows["cfads"]}/{L}{rows["ds"]},"")',
            r.dscr[t] if r.dscr[t] is not None else "",
            MULT,
        )
        tv = f"+{p.terminal_value}" if t == n - 1 and p.terminal_value else ""
        s.formula(rows["equity"], col, f"={L}{rows['cfads']}-{L}{rows['ds']}{tv}", r.equity_flows[c + t], TOTAL)
        s.formula(rows["project"], col, f"={L}{rows['ebitda']}{tv}", r.ebitda[t] + (p.terminal_value if tv else 0))
    last = col_letter(1 + c + n)
    first_op = col_letter(2 + c)
    k = 15
    s.set(k, 1, "Returns (live)", HEADER)
    s.set(k, 2, "", HEADER)
    metrics = [
        ("Equity IRR", f"=IRR(B{rows['equity']}:{last}{rows['equity']})", r.equity_irr, PCT),
        (
            "Equity NPV at hurdle",
            f"=NPV({ins['ke']},C{rows['equity']}:{last}{rows['equity']})+B{rows['equity']}",
            None,
            NUM,
        ),
        ("Minimum DSCR", f"=MIN({first_op}{rows['dscr']}:{last}{rows['dscr']})", r.min_dscr, MULT),
        ("Average DSCR", f"=AVERAGE({first_op}{rows['dscr']}:{last}{rows['dscr']})", r.avg_dscr, MULT),
        ("Pre-tax project IRR", f"=IRR(B{rows['project']}:{last}{rows['project']})", None, PCT),
    ]
    for i, (label, f, cached, style) in enumerate(metrics, k + 1):
        s.set(i, 1, label)
        s.formula(i, 2, f, cached, style)
    s.set(
        k + 7,
        1,
        "Revenue, opex, CFADS, DSCR and returns are formulas: change price, utilisation or opex on "
        "Inputs to see the effect. Debt size, interest and tax come from the engine's debt "
        "sculpting (re-run the model on the web platform to re-size debt).",
        NOTE,
    )
    report_tables(wb, report)
    suggestions_sheet(wb, report)
    return wb.to_bytes()
