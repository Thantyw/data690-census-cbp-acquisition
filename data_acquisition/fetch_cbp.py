"""Acquire review-only County Business Patterns candidates from the Census API."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
from itertools import combinations, product
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from uuid import uuid4

API = "https://api.census.gov/data"
DEFAULT_STATES = ("10", "11", "24", "42", "51")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "candidate"
MEASURES = {
    "ESTAB": "establishments",
    "EMP": "employment",
    "PAYQTR1": "first_quarter_payroll_thousands",
    "PAYANN": "annual_payroll_thousands",
}
GEOGRAPHIES = {
    # CLI name: (Census geography name, combined code width, state parent)
    "us": ("us", 1, False),
    "state": ("state", 2, False),
    "county": ("county", 5, True),
    "metro": ("metropolitan statistical area/micropolitan statistical area", 5, False),
    "csa": ("combined statistical area", 3, False),
    "district": ("congressional district", 4, True),
    "zip": ("zip code", 5, False),
}
KEY = ("geography_level", "geography_code", "naics_vintage", "industry_code", "LFO", "EMPSZES")
SEVERITY = {"PASS": 0, "WARNING": 1, "FAIL": 2}
MISSING = {"", "NULL", "(X)", "X", "N", "NA", "N/A", "-", "--"}
WITHHELD = {"D", "S", "N", "X", "(D)", "(S)", "(N)", "(X)"}
NOISE = {"G", "H", "J"}
COMPARABILITY = [
    "Review NAICS editions, industry labels, geography boundaries, and Census methodology by year.",
    "Match geography, industry, legal form and establishment size before comparing.",
    "Check missing or omitted cells and disclosure/noise flags in both years.",
    "Payroll is in nominal thousands of dollars. Adjust for inflation if reporting real changes.",
]


class AcquisitionError(Exception):
    """A diagnostic that is safe to record in provenance and console output."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(endpoint, params=None, key=None):
    query = dict(params or {})
    if key:
        query["key"] = key
    url = endpoint + ("?" + urlencode(query) if query else "")
    try:
        with build_opener(NoRedirect()).open(url, timeout=45) as response:
            if response.status == 204:
                return []
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 302:
            path = urlsplit(exc.headers.get("Location", "")).path
            if path == "/data/invalid_key.html":
                raise AcquisitionError("Census rejected the key. Check registration and paste only the API key.") from None
            if path == "/data/missing_key.html":
                raise AcquisitionError("Census did not receive a usable API key.") from None
        raise AcquisitionError(f"Census returned HTTP {exc.code}.") from None
    except (URLError, OSError):
        raise AcquisitionError("Census connection failed or timed out.") from None
    except (ValueError, UnicodeError):
        raise AcquisitionError("Census returned a non-JSON response. Check the API key and dataset availability.") from None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", nargs="+", type=int, default=[2023], help="One or more CBP reference years")
    parser.add_argument("--geography", choices=GEOGRAPHIES, default="state")
    parser.add_argument("--states", nargs="+", help="Two-digit FIPS codes for state-level requests")
    parser.add_argument("--geo-codes", nargs="+", help="Codes for the chosen level, including state prefixes for counties and districts")
    parser.add_argument("--naics", nargs="+", default=["00"], help="Exact NAICS codes, including 00 or a sector such as 31-33")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reference", type=Path, help="Read-only validated CSV in candidate format")
    parser.add_argument("--reference-metadata", type=Path, help="JSON provenance for the reference CSV")
    args = parser.parse_args(argv)
    if any(not 1900 <= year <= 9999 for year in args.year):
        parser.error("Supply four-digit reference years.")
    if args.states and (args.geography != "state" or args.geo_codes):
        parser.error("--states applies to state requests and cannot be combined with --geo-codes.")
    if args.reference_metadata and not args.reference:
        parser.error("--reference-metadata requires --reference.")
    args.codes = args.states or args.geo_codes or {"state": DEFAULT_STATES, "us": ("1",)}.get(args.geography)
    width = GEOGRAPHIES[args.geography][1]
    if not args.codes or any(not re.fullmatch(f"[0-9]{{{width}}}", code) for code in args.codes):
        parser.error(f"Supply {width}-digit geography codes, preserving leading zeros.")
    if args.geography == "us" and list(args.codes) != ["1"]:
        parser.error("Use geography code 1 for the United States.")
    if any(not re.fullmatch(r"[0-9]{2,6}|[0-9]{2}-[0-9]{2}", code) for code in args.naics):
        parser.error("Supply exact NAICS codes or Census sector ranges such as 31-33.")
    args.codes = sorted(set(args.codes))
    args.naics = sorted(set(args.naics))
    args.year = sorted(set(args.year))
    return args


