// Offline entry point for the same packet-preserving remux used by the browser.
import { remuxFsbVorbis } from '../../src/original/unityAudioClip';
const [input, output] = Bun.argv.slice(2);
if (!input || !output) throw new Error('Usage: bun remux-audio.ts input.fsb output.ogg');
await Bun.write(output, remuxFsbVorbis(new Uint8Array(await Bun.file(input).arrayBuffer())));
