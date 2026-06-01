"""Integration tests — deliberately contains G2, G3-mock, G7, G8.3 defects.

NOTE: no spec reference in any docstring (G7), uses MagicMock in an integration
test (G8.3), and the create-then-query test asserts only type/bool (G2).
"""

import os
from unittest.mock import MagicMock

import pytest


def test_charge_then_list_charges():
    # creates data then queries it...
    db = MagicMock()  # G8.3 VIOLATION: mock in an integration test
    db.insert_charge({"amount": 100})
    charges = db.list_charges()
    # G2 VIOLATION: only a type assertion — an empty list passes vacuously.
    assert isinstance(charges, list)


@pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1",
    reason="requires a live database",
)
def test_charge_persists_to_real_db():
    # G8.2 VIOLATION: RUN_DB_TESTS is never set in any CI workflow -> dead code.
    assert True
