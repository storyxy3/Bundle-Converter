using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using ActorAnimation;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;
using Object = UnityEngine.Object;

// Offline conversion only: emitted prefabs contain native components exclusively.
public static class NativeActorExport
{
    const string Out = "/work/motion-bake/task-S/actor-out";
    const string Assets = "Assets/NativeActor";
    public static void Run()
    {
        try { Export(); EditorApplication.Exit(0); }
        catch(Exception e) { Debug.LogException(e); EditorApplication.Exit(1); }
    }
    static void Export()
    {
        Debug.Log("NATIVE_PART_CONTRACT root="+VL.VLActorDefine.GetRootName("mdl_chr_ttmr-cstm-0003_body")+" face="+VL.VLActorDefine.GetRootName("mdl_chr_ttmr-base-0000_face"));
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Standalone, ScriptingImplementation.Mono2x);
        Directory.CreateDirectory(Out); Directory.CreateDirectory(Assets);
        var bundle = AssetBundle.LoadFromFile(Environment.GetEnvironmentVariable("S_SWING_BUNDLE") ?? "/work/gakumas/live-urp-ext/.recon/task-O/actor/ichika.swing.bundle");
        var actor = Object.Instantiate(bundle.LoadAllAssets<GameObject>().Single());
        actor.name = "mdl_chr_ttmr-cstm-0003_body";
        // O's fitting process leaves a sampled pose on its output. Restore L's authored rest skeleton.
        var restBundle=AssetBundle.LoadFromFile("/work/motion-bake/task-L/actor-export/output/ichika.actor.bundle");
        var restActor=restBundle.LoadAllAssets<GameObject>().Single();
        var rest=restActor.GetComponentsInChildren<Transform>(true).ToDictionary(t=>AnimationUtility.CalculateTransformPath(t,restActor.transform));
        foreach(var t in actor.GetComponentsInChildren<Transform>(true))
            if(rest.TryGetValue(AnimationUtility.CalculateTransformPath(t,actor.transform),out var r))
            {t.localPosition=r.localPosition;t.localRotation=r.localRotation;t.localScale=r.localScale;}
        Object.DestroyImmediate(actor.GetComponent<Animator>());
        foreach(var c in actor.GetComponentsInChildren<Component>(true))if(c is UnityEngine.Animations.IConstraint)Object.DestroyImmediate(c);
        foreach(var t in actor.GetComponentsInChildren<Transform>(true)) GameObjectUtility.RemoveMonoBehavioursWithMissingScript(t.gameObject);
        // Humanoid correspondence is the original exporter's explicit source mapping.
        var source = JObject.Parse(File.ReadAllText("/work/motion-bake/task-L/actor-export/source.json"));
        var bones = actor.GetComponentsInChildren<Transform>(true);
        var human = new Dictionary<Transform,string>();
        foreach(var h in source["human"])
        {
            string hn = (string)h["humanName"];
            var id = Enumerable.Range(0,HumanTrait.BoneName.Length).Single(i=>HumanTrait.BoneName[i]==hn);
            var nativeName = NativeName((HumanBodyBones)id);
            human.Add(bones.Single(t=>t.name==(string)h["bone"]),nativeName);
        }
        var skins = actor.GetComponentsInChildren<SkinnedMeshRenderer>(true);
        var materials=new Dictionary<Material,Material>();
        foreach(var r in skins)r.sharedMaterials=r.sharedMaterials.Select(m=> {
            if(materials.TryGetValue(m,out var known))return known;
            var clone=Object.Instantiate(m);clone.name=m.name;
            foreach(var property in clone.GetTexturePropertyNames())
            {
                var tex=clone.GetTexture(property);if(!tex)continue;
                var copy=Object.Instantiate(tex);copy.name=tex.name;
                string path=Assets+"/"+copy.name+".asset";
                var existing=AssetDatabase.LoadAssetAtPath<Texture>(path);
                if(existing) {Object.DestroyImmediate(copy);copy=existing;} else AssetDatabase.CreateAsset(copy,path);
                clone.SetTexture(property,copy);
            }
            clone.shader=AssetDatabase.LoadAssetAtPath<Shader>("Assets/NativeActorSerialization.shader");
            if(!clone.shader)throw new InvalidDataException("Missing export-only texture carrier");
            AssetDatabase.CreateAsset(clone,Assets+"/"+clone.name+".mat");materials[m]=clone;return clone;
        }).ToArray();
        var original = skins.ToDictionary(r=>r,r=>r.bones.Select(b=>b.localToWorldMatrix).ToArray());
        // Native Swing uses rigid transforms: bake inherited source scale into translations.
        foreach(var b in actor.GetComponentsInChildren<MonoBehaviour>(true).OfType<IActorSwingBone>())
        {
            var component=(Component)b;float scale=component.transform.lossyScale.x;
            var collider=b.swingCollider;if(collider==null)continue;
            collider.float_A*=scale;collider.float_B*=scale;collider.vector3_A*=scale;
            if(collider.type==ActorSwingColliderType.Capsule)collider.vector3_B=new Vector3(collider.vector3_B.x,collider.vector3_B.y*scale,collider.vector3_B.z);
        }
        var worldPositions=bones.ToDictionary(t=>t,t=>t.position);
        var worldRotations=bones.ToDictionary(t=>t,t=>t.rotation);
        foreach(var t in bones) {t.localScale=Vector3.one;t.position=worldPositions[t];t.rotation=worldRotations[t];}
        var dynamics = actor.GetComponentsInChildren<ActorSwingDynamicBone>(true).Where(b=>!b.name.StartsWith("__SwingTip")).ToArray();
        var keep = new HashSet<Transform>(human.Keys.Concat(dynamics.Select(b=>b.transform)));
        foreach(var b in actor.GetComponentsInChildren<ActorSwingStaticBone>(true)) keep.Add(b.transform);
        var reference = new GameObject("Reference").transform; reference.SetParent(actor.transform,false);
        var oldNames = bones.ToDictionary(t=>t,t=>t.name);
        foreach(var t in keep.ToArray())
        {
            var p=t.parent;
            while(p!=null && !keep.Contains(p))p=p.parent;
            t.SetParent(p ? p : reference,true);
        }
        foreach(var pair in human)pair.Key.name=pair.Value;
        // Genuine uninterrupted Swing topology; offset transforms are folded offline.
        foreach(var b in dynamics)
        {
            var t=b.transform;
            t.name=oldNames[t].Replace("EX_","").Replace("_","")+"_S";
            var tip=t.Cast<Transform>().SingleOrDefault(c=>c.name=="__SwingTip");
            var child=t.Cast<Transform>().FirstOrDefault(c=>c.GetComponent<ActorSwingDynamicBone>() && c!=tip);
            if(child && tip)
            {
                EditorUtility.CopySerialized(tip.GetComponent<ActorSwingDynamicBone>(),child.GetComponent<ActorSwingDynamicBone>());
                Object.DestroyImmediate(tip.gameObject);
                child.SetAsFirstSibling();
            }
            else if(tip) { tip.name=t.name+"_End"; keep.Add(tip); tip.SetAsFirstSibling(); }
        }
        foreach(var b in dynamics)
        {
            var children=b.transform.Cast<Transform>().Where(t=>t.GetComponent<ActorSwingDynamicBone>()).ToArray();
            foreach(var child in children.Skip(1))
            {
                var anchor=new GameObject(child.name+"_A").transform;anchor.SetParent(b.transform,false);
                child.SetParent(anchor,true);keep.Add(anchor);
            }
        }
        // Use the complete native body scaffold, including its IK and Quartz authoring.
        var nativeBundle=AssetBundle.LoadFromFile("/work/gakumas/live-urp-ext/Build/Content-Linux/ttmr001/mdl_chr_ttmr-cstm-0003_body.unity3d");
        var scaffold=Object.Instantiate(nativeBundle.LoadAllAssets<GameObject>().Single());
        actor.layer=scaffold.layer;
        foreach(var renderer in scaffold.GetComponentsInChildren<Renderer>(true))Object.DestroyImmediate(renderer.gameObject);
        foreach(var c in scaffold.GetComponentsInChildren<MonoBehaviour>(true))
            if(c is IActorSwingComponent)Object.DestroyImmediate(c);
        var nativeBones=scaffold.GetComponentsInChildren<Transform>(true).ToDictionary(t=>t.name);
        var redirects=new Dictionary<Transform,Transform>();
        foreach(var pair in human)
        {
            var target=nativeBones[pair.Value];redirects[pair.Key]=target;
            foreach(var child in pair.Key.Cast<Transform>().Where(t=>!human.ContainsKey(t)).ToArray())child.SetParent(target,true);
            keep.Remove(pair.Key);
        }
        foreach(var side in new[]{"Left","Right"})foreach(var roll in new[]{"Arm","ForeArm"})
        {
            var old=bones.SingleOrDefault(t=>t && oldNames[t]==side+"_"+roll+"Roll");
            if(old)redirects[old]=nativeBones[side+roll+"_Roll_H"];
        }
        foreach(var child in scaffold.transform.Cast<Transform>().ToArray())child.SetParent(actor.transform,false);
        Object.DestroyImmediate(scaffold);
        var oldReference=reference;reference=nativeBones["Reference"];
        foreach(var t in nativeBones.Values)if(t)keep.Add(t);
        // Fold skin influences from removed offsets/helpers into their retained ancestor.
        double sum=0; float max=0; long count=0;
        foreach(var r in skins)
        {
            var mesh=Object.Instantiate(r.sharedMesh);mesh.name=r.name+"Native";
            var old=r.bones;
            var mapped=old.Select(b=> {while(b && !keep.Contains(b)) {if(redirects.TryGetValue(b,out var redirected))return redirected;b=b.parent;}return b?b:reference;}).ToArray();
            var poses=mesh.bindposes;
            for(int i=0;i<poses.Length;i++) poses[i]=mapped[i].worldToLocalMatrix*original[r][i]*poses[i];
            mesh.bindposes=poses;
            var verts=mesh.vertices; var weights=mesh.boneWeights;
            for(int i=0;i<verts.Length;i++)
            {
                var w=weights[i];var before=Vector3.zero;var after=Vector3.zero;
                int[] ids={w.boneIndex0,w.boneIndex1,w.boneIndex2,w.boneIndex3};float[] ws={w.weight0,w.weight1,w.weight2,w.weight3};
                for(int j=0;j<4;j++)if(ws[j]>0)
                {
                    int k=ids[j];before+=ws[j]*original[r][k].MultiplyPoint3x4(r.sharedMesh.bindposes[k].MultiplyPoint3x4(verts[i]));
                    after+=ws[j]*mapped[k].localToWorldMatrix.MultiplyPoint3x4(poses[k].MultiplyPoint3x4(verts[i]));
                }
                float error=Vector3.Distance(before,after);sum+=error*error;max=Mathf.Max(max,error);count++;
            }
            AssetDatabase.CreateAsset(mesh,Assets+"/"+mesh.name+".asset");
            r.sharedMesh=mesh;r.bones=mapped;r.rootBone=reference;
            r.transform.SetParent(actor.transform,true);r.name="Geo_"+r.name;
            r.localBounds=new Bounds(new Vector3(0,.8f,0),new Vector3(3,3,3));
        }
        foreach(var t in bones.Reverse())
        {
            if(!t || t==actor.transform || keep.Contains(t) || t.GetComponent<Renderer>())continue;
            foreach(var child in t.Cast<Transform>().ToArray())child.SetParent(t.parent,true);
            Object.DestroyImmediate(t.gameObject);
        }
        Object.DestroyImmediate(oldReference.gameObject);
        foreach(var b in actor.GetComponentsInChildren<ActorSwingDynamicBone>(true))
            b.modelingTransform=new InitialTransform {localPosition=b.transform.localPosition,localRotation=b.transform.localRotation};
        var scriptCopies=new Dictionary<MonoBehaviour,MonoBehaviour>();
        foreach(var component in actor.GetComponentsInChildren<MonoBehaviour>(true))
        {
            var serialized=new SerializedObject(component);var property=serialized.GetIterator();
            while(property.Next(true))if(property.propertyType==SerializedPropertyType.ObjectReference)
            {
                var value=property.objectReferenceValue;
                string targetName=value is GameObject obj?obj.name:value is Transform tx?tx.name:null;
                if(targetName!=null && nativeBones.TryGetValue(targetName,out var target) && target)
                    property.objectReferenceValue=value is GameObject?(Object)target.gameObject:target;
            }
            serialized.ApplyModifiedPropertiesWithoutUndo();
            if(component is ActorAnimationQuartzDriverRotationBone rotation)
                Debug.Log("NATIVE_QUARTZ_REFERENCE "+component.name+" -> "+(rotation.setting.referenceBone?rotation.setting.referenceBone.name:"NULL"));
            var replacement=(MonoBehaviour)component.gameObject.AddComponent(component.GetType());
            EditorUtility.CopySerializedManagedFieldsOnly(component,replacement);
            scriptCopies.Add(component,replacement);
        }
        foreach(var replacement in scriptCopies.Values)
        {
            var serialized=new SerializedObject(replacement);var property=serialized.GetIterator();
            while(property.Next(true))if(property.propertyType==SerializedPropertyType.ObjectReference && property.objectReferenceValue is MonoBehaviour old && scriptCopies.TryGetValue(old,out var newer))property.objectReferenceValue=newer;
            serialized.ApplyModifiedPropertiesWithoutUndo();
        }
        foreach(var old in scriptCopies.Keys)Object.DestroyImmediate(old);
        var head=nativeBones["Head"];
        var parts=new Dictionary<string,GameObject>{{"body",actor}};
        foreach(var suffix in new[]{"hair","face"})
        {
            var part=new GameObject(suffix=="hair"?"mdl_chr_ttmr-cstm-0003_hair":"mdl_chr_ttmr-base-0000_face");parts[suffix]=part;part.layer=actor.layer;
            var root=new GameObject("Head_"+(suffix=="hair"?"Hair":"Face")).transform;
            root.SetParent(part.transform,false);root.position=head.position;root.rotation=head.rotation;
            if(suffix=="hair")foreach(var b in actor.GetComponentsInChildren<ActorSwingDynamicBone>(true).Where(b=>oldNames.ContainsKey(b.transform) && oldNames[b.transform].ToLowerInvariant().Contains("hair")))
            {
                if(!b.transform.parent.name.Contains("_S"))b.transform.SetParent(root,true);
            }
            foreach(var r in skins.Where(r=>suffix=="hair"?r.name=="Geo_Hair":r.name!="Geo_Hair" && r.name!="Geo_Body"))
            {
                var mesh=r.sharedMesh;var poses=mesh.bindposes;var bound=r.bones;
                for(int i=0;i<bound.Length;i++)if(!bound[i].IsChildOf(root))
                {if(i<poses.Length)poses[i]=root.worldToLocalMatrix*bound[i].localToWorldMatrix*poses[i];bound[i]=root;}
                mesh.bindposes=poses;r.bones=bound;r.rootBone=root;r.transform.SetParent(part.transform,true);
                if(suffix=="face" && r.name=="Geo_Face")r.name="Geo_Eye";
                EditorUtility.SetDirty(mesh);
            }
        }
        foreach(var part in parts.Values)
        {
            foreach(var bone in part.GetComponentsInChildren<ActorSwingDynamicBone>(true).Where(b=>!b.transform.parent.GetComponent<ActorSwingDynamicBone>()))
            {
                var chain=bone.gameObject.AddComponent<ActorSwingChain>();chain.rootBones.Add(bone);chain.UpdateChainInfo();
            }
        }
        // Source arm roll influences use the native template Quartz roll bones.
        // TODO(qa-recon): measure motion-space twist residual against the original PJSK drivers.
        // TODO(qa-recon): source AssistHip leg-helper drivers are not reconstructed;
        // their influences fold to UpLeg and lose the source helper deformation.
        var paths=new List<string>();
        foreach(var suffix in new[]{"body","hair","face"})
        {
            var go=parts[suffix];
            var path=Assets+"/"+go.name+".prefab";PrefabUtility.SaveAsPrefabAsset(go,path);paths.Add(path);
        }
        AssetDatabase.SaveAssets();
        var builds=Enumerable.Select(paths,p=>new AssetBundleBuild{assetBundleName=(p.EndsWith("face.prefab")?"mdl_chr_ttmr-base-0000_face":p.EndsWith("hair.prefab")?"mdl_chr_ttmr-cstm-0003_hair":"mdl_chr_ttmr-cstm-0003_body")+".unity3d",assetNames=new[]{p}}).ToArray();
        Debug.Log("NATIVE_BUILD_INPUT "+builds.Length+" "+string.Join(",",builds.Select(b=>b.assetBundleName+":"+string.Join(";",b.assetNames))));
        if(!BuildPipeline.BuildAssetBundles(Out,builds,BuildAssetBundleOptions.ChunkBasedCompression,BuildTarget.StandaloneLinux64))throw new Exception("Bundle build failed");
        File.WriteAllText(Out+"/rebind.json",new JObject{["vertices"]=count,["restRmsMetres"]=Math.Sqrt(sum/count),["restMaxMetres"]=max,["dynamicBones"]=actor.GetComponentsInChildren<ActorSwingDynamicBone>(true).Length}.ToString());
        Debug.Log($"NATIVE_ACTOR_EXPORTED vertices={count} rms={Math.Sqrt(sum/count)} max={max}");
    }
    static string NativeName(HumanBodyBones b)
    {
        foreach(var name in new[]{"Hips","Spine","Spine1","Spine2","Neck","Head","LeftShoulder","LeftArm","LeftForeArm","LeftHand","LeftUpLeg","LeftLeg","LeftFoot","LeftToeBase","RightShoulder","RightArm","RightForeArm","RightHand","RightUpLeg","RightLeg","RightFoot","RightToeBase"}.Concat(new[]{"Left","Right"}.SelectMany(s=>new[]{"Thumb","Index","Middle","Ring","Pinky"}.SelectMany(f=>Enumerable.Range(1,3).Select(i=>s+"Hand"+f+i)))))
            if(VL.VLActorDefine.TryGetHumanBodyBone(name,out var v)&&v==b)return name;
        throw new Exception("Unknown humanoid bone "+b);
    }
}
