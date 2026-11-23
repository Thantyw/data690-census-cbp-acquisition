# DATA 690 Census CBP acquisition

Retrieve and validate U.S. Census Bureau County Business Patterns data and produce versioned candidates and provenance reports for human review.

Requires Python 3.10+, internet access, and a Census API key in the `CENSUS_API_KEY` environment variable.

```sh
python data_acquisition/fetch_cbp.py --year 2022 2023
```

See the [developer guide](data_acquisition/README.md) for key setup, geography and industry options, disclosure flags, and comparison with approved snapshots.

## Run on GitHub

1. In **Settings → Secrets and variables → Actions**, add the repository secret `CENSUS_API_KEY`.
2. In **Actions → Run Census CBP Acquisition**, select **Run workflow**.
3. On the run page, download **cbp-candidate-outputs** under **Artifacts**. Review the validation reports before promoting any candidate. Failed runs can also contain diagnostic reports.

The workflow runs manually and stores outputs as artifacts. It does not commit data or credentials to the repository.
