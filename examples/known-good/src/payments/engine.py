"""Business-logic module — G5 clean: the except handler is observable."""

import logging

log = logging.getLogger(__name__)


def charge_card(card, amount):
    """Charge a card. The except handler logs AND re-raises, so failures are
    observable to callers and tests (G5 clean)."""
    try:
        return _do_charge(card, amount)
    except Exception:
        log.exception("charge_card failed for amount=%s", amount)
        raise


def _do_charge(card, amount):
    if amount <= 0:
        raise ValueError("amount must be positive")
    return {"id": "ch_1", "amount": amount, "status": "succeeded"}
