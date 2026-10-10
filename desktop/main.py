"""Start the standalone provider desktop application."""
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent / "05-desktop-app-shell"
sys.path.insert(0, str(APP_ROOT))

from production_seeder import main  # noqa: E402


if __name__ == "__main__":
    main()
