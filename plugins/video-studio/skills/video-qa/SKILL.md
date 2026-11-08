---
name: video-qa
description: >-
  The shared last gate before any video is called done, whichever skill made it (brag, onetake,
  collage-broll-explainers, HyperFrames, Remotion, video-edit). Runs the video-tools qa_report
  (dimensions, pixel format, fps, aspect, platform length, loudness, true peak, black and frozen
  frames, dead air, pacing) and a visual contact-sheet review, then fixes and re-checks. Use after
  rendering or exporting a video, or when the user asks "is this ready", "check this video", "QA
  this", or "why does this look/sound off".
---

# Video QA

A specialist's own checks (onetake's slideshow oracle, brag's render checks, the collage
skill's frame QA) run first and are never skipped. This gate adds the delivery checks every
video needs, plus a look with your own eyes.

## Loop

1. **Numbers**: `qa_report(input, target)` with the target that matches the destination
   (`youtube`, `shorts`, `tiktok`, `reels`, `x`, or `any`). Pass `expected_duration` when the
   brief fixed a length.
2. **Eyes**: `contact_sheet(input, frames=12)`. Look at it. Check:
   - the first frame is a real image (not black, not a loading state), and it hooks;
   - text is inside safe areas (9:16: keep ~250 px clear top and bottom for platform UI);
   - nothing is cut off, stretched, or letterboxed by accident;
   - captions are readable and not covering faces or UI that matters;
   - the shot changes often enough for the platform (social: something new every 1-3 s).
3. **Fix** what failed with the matching tool (`normalize_audio` for loudness or peak,
   `reframe` / `export` for aspect and pixel format, `trim` for black heads/tails,
   `remove_silence` for dead air). For problems in generated content, go back to the
   specialist that made it, using its own revision flow.
4. **Re-run** steps 1-2 on the fixed file. Repeat until the verdict is `pass`, or only
   `warn`s remain that you can explain.

## Report

State the verdict, list any remaining warnings with why they are acceptable, give the final
path(s), and never say "looks good" without having looked at the contact sheet.
