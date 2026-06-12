"""Research tests need the dev-only deps; skip the whole directory without them."""

import pytest

pytest.importorskip("pandas")
pytest.importorskip("pyarrow")
