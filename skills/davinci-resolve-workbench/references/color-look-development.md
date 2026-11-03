# Color and look development

The branch for "give this footage a look": grade, LUT, film grain, glow,
vignette, stabilization. Read `resolve-api-gotchas.md` alongside this file —
half the trouble here is API-level, not creative.

## 1. Analyze the references before grading anything

Run `media_probe.py` on every reference and read four numbers per file:
black point (p01), highlight (p99), mean saturation, shadow noise (std below
p10). Then:

- **Black level.** A film look never has pure 0. Lift to ~0.02–0.05 and give
  the shadows a hue (the reference set measured ≈ 209°, a cool teal-navy).
- **Contrast.** p99 − p01 around 0.5–0.65 reads "filmic"; above ~0.85 it turns
  harsh and starts crushing the bodywork.
- **Saturation.** The reference clips sat around 0.17–0.22 mean saturation with
  shadow saturation up to ~0.44; the daylight key frame was far lower. A safe
  target for a "premium, not trailer" look is a mean of 0.22–0.30.
- **Grain.** Measured grain in the references was ≈ 1.8 % on the key frame and
  ≈ 0.17–0.22 % on the clips. Very fine grain at the low end of that range is
  the safe choice.

Then name the dominant complementary pairs (e.g. teal/navy ↔ amber,
magenta/pink ↔ violet/blue). Conflicts between references are resolved by the
still image — it is the color key frame.

## 2. Design the LUT

Write the transform in numpy first (fast to iterate), then emit a `.cube` and
validate it against the numpy version.

Anchor table for a dusty-pink / teal film family — a **template**, adapt it to
the target look and check each anchor after generation:

| Input | Intended output | Reason |
|---|---|---|
| black (0,0,0) | ≈ (0.002, 0.000, 0.007) | lifted, cool black |
| red (1,0,0) | ≈ (1.0, 0.77, 0.91) | dominant body colour → dusty pink, sat ≈ 0.24, hue ≈ 337° |
| green (0,1,0) | ≈ (0.54, 0.95, 0.80) | foliage/cyans → teal |
| blue (0,0,1) | ≈ (0.35, 0.68, 1.0) | sky/shadows → cool blue |
| white (1,1,1) | ≈ (0.94, 0.92, 0.98) | highlights stay slightly cool, never blown |

Rules that matter:

- **Red is the fastest-varying axis** in a `.cube` for Resolve. Flat index:
  `(b*N + g)*N + r`. Indexing as `lut[g,r,b]` swaps R and B and silently ruins
  the grade — this cost a full debug cycle once.
- WB and exposure belong **inside** the LUT. `SetCDL` through the API applies
  its own transfer curve and blows the picture out (measured ≈ `y = 1.19·x^0.196`),
  so it is not used for the project look; a CDL offset is applied later in the
  offline post pass instead.
- The LUT is installed in `…\DaVinci Resolve\Support\LUT\MCP\` and referenced
  from Resolve as `MCP\Name.cube`.

## 3. Iterate the look offline, not in Resolve

The offline loop is 10–50× cheaper than re-rendering in Resolve:

1. `ffmpeg -i src -vf "lut3d=file=<copy>.cube" ...` — copy the cube to a
   colon-free path first, the filter parser breaks on drive letters.
2. numpy pass for glow (bright-pass + blur + screen), grain, and vignette.
3. Apply the same CDL math as the final post pass, so the preview and the
   final are numerically identical.

Ship the preview to the user as approval material before touching Resolve.

Glow must be a **bright-pass blur added to the source**, not a global haze:
threshold high (only sources and speculars survive), blur radius moderate,
blend low. Anything else produces the "milky fog" look that flattens the car.

Vignette: a soft radial falloff, strength ≈ 0.20 at radius ≈ 1.05, applied as
`1 - strength * clip((d - 0.42) / 0.75, 0, 1) ** 1.7` with `d` the normalized
elliptical distance. Doing it in Fusion (EllipseMask + Merge/EffectMask) did not
produce a usable gradient in this build — keep it in the post pass.

## 4. Build the Resolve chain to match

- One Color node: `ti.GetNodeGraph(1).SetLUT(1, "MCP\\Name.cube")`. There is
  no `AddNode`, so a four-node graph is not scriptable — encode the whole
  transform in the LUT.
- Fusion comp on the clip: `MediaIn → Glow → FilmGrain → MediaOut`.
  Connect by input **name** (`"Input"`, `"Background"`, …), never by index.
- Parameters that produced the approved look:
  - Glow — Blend 1.0, Low 97, High 100, Glow 0.12, XGlowSize 4, YGlowSize 4,
    Passes 1, ColorScale 1, Alpha 1, filter `Fog Glow`.
  - FilmGrain — Blend 1.0, MasterStrength 0.03, MasterXSize 1.0,
    MasterYSize 1.0, MasterRoughness 0.5, Monochrome 1, Randomize 1,
    Complexity 1.
- Verify the comp by rendering one frame, not by trusting the parameters.

## 5. Stabilization

`ti.Stabilize()` is the only available mechanism, and its effect is not
readable through the API (`GetProperty("Stabilization")` stays `False`).
Verify it on the rendered output instead:

```
python frame_qc.py motion --src source.mov --graded render.mp4 --start 200 --count 40
```

Compare the same frame range in both files. A moving-camera shot typically
lands around a 30–50 % drop in mean frame-to-frame difference; a shot dominated
by the car's own motion shows less, which is expected and not a failure.

## 6. QC thresholds

Measure, do not eyeball. `frame_qc.py compare` prints per frame:

| Metric | Healthy | Warning sign |
|---|---|---|
| clipping (`clip_pct`) | ≤ 0.5 % | > 2 % → blown highlights |
| shadow noise (`shadow_std`) | ≤ 0.03 and no colour cast | rising → colour noise in shadows |
| contrast | 0.55–0.85 | < 0.4 → flat, > 0.9 → harsh |
| mean saturation | 0.20–0.30 | > 0.45 → loud, trailer-like |
| black point | 0.02–0.10 | 0.000 → crushed, no atmosphere |

Compare the Resolve output against the approved preview: mean absolute
difference per channel should stay below ~0.02. A larger gap means the
Resolve chain does not reproduce the approved look — fix it before showing
anything.

## 7. Control frames

Four scenes cover most footage and keep the review short:

1. **dark / far** — shadow behaviour, noise, overall mood;
2. **bright specular** — highlight roll-off, glow on the light source;
3. **metal / reflection** — saturation of the bodywork, how reflections read;
4. **close-up** — sharpness and detail retention on the body.

Extract them with `frame_qc.py compare --frames ...`, build the contact sheet
(source vs result) and attach it with the numbers.

## 8. Approval flow

Preview (low res) → control sheet + metrics → explicit go/no-go → final render
at the agreed resolution → post pass (CDL + vignette) so the final matches the
approved frames → verify → deliver master plus compact copies.
