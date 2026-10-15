"""Processing chain: validity mask, 3x3 valid-neighbour mean, indices, median, medoid, metrics."""
import numpy as np

from gee_mpc_s2val.impact import medoid, median, metrics, scene_indices

VALID = {2, 4, 5, 6, 7}


def flat(value, shape=(5, 5)):
    return np.full(shape, value, dtype=np.float64)


def test_indices_formulas_without_smoothing():
    b, g, r, n = 0.05, 0.08, 0.06, 0.40
    refl = np.stack([flat(b), flat(g), flat(r), flat(n)])
    idx = scene_indices(refl, np.ones((5, 5), bool), np.full((5, 5), 4), VALID, use_3x3=False)
    assert np.allclose(idx["NDVI"], (n - r) / (n + r))
    assert np.allclose(idx["EVI"], 2.5 * (n - r) / (n + 6 * r - 7.5 * b + 1))
    assert np.allclose(idx["NDWI"], (g - n) / (g + n))


def test_invalid_scl_class_is_masked():
    refl = np.stack([flat(0.05), flat(0.08), flat(0.06), flat(0.4)])
    scl = np.full((5, 5), 4)
    scl[2, 2] = 9                                         # cloud high probability
    idx = scene_indices(refl, np.ones((5, 5), bool), scl, VALID, use_3x3=True)
    assert np.isnan(idx["NDVI"][2, 2]) and np.isfinite(idx["NDVI"][2, 1])


def test_3x3_mean_uses_only_valid_neighbours():
    red = flat(0.10)
    red[2, 2] = 0.30
    refl = np.stack([flat(0.05), flat(0.08), red, flat(0.40)])
    scl = np.full((5, 5), 4)
    scl[1, 1] = 9                                         # neighbour excluded from the mean
    idx = scene_indices(refl, np.ones((5, 5), bool), scl, VALID, use_3x3=True)
    mean_red = (0.30 + 7 * 0.10) / 8                      # 8 valid pixels in the window
    assert np.isclose(idx["NDVI"][2, 2], (0.40 - mean_red) / (0.40 + mean_red))


def test_monthly_median_averages_two_central_values():
    stack = [flat(v, (1, 1)) for v in (0.2, 0.4, 0.6, 0.9)]
    stack.append(flat(np.nan, (1, 1)))
    m, n = median(stack)
    assert np.isclose(m[0, 0], 0.5) and n[0, 0] == 4


def test_medoid_eligibility():
    months = [f"2024-{i:02d}" for i in range(1, 13)]
    layers = [np.stack([flat(0.5 + 0.01 * i, (2, 2))] * 3) for i in range(12)]
    layers[0][:, 0, 0] = np.nan                           # still >= 8 months and 4 quarters
    for i in range(0, 9):                                  # pixel (1,1): only 3 months left
        layers[i][:, 1, 1] = np.nan
    annual, eligible = medoid(months, layers, 8, 4)
    assert eligible[0, 0] and not eligible[1, 1]
    assert np.isnan(annual[:, 1, 1]).all()


def test_metrics_bias_mae_and_masks():
    inside = np.ones((2, 2), bool)
    a = np.array([[0.5, 0.6], [np.nan, 0.8]])
    b = np.array([[0.4, 0.6], [0.7, np.nan]])
    m = metrics(a, b, inside)
    assert m["common_pixels"] == 2 and m["valid_only_a"] == 1 and m["valid_only_b"] == 1
    assert np.isclose(m["bias_a_minus_b"], 0.05) and np.isclose(m["mae"], 0.05)
    assert m["fraction_pixels_changed"] == 0.5
