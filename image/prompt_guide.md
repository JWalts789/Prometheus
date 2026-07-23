# Professional image-prompt engineering (Stable Diffusion 1.5 / DreamShaper)

Baseline craft principles. PROMETHEUS's own studied knowledge is layered on top of these.

## Structure a prompt in this order (most important first — SD weights early tokens more)
1. **Subject** — the concrete main thing, with a few defining traits ("an elderly potter", "a lone lighthouse").
2. **Action / setting** — what it's doing, where ("mending a cracked bowl", "on a storm-lashed cliff").
3. **Medium** — pick ONE and commit: "oil painting", "cinematic photograph", "digital concept art", "watercolor", "3D render".
4. **Style / mood** — an art movement or descriptive style ("baroque", "impressionist", "ethereal", "moody", "minimalist").
5. **Lighting** — one of the strongest levers: "dramatic rim lighting", "golden hour", "soft diffused light", "chiaroscuro", "volumetric god rays".
6. **Composition / camera** — "wide establishing shot", "close-up portrait", "rule of thirds", "shallow depth of field, bokeh", "low angle".
7. **Quality boosters** (end): "highly detailed, sharp focus, intricate, masterpiece, professional, award-winning".

## Rules that matter on SD1.5
- **Comma-separated phrases**, not sentences. One clean line.
- **Keep it ~30–60 words.** Overlong prompts dilute; the model attends to the front.
- **Concrete, visual nouns and adjectives only.** SD cannot render abstract ideas ("justice", "the meaning of learning") — translate them into a *depictable scene or metaphor* (e.g. "learning" → "a figure reading by candlelight, glowing pages, motes of dust in warm light").
- **One clear subject.** Multiple competing subjects/actions confuse it; if you need a scene, make one the clear focus.
- **Name a concrete medium and lighting** — these do more for quality than piling on adjectives.
- DreamShaper leans **painterly / cinematic / fantasy-realism**; it rewards artistic, evocative descriptions.
- Avoid contradictions (e.g. "photorealistic, flat cartoon") and unrenderable specifics (exact text, precise counts, brand logos).

## Negative prompt (what to exclude)
Standard: `lowres, bad anatomy, extra fingers, extra limbs, deformed, disfigured, mutated, text, watermark, signature, jpeg artifacts, blurry, worst quality, low quality, cropped, out of frame`.

## Example transforms
- "kintsugi" → `a weathered hand repairing a cracked ceramic bowl with veins of molten gold, macro close-up, warm studio lighting, dark background, cinematic photograph, shallow depth of field, highly detailed, intricate, masterpiece`
- "the Fermi paradox" → `a lone astronomer silhouetted against a vast starfield and a silent radio telescope, cosmic scale, deep blue and violet palette, volumetric light, wide cinematic shot, awe and solitude, concept art, highly detailed`
