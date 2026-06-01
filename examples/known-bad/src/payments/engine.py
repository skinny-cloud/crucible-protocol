"""Business-logic module — deliberately contains a G5 silent-exception defect."""


def charge_card(card, amount):
    """Charge a card. The except handler below SWALLOWS the failure (G5 defect):
    a real charge error returns None silently, so callers and tests never see it.
    """
    try:
        result = _do_charge(card, amount)
        return result
    except Exception:
        # G5 VIOLATION: error swallowed — no log, no raise, no error status.
        pass


def _do_charge(card, amount):
    if amount <= 0:
        raise ValueError("amount must be positive")
    return {"id": "ch_1", "amount": amount, "status": "succeeded"}
