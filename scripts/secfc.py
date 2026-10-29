#!/usr/bin/env python3
"""
secfc.py - SEC filing catalog + query-controlled extraction.

Commands (run with -h for options):
  catalog  TICKER                 Filing list with fiscal year/period, 8-K -> period matching
  menu     TICKER                 R-page menu (FilingSummary.xml) for selected filings
  find     TICKER --topic X       Rank menu pages for a topic; show pick + alternatives (no page download)
  fetch    TICKER --topic X       Download ONLY the picked pages, convert to markdown/CSV
  exhibits TICKER                 Earnings-release (8-K Item 2.02 / 7.01) exhibits, with --grep

Design rules:
  * Every network call is throttled (<= ~6 req/s) and cached on disk for the session.
  * Filing documents never change, so Archives files are cached forever; index JSON for 12h.
  * Output printed to the console is compact; full content goes to files under the cache dir.
"""
import argparse, csv, datetime as dt, gzip, io, json, os, re, sys, time, urllib.error, urllib.request

# ---------------------------------------------------------------------------
# CONFIG - the SEC requires a real contact in the User-Agent: "Name email@domain"
# Set it here once, or export SEC_USER_AGENT in the shell.
SEC_USER_AGENT = ""
# ---------------------------------------------------------------------------

CACHE = os.environ.get("SECFC_CACHE", os.path.join(os.getcwd(), "sec_cache"))
MIN_INTERVAL = 0.17          # seconds between requests (~6/s, below the SEC's 10/s ceiling)
INDEX_TTL = 12 * 3600        # seconds to trust cached submissions / companyconcept / tickers
PERIODIC = {"10-K", "10-Q", "10-KT", "10-QT"}
ANNUAL_FOREIGN = {"20-F", "40-F"}
CATALOG_FORMS = PERIODIC | ANNUAL_FOREIGN | {f + "/A" for f in PERIODIC | ANNUAL_FOREIGN} | {"8-K", "8-K/A", "6-K"}
FP_NEXT = {"Q1": "Q2", "Q2": "Q3", "Q3": "FY", "FY": "Q1"}

_last = [0.0]


def die(msg, code=2):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def user_agent():
    ua = os.environ.get("SEC_USER_AGENT") or SEC_USER_AGENT
    if not ua or "@" not in ua or "your.email" in ua.lower():
        die("SEC_USER_AGENT is not set. The SEC requires 'Name email@domain' in every request. "
            "Ask the user for the contact to use, then export SEC_USER_AGENT='Name email@domain' "
            "or set it at the top of scripts/secfc.py.")
    return ua


def http_get(url, ttl=None):
    """GET with throttle, retry and disk cache. ttl=None -> cache forever."""
    path = os.path.join(CACHE, "http", re.sub(r"^https?://", "", url).replace("?", "_"))
    if os.path.exists(path) and (ttl is None or time.time() - os.path.getmtime(path) < ttl):
        with open(path, "rb") as f:
            return f.read()
    ua = user_agent()
    for attempt in range(5):
        wait = MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)        # back off; never hammer the SEC
                continue
            if e.code == 403:
                die(f"403 from {url}. Either the SEC rejected the User-Agent or this environment's "
                    "network allowlist blocks sec.gov. Do not retry with other tools; tell the user.")
            raise
        except urllib.error.URLError as e:
            if attempt == 4:
                die(f"Network error for {url}: {e}. sec.gov may not be reachable from this environment.")
            time.sleep(2 ** attempt)
    die(f"Gave up on {url} after retries (rate limited?).")


def get_json(url, ttl=INDEX_TTL):
    data = http_get(url, ttl)
    return json.loads(data) if data else None


def soup(html):
    from bs4 import BeautifulSoup
    try:
        import lxml  # noqa: F401
        return BeautifulSoup(html, "lxml")
    except ImportError:
        return BeautifulSoup(html, "html.parser")


# ======================================================================
# 1. Company + filing catalog
# ======================================================================
def resolve(ticker_or_cik):
    t = ticker_or_cik.strip().upper()
    if t.isdigit():
        return int(t), t
    data = get_json("https://www.sec.gov/files/company_tickers.json")
    for row in data.values():
        if row["ticker"].upper() == t.replace(".", "-") or row["ticker"].upper() == t:
            return int(row["cik_str"]), row["title"]
    die(f"Ticker {t} not found in SEC company_tickers.json (delisted or renamed?). Pass the CIK number instead.")


