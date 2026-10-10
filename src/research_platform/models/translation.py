"""A simple translation identity for fictional revenue amounts."""

from collections.abc import Mapping

from research_platform.factors.fx import cross_rate


def translate_amount(
    amount: float, local_currency: str, reporting_currency: str,
    currency_state: Mapping[str, float],
) -> float:
    """Translate at one scenario rate; not an average/closing FX rate policy."""
    return amount * cross_rate(currency_state, local_currency, reporting_currency)

