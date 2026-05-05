# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

live2d_datas = collect_data_files("live2d", include_py_files=False)
live2d_binaries = collect_dynamic_libs("live2d")

hiddenimports = [
    "persona_speech_input_once",
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "sounddevice",
]

excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "tensorboard",
    "paddle",
    "paddleocr",
    "pandas",
    "scipy",
    "matplotlib",
    "cv2",
    "onnx",
    "onnxruntime",
    "sklearn",
    "numba",
]

a = Analysis(
    ["persona_bot_test.py"],
    pathex=[],
    binaries=live2d_binaries,
    datas=live2d_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PersonaPet",
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PersonaPet",
)