def add_months(d, m):
    y, mo = divmod(d.month - 1 + m, 12)
    y += d.year
    mo += 1
    import calendar
    last = calendar.monthrange(y, mo)[1]
    day = last if d.day >= calendar.monthrange(d.year, d.month)[1] - 3 else min(d.day, last)
    return dt.date(y, mo, day)


def derive_fy_fp(period_end, fye_mmdd, form):
    """Fallback when dei facts are missing: fiscal year = the FYE on/after the period end."""
    if not period_end:
        return None, None
    pe = dt.date.fromisoformat(period_end)
    fm, fd = int(fye_mmdd[:2]), int(fye_mmdd[2:])
    fye_this = dt.date(pe.year, fm, min(fd, 28 if fm == 2 else fd))
    fy = pe.year if pe <= fye_this + dt.timedelta(days=7) else pe.year + 1
    if form.startswith(("10-K", "20-F", "40-F")):
        return fy, "FY"
    fye_prev = dt.date(fy - 1, fm, min(fd, 28 if fm == 2 else fd))
    q = round((pe - fye_prev).days / 91.3)
    return fy, {1: "Q1", 2: "Q2", 3: "Q3"}.get(q, f"Q{q}")


def build_catalog(tick, since_year):
    cik, title = resolve(tick)
    sub = get_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if not sub:
        die(f"No submissions JSON for CIK {cik}.")
    name, fye = sub.get("name", title), sub.get("fiscalYearEnd") or "1231"
    blocks = [sub["filings"]["recent"]]
    for f in sub["filings"].get("files", []):          # older filings live in extra pages
        if f.get("filingTo", "9999")[:4] >= str(since_year):
            blocks.append(get_json("https://data.sec.gov/submissions/" + f["name"]))
    rows = []
    for b in blocks:
        for i, form in enumerate(b["form"]):
            if form not in CATALOG_FORMS or b["filingDate"][i][:4] < str(since_year):
                continue
            items = b.get("items", [""] * len(b["form"]))[i] or ""
            if form.startswith("8-K") and not re.search(r"\b(2\.02|7\.01)\b", items):
                continue
            rows.append(dict(form=form, filed=b["filingDate"][i], report_date=b["reportDate"][i] or "",
                             accn=b["accessionNumber"][i], items=items, xbrl=b.get("isXBRL", [0] * 9999)[i],
                             primary=b["primaryDocument"][i]))
    # dei facts: fiscal year / period as tagged by the filer, keyed by accession (dedupe dual-class rows)
    dei = {}
    cc = get_json(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/dei/EntityCommonStockSharesOutstanding.json")
    if cc:
        for unit in cc["units"].values():
            for e in unit:
                dei.setdefault(e["accn"], (e.get("fy"), e.get("fp")))
    periods = []
    for r in rows:
        r["fy"], r["fp"], r["fy_source"], r["flag"] = "", "", "", ""
        if r["form"].startswith("8-K") or r["form"] == "6-K":
            continue
        dfy, dfp = derive_fy_fp(r["report_date"], fye, r["form"])
        if r["accn"] in dei and dei[r["accn"]][0]:
            r["fy"], r["fp"], r["fy_source"] = dei[r["accn"]][0], dei[r["accn"]][1], "dei"
            if dfy and (dfy != r["fy"] or dfp != r["fp"]):
                r["flag"] = f"dei fy/fp differs from date-derived {dfy}{dfp}; check"
        else:
            r["fy"], r["fp"], r["fy_source"] = dfy, dfp, "derived"
        if not r["form"].endswith("/A") and r["report_date"]:
            periods.append((r["report_date"], r["fy"], r["fp"], r["accn"], r["form"]))
    periods.sort()
    # extend with inferred upcoming periods so a fresh earnings release can be mapped before its 10-Q exists
    today = dt.date.today()
    if periods:
        pe, fy, fp = dt.date.fromisoformat(periods[-1][0]), periods[-1][1], periods[-1][2]
        if fp in FP_NEXT:
            while True:
                pe = add_months(pe, 3)
                fp = FP_NEXT[fp]
                fy = fy + 1 if fp == "Q1" else fy
                if pe >= today:
                    break
                periods.append((pe.isoformat(), fy, fp, "", "inferred"))
    for r in rows:
        if not (r["form"].startswith("8-K") or r["form"] == "6-K"):
            continue
        d = r["filed"]
        cands = [p for p in periods if p[0] < d]
        if not cands:
            r["flag"] = "no period before this filing"
            continue
        p = cands[-1]
        r["report_date"], r["fy"], r["fp"] = p[0], p[1], p[2]
        r["fy_source"] = "matched:" + (p[3] or "inferred(no 10-Q/10-K yet)")
        gap = (dt.date.fromisoformat(d) - dt.date.fromisoformat(p[0])).days
        kind = "earnings(2.02)" if "2.02" in r["items"] else ("reg-FD(7.01)" if "7.01" in r["items"] else "6-K")
        r["flag"] = kind + (f"; {gap}d after period end - may be mid-quarter update" if gap > 100 else "")
    rows.sort(key=lambda r: r["filed"], reverse=True)
    meta = dict(cik=cik, name=name, fye=fye, ticker=tick.upper(),
                filer=("foreign (20-F/40-F; interims on 6-K, usually no XBRL)" if any(r["form"] in ANNUAL_FOREIGN for r in rows)
                       else "domestic (10-K/10-Q)"))
    d = os.path.join(CACHE, f"CIK{cik:010d}")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "catalog.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["form"])
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump(meta, f)
    return meta, rows


def load_catalog(tick, since_year):
    return build_catalog(tick, since_year)


def select(rows, forms, last, fy=None, include_amend=False):
    want = set()
    for f in forms:
        want.add(f)
        if include_amend:
            want.add(f + "/A")
    sel = [r for r in rows if r["form"] in want]
    if fy:
        sel = [r for r in sel if str(r["fy"]) in [str(x) for x in fy]]
    return sel[:last] if last else sel


def accn_url(cik, accn):
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}"