def check(result, stage, status, detail):
    result["checks"][stage] = {"status": status, "detail": detail}


def overall(result):
    return max((item["status"] for item in result["checks"].values()), key=SEVERITY.get)


def discover(result, args):
    endpoint = result["api_endpoint"]
    catalog = request_json(endpoint + "/variables.json")
    geo_catalog = request_json(endpoint + "/geography.json")
    if not isinstance(catalog, dict) or not isinstance(geo_catalog, dict):
        raise AcquisitionError("Invalid Census metadata response.")
    variables = catalog.get("variables", {})
    geo_name, _, has_parent = GEOGRAPHIES[args.geography]
    geo = next((item for item in geo_catalog.get("fips", []) if item["name"] == geo_name), None)
    if not geo or set(geo.get("requires", [])) != ({"state"} if has_parent else set()):
        raise AcquisitionError("Selected geography or its hierarchy is unavailable for this year.")
    naics_fields = [name for name in variables if re.fullmatch(r"NAICS[0-9]{4}", name)]
    if len(naics_fields) != 1:
        raise AcquisitionError("Expected one year-specific NAICS field. Review this CBP schema.")
    naics = naics_fields[0]
    group = variables.get("ESTAB", {}).get("group", "")
    if not re.fullmatch(r"CB[A-Z0-9]+", group):
        raise AcquisitionError("Could not identify the CBP measure group.")
    group_url = endpoint + f"/groups/{group}.json"
    group_metadata = request_json(group_url)
    if not isinstance(group_metadata, dict):
        raise AcquisitionError("Invalid Census variable group metadata.")
    definitions = group_metadata.get("variables", {}) | variables
    required = ["NAME", "GEO_ID", "YEAR", naics, naics + "_LABEL", "LFO", "EMPSZES", *MEASURES]
    if not set(required) <= definitions.keys():
        raise AcquisitionError("Core CBP fields are unavailable for this year.")
    # The dataset catalog declares attributes that are defined in the group catalog.
    for field in (*MEASURES, naics, "GEO_ID", "LFO", "EMPSZES"):
        for attribute in definitions[field].get("attributes", "").split(","):
            if attribute and attribute not in definitions:
                definitions[attribute] = request_json(endpoint + f"/variables/{attribute}.json")
    indicators = [
        *(field + "_F" for field in MEASURES),
        *(field + suffix for field in ("EMP", "PAYQTR1", "PAYANN") for suffix in ("_N", "_N_F")),
    ]
    optional = [*indicators, naics + "_F", "GEO_ID_F", "LFO_LABEL", "EMPSZES_LABEL", "INDLEVEL", "EMPFLAG"]
    get_fields = required + [field for field in optional if field in definitions]
    result.update(
        variable_catalog=endpoint + "/variables.json",
        variable_group_catalog=group_url,
        geography_catalog=endpoint + "/geography.json",
        geography_definition=geo,
        naics_field=naics,
        naics_vintage=naics[-4:],
        variables_requested=get_fields,
        variable_definitions={field: {
            **{attr: definitions[field][attr] for attr in ("label", "predicateType", "attributes", "concept", "group")
               if attr in definitions[field]},
            **({"unit": "USD thousands"} if field in ("PAYQTR1", "PAYANN") else {}),
        } for field in get_fields},
        unavailable_disclosure_fields=sorted(set(indicators) - definitions.keys()),
    )
    return geo_name, has_parent, naics, get_fields


