"""Motion-only interchange. Original component bindings and settings remain explicit metadata."""
import json
from pathlib import Path
import numpy as np
from .unity_assets import Assets
from .unity_clip import clips, TRANSFORM_WIDTH
from . import profiles
from .sources.pjsk_twist import euler_to_q


def flags(c):
    return {k.removeprefix('m_'): v for k, v in c.muscle_clip.items()
            if isinstance(v, (bool, float, int))}


def metadata(a):
    for o in a.of_type('MonoBehaviour'):
        t = o.read_typetree()
        if 'baseAnimation' in t:
            return t
    return {}


def paths(skeleton):
    out = []
    for b in skeleton['bones']:
        out.append('' if b['parent'] < 0 else '/'.join(filter(None, (out[b['parent']], b['name']))))
    return out


def generic(bundle, skeleton, prefix, clip_name, rate=60, height=1.58):
    if rate <= 0 or height <= 0:
        raise ValueError('rate and height must be positive')
    sk = json.load(open(skeleton))
    a = Assets([bundle], profiles.load('pjsk')['unityVersion'])
    selected = list(clips(a, lambda n: n == clip_name))
    if len(selected) != 1:
        raise ValueError(f'expected exactly one clip {clip_name}, found {len(selected)}')
    c = selected[0]
    n = int(np.ceil((c.stop - c.start) * rate)) + 1
    times = np.minimum(c.start + np.arange(n) / rate, c.stop)
    names, data, bound = [], [], set()
    for b, path in zip(sk['bones'], paths(sk)):
        indices = {a: c.transform(path, a) for a in ('position', 'rotation', 'euler', 'scale')}
        if all(i is None for i in indices.values()):
            continue
        names.append(b['name'])
        row = np.tile(b['position'] + b['rotation'] + b['scale'], (n, 1))
        for attr, start, width in (('position', 0, 3), ('rotation', 3, 4), ('scale', 7, 3)):
            ci = indices[attr]
            if ci is not None:
                for k in range(width):
                    row[:, start + k] = [c.sample(ci+k, float(t)) for t in times]
                bound.add((path, attr))
        if indices['rotation'] is None and indices['euler'] is not None:
            ci = indices['euler']
            row[:, 3:7] = [euler_to_q([c.sample(ci+k, float(t)) for k in range(3)]) for t in times]
        norms = np.linalg.norm(row[:, 3:7], axis=1)
        if np.any(norms < 1e-8):
            raise ValueError(f'zero quaternion on {b["name"]}')
        row[:, 3:7] /= norms[:, None]
        data.append(row)
    values = np.concatenate(data, axis=1).astype('<f4')
    if not np.isfinite(values).all():
        raise ValueError('non-finite Generic sample')
    values.tofile(prefix + '.f32')
    header = dict(format='haruki-generic-samples/1', clip=c.name, source=bundle, rate=rate, frames=n,
                  start=c.start, duration=c.stop-c.start, characterHeight=height, bones=names,
                  floatsPerFrame=values.shape[1], settings=flags(c),
                  positionPolicy='original Position is interpreted as normalized travel for this conversion; Move = Position * characterHeight',
                  layout='per bone: localPosition xyz, localRotation xyzw, localScale xyz')
    Path(prefix + '.json').write_text(json.dumps(header, indent=2))
    helper_names = [name for name in names if any(k in name for k in ('AssistHip', 'Pectoralis_01', 'ArmRoll', 'ForeArmRoll'))]
    helper_indices = [names.index(name) for name in helper_names]
    helper_values = values.reshape(n, len(names), 10)[:, helper_indices, :7].copy()
    helper_values.astype('<f4').tofile(prefix + '.helpers.f32')
    Path(prefix + '.helpers.json').write_text(json.dumps(dict(format='haruki-motion-helpers/1', rate=rate, frames=n,
        bones=helper_names, floatsPerFrame=7*len(helper_names), dataFile=Path(prefix).name+'.helpers.f32',
        layout='per bone: localPosition xyz, localRotation xyzw', source=bundle, clip=c.name), indent=2))
    print(f'Generic {c.name}: {n} frames, {len(names)} bones, {values.nbytes} bytes')


