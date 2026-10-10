import os
import glob
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

# ===== Flexible SG import (FreeSimpleGUI優先) =====
import sys
tp = os.path.join(os.path.dirname(__file__), "third_party")
if os.path.isdir(tp) and tp not in sys.path:
    sys.path.insert(0, tp)
_GUI_BACKEND = None
try:
    import FreeSimpleGUI as sg  # 推奨（v4互換）
    _GUI_BACKEND = "FreeSimpleGUI(v4 fork)"
except Exception:
    try:
        import PySimpleGUI as sg
        _GUI_BACKEND = "PySimpleGUI(v4)"
    except Exception as e:
        raise ImportError(
            "No usable SG backend found. Install `FreeSimpleGUI` or `PySimpleGUI`."
        ) from e
finally:
    print(f"[INFO] GUI backend: {_GUI_BACKEND}")

# =========================
#  Utilities
# =========================

SUPPORTED_EXTS = (".mp4", ".m4v", ".mov", ".mkv", ".webm")

AUDIO_FORMATS = [
    "mp3",          # libmp3lame: CBR or VBR(-q:a 0..9)
    "m4a (aac)",    # aac: CBR(-b:a). VBRは環境依存が強いので非推奨
    "wav",          # pcm_s16le: ビットレート設定は無効
    "flac",         # flac: 可逆圧縮。ビットレート設定は無効
    "ogg (vorbis)", # libvorbis: VBR(-q:a 0..9) を推奨
    "opus",         # libopus: ビットレート(-b:a)推奨、VBRはデフォルトで可
]

def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None or shutil.which("ffmpeg.exe") is not None

