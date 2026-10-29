# Nextyn Biopharma Company Monitor — Handover Package

## What you're getting

**`dashboard/company_monitor_dashboard.html`** — the deliverable. A single
self-contained HTML file covering 20 Nasdaq-listed biopharma companies: an
executive overview, four comparative views (Financial Capacity, Commercial &
Revenue, Pipeline & Milestones, Strategic Developments), a 2-3-company Compare
tool, a Pipeline Timeline (stage-by-company matrix), and a full per-company
tearsheet library — all built exclusively from each company's own SEC filings,
with every filing-fact figure carrying a clickable citation to its exact source.

Open it by double-clicking. No server, no install, no dependencies.

## Where to start

1. **Read `docs/DATA_METHODOLOGY.md` first** — how data is pulled, the 7-section
   tearsheet spec, the runway formula, and the Stage/Hybrid/econ-model
   classification rules. This is the thing you need before touching any data.
2. **`docs/PROVENANCE_NOTES.md`** — how the citation system works, what's cited
   vs. not and why, and how to extend it.
3. **`docs/QA_CHECKLIST.md`** — run this after any data refresh, before sending
   the file to anyone.
4. **`docs/KNOWN_GAPS.md`** — the blunt, internal version of what's not done,
   what's judgment-call, and what to watch for. Read this before you trust a
   number you didn't personally check.

## Folder structure

```
handover_package/
  README.md                        ← you are here
  dashboard/
    company_monitor_dashboard.html ← THE deliverable
  sources/
    dossiers/<TICKER>/content.md   ← raw research, 20 companies, source of
                                      truth for every figure in the dashboard
  docs/
    DATA_METHODOLOGY.md            ← SOP: how to pull & classify data
    PROVENANCE_NOTES.md            ← citation system reference
    QA_CHECKLIST.md                ← pre-ship checklist
    KNOWN_GAPS.md                  ← honest limitations
  scripts/
    secfc.py                       ← EDGAR fetch helper (catalog/menu/find/fetch)
    fetch_filings.py               ← bulk filing-date fetcher
    extract_citations.py           ← rebuilds the dashboard's CITATIONS object
                                      from the tearsheet data (run after any
                                      tearsheet edit)
```

## The 20 companies covered

ADMA Biologics (ADMA) · Ardelyx (ARDX) · Beam Therapeutics (BEAM) · CorMedix
(CRMD) · CRISPR Therapeutics (CRSP) · Fortress Biotech (FBIO) · Heron
Therapeutics (HRTX) · IDEAYA Biosciences (IDYA) · Janux Therapeutics (JANX) ·
Karyopharm Therapeutics (KPTI) · Kura Oncology (KURA) · Kymera Therapeutics
(KYMR) · MiMedx Group (MDXG) · Mirum Pharmaceuticals (MIRM) · Intellia
Therapeutics (NTLA) · Pharming Group (PHAR) · Relay Therapeutics (RLAY) ·
Scholar Rock (SRRK) · Tango Therapeutics (TNGX) · Travere Therapeutics (TVTX)

## What this is not

- Not an investment recommendation, stock screen, or company ranking — the
  dashboard explicitly avoids scoring, "winners/losers" labels, or an opaque
  health score, by design.
- Not automatically refreshing — see `KNOWN_GAPS.md` for what refresh would
  require.
- Not independently audited against every line of every filing — see
  `KNOWN_GAPS.md` for the actual verification depth.

## Forward path, if this grows

This was deliberately kept as a single static HTML file with inline data (no
server, no build step) to stay simple and portable. If this becomes a bigger,
ongoing product, the natural next step — not done here, intentionally scoped
out of this handover — is extracting the data model (`DATA`, `PIPELINE`,
`CITATIONS`, and the tearsheet's `window.COMPANIES`) into a clean JSON schema
that could seed a React + TypeScript frontend backed by Postgres. The data
shapes are already reasonably clean and would translate directly.
