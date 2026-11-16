using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using ActorAnimation;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using Object=UnityEngine.Object;
public static class MikuPrepare
{
 public static void Run(){try{Export();EditorApplication.Exit(0);}catch(Exception e){Debug.LogException(e);EditorApplication.Exit(1);}}
 static void Export(){
 var source=JObject.Parse(File.ReadAllText("/work/motion-bake/task-U/miku/source.json"));
 var actor=new GameObject("Miku21");var aliases=new Dictionary<Transform,string>();
 foreach(var part in source["parts"]){
  var bundle=AssetBundle.LoadFromFile((string)part["source"]);var sourcePrefab=bundle.LoadAllAssets<GameObject>().First();var go=Object.Instantiate(sourcePrefab);go.transform.SetParent(actor.transform,false);go.transform.localScale=Vector3.one;
  var transforms=go.GetComponentsInChildren<Transform>(true);var nodes=part["nodes"].ToDictionary(n=>(string)n["go"]);
  foreach(var skin in go.GetComponentsInChildren<SkinnedMeshRenderer>(true)){skin.sharedMesh=Object.Instantiate(skin.sharedMesh);AssetDatabase.CreateAsset(skin.sharedMesh,"Assets/NativeActor/Miku"+part["label"]+skin.name+".asset");}
  foreach(var physics in part["physics"].Where(p=>((string)p["type"]).Contains("SpringBone"))){
   string name=(string)nodes[(string)physics["go"]]["name"];var transform=transforms.FirstOrDefault(t=>t.name==name);if(!transform||transform.GetComponent<ActorSwingDynamicBone>())continue;
   var b=transform.gameObject.AddComponent<ActorSwingDynamicBone>();b.modelingTransform=new InitialTransform{localPosition=transform.localPosition,localRotation=transform.localRotation};aliases[transform]=name;
  }
  foreach(var component in go.GetComponentsInChildren<Component>(true))if(component is UnityEngine.Animations.IConstraint)Object.DestroyImmediate(component);
  foreach(var t in transforms)GameObjectUtility.RemoveMonoBehavioursWithMissingScript(t.gameObject);
 }

 var skins=actor.GetComponentsInChildren<SkinnedMeshRenderer>(true);
 var body=skins.First(r=>r.name.ToLowerInvariant().Contains("body"));var face=skins.First(r=>r!=body);body.name="Body";face.name="Face";
 Transform Find(Transform root,string name)=>root.GetComponentsInChildren<Transform>(true).First(t=>t.name==name);
 var bodyNeck=Find(body.rootBone,"Neck");var bodyHead=Find(body.rootBone,"Head");var faceNeck=Find(face.rootBone,"Neck");var faceHead=Find(face.rootBone,"Head");
 foreach(var child in bodyHead.Cast<Transform>().ToArray())child.SetParent(faceHead,true);
 foreach(var child in faceNeck.Cast<Transform>().Where(t=>t.name.EndsWith("_target")).ToArray())child.SetParent(bodyNeck.parent,true);
 face.transform.SetParent(body.transform.parent,false);faceNeck.SetParent(bodyNeck.parent,false);
 faceNeck.localPosition=bodyNeck.localPosition;faceNeck.localRotation=bodyNeck.localRotation;faceNeck.localScale=bodyNeck.localScale;faceHead.localPosition=bodyHead.localPosition;faceHead.localRotation=bodyHead.localRotation;faceHead.localScale=bodyHead.localScale;
 body.bones=body.bones.Select(t=>t==bodyNeck?faceNeck:t==bodyHead?faceHead:t).ToArray();Object.DestroyImmediate(bodyHead.gameObject);Object.DestroyImmediate(bodyNeck.gameObject);face.rootBone=body.rootBone;
 var bodyNames=body.bones.Where(t=>t).GroupBy(t=>t.name).ToDictionary(g=>g.Key,g=>g.First());
 var faceBound=face.bones;var facePoses=face.sharedMesh.bindposes;
 for(int i=0;i<faceBound.Length;i++)if(faceBound[i] && faceBound[i]!=faceNeck && faceBound[i]!=faceHead && bodyNames.TryGetValue(faceBound[i].name,out var target) && target!=faceBound[i]){facePoses[i]=target.worldToLocalMatrix*faceBound[i].localToWorldMatrix*facePoses[i];faceBound[i]=target;}
 face.bones=faceBound;face.sharedMesh.bindposes=facePoses;
 foreach(var boneName in new[]{"Hip","Waist","Spine","Chest"})foreach(var extra in actor.GetComponentsInChildren<Transform>(true).Where(t=>t.name==boneName && bodyNames.ContainsKey(boneName) && t!=bodyNames[boneName]).ToArray())extra.name="UnusedFace"+boneName;
 var position=Find(actor.transform,"Position");position.localScale=Vector3.one*(float)source["characterHeight"];
 // Separate hair triangles using secondary hair skin influences; leave face triangles on the face renderer.
 var original=face.sharedMesh;var hairMesh=Object.Instantiate(original);hairMesh.name="MikuHair";var weights=original.boneWeights;var bounds=face.bones;
 bool Hair(int i){var w=weights[i];int[] ids={w.boneIndex0,w.boneIndex1,w.boneIndex2,w.boneIndex3};float[] ws={w.weight0,w.weight1,w.weight2,w.weight3};float total=0;for(int j=0;j<4;j++)if(ws[j]>0&&bounds[ids[j]].name.ToLowerInvariant().Contains("hair"))total+=ws[j];return total>.1f;}
 for(int sub=0;sub<original.subMeshCount;sub++){var triangles=original.GetTriangles(sub);var hair=new List<int>();var facial=new List<int>();for(int i=0;i<triangles.Length;i+=3){var selected=Hair(triangles[i])||Hair(triangles[i+1])||Hair(triangles[i+2])?hair:facial;selected.Add(triangles[i]);selected.Add(triangles[i+1]);selected.Add(triangles[i+2]);}hairMesh.SetTriangles(hair,sub);original.SetTriangles(facial,sub);}
 AssetDatabase.CreateAsset(hairMesh,"Assets/NativeActor/MikuHairSeparated.asset");var hairRenderer=new GameObject("Hair").AddComponent<SkinnedMeshRenderer>();hairRenderer.transform.SetParent(face.transform.parent,false);hairRenderer.transform.localPosition=face.transform.localPosition;hairRenderer.transform.localRotation=face.transform.localRotation;hairRenderer.transform.localScale=face.transform.localScale;hairRenderer.bones=face.bones;hairRenderer.rootBone=face.rootBone;hairRenderer.sharedMesh=hairMesh;hairRenderer.sharedMaterials=face.sharedMaterials;
 foreach(var t in actor.GetComponentsInChildren<Transform>(true))GameObjectUtility.RemoveMonoBehavioursWithMissingScript(t.gameObject);
 var templatesBundle=AssetBundle.LoadFromFile("/work/gakumas/live-urp-ext/.recon/task-O/actor/ichika.swing.bundle");
 var templatesActor=templatesBundle.LoadAllAssets<GameObject>().Single();var templates=templatesActor.GetComponentsInChildren<SkinnedMeshRenderer>(true);
 var materialRecords=new JArray();
 foreach(var renderer in actor.GetComponentsInChildren<SkinnedMeshRenderer>(true)){
  var template=templates.First(t=>t.name=="Body").sharedMaterials[0];
  var nativeMaterials=new List<Material>();int index=0;
  foreach(var material in renderer.sharedMaterials){
   var converted=Object.Instantiate(template);converted.name="Miku"+renderer.name+index;
   foreach(var property in converted.GetTexturePropertyNames()){var texture=converted.GetTexture(property);if(texture){var clone=Object.Instantiate(texture);clone.name=converted.name+property;AssetDatabase.CreateAsset(clone,"Assets/NativeActor/"+clone.name+".asset");converted.SetTexture(property,clone);}}
   var main=material.GetTexture("_MainTex");if(main){var clone=Object.Instantiate(main);clone.name=converted.name+"Base";AssetDatabase.CreateAsset(clone,"Assets/NativeActor/"+clone.name+".asset");converted.SetTexture("_BaseMap",clone);}
   materialRecords.Add(new JObject{["name"]=converted.name,["keywords"]=new JArray(converted.shaderKeywords),["renderQueue"]=converted.renderQueue,["textures"]=new JArray()});
   converted.shader=AssetDatabase.LoadAssetAtPath<Shader>("Assets/NativeActorSerialization.shader");AssetDatabase.CreateAsset(converted,"Assets/NativeActor/"+converted.name+".mat");nativeMaterials.Add(converted);index++;
  }
  renderer.sharedMaterials=nativeMaterials.ToArray();
 }
 File.WriteAllText("/work/motion-bake/task-U/miku/materials.json",new JObject{["materials"]=materialRecords}.ToString());
 var path="Assets/NativeActor/MikuPrepared.prefab";PrefabUtility.SaveAsPrefabAsset(actor,path);AssetDatabase.SaveAssets();Directory.CreateDirectory("/work/motion-bake/task-U/miku/prepared");
 BuildPipeline.BuildAssetBundles("/work/motion-bake/task-U/miku/prepared",new[]{new AssetBundleBuild{assetBundleName="miku.bundle",assetNames=new[]{path}}},BuildAssetBundleOptions.ChunkBasedCompression,BuildTarget.StandaloneLinux64);Debug.Log("U_MIKU_PREPARED");
 }
}