def sidecar(a, c, prefix, rate, times, include_props=False, layout_bundle=None, actor='Actor_00'):
    """All non-human body channels, with compiled binding identity; no facial clip is read."""
    meta = metadata(a)
    path_names = {0: ''}
    import zlib
    for b in meta.get('baseAnimation', {}).get('bindings', []):
        path = b.get('path', '')
        path_names[zlib.crc32(path.encode()) & 0xffffffff] = path
    records, samples, offset = [], [], 0
    for g in c.bindings:
        if g['typeID'] == 95:
            continue
        path = path_names.get(g['path'])
        if not include_props and (path or '').startswith('Root_Microphone'):
            continue
        width = TRANSFORM_WIDTH.get(g['attribute'], 1) if g['typeID'] == 4 else 1
        ci = c.bind[(g['path'], g['attribute'], g['typeID'])]
        records.append(dict(binding=g, path=path, offset=offset, width=width))
        samples.append([[c.sample(ci+k, float(t)) for k in range(width)] for t in times])
        offset += width
    values = np.concatenate(samples, axis=1).astype('<f4') if samples else np.empty((len(times), 0), '<f4')
    values.tofile(prefix + '.semantics.f32')
    doc = dict(format='haruki-motion-semantics/1', sourceBundles=a.paths, sourceClip=c.name, rate=rate, frames=len(times), floatsPerFrame=offset,
               clipSettings=flags(c), motionDefine=meta, bindings=records, includeProps=include_props,
               dataFile=Path(prefix).name + '.semantics.f32', evaluationOrder=['layout', 'Humanoid', 'FullBodyIK', 'constraints', 'Quartz', 'Swing', 'HipCorrector'])
    excluded = {'effects', 'faceAnimation', 'isLoopMotionEffect'}
    if not include_props: excluded.add('propConstraints')
    doc['motionDefine'] = {k:v for k,v in meta.items() if k not in excluded}
    if layout_bundle:
        la = Assets([layout_bundle], profiles.load('gakumas')['unityVersion'])
        lc = next(clips(la))
        layout = []
        for t in times:
            row = []
            for path in ('', actor):
                for attr, width in (('position',3),('euler',3)):
                    ci = lc.transform(path, attr)
                    row.extend([lc.sample(ci+k, float(t)) if ci is not None else 0 for k in range(width)])
            layout.append(row)
        np.array(layout, '<f4').tofile(prefix + '.layout.f32')
        doc['layout'] = dict(source=layout_bundle, actor=actor, dataFile=Path(prefix).name+'.layout.f32',
                             layout='root position xyz, root Euler xyz, actor position xyz, actor Euler xyz', floatsPerFrame=12)
    Path(prefix + '.semantics.json').write_text(json.dumps(doc, indent=2))
    return doc, values


