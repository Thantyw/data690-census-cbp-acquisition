# DATA 690 Census County Business Patterns

Acquisition, validation, exploratory analysis, and reproducible visualization development using U.S. Census Bureau County Business Patterns (CBP) data for the DATA 690 Census Bureau capstone.

## Workflow

`Census API → candidate acquisition → validation → approved analytical snapshot → EDA → reproducible visualization → cross-language validation → publication output`

The project preserves a separation between **data refresh** and **reproduction**. The API workflow creates candidates for review; visualization work should use approved snapshots in `data/validated/` unless a refresh is intentionally being evaluated.

## Current scope

The approved analytical snapshots cover 2018 and 2023 CBP state-level data for Delaware, District of Columbia, Maryland, Pennsylvania, and Virginia, using NAICS2017 code `00` (Total for all sectors), legal-form code `001`, and employment-size code `001`.

Core measures are establishments (`ESTAB`), employment (`EMP`), first-quarter payroll (`PAYQTR1`), and annual payroll (`PAYANN`). Relevant noise/disclosure fields are retained for review.

## Repository structure

- `data_acquisition/` — reusable Census CBP API acquisition and validation utility
- `data/validated/` — approved analytical snapshots used for reproducible analysis
- `data/metadata/` — original acquisition/provenance metadata
- `analysis/` — cross-year EDA and validation notebook
- `results/validation/` — machine-readable cross-year validation evidence
- `VALIDATION.md` — validation and promotion record
- `data_dictionary.csv` — working field dictionary for the analytical snapshots

Visualization scripts and publication outputs will be added incrementally after the validated-data foundation is established.

## Refresh data

Requires Python 3.10+, internet access, and a Census API key in the `CENSUS_API_KEY` environment variable.

```sh
python data_acquisition/fetch_cbp.py --year 2022 2023
```

See `data_acquisition/README.md` for key setup, geography and industry options, disclosure fields, and candidate comparison procedures.

## Run acquisition on GitHub

1. In **Settings → Secrets and variables → Actions**, add the repository secret `CENSUS_API_KEY`.
2. In **Actions → Run Census CBP Acquisition**, select **Run workflow**.
3. Download the candidate-output artifact and review its validation report before promotion.

The acquisition workflow stores outputs as artifacts and does not commit Census API credentials to the repository.

## Interpretation note

Cross-year payroll comparisons are nominal unless an explicit inflation adjustment is performed. Visualizations must state this clearly when comparing payroll across years.
