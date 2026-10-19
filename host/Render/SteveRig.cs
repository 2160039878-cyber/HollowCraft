using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace HollowCraft.Render
{
    // The streamed model and Blender use these same cuboids, UVs and motion curves.
    internal sealed class SteveRig : IDisposable
    {
        private const float Unit = 1.8f / 32;
        private static readonly JObject Model = ReadJson("model.json"), Motions = ReadJson("poses.json");
        private static Texture2D skin;
        // Death Glow uses Spell Effects frames; it is light, not another Shade body.
        private static readonly Dictionary<string,string> ShadeMotions = new Dictionary<string,string> {
            {"Idle","idle"},{"Cast","cast"},{"Death","die"},{"Depart","teleport"},{"Fly","air"},{"Slash","slash"},
            {"Startle","hurt"},{"TurnToFly","turn"},{"Slash Antic","charge"},{"Slash CD","idle"},
            {"Cast Antic","charge"},{"Death Start","die"},{"Cast Charge","charge"},
            {"Appear","appear"},{"Retreat Start","air"},{"Retreat End","land"},{"TurnToIdle","turn"},
            {"Quake Antic","quake_antic"},{"Quake Start","quake"},{"Quake","quake"},{"Quake Land","hard_land"},
            {"Scream Antic","scream"},{"Scream","scream"},{"Scream End","idle"} };
        private readonly GameObject root;
        private readonly Transform poseRoot;
        private readonly Dictionary<string, Transform> bones = new Dictionary<string, Transform>();
        private readonly List<Part> parts = new List<Part>();
        private readonly int headHalf;
        private readonly Vector3 rightHandEnd;
        private readonly Vector3 forwardArmSocket;
        private readonly Vector3 rightLegPosition, leftLegPosition;
        private readonly float rightArmLength;
        private readonly MaterialPropertyBlock properties = new MaterialPropertyBlock();
        private readonly MaterialPropertyBlock eyeProperties = new MaterialPropertyBlock();
        private sealed class Part
        {
            public Mesh Mesh;
            public MeshRenderer Renderer;
            public Vector3[] Normals;
            public bool Head, Eye, Arm, RightArm;
            public readonly List<int> Triangles = new List<int>(36);
            public int VisibleFaces = -1;
            public Vector3[] UncutVertices;
            public Vector2[] UncutUv;
            public Color32[] UncutColors;
            public bool Cropped;
        }
        private static Stream Resource(string name) => typeof(SteveRig).Assembly.GetManifestResourceStream("HollowCraft.Steve." + name)
            ?? throw new InvalidDataException("Missing embedded Steve asset: " + name);
        internal static JObject ReadJson(string name)
        {
            using (var reader = new StreamReader(Resource(name))) return JObject.Parse(reader.ReadToEnd());
        }
        internal static Texture2D ReadTexture(string name)
        {
            using (var source = Resource(name))
            using (var bytes = new MemoryStream())
            {
                source.CopyTo(bytes);
                var texture = new Texture2D(2, 2, TextureFormat.RGBA32, false) { name = "HollowCraft " + name, filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
                if (!texture.LoadImage(bytes.ToArray())) throw new InvalidDataException("Invalid Steve asset: " + name);
                return texture;
            }
        }
        private static bool HeadClip(string name) => name != null && name.StartsWith("Death Head ", StringComparison.Ordinal);
        public static bool CanReplaceClip(string name, bool shade, int frame) => name != null
            // This legacy clip mixes four Knight body frames with two crystal-only frames.
            && (shade ? ShadeMotions.ContainsKey(name) : (name!="Hit Crack Appear" || frame!=1 && frame!=5)
                && (Motions["aliases"][name] != null || HeadClip(name)));
        private static Vector3 ReadVector(JToken values) => new Vector3((float)values[0], (float)values[1], (float)values[2]);
        private static Vector3 ConvertPoint(Vector3 value) => new Vector3(value.x, -value.y, value.z) * Unit;
        public SteveRig(bool solidVoid = false,int headHalf=0)
        {
            if(headHalf < -1 || headHalf > 1) throw new ArgumentOutOfRangeException(nameof(headHalf));
            this.headHalf=headHalf;
            if (skin == null) skin = ReadTexture("steve.png");
            root = new GameObject("HollowCraft Steve replica");
            UnityEngine.Object.DontDestroyOnLoad(root);
            poseRoot = new GameObject("Pose").transform;
            poseRoot.SetParent(root.transform, false);
            var definitions = new Dictionary<string, JToken>();
            foreach (JToken definition in Model["parts"]) definitions[(string)definition["name"]] = definition;
            foreach (JToken boneName in Motions["bones"])
            {
                string name = (string)boneName;
                var bone = new GameObject(name).transform;
                bone.SetParent(poseRoot, false);
                bone.localPosition = ConvertPoint(ReadVector(definitions[name]["pivot"])) + Vector3.up * (24 * Unit);
                bones[name] = bone;
            }
            rightLegPosition = bones["right_leg"].localPosition;
            leftLegPosition = bones["left_leg"].localPosition;
            JToken armCube = definitions["right_arm"]["cube"];
            Vector3 armSize = ReadVector(armCube["size"]);
            rightArmLength = armSize.y * Unit;
            rightHandEnd = bones["right_arm"].localPosition + ConvertPoint(ReadVector(armCube["origin"])
                + new Vector3(armSize.x / 2, armSize.y, armSize.z / 2));
            JToken bodyCube=definitions["body"]["cube"];Vector3 bodyOrigin=ReadVector(bodyCube["origin"]),bodySize=ReadVector(bodyCube["size"]);
            float shoulderY=(float)definitions["left_arm"]["pivot"][1]-(float)definitions["body"]["pivot"][1];
            forwardArmSocket=ConvertPoint(new Vector3(bodyOrigin.x+bodySize.x,shoulderY,bodyOrigin.z+bodySize.z/2));
            foreach (var entry in definitions)
            {
                if (solidVoid && !bones.ContainsKey(entry.Key)) continue;
                string owner = bones.ContainsKey(entry.Key) ? entry.Key : (string)entry.Value["parent"];
                if(headHalf!=0 && owner!="head") continue;
                var obj = new GameObject(entry.Key + " mesh");
                obj.transform.SetParent(bones[owner], false);
                Mesh mesh = BuildCube(entry.Value["cube"], out Vector3[] normals);
                if(headHalf!=0) CutHeadHalf(mesh,headHalf);
                obj.AddComponent<MeshFilter>().sharedMesh = mesh;
                var renderer = obj.AddComponent<MeshRenderer>();
                renderer.sharedMaterial = Materials.Get(Materials.Kind.Cutout, solidVoid ? Texture2D.whiteTexture : skin);
                parts.Add(new Part { Mesh = mesh, Renderer = renderer, Normals = normals, Head = owner == "head", Arm = owner == "right_arm" || owner == "left_arm", RightArm = owner == "right_arm" });
            }
            foreach (float x in new[] { -3f, 1f })
            {
                var eye = new GameObject("Shade eye"); eye.transform.SetParent(bones["head"], false);
                var cube = new JObject { ["origin"]=new JArray(x,-4,-4.03f),["size"]=new JArray(2,1,.02f),["uv"]=new JArray(0,0) };
                Mesh mesh=BuildCube(cube,out Vector3[] normals);
                eye.AddComponent<MeshFilter>().sharedMesh=mesh;
                var renderer=eye.AddComponent<MeshRenderer>();
                renderer.sharedMaterial=Materials.Get(Materials.Kind.Cutout,Texture2D.whiteTexture);
                parts.Add(new Part { Mesh=mesh,Renderer=renderer,Normals=normals,Head=true,Eye=true });
            }
            root.SetActive(false);
        }
        private static Mesh BuildCube(JToken cube, out Vector3[] normals)
        {
            Vector3 origin = ReadVector(cube["origin"]), size = ReadVector(cube["size"]);
            float expand = (float?)cube["deformation"] ?? 0;
            Vector3 lo = origin - Vector3.one * expand, hi = origin + size + Vector3.one * expand;
            bool mirror = (bool?)cube["mirror"] ?? false;
            if (mirror) { float old = lo.x; lo.x = hi.x; hi.x = old; }
            Vector3[] corners = { new Vector3(lo.x,lo.y,lo.z),new Vector3(hi.x,lo.y,lo.z),new Vector3(hi.x,hi.y,lo.z),new Vector3(lo.x,hi.y,lo.z),
                new Vector3(lo.x,lo.y,hi.z),new Vector3(hi.x,lo.y,hi.z),new Vector3(hi.x,hi.y,hi.z),new Vector3(lo.x,hi.y,hi.z) };
            int[][] faces = { new[]{5,4,0,1},new[]{2,3,7,6},new[]{0,4,7,3},new[]{1,0,3,2},new[]{5,1,2,6},new[]{4,5,6,7} };
            float u=(float)cube["uv"][0],v=(float)cube["uv"][1],w=size.x,h=size.y,d=size.z;
            float u1=u+d,u2=u+d+w,u3=u+d+w+w,u4=u+d+w+d,u5=u+d+w+d+w,v1=v+d,v2=v+d+h;
            float[][] rects={new[]{u1,v,u2,v1},new[]{u2,v1,u3,v},new[]{u,v1,u1,v2},new[]{u1,v1,u2,v2},new[]{u2,v1,u4,v2},new[]{u4,v1,u5,v2}};
            var vertices = new Vector3[24]; var uv = new Vector2[24]; var colors = new Color32[24]; normals = new Vector3[6];
            Vector3 center = ConvertPoint(origin + size / 2);
            for (int f=0; f<6; f++)
            {
                float[] r=rects[f]; Vector2[] faceUv={new Vector2(r[2],r[1]),new Vector2(r[0],r[1]),new Vector2(r[0],r[3]),new Vector2(r[2],r[3])};
                for (int j=0; j<4; j++)
                {
                    vertices[f*4+j]=ConvertPoint(corners[faces[f][j]]);
                    uv[f*4+j]=new Vector2(faceUv[j].x/64,1-faceUv[j].y/64);
                    colors[f*4+j]=new Color32(255,255,255,255);
                }
                Vector3 normal=Vector3.Cross(vertices[f*4+1]-vertices[f*4],vertices[f*4+2]-vertices[f*4]).normalized;
                if (Vector3.Dot(normal,vertices[f*4]-center)<0) normal=-normal;
                normals[f]=normal;
            }
            var mesh=new Mesh { name="Steve cuboid", vertices=vertices, uv=uv, colors32=colors };
            mesh.MarkDynamic(); mesh.RecalculateBounds();
            return mesh;
        }
        private static float Value(JToken motion, string key, float phase, float fallback=0)
        {
            JToken curve=motion["tracks"][key];
            if (curve==null) return fallback;
            for(int i=1;i<curve.Count();i++)
            {
                float b=(float)curve[i][0];
                if(phase>b) continue;
                float a=(float)curve[i-1][0],u=Mathf.Clamp01((phase-a)/(b-a));
                return Mathf.LerpUnclamped((float)curve[i-1][1],(float)curve[i][1],u*u*(3-2*u));
            }
            return (float)curve.Last[1];
        }
        public void Show(bool visible) { if(root!=null && root.activeSelf!=visible) root.SetActive(visible); }
        private static void CutHeadHalf(Mesh mesh,int side)
        {
            var vertices=mesh.vertices;var uv=mesh.uv;
            for(int i=0;i<vertices.Length;i++)
            {
                if(vertices[i].x*side>=0) continue;
                for(int j=i/4*4;j<i/4*4+4;j++)
                    if(vertices[j].x*side>0 && Mathf.Abs(vertices[i].y-vertices[j].y)<1e-5f && Mathf.Abs(vertices[i].z-vertices[j].z)<1e-5f)
                    { uv[i]=Vector2.Lerp(uv[i],uv[j],.5f);break; }
                vertices[i].x=0;
            }
            mesh.vertices=vertices;mesh.uv=uv;mesh.RecalculateBounds();
        }
        internal void FrameHeadHalf(SpriteRenderer source,float scale)
        {
            Frame(Vector3.zero,1/scale,false,null,source,source.color,false,"idle",0f);
            poseRoot.localRotation=Quaternion.identity;poseRoot.localPosition=Vector3.zero;
            Vector3 worldScale=source.transform.lossyScale*scale;
            if(source.flipX) worldScale.x=-worldScale.x;if(source.flipY) worldScale.y=-worldScale.y;
            root.transform.localScale=worldScale;
            root.transform.position+=source.bounds.center-bones["head"].TransformPoint(new Vector3(headHalf*2*Unit,4*Unit,0));
            var camera=GameCameras.instance.mainCamera;
            foreach(var part in parts)
            {
                part.Renderer.enabled=part.Head && !part.Eye;
                UpdateFaces(part,-camera.transform.forward);
            }
        }
        internal void HideHead() { foreach(var part in parts) if(part.Head) part.Renderer.enabled=false; }
        internal static float ClipTime(tk2dSpriteAnimator animator)
        {
            var clip=animator!=null ? animator.CurrentClip : null;
            if(clip==null) return 0;
            float time=animator.ClipTimeSeconds,fps=animator.ClipFps>0 ? animator.ClipFps : clip.fps;
            float frame=time*fps;
            // LoopSection repeats only the tail; wrapping the full duration replays its entry motion.
            if(clip.wrapMode==tk2dSpriteAnimationClip.WrapMode.LoopSection) frame=animator.CurrentFrame+Mathf.Repeat(frame,1);
            return clip.fps>0 ? frame/clip.fps : time;
        }
        public void Frame(Vector3 feet,float blocksPerUnit,bool facingRight,tk2dSpriteAnimator animator,Renderer source,Color tint,bool shade=false,string motionOverride=null,float? phaseOverride=null)
        {
            var clip=animator!=null ? animator.CurrentClip ?? animator.DefaultClip : null;
            string motionName=motionOverride ?? (shade && clip!=null && ShadeMotions.TryGetValue(clip.name,out string shadeMotion) ? shadeMotion
                : (string)Motions["aliases"][clip?.name ?? "Idle"] ?? "idle");
            JToken motion=Motions["poses"][motionName];
            bool headOnly=HeadClip(clip?.name) || (bool?)motion["headOnly"]==true;
            bool voidEyes=shade || (bool?)motion["voidEyes"]==true;
            float duration=clip!=null && clip.fps>0 ? clip.frames.Length/clip.fps : 1;
            float t=phaseOverride ?? ClipTime(animator)/Mathf.Max(.001f,duration);
            bool loop=clip!=null && (clip.wrapMode==tk2dSpriteAnimationClip.WrapMode.Loop || clip.wrapMode==tk2dSpriteAnimationClip.WrapMode.LoopSection || clip.wrapMode==tk2dSpriteAnimationClip.WrapMode.PingPong);
            t=loop ? t-Mathf.Floor(t) : Mathf.Clamp01(t);
            root.transform.position=feet;
            root.transform.localScale=Vector3.one / blocksPerUnit;
            root.transform.rotation=motionOverride!=null && source!=null ? source.transform.rotation : Quaternion.identity;
            Quaternion rotation=Quaternion.AngleAxis(Value(motion,"root.roll",t)*(facingRight?1:-1),Vector3.forward)
                * Quaternion.AngleAxis(Value(motion,"root.yaw",t)+Value(motion,"root.yawSide",t)*(facingRight?-1:1)+(facingRight?-90:90),Vector3.up);
            float sy=Value(motion,"root.sy",t,1);
            poseRoot.localRotation=rotation;
            poseRoot.localScale=new Vector3(1,sy,1);
            poseRoot.localPosition=Vector3.up*(.9f+Value(motion,"root.dy",t))-rotation*(Vector3.up*(.9f*sy));
            if (headOnly && source!=null)
            {
                poseRoot.localRotation=Quaternion.Inverse(root.transform.rotation)*source.transform.rotation*rotation;
                root.transform.position=source.bounds.center-(root.transform.rotation*poseRoot.localRotation)*(Vector3.up*(1.575f/blocksPerUnit));
            }
            foreach(var bone in bones)
            {
                bone.Value.localScale=Vector3.one;
                bone.Value.localRotation=Quaternion.AngleAxis(-Value(motion,bone.Key+".rz",t),Vector3.forward)
                    *Quaternion.AngleAxis(Value(motion,bone.Key+".ry",t),Vector3.up)*Quaternion.AngleAxis(-Value(motion,bone.Key+".rx",t),Vector3.right);
            }
            properties.Clear(); properties.SetColor("_Color",shade ? new Color(.03f,.03f,.04f,tint.a) : tint);
            eyeProperties.SetColor("_Color",new Color(1,1,1,tint.a));
            if(source!=null && source.sharedMaterial!=null && source.sharedMaterial.HasProperty("_FlashAmount"))
                properties.SetFloat("_FlashAmount",source.sharedMaterial.GetFloat("_FlashAmount"));
            if(motion["tracks"]["flash"]!=null)
            { properties.SetColor("_FlashColor",Color.white);properties.SetFloat("_FlashAmount",Value(motion,"flash",t)); }
            Camera camera=GameCameras.instance!=null ? GameCameras.instance.mainCamera : Camera.main;
            Vector3 towardCamera=camera!=null ? -camera.transform.forward : Vector3.back;
            foreach(var part in parts)
            {
                part.Renderer.enabled=(!headOnly || part.Head) && (!part.Eye || voidEyes);
                if(source!=null) {
                    part.Renderer.gameObject.layer=source.gameObject.layer;
                    part.Renderer.sortingLayerID=source.sortingLayerID; part.Renderer.sortingOrder=source.sortingOrder;
                }
                part.Renderer.SetPropertyBlock(part.Eye ? eyeProperties : properties);
                UpdateFaces(part, towardCamera);
            }
        }
        internal void AlignBottom(float y)
        {
            float bottom=float.PositiveInfinity;
            foreach(var part in parts) if(part.Renderer.enabled && !part.Eye) bottom=Mathf.Min(bottom,part.Renderer.bounds.min.y);
            if(!float.IsInfinity(bottom)) root.transform.position+=Vector3.up*(y-bottom);
        }
        internal void AlignHead(Vector3 point,bool eyes)
        {
            Vector3 anchor=bones["head"].TransformPoint(new Vector3(0,(eyes ? 3.5f : 4f)*Unit,eyes ? -4.04f*Unit : 0));
            root.transform.position+=point-anchor;
        }
        internal void Mirror(bool mirrored)
        {
            Vector3 scale=root.transform.localScale;scale.x=Mathf.Abs(scale.x)*(mirrored ? -1 : 1);root.transform.localScale=scale;
            Camera camera=GameCameras.instance!=null ? GameCameras.instance.mainCamera : Camera.main;
            foreach(var part in parts) UpdateFaces(part,camera!=null ? -camera.transform.forward : Vector3.back);
        }
        internal void ShowVoidEyes(bool visible) { foreach(var part in parts) if(part.Eye) part.Renderer.enabled=visible; }
        internal void HideForwardArm() { foreach(var part in parts) if(part.Arm && !part.RightArm) part.Renderer.enabled=false; }
        internal Vector3 ForwardArmStart => bones["body"].TransformPoint(forwardArmSocket);
        internal void PointRightHand(Vector3 point)
        {
            Transform arm=bones["right_arm"];
            Vector3 end=rightHandEnd-arm.localPosition;
            Vector3 target=arm.parent.InverseTransformPoint(point)-arm.localPosition;
            float stretch=Mathf.Sqrt(Mathf.Max(.000001f,target.sqrMagnitude-end.x*end.x-end.z*end.z))/Mathf.Abs(end.y);
            arm.localScale=new Vector3(1,stretch,1);
            arm.localRotation=Quaternion.FromToRotation(Vector3.Scale(end,arm.localScale),target);
            Camera camera=GameCameras.instance!=null ? GameCameras.instance.mainCamera : Camera.main;
            foreach(var part in parts) if(part.RightArm) UpdateFaces(part,camera!=null ? -camera.transform.forward : Vector3.back);
        }
        public void FrameVoidLord(SpriteRenderer head, SpriteRenderer body, SpriteRenderer arms)
        {
            // The installed head artwork uses 64 pixels/unit. Its eye group is centred at
            // (170.5,286) in the 310x364 canvas; match this anchor instead of its long horns.
            float scale = Mathf.Abs(head.transform.lossyScale.x) * (81f / 64f) / (6 * Unit);
            Quaternion rotation = head.transform.rotation;
            root.transform.localScale = Vector3.one * scale;
            root.transform.rotation = rotation;
            root.transform.position = head.transform.TransformPoint(new Vector3(15.5f / 64f, -104f / 64f, 0))
                - rotation * (new Vector3(0, 1.546875f, -4.04f * Unit) * scale);
            poseRoot.localPosition = Vector3.zero;
            poseRoot.localRotation = Quaternion.identity;
            poseRoot.localScale = Vector3.one;
            foreach (var bone in bones) bone.Value.localRotation = Quaternion.identity;
            // Native sprite changes drive the same small pose changes in the block arms.
            float wave = arms.sprite != null && arms.sprite.name.EndsWith("0001", StringComparison.Ordinal) ? 4f : 0f;
            bones["right_arm"].localRotation = Quaternion.AngleAxis(-125f - wave, Vector3.forward);
            bones["left_arm"].localRotation = Quaternion.AngleAxis(65f + wave, Vector3.forward);
            bones["right_leg"].localRotation = Quaternion.AngleAxis(-4f, Vector3.forward);
            bones["left_leg"].localRotation = Quaternion.AngleAxis(4f, Vector3.forward);
            Vector3 hipInset = Vector3.up * (2 * Unit * Mathf.Sin(4 * Mathf.Deg2Rad));
            bones["right_leg"].localPosition = rightLegPosition + hipInset;
            bones["left_leg"].localPosition = leftLegPosition + hipInset;
            Camera camera = GameCameras.instance != null ? GameCameras.instance.mainCamera : Camera.main;
            Vector3 towardCamera = camera != null ? -camera.transform.forward : Vector3.back;
            foreach (var part in parts)
            {
                SpriteRenderer source = part.Head ? head : part.Arm ? arms : body;
                part.Renderer.gameObject.layer = source.gameObject.layer;
                part.Renderer.enabled = source.enabled && source.sprite != null && source.gameObject.activeInHierarchy;
                part.Renderer.sortingLayerID = source.sortingLayerID;
                part.Renderer.sortingOrder = source.sortingOrder;
                properties.Clear();
                properties.SetColor("_Color", part.Eye ? new Color(1, 1, 1, source.color.a) : new Color(0, 0, 0, source.color.a));
                part.Renderer.SetPropertyBlock(properties);
                UpdateFaces(part, towardCamera);
            }
        }
        public void FrameVoidHand(Renderer source, Vector3 start, Vector3 end, float alpha,float? widthScale=null)
        {
            Vector3 direction = end - start;
            float scale = direction.magnitude / rightArmLength;
            Quaternion rotation = direction.sqrMagnitude > 1e-8f ? Quaternion.FromToRotation(Vector3.down, direction.normalized) : Quaternion.identity;
            root.transform.localScale = new Vector3(widthScale ?? scale,scale,widthScale ?? scale);
            root.transform.rotation = rotation;
            root.transform.position = end - rotation * Vector3.Scale(rightHandEnd,root.transform.localScale);
            poseRoot.localPosition = Vector3.zero;
            poseRoot.localRotation = Quaternion.identity;
            poseRoot.localScale = Vector3.one;
            bones["right_arm"].localRotation = Quaternion.identity;
            properties.Clear(); properties.SetColor("_Color", new Color(0, 0, 0, alpha));
            Camera camera = GameCameras.instance != null ? GameCameras.instance.mainCamera : Camera.main;
            Vector3 towardCamera = camera != null ? -camera.transform.forward : Vector3.back;
            foreach (var part in parts)
            {
                part.Renderer.enabled = part.RightArm && direction.sqrMagnitude > 1e-8f;
                if (!part.RightArm) continue;
                part.Renderer.gameObject.layer = source.gameObject.layer;
                part.Renderer.sortingLayerID = source.sortingLayerID;
                part.Renderer.sortingOrder = source.sortingOrder + 1;
                part.Renderer.SetPropertyBlock(properties);
                UpdateFaces(part, towardCamera);
            }
        }
        private static void UpdateFaces(Part part, Vector3 towardCamera)
        {
            if(part.Cropped)
            {
                part.Mesh.Clear();part.Mesh.vertices=part.UncutVertices;part.Mesh.uv=part.UncutUv;part.Mesh.colors32=part.UncutColors;
                part.Mesh.RecalculateBounds();part.Cropped=false;part.VisibleFaces=-1;
            }
            int mask = 0;
            for (int f = 0; f < 6; f++)
                if (Vector3.Dot(part.Renderer.transform.TransformVector(part.Normals[f]), towardCamera) > 1e-5f) mask |= 1 << f;
            if (mask == part.VisibleFaces) return;
            // Native sprite shaders disable face culling. Select visible cuboid faces explicitly.
            part.VisibleFaces = mask; part.Triangles.Clear();
            for (int f = 0; f < 6; f++) if ((mask & (1 << f)) != 0)
            {
                int a = f * 4;
                part.Triangles.Add(a); part.Triangles.Add(a + 1); part.Triangles.Add(a + 2);
                part.Triangles.Add(a); part.Triangles.Add(a + 2); part.Triangles.Add(a + 3);
            }
            part.Mesh.SetTriangles(part.Triangles, 0, false);
        }
        internal void CropBelow(float worldY)
        {
            // ponytail: short single-actor cutscene; pool these buffers if clipping is reused for crowds.
            foreach(var part in parts)
            {
                if(!part.Renderer.enabled) continue;
                if(part.UncutVertices==null) {part.UncutVertices=part.Mesh.vertices;part.UncutUv=part.Mesh.uv;part.UncutColors=part.Mesh.colors32;}
                var vertices=new List<Vector3>();var uv=new List<Vector2>();var colors=new List<Color32>();var triangles=new List<int>();
                var below=new List<World.Clip.Vert>();var above=new List<World.Clip.Vert>();var transform=part.Renderer.transform;
                for(int i=0;i<part.Triangles.Count;i+=3)
                {
                    int ia=part.Triangles[i],ib=part.Triangles[i+1],ic=part.Triangles[i+2];
                    Vector3 a=transform.TransformPoint(part.UncutVertices[ia]),b=transform.TransformPoint(part.UncutVertices[ib]),c=transform.TransformPoint(part.UncutVertices[ic]);
                    World.Clip.Split(World.Clip.FromTriangle(a.x,a.y,a.z,b.x,b.y,b.z,c.x,c.y,c.z),1,worldY,below,above);
                    int first=vertices.Count;
                    foreach(var v in above)
                    {
                        vertices.Add(transform.InverseTransformPoint(new Vector3(v.X,v.Y,v.Z)));
                        uv.Add(part.UncutUv[ia]*v.B0+part.UncutUv[ib]*v.B1+part.UncutUv[ic]*v.B2);
                        colors.Add(new Color32(255,255,255,255));
                    }
                    for(int j=1;j+1<above.Count;j++) {triangles.Add(first);triangles.Add(first+j);triangles.Add(first+j+1);}
                }
                part.Mesh.Clear();part.Mesh.SetVertices(vertices);part.Mesh.SetUVs(0,uv);part.Mesh.SetColors(colors);
                part.Mesh.SetTriangles(triangles,0);part.Mesh.RecalculateBounds();part.Cropped=true;
            }
        }
        public void Dispose()
        {
            Show(false);
            foreach(var part in parts) UnityEngine.Object.Destroy(part.Mesh);
            UnityEngine.Object.Destroy(root);
        }
    }
}
