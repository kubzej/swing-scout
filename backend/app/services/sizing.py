"""
Centralized position sizing — tranche model.

A position is built in up to MAX_TRANCHES buys, each a percentage of total
portfolio value. The first tranche is slightly larger; subsequent adds are equal.
The per-name cap (= sum of all tranches) is a live concentration limit.
All percentages scale by confidence.

Why % of portfolio and not portfolio/max_positions: most names never fill all
tranches, so deriving the budget from /max_positions left the book heavily
under-deployed. Here deployment floats with how many adds actually fire, and
cash is the dry-powder buffer.
"""
from typing import Optional

ENTRY_PCT = 0.03   # first buy
ADD_PCT = 0.02     # each subsequent add
CAP_PCT = 0.07     # per-name concentration cap (= 3% + 2% + 2%)
MAX_TRANCHES = 3   # entry + 2 adds

CONFIDENCE_MULT = {4: 1.0, 3: 0.85, 2: 0.65, 1: 0.0}
DEFAULT_MULT = 0.85  # manual buys / unknown confidence


def _conf_mult(confidence: Optional[int]) -> float:
    if confidence is None:
        return DEFAULT_MULT
    return CONFIDENCE_MULT.get(confidence, DEFAULT_MULT)


def _round_czk(value: float) -> float:
    return round(value / 1000) * 1000


def entry_size_czk(portfolio_value_czk: float, confidence: Optional[int]) -> float:
    """Size of the first buy."""
    return _round_czk(portfolio_value_czk * ENTRY_PCT * _conf_mult(confidence))


def add_size_czk(portfolio_value_czk: float, confidence: Optional[int]) -> float:
    """Size of a single add tranche."""
    return _round_czk(portfolio_value_czk * ADD_PCT * _conf_mult(confidence))


def position_cap_czk(portfolio_value_czk: float, confidence: Optional[int]) -> float:
    """Max total cost basis a single name may reach (concentration limit)."""
    return _round_czk(portfolio_value_czk * CAP_PCT * _conf_mult(confidence))


def add_reserve_czk(portfolio_value_czk: float, confidence: Optional[int]) -> float:
    """Planned budget for the remaining add tranches after entry (display/plan only)."""
    return _round_czk(portfolio_value_czk * ADD_PCT * (MAX_TRANCHES - 1) * _conf_mult(confidence))