def decode_table(body):
    if body == []:
        return [], []
    if not isinstance(body, list) or not body or not isinstance(body[0], list):
        raise AcquisitionError("Expected a Census JSON table.")
    header = body[0]
    if not header or any(not isinstance(field, str) or not field.strip() for field in header):
        raise AcquisitionError("Response contains an empty or invalid field name.")
    rows = []
    for row in body[1:]:
        if (not isinstance(row, list) or len(row) != len(header)
                or any(value is not None and type(value) not in (str, int) for value in row)):
            raise AcquisitionError("Response contains malformed rows or non-scalar cells.")
        record = {}
        for field, value in zip(header, row):
            # Census can repeat requested dimensions when it echoes predicates.
            if field in record and record[field] != value:
                raise AcquisitionError(f"Repeated Census column has conflicting values: {field}.")
            record[field] = value
        rows.append(record)
    return list(dict.fromkeys(header)), rows


def interpret(value, flag):
    raw = "" if value is None else str(value).strip().upper()
    if flag in WITHHELD or raw in WITHHELD:
        return "", "withheld_or_unavailable"
    if raw in MISSING:
        return "", "missing"
    if re.fullmatch(r"[0-9]+", raw):
        return int(raw), "available" if not flag else "flagged"
    return "", "invalid"


def collect(result, args, key, layout):
    geo_name, has_parent, naics, fields = layout
    identity_fields = (["state"] if has_parent else []) + [geo_name]
    required = set(fields + identity_fields)
    original_columns = fields + identity_fields
    extra_columns = set()
    rows = []
    problems = []
    absent = []
    geography_errors = []
    schema_errors = []
    numeric_errors = Counter()
    disclosure = Counter()
    seen = set()
    geo_ids = {}
    geo_codes = {}

    for code, industry in product(args.codes, args.naics):
        params = {"get": ",".join(fields), "for": f"{geo_name}:{code[2:] if has_parent else code}",
                  naics: industry, "LFO": "001", "EMPSZES": "001"}
        if has_parent:
            params["in"] = "state:" + code[:2]
        result["requests"].append(params)
        try:
            body = request_json(result["api_endpoint"], params, key)
        except AcquisitionError as exc:
            problems.append(f"{code}/{industry}: {exc}")
            continue
        try:
            header, batch = decode_table(body)
            if header and not required.issubset(header):
                raise AcquisitionError("Missing columns: " + ", ".join(sorted(required - set(header))))
        except AcquisitionError as exc:
            schema_errors.append(f"{code}/{industry}: {exc}")
            continue
        if not batch:
            absent.append(f"{code}/{industry}")
            continue
        extra_columns.update(set(header) - required)
        for row in batch:
            returned_code = "".join(str(row.get(field) or "") for field in identity_fields)
            geo_id = str(row["GEO_ID"] or "").strip()
            if (returned_code != code or not geo_id or not str(row["NAME"] or "").strip()
                    or geo_ids.setdefault(code, geo_id) != geo_id
                    or geo_codes.setdefault(geo_id, code) != code):
                geography_errors.append(f"{code}/{industry}: missing or unexpected geography identifier")
            if (str(row["YEAR"]) != str(result["reference_year"]) or row[naics] != industry
                    or str(row["LFO"]) != "001" or str(row["EMPSZES"]) != "001"
                    or not str(row[naics + "_LABEL"] or "").strip()):
                schema_errors.append(f"{code}/{industry}: inconsistent year, industry or aggregate filters")
            row.update(geography_level=args.geography, geography_code=returned_code,
                       naics_vintage=naics[-4:], industry_code=row[naics], industry_label=row[naics + "_LABEL"])
            identity = tuple(row[name] for name in KEY)
            if identity in seen:
                geography_errors.append(f"{code}/{industry}: duplicate analytical row")
            seen.add(identity)
            for field, analytic in MEASURES.items():
                flag = str(row.get(field + "_F") or "").strip().upper()
                value, status = interpret(row[field], flag)
                row[analytic] = value
                row[analytic + "_status"] = status
                if status == "invalid":
                    numeric_errors[field] += 1
                elif status != "available":
                    disclosure[f"{field}:{status}"] += 1
                for suffix in ("_N", "_N_F"):
                    noise = str(row.get(field + suffix) or "").strip().upper()
                    if noise and noise not in MISSING:
                        disclosure[f"{field + suffix}:{noise if noise in NOISE or noise in WITHHELD else 'reported'}"] += 1
            for field in (naics + "_F", "GEO_ID_F", "EMPFLAG"):
                if str(row.get(field) or "").strip().upper() not in MISSING:
                    disclosure[field + ":reported"] += 1
            rows.append(row)

    empty = not rows and not schema_errors
    check(result, "API retrieval", "FAIL" if problems or empty else "PASS",
          problems or ("No CBP data rows returned" if empty else "Census responded to all data requests"))
    check(result, "Schema validation", "FAIL" if schema_errors or not rows else "PASS",
          schema_errors or ("Required identifiers and measures present" if rows else "No rows to validate"))
    geo_status = "FAIL" if geography_errors or not rows or ("00" in args.naics and any(
        pair.endswith("/00") for pair in absent)) else ("WARNING" if absent else "PASS")
    check(result, "Geography validation", geo_status, {
        "errors": geography_errors, "unreturned_geography_industry_pairs": absent,
    })
    check(result, "Numeric validation", "FAIL" if numeric_errors or not rows else "PASS",
          dict(numeric_errors) or ("Nonnegative integers or identified unavailable values" if rows else "No rows to validate"))
    check(result, "Disclosure review", "WARNING" if disclosure or absent or result["unavailable_disclosure_fields"] else "PASS",
          {"indicators": dict(disclosure), "unreturned_pairs": absent,
           "fields_unavailable_in_catalog": result["unavailable_disclosure_fields"]})
    columns = original_columns + sorted(extra_columns) + list(KEY[:4]) + ["industry_label"]
    columns += [column for analytic in MEASURES.values() for column in (analytic, analytic + "_status")]
    if len(columns) != len(set(columns)):
        check(result, "Schema validation", "FAIL", "Source columns conflict with derived CSV fields.")
    return columns, rows


