"""Catalogue reconciliation: states BOTH / GEE_ONLY / MPC_ONLY and identity E1 / E2."""
import pandas as pd

from gee_mpc_s2val.reconcile import reconcile, summarise

T = pd.Timestamp


def gee_row(dt, tile, prod, asset, cloud=5.0):
    return {"asset_id": asset, "sensing_utc": T(dt, tz="UTC"), "platform": "S2A", "tile": tile,
            "datatake": dt.replace("-", "")[:8], "product": prod, "baseline": 5.11,
            "generation": T(dt, tz="UTC"), "cloud_cover": cloud, "aoi_coverage": 1.0}


def mpc_row(dt, tile, prod, item, cloud=5.0):
    r = gee_row(dt, tile, prod, None, cloud)
    r.pop("asset_id")
    r["item_id"] = item
    return r


def make():
    gee = pd.DataFrame([
        gee_row("2024-06-01", "18PXS", "P1", "g1"),            # E1 with MPC
        gee_row("2024-06-06", "18PXS", "P2_GEE", "g2"),        # E2: other generation in MPC
        gee_row("2024-06-11", "18PXS", "P3", "g3"),            # GEE only
    ])
    mpc = pd.DataFrame([
        mpc_row("2024-06-01", "18PXS", "P1", "m1"),
        mpc_row("2024-06-06", "18PXS", "P2_MPC", "m2"),
        mpc_row("2024-06-16", "18PXS", "P4", "m4"),            # MPC only
    ])
    return reconcile(gee, mpc)


def test_states_and_identity():
    t = make().set_index("ids_gee", drop=False)
    states = dict(zip(make()["sensing_utc"].dt.day, make()["state"]))
    assert states == {1: "BOTH", 6: "BOTH", 11: "GEE_ONLY", 16: "MPC_ONLY"}
    ident = dict(zip(make()["sensing_utc"].dt.day, make()["identity"]))
    assert ident[1] == "E1" and ident[6] == "E2"
    assert pd.isna(ident[11]) and pd.isna(ident[16])
    assert len(t) == 4


def test_no_record_is_dropped():
    t = make()
    assert t["ids_gee"].fillna("").ne("").sum() == 3
    assert t["ids_mpc"].fillna("").ne("").sum() == 3


def test_same_acquisition_in_two_tiles_is_two_records():
    gee = pd.DataFrame([gee_row("2024-06-01", "18PXS", "A", "g1"), gee_row("2024-06-01", "18PYS", "B", "g2")])
    mpc = pd.DataFrame([mpc_row("2024-06-01", "18PXS", "A", "m1"), mpc_row("2024-06-01", "18PYS", "B", "m2")])
    t = reconcile(gee, mpc)
    assert len(t) == 2 and set(t["state"]) == {"BOTH"} and set(t["identity"]) == {"E1"}


def test_summary_counts():
    s = summarise(make(), "month").iloc[0]
    assert (s["BOTH"], s["GEE_ONLY"], s["MPC_ONLY"], s["total"], s["E2"]) == (2, 1, 1, 4, 1)
    assert s["fraction_single_catalogue"] == 0.5
