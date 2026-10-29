# QA Checklist — run this after every data refresh

Open `company_monitor_dashboard.html` directly in a browser (double-click, no
server needed) and work through this list. Takes about 10 minutes.

## 1. Console check
- [ ] Open DevTools console. Zero errors on load.
- [ ] Click through all 7 top-level views (Overview, the 4 Comparative Dashboard
      sub-tabs, Methodology & Sources, Company Tearsheets, Pipeline Timeline).
      Zero errors on any of them.

## 2. Citation integrity
- [ ] Run the broken-citation check from `PROVENANCE_NOTES.md` in the console.
      It should print nothing.
- [ ] Click 3-4 random citation superscripts across different tabs. Each should
      jump to Company Tearsheets, select the right company, and land on a
      source that is a real, clickable `sec.gov/Archives/edgar/...` URL.

## 3. Company count sanity
- [ ] Overview tile "Companies covered" reads 20.
- [ ] The 20-company comparison table has exactly 20 data rows (plus group
      headers).
- [ ] Company Tearsheets dropdown lists exactly 20 companies.
- [ ] Pipeline Timeline, with all companies selected, shows the expected total
      program count (126 as of this handover — update this number if you add
      companies or programs).

## 4. Spot-check figures against source filings
Pick 2-3 companies you did NOT just edit. For each:
- [ ] Open its Company Tearsheets entry. Confirm cash, revenue, and debt figures
      match what's shown in the Compare/Financial Capacity views for the same
      company (they're meant to be the same numbers, sourced from the same
      filing).
- [ ] Click through to the actual SEC filing via a citation link. Confirm the
      figure is genuinely in that filing.

## 5. Interactive features
- [ ] Search bar: type a partial ticker and a partial company name, confirm
      fuzzy results appear and clicking one opens that company's profile.
- [ ] Compare button: select 2 and then 3 companies, confirm the compare table
      renders with the nested pipeline-by-phase breakdown.
- [ ] Pipeline Timeline: toggle a few company chips off/on, confirm the matrix
      updates; click a stage header, confirm the phase modal lists all selected
      companies (with — for zero, not omission); click a drug name, confirm the
      program detail modal opens with working company/program switcher
      dropdowns.
- [ ] Comparative Dashboard dropdown: confirm all 4 sub-tabs are reachable and
      the dropdown button stays highlighted while any of them is active.

## 6. New-company addition (if applicable)
- [ ] New ticker appears everywhere a ticker should: search, Compare picker,
      Pipeline Timeline company filter, Company Tearsheets dropdown, the
      20-company Overview table, and all four Comparative Dashboard sub-tabs.
- [ ] New ticker's Stage/Hybrid/econ-model classification was derived using the
      rules in `DATA_METHODOLOGY.md`, not copied from a similar-looking company.
- [ ] `scripts/extract_citations.py` was re-run after adding the new company's
      tearsheet data, and its citations pass the broken-citation check above.

## 7. Before sending to anyone
- [ ] File opens cleanly from a fresh double-click (not just from a tab that was
      already open) — confirms there's no leftover browser state masking a bug.
- [ ] No internal process language leaked into the UI (check Overview,
      Methodology tab, and any tile/card notes for phrases like "this dashboard"
      or "per the rule" — those should read as a normal client-facing document,
      not a build log).
