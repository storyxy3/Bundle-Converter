"""Measure an explicitly approximate assist-bone fit; report held-out motions, never label it original code."""
import json
from pathlib import Path
import numpy as np
from ..unity_assets import Assets
from ..unity_clip import clips
from ..motion import paths
from .pjsk_twist import euler_to_q, qmul, qinv


def rotation_vector(q):
    q = q / np.linalg.norm(q)
    if q[3] < 0: q = -q
    n = np.linalg.norm(q[:3])
    return q[:3] * (2*np.arctan2(n,q[3])/n) if n > 1e-8 else q[:3]*2


def features(v):
    return [1, *v, *(v[i]*v[j] for i in range(len(v)) for j in range(i,len(v)))]


def run(skeleton, bundles, output):
    sk=json.load(open(skeleton)); bones={b['name']:b for b in sk['bones']}; p=dict(zip(bones,paths(sk)))
    records=[]
    for side in ('Left','Right'):
        for suffix,drivers in (('AssistHip',[side+'_Thigh']),('Pectoralis_01',[side+'_Shoulder',side+'_Arm'])):
            records.append(dict(bone=side+'_'+suffix,drivers=drivers,X=[],Y=[],groups=[]))
    names=[]
    for group,bundle in enumerate(bundles):
        a=Assets([bundle],'2022.3.62f2')
        for c in clips(a,lambda n:n.startswith('motion_')):
            names.append(c.name)
            def q(name,t):
                ci=c.transform(p[name],'rotation'); ei=c.transform(p[name],'euler')
                return np.array([c.sample(ci+k,t) for k in range(4)]) if ci is not None else euler_to_q([c.sample(ei+k,t) for k in range(3)]) if ei is not None else np.array(bones[name]['rotation'])
            for t in np.arange(c.start,c.stop,1/15):
                for r in records:
                    b=bones[r['bone']]; ci=c.transform(p[r['bone']],'position')
                    v=np.concatenate([rotation_vector(qmul(qinv(bones[d]['rotation']),q(d,t))) for d in r['drivers']])
                    pos=np.array([c.sample(ci+k,t) for k in range(3)]) if ci is not None else np.array(b['position'])
                    r['X'].append(features(v)); r['Y'].append([*(pos-b['position']),*rotation_vector(qmul(qinv(b['rotation']),q(r['bone'],t)))]); r['groups'].append(group)
    for r in records:
        X=np.array(r.pop('X'));Y=np.array(r.pop('Y')); groups=np.array(r.pop('groups'))
        # Last bundle is held out, rather than reporting only training residuals.
        train=groups<len(bundles)-1
        coef=np.linalg.lstsq(X[train],Y[train],rcond=None)[0]
        err=X[~train]@coef-Y[~train]
        r['heldOutSamples']=int(sum(~train));r['positionRMSE']=float(np.sqrt(np.mean(np.sum(err[:,:3]**2,axis=1))))
        r['rotationVectorRMSEDeg']=float(np.degrees(np.sqrt(np.mean(np.sum(err[:,3:]**2,axis=1)))))
        r['coefficients']=coef.T.flatten().tolist();r['featureCount']=len(coef)
        print(r['bone'],'position RMSE',r['positionRMSE'],'rotation RMSE deg',r['rotationVectorRMSEDeg'])
    Path(output).write_text(json.dumps(dict(format='haruki-pjsk-assist-fit/1',kind='measured approximation, not reconstructed authoring algorithm',
        sources=bundles,motions=names,rate=15,featureOrder='1, driver rest-relative rotation vectors xyz in radians, quadratic products i<=j',
        outputOrder='position delta xyz, rest-relative rotation vector xyz; coefficients output-major',fits=records),indent=2))
