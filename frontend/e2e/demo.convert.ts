import { spawnSync } from 'node:child_process'
import { readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

/**
 * Converts the newest Playwright recording into the README's hero GIF.
 *
 * The recording step (demo.record.ts) and this conversion were split: Playwright
 * writes a hash-named .webm into demo-recording/, and turning that into a small,
 * clean gif is its own ffmpeg incantation worth committing rather than
 * remembering. Together they make docs/demo.gif reproducible end to end -- run
 * the recorder, then run this, and the committed gif is regenerated from the real
 * app, not hand-captured.
 *
 * A two-pass palette is why the gif looks clean at a small size: palettegen picks
 * the best 256 colours for THIS clip, paletteuse maps every frame onto them.
 * A flat single-pass gif quantises per frame and shimmers.
 *
 * Requires ffmpeg on PATH.
 *
 * Run (from frontend/):  pnpm exec tsx e2e/demo.convert.ts
 * Tunables:  DEMO_OUT (recording dir), DEMO_GIF (output), DEMO_FPS, DEMO_WIDTH
 */

const OUT = process.env.DEMO_OUT ?? 'demo-recording'
const GIF = process.env.DEMO_GIF ?? '../docs/demo.gif'
// The demo is static holds punctuated by instant navigations -- there is no smooth
// motion to preserve -- so 10 fps loses nothing a viewer would notice while trimming
// frames. 1000px keeps the small stat/table text legible; drop width before fps if the
// file still grows past a few MB, since legibility is what the README hero is for.
const FPS = process.env.DEMO_FPS ?? '10'
const WIDTH = process.env.DEMO_WIDTH ?? '1000'

// Newest .webm in the recording dir -- Playwright names them by hash, so "the one
// just recorded" is the most recently modified, not a fixed filename.
const webms = readdirSync(OUT)
  .filter((f) => f.endsWith('.webm'))
  .map((f) => ({ path: join(OUT, f), mtime: statSync(join(OUT, f)).mtimeMs }))
  .sort((a, b) => b.mtime - a.mtime)

if (webms.length === 0) {
  console.error(`No .webm in ${OUT}/ -- run "pnpm exec tsx e2e/demo.record.ts" first.`)
  process.exit(1)
}

const input = webms[0].path
// bayer_scale=5 is a fine dither: enough to keep the molecule's anti-aliased strokes
// from banding, little enough noise that flat UI regions still compress small.
const filter =
  `fps=${FPS},scale=${WIDTH}:-1:flags=lanczos,` +
  `split[s0][s1];[s0]palettegen=stats_mode=diff[p];` +
  `[s1][p]paletteuse=dither=bayer:bayer_scale=5`

console.log(`converting ${input} -> ${GIF} (fps=${FPS}, width=${WIDTH})`)
const res = spawnSync('ffmpeg', ['-y', '-i', input, '-vf', filter, '-loop', '0', GIF], {
  stdio: 'inherit',
})

if (res.error || res.status !== 0) {
  console.error('ffmpeg failed', res.error ?? `exit ${res.status}`)
  process.exit(1)
}
const bytes = statSync(GIF).size
console.log(`wrote ${GIF} (${(bytes / 1_048_576).toFixed(2)} MB)`)