def parse_time_to_seconds(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    s = s.strip()
    try:
        return float(s)  # plain seconds
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

def normalize_outfmt(outfmt: str) -> str:
    # "m4a (aac)" -> "m4a", "ogg (vorbis)" -> "ogg"
    return outfmt.split()[0].lower().strip()

def default_ext_for_outfmt(outfmt: str) -> str:
    ext = normalize_outfmt(outfmt)
    return f".{ext}"

def build_output_path(src: str, root: str, outdir: Optional[str], keep_structure: bool, outfmt: str) -> str:
    base = os.path.splitext(os.path.basename(src))[0] + default_ext_for_outfmt(outfmt)
    if outdir:
        if keep_structure and root:
            rel = os.path.relpath(os.path.dirname(src), start=root)
            dest_dir = os.path.join(outdir, rel)
        else:
            dest_dir = outdir
    else:
        dest_dir = os.path.dirname(src)
    os.makedirs(dest_dir, exist_ok=True)
    return os.path.join(dest_dir, base)

def gather_files(
    file_input: Optional[str],
    dir_input: Optional[str],
    pattern: str,
    recursive: bool
) -> List[Tuple[str, str]]:
    """
    Return a list of tuples (src_path, root_dir). root_dir is used for keeping folder structure.
    """
    tasks: List[Tuple[str, str]] = []

    if file_input:
        p = os.path.abspath(file_input)
        if os.path.isfile(p) and os.path.splitext(p)[1].lower() in SUPPORTED_EXTS:
            tasks.append((p, os.path.dirname(p)))

    if dir_input and os.path.isdir(dir_input):
        root = os.path.abspath(dir_input)
        pat = "**/" + pattern if recursive else pattern
        for p in glob.iglob(os.path.join(root, pat), recursive=recursive):
            p = os.path.abspath(p)
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in SUPPORTED_EXTS:
                tasks.append((p, root))

    seen = set()
    uniq = []
    for src, root in tasks:
        if src not in seen:
            uniq.append((src, root))
            seen.add(src)
    return uniq

# =========================
#  FFmpeg conversion
# =========================

def codec_args_for_format(
    outfmt: str,
    mode_cbr: bool,              # True=CBR, False=VBR（UI側の希望）
    bitrate: Optional[str],      # 例 "192k"
    vbr_q: Optional[int]         # 0(best) .. 9(worst)
) -> Tuple[list, str]:
    """
    出力形式に応じた -acodec 等の引数セットを返す。
    返り値: (args_list, note)  ※noteはログ向け
    """
    fmt = normalize_outfmt(outfmt)
    args = []
    note = ""

    if fmt == "mp3":
        args += ["-acodec", "libmp3lame"]
        if mode_cbr:
            args += ["-b:a", (bitrate or "192k")]
            note = f"mp3 CBR {bitrate or '192k'}"
        else:
            q = 2 if vbr_q is None else int(vbr_q)
            args += ["-q:a", str(q)]
            note = f"mp3 VBR q={q}"
    elif fmt == "m4a":
        # M4AはAAC。ffmpegビルドによってはlibfdk_aacが無いことが多いので、デフォは内蔵aac
        args += ["-acodec", "aac"]
        # 実質CBR/ABR指定が安定
        args += ["-b:a", (bitrate or "192k")]
        note = f"m4a(aac) {bitrate or '192k'}"
        # m4aコンテナ指定
        args += ["-f", "mp4"]
    elif fmt == "wav":
        args += ["-acodec", "pcm_s16le"]
        note = "wav pcm_s16le"
    elif fmt == "flac":
        args += ["-acodec", "flac"]
        note = "flac lossless"
    elif fmt == "ogg":
        args += ["-acodec", "libvorbis"]
        # vorbisは -q:a が自然（-b:aも可だが品質優先ならq）
        q = 4 if vbr_q is None else int(vbr_q)
        if mode_cbr and bitrate:
            args += ["-b:a", bitrate]
            note = f"ogg(vorbis) CBR {bitrate}"
        else:
            args += ["-q:a", str(q)]
            note = f"ogg(vorbis) VBR q={q}"
    elif fmt == "opus":
        args += ["-acodec", "libopus"]
        # opusは -b:a 指定が分かりやすい（内部VBR）
        args += ["-b:a", (bitrate or "128k")]
        note = f"opus {bitrate or '128k'}"
        # コンテナはogg/opusどちらでもよいが、拡張子opusならOGGコンテナに乗る
    else:
        raise ValueError(f"Unsupported output format: {outfmt}")

    return args, note

def ffmpeg_extract_audio(
    input_path: str,
    output_path: str,
    outfmt: str,
    mode_cbr: bool,              # True=CBR, False=VBR
    cbr_bitrate: Optional[str],
    vbr_q: Optional[int],
    channels: int = 2,           # 1 or 2
    sample_rate: Optional[int] = None,  # e.g., 44100, 48000
    start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
) -> str:
    if not has_ffmpeg():
        raise RuntimeError("FFmpeg not found. Ensure it's in PATH.")

    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", input_path]

    # タイミング：入力後でもOKだが、体感上 入力直後の -ss は高速
    if start_sec is not None:
        cmd += ["-ss", sec_to_ffmpeg_str(start_sec)]
    if duration_sec is not None:
        cmd += ["-t", sec_to_ffmpeg_str(duration_sec)]

    cmd += ["-vn"]  # 映像は捨てる
    cmd += ["-ac", str(2 if channels != 1 else 1)]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]

    more, note = codec_args_for_format(outfmt, mode_cbr, cbr_bitrate, vbr_q)
    cmd += more
    cmd += [output_path]

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

    return note

def convert_one(
    src: str,
    dst: str,
    outfmt: str,
    mode: str,                 # "CBR" or "VBR"
    bitrate: str,
    vbr_q: int,
    ch_str: str,               # "Stereo (2ch)" or "Mono (1ch)"
    sr_str: Optional[str],
    start: Optional[str],
    duration: Optional[str],
    overwrite: bool
):
    try:
        if (not overwrite) and os.path.exists(dst):
            return True, f"SKIP (exists): {dst}"
        start_sec = parse_time_to_seconds(start) if start else None
        dur_sec = parse_time_to_seconds(duration) if duration else None
        channels = 2 if ("Stereo" in ch_str) else 1
        sample_rate = int(sr_str) if (sr_str and sr_str.isdigit()) else None
        mode_cbr = (mode.upper() == "CBR")

        note = ffmpeg_extract_audio(
            input_path=src,
            output_path=dst,
            outfmt=outfmt,
            mode_cbr=mode_cbr,
            cbr_bitrate=(bitrate or None),
            vbr_q=(vbr_q if not mode_cbr else None),
            channels=channels,
            sample_rate=sample_rate,
            start_sec=start_sec,
            duration_sec=dur_sec,
        )
        return True, f"OK: {dst}  [{note}]"
    except Exception as e:
        return False, f"NG: {os.path.basename(src)} -> {e}"

