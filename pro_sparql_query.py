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
        "Q9JI66": {
            "pro_id": "PR:Q9JI66",
            "pro_uri": "http://purl.obolibrary.org/obo/PR_Q9JI66",
            "results": {
                "files": [
                    "https://staging.physiomeproject.org/workspace/267/rawfile/HEAD/Ostby_2009_NBC.cellml",
                    ...
                ],
                "infiles": [
                    {"s": "Ostby_2009_NBC.cellml#entity_7", "p": "http://..."},
                    {"s": "Ostby_2009_NBC.cellml#Ostby_2009_NBC", "p": "https://..."},
                    ...
                ]
            }
        },
        ...
    }
"""

import json
import sys
import time

from urllib.parse import urlparse
import requests

SPARQL_ENDPOINT = "https://staging.physiomeproject.org/pmr2_virtuoso_search"
# SPARQL_ENDPOINT = "https://models.physiomeproject.org/pmr2_virtuoso_search"
REQUEST_DELAY = 0.25  # seconds between requests

def query_sparql(session: requests.Session, uri: str) -> tuple[set[str], list[dict[str, str]]]:
    response = session.post(
        SPARQL_ENDPOINT,
        data=f"""
             SELECT ?s ?p
             WHERE {{
                 GRAPH ?g {{
                     ?s ?p <{uri}> .
                 }}
             }}""",
    )
    response.raise_for_status()
    bindings = response.json()["results"]["bindings"]
    file_set = set()
    infiles = []
    for binding in bindings:
        file_set.add(f'{binding["g"]["value"]}/rawfile/HEAD/{binding["s"]["value"].split("#", 1)[0]}')
        if binding["s"]["type"] != "bnode":
            infiles.append({"s": binding["s"]["value"], "p": binding["p"]["value"]})
    
    return file_set, infiles


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
                files, infiles = query_sparql(session, pro_uri)
                print(f"{len(files)} file(s), {len(infiles)} triple(s)")
                if files or infiles:
                    output[uniprot_id] = {
                        "pro_id": pro_id,
                        "pro_uri": pro_uri,
                        "results": {
                            "files": sorted(files),
                            "infiles": infiles
                        }
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
