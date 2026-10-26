# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
import sys

import rapidocr

# tinify is optional in the build environment; import safely.
try:
    import tinify
    _tinify_installed = True
except Exception:
    tinify = None
    _tinify_installed = False

SPEC_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
if str(SPEC_DIR) not in sys.path:
    sys.path.insert(0, str(SPEC_DIR))

from build_assets import get_pyinstaller_common_datas, get_rapidocr_datas

block_cipher = None

# Include tinify package files so PyInstaller will bundle tinify resources
# Include Python source and PEM/certificate files used by tinify (e.g. API certs).
# Only add patterns if tinify is installed and matching files exist to avoid
# PyInstaller complaining about missing files.
tinify_add_data = []
if _tinify_installed:
    tinify_dir = Path(tinify.__file__).resolve().parent
    # include top-level .py files
    if any(tinify_dir.glob("*.py")):
        tinify_add_data.append((str(tinify_dir / "*.py"), "tinify"))
    # recursively find .pem files and add each parent folder so subfolders are preserved
    pem_parents = {p.parent for p in tinify_dir.rglob("*.pem")}
    for parent in sorted(pem_parents):
        # compute relative destination inside tinify package
        try:
            rel = parent.relative_to(tinify_dir)
        except Exception:
            rel = None
        if rel and str(rel) != ".":
            dest = f"tinify/{str(rel).replace('\\\\', '/') }"
        else:
            dest = "tinify"
        tinify_add_data.append((str(parent / "*.pem"), dest))


site_packages = Path(rapidocr.__file__).resolve().parent.parent


mower_a = Analysis(
    ["webview_ui.py"],
    pathex=[],
    binaries=[],
    datas=get_pyinstaller_common_datas()
    + [
        (
            f"{site_packages}/onnxruntime/capi/onnxruntime_providers_shared.dll",
            "onnxruntime/capi/",
        ),
        (f"{site_packages}/pyzbar/libzbar-64.dll", "."),
        (f"{site_packages}/pyzbar/libiconv.dll", "."),
    ]
    + get_rapidocr_datas()
    + tinify_add_data,
    hiddenimports=(
        ["rapidocr.main", "quickjs", "_quickjs"]
        + (["tinify"] if _tinify_installed else [])
        + collect_submodules("psutil")
        + [
            "arknights_mower.utils.instance_supervisor",
            "arknights_mower.utils.crash_recovery",
            "arknights_mower.utils.jpeg_worker",
            "arknights_mower.utils.jpeg_codec",
        ]
    ),
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "transformers",
        "tokenizers",
        "safetensors",
        "huggingface_hub",
        "accelerate",
        "scipy",
        "skimage",
        "sklearn",
        "opencv_videoio_ffmpeg",
        "sympy",
        "mpmath",
        "setuptools",
        "pkg_resources",
        "pygments",
        "rich",
        "fsspec",
        "xlsxwriter",
        "openpyxl",
        "_pytest",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

mower_pure = [i for i in mower_a.pure if not i[0].startswith("arknights_mower")]

mower_pyz = PYZ(
    mower_pure,
    mower_a.zipped_data,
    cipher=block_cipher,
)


mower_exe = EXE(
    mower_pyz,
    mower_a.scripts,
    [],
    exclude_binaries=True,
    name="mower",
    uac_admin=False,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="logo.ico",
)


manager_a = Analysis(
    ["manager.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "setuptools",
        "pkg_resources",
        "sympy",
        "mpmath",
        "pygments",
        "rich",
        "fsspec",
        "xlsxwriter",
        "openpyxl",
        "_pytest",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

manager_pyz = PYZ(
    manager_a.pure,
    manager_a.zipped_data,
    cipher=block_cipher,
)

manager_exe = EXE(
    manager_pyz,
    manager_a.scripts,
    [],
    exclude_binaries=True,
    name="多开管理器",
    uac_admin=False,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="logo.ico",
)


coll = COLLECT(
    mower_exe,
    mower_a.binaries,
    mower_a.zipfiles,
    mower_a.datas,
    manager_exe,
    manager_a.binaries,
    manager_a.zipfiles,
    manager_a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="mower",
)
