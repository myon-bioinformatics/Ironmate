# -*- coding: utf-8 -*-
"""
Audio Any->Any Batch (FFmpeg GUI)
- FreeSimpleGUI 優先 / PySimpleGUI v4 フォールバック
- 入力: 単一ファイル / フォルダ（再帰） + ; 区切りパターン
- 出力: WAV / MP3 / FLAC / M4A(AAC) / OGG(Vorbis) / Opus / AAC
- 変換: SR / CH / トリム / loudnorm、一括・並列対応、階層維持
"""

import os, sys, glob, shutil, subprocess, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional

# ===== Flexible SG import (v4優先フォールバック) =====
tp = os.path.join(os.path.dirname(__file__), "third_party")
if os.path.isdir(tp) and tp not in sys.path:
    sys.path.insert(0, tp)
_GUI_BACKEND = None
try:
    import FreeSimpleGUI as sg  # 推奨
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
#  基本ユーティリティ
# =========================

def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def parse_time_to_seconds(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    s = s.strip()
    # 素直に数字（秒）
    try:
        return float(s)
    except ValueError:
        pass
    # "HH:MM:SS(.ms)" or "MM:SS(.ms)"
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
    # ffmpeg は "秒" 文字列でOK（小数可）
    return f"{sec}"

def change_ext(path: str, new_ext: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0] + f".{new_ext}"
    return base

def build_output_path(src: str, root: str, outdir: Optional[str], keep_structure: bool, out_ext: str) -> str:
    base = change_ext(src, out_ext)
    if outdir:
        if keep_structure and root:
            rel = os.path.relpath(os.path.dirname(src), start=root)
            dest_dir = os.path.join(outdir, rel)
        else:
            dest_dir = outdir
    else:
        # 未指定なら元ファイル横
        dest_dir = os.path.dirname(src)
    os.makedirs(dest_dir, exist_ok=True)
    return os.path.join(dest_dir, base)

def split_patterns(pattern_field: str) -> List[str]:
    """
    ';' 区切りで複数パターンを受け取り、空白をトリムして返す
    例: "*.mp3; *.m4a;*.wav"
    """
    if not pattern_field:
        return ["*.mp3"]
    pats = [p.strip() for p in pattern_field.split(";") if p.strip()]
    return pats or ["*.mp3"]

def gather_files(
    file_input: Optional[str],
    dir_input: Optional[str],
    pattern_field: str,
    recursive: bool
) -> List[Tuple[str, str]]:
    """
    変換対象 (src_path, root_dir) のリスト。
    root_dir は階層維持の基準。
    """
    tasks: List[Tuple[str, str]] = []

    # 個別ファイル
    if file_input:
        p = os.path.abspath(file_input)
        if os.path.isfile(p):
            tasks.append((p, os.path.dirname(p)))

    # ディレクトリ走査
    pats = split_patterns(pattern_field)
    if dir_input and os.path.isdir(dir_input):
        root = os.path.abspath(dir_input)
        for pat in pats:
            pat_glob = "**/" + pat if recursive else pat
            for p in glob.iglob(os.path.join(root, pat_glob), recursive=recursive):
                p = os.path.abspath(p)
                if os.path.isfile(p):
                    tasks.append((p, root))

    # 重複除去
    seen = set()
    uniq = []
    for src, root in tasks:
        if src not in seen:
            uniq.append((src, root))
            seen.add(src)
    return uniq

# =========================
#  出力フォーマット定義
# =========================
"""
各フォーマットごとに、必要な ffmpeg オプションを与える。
- WAV: コーデック（ビット深度）変更可
- MP3: libmp3lame / 固定CBRまたは平均ビットレート（ここでは -b:a を採用）
- AAC/M4A: aac / -b:a
- OGG(Vorbis): libvorbis / -q:a （0〜10 程度、既定 4〜6 が無難）
- Opus: libopus / -b:a
- FLAC: flac / -compression_level（0〜12、デフォ 5）
"""
WAV_CODECS = {
    "16-bit PCM (pcm_s16le)": "pcm_s16le",
    "24-bit PCM (pcm_s24le)": "pcm_s24le",
    "32-bit PCM (pcm_s32le)": "pcm_s32le",
    "32-bit Float (pcm_f32le)": "pcm_f32le",
}

OUT_FORMATS = [
    "wav",
    "mp3",
    "flac",
    "m4a(aac)",
    "ogg(vorbis)",
    "opus",
    "aac",
]

DEFAULT_BITRATES = ["96k", "128k", "160k", "192k", "256k", "320k"]
DEFAULT_VORBIS_Q = ["2", "3", "4", "5", "6", "7", "8"]  # 目安: 4〜6
DEFAULT_FLAC_LEVEL = ["0","2","4","5","6","8","10","12"]  # 5 が既定相当

# =========================
#  FFmpeg 変換
# =========================

def build_common_trim_and_rate(cmd: list, sr: Optional[int], channels: Optional[int],
                               start_sec: Optional[float], duration_sec: Optional[float],
                               normalize: bool) -> list:
    # 精度重視：-ss/-t は -i の後
    if start_sec is not None:
        cmd += ["-ss", sec_to_ffmpeg_str(start_sec)]
    if duration_sec is not None:
        cmd += ["-t", sec_to_ffmpeg_str(duration_sec)]
    if channels:
        cmd += ["-ac", str(channels)]
    if sr:
        cmd += ["-ar", str(sr)]
    # メタや映像は不要
    cmd += ["-vn", "-sn", "-dn"]
    # 正規化（ワンパス EBU R128）
    if normalize:
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    return cmd

def ffmpeg_convert_general(
    input_path: str,
    output_path: str,
    out_format: str,
    # 共通
    sr: Optional[int] = None,
    channels: Optional[int] = None,
    start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
    normalize: bool = False,
    # 各フォーマット固有
    wav_codec_name: str = "pcm_s16le",
    abr_bitrate: Optional[str] = None,     # mp3/aac/opus 用（-b:a）
    vorbis_q: Optional[str] = None,        # ogg(vorbis) 用（-q:a）
    flac_level: Optional[str] = None,      # flac 用（-compression_level）
) -> None:
    if not has_ffmpeg():
        raise RuntimeError("FFmpeg not found. Ensure it's in PATH.")

    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
           "-i", input_path]

    # 共通オプション
    cmd = build_common_trim_and_rate(cmd, sr, channels, start_sec, duration_sec, normalize)

    of = out_format.lower()
    if of == "wav":
        cmd += ["-c:a", wav_codec_name]
    elif of == "mp3":
        cmd += ["-c:a", "libmp3lame"]
        if abr_bitrate:
            cmd += ["-b:a", abr_bitrate]
    elif of == "m4a(aac)":
        # mp4/m4a の container は拡張子で自動判別、ここでは aac を想定
        cmd += ["-c:a", "aac"]
        if abr_bitrate:
            cmd += ["-b:a", abr_bitrate]
    elif of == "aac":
        cmd += ["-c:a", "aac"]
        if abr_bitrate:
            cmd += ["-b:a", abr_bitrate]
    elif of == "ogg(vorbis)":
        cmd += ["-c:a", "libvorbis"]
        if vorbis_q:
            cmd += ["-q:a", vorbis_q]
    elif of == "opus":
        cmd += ["-c:a", "libopus"]
        if abr_bitrate:
            cmd += ["-b:a", abr_bitrate]
    elif of == "flac":
        cmd += ["-c:a", "flac"]
        if flac_level:
            cmd += ["-compression_level", flac_level]
    else:
        raise ValueError(f"Unsupported out format: {out_format}")

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

