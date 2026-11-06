# Compatibility PyInstaller entrypoint; use the canonical source and runtime.
import os
from pathlib import Path

canonical_shell = Path(SPECPATH).resolve().parents[1] / '08-provider-node' / '05-desktop-app-shell'
canonical_spec = canonical_shell / 'seeder.spec'
if not canonical_spec.is_file():
    raise RuntimeError('The canonical 08-provider-node desktop source is missing')
os.chdir(canonical_shell)
SPECPATH = str(canonical_shell)
exec(compile(canonical_spec.read_bytes(), str(canonical_spec), 'exec'), globals())