# =========================
#  GUI
# =========================

sg.theme("TealMono")

layout = [
    [sg.Text("Video → Audio Extract (FFmpeg)", font=("Segoe UI", 12, "bold"))],
    [sg.Frame("Input", [
        [sg.Text("Single file"), sg.Input(key="-INFILE-", size=(50,1)),
         sg.FileBrowse(file_types=(("Video","*.mp4;*.m4v;*.mov;*.mkv;*.webm"),("All","*.*")))],
        [sg.Text("Folder    "), sg.Input(key="-INDIR-", size=(50,1)), sg.FolderBrowse()],
        [sg.Checkbox("Include subfolders (recursive)", key="-REC-", default=True),
         sg.Text("Pattern"), sg.Input("*.mp4;*.m4v;*.mov;*.mkv;*.webm", key="-PAT-", size=(34,1))],
        [sg.Text("FFmpeg:"), sg.Text("unknown", key="-FFMPEG-STATUS-", text_color="orange")],
    ])],
    [sg.Frame("Output", [
        [sg.Text("Output folder (empty -> next to source)"), sg.Input(key="-OUTDIR-", size=(46,1)), sg.FolderBrowse()],
        [sg.Checkbox("Keep original folder structure", key="-KEEP-", default=True),
         sg.Checkbox("Overwrite existing files", key="-OVW-")],
        [sg.Text("Format"),
         sg.Combo(AUDIO_FORMATS, default_value="mp3", key="-OUTFMT-", readonly=True, size=(14,1)),
         sg.Text("Mode"),
         sg.Radio("CBR", "MODE", default=True, key="-MODE-CBR-"),
         sg.Radio("VBR", "MODE", default=False, key="-MODE-VBR-"),
         sg.Text("Bitrate"), sg.Combo(["96k","128k","160k","192k","224k","256k","320k"], default_value="192k", key="-BITRATE-", size=(8,1)),
         sg.Text("VBR q(0-9)"), sg.Spin([i for i in range(10)], initial_value=2, key="-VBRQ-", size=(4,1))],
    ])],
    [sg.Frame("Extract params", [
        [sg.Text("Channels"), sg.Combo(["Stereo (2ch)", "Mono (1ch)"], default_value="Stereo (2ch)", key="-CHAN-", size=(14,1)),
         sg.Text("Sample rate"), sg.Combo(["","44100","48000"], default_value="", key="-SR-", size=(8,1)),
         sg.Text("Start"), sg.Input("", key="-START-", size=(10,1)),
         sg.Text("Duration"), sg.Input("", key="-DUR-", size=(10,1)),
         sg.Text("Jobs"), sg.Spin([i for i in range(1, 17)], initial_value=1, key="-JOBS-", size=(5,1))],
        [sg.Text("Note:"), sg.Text("", key="-NOTE-", size=(80,1), text_color="yellow")]
    ])],
    [sg.ProgressBar(max_value=100, orientation="h", size=(50,20), key="-PROG-")],
    [sg.Multiline(size=(100,12), key="-LOG-", autoscroll=True, disabled=True)],
    [sg.Button("Batch Convert", key="-BATCH-"), sg.Button("Convert One", key="-ONE-"), sg.Button("Exit")]
]

window = sg.Window("Video → Audio Extract (FFmpeg GUI)", layout, finalize=True, resizable=True)
window["-FFMPEG-STATUS-"].update("OK" if has_ffmpeg() else "NG", text_color=("green" if has_ffmpeg() else "red"))
window.set_min_size((980, 560))

def log_print(text: str):
    window["-LOG-"].update(text + "\n", append=True)

