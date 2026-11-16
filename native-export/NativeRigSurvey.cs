using System;
using System.IO;
using System.Linq;
using ActorAnimation;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
public static class NativeRigSurvey {
 public static void Run() {
 try {
 var results=new JArray();
 foreach(var path in Directory.GetFiles("/work/gakumas/models/bundles", "mdl_chr_*.unity3d").Where(p=>p.Contains("_body.")||p.Contains("_hair.")).OrderBy(p=>p)) {
 var bundle=AssetBundle.LoadFromFile(path); if(!bundle)continue;
 foreach(var go in bundle.LoadAllAssets<GameObject>()) {
 var chains=new JArray();
 foreach(var chain in go.GetComponentsInChildren<ActorSwingChain>(true)) {
 var layers=new JArray();
 foreach(var layer in chain.chains.layers) layers.Add(new JObject { ["active"]=layer.active,["around"]=layer.around,["radius"]=layer.radius,["smoothing"]=layer.smoothing,["bones"]=new JArray((layer.bones ?? new System.Collections.Generic.List<ActorSwingDynamicBone>()).Select(b=>b?b.name:"NULL").ToArray()) });
 chains.Add(new JObject { ["name"]=chain.name,["roots"]=new JArray((chain.rootBones ?? new System.Collections.Generic.List<ActorSwingDynamicBone>()).Select(b=>b?b.name:"NULL").ToArray()),["layers"]=layers });
 }
 var bones=new JArray();
 foreach(var b in go.GetComponentsInChildren<ActorSwingDynamicBone>(true)) bones.Add(new JObject { ["name"]=b.name,["parent"]=b.transform.parent?b.transform.parent.name:"",["position"]=JToken.FromObject(new[]{b.transform.position.x,b.transform.position.y,b.transform.position.z}),["localPosition"]=JToken.FromObject(new[]{b.transform.localPosition.x,b.transform.localPosition.y,b.transform.localPosition.z}),["settings"]=JObject.Parse(JsonUtility.ToJson(b)) });
 var colliders=new JArray(); foreach(var b in go.GetComponentsInChildren<ActorSwingStaticBone>(true))colliders.Add(new JObject{["name"]=b.name,["settings"]=JObject.Parse(JsonUtility.ToJson(b))});
 var quartz=new JArray(); foreach(var b in go.GetComponentsInChildren<MonoBehaviour>(true).Where(b=>b && b.GetType().Name.Contains("Quartz")))quartz.Add(new JObject{["name"]=b.name,["type"]=b.GetType().FullName,["settings"]=JObject.Parse(JsonUtility.ToJson(b))});
 results.Add(new JObject{["bundle"]=path,["prefab"]=go.name,["chains"]=chains,["bones"]=bones,["colliders"]=colliders,["quartz"]=quartz});
 }
 bundle.Unload(true);
 }
 File.WriteAllText("/work/motion-bake/task-U/survey/native-rigs.json",results.ToString());
 Debug.Log("U_SURVEY prefabs="+results.Count); EditorApplication.Exit(0);
 }catch(Exception e){Debug.LogException(e);EditorApplication.Exit(1);}
 }
}
