# sparql-query

Tools for querying the PMR SPARQL endpoint and mapping UniProt accessions to the Protein Ontology (PRO).

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```powershell
cd sparql-query
uv sync
```

---

## Scripts

### `uniprot_extract.py`

Queries the PMR SPARQL endpoint for all triples where a UniProt accession (in
`urn:miriam`, `http://identifiers.org`, or `https://identifiers.org` URI form)
appears as the object. Reads UniProt IDs from a CSV file and writes the results
as JSON to stdout.

**Usage**

```powershell
uv run uniprot_extract.py <mapping-report.csv>
```

**Output** — JSON array of `[subject, predicate, term_uri]` tuples printed to stdout:

```json
[
  ["http://example.org/workspace/entity", "http://example.org/prop", "urn:miriam:uniprot:Q02013"],
  ...
]
```

---

### `uniprot_to_pro.py`

Fetches Protein Ontology (PRO) cross-references for each UniProt accession in a
CSV file via the [UniProt REST API](https://rest.uniprot.org). Only IDs that
have at least one PRO mapping are written to the output file, making the result
suitable as a persistent lookup cache.

**Usage**

```powershell
uv run uniprot_to_pro.py <mapping-report.csv> [output.json]
```

- `mapping-report.csv` — CSV with a `uniprot_id` column (defaults to `mapping-report.csv`)
- `output.json` — destination file (defaults to `uniprot_pro_mapping.json`)

**Output** — JSON object keyed by UniProt accession:

```json
{
  "Q02013": [
    {
      "id": "PR:Q02013",
      "uri": "http://purl.obolibrary.org/obo/PR_Q02013",
      "Description": "-"
    }
  ]
}
```

---

### `pro_sparql_query.py`

Uses a `uniprot_pro_mapping.json` file (produced by `uniprot_to_pro.py`) to
query the PMR SPARQL endpoint for every triple where a PRO URI appears as the
object. Only UniProt IDs that produce at least one hit are written to the output
file.

**Usage**

```powershell
uv run pro_sparql_query.py [mapping.json] [output.json]
```

- `mapping.json` — PRO mapping file (defaults to `uniprot_pro_mapping.json`)
- `output.json` — destination file (defaults to `pro_sparql_results.json`)

**Output** — JSON object keyed by UniProt accession:

```json
{
  "Q02013": {
    "pro_id": "PR:Q02013",
    "pro_uri": "http://purl.obolibrary.org/obo/PR_Q02013",
    "results": {
       "files": [
        "https://..."
      ],
      "infiles":[
      {"s": "http://...", "p": "http://..."}
      ]
  }
  }
}
```

**Switching endpoints**

Both `uniprot_extract.py` and `pro_sparql_query.py` target the staging PMR
endpoint by default. To switch to production, edit the commented-out line near
the top of each script:

```python
# SPARQL_ENDPOINT = "https://models.physiomeproject.org/pmr2_virtuoso_search"
```

---

## Typical workflow

```powershell
# 1. Build the PRO mapping cache from a CSV of UniProt IDs
uv run uniprot_to_pro.py mapping-report.csv

# 2. Query PMR for triples referencing those PRO URIs
uv run pro_sparql_query.py

# 3. (Optional) Query PMR for triples referencing UniProt URIs directly
uv run uniprot_extract.py mapping-report.csv > uniprot_sparql_results.json

# 4. From the `pro_sparql_results.json`, you can find relevant model files. You can also check the details of a specific model.

uv run pmr_ke "https://models.physiomeproject.org/workspace/267/rawfile/HEAD/Ostby_2009_NBC.cellml" `
  --ttl-output output/Ostby_2009_NBC.ttl `
  --json-output output/Ostby_2009_NBC_simplified.json `
  --png-output output/Ostby_2009_NBC_graph

```
