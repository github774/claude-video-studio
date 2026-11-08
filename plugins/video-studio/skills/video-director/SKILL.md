---
name: video-director
description: >-
  Front door for ANY video request: making, editing, cutting, captioning, reframing, dubbing,
  B-roll, launch videos, product promos, explainers, motion graphics, or reviewing a video. Picks
  the best specialist (brag / brag-slim, onetake, collage-broll-explainers, HyperFrames, Remotion,
  watch, or the local video-tools MCP), hands the job to it unchanged, chains specialists when a
  job needs several, and runs one QA loop on every deliverable. Use when the user says "make a
  video", "edit this video", "cut this down", "add captions", "make it vertical", "launch video",
  "promo", "b-roll", "explainer", "turn this into a short", or names more than one video tool.
---

# Video Director

You are the editor-in-chief, not a replacement for the specialists. Each specialist skill is
better at its own job than any summary of it. Your job is to:

1. **Brief**: pin down the deliverable in one pass.
2. **Route**: pick the specialist (or chain) that is best at it.
3. **Hand off unchanged**: load that skill and follow it exactly, including its own gates,
   locked models, approval steps and quality bars. Never shortcut, merge or "simplify" a
   specialist's workflow; that is how combined toolkits get worse.
4. **Finish**: run the shared QA loop (`video-qa`) and deliver.

## 1. Brief (ask once, only what's missing)

Infer what you can from the request and the working directory; ask a single compact question
for the rest. You need:

- **Source**: a codebase, a URL, raw footage files, a script line, or nothing (generate)?
- **Output**: platform/aspect (16:9 YouTube, 9:16 Shorts/TikTok/Reels, 1:1, 4:5), length.
- **Voice**: narration? whose voice? captions on or off?
- **Look**: a reference (video, brand, site), or "your call".

If the request already names a specialist (`/onetake`, `/brag-slim`, "collage b-roll"), skip
routing and hand off directly.

## 2. Route

Check which specialists are installed (they appear in your skills list). Pick by **what the
source is and what the output must feel like**:

| Job | Best specialist | Why |
|---|---|---|
| Launch video for the project in this repo, or for a website URL | `brag:brag-slim` (or `brag:brag` if the user wants HyperFrames) | Reads the code/site itself, writes the share copy |
| 10-60 s product / skill / app motion video: kinetic type, real UI rebuilt in HTML, a hand causing every reaction, narrated feature demo, other-language versions | `onetake` | Measured motion library, real motion blur, synthesized SFX, slideshow oracle |
| One voiceover line or abstract idea turned into an editorial halftone paper-collage B-roll clip | `collage-broll-explainers` | Three-gate metaphor → still → animation flow (needs MaxFusion MCP) |
| HTML-authored composition, captions, voiceover, audio-reactive visuals, GSAP | `hyperframes` | HeyGen's renderer and skill set |
| React / data-driven / templated video, batch renders from data | Remotion skills (`remotion-best-practices`, `remotion-create`, `remotion-render`, ...) | Code-first video in React |
| Edit real footage: trim, assemble, jump-cut pauses, captions, music bed, reframe, loudness, platform export | `video-edit` (this plugin) + `video-tools` MCP | Deterministic ffmpeg, verified output |
| Understand / review / summarize an existing video | `watch` | Frames + transcript as evidence |

Any other installed video skill (explainer, podcast, language-swap, viral-hook, ugc-ads,
founder-product-video, app-sizzle, content-director, ...) is a valid route when its trigger
matches better than the table; read its description and prefer it for its niche.

Full decision notes and chaining recipes: `references/pipelines.md`.

**If the best specialist isn't installed**, say which one would do it best and give its install
command (see `references/pipelines.md#install`), then offer the best installed fallback. Never
silently downgrade.

## 3. Hand off and chain

- Load the chosen skill with the Skill tool and follow it as written. Its rules beat yours.
- Pass it the brief you gathered so it doesn't re-ask what the user already answered.
- For multi-part jobs, run specialists in sequence and join their outputs with `video-tools`
  (`concat`, `add_music`, `burn_captions`, `reframe`, `export`). Keep every intermediate file;
  never overwrite a specialist's output in place.
- Keep one project folder: `video-out/<slug>/` with `01_*`, `02_*` numbered intermediates and
  `final_<platform>.mp4`.

## 4. Finish: the QA loop (always)

Load `video-qa` and run it on every deliverable, whichever specialist made it. A specialist's
own QA (onetake's oracle, brag's checks) runs first; `video-qa` is the shared last gate for
delivery specs (loudness, aspect, black/frozen frames, dead air) and a visual look via contact
sheet. Fix, re-run, and only then report.

Report to the user: what was made, which specialist(s) made it, the file paths, the QA verdict,
and anything that is placeholder or unverified.