def convert_one(
    src: str,
    dst: str,
    out_format: str,
    # 共通
    sr: Optional[int],
    ch: Optional[int],
    start: Optional[str],
    duration: Optional[str],
    normalize: bool,
    # 各フォーマット固有
    wav_codec_label: str,
    abr_bitrate: Optional[str],
    vorbis_q: Optional[str],
    flac_level: Optional[str],
    overwrite: bool,
) -> Tuple[bool, str]:
    try:
        if (not overwrite) and os.path.exists(dst):
            return True, f"SKIP (exists): {dst}"

        start_sec = parse_time_to_seconds(start) if start else None
        dur_sec = parse_time_to_seconds(duration) if duration else None
        wav_codec_name = WAV_CODECS.get(wav_codec_label, "pcm_s16le")

        ffmpeg_convert_general(
            input_path=src,
            output_path=dst,
            out_format=out_format,
            sr=sr,
            channels=ch,
            start_sec=start_sec,
            duration_sec=dur_sec,
            normalize=normalize,
            wav_codec_name=wav_codec_name,
            abr_bitrate=abr_bitrate,
            vorbis_q=vorbis_q,
            flac_level=flac_level
        )
        return True, f"OK: {dst}"
    except Exception as e:
        return False, f"NG: {os.path.basename(src)} -> {e}"

