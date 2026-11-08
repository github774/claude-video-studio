# Pipelines, chains and installs

## Decision notes

**Code or site → launch video.** `brag-slim` when the user wants it fast with tools already on
the machine; `brag` (HyperFrames) when they want its richer templates. If the user wants the UI
to *move* like an Apple-grade feature film rather than a launch reel, use `onetake` instead.

**Product feature demo without screen recording.** `onetake`: it rebuilds the UI in HTML from
screenshots, so the result is crisp at 4K and every motion is designed.

**A narrated explainer with talking points.** Write the script first. A-roll = the user's
footage (cut with `video-edit`) or a `onetake` narrated cut. For each abstract line that needs
a visual, a `collage-broll-explainers` clip. Join with `video-tools`.

**A film whose look IS the point** (a painted, printed, drawn or diagrammatic style), or an
evidence film built from real documents, scans or data: `lemo-opuscar`. It has its own
treatment → production → delivery flow and one round of questions; let it run that flow, then
use `video-tools` only for platform exports and `video-qa`. Its skill says it is not for plain
editing of existing files; send those to `video-edit`.

**Collage B-roll vs lemo-opuscar.** One ~5 s voiceover line as a paper-collage insert →
`collage-broll-explainers`. A whole film in one consistent style → `lemo-opuscar`.

**Lots of variants from data** (per-customer, per-locale, per-stat). Remotion.

**Footage already exists.** `video-edit` first. Generate nothing until the cut works.

## Chaining recipes

### Talking head + collage B-roll explainer (YouTube)
1. `video-edit`: `remove_silence` → trim → A-roll `01_aroll.mp4`.
2. Pick 2-4 abstract lines from the transcript. `collage-broll-explainers` for each (it runs
   its own three approval gates with the user).
3. `concat` A-roll segments and B-roll in script order (use `trim` to split the A-roll at the
   B-roll insert points). B-roll carries its own fitted voiceover if made with one; otherwise
   keep the A-roll audio continuous by building the picture edit first and laying the
   original audio back with `add_music`-style mixing.
4. `burn_captions` (if wanted) → `export preset=youtube` → `video-qa`.

### Launch video → every platform
1. `brag-slim` or `onetake` makes the master (keep its native resolution).
2. `export` for `youtube`, `shorts` (blur-pad or crop), `x`, `linkedin`.
3. `video-qa` each export with its matching target.

### Product demo + other languages
`onetake` handles narration, subtitles and other-language versions natively; let it. Then
`video-qa` each language file.

### Review someone's cut
`watch` to read it, `video-tools` `detect` + `qa_report` for hard numbers, `contact_sheet` to
see pacing. Report notes with timestamps.

## Install

| Specialist | Install | License |
|---|---|---|
| video-studio (this) | `/plugin marketplace add github774/claude-video-studio` then `/plugin install video-studio@claude-video-studio` | MIT |
| brag, brag-slim | `/plugin install brag@claude-video-studio` | MIT (latent-spaces/brag) |
| HyperFrames | `/plugin install hyperframes@claude-video-studio` | Apache-2.0 (heygen-com/hyperframes) |
| watch | `/plugin install watch@claude-video-studio` | MIT (bradautomates/claude-video) |
| lemo-opuscar | `/plugin install lemo-opuscar@claude-video-studio`, or let the director install it on first use | MIT code, CC BY 4.0 media (lemomo-ai/lemo-opuscar) |
| onetake | `scripts/install-upstream.sh onetake` (clones feitangyuan/onetake into `~/.claude/skills`) | PolyForm Noncommercial 1.0.0: free for noncommercial use only |
| Remotion skills | `npx skills add remotion-dev/skills` or `scripts/install-upstream.sh remotion` | see remotion-dev/skills |
| collage-broll-explainers | Install from its original source (needs MaxFusion MCP). Not redistributed here: no license was published with it. | unpublished |
