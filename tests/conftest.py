import os
import sys
import tempfile
from pathlib import Path

# Point the app at an isolated temp SQLite DB *before* any app module is
# imported, so the test suite never touches the dev/demo database.
_tmp_db = Path(tempfile.mkdtemp()) / "test_metrictrust.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
