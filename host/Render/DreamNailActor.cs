using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace HollowCraft.Render
{
    internal sealed class DreamNailActor : IDisposable
    {
        private static readonly JToken Geometry=SteveRig.ReadJson("dream-geometry.json")["sprites"];
        private static readonly Dictionary<string,string> Motions=new Dictionary<string,string> {
            {"Warp In","dream_warp"},{"DN Get 1","dream_get_1"},{"DN Get 2","dream_get_2"},
            {"DN Get 3","dream_get_3"},{"DN End","dream_end"} };
        private readonly tk2dSpriteAnimator animator;
        private readonly tk2dBaseSprite sprite;
        private readonly Renderer source;
        private readonly MeshFilter sourceMesh;
        private readonly GameObject effects;
        private readonly MeshRenderer effectRenderer;
        private readonly Mesh mesh;
        private readonly tk2dSprite glow;
        private readonly MaterialPropertyBlock properties=new MaterialPropertyBlock();
        private readonly List<Vector3> quad=new List<Vector3>(4);
        private readonly List<Vector2> uv=new List<Vector2>(4);
        private readonly List<Color32> colors=new List<Color32>(4);
        private readonly SteveRig rig=new SteveRig();
        private string lastSprite;
        private Vector3 lastScale;
        private Color32 lastColor;
        public DreamNailActor(tk2dSpriteAnimator animator)
        {
            this.animator=animator; sprite=animator.Sprite;
            source=sprite.GetComponent<Renderer>(); sourceMesh=sprite.GetComponent<MeshFilter>();
            effects=new GameObject("HollowCraft retained Dream Nail effects");
            effects.transform.SetParent(sprite.transform,false);
            mesh=new Mesh { name="Native Dream Nail and teleport regions" }; mesh.MarkDynamic();
            effects.AddComponent<MeshFilter>().sharedMesh=mesh;
            effectRenderer=effects.AddComponent<MeshRenderer>(); effects.SetActive(false);
            var glowObject=new GameObject("HollowCraft Dream arrival light");glowObject.transform.SetParent(sprite.transform,false);
            glow=glowObject.AddComponent<tk2dSprite>();
            var light=animator.GetClipByName("Warp In").frames[0];glow.SetSprite(light.spriteCollection,light.spriteId);
            glowObject.SetActive(false);
        }
        public bool Frame(bool replace=true)
        {
            string motion=null;
            var clip=animator!=null ? animator.CurrentClip ?? animator.DefaultClip : null;
            bool visible=replace && animator!=null && sprite!=null && source!=null && source.enabled
                && animator.gameObject.activeInHierarchy && clip!=null && Motions.TryGetValue(clip.name,out motion);
            string name=visible ? sprite.GetCurrentSpriteDef()?.name : null;
            JToken geometry=name==null ? null : Geometry[name];
            visible &= geometry!=null && (bool)geometry["replace"] && sourceMesh!=null && sourceMesh.sharedMesh!=null;
            if(visible)
            {
                sourceMesh.sharedMesh.GetVertices(quad); sourceMesh.sharedMesh.GetUVs(0,uv); sourceMesh.sharedMesh.GetColors(colors);
                visible=quad.Count==4 && uv.Count==4 && colors.Count==4;
                if(visible)
                {
                    if(lastSprite!=name || lastScale!=sprite.scale || !lastColor.Equals(colors[0]))
                    {
                        var vertices=new List<Vector3>(); var texcoords=new List<Vector2>();
                        var vertexColors=new List<Color32>(); var triangles=new List<int>();
                        foreach(JArray polygon in geometry["keep"])
                        {
                            int first=vertices.Count;
                            foreach(JArray point in polygon)
                            {
                                float x=(float)point[0], y=1-(float)point[1];
                                vertices.Add(Point(x,y));
                                texcoords.Add(uv[0]+(uv[1]-uv[0])*(float)point[3]+(uv[2]-uv[0])*(1-(float)point[4]));
                                Color32 color=colors[0];color.a=(byte)Mathf.RoundToInt(color.a*(float)point[2]);vertexColors.Add(color);
                            }
                            for(int i=1;i+1<polygon.Count;i++) { triangles.Add(first);triangles.Add(first+i);triangles.Add(first+i+1); }
                        }
                        mesh.Clear();mesh.SetVertices(vertices);mesh.SetUVs(0,texcoords);mesh.SetColors(vertexColors);
                        mesh.SetTriangles(triangles,0);mesh.RecalculateBounds();
                        lastSprite=name;lastScale=sprite.scale;lastColor=colors[0];
                    }
                    effects.layer=source.gameObject.layer; effectRenderer.sharedMaterial=source.sharedMaterial;
                    effectRenderer.sortingLayerID=source.sortingLayerID;effectRenderer.sortingOrder=source.sortingOrder+1;
                    source.GetPropertyBlock(properties);effectRenderer.SetPropertyBlock(properties);
                    float scale=Mathf.Max(.01f,Mathf.Abs(sprite.transform.lossyScale.y*sprite.scale.y));
                    Vector3 feet=sprite.transform.TransformPoint(Vector3.Scale(new Vector3(0,-1.390625f,0),sprite.scale));
                    if(geometry["floor"] is JValue floor && floor.Type!=JTokenType.Null)
                        feet=sprite.transform.TransformPoint(new Vector3(0,Point(.5f,1-(float)floor).y,0));
                    rig.Frame(feet,Coords.K/scale,sprite.transform.lossyScale.x*sprite.scale.x<0,animator,source,sprite.color,false,motion);
                    if(geometry["hand"] is JArray hand)
                        rig.PointRightHand(sprite.transform.TransformPoint(Point((float)hand[0],1-(float)hand[1])));
                }
            }
            if(source!=null) source.forceRenderingOff=visible;
            if(effects!=null) effects.SetActive(visible);
            if(glow!=null)
            {
                int frame=animator!=null && animator.CurrentClip!=null ? animator.CurrentFrame : 0;
                bool arriving=visible && clip.name=="Warp In" && frame>=2 && frame<=3;
                glow.gameObject.SetActive(arriving);
                if(arriving)
                {
                    // The first native frame contains only light; reuse it while the block body appears.
                    bool first=frame==2;
                    glow.gameObject.layer=source.gameObject.layer;
                    glow.transform.localPosition=new Vector3(0,.35f,0);glow.scale=Vector3.one*(first ? 1f : .65f);
                    glow.color=new Color(sprite.color.r,sprite.color.g,sprite.color.b,sprite.color.a*(first ? .9f : .35f));
                    var renderer=glow.GetComponent<Renderer>();renderer.sortingLayerID=source.sortingLayerID;renderer.sortingOrder=source.sortingOrder+2;
                }
            }
            rig.Show(visible);
            return visible;
        }
        private Vector3 Point(float x,float y)=>quad[0]+(quad[1]-quad[0])*x+(quad[2]-quad[0])*y;
        public void Dispose()
        {
            if(source!=null) source.forceRenderingOff=false;
            rig.Dispose();UnityEngine.Object.Destroy(mesh);UnityEngine.Object.Destroy(effects);
            if(glow!=null) UnityEngine.Object.Destroy(glow.gameObject);
        }
    }
}