# =========================
#  GUI
# =========================

sg.theme("TealMono")

sr_choices = ["そのまま", "22050", "32000", "44100", "48000", "88200", "96000"]
ch_choices = ["そのまま", "ステレオ(2ch)", "モノラル(1ch)"]
wav_bitdepth_choices = list(WAV_CODECS.keys())

layout = [
    [sg.Text("Audio Any→Any 一括変換（FFmpeg専用）", font=("Segoe UI", 12, "bold"))],
    [sg.Frame("入力", [
        [sg.Text("単一ファイル"), sg.Input(key="-INFILE-", size=(50,1)),
         sg.FileBrowse(file_types=(("Audio","*.mp3;*.wav;*.m4a;*.aac;*.flac;*.ogg;*.opus;*.wma"),("All","*.*")))],
        [sg.Text("フォルダ   "), sg.Input(key="-INDIR-", size=(50,1)), sg.FolderBrowse()],
        [sg.Checkbox("サブフォルダも含める（再帰）", key="-REC-", default=True),
         sg.Text("パターン( ; 区切り)"),
         sg.Input("*.mp3;*.m4a;*.wav;*.flac;*.aac;*.ogg;*.opus", key="-PAT-", size=(40,1))]
    ])],
    [sg.Frame("出力", [
        [sg.Text("出力先フォルダ（未指定なら元ファイル横）"), sg.Input(key="-OUTDIR-", size=(46,1)), sg.FolderBrowse()],
        [sg.Checkbox("元のフォルダ階層を保持", key="-KEEP-", default=True),
         sg.Checkbox("既存ファイルを上書き", key="-OVW-")],
        [sg.Text("出力フォーマット"), sg.Combo(OUT_FORMATS, default_value="wav", key="-OUTFMT-", readonly=True, size=(14,1)),
         sg.Text("WAVビット深度"), sg.Combo(wav_bitdepth_choices, default_value=wav_bitdepth_choices[0], key="-WAVBD-", readonly=True, size=(26,1))]
    ])],
    [sg.Frame("変換パラメータ", [
        [sg.Text("サンプリングレート"), sg.Combo(sr_choices, default_value=sr_choices[0], key="-SR-", readonly=True, size=(10,1)),
         sg.Text("チャンネル"), sg.Combo(ch_choices, default_value=ch_choices[0], key="-CH-", readonly=True, size=(14,1)),
         sg.Text("loudnorm正規化"), sg.Checkbox("", key="-NORM-", default=False)],
        [sg.Text("Start"), sg.Input("", key="-START-", size=(10,1)),
         sg.Text("Duration"), sg.Input("", key="-DUR-", size=(10,1)),
         sg.Text("ビットレート(例: 192k) / 品質(q) / FLAC圧縮"),
         sg.Combo(DEFAULT_BITRATES, default_value="192k", key="-ABR-", size=(8,1)),
         sg.Combo(DEFAULT_VORBIS_Q, default_value="5", key="-VQ-", size=(4,1)),
         sg.Combo(DEFAULT_FLAC_LEVEL, default_value="5", key="-FLVL-", size=(4,1)),
        ],
        [sg.Text("並列ジョブ数"), sg.Spin([i for i in range(1, 17)], initial_value=1, key="-JOBS-", size=(5,1)),
         sg.Text("FFmpeg検出:"), sg.Text("未確認", key="-FFMPEG-STATUS-", text_color="orange")]
    ])],
    [sg.ProgressBar(max_value=100, orientation="h", size=(50,20), key="-PROG-")],
    [sg.Multiline(size=(100,12), key="-LOG-", autoscroll=True, disabled=True)],
    [sg.Button("一括変換", key="-BATCH-"), sg.Button("単体変換", key="-ONE-"), sg.Button("Exit")]
]

window = sg.Window("Audio Any→Any Batch (FFmpeg GUI)", layout, finalize=True)
window["-FFMPEG-STATUS-"].update("OK" if has_ffmpeg() else "NG",
                                 text_color=("green" if has_ffmpeg() else "red"))

def log_print(text: str):
    window["-LOG-"].update(text + "\n", append=True)

def set_progress(current: int, total: int):
    total = max(total, 1)
    pct = int(current * 100 / total)
    window["-PROG-"].update(current_count=pct)

