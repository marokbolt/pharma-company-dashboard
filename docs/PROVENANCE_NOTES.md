# Provenance Notes — what's cited, what isn't, and why

## Two kinds of numbers in this dashboard

**Filing facts** — a specific figure, date, or quote taken directly from a specific
SEC filing. These carry a small clickable citation number (e.g. "$256.7M¹") that
jumps straight to the exact source in that company's Company Tearsheets entry.

**Derived / classified fields** — an analytical judgment applied *to* filing facts
(Stage, Hybrid flag, economic-participation model, disease-area tags, portfolio
concentration, "highest stage reached" phrasing). These are **not cited**, because
no single filing states them — they're read off the underlying facts using the
rules in `DATA_METHODOLOGY.md`. Citing them with a document page number would
overstate how directly sourced they are. If you want to check a derived field,
check the rule it was computed from, not a filing.

This project cites only filing facts, at block level, matching the convention
already used inside each company's own Company Tearsheets entry (one citation per
card, table heading, or quote — not one per individual number inside a multi-row
table).

## The CITATIONS object

`company_monitor_dashboard.html` contains a `CITATIONS` object, one entry per
ticker, with six fields:

| Field | What it points to | Dashboard fields it's used for |
|---|---|---|
| `income` | The tearsheet's income-statement financials block | Revenue, FY guidance |
| `balance` | The tearsheet's balance-sheet financials block | Cash position, debt/commitments |
| `cashflow` | The tearsheet's cash-flow-statement financials block | Operating cash flow direction/figure |
| `runway` | The tearsheet's runway quote/narrative | Runway guidance |
| `funding` | The tearsheet's runway `fundingBullets` block | Funding sources beyond operating cash |
| `pipeline` | The tearsheet's first pipeline-groups table | Highest stage reached |
| `trial` | The tearsheet's first trial-results block | Latest material event, next milestone |

Each value is an array of 1-based indices into that company's own numbered
Sources list (e.g. `balance:[1,3]` means "see sources 1 and 3 in this company's
tearsheet"). These are **not hand-typed** — they're extracted automatically from
the tearsheet's own existing `src:[...]` citations by `scripts/extract_citations.py`,
so they stay in sync with whatever the tearsheet actually cites. If you edit a
tearsheet's citations, re-run that script; don't hand-edit `CITATIONS` directly.

## How the click-through works

Every citable figure renders a small superscript number
(`<sup class="dcite" data-cite-ticker="..." data-cite-src="...">`). Clicking it:
1. Switches to the Company Tearsheets tab
2. Selects the right company in the dropdown
3. Scrolls to that exact numbered source in the tearsheet's Sources list (which
   is itself a working link to the SEC filing)

## Extending this system

If you add a new dashboard field that should be cited, you need:
1. A matching `src:[...]` already present on the relevant tearsheet block (card,
   table heading, or quote) — add it there first if it's missing.
2. A new key in the `CITATIONS` extraction logic in `extract_citations.py`
   pointing at that block.
3. A `cite(ticker, "yourNewField")` call wherever you render that dashboard value.

## What was explicitly left uncited, and why

- **Strategic Developments bullets** — matching the tearsheet's own convention,
  where narrative bullets (`bullets2`) are not individually cited either; only
  cards, tables, and quotes are. Citing every bullet would be sentence-level,
  which this project deliberately does not do.
- **Stage, Hybrid, economic model, disease areas, modality, portfolio
  concentration** — derived judgments, see above.
- **Program names and indications in the Pipeline Timeline matrix** — covered at
  the company level by the `pipeline`/`trial` citations already shown elsewhere
  for that company; not re-cited per cell to avoid visual clutter on a
  120+-row matrix.

## Verifying citation integrity

A broken citation is one whose index number doesn't exist in that company's own
Sources array. Check for this with:

```js
Object.keys(CITATIONS).forEach(function(t){
  var c = CITATIONS[t];
  Object.keys(c).forEach(function(field){
    c[field].forEach(function(n){
      var srcs = window.COMPANIES[t].sources;
      if (n < 1 || n > srcs.length) console.log("BROKEN:", t, field, n);
    });
  });
});
```
Run this in the browser console after any data refresh — it should print nothing.
