using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

public static partial class HumanoidBake
{
    [Serializable] private class GenericMotion
    {
        public string format, clip, source;
        public int rate, frames, floatsPerFrame;
        public float start, duration, characterHeight;
        public string[] bones;
        public ClipFlags settings;
    }
    [Serializable] private class ExternalMotion
    {
        public string format = "haruki-external-motion/1", clip, source, dataFile, helpersFile;
        public int rate, frames, floatsPerFrame = 152;
        public float duration, characterHeight, sourceHumanScale;
        public bool loop;
        public string[] channels;
        public string rootPolicy = "RootT/Q contains full pose and Position travel; apply once through HumanPoseHandler. Move is meters, for the native Gakumas HipCorrector only.";
        public string goalSpace = "source Avatar root-local, divided by sourceHumanScale (not Unity serialized goal space); weights zero; consumer must reject nonzero weights unless it supports this space";
        public string twistPolicy = "Wrist local-X twist folded into Elbow preserving wrist world rotation; side-branch ArmRoll/ForeArmRoll are skin helpers, not additional chain rotation.";
        public string limitations = "Humanoid muscles do not carry nonhuman helpers; apply helpersFile separately on matching PJSK bones. Retargeting changes proportions. Template metadata is a separate source-preserving sidecar; it is not automatically executed.";
    }
    public static void Reverse()
    {
        try { ReverseInner(); EditorApplication.Exit(0); }
        catch (Exception e) { Debug.LogError("[ReverseBake] FAILED " + e); EditorApplication.Exit(1); }
    }
    private static void ReverseInner()
    {
        string data = Env("HB_DATA"), output = Env("HB_OUT"), name = Env("HB_MOTION");
        Directory.CreateDirectory(output);
        var skeleton = JsonUtility.FromJson<SkeletonJson>(File.ReadAllText(Path.Combine(data, "pjsk_skeleton.json")));
        var sourceDesc = JsonUtility.FromJson<SkeletonJson>(File.ReadAllText(Path.Combine(data, "gakumas_skeleton.json"))).description;
        var rig = BuildRig("pjsk", skeleton, sourceDesc);
        var header = JsonUtility.FromJson<GenericMotion>(File.ReadAllText(Path.Combine(data, name + ".json")));
        if (header.format != "haruki-generic-samples/1" || header.floatsPerFrame != header.bones.Length * 10 || header.frames < 1 || header.rate <= 0)
            throw new Exception("invalid Generic motion header");
        var raw = File.ReadAllBytes(Path.Combine(data, name + ".f32"));
        if (raw.LongLength != (long)header.frames * header.floatsPerFrame * 4) throw new Exception("Generic payload size mismatch");
        var animated = header.bones.Select(b => rig.byName[b]).ToArray();
        var canonical = JsonUtility.FromJson<MotionJson>(File.ReadAllText(Path.Combine(data, "hski_all001.json"))).channels;
        if (canonical.Length != 137) throw new Exception("expected canonical 137 humanoid channels");
        var names = canonical.Concat(new[] {"Move.x", "Move.y", "Move.z"}).Concat(
            new[] {"LeftFoot", "RightFoot", "LeftHand", "RightHand"}.SelectMany(n => new[] {
                "IKGoal_"+n+".weightPosition", "IKGoal_"+n+".weightRotation", "IKGoal_"+n+".pullWeight"})).ToArray();
        int[] muscles = HumanTrait.MuscleName.Select(m => Array.FindIndex(canonical,
            c => c.Replace("LeftHand.", "Left ").Replace("RightHand.", "Right ").Replace('.', ' ') == m)).ToArray();
        if (muscles.Any(m => m < 42)) throw new Exception("muscle name mismatch");
        float V(int f, int c) => BitConverter.ToSingle(raw, (f * header.floatsPerFrame + c) * 4);
        var pose = new HumanPose { muscles = new float[HumanTrait.MuscleCount] };
        var rest = skeleton.bones.ToDictionary(b => b.name, b => new Quaternion(b.rotation[0], b.rotation[1], b.rotation[2], b.rotation[3]));
        float maxFoldError = 0, maxPoseError = 0, maxMuscle = 0;
        int frameCount = Math.Min(header.frames, int.Parse(Env("HB_FRAMES", header.frames.ToString()), Inv));
        using (var writer = new BinaryWriter(File.Create(Path.Combine(output, name + ".gakumas.f32"))))
        for (int f = 0; f < frameCount; f++)
        {
            // Reset every transform: HumanPose roundtrip below also writes nonanimated bones.
            for (int i=0; i<skeleton.bones.Length; i++)
            {
                var b=skeleton.bones[i]; var t=rig.transforms[i];
                t.localPosition = new Vector3(b.position[0],b.position[1],b.position[2]);
                t.localRotation = rest[b.name]; t.localScale = new Vector3(b.scale[0],b.scale[1],b.scale[2]);
            }
            for (int b = 0; b < animated.Length; b++)
            {
                int k = b * 10; var t = animated[b];
                t.localPosition = new Vector3(V(f,k), V(f,k+1), V(f,k+2));
                t.localRotation = Normalize(new Quaternion(V(f,k+3), V(f,k+4), V(f,k+5), V(f,k+6)));
                t.localScale = new Vector3(V(f,k+7), V(f,k+8), V(f,k+9));
            }
            var travel = rig.byName["Position"].localPosition;
            foreach (var side in new[] {"Left", "Right"})
            {
                var elbow=rig.byName[side+"_Elbow"]; var wrist=rig.byName[side+"_Wrist"];
                var before=wrist.rotation;
                var d=Quaternion.Inverse(rest[wrist.name])*wrist.localRotation;
                float angle=2*Mathf.Atan2(d.x,d.w)*Mathf.Rad2Deg;
                var old=elbow.localRotation;
                var next=old*Quaternion.AngleAxis(angle,Vector3.right);
                wrist.localRotation=Quaternion.Inverse(next)*old*wrist.localRotation;
                elbow.localRotation=next;
                maxFoldError=Mathf.Max(maxFoldError,Quaternion.Angle(before,wrist.rotation));
            }
            // Side-branch roll bones do not contribute to the mapped wrist's global orientation.
            rig.handler.GetHumanPose(ref pose);
            var row = new float[152]; row[6]=1;
            row[7]=pose.bodyPosition.x; row[8]=pose.bodyPosition.y; row[9]=pose.bodyPosition.z;
            row[10]=pose.bodyRotation.x; row[11]=pose.bodyRotation.y; row[12]=pose.bodyRotation.z; row[13]=pose.bodyRotation.w;
            for (int m=0;m<muscles.Length;m++) { row[muscles[m]]=pose.muscles[m]; maxMuscle=Mathf.Max(maxMuscle,Mathf.Abs(pose.muscles[m])); }
            int gi=14;
            foreach (string goal in new[] {"LeftFoot","RightFoot","LeftHand","RightHand"})
            {
                var t=rig.byHuman[goal]; var p=rig.root.transform.InverseTransformPoint(t.position)/rig.humanScale;
                var q=Quaternion.Inverse(rig.root.transform.rotation)*t.rotation;
                row[gi++]=p.x; row[gi++]=p.y; row[gi++]=p.z;
                row[gi++]=q.x; row[gi++]=q.y; row[gi++]=q.z; row[gi++]=q.w;
            }
            row[137]=travel.x*header.characterHeight; row[138]=travel.y*header.characterHeight; row[139]=travel.z*header.characterHeight;
            if (row.Any(v=>float.IsNaN(v)||float.IsInfinity(v))) throw new Exception("non-finite reverse sample at "+f);
            foreach (float v in row) writer.Write(v);
            // Measure conversion loss in this actual conversion, without creating a separate test framework.
            if (f % header.rate == 0)
            {
                var endpoints = new[] {"Head","LeftHand","RightHand","LeftFoot","RightFoot"}.Select(n=>rig.byHuman[n]).ToArray();
                var before=endpoints.Select(t=>t.position).ToArray();
                rig.handler.SetHumanPose(ref pose);
                for(int i=0;i<before.Length;i++) maxPoseError=Mathf.Max(maxPoseError,Vector3.Distance(before[i],endpoints[i].position));
            }
        }
        var doc=new ExternalMotion {clip=header.clip,source=header.source,rate=header.rate,frames=frameCount,
            duration=Mathf.Min(header.duration,(frameCount-1f)/header.rate), characterHeight=header.characterHeight,
            sourceHumanScale=rig.humanScale, loop=header.settings!=null&&header.settings.LoopTime, channels=names, dataFile=name+".gakumas.f32"};
        var helperHeader=Path.Combine(data,name+".helpers.json");
        if(File.Exists(helperHeader))
        {
            // Helpers use their original source frame grid; the runtime samples them with the same absolute clock.
            File.Copy(helperHeader,Path.Combine(output,name+".helpers.json"),true);
            File.Copy(Path.Combine(data,name+".helpers.f32"),Path.Combine(output,name+".helpers.f32"),true);
            doc.helpersFile=name+".helpers.json";
        }
        File.WriteAllText(Path.Combine(output,name+".gakumas.json"),JsonUtility.ToJson(doc,true));
        var report=$"Unity {Application.unityVersion}; Avatar valid={rig.avatar.isValid}, human={rig.avatar.isHuman}; frames={frameCount}; humanScale={rig.humanScale:R}; height={header.characterHeight:R}\n"+
            $"Twist fold max wrist world orientation error={maxFoldError:R} degrees\n"+
            $"Get/SetHumanPose max endpoint position error at 1 Hz={maxPoseError:R} normalized units; maximum absolute muscle={maxMuscle:R}\n"+
            "Original FK: all 12 goal weights zero. No fabricated foot contacts. Nonhuman assist translation is not representable by the 95 muscles.\n";
        File.WriteAllText(Path.Combine(output,name+".reverse-report.txt"),report); Log(report);
    }
}