# ======================================================================
# 2. R-page menu
# ======================================================================
def classify(longname):
    ln = longname.lower()
    if "(details" in ln: return "Details"
    if "(tables" in ln: return "Tables"
    if "(policies" in ln: return "Policies"
    if " - statement - " in ln: return "Statements"
    if " - document - " in ln: return "Cover"
    if " - disclosure - " in ln: return "Notes"
    return "Uncategorized"


def menu_for(cik, r):
    base = accn_url(cik, r["accn"])
    raw = http_get(base + "/FilingSummary.xml")
    if not raw:
        return [], "no FilingSummary.xml (pre-XBRL or non-XBRL filing)"
    x = raw.decode("utf-8", "ignore")
    out, note = [], ""
    for rep in re.findall(r"<Report\b.*?</Report>", x, re.S):
        g = lambda t: (re.search(rf"<{t}>(.*?)</{t}>", rep, re.S) or [None, ""])[1].strip()
        fn = g("HtmlFileName") or g("XmlFileName")
        if not fn:
            continue
        if fn.endswith(".xml"):
            note = "R pages are .xml (2009-2010 era); fetch supports only .htm"
        longname = g("LongName")
        cat = g("MenuCategory") or classify(longname)
        nm = re.sub(r"^\d+\s*-\s*(Statement|Disclosure|Document)\s*-\s*", "", longname)
        out.append(dict(accn=r["accn"], form=r["form"], fy=r["fy"], fp=r["fp"], report_date=r["report_date"],
                        R=fn.rsplit(".", 1)[0], category=cat, name=nm, url=f"{base}/{fn}"))
    return out, note


