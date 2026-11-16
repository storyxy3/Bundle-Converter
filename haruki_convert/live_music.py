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
    try:
        import fsb5
        bank = fsb5.FSB5(raw)
        if len(bank.samples) != 1:
            raise ValueError('Expected one FSB sample')
        ogg = bank.rebuild_sample(bank.samples[0])
        if not ogg.startswith(b'OggS'):
            raise ValueError('Remux did not produce Ogg')
        (dest / 'music.ogg').write_bytes(ogg)
    except (ImportError, ValueError, KeyError, NotImplementedError) as error:
        method = f'vgmstream decode + libvorbis quality 9; remux unavailable: {error}'
        with tempfile.TemporaryDirectory(dir=dest) as scratch:
            fsb, wav = Path(scratch)/'music.fsb', Path(scratch)/'music.wav'
            fsb.write_bytes(raw)
            subprocess.run([vgmstream, '-i', '-W', '4', '-o', str(wav), str(fsb)], check=True)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wav), '-c:a', 'libvorbis', '-q:a', '9', str(dest/'music.ogg')], check=True)
    manifest = dict(format='audio-file/1', file='music.ogg', codec='vorbis', length=clip.m_Length)
    (dest/'music.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(**manifest, source=clip.m_Name, sampleRate=clip.m_Frequency, channels=clip.m_Channels, method=method), indent=2))
