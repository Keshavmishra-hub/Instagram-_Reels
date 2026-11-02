# MASS ENTHUSIAST — cinematic title intro

A 33-second, fully original title sequence for **MASS ENTHUSIAST**, built from code:
3D scenes in Blender (Cycles), a Python compositor, and a soundtrack synthesised from scratch.

| Deliverable | File |
|---|---|
| 16:9 master — 1920×1080, 30 fps, H.264 High / yuv420p, AAC 48 kHz 320 kb/s | `exports/MASS_ENTHUSIAST_Intro_16x9_1080p.mp4` |
| 9:16 Instagram edition — 1080×1920, same specs, native vertical framing | `exports/MASS_ENTHUSIAST_Intro_9x16_Reels.mp4` |
| Soundtrack (mastered, −15 LUFS, −1.2 dBTP) and stems | `audio/mass_enthusiast_mix.wav`, `audio/stems/` |

## The idea

The reference ("What if LCU had an intro") builds tension with symbolic objects lit in the dark, then
forges its logo from metal. This intro uses the same storytelling principle with its own universe: the
objects of cinema, joined by match cuts on circles and by a red light that travels from object to object
until it forges the title.

| Time | Shot | What happens |
|---|---|---|
| 0:00 | Chain | A steel chain turns in total darkness; light finds it link by link. The bottom ring turns to face us and we push into its hole. |
| 0:05 | Reel | Match cut on the circle: a 35 mm reel spins, lamp light through its windows. |
| 0:06 | Film gate | The strip clacks through the gate one frame at a time — moments from your own photos. |
| 0:07 | Projector | The lamp ignites, whip-pan down the beam: the screen fills with the speech (fist raised). |
| 0:09 | Ticket | An ADMIT ONE ticket tumbles in slow motion, burning in from the edges. |
| 0:10 | Lens | A cine lens stares back; its iris snaps shut over a red glow. |
| 0:11 | Speaker | Two bass hits; steel beads leap off the cone. |
| 0:12 | Red line | A red light races along the chain lying on a steel floor. |
| 0:13 | Sparks | A grinder (unseen) screams across a chamfered steel edge. |
| 0:14 | Spotlight | A stage light swings round and stares into the lens; flare. |
| 0:15 | Vortex | Every object tumbles at camera through firelight; speed ramp, hits on the beat. |
| 0:18 | Flash | White-red flash, suck-back to silence. |
| 0:19 | **Title** | Each MASS letter is a gunmetal frame filled with molten metal; a brushed-steel plate slams into it and squeezes sparks out of the glowing seam (M, A, S, S — four close-ups). Pull back: MASS locks, light sweep. ENTHUSIAST flips up letter by letter, each plate locking on a note of a rising scale. |
| 0:27 | Hero | Slow push-in on the lock-up over a dark reflective floor; final impact at 0:29.8, fade at 0:32. |

### Typography
`blender/lib/glyphs.py` draws an original heavy angular face (only the nine glyphs the title needs:
M A S E N T H U I). Every convex corner is chamfered; the top-left and bottom-right corners get a long
"blade" cut, which gives the word a forward, forged feel; the A has a triangular counter. MASS sits on
top, ENTHUSIAST is justified to exactly the same width underneath. Each 3D letter is three parts —
gunmetal body, polished rim, brushed-steel face plate — with a crimson seam between rim and plate.

## How it is built

```
mass_enthusiast_intro/
  timeline.py              every shot range and every beat (frames @30 fps) — picture and sound read it
  blender/
    lib/common.py          render setup, procedural materials (metal, molten, emission), lights, cameras
    lib/glyphs.py          the custom letterforms (shapely geometry)
    lib/title_rig.py       title choreography: slams, recoil, glow temperature, camera moves
    lib/assets.py          procedural models: chain, ring, reel, film strip, projector, ticket, iris, speaker, spotlight
    shots/*.py             one module per shot
    render.py              builds a shot and renders EXR frames (resumable)
    queue.sh, jobs_*.txt   render job lists (16:9 and 9:16)
  comp/                    compositor: sparks/embers/dust simulated in 3D and projected with the real
                           camera + depth test, god rays, projector beam, flares, smoke, floor reflection,
                           bloom, filmic tone map, grade, chromatic aberration, vignette, grain
  audio/                   synth.py (DSP toolkit) + sound_design.py (score, effects, mix, master)
  assets/scripts/make_textures.py   film frames, film strip, screen image, ticket, lens markings
  assets/textures/         generated textures      assets/images/source/  stills taken from your video
  make_final.py            composite + mux + verify specs
  render/ build/           intermediates (git-ignored)
```

### Requirements
Python 3.13, FFmpeg, and (in a venv) `pip install bpy==5.2.3 numpy scipy pillow opencv-python-headless
soundfile OpenEXR shapely`. No GPU is needed (Cycles CPU, 4 cores used for the master).

### Re-render from scratch
```bash
PY=/path/to/venv/bin/python
$PY assets/scripts/make_textures.py                 # only if you change photos/ticket text
grep -v '^#' blender/jobs_16x9.txt | PY=$PY blender/queue.sh   # 3D renders (resumable)
$PY audio/sound_design.py                           # soundtrack
$PY make_final.py --variant 16x9                    # composite, mux, verify
grep -v '^#' blender/jobs_9x16.txt | PY=$PY blender/queue.sh
$PY make_final.py --variant 9x16
```
Quick checks: `$PY blender/render.py --shot s13_title --frames 600,700 --scale 0.3 --samples 4 --preview`
writes small PNG previews; `$PY comp/comp.py --variant 16x9 --frames 560-640 --png build/qc` composites stills.

### Common changes
* **Timing** — edit `timeline.py` (shot ranges, `TITLE`, `BEATS`); re-render the affected shots, then
  re-run the soundtrack and `make_final.py`. Sound cues follow automatically.
* **Title colours / metal** — `blender/shots/title.py` (`_materials`, lights, reflection cards) and the
  glow curve in `blender/lib/title_rig.py` (`glow`).
* **Letterforms** — `blender/lib/glyphs.py` (`BIG`/`SMALL` chamfers, glyph functions, `lockup()` spacing).
* **Photos on the film strip / projector screen** — edit `FRAMES` in `assets/scripts/make_textures.py`
  and re-run it, then re-render `s03_film` and `s04_projector`.
* **Look** — `GRADE` table and the recipes in `comp/comp.py`; no 3D re-render needed.
* **Music / effects** — `audio/sound_design.py` (`build()` places every element on its cue).

### Render settings used
16 samples + OpenImageDenoise. Montage shots and the title close-ups render at 75 % and are upscaled in
the compositor (they are dominated by depth of field and motion blur); the title pull-back and hero shot
render at full 1920×1080. The 9:16 edition renders smaller and is upscaled.

## Rights
Everything here is original: geometry, materials, animation, letterforms and every sound are generated
by these scripts. Fonts used for small printed details (ticket, film edge numbers) are the OFL fonts
already in `renderer/public/fonts`. The film frames and the projected image come from the photos and
video you supplied. The reference video was only studied for pacing and atmosphere — none of its
footage, music, watermark or logo is used.
