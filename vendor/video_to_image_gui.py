import sys, os, glob, shutil, subprocess, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
import platform

# --- Flexible SG import (v4優先) -------------------------
tp = os.path.join(os.path.dirname(__file__), "third_party")
if os.path.isdir(tp) and tp not in sys.path:
    sys.path.insert(0, tp)
_BACKEND = None

try:
    import FreeSimpleGUI as sg
    _BACKEND = "FreeSimpleGUI(v4 fork)"
except Exception:
    try:
        import PySimpleGUI as sg
        _BACKEND = "PySimpleGUI(v4 local/wrapper)"
    except Exception as e:
        raise ImportError(
            "No usable SG backend found. "
            "Place PySimpleGUI.py (v4) locally OR `pip install FreeSimpleGUI` "
        ) from e
finally:
    print(f"[INFO] GUI backend: {_BACKEND}")

# =========================
#  基本ユーティリティ
# =========================

def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def parse_time_to_seconds(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        pass
    parts = s.split(":")
    try:
        parts = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"Invalid time format: {s}")
    if len(parts) == 3:
        h, m, sec = parts
        return h * 3600 + m * 60 + sec
    if len(parts) == 2:
        m, sec = parts
        return m * 60 + sec
    raise ValueError(f"Invalid time format: {s}")

def sec_to_ffmpeg_str(sec: Optional[float]) -> Optional[str]:
    if sec is None:
        return None
    return f"{sec}"

def build_output_path(src: str, root: str, outdir: Optional[str], keep_structure: bool,
                      fmt: str) -> str:
    """
    通常のアニメ形式は拡張子のみ差し替え。
    連番形式(*_seq)は basename_0001.ext というファイルパターン文字列を返す。
    """
    base_noext = os.path.splitext(os.path.basename(src))[0]
    if fmt == "gif":
        filename = base_noext + ".gif"
    elif fmt == "webp":
        filename = base_noext + ".webp"
    elif fmt == "apng":
        filename = base_noext + ".png"  # APNGは拡張子png
    elif fmt == "png_seq":
        filename = base_noext + "_%04d.png"
    elif fmt in ("jpg_seq", "jpeg_seq"):
        ext = "jpg" if fmt == "jpg_seq" else "jpeg"
        filename = f"{base_noext}_%04d.{ext}"
    elif fmt == "bmp_seq":
        filename = base_noext + "_%04d.bmp"
    elif fmt == "tiff_seq":
        filename = base_noext + "_%04d.tiff"
    elif fmt == "heic_seq":
        filename = base_noext + "_%04d.heic"
    else:
        filename = base_noext + ".gif"

    if outdir:
        if keep_structure and root:
            rel = os.path.relpath(os.path.dirname(src), start=root)
            dest_dir = os.path.join(outdir, rel)
        else:
            dest_dir = outdir
    else:
        dest_dir = os.path.dirname(src)
    os.makedirs(dest_dir, exist_ok=True)
    return os.path.join(dest_dir, filename)

def gather_files(
    file_input: Optional[str],
    dir_input: Optional[str],
    pattern: str,
    recursive: bool
) -> List[Tuple[str, str]]:
    tasks: List[Tuple[str, str]] = []
    if file_input:
        p = os.path.abspath(file_input)
        if os.path.isfile(p) and p.lower().endswith(".mp4"):
            tasks.append((p, os.path.dirname(p)))
    if dir_input and os.path.isdir(dir_input):
        root = os.path.abspath(dir_input)
        pat = "**/" + pattern if recursive else pattern
        for p in glob.iglob(os.path.join(root, pat), recursive=recursive):
            p = os.path.abspath(p)
            if os.path.isfile(p) and p.lower().endswith(".mp4"):
                tasks.append((p, root))
    seen = set()
    uniq = []
    for src, root in tasks:
        if src not in seen:
            uniq.append((src, root))
            seen.add(src)
    return uniq

# =========================
#  バージョン情報
# =========================

def _first_line(text: str) -> str:
    return (text.splitlines() or [""])[0].strip()

