from __future__ import annotations

import math


def idx_price_fraction(reference_close: float) -> int:
    """IDX regular/cash-market price fraction for one trading day.

    The applicable fraction is determined by the reference/previous close and
    remains valid for that trading day. It is adjusted on the following trading
    day when the closing price moves into another price group.
    """
    p = float(reference_close)
    if p < 200:
        return 1
    if p < 500:
        return 2
    if p < 2000:
        return 5
    if p < 5000:
        return 10
    return 25


def round_idx_price(price: float, reference_close: float, mode: str = "nearest") -> float:
    """Round a planned order price to the applicable IDX fraction.

    mode:
      - floor: at or below the raw level
      - ceil: at or above the raw level
      - nearest: nearest valid price
    """
    tick = idx_price_fraction(reference_close)
    x = float(price) / tick

    if mode == "floor":
        units = math.floor(x + 1e-12)
    elif mode == "ceil":
        units = math.ceil(x - 1e-12)
    elif mode == "nearest":
        units = math.floor(x + 0.5)
    else:
        raise ValueError("mode must be floor, ceil, or nearest")

    return float(max(units * tick, tick))