def load_reference(args):
    metadata = {}
    if args.reference_metadata:
        with args.reference_metadata.open(encoding="utf-8-sig") as file:
            metadata = json.load(file)
        if not isinstance(metadata, dict) or not isinstance(metadata.get("variable_definitions", {}), dict):
            raise AcquisitionError("Reference metadata must contain an object of variable definitions.")
    with args.reference.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, strict=True)
        columns = reader.fieldnames or []
        if not {*KEY, "YEAR", *MEASURES.values()}.issubset(columns) or len(columns) != len(set(columns)):
            raise AcquisitionError("Reference CSV requires unique headers and the CBP candidate schema.")
        rows = list(reader)
    if not rows or any(None in row or None in row.values() or any(not row[name] for name in KEY) for row in rows):
        raise AcquisitionError("Reference CSV is empty or has malformed rows.")
    years = {row["YEAR"] for row in rows}
    if len(years) != 1 or any(not re.fullmatch(r"[0-9]{4}", year) for year in years):
        raise AcquisitionError("Reference CSV must represent one reference year.")
    if len({tuple(row[name] for name in KEY) for row in rows}) != len(rows):
        raise AcquisitionError("Reference CSV has duplicate analytical rows.")
    if "reference_year" in metadata and str(metadata["reference_year"]) not in years:
        raise AcquisitionError("Reference year differs from its metadata.")
    expected_hash = metadata.get("candidate_sha256")
    if expected_hash and expected_hash != hashlib.sha256(args.reference.read_bytes()).hexdigest():
        raise AcquisitionError("Reference CSV differs from the hash recorded in its metadata.")
    return metadata, columns, rows


def csv_value(value):
    return "" if value is None else str(value)


