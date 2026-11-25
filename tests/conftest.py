import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Isolate test artefacts before any prism module resolves its data directory.
_TMP = Path(tempfile.mkdtemp(prefix="prism-test-"))
os.environ["PRISM_DATA"] = str(_TMP)

# Tests never call paid APIs: ignore the project .env and drop any key from the environment.
os.environ["PRISM_NO_DOTENV"] = "1"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


@pytest.fixture(scope="session")
def tmp_data():
    return _TMP
