using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using HollowCraft.Render;
using Newtonsoft.Json;
using UnityEngine;
using UnitySceneManager = UnityEngine.SceneManagement.SceneManager;

namespace HollowCraft
{
    // Explicit command-line fixture: sample the original preloaded animator without loading a save.
    internal sealed class LiveFormProbe : MonoBehaviour
    {
        internal Dictionary<string, Dictionary<string, GameObject>> PreloadedObjects;
        internal bool DreamOnly;
        internal bool RadianceOnly;
        internal bool StaticOnly;
        internal bool AbyssOnly;
        private const int Width = 1920, Height = 1080, ActorLayer = 31;
        private readonly List<object> frames = new List<object>();
        private readonly List<string> errors = new List<string>();
        private GameObject actor, cameraObject;
        private Camera probeCamera;
        private RenderTexture target;
        private Texture2D pixels;
        private ProtagonistReplicas replacement;
        private string directory;
        private bool defaultDreamReplaced;
        private bool defaultRadianceReplaced;
        private bool defaultAbyssReplaced;

        private IEnumerator Start()
        {
            float deadline = Time.realtimeSinceStartup + 90;
            while ((StaticOnly ? HeroController.instance==null || !GameManager.instance.IsGameplayScene()
                : UnitySceneManager.GetActiveScene().name != "Menu_Title") && Time.realtimeSinceStartup < deadline) yield return null;
            directory = Path.Combine(Directory.GetParent(Application.dataPath).Parent.FullName,
                "work-assets", "live-forms", "probe-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            try
            {
                if (!StaticOnly && UnitySceneManager.GetActiveScene().name != "Menu_Title") throw new InvalidOperationException("Title menu was not reached");
                if (StaticOnly) RunStatic(); else if(AbyssOnly) RunAbyss(); else if (RadianceOnly) RunRadiance(); else if (DreamOnly) RunDream(); else Run();
            }
            catch (Exception exception) { errors.Add(exception.ToString()); Log.Error(exception.ToString()); }
            finally
            {
                replacement?.Dispose();
                if (actor != null) Destroy(actor);
                if (cameraObject != null) Destroy(cameraObject);
                if (target != null) { target.Release(); Destroy(target); }
                if (pixels != null) Destroy(pixels);
                File.WriteAllText(Path.Combine(directory, "result.json"), JsonConvert.SerializeObject(new {
                    passed = errors.Count == 0 && frames.Count == (StaticOnly ? 15 : AbyssOnly ? 159 : RadianceOnly ? 124 : 49)
                        && (!DreamOnly || defaultDreamReplaced) && (!RadianceOnly || defaultRadianceReplaced) && (!AbyssOnly || defaultAbyssReplaced),
                    defaultDreamReplaced,defaultRadianceReplaced,defaultAbyssReplaced, errors, frames, resolution = new[] { Width, Height },
                    scene = UnitySceneManager.GetActiveScene().name,
                    scope = StaticOnly ? "Native hero-referenced prefab components in isolated Town: static cutscene, default death/spike/acid poses, mirrored/tinted static body, three preserved Fury Aura frames and six mixed Hit Crack Appear frames. Activation hooks and source layers checked. No actual story/reflecting-surface flow or performance acceptance."
                        : AbyssOnly ? "Native Abyss Dream library:80 protagonist frames,71 preserved NPC/effect frames,3 mirrored poses and5 loop-section overrun samples including doubled playback speed. Offscreen component fixture; story flow tested separately."
                        : RadianceOnly ? "Native preloaded Dream_Final_Boss/Knight Ball component:64 protagonist frames,57 preserved shared-library frames,3 mirrored cases. Production renderers; offscreen actor-only fixture. Actual boss/story flow, audio and gameplay performance are not covered."
                        : DreamOnly ? "Native preloaded Dream Moth/Knight Dummy:49 frames across six clips. Production replacement; original DN Item and teleport-only frames preserved. Offscreen actor-only fixture, no save loaded; actual story flow is not covered."
                        : "Native preloaded Shade_Lord (37 samples) and Shade Lord Hand (12 clip frames), production replacement renderers, isolated offscreen camera. No save loaded. Body faders/particles excluded from this actor-only fixture. Actual boss/story flow and other forms are not covered."
                }));
                Log.Info("Live form probe finished: " + directory);
                Application.Quit();
            }
        }
        private void RunAbyss()
        {
            if(PreloadedObjects==null || !PreloadedObjects.TryGetValue("Abyss_15",out var scene)
                || !scene.TryGetValue("Dream Enter Abyss/Knight Dummy",out var prefab) || prefab==null)
                throw new InvalidOperationException("Native Abyss actor preload is missing");
            actor=Instantiate(prefab);actor.SetActive(false);
            foreach(var script in actor.GetComponentsInChildren<MonoBehaviour>(true))
                if(!(script is tk2dBaseSprite) && !(script is tk2dSpriteAnimator)) script.enabled=false;
            foreach(var transform in actor.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer=ActorLayer;
            actor.transform.position=Vector3.zero;actor.transform.localScale=Vector3.one;actor.SetActive(true);
            var animator=actor.GetComponent<tk2dSpriteAnimator>();var source=animator.Sprite.GetComponent<Renderer>();
            if(animator.Library.name!="Abyss Dream Anim" || animator.Library.clips.Length!=24
                || animator.Library.clips.Sum(c=>c.frames.Length)!=151) throw new InvalidOperationException("Abyss library changed");
            Materials.BindHero(source.sharedMaterial);Coords.K=1.8f/1.28125f;replacement=new ProtagonistReplicas();
            defaultAbyssReplaced=replacement.TrackAbyssActor(animator) && replacement.RenderAbyssActors()==1 && source.forceRenderingOff;
            if(!defaultAbyssReplaced) throw new InvalidOperationException("Default Abyss body leaked");
            Bounds shot=source.bounds;
            foreach(var clip in animator.Library.clips) for(int frame=0;frame<clip.frames.Length;frame++)
            {
                animator.PlayFromFrame(clip,frame);animator.Pause();shot.Encapsulate(source.bounds);replacement.RenderAbyssActors();
                foreach(var renderer in UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None))
                    if(renderer.gameObject.layer==ActorLayer && renderer.enabled && renderer.gameObject.activeInHierarchy) shot.Encapsulate(renderer.bounds);
            }
            var mirrored=shot;mirrored.center=new Vector3(-shot.center.x,shot.center.y,shot.center.z);shot.Encapsulate(mirrored);
            cameraObject=new GameObject("HollowCraft Abyss test camera");probeCamera=cameraObject.AddComponent<Camera>();probeCamera.enabled=false;
            probeCamera.orthographic=true;probeCamera.aspect=(float)Width/Height;probeCamera.cullingMask=1<<ActorLayer;
            probeCamera.clearFlags=CameraClearFlags.SolidColor;probeCamera.backgroundColor=new Color(.39f,.45f,.51f,1);
            probeCamera.orthographicSize=Mathf.Max(shot.extents.y,shot.extents.x/probeCamera.aspect)*1.08f;
            probeCamera.transform.position=new Vector3(shot.center.x,shot.center.y,shot.min.z-40);probeCamera.nearClipPlane=.1f;probeCamera.farClipPlane=200;
            target=new RenderTexture(Width,Height,24,RenderTextureFormat.ARGB32);target.Create();probeCamera.targetTexture=target;
            pixels=new Texture2D(Width,Height,TextureFormat.RGB24,false);
            foreach(var clip in animator.Library.clips) for(int frame=0;frame<clip.frames.Length;frame++) CaptureAbyss(animator,source,clip,frame,false);
            foreach(string name in new[]{"Knight Grab","Knight Falter"}) foreach(float time in new[]{1.25f,2.75f})
                CaptureAbyss(animator,source,animator.GetClipByName(name),0,false,time);
            CaptureAbyss(animator,source,animator.GetClipByName("Knight Grab"),0,false,1.25f,24);
            actor.transform.localScale=new Vector3(-1,1,1);
            foreach(string name in new[]{"Climb 1","Climb 3","Knight Grab"}) CaptureAbyss(animator,source,animator.GetClipByName(name),2,true);
            actor.SetActive(false);if(replacement.RenderAbyssActors()!=0) throw new InvalidOperationException("Abyss replacement survived deactivation");
            replacement.Clear();if(source.forceRenderingOff) throw new InvalidOperationException("Abyss source was not restored");
        }
        private void CaptureAbyss(tk2dSpriteAnimator animator,Renderer source,tk2dSpriteAnimationClip clip,int frame,bool mirrored,float? time=null,float? fps=null)
        {
            if(time.HasValue) animator.Play(clip,time.Value,fps ?? clip.fps);else animator.PlayFromFrame(clip,frame);
            animator.Resume();animator.UpdateAnimation(0);animator.Pause();replacement.RenderAbyssActors(false);
            string label="abyss-"+(mirrored ? "mirror-" : "")+clip.name.Replace(' ','_')+"-"+(time.HasValue ? "time-"+time.Value.ToString(System.Globalization.CultureInfo.InvariantCulture) : frame.ToString("D2"))+(fps.HasValue ? "-fast" : "");
            byte[] original=Capture(label+"-native.png");bool expected=AbyssActor.CanReplace(clip.name);
            bool tracked=replacement.TrackAbyssActor(animator);int count=replacement.RenderAbyssActors();byte[] steve=Capture(label+"-steve.png");
            if(tracked!=expected || (count==1)!=expected || source.forceRenderingOff!=expected || original.SequenceEqual(steve)==expected)
                throw new InvalidOperationException("Abyss replacement/preservation failed: "+label);
            float phase=SteveRig.ClipTime(animator)*clip.fps/clip.frames.Length;
            if(animator.Sprite.spriteId!=clip.frames[Math.Min(animator.CurrentFrame,clip.frames.Length-1)].spriteId)
                throw new InvalidOperationException("Native sampled sprite/time disagree");
            if(time.HasValue && (phase<(float)clip.loopStart/clip.frames.Length || phase>=1)) throw new InvalidOperationException("Loop-section replayed its entry pose");
            frames.Add(new {actor="abyss",clip=clip.name,frame=animator.CurrentFrame,mirrored,time=animator.ClipTimeSeconds,phase,fps=animator.ClipFps,
                label,sprite=animator.Sprite.GetCurrentSpriteDef().name,replaced=expected,originalHidden=source.forceRenderingOff});
        }
        private void RunStatic()
        {
            var hero=HeroController.instance;
            if(hero==null || hero.cutscenePrefab==null) throw new InvalidOperationException("Native hero prefab references unavailable");
            var collider=hero.GetComponent<Collider2D>();
            var feet=new Vector3(hero.transform.position.x,collider.bounds.min.y,hero.transform.position.z);
            Coords.K=1.8f/collider.bounds.size.y;
            Materials.BindHero(hero.GetComponent<Renderer>().sharedMaterial);
            replacement=new ProtagonistReplicas();replacement.Frame(hero,feet);replacement.Install();
            cameraObject=new GameObject("HollowCraft static test camera");probeCamera=cameraObject.AddComponent<Camera>();probeCamera.enabled=false;
            probeCamera.orthographic=true;probeCamera.orthographicSize=2;probeCamera.aspect=(float)Width/Height;
            probeCamera.cullingMask=1<<ActorLayer;probeCamera.clearFlags=CameraClearFlags.SolidColor;
            probeCamera.backgroundColor=new Color(.39f,.45f,.51f,1);probeCamera.transform.position=new Vector3(0,-.35f,-40);
            probeCamera.nearClipPlane=.1f;probeCamera.farClipPlane=100;
            target=new RenderTexture(Width,Height,24,RenderTextureFormat.ARGB32);target.Create();probeCamera.targetTexture=target;
            pixels=new Texture2D(Width,Height,TextureFormat.RGB24,false);
            foreach(var prefab in new[]{hero.cutscenePrefab,hero.heroDeathPrefab,hero.spikeDeathPrefab,hero.acidDeathPrefab})
            {
                actor=Instantiate(prefab);actor.SetActive(false);actor.transform.position=Vector3.zero;actor.transform.localScale=Vector3.one;
                foreach(var script in actor.GetComponentsInChildren<MonoBehaviour>(true))
                    if(!(script is tk2dBaseSprite) && !(script is tk2dSpriteAnimator)) script.enabled=false;
                foreach(var c in actor.GetComponentsInChildren<Collider2D>(true)) c.enabled=false;
                foreach(var body in actor.GetComponentsInChildren<Rigidbody2D>(true)) body.simulated=false;
                foreach(var t in actor.GetComponentsInChildren<Transform>(true)) t.gameObject.layer=ActorLayer;
                var animator=actor.GetComponent<tk2dSpriteAnimator>();var source=actor.GetComponent<Renderer>();
                foreach(var r in actor.GetComponentsInChildren<Renderer>(true)) if(r!=source) r.enabled=false;
                animator.playAutomatically=false;animator.playAutomaticallyOnEnable=false;
                actor.SetActive(true);
                if(!source.forceRenderingOff) throw new InvalidOperationException("Activation leaked native body: "+prefab.name);
                CaptureStatic(hero,feet,animator,source,prefab.name.Replace(' ','_'),true);
                if(prefab==hero.cutscenePrefab)
                {
                    actor.transform.localScale=new Vector3(-1,1,1);
                    CaptureStatic(hero,feet,animator,source,"Static_mirrored",true);
                    actor.transform.localScale=Vector3.one;animator.Sprite.color=new Color(.6f,.7f,.8f,.45f);
                    CaptureStatic(hero,feet,animator,source,"Static_tinted",true);
                    animator.Sprite.color=Color.white;
                    var effect=animator.GetClipByName("Fury Aura");
                    foreach(int frame in new[]{0,effect.frames.Length/2,effect.frames.Length-1})
                    { animator.PlayFromFrame(effect,frame);animator.Pause();CaptureStatic(hero,feet,animator,source,"Preserved_Fury_"+frame,false); }
                }
                if(prefab==hero.heroDeathPrefab)
                {
                    var mixed=animator.GetClipByName("Hit Crack Appear");
                    if(mixed==null || mixed.frames.Length!=6) throw new InvalidOperationException("Native mixed body/effect clip changed");
                    for(int frame=0;frame<mixed.frames.Length;frame++)
                    {
                        animator.PlayFromFrame(mixed,frame);animator.Pause();
                        CaptureStatic(hero,feet,animator,source,"Mixed_Hit_"+frame,frame!=1 && frame!=5);
                    }
                }
                actor.SetActive(false);replacement.Frame(hero,feet);
                if(UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None)
                    .Any(r=>r.gameObject.layer==ActorLayer && r.enabled && r.gameObject.activeInHierarchy))
                    throw new InvalidOperationException("Replacement survived source deactivation");
                replacement.Clear();if(source.forceRenderingOff) throw new InvalidOperationException("Source was not restored on clear");
                Destroy(actor);actor=null;replacement.Frame(hero,feet);
            }
        }
        private void CaptureStatic(HeroController hero,Vector3 feet,tk2dSpriteAnimator animator,Renderer source,string label,bool expected)
        {
            replacement.Frame(hero,feet,false);
            if(UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None)
                .Any(r=>r!=source && r.gameObject.layer==ActorLayer && r.enabled && r.gameObject.activeInHierarchy))
                throw new InvalidOperationException("Static native baseline contains another renderer");
            byte[] native=Capture(label+"-native.png");replacement.Frame(hero,feet);
            byte[] steve=Capture(label+"-steve.png");
            if(source.forceRenderingOff!=expected || native.SequenceEqual(steve)==expected)
                throw new InvalidOperationException("Static replacement/preservation failed: "+label);
            frames.Add(new{actor="static",label,sprite=animator.Sprite.GetCurrentSpriteDef().name,
                clip=animator.CurrentClip?.name,defaultClip=animator.DefaultClip?.name,layer=source.gameObject.layer,
                replaced=expected,originalHidden=source.forceRenderingOff});
        }
        private void RunRadiance()
        {
            if(PreloadedObjects==null || !PreloadedObjects.TryGetValue("Dream_Final_Boss",out var scene)
                || !scene.TryGetValue("Knight Ball",out var prefab) || prefab==null) throw new InvalidOperationException("Native Radiance protagonist preload is missing");
            actor=Instantiate(prefab);actor.SetActive(false);
            foreach(var script in actor.GetComponentsInChildren<MonoBehaviour>(true))
                if(!(script is tk2dBaseSprite) && !(script is tk2dSpriteAnimator)) script.enabled=false;
            foreach(var transform in actor.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer=ActorLayer;
            var animator=actor.GetComponent<tk2dSpriteAnimator>();
            if(animator==null || animator.Library.name!="Radiance Anim") throw new InvalidOperationException("Native Radiance library changed");
            actor.SetActive(true);var source=animator.Sprite.GetComponent<Renderer>();
            var shader=Shader.Find("Sprites/Default-ColorFlash");if(shader==null) throw new InvalidOperationException("Native player shader unavailable");
            var material=new Material(shader);Materials.BindHero(material);Destroy(material);Coords.K=1.8f/1.28125f;
            replacement=new ProtagonistReplicas();defaultRadianceReplaced=replacement.TrackRadianceActor(animator) && source.forceRenderingOff;
            if(!defaultRadianceReplaced) throw new InvalidOperationException("Default Radiance protagonist was not replaced");
            string[] playerNames={"Knight Ball","Knight Form","Knight Idle","Slash1 Antic","Slash1","Slash2 Antic","Slash2","Knight Unform","Knight Pull","Knight Hang","Knight Split Antic","Knight Split"};
            string[] otherNames={"HollowShade Rise","HollowShade 1","HollowShade 2","HollowShade 3","HollowShade 4","BG Shade 1","BG Shade 2","BG Shade 3","BG Shade 4","Eye Struggle"};
            var playerClips=playerNames.Select(animator.GetClipByName).ToArray();var otherClips=otherNames.Select(animator.GetClipByName).ToArray();
            if(playerClips.Any(c=>c==null) || playerClips.Sum(c=>c.frames.Length)!=64
                || otherClips.Any(c=>c==null) || otherClips.Sum(c=>c.frames.Length)!=57) throw new InvalidOperationException("Radiance clip inventory changed");
            var clips=playerClips.Concat(otherClips).ToArray();Bounds shot=source.bounds;
            foreach(var clip in clips) for(int frame=0;frame<clip.frames.Length;frame++)
            {
                animator.PlayFromFrame(clip,frame);animator.Pause();shot.Encapsulate(source.bounds);
                replacement.RenderRadianceActors();
                foreach(var renderer in UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None))
                    if(renderer.gameObject.layer==ActorLayer && renderer.enabled && renderer.gameObject.activeInHierarchy) shot.Encapsulate(renderer.bounds);
            }
            var mirrored=shot;mirrored.center=new Vector3(2*actor.transform.position.x-shot.center.x,shot.center.y,shot.center.z);shot.Encapsulate(mirrored);
            cameraObject=new GameObject("HollowCraft Radiance test camera");probeCamera=cameraObject.AddComponent<Camera>();probeCamera.enabled=false;
            probeCamera.orthographic=true;probeCamera.aspect=(float)Width/Height;probeCamera.cullingMask=1<<ActorLayer;
            probeCamera.clearFlags=CameraClearFlags.SolidColor;probeCamera.backgroundColor=new Color(.39f,.45f,.51f,1);
            probeCamera.orthographicSize=Mathf.Max(shot.extents.y,shot.extents.x/probeCamera.aspect)*1.08f;
            probeCamera.transform.position=new Vector3(shot.center.x,shot.center.y,shot.min.z-40);probeCamera.nearClipPlane=.1f;probeCamera.farClipPlane=200;
            target=new RenderTexture(Width,Height,24,RenderTextureFormat.ARGB32);target.Create();probeCamera.targetTexture=target;
            pixels=new Texture2D(Width,Height,TextureFormat.RGB24,false);
            foreach(var clip in clips) for(int frame=0;frame<clip.frames.Length;frame++) CaptureRadiance(animator,source,clip,frame,false);
            actor.transform.localScale=new Vector3(-1,1,1);
            foreach(string name in new[]{"Knight Idle","Slash1","Knight Hang"}) CaptureRadiance(animator,source,animator.GetClipByName(name),0,true);
            actor.SetActive(false);if(replacement.RenderRadianceActors()!=0) throw new InvalidOperationException("Radiance replica survived source deactivation");
            replacement.Clear();if(source.forceRenderingOff) throw new InvalidOperationException("Radiance source renderer was not restored");
        }
        private void CaptureRadiance(tk2dSpriteAnimator animator,Renderer source,tk2dSpriteAnimationClip clip,int frame,bool mirrored)
        {
            animator.PlayFromFrame(clip,frame);animator.Pause();replacement.RenderRadianceActors(false);
            if(UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None)
                .Any(r=>r!=source && r.gameObject.layer==ActorLayer && r.enabled && r.gameObject.activeInHierarchy))
                throw new InvalidOperationException("Native Radiance baseline contains a replacement renderer");
            string label="radiance-"+(mirrored ? "mirror-" : "")+clip.name.Replace(' ','_')+"-"+frame.ToString("D2");
            byte[] original=Capture(label+"-native.png");bool expected=RadianceActor.CanReplace(clip.name);
            bool tracked=replacement.TrackRadianceActor(animator);int count=replacement.RenderRadianceActors();byte[] steve=Capture(label+"-steve.png");
            if(tracked!=expected || (count==1)!=expected || source.forceRenderingOff!=expected || original.SequenceEqual(steve)==expected)
                throw new InvalidOperationException("Radiance replacement/preservation failed: "+label);
            frames.Add(new{actor="radiance",clip=clip.name,frame,mirrored,time=animator.ClipTimeSeconds,
                sprite=animator.Sprite.GetCurrentSpriteDef().name,spriteId=animator.Sprite.spriteId,replaced=expected,originalHidden=source.forceRenderingOff});
        }
        private void RunDream()
        {
            if (PreloadedObjects==null || !PreloadedObjects.TryGetValue("RestingGrounds_07",out var scene)
                || !scene.TryGetValue("Dream Moth/Knight Dummy",out var prefab) || prefab==null)
                throw new InvalidOperationException("Native Dream Nail actor preload is missing");
            actor=Instantiate(prefab);actor.SetActive(false);
            foreach(var script in actor.GetComponentsInChildren<MonoBehaviour>(true))
                if(!(script is tk2dBaseSprite) && !(script is tk2dSpriteAnimator)) script.enabled=false;
            foreach(var transform in actor.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer=ActorLayer;
            var animator=actor.GetComponent<tk2dSpriteAnimator>();
            if(animator==null || animator.Library.name!="Knight Dream Custcene Anim") throw new InvalidOperationException("Native Dream Nail library changed");
            actor.SetActive(true);
            var source=animator.Sprite.GetComponent<Renderer>();
            var shader=Shader.Find("Sprites/Default-ColorFlash");
            if(shader==null) throw new InvalidOperationException("Native player flash shader is unavailable");
            var heroMaterial=new Material(shader);Materials.BindHero(heroMaterial);Destroy(heroMaterial);
            Coords.K=1.8f/1.28125f;
            replacement=new ProtagonistReplicas();
            if(!replacement.TrackDreamActor(animator)) throw new InvalidOperationException("Production Dream actor detection rejected native prefab");
            defaultDreamReplaced=replacement.RenderDreamActors()==1 && source.forceRenderingOff;
            if(!defaultDreamReplaced) throw new InvalidOperationException("Static default Dream actor was not replaced");
            var clips=new[]{"Warp In","DN Item","DN Get 1","DN Get 2","DN Get 3","DN End"}.Select(animator.GetClipByName).ToArray();
            if(clips.Any(c=>c==null) || clips.Sum(c=>c.frames.Length)!=49) throw new InvalidOperationException("Dream clip inventory changed");
            cameraObject=new GameObject("HollowCraft Dream test camera");probeCamera=cameraObject.AddComponent<Camera>();probeCamera.enabled=false;
            probeCamera.orthographic=true;probeCamera.aspect=(float)Width/Height;probeCamera.cullingMask=1<<ActorLayer;
            probeCamera.clearFlags=CameraClearFlags.SolidColor;probeCamera.backgroundColor=new Color(.39f,.45f,.51f,1);
            Bounds shot=source.bounds;
            foreach(var clip in clips) for(int frame=0;frame<clip.frames.Length;frame++)
            { animator.PlayFromFrame(clip,frame);animator.Pause();shot.Encapsulate(source.bounds); }
            probeCamera.orthographicSize=Mathf.Max(shot.extents.y,shot.extents.x/probeCamera.aspect)*1.08f;
            probeCamera.transform.position=new Vector3(shot.center.x,shot.center.y,shot.min.z-40);
            probeCamera.nearClipPlane=.1f;probeCamera.farClipPlane=200;
            target=new RenderTexture(Width,Height,24,RenderTextureFormat.ARGB32);target.Create();probeCamera.targetTexture=target;
            pixels=new Texture2D(Width,Height,TextureFormat.RGB24,false);
            foreach(var clip in clips) for(int frame=0;frame<clip.frames.Length;frame++)
            {
                animator.PlayFromFrame(clip,frame);animator.Pause();
                string label="dream-"+clip.name.Replace(' ','_')+"-"+frame.ToString("D2");
                replacement.RenderDreamActors(false);
                if(UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None)
                    .Any(r=>r!=source && r.gameObject.layer==ActorLayer && r.enabled && r.gameObject.activeInHierarchy))
                    throw new InvalidOperationException("Native baseline contains another replacement renderer: "+label);
                byte[] original=Capture(label+"-native.png");
                bool expected=clip.name!="DN Item" && !(clip.name=="Warp In" && frame<2);
                int count=replacement.RenderDreamActors();byte[] steve=Capture(label+"-steve.png");
                if((count==1)!=expected || source.forceRenderingOff!=expected || original.SequenceEqual(steve)==expected)
                    throw new InvalidOperationException("Dream replacement/preservation failed: "+label);
                frames.Add(new{actor="dream",clip=clip.name,frame,time=animator.ClipTimeSeconds,
                    sprite=animator.Sprite.GetCurrentSpriteDef().name,replaced=expected,originalHidden=source.forceRenderingOff});
            }
            actor.SetActive(false);
            if(replacement.RenderDreamActors()!=0) throw new InvalidOperationException("Dream replacement survived source deactivation");
            replacement.Clear();if(source.forceRenderingOff) throw new InvalidOperationException("Dream source was not restored on clear");
        }
        private void Run()
        {
            if (PreloadedObjects == null || !PreloadedObjects.TryGetValue("GG_Radiance", out var scene)
                || !scene.TryGetValue("Boss Control/Shade_Lord", out var prefab) || prefab == null)
                throw new InvalidOperationException("Native Shade_Lord preload is missing");
            actor = Instantiate(prefab);
            actor.SetActive(false);
            foreach (var script in actor.GetComponentsInChildren<MonoBehaviour>(true)) script.enabled = false;
            string[] names = { "head", "body", "arms", "tendril", "tendril (1)", "tendril (2)", "tendril (3)", "tendril (4)" };
            var sources = names.Select(name => actor.transform.Find(name)?.GetComponent<SpriteRenderer>()).ToArray();
            if (sources.Any(source => source == null)) throw new InvalidOperationException("Native body hierarchy changed");
            foreach (var transform in actor.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer = 30;
            foreach (var source in sources) source.gameObject.layer = ActorLayer;
            var animator = actor.GetComponent<Animator>();
            var clip = animator.runtimeAnimatorController.animationClips.Single(value => value.name == "Radiance_ShadeLord");
            if (Mathf.RoundToInt(clip.length * clip.frameRate) != 36) throw new InvalidOperationException("Native body loop timing changed");
            actor.SetActive(true); animator.speed = 0; animator.Rebind(); animator.Update(0);
            Materials.BindHero(sources[0].sharedMaterial);
            replacement = new ProtagonistReplicas();
            if (!replacement.TrackVoidLord(animator)) throw new InvalidOperationException("Production actor detection rejected the original prefab");
            cameraObject = new GameObject("HollowCraft live form test camera");
            probeCamera = cameraObject.AddComponent<Camera>(); probeCamera.enabled = false;
            probeCamera.orthographic = true; probeCamera.aspect = (float)Width / Height; probeCamera.cullingMask = 1 << ActorLayer;
            probeCamera.clearFlags = CameraClearFlags.SolidColor; probeCamera.backgroundColor = new Color(.39f, .45f, .51f, 1);
            Bounds shot = sources[0].bounds; shot.Encapsulate(sources[1].bounds); shot.Encapsulate(sources[2].bounds);
            replacement.RenderVoidLord();
            foreach (var renderer in UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None))
                if (renderer.gameObject.layer == ActorLayer && renderer.enabled) shot.Encapsulate(renderer.bounds);
            probeCamera.orthographicSize = Mathf.Max(shot.extents.y, shot.extents.x / probeCamera.aspect) * 1.15f;
            probeCamera.transform.position = new Vector3(shot.center.x, shot.center.y, shot.min.z - 40);
            probeCamera.nearClipPlane = .1f; probeCamera.farClipPlane = 200;
            target = new RenderTexture(Width, Height, 24, RenderTextureFormat.ARGB32); target.Create(); probeCamera.targetTexture = target;
            pixels = new Texture2D(Width, Height, TextureFormat.RGB24, false);
            for (int frame = 0; frame <= 36; frame++)
            {
                animator.Play("Base Layer.Radiance_ShadeLord", 0, frame / 36f); animator.Update(0);
                replacement.RenderVoidLord(false);
                byte[] original = Capture("native-" + frame.ToString("D2") + ".png");
                if (!replacement.RenderVoidLord()) throw new InvalidOperationException("Native actor was not replaced");
                byte[] steve = Capture("steve-" + frame.ToString("D2") + ".png");
                if (original.SequenceEqual(steve) || sources.Any(source => !source.forceRenderingOff))
                    throw new InvalidOperationException("Original and replacement views did not switch at frame " + frame);
                Vector3 head = sources[0].transform.position;
                frames.Add(new { actor = "body", frame, time = frame / clip.frameRate, head = new[] { head.x, head.y, head.z },
                    headSprite = sources[0].sprite?.name, armsSprite = sources[2].sprite?.name, hiddenOriginalBodyParts = sources.Length });
            }
            actor.SetActive(false); replacement.Dispose(); Destroy(actor);
            RunHand(scene);
        }
        private void RunHand(Dictionary<string, GameObject> scene)
        {
            if (!scene.TryGetValue("Boss Control/Shade Lord Hand", out var prefab) || prefab == null)
                throw new InvalidOperationException("Native Shade Lord Hand preload is missing");
            actor = Instantiate(prefab); actor.SetActive(false);
            foreach (var script in actor.GetComponentsInChildren<MonoBehaviour>(true))
                if (!(script is tk2dBaseSprite) && !(script is tk2dSpriteAnimator)) script.enabled = false;
            foreach (var transform in actor.GetComponentsInChildren<Transform>(true)) transform.gameObject.layer = ActorLayer;
            var animator = actor.GetComponent<tk2dSpriteAnimator>();
            if (animator == null) throw new InvalidOperationException("Native hand animator is missing");
            actor.SetActive(true);
            var source = animator.Sprite.GetComponent<Renderer>();
            var clips = new[] { "Grab", "Break", "Leave" }.Select(animator.GetClipByName).ToArray();
            if (clips.Any(clip => clip == null) || clips.Sum(clip => clip.frames.Length) != 12)
                throw new InvalidOperationException("Native hand clip inventory changed");
            Bounds shot = source.bounds;
            foreach (var clip in clips)
            {
                animator.Play(clip); animator.Pause();
                for (int frame = 0; frame < clip.frames.Length; frame++)
                {
                    animator.SetFrame(frame, false); shot.Encapsulate(source.bounds);
                }
            }
            probeCamera.orthographicSize = Mathf.Max(shot.extents.y, shot.extents.x / probeCamera.aspect) * 1.15f;
            probeCamera.transform.position = new Vector3(shot.center.x, shot.center.y, shot.min.z - 40);
            replacement = new ProtagonistReplicas();
            if (!replacement.TrackVoidHand(animator)) throw new InvalidOperationException("Production hand detection rejected the original prefab");
            foreach (var clip in clips)
            {
                animator.Play(clip); animator.Pause();
                for (int frame = 0; frame < clip.frames.Length; frame++)
                {
                    animator.SetFrame(frame, false);
                    string label = "hand-" + clip.name + "-" + frame.ToString("D2");
                    replacement.RenderVoidHands(false);
                    byte[] original = Capture(label + "-native.png");
                    if (replacement.RenderVoidHands() != 1) throw new InvalidOperationException("Native hand was not replaced: " + label);
                    byte[] steve = Capture(label + "-steve.png");
                    if (original.SequenceEqual(steve) || !source.forceRenderingOff)
                        throw new InvalidOperationException("Original hand did not switch: " + label);
                    frames.Add(new { actor = "hand", clip = clip.name, frame,
                        sprite = animator.Sprite.GetCurrentSpriteDef().name, hiddenOriginalBodyParts = 1 });
                }
            }
            actor.SetActive(false);
            if (replacement.RenderVoidHands() != 0) throw new InvalidOperationException("Replacement survived native hand deactivation");
            replacement.Clear();
            if (source.forceRenderingOff) throw new InvalidOperationException("Hand renderer was not restored on clear");
        }
        private byte[] Capture(string name)
        {
            RenderTexture previous = RenderTexture.active;
            try
            {
                probeCamera.Render(); RenderTexture.active = target;
                pixels.ReadPixels(new Rect(0, 0, Width, Height), 0, 0); pixels.Apply(false, false);
                var values = pixels.GetPixels32(); Color32 first = values[0];
                if (!values.Any(value => value.r != first.r || value.g != first.g || value.b != first.b))
                    throw new InvalidOperationException("Camera captured an empty actor frame: " + name);
                byte[] png = pixels.EncodeToPNG(); File.WriteAllBytes(Path.Combine(directory, name), png); return png;
            }
            finally { RenderTexture.active = previous; }
        }
    }
}
