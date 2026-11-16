using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;

public static partial class HumanoidBake
{
    [Serializable] private class AssistModel { public string format; public AssistRecord[] fits; }
    [Serializable] private class AssistRecord { public string bone; public string[] drivers; public int featureCount; public float[] coefficients; }
    private sealed class AssistFit
    {
        private readonly AssistModel model;
        private readonly Rig rig;
        private readonly Dictionary<string,BoneJson> rest;
        public Transform[] Bones {get;}
        public AssistFit(string file,Rig rig,SkeletonJson skeleton)
        {
            this.rig=rig;rest=skeleton.bones.ToDictionary(b=>b.name);
            model=JsonUtility.FromJson<AssistModel>(File.ReadAllText(file));
            if(model.format!="haruki-pjsk-assist-fit/1")throw new Exception("unknown assist model version");
            Bones=model.fits.Select(f=>rig.byName[f.bone]).ToArray();
            foreach(var fit in model.fits)if(fit.coefficients.Length!=6*fit.featureCount)throw new Exception("invalid assist coefficient count");
        }
        private Quaternion RestQ(string name){var r=rest[name].rotation;return new Quaternion(r[0],r[1],r[2],r[3]);}
        private static Vector3 LogQ(Quaternion q)
        {
            q=Normalize(q);if(q.w<0)q=new Quaternion(-q.x,-q.y,-q.z,-q.w);
            var v=new Vector3(q.x,q.y,q.z);float n=v.magnitude;
            return n>1e-8f?v*(2*Mathf.Atan2(n,q.w)/n):v*2;
        }
        public void Apply()
        {
            foreach(var fit in model.fits)
            {
                var values=new List<float>();
                foreach(string driver in fit.drivers){var v=LogQ(Quaternion.Inverse(RestQ(driver))*rig.byName[driver].localRotation);values.Add(v.x);values.Add(v.y);values.Add(v.z);}
                var features=new List<float>{1};features.AddRange(values);
                for(int i=0;i<values.Count;i++)for(int j=i;j<values.Count;j++)features.Add(values[i]*values[j]);
                if(features.Count!=fit.featureCount)throw new Exception("assist feature count mismatch");
                var y=new float[6];
                for(int i=0;i<6;i++)for(int j=0;j<features.Count;j++)y[i]+=fit.coefficients[i*features.Count+j]*features[j];
                var t=rig.byName[fit.bone];var p=rest[fit.bone].position;
                t.localPosition=new Vector3(p[0]+y[0],p[1]+y[1],p[2]+y[2]);
                var rv=new Vector3(y[3],y[4],y[5]);
                t.localRotation=RestQ(fit.bone)*Quaternion.AngleAxis(rv.magnitude*Mathf.Rad2Deg,rv.normalized);
            }
        }
    }
}
