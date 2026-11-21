"""Input fields for each model: drives the web form, templates and file upload mapping."""

from __future__ import annotations

from typing import Any

# Each field: [key, label, type, hint]. Types: text, num, int, pct (fraction), x (multiple),
# sector, currency, select:a,b, list (comma-separated %), rounds (month=amount lines).
FORMS: dict[str, dict[str, Any]] = {
    "company": {
        "title": "Company valuation",
        "blurb": "Last year's figures plus a few assumptions. Percentages in %. All amounts in one unit "
        "(e.g. ₹ crore).",
        "groups": [
            [
                "Company",
                [
                    ["name", "Company name", "text"],
                    ["sector", "Sector", "sector"],
                    ["currency", "Currency", "currency"],
                    ["unit", "Amount unit", "text", "e.g. Cr, Mn"],
                    ["years", "Projection years", "int"],
                ],
            ],
            ["Last financial year", [["revenue", "Revenue", "num"], ["ebitda_margin", "EBITDA margin", "pct"]]],
            [
                "Growth and margins",
                [
                    ["growth_start", "Revenue growth, year 1", "pct"],
                    ["growth_end", "Revenue growth, final year", "pct", "fades linearly"],
                    ["growth", "Or growth per year", "list", "comma-separated %, overrides the fade"],
                    ["margin_target", "EBITDA margin, final year", "pct", "fades from today"],
                ],
            ],
            [
                "Operations",
                [
                    ["da_pct", "D&A, % of revenue", "pct"],
                    ["capex_pct", "Capex, % of revenue", "pct"],
                    ["nwc_pct", "Working capital, % of revenue", "pct"],
                    ["tax_rate", "Tax rate", "pct"],
                ],
            ],
            [
                "Balance sheet and market",
                [
                    ["debt", "Debt", "num"],
                    ["cash", "Cash", "num"],
                    ["interest_rate", "Cost of debt (pre-tax)", "pct"],
                    ["shares", "Shares outstanding", "num", "same unit basis as amounts"],
                    ["share_price", "Share price", "num", "for Buy / Hold / Reduce"],
                    ["invested_capital", "Invested capital", "num", "optional, for ROIC"],
                ],
            ],
            [
                "Cost of capital",
                [
                    ["risk_free", "Risk-free rate", "pct"],
                    ["equity_risk_premium", "Equity risk premium", "pct"],
                    ["beta", "Levered beta", "num", "blank = sector beta relevered"],
                    ["size_premium", "Size / specific premium", "pct"],
                    ["debt_weight", "Target debt weight D/(D+E)", "pct", "blank = from market cap"],
                ],
            ],
            [
                "Terminal value and LBO",
                [
                    ["terminal_growth", "Terminal growth", "pct"],
                    ["exit_multiple", "Exit EV/EBITDA", "x", "blank = sector mid"],
                    ["lbo_entry_multiple", "LBO entry EV/EBITDA", "x", "blank = sector mid"],
                    ["lbo_leverage", "LBO leverage (debt / EBITDA)", "x"],
                    ["lbo_interest_rate", "LBO interest rate", "pct"],
                ],
            ],
        ],
    },
    "project": {
        "title": "Project finance",
        "blurb": "An asset with a build period and years of operating cash flow: solar, wind, roads, "
        "plants, real estate. Percentages in %.",
        "groups": [
            [
                "Project",
                [
                    ["name", "Project name", "text"],
                    ["currency", "Currency", "currency"],
                    ["unit", "Amount unit", "text"],
                ],
            ],
            [
                "Asset and revenue",
                [
                    ["capex", "Capex", "num"],
                    ["construction_years", "Construction years", "int"],
                    ["operating_years", "Operating years", "int"],
                    ["capacity", "Capacity per year at 100%", "num", "units sold (MWh, tonnes…)"],
                    ["utilisation", "Utilisation / PLF", "pct"],
                    ["price", "Price per unit (year 1)", "num", "in amount unit per capacity unit"],
                    ["price_escalation", "Price escalation / year", "pct"],
                ],
            ],
            [
                "Costs and tax",
                [
                    ["opex_fixed", "Fixed opex / year", "num"],
                    ["opex_variable", "Variable opex / unit", "num"],
                    ["opex_escalation", "Opex escalation / year", "pct"],
                    ["tax_rate", "Tax rate", "pct"],
                    ["depreciation_years", "Depreciation years", "int", "blank = operating years"],
                ],
            ],
            [
                "Financing",
                [
                    ["gearing", "Maximum gearing", "pct"],
                    ["debt_rate", "Debt interest rate", "pct"],
                    ["tenor", "Debt tenor (years)", "int"],
                    ["repayment", "Repayment", "select:sculpted,annuity"],
                    ["target_dscr", "Target DSCR", "x"],
                ],
            ],
            [
                "Returns",
                [
                    ["discount_rate", "Project discount rate", "pct"],
                    ["cost_of_equity", "Equity hurdle (cost of equity)", "pct"],
                    ["terminal_value", "Residual value at end", "num"],
                ],
            ],
        ],
    },
    "startup": {
        "title": "Startup model",
        "blurb": "Monthly model from customers to cash. Amounts in one unit (e.g. ₹ lakh). Percentages in %.",
        "groups": [
            [
                "Startup",
                [
                    ["name", "Startup name", "text"],
                    ["sector", "Sector", "sector"],
                    ["currency", "Currency", "currency"],
                    ["unit", "Amount unit", "text", "e.g. L, K"],
                    ["months", "Months to model", "int"],
                ],
            ],
            [
                "Customers",
                [
                    ["starting_customers", "Customers today", "num"],
                    ["new_customers", "New customers in month 1", "num"],
                    ["new_customer_growth", "Growth in new customers / month", "pct"],
                    ["churn", "Monthly churn", "pct"],
                ],
            ],
            [
                "Pricing and costs",
                [
                    ["arpu", "Revenue per customer / month", "num"],
                    ["arpu_growth", "Price increase / year", "pct"],
                    ["gross_margin", "Gross margin", "pct"],
                    ["cac", "Cost to acquire a customer", "num"],
                    ["fixed_costs", "Team & overheads / month", "num"],
                    ["fixed_cost_growth", "Growth in team & overheads / month", "pct"],
                ],
            ],
            [
                "Cash and fundraising",
                [
                    ["cash", "Cash today", "num"],
                    ["funding", "Planned funding", "rounds", "one per line: month=amount"],
                    ["raise_amount", "Round being raised now", "num", "for pre-money and dilution"],
                    ["exit_multiple", "Exit ARR multiple", "x", "blank = sector mid"],
                    ["target_return", "VC target return", "x"],
                ],
            ],
        ],
    },
}

