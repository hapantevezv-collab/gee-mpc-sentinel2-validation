"""Radiometric conventions: offset, scale and no-data in each catalogue."""
import numpy as np

from gee_mpc_s2val.radiometry import (NODATA_OUT, gee_reflectance, gee_valid, harmonise_mpc_dn,
                                      mpc_reflectance, mpc_valid, to_output)

DN_MPC = np.array([0, 500, 1000, 1001, 3000, 11000], dtype=np.uint16)


def test_gee_convention_equals_mpc_minus_offset():
    """DN_GEE = max(DN_MPC - 1000, 0) gives the same reflectance as MPC with offset -1000."""
    dn_gee = harmonise_mpc_dn(DN_MPC, -1000)
    assert list(dn_gee) == [0, 0, 0, 1, 2000, 10000]
    np.testing.assert_array_equal(gee_reflectance(dn_gee), mpc_reflectance(DN_MPC, -1000))


def test_scale_and_clip():
    r = mpc_reflectance(DN_MPC, -1000)
    assert r.dtype == np.float64
    assert r.min() == 0.0                       # negative reflectance is clipped to 0
    assert r[-1] == 1.0
    assert mpc_reflectance([3000], 0.0)[0] == 0.3    # baseline < 04.00: no offset


def test_no_uint16_overflow():
    assert mpc_reflectance(np.array([500], dtype=np.uint16), -1000)[0] == 0.0


def test_nodata_rules_differ_between_catalogues():
    # MPC: DN 0 is no data.
    assert list(mpc_valid(DN_MPC)) == [False, True, True, True, True, True]
    # MPC: a pixel masked by the reader is invalid even with DN != 0.
    assert list(mpc_valid([5, 5], read_mask=[True, False])) == [False, True]
    # GEE: harmonised DN 0 is a valid dark pixel when the mask band says so.
    dn_gee = harmonise_mpc_dn(DN_MPC, -1000)
    mask = np.array([0, 1, 1, 1, 1, 1])
    valid = gee_valid(mask)
    assert dn_gee[1] == 0 and valid[1]


def test_output_nodata():
    out = to_output([0.5, np.nan, np.inf])
    assert out.dtype == np.float32
    assert list(out) == [0.5, NODATA_OUT, NODATA_OUT]
