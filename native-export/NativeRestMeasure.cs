using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using Object=UnityEngine.Object;
// Offline artifact measurement; never changes the exported bundles.
public static class NativeRestMeasure
{
 static Vector3[] Vertices(SkinnedMeshRenderer r){var mesh=r.sharedMesh;var vs=mesh.vertices;var ws=mesh.boneWeights;var poses=mesh.bindposes;var bones=r.bones;var output=new Vector3[vs.Length];for(int i=0;i<vs.Length;i++){var w=ws[i];int[] ids={w.boneIndex0,w.boneIndex1,w.boneIndex2,w.boneIndex3};float[] weights={w.weight0,w.weight1,w.weight2,w.weight3};for(int j=0;j<4;j++)if(weights[j]>0)output[i]+=weights[j]*bones[ids[j]].localToWorldMatrix.MultiplyPoint3x4(poses[ids[j]].MultiplyPoint3x4(vs[i]));}return output;}
 public static void Run(){try{
 var sourceBundle=AssetBundle.LoadFromFile("/work/motion-bake/task-L/actor-export/output/ichika.actor.bundle");var source=Object.Instantiate(sourceBundle.LoadAllAssets<GameObject>().Single());
 var targets=new List<SkinnedMeshRenderer>();foreach(var name in new[]{"mdl_chr_ttmr-cstm-0003_body","mdl_chr_ttmr-cstm-0003_hair","mdl_chr_ttmr-base-0000_face"}){var bundle=AssetBundle.LoadFromFile("/work/motion-bake/task-U/content-native/"+name+".unity3d");var part=Object.Instantiate(bundle.LoadAllAssets<GameObject>().Single());targets.AddRange(part.GetComponentsInChildren<SkinnedMeshRenderer>(true));}
 var rows=new JArray();double squared=0;float maximum=0;long count=0;
 foreach(var renderer in source.GetComponentsInChildren<SkinnedMeshRenderer>(true)){
 var name=renderer.name=="Face"?"Geo_Eye":"Geo_"+renderer.name;var target=targets.Single(r=>r.name==name);var before=Vertices(renderer);var after=Vertices(target);if(before.Length!=after.Length)throw new InvalidDataException(name+" vertex count differs");
 for(int i=0;i<before.Length;i++){float error=Vector3.Distance(before[i],after[i]);squared+=error*error;maximum=Mathf.Max(maximum,error);count++;rows.Add(new JObject{["mesh"]=name,["vertex"]=i,["metres"]=error});}
 }
 File.WriteAllText("/work/motion-bake/task-U/global-rest-error.json",new JObject{["vertices"]=count,["rmsMetres"]=Math.Sqrt(squared/count),["maxMetres"]=maximum,["perVertex"]=rows}.ToString());Debug.Log("U_GLOBAL_REST vertices="+count+" maximum="+maximum);EditorApplication.Exit(0);
 }catch(Exception e){Debug.LogException(e);EditorApplication.Exit(1);}}
}
