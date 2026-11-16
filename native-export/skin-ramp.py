# Offline authoring policy: preserve the character's source shadow/base ratio in a native RGBA ramp.
import numpy as np
from PIL import Image

def linear(x):
 x=np.asarray(x,dtype=float)/255
 return np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)

def encode(x):
 x=np.clip(x,0,1)
 return np.rint(255*np.where(x<=.0031308,x*12.92,1.055*x**(1/2.4)-.055)).astype('uint8')

def source_ratio(base,shade):
 b=np.asarray(base.convert('RGBA'));s=np.asarray(shade.convert('RGBA').resize(base.size))
 # The old models can lack a ValueTex skin bit; use the same documented pale/warm inference as V.
 mask=(b[:,:,0]>b[:,:,1]*1.02)&(b[:,:,0]>b[:,:,2]*1.01)&(b[:,:,:3].min(2)>120)
 if not mask.any():raise ValueError('No source skin samples for shadow tint')
 ratio=np.median(linear(s[:,:,:3][mask])/np.maximum(linear(b[:,:,:3][mask]),1e-6),axis=0)
 return np.clip(ratio,0,1),{'samples':int(mask.sum()),'linearShadowBaseRatio':ratio.tolist(),'baseMedian':np.median(b[:,:,:3][mask],0).tolist(),'shadowMedian':np.median(s[:,:,:3][mask],0).tolist()}

def faithful(ramp,ratio):
 a=np.array(ramp.convert('RGBA'));curve=a[:,:,3].astype(float)/255
 # Keep every native alpha texel. RGB is white at the lit endpoint and source tint at the dark endpoint.
 a[:,:,:3]=encode(1-curve[:,:,None]*(1-np.asarray(ratio)))
 return Image.fromarray(a)