def compare(candidate, reference):
    current_meta, current_columns, current_rows = candidate
    baseline_meta, baseline_columns, baseline_rows = reference
    current = {tuple(csv_value(row[name]) for name in KEY): row for row in current_rows}
    baseline = {tuple(csv_value(row[name]) for name in KEY): row for row in baseline_rows}
    shared_fields = (set(current_columns) & set(baseline_columns)) - {*KEY, "YEAR"}
    current_defs = current_meta.get("variable_definitions", {})
    baseline_defs = baseline_meta.get("variable_definitions", {})
    definition_fields = ("label", "predicateType", "attributes", "unit")
    definition_changes = sorted(
        field for field in current_defs.keys() & baseline_defs.keys()
        if any(current_defs[field].get(attr) != baseline_defs[field].get(attr) for attr in definition_fields)
    )
    changed = []
    for identity in sorted(current.keys() & baseline.keys()):
        before, after = baseline[identity], current[identity]
        changes = {field: {"reference": csv_value(before[field]), "candidate": csv_value(after[field])}
                   for field in sorted(shared_fields) if csv_value(before.get(field)) != csv_value(after.get(field))}
        if changes:
            changed.append({"key": identity, "fields": changes})

    def dimensions(index, positions):
        return {tuple(identity[pos] for pos in positions) for identity in index}

    def difference(new, old):
        return {"added": sorted(new - old), "removed": sorted(old - new)}

    def availability(rows):
        return dict(Counter(
            field + ":" + row.get(field + "_status", "unknown")
            for row in rows for field in MEASURES.values()
            if row.get(field + "_status") != "available"
        ))

    found = {
        "reference_year": baseline_rows[0]["YEAR"],
        "candidate_year": current_meta["reference_year"],
        "key_columns": KEY,
        "rows": difference(current.keys(), baseline.keys()),
        "geographies": difference(dimensions(current, (0, 1)), dimensions(baseline, (0, 1))),
        "industries": difference(dimensions(current, (2, 3)), dimensions(baseline, (2, 3))),
        "columns": difference(set(current_columns), set(baseline_columns)),
        "changed_values": changed,
        "availability": {"reference": availability(baseline_rows), "candidate": availability(current_rows)},
        "variable_definitions_compared": bool(baseline_defs),
        "variable_definition_changes": definition_changes,
        "variable_catalog_fields": difference(current_defs.keys(), baseline_defs.keys()) if baseline_defs else None,
        "geography_definition_changed": (
            current_meta["geography_definition"] != baseline_meta["geography_definition"]
            if "geography_definition" in baseline_meta else None
        ),
    }
    review = any(any(found[name].values()) for name in ("rows", "columns")) or bool(
        changed or definition_changes or found["geography_definition_changed"] or not baseline_defs
        or any((found["variable_catalog_fields"] or {}).values())
        or found["availability"]["reference"] != found["availability"]["candidate"]
        or str(found["reference_year"]) != str(found["candidate_year"])
    )
    return found, review


def acquire(year, args, key):
    now = datetime.now(timezone.utc)
    result = {
        "source_agency": "U.S. Census Bureau",
        "program": "County Business Patterns",
        "api_dataset": "cbp",
        "api_endpoint": f"{API}/{year}/cbp",
        "reference_year": year,
        "retrieval_started_utc": now.isoformat(),
        "geography_level": args.geography,
        "selected_geography_codes": args.codes,
        "industry_codes": args.naics,
        "aggregate_filters": {"LFO": "001", "EMPSZES": "001"},
        "requests": [],
        "checks": {},
        "candidate_filename": None,
        "human_review_required": True,
    }
    columns, rows = [], []
    try:
        if not key:
            raise AcquisitionError("Set CENSUS_API_KEY in the process environment. Census data queries require a key.")
        layout = discover(result, args)
    except (AcquisitionError, TypeError, KeyError, AttributeError) as exc:
        detail = str(exc) if isinstance(exc, AcquisitionError) else "Unexpected Census metadata schema."
        check(result, "API retrieval", "FAIL", detail)
    else:
        columns, rows = collect(result, args, key, layout)
    result.update(row_count=len(rows), column_count=len(columns), retrieval_completed_utc=datetime.now(timezone.utc).isoformat())
    return result, columns, rows


