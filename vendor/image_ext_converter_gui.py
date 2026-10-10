# -*- coding: utf-8 -*-
"""
Image Extension Converter GUI (simple inline options)
- 画像/フォルダ一括の拡張子変換
- PySimpleGUI v4 / FreeSimpleGUI 柔軟フォールバック
- EXIF 自動回転・EXIF の継承
- 透過の扱い（アルファ不可形式は白で合成）
- オプションは横一列に Text/Spin/Checkbox/Input を並べるだけ
"""

import os, sys, glob, shutil, threading, platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple, Dict

# ===== SG フォールバック =====
_BACKEND = None
try:
    import FreeSimpleGUI as sg  # v4 互換フォーク
    _BACKEND = "FreeSimpleGUI(v4 fork)"
except Exception:
    try:
        import PySimpleGUI as sg
        _BACKEND = "PySimpleGUI(v4)"
    except Exception as e:
        raise ImportError(
            "GUI backend not found. Install FreeSimpleGUI or place PySimpleGUI.py locally."
        ) from e

# ===== Pillow =====
from PIL import Image, ImageOps
try:
    import pillow_heif  # HEIC/HEIF
    pillow_heif.register_heif_opener()
    _HAS_HEIF = True
except Exception:
    _HAS_HEIF = False

# AVIF（pillow-avif-plugin を入れると自動で対応）
try:
    import pillow_avif  # noqa: F401
    _HAS_AVIF = True
except Exception:
    _HAS_AVIF = False

