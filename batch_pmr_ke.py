import argparse
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
import requests


from pmr_ke import build_bioprocess_graph, extract_rdf, get_bioProcess, simplify_bio_process


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Process every CellML file referenced by a PRO SPARQL results JSON file "
            "through the pmr_ke Python API."
        )
    )
    parser.add_argument(
        "input_json",
        nargs="?",
        default="pro_sparql_results.json",
        help="Path to a JSON file like pro_sparql_results.json.",
    )
    parser.add_argument(
        "output_dir",
        help="Directory where generated TTL, JSON, PNG, and summary files will be written.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a CellML source when its TTL, JSON, and PNG outputs already exist.",
    )
    parser.add_argument(
        "--skip-png",
        action="store_true",
        help="Do not render Graphviz PNG output.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most this many unique CellML files.",
    )
    parser.add_argument(
        "--search-pmr-by-filename",
        dest="search_pmr_by_filename",
        action="store_true",
        default=True,
        help="After processing, search PMR entries by each model filename.",
    )
    parser.add_argument(
        "--no-search-pmr-by-filename",
        dest="search_pmr_by_filename",
        action="store_false",
        help="Disable PMR filename search after processing.",
    )
    parser.add_argument(
        "--pmr-search-base-url",
        default="https://models.physiomeproject.org/search",
        help="PMR search endpoint base URL.",
    )
    return parser.parse_args()


def load_results(input_json: Path) -> dict:
    with input_json.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Expected the input JSON to contain a top-level object.")
    return payload


def is_cellml_reference(reference: str) -> bool:
    return reference.lower().endswith(".cellml")


def iter_unique_cellml_files(payload: dict) -> Iterable[str]:
    seen: set[str] = set()
    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        results = entry.get("results", {})
        if not isinstance(results, dict):
            continue
        files = results.get("files", [])
        if not isinstance(files, list):
            continue
        for file_ref in files:
            if not isinstance(file_ref, str) or not is_cellml_reference(file_ref):
                continue
            if file_ref not in seen:
                seen.add(file_ref)
                yield file_ref


def build_output_stem(output_dir: Path, source: str) -> Path:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 5 and parts[0] == "workspace" and parts[2] == "rawfile" and parts[3] == "HEAD":
            workspace_id = parts[1]
            relative_parts = parts[4:]
            file_name = relative_parts[-1]
            parent = output_dir / f"workspace_{workspace_id}" / Path(*relative_parts[:-1])
            return parent / Path(file_name).stem
        parent = output_dir / parsed.netloc / Path(*parts[:-1])
        file_name = parts[-1] if parts else "remote.cellml"
        return parent / Path(file_name).stem

    source_path = Path(source)
    local_root = output_dir / "local"
    drive_prefix = source_path.drive.rstrip(":")
    parts = [part for part in source_path.parts if part not in {source_path.drive, source_path.root}]
    if drive_prefix:
        local_root = local_root / drive_prefix
    parent = local_root / Path(*parts[:-1]) if parts[:-1] else local_root
    file_name = parts[-1] if parts else source_path.name
    return parent / Path(file_name).stem


def output_paths_for_source(output_dir: Path, source: str) -> dict[str, Path]:
    stem = build_output_stem(output_dir, source)
    stem.parent.mkdir(parents=True, exist_ok=True)
    return {
        "ttl": stem.with_suffix(".ttl"),
        "json": stem.parent / f"{stem.name}_simplified.json",
        "png_base": stem.parent / f"{stem.name}_graph",
        "png": stem.parent / f"{stem.name}_graph.png",
    }


def should_skip(paths: dict[str, Path], skip_png: bool) -> bool:
    required = [paths["ttl"], paths["json"]]
    if not skip_png:
        required.append(paths["png"])
    return all(path.exists() for path in required)


