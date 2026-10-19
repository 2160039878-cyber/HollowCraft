using System;
using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace HollowCraft.Render
{
    internal sealed class RadianceActor : IDisposable
    {
        private static readonly JToken Geometry=SteveRig.ReadJson("radiance-geometry.json");
        private static readonly Dictionary<string,string> Motions=new Dictionary<string,string> {
            {"Knight Ball","radiance_ball"},{"Knight Form","radiance_form"},{"Knight Idle","radiance_idle"},
            {"Knight Unform","radiance_unform"},{"Knight Pull","radiance_pull"},{"Knight Hang","radiance_hang"},
            {"Knight Split Antic","radiance_split_antic"},{"Knight Split","radiance_split"},
            {"Slash1 Antic","radiance_swing_1_antic"},{"Slash1","radiance_swing_1"},
            {"Slash2 Antic","radiance_swing_2_antic"},{"Slash2","radiance_swing_2"} };
        internal static bool CanReplace(string clip)=>clip!=null && Motions.ContainsKey(clip);
        private readonly tk2dSpriteAnimator animator;
        private readonly tk2dBaseSprite sprite;
        private readonly Renderer source;
        private readonly MeshFilter sourceMesh;
        private readonly List<Vector3> quad=new List<Vector3>(4);
        private readonly GameObject streak;
        private readonly Mesh mesh;
        private readonly MeshRenderer streakRenderer;
        private readonly Material streakMaterial;
        private SteveRig skin,shadow,arm;
        private readonly Dictionary<SpriteRenderer,SteveRig> headHalves=new Dictionary<SpriteRenderer,SteveRig>();
        private static readonly float HeadScale=(float)Geometry["sprites"][Geometry["clips"]["Knight Hang"]["frames"][0].ToString()]["scale"];
        public RadianceActor(tk2dSpriteAnimator animator)
        {
            this.animator=animator;sprite=animator.Sprite;source=sprite.GetComponent<Renderer>();sourceMesh=sprite.GetComponent<MeshFilter>();
            streak=new GameObject("HollowCraft split streak");streak.transform.SetParent(sprite.transform,false);
            mesh=new Mesh {name="Protagonist split streak"};mesh.MarkDynamic();streak.AddComponent<MeshFilter>().sharedMesh=mesh;
            streakRenderer=streak.AddComponent<MeshRenderer>();streakMaterial=new Material(Materials.Lines());
            streakRenderer.sharedMaterial=streakMaterial;streak.SetActive(false);
            foreach(var fragment in animator.GetComponentsInChildren<SpriteRenderer>(true))
                if(fragment.sprite!=null && (fragment.sprite.name=="hollow_knight_skull_left" || fragment.sprite.name=="hollow_knight_skull_right"))
                    headHalves.Add(fragment,new SteveRig(headHalf:fragment.sprite.name.EndsWith("left",StringComparison.Ordinal) ? -1 : 1));
        }
        public bool Frame(bool replace=true)
        {
            var clip=animator!=null ? animator.CurrentClip ?? animator.DefaultClip : null;
            string motion=null;
            bool visible=replace && animator!=null && sprite!=null && source!=null && source.enabled
                && sprite.gameObject.activeInHierarchy && clip!=null && Motions.TryGetValue(clip.name,out motion)
                && sprite.Collection!=null && sprite.Collection.name==(string)Geometry["collection"];
            JToken data=visible ? Geometry["sprites"][sprite.spriteId.ToString(CultureInfo.InvariantCulture)] : null;
            visible &= data!=null && sourceMesh!=null && sourceMesh.sharedMesh!=null;
            bool normal=false,extended=false,beam=false;
            if(visible)
            {
                sourceMesh.sharedMesh.GetVertices(quad);visible=quad.Count==4;
                if(visible)
                {
                    string kind=(string)data["kind"];normal=kind=="skin";
                    SteveRig rig=normal ? (skin ??= new SteveRig()) : (shadow ??= new SteveRig(solidVoid:true));
                    float scale=(float)data["scale"]*Mathf.Max(.01f,Mathf.Abs(sprite.transform.lossyScale.y*sprite.scale.y));
                    rig.Frame(Vector3.zero,1/scale,true,animator,source,normal ? sprite.color : new Color(0,0,0,sprite.color.a),
                        false,kind=="ball" ? "radiance_ball" : motion);
                    rig.Mirror(sprite.transform.lossyScale.x*sprite.scale.x<0);
                    rig.AlignHead(World(data["anchor"]),kind!="ball");rig.ShowVoidEyes((bool)data["eyes"]);
                    if(data["hand"] is JArray hand)
                    {
                        arm ??= new SteveRig(solidVoid:true);
                        arm.FrameVoidHand(source,rig.ForwardArmStart,World(hand),sprite.color.a,scale);
                        rig.HideForwardArm();extended=true;
                    }
                    if(data["beam"] is JArray line)
                    {
                        DrawStreak(line,(JArray)data["beamStyle"]);beam=true;
                    }
                }
            }
            if(source!=null) source.forceRenderingOff=visible;
            skin?.Show(visible && normal);shadow?.Show(visible && !normal);arm?.Show(visible && extended);
            if(streak!=null) streak.SetActive(visible && beam);
            bool fragmentsVisible=false;
            foreach(var fragment in headHalves)
            {
                bool active=replace && fragment.Key!=null && fragment.Key.enabled && fragment.Key.gameObject.activeInHierarchy;
                if(fragment.Key!=null) fragment.Key.forceRenderingOff=active;
                // tk2d's cutscene scale is independent of the detached SpriteRenderer transforms.
                if(active) {fragment.Value.FrameHeadHalf(fragment.Key,HeadScale*Mathf.Abs(sprite.scale.y));fragmentsVisible=true;}
                fragment.Value.Show(active);
            }
            if(fragmentsVisible) {skin?.HideHead();shadow?.HideHead();}
            return visible || fragmentsVisible;
        }
        private Vector3 Point(JToken point)=>quad[0]+(quad[1]-quad[0])*(float)point[0]+(quad[2]-quad[0])*(1-(float)point[1]);
        private Vector3 World(JToken point)=>sprite.transform.TransformPoint(Point(point));
        private void DrawStreak(JArray line,JArray style)
        {
            Vector3 a=Point(line[0]),b=Point(line[1]),direction=b-a;
            Vector3 side=new Vector3(-direction.y,direction.x,0).normalized*((float)style[0]*Mathf.Abs(sprite.scale.x));
            float[] along={0,.12f,.5f,.88f,1},fade={0,.7f,1,.7f,0},width={.1f,.5f,1,.5f,.1f},across={-1.5f,-.5f,-.12f,.12f,.5f,1.5f};
            var vertices=new Vector3[30];var colors=new Color[30];var triangles=new List<int>(120);
            for(int y=0;y<5;y++) for(int x=0;x<6;x++)
            {
                int i=y*6+x;vertices[i]=Vector3.Lerp(a,b,along[y])+side*(across[x]*width[y]);
                bool core=(x==2 || x==3) && (float)style[2]>0;
                Color c=core ? Color.white : Color.black;
                c.a=(x==0 || x==5 ? 0 : (float)style[core ? 2 : 1])*fade[y]*sprite.color.a;colors[i]=c;
                if(y<4 && x<5) {triangles.Add(i);triangles.Add(i+1);triangles.Add(i+6);triangles.Add(i+1);triangles.Add(i+7);triangles.Add(i+6);}
            }
            mesh.Clear();mesh.vertices=vertices;mesh.colors=colors;mesh.SetTriangles(triangles,0);mesh.RecalculateBounds();
            streak.layer=source.gameObject.layer;streakMaterial.renderQueue=source.sharedMaterial.renderQueue;
            streakRenderer.sortingLayerID=source.sortingLayerID;streakRenderer.sortingOrder=source.sortingOrder+2;
        }
        public void Dispose()
        {
            if(source!=null) source.forceRenderingOff=false;
            skin?.Dispose();shadow?.Dispose();arm?.Dispose();
            foreach(var fragment in headHalves) {if(fragment.Key!=null) fragment.Key.forceRenderingOff=false;fragment.Value.Dispose();}
            UnityEngine.Object.Destroy(mesh);UnityEngine.Object.Destroy(streakMaterial);UnityEngine.Object.Destroy(streak);
        }
    }
}
