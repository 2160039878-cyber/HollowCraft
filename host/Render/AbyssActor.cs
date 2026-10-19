using System;
using System.Collections.Generic;
using UnityEngine;

namespace HollowCraft.Render
{
    internal sealed class AbyssActor : IDisposable
    {
        private static readonly Dictionary<string,string> Motions=new Dictionary<string,string> {
            {"Knight Collapse","abyss_collapse"},{"Climb 1","abyss_climb_1"},{"Climb 2","abyss_climb_2"},
            {"Climb 3","abyss_climb_3"},{"Climb 4","abyss_climb_4"},{"Knight Grab","abyss_grab"},
            {"Knight Falter","abyss_falter"},{"Knight Fall","abyss_fall"} };
        internal static bool CanReplace(string clip)=>clip!=null && Motions.ContainsKey(clip);
        private readonly tk2dSpriteAnimator animator;
        private readonly tk2dBaseSprite sprite;
        private readonly Renderer source;
        private readonly SteveRig rig=new SteveRig();
        internal AbyssActor(tk2dSpriteAnimator animator)
        { this.animator=animator;sprite=animator.Sprite;source=sprite.GetComponent<Renderer>(); }
        internal bool Frame(bool replace=true)
        {
            var clip=animator!=null ? animator.CurrentClip ?? animator.DefaultClip : null;
            string motion=null;
            bool visible=replace && sprite!=null && source!=null && source.enabled && sprite.gameObject.activeInHierarchy
                && sprite.Collection!=null && sprite.Collection.name=="Abyss Dream Cln" && clip!=null && Motions.TryGetValue(clip.name,out motion);
            if(visible)
            {
                float scale=Mathf.Max(.01f,Mathf.Abs(sprite.transform.lossyScale.y*sprite.scale.y));
                Vector3 feet=sprite.transform.TransformPoint(Vector3.Scale(new Vector3(0,-1.390625f,0),sprite.scale));
                bool mirrored=sprite.transform.lossyScale.x*sprite.scale.x<0;
                bool hanging=clip.name=="Knight Grab" || clip.name=="Knight Falter" || clip.name=="Knight Fall";
                rig.Frame(feet,Coords.K/scale,hanging ? !mirrored : mirrored,animator,source,sprite.color,false,motion);
                if(clip.name=="Knight Grab" || clip.name=="Knight Falter")
                    rig.PointRightHand(sprite.transform.TransformPoint(Vector3.Scale(new Vector3(.55f,0,0),sprite.scale)));
                if(clip.name=="Climb 1" || clip.name=="Climb 2" || clip.name=="Climb 3") rig.CropBelow(feet.y);
            }
            if(source!=null) source.forceRenderingOff=visible;
            rig.Show(visible);return visible;
        }
        public void Dispose() { if(source!=null) source.forceRenderingOff=false;rig.Dispose(); }
    }
}
