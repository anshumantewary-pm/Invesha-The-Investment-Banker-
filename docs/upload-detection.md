# Automatic input detection

Uploaded Excel (every sheet), CSV or JSON files are read without a template:

1. Year columns are found (FY24, 2023-24, Mar-24, 2024, Q1FY24, Jan-24, M1…) and ordered chronologically.
2. Units such as "₹ in crore" or "$ in millions" are recognised.
3. Line items are classified by their Ind-AS / IFRS / US GAAP names (and startup MIS / project term sheet names).
4. The latest year is used, and assumptions are derived from history: EBITDA (PBT + D&A + finance costs when
   not reported), growth, D&A / capex / NWC as a share of revenue, effective tax rate, cost of debt, shares from
   EPS, and for startups ARPU, churn and CAC.
5. Every value is returned with a trace (found or calculated, and its source row); required inputs that could
   not be found are listed so the user only fills those in.