# ======================================================================
# 3. Topic finder
# ======================================================================
TOPICS = {
    # statement titles vary: plural/singular, US GAAP vs IFRS ("of income", "of operations", "profit or loss")
    "income": ["of income", "of earnings", "of operations", "income statement", "profit or loss"],
    "balance": ["balance sheet", "financial position", "financial condition"],
    "cashflow": ["cash flow"],
    "equity": ["changes in equity", "stockholders", "shareholders", "of equity"],
    "comprehensive": ["comprehensive income", "comprehensive earnings", "comprehensive loss"],
    "acquisitions": ["acquisition", "business combination", "purchase price", "acquired"],
    "divestitures": ["discontinued operation", "divestiture", "disposition", "held for sale"],
    "debt": ["debt", "borrowing", "notes payable", "credit facilit", "financing arrangement"],
    "revenue": ["revenue", "contract with customer", "disaggregat"],
    "segments": ["segment"],
    "tax": ["income tax", "taxes"],
    "leases": ["lease"],
    "goodwill": ["goodwill", "intangible"],
    "pension": ["pension", "retirement", "postretirement", "benefit plan"],
    "stockcomp": ["stock-based", "share-based", "stock based", "equity incentive", "stock compensation"],
    "eps": ["earnings per share", "net income per share", "earnings (loss) per share"],
    "inventory": ["inventor"],
    "ppe": ["property, plant", "property and equipment", "fixed asset"],
    "restructuring": ["restructuring"],
    "contingencies": ["contingenc", "commitments", "legal proceeding", "litigation"],
    "derivatives": ["derivative", "hedg", "financial instrument", "fair value"],
    "equity_actions": ["share repurchase", "treasury", "dividend", "capital stock"],
    "receivables": ["receivable", "credit loss", "allowance"],
    "accrued": ["accrued", "other liabilities", "warrant"],
}
STATEMENT_TOPICS = {"income", "balance", "cashflow", "equity", "comprehensive"}
CAT_WEIGHT = {
    "read":      {"Notes": 3, "Policies": 1, "Tables": 1, "Details": 0.5, "Statements": 2},
    "numbers":   {"Details": 3, "Statements": 3, "Tables": 1, "Notes": 1.5, "Policies": 0},
    "statement": {"Statements": 5},
}


def score(page, topic, purpose):
    name = page["name"].lower()
    if topic in TOPICS:
        terms = TOPICS[topic]
    else:
        terms = [t.strip().lower() for t in re.split(r"[,|]", topic) if t.strip()]
    hits = sum(1 for t in terms if t in name)
    if not hits:
        return 0
    # category fit (read -> Notes, numbers -> Details) dominates; keyword count only breaks ties,
    # otherwise long Details names that repeat the keyword would outrank the note itself
    s = CAT_WEIGHT[purpose].get(page["category"], 0) * 3 + min(hits, 2) + (1 if len(name) < 45 else 0)
    if "parenthetical" in name:
        s -= 4
    if topic in STATEMENT_TOPICS and page["category"] != "Statements":
        s -= 3
    if topic in ("income", "equity") and "comprehensive" in name:
        s -= 4                                   # "statements of comprehensive income" is not the P&L
    return s


def find_pages(menu, topic, purpose, top):
    by_filing = {}
    for p in menu:
        s = score(p, topic, purpose)
        if s > 0:
            by_filing.setdefault(p["accn"], []).append((s, p))
    res = []
    for accn, lst in by_filing.items():
        lst.sort(key=lambda x: (-x[0], int(re.sub(r"\D", "", x[1]["R"]) or 0)))
        res.append((accn, [p for _, p in lst[:top]], [p for _, p in lst[top:top + 3]]))
    return res


# ======================================================================
# 4. Page conversion
# ======================================================================
def table_to_md(tbl):
    rows = []
    for tr in tbl.find_all("tr"):
        cells = [c.get_text(" ", strip=True).replace("|", "/") for c in tr.find_all(["td", "th"])]
        merged = []
        for c in cells:            # glue lone '$' / '%' / ')' cells onto neighbours, drop empties
            if c in ("$", "€", "£") and merged is not None:
                merged.append(c); continue
            if c in ("%", ")") and merged:
                merged[-1] += c; continue
            if merged and merged[-1] in ("$", "€", "£"):
                merged[-1] = merged[-1] + c; continue
            merged.append(c)
        # drop spacer cells but keep a blank first column so headers / total rows stay aligned
        merged = merged[:1] + [c for c in merged[1:] if c]
        if any(merged):            # skip spacer rows that are entirely blank
            rows.append(merged)
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    lines = ["| " + " | ".join(r + [""] * (w - len(r))) + " |" for r in rows]
    lines.insert(1, "|" + "---|" * w)
    return "\n".join(lines)