def save(result, columns, rows, output_dir):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    batch = f"cbp_{result['reference_year']}_{stamp}_{uuid4().hex[:12]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / batch
    with tempfile.TemporaryDirectory(prefix=".cbp-", dir=output_dir) as temporary:
        stage = Path(temporary) / "batch"
        stage.mkdir()
        if overall(result) != "FAIL":
            name = batch + "_candidate.csv"
            path = stage / name
            with path.open("x", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=columns)
                writer.writeheader()
                writer.writerows(sorted(rows, key=lambda row: tuple(csv_value(row[field]) for field in KEY)))
            result["candidate_filename"] = name
            result["candidate_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            check(result, "Candidate saved", "PASS", name)
        else:
            check(result, "Candidate saved", "FAIL", "Validation failed. Only the metadata report is saved.")
        metadata = batch + "_metadata.json"
        check(result, "Metadata saved", "PASS", metadata)
        result["validation_status"] = overall(result)
        result["warnings"] = [name for name, item in result["checks"].items() if item["status"] == "WARNING"]
        (stage / metadata).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        stage.rename(destination)
    return destination


def main(argv=None):
    args = parse_args(argv)
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    reference = None
    reference_problem = None
    if args.reference:
        try:
            reference = load_reference(args)
            if any(not isinstance(item, dict) for item in reference[0].get("variable_definitions", {}).values()):
                raise AcquisitionError("Reference variable definitions must be objects.")
        except (OSError, ValueError, csv.Error, AcquisitionError) as exc:
            reference = None
            reference_problem = str(exc) if isinstance(exc, AcquisitionError) else "Cannot read the reference CSV or its JSON metadata."

    candidates = [acquire(year, args, key) for year in args.year]
    valid = [candidate for candidate in candidates if overall(candidate[0]) != "FAIL"]
    if len(candidates) > 1:
        for result, _, _ in candidates:
            result["cross_year_review"] = {"considerations": COMPARABILITY, "comparisons": []}
            check(result, "Cross-year review", "WARNING",
                  "Review comparability before combining years. Each year was validated independently.")
        for baseline, current in combinations(valid, 2):
            report, _ = compare(current, baseline)
            current[0]["cross_year_review"]["comparisons"].append(report)
            baseline[0]["cross_year_review"]["comparisons"].append(report)

    exit_code = 0
    for candidate in candidates:
        result, columns, rows = candidate
        if overall(result) != "FAIL":
            if reference_problem:
                check(result, "Reference comparison", "WARNING", reference_problem)
            elif reference:
                report, review = compare(candidate, reference)
                result["reference_comparison"] = report
                check(result, "Reference comparison", "WARNING" if review else "PASS",
                      "See the comparison report in the provenance JSON.")
        try:
            destination = save(result, columns, rows, args.output_dir)
        except (OSError, ValueError, csv.Error):
            destination = None
            check(result, "Candidate saved", "FAIL", "Output transaction did not complete.")
            check(result, "Metadata saved", "FAIL", "Output transaction did not complete.")
        print("\nCBP DATA ACQUISITION")
        print(f"Year: {result['reference_year']} | Dataset: County Business Patterns")
        print(f"Geography: {args.geography} ({', '.join(args.codes)}) | NAICS: {', '.join(args.naics)}")
        for name in ("API retrieval", "Schema validation", "Geography validation", "Numeric validation",
                     "Disclosure review", "Cross-year review", "Reference comparison", "Candidate saved", "Metadata saved"):
            item = result["checks"].get(name)
            print_line = item or {"status": "SKIPPED"}
            if item or name not in ("Cross-year review", "Reference comparison"):
                print(f"{name}: {print_line['status']}")
            if item and item["status"] == "FAIL":
                print(f"  {item['detail']}")
        print(f"Overall status: {overall(result)}")
        if destination:
            print(f"Output: {destination}")
        if result["candidate_filename"] and destination:
            print("Human review is required before promotion.")
        if overall(result) == "FAIL":
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
