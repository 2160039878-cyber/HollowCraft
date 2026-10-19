using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using GlobalEnums;
using MonoMod.RuntimeDetour;
using Newtonsoft.Json;
using TeamCherry.Cinematics;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.Video;

namespace HollowCraft
{
    // Development-only native playback check; never installed without -hollowcraft-test.
    internal sealed class CinematicProbe : MonoBehaviour
    {
        private sealed class Request { public string Name; public float SkipAt = -1; public bool Capture; public bool ObserveNative; }
        private Request request, pendingObservation;
        private Hook beginHook, playerStartHook, playerFinishHook;
        private GameObject root;
        private CinematicSequence sequence;
        private CinematicPlayer nativePlayer;
        private CinematicVideoReference reference;
        private VideoPlayer video;
        private Material material;
        private AudioClip referenceAudio;
        private AudioSource sound;
        private UnityEngine.EventSystems.EventSystem menuEvents;
        private bool menuEventsEnabled;
        private bool loadingAudio;
        private readonly float[] audioWindow = new float[256];
        private readonly List<object> samples = new List<object>();
        private readonly List<string> errors = new List<string>();
        private float started, nextPoll, nextSample, nextCapture, armedAt;
        private int endCallbacks, captureIndex;
        private long? firstReadyFrame;
        private bool skipSent, finishPending, observingNative;
        private string captureDirectory, sourceUrl, beganInScene, skipModeAtRequest;
        private double? skipVideoTime;
        private long? endingFrame;
        private object sourceAudio;
        private string controller;
        private string PathFor(string name) => Path.Combine(Application.persistentDataPath, name);
        private static int FrameCount(string name) => name == "StagTunnelRun" ? 116
            : name == "Nailsmith" ? 130 : name == "NailsmithPaint" ? 316 : name == "Intro" ? 953
            : name == "FinalA" ? 969 : name == "FinalB" ? 1144 : name == "FinalC" ? 2532
            : name == "FinalD" ? 1508 : name == "FinalE" ? 1957 : 0;
        private static float FrameRate(string name) => name == "Intro" ? 25f : 30f;

        private void Awake()
        {
            beginHook = new Hook(typeof(CinematicSequence).GetMethod("Begin"),
                (Action<Action<CinematicSequence>, CinematicSequence>)ObserveBegin);
            playerStartHook = new Hook(typeof(CinematicPlayer).GetMethod("StartVideo",BindingFlags.Instance|BindingFlags.NonPublic),
                (Func<Func<CinematicPlayer,IEnumerator>,CinematicPlayer,IEnumerator>)ObservePlayerStart);
            playerFinishHook = new Hook(typeof(CinematicPlayer).GetMethod("Finish",BindingFlags.Instance|BindingFlags.NonPublic),
                (Action<Action<CinematicPlayer>,CinematicPlayer>)ObservePlayerFinish);
        }

        private void OnDestroy()
        {
            if (sequence != null) sequence.OnPlaybackEnded -= PlaybackEnded;
            if (menuEvents != null) menuEvents.enabled = menuEventsEnabled;
            beginHook?.Dispose();playerStartHook?.Dispose();playerFinishHook?.Dispose();
        }

        private void PlaybackEnded() { endingFrame=video!=null ? video.frame : (long?)null;endCallbacks++;finishPending=true; }

        private void StartTracking(Request candidate)
        {
            request = candidate; samples.Clear(); errors.Clear(); endCallbacks = captureIndex = 0;
            skipSent = finishPending = false; started = nextSample = nextCapture = Time.realtimeSinceStartup;
            firstReadyFrame = null; beganInScene = sourceUrl = skipModeAtRequest = null; skipVideoTime = null;
            endingFrame=null;
            sourceAudio=null;controller="CinematicSequence";
            captureDirectory = request.Capture ? PathFor("cinematic-probe-" + Guid.NewGuid().ToString("N")) : null;
            if (captureDirectory != null) Directory.CreateDirectory(captureDirectory);
        }

