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

# Optional authoring policy, not reconstructed game behavior: match native skin L/C while keeping source Lab hue.
def native_base(base,reference,reference_mask):
 b=np.array(base.convert('RGBA'));rgb=b[:,:,:3].astype(float)
 skin=(rgb[:,:,0]>rgb[:,:,1]*1.02)&(rgb[:,:,0]>rgb[:,:,2]*1.01)&(rgb.min(2)>120)
 if not skin.any():return base,{'samples':0}
 def lab(a):
  xyz=linear(a)@np.array([[.4124564,.2126729,.0193339],[.3575761,.7151522,.1191920],[.1804375,.0721750,.9503041]])/np.array([.95047,1,1.08883]);f=np.where(xyz>(6/29)**3,np.cbrt(xyz),xyz/(3*(6/29)**2)+4/29)
  return np.stack((116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])),-1)
 src=lab(rgb[skin]);native=lab(np.array(reference.convert('RGB'))[reference_mask]);origin=np.median(src,0);target=np.median(native,0)
 # One common native body-skin reference avoids separate face/body palettes. L detail and hue remain source-authored.
 shift=target[0]-origin[0];scale=np.linalg.norm(target[1:])/max(np.linalg.norm(origin[1:]),1e-6)
 adjusted=src.copy();adjusted[:,0]+=shift;adjusted[:,1:]*=scale
 fy=(adjusted[:,0]+16)/116;f=np.stack((fy+adjusted[:,1]/500,fy,fy-adjusted[:,2]/200),-1)
 xyz=np.where(f>6/29,f**3,3*(6/29)**2*(f-4/29))*[.95047,1,1.08883]
 rgb_linear=xyz@np.linalg.inv(np.array([[.4124564,.2126729,.0193339],[.3575761,.7151522,.1191920],[.1804375,.0721750,.9503041]]))
 b[:,:,:3][skin]=encode(rgb_linear)
 return Image.fromarray(b),{'samples':int(skin.sum()),'sourceMedianLab':origin.tolist(),'nativeBodyMedianLab':target.tolist(),'LShift':float(shift),'chromaScale':float(scale),'huePolicy':'Lab a/b common scale; sRGB gamut clipping/rounding can alter final hue'}