def html_blocks(node):
    """Flatten HTML into ordered text paragraphs and markdown tables."""
    blocks = []
    for t in node.find_all("table"):
        if t.find_parent("table") is None or t.find_parent("table") is node:
            pass
    def walk(el):
        for ch in getattr(el, "children", []):
            name = getattr(ch, "name", None)
            if name == "table":
                md = table_to_md(ch)
                if md:
                    blocks.append(("table", md))
            elif name in ("p", "div", "span", "li", "h1", "h2", "h3", "h4", "font", "b", "i", "u") and ch.find("table") is None:
                txt = ch.get_text(" ", strip=True)
                if txt and (not blocks or blocks[-1] != ("text", txt)):
                    blocks.append(("text", txt))
            elif name:
                walk(ch)
            else:
                txt = str(ch).strip()
                if txt and len(txt) > 1:
                    blocks.append(("text", txt))
    walk(node)
    return blocks


def convert_r_page(html, page):
    """Return (markdown, csv_rows). Handles statements/details (fact rows) and notes (text blocks)."""
    s = soup(html)
    tbl = s.find("table", class_="report")
    if tbl is None:
        return f"(could not parse {page['url']})", []
    trs = tbl.find_all("tr", recursive=False) or tbl.find_all("tr")
    title_th = trs[0].find("th")
    title = title_th.get_text(" ", strip=True) if title_th else page["name"]
    scale = (re.search(r"in (Thousands|Millions|Billions)", title) or [None, "units as shown"])[1]
    head_rows = [tr for tr in trs if tr.find("th") and not tr.find("td")]
    groups, dates = [], []
    if head_rows:
        first = head_rows[0].find_all("th")[1:]
        for th in first:
            groups += [th.get_text(" ", strip=True)] * int(th.get("colspan", 1))
        if len(head_rows) > 1:
            dates = [th.get_text(" ", strip=True) for th in head_rows[1].find_all("th")]
    if dates and groups:
        cols = [f"{g} {d}".strip() for g, d in zip(groups, dates)] if len(groups) == len(dates) else dates
    else:
        cols = dates or groups
    md = [f"# {page['name']}", f"Source: {page['url']}  |  {page['form']} FY{page['fy']} {page['fp']}  |  {title}", ""]
    csv_rows, fact_lines = [], []
    for tr in trs:
        td = tr.find("td", class_="pl")
        if not td:
            continue
        a = td.find("a")
        tag = ""
        if a and a.get("onclick"):
            m = re.search(r"defref_([\w-]+)", a["onclick"])
            tag = m.group(1).replace("_", ":", 1) if m else ""
        label = td.get_text(" ", strip=True)
        cells = tr.find_all("td")[1:]
        if tag.endswith("TextBlock") or (cells and cells[0].find("table") is not None) or (cells and len(cells[0].get_text()) > 400):
            md.append(f"_[{label} - {tag}]_\n")
            for kind, b in html_blocks(cells[0]):
                md.append(b + "\n")
            continue
        vals = [c.get_text(" ", strip=True) for c in cells]
        if not any(vals):
            fact_lines.append(f"| **{label}** |" + " |" * len(cols))
            continue
        fact_lines.append(f"| {label} | " + " | ".join(vals) + " |")
        for i, v in enumerate(vals):
            if v:
                csv_rows.append(dict(accn=page["accn"], form=page["form"], fy=page["fy"], fp=page["fp"], R=page["R"],
                                     page=page["name"], label=label, tag=tag, column=cols[i] if i < len(cols) else f"col{i+1}",
                                     value=v, scale=scale, url=page["url"]))
    if fact_lines:
        md.append("| Line item | " + " | ".join(cols) + " |")
        md.append("|---|" + "---|" * max(len(cols), 1))
        md += fact_lines
    return "\n".join(md), csv_rows


