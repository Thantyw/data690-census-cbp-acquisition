# County Business Patterns acquisition for DATA 690

`fetch_cbp.py` retrieves official County Business Patterns (CBP) data and checks each year independently. A successful acquisition creates a **candidate** for human review. The Bar Chart, Slope Diagram, Table, and optional Lollipop Chart can share an approved snapshot. Acquisition has no promotion step and does not alter an ACS file, visualization script, validated reference, or stable dataset.

## Setup and commands

Use Python 3.10+ with internet access to `api.census.gov`. The script uses the Python standard library. Census requires a key for data queries. [Request a Census API key](https://api.census.gov/data/key_signup.html) and set `CENSUS_API_KEY` privately in the process environment or from a secrets manager. For example, in Bash:

```bash
read -rs -p "Census API key: " CENSUS_API_KEY
printf '\n'
export CENSUS_API_KEY
```

The script does not load a `.env` file. Git ignores `.env` at every level. Keep the key in the environment, including when running in CI. Requests to public metadata catalogs omit the key.

Run from the repository root:

```bash
# 2023, all industries, Delaware, DC, Maryland, Pennsylvania, and Virginia
python data_acquisition/fetch_cbp.py

# Capture separate candidates and comparability reports for a slope diagram
python data_acquisition/fetch_cbp.py --year 2022 2023

# Payroll and other CBP measures for manufacturing and health care in MD and VA
python data_acquisition/fetch_cbp.py --year 2023 --states 24 51 --naics 31-33 62

# Two Maryland county equivalents. Use the full five-digit geography codes.
python data_acquisition/fetch_cbp.py --year 2023 --geography county --geo-codes 24031 24510

# Read an approved same-year reference and its retained provenance
python data_acquisition/fetch_cbp.py --year 2023 \
  --reference data/stable/cbp_2023.csv \
  --reference-metadata data/stable/cbp_2023_metadata.json
```

The default output directory is `data/candidate/` relative to the repository. Use `--output-dir` for another location. Select exact NAICS codes with `--naics`. `00` is the all-industry aggregate. Sector codes and ranges such as `31-33` must match Census codes. Other options include `--geography us`, `state`, `county`, `metro`, `csa`, `district`, and `zip`. Use `--geo-codes` with leading zeros intact. Supply two digits for states, five for counties (state + county), five for metro areas, three for CSAs, four for districts (state + district), and five for ZIP codes. The U.S. geography defaults to `1`. The utility queries one geography and industry pair at a time. Keep selections targeted.

## Product and variables

Census lists 2023 as the latest released reference year. The initial two-year comparison uses 2022 and 2023, both classified in 2017 NAICS. The program covers establishments with paid employees in most industries. CBP is annual and uses disclosure controls. Its noise ranges are different from ACS sampling margins of error. Payroll measures are nominal, in thousands of dollars.

| Source field | Census meaning and use |
| --- | --- |
| `ESTAB` | Number of establishments |
| `EMP` | Employment during the pay period including March 12 |
| `PAYQTR1` | First-quarter payroll in thousands of dollars |
| `PAYANN` | Annual payroll in thousands of dollars |
| `NAICS2017`, `NAICS2017_LABEL` | Industry code and description for the initial vintages. The script discovers the edition each year. |
| `NAME`, `GEO_ID`, returned FIPS geography fields | Published geographic name and identifier, plus the requested geography codes |
| `YEAR`, `LFO`, `EMPSZES` | Reference year, legal form code, and establishment employment size class. The utility uses `001` for all legal forms and all establishment sizes. |
| `INDLEVEL`, `LFO_LABEL`, `EMPSZES_LABEL` | Industry level and aggregate descriptions when published |
| `ESTAB_F`, `EMP_F`, `PAYQTR1_F`, `PAYANN_F` | Measure flags when published |
| `EMP_N`, `PAYQTR1_N`, `PAYANN_N` and their `_F` attributes | Published noise ranges and associated flags |
| `NAICS2017_F`, `GEO_ID_F`, `EMPFLAG` | Industry and geography flags, and historical employment flag, when listed for the selected vintage |

Official sources: [CBP releases](https://www.census.gov/programs-surveys/cbp/data.html), [2023 API variables](https://api.census.gov/data/2023/cbp/variables.html), [2022 API variables](https://api.census.gov/data/2022/cbp/variables.html), [2023 query examples](https://api.census.gov/data/2023/cbp/examples.html), [2023 geography levels](https://api.census.gov/data/2023/cbp/geography.html), [Census methodology](https://www.census.gov/programs-surveys/cbp/technical-documentation/methodology.html), and the [2023 CBP user guide](https://www2.census.gov/programs-surveys/cbp/resources/2023-CBP-User-Guide.pdf).

## Validation and disclosure review

- **PASS** means the requested slice passed automated checks. The script checks the annual variable and geography catalogs, API table structure, required columns, reference year, filter values, geographic identifiers, and uniqueness by geography, industry edition/code, legal form, and establishment size. It preserves codes as strings.
- **WARNING** means the file can be saved for review. This includes blank measures, withheld or unavailable values, published flags/noise, missing indicator fields, and omitted detailed industry rows when some data are returned. An omitted row does not establish that a business count or payroll amount was zero. Census may omit small cells, and some geography/industry combinations fall outside release coverage. ZIP and district examples can have additional product limitations.
- **FAIL** covers request or catalog failures, an empty result, missing required fields, missing all-industry geographies, unexpected identifiers or filters, duplicates, and unexplained non-integer or negative measure values. A failed year produces a metadata report only when the output directory is writable. A multi-year run still evaluates and saves other passing or warning years. The command exits with code 1 if any year fails and 0 for PASS/WARNING-only runs.

The candidate preserves original Census columns, including flags. JSON null is represented as blank in CSV. The four derived measure columns contain nonnegative integers or blanks, with an adjacent `_status` column. `D` indicates disclosure withholding in historical products, `S` indicates a cell withheld under publication standards, and `N` means unavailable or not comparable. The utility leaves corresponding analytic values blank even when the raw measure is zero. It also leaves blank or placeholder values blank. An unflagged reported zero remains zero. Numeric values with other measure flags are marked `flagged` and require review. Review the noise fields even when the numeric measure is available. Census codes `G`, `H`, and `J` indicate changes due to noise of less than 2%, 2% to less than 5%, and at least 5%, respectively. Unsupported historical schemas fail discovery instead of using assumed mappings.

## Candidate, provenance, and promotion

Each run writes a fresh `data/candidate/cbp_<year>_<UTC timestamp>_<run ID>/` containing matching `*_candidate.csv` and `*_metadata.json` files. Files are staged together before the run directory is made visible. The JSON records year, source, request parameters with no credentials, variable and geography definitions, retrieval time, dimensions, validation findings, and a SHA-256 checksum of the CSV. The default candidate directory is Git-ignored.

The optional reference comparison reads a single-year CSV with the candidate-format keys and measure columns. Its JSON provenance is optional and allows variable-definition and checksum checks. Differences are recorded for review, including added or removed keys, geography and industry changes, added or removed columns, changed cells and flags, and measure availability. Meaningful variable definition fields are compared when present on both sides. Year-specific group identifiers and titles are retained in provenance but are not treated as semantic variable-definition changes. A missing, invalid, or incomplete reference produces a comparison warning where applicable.

Multi-year runs save each year separately and compare eligible years by geography, NAICS edition and code, legal form, and establishment size. Verify geographic definitions and boundaries, industry classifications, measure units, disclosure flags, and coverage before making a slope diagram. A changed NAICS edition prevents matching those rows by the old industry identities. For payroll comparisons, label values as nominal or document an inflation adjustment if the analysis calls for real-dollar changes. Treat changes as descriptive.

For publication, review the report and CSV together and resolve material warnings. Confirm the file matches the recorded checksum and comparison scope. After approval, manually copy or commit the approved CSV and retained JSON to the agreed stable location. Point Python and R visualization code to that versioned, reviewed snapshot.