# =========================
# ユーティリティ
# =========================
def is_image(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in {
        ".jpg",".jpeg",".png",".bmp",".tif",".tiff",".webp",".heic",".heif",".avif",".ico"
    }

def ensure_dir(d: str) -> None:
    os.makedirs(d, exist_ok=True)

def gather_images(file_input: Optional[str], dir_input: Optional[str], pattern: str, recursive: bool) -> List[str]:
    out: List[str] = []
    if file_input:
        f = os.path.abspath(file_input)
        if os.path.isfile(f) and is_image(f):
            out.append(f)
    if dir_input and os.path.isdir(dir_input):
        root = os.path.abspath(dir_input)
        pats = [p.strip() for p in pattern.split(";") if p.strip()]
        if not pats:
            pats = ["*.jpg","*.jpeg","*.png","*.bmp","*.tif","*.tiff","*.webp","*.heic","*.heif","*.avif","*.ico"]
        for pat in pats:
            pat2 = ("**/" + pat) if recursive else pat
            for p in glob.iglob(os.path.join(root, pat2), recursive=recursive):
                if os.path.isfile(p) and is_image(p):
                    out.append(os.path.abspath(p))
    return list(dict.fromkeys(out))  # 重複排除・順序保持

def suggest_jobs() -> int:
    n = os.cpu_count() or 4
    return max(1, min(16, n - 1))

# =========================
# 既定保存パラメータ
# =========================
DEFAULTS: Dict[str, Dict] = {
    "png":  {"optimize": True, "compress_level": 6},
    "jpeg": {"quality": 90, "progressive": True, "subsampling": "4:2:0"},
    "jpg":  {"quality": 90, "progressive": True, "subsampling": "4:2:0"},
    "webp": {"quality": 90, "method": 4, "lossless": False},
    "avif": {"quality": 50},
    "heic": {"quality": 80},
    "tiff": {"compression": "tiff_lzw"},
    "bmp":  {},
    "ico":  {"sizes": [(16,16),(32,32),(48,48),(64,64)]},
}

# 透過を保持できない形式（簡便化のため TIFF もここに含む）
_ALPHA_UNSUPPORTED = {"jpg", "jpeg", "bmp", "heic", "avif", "tiff"}

# =========================
# 画像ロード & 事前処理
# =========================
def load_image_autorotate(path: str) -> Image.Image:
    img = Image.open(path)
    return ImageOps.exif_transpose(img)  # EXIF orientation 反映

def flatten_alpha(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """アルファがある場合、bg に合成して RGB に"""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        base = Image.new("RGB", img.size, bg)
        alpha = img.split()[-1] if img.mode in ("LA", "RGBA") else Image.new("L", img.size, 255)
        base.paste(img.convert("RGB"), mask=alpha)
        return base
    if img.mode not in ("RGB", "L"):
        return img.convert("RGB")
    return img

def prepare_for_format(img: Image.Image, fmt: str) -> Image.Image:
    if fmt.lower() in _ALPHA_UNSUPPORTED:
        return flatten_alpha(img)
    return img

def pick_exif(img: Image.Image, fmt: str):
    # EXIF は JPEG/TIFF/HEIC でよく使う
    if "exif" in img.info and fmt.lower() in {"jpeg", "jpg", "tiff", "heic"}:
        return img.info["exif"]
    return None

# =========================
# 保存
# =========================
def save_image(img: Image.Image, out_path: str, fmt: str, overrides: Optional[Dict]=None) -> None:
    fmt_key = fmt.lower()
    params = dict(DEFAULTS.get(fmt_key, {}))
    if overrides:
        params.update(overrides)
    exif = pick_exif(img, fmt_key)
    if exif is not None:
        params["exif"] = exif

    try:
        img.save(out_path, format=fmt.upper(), **params)
    except TypeError:
        # 未対応キーは自動でスキップ
        safe = {}
        for k, v in list(params.items()):
            try:
                img.save(out_path, format=fmt.upper(), **{k: v})
                safe[k] = v
            except TypeError:
                pass
        img.save(out_path, format=fmt.upper(), **safe)

# =========================
# オプション収集（拡張子に応じて必要な値だけ使う）
# =========================
def collect_overrides(values: Dict, ext: str) -> Dict:
    ext = (ext or "png").lower()
    ov: Dict = {}
    if ext in ("jpg","jpeg"):
        ov["quality"] = int(values["-Q_JPEG-"])
        ov["progressive"] = bool(values["-PROG_JPEG-"])
        subs = values["-SUBS_JPEG-"]
        if subs: ov["subsampling"] = subs
    elif ext == "png":
        ov["optimize"] = bool(values["-OPT_PNG-"])
        ov["compress_level"] = int(values["-CL_PNG-"])
    elif ext == "webp":
        lossless = bool(values["-LOSS_WEBP-"])
        ov["lossless"] = lossless
        if not lossless:
            ov["quality"] = int(values["-Q_WEBP-"])
        ov["method"] = int(values["-M_WEBP-"])
    elif ext == "avif":
        ov["quality"] = int(values["-Q_AVIF-"])
    elif ext in ("heic","heif"):
        ov["quality"] = int(values["-Q_HEIC-"])
    elif ext == "tiff":
        comp = values["-COMP_TIFF-"]
        if comp: ov["compression"] = comp
    elif ext == "ico":
        raw = values["-SIZES_ICO-"].strip()
        try:
            nums = [int(x) for x in raw.split()]
            ov["sizes"] = [(n,n) for n in nums if n > 0]
        except Exception:
            pass
    return ov

# =========================
# バッチ変換
# =========================
def convert_one(path: str, out_dir: Optional[str], target_ext: str, overwrite: bool, overrides: Optional[Dict]) -> Tuple[bool, str]:
    try:
        img = load_image_autorotate(path)
        img = prepare_for_format(img, target_ext)

        stem = os.path.splitext(os.path.basename(path))[0]
        if out_dir:
            ensure_dir(out_dir)
            out_path = os.path.join(out_dir, f"{stem}.{target_ext}")
        else:
            out_path = os.path.join(os.path.dirname(path), f"{stem}.{target_ext}")

        if (not overwrite) and os.path.exists(out_path):
            return True, f"SKIP (exists): {os.path.basename(out_path)}"

        save_image(img, out_path, target_ext, overrides)
        return True, f"OK: {os.path.basename(path)} -> {os.path.basename(out_path)}"
    except Exception as e:
        return False, f"NG: {os.path.basename(path)} -> {e}"

# =========================
# GUI
# =========================
sg.theme("TealMono")

TARGETS = ["png","jpg","jpeg","webp","avif","heic","tiff","bmp","ico"]

# 横並びのシンプルなオプション行
OPTIONS_ROW = [
    sg.Text("JPEG quality"), sg.Spin([i for i in range(1,101)], initial_value=90, key="-Q_JPEG-", size=(4,1)),
    sg.Text("progressive"), sg.Checkbox("", key="-PROG_JPEG-", default=True),
    sg.Text("subsampling"), sg.Combo(["4:4:4","4:2:2","4:2:0"], default_value="4:2:0", key="-SUBS_JPEG-", size=(6,1)),

    sg.Text(" | PNG optimize"), sg.Checkbox("", key="-OPT_PNG-", default=True),
    sg.Text("compress_level"), sg.Spin([i for i in range(0,10)], initial_value=6, key="-CL_PNG-", size=(3,1)),

    sg.Text(" | WEBP lossless"), sg.Checkbox("", key="-LOSS_WEBP-", default=False),
    sg.Text("quality"), sg.Spin([i for i in range(1,101)], initial_value=90, key="-Q_WEBP-", size=(4,1)),
    sg.Text("method(0-6)"), sg.Spin([i for i in range(0,7)], initial_value=4, key="-M_WEBP-", size=(3,1)),

    sg.Text(" | AVIF quality"), sg.Spin([i for i in range(1,101)], initial_value=50, key="-Q_AVIF-", size=(4,1)),

    sg.Text(" | HEIC quality"), sg.Spin([i for i in range(1,101)], initial_value=80, key="-Q_HEIC-", size=(4,1)),

    sg.Text(" | TIFF compression"),
    sg.Combo(["tiff_lzw","tiff_deflate","tiff_adobe_deflate","packbits","none"], default_value="tiff_lzw", key="-COMP_TIFF-", size=(14,1)),

    sg.Text(" | ICO sizes"), sg.Input("16 32 48 64", key="-SIZES_ICO-", size=(15,1)),
]

layout = [
    [sg.Text("画像拡張子 変換ツール", font=("Segoe UI", 12, "bold"))],
    [sg.Frame("入力", [
        [sg.Text("単一画像"), sg.Input(key="-IMGFILE-", size=(52,1)), sg.FileBrowse(file_types=(("Images","*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.webp;*.heic;*.heif;*.avif;*.ico"),("All","*.*")))]
    ])],
    [sg.Frame("フォルダ入力（任意）", [
        [sg.Text("画像フォルダ"), sg.Input(key="-IMGDIR-", size=(52,1)), sg.FolderBrowse()],
        [sg.Checkbox("サブフォルダ再帰", key="-REC-", default=True),
         sg.Text("パターン( ; 区切り)"), sg.Input("*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.webp;*.heic;*.heif;*.avif;*.ico", key="-PAT-", size=(50,1))]
    ])],
    [sg.Frame("出力設定", [
        [sg.Text("ターゲット拡張子"),
         sg.Combo(TARGETS, default_value="png", key="-EXT-", size=(10,1), enable_events=True),
         sg.Text("出力先（未指定なら元の場所）"), sg.Input(key="-OUTDIR-", size=(36,1)), sg.FolderBrowse()],
        [sg.Checkbox("既存出力を上書き", key="-OVW-", default=False),
         sg.Text("並列ジョブ数"), sg.Spin([i for i in range(1,17)], initial_value=suggest_jobs(), key="-JOBS-", size=(4,1))]
    ])],
    [sg.Frame("保存オプション（拡張子に応じて有効化）", [OPTIONS_ROW])],
    [sg.Frame("環境情報", [
        [sg.Text(f"Backend: {_BACKEND} | Python: {platform.python_version()} | Pillow: {Image.__version__} | HEIF: {('ON' if _HAS_HEIF else 'OFF')} | AVIF: {('ON' if _HAS_AVIF else 'OFF')}")]
    ])],
    [sg.ProgressBar(max_value=100, orientation="h", size=(50,20), key="-PROG-")],
    [sg.Multiline(size=(100,12), key="-LOG-", autoscroll=True, disabled=True)],
    [sg.Button("変換開始", key="-RUN-"), sg.Button("終了")]
]

window = sg.Window("Image Extension Converter", layout, finalize=True)

# 拡張子ごとに有効化するキー（それ以外は disable）
ENABLE_MAP = {
    "jpg":  ["-Q_JPEG-","-PROG_JPEG-","-SUBS_JPEG-"],
    "jpeg": ["-Q_JPEG-","-PROG_JPEG-","-SUBS_JPEG-"],
    "png":  ["-OPT_PNG-","-CL_PNG-"],
    "webp": ["-LOSS_WEBP-","-Q_WEBP-","-M_WEBP-"],
    "avif": ["-Q_AVIF-"],
    "heic": ["-Q_HEIC-"],
    "tiff": ["-COMP_TIFF-"],
    "bmp":  [],
    "ico":  ["-SIZES_ICO-"],
}

ALL_OPTION_KEYS = [k for ks in ENABLE_MAP.values() for k in ks]
ALL_OPTION_KEYS = sorted(set(ALL_OPTION_KEYS))

def set_enabled_for_ext(ext: str):
    ext = (ext or "png").lower()
    allow = set(ENABLE_MAP.get(ext, []))
    for k in ALL_OPTION_KEYS:
        window[k].update(disabled=(k not in allow))

# 初期状態（png）
set_enabled_for_ext("png")

def log(s: str):
    window["-LOG-"].update(s + "\n", append=True)

def set_progress(cur: int, total: int):
    total = max(total, 1)
    pct = int(cur * 100 / total)
    window["-PROG-"].update(current_count=pct)

def run_convert(values):
    img_file = values["-IMGFILE-"].strip()
    img_dir  = values["-IMGDIR-"].strip()
    recursive = values["-REC-"]
    pattern   = values["-PAT-"].strip()
    outdir    = values["-OUTDIR-"].strip() or None
    overwrite = values["-OVW-"]
    jobs      = int(values["-JOBS-"] or 1)
    target    = (values["-EXT-"] or "png").lower()

    # AVIF / HEIC 可用性チェック
    if target == "avif" and not _HAS_AVIF:
        window.write_event_value("-LOG-", "pillow-avif-plugin がインストールされていないため AVIF は保存できません。")
        return
    if target in {"heic","heif"} and not _HAS_HEIF:
        window.write_event_value("-LOG-", "pillow-heif がインストールされていないため HEIC/HEIF は保存できません。")
        return

    # UIから上書きオプションを収集
    overrides = collect_overrides(values, target)

    targets = gather_images(img_file, img_dir, pattern, recursive)
    if not targets:
        window.write_event_value("-LOG-", "画像が見つかりません。")
        return

    ok = ng = done = 0
    total = len(targets)
    window.write_event_value("-STARTED-", total)

    def _do_one(p: str):
        return convert_one(p, outdir, target, overwrite, overrides)

    if jobs <= 1:
        for p in targets:
            success, msg = _do_one(p)
            done += 1; ok += int(success); ng += int(not success)
            window.write_event_value("-STEP-", (done, total, msg))
    else:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            futs = {ex.submit(_do_one, p): p for p in targets}
            for fut in as_completed(futs):
                success, msg = fut.result()
                done += 1; ok += int(success); ng += int(not success)
                window.write_event_value("-STEP-", (done, total, msg))

    window.write_event_value("-FINISHED-", (ok, ng, total))

# ===== イベントループ =====
while True:
    event, values = window.read(timeout=100)
    if event in (sg.WIN_CLOSED, "終了"):
        break

    if event == "-RUN-":
        window["-LOG-"].update("")
        window["-PROG-"].update(current_count=0)
        log("変換を開始します…")
        threading.Thread(target=run_convert, args=(values,), daemon=True).start()

    if event == "-STARTED-":
        total = values[event]
        set_progress(0, total if isinstance(total, int) else 100)

    if event == "-STEP-":
        done, total, msg = values[event]
        log(msg)
        set_progress(done, total)

    if event == "-FINISHED-":
        ok, ng, total = values[event]
        log(f"\nSummary: OK={ok}, NG={ng}, Total={total}")
        set_progress(total, total)

    if event == "-LOG-":
        log(values[event])

    if event == "-EXT-":
        set_enabled_for_ext(values["-EXT-"])

window.close()
# EOF