FORMS["merger"] = {
    "title": "M&A accretion / dilution",
    "blurb": "An acquirer buys a target at a premium, paying in stock, new debt and cash. Percentages in %. Amounts in one unit.",
    "groups": [
        [
            "Deal",
            [
                ["name", "Deal name", "text"],
                ["acquirer_name", "Acquirer name", "text"],
                ["target_name", "Target name", "text"],
                ["currency", "Currency", "currency"],
                ["unit", "Amount unit", "text"],
            ],
        ],
        [
            "Acquirer",
            [
                ["acquirer_net_income", "Acquirer net income (last year)", "num"],
                ["acquirer_shares", "Acquirer shares outstanding", "num"],
                ["acquirer_share_price", "Acquirer share price", "num"],
                ["acquirer_growth", "Acquirer net income growth", "pct"],
                ["acquirer_ebitda", "Acquirer EBITDA", "num", "optional, for leverage"],
                ["acquirer_net_debt", "Acquirer net debt", "num"],
            ],
        ],
        [
            "Target",
            [
                ["target_net_income", "Target net income (last year)", "num"],
                ["target_shares", "Target shares outstanding", "num"],
                ["target_share_price", "Target share price (undisturbed)", "num"],
                ["target_growth", "Target net income growth", "pct"],
                ["target_ebitda", "Target EBITDA", "num", "optional, for leverage"],
                ["target_net_debt", "Target net debt", "num"],
            ],
        ],
        [
            "Offer and financing",
            [
                ["premium", "Offer premium", "pct"],
                ["pct_stock", "Paid in stock", "pct"],
                ["pct_debt", "Paid with new debt", "pct", "the rest is cash"],
                ["cost_of_debt", "Cost of new debt", "pct"],
                ["interest_on_cash", "Interest forgone on cash", "pct"],
                ["fees_pct", "Fees, % of price", "pct"],
            ],
        ],
        [
            "Synergies and accounting",
            [
                ["synergies", "Run-rate synergies (pre-tax)", "num"],
                ["synergy_phase_in", "Synergies achieved in year 1", "pct"],
                ["integration_costs", "One-off integration costs", "num"],
                ["ppa_amortisation", "Intangibles amortisation / year", "num"],
                ["tax_rate", "Tax rate", "pct"],
            ],
        ],
    ],
}


