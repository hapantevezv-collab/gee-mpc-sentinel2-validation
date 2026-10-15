# Contributing

Thank you for your interest. Issues and pull requests are welcome.

## Reporting a problem

Open an issue with: the command you ran, the AOI (or a public stand-in if yours is
private), the period, the package version (`pip show gee-mpc-sentinel2-validation`) and
the error or the unexpected output. Do not attach private geometries or credentials.

## Development

```bash
git clone https://github.com/hapantevezv-collab/gee-mpc-sentinel2-validation.git
cd gee-mpc-sentinel2-validation
pip install -e ".[test]"
pytest -m "not ee"                 # offline tests
GEE_PROJECT=your-project pytest    # also runs the Earth Engine tests
```

Rules for changes:

- A change to the processing chain must keep the acceptance test on the public AOI
  passing, or explain in the pull request why the reference values change.
- Add a test for every bug fix.
- Code, comments and messages in English.
- Never commit private geometries, Earth Engine credentials or project identifiers.

## Catalogue changes

GEE and MPC update their catalogues. If `test_live_ee.py` fails while the offline tests
pass, a catalogue probably changed: report it, with the query date, rather than editing
the reference files.
