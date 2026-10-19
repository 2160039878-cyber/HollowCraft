using System;
using System.Collections.Generic;
using MonoMod.RuntimeDetour;
using UnityEngine;

namespace HollowCraft.Render
{
    internal sealed class ProtagonistReplicas : IDisposable
    {
        private sealed class Replica
        {
            public Renderer Source;
            public SteveRig Rig;
            public bool Shade;
        }
        private readonly Dictionary<tk2dSpriteAnimator, Replica> replicas = new Dictionary<tk2dSpriteAnimator, Replica>();
        private readonly Dictionary<tk2dSpriteAnimator, VoidHand> hands = new Dictionary<tk2dSpriteAnimator, VoidHand>();
        private readonly Dictionary<tk2dSpriteAnimator, DreamNailActor> dreams = new Dictionary<tk2dSpriteAnimator, DreamNailActor>();
        private readonly Dictionary<tk2dSpriteAnimator, RadianceActor> radiance = new Dictionary<tk2dSpriteAnimator, RadianceActor>();
        private readonly Dictionary<tk2dSpriteAnimator, AbyssActor> abyss = new Dictionary<tk2dSpriteAnimator, AbyssActor>();
        private tk2dSpriteAnimation library;
        private tk2dSpriteAnimator main;
        private tk2dBaseSprite cutsceneSprite;
        private Hook playHook, enableHook;
        private float nextScan;
        private Animator voidLord;
        private SpriteRenderer voidHead, voidBody, voidArms;
        private readonly List<SpriteRenderer> voidParts = new List<SpriteRenderer>();
        private SteveRig voidRig;
        public int ReplacedCount { get; private set; }
        private delegate void PlayOriginal(tk2dSpriteAnimator animator, tk2dSpriteAnimationClip clip, float start, float fps);
        private delegate void EnableOriginal(tk2dSpriteAnimator animator);
        public void Install()
        {
            var method = typeof(tk2dSpriteAnimator).GetMethod("Play", new[] { typeof(tk2dSpriteAnimationClip), typeof(float), typeof(float) });
            if (method == null) throw new MissingMethodException("Native animation playback entry point changed");
            playHook = new Hook(method, (Action<PlayOriginal, tk2dSpriteAnimator, tk2dSpriteAnimationClip, float, float>)Played);
            var enable=typeof(tk2dSpriteAnimator).GetMethod("OnEnable",System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.NonPublic);
            if(enable==null) throw new MissingMethodException("Native animator activation entry point changed");
            enableHook=new Hook(enable,(Action<EnableOriginal,tk2dSpriteAnimator>)Enabled);
        }
        private void Enabled(EnableOriginal original,tk2dSpriteAnimator animator) { original(animator);Track(animator); }
        // The native cutscene prefab stores Knight/Sit frame 0 under the unrelated Fury Aura animation library.
        private bool StaticKnight(tk2dSpriteAnimator animator) => cutsceneSprite!=null && animator.Sprite!=null
            && animator.Sprite.Collection==cutsceneSprite.Collection && animator.Sprite.spriteId==cutsceneSprite.spriteId;
        // This shared NPC library also contains a separate seated protagonist, used beside Mato and Quirrel.
        private static string SeatedKnightMotion(tk2dSpriteAnimator animator)
        {
            if(animator.Library==null || animator.Library.name!="Quirrel") return null;
            string clip=(animator.CurrentClip ?? animator.DefaultClip)?.name;
            return clip=="Knight Sit" ? "sit" : clip=="Knight Sit End" ? "bench_exit" : null;
        }
        private void Played(PlayOriginal original, tk2dSpriteAnimator animator, tk2dSpriteAnimationClip clip, float start, float fps)
        {
            original(animator, clip, start, fps);
            Track(animator);
        }
        private void Track(tk2dSpriteAnimator animator)
        {
            var candidate=animator.Library;
            // Unity object names cross the native boundary; read once during the full-scene scan.
            string name=candidate!=null ? candidate.name : null;
            switch(name)
            {
                case "Shade Lord Anim": if(TrackVoidHand(animator)) return; break;
                case "Knight Dream Custcene Anim": if(TrackDreamActor(animator)) return; break;
                case "Radiance Anim": if(TrackRadianceActor(animator)) return; break;
                case "Abyss Dream Anim": if(TrackAbyssActor(animator)) return; break;
            }
            if(library==null || animator==main) return;
            bool shade=name=="Hollow Shade", isStatic=StaticKnight(animator);
            string seated=name=="Quirrel" ? SeatedKnightMotion(animator) : null;
            if(candidate!=library && !shade && !isStatic && seated==null) return;
            if (!replicas.TryGetValue(animator, out Replica replica))
            {
                var renderer = animator.GetComponent<Renderer>();
                if (renderer == null) return;
                replicas.Add(animator, replica = new Replica { Source = renderer, Shade=shade });
            }
            replica.Source.forceRenderingOff = isStatic || seated!=null || SteveRig.CanReplaceClip((animator.CurrentClip ?? animator.DefaultClip)?.name,replica.Shade,animator.CurrentClip!=null ? animator.CurrentFrame : 0);
        }

