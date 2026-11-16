using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using ActorAnimation;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using Object=UnityEngine.Object;
public static class MikuRestructure
{
 public static void Run(){try{Export();EditorApplication.Exit(0);}catch(Exception e){Debug.LogException(e);EditorApplication.Exit(1);}}
 static void Export(){
 var source=JObject.Parse(File.ReadAllText("/work/motion-bake/task-U/miku/source.json"));
 var actor=new GameObject("Miku21");var aliases=new Dictionary<Transform,string>();
 foreach(var part in source["parts"]){
  var bundle=AssetBundle.LoadFromFile((string)part["source"]);var original=bundle.LoadAllAssets<GameObject>().First();var go=Object.Instantiate(original);go.transform.SetParent(actor.transform,false);go.transform.localScale=Vector3.one*1.58f;
  var transforms=go.GetComponentsInChildren<Transform>(true);var nodes=part["nodes"].ToDictionary(n=>(string)n["go"]);
  foreach(var skin in go.GetComponentsInChildren<SkinnedMeshRenderer>(true)){skin.sharedMesh=Object.Instantiate(skin.sharedMesh);AssetDatabase.CreateAsset(skin.sharedMesh,"Assets/NativeActor/Miku"+part["label"]+skin.name+".asset");}
  foreach(var physics in part["physics"].Where(p=>((string)p["type"]).Contains("SpringBone"))){
   string name=(string)nodes[(string)physics["go"]]["name"];var transform=transforms.FirstOrDefault(t=>t.name==name);if(!transform||transform.GetComponent<ActorSwingDynamicBone>())continue;
   var b=transform.gameObject.AddComponent<ActorSwingDynamicBone>();b.modelingTransform=new InitialTransform{localPosition=transform.localPosition,localRotation=transform.localRotation};aliases[transform]=name;
  }
  foreach(var component in go.GetComponentsInChildren<Component>(true))if(component is UnityEngine.Animations.IConstraint)Object.DestroyImmediate(component);
  foreach(var t in transforms)GameObjectUtility.RemoveMonoBehavioursWithMissingScript(t.gameObject);
 }
 NativeChainRestructure.Apply(actor,aliases);
 File.Copy("/work/motion-bake/task-U/restructure.json","/work/motion-bake/task-U/miku/restructure.json",true);
 PrefabUtility.SaveAsPrefabAsset(actor,"Assets/NativeActor/MikuRestructured.prefab");AssetDatabase.SaveAssets();Debug.Log("U_MIKU_RESTRUCTURED");
 }
}