def set_progress(current: int, total: int):
    total = max(total, 1)
    pct = int(current * 100 / total)
    window["-PROG-"].update(current_count=pct)

def outfmt_note(values) -> str:
    fmt = values["-OUTFMT-"]
    is_cbr = values["-MODE-CBR-"]
    br = values["-BITRATE-"]
    q = int(values["-VBRQ-"] or 2)
    f = normalize_outfmt(fmt)
    if f == "mp3":
        return ("mp3: CBRは-b:a、VBRは-q:a(0=高品質)を使用。"
                f" 現在: {'CBR '+br if is_cbr else 'VBR q='+str(q)}")
    if f == "m4a":
        return "m4a(aac): -b:a によるCBR/ABR指定。VBRは環境依存のため非推奨。"
    if f == "wav":
        return "wav(pcm_s16le): 無圧縮。ビットレート/品質指定は無効。"
    if f == "flac":
        return "flac: 可逆圧縮。ビットレート/品質指定は無効。"
    if f == "ogg":
        return ("ogg(vorbis): 通常はVBR(-q:a)推奨。"
                f" 現在: {'CBR '+br if is_cbr else 'VBR q='+str(q)}")
    if f == "opus":
        return "opus: -b:a で目標ビットレート指定（内部は可変）。"
    return ""

def update_param_enable(values):
    f = normalize_outfmt(values["-OUTFMT-"])
    # 形式ごとに有効/無効を制御（見た目・誤操作防止）
    enable_bitrate = (f in ["mp3", "m4a", "opus", "ogg"])
    enable_q = (f in ["mp3", "ogg"])
    # wav/flac はビットレートもVBRも無効
    if f in ["wav", "flac"]:
        enable_bitrate = False
        enable_q = False
    window["-BITRATE-"].update(disabled=not enable_bitrate)
    window["-VBRQ-"].update(disabled=not enable_q)
    # VBR/CBR 切替の意味が薄い形式ではCBRを強制 or どちらでも可
    if f in ["m4a", "opus"]:
        window["-MODE-CBR-"].update(value=True)
        window["-MODE-VBR-"].update(value=False, disabled=True)
    elif f in ["wav", "flac"]:
        window["-MODE-CBR-"].update(value=True, disabled=True)
        window["-MODE-VBR-"].update(value=False, disabled=True)
    else:
        window["-MODE-CBR-"].update(disabled=False)
        window["-MODE-VBR-"].update(disabled=False)
    window["-NOTE-"].update(outfmt_note(values))

def worker_batch(values):
    infile = (values["-INFILE-"] or "").strip()
    indir = (values["-INDIR-"] or "").strip()
    # パターンはセミコロン区切りを許容
    raw_pat = (values["-PAT-"] or "").strip() or "*.mp4;*.m4v;*.mov;*.mkv;*.webm"
    patterns = [p.strip() for p in raw_pat.split(";") if p.strip()]
    recursive = values["-REC-"]
    outdir = (values["-OUTDIR-"] or "").strip() or None
    keep = values["-KEEP-"]
    overwrite = values["-OVW-"]

    outfmt = values["-OUTFMT-"]
    mode = "VBR" if values["-MODE-VBR-"] else "CBR"
    bitrate = values["-BITRATE-"]
    vbr_q = int(values["-VBRQ-"] or 2)
    ch_str = values["-CHAN-"]
    sr_str = values["-SR-"] or None
    start = (values["-START-"] or "").strip() or None
    dur = (values["-DUR-"] or "").strip() or None
    jobs = int(values["-JOBS-"] or 1)

    # gather targets for all patterns
    targets = []
    if infile:
        targets.extend(gather_files(infile, None, "*", False))
    if indir:
        for pat in patterns:
            targets.extend(gather_files(None, indir, pat, recursive))

    window.write_event_value("-BATCH-STARTED-", len(targets))
    if not targets:
        window.write_event_value("-LOG-", "No targets were found. Check input/pattern.")
        window.write_event_value("-PROG-", (0, 1))
        return

    tasks = []
    for src, root in targets:
        dst = build_output_path(src, root, outdir, keep, outfmt)
        tasks.append((src, root, dst))

    ok = ng = done = 0
    if jobs <= 1:
        for (src, _root, dst) in tasks:
            success, msg = convert_one(src, dst, outfmt, mode, bitrate, vbr_q, ch_str, sr_str, start, dur, overwrite)
            done += 1
            ok += int(success); ng += (0 if success else 1)
            window.write_event_value("-ONE-DONE-", (done, len(tasks), msg))
    else:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            future_map = {
                ex.submit(convert_one, src, dst, outfmt, mode, bitrate, vbr_q, ch_str, sr_str, start, dur, overwrite): (src, dst)
                for (src, _root, dst) in tasks
            }
            for fut in as_completed(future_map):
                try:
                    success, msg = fut.result()
                except Exception as e:
                    success, msg = False, f"NG: worker crashed -> {e}"
                done += 1
                ok += int(success); ng += (0 if success else 1)
                window.write_event_value("-ONE-DONE-", (done, len(tasks), msg))

    window.write_event_value("-BATCH-FINISHED-", (ok, ng, len(tasks)))