# ======================================================================
# 5. 8-K exhibits
# ======================================================================
def exhibit_list(cik, accn):
    base = accn_url(cik, accn)
    raw = http_get(f"{base}/{accn}-index.htm")
    if not raw:
        return []
    s = soup(raw.decode("utf-8", "ignore"))
    out = []
    for t in s.find_all("table", class_="tableFile"):
        for tr in t.find_all("tr")[1:]:
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            a = tr.find("a")
            if len(tds) >= 4 and tds[3].upper().startswith("EX-99") and a:
                href = a["href"].replace("/ix?doc=", "")
                out.append(dict(type=tds[3], desc=tds[1], file=tds[2].split()[0], url="https://www.sec.gov" + href))
    return out


def exhibit_text(url):
    raw = http_get(url)
    if raw is None:
        return []
    if url.lower().endswith(".pdf"):
        p = os.path.join(CACHE, "http", re.sub(r"^https?://", "", url))
        try:
            import subprocess
            txt = subprocess.run(["pdftotext", "-layout", p, "-"], capture_output=True, text=True, timeout=120).stdout
            return [("text", para) for para in re.split(r"\n\s*\n", txt) if para.strip()]
        except Exception:
            return [("text", "(PDF exhibit; pdftotext not available - open the URL)")]
    s = soup(raw.decode("utf-8", "ignore"))
    body = s.body or s
    return html_blocks(body)


# ======================================================================
# CLI
# ======================================================================
def cprint_rows(rows, cols, limit):
    w = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows[:limit])) if rows else len(c) for c in cols}
    print("  ".join(c.ljust(min(w[c], 46)) for c in cols))
    for r in rows[:limit]:
        print("  ".join(str(r.get(c, ""))[:46].ljust(min(w[c], 46)) for c in cols))
    if len(rows) > limit:
        print(f"... {len(rows) - limit} more (full list in catalog.csv)")


def cmd_catalog(a):
    meta, rows = load_catalog(a.ticker, a.since)
    print(f"{meta['name']} | CIK {meta['cik']} | FYE {meta['fye'][:2]}-{meta['fye'][2:]} | {meta['filer']}")
    print(f"Catalog: {len(rows)} filings since {a.since} -> {os.path.join(CACHE, 'CIK%010d' % meta['cik'], 'catalog.csv')}")
    if a.forms:
        rows = [r for r in rows if r["form"] in a.forms or r["form"].replace("/A", "") in a.forms]
    else:
        n6k = sum(1 for r in rows if r["form"] == "6-K")
        rows = [r for r in rows if r["form"] != "6-K"]
        if n6k:
            print(f"({n6k} 6-K filings hidden; listed in catalog.csv, add --forms 6-K to show)")
    cprint_rows(rows, ["form", "filed", "report_date", "fy", "fp", "accn", "items", "fy_source", "flag"], a.limit)


def gather_menu(a, meta, rows):
    sel = select(rows, a.forms, a.last, a.fy, a.include_amend)
    if not sel:
        die(f"No filings of type {a.forms} in catalog (since {a.since}).")
    menu, notes = [], []
    for r in sel:
        m, note = menu_for(meta["cik"], r)
        menu += m
        if note:
            notes.append(f"{r['form']} {r['filed']} {r['accn']}: {note}")
    return sel, menu, notes


