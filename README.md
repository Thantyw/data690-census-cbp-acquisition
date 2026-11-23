# DATA 690 Census CBP acquisition

Retrieve and validate U.S. Census Bureau County Business Patterns data and produce versioned candidates and provenance reports for human review.

Requires Python 3.10+, internet access, and a Census API key in the `CENSUS_API_KEY` environment variable.

```sh
python data_acquisition/fetch_cbp.py --year 2022 2023
```

See the [developer guide](data_acquisition/README.md) for key setup, geography and industry options, disclosure flags, and comparison with approved snapshots.
