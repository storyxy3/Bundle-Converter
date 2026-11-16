using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

public static partial class HumanoidBake
{
    [Serializable] private class ClipFlags
    {
        public bool Mirror, LoopTime, LoopBlend, LoopBlendOrientation, LoopBlendPositionY, LoopBlendPositionXZ;
        public bool StartAtOrigin, KeepOriginalOrientation, KeepOriginalPositionY, KeepOriginalPositionXZ, HeightFromFeet;
        public float OrientationOffsetY, Level, CycleOffset;
    }
    // Original ordering from original_rig_audit.md and ActorAnimationFullBodyIKJobSkeleton.
    // This is a clip/rig bake, not simulation of LookAt, collision correction, nod, Quartz or Swing.
    private struct Limb
    {
        public TransformStreamHandle top, middle, end, goal, hint;
        public float maximum;
        public void Maximum(AnimationStream stream)
        {
            if(maximum==0)maximum=Vector3.Distance(top.GetPosition(stream),middle.GetPosition(stream))+Vector3.Distance(middle.GetPosition(stream),end.GetPosition(stream));
        }
        public void Effector(AnimationStream stream, Vector3 delta, AvatarIKGoal kind)
        {
            var human=stream.AsHuman(); var w=goal.GetLocalScale(stream);
            if ((int)kind<2 && Mathf.Max(w.x,w.y)<=1e-5f) return;
            var p=goal.GetPosition(stream); var q=goal.GetRotation(stream);
            if ((int)kind<2) { p=Vector3.LerpUnclamped(human.GetGoalPosition(kind),p,w.x); q=Quaternion.SlerpUnclamped(human.GetGoalRotation(kind),q,w.y); }
            human.SetGoalPosition(kind,p+delta); human.SetGoalRotation(kind,q);
            human.SetGoalWeightPosition(kind,w.x); human.SetGoalWeightRotation(kind,w.y);
        }
        public void Hint(AnimationStream stream, Vector3 delta, AvatarIKHint kind)
        {
            var w=hint.GetLocalScale(stream).x;
            if(w<1e-5f) return;
            var human=stream.AsHuman();
            human.SetHintPosition(kind,delta+Vector3.LerpUnclamped(human.GetHintPosition(kind),hint.GetPosition(stream),w));
            human.SetHintWeightPosition(kind,w);
        }
        public Vector3 Pull(AnimationStream stream,Vector3 original,Vector3 current,AvatarIKGoal kind,float stiffness)
        {
            var human=stream.AsHuman();
            var local=top.GetPosition(stream)-original;
            var d=human.GetGoalPosition(kind)-(current+local);
            return d.normalized*Mathf.Max((d.magnitude-maximum)*stiffness,0)*goal.GetLocalScale(stream).z*human.GetGoalWeightPosition(kind);
        }
    }
    private struct NativeIK : IAnimationJob
    {
        public TransformStreamHandle hips, reference, move, body;
        public Limb leftFoot,rightFoot,leftHand,rightHand;
        public float stiffness;
        public int iterations;
        public void ProcessRootMotion(AnimationStream stream) {}
        public void ProcessAnimation(AnimationStream stream)
        {
            var h=stream.AsHuman();
            var delta=reference.GetPosition(stream)-move.GetPosition(stream);delta.y=0;
            var hip=hips.GetLocalPosition(stream);hip.x=0;hip.z=0;hips.SetLocalPosition(stream,hip);
            leftHand.Maximum(stream);rightHand.Maximum(stream);leftFoot.Maximum(stream);rightFoot.Maximum(stream);
            var bw=body.GetLocalScale(stream);var bp=h.bodyPosition;
            bp.y=Mathf.LerpUnclamped(bp.y,body.GetPosition(stream).y,bw.x);
            h.bodyPosition=bp;
            // D.samples original disassembly: scale.y is rotation, unlike the current reconstructed package's scale.x typo.
            h.bodyRotation=Quaternion.SlerpUnclamped(h.bodyRotation,body.GetRotation(stream),bw.y);
            leftFoot.Effector(stream,delta,AvatarIKGoal.LeftFoot);rightFoot.Effector(stream,delta,AvatarIKGoal.RightFoot);
            leftHand.Effector(stream,delta,AvatarIKGoal.LeftHand);rightHand.Effector(stream,delta,AvatarIKGoal.RightHand);
            leftFoot.Hint(stream,delta,AvatarIKHint.LeftKnee);rightFoot.Hint(stream,delta,AvatarIKHint.RightKnee);
            leftHand.Hint(stream,delta,AvatarIKHint.LeftElbow);rightHand.Hint(stream,delta,AvatarIKHint.RightElbow);
            var original=h.bodyPosition;var pos=original;
            for(int i=iterations;i>0;i--)
                pos+=(leftHand.Pull(stream,original,pos,AvatarIKGoal.LeftHand,stiffness)+rightHand.Pull(stream,original,pos,AvatarIKGoal.RightHand,stiffness)
                    +leftFoot.Pull(stream,original,pos,AvatarIKGoal.LeftFoot,stiffness)+rightFoot.Pull(stream,original,pos,AvatarIKGoal.RightFoot,stiffness))/i;
            h.bodyPosition=pos;h.SolveIK();reference.SetPosition(stream,move.GetPosition(stream));
        }
    }
    [Serializable] private class SourceBinding { public int typeID, attribute; }
    [Serializable] private class SourceChannel { public SourceBinding binding; public string path; public int offset, width; }
    [Serializable] private class SourceSemantics { public int frames, rate, floatsPerFrame; public SourceChannel[] bindings; }
    private sealed class NativeSource : IDisposable
    {
        private readonly PlayableGraph graph;
        private readonly AnimationClipPlayable playable;
        private readonly AnimationClip clip;
        private readonly Rig rig;
        private int weightedFeet;
        private float maxFootErrorBeforeHip, maxFootErrorAfterHip;
        public string Report=>$"native weighted-foot samples={weightedFeet}; max ankle-to-authored-goal distance before HipCorrector={maxFootErrorBeforeHip:R} m, after={maxFootErrorAfterHip:R} m; excludes unreachable-target guarantees and scene overrides\n";
        public NativeSource(Rig rig, MotionJson header, byte[] raw, string dataDir)
        {
            this.rig=rig;
            if(header.isAdditive||header.hasMask)throw new NotSupportedException("TODO(qa-recon): additive/masked motion requires a base layer graph");
            int stride=header.channels.Length;
            float V(int f,int c)=>BitConverter.ToSingle(raw,(f*stride+c)*4);
            // Unknown runtime inputs must not become guessed defaults.
            foreach(var label in new[]{"LookAt.x","IKHint_LeftElbow.y","IKHint_RightElbow.y"})
            {
                int c=Array.IndexOf(header.channels,label);
                if(c>=0 && Enumerable.Range(0,header.frames).Any(f=>Mathf.Abs(V(f,c))>(label=="LookAt.x"?.001f:1e-8f)))
                    throw new NotSupportedException("TODO(qa-recon): external "+label+" needs model collision/look-at state");
            }
            clip=new AnimationClip {name=header.clip,frameRate=header.rate,legacy=false};
            for(int c=0;c<stride;c++)
            {
                if(header.present!=null&&header.present.Length==stride&&!header.present[c])continue;
                var channel=header.channels[c];string path="",property=channel;Type type=typeof(Animator);
                if(c>=137)
                {
                    int dot=channel.LastIndexOf('.');path=channel.Substring(0,dot);type=typeof(Transform);
                    property=(path=="Move"?"m_LocalPosition.":"m_LocalScale.")+channel.Substring(dot+1);
                }
                var keys=new Keyframe[header.frames];
                for(int f=0;f<keys.Length;f++)
                {
                    float previous=f>0?V(f-1,c):V(f,c),next=f+1<keys.Length?V(f+1,c):V(f,c);
                    keys[f]=new Keyframe(f/(float)header.rate,V(f,c),(V(f,c)-previous)*header.rate,(next-V(f,c))*header.rate);
                }
                AnimationUtility.SetEditorCurve(clip,EditorCurveBinding.FloatCurve(path,type,property),new AnimationCurve(keys));
            }
            if(!string.IsNullOrEmpty(header.semanticsFile))
            {
                var semanticsPath=Path.Combine(dataDir,header.semanticsFile);
                var semantics=JsonUtility.FromJson<SourceSemantics>(File.ReadAllText(semanticsPath));
                var bytes=File.ReadAllBytes(Path.ChangeExtension(semanticsPath,"f32"));
                if(semantics.frames!=header.frames||semantics.rate!=header.rate||bytes.LongLength!=(long)semantics.frames*semantics.floatsPerFrame*4)
                    throw new Exception("source semantics grid mismatch");
                foreach(var binding in semantics.bindings)
                {
                    if(binding.binding.typeID!=4||binding.path==null||!binding.path.StartsWith("Root_Body/"))continue;
                    var path=binding.path.Substring("Root_Body/".Length);
                    if(rig.root.transform.Find(path)==null)continue; // Retained unresolved identity remains in sidecar.
                    string property=binding.binding.attribute==1?"m_LocalPosition":binding.binding.attribute==2?"m_LocalRotation":binding.binding.attribute==3?"m_LocalScale":binding.binding.attribute==4?"localEulerAnglesRaw":null;
                    if(property==null)throw new Exception("unknown Transform attribute");
                    for(int component=0;component<binding.width;component++)
                    {
                        float Read(int frame)=>BitConverter.ToSingle(bytes,(frame*semantics.floatsPerFrame+binding.offset+component)*4);
                        var keys=new Keyframe[header.frames];
                        for(int f=0;f<keys.Length;f++)keys[f]=new Keyframe(f/(float)header.rate,Read(f),
                            (Read(f)-Read(Math.Max(0,f-1)))*header.rate,(Read(Math.Min(keys.Length-1,f+1))-Read(f))*header.rate);
                        AnimationUtility.SetEditorCurve(clip,EditorCurveBinding.FloatCurve(path,typeof(Transform),property+"."+"xyzw"[component]),new AnimationCurve(keys));
                    }
                }
            }
            var flags=header.settings??new ClipFlags {StartAtOrigin=true,KeepOriginalPositionY=true};
            var settings=AnimationUtility.GetAnimationClipSettings(clip);
            settings.loopTime=flags.LoopTime;settings.loopBlend=flags.LoopBlend;settings.mirror=flags.Mirror;
            settings.keepOriginalOrientation=flags.KeepOriginalOrientation;settings.keepOriginalPositionY=flags.KeepOriginalPositionY;
            settings.keepOriginalPositionXZ=flags.KeepOriginalPositionXZ;settings.heightFromFeet=flags.HeightFromFeet;
            settings.orientationOffsetY=flags.OrientationOffsetY;settings.level=flags.Level;settings.cycleOffset=flags.CycleOffset;
            settings.loopBlendOrientation=flags.LoopBlendOrientation;settings.loopBlendPositionY=flags.LoopBlendPositionY;settings.loopBlendPositionXZ=flags.LoopBlendPositionXZ;
            settings.startTime=0;settings.stopTime=header.stop-header.start;
            AnimationUtility.SetAnimationClipSettings(clip,settings);
            // startAtOrigin is serialized by Unity; preserve it through the native property instead of inferring a translation.
            var serialized=new SerializedObject(clip);var startAtOrigin=serialized.FindProperty("m_MuscleClip.m_StartAtOrigin");
            if(startAtOrigin!=null){startAtOrigin.boolValue=flags.StartAtOrigin;serialized.ApplyModifiedPropertiesWithoutUndo();}
            else if(!flags.StartAtOrigin)throw new NotSupportedException("TODO(qa-recon): this Unity build does not expose startAtOrigin=false");
            if(!clip.isHumanMotion)throw new Exception("generated clip is not Humanoid");
            var animator=rig.root.GetComponent<Animator>();animator.applyRootMotion=false;animator.cullingMode=AnimatorCullingMode.AlwaysAnimate;
            TransformStreamHandle H(string name)=>animator.BindStreamTransform(rig.byName[name]);
            Limb L(string side,string part,string hint,string top,string middle,string end)=>new Limb {
                top=animator.BindStreamTransform(rig.byHuman[side+top]),middle=animator.BindStreamTransform(rig.byHuman[side+middle]),
                end=animator.BindStreamTransform(rig.byHuman[side+end]),goal=H("IKGoal_"+side+part),hint=H("IKHint_"+side+hint)};
            var job=new NativeIK {hips=H("Hips"),reference=H("Reference"),move=H("Move"),body=H("IKBody"),
                leftFoot=L("Left","Foot","Knee","UpperLeg","LowerLeg","Foot"),rightFoot=L("Right","Foot","Knee","UpperLeg","LowerLeg","Foot"),
                leftHand=L("Left","Hand","Elbow","UpperArm","LowerArm","Hand"),rightHand=L("Right","Hand","Elbow","UpperArm","LowerArm","Hand"),
                // Source CampusActorAnimation field initializers: stiffness=1, maxPullIteration=5; no runtime overrides in this offline context.
                stiffness=float.Parse(Env("HB_IK_STIFFNESS","1"),Inv),iterations=int.Parse(Env("HB_IK_ITERATIONS","5"),Inv)};
            graph=PlayableGraph.Create("ConverterNativeMotion");graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
            playable=AnimationClipPlayable.Create(graph,clip);playable.SetApplyFootIK(header.applyFootIK);playable.SetApplyPlayableIK(header.applyPlayableIK);
            var ik=AnimationScriptPlayable.Create(graph,job,1);graph.Connect(playable,0,ik,0);ik.SetInputWeight(0,1);
            AnimationPlayableOutput.Create(graph,"source",animator).SetSourcePlayable(ik);graph.Play();
        }
        public void Sample(float time,ref HumanPose pose)
        {
            playable.SetTime(time);graph.Evaluate(0);
            foreach(var side in new[]{"Left","Right"})
            {
                var goal=rig.byName["IKGoal_"+side+"Foot"];
                if(goal.localScale.x>1e-5f){weightedFeet++;maxFootErrorBeforeHip=Mathf.Max(maxFootErrorBeforeHip,Vector3.Distance(rig.byHuman[side+"Foot"].position,goal.position));}
            }
            // CampusActorHipCorrector.LateUpdate follows jobs. Physics is deliberately outside the motion bake.
            var hip=rig.byHuman["Hips"];var p=hip.localPosition;var move=rig.byName["Move"].localPosition;
            hip.localPosition=new Vector3(move.x,p.y,move.z);
            foreach(var side in new[]{"Left","Right"})
            {
                var goal=rig.byName["IKGoal_"+side+"Foot"];
                if(goal.localScale.x>1e-5f)maxFootErrorAfterHip=Mathf.Max(maxFootErrorAfterHip,Vector3.Distance(rig.byHuman[side+"Foot"].position,goal.position));
            }
            rig.handler.GetHumanPose(ref pose);
        }
        public void Dispose(){graph.Destroy();UnityEngine.Object.DestroyImmediate(clip);}
    }
}
