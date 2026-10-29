# Known Gaps & Limitations — internal, blunt version

This is the internal counterpart to the dashboard's own Methodology tab, written
for whoever takes this over rather than for an external reader. Read this before
you trust any specific number too far.

## Data freshness
- All 20 companies are current as of their **Q2 2026 10-Q** (or equivalent) plus
  8-Ks/6-Ks through roughly **Oct 19–26, 2026**, per company (see each company's
  `period` field and its source list's filing dates). Nothing refreshes
  automatically. There is **no scheduled job** pulling new filings — this was
  explored (a biweekly cloud routine) but shelved because:
  - Cloud routines can only act on a GitHub repo or no files at all; this project
    lives on a local Desktop folder, not in git.
  - Standing this up would mean either (a) pushing the project to a repo so a
    cloud agent can clone/update/push it, or (b) a local scheduled task
    (Windows Task Scheduler) running Claude Code on a timer. Neither was set up.
  - **If you want automated refresh, that decision and setup is still open.**

## Verification depth
- Every financial subtotal was independently re-added and checked against the
  filing it came from, and every citation was spot-checked, but this was **not**
  a line-by-line audit of every disclosed number in every filing (e.g. every
  footnote, every segment breakout). Treat the headline figures (cash, revenue,
  debt, runway) as carefully checked; treat narrative color (bullets, strategic
  developments) as faithfully summarized but not independently re-derived from
  the primary source word-for-word.

## Classification judgment calls
The Stage/Hybrid/econ-model framework has a few genuinely debatable edges, applied
consistently but worth knowing about:
- **"Marketed: Recent" can apply to a years-old product.** Karyopharm's XPOVIO has
  been marketed since 2019 but reads "Marketed: Recent Commercial" because the
  company is operating-cash-flow negative and in active default — the framework's
  cash-flow test, not a calendar-time test, drives this. This is correct per the
  rule but can look surprising at a glance.
- **Phase 1/2 and Phase 2/3 trials are bucketed to the later phase.** A company
  whose only asset is in a true dose-escalation Phase 1/2 trial reads "Phase 2,"
  which slightly overstates maturity for trials still mostly in the Phase 1 part
  of that combined design.
- **"Cash shell / no lead asset"** is defined but currently has zero companies in
  it. Not tested against a real example — if you add a company that fits, double
  check the logic actually assigns it correctly.

## Combined-product rows (fixed, but check for recurrence)
Earlier versions of the Pipeline Timeline data compressed multiple distinct
marketed products into one row (e.g. ADMA's ASCENIV/BIVIGAM/NABI-HB counted as
2 rows instead of 3; CorMedix's KIMYRSA/ORBACTIV and MiMedx's AMNIOFIX/AMNIOEFFECT
had the same issue). These were found and fixed, but **this is a plausible class
of bug to recur** if a new company's marketed portfolio is entered as a single
slash-separated row instead of one row per product. Watch for `program:"X / Y"`
patterns in the PIPELINE array when adding a new company.

## Revenue/cash basis is not uniform across companies
- Some companies' "cash" figure is cash alone; others are cash + short-term
  investments; others are cash + all marketable securities (current and
  non-current). This is intentional — each company's own reported liquidity
  measure is preserved rather than forced into one definition — but it means
  **you cannot sum the "cash" column across companies** and get a meaningful
  total; the units aren't the same thing.
- Similarly, most companies report H1 2026 (six months), but Pharming reports
  on a half-yearly IFRS cycle that isn't perfectly calendar-aligned with the
  others' 10-Q periods.

## The two HTML files' relationship
- `biotech_tearsheets.html` (the original 20-company tearsheet file) and
  `company_monitor_dashboard.html` (the comparative dashboard) used to be
  separate files. The dashboard now embeds the full tearsheet tab inside itself
  (Company Tearsheets tab), so **`company_monitor_dashboard.html` is the single
  file to hand over** — `biotech_tearsheets.html` is now redundant/legacy and can
  be archived rather than maintained going forward.

## No automated tests
There is no test suite. `QA_CHECKLIST.md` is a manual process. If this project
grows meaningfully (more companies, more features), consider whether a headless
browser smoke test (checking console errors, citation integrity, and row counts
automatically) is worth building before manual QA becomes a bottleneck.

## Data is not centralized across files (deliberate, for now)
The dashboard's company data (`DATA`, `PIPELINE`, `CITATIONS`, and the tearsheet's
own `window.COMPANIES`) all live inline inside the one HTML file, duplicated in
spirit across the tearsheet layer and the dashboard layer (the dashboard's `DATA`
array is a hand-distilled summary of each tearsheet, not a live read of it). This
was a deliberate choice to keep everything in one double-click-able file rather
than requiring a server or build step. If this project grows into something
bigger (a real React + Postgres + TypeScript system, as discussed at handover),
the natural next step is extracting a clean JSON data model as the seed for that
— not yet done, scoped out of this handover intentionally.
