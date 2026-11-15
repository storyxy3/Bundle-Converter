// Humanoid bake + verification (tooling, not game code; tools/converter). Batch entry: -executeMethod HumanoidBake.Run
//
// Builds two Humanoid Avatars from haruki-skeleton/0 JSON (no game bundles are loaded):
//   * the source game's avatar (its own bone map and HumanDescription), the reference for what the source game shows;
//   * the target skeleton (PJSK: one normalized body skeleton for every character).
// Every frame of the haruki-humanoid-curves/0 data (RootT/RootQ + 95 muscles, already sampled at the bake rate) is applied
// to both with HumanPoseHandler.SetHumanPose. The target local rotations (+ travel carrier and hip positions) are written
// as haruki-pjsk-bone-curves/1; the two poses are compared segment by segment; a few frames are rendered on a flat ground.
//
// Env: HB_DATA (input dir: <game>_skeleton.json, <motion>.json/.f32), HB_OUT (output dir), HB_MOTION (curves prefix),
//      HB_SOURCE (source game, default gakumas), HB_TARGET (target game, default pjsk),
//      HB_FRAMES (optional frame limit), HB_RENDER_TIMES (comma separated source seconds, optional),
//      HB_RANGE ("start,end" source seconds to keep; default the whole clip),
//      HB_TRAVEL ("keep" | "inplace"; default keep), HB_TRAVEL_SCALE (stage travel multiplier; default 1).
//
// The target's own conventions for bones a Humanoid does not know about come from its skeleton JSON ("conventions",
// from tools/converter/profiles/<target>.json): twist moved between bones (moveTwist), roll bones driven by a ratio of a
// limb's twist (rollBones), and the bone carrying the horizontal travel (travel).
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class HumanoidBake
{
    [Serializable] private class BoneJson { public string name; public int parent; public float[] position; public float[] rotation; public float[] scale; }
    [Serializable] private class HumanJson { public string bone; public string humanName; }
    [Serializable] private class DescJson { public float upperArmTwist = 0.5f, lowerArmTwist = 0.5f, upperLegTwist = 0.5f, lowerLegTwist = 0.5f, armStretch = 0.05f, legStretch = 0.05f, feetSpacing; public bool hasTranslationDoF; }
    [Serializable] private class MoveTwistJson { public string from; public string to; }
    [Serializable] private class RollJson { public string bone; public string twistOf; public float ratio; }
    [Serializable] private class TravelJson { public string carrier; public string hip; }
    [Serializable] private class ConventionsJson { public float[] twistAxis; public MoveTwistJson[] moveTwist; public RollJson[] rollBones; public TravelJson travel; }
    [Serializable] private class SkeletonJson { public string game; public string root; public BoneJson[] bones; public HumanJson[] human; public DescJson description; public ConventionsJson conventions; }
    [Serializable] private class MotionJson { public string clip; public int rate; public int frames; public float start; public string[] channels; }

    private sealed class Rig
    {
        public string label;
        public GameObject root;
        public Transform[] transforms;
        public Dictionary<string, Transform> byName = new Dictionary<string, Transform>();
        public Dictionary<string, Transform> byHuman = new Dictionary<string, Transform>();
        public Avatar avatar;
        public HumanPoseHandler handler;
        public float restHipHeight;
        public float humanScale;
    }

    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    public static void Run()
    {
        try { RunInner(); EditorApplication.Exit(0); }
        catch (Exception e) { Debug.LogError("[HumanoidBake] FAILED " + e); EditorApplication.Exit(1); }
    }

    private static string Env(string key, string fallback = null)
    {
        var v = Environment.GetEnvironmentVariable(key);
        if (string.IsNullOrEmpty(v)) { if (fallback == null) throw new Exception("missing env " + key); return fallback; }
        return v;
    }

    private static void Log(string s) => Debug.Log("[HumanoidBake] " + s);

    private static void RunInner()
    {
        var dataDir = Env("HB_DATA");
        var outDir = Env("HB_OUT");
        var motionName = Env("HB_MOTION");
        var sourceGame = Env("HB_SOURCE", "gakumas");
        var targetGame = Env("HB_TARGET", "pjsk");
        Directory.CreateDirectory(outDir);

        var srcJson = JsonUtility.FromJson<SkeletonJson>(File.ReadAllText(Path.Combine(dataDir, sourceGame + "_skeleton.json")));
        var src = BuildRig(sourceGame, srcJson, null);
        var pjskJson = JsonUtility.FromJson<SkeletonJson>(File.ReadAllText(Path.Combine(dataDir, targetGame + "_skeleton.json")));
        // Same twist / stretch distribution as the source avatar, so both decode the muscles alike.
        var dst = BuildRig(targetGame, pjskJson, srcJson.description);

        var header = JsonUtility.FromJson<MotionJson>(File.ReadAllText(Path.Combine(dataDir, motionName + ".json")));
        var raw = File.ReadAllBytes(Path.Combine(dataDir, motionName + ".f32"));
        int ch = header.channels.Length;
        int frames = header.frames;
        if (raw.Length != frames * ch * 4) throw new Exception($"muscle file size {raw.Length} != {frames}x{ch}x4");
        var limit = int.Parse(Env("HB_FRAMES", frames.ToString()), Inv);
        var range = Env("HB_RANGE", "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries).Select(x => float.Parse(x, Inv)).ToArray();
        int first = range.Length == 2 ? Mathf.Clamp(Mathf.RoundToInt(range[0] * header.rate), 0, frames - 1) : 0;
        int last = range.Length == 2 ? Mathf.Clamp(Mathf.RoundToInt(range[1] * header.rate), first, frames - 1) : frames - 1;
        last = Math.Min(last, first + limit - 1);
        var travelMode = Env("HB_TRAVEL", "keep");
        var travelScale = float.Parse(Env("HB_TRAVEL_SCALE", "1"), Inv);
        if (travelMode != "keep" && travelMode != "inplace") throw new Exception("HB_TRAVEL must be keep or inplace");
        float V(int f, int c) => BitConverter.ToSingle(raw, (f * ch + c) * 4);

        // Muscle channel -> HumanTrait muscle index, by name (curve "LeftHand.Thumb.1 Stretched" == muscle "Left Thumb 1 Stretched").
        var muscleIndex = new int[HumanTrait.MuscleCount];
        var channelByName = new Dictionary<string, int>();
        for (int c = 0; c < ch; c++)
            channelByName[header.channels[c].Replace("LeftHand.", "Left ").Replace("RightHand.", "Right ").Replace('.', ' ')] = c;
        for (int m = 0; m < HumanTrait.MuscleCount; m++)
        {
            if (!channelByName.TryGetValue(HumanTrait.MuscleName[m], out muscleIndex[m]))
                throw new Exception("no channel for muscle " + HumanTrait.MuscleName[m]);
        }
        int C(string n) => Array.IndexOf(header.channels, n);
        int rootT = C("RootT.x"), rootQ = C("RootQ.x");
        Log($"motion {header.clip}: frames {first}..{last} of {frames} @ {header.rate} Hz, {ch} channels; muscles mapped by name: {HumanTrait.MuscleCount}; travel {travelMode} x{travelScale}");

        // Output: the PJSK bones the humanoid drives (human bones) + the roll bones, then Position and Hip positions.
        var conv = new TargetConventions(dst, pjskJson);
        var outBones = pjskJson.human.Select(h => dst.byName[h.bone]).Concat(conv.RollBones).ToArray();
        var hip = conv.Hip;
        var position = conv.Carrier;
        var bakePath = Path.Combine(outDir, motionName + ".pjsk.f32");
        var segments = Segments(src, dst);
        var stats = segments.ToDictionary(s => s.name, s => new List<float>());
        var restDiff = segments.ToDictionary(s => s.name, s => Vector3.Angle(
            (s.srcChild.position - s.srcBone.position).normalized, (s.dstChild.position - s.dstBone.position).normalized));
        var restFoot = FootHeight(dst) - FootHeight(src);
        var footStats = new List<float>();
        var renderTimes = Env("HB_RENDER_TIMES", "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(x => float.Parse(x, Inv)).ToList();
        var renderFrames = new HashSet<int>(renderTimes.Select(t => Mathf.Clamp(Mathf.RoundToInt(t * header.rate), 0, frames - 1)));
        var renderer = renderFrames.Count > 0 ? new GroundRenderer(src, dst, outDir) : null;

        var pose = new HumanPose { muscles = new float[HumanTrait.MuscleCount] };
        var firstFrameReport = new StringBuilder();
        using (var w = new BinaryWriter(File.Create(bakePath)))
        {
            for (int f = first; f <= last; f++)
            {
                pose.bodyPosition = new Vector3(V(f, rootT), V(f, rootT + 1), V(f, rootT + 2));
                var q = new Quaternion(V(f, rootQ), V(f, rootQ + 1), V(f, rootQ + 2), V(f, rootQ + 3));
                pose.bodyRotation = Normalize(q);
                for (int m = 0; m < pose.muscles.Length; m++) pose.muscles[m] = V(f, muscleIndex[m]);
                src.handler.SetHumanPose(ref pose);
                dst.handler.SetHumanPose(ref pose);
                conv.Apply(travelMode == "inplace" ? 0f : travelScale);

                foreach (var b in outBones)
                {
                    var r = b.localRotation; w.Write(r.x); w.Write(r.y); w.Write(r.z); w.Write(r.w);
                }
                var pp = position.localPosition; w.Write(pp.x); w.Write(pp.y); w.Write(pp.z);
                var hp = hip.localPosition; w.Write(hp.x); w.Write(hp.y); w.Write(hp.z);

                foreach (var s in segments)
                {
                    var a = (s.srcChild.position - s.srcBone.position).normalized;
                    var b = (s.dstChild.position - s.dstBone.position).normalized;
                    stats[s.name].Add(Vector3.Angle(a, b));
                }
                // Foot height above the lowest point of the rig, relative to hip height (ground contact check).
                footStats.Add(FootHeight(dst) - FootHeight(src));

                if (f == first)
                {
                    firstFrameReport.AppendLine($"frame0 bodyPosition {pose.bodyPosition} " +
                        $"| gakumas Hips {src.byHuman["Hips"].position} humanScale {src.humanScale:F4} " +
                        $"| pjsk Hips {dst.byHuman["Hips"].position} humanScale {dst.humanScale:F4}");
                    firstFrameReport.AppendLine($"frame0 feet y gakumas L {src.byHuman["LeftFoot"].position.y:F4} R {src.byHuman["RightFoot"].position.y:F4} " +
                        $"| pjsk L {dst.byHuman["LeftFoot"].position.y:F4} R {dst.byHuman["RightFoot"].position.y:F4}");
                }
                if (renderer != null && renderFrames.Contains(f)) renderer.Render(f, f / (float)header.rate);
            }
        }
        Log(firstFrameReport.ToString().TrimEnd());

        // Header for the baked motion.
        var hdr = new StringBuilder("{\n");
        hdr.Append($"  \"format\": \"haruki-pjsk-bone-curves/1\",\n  \"source\": \"{header.clip}\",\n  \"rate\": {header.rate},\n  \"frames\": {last - first + 1},\n");
        hdr.Append($"  \"sourceStartSeconds\": {(first / (double)header.rate).ToString("R", Inv)},\n  \"travel\": \"{travelMode}\",\n  \"travelScale\": {travelScale.ToString("R", Inv)},\n");
        hdr.Append("  \"layout\": \"per frame: for each bone localRotation xyzw (float32), then Position localPosition xyz, then Hip localPosition xyz\",\n");
        hdr.Append("  \"positionUnits\": \"normalized skeleton units: multiply Position by the character height (Position is the PositionNote, its own localPosition is not scaled); Hip is under the scaled Position and is used as is\",\n");
        hdr.Append("  \"bones\": [" + string.Join(", ", outBones.Select(b => "\"" + b.name + "\"")) + "]\n}\n");
        File.WriteAllText(Path.Combine(outDir, motionName + ".pjsk.json"), hdr.ToString());

        // Verification report.
        var rep = new StringBuilder();
        rep.AppendLine($"avatar gakumas valid={src.avatar.isValid} human={src.avatar.isHuman} humanScale={src.humanScale:F4}");
        rep.AppendLine($"avatar pjsk    valid={dst.avatar.isValid} human={dst.avatar.isHuman} humanScale={dst.humanScale:F4}");
        rep.AppendLine($"frames {first}..{last} @ {header.rate} Hz, travel {travelMode} x{travelScale}");
        rep.AppendLine($"twist moved ({string.Join(", ", conv.MoveTwistLabels)}): max child orientation change {conv.MaxHandError:F4} deg; max twist moved {conv.MaxMovedTwist:F1} deg");
        rep.AppendLine("roll bones: " + string.Join(", ", conv.RollRanges.Select(r => $"{r.Key} [{r.Value.x:F1}, {r.Value.y:F1}] deg")));
        rep.AppendLine($"{conv.Carrier.name} x [{conv.PosMin.x:F3}, {conv.PosMax.x:F3}] z [{conv.PosMin.z:F3}, {conv.PosMax.z:F3}] (PJSK originals sampled: x [-3.23, 3.67] z [-2.75, 2.77])");
        rep.AppendLine("segment direction difference, gakumas vs pjsk (degrees)");
        rep.AppendLine("  rest = difference already present in the two T-poses (skeleton geometry); spread = p95 - p5 over the motion");
        rep.AppendLine($"  {"segment",-46} {"rest",7} {"mean",7} {"p95",7} {"max",7} {"spread",7}");
        foreach (var s in segments)
        {
            var v = stats[s.name]; v.Sort();
            float P(double q) => v[Math.Min(v.Count - 1, (int)(v.Count * q))];
            rep.AppendLine($"  {s.name,-46} {restDiff[s.name],7:F2} {v.Average(),7:F2} {P(0.95),7:F2} {v[v.Count - 1],7:F2} {P(0.95) - P(0.05),7:F2}");
        }
        footStats.Sort();
        rep.AppendLine($"lower ankle height difference (pjsk - gakumas, fraction of rest hip height): rest {restFoot:F4}  motion p5 {footStats[(int)(footStats.Count * 0.05)]:F4} median {footStats[footStats.Count / 2]:F4} p95 {footStats[(int)(footStats.Count * 0.95)]:F4}");
        File.WriteAllText(Path.Combine(outDir, motionName + ".report.txt"), rep.ToString());
        Log("\n" + rep);
        renderer?.Dispose();
    }

    private static Quaternion Normalize(Quaternion q)
    {
        var n = Mathf.Sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
        return n > 1e-8f ? new Quaternion(q.x / n, q.y / n, q.z / n, q.w / n) : Quaternion.identity;
    }

    // Lowest foot (ankle) height above y = 0, divided by hip height in the rest pose.
    private static float FootHeight(Rig r)
    {
        var y = Mathf.Min(r.byHuman["LeftFoot"].position.y, r.byHuman["RightFoot"].position.y);
        return y / r.restHipHeight;
    }

    // The target's own conventions for the bones a Humanoid does not know about (skeleton JSON "conventions").
    private sealed class TargetConventions
    {
        private readonly Dictionary<Transform, Quaternion> _rest = new Dictionary<Transform, Quaternion>();
        private readonly (Transform from, Transform to)[] _moves;
        private readonly (Transform bone, Transform twistOf, float ratio)[] _rolls;
        private readonly Vector3 _axis;
        private readonly Vector3 _hipRest;
        public readonly Transform Carrier, Hip;
        public Transform[] RollBones => _rolls.Select(r => r.bone).ToArray();
        public IEnumerable<string> MoveTwistLabels => _moves.Select(m => m.from.name + "->" + m.to.name);
        public readonly Dictionary<string, Vector2> RollRanges = new Dictionary<string, Vector2>();
        public float MaxHandError, MaxMovedTwist;
        public Vector3 PosMin = Vector3.one * 999, PosMax = Vector3.one * -999;

        private static IEnumerable<string> Sides(string pattern) =>
            pattern.Contains("{S}") ? new[] { pattern.Replace("{S}", "Left"), pattern.Replace("{S}", "Right") } : new[] { pattern };

        public TargetConventions(Rig rig, SkeletonJson json)
        {
            var c = json.conventions ?? throw new Exception(json.game + " skeleton has no conventions");
            foreach (var b in json.bones)
                if (rig.byName.TryGetValue(b.name, out var t) && !_rest.ContainsKey(t))
                    _rest[t] = new Quaternion(b.rotation[0], b.rotation[1], b.rotation[2], b.rotation[3]);
            _axis = c.twistAxis != null && c.twistAxis.Length == 3 ? new Vector3(c.twistAxis[0], c.twistAxis[1], c.twistAxis[2]) : Vector3.right;
            _moves = (c.moveTwist ?? new MoveTwistJson[0])
                .SelectMany(m => Sides(m.from).Zip(Sides(m.to), (f, t) => (rig.byName[f], rig.byName[t]))).ToArray();
            _rolls = (c.rollBones ?? new RollJson[0])
                .SelectMany(r => Sides(r.bone).Zip(Sides(r.twistOf), (b, t) => (rig.byName[b], rig.byName[t], r.ratio))).ToArray();
            Carrier = rig.byName[c.travel.carrier];
            Hip = rig.byName[c.travel.hip];
            var hb = json.bones.First(b => b.name == c.travel.hip);
            _hipRest = new Vector3(hb.position[0], hb.position[1], hb.position[2]);
        }

        // Signed twist (degrees) about the twist axis of a rest-relative local rotation.
        private float Twist(Quaternion d)
        {
            var v = new Vector3(d.x, d.y, d.z);
            var a = 2f * Mathf.Atan2(Vector3.Dot(v, _axis), d.w) * Mathf.Rad2Deg;
            return Mathf.Repeat(a + 180f, 360f) - 180f;
        }

        public void Apply(float travelScale)
        {
            foreach (var (from, to) in _moves)
            {
                var childBefore = to.rotation;
                var e = from.localRotation;
                var d = Quaternion.Inverse(_rest[from]) * e;
                var tw = Twist(d);
                var e2 = _rest[from] * (d * Quaternion.Inverse(Quaternion.AngleAxis(tw, _axis)));
                to.localRotation = Quaternion.Inverse(e2) * e * to.localRotation;
                from.localRotation = e2;
                MaxMovedTwist = Mathf.Max(MaxMovedTwist, Mathf.Abs(tw));
                MaxHandError = Mathf.Max(MaxHandError, Quaternion.Angle(childBefore, to.rotation));
            }
            foreach (var (bone, twistOf, ratio) in _rolls)
            {
                var angle = ratio * Twist(Quaternion.Inverse(_rest[twistOf]) * twistOf.localRotation);
                bone.localRotation = _rest[bone] * Quaternion.AngleAxis(angle, _axis);
                RollRanges[bone.name] = RollRanges.TryGetValue(bone.name, out var r) ? new Vector2(Mathf.Min(r.x, angle), Mathf.Max(r.y, angle)) : new Vector2(angle, angle);
            }
            // The carrier (a child of the rig root, identity rotation) takes the horizontal travel; the hip keeps its rest x/z.
            var hipInRoot = Carrier.parent.InverseTransformPoint(Hip.position);
            var travel = new Vector3(hipInRoot.x - _hipRest.x, 0f, hipInRoot.z - _hipRest.z) * travelScale;
            Carrier.localPosition = travel;
            var hipLocalY = Hip.parent.InverseTransformPoint(Hip.position).y;
            Hip.localPosition = new Vector3(_hipRest.x, hipLocalY, _hipRest.z);
            PosMin = Vector3.Min(PosMin, travel); PosMax = Vector3.Max(PosMax, travel);
        }
    }

    private sealed class Segment { public string name; public Transform srcBone, srcChild, dstBone, dstChild; }

    private static readonly string[][] SegmentDefs =
    {
        new[] { "Hips", "Spine" }, new[] { "Spine", "Chest" }, new[] { "Chest", "UpperChest" }, new[] { "UpperChest", "Neck" }, new[] { "Neck", "Head" },
        new[] { "LeftShoulder", "LeftUpperArm" }, new[] { "LeftUpperArm", "LeftLowerArm" }, new[] { "LeftLowerArm", "LeftHand" }, new[] { "LeftHand", "Left Middle Proximal" },
        new[] { "RightShoulder", "RightUpperArm" }, new[] { "RightUpperArm", "RightLowerArm" }, new[] { "RightLowerArm", "RightHand" }, new[] { "RightHand", "Right Middle Proximal" },
        new[] { "LeftUpperLeg", "LeftLowerLeg" }, new[] { "LeftLowerLeg", "LeftFoot" }, new[] { "LeftFoot", "LeftToes" },
        new[] { "RightUpperLeg", "RightLowerLeg" }, new[] { "RightLowerLeg", "RightFoot" }, new[] { "RightFoot", "RightToes" },
        new[] { "Left Index Proximal", "Left Index Intermediate" }, new[] { "Left Thumb Proximal", "Left Thumb Intermediate" },
        new[] { "Right Index Proximal", "Right Index Intermediate" }, new[] { "Right Thumb Proximal", "Right Thumb Intermediate" },
    };

    private static List<Segment> Segments(Rig a, Rig b)
    {
        var list = new List<Segment>();
        foreach (var d in SegmentDefs)
        {
            if (a.byHuman.TryGetValue(d[0], out var a0) && a.byHuman.TryGetValue(d[1], out var a1) &&
                b.byHuman.TryGetValue(d[0], out var b0) && b.byHuman.TryGetValue(d[1], out var b1))
                list.Add(new Segment { name = d[0] + ">" + d[1], srcBone = a0, srcChild = a1, dstBone = b0, dstChild = b1 });
        }
        return list;
    }

    private static Rig BuildRig(string label, SkeletonJson json, DescJson descOverride)
    {
        var rig = new Rig { label = label, transforms = new Transform[json.bones.Length] };
        var skeleton = new List<SkeletonBone>();
        var seen = new HashSet<string>();
        for (int i = 0; i < json.bones.Length; i++)
        {
            var b = json.bones[i];
            var go = new GameObject(b.name);
            var t = go.transform;
            if (b.parent >= 0) t.SetParent(rig.transforms[b.parent], false);
            t.localPosition = new Vector3(b.position[0], b.position[1], b.position[2]);
            t.localRotation = new Quaternion(b.rotation[0], b.rotation[1], b.rotation[2], b.rotation[3]);
            t.localScale = new Vector3(b.scale[0], b.scale[1], b.scale[2]);
            rig.transforms[i] = t;
            if (!seen.Add(b.name)) { Log($"{label}: duplicate transform name '{b.name}' (only the first is used by the avatar)"); continue; }
            rig.byName[b.name] = t;
            skeleton.Add(new SkeletonBone { name = b.name, position = t.localPosition, rotation = t.localRotation, scale = t.localScale });
        }
        rig.root = rig.transforms[0].gameObject;
        var human = json.human.Select(h => new HumanBone { boneName = h.bone, humanName = h.humanName, limit = new HumanLimit { useDefaultValues = true } }).ToArray();
        foreach (var h in json.human) rig.byHuman[h.humanName] = rig.byName[h.bone];
        var d = descOverride ?? json.description ?? new DescJson();
        var desc = new HumanDescription
        {
            human = human, skeleton = skeleton.ToArray(),
            upperArmTwist = d.upperArmTwist, lowerArmTwist = d.lowerArmTwist, upperLegTwist = d.upperLegTwist, lowerLegTwist = d.lowerLegTwist,
            armStretch = d.armStretch, legStretch = d.legStretch, feetSpacing = d.feetSpacing, hasTranslationDoF = d.hasTranslationDoF,
        };
        rig.avatar = AvatarBuilder.BuildHumanAvatar(rig.root, desc);
        rig.avatar.name = label;
        if (!rig.avatar.isValid || !rig.avatar.isHuman) throw new Exception($"{label}: avatar invalid (valid={rig.avatar.isValid} human={rig.avatar.isHuman})");
        var animator = rig.root.AddComponent<Animator>();
        animator.avatar = rig.avatar;
        rig.humanScale = animator.humanScale;
        rig.handler = new HumanPoseHandler(rig.avatar, rig.root.transform);
        rig.restHipHeight = rig.byHuman["Hips"].position.y;
        Log($"{label}: {json.bones.Length} transforms, {human.Length} human bones, humanScale {rig.humanScale:F4}, rest hip height {rig.restHipHeight:F4}");
        return rig;
    }

    // Stick figures of both rigs on a flat ground, rendered side by side. Each rig is shown in place (its hip xz is
    // subtracted) and the PJSK rig is scaled to the source's rest hip height, so the two can be compared directly.
    private sealed class GroundRenderer : IDisposable
    {
        private readonly Rig _a, _b;
        private readonly string _dir;
        private readonly Camera _cam;
        private readonly RenderTexture _rt;
        private readonly Texture2D _tex;
        private readonly List<(Transform from, Transform to, Transform shape, Rig rig)> _sticks = new List<(Transform, Transform, Transform, Rig)>();
        private readonly List<UnityEngine.Object> _owned = new List<UnityEngine.Object>();
        private readonly GameObject _scene;

        public GroundRenderer(Rig a, Rig b, string dir)
        {
            _a = a; _b = b; _dir = dir;
            _scene = new GameObject("GroundScene");
            var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ground.transform.SetParent(_scene.transform); ground.transform.localScale = new Vector3(1, 1, 1);
            ground.GetComponent<Renderer>().sharedMaterial = Mat(new Color(0.32f, 0.34f, 0.37f));
            var grid = new GameObject("Grid"); grid.transform.SetParent(_scene.transform);
            for (int i = -5; i <= 5; i++)
            {
                Line(grid.transform, new Vector3(i * 0.5f, 0.001f, -2.5f), new Vector3(i * 0.5f, 0.001f, 2.5f), 0.005f, new Color(0.4f, 0.42f, 0.45f));
                Line(grid.transform, new Vector3(-2.5f, 0.001f, i * 0.5f), new Vector3(2.5f, 0.001f, i * 0.5f), 0.005f, new Color(0.4f, 0.42f, 0.45f));
            }
            var light = new GameObject("Sun").AddComponent<Light>();
            light.type = LightType.Directional; light.transform.rotation = Quaternion.Euler(50, -30, 0); light.intensity = 0.9f;
            light.shadows = LightShadows.Soft; light.transform.SetParent(_scene.transform);
            RenderSettings.ambientLight = new Color(0.45f, 0.45f, 0.5f);
            _cam = new GameObject("Cam").AddComponent<Camera>();
            _cam.transform.SetParent(_scene.transform);
            _cam.transform.position = new Vector3(0.9f, 1.25f, 3.6f);
            _cam.transform.LookAt(new Vector3(0, 0.8f, 0));
            _cam.fieldOfView = 35; _cam.clearFlags = CameraClearFlags.SolidColor; _cam.backgroundColor = new Color(0.16f, 0.17f, 0.2f);
            _rt = new RenderTexture(1280, 720, 24) { antiAliasing = 4 };
            _cam.targetTexture = _rt;
            _tex = new Texture2D(1280, 720, TextureFormat.RGB24, false);
            Build(a, new Color(0.95f, 0.55f, 0.35f));
            Build(b, new Color(0.35f, 0.7f, 0.95f));
        }

        private Material Mat(Color c)
        {
            var m = new Material(Shader.Find("Standard")) { color = c };
            _owned.Add(m);
            return m;
        }

        private void Line(Transform parent, Vector3 p0, Vector3 p1, float width, Color c)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.transform.SetParent(parent);
            go.transform.position = (p0 + p1) * 0.5f;
            go.transform.rotation = Quaternion.LookRotation(p1 - p0);
            go.transform.localScale = new Vector3(width, 0.001f, (p1 - p0).magnitude);
            go.GetComponent<Renderer>().sharedMaterial = Mat(c);
        }

        private void Build(Rig r, Color c)
        {
            var mat = Mat(c);
            var joint = Mat(c * 0.7f);
            var humanSet = new HashSet<Transform>(r.byHuman.Values);
            foreach (var t in humanSet)
            {
                var parent = t.parent;
                while (parent != null && !humanSet.Contains(parent)) parent = parent.parent;
                if (parent == null) continue;
                var stick = GameObject.CreatePrimitive(PrimitiveType.Capsule);
                UnityEngine.Object.DestroyImmediate(stick.GetComponent<Collider>());
                stick.GetComponent<Renderer>().sharedMaterial = mat;
                stick.transform.SetParent(_scene.transform);
                _sticks.Add((parent, t, stick.transform, r));
                var ball = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                UnityEngine.Object.DestroyImmediate(ball.GetComponent<Collider>());
                ball.GetComponent<Renderer>().sharedMaterial = joint;
                ball.transform.SetParent(stick.transform, false);
                ball.name = "joint";
            }
        }

        public void Render(int frame, float seconds)
        {
            foreach (var (from, to, shape, rig) in _sticks)
            {
                var place = Placement(rig);
                var p0 = place.MultiplyPoint3x4(from.position);
                var p1 = place.MultiplyPoint3x4(to.position);
                var len = Mathf.Max((p1 - p0).magnitude, 1e-4f);
                var thick = rig.byHuman.ContainsValue(to) && (to.name.Contains("Thumb") || to.name.Contains("Index") || to.name.Contains("Middle") || to.name.Contains("Ring") || to.name.Contains("Pinky") || to.name.Contains("Little")) ? 0.012f : 0.035f;
                shape.position = (p0 + p1) * 0.5f;
                shape.rotation = Quaternion.FromToRotation(Vector3.up, (p1 - p0) / len);
                shape.localScale = new Vector3(thick, len * 0.5f, thick);
                var ball = shape.Find("joint");
                ball.position = p1;
                ball.localScale = new Vector3(1.4f, 1.4f * thick / Mathf.Max(len * 0.5f, 1e-4f), 1.4f);
            }
            _cam.Render();
            RenderTexture.active = _rt;
            _tex.ReadPixels(new Rect(0, 0, 1280, 720), 0, 0);
            _tex.Apply();
            RenderTexture.active = null;
            File.WriteAllBytes(Path.Combine(_dir, $"ground_{seconds:000.00}s.png"), _tex.EncodeToPNG());
        }

        // Source (orange) on the left of the picture, PJSK (blue) on the right; each kept in place; PJSK scaled to the source's hip height.
        private Matrix4x4 Placement(Rig rig)
        {
            var hips = rig.byHuman["Hips"].position;
            var scale = rig == _b ? _a.restHipHeight / _b.restHipHeight : 1f;
            var offset = rig == _a ? new Vector3(0.55f, 0, 0) : new Vector3(-0.55f, 0, 0);
            return Matrix4x4.Translate(offset) * Matrix4x4.Scale(Vector3.one * scale) * Matrix4x4.Translate(new Vector3(-hips.x, 0, -hips.z));
        }

        public void Dispose()
        {
            UnityEngine.Object.DestroyImmediate(_scene);
            _rt.Release();
            foreach (var o in _owned) UnityEngine.Object.DestroyImmediate(o);
        }
    }
}
