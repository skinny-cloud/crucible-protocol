"""conftest — G8.6 clean: no module-level infrastructure mocks.

Fixtures that need fakes build them per-test (function scope), never as a
module-level rebinding of a real infra client name.
"""

import pytest


@pytest.fixture
def ledger():
    from tests.integration.test_payments import FakeLedger
    return FakeLedger()
