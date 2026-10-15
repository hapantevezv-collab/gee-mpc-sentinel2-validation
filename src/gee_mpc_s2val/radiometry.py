# Part of gee-mpc-sentinel2-validation (https://doi.org/10.5281/zenodo.23241823)
# Author: Heiber Alexander Pantevez Villamil (hapantevezv@unal.edu.co, ORCID 0000-0003-1797-0057), Universidad Nacional de Colombia
# Licence: MIT (see LICENSE)
"""Radiometric conventions of the two catalogues, as pure functions.

GEE (COPERNICUS/S2_SR_HARMONIZED) serves DN with the BOA offset already applied:
    DN_GEE = max(DN_MPC + BOA_ADD_OFFSET, 0)      (offset = -1000 for baseline >= 04.00)
MPC (sentinel-2-l2a) serves the original DN; the offset is read from the product XML.
In both cases reflectance = DN_harmonised / BOA_QUANTIFICATION_VALUE (10 000).

No-data rules:
* MPC: DN 0 (or a masked read) means no data.
* GEE: a harmonised DN of 0 is a real value (dark pixel after the offset); validity
  comes from the image mask, downloaded as its own band.
"""
from __future__ import annotations

import numpy as np

QUANTIFICATION = 10000.0
NODATA_OUT = -9999.0


def mpc_reflectance(dn, offset: float, qv: float = QUANTIFICATION) -> np.ndarray:
    """MPC DN -> reflectance: max(DN + offset, 0) / qv, computed in float64."""
    return np.maximum(np.asarray(dn, dtype=np.float64) + offset, 0.0) / qv


def mpc_valid(dn, read_mask=None) -> np.ndarray:
    """MPC validity: not masked by the reader and DN != 0."""
    dn = np.asarray(dn)
    valid = dn != 0
    if read_mask is not None:
        valid &= ~np.asarray(read_mask, dtype=bool)
    return valid


def gee_reflectance(dn_harmonised, qv: float = QUANTIFICATION) -> np.ndarray:
    """GEE harmonised DN -> reflectance (offset already applied by GEE)."""
    return np.asarray(dn_harmonised, dtype=np.float64) / qv


def gee_valid(mask_band) -> np.ndarray:
    """GEE validity from the downloaded native-mask band (DN 0 is NOT no data)."""
    return np.asarray(mask_band) > 0


def harmonise_mpc_dn(dn, offset: float) -> np.ndarray:
    """MPC DN expressed in the GEE harmonised convention: max(DN + offset, 0)."""
    return np.maximum(np.asarray(dn, dtype=np.int64) + int(offset), 0)


def to_output(values) -> np.ndarray:
    """Non-finite values -> NODATA_OUT (-9999), as float32 for GeoTIFF output."""
    v = np.asarray(values, dtype=np.float64)
    return np.where(np.isfinite(v), v, NODATA_OUT).astype("float32")
