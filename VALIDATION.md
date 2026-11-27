# CBP Validation Record

This repository separates Census API acquisition from approved analytical snapshots and downstream visualization work.

## Approved analytical snapshots

The 2018 and 2023 state-level County Business Patterns (CBP) extracts in `data/validated/` were promoted from candidate outputs after the acquisition validation reports returned `PASS` and the cross-year structural review returned `PASS`.

Scope for both snapshots:

- Geography: state
- Selected FIPS: 10 (Delaware), 11 (District of Columbia), 24 (Maryland), 42 (Pennsylvania), 51 (Virginia)
- Industry: NAICS2017 code `00` (Total for all sectors)
- Legal form: `001`
- Employment size: `001`
- Core measures: `ESTAB`, `EMP`, `PAYQTR1`, `PAYANN`
- Retained disclosure/noise fields: `EMP_N`, `PAYQTR1_N`, `PAYANN_N`

## Acquisition validation

Each source candidate passed checks for required columns, selected geography coverage, one row per selected state, state name/FIPS agreement, numeric conversion, nonnegative core measures, missing core measures, the first-quarter/annual payroll relationship, and retention of noise/disclosure fields.

The original acquisition metadata is preserved in `data/metadata/`. It records the source API endpoint, retrieval timestamp, requested variables, validation results, and confirms that the API key was not stored.

## Cross-year validation

The 2018–2023 comparison passed all structural checks recorded in `results/validation/cbp_2018_2023_validation.csv` and `results/validation/cbp_2018_2023_crossyear_report.json`. Both years use the same selected geography set, NAICS2017 code `00`, legal-form slice `001`, employment-size slice `001`, and core measures.

Payroll comparisons are **nominal unless an explicit inflation adjustment is performed**. Downstream visualizations must preserve that interpretation.

## Reproducibility rule

Visualization scripts should read the stable files in `data/validated/` by default. The Census API acquisition process remains available in `data_acquisition/` for controlled refreshes and candidate generation. New API output should not silently overwrite the approved snapshots.
