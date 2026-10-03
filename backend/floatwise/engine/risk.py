"""Turn P10/P50/P90 forecasts into a full demand distribution (SRS §7.1).

The three quantiles are joined into a piecewise-linear CDF with explicit tails:
    x:  lo        q10   q50   q90   q90 + s   q90 + 2s      (s = q90 - q50, lo = q10 - 1.5 (q50 - q10))
    F:  0.00      0.10  0.50  0.90  0.99      1.00
From it we read stockout probabilities, any service-level quantile and the expected shortfall.
All functions are vectorised: inputs are arrays of shape (n,), quantiles of shape (n, 3).
"""

from __future__ import annotations

import numpy as np

PROBS = np.array([0.0, 0.10, 0.50, 0.90, 0.99, 1.0])
_EPS = 1e-6


def knots(q: np.ndarray) -> np.ndarray:
    """(n, 3) quantiles [P10, P50, P90] -> (n, 6) strictly increasing CDF knots."""
    q = np.sort(np.maximum(np.atleast_2d(np.asarray(q, dtype=float)), 0.0), axis=1)
    q10, q50, q90 = q[:, 0], q[:, 1], q[:, 2]
    lo_spread = np.maximum(q50 - q10, 1.0)
    hi_spread = np.maximum(q90 - q50, 1.0)
    x = np.column_stack(
        [np.maximum(q10 - 1.5 * lo_spread, 0.0), q10, q50, q90, q90 + hi_spread, q90 + 2 * hi_spread]
    )
    # enforce strict monotonicity (ties happen when quantiles collapse or clip at zero)
    return np.maximum.accumulate(x + _EPS * np.arange(6), axis=1)


def cdf(x: np.ndarray, q: np.ndarray) -> np.ndarray:
    """P(demand <= x)."""
    k = knots(q)
    x = np.asarray(x, dtype=float).reshape(-1, 1)
    frac = np.clip((x - k[:, :-1]) / (k[:, 1:] - k[:, :-1]), 0.0, 1.0)
    return (frac * np.diff(PROBS)).sum(axis=1)


def stockout_probability(available: np.ndarray, q: np.ndarray) -> np.ndarray:
    """P(demand > available balance)."""
    return np.clip(1.0 - cdf(available, q), 0.0, 1.0)


def quantile(level: float | np.ndarray, q: np.ndarray) -> np.ndarray:
    """Demand level not exceeded with probability `level` (inverse CDF)."""
    k = knots(q)
    p = np.broadcast_to(np.asarray(level, dtype=float), (k.shape[0],)).reshape(-1, 1)
    frac = np.clip((p - PROBS[:-1]) / np.diff(PROBS), 0.0, 1.0)
    return k[:, 0] + (frac * np.diff(k, axis=1)).sum(axis=1)


def expected_shortfall(available: np.ndarray, q: np.ndarray) -> np.ndarray:
    """E[(demand - available)+] in taka: the expected unserved amount for a balance."""
    k = knots(q)
    a = np.asarray(available, dtype=float).reshape(-1, 1)
    lo = np.maximum(k[:, :-1], a)  # part of each segment above the available balance
    hi = k[:, 1:]
    width = np.clip(hi - lo, 0.0, None)
    f_lo = cdf_from_knots(lo, k)
    f_hi = np.broadcast_to(PROBS[1:], hi.shape)
    survival = 1.0 - (f_lo + f_hi) / 2.0
    below_first = np.clip(k[:, :1] - a, 0.0, None)  # demand is certainly above `a` up to the first knot
    return (width * survival).sum(axis=1) + below_first[:, 0]


def cdf_from_knots(x: np.ndarray, k: np.ndarray) -> np.ndarray:
    """CDF evaluated element-wise for x of shape (n, m) against per-row knots k (n, 6)."""
    out = np.zeros_like(x, dtype=float)
    for j in range(5):
        seg = np.clip((x - k[:, j : j + 1]) / (k[:, j + 1 : j + 2] - k[:, j : j + 1]), 0.0, 1.0)
        out += seg * (PROBS[j + 1] - PROBS[j])
    return out
