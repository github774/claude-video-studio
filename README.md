# Claude Video Studio

**One front door for video work in Claude Code.** Ask for any video (a launch reel, a product
promo, a collage B-roll explainer, a cut-down of your footage, vertical shorts with captions)
and Claude routes it to the specialist that does that job best, edits real footage with a
local ffmpeg MCP server, and checks every deliverable the same way before calling it done.

It **combines without diluting.** The specialist skills are not copied, merged or rewritten:
they install from their own upstream repos and run exactly as their authors designed them,
including their approval gates and quality checks. This repo adds what none of them has alone:

| Piece | What it adds |
|---|---|
| `video-director` skill | Gathers the brief once, routes to the best installed specialist, chains several for multi-part jobs, says what's missing instead of silently downgrading |
| `video-tools` MCP server | 15 real editing tools over ffmpeg: `probe`, `trim`, `concat` (mixed sizes, crossfades), `reframe` (9:16/1:1/4:5, blur-pad), `remove_silence` (jump cuts), `normalize_audio` (two-pass EBU R128), `add_music` (looped + sidechain ducking), `burn_captions`, `speed`, `extract_audio`, `frame`, `contact_sheet` (Claude *sees* the cut), `detect` (scenes, black, frozen, silence), `qa_report`, `export` (YouTube, Shorts, TikTok, Reels, X, LinkedIn, ProRes) |
| `video-edit` skill | The footage-editing workflow: picture → captions → music → loudness → export, never touching originals |
| `video-qa` skill | One last gate for every video from every specialist: delivery numbers plus a visual contact-sheet review, fix, re-check |

The MCP server is a single Python file with **no dependencies** beyond Python 3.9+ and ffmpeg.

## Install

```bash
# in Claude Code
/plugin marketplace add github774/claude-video-studio
/plugin install video-studio@claude-video-studio
```

Then add the specialists you want (each from its own repo, under its own license):

```bash
/plugin install brag@claude-video-studio         # launch videos from a repo or URL (MIT)
/plugin install hyperframes@claude-video-studio  # HTML -> video by HeyGen (Apache-2.0)
/plugin install watch@claude-video-studio        # let Claude watch videos (MIT)
/plugin install lemo-opuscar@claude-video-studio # 66 film styles made in code, by Lemomo (MIT / CC BY 4.0)
```

Skill-only upstreams:

```bash
git clone https://github.com/github774/claude-video-studio && cd claude-video-studio
scripts/install-upstream.sh onetake    # PolyForm Noncommercial: noncommercial use only
scripts/install-upstream.sh remotion   # Remotion's official agent skills
```

Requires `ffmpeg` and `ffprobe` on PATH (`brew install ffmpeg`, `apt install ffmpeg`, or
`winget install ffmpeg`).

## Use

Just ask. The director loads on any video request:

- "Make a 20-second launch video for this repo" → `brag-slim`
- "Make a product demo of these three screens, Apple-style, with voice-over" → `onetake`
- "Turn 'attention is the new currency' into a collage B-roll shot" → `collage-broll-explainers`
- "Make a 60-second explainer about tides in ukiyo-e style" → `lemo-opuscar`
- "Cut the pauses out of interview.mov, add captions and make a 9:16 short" → `video-edit`
- "Is this ready for YouTube?" → `video-qa`

Name a specialist directly (`/onetake`, `/brag-slim`) and the director stays out of the way.

## Credits and licenses

This repo's own code and skills are MIT. The specialists belong to their authors and are
installed from their own repositories, never redistributed here. See
[THIRD_PARTY.md](THIRD_PARTY.md).

## Develop

```bash
python3 -m unittest discover -s tests -v   # drives the MCP server end to end on generated clips
```
