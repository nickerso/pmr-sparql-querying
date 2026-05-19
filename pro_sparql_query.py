"""
Query the PMR SPARQL endpoint for triples that use a PRO URI as an object,
using the uniprot_pro_mapping.json file as the source of PRO URIs.

Usage:
    uv run pro_sparql_query.py [mapping.json] [output.json]

Defaults:
    mapping.json -> uniprot_pro_mapping.json
    output.json  -> pro_sparql_results.json

Output format:
    {
        "Q02013": {
            "pro_id": "PR:Q02013",
            "pro_uri": "http://purl.obolibrary.org/obo/PR_Q02013",
            "results": [
                {"s": "http://...", "p": "http://..."},
                ...
            ]
        },
        ...
    }
"""

import json
import sys
import time

import requests

SPARQL_ENDPOINT = "https://staging.physiomeproject.org/pmr2_virtuoso_search"
# SPARQL_ENDPOINT = "https://models.physiomeproject.org/pmr2_virtuoso_search"
REQUEST_DELAY = 0.25  # seconds between requests


def query_sparql(session: requests.Session, uri: str) -> list[dict]:
    response = session.post(
        SPARQL_ENDPOINT,
        data=f"""
            SELECT ?s ?p
            WHERE {{
                ?s ?p <{uri}> .
            }}""",
    )
    response.raise_for_status()
    bindings = response.json()["results"]["bindings"]
    return [
        {"s": b["s"]["value"], "p": b["p"]["value"]}
        for b in bindings
        if b["s"]["type"] != "bnode"
    ]


def main():
    mapping_path = sys.argv[1] if len(sys.argv) > 1 else "uniprot_pro_mapping.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "pro_sparql_results.json"

    with open(mapping_path) as f:
        mapping = json.load(f)

    session = requests.Session()
    session.headers["Accept"] = "application/sparql-results+json"

    output = {}
    entries = list(mapping.items())

    for i, (uniprot_id, pro_terms) in enumerate(entries, 1):
        for pro_term in pro_terms:
            pro_uri = pro_term["uri"]
            pro_id = pro_term["id"]
            print(f"[{i}/{len(entries)}] {uniprot_id} -> {pro_uri} ...", end=" ", flush=True)
            try:
                results = query_sparql(session, pro_uri)
                print(f"{len(results)} triple(s)")
                if results:
                    output[uniprot_id] = {
                        "pro_id": pro_id,
                        "pro_uri": pro_uri,
                        "results": results,
                    }
            except requests.HTTPError as exc:
                print(f"HTTP {exc.response.status_code} — skipped")
            except Exception as exc:
                print(f"error: {exc} — skipped")

            if i < len(entries):
                time.sleep(REQUEST_DELAY)

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(output)} UniProt IDs with SPARQL hits to {out_path}")


if __name__ == "__main__":
    main()
