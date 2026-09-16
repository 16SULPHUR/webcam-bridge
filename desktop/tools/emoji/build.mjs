// build.mjs — Rebuild the bundled reaction emoji from Twemoji SVGs.
//
//   cd desktop/tools/emoji
//   npm install
//   npm run build              # rebuild the bundled pack
//   npm run build -- 🦄 🫠      # add your own
//
// Output: desktop/webcam_bridge/assets/emoji/<codepoints>.png (192 px)
// Artwork: Twemoji by Twitter, Inc and other contributors, CC-BY 4.0
//          https://github.com/jdecked/twemoji

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Resvg } from "@resvg/resvg-js";

const TWEMOJI_VERSION = "15.1.0";
const SVG_BASE = `https://cdn.jsdelivr.net/gh/jdecked/twemoji@${TWEMOJI_VERSION}/assets/svg`;
const SIZE = 192;

// Keep in sync with the emoji used by reactions/catalog.py defaults.
const BUNDLED = [
  "👍", "👎", "✌", "👋", "✊", "👌", "🤘", "🤙", "☝", "❤",
  "🎉", "😄", "😮", "😉", "🤨", "🔥", "💯", "😂", "🤯", "👏",
  "🙌", "⭐", "💀", "🥳", "🤔", "✨", "🙏", "🤝", "😎", "😭",
  "🤡", "🫶", "👀", "💩", "🚀", "🍿", "🎯", "🧠", "⚡", "🏆",
];

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, "..", "..", "webcam_bridge", "assets", "emoji");

const codepoints = (s) => [...s].map((c) => c.codePointAt(0));
const SKIP = new Set([0xfe0f, 0xfe0e]);

// Must match reactions/common.py emoji_filename().
function outputName(char) {
  const parts = codepoints(char).filter((cp) => !SKIP.has(cp) && cp !== 0x200d);
  return (parts.map((cp) => `u${cp.toString(16)}`).join("_") || "unknown") + ".png";
}

// Twemoji drops FE0F except inside ZWJ sequences.
function twemojiName(char) {
  const cps = codepoints(char);
  const list = cps.includes(0x200d) ? cps : cps.filter((cp) => cp !== 0xfe0f);
  return list.map((cp) => cp.toString(16)).join("-");
}

async function build(char) {
  const url = `${SVG_BASE}/${twemojiName(char)}.svg`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${char}: HTTP ${res.status} for ${url}`);
  const svg = await res.text();
  const png = new Resvg(svg, { fitTo: { mode: "width", value: SIZE } }).render().asPng();
  const file = join(outDir, outputName(char));
  await writeFile(file, png);
  console.log(`${char}  ->  ${outputName(char)}`);
}

const chars = process.argv.slice(2).length ? process.argv.slice(2) : BUNDLED;
await mkdir(outDir, { recursive: true });
let failed = 0;
for (const c of chars) {
  try {
    await build(c);
  } catch (err) {
    failed++;
    console.error(err.message);
  }
}
process.exit(failed ? 1 : 0);
