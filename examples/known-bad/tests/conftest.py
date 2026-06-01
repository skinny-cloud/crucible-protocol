"""conftest — deliberately contains the G8.6 structural-oracle-compromise defect.

The module-level assignment below mocks the database client for EVERY test that
imports it. This is exactly the dx3 conftest incident from the CRUCIBLE paper:
4,726 tests passing against a mock, zero real database coverage.
"""

from unittest.mock import AsyncMock

# G8.6 VIOLATION: module-level infra mock — affects all importing tests.
asyncpg = AsyncMock()