def process_source(source: str, output_dir: Path, skip_png: bool) -> dict:
    paths = output_paths_for_source(output_dir, source)
    rdf_graph = extract_rdf(source, str(paths["ttl"]))
    if rdf_graph is None:
        raise RuntimeError("RDF extraction failed.")

    bio_process = get_bioProcess(rdf_graph)
    simplified = simplify_bio_process(bio_process, str(paths["json"]))

    if not skip_png:
        dot = build_bioprocess_graph(simplified)
        dot.render(str(paths["png_base"]), view=False, format="png", cleanup=True)

    result = {
        "source": source,
        "status": "processed",
        "outputs": {
            "ttl": str(paths["ttl"]),
            "json": str(paths["json"]),
        },
    }
    if not skip_png:
        result["outputs"]["png"] = str(paths["png"])
    return result


def model_filename(source: str) -> str:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"} and parsed.path:
        return Path(parsed.path).name
    return Path(source).name


def pmr_search(url, search_text):
    post_data = {
        "template": {
            "data": [
                {"name": "SearchableText", "value": search_text},
            ]
        }
    }
    res = requests.post(
        url,
        json=post_data,
        headers={
            "Accept": "application/vnd.physiome.pmr2.json.1",
            "User-Agent": "andre.sparql_query.batch_pmr_ke/0.0",
        },
    )
    data = res.json()["collection"]["links"]
    results = []
    for link in data:
        if link.get("rel") == "bookmark":
            results.append({
                "href": link.get("href"),
                "title": link.get("prompt")
            })
    return results


def search_pmr_by_filename(filename: str, base_url: str, timeout: int = 20) -> dict:

    matches = pmr_search(base_url, quote_plus(filename))

    return {
        "filename": filename,
        "search_url": base_url,
        "match_count": len(matches),
        "matches": matches,
    }


def main() -> int:
    args = parse_args()
    input_json = Path(args.input_json)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = load_results(input_json)
    sources = list(iter_unique_cellml_files(payload))
    if args.limit is not None:
        sources = sources[: args.limit]

    summary = {
        "input_json": str(input_json.resolve()),
        "output_dir": str(output_dir.resolve()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_unique_cellml_files": len(sources),
        "processed": [],
        "failed": [],
        "skipped": [],
        "filename_search": {
            "enabled": args.search_pmr_by_filename,
            "base_url": args.pmr_search_base_url,
            "results": [],
            "failed": [],
        },
    }

    print(f"Found {len(sources)} unique CellML file(s) in {input_json}.")
    for index, source in enumerate(sources, start=1):
        print(f"[{index}/{len(sources)}] {source}")
        paths = output_paths_for_source(output_dir, source)
        if args.skip_existing and should_skip(paths, args.skip_png):
            print("  Skipped: outputs already exist.")
            summary["skipped"].append({
                "source": source,
                "status": "skipped",
                "reason": "outputs already exist",
            })
            continue
        try:
            result = process_source(source, output_dir, args.skip_png)
            summary["processed"].append(result)
            print("  Processed successfully.")
        except Exception as exc:
            print(f"  Failed: {exc}")
            summary["failed"].append({
                "source": source,
                "status": "failed",
                "error": str(exc),
            })

    if args.search_pmr_by_filename:
        unique_filenames = sorted({name for name in (model_filename(source) for source in sources) if name})
        print(f"Searching PMR for {len(unique_filenames)} unique model filename(s)...")
        for index, filename in enumerate(unique_filenames, start=1):
            print(f"  [{index}/{len(unique_filenames)}] {filename}")
            try:
                search_result = search_pmr_by_filename(filename, args.pmr_search_base_url)
                summary["filename_search"]["results"].append(search_result)
                print(f"    Found {search_result['match_count']} PMR match(es).")
            except Exception as exc:
                print(f"    Search failed: {exc}")
                summary["filename_search"]["failed"].append({
                    "filename": filename,
                    "error": str(exc),
                })

    summary_path = output_dir / "pmr_ke_batch_summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    print(
        "Completed "
        f"{len(summary['processed'])} processed, "
        f"{len(summary['skipped'])} skipped, "
        f"{len(summary['failed'])} failed."
    )
    if args.search_pmr_by_filename:
        print(
            "Filename search: "
            f"{len(summary['filename_search']['results'])} searched, "
            f"{len(summary['filename_search']['failed'])} failed."
        )
    print(f"Summary written to {summary_path}")
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())