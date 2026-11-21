"""Ready-made inputs for each model (used by the web app's "Load example" and the CLI)."""

from __future__ import annotations

from typing import Any

COMPANY: dict[str, Any] = {
    "name": "Northstar Components Ltd",
    "sector": "manufacturing",
    "currency": "₹",
    "unit": "Cr",
    "revenue": 1200.0,
    "ebitda_margin": 0.16,
    "years": 5,
    "growth_start": 0.18,
    "growth_end": 0.09,
    "margin_target": 0.19,
    "da_pct": 0.04,
    "capex_pct": 0.06,
    "nwc_pct": 0.12,
    "tax_rate": 0.25,
    "debt": 350.0,
    "cash": 90.0,
    "interest_rate": 0.095,
    "shares": 10.0,
    "share_price": 210.0,
    "risk_free": 0.07,
    "equity_risk_premium": 0.065,
    "terminal_growth": 0.05,
    "invested_capital": 900.0,
}

PROJECT: dict[str, Any] = {
    "name": "Sunfield 100 MW Solar Park",
    "currency": "₹",
    "unit": "Cr",
    "capex": 450.0,
    "construction_years": 1,
    "operating_years": 25,
    "capacity": 8760.0,  # lakh kWh a year at 100% (100 MW x 8,760 h)
    "utilisation": 0.22,
    "price": 0.03,  # Rs crore per lakh kWh (= Rs 3.00 per kWh)
    "price_escalation": 0.0,
    "opex_fixed": 6.0,
    "opex_variable": 0.0,
    "opex_escalation": 0.04,
    "tax_rate": 0.25,
    "gearing": 0.75,
    "debt_rate": 0.09,
    "tenor": 18,
    "repayment": "sculpted",
    "target_dscr": 1.30,
    "discount_rate": 0.10,
    "cost_of_equity": 0.14,
}

STARTUP: dict[str, Any] = {
    "name": "LedgerLoop (B2B SaaS)",
    "sector": "technology",
    "currency": "₹",
    "unit": "L",
    "months": 36,
    "starting_customers": 40,
    "new_customers": 25,
    "new_customer_growth": 0.07,
    "arpu": 0.25,
    "arpu_growth": 0.10,
    "churn": 0.025,
    "gross_margin": 0.78,
    "cac": 1.5,
    "fixed_costs": 28.0,
    "fixed_cost_growth": 0.025,
    "cash": 400.0,
    "funding": [{"month": 14, "amount": 1500.0}],
    "raise_amount": 1500.0,
    "target_return": 10.0,
}

EXAMPLES = {"company": COMPANY, "project": PROJECT, "startup": STARTUP}
