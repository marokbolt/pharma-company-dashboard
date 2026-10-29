import json
import time
import os
import re
import csv
import sys
import urllib.request

HEADERS = {"User-Agent": "Nextyn Research atul.rokkam@nextyn.com"}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOSSIERS = os.path.join(ROOT, "dossiers")
N_FILINGS = 3

def fetch_json(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(1)

def fetch_bytes(url, retries=3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(1)

def safe(s):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)

def main():
    rows = list(csv.DictReader(open(os.path.join(ROOT, "scripts", "last_8k_results.csv"), encoding="utf-8")))
    os.makedirs(DOSSIERS, exist_ok=True)

    overall_manifest = []
    for r in rows:
        ticker = r["ticker"]
        cik = r["cik"]
        if not cik:
            print(f"{ticker}: skip, no CIK", file=sys.stderr)
            continue
        cik_padded = cik.zfill(10)
        company_dir = os.path.join(DOSSIERS, ticker)
        filings_dir = os.path.join(company_dir, "filings")
        os.makedirs(filings_dir, exist_ok=True)

        try:
            data = fetch_json(f"https://data.sec.gov/submissions/CIK{cik_padded}.json")
        except Exception as e:
            print(f"{ticker}: submissions fetch error {e}", file=sys.stderr)
            continue

        forms = data.get("filings", {}).get("recent", {})
        form_list = forms.get("form", [])
        dates = forms.get("filingDate", [])
        accns = forms.get("accessionNumber", [])
        docs = forms.get("primaryDocument", [])
        prim_descs = forms.get("primaryDocDescription", [])
        items = forms.get("items", []) if "items" in forms else [None]*len(form_list)

        target_forms = {"8-K", "8-K/A", "6-K", "6-K/A"}
        matches = []
        for i, f in enumerate(form_list):
            if f in target_forms:
                matches.append(i)
            if len(matches) >= N_FILINGS:
                break

        manifest = {
            "ticker": ticker, "name": r["name"], "cik": cik,
            "company_name_edgar": data.get("name"),
            "sic": data.get("sicDescription"),
            "filings": []
        }

        for i in matches:
            accn = accns[i]
            accn_nodash = accn.replace("-", "")
            primary_doc = docs[i]
            filing_date = dates[i]
            form_type = form_list[i]
            item_str = items[i] if i < len(items) else None
            filing_dir_name = safe(f"{filing_date}_{form_type}_{accn}")
            local_dir = os.path.join(filings_dir, filing_dir_name)
            os.makedirs(local_dir, exist_ok=True)

            index_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
            filing_index_json_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn_nodash}/"
            # Get the filing's own index.json for full doc list
            try:
                idx = fetch_json(f"https://www.sec.gov/cgi-bin/browse-edgar")  # placeholder, not used
            except Exception:
                pass
            try:
                idx = fetch_json(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn_nodash}/index.json")
                doc_items = idx.get("directory", {}).get("item", [])
            except Exception as e:
                doc_items = []
                print(f"{ticker} {accn}: index fetch error {e}", file=sys.stderr)

            saved_docs = []
            for d in doc_items:
                fname = d.get("name", "")
                lower = fname.lower()
                if re.fullmatch(r"r\d+\.htm", lower):
                    continue  # XBRL viewer rendering fragment, not a filed document
                if "-index" in lower or lower.endswith(".txt"):
                    continue
                if lower.endswith((".htm", ".html")):
                    doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn_nodash}/{fname}"
                    try:
                        content = fetch_bytes(doc_url)
                        local_path = os.path.join(local_dir, safe(fname))
                        with open(local_path, "wb") as fh:
                            fh.write(content)
                        saved_docs.append({"filename": fname, "url": doc_url, "local_path": os.path.relpath(local_path, ROOT)})
                    except Exception as e:
                        print(f"{ticker} {accn} {fname}: download error {e}", file=sys.stderr)
                    time.sleep(0.12)

            manifest["filings"].append({
                "form_type": form_type,
                "filing_date": filing_date,
                "accession_number": accn,
                "items": item_str,
                "filing_folder_url": filing_index_json_url,
                "documents": saved_docs,
            })
            print(f"{ticker}: {form_type} {filing_date} -> {len(saved_docs)} docs", file=sys.stderr)

        with open(os.path.join(company_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        overall_manifest.append(manifest)
        time.sleep(0.2)

    with open(os.path.join(DOSSIERS, "_all_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(overall_manifest, f, indent=2)
    print(f"\nDone. Processed {len(overall_manifest)} companies.", file=sys.stderr)

if __name__ == "__main__":
    main()
