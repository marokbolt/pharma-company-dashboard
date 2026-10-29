# Data Methodology — Nextyn Biopharma Company Monitor

This document is the step-by-step playbook for adding a company, refreshing a company,
or auditing the data in `company_monitor_dashboard.html`. It is written for someone with
no prior context on this project.

## 1. What this project is

A single self-contained HTML file (`company_monitor_dashboard.html`) covering 20
Nasdaq-listed biopharma companies, built entirely from each company's own SEC filings
(10-Q, 10-K, 8-K, 6-K, or 20-F). No market data, analyst estimates, or external sources
are used anywhere. The file has two layers:

- **Company Tearsheets tab** — one detailed 7-section dossier per company (profile,
  one-minute read, pipeline, trial results, financials, runway, numbered sources).
  This is the primary research layer; every card/table/quote in it carries a numbered
  citation into that company's own Sources list.
- **Comparative Dashboard** (Overview, Financial Capacity, Commercial & Revenue,
  Pipeline & Milestones, Strategic Developments, Pipeline Timeline, Compare) — a
  synthesis layer built *from* the tearsheet layer. Every filing-fact figure here
  carries a small clickable citation number that jumps to the exact source in the
  Company Tearsheets tab.

## 2. Adding or refreshing one company — step by step

### Step 1: Identify the company and its CIK
- Ticker → CIK lookup: `https://www.sec.gov/files/company_tickers.json`
- All SEC requests **must** send a `User-Agent` header identifying you, e.g.
  `"Nextyn Research <your-email>"`. Requests without one are frequently blocked or
  rate-limited.

### Step 2: Pull the filing list
- `https://data.sec.gov/submissions/CIK##########.json` (10-digit, zero-padded CIK)
  returns the company's recent filings, form types, and accession numbers.
- Identify the **most recent 10-Q** (or 10-K if between quarters) and **every 8-K
  filed since the prior quarter's filing** (or since the last review, on a refresh).
- Foreign private issuers (e.g. Pharming) file **20-F** annually and **6-K** for
  interim/event disclosures instead of 10-Q/8-K — check the filer type before
  assuming the US domestic cadence.

### Step 3: Fetch the actual documents
- `https://www.sec.gov/Archives/edgar/data/<cik>/<accession-no-dashes>/index.json`
  lists the documents inside a filing (the 10-Q itself, exhibit 99.1 press releases,
  R-pages for XBRL-tagged financial statement data).
- Read the filing's full text, not just the press release — guidance, risk factors,
  and footnotes rarely appear in the press release alone.

### Step 4: Fill the 7-section content spec (per `biotech-tearsheet/SKILL.md`)
1. **Profile** — what the company is, lead product(s)/platform, one paragraph.
2. **One-minute read** — 3-5 bullets, the single most important facts.
3. **Clinical pipeline** — every named program with mechanism, indication, status
   (quoting the company's own stage language), next step/date.
4. **Trial results** — only genuine readouts in the review window, with design
   (randomized/controlled vs. open-label), population size, and the actual
   numbers reported. Never fabricate a percentage or effect size.
5. **Financial summary** — income statement, balance sheet, cash flow, each with
   every subtotal independently re-added and checked against the filing.
6. **Runway** — see the runway formula below.
7. **Sources** — every filing referenced, with its exact SEC URL and accession
   number, numbered in citation order.

### Step 5: Runway math (when applicable)
Only compute a mechanical runway for companies that are genuinely burning cash
(operating-cash-flow negative). For cash-generative companies, say so explicitly
instead of forcing a meaningless "quarters of runway" number.

```
Calculated A (operating burn only) = Cash + investments ÷ (burn per quarter)
Calculated B (+ debt service)      = same, netting out scheduled near-term
                                      principal/interest payments
```
Always show management's own stated runway guidance (quoted verbatim) alongside
the calculated figure, and flag when they diverge and why.

### Step 6: Classify Stage, Hybrid, and economic model
These three fields are **analytical judgments**, not filing facts — they do not
get a numbered citation. The rules (see `US Biopharma Classification Framework`,
the framework this project follows):

- **Stage** = the status of the company's **lead asset only** — its single most
  advanced program, excluding anything discontinued. Categories, in order:
  Preclinical → Phase 1 → Phase 2 → Phase 3 → Under Review → Marketed: Recent
  Commercial → Marketed: Established → Cash shell / no lead asset.
  - Phase 1/2 trials are grouped with Phase 2; Phase 2/3 trials with Phase 3.
  - A marketed lead asset is **Established** only if the company also has
    *sustained positive operating cash flow* **and** more than one marketed
    product. Otherwise it is **Recent Commercial** — regardless of how many
    years the product has actually been on the market. This is a cash-flow
    test, not a calendar-time test.
- **Hybrid flag** (true/false) = the company has a marketed lead asset **and**
  a separate Phase-3-or-later asset that is *not* the lead. This is an overlay
  on top of Stage, never folded into the Stage label itself.
- **Economic-participation model** — tracked completely independently of Stage.
  A marketed, partnered product (e.g. CRISPR Therapeutics' CASGEVY, sold by
  Vertex) does not necessarily mean the company books direct product revenue.
  Categories: Direct product sales / Mixed model / Collaboration profit-loss
  sharing / Pre-revenue, primarily milestone-or-licensing funded.

### Step 7: Build the dashboard's DATA entry
Translate the tearsheet into the dashboard's `DATA` array entry (ticker, name, hq,
period, areas, modality, maturity/hybrid, econ, cash/revenue/debt/runway fields,
topDrugs, fyGuidance, pipeline summary fields, strategic developments, flags).
Every field here should be traceable back to a specific block in that company's
tearsheet section — see `PROVENANCE_NOTES.md` for exactly which tearsheet block
each dashboard field should cite.

### Step 8: Add PIPELINE rows
One row per named program: `{t, program, indication, stageNum, kind}`.
`stageNum` is the 0-7 index into `STAGE_LABELS` (same 8-stage system as Step 6,
applied per-program rather than per-company). `kind` is `active` / `done`
(approved) / `warn` (setback, e.g. missed endpoint or patent challenge under
appeal) / `stopped` (discontinued — still shown, but does not count toward the
company's lead-asset Stage).

### Step 9: Regenerate citations
Run `scripts/extract_citations.py` against the dashboard file. It parses the
`window.COMPANIES` tearsheet data and rebuilds the `CITATIONS` object (one entry
per ticker, per financial-statement/runway/pipeline/trial block) automatically —
do not hand-edit citation numbers. See `PROVENANCE_NOTES.md` for what each field
means and how to extend it if you add a new citable field.

### Step 10: QA before shipping
Run through `QA_CHECKLIST.md` in full before calling a refresh done.

## 3. Known conventions worth preserving
- **Never fabricate.** If a figure or date isn't disclosed, write "Not disclosed
  in filings reviewed" — never a zero, a guess, or an inferred number.
- **No chart for categorical status.** Pipeline stage is shown as a status badge
  quoting the company's own wording, never a fabricated progress-bar percentage.
- **No chart for 2-point comparisons.** Use a card/stat, not a bar chart, when
  there are only two things to compare.
- **Revenue growth is "not meaningful"** rather than a percentage when the
  prior-year base was zero (e.g. a wound-down collaboration).