# Extra names a column/row may use for a field (e.g. the labels on the Excel Inputs sheet).
ALIASES: dict[str, list[str]] = {
    "growth": ["Growth per year", "Revenue growth by year", "Growth path"],
    "margin_target": ["Target EBITDA margin", "Final EBITDA margin"],
    "revenue": ["Revenue (FY0)", "Sales", "Turnover", "Revenue last year"],
    "ebitda_margin": ["EBITDA margin (FY0)", "Margin"],
    "da_pct": ["D&A, % of revenue", "Depreciation % of revenue"],
    "capex_pct": ["Capex, % of revenue"],
    "nwc_pct": ["Net working capital, % of revenue", "NWC %"],
    "interest_rate": ["Pre-tax cost of debt", "Cost of debt", "Interest rate"],
    "shares": ["Shares outstanding", "Shares"],
    "beta": ["Levered beta", "Beta"],
    "size_premium": ["Size / specific risk premium"],
    "debt_weight": ["Debt weight D/(D+E)", "Debt weight"],
    "exit_multiple": ["Exit EV / EBITDA", "Exit multiple"],
    "capacity": ["Capacity per year at 100%", "Capacity"],
    "utilisation": ["Utilisation", "Utilization", "PLF"],
    "price": ["Price per unit (operating year 1)", "Price", "Tariff"],
    "price_escalation": ["Price escalation per year"],
    "opex_fixed": ["Fixed opex per year (year 1)", "Fixed opex"],
    "opex_variable": ["Variable opex per unit (year 1)", "Variable opex"],
    "opex_escalation": ["Opex escalation per year"],
    "cost_of_equity": ["Cost of equity (hurdle)", "Equity hurdle", "Cost of equity"],
    "discount_rate": ["Project discount rate", "Discount rate"],
    "starting_customers": ["Starting customers", "Customers"],
    "new_customers": ["New customers in month 1"],
    "new_customer_growth": ["Monthly growth in new customers"],
    "arpu": ["Monthly revenue per customer (ARPU)", "ARPU"],
    "arpu_growth": ["Yearly price increase"],
    "cac": ["Customer acquisition cost (CAC)", "CAC"],
    "fixed_costs": ["Team & overheads per month (month 1)", "Fixed costs", "Burn"],
    "fixed_cost_growth": ["Monthly growth in team & overheads"],
    "cash": ["Starting cash", "Cash"],
    "raise_amount": ["Round size being raised", "Raise amount"],
    "target_return": ["VC target return (money multiple)", "Target return"],
}


def fields(kind: str) -> list[list[str]]:
    return [f for _, group in FORMS[kind]["groups"] for f in group]
