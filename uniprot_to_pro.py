"""
Fetch Protein Ontology (PRO) cross-references for UniProt accessions and
write a JSON mapping file containing only IDs that have PRO entries.

Usage:
    uv run uniprot_to_pro.py <mapping-report.csv> [output.json]

Output format:
    {
        "Q02013": [
            {"id": "PR:000001009", "isoformId": "Q02013-1"}
        ],
        ...
    }
"""

import csv
import json
import sys
import time

import requests

UNIPROT_API = "https://rest.uniprot.org/uniprotkb/{accession}.json"
REQUEST_DELAY = 0.25  # seconds between requests to be polite


def fetch_pro_terms(session: requests.Session, accession: str) -> list[dict]:
    url = UNIPROT_API.format(accession=accession)
    response = session.get(url)
    response.raise_for_status()
    data = response.json()

    pro_entries = []
    for xref in data.get("uniProtKBCrossReferences", []):
        if xref.get("database") == "PRO":
            pro_id = xref["id"]
            entry = {
                "id": pro_id,
                "uri": "http://purl.obolibrary.org/obo/" + pro_id.replace(":", "_"),
            }
            # isoformId is present when the PRO term maps to a specific isoform
            if "isoformId" in xref:
                entry["isoformId"] = xref["isoformId"]
            # capture any additional properties returned (e.g. term name)
            for prop in xref.get("properties", []):
                entry[prop["key"]] = prop["value"]
            pro_entries.append(entry)

    return pro_entries


def read_uniprot_ids(csv_path: str) -> list[str]:
    seen = set()
    ids = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            uid = row["uniprot_id"].strip()
            if uid and uid not in seen:
                seen.add(uid)
                ids.append(uid)
    return ids


def main():
    if len(sys.argv) < 2:
        sys.stderr.write(f"usage: {sys.argv[0]} <mapping-report.csv> [output.json]\n")
        sys.exit(1)

    csv_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "uniprot_pro_mapping.json"

    accessions = read_uniprot_ids(csv_path)
    print(f"Found {len(accessions)} unique UniProt IDs in {csv_path}")

    mapping: dict[str, list[dict]] = {}
    session = requests.Session()
    session.headers["Accept"] = "application/json"

    for i, accession in enumerate(accessions, 1):
        print(f"[{i}/{len(accessions)}] {accession} ...", end=" ", flush=True)
        try:
            pro_terms = fetch_pro_terms(session, accession)
            if pro_terms:
                mapping[accession] = pro_terms
                print(f"{len(pro_terms)} PRO term(s)")
            else:
                print("no PRO mapping")
        except requests.HTTPError as exc:
            print(f"HTTP {exc.response.status_code} — skipped")
        except Exception as exc:
            print(f"error: {exc} — skipped")

        if i < len(accessions):
            time.sleep(REQUEST_DELAY)

    with open(out_path, "w") as f:
        json.dump(mapping, f, indent=2)

    print(f"\nWrote {len(mapping)} mapped IDs to {out_path}")


if __name__ == "__main__":
    main()
