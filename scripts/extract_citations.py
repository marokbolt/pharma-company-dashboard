import re, json, os

# Run this from the handover_package/scripts/ folder (or pass a path as argv[1]).
# It reads ../dashboard/company_monitor_dashboard.html by default.
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "dashboard", "company_monitor_dashboard.html")
html = open(PATH, encoding="utf-8").read()

# Find the tearsheet script block (second <script> tag, contains window.COMPANIES.X = {...})
company_re = re.compile(r'window\.COMPANIES\.(\w+) = \{(.*?)\n\};\n', re.S)

CITATIONS = {}

for m in company_re.finditer(html):
    ticker = m.group(1)
    block = m.group(2)

    # financials array: scope to the financials:[...] block first, then find headings within it
    fin_block_m = re.search(r'financials:\s*\[(.*?)\n  \],\n', block, re.S)
    fin_block = fin_block_m.group(1) if fin_block_m else ""
    fin_srcs = re.findall(r'\{\s*heading:\s*"[^"]*",\s*src:\s*\[([\d,\s]+)\]', fin_block)
    fin_srcs = [[int(x) for x in s.split(",")] for s in fin_srcs]
    income_src = fin_srcs[0] if len(fin_srcs) > 0 else []
    balance_src = fin_srcs[1] if len(fin_srcs) > 1 else income_src
    cashflow_src = fin_srcs[2] if len(fin_srcs) > 2 else balance_src

    # runway quoteSrc
    rm = re.search(r'runway:\s*\{.*?quoteSrc:\s*\[([\d,\s]+)\]', block, re.S)
    runway_src = [int(x) for x in rm.group(1).split(",")] if rm else (balance_src or income_src)

    # first pipelineGroups src
    pm = re.search(r'pipelineGroups:\s*\[\s*\{[^}]*?src:\s*\[([\d,\s]+)\]', block, re.S)
    pipeline_src = [int(x) for x in pm.group(1).split(",")] if pm else income_src

    # first trial block src
    tm = re.search(r'trial:\s*\{.*?blocks:\s*\[\s*\{\s*heading:[^,]*,\s*src:\s*\[([\d,\s]+)\]', block, re.S)
    trial_src = [int(x) for x in tm.group(1).split(",")] if tm else pipeline_src

    # fundingSrc within runway block
    fm = re.search(r'runway:\s*\{.*?fundingSrc:\s*\[([\d,\s]+)\]', block, re.S)
    funding_src = [int(x) for x in fm.group(1).split(",")] if fm else balance_src

    CITATIONS[ticker] = {
        "income": income_src,
        "balance": balance_src,
        "cashflow": cashflow_src,
        "runway": runway_src,
        "funding": funding_src,
        "pipeline": pipeline_src,
        "trial": trial_src,
    }

print("companies parsed:", len(CITATIONS))

# Save as a JS var injection
js_lines = ["var CITATIONS = {"]
for t, d in CITATIONS.items():
    js_lines.append('  "%s": {income:%s, balance:%s, cashflow:%s, runway:%s, funding:%s, pipeline:%s, trial:%s},' % (
        t, d["income"], d["balance"], d["cashflow"], d["runway"], d["funding"], d["pipeline"], d["trial"]
    ))
js_lines.append("};")
js_text = "\n".join(js_lines)

out_path = os.path.join(HERE, "citations_var.js")
open(out_path, "w", encoding="utf-8").write(js_text)
print("wrote", out_path)

# ---- Inject/replace the CITATIONS block directly in the dashboard file ----
existing_pattern = re.compile(r'var CITATIONS = \{.*?\n\};', re.S)
data_marker = "var DATA = ["

if existing_pattern.search(html):
    new_html, n = existing_pattern.subn(js_text, html, count=1)
    print("Replaced existing CITATIONS block in", PATH)
elif data_marker in html:
    idx = html.index(data_marker)
    new_html = html[:idx] + js_text + "\n\n" + html[idx:]
    print("Inserted new CITATIONS block before 'var DATA = [' in", PATH)
else:
    new_html = None
    print("WARNING: could not find a CITATIONS block or 'var DATA = [' marker.")
    print("citations_var.js was written, but you must splice it into the dashboard by hand.")

if new_html is not None:
    open(PATH, "w", encoding="utf-8").write(new_html)
    print("Dashboard file updated in place:", PATH)
