# -*- mode: python ; coding: utf-8 -*-
"""倒计时挂件的绿色单文件打包配置。

用法（在项目根目录执行）：

    python -m PyInstaller countdown_widget.spec

产物：dist/mower-countdown.exe（单文件、免安装、带图标）。
打包前请先退出正在运行的 mower-countdown.exe，否则替换文件会被占用。

要点说明：
- onefile：EXE(...) 直接接收 a.binaries / a.datas，不再经过 COLLECT。
- console=False：双击运行不弹黑色控制台（程序内部已处理无 stdout 的情况）。
- datas：把 ico 放进包内，运行时用 sys._MEIPASS 定位（见 countdown_widget.resource_path）。
- excludes：本工具只发自己的 HTTP/HTTPS 请求，不需要 requests/cryptography 那一套，
  排除后能把 exe 从约 15 MB 压到约 13 MB。
  **必须保留 ssl / _ssl**：工具支持 `--host https://...`（含 `--insecure`），
  排除后会在启动时直接 ImportError 崩溃（已踩过：`ModuleNotFoundError: No module named 'ssl'`）；
  保留 ssl 会连带带上 libssl-3.dll / libcrypto-3.dll（约 2.5 MB 压缩后体积）。
  如果哪天不再需要 HTTPS，可先删掉代码里的 ssl 用法，再把 ssl/_ssl 加回 excludes 进一步瘦身。
"""

a = Analysis(
    ["countdown_widget.py"],
    pathex=[],
    binaries=[],
    datas=[("countdown_widget.ico", ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "cryptography",
        "requests",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "tkinter.test",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mower-countdown",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="countdown_widget.ico",
)
