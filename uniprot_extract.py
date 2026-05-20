import requests

class Extractor:
    def __init__(self, host):
        self.sess = requests.Session()
        self.sess.headers["Accept"] = "application/sparql-results+json"
        self.host = host

    def get_terms(self, term):
        return [
            f"urn:miriam:uniprot:{term}",
            f"http://identifiers.org/uniprot/{term}",
            f"https://identifiers.org/uniprot/{term}",
            f"https://www.uniprot.org/uniprotkb/{term}/entry",
        ]

    def execute(self, term):
        filter_expr = " || ".join(
            f"?term = <{uri}>" for uri in self.get_terms(term)
        )
        query_string = f"""
                SELECT ?s ?p ?term
                WHERE {{
                    ?s ?p ?term .
                    FILTER ({filter_expr})
                }}"""
        # print(f"Executing sparql query: {query_string.strip()}")
        response = self.sess.post(
            self.host,
            data=query_string,
            timeout=30,
        )

        if not response.ok:
            snippet = response.text[:200].replace("\n", " ")
            print(
                f"Request failed for {term}: HTTP {response.status_code}. "
                f"Response starts with: {snippet}"
            )
            return {"results": {"bindings": []}}

        try:
            return response.json()
        except ValueError:
            content_type = response.headers.get("Content-Type", "<missing>")
            snippet = response.text[:200].replace("\n", " ")
            print(
                f"Non-JSON response for {term}. Content-Type: {content_type}. "
                f"Response starts with: {snippet}"
            )
            return {"results": {"bindings": []}}

    def extract(self, term):
        results = []
        for bindings in self.execute(term)["results"]["bindings"]:
            if bindings["s"]["type"] == "bnode":
                continue
            results.append((
                bindings["s"]["value"],
                bindings["p"]["value"],
                bindings["term"]["value"],
            ))
        return results

    def extract_all(self, term):
        return self.extract(term)


if __name__ == "__main__":
    import csv
    import json
    import sys

    try:
        filename = sys.argv[1]
    except IndexError:
        sys.stderr.write(f"usage: {sys.argv[0]} <mapping-report.csv>")
        sys.exit(1)

    out_path = sys.argv[2] if len(sys.argv) > 2 else "uniprot_sparql_results.json"

    extractor = Extractor(
        # "https://staging.physiomeproject.org/pmr2_virtuoso_search",
        "https://models.physiomeproject.org/pmr2_virtuoso_search",
    )

    results = []

    with open(filename) as src:
        table = csv.DictReader(src)
        for row in table:
            term = row["uniprot_id"]
            print(f"Looking for any annotations for the uniprot ID {term}...")
            results.extend(extractor.extract_all(term))

    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nWrote {len(results)} UniProt IDs with SPARQL hits to {out_path}")
    # print(json.dumps(results, indent=1))