def worker_one(values):
    infile = (values["-INFILE-"] or "").strip()
    if not infile:
        window.write_event_value("-LOG-", "Convert One: please choose input file.")
        return
    outdir = (values["-OUTDIR-"] or "").strip() or None
    keep = values["-KEEP-"]

    outfmt = values["-OUTFMT-"]
    mode = "VBR" if values["-MODE-VBR-"] else "CBR"
    bitrate = values["-BITRATE-"]
    vbr_q = int(values["-VBRQ-"] or 2)
    ch_str = values["-CHAN-"]
    sr_str = values["-SR-"] or None
    start = (values["-START-"] or "").strip() or None
    dur = (values["-DUR-"] or "").strip() or None
    overwrite = values["-OVW-"]

    src = os.path.abspath(infile)
    root = os.path.dirname(src)
    dst = build_output_path(src, root, outdir, keep, outfmt)

    window.write_event_value("-BATCH-STARTED-", 1)
    success, msg = convert_one(src, dst, outfmt, mode, bitrate, vbr_q, ch_str, sr_str, start, dur, overwrite)
    window.write_event_value("-ONE-DONE-", (1, 1, msg))
    window.write_event_value("-BATCH-FINISHED-", (int(success), int(not success), 1))

# =========================
#  Event loop
# =========================
# 初期のNote/有効化
window["-NOTE-"].update("形式に応じてCBR/VBRやビットレート設定の意味が変わります。")
update_param_enable(window.read(timeout=0)[1] if hasattr(window, "read") else {})

while True:
    event, values = window.read(timeout=100)
    if event in (sg.WIN_CLOSED, "Exit"):
        break

    if event in ("-OUTFMT-", "-MODE-CBR-", "-MODE-VBR-", "-BITRATE-", "-VBRQ-"):
        update_param_enable(values)

    if event == "-BATCH-":
        if not has_ffmpeg():
            sg.popup_error("FFmpeg not found. Please set PATH.")
            continue
        window["-LOG-"].update("")  # clear log
        window["-PROG-"].update(current_count=0)
        window["-NOTE-"].update(outfmt_note(values))
        log_print("Start batch...")
        threading.Thread(target=worker_batch, args=(values,), daemon=True).start()

    if event == "-ONE-":
        if not has_ffmpeg():
            sg.popup_error("FFmpeg not found. Please set PATH.")
            continue
        window["-LOG-"].update("")
        window["-PROG-"].update(current_count=0)
        window["-NOTE-"].update(outfmt_note(values))
        log_print("Start single...")
        threading.Thread(target=worker_one, args=(values,), daemon=True).start()

    if event == "-BATCH-STARTED-":
        total = values[event]
        log_print(f"Targets: {total}")
        set_progress(0, max(total, 1))

    if event == "-ONE-DONE-":
        done, total, msg = values[event]
        log_print(msg)
        set_progress(done, total)

    if event == "-BATCH-FINISHED-":
        ok, ng, total = values[event]
        log_print(f"\nSummary: OK={ok}, NG={ng}, Total={total}")
        set_progress(total, total)

# 終了
window.close()