        private void ObserveVideo()
        {
            if (video == null) throw new InvalidOperationException("Native sequence did not create a VideoPlayer");
            sourceUrl = video.url;
            if(referenceAudio!=null) sourceAudio=new {referenceAudio.name,referenceAudio.length,referenceAudio.frequency,referenceAudio.channels,referenceAudio.samples};
            beganInScene = (sequence!=null ? sequence.gameObject : nativePlayer.gameObject).scene.name;
            if(sequence!=null) sequence.OnPlaybackEnded += PlaybackEnded;
            video.frameReady += (_, frame) => { if (!firstReadyFrame.HasValue) firstReadyFrame = frame; };
            video.errorReceived += (_, error) => { errors.Add(error); finishPending = true; };
        }

        private void ObserveBegin(Action<CinematicSequence> original, CinematicSequence actual)
        {
            original(actual);
            if (pendingObservation == null || actual.VideoReference == null || actual.VideoReference.name != pendingObservation.Name) return;
            var candidate = pendingObservation; pendingObservation = null;
            observingNative = true; StartTracking(candidate);
            try
            {
                sequence = actual; reference = actual.VideoReference;
                referenceAudio = (AudioClip)typeof(CinematicVideoReference).GetField("audio", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(reference);
                sound = actual.GetComponent<AudioSource>();
                video = (VideoPlayer)typeof(CinematicSequence).GetField("unityVideoPlayer", BindingFlags.Instance | BindingFlags.NonPublic)?.GetValue(actual);
                ObserveVideo();
            }
            catch (Exception e) { errors.Add(e.ToString()); Finish(); }
        }

        private IEnumerator ObservePlayerStart(Func<CinematicPlayer,IEnumerator> original,CinematicPlayer actual)
        {
            var routine=original(actual);
            while(routine.MoveNext())
            {
                var clip=pendingObservation!=null ? (CinematicVideoReference)typeof(CinematicPlayer).GetField("videoClip",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(actual) : null;
                if(pendingObservation!=null && clip!=null && clip.name==pendingObservation.Name)
                {
                    var candidate=pendingObservation;pendingObservation=null;observingNative=true;StartTracking(candidate);
                    try
                    {
                        nativePlayer=actual;controller="CinematicPlayer";reference=clip;referenceAudio=clip.Audio;sound=actual.GetComponent<AudioSource>();
                        video=(VideoPlayer)typeof(CinematicPlayer).GetField("unityVideo",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(actual);
                        ObserveVideo();
                    }
                    catch(Exception e) { errors.Add(e.ToString());Finish(); }
                }
                yield return routine.Current;
            }
        }

        private void ObservePlayerFinish(Action<CinematicPlayer> original,CinematicPlayer actual)
        {
            bool tracked=actual==nativePlayer && !(bool)typeof(CinematicPlayer).GetField("didFinish",BindingFlags.Instance|BindingFlags.NonPublic).GetValue(actual);
            if(tracked) PlaybackEnded();
            original(actual);
        }

        private static void Set(object target, string name, object value)
        {
            FieldInfo field = target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null) throw new MissingFieldException(target.GetType().Name, name);
            field.SetValue(target, value);
        }

        private void Update()
        {
            float now = Time.realtimeSinceStartup;
            try
            {
                if (loadingAudio) return;
                if (pendingObservation != null && now - armedAt > 180)
                {
                    var expired = pendingObservation; pendingObservation = null;
                    observingNative = true; StartTracking(expired); started = armedAt;
                    errors.Add("Timed out waiting for the actual native cinematic scene"); Finish();
                }
                if (request == null && pendingObservation == null && now >= nextPoll && GameManager.instance != null && UIManager.instance != null)
                {
                    nextPoll = now + .25f;
                    string path = PathFor("hollowcraft-cinematic-probe.json");
                    if (!File.Exists(path)) return;
                    if (new FileInfo(path).Length > 1024) { File.Delete(path); throw new InvalidDataException("Oversized cinematic probe"); }
                    var candidate = JsonConvert.DeserializeObject<Request>(File.ReadAllText(path));
                    File.Delete(path);
                    if (candidate == null || FrameCount(candidate.Name) == 0 || float.IsNaN(candidate.SkipAt)
                        || float.IsInfinity(candidate.SkipAt) || candidate.SkipAt < -1 || candidate.SkipAt > FrameCount(candidate.Name) / FrameRate(candidate.Name) - .05f)
                        throw new InvalidDataException("Unsupported cinematic probe request");
                    if (!candidate.ObserveNative && UnityEngine.SceneManagement.SceneManager.GetActiveScene().name != "Menu_Title")
                        throw new InvalidOperationException("Run the isolated component probe from the title menu");
                    if (candidate.ObserveNative)
                    {
                        pendingObservation = candidate; armedAt = now;
                        File.WriteAllText(PathFor("hollowcraft-cinematic-probe-armed.json"), JsonConvert.SerializeObject(new { candidate, armedAt }));
                    }
                    else if (candidate.Name != "StagTunnelRun") StartCoroutine(LoadAudioAndBegin(candidate));
                    else Begin(candidate);
                }
                if (request == null) return;
                if (video != null && now >= nextSample)
                {
                    nextSample = now + 1f / 60;
                    double audioEnergy = 0;
                    if (sound != null && sound.isPlaying)
                    {
                        sound.GetOutputData(audioWindow, 0);
                        foreach (float sample in audioWindow) audioEnergy += sample * sample;
                    }
                    samples.Add(new { t = now - started, video.time, video.frame, video.isPrepared, video.isPlaying,
                        video.width, video.height, video.frameCount, video.frameRate,
                        IsSkipped=sequence!=null ? (bool?)sequence.IsSkipped : null,DidPlay=sequence!=null ? (bool?)sequence.DidPlay : null,
                        audioTime = sound != null && sound.clip != null ? (float?)sound.time : null,
                        audioPlaying = sound != null && sound.isPlaying, audioRms = Math.Sqrt(audioEnergy / audioWindow.Length) });
                }
                bool nativeSkipAllowed = !observingNative || GameManager.instance.inputHandler.skipMode == SkipPromptMode.SKIP_PROMPT
                    || GameManager.instance.inputHandler.skipMode == SkipPromptMode.SKIP_INSTANT;
                if (!skipSent && request.SkipAt >= 0 && video != null && video.isPlaying && video.time >= request.SkipAt && nativeSkipAllowed)
                {
                    skipSent = true;
                    skipVideoTime = video.time;
                    skipModeAtRequest = GameManager.instance.inputHandler.skipMode.ToString();
                    if (observingNative) GameManager.instance.SkipCutscene();
                    else sequence.Skip();
                }
                if (request.Capture && video != null && video.isPlaying && now >= nextCapture)
                {
                    nextCapture = now + .1f;
                    ScreenCapture.CaptureScreenshot(Path.Combine(captureDirectory, $"{captureIndex++:D5}.png"));
                }
                if (finishPending || now - started > FrameCount(request.Name) / FrameRate(request.Name) + 15)
                {
                    if (!finishPending) errors.Add("Native sequence timeout");
                    Finish();
                }
            }
            catch (Exception e) { errors.Add(e.ToString()); Finish(); }
        }

        private IEnumerator LoadAudioAndBegin(Request candidate)
        {
            string path = Path.Combine(Application.streamingAssetsPath, "HollowCraftProbe", candidate.Name + ".wav");
            if (!File.Exists(path))
            {
                errors.Add("Missing decoded original AudioClip test fixture: " + path);
                Finish();
                yield break;
            }
            loadingAudio = true;
            using (UnityWebRequest download = UnityWebRequestMultimedia.GetAudioClip(new Uri(path), AudioType.WAV))
            {
                download.timeout = 10;
                yield return download.SendWebRequest();
                loadingAudio = false;
                try
                {
                    if (download.result != UnityWebRequest.Result.Success) throw new IOException(download.error);
                    referenceAudio = DownloadHandlerAudioClip.GetContent(download);
                    referenceAudio.name = candidate.Name + " (decoded original AudioClip test fixture)";
                    Begin(candidate);
                }
                catch (Exception e) { errors.Add(e.ToString()); Finish(); }
            }
        }

        private void Begin(Request candidate)
        {
            string path = Path.Combine(Application.streamingAssetsPath, candidate.Name + ".mp4");
            if (!File.Exists(path)) throw new FileNotFoundException("Replacement must be installed before the native probe", path);
            observingNative = false; StartTracking(candidate);
            // The fixture covers the title menu; clicks and submit must not activate buttons underneath it.
            menuEvents = UnityEngine.EventSystems.EventSystem.current;
            if (menuEvents != null) { menuEventsEnabled = menuEvents.enabled; menuEvents.enabled = false; }
            Shader shader = Shader.Find("Sprites/Default") ?? Shader.Find("Unlit/Texture");
            if (shader == null) throw new InvalidOperationException("No loaded video-compatible shader");
            material = new Material(shader);
            root = new GameObject("HollowCraft native cinematic probe"); root.SetActive(false);
            var target = root.AddComponent<MeshRenderer>(); target.sharedMaterial = material;
            var blanker = new GameObject("Blanker"); blanker.transform.SetParent(root.transform);
            var blankerRenderer = blanker.AddComponent<MeshRenderer>(); blankerRenderer.sharedMaterial = material;
            reference = ScriptableObject.CreateInstance<CinematicVideoReference>(); reference.name = request.Name;
            bool nailsmith = request.Name == "Nailsmith";
            Set(reference, "videoFileLength", FrameCount(request.Name) / FrameRate(request.Name)); Set(reference, "videoFileFrameRate", FrameRate(request.Name));
            Set(reference, "videoFileWidth", nailsmith ? 1912 : 1920); Set(reference, "videoFileHeight", 1080);
            if (referenceAudio != null) Set(reference, "audio", referenceAudio);
            sequence = root.AddComponent<CinematicSequence>();
            Set(sequence, "targetRenderer", target); Set(sequence, "blankerRenderer", blankerRenderer);
            Set(sequence, "autoScaleToHUDCamera", false); sequence.VideoReference = reference;
            root.SetActive(true); sequence.Begin();
            sound = root.GetComponent<AudioSource>();
            video = target.GetComponent<VideoPlayer>();
            ObserveVideo();
        }

        private void OnGUI()
        {
            if (request == null || observingNative) return;
            GUI.depth = -10000;
            GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), Texture2D.blackTexture);
            if (video != null && video.texture != null)
                GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), video.texture, ScaleMode.ScaleToFit);
        }

        private void Finish()
        {
            var result = new { request, sourceUrl, endCallbacks, skipSent, skipVideoTime, skipModeAtRequest, firstReadyFrame, endingFrame,
                controller,skipped = sequence != null ? sequence.IsSkipped : skipSent,
                elapsed = Time.realtimeSinceStartup - started, errors, samples, captureDirectory, captureIndex, beganInScene,
                endedInScene = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name,
                separateAudio = sourceAudio,
                scope = observingNative ? (request != null && request.SkipAt >= 0
                    ? "Actual native scene, rendering and AudioClip; timed GameManager.SkipCutscene request only when native skipMode allows it; physical keyboard skip not asserted"
                    : "Passive observation of actual native cinematic scene; original scene controller, rendering and AudioClip; no forced skip or replacement test player")
                    : "Native CinematicSequence component on title menu; original decoded AudioClip fixture when specified; actual story/scene controller not exercised" };
            File.WriteAllText(PathFor("hollowcraft-cinematic-probe-result.json"), JsonConvert.SerializeObject(result));
            request = null;
            if (menuEvents != null) menuEvents.enabled = menuEventsEnabled;
            menuEvents = null;
            if (sequence != null) sequence.OnPlaybackEnded -= PlaybackEnded;
            if (root != null) { root.SetActive(false); Destroy(root); }
            if (reference != null && !observingNative) Destroy(reference);
            if (material != null) Destroy(material);
            if (referenceAudio != null && !observingNative) Destroy(referenceAudio);
            root = null; reference = null; material = null; sequence = null; nativePlayer=null;video = null;
            referenceAudio = null; sound = null; loadingAudio = observingNative = false;
        }
    }
}