        public void Frame(HeroController hero, Vector3 feet, bool render=true)
        {
            if (hero == null) { Clear(); return; }
            var current = hero.GetComponent<tk2dSpriteAnimator>();
            if (current.Library != library) { Clear(); library = current.Library; }
            main = current;
            cutsceneSprite=hero.cutscenePrefab!=null ? hero.cutscenePrefab.GetComponent<tk2dBaseSprite>() : null;
            if (Time.unscaledTime >= nextScan)
            {
                nextScan = Time.unscaledTime + 2;
                foreach (var animator in UnityEngine.Object.FindObjectsByType<tk2dSpriteAnimator>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                {
                    // Shared native animation library identifies protagonist replicas without matching NPC names.
                    Track(animator);
                }
                foreach (var animator in new List<tk2dSpriteAnimator>(replicas.Keys))
                    if (animator == null) { replicas[animator].Rig?.Dispose(); replicas.Remove(animator); }
                foreach (var animator in new List<tk2dSpriteAnimator>(hands.Keys))
                    if (animator == null) { hands[animator].Dispose(); hands.Remove(animator); }
                foreach (var animator in new List<tk2dSpriteAnimator>(dreams.Keys))
                    if (animator == null) { dreams[animator].Dispose(); dreams.Remove(animator); }
                foreach (var animator in new List<tk2dSpriteAnimator>(radiance.Keys))
                    if (animator == null) { radiance[animator].Dispose(); radiance.Remove(animator); }
                foreach (var animator in new List<tk2dSpriteAnimator>(abyss.Keys))
                    if (animator == null) { abyss[animator].Dispose(); abyss.Remove(animator); }
                if (voidLord == null)
                {
                    foreach (var animator in UnityEngine.Object.FindObjectsByType<Animator>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                        if (TrackVoidLord(animator)) break;
                }
            }
            ReplacedCount = 0;
            float offset = hero.transform.position.y - feet.y;
            foreach (var entry in replicas)
            {
                tk2dSpriteAnimator animator = entry.Key;
                Replica replica = entry.Value;
                if (animator == null || replica.Source == null) { replica.Rig?.Show(false); continue; }
                bool isStatic=StaticKnight(animator);
                string seated=SeatedKnightMotion(animator);
                bool replace = render && (isStatic || seated!=null || SteveRig.CanReplaceClip((animator.CurrentClip ?? animator.DefaultClip)?.name,replica.Shade,animator.CurrentClip!=null ? animator.CurrentFrame : 0));
                replica.Source.forceRenderingOff = replace;
                bool visible = replace && replica.Source.enabled && animator.gameObject.activeInHierarchy;
                if (visible)
                {
                    replica.Rig ??= new SteveRig();
                    var sprite = animator.GetComponent<tk2dSprite>();
                    float scale = Mathf.Max(.01f, Mathf.Abs(animator.transform.lossyScale.y));
                    replica.Rig.Frame(animator.transform.position - Vector3.up * (offset * scale), Coords.K / scale,
                        animator.transform.lossyScale.x < 0, animator, replica.Source, sprite != null ? sprite.color : Color.white,replica.Shade,
                        isStatic ? "bench_enter" : seated,isStatic ? 0f : (float?)null);
                    if(seated!=null) replica.Rig.AlignBottom(replica.Source.bounds.min.y);
                    ReplacedCount++;
                }
                replica.Rig?.Show(visible);
            }
            if (RenderVoidLord(render)) ReplacedCount++;
            ReplacedCount += RenderVoidHands(render);
            ReplacedCount += RenderDreamActors(render);
            ReplacedCount += RenderRadianceActors(render);
            ReplacedCount += RenderAbyssActors(render);
        }
        internal bool TrackAbyssActor(tk2dSpriteAnimator animator)
        {
            if(animator.Library==null || animator.Library.name!="Abyss Dream Anim" || animator.Sprite==null) return false;
            bool selected=AbyssActor.CanReplace((animator.CurrentClip ?? animator.DefaultClip)?.name);
            if(!abyss.TryGetValue(animator,out var actor))
            {
                if(!selected) return false;
                abyss.Add(animator,actor=new AbyssActor(animator));
            }
            actor.Frame();return selected;
        }
        internal int RenderAbyssActors(bool replace=true)
        {
            int count=0;foreach(var actor in abyss.Values) if(actor.Frame(replace)) count++;return count;
        }
        internal bool TrackRadianceActor(tk2dSpriteAnimator animator)
        {
            if(animator.Library==null || animator.Library.name!="Radiance Anim" || animator.Sprite==null) return false;
            bool selected=RadianceActor.CanReplace((animator.CurrentClip ?? animator.DefaultClip)?.name);
            if(!radiance.TryGetValue(animator,out var actor))
            {
                if(!selected) return false;
                radiance.Add(animator,actor=new RadianceActor(animator));
            }
            actor.Frame();return selected;
        }
        internal int RenderRadianceActors(bool replace=true)
        {
            int count=0;
            foreach(var actor in radiance.Values) if(actor.Frame(replace)) count++;
            return count;
        }
        internal bool TrackDreamActor(tk2dSpriteAnimator animator)
        {
            if (animator.Library==null || animator.Library.name!="Knight Dream Custcene Anim" || animator.Sprite==null) return false;
            if (!dreams.ContainsKey(animator)) dreams.Add(animator,new DreamNailActor(animator));
            dreams[animator].Frame();
            return true;
        }
        internal int RenderDreamActors(bool replace=true)
        {
            int count=0;
            foreach (var actor in dreams.Values) if (actor.Frame(replace)) count++;
            return count;
        }
        internal bool TrackVoidHand(tk2dSpriteAnimator animator)
        {
            if (animator.Library == null || animator.Library.name != "Shade Lord Anim" || animator.Sprite == null) return false;
            if (!hands.ContainsKey(animator)) hands.Add(animator, new VoidHand(animator));
            return true;
        }
        internal int RenderVoidHands(bool replace = true)
        {
            int count = 0;
            foreach (var hand in hands.Values) if (hand.Frame(replace)) count++;
            return count;
        }
        internal bool TrackVoidLord(Animator animator)
        {
            if (animator.runtimeAnimatorController == null || animator.runtimeAnimatorController.name != "Shade_Lord") return false;
            var head = animator.transform.Find("head")?.GetComponent<SpriteRenderer>();
            var body = animator.transform.Find("body")?.GetComponent<SpriteRenderer>();
            var arms = animator.transform.Find("arms")?.GetComponent<SpriteRenderer>();
            if (head == null || body == null || arms == null) return false;
            voidLord = animator; voidHead = head; voidBody = body; voidArms = arms;
            voidParts.Clear();
            foreach (Transform child in animator.transform)
                if (child.name == "head" || child.name == "body" || child.name == "arms" || child.name.StartsWith("tendril", StringComparison.Ordinal))
                {
                    var source = child.GetComponent<SpriteRenderer>();
                    if (source != null) voidParts.Add(source);
                }
            return true;
        }
        internal bool RenderVoidLord(bool replace = true)
        {
            bool visible = replace && voidLord != null && voidHead != null && voidBody != null && voidArms != null && voidLord.gameObject.activeInHierarchy;
            if (visible)
            {
                voidRig ??= new SteveRig(solidVoid: true);
                voidRig.FrameVoidLord(voidHead, voidBody, voidArms);
            }
            foreach (var source in voidParts) if (source != null) source.forceRenderingOff = replace;
            voidRig?.Show(visible);
            return visible;
        }
        public void Clear()
        {
            foreach (var replica in replicas.Values)
            {
                if (replica.Source != null) replica.Source.forceRenderingOff = false;
                replica.Rig?.Dispose();
            }
            replicas.Clear(); ReplacedCount = 0; library = null; main = null; cutsceneSprite=null; nextScan = 0;
            foreach (var hand in hands.Values) hand.Dispose();
            hands.Clear();
            foreach (var actor in dreams.Values) actor.Dispose();
            dreams.Clear();
            foreach(var actor in radiance.Values) actor.Dispose();
            radiance.Clear();
            foreach(var actor in abyss.Values) actor.Dispose();
            abyss.Clear();
            foreach (var source in voidParts) if (source != null) source.forceRenderingOff = false;
            voidRig?.Dispose(); voidRig = null; voidParts.Clear();
            voidLord = null; voidHead = voidBody = voidArms = null;
        }
        public void Dispose() { Clear(); playHook?.Dispose(); playHook = null; enableHook?.Dispose(); enableHook=null; }
    }
}
