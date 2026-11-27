# CBP 2023 Employment Bar Chart

This example uses the approved `data/validated/cbp_2023_validated.csv` snapshot. Neither visualization script calls the Census API.

## Analytical question

How does 2023 employment compare across Delaware, District of Columbia, Maryland, Pennsylvania, and Virginia for CBP Total for all sectors?

## Scope

- Dataset: U.S. Census Bureau County Business Patterns (CBP), 2023
- Geography: selected states / state-equivalent
- Industry: NAICS2017 `00` — Total for all sectors
- Legal form: `001`
- Employment size: `001`
- Measure: `EMP`
- Quality metadata retained in the stable snapshot: `EMP_N`

## Implementations

- `visualization/BarChart.py` — Python / Matplotlib
- `visualization/BarChart.R` — R / ggplot2

Both scripts validate the expected geography, year, industry slice, legal-form slice, employment-size slice, and nonnegative employment values before plotting.

## Outputs

- `results/charts/CBP_BarChart_2023_Employment.png`
- `results/charts/CBP_BarChart_2023_Employment_R.png`

## Cross-language validation

The retained validation evidence in `results/validation/` records analytical equivalence between the Python and R implementations. The comparison is based on data and analytical output, not pixel-level image identity.
