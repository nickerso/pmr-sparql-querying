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
        ]

    def execute(self, term):
        return (
            self.sess.post(
                self.host,
                data=f"""
                    SELECT ?s ?p
                    WHERE {{
                        ?s ?p <{term}> .
                    }}""",
                )
                .json()
        )

    def extract(self, term):
        results = []
        for bindings in self.execute(term)["results"]["bindings"]:
            if bindings["s"]["type"] == "bnode":
                continue
            results.append((
                bindings["s"]["value"],
                bindings["p"]["value"],
                term,
            ))
        return results

    def extract_all(self, term):
        results = []
        for term in self.get_terms(term):
            print(f"Looking for any annotations for the uniprot ID {term}...")
            results.extend(self.extract(term))
        return results


if __name__ == "__main__":
    import csv
    import json
    import sys

    try:
        filename = sys.argv[1]
    except IndexError:
        sys.stderr.write(f"usage: {sys.argv[0]} <mapping-report.csv>")
        sys.exit(1)

    extractor = Extractor(
        "https://staging.physiomeproject.org/pmr2_virtuoso_search",
        # "https://models.physiomeproject.org/pmr2_virtuoso_search",
    )

    results = []

    with open(filename) as src:
        table = csv.DictReader(src)
        for row in table:
            term = row["uniprot_id"]
            print(f"Looking for any annotations for the uniprot ID {term}...")
            results.extend(extractor.extract_all(term))

    print(json.dumps(results, indent=1))