def _run_version(cmd: str) -> Optional[str]:
    path = shutil.which(cmd)
    if not path:
        return None
    try:
        proc = subprocess.run(
            [cmd, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0 and proc.stdout:
            return _first_line(proc.stdout)
        return f"{cmd} found at {path} (version output unavailable)"
    except Exception as e:
        return f"{cmd} found at {path} (error: {e})"

def get_versions_text() -> str:
    sg_ver = getattr(sg, "__version__", getattr(sg, "version", "unknown"))
    lines = [
        f"Python: {platform.python_version()} ({platform.python_implementation()})",
        f"Platform: {platform.platform()}",
        f"GUI backend: {_BACKEND}, version: {sg_ver}",
        f"ffmpeg path: {shutil.which('ffmpeg') or 'NOT FOUND'}",
        f"ffmpeg: {_run_version('ffmpeg') or 'NOT FOUND'}",
        f"ffprobe path: {shutil.which('ffprobe') or 'NOT FOUND'}",
        f"ffprobe: {_run_version('ffprobe') or 'NOT FOUND'}",
    ]
    return "\n".join(lines)

# =========================
#  プリセット（形式ごとのデフォルト）
# =========================

DEFAULTS = {
    "gif":      {"fps": 12, "width": 480, "loop": 0, "dither": "sierra2_4a", "quality": None, "crf": None},
    "webp":     {"fps": 15, "width": 720, "loop": 0, "dither": "sierra2_4a", "quality": 80,   "crf": None},
    "apng":     {"fps": 15, "width": 720, "loop": 0, "dither": "sierra2_4a", "quality": None, "crf": None},
    "png_seq":  {"fps": 10, "width": 720, "loop": 0, "dither": "sierra2_4a", "quality": None, "crf": None},
    "jpg_seq":  {"fps": 10, "width": 720, "loop": 0, "dither": "sierra2_4a", "quality": 3,    "crf": None},  # q:v 2-31（小さいほど高画質）
    "jpeg_seq": {"fps": 10, "width": 720, "loop": 0, "dither": "sierra2_4a", "quality": 3,    "crf": None},  # jpg_seq と同等
    "bmp_seq":  {"fps": 5,  "width": 720, "loop": 0, "dither": "sierra2_4a", "quality": None, "crf": None},
    "tiff_seq": {"fps": 5,  "width": 720, "loop": 0, "dither": "sierra2_4a", "quality": None, "crf": None},
    "heic_seq": {"fps": 5,  "width": 1080,"loop": 0, "dither": "sierra2_4a", "quality": None, "crf": 28},   # libx265 のCRF
}

# =========================
#  変換ロジック（FFmpeg）
# =========================

def ffmpeg_convert(
    input_path: str,
    output_path: str,
    fmt: str,
    fps: int = 12,
    width: Optional[int] = 480,
    start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
    loop: int = 0,
    dither: str = "sierra2_4a",
    quality: Optional[int] = None,
    crf: Optional[int] = None,
) -> None:
    if not has_ffmpeg():
        raise RuntimeError("FFmpeg not found. Ensure it's in PATH.")

    vf_steps = []
    if fps and fps > 0:
        vf_steps.append(f"fps={fps}")
    if width and width > 0:
        vf_steps.append(f"scale={width}:-1:flags=lanczos")
    vf_core = ",".join(vf_steps) if vf_steps else "scale=iw:ih"

    # 基本コマンド
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", input_path]
    if start_sec is not None:
        cmd += ["-ss", sec_to_ffmpeg_str(start_sec)]
    if duration_sec is not None:
        cmd += ["-t", sec_to_ffmpeg_str(duration_sec)]

    if fmt == "gif":
        filter_complex = (
            f"[0:v]{vf_core},split[s0][s1];"
            f"[s0]palettegen=stats_mode=single[p];"
            f"[s1][p]paletteuse=dither={dither}"
        )
        cmd += ["-filter_complex", filter_complex, "-gifflags", "+transdiff", "-loop", str(loop), output_path]

    elif fmt == "webp":
        # アニメWebP（libwebp）
        q = str(quality if (quality is not None) else (DEFAULTS["webp"]["quality"]))
        cmd += ["-vf", vf_core, "-an", "-c:v", "libwebp", "-quality", q, "-loop", str(loop), output_path]

    elif fmt == "apng":
        # APNG（-plays 0 で無限ループ）
        plays = str(loop) if loop > 0 else "0"
        cmd += ["-vf", vf_core, "-plays", plays, output_path]

    elif fmt in ("png_seq", "bmp_seq", "tiff_seq", "jpg_seq", "jpeg_seq"):
        # 連番（JPG/JPEGのみ品質あり）
        cmd += ["-vf", vf_core, "-vsync", "0"]
        if fmt in ("jpg_seq", "jpeg_seq"):
            qv = str(quality if (quality is not None) else (DEFAULTS["jpg_seq"]["quality"]))
            cmd += ["-q:v", qv]
        cmd += [output_path]

    elif fmt == "heic_seq":
        # HEIC 連番（libx265 + HEIF muxer相当）。環境により未対応の可能性あり。
        # 可能なら -c:v libx265 -tag:v hvc1 -crf <n>
        cmd += ["-vf", vf_core, "-vsync", "0", "-c:v", "libx265", "-tag:v", "hvc1"]
        if crf is not None:
            cmd += ["-crf", str(crf)]
        else:
            cmd += ["-crf", str(DEFAULTS["heic_seq"]["crf"])]
        cmd += [output_path]

    else:
        raise ValueError(f"Unsupported format: {fmt}")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "FFmpeg conversion failed")

def convert_one(
    src: str,
    dst: str,
    fmt: str,
    fps: int,
    width: Optional[int],
    start: Optional[str],
    duration: Optional[str],
    loop: int,
    dither: str,
    overwrite: bool,
    quality: Optional[int],
    crf: Optional[int],
) -> Tuple[bool, str]:
    try:
        # 連番は存在チェックが難しいため常に実行（ユーザーが上書き管理）
        if (not overwrite) and ("%04d" not in os.path.basename(dst)) and os.path.exists(dst):
            return True, f"SKIP (exists): {dst}"

        start_sec = parse_time_to_seconds(start) if start else None
        dur_sec = parse_time_to_seconds(duration) if duration else None

        ffmpeg_convert(
            input_path=src,
            output_path=dst,
            fmt=fmt,
            fps=fps,
            width=width,
            start_sec=start_sec,
            duration_sec=dur_sec,
            loop=loop,
            dither=dither,
            quality=quality,
            crf=crf,
        )
        return True, f"OK: {dst}"
    except Exception as e:
        return False, f"NG: {os.path.basename(src)} -> {e}"

# =========================
#  GUI
# =========================

sg.theme("TealMono")

FORMAT_CHOICES = ["gif","webp","apng","png_seq","jpg_seq","jpeg_seq","bmp_seq","tiff_seq","heic_seq"]

layout = [
    [sg.Text("MP4 → 画像形式 変換（FFmpeg）", font=("Segoe UI", 12, "bold"))],
    [sg.Frame("入力", [
        [sg.Text("単一MP4"), sg.Input(key="-INFILE-", size=(50,1)), sg.FileBrowse(file_types=(("MP4","*.mp4"),("All","*.*")))],
        [sg.Text("フォルダ"), sg.Input(key="-INDIR-", size=(50,1)), sg.FolderBrowse()],
        [sg.Checkbox("サブフォルダも含める（再帰）", key="-REC-", default=True),
         sg.Text("パターン"), sg.Input("*.mp4", key="-PAT-", size=(15,1))]
    ])],
    [sg.Frame("出力", [
        [sg.Text("出力先フォルダ（未指定なら元ファイル横）"), sg.Input(key="-OUTDIR-", size=(46,1)), sg.FolderBrowse()],
        [sg.Checkbox("元のフォルダ階層を保持", key="-KEEP-", default=True),
         sg.Checkbox("既存ファイルを上書き（アニメ/単体）", key="-OVW-")],
    ])],
    [sg.Frame("変換パラメータ", [
        [sg.Text("出力形式"),
         sg.Combo(FORMAT_CHOICES, default_value="gif", key="-FMT-", size=(12,1), enable_events=True),
         sg.Text("FPS"), sg.Input(str(DEFAULTS["gif"]["fps"]), key="-FPS-", size=(6,1)),
         sg.Text("幅(px)"), sg.Input(str(DEFAULTS["gif"]["width"]), key="-W-", size=(6,1)),
         sg.Text("Start"), sg.Input("", key="-START-", size=(10,1)),
         sg.Text("Duration"), sg.Input("", key="-DUR-", size=(10,1)),
        ],
        [sg.Text("Loop(0=∞)"), sg.Input(str(DEFAULTS["gif"]["loop"]), key="-LOOP-", size=(5,1)),
         sg.Text("Dither(GIF)"), sg.Combo(["sierra2_4a","bayer","floyd_steinberg","heckbert"],
                                      default_value=DEFAULTS["gif"]["dither"], key="-DITHER-", size=(15,1)),
         sg.Text("Quality(WebP 0-100 / JPG 2-31)"), sg.Input("", key="-QUAL-", size=(8,1)),
         sg.Text("CRF(HEIC/libx265)"), sg.Input("", key="-CRF-", size=(6,1)),
         sg.Push(), sg.Button("形式のデフォルトに戻す", key="-APPLY-DEFAULTS-")
        ],
        [sg.Text("並列ジョブ数"), sg.Spin([i for i in range(1, 17)], initial_value=1, key="-JOBS-", size=(5,1)),
         sg.Text("FFmpeg検出:"), sg.Text("未確認", key="-FFMPEG-STATUS-", text_color="orange"),
         sg.Push(), sg.Button("バージョン情報", key="-SHOW-VER-")]
    ])],
    [sg.ProgressBar(max_value=100, orientation="h", size=(50,20), key="-PROG-")],
    [sg.Multiline(size=(100,12), key="-LOG-", autoscroll=True, disabled=True)],
    [sg.Button("一括変換", key="-BATCH-"), sg.Button("単体変換", key="-ONE-"), sg.Button("Exit")]
]

window = sg.Window("MP4 → Multi Image Converter (FFmpeg GUI)", layout, finalize=True)
window["-FFMPEG-STATUS-"].update("OK" if has_ffmpeg() else "NG", text_color=("green" if has_ffmpeg() else "red"))

def log_print(text: str):
    window["-LOG-"].update(text + "\n", append=True)

def set_progress(current: int, total: int):
    total = max(total, 1)
    pct = int(current * 100 / total)
    window["-PROG-"].update(current_count=pct)

def _parse_quality(fmt: str, qual_str: str) -> Optional[int]:
    if not qual_str:
        return None
    try:
        q = int(qual_str)
    except ValueError:
        return None
    if fmt == "webp":
        return max(0, min(100, q))
    if fmt in ("jpg_seq", "jpeg_seq"):
        return max(2, min(31, q))
    return None

def _parse_crf(crf_str: str) -> Optional[int]:
    if not crf_str:
        return None
    try:
        q = int(crf_str)
    except ValueError:
        return None
    # x265の一般的な範囲目安 0(無劣化)〜51（低画質）
    return max(0, min(51, q))

def _apply_defaults_to_fields(fmt: str):
    d = DEFAULTS.get(fmt, DEFAULTS["gif"])
    window["-FPS-"].update(str(d["fps"]))
    window["-W-"].update(str(d["width"]))
    window["-LOOP-"].update(str(d["loop"]))
    window["-DITHER-"].update(d["dither"])
    window["-QUAL-"].update("" if d["quality"] is None else str(d["quality"]))
    window["-CRF-"].update("" if d["crf"] is None else str(d["crf"]))

def worker_batch(values):
    infile = values["-INFILE-"].strip()
    indir = values["-INDIR-"].strip()
    pattern = values["-PAT-"].strip() or "*.mp4"
    recursive = values["-REC-"]
    outdir = values["-OUTDIR-"].strip() or None
    keep = values["-KEEP-"]
    overwrite = values["-OVW-"]
    fmt = values["-FMT-"]

    fps = int(values["-FPS-"] or DEFAULTS[fmt]["fps"])
    width = int(values["-W-"] or DEFAULTS[fmt]["width"])
    start = values["-START-"].strip() or None
    dur = values["-DUR-"].strip() or None
    loop = int(values["-LOOP-"] or DEFAULTS[fmt]["loop"])
    dither = values["-DITHER-"]
    quality = _parse_quality(fmt, values["-QUAL-"].strip())
    crf = _parse_crf(values["-CRF-"].strip())

    targets = gather_files(infile, indir, pattern, recursive)
    window.write_event_value("-BATCH-STARTED-", len(targets))

    if not targets:
        window.write_event_value("-LOG-", "変換対象が見つかりません。入力ファイル/フォルダとパターンを確認してください。")
        window.write_event_value("-PROG-", (0, 1))
        return

    tasks = []
    for src, root in targets:
        dst = build_output_path(src, root, outdir, keep, fmt)
        tasks.append((src, root, dst))

    ok = ng = done = 0
    jobs = int(values["-JOBS-"] or 1)

    if jobs <= 1:
        for (src, _root, dst) in tasks:
            success, msg = convert_one(src, dst, fmt, fps, width, start, dur, loop, dither, overwrite, quality, crf)
            done += 1
            ok += int(success); ng += int(not success)
            window.write_event_value("-ONE-DONE-", (done, len(tasks), msg))
    else:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            future_map = {
                ex.submit(convert_one, src, dst, fmt, fps, width, start, dur, loop, dither, overwrite, quality, crf): (src, dst)
                for (src, _root, dst) in tasks
            }
            for fut in as_completed(future_map):
                try:
                    success, msg = fut.result()
                except Exception as e:
                    success, msg = False, f"NG: worker crashed -> {e}"
                done += 1
                ok += int(success); ng += int(not success)
                window.write_event_value("-ONE-DONE-", (done, len(tasks), msg))

    window.write_event_value("-BATCH-FINISHED-", (ok, ng, len(tasks)))

def worker_one(values):
    infile = values["-INFILE-"].strip()
    if not infile:
        window.write_event_value("-LOG-", "単体変換：入力MP4を指定してください。")
        return
    outdir = values["-OUTDIR-"].strip() or None
    keep = values["-KEEP-"]
    fmt = values["-FMT-"]

    fps = int(values["-FPS-"] or DEFAULTS[fmt]["fps"])
    width = int(values["-W-"] or DEFAULTS[fmt]["width"])
    start = values["-START-"].strip() or None
    dur = values["-DUR-"].strip() or None
    loop = int(values["-LOOP-"] or DEFAULTS[fmt]["loop"])
    dither = values["-DITHER-"]
    overwrite = values["-OVW-"]
    quality = _parse_quality(fmt, values["-QUAL-"].strip())
    crf = _parse_crf(values["-CRF-"].strip())

    src = os.path.abspath(infile)
    root = os.path.dirname(src)
    dst = build_output_path(src, root, outdir, keep, fmt)

    window.write_event_value("-BATCH-STARTED-", 1)
    success, msg = convert_one(src, dst, fmt, fps, width, start, dur, loop, dither, overwrite, quality, crf)
    window.write_event_value("-ONE-DONE-", (1, 1, msg))
    window.write_event_value("-BATCH-FINISHED-", (int(success), int(not success), 1))

# =========================
#  イベントループ
# =========================
while True:
    event, values = window.read(timeout=100)
    if event in (sg.WIN_CLOSED, "Exit"):
        break

    if event == "-SHOW-VER-":
        sg.popup_scrolled(get_versions_text(), title="バージョン情報", size=(80, 20))

    if event == "-FMT-":
        _apply_defaults_to_fields(values["-FMT-"])

    if event == "-APPLY-DEFAULTS-":
        _apply_defaults_to_fields(values["-FMT-"])

    if event == "-BATCH-":
        if not has_ffmpeg():
            sg.popup_error("FFmpegが見つかりません。PATH設定を確認してください。")
            continue
        window["-LOG-"].update("")
        window["-PROG-"].update(current_count=0)
        log_print("一括変換を開始します…")
        threading.Thread(target=worker_batch, args=(values,), daemon=True).start()

    if event == "-ONE-":
        if not has_ffmpeg():
            sg.popup_error("FFmpegが見つかりません。PATH設定を確認してください。")
            continue
        window["-LOG-"].update("")
        window["-PROG-"].update(current_count=0)
        log_print("単体変換を開始します…")
        threading.Thread(target=worker_one, args=(values,), daemon=True).start()

    # ワーカー→GUIへの通知
    if event == "-BATCH-STARTED-":
        total = values[event]
        log_print(f"対象ファイル数: {total}")
        set_progress(0, max(total, 1))

    if event == "-ONE-DONE-":
        done, total, msg = values[event]
        log_print(msg)
        set_progress(done, total)

    if event == "-BATCH-FINISHED-":
        ok, ng, total = values[event]
        log_print(f"\nSummary: OK={ok}, NG={ng}, Total={total}")
        set_progress(total, total)

    if event == "-LOG-":
        log_print(values[event])

    if event == "-PROG-":
        cur, total = values[event]
        set_progress(cur, total)

window.close()
# EOF