def cmd_menu(a):
    meta, rows = load_catalog(a.ticker, a.since)
    sel, menu, notes = gather_menu(a, meta, rows)
    if a.category:
        menu = [p for p in menu if p["category"] in a.category]
    d = os.path.join(CACHE, "CIK%010d" % meta["cik"])
    with open(os.path.join(d, "menu.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["accn", "form", "fy", "fp", "report_date", "R", "category", "name", "url"])
        w.writeheader(); w.writerows(menu)
    print(f"{meta['name']}: menu for {len(sel)} filing(s), {len(menu)} pages -> {os.path.join(d, 'menu.csv')}")
    for n in notes:
        print("NOTE:", n)
    for r in sel:
        pages = [p for p in menu if p["accn"] == r["accn"]]
        cats = {}
        for p in pages:
            cats[p["category"]] = cats.get(p["category"], 0) + 1
        print(f"\n{r['form']} FY{r['fy']} {r['fp']} (period {r['report_date']}, filed {r['filed']}, {r['accn']}): " +
              ", ".join(f"{k} {v}" for k, v in sorted(cats.items())))
        if a.show:
            for p in pages:
                print(f"  {p['R']:>5}  {p['category']:<10} {p['name'][:110]}")


def picks_for(a):
    meta, rows = load_catalog(a.ticker, a.since)
    sel, menu, notes = gather_menu(a, meta, rows)
    purpose = "statement" if a.topic in STATEMENT_TOPICS else a.purpose
    res = find_pages(menu, a.topic, purpose, a.top)
    order = {r["accn"]: i for i, r in enumerate(sel)}
    res.sort(key=lambda x: order.get(x[0], 99))
    missing = [r for r in sel if r["accn"] not in {x[0] for x in res}]
    return meta, sel, res, missing, notes, purpose


def cmd_find(a):
    meta, sel, res, missing, notes, purpose = picks_for(a)
    print(f"{meta['name']}: topic '{a.topic}', purpose '{purpose}', {len(sel)} filing(s)")
    for n in notes:
        print("NOTE:", n)
    for accn, picks, alts in res:
        p0 = picks[0]
        print(f"\n{p0['form']} FY{p0['fy']} {p0['fp']} ({accn})")
        for p in picks:
            print(f"  PICK {p['R']:>5} {p['category']:<10} {p['name'][:100]}")
        for p in alts:
            print(f"  alt  {p['R']:>5} {p['category']:<10} {p['name'][:100]}")
    for r in missing:
        print(f"\nNO MATCH in {r['form']} FY{r['fy']} {r['fp']} ({r['accn']}) - try another --topic wording or run `menu --show`")


def cmd_fetch(a):
    meta, sel, res, missing, notes, purpose = picks_for(a)
    outdir = os.path.join(CACHE, "CIK%010d" % meta["cik"], "pages")
    os.makedirs(outdir, exist_ok=True)
    all_csv = []
    print(f"{meta['name']}: fetching topic '{a.topic}' ({purpose}) from {len(res)} filing(s)")
    for accn, picks, alts in res:
        for p in picks:
            if p["url"].endswith(".xml"):
                print(f"  SKIP {p['form']} FY{p['fy']} {p['R']}: 2009-2010 era .xml R page; open {p['url']} or use the filing's HTML")
                continue
            html = http_get(p["url"])
            md, rows_ = convert_r_page(html.decode("utf-8", "ignore"), p)
            fn = os.path.join(outdir, f"{p['form'].replace('/', '')}_FY{p['fy']}{p['fp']}_{p['R']}.md")
            with open(fn, "w") as f:
                f.write(md)
            all_csv += rows_
            print(f"  {p['form']} FY{p['fy']} {p['fp']} {p['R']:>5} {p['category']:<10} {p['name'][:70]}  -> {fn} ({len(md):,} chars, {len(rows_)} tagged values)")
            if a.print:
                print("\n" + md[:a.max_chars] + ("\n...(truncated; full file above)" if len(md) > a.max_chars else "") + "\n")
    for r in missing:
        print(f"  NO MATCH in {r['form']} FY{r['fy']} {r['fp']} ({r['accn']})")
    if all_csv:
        cf = os.path.join(outdir, f"{a.topic.replace(' ', '_').replace(',', '_')}_{purpose}_values.csv")
        with open(cf, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(all_csv[0].keys()))
            w.writeheader(); w.writerows(all_csv)
        print(f"Tagged values (one row per number, with XBRL tag and source URL): {cf}")


def cmd_exhibits(a):
    meta, rows = load_catalog(a.ticker, a.since)
    if meta["filer"].startswith("foreign"):
        print("NOTE: foreign filer - earnings releases come on 6-K, which this v1 lists but does not parse.")
    want = ["2.02"] + (["7.01"] if a.include_701 else [])
    ks = [r for r in rows if r["form"].startswith("8-K") and any(w in r["items"] for w in want)]
    if not a.include_701:
        ks = [r for r in ks if "2.02" in r["items"]]
    ks = ks[:a.last]
    outdir = os.path.join(CACHE, "CIK%010d" % meta["cik"], "exhibits")
    os.makedirs(outdir, exist_ok=True)
    pat = re.compile(a.grep, re.I) if a.grep else None
    for r in ks:
        print(f"\n=== 8-K filed {r['filed']} items {r['items']} -> FY{r['fy']} {r['fp']} (period {r['report_date']}) {r['accn']}")
        for ex in exhibit_list(meta["cik"], r["accn"]):
            if a.types and ex["type"] not in a.types:
                print(f"  skip {ex['type']} {ex['file']}")
                continue
            blocks = exhibit_text(ex["url"])
            fn = os.path.join(outdir, f"{r['filed']}_{ex['type']}_{ex['file'].rsplit('.', 1)[0]}.md")
            with open(fn, "w") as f:
                f.write(f"# {ex['type']} {ex['desc']}\nSource: {ex['url']}\n\n" + "\n\n".join(b for _, b in blocks))
            ntab = sum(1 for k, _ in blocks if k == "table")
            print(f"  {ex['type']} {ex['file']} -> {fn} ({len(blocks)} blocks, {ntab} tables)")
            print(f"     source: {ex['url']}")
            if pat:
                is_head = lambda b: len(b) < 100 and (b.rstrip().endswith(":") or b.upper() == b)
                hits = [i for i, (_, b) in enumerate(blocks) if pat.search(b)]
                # section headings ("FULL YEAR 2026 GUIDANCE:", "Outlook") first: their body is what you want
                hits.sort(key=lambda i: (not is_head(blocks[i][1]), i))
                if not hits:
                    print(f"  (no blocks match /{a.grep}/)")
                for n, i in enumerate(hits[:a.max_hits]):
                    print(f"  --- hit {n + 1} (block {i}) ---")
                    out, j = [blocks[i][1]], i + 1
                    # a heading hit: print the section body until the next heading (max 4 blocks)
                    # a text hit: print a directly following table (reconciliations, outlook tables)
                    while j < len(blocks) and len(out) < 5 and (
                            (is_head(blocks[i][1]) and not is_head(blocks[j][1])) or
                            (j == i + 1 and blocks[j][0] == "table")):
                        out.append(blocks[j][1]); j += 1
                    print("  " + "\n  ".join(out)[:a.max_chars].replace("\n", "\n  "))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    def common(p, forms_default):
        p.add_argument("ticker", help="ticker (e.g. DOV) or CIK number")
        p.add_argument("--since", type=int, default=dt.date.today().year - 6, help="earliest filing year (default: 6 years back)")
        p.add_argument("--forms", nargs="+", default=forms_default)
        p.add_argument("--last", type=int, default=1, help="N most recent matching filings")
        p.add_argument("--fy", nargs="+", help="restrict to fiscal year(s)")
        p.add_argument("--include-amend", action="store_true", help="also include /A amendments")

    p = sp.add_parser("catalog"); p.add_argument("ticker"); p.add_argument("--since", type=int, default=dt.date.today().year - 6)
    p.add_argument("--forms", nargs="+"); p.add_argument("--limit", type=int, default=25); p.set_defaults(fn=cmd_catalog)

    p = sp.add_parser("menu"); common(p, ["10-K"]); p.add_argument("--category", nargs="+")
    p.add_argument("--show", action="store_true", help="list every page"); p.set_defaults(fn=cmd_menu)

    for name, fn in (("find", cmd_find), ("fetch", cmd_fetch)):
        p = sp.add_parser(name); common(p, ["10-K"])
        p.add_argument("--topic", required=True, help="built-in topic (" + ", ".join(TOPICS) + ") or comma-separated keywords")
        p.add_argument("--purpose", choices=["read", "numbers"], default="read", help="read=Notes page (full note); numbers=Details pages (tagged values)")
        p.add_argument("--top", type=int, default=1, help="pages to pick per filing")
        if name == "fetch":
            p.add_argument("--print", action="store_true", help="also print converted content")
            p.add_argument("--max-chars", type=int, default=6000)
        p.set_defaults(fn=fn)

    p = sp.add_parser("exhibits"); p.add_argument("ticker"); p.add_argument("--since", type=int, default=dt.date.today().year - 3)
    p.add_argument("--last", type=int, default=1); p.add_argument("--include-701", action="store_true")
    p.add_argument("--types", nargs="+", default=["EX-99.1"]); p.add_argument("--grep")
    p.add_argument("--max-hits", type=int, default=4); p.add_argument("--max-chars", type=int, default=3000)
    p.set_defaults(fn=cmd_exhibits)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