def read_common_params(values):
    # SR
    sr_val = values["-SR-"]
    sr = None
    if sr_val and sr_val != "そのまま":
        try:
            sr = int(sr_val)
        except ValueError:
            sr = None
    # Channels
    ch_text = values["-CH-"]
    if ch_text == "ステレオ(2ch)":
        ch = 2
    elif ch_text == "モノラル(1ch)":
        ch = 1
    else:
        ch = None
    start = values["-START-"].strip() or None
    dur = values["-DUR-"].strip() or None
    norm = bool(values["-NORM-"])
    return sr, ch, start, dur, norm

def worker_batch(values):
    infile = (values["-INFILE-"] or "").strip()
    indir = (values["-INDIR-"] or "").strip()
    pattern = (values["-PAT-"] or "*.mp3").strip()
    recursive = values["-REC-"]
    outdir = (values["-OUTDIR-"] or "").strip() or None
    keep = values["-KEEP-"]
    overwrite = values["-OVW-"]

    outfmt = values["-OUTFMT-"]
    wavbd = values["-WAVBD-"] or list(WAV_CODECS.keys())[0]
    abr = (values["-ABR-"] or "").strip() or None
    vq = (values["-VQ-"] or "").strip() or None
    flvl = (values["-FLVL-"] or "").strip() or None

    sr, ch, start, dur, norm = read_common_params(values)
    jobs = int(values["-JOBS-"] or 1)

    targets = gather_files(infile, indir, pattern, recursive)
    window.write_event_value("-BATCH-STARTED-", len(targets))

    if not targets:
        window.write_event_value("-LOG-", "変換対象が見つかりません。入力ファイル/フォルダとパターンを確認してください。")
        window.write_event_value("-PROG-", (0, 1))
        return

    out_ext_map = {
        "wav": "wav",
        "mp3": "mp3",
        "flac": "flac",
        "m4a(aac)": "m4a",
        "ogg(vorbis)": "ogg",
        "opus": "opus",
        "aac": "aac",
    }
    out_ext = out_ext_map[outfmt]

    tasks = []
    for src, root in targets:
        dst = build_output_path(src, root, outdir, keep, out_ext)
        tasks.append((src, root, dst))

    ok = ng = done = 0
    if jobs <= 1:
        for (src, _root, dst) in tasks:
            success, msg = convert_one(
                src, dst, outfmt, sr, ch, start, dur, norm,
                wavbd, abr, vq, flvl, overwrite
            )
            done += 1
            ok += int(success); ng += int(not success)
            window.write_event_value("-ONE-DONE-", (done, len(tasks), msg))
    else:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            future_map = {
                ex.submit(
                    convert_one, src, dst, outfmt, sr, ch, start, dur, norm,
                    wavbd, abr, vq, flvl, overwrite
                ): (src, dst)
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
    infile = (values["-INFILE-"] or "").strip()
    if not infile:
        window.write_event_value("-LOG-", "単体変換：入力ファイルを指定してください。")
        return
    outdir = (values["-OUTDIR-"] or "").strip() or None
    keep = values["-KEEP-"]
    overwrite = values["-OVW-"]

    outfmt = values["-OUTFMT-"]
    wavbd = values["-WAVBD-"] or list(WAV_CODECS.keys())[0]
    abr = (values["-ABR-"] or "").strip() or None
    vq = (values["-VQ-"] or "").strip() or None
    flvl = (values["-FLVL-"] or "").strip() or None

    sr, ch, start, dur, norm = read_common_params(values)

    out_ext_map = {
        "wav": "wav",
        "mp3": "mp3",
        "flac": "flac",
        "m4a(aac)": "m4a",
        "ogg(vorbis)": "ogg",
        "opus": "opus",
        "aac": "aac",
    }
    out_ext = out_ext_map[outfmt]

    src = os.path.abspath(infile)
    root = os.path.dirname(src)
    dst = build_output_path(src, root, outdir, keep, out_ext)

    window.write_event_value("-BATCH-STARTED-", 1)
    success, msg = convert_one(
        src, dst, outfmt, sr, ch, start, dur, norm,
        wavbd, abr, vq, flvl, overwrite
    )
    window.write_event_value("-ONE-DONE-", (1, 1, msg))
    window.write_event_value("-BATCH-FINISHED-", (int(success), int(not success), 1))

# =========================
#  イベントループ
# =========================
while True:
    event, values = window.read(timeout=100)
    if event in (sg.WIN_CLOSED, "Exit"):
        break

    if event == "-BATCH-":
        if not has_ffmpeg():
            sg.popup_error("FFmpegが見つかりません。PATH設定を確認してください。")
            continue
        window["-LOG-"].update("")  # ログクリア
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