def track(timeline, bundles, actor, output, overrides=()):
    """Resolve a real native motion track, including direct motion and exposed defaults."""
    replacements={}
    for replacement in overrides:
        key,path=replacement.split('=',1)
        oa=Assets([path],profiles.load('gakumas')['unityVersion'])
        roots=[o for o in oa.of_type('MonoBehaviour') if 'baseAnimation' in o.read_typetree()]
        if len(roots)!=1:raise ValueError('override bundle must contain one MotionDefine')
        replacements[key]=(oa,roots[0])
    a=Assets([timeline,*bundles],profiles.load('gakumas')['unityVersion'])
    found=[]
    for o in a.of_type('MonoBehaviour'):
        t=o.read_typetree()
        if t.get('m_Name')==actor and 'm_Clips' in t: found.append((o,t))
    if len(found)!=1: raise ValueError(f'expected one {actor} track, found {len(found)}')
    obj,t=found[0];segments=[]
    for entry in t['m_Clips']:
        asset=a.deref(obj,entry['m_Asset'])
        if asset is None: raise ValueError('unresolved timeline clip asset')
        asset_t=asset.read_typetree()
        exposed=asset_t.get('exposedMotion',{}).get('exposedName','')
        owner,motion=replacements.get(exposed,(a,None))
        if motion is None:motion=a.deref(asset,asset_t.get('motion')) or a.deref(asset,asset_t.get('exposedMotion',{}).get('defaultValue'))
        if motion is None: raise ValueError('unresolved motion; supply its bundle closure (scene exposed overrides require explicit resolution)')
        mt=motion.read_typetree();base=mt['baseAnimation']
        clip=owner.deref(motion,base.get('clip'))
        if clip is None or base.get('customClip',{}).get('m_PathID'):raise ValueError('unsupported custom/unresolved clip')
        if mt.get('isAdditive') or base.get('mask',{}).get('m_PathID'):raise ValueError('TODO(qa-recon): additive/masked track flattening requires layer graph')
        ct=clip.read_typetree()
        # Easing and overlaps require the original layer mixer, not arbitrary linear blending.
        if any(entry.get(k,0)>0 for k in ('m_EaseInDuration','m_EaseOutDuration','m_BlendInDuration','m_BlendOutDuration')):
            raise ValueError('TODO(qa-recon): eased/blended segments require original layer mixer')
        segments.append(dict(clip=ct['m_Name'],start=entry['m_Start'],clipIn=entry['m_ClipIn'],duration=entry['m_Duration'],
            timeScale=entry['m_TimeScale'],loop=ct['m_MuscleClip']['m_LoopTime'],sourceMotion=mt['m_Name'],exposedName=exposed,overridden=exposed in replacements,
            preExtrapolation=entry['m_PreExtrapolationMode'],postExtrapolation=entry['m_PostExtrapolationMode']))
    segments.sort(key=lambda s:s['start'])
    if not segments:raise ValueError('empty track')
    for prev,nxt in zip(segments,segments[1:]):
        if abs(prev['start']+prev['duration']-nxt['start'])>1e-5:raise ValueError('gaps/overlaps need explicit native mixing policy')
    doc=dict(format='haruki-motion-track/1',source=timeline,actor=actor,segments=segments,
             duration=max(s['start']+s['duration'] for s in segments),timePolicy='local = clipIn + (timelineTime - start) * timeScale; loop from source flag, otherwise clamp')
    Path(output).write_text(json.dumps(doc,indent=2));print('track',actor,len(segments),'segments',doc['duration'],'seconds')


def flatten(track_file, mappings, prefix, rate):
    """Flatten already evaluated bone segments; their Unity flags and native jobs were applied before this step."""
    if rate<=0:raise ValueError('rate must be positive')
    doc=json.load(open(track_file))
    if doc.get('format')!='haruki-motion-track/1':raise ValueError('unsupported track version')
    sources={}
    for mapping in mappings:
        name,path=mapping.split('=',1);h=json.load(open(path+'.json'))
        if h['format'] not in ('haruki-pjsk-bone-curves/1','haruki-pjsk-bone-curves/2'):raise ValueError('flatten expects evaluated bone curves')
        if abs(h.get('sourceStartSeconds',0))>1e-6:raise ValueError('flatten requires full source bakes; apply clip-in in the track')
        width=4*len(h['bones'])+6+3*len(h.get('extraPositionBones',[]))
        a=np.fromfile(path+'.f32','<f4')
        if len(a)!=h['frames']*width:raise ValueError('bone payload size mismatch')
        sources[name]=(h,a.reshape(h['frames'],width))
    first=sources[doc['segments'][0]['clip']][0]
    n=int(np.ceil(doc['duration']*rate))+1; rows=[]
    for t in np.minimum(np.arange(n)/rate,doc['duration']):
        active=[s for s in doc['segments'] if s['start']-1e-8<=t<=s['start']+s['duration']+1e-8]
        if not active:raise ValueError(f'no segment at {t}')
        segment=active[-1];h,a=sources[segment['clip']]
        if h['bones']!=first['bones'] or h.get('extraPositionBones',[])!=first.get('extraPositionBones',[]):raise ValueError('incompatible segment skeletons')
        local=segment['clipIn']+(t-segment['start'])*segment['timeScale']
        length=h.get('duration',(h['frames']-1)/h['rate'])
        if segment['loop'] and length>0:local%=length
        else:local=np.clip(local,0,length)
        f=local*h['rate'];i=min(int(f),len(a)-1);j=min(i+1,len(a)-1);u=f-i
        row=a[i]*(1-u)+a[j]*u
        # Shortest-path slerp for each local quaternion; scalar components remain linear.
        for b in range(len(h['bones'])):
            q0=a[i,b*4:b*4+4].astype(float);q1=a[j,b*4:b*4+4].astype(float)
            dot=float(q0@q1)
            if dot<0:q1=-q1;dot=-dot
            theta=np.arccos(np.clip(dot,-1,1))
            q=q0*(1-u)+q1*u if theta<1e-5 else (q0*np.sin((1-u)*theta)+q1*np.sin(u*theta))/np.sin(theta)
            row[b*4:b*4+4]=q/np.linalg.norm(q)
        rows.append(row)
    output=np.array(rows,'<f4');output.tofile(prefix+'.f32')
    header={**first,'frames':n,'rate':rate,'duration':doc['duration'],'sourceTimeline':doc,'loop':False,'sourceStartSeconds':0}
    Path(prefix+'.json').write_text(json.dumps(header,indent=2));print('flattened',n,'frames',output.nbytes,'bytes')


