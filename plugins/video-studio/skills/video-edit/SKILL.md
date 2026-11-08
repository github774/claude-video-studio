---
name: video-edit
description: >-
  Edit real footage with the local video-tools MCP (ffmpeg) - trim, assemble, jump-cut pauses out
  of talking-head video, burn captions, lay a ducked music bed, reframe to 9:16 / 1:1 / 4:5,
  normalize loudness and export per platform. Use when the user hands you video files and says
  "cut this", "edit this", "remove the pauses / dead air", "add captions/subtitles", "add music",
  "make it vertical", "make a short from this", "export for TikTok/YouTube", or "clean up the
  audio".
---

# Video Edit

Real footage, deterministic edits, verified output. Every operation is a `video-tools` MCP tool;
call them instead of hand-writing ffmpeg so paths, encodes and loudness are always right.

## Ground rules

- **Never touch the originals.** Write into `video-out/<slug>/` with numbered steps
  (`01_trim.mp4`, `02_jumpcut.mp4`, ...). Tools refuse to overwrite unless `overwrite=true`.
- **Look before you cut.** Start with `probe` and `contact_sheet` on every source. Use
  `detect` for scene cuts and silences. If a transcript is needed and the `watch` plugin is
  installed, use it; otherwise `extract_audio` to `.wav` and transcribe with whatever is
  available (whisper, a cloud API the user has), and say which.
- **One change per step**, then glance at the result (`contact_sheet`) before the next.
- **Picture first, sound second, delivery last**: cut → captions → music → loudness → export.

## Standard passes

| Goal | Tool call |
|---|---|
| Inspect | `probe(path, measure_loudness=true)`, `contact_sheet(input)`, `detect(input)` |
| Select a range | `trim(input, output, start, end)` (precise by default) |
| Talking-head tightening | `remove_silence(input, output, threshold_db=-35, min_silence=0.45, padding=0.12)`; raise `threshold_db` toward -30 for noisy rooms, raise `padding` if words get clipped |
| Assemble | `concat(inputs, output, crossfade=0)`; mixed sizes/fps/no-audio clips are conformed automatically |
| Captions | write an `.srt` from the transcript (max ~32 chars/line, 2 lines, 1-6 s each), then `burn_captions(style=clean|bold|boxed|yellow)`; use an `.ass` file for word-level styling |
| Music | `add_music(input, music, output, music_db=-16, duck=true)`; the music is looped, trimmed, faded and sidechain-ducked under speech |
| Vertical / square | `reframe(aspect="9:16", fit=blur|crop|pad)`; `crop` when the subject is centred, `blur` when it isn't |
| Speed ramp | `speed(factor)` on a trimmed segment, then `concat` |
| Thumbnail candidates | `frame(time)` at 3-5 strong moments from the contact sheet |
| Loudness only | `normalize_audio(target_lufs=-14)` |
| Delivery | `export(preset=youtube|shorts|tiktok|reels|x|linkedin|web-small|prores)`: conforms size, fps, GOP and loudness in one pass |

## Short-form from long-form

1. `detect` + transcript → pick 15-60 s with a hook in the first 2 s and one complete idea.
2. `trim` → `remove_silence` → `reframe 9:16` → `burn_captions style=bold` → `export shorts`.
3. If the user wants a stronger opener and the `viral-hook` skill is installed, offer it.

## Finish

Always end with the `video-qa` skill on the final file with the matching target.
