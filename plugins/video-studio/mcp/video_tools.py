#!/usr/bin/env python3
"""video-tools: a zero-dependency MCP server that gives Claude real video editing hands.

Speaks MCP (JSON-RPC 2.0, newline-delimited) over stdio. Every tool shells out to
ffmpeg/ffprobe with argument lists (never a shell), refuses to overwrite files unless
asked, and returns JSON describing what it did. Requires ffmpeg >= 6 on PATH.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable

SERVER_NAME = "video-tools"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL = "2025-06-18"

FFMPEG = os.environ.get("VIDEO_TOOLS_FFMPEG", "ffmpeg")
FFPROBE = os.environ.get("VIDEO_TOOLS_FFPROBE", "ffprobe")

ENCODE_V = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
ENCODE_A = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
MP4_FLAGS = ["-movflags", "+faststart"]

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}

EXPORT_PRESETS: dict[str, dict[str, Any]] = {
    "youtube": {"size": (1920, 1080), "fps": 30, "crf": 18, "lufs": -14},
    "youtube-4k": {"size": (3840, 2160), "fps": 30, "crf": 18, "lufs": -14},
    "shorts": {"size": (1080, 1920), "fps": 30, "crf": 19, "lufs": -14},
    "tiktok": {"size": (1080, 1920), "fps": 30, "crf": 19, "lufs": -14},
    "reels": {"size": (1080, 1920), "fps": 30, "crf": 19, "lufs": -14},
    "x": {"size": (1280, 720), "fps": 30, "crf": 21, "lufs": -14},
    "linkedin": {"size": (1080, 1080), "fps": 30, "crf": 20, "lufs": -14},
    "web-small": {"size": (1280, 720), "fps": 30, "crf": 26, "lufs": -16},
    "prores": {"size": None, "fps": None, "crf": None, "lufs": None},
}


class ToolError(Exception):
    pass


# ---------------------------------------------------------------- helpers


def run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise ToolError(f"{cmd[0]} not found on PATH; install ffmpeg first") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{cmd[0]} timed out after {timeout}s") from exc
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise ToolError(f"{cmd[0]} failed (exit {proc.returncode}):\n{tail}")
    return proc


def need_input(path: str) -> str:
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise ToolError(f"input not found: {path}")
    return path


def need_output(path: str, overwrite: bool) -> str:
    path = os.path.abspath(os.path.expanduser(path))
    if os.path.exists(path) and not overwrite:
        raise ToolError(f"output exists: {path} (pass overwrite=true to replace it)")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path


def ff(*args: str) -> list[str]:
    return [FFMPEG, "-hide_banner", "-nostdin", "-y", *args]


def probe_raw(path: str) -> dict[str, Any]:
    out = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(out.stdout)


def parse_rate(rate: str | None) -> float | None:
    if not rate or rate == "0/0":
        return None
    num, _, den = rate.partition("/")
    return float(num) / float(den or 1)


def info(path: str) -> dict[str, Any]:
    raw = probe_raw(path)
    v = next((s for s in raw["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in raw["streams"] if s["codec_type"] == "audio"), None)
    out: dict[str, Any] = {
        "path": path,
        "duration": float(raw["format"].get("duration", 0) or 0),
        "size_bytes": int(raw["format"].get("size", 0) or 0),
        "bitrate": int(raw["format"].get("bit_rate", 0) or 0),
        "has_video": v is not None,
        "has_audio": a is not None,
    }
    if v:
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        w, h = int(v["width"]), int(v["height"])
        if abs(rot) in (90, 270):
            w, h = h, w
        out["video"] = {
            "codec": v.get("codec_name"),
            "width": w,
            "height": h,
            "fps": round(parse_rate(v.get("avg_frame_rate")) or parse_rate(v.get("r_frame_rate")) or 0, 3),
            "pix_fmt": v.get("pix_fmt"),
            "rotation": rot,
        }
    if a:
        out["audio"] = {
            "codec": a.get("codec_name"),
            "sample_rate": int(a.get("sample_rate", 0) or 0),
            "channels": a.get("channels"),
        }
    return out


def loudness(path: str) -> dict[str, float]:
    proc = run(ff("-i", path, "-vn", "-af", "loudnorm=print_format=json", "-f", "null", "-"))
    blob = proc.stderr[proc.stderr.rfind("{") : proc.stderr.rfind("}") + 1]
    data = json.loads(blob)
    return {
        "integrated_lufs": float(data["input_i"]),
        "true_peak_db": float(data["input_tp"]),
        "lra": float(data["input_lra"]),
        "threshold": float(data["input_thresh"]),
    }


def intervals(stderr: str, start_key: str, end_key: str) -> list[list[float]]:
    starts = [float(x) for x in re.findall(rf"{start_key}:\s*(-?[\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(rf"{end_key}:\s*(-?[\d.]+)", stderr)]
    pairs = []
    for i, s in enumerate(starts):
        pairs.append([round(max(s, 0.0), 3), round(ends[i], 3) if i < len(ends) else None])
    return pairs


def silences(path: str, threshold_db: float, min_silence: float) -> list[list[float]]:
    proc = run(ff("-i", path, "-vn", "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}", "-f", "null", "-"))
    return intervals(proc.stderr, "silence_start", "silence_end")


def even(n: float) -> int:
    return int(round(n / 2)) * 2


def fit_filter(w: int, h: int, mode: str) -> str:
    """Filter chain that fits any frame into w x h by cropping, padding or blurred padding."""
    if mode == "crop":
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    if mode == "pad":
        return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    if mode == "blur":
        return (
            f"split=2[bg][fg];[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"boxblur=luma_radius=40:luma_power=2,eq=brightness=-0.06[bgb];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    raise ToolError(f"unknown fit mode {mode!r}; use crop, pad or blur")


def atempo_chain(factor: float) -> str:
    parts = []
    while factor > 2.0:
        parts.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append(f"atempo={factor:.6f}")
    return ",".join(parts)


def escape_filter_path(path: str) -> str:
    return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


def result(**kw: Any) -> dict[str, Any]:
    out = kw.get("output")
    if out and os.path.isfile(out) and out.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".m4a", ".wav", ".mp3")):
        try:
            meta = info(out)
            kw["output_info"] = {k: meta[k] for k in ("duration", "size_bytes") if k in meta}
            if "video" in meta:
                kw["output_info"]["resolution"] = f"{meta['video']['width']}x{meta['video']['height']}"
        except ToolError:
            pass
    return kw


# ---------------------------------------------------------------- tools


def t_probe(path: str, measure_loudness: bool = False) -> dict[str, Any]:
    path = need_input(path)
    out = info(path)
    if measure_loudness and out["has_audio"]:
        out["loudness"] = loudness(path)
    return out


def t_trim(input: str, output: str, start: float = 0.0, end: float | None = None,
           precise: bool = True, overwrite: bool = False) -> dict[str, Any]:
    src = need_input(input)
    dst = need_output(output, overwrite)
    args = ["-ss", f"{start:.3f}"]
    if end is not None:
        if end <= start:
            raise ToolError("end must be greater than start")
        args += ["-t", f"{end - start:.3f}"]
    if precise:
        cmd = ff(*args, "-i", src, *ENCODE_V, *ENCODE_A, *MP4_FLAGS, dst)
    else:
        cmd = ff(*args, "-i", src, "-c", "copy", "-avoid_negative_ts", "make_zero", dst)
    run(cmd)
    return result(output=dst, mode="re-encoded (frame accurate)" if precise else "stream copy (keyframe aligned)")


def t_concat(inputs: list[str], output: str, crossfade: float = 0.0, width: int | None = None,
             height: int | None = None, fps: float = 30, fit: str = "blur", overwrite: bool = False) -> dict[str, Any]:
    if len(inputs) < 2:
        raise ToolError("concat needs at least two inputs")
    srcs = [need_input(p) for p in inputs]
    dst = need_output(output, overwrite)
    metas = [info(p) for p in srcs]
    if not all(m["has_video"] for m in metas):
        raise ToolError("every concat input needs a video stream")
    w = width or metas[0]["video"]["width"]
    h = height or metas[0]["video"]["height"]
    w, h = even(w), even(h)
    args: list[str] = []
    for p in srcs:
        args += ["-i", p]
    chains = []
    for i, m in enumerate(metas):
        fit_c = fit_filter(w, h, fit).replace("[bg]", f"[bg{i}]").replace("[fg]", f"[fg{i}]") \
            .replace("[bgb]", f"[bgb{i}]").replace("[fgs]", f"[fgs{i}]")
        chains.append(f"[{i}:v]fps={fps},{fit_c},format=yuv420p,settb=AVTB[v{i}]")
        if m["has_audio"]:
            chains.append(f"[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,asettb=AVTB[a{i}]")
        else:
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={m['duration']:.3f},asettb=AVTB[a{i}]")
    n = len(srcs)
    if crossfade <= 0:
        chains.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vo][ao]")
    else:
        shortest = min(m["duration"] for m in metas)
        if crossfade >= shortest / 2:
            raise ToolError(f"crossfade {crossfade}s is too long for a {shortest:.2f}s clip")
        prev_v, prev_a, offset = "v0", "a0", 0.0
        for i in range(1, n):
            offset += metas[i - 1]["duration"] - crossfade
            ov, oa = ("vo", "ao") if i == n - 1 else (f"vx{i}", f"ax{i}")
            chains.append(f"[{prev_v}][v{i}]xfade=transition=fade:duration={crossfade}:offset={offset:.3f}[{ov}]")
            chains.append(f"[{prev_a}][a{i}]acrossfade=d={crossfade}[{oa}]")
            prev_v, prev_a = ov, oa
    run(ff(*args, "-filter_complex", ";".join(chains), "-map", "[vo]", "-map", "[ao]",
           *ENCODE_V, *ENCODE_A, *MP4_FLAGS, dst))
    return result(output=dst, clips=n, resolution=f"{w}x{h}", crossfade=crossfade)


def t_reframe(input: str, output: str, aspect: str = "9:16", fit: str = "blur",
              overwrite: bool = False) -> dict[str, Any]:
    if aspect not in ASPECTS:
        raise ToolError(f"aspect must be one of {sorted(ASPECTS)}")
    src = need_input(input)
    dst = need_output(output, overwrite)
    w, h = ASPECTS[aspect]
    has_audio = info(src)["has_audio"]
    cmd = ff("-i", src, "-filter_complex", f"[0:v]{fit_filter(w, h, fit)}[vo]", "-map", "[vo]")
    if has_audio:
        cmd += ["-map", "0:a:0", *ENCODE_A]
    run(cmd + [*ENCODE_V, *MP4_FLAGS, dst])
    return result(output=dst, aspect=aspect, fit=fit)


def t_remove_silence(input: str, output: str, threshold_db: float = -35.0, min_silence: float = 0.45,
                     padding: float = 0.12, overwrite: bool = False) -> dict[str, Any]:
    src = need_input(input)
    dst = need_output(output, overwrite)
    meta = info(src)
    if not meta["has_audio"]:
        raise ToolError("input has no audio to detect silence in")
    dur = meta["duration"]
    gaps = silences(src, threshold_db, min_silence)
    keep, cursor = [], 0.0
    for s, e in gaps:
        e = dur if e is None else e
        cut_from, cut_to = s + padding, e - padding
        if cut_to - cut_from <= 0.05:
            continue
        if cut_from > cursor:
            keep.append((cursor, cut_from))
        cursor = cut_to
    if cursor < dur:
        keep.append((cursor, dur))
    if not keep:
        raise ToolError("the whole clip is below the silence threshold; raise threshold_db")
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep)
    vf = f"select='{expr}',setpts=N/FRAME_RATE/TB"
    af = f"aselect='{expr}',asetpts=N/SR/TB"
    cmd = ff("-i", src)
    if meta["has_video"]:
        cmd += ["-vf", vf, *ENCODE_V]
    run(cmd + ["-af", af, *ENCODE_A, *MP4_FLAGS, dst])
    kept = sum(b - a for a, b in keep)
    return result(output=dst, segments_kept=len(keep), seconds_removed=round(dur - kept, 2),
                  original_duration=round(dur, 2))


def t_normalize_audio(input: str, output: str, target_lufs: float = -14.0, true_peak: float = -1.0,
                      lra: float = 11.0, overwrite: bool = False) -> dict[str, Any]:
    src = need_input(input)
    dst = need_output(output, overwrite)
    meta = info(src)
    if not meta["has_audio"]:
        raise ToolError("input has no audio")
    before = loudness(src)
    ln = (f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}:measured_I={before['integrated_lufs']}:"
          f"measured_TP={before['true_peak_db']}:measured_LRA={before['lra']}:"
          f"measured_thresh={before['threshold']}:linear=true")
    cmd = ff("-i", src, "-af", ln, *ENCODE_A)
    cmd += ["-c:v", "copy"] if meta["has_video"] else ["-vn"]
    run(cmd + [*MP4_FLAGS, dst] if dst.lower().endswith((".mp4", ".mov", ".m4a")) else cmd + [dst])
    return result(output=dst, before=before, after=loudness(dst), target_lufs=target_lufs)


def t_add_music(input: str, music: str, output: str, music_db: float = -16.0, duck: bool = True,
                fade_out: float = 1.5, overwrite: bool = False) -> dict[str, Any]:
    src, mus = need_input(input), need_input(music)
    dst = need_output(output, overwrite)
    meta = info(src)
    dur = meta["duration"]
    fo_start = max(dur - fade_out, 0)
    music_chain = (f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={music_db}dB,"
                   f"atrim=duration={dur:.3f},afade=t=out:st={fo_start:.3f}:d={fade_out}")
    if not meta["has_audio"]:
        graph = f"{music_chain}[ao]"
    elif duck:
        graph = (f"{music_chain}[m];[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo1][vo2];"
                 f"[m][vo1]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=350[md];"
                 f"[vo2][md]amix=inputs=2:duration=first:normalize=0[ao]")
    else:
        graph = (f"{music_chain}[m];[0:a]aformat=sample_rates=48000:channel_layouts=stereo[v];"
                 f"[v][m]amix=inputs=2:duration=first:normalize=0[ao]")
    run(ff("-i", src, "-stream_loop", "-1", "-i", mus, "-filter_complex", graph,
           "-map", "0:v:0", "-map", "[ao]", "-c:v", "copy", *ENCODE_A, "-t", f"{dur:.3f}", *MP4_FLAGS, dst))
    return result(output=dst, ducking=duck and meta["has_audio"], music_db=music_db)


CAPTION_STYLES = {
    "clean": "FontName=Helvetica,Fontsize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=1,Outline=1.2,Shadow=0,MarginV=40",
    "bold": "FontName=Arial Black,Fontsize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,MarginV=60",
    "boxed": "FontName=Helvetica,Fontsize=15,PrimaryColour=&H00FFFFFF,BackColour=&H99000000,BorderStyle=3,Outline=6,Shadow=0,MarginV=40",
    "yellow": "FontName=Arial Black,Fontsize=20,PrimaryColour=&H0000E5FF,OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=0,MarginV=60",
}


def t_burn_captions(input: str, subtitles: str, output: str, style: str = "clean",
                    overwrite: bool = False) -> dict[str, Any]:
    src, subs = need_input(input), need_input(subtitles)
    dst = need_output(output, overwrite)
    if style not in CAPTION_STYLES:
        raise ToolError(f"style must be one of {sorted(CAPTION_STYLES)}")
    vf = f"subtitles='{escape_filter_path(subs)}'"
    if not subs.lower().endswith(".ass"):
        vf += f":force_style='{CAPTION_STYLES[style]}'"
    cmd = ff("-i", src, "-vf", vf, *ENCODE_V)
    cmd += ["-c:a", "copy"] if info(src)["has_audio"] else []
    run(cmd + [*MP4_FLAGS, dst])
    return result(output=dst, style=style)


def t_speed(input: str, output: str, factor: float, overwrite: bool = False) -> dict[str, Any]:
    if not 0.1 <= factor <= 8:
        raise ToolError("factor must be between 0.1 and 8")
    src = need_input(input)
    dst = need_output(output, overwrite)
    meta = info(src)
    cmd = ff("-i", src, "-vf", f"setpts=PTS/{factor}", *ENCODE_V)
    cmd += ["-af", atempo_chain(factor), *ENCODE_A] if meta["has_audio"] else []
    run(cmd + [*MP4_FLAGS, dst])
    return result(output=dst, factor=factor)


def t_extract_audio(input: str, output: str, overwrite: bool = False) -> dict[str, Any]:
    src = need_input(input)
    dst = need_output(output, overwrite)
    codec = ["-c:a", "pcm_s16le"] if dst.lower().endswith(".wav") else (
        ["-c:a", "libmp3lame", "-q:a", "2"] if dst.lower().endswith(".mp3") else ENCODE_A)
    run(ff("-i", src, "-vn", *codec, dst))
    return result(output=dst)


def t_frame(input: str, output: str, time: float = 0.0, overwrite: bool = False) -> dict[str, Any]:
    src = need_input(input)
    dst = need_output(output, overwrite)
    run(ff("-ss", f"{time:.3f}", "-i", src, "-frames:v", "1", "-q:v", "2", dst))
    return result(output=dst, time=time)


def t_contact_sheet(input: str, output: str | None = None, frames: int = 12, columns: int = 4,
                    tile_width: int = 400, overwrite: bool = True) -> dict[str, Any]:
    src = need_input(input)
    meta = info(src)
    if not meta["has_video"]:
        raise ToolError("input has no video")
    frames = max(1, min(frames, 48))
    columns = max(1, min(columns, frames))
    rows = -(-frames // columns)
    dst = need_output(output or tempfile.mktemp(prefix="sheet_", suffix=".png"), overwrite)
    dur = max(meta["duration"], 0.04)
    times = [dur * (i + 0.5) / frames for i in range(frames)]
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(times):
            run(ff("-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
                   "-vf", f"scale={tile_width}:-2,drawtext=text='{t:.1f}s':x=8:y=8:fontsize=20:"
                          f"fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=4",
                   os.path.join(tmp, f"f{i:03d}.png")))
        run(ff("-framerate", "1", "-i", os.path.join(tmp, "f%03d.png"),
               "-vf", f"tile={columns}x{rows}:padding=4:margin=4:color=0x111111", "-frames:v", "1", dst))
    return result(output=dst, timestamps=[round(t, 2) for t in times], _image=dst)


def t_detect(input: str, scene_threshold: float = 0.3, silence_db: float = -35.0,
             min_silence: float = 0.5) -> dict[str, Any]:
    src = need_input(input)
    meta = info(src)
    out: dict[str, Any] = {"duration": meta["duration"]}
    if meta["has_video"]:
        proc = run(ff("-i", src, "-an", "-vf",
                      f"select='gt(scene,{scene_threshold})',showinfo,blackdetect=d=0.2:pix_th=0.10,freezedetect=n=0.003:d=0.6",
                      "-f", "null", "-"))
        cuts = [round(float(x), 3) for x in re.findall(r"Parsed_showinfo.*?pts_time:([\d.]+)", proc.stderr)]
        out["scene_cuts"] = cuts
        out["black"] = intervals(proc.stderr, "black_start", "black_end")
        out["frozen"] = intervals(proc.stderr, "freeze_start", "freeze_end")
        if cuts:
            bounds = [0.0, *cuts, meta["duration"]]
            shots = [b - a for a, b in zip(bounds, bounds[1:]) if b > a]
            out["average_shot_seconds"] = round(sum(shots) / len(shots), 2)
    if meta["has_audio"]:
        out["silences"] = silences(src, silence_db, min_silence)
    return out


QA_TARGETS = {
    "youtube": {"aspect": 16 / 9, "lufs": (-16, -12), "max_tp": -0.5, "max_s": None},
    "shorts": {"aspect": 9 / 16, "lufs": (-16, -12), "max_tp": -0.5, "max_s": 180},
    "tiktok": {"aspect": 9 / 16, "lufs": (-16, -12), "max_tp": -0.5, "max_s": 600},
    "reels": {"aspect": 9 / 16, "lufs": (-16, -12), "max_tp": -0.5, "max_s": 180},
    "x": {"aspect": None, "lufs": (-17, -12), "max_tp": -0.5, "max_s": 140},
    "any": {"aspect": None, "lufs": (-18, -10), "max_tp": -0.3, "max_s": None},
}


def t_qa_report(input: str, target: str = "any", expected_duration: float | None = None) -> dict[str, Any]:
    if target not in QA_TARGETS:
        raise ToolError(f"target must be one of {sorted(QA_TARGETS)}")
    spec = QA_TARGETS[target]
    src = need_input(input)
    meta = info(src)
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str, severity: str = "fail") -> None:
        checks.append({"check": name, "status": "pass" if ok else severity, "detail": detail})

    check("has video", meta["has_video"], "video stream present" if meta["has_video"] else "no video stream")
    check("has audio", meta["has_audio"], "audio stream present" if meta["has_audio"] else "silent file", "warn")
    if meta["has_video"]:
        v = meta["video"]
        check("even dimensions", v["width"] % 2 == 0 and v["height"] % 2 == 0, f"{v['width']}x{v['height']}")
        check("pixel format", v["pix_fmt"] in ("yuv420p", "yuvj420p"), f"{v['pix_fmt']} (yuv420p plays everywhere)", "warn")
        check("frame rate", 23 <= v["fps"] <= 61, f"{v['fps']} fps", "warn")
        if spec["aspect"]:
            ratio = v["width"] / v["height"]
            check("aspect ratio", abs(ratio - spec["aspect"]) < 0.02, f"{ratio:.3f} vs target {spec['aspect']:.3f}")
    if spec["max_s"]:
        check("platform length", meta["duration"] <= spec["max_s"], f"{meta['duration']:.1f}s (max {spec['max_s']}s)")
    if expected_duration:
        check("duration", abs(meta["duration"] - expected_duration) <= 0.5,
              f"{meta['duration']:.2f}s vs expected {expected_duration:.2f}s")
    det = t_detect(src)
    head_tail = [b for b in det.get("black", []) if b[0] < 0.1 or (b[1] or meta["duration"]) > meta["duration"] - 0.1]
    mid_black = [b for b in det.get("black", []) if b not in head_tail]
    check("black frames", not mid_black, f"mid-video black at {mid_black}" if mid_black else "none mid-video", "warn")
    check("frozen frames", not det.get("frozen"), f"frozen at {det.get('frozen')}" if det.get("frozen") else "none")
    if "average_shot_seconds" in det:
        check("pacing", det["average_shot_seconds"] <= 6.0,
              f"average shot {det['average_shot_seconds']}s (over 6s reads slow for social)", "warn")
    if meta["has_audio"]:
        lo, hi = spec["lufs"]
        ld = loudness(src)
        check("loudness", lo <= ld["integrated_lufs"] <= hi, f"{ld['integrated_lufs']:.1f} LUFS (target {lo}..{hi})")
        check("true peak", ld["true_peak_db"] <= spec["max_tp"], f"{ld['true_peak_db']:.1f} dBTP (max {spec['max_tp']})")
        long_sil = [s for s in det.get("silences", []) if s[1] and s[1] - s[0] > 2.0]
        check("dead air", not long_sil, f"silences over 2s at {long_sil}" if long_sil else "none over 2s", "warn")
    verdict = "fail" if any(c["status"] == "fail" for c in checks) else (
        "warn" if any(c["status"] == "warn" for c in checks) else "pass")
    return {"verdict": verdict, "target": target, "checks": checks, "file": meta}


def t_export(input: str, output: str, preset: str = "youtube", fit: str = "blur",
             overwrite: bool = False) -> dict[str, Any]:
    if preset not in EXPORT_PRESETS:
        raise ToolError(f"preset must be one of {sorted(EXPORT_PRESETS)}")
    p = EXPORT_PRESETS[preset]
    src = need_input(input)
    dst = need_output(output, overwrite)
    meta = info(src)
    if preset == "prores":
        cmd = ff("-i", src, "-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le")
        cmd += ["-c:a", "pcm_s16le"] if meta["has_audio"] else []
        run(cmd + [dst])
        return result(output=dst, preset=preset)
    w, h = p["size"]
    cmd = ff("-i", src, "-filter_complex", f"[0:v]fps={p['fps']},{fit_filter(w, h, fit)}[vo]", "-map", "[vo]",
             "-c:v", "libx264", "-preset", "slow", "-crf", str(p["crf"]), "-pix_fmt", "yuv420p",
             "-profile:v", "high", "-g", str(p["fps"] * 2))
    if meta["has_audio"]:
        before = loudness(src)
        cmd += ["-map", "0:a:0", "-af",
                f"loudnorm=I={p['lufs']}:TP=-1:LRA=11:measured_I={before['integrated_lufs']}:"
                f"measured_TP={before['true_peak_db']}:measured_LRA={before['lra']}:"
                f"measured_thresh={before['threshold']}:linear=true", *ENCODE_A]
    run(cmd + [*MP4_FLAGS, dst])
    return result(output=dst, preset=preset, resolution=f"{w}x{h}", loudness_target=p["lufs"])


# ---------------------------------------------------------------- MCP plumbing

S = {"type": "string"}
N = {"type": "number"}
B = {"type": "boolean"}
I = {"type": "integer"}
OVERWRITE = {"type": "boolean", "description": "Replace the output if it exists (default false)."}


def schema(required: list[str], **props: Any) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


TOOLS: dict[str, tuple[Callable[..., dict[str, Any]], str, dict[str, Any]]] = {
    "probe": (t_probe, "Read a media file: duration, resolution, fps, codecs, audio; optionally EBU R128 loudness.",
              schema(["path"], path=S, measure_loudness=B)),
    "trim": (t_trim, "Cut a clip to [start, end] seconds. precise=true re-encodes for frame accuracy; false stream-copies.",
             schema(["input", "output"], input=S, output=S, start=N, end=N, precise=B, overwrite=OVERWRITE)),
    "concat": (t_concat, "Join clips in order into one video, conforming size/fps/audio; optional crossfade seconds.",
               schema(["inputs", "output"], inputs={"type": "array", "items": S}, output=S, crossfade=N,
                      width=I, height=I, fps=N, fit={"enum": ["crop", "pad", "blur"]}, overwrite=OVERWRITE)),
    "reframe": (t_reframe, "Convert to 9:16, 16:9, 1:1 or 4:5 by crop, pad or blurred-background pad.",
                schema(["input", "output"], input=S, output=S, aspect={"enum": list(ASPECTS)},
                       fit={"enum": ["crop", "pad", "blur"]}, overwrite=OVERWRITE)),
    "remove_silence": (t_remove_silence, "Jump-cut: remove pauses below threshold_db longer than min_silence, keeping padding.",
                       schema(["input", "output"], input=S, output=S, threshold_db=N, min_silence=N, padding=N,
                              overwrite=OVERWRITE)),
    "normalize_audio": (t_normalize_audio, "Two-pass EBU R128 loudness normalization (default -14 LUFS, -1 dBTP). Video is copied.",
                        schema(["input", "output"], input=S, output=S, target_lufs=N, true_peak=N, lra=N,
                               overwrite=OVERWRITE)),
    "add_music": (t_add_music, "Lay a music bed under a video (looped, faded out), ducking it under speech by default.",
                  schema(["input", "music", "output"], input=S, music=S, output=S, music_db=N, duck=B, fade_out=N,
                         overwrite=OVERWRITE)),
    "burn_captions": (t_burn_captions, "Burn an .srt/.vtt/.ass subtitle file into the picture with a style preset.",
                      schema(["input", "subtitles", "output"], input=S, subtitles=S, output=S,
                             style={"enum": list(CAPTION_STYLES)}, overwrite=OVERWRITE)),
    "speed": (t_speed, "Change playback speed (0.1-8x) with pitch-preserving audio.",
              schema(["input", "output", "factor"], input=S, output=S, factor=N, overwrite=OVERWRITE)),
    "extract_audio": (t_extract_audio, "Write the audio track to .wav, .mp3 or .m4a (for transcription or mixing).",
                      schema(["input", "output"], input=S, output=S, overwrite=OVERWRITE)),
    "frame": (t_frame, "Save one still frame at a time in seconds (thumbnail candidates, review).",
              schema(["input", "output"], input=S, output=S, time=N, overwrite=OVERWRITE)),
    "contact_sheet": (t_contact_sheet, "Grid of evenly spaced, timestamped frames returned as an image so Claude can SEE the cut.",
                      schema(["input"], input=S, output=S, frames=I, columns=I, tile_width=I, overwrite=OVERWRITE)),
    "detect": (t_detect, "Find scene cuts, black frames, frozen frames, silences and average shot length.",
               schema(["input"], input=S, scene_threshold=N, silence_db=N, min_silence=N)),
    "qa_report": (t_qa_report, "Pass/warn/fail delivery check: dimensions, pix_fmt, fps, aspect, length, loudness, true peak, black/frozen frames, dead air, pacing.",
                  schema(["input"], input=S, target={"enum": list(QA_TARGETS)}, expected_duration=N)),
    "export": (t_export, "Platform export: youtube, youtube-4k, shorts, tiktok, reels, x, linkedin, web-small, prores. Conforms size/fps and loudness.",
               schema(["input", "output"], input=S, output=S, preset={"enum": list(EXPORT_PRESETS)},
                      fit={"enum": ["crop", "pad", "blur"]}, overwrite=OVERWRITE)),
}


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
    fn = TOOLS[name][0]
    try:
        out = fn(**args)
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    except TypeError as exc:
        return {"content": [{"type": "text", "text": f"bad arguments: {exc}"}], "isError": True}
    image = out.pop("_image", None)
    content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(out, indent=2)}]
    if image and os.path.getsize(image) < 4_500_000:
        with open(image, "rb") as fh:
            content.append({"type": "image", "mimeType": "image/png", "data": base64.b64encode(fh.read()).decode()})
    return {"content": content, "isError": False}


def handle(msg: dict[str, Any]) -> dict[str, Any] | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None  # notification
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion", DEFAULT_PROTOCOL)
        res: Any = {"protocolVersion": version, "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": "Local ffmpeg editing tools. Never overwrite inputs; write new files and run qa_report "
                                    "plus contact_sheet on every deliverable before calling it done."}
    elif method == "ping":
        res = {}
    elif method == "tools/list":
        res = {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in TOOLS.items()]}
    elif method == "tools/call":
        p = msg.get("params") or {}
        res = call_tool(p.get("name", ""), p.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def main() -> None:
    if not shutil.which(FFMPEG):
        print(f"[{SERVER_NAME}] warning: {FFMPEG} not on PATH; tools will fail until ffmpeg is installed", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply: dict[str, Any] | None = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            try:
                reply = handle(msg)
            except Exception as exc:  # keep the server alive no matter what one call does
                reply = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": repr(exc)}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
