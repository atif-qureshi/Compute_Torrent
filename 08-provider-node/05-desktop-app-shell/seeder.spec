# -*- mode: python ; coding: utf-8 -*-

import os
import shutil
from PyInstaller.utils.hooks import collect_all

block_cipher = None
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')
node_binary = shutil.which('node.exe') or shutil.which('node')
if not node_binary:
    raise RuntimeError('Node.js is required to bundle WebTorrent support')
sync_module = os.path.abspath(os.path.join(SPECPATH, '..', '04-webtorrent-sync'))
sync_src = os.path.join(sync_module, 'src')
bundle_datas = []
assets_dir = os.path.join(SPECPATH, 'assets')
if os.path.isdir(assets_dir):
    bundle_datas.append((assets_dir, 'assets'))
bundle_datas.extend([
    (os.path.join(sync_src, 'webtorrent_helper.mjs'), 'webtorrent'),
    (os.path.join(sync_src, 'libp2p_peer.mjs'), 'webtorrent'),
    (os.path.join(sync_src, 'libp2p_network.mjs'), 'webtorrent'),
    (os.path.join(sync_module, 'node_modules'), 'webtorrent/node_modules'),
])
petals_runtime = os.path.abspath(os.path.join(SPECPATH, '..', '06-petals-runtime'))
if not os.path.isfile(os.path.join(petals_runtime, 'Dockerfile')):
    raise RuntimeError('Petals runtime recipe is missing')
from pathlib import Path
runtime_root = Path(petals_runtime)
runtime_sources = sorted(runtime_root.glob('*.py'))
runtime_sources += [runtime_root / 'Dockerfile', runtime_root / 'Dockerfile.cuda']
runtime_sources += sorted(runtime_root.glob('requirements*.txt'))
runtime_sources += sorted(runtime_root.glob('*.whl'))
bundle_datas.extend((str(path), 'petals-runtime') for path in runtime_sources if path.is_file())
bundle_datas.extend(ctk_datas)

a = Analysis(
    ['production_seeder.py'],
    pathex=['.', sync_src],
    binaries=[(node_binary, '.')] + ctk_binaries,
    datas=bundle_datas,
    hiddenimports=[
        'inference_runtime',
        'petals_control',
        'hardware_details',
        'webtorrent_client',
        'customtkinter',
        'psutil',
        'websockets',
        'asyncio',
    ] + ctk_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ComputeTorrent_Seeder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)
