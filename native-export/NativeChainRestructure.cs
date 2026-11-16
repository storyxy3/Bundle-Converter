using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using ActorAnimation;
using Newtonsoft.Json.Linq;
using UnityEngine;
using Object=UnityEngine.Object;

// Offline authoring: native components and standard skin weights only.
public static class NativeChainRestructure
{
    const string Output="/work/motion-bake/task-U";
    static string Category(string n) {n=n.ToLowerInvariant();return n.Contains("skirt")?"skirt":n.Contains("hair")?(n.Contains("front")?"front-hair":n.Contains("side")?"side-hair":"back-hair"):"accessory";}
    public static void Apply(GameObject actor, Dictionary<Transform,string> aliases)
    {
        var presets=JArray.Parse(File.ReadAllText(Output+"/survey/presets.json"));
        var skins=actor.GetComponentsInChildren<SkinnedMeshRenderer>(true);
        var nativeHairBundle=AssetBundle.LoadFromFile("/work/gakumas/live-urp-ext/Build/Content-Linux/ttmr001/mdl_chr_ttmr-cstm-0003_hair.unity3d");
        var nativeHair=nativeHairBundle.LoadAllAssets<GameObject>().Single();var hairDrivers=nativeHair.GetComponentsInChildren<ActorAnimationQuartzDriverHairBone>(true);
        var nativeHairHead=nativeHair.GetComponentsInChildren<Transform>(true).First(t=>t.name=="Head_Hair");
        var roots=actor.GetComponentsInChildren<ActorSwingDynamicBone>(true).Where(b=>!b.transform.parent.GetComponent<ActorSwingDynamicBone>()).ToArray();
        var report=new JArray();var skirts=new List<ActorSwingDynamicBone[]>();JToken skirtPreset=null;
        foreach(var root in roots)
        {
            if(!root)continue;
            var old=root.GetComponentsInChildren<ActorSwingDynamicBone>(true);var members=new HashSet<Transform>(old.Select(b=>b.transform));
            var origin=root.transform.position;var points=new List<Vector3>();
            foreach(var r in skins) {var vs=r.sharedMesh.vertices;var ws=r.sharedMesh.boneWeights;for(int i=0;i<vs.Length;i++){var w=ws[i];float weight=0;int[] ids={w.boneIndex0,w.boneIndex1,w.boneIndex2,w.boneIndex3};float[] weights={w.weight0,w.weight1,w.weight2,w.weight3};for(int j=0;j<4;j++)if(weights[j]>0&&members.Contains(r.bones[ids[j]]))weight+=weights[j];if(weight>.05f)points.Add(r.bones[ids[0]].localToWorldMatrix.MultiplyPoint3x4(r.sharedMesh.bindposes[ids[0]].MultiplyPoint3x4(vs[i])));}}
            if(points.Count<3)continue;
            // Principal axis of affected vertices, oriented away from the chain anchor.
            var mean=points.Aggregate(Vector3.zero,(a,b)=>a+b)/points.Count;var direction=(mean-origin).normalized;
            for(int k=0;k<16;k++){Vector3 v=Vector3.zero;foreach(var p in points){var q=p-mean;v+=q*Vector3.Dot(q,direction);}if(v.sqrMagnitude>1e-12f)direction=v.normalized;}
            if(Vector3.Dot(direction,mean-origin)<0)direction=-direction;
            float length=points.Max(p=>Vector3.Dot(p-origin,direction));if(length<.005f)continue;
            string category=Category(root.name);
            if(category.Contains("hair")){
                var head=actor.GetComponentsInChildren<Transform>(true).FirstOrDefault(t=>t.name=="Head");
                if(head){var relative=head.InverseTransformPoint(mean);category=relative.z>0?"front-hair":Mathf.Abs(relative.x)>.07f?"side-hair":"back-hair";}
            }
            var preset=presets.Where(p=>(string)p["category"]==category&&(float)p["length"]>.005f && ((JArray)p["names"]).Count>=2).OrderBy(p=>Mathf.Abs(Mathf.Log(length/(float)p["length"]))).First();
            var chainParent=root.transform.parent;
            if(category=="skirt"){var drivers=actor.GetComponentsInChildren<ActorAnimationQuartzDriverSkirtBone>(true);if(drivers.Length>0)chainParent=drivers.OrderBy(d=>(d.transform.position-origin).sqrMagnitude).First().transform;}
            if(category=="back-hair" || category=="side-hair"){
                var head=actor.GetComponentsInChildren<Transform>(true).FirstOrDefault(t=>t.name=="Head");
                if(head && hairDrivers.Length>0){
                    var local=head.InverseTransformPoint(origin);var donor=hairDrivers.OrderBy(d=>(nativeHairHead.InverseTransformPoint(d.transform.position)-local).sqrMagnitude).First();
                    var anchor=new GameObject("NativeHairQuartz_"+root.name+"_A").transform;anchor.SetParent(head,false);anchor.position=origin;anchor.rotation=root.transform.rotation;
                    var driver=anchor.gameObject.AddComponent<ActorAnimationQuartzDriverHairBone>();driver.setting=JsonUtility.FromJson<ActorAnimationQuartzDriverHairSetting>(JsonUtility.ToJson(donor.setting));
                    // Native hair authoring uses null head/neck references; the builder supplies the actor's bones.
                    driver.setting.referenceHeadBone=null;driver.setting.referenceNeckBone=null;chainParent=anchor;
                }
            }
            int count=((JArray)preset["names"]).Count;var nodes=new ActorSwingDynamicBone[count];float nativeLength=(float)preset["length"];float distance=0;
            for(int k=0;k<count;k++) {
                if(k>0)distance+=(float)preset["spacing"][k-1];
                var t=new GameObject(root.name+"_U"+k+"_S").transform;t.SetParent(k==0?chainParent:nodes[k-1].transform,true);t.position=origin+direction*(distance/nativeLength*length);t.rotation=root.transform.rotation;
                var bone=t.gameObject.AddComponent<ActorSwingDynamicBone>();JsonUtility.FromJsonOverwrite(preset["settings"][k].ToString(),bone);
                bone.referenceLimitInfo=new ReferenceLimitInfo();bone.modelingTransform=new InitialTransform{localPosition=t.localPosition,localRotation=t.localRotation};nodes[k]=bone;aliases[t]=category.Contains("hair")?"hair_"+t.name:t.name;
            }
            double squared=0;float maximum=0;long vertices=0;var errors=new JArray();
            foreach(var r in skins) {
                var mesh=r.sharedMesh;var weights=mesh.boneWeights;var vs=mesh.vertices;var bound=r.bones.ToList();var poses=mesh.bindposes.ToList();int offset=bound.Count;
                int sourceIndex=bound.FindIndex(t=>members.Contains(t));
                if(sourceIndex<0)continue;
                var restMatrix=bound[sourceIndex].localToWorldMatrix*poses[sourceIndex];
                foreach(var node in nodes){bound.Add(node.transform);poses.Add(node.transform.worldToLocalMatrix*restMatrix);}
                for(int i=0;i<vs.Length;i++) {
                    var w=weights[i];int[] ids={w.boneIndex0,w.boneIndex1,w.boneIndex2,w.boneIndex3};float[] ws={w.weight0,w.weight1,w.weight2,w.weight3};float total=0;var result=new Dictionary<int,float>();Vector3 before=Vector3.zero;
                    for(int j=0;j<4;j++)if(ws[j]>0){before+=ws[j]*bound[ids[j]].localToWorldMatrix.MultiplyPoint3x4(poses[ids[j]].MultiplyPoint3x4(vs[i]));if(members.Contains(bound[ids[j]]))total+=ws[j];else {if(!result.ContainsKey(ids[j]))result[ids[j]]=0;result[ids[j]]+=ws[j];}}
                    if(total==0)continue;
                    float along=Mathf.Clamp01(Vector3.Dot(restMatrix.MultiplyPoint3x4(vs[i])-origin,direction)/length)*(count-1);int lo=Mathf.Min(count-2,Mathf.FloorToInt(along));float f=along-lo;result[offset+lo]=total*(1-f);result[offset+lo+1]=total*f;
                    var ranked=result.Where(p=>p.Value>0).OrderByDescending(p=>p.Value).Take(4).ToArray();float sum=ranked.Sum(p=>p.Value);int[] ni=new int[4];float[] nw=new float[4];Vector3 after=Vector3.zero;
                    for(int j=0;j<ranked.Length;j++){ni[j]=ranked[j].Key;nw[j]=ranked[j].Value/sum;after+=nw[j]*bound[ni[j]].localToWorldMatrix.MultiplyPoint3x4(poses[ni[j]].MultiplyPoint3x4(vs[i]));}
                    weights[i]=new BoneWeight{boneIndex0=ni[0],boneIndex1=ni[1],boneIndex2=ni[2],boneIndex3=ni[3],weight0=nw[0],weight1=nw[1],weight2=nw[2],weight3=nw[3]};float error=Vector3.Distance(before,after);squared+=error*error;maximum=Mathf.Max(maximum,error);vertices++;errors.Add(new JObject{["mesh"]=mesh.name,["vertex"]=i,["metres"]=error});
                }
                mesh.bindposes=poses.ToArray();mesh.boneWeights=weights;r.bones=bound.ToArray();UnityEditor.EditorUtility.SetDirty(mesh);
            }
            foreach(var bone in old)Object.DestroyImmediate(bone);
            if(category=="skirt"){
                var anchors=actor.GetComponentsInChildren<ActorAnimationQuartzDriverSkirtBone>(true);
                if(anchors.Length>0){var anchor=anchors.OrderBy(a=>(a.transform.position-origin).sqrMagnitude).First();nodes[0].transform.SetParent(anchor.transform,true);nodes[0].modelingTransform=new InitialTransform{localPosition=nodes[0].transform.localPosition,localRotation=nodes[0].transform.localRotation};}
                skirts.Add(nodes);skirtPreset=preset;
            }
            report.Add(new JObject{["root"]=root?root.name:nodes[0].name,["category"]=category,["sourceBones"]=old.Length,["nodes"]=count,["length"]=length,["presetBundle"]=preset["bundle"],["presetRoot"]=preset["root"],["vertices"]=vertices,["restRms"]=vertices>0?Math.Sqrt(squared/vertices):0,["restMax"]=maximum,["perVertexRestError"]=errors});
        }
        // Surface constraints follow serialized native layer flags and angular ordering.
        if(skirts.Count>1) {
            skirts=skirts.OrderBy(c=>Mathf.Atan2(c[0].transform.position.x,c[0].transform.position.z)).ToList();
            int depth=skirts.Min(c=>c.Length);var chain=actor.AddComponent<ActorSwingChain>();foreach(var column in skirts)chain.rootBones.Add(column[0]);
            for(int k=0;k<depth;k++){var p=skirtPreset["layers"][Math.Min(k,((JArray)skirtPreset["layers"]).Count-1)];var layer=new ChainLayerInfo{active=(bool)p["active"],around=(bool)p["around"],radius=(float)p["radius"],smoothing=(float)p["smoothing"]};foreach(var column in skirts)layer.bones.Add(column[k]);chain.chains.layers.Add(layer);}
        }
        // Fit the existing native capsule orientation and collision masks to body skin vertices.
        var fits=new JArray();
        foreach(var collider in actor.GetComponentsInChildren<ActorSwingStaticBone>(true)){
            var shape=collider.staticCollider;if(shape==null||shape.type!=ActorSwingColliderType.Capsule)continue;
            var samples=new List<Vector3>();
            foreach(var skin in skins.Where(r=>r.name.ToLowerInvariant().Contains("body"))){
                var verts=skin.sharedMesh.vertices;var weights=skin.sharedMesh.boneWeights;var bound=skin.bones;var poses=skin.sharedMesh.bindposes;
                for(int i=0;i<verts.Length;i++){
                    var w=weights[i];int[] ids={w.boneIndex0,w.boneIndex1,w.boneIndex2,w.boneIndex3};float[] ws={w.weight0,w.weight1,w.weight2,w.weight3};float influence=0;Vector3 position=Vector3.zero;
                    for(int j=0;j<4;j++)if(ws[j]>0){if(bound[ids[j]]==collider.transform)influence+=ws[j];position+=ws[j]*bound[ids[j]].localToWorldMatrix.MultiplyPoint3x4(poses[ids[j]].MultiplyPoint3x4(verts[i]));}
                    if(influence>.5f)samples.Add(collider.transform.InverseTransformPoint(position));
                }
            }
            if(samples.Count<8)continue;
            int axis=(int)shape.vector3_B.x;var center=samples.Aggregate(Vector3.zero,(a,b)=>a+b)/samples.Count;
            var radialList=new List<float>();foreach(var sample in samples){var delta=sample-center;delta[axis]=0;radialList.Add(delta.magnitude);}radialList.Sort();var radial=radialList.ToArray();
            float radius=radial[(int)(.9f*(radial.Length-1))];float span=samples.Max(v=>v[axis])-samples.Min(v=>v[axis]);
            shape.vector3_A=center;shape.float_A=shape.float_B=radius;shape.vector3_B=new Vector3(axis,Mathf.Max(span,2*radius),shape.vector3_B.z);
            fits.Add(new JObject{["bone"]=collider.name,["vertices"]=samples.Count,["radius"]=radius,["height"]=shape.vector3_B.y});
        }
        var reportDirectory=Environment.GetEnvironmentVariable("U_REPORT_DIR") ?? Output;Directory.CreateDirectory(reportDirectory);
        File.WriteAllText(reportDirectory+"/collider-fit.json",fits.ToString());
        File.WriteAllText(reportDirectory+"/restructure.json",report.ToString());
    }
}
