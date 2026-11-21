# Invesha AutoModel

**Company in → financial model, valuation and investment view out.** Invesha is a web platform for investment banking and corporate finance that builds bank-grade models from a company's figures or its uploaded financial statements, values the business several ways, gives a recommendation with next steps, and exports the whole model as a live, formula-driven Excel workbook. Invesha Academy teaches every concept from first principles to deal-desk level.

[![CI](https://github.com/anshumantewary-pm/Invesha-The-Investment-Banker-/actions/workflows/ci.yml/badge.svg)](https://github.com/anshumantewary-pm/Invesha-The-Investment-Banker-/actions/workflows/ci.yml)
![Version](https://img.shields.io/badge/version-0.2.0-ff6b2c)
![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)
![Dependencies](https://img.shields.io/badge/runtime%20dependencies-0-3ecf8e)
![License](https://img.shields.io/badge/license-Apache%202.0-lightgrey)

**[Open the platform](https://anshumantewary-pm.github.io/Invesha-The-Investment-Banker-/)** · **[Invesha Academy](https://anshumantewary-pm.github.io/Invesha-The-Investment-Banker-/tutorial.html)** · [Methodology](docs/methodology.md) · [Changelog](CHANGELOG.md)

Everything runs in the browser (the Python engine is loaded with Pyodide): nothing you enter or upload leaves your machine.

## At a glance

| | |
|---|---|
| **Models** | Company valuation · Project finance · Startup finance · M&A accretion / dilution |
| **Valuation toolkit** | DCF (perpetuity and exit), WACC, trading comparables, scenarios, Monte Carlo, reverse DCF, full LBO, credit profile, football field |
| **Data in** | Upload financial statements, a P&L, an MIS report or a term sheet in any layout (inputs detected automatically with a source trace), use the sample library, or fill in a guided form |
| **Output** | Verdict, executive summary, charts, sensitivity heatmaps, prioritised suggestions, recommended next steps, full model tables |
| **Excel** | Live-formula workbook for every model, verified by recalculating every formula in LibreOffice |
| **Academy** | 12 modules, 23 lessons, quizzes and a 92-term glossary, from the three statements to LBOs and project finance |
| **Quality** | 140 automated tests, 96%+ coverage, no runtime dependencies |

## What's in the platform

- **Four models**: company valuation, project finance, startup finance and M&A accretion / dilution.
- **Sample library**: 12 fictional companies, projects, startups and deals (BUY, HOLD and REDUCE cases, restructure and invest projects, accretive and dilutive deals), loadable in one click, plus sample financial-statement files to try the automatic upload.
- **Executive summary and recommended next steps** in every report, specific to the result: what a deal team would do next.
- **Accounts**: sign up with organisation, role and experience level; password strength check; profile and password changes; export or delete your data; **My models** to save, reopen, duplicate and delete named models. Beginners get "?" definitions on every input and links into the Academy.
- **Invesha Academy** (`tutorial.html`): every lesson explains the vocabulary, gives the formulas, works an example with the platform's numbers, adds a banker-level note and links to a live model ("Try it"). Module quizzes, a searchable glossary and progress tracking per account.

## How it works

1. **Sign in** (or create an account, or continue as a guest).
2. **Pick a model**: company valuation, project finance, startup or M&A.
3. **Add your data**, in any of three ways:
   - **Upload any spreadsheet**, no template needed: annual-report financial statements (P&L, balance sheet, cash flow), a management P&L, a monthly startup MIS or a project term sheet, as Excel (.xlsx, every sheet is scanned), CSV or JSON. The platform finds the year columns, recognises line items by their Ind-AS / IFRS / US GAAP names, takes the latest year and calculates the model's inputs: EBITDA (PBT + D&A + finance costs), revenue growth from history, D&A / capex / working capital as a share of revenue, effective tax rate, cost of debt, shares from EPS, and for startups ARPU, churn and CAC. It shows a **trace** of every value (found or calculated, with the source row) and lists only the inputs it could not find.
   - **Load a sample** from the library.
   - **Fill in manually** from a blank form (sensible defaults pre-filled) or a worked example.
4. **Review** the filled form, then **Build model** to get the report, charts, suggestions and next steps; save it to My models or download the Excel model.

> **About accounts:** the site is static (GitHub Pages), so accounts live on the device: passwords are stored as salted SHA-256 hashes in the browser and never sent anywhere. This separates users on a shared machine but is not server-grade authentication. Connecting a hosted auth service (e.g. Supabase or Firebase) would give real, cross-device accounts.

## Four models

| Model | What you enter | What you get |
|---|---|---|
| **Company valuation** | Last year's revenue and EBITDA margin, growth and margin path, capex / D&A / working capital, debt, cash, shares and price, cost-of-capital inputs (or upload the financial statements) | 5-year income statement and unlevered free cash flow, WACC, DCF (perpetuity growth and exit multiple), trading comparables, **bear / base / bull scenarios** with a probability-weighted value, **Monte Carlo** valuation range (P10-P90) and probability of exceeding the market price, **reverse DCF** (growth implied by the price), **full LBO** (sources & uses, senior amortising + junior debt, cash sweep, credit statistics by year, entry × exit IRR grid, returns attribution), **credit profile** with an indicative rating band, football field, executive summary, **Buy / Hold / Reduce** and corporate finance options |
| **Project finance** | Capex, build and operating years, capacity, utilisation, price and escalation, fixed and variable opex, gearing, debt rate, tenor, target DSCR, hurdle rates | Operations and CFADS, debt sized to the lower of gearing and DSCR capacity, sculpted or annuity repayment with interest during construction, DSCR / LLCR, project and equity IRR and NPV, payback, break-even tariff, stress tests (price, capex, opex, utilisation, rates, delay), **Invest / Restructure / Do not invest** |
| **Startup model** | Customers, new-customer growth, ARPU, churn, gross margin, CAC, team costs, cash and planned rounds | Monthly model to cash, runway, break-even month, funding gap, LTV/CAC, CAC payback, burn multiple, Rule of 40, VC-method valuation (post / pre-money, dilution), how much to raise and by when |
| **M&A accretion / dilution** | Acquirer and target net income, shares and prices, premium, stock / debt / cash mix, synergies and phase-in, fees, amortisation, optional EBITDA and net debt | Pro forma EPS for two years, accretion / dilution, breakeven synergies, offer vs acquirer P/E, ownership and contribution analysis, pro forma leverage, EPS bridge, premium × stock-mix sensitivity, **Accretive / Dilutive** verdict |

Each report has key-figure tiles, a verdict, **charts** (football field, grouped bars, line charts with covenant / break-even markers, EV-to-equity waterfall, donuts, tornado), a **sensitivity heatmap**, every model table, and **prioritised suggestions** with actions.

## Excel download

Every model has a **Download Excel model** button. The workbook contains:

- **Summary**: verdict, executive summary, next steps, key figures and assumptions
- **Inputs**: blue cells you can edit
- **Live formula sheets**: change an input and the model recalculates
  - Company: `Model` (projections, FCFF, discounting) and `Valuation` (WACC, DCF both ways, comparables, a live WACC × growth grid)
  - Startup: `Monthly model` plus live runway, LTV/CAC and VC valuation
  - Project: `Cash flow model` with revenue, opex, CFADS, DSCR and IRRs as formulas (debt size comes from the engine's sculpting solve)
  - M&A: `Accretion model` with pro forma EPS, accretion / dilution, breakeven synergies and ownership as formulas
- All report tables, the **Suggestions**, the executive summary and recommended next steps

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

## Command line

```bash
invesha samples                         # list the sample library
invesha example company:saas > in.json  # print a sample's inputs
invesha company --file in.json --xlsx model.xlsx
invesha merger --file deal.json --json  # full report as JSON
invesha sectors
```

## Documentation

- [Company valuation methodology](docs/methodology.md)
- [Project finance methodology](docs/project-finance.md)
- [M&A accretion / dilution](docs/merger-model.md)
- [Startup model](docs/startup-model.md)
- [Automatic input detection](docs/upload-detection.md)
- [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Security](SECURITY.md)

## Project layout

```
src/invesha/
  corporate.py   company model: projections, WACC, DCF, comps, suggestions
  advanced.py    scenarios, Monte Carlo, reverse DCF, detailed LBO, credit profile, executive summary
  merger.py      M&A accretion / dilution
  project.py     project finance: debt sculpting, DSCR/LLCR, IRRs, stress tests
  startup.py     monthly startup model, unit economics, VC method
  excel.py       workbook builders (live formulas)
  extract.py     automatic extraction from statements / MIS / term sheets, with a trace
  inputs_io.py   read uploaded Excel / CSV / JSON files
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
