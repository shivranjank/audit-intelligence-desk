import shutil

import pytest

requires_claude_cli = pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="requires the claude CLI to be installed and authenticated (query() shells out to it)",
)
