# Invesha AutoModel

**Company in → financial model + valuation out.** A web platform for investment banking and corporate finance (CIB) that builds the full model, values the business, gives an investment view with suggestions, and lets you download the whole model as a live Excel workbook.

**Web platform:** https://anshumantewary-pm.github.io/Invesha-The-Investment-Banker-/

Everything runs in the browser (the Python engine is loaded with Pyodide), so nothing you enter leaves your machine.

## How it works

1. **Sign in** (or create an account, or continue as a guest).
2. **Pick a model**: company valuation, project finance or startup.
3. **Add your data**, either way:
   - **Upload** an Excel (.xlsx), CSV or JSON file: the platform's template, any simple two-column sheet (field, value), or an Invesha Excel model you downloaded earlier (edit it and upload it again). Percentages can be written as `18%`, `18` or `0.18`.
   - **Fill in manually** from a blank form (sensible defaults pre-filled) or a worked example.
4. **Review** the filled form, then **Build model** to get the report, charts and suggestions, and download the Excel model.

Your last inputs for each model are remembered per account, so you can continue where you left off.

> **About accounts:** the site is static (GitHub Pages), so accounts live on the device: passwords are stored as salted SHA-256 hashes in the browser and never sent anywhere. This separates users on a shared machine but is not server-grade authentication. Connecting a hosted auth service (e.g. Supabase or Firebase) would give real, cross-device accounts.

## Three models

| Model | What you enter | What you get |
|---|---|---|
| 🏦 **Company valuation** | Last year's revenue and EBITDA margin, growth and margin path, capex / D&A / working capital, debt, cash, shares and price, cost-of-capital inputs | 5-year income statement and unlevered free cash flow, WACC (CAPM, relevered sector beta), DCF by perpetuity growth and exit multiple, trading comparables (EV/EBITDA, EV/Revenue, P/E), LBO returns (IRR, MOIC), WACC × growth sensitivity, value-driver tornado, football field, **Buy / Hold / Reduce** call and corporate finance options (PE sale, IPO, debt raise, M&A) |
| 🏗️ **Project finance** | Capex, build and operating years, capacity, utilisation, price and escalation, fixed and variable opex, gearing, debt rate, tenor, target DSCR, hurdle rates | Operations and CFADS, debt sized to the lower of gearing and DSCR capacity, sculpted or annuity repayment with interest during construction, DSCR / LLCR, project and equity IRR and NPV, payback, break-even tariff, stress tests (price, capex, opex, utilisation, rates, delay), **Invest / Restructure / Do not invest** |
| 🚀 **Startup model** | Customers, new-customer growth, ARPU, churn, gross margin, CAC, team costs, cash and planned rounds | Monthly model to cash, runway, break-even month, funding gap, LTV/CAC, CAC payback, burn multiple, Rule of 40, VC-method valuation (post / pre-money, dilution), how much to raise and by when |

Each report has key-figure tiles, a verdict, **charts** (football field, grouped bars, line charts with covenant / break-even markers, EV-to-equity waterfall, donuts, tornado), a **sensitivity heatmap**, every model table, and **prioritised suggestions** with actions.

## Excel download

Every model has a **Download Excel model** button. The workbook contains:

- **Summary**: verdict, key figures, assumptions
- **Inputs**: blue cells you can edit
- **Live formula sheets**: change an input and the model recalculates
  - Company: `Model` (projections, FCFF, discounting) and `Valuation` (WACC, DCF both ways, comparables, a live WACC × growth grid)
  - Startup: `Monthly model` plus live runway, LTV/CAC and VC valuation
  - Project: `Cash flow model` with revenue, opex, CFADS, DSCR and IRRs as formulas (debt size comes from the engine's sculpting solve)
- All report tables and the **Suggestions**

The test suite recalculates the workbooks in LibreOffice and checks every formula against the engine.

## Run locally

```bash
pip install -e ".[dev]"
invesha example company > company.json
invesha company --file company.json --xlsx company.xlsx
```

`invesha project ...` and `invesha startup ...` work the same way; `--json` prints the full report. `invesha sectors` lists the sector reference data.

To try the web platform locally, build the wheel and serve `web/` with it:

```bash
python -m build --wheel && mkdir -p site && cp web/index.html dist/*.whl site/
printf '{"wheel": "%s", "version": "0.1.0"}' "$(basename dist/*.whl)" > site/manifest.json
python -m http.server -d site 8000
```

## Project layout

```
src/invesha/
  corporate.py   company model: projections, WACC, DCF, comps, LBO, suggestions
  project.py     project finance: debt sculpting, DSCR/LLCR, IRRs, stress tests
  startup.py     monthly startup model, unit economics, VC method
  excel.py       workbook builders (live formulas)
  inputs_io.py   read uploaded Excel / CSV / JSON inputs; make templates
  fields.py      input field definitions (form, templates, upload mapping)
  xlsx.py        dependency-free .xlsx writer
  sectors.py     indicative sector multiples, betas and ranges
  core.py        finance math, validation, report structures
  cli.py         command line
web/index.html   the web platform
```

No runtime dependencies. Python 3.10+.

## Notes

Sector multiples, betas and operating ranges are indicative screening values, not live market data; override them in the inputs. Results are analysis for discussion, not investment advice.