def attach_template(template, prefix, include_props=False):
    """Copy native motion metadata and nonhuman channels, sampled at the converted motion's times."""
    path=Path(prefix+'.json');h=json.loads(path.read_text())
    a=Assets([template],profiles.load('gakumas')['unityVersion']);c=next(clips(a,lambda n:n.endswith('_b')))
    times=np.arange(h['frames'])/h['rate']+c.start
    if c.muscle_clip['m_LoopTime']:times=c.start+np.remainder(times-c.start,c.stop-c.start)
    else:times=np.minimum(times,c.stop)
    sidecar(a,c,prefix,h['rate'],times,include_props)
    h['templateSemanticsFile']=Path(prefix).name+'.semantics.json'
    h['clipSettings']=flags(c)
    h['clipSettings']['LoopTime']=h['loop']  # Converted source playback policy; original template flag remains in sidecar.
    h['templatePolicy']='nonhuman channels sampled at same seconds, loop or clamp using template flag; face/effects excluded unless optional props selected; no native object PPtr rebinding is claimed'
    path.write_text(json.dumps(h,indent=2))


def contacts(source, output, height_threshold, speed_threshold):
    """Opt-in contact inference; never presented as authored PJSK IK."""
    if height_threshold<=0 or speed_threshold<=0:raise ValueError('contact thresholds must be positive')
    h=json.load(open(source+'.json'))
    if h['format']!='haruki-external-motion/1' or h['floatsPerFrame']!=152:raise ValueError('expected external motion/1')
    a=np.fromfile(source+'.f32','<f4').reshape(h['frames'],152)
    feet=[a[:,i:i+3].astype(float)*h['sourceHumanScale']*h['characterHeight'] for i in (14,21)]
    floor=float(min(np.percentile(p[:,1],5) for p in feet))
    for foot,p in enumerate(feet):
        speed=np.linalg.norm(np.gradient(p,axis=0)*h['rate'],axis=1)
        w=np.clip(1-(p[:,1]-floor)/height_threshold,0,1)*np.clip(1-speed/speed_threshold,0,1)
        a[:,140+foot*3]=w;a[:,141+foot*3]=w
    a.tofile(output+'.f32')
    h['dataFile']=Path(output).name+'.f32'
    h['contactPolicy']=dict(kind='inferred approximation, opt-in',floorMeters=floor,heightThresholdMeters=height_threshold,
        speedThresholdMetersPerSecond=speed_threshold,formula='clamp01(1-height/heightThreshold)*clamp01(1-speed/speedThreshold)',
        consumerRequirement='supports source-avatar-root-local goal space and nonzero weights; base FK-only runtime rejects this variant')
    Path(output+'.json').write_text(json.dumps(h,indent=2))
    print('inferred weighted foot samples',int(np.count_nonzero(a[:,140])),int(np.count_nonzero(a[:,143])))
