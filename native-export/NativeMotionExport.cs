using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using VL;

// Offline only. Runtime consumes ordinary ActorMotionDefine/AnimationClip assets.
public static class NativeMotionExport
{
    [Serializable] private class Samples
    {
        public string format, dataFile;
        public int frames, rate, floatsPerFrame;
        public float duration;
        public bool loop;
        public string[] channels;
    }
    [Serializable] private class Semantics { public string dataFile; public int floatsPerFrame; public GenericBinding[] bindings; }
    [Serializable] private class GenericBinding { public BindingIdentity binding; public string path; public int offset, width; }
    [Serializable] private class BindingIdentity { public int attribute, typeID; }
    public static void Run()
    {
        try { Export(); EditorApplication.Exit(0); }
        catch (Exception e) { Debug.LogException(e); EditorApplication.Exit(1); }
    }
    private static void Export()
    {
        PlayerSettings.SetScriptingBackend(UnityEditor.Build.NamedBuildTarget.Standalone, ScriptingImplementation.Mono2x);
        string input = Environment.GetEnvironmentVariable("S_MOTION");
        var h = JsonUtility.FromJson<Samples>(File.ReadAllText(input));
        if (h.format != "haruki-external-motion/1" || h.frames < 2 || h.rate <= 0 || h.floatsPerFrame != 152 || h.channels.Length != 152)
            throw new InvalidDataException("Unsupported sampled motion");
        var raw = File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(input), h.dataFile));
        if (raw.LongLength != (long)h.frames * 152 * 4) throw new InvalidDataException("Payload length");
        float Value(int f, int c)
        {
            float v = BitConverter.ToSingle(raw, (f * 152 + c) * 4);
            if (float.IsNaN(v) || float.IsInfinity(v)) throw new InvalidDataException("Nonfinite sample");
            return v;
        }
        // Goal values use source-local coordinates, not serialized Humanoid goal space.
        // They must never be activated by copying template IK weights.
        for (int f = 0; f < h.frames; f++)
            for (int c = 140; c < 152; c++)
                if (Value(f, c) != 0) throw new InvalidDataException("Nonzero source IK needs offline goal-space conversion");
        string content = Environment.GetEnvironmentVariable("S_CONTENT");
        const string bundleName = "mot_live_chr_ttmr_ttmr-001_00_in";
        var bundle = AssetBundle.LoadFromFile(Path.Combine(content, bundleName + ".unity3d"));
        if (bundle == null) throw new IOException("Cannot load template motion bundle");
        var template = bundle.LoadAllAssets<ActorMotionDefine>().Single();
        var clip = new AnimationClip { name = "motion_0001_native", frameRate = h.rate };
        // Preserve native Generic bindings and their typed paths. Override travel and IK scales below.
        foreach (var b in AnimationUtility.GetCurveBindings(template.baseAnimation.clip))
        {
            if (b.type == typeof(Animator)) continue;
            var curve = AnimationUtility.GetEditorCurve(template.baseAnimation.clip, b);
            AnimationUtility.SetEditorCurve(clip, b, AnimationCurve.Constant(0, h.duration, curve.Evaluate(0)));
        }
        // Bundled clips do not expose their compressed Generic curves through AnimationUtility.
        // Use the source-preserving typed sidecar produced by the existing offline converter.
        string semanticPath = Environment.GetEnvironmentVariable("S_TEMPLATE_SEMANTICS");
        var semantics = JsonUtility.FromJson<Semantics>(File.ReadAllText(semanticPath));
        var genericRaw = File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(semanticPath), semantics.dataFile));
        foreach (var b in semantics.bindings)
        {
            if (b.binding.typeID != 4) continue;
            string property = b.binding.attribute == 1 ? "m_LocalPosition." : b.binding.attribute == 2 ? "m_LocalRotation." : b.binding.attribute == 3 ? "m_LocalScale." : b.binding.attribute == 4 ? "localEulerAnglesRaw." : null;
            if (property == null) throw new InvalidDataException("Unknown Transform attribute");
            for (int axis = 0; axis < b.width; axis++)
                AnimationUtility.SetEditorCurve(clip, EditorCurveBinding.FloatCurve(b.path, typeof(Transform), property + "xyzw"[axis]), AnimationCurve.Constant(0,h.duration,BitConverter.ToSingle(genericRaw,(b.offset+axis)*4)));
        }
        for (int c = 7; c < 137; c++)
        {
            // FK source goal samples are not Unity's serialized goal coordinates.
            if (c >= 14 && c < 42) continue;
            var keys = new Keyframe[h.frames];
            for (int f = 0; f < keys.Length; f++) keys[f] = new Keyframe(Math.Min((float)f / h.rate, h.duration), Value(f, c));
            var curve = new AnimationCurve(keys.GroupBy(k => k.time).Select(g => g.Last()).ToArray());
            for (int f = 0; f < curve.length; f++)
            {
                AnimationUtility.SetKeyLeftTangentMode(curve, f, AnimationUtility.TangentMode.Linear);
                AnimationUtility.SetKeyRightTangentMode(curve, f, AnimationUtility.TangentMode.Linear);
            }
            AnimationUtility.SetEditorCurve(clip, EditorCurveBinding.FloatCurve("", typeof(Animator), h.channels[c]), curve);
        }
        foreach (var b in AnimationUtility.GetCurveBindings(clip))
        {
            if (b.type != typeof(Transform)) continue;
            string leaf = b.path.Split('/').Last();
            if (leaf.StartsWith("IK") && b.propertyName.StartsWith("m_LocalScale."))
                AnimationUtility.SetEditorCurve(clip, b, AnimationCurve.Constant(0, h.duration, 0));
            if (leaf == "Move" && b.propertyName.StartsWith("m_LocalPosition."))
            {
                int axis = "xyz".IndexOf(b.propertyName.Last());
                var keys = Enumerable.Range(0, h.frames).Select(f => new Keyframe(Math.Min((float)f/h.rate,h.duration), Value(f,137+axis))).ToArray();
                AnimationUtility.SetEditorCurve(clip, b, new AnimationCurve(keys.GroupBy(k => k.time).Select(g => g.Last()).ToArray()));
            }
        }
        var settings = AnimationUtility.GetAnimationClipSettings(template.baseAnimation.clip);
        settings.startTime = 0;
        settings.stopTime = h.duration;
        settings.loopTime = h.loop;
        AnimationUtility.SetAnimationClipSettings(clip, settings);
        const string folder = "Assets/NativeExport";
        Directory.CreateDirectory(folder);
        AssetDatabase.Refresh();
        AssetDatabase.DeleteAsset(folder + "/motion.anim");
        AssetDatabase.CreateAsset(clip, folder + "/motion.anim");
        var neutral = new AnimationClip { name = "neutral", frameRate = h.rate };
        if (template.faceAnimation?.clip != null)
            foreach (var b in AnimationUtility.GetCurveBindings(template.faceAnimation.clip))
                AnimationUtility.SetEditorCurve(neutral, b, AnimationCurve.Constant(0, h.duration, AnimationUtility.GetEditorCurve(template.faceAnimation.clip,b).Evaluate(0)));
        AssetDatabase.DeleteAsset(folder + "/neutral.anim");
        AssetDatabase.CreateAsset(neutral, folder + "/neutral.anim");
        var define = ScriptableObject.CreateInstance<ActorMotionDefine>();
        JsonUtility.FromJsonOverwrite(JsonUtility.ToJson(template), define);
        define.name = template.name;
        define.baseAnimation.clip = clip;
        define.baseAnimation.customClip = null;
        define.faceAnimation = new AnimationData { clip = neutral };
        define.effects = null;
        define.propConstraints = null;
        AssetDatabase.DeleteAsset(folder + "/motion.asset");
        AssetDatabase.CreateAsset(define, folder + "/motion.asset");
        AssetDatabase.SaveAssets();
        string output = Environment.GetEnvironmentVariable("S_OUT");
        Directory.CreateDirectory(output);
        var result = BuildPipeline.BuildAssetBundles(output, new[] { new AssetBundleBuild {
            assetBundleName = bundleName + ".unity3d", assetNames = new[] { folder + "/motion.asset" }
        } }, BuildAssetBundleOptions.ChunkBasedCompression, BuildTarget.StandaloneLinux64);
        if (result == null) throw new Exception("Bundle build failed");
        Debug.Log($"NATIVE_MOTION_EXPORTED humanoid={clip.humanMotion} duration={clip.length} bindings={AnimationUtility.GetCurveBindings(clip).Length}");
    }
}
