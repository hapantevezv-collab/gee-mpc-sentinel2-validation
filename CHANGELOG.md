# Changelog

## 1.1.0 — 2026-10-15

Engineering release; no change to the methods or to the published results.

- Installable package `gee_mpc_s2val` (`pip install`), with commands `gee-mpc-reconcile`,
  `gee-mpc-e2`, `gee-mpc-impact` and `gee-mpc-verify-demo`. The v1.0.0 scripts in
  `scripts/` still work and call the same code.
- Radiometric conventions (offset, scale, no-data) moved to `radiometry.py` as tested functions.
- Test suite (pytest): identifier parsing, reconciliation states and E1/E2 identity, E2
  strata, radiometry, processing chain, demo verifier, and offline acceptance on the
  public demonstration AOI. Tests that need Earth Engine are marked `ee` and skipped
  without credentials.
- Public demonstration AOI moved to `data/demo_aoi.geojson`, with reference outputs,
  acceptance values (`acceptance_demo.json`) and SHA-256 hashes in `data/acceptance/demo/`.
- Demo verifier (`gee-mpc-verify-demo`) treats empty text cells consistently across
  pandas versions.
- Continuous integration with GitHub Actions (Python 3.10–3.12).
- `CONTRIBUTING.md`; metadata for the GitHub–Zenodo integration.

## 1.0.0 — 2026-10-08

First public release, archived on Zenodo with the preprint and data:
https://doi.org/10.5281/zenodo.23241823

- `reconcile_catalogues.py`, `e2_frequency.py`, `composite_impact.py`.
- Spanish-language guide (`docs/guide_es.html`), acceptance test and workflow figures.
