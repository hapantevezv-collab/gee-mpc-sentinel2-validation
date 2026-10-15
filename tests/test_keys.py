"""Identifier parsing used to match acquisitions across catalogues."""
import pytest

from gee_mpc_s2val.reconcile import baseline, datatake_core, platform, product, tile


@pytest.mark.parametrize("raw, expected", [
    ("GS2B_20240601T152659_037803_N05.10", "GS2B_20240601T152659_037803"),
    ("GS2C_20241213T152721_001234_N99.05", "GS2C_20241213T152721_001234"),
    ("GS2A_20240606T152701_046783", "GS2A_20240606T152701_046783"),   # no suffix
    ("  GS2A_20240606T152701_046783_N05.11 ", "GS2A_20240606T152701_046783"),
    (None, None),
    ("", None),
])
def test_datatake_core_strips_baseline_suffix(raw, expected):
    assert datatake_core(raw) == expected


def test_two_generations_share_the_same_core():
    assert datatake_core("GS2B_20240601T152659_037803_N05.10") == \
        datatake_core("GS2B_20240601T152659_037803_N05.11")


@pytest.mark.parametrize("raw, expected", [
    ("Sentinel-2A", "S2A"), ("sentinel-2c", "S2C"), ("S2B", "S2B"), (None, None)])
def test_platform(raw, expected):
    assert platform(raw) == expected


def test_tile_product_baseline():
    assert tile("T18PXS") == "18PXS" and tile("18pys") == "18PYS"
    assert product("S2A_MSIL2A_20240914T152651_N0511_R025_T18PXS_20240914T222508.SAFE") == \
        "S2A_MSIL2A_20240914T152651_N0511_R025_T18PXS_20240914T222508"
    assert baseline("05.11") == 5.11 and baseline("N99.05") == 99.05 and baseline(None) is None
