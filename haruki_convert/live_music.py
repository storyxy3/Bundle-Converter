"""Extract one Unity AudioClip without invoking UnityPy's FMOD playback path."""
import json
import subprocess
import tempfile
from pathlib import Path


def export(bundle, out, vgmstream, deobfuscator=None, bundle_name=None):
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.77f1"
    from UnityPy.helpers.ResourceReader import get_resource_data
    data = Path(bundle).read_bytes()
    if not data.startswith(b'UnityFS'):
        if not deobfuscator or not bundle_name:
            raise ValueError('Obfuscated input needs --deobfuscator and --bundle-name')
        import importlib.util
        spec = importlib.util.spec_from_file_location('octo_deobf', deobfuscator)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data = module.apply(data, bundle_name.encode())
    clips = [o.read() for o in UnityPy.load(data).objects if o.type.name == 'AudioClip']
    if len(clips) != 1:
        raise ValueError('Expected exactly one AudioClip')
    clip = clips[0]
    if clip.m_CompressionFormat != 1:
        raise ValueError('Expected a Vorbis AudioClip')
    r = clip.m_Resource
    raw = bytes(clip.m_AudioData) if clip.m_AudioData else get_resource_data(
        r.m_Source, clip.object_reader.assets_file, r.m_Offset, r.m_Size)
    dest = Path(out)
    dest.mkdir(parents=True, exist_ok=True)
    method = 'FSB5 Vorbis lossless remux'
    # Shared TypeScript remuxer: unknown setup CRCs fail without re-encoding.
    import shutil
    bun = shutil.which('bun')
    if not bun:
        raise ValueError('Lossless live-music conversion requires bun on PATH')
    with tempfile.TemporaryDirectory(dir=dest) as scratch:
        fsb = Path(scratch)/'music.fsb'
        fsb.write_bytes(raw)
        subprocess.run([bun, str(Path(__file__).resolve().parents[1]/'remux-audio.ts'), str(fsb), str(dest/'music.ogg')], check=True)
    manifest = dict(format='audio-file/1', file='music.ogg', codec='vorbis', length=clip.m_Length)
    (dest/'music.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(**manifest, source=clip.m_Name, sampleRate=clip.m_Frequency, channels=clip.m_Channels, method=method), indent=2))
