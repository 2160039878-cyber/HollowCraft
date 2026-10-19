using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using HollowCraft.Link;
using InControl;
using Newtonsoft.Json;
using UnityEngine;

namespace HollowCraft
{
    // Explicit development mode only: exercises real InControl bindings and the real MC input ring.
    internal sealed class RuntimeProbe
    {
        public sealed class Step
        {
            public float Duration = .5f;
            public int Move, Slot;
            public int GGEnding;
            public int SealEnding;
            public int PhysicsPollDelay;
            public bool RenderOnly, TrackRenderPose, InspectTerrain, SaveCheckpoint, RestoreRoom, CloseRecovery;
            public bool AbortOnDamage, HandPlacedTnt;
            public int Look;
            public int Damage;
            public int DamageSide;
            public bool Block;
            public string Arena;
            public string[] Targets;
            public int[] Charms;
            public float? AimX, AimY;
            public float? PlaceX, PlaceY;
            public bool Jump, Attack, Dash, Focus, DreamNail, Pause, Inventory, Refill, ReturnSafe, HideOverlay, Capture, DumpVisuals, TrackCombat, TrackStory, DreamUpgrade, DreamGateReward, AbyssDream, RadianceAscend, SealFinish, AutoFight, Godseeker, StagStations, Quit;
        }
        public static bool BackgroundInput { get; private set; }
        public static Vector2? AimOverride { get; private set; }
        public static bool ShieldHeld { get; private set; }
        internal static int PhysicsPollDelay { get; private set; }
        internal static int TakePhysicsPollDelay() { int delay=PhysicsPollDelay;PhysicsPollDelay=0;return delay; }
        private static float transitionUntil;
        public static bool HiddenWindow { get; } = Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test") >= 0
            && Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-background") >= 0;
        public static bool HasInputFocus => BackgroundInput || Time.realtimeSinceStartup < transitionUntil || (!HiddenWindow && Application.isFocused);
        private static readonly uint ProcessId = (uint)System.Diagnostics.Process.GetCurrentProcess().Id;
        private delegate bool VisitWindow(IntPtr window, IntPtr state);
        [DllImport("user32.dll")] private static extern bool EnumWindows(VisitWindow visit, IntPtr state);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint pid);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")] private static extern bool ShowWindow(IntPtr window, int command);
        [DllImport("user32.dll",CharSet=CharSet.Unicode)] private static extern int GetClassNameW(IntPtr window,System.Text.StringBuilder name,int length);
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
        [DllImport("user32.dll")] private static extern IntPtr GetThreadDesktop(uint thread);
        [DllImport("user32.dll")] private static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint access);
        [DllImport("user32.dll")] private static extern bool CloseDesktop(IntPtr desktop);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)]
        private static extern bool GetUserObjectInformationW(IntPtr handle, int index, System.Text.StringBuilder name, uint length, out uint needed);
        private static string DesktopName(IntPtr desktop)
        {
            var name=new System.Text.StringBuilder(256);
            return desktop!=IntPtr.Zero && GetUserObjectInformationW(desktop,2,name,512,out _) ? name.ToString() : null;
        }
        private static bool OnPrivateDesktop()
        {
            string current=DesktopName(GetThreadDesktop(GetCurrentThreadId()));
            if(current==null || !current.StartsWith("HollowCraft-",StringComparison.Ordinal)
                || !Guid.TryParseExact(current.Substring(12),"N",out _)) return false;
            IntPtr input=OpenInputDesktop(0,false,1);
            try { string active=DesktopName(input);return active!=null && active!=current; }
            finally { if(input!=IntPtr.Zero) CloseDesktop(input); }
        }
        private static readonly bool PresentRequested=Array.IndexOf(Environment.GetCommandLineArgs(),"-hollowcraft-present")>=0;
        private bool presentationMode;
        private int nativeCameraFrames;
        private Unity.Profiling.ProfilerRecorder cpuTimingRecorder, gpuTimingRecorder;
        private readonly FrameTiming[] frameTimings=new FrameTiming[8];
        private struct NativeFrameSample { public double t;public int step,cameraFrames;public FrameTiming timing; }
        private readonly List<NativeFrameSample> nativeFrames=new List<NativeFrameSample>(8192);
        private struct VisualFrame { public float t,spriteX,spriteY,bodyX,bodyY,feetOffset,avatarX,avatarY;public int step,interpolation;public bool native; }
        private readonly List<VisualFrame> visualFrames=new List<VisualFrame>();
        private ulong lastNativeFrame;
        private static bool OwnsForegroundWindow()
        {
            GetWindowThreadProcessId(GetForegroundWindow(), out uint pid);
            return pid == ProcessId;
        }
        private int visibleWindows = -1;
        private float nextWindowCheck;
        private void KeepHidden()
        {
            if (!HiddenWindow || Time.realtimeSinceStartup < nextWindowCheck) return;
            nextWindowCheck = Time.realtimeSinceStartup + .25f; visibleWindows = 0;
            // Exercise the normal renderer only on our inactive desktop; never expose a test window on the user's desktop.
            presentationMode=PresentRequested && OnPrivateDesktop();
            if(!presentationMode)
            {
                QualitySettings.vSyncCount = 0;
                Application.targetFrameRate = 60;
            }
            if (!EnumWindows((window, state) => {
                GetWindowThreadProcessId(window, out uint pid);
                if (pid == ProcessId) {
                    var name=new System.Text.StringBuilder(256);
                    bool show=presentationMode && GetClassNameW(window,name,name.Capacity)>0 && name.ToString()=="UnityWndClass";
                    if(IsWindowVisible(window)!=show) ShowWindow(window,show ? 4 : 0);
                    if (IsWindowVisible(window)) visibleWindows++;
                }
                return true;
            }, IntPtr.Zero)) visibleWindows = -1;
        }
        private static readonly System.Reflection.FieldInfo JumpedSteps = typeof(HeroController).GetField("jumped_steps",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);
        private static readonly System.Reflection.FieldInfo InvulnerableDuration = typeof(HeroController).GetField("invulnerableDuration",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);
        private static readonly System.Reflection.FieldInfo MantisAirJumpUsed = typeof(HeroController).GetField("doubleJumped",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);
        private sealed class ProbeBinding : KeyBindingSource
        {
            private readonly Func<bool> pressed;
            public ProbeBinding(KeyCombo keys, Func<bool> pressed) : base(keys) { this.pressed = pressed; }
            public override bool GetState(InputDevice device) => BackgroundInput ? pressed() : base.GetState(device);
        }
        private Step[] steps;
        private readonly List<object> samples = new List<object>();
        private readonly List<object> hits = new List<object>();
        private readonly List<object> deaths = new List<object>();
        private readonly List<object> contacts = new List<object>();
        private readonly List<object> captures = new List<object>();
        private readonly List<object> requests = new List<object>(), transfers = new List<object>();
        private readonly List<object> damage = new List<object>();
        private readonly List<object> received = new List<object>(), combatSamples = new List<object>(), bounces = new List<object>();
        private readonly List<object> storySamples=new List<object>();
        private readonly List<object> suppressedAchievements=new List<object>();
        private readonly float[] audioSamples=new float[256];
        private float nextStorySample;
        private string pendingCapture;
        private struct RenderSample { public double t,intervalMs,renderMs,engineMs,statusMs,physicsMs,runtimeMs,probeMs,drainMs,replicaMs;public int step,cameras;public float timeScale; }
        private readonly List<RenderSample> renderedFrames=new List<RenderSample>(8192);
        private RenderTexture renderTarget;
        private Texture2D renderPixel;
        private Camera[] renderCameras;
        private long lastRenderTick;
        private object renderContext;
        private ProbeAudio audioRecorder;
        private object recordedAudio;
        private float nextCombatSample;
        private float nextEnemyScan;
        private HealthManager[] observedEnemies = Array.Empty<HealthManager>();
        private int autoMove, autoLook;
        private bool autoAttack, autoJump, autoDash, autoFocus, autoBlock;
        private float bowUntil, bowStarted, nextBowAt, nextAutoSlot;
        private bool crossbowLoaded = true, crossbowReloading;
        private float handBuildStarted, handIgnitionStarted, handNextSlot;
        private int handBuildIndex, handTntX, handBaseY, handCurrentSlot;
        private float jumpUntil, nextAutoJump, dashUntil, nextAutoDash, attackUntil, nextAutoAttack;
        private float mantisEscapeUntil;
        private int mantisEscapeDirection;
        private float mantisDropUntil;
        private int mantisDropDirection;
        private int mantisFallingId;
        private float guardUntil;
        private int guardDirection;
        private bool abortForDamage;
        private readonly Dictionary<int,(Vector2 position,Vector2 velocity,float time)> mantisShots = new Dictionary<int,(Vector2,Vector2,float)>();
        private int pendingDamage;
        private uint lastControl, lastAck, lastHeldFlags;
        private bool lastNative;
        private HeroActions boundActions;
        private int index;
        private float started, stepStarted, nextSample, nextPoll;
        private int slotDown;
        private bool wroteAnimations;
        private bool previousSuspend;
        private uint world, epoch;
        private readonly RecoveryTools recovery;
        private readonly Action<Vector2> placePlayer;
        private string captureDirectory;
        private float nextCapture;
        private int captureIndex;
        private Step Current => steps != null && index < steps.Length ? steps[index] : null;
        internal bool MeasuringRender => Current?.RenderOnly==true || presentationMode;
        private string Directory => Application.persistentDataPath;

        public RuntimeProbe(RecoveryTools recovery, Action<Vector2> placePlayer)
        {
            this.recovery=recovery;
            this.placePlayer = placePlayer;
            KeepHidden();
            Camera.onPostRender += camera => {
                if(presentationMode && GameCameras.instance!=null && camera==GameCameras.instance.mainCamera) nativeCameraFrames++;
            };
            On.HealthManager.Hit += RecordHit;
            On.HealthManager.ApplyExtraDamage += RecordExtraDamage;
            On.HealthManager.Die += RecordDeath;
            On.HeroController.OnCollisionEnter2D += RecordContact;
            On.HeroController.TakeDamage += RecordDamage;
            On.HeroController.Bounce += RecordBounce;
            On.AchievementHandler.AwardAchievementToPlayer += (original,handler,key) => {
                if(steps!=null) suppressedAchievements.Add(new {t=Time.realtimeSinceStartup-started,key});
                Log.Info("Test mode suppressed achievement: "+key);
            };
        }

        private void RecordDamage(On.HeroController.orig_TakeDamage original, HeroController hero, GameObject source,
            GlobalEnums.CollisionSide side, int amount, int hazard)
        {
            int before = PlayerData.instance.health;
            string sourceName = source != null ? source.name : null;
            original(hero, source, side, amount, hazard);
            if(steps!=null && Current.AbortOnDamage && before>PlayerData.instance.health) abortForDamage=true;
            if (steps != null && PlayerData.instance.health == 0) transitionUntil = Time.realtimeSinceStartup + 30;
            if (steps != null && received.Count < 10000)
                received.Add(new { t = Time.realtimeSinceStartup - started, source = sourceName, side = side.ToString(), amount, hazard,
                    before, after = PlayerData.instance.health, hero.cState.invulnerable, x = hero.transform.position.x, y = hero.transform.position.y });
        }

        private void RecordBounce(On.HeroController.orig_Bounce original, HeroController hero)
        {
            original(hero);
            if (steps != null) bounces.Add(new { t = Time.realtimeSinceStartup - started,
                x = hero.transform.position.x, y = hero.transform.position.y, velocityY = hero.GetComponent<Rigidbody2D>().linearVelocity.y });
        }

        private void RecordContact(On.HeroController.orig_OnCollisionEnter2D original, HeroController hero, Collision2D collision)
        {
            original(hero, collision);
            if (steps == null || contacts.Count >= 10000) return;
            Rigidbody2D body = hero.GetComponent<Rigidbody2D>();
            var points = new List<object>();
            for (int i = 0; i < Math.Min(8, collision.contactCount); i++)
            {
                ContactPoint2D point = collision.GetContact(i);
                points.Add(new { x = point.point.x, y = point.point.y, nx = point.normal.x, ny = point.normal.y });
            }
            contacts.Add(new { t = Time.realtimeSinceStartup - started, other = collision.gameObject.name,
                x = body.position.x, y = body.position.y, vx = body.linearVelocity.x, vy = body.linearVelocity.y, points });
        }

        private void RecordHit(On.HealthManager.orig_Hit original, HealthManager enemy, HitInstance hit)
        {
            int before = enemy.hp; string name = enemy.name; int id = enemy.GetInstanceID();
            bool invincible = enemy.IsInvincible; int blockedDirection = enemy.InvincibleFromDirection;
            original(enemy, hit);
            if (steps != null && hits.Count < 10000)
                hits.Add(new { t = Time.realtimeSinceStartup - started, id, name, before, after = enemy.hp, invincible, blockedDirection,
                    hit.DamageDealt, hit.Direction, hit.IgnoreInvulnerable, hit.MagnitudeMultiplier, attackType = hit.AttackType.ToString(),
                    sourceId = hit.Source != null ? hit.Source.GetInstanceID() : 0, source = hit.Source != null ? hit.Source.name : null });
        }

        private void RecordExtraDamage(On.HealthManager.orig_ApplyExtraDamage original,HealthManager enemy,int amount)
        {
            int before=enemy.hp,id=enemy.GetInstanceID();string name=enemy.name;
            original(enemy,amount);
            if(steps!=null && hits.Count<10000)
                hits.Add(new {t=Time.realtimeSinceStartup-started,id,name,before,after=enemy.hp,DamageDealt=amount,
                    attackType="NativeExtra",source="Native extra damage",IgnoreInvulnerable=(bool?)null});
        }

        private void RecordDeath(On.HealthManager.orig_Die original,HealthManager enemy,float? direction,AttackTypes type,bool ignoreEvasion)
        {
            string name=enemy.name;int id=enemy.GetInstanceID(),hp=enemy.hp;
            bool nativeResponder=ReferenceEquals(enemy.GetComponent<IHitResponder>(),enemy);
            original(enemy,direction,type,ignoreEvasion);
            if(steps!=null) deaths.Add(new {t=Time.realtimeSinceStartup-started,id,name,hp,nativeResponder,attackType=type.ToString(),ignoreEvasion});
        }

        public void Frame(HeroController hero, HostState host, McState mc, bool nativeControl, bool peerReady, int actorCount)
        {
            KeepHidden();
            if(steps!=null && abortForDamage) {Cancel("damage observed");return;}
            if (steps != null && (world != host.WorldId || epoch != host.CollisionEpoch))
            { Cancel("scene scope changed"); return; }
            if (hero == null || GameManager.instance == null) return;
            if (steps == null && peerReady && hero.acceptingInput && !hero.controlReqlinquished
                && GameManager.instance.gameState == GlobalEnums.GameState.PLAYING) transitionUntil = 0;
            var animator = hero.GetComponent<tk2dSpriteAnimator>();
            if (!wroteAnimations && animator != null && animator.Library != null)
            {
                File.WriteAllText(Path.Combine(Directory, "hollowcraft-animation-clips.json"), JsonConvert.SerializeObject(
                    animator.Library.clips.Select(clip => new { clip.name, clip.fps, frames = clip.frames.Length, wrap = clip.wrapMode.ToString() })));
                wroteAnimations = true;
            }
            HeroActions actions = GameManager.instance.inputHandler.inputActions;
            if (actions != boundActions)
            {
                Bind(actions.left, () => Current?.AutoFight == true ? autoMove < 0 : Current?.Move < 0);
                Bind(actions.right, () => Current?.AutoFight == true ? autoMove > 0 : Current?.Move > 0);
                Bind(actions.jump, () => Current?.AutoFight == true ? autoJump : Current?.Jump == true);
                Bind(actions.attack, () => Current?.AutoFight == true ? autoAttack : Current?.Attack == true);
                Bind(actions.up, () => Current?.AutoFight == true ? autoLook > 0 : Current?.Look > 0);
                Bind(actions.down, () => Current?.AutoFight == true ? autoLook < 0 : Current?.Look < 0);
                Bind(actions.dash, () => Current?.AutoFight == true ? autoDash : Current?.Dash == true);
                Bind(actions.dreamNail, () => Current?.DreamNail==true);
                if (actions.cast.Bindings.OfType<KeyBindingSource>().Any())
                    Bind(actions.cast, () => Current?.AutoFight == true ? autoFocus : Current?.Focus == true);
                if (actions.focus.Bindings.OfType<KeyBindingSource>().Any())
                    Bind(actions.focus, () => Current?.AutoFight == true ? autoFocus : Current?.Focus == true);
                Bind(actions.pause, () => Current?.Pause == true);
                boundActions = actions;
            }
            float now = Time.realtimeSinceStartup;
            if (steps == null && now >= nextPoll)
            {
                nextPoll = now + .25f;
                string path = Path.Combine(Directory, "hollowcraft-probe.json");
                if (!File.Exists(path)) return;
                try
                {
                    if (new FileInfo(path).Length > 65536) throw new InvalidDataException("Probe request too large");
                    Step[] request = JsonConvert.DeserializeObject<Step[]>(File.ReadAllText(path));
                    if (request == null || request.Length == 0 || request.Length > 1000 || request.Any(s => s == null
                        || !DamageRules.Finite(s.Duration) || s.Duration < .05f || s.Duration > 10
                        || Math.Abs(s.Move) > 1 || Math.Abs(s.Look) > 1 || s.Slot < 0 || s.Slot > 9 || s.Damage < 0 || s.Damage > 1 || Math.Abs(s.DamageSide)>1
                        || s.PhysicsPollDelay<0 || s.PhysicsPollDelay>100
                        || s.RenderOnly && (PresentRequested || s.Capture || s.DumpVisuals || s.InspectTerrain || s.SaveCheckpoint || s.RestoreRoom || s.CloseRecovery)
                        || (s.SaveCheckpoint || s.RestoreRoom || s.CloseRecovery) && (s.Arena!=null || s.PlaceX.HasValue || s.ReturnSafe || s.Quit)
                        || (s.SaveCheckpoint && s.RestoreRoom) || (s.CloseRecovery && (s.SaveCheckpoint || s.RestoreRoom))
                        || (s.Arena != null && s.Arena != "GG_False_Knight" && s.Arena != "GG_Hornet_1" && s.Arena != "GG_Mantis_Lords" && s.Arena != "GG_Mantis_Lords_V"
                            && s.Arena != "Ruins2_01" && s.Arena != "Fungus1_02" && s.Arena != "RestingGrounds_07" && s.Arena != "RestingGrounds_04" && s.Arena != "Abyss_15" && s.Arena != "Dream_Final_Boss" && s.Arena != "GG_Radiance"
                            && s.Arena != "Room_nailmaster" && s.Arena != "Room_nailmaster_02" && s.Arena != "Room_nailmaster_03" && s.Arena != "Room_Town_Stag_Station" && s.Arena!="Room_Final_Boss_Core"
                            && s.Arena!="Crossroads_50" && s.Arena!="Ruins_Bathhouse")
                        || s.SealEnding<0 || s.SealEnding>2 || s.SealEnding!=0 && s.Arena!="Room_Final_Boss_Core"
                        || s.Arena=="Room_Final_Boss_Core" && s.SealEnding==0
                        || s.SealFinish && (s.Arena!=null || UnityEngine.SceneManagement.SceneManager.GetActiveScene().name!="Room_Final_Boss_Core")
                        || s.GGEnding<0 || s.GGEnding>2 || s.GGEnding!=0 && (s.Arena!="GG_Radiance" || !s.Godseeker)
                        || s.Arena=="GG_Radiance" && s.GGEnding==0
                        || (s.Godseeker && (s.Arena == null || !s.Arena.StartsWith("GG_", StringComparison.Ordinal)))
                        || (s.DreamUpgrade && s.Arena!="RestingGrounds_07")
                        || (s.DreamGateReward && (s.Arena!="RestingGrounds_07" || s.DreamUpgrade))
                        || (s.StagStations && s.Arena!="Room_Town_Stag_Station")
                        || (s.AbyssDream && s.Arena!="Abyss_15")
                        || (s.RadianceAscend && (s.Arena!=null || UnityEngine.SceneManagement.SceneManager.GetActiveScene().name!="Dream_Final_Boss"
                            && UnityEngine.SceneManagement.SceneManager.GetActiveScene().name!="GG_Radiance"))
                        || (s.Charms != null && (!s.Godseeker || s.Charms.Length > 3 || s.Charms.Any(c => c != 7 && c != 13 && c != 23 && c != 25 && c != 32 && c != 38)
                            || s.Charms.Distinct().Count() != s.Charms.Length))
                        || (s.AutoFight && (s.Targets == null || s.Targets.Length == 0 || s.Targets.Length > 4
                            || s.Targets.Any(t => string.IsNullOrWhiteSpace(t) || t.Length > 64) || s.AimX.HasValue))
                        || s.AimX.HasValue != s.AimY.HasValue
                        || s.PlaceX.HasValue != s.PlaceY.HasValue
                        || (s.PlaceX.HasValue && (!DamageRules.Finite(s.PlaceX.Value) || !DamageRules.Finite(s.PlaceY.Value)
                            || Mathf.Abs(s.PlaceX.Value) > 10000 || Mathf.Abs(s.PlaceY.Value) > 10000))
                        || (s.AimX.HasValue && (!DamageRules.Finite(s.AimX.Value) || !DamageRules.Finite(s.AimY.Value)
                            || Mathf.Abs(s.AimX.Value) > 10000 || Mathf.Abs(s.AimY.Value) > 10000)))) throw new InvalidDataException("Invalid probe steps");
                    // Native bench/menu input must be able to release a loading pause before Minecraft is ready.
                    if (!peerReady && request.Any(s => !s.Quit && (!nativeControl || s.Slot != 0 || s.Inventory || s.Refill
                        || s.Arena != null || s.PlaceX.HasValue || s.ReturnSafe || s.SaveCheckpoint || s.RestoreRoom || s.Damage != 0 || s.AutoFight || s.RadianceAscend || s.SealFinish))) return;
                    if (request.Any(s => s.Arena != null || s.PlaceX.HasValue || s.RadianceAscend) && !CanNavigate(hero)) return;
                    File.Delete(path);
                    steps = request; samples.Clear(); hits.Clear(); contacts.Clear(); captures.Clear(); requests.Clear(); transfers.Clear(); index = 0;
                    damage.Clear(); received.Clear(); combatSamples.Clear(); bounces.Clear(); deaths.Clear();abortForDamage=false; pendingDamage = 0; nextCombatSample = nextEnemyScan = now;
                    if(request.Any(s=>s.HandPlacedTnt)) {handBuildIndex=handCurrentSlot=0;handBuildStarted=handIgnitionStarted=0;}
                    renderedFrames.Clear();renderContext=null;lastRenderTick=0;
                    nativeFrames.Clear();visualFrames.Clear();lastNativeFrame=0;
                    if(presentationMode)
                    {
                        cpuTimingRecorder=Unity.Profiling.ProfilerRecorder.StartNew(Unity.Profiling.ProfilerCategory.Internal,"CPU Total Frame Time");
                        gpuTimingRecorder=Unity.Profiling.ProfilerRecorder.StartNew(Unity.Profiling.ProfilerCategory.Internal,"GPU Frame Time");
                    }
                    storySamples.Clear();suppressedAchievements.Clear();nextStorySample=now;
                    lastControl = lastAck = lastHeldFlags = uint.MaxValue;
                    world = host.WorldId; epoch = host.CollisionEpoch;
                    previousSuspend = InputManager.SuspendInBackground;
                    InputManager.SuspendInBackground = false;
                    BackgroundInput = true;
                    transitionUntil = 0;
                    started = stepStarted = nextSample = now;
                    captureIndex = 0; nextCapture = now;
                    captureDirectory = request.Any(s => s.Capture) ? Path.Combine(System.IO.Directory.GetParent(Application.dataPath).Parent.FullName,
                        "work-assets","runtime-captures", Guid.NewGuid().ToString("N")) : null;
                    if (captureDirectory != null) System.IO.Directory.CreateDirectory(captureDirectory);
                    recordedAudio=null;
                    if(captureDirectory!=null)
                    {
                        var listener=UnityEngine.Object.FindObjectsByType<AudioListener>(FindObjectsSortMode.None).FirstOrDefault(a=>a.enabled);
                        if(listener==null) throw new InvalidOperationException("Native audio listener unavailable");
                        audioRecorder=listener.gameObject.AddComponent<ProbeAudio>();audioRecorder.Begin(captureDirectory,started);
                    }
                    StartStep();
                }
                // A published request may be temporarily locked. Consume it only after deletion succeeds.
                catch (IOException e) when(steps==null && ((e.HResult & 0xffff)==32 || (e.HResult & 0xffff)==33)) { return; }
                catch (Exception e) { Stop(); WriteResult(new { error = e.Message }); File.Delete(path); }
            }
            if (steps == null) return;
            if(Current.TrackStory && now>=nextStorySample)
            {
                nextStorySample=now+.1f;
                AudioListener.GetOutputData(audioSamples,0);
                var actors=UnityEngine.Object.FindObjectsByType<tk2dSpriteAnimator>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                    .Where(a=>a==animator || a.name=="Dream Moth" || a.name.IndexOf("Witch",StringComparison.OrdinalIgnoreCase)>=0
                        || a.name=="Hollow Knight Boss" || a.name=="Boss Corpse" || a.name.StartsWith("Hornet",StringComparison.Ordinal)
                        || a.name.StartsWith("NM ",StringComparison.Ordinal) || a.name.IndexOf("Nailmaster",StringComparison.OrdinalIgnoreCase)>=0 || a.name.IndexOf("Stag",StringComparison.OrdinalIgnoreCase)>=0
                        || a.Library!=null && (a.Library.name=="Quirrel" || a.Library.name=="Knight Dream Custcene Anim"
                        || a.Library.name=="Abyss Dream Anim" || a.Library.name=="Sibling Anim" || a.Library.name=="Shade Lord Anim" || a.name=="Death Glow" && a.Library.name=="Hollow Shade"
                        || a.Library.name=="Radiance Anim" && (a.name=="Radiance" || a.name=="Absolute Radiance" || Render.RadianceActor.CanReplace((a.CurrentClip ?? a.DefaultClip)?.name))))
                    .Select(a=>new {a.name,library=a.Library?.name,active=a.gameObject.activeInHierarchy,clip=a.CurrentClip?.name,frame=a.CurrentClip!=null ? a.CurrentFrame : -1,
                        visible=a.GetComponent<Renderer>()?.enabled,hidden=a.GetComponent<Renderer>()?.forceRenderingOff,
                        minY=a.GetComponent<Renderer>()?.bounds.min.y,maxY=a.GetComponent<Renderer>()?.bounds.max.y,
                        x=a.transform.position.x,y=a.transform.position.y,layer=a.gameObject.layer}).ToArray();
                var story=UnityEngine.Object.FindObjectsByType<PlayMakerFSM>(FindObjectsSortMode.None)
                    .Where(f=>f.name=="Dream Moth" || f.name=="Mirror" || f.name=="Dream Enter Abyss" || f.name=="Entry Cutscene" || f.name=="End Cutscene"
                        || f.name=="Dreamer Scene 2" || f.name=="Dreamer Plaque Inspect" || f.name=="Witch Control" || f.name=="Dream Nail Get"
                        || f.name=="Dream Entry" || f.name=="Boss Control" || f.name=="Radiance" || f.name=="Absolute Radiance" || f.name=="Knight Ball"
                        || f.name=="Boss Scene Controller" || f.name=="Shade_Lord" || f.name=="Shade Lord Hand" || f.name=="Cinematic Player"
                        || f.name=="Hollow Knight Boss" || f.name=="Boss Corpse" || f.name.StartsWith("Hornet",StringComparison.Ordinal)
                        || f.name=="Sit Region" || f.name=="Quirrel Lakeside" || f.name=="Ghost NPC" || f.name.StartsWith("NM ",StringComparison.Ordinal) || f.name.IndexOf("Nailmaster",StringComparison.OrdinalIgnoreCase)>=0 || f.name.IndexOf("Stag",StringComparison.OrdinalIgnoreCase)>=0
                        || f.gameObject==hero.gameObject && (f.FsmName=="Dream Nail" || f.FsmName=="Dream Return"))
                    .Select(f=>new {f.name,f.FsmName,f.ActiveStateName}).ToArray();
                var mirrors=UnityEngine.Object.FindObjectsByType<PlanarRealtimeReflection>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                    .Select(m=>new {m.name,m.enabled,active=m.gameObject.activeInHierarchy,mask=m.m_ReflectLayers.value,
                        visible=m.GetComponent<Renderer>()?.enabled,texture=m.GetComponent<Renderer>()?.sharedMaterial?.GetTexture("_ReflectionTex")?.name}).ToArray();
                var sound=UnityEngine.Object.FindObjectsByType<AudioSource>(FindObjectsSortMode.None)
                    .Where(a=>a.isPlaying && a.clip!=null).Select(a=>new {a.name,clip=a.clip.name,a.volume,a.mute,a.time}).ToArray();
                var fragments=UnityEngine.Object.FindObjectsByType<SpriteRenderer>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                    .Where(r=>r.sprite!=null && (r.sprite.name=="hollow_knight_skull_left" || r.sprite.name=="hollow_knight_skull_right"))
                    .Select(r=>new {r.name,sprite=r.sprite.name,active=r.gameObject.activeInHierarchy,r.enabled,hidden=r.forceRenderingOff,
                        x=r.transform.position.x,y=r.transform.position.y}).ToArray();
                var lords=UnityEngine.Object.FindObjectsByType<Animator>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                    .Where(a=>a.runtimeAnimatorController!=null && a.runtimeAnimatorController.name=="Shade_Lord")
                    .Select(a=>new {a.name,active=a.gameObject.activeInHierarchy,parts=a.GetComponentsInChildren<SpriteRenderer>(true)
                        .Select(r=>new {r.name,active=r.gameObject.activeInHierarchy,r.enabled,hidden=r.forceRenderingOff,sprite=r.sprite?.name,r.color.a}).ToArray()}).ToArray();
                int rigs=UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None)
                    .Count(r=>r.enabled && r.gameObject.activeInHierarchy && r.transform.root.name=="HollowCraft Steve replica");
                var rigBounds=UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None)
                    .Where(r=>r.enabled && r.gameObject.activeInHierarchy && r.transform.root.name=="HollowCraft Steve replica")
                    .GroupBy(r=>r.transform.root).Select(g=>new {x=g.Key.position.x,minY=g.Min(r=>r.bounds.min.y),maxY=g.Max(r=>r.bounds.max.y)}).ToArray();
                storySamples.Add(new {t=now-started,scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name,
                    hero.acceptingInput,hero.controlReqlinquished,hasDreamNail=PlayerData.instance.GetBool("hasDreamNail"),
                    PlayerData.instance.hasDreamGate,PlayerData.instance.dreamReward5b,PlayerData.instance.dreamOrbs,
                    PlayerData.instance.dreamGateScene,PlayerData.instance.dreamGateX,PlayerData.instance.dreamGateY,
                    fixtureInvincible=PlayerData.instance.GetBool("isInvincible"),
                    BossSequenceController.IsInSequence,BossSequenceController.BossIndex,BossSequenceController.BossCount,BossSequenceController.WasCompleted,
                    PlayerData.instance.givenGodseekerFlower,PlayerData.instance.bossRushMode,PlayerData.instance.openedBlackEggDoor,tier5Complete=PlayerData.instance.bossDoorStateTier5.completed,
                    PlayerData.instance.hasCyclone,PlayerData.instance.hasDashSlash,PlayerData.instance.hasUpwardSlash,
                    PlayerData.instance.travelling,PlayerData.instance.stagPosition,PlayerData.instance.nextScene,
                    PlayerData.instance.openedTown,PlayerData.instance.openedCrossroads,PlayerData.instance.geo,
                    PlayerData.instance.gotShadeCharm,
                    upgraded=PlayerData.instance.GetBool("dreamNailUpgraded"),royalCharm=PlayerData.instance.GetInt("royalCharmState"),
                    charmCost=PlayerData.instance.GetInt("charmCost_36"),charmSlotsFilled=PlayerData.instance.GetInt("charmSlotsFilled"),
                    actors,story,sound,rigs,rigBounds,mirrors,fragments,lords,overlay=Render.Overlay.Instance?.Show,
                    audioPeak=audioSamples.Max(v=>Math.Abs(v))});
            }
            if ((Current.TrackCombat || Current.AutoFight) && now >= nextEnemyScan)
            {
                nextEnemyScan = now + .1f;
                observedEnemies = UnityEngine.Object.FindObjectsByType<HealthManager>(FindObjectsSortMode.None);
            }
            if ((Current.TrackCombat || Current.AutoFight) && now >= nextCombatSample)
            {
                nextCombatSample = now + (Current.AutoFight ? .1f : MeasuringRender ? .5f : .1f);
                var targets = observedEnemies.Where(enemy=>enemy!=null).Take(128).Select(enemy => new { id = enemy.GetInstanceID(), objectId = enemy.gameObject.GetInstanceID(), enemy.enabled,
                        enemy.name, enemy.hp, enemy.IsInvincible, enemy.InvincibleFromDirection,
                        nativeResponder = ReferenceEquals(enemy.GetComponent<IHitResponder>(), enemy),
                        x = enemy.transform.position.x, y = enemy.transform.position.y,
                        animation = enemy.GetComponent<tk2dSpriteAnimator>()?.CurrentClip?.name,
                        colliders = enemy.GetComponentsInChildren<Collider2D>().Select(c => new { c.name, c.enabled, c.isTrigger, c.gameObject.layer,
                            x = c.bounds.center.x, y = c.bounds.center.y, width = c.bounds.size.x, height = c.bounds.size.y }).ToArray(),
                        fsms = enemy.GetComponents<PlayMakerFSM>().Select(f => new { f.FsmName, f.ActiveStateName }).ToArray() }).ToArray();
                combatSamples.Add(new { t = now - started, step = index, scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name,
                    x = hero.transform.position.x, y = hero.transform.position.y, hp = PlayerData.instance.health,
                    maxHp = PlayerData.instance.maxHealth, charms = PlayerData.instance.equippedCharms.ToArray(), actorCount, targets });
            }
            if (Current.AutoFight) UpdateCombatInput(hero, mc);
            ShieldHeld = Current.Block || Current.AutoFight && autoBlock;
            if (lastControl != host.ControlSeq || lastAck != mc.ControlAck || lastHeldFlags != mc.HeldFlags || lastNative != nativeControl)
            {
                transfers.Add(new { t = now - started, step = index, host.ControlSeq, mc.ControlAck, mc.HeldFlags, native = nativeControl });
                lastControl = host.ControlSeq; lastAck = mc.ControlAck; lastHeldFlags = mc.HeldFlags; lastNative = nativeControl;
            }
            if (Current.Capture && now >= nextCapture && now-stepStarted<Current.Duration)
            {
                nextCapture = now + .05f;
                captures.Add(new { index = captureIndex, t = now - started, step = index });
                string capture=Path.Combine(captureDirectory,$"{captureIndex++:D5}.png");
                if(HiddenWindow) pendingCapture=capture;else ScreenCapture.CaptureScreenshot(capture);
            }
            if (slotDown != 0 && now - stepStarted >= .12f) ReleaseSlot();
            if (now >= nextSample)
            {
                nextSample = now + (MeasuringRender ? .25f : 1f / 60);
                var body = hero.GetComponent<Rigidbody2D>();
                samples.Add(new { t = now - started, realtime=Time.realtimeSinceStartupAsDouble, step = index, x = hero.transform.position.x, y = hero.transform.position.y,
                    physicsX = body.position.x, physicsY = body.position.y, physicsVelocityX = body.linearVelocity.x, physicsVelocityY = body.linearVelocity.y,
                    gravityScale = body.gravityScale,
                    unityTime = Time.time, fixedTime = Time.fixedTime, fixedStep = Time.fixedDeltaTime,
                    jumpInput = actions.jump.IsPressed, attackInput = actions.attack.IsPressed,
                    jumpedFixedSteps = JumpedSteps == null ? -1 : (int)JumpedSteps.GetValue(hero),
                    hero.cState.jumping, hero.cState.doubleJumping,
                    hp = PlayerData.instance.health, soul = PlayerData.instance.MPCharge, ground = hero.cState.onGround, hero.acceptingInput,
                    hero.cState.invulnerable, hero.cState.attacking, hero.cState.recoiling,
                    hero.cState.recoilFrozen, hero.cState.dashing, hero.cState.focusing, hero.cState.nailCharging,
                    invulnerableDuration = InvulnerableDuration?.GetValue(hero),
                    hero.RECOIL_VELOCITY,
                    native = nativeControl, host.ControlSeq, mc.ControlAck, host.AirJumpUsed,
                    heldItem = mc.HeldItem, heldFlags = mc.HeldFlags, shieldUsing = mc.Has(Proto.McShieldUsing),
                    shieldReady = mc.Has(Proto.McShieldReady), offhandShield = mc.Has(Proto.McOffhandShield), host.JumpHeldSeconds, host.JumpPressSeq,
                    crossbowLoaded = mc.Has(Proto.McCrossbowLoaded),
                    host.PhysicsTick, host.JumpPressTick, host.JumpReleaseTick,
                    mcPhysicsTick = mc.PhysicsTick, mcGround = mc.Has(Proto.McOnGround), scale = Coords.K,
                    mcScreenOpen = mc.Has(Proto.McScreenOpen), hostMenuOpen = (host.Flags & Proto.HostMenuOpen) != 0, mcTickQpc = mc.TickQpc,
                    host.MotionState, mcMotionState = mc.MotionState,
                    host.RunSpeed, host.JumpVelocity, host.Gravity, host.JumpHold, host.DoubleHold,
                    atBench = PlayerData.instance.atBench, hero.controlReqlinquished, hero.cState.nearBench,
                    focused = Application.isFocused, BackgroundInput, InputManager.SuspendInBackground, InputManager.Enabled,
                    HiddenWindow, visibleWindows, ownsForegroundWindow = OwnsForegroundWindow(),
                    presentationMode, nativeCameraFrames, screenWidth=Screen.width, screenHeight=Screen.height,
                    targetFps = Application.targetFrameRate,
                    host.MoveX, mcX = mc.X, mcY = mc.Y, mc.VelocityX, mc.VelocityY, timeScale = Time.timeScale,
                    state = hero.hero_state.ToString(), animation = animator?.CurrentClip?.name,
                    gameState = GameManager.instance.gameState.ToString(), GameManager.instance.isPaused,
                    animationTime = animator!=null && animator.CurrentClip!=null ? animator.ClipTimeSeconds : 0, captureIndex });
            }
            if (now - stepStarted < Current.Duration) return;
            ReleaseSlot();
            if (++index >= steps.Length)
            {
                Stop();
                WriteResult(new { complete = true, samples, hits, deaths, contacts, captureDirectory, captures, audio=recordedAudio, requests, transfers, damage, received, combatSamples, bounces, storySamples, suppressedAchievements,renderContext,renderedFrames,nativeFrames,visualFrames });
                return;
            }
            stepStarted = now;
            StartStep();
        }

        public void Cancel(string reason)
        {
            if (steps == null) return;
            Stop();
            WriteResult(new { cancelled = true, reason, samples, hits, deaths, contacts, captureDirectory, captures, audio=recordedAudio, requests, transfers, damage, received, combatSamples, bounces, storySamples, suppressedAchievements,renderContext,renderedFrames,nativeFrames,visualFrames });
        }
        private void Stop()
        {
            if (steps == null) return;
            ReleaseSlot(); steps = null; BackgroundInput = false; ShieldHeld = false;
            AimOverride = null;
            PhysicsPollDelay=0;
            pendingDamage = 0;
            pendingCapture=null;
            if(renderTarget!=null) {renderTarget.Release();UnityEngine.Object.Destroy(renderTarget);renderTarget=null;}
            if(renderPixel!=null) {UnityEngine.Object.Destroy(renderPixel);renderPixel=null;}
            renderCameras=null;lastRenderTick=0;
            cpuTimingRecorder.Dispose();gpuTimingRecorder.Dispose();
            if(audioRecorder!=null) { recordedAudio=audioRecorder.Finish();UnityEngine.Object.Destroy(audioRecorder);audioRecorder=null; }
            InputManager.ClearInputState();
            InputManager.SuspendInBackground = previousSuspend;
            if (Render.Overlay.Instance != null) Render.Overlay.Instance.DebugHidden = false;
        }

        private static void Bind(PlayerAction action, Func<bool> down)
        {
            var binding = action.Bindings.OfType<KeyBindingSource>().FirstOrDefault();
            if (binding == null) throw new InvalidOperationException("Missing keyboard binding for " + action.Name);
            action.ReplaceBinding(binding, new ProbeBinding(binding.Control, down));
        }
        private void StartStep()
        {
            PhysicsPollDelay=Current.PhysicsPollDelay;
            if(!Current.RenderOnly) lastRenderTick=0;
            if (Current.Quit) { Application.Quit(); return; }
            if ((Current.Arena != null || Current.PlaceX.HasValue || Current.RadianceAscend) && !CanNavigate(HeroController.instance))
            { Cancel("navigation deferred during native death or transition"); return; }
            autoMove = autoLook = 0; autoAttack = autoJump = autoDash = autoFocus = false;
            AimOverride = Current.AimX.HasValue ? new Vector2(Current.AimX.Value, Current.AimY.Value) : (Vector2?)null;
            if(Current.RadianceAscend)
            {
                bool gg=UnityEngine.SceneManagement.SceneManager.GetActiveScene().name=="GG_Radiance";
                var boss=GameObject.Find(gg ? "Boss Control/Absolute Radiance" : "Boss Control/Radiance");
                var control=boss?.GetComponents<PlayMakerFSM>().SingleOrDefault(f=>f.FsmName=="Control");
                var phase=boss?.GetComponents<PlayMakerFSM>().SingleOrDefault(f=>f.FsmName=="Phase Control");
                if(control==null || phase?.ActiveStateName!="Idle 1" || string.IsNullOrEmpty(control.ActiveStateName) || control.ActiveStateName=="Init")
                    throw new InvalidOperationException("Radiance ending fixture requires the active first arena");
                if(gg && (!BossSequenceController.IsInSequence || !BossSequenceController.IsLastBossScene))
                    throw new InvalidOperationException("Absolute Radiance fixture requires the final sequence scene");
                // Ending-only fixture: native teleport/platform setup and the final hit still run normally.
                PlayerData.instance.SetBool("isInvincible",true);
                control.SetState("Ascend Tele");
                return;
            }
            if(Current.SealFinish)
            {
                var boss=GameObject.Find("Boss Control/Hollow Knight Boss");
                var phase=boss?.GetComponents<PlayMakerFSM>().SingleOrDefault(f=>f.FsmName=="Phase Control");
                if(phase?.ActiveStateName!="Idle 1" || boss.GetComponent<HealthManager>()==null)
                    throw new InvalidOperationException("Seal ending fixture requires the active first phase");
                PlayerData.instance.SetBool("isInvincible",true);
                phase.SetState("Set Phase 4");
                return;
            }
            if (Current.PlaceX.HasValue)
            {
                transitionUntil = Time.realtimeSinceStartup + 30;
                placePlayer(new Vector2(Current.PlaceX.Value, Current.PlaceY.Value));
                return;
            }
            if (Current.Arena != null)
            {
                if(Current.SealEnding!=0)
                {
                    PlayerData.instance.gotShadeCharm=Current.SealEnding==2;
                    PlayerData.instance.royalCharmState=Current.SealEnding==2 ? 4 : 0;
                    PlayerData.instance.openedBlackEggDoor=true;
                }
                if(Current.StagStations)
                {
                    var data=PlayerData.instance;data.openedTown=data.openedCrossroads=data.metStag=true;
                    data.stationsOpened=2;data.stagPosition=0;data.travelling=false;
                }
                if(Current.Arena=="Room_nailmaster_03")
                    PlayerData.instance.geo=Math.Max(PlayerData.instance.geo,800);
                if(Current.Arena=="Crossroads_50")
                {
                    PlayerData.instance.SetBool("monomonDefeated",true);
                    PlayerData.instance.SetBool("quirrelEpilogueCompleted",false);
                }
                if(Current.Arena=="Ruins_Bathhouse") PlayerData.instance.SetBool("hasDreamNail",true);
                if(Current.DreamGateReward)
                {
                    var data=PlayerData.instance;data.SetBool("hasDreamNail",true);data.SetBool("hasDreamGate",false);
                    data.SetBool("metMoth",true);data.SetBool("dreamMothConvo1",true);data.SetBool("mothDeparted",false);data.SetInt("dreamOrbs",900);
                    for(int reward=1;reward<=9;reward++) data.SetBool("dreamReward"+reward,reward<=5);
                    data.SetBool("dreamReward5b",false);data.SetBool("dreamNailUpgraded",false);
                }
                if(Current.AbyssDream)
                {
                    var data=PlayerData.instance;data.SetBool("hasDreamNail",true);data.SetInt("royalCharmState",3);
                    data.SetBool("gotCharm_36",true);data.SetInt("charmCost_36",5);data.SetInt("charmSlots",Math.Max(5,data.GetInt("charmSlots")));
                    if(!data.equippedCharms.Contains(36)) data.EquipCharm(36);
                    data.SetBool("equippedCharm_36",true);data.CalculateNotchesUsed();HeroController.instance.CharmUpdate();
                }
                if(Current.DreamUpgrade)
                {
                    var data=PlayerData.instance;
                    data.SetBool("hasDreamNail",true);data.SetBool("hasDreamGate",true);data.SetBool("metMoth",true);
                    data.SetBool("dreamMothConvo1",true);data.SetBool("mothDeparted",false);data.SetInt("dreamOrbs",1800);
                    for(int reward=1;reward<=7;reward++) data.SetBool("dreamReward"+reward,true);
                    data.SetBool("dreamReward5b",true);data.SetBool("dreamReward8",false);data.SetBool("dreamNailUpgraded",false);
                }
                if (Current.Godseeker)
                {
                    var data = PlayerData.instance;
                    var respawn = (data.respawnScene, data.respawnMarkerName, data.respawnType, data.respawnFacingRight);
                    data.AddGGPlayerDataOverrides();
                    (data.respawnScene, data.respawnMarkerName, data.respawnType, data.respawnFacingRight) = respawn;
                    foreach (int charm in data.equippedCharms.ToArray())
                        if (charm != 36) { data.UnequipCharm(charm); data.SetBool("equippedCharm_" + charm, false); }
                    foreach (int charm in Current.Charms ?? Array.Empty<int>())
                    { data.EquipCharm(charm); data.SetBool("equippedCharm_" + charm, true); }
                    data.CalculateNotchesUsed();
                    HeroController.instance.CharmUpdate();
                }
                bool boss = Current.Arena.StartsWith("GG_", StringComparison.Ordinal);
                BossSceneController.SetupEvent = null;
                if(Current.GGEnding!=0)
                {
                    var sequence=Resources.Load<BossSequence>("GG/Boss Sequence Tier 5");
                    if(sequence==null || sequence.Count!=53 || sequence.GetSceneAt(52)!="GG_Radiance")
                        throw new InvalidOperationException("Native Tier5 sequence does not match this fixture");
                    PlayerData.instance.bossRushMode=false;
                    PlayerData.instance.givenGodseekerFlower=Current.GGEnding==2;
                    PlayerData.instance.openedBlackEggDoor=true;
                    BossSequenceController.SetupNewSequence(sequence,BossSequenceController.ChallengeBindings.None,nameof(PlayerData.bossDoorStateTier5),52);
                    BossSequenceController.KnightDamaged=true;
                }
                else if (boss)
                {
                    string statue = Current.Arena == "GG_False_Knight" ? "GG_Statue_FalseKnight"
                        : Current.Arena == "GG_Hornet_1" ? "GG_Statue_Hornet" : "GG_Statue_MantisLords";
                    PlayerData.instance.dreamReturnScene = "GG_Workshop";
                    PlayerData.instance.bossReturnEntryGate = "door_dreamReturnGG_" + statue;
                    BossSceneController.SetupEvent = controller => {
                        controller.BossLevel = 0;
                        controller.DreamReturnEvent = "DREAM RETURN";
                        controller.OnBossSceneComplete += () => { transitionUntil = Time.realtimeSinceStartup + 30; controller.DoDreamReturn(); };
                    };
                }
                // Permit only the requested native transition to progress after scene-scoped inputs are cancelled.
                transitionUntil = Time.realtimeSinceStartup + 30;
                GameManager.instance.BeginSceneTransition(new GameManager.SceneLoadInfo {
                    SceneName = Current.Arena, EntryGateName = boss ? "door_dreamEnter" : Current.Arena == "Ruins2_01" ? "bot1"
                        : Current.Arena == "RestingGrounds_07" || Current.Arena == "RestingGrounds_04" || Current.Arena=="Crossroads_50" || Current.Arena=="Ruins_Bathhouse" ? "right1" : Current.Arena == "Abyss_15" ? "top1"
                        : Current.Arena == "Dream_Final_Boss" ? "door1" : Current.Arena.StartsWith("Room_nailmaster",StringComparison.Ordinal) || Current.Arena=="Room_Town_Stag_Station" || Current.Arena=="Room_Final_Boss_Core" ? "left1" : "right2",
                    Visualization = boss ? GameManager.SceneLoadVisualizations.GodsAndGlory : Current.Arena == "Dream_Final_Boss"
                        ? GameManager.SceneLoadVisualizations.Dream : GameManager.SceneLoadVisualizations.Default,
                    PreventCameraFadeOut = Current.Arena == "Dream_Final_Boss" || Current.GGEnding!=0 });
                return;
            }
            pendingDamage = Current.Damage;
            if (Current.Refill) SharedLink.Instance.PushInput(Proto.InRefill, 0, 0);
            if (Current.Inventory) {
                SharedLink.Instance.PushInput(Proto.InKey, 8, 1);
                SharedLink.Instance.PushInput(Proto.InKey, 8, 0);
            }
            if(Current.ReturnSafe) recovery.ReturnSafe();
            if(Current.RestoreRoom) recovery.RestoreRoom();
            if(Current.CloseRecovery) recovery.Close();
            if (Current.DumpVisuals) DumpVisuals();
            if (Current.InspectTerrain) TerrainProbe.Write(Directory, AimOverride);
            if (Current.SaveCheckpoint)
                GameManager.instance.SaveGame(saved=>Log.Info(saved ? "Terrain probe checkpoint saved" : "Terrain probe checkpoint save failed"));
            if (Render.Overlay.Instance != null) Render.Overlay.Instance.DebugHidden = Current.HideOverlay;
            if (Current.Slot == 0) return;
            slotDown = Current.Slot;
            requests.Add(new { t = Time.realtimeSinceStartup - started, step = index, slot = slotDown });
            SharedLink.Instance.PushInput(Proto.InKey, (ushort)(29 + slotDown), 1);
        }

        private void UpdateCombatInput(HeroController hero, McState mc)
        {
            autoMove = autoLook = 0; autoAttack = autoJump = autoDash = autoFocus = autoBlock = false; AimOverride = null;
            if ((!hero.acceptingInput && !hero.cState.focusing) || hero.cState.dead) return;
            HealthManager target = null; Bounds bounds = default; float nearest = 60, bestScore = 120;
            foreach (HealthManager enemy in observedEnemies)
            {
                if (enemy == null || enemy.hp <= 0 || enemy.GetComponent<IHitResponder>() as HealthManager != enemy
                    || !Current.Targets.Any(n => enemy.name == n || enemy.name.StartsWith(n + " (", StringComparison.Ordinal))) continue;
                Collider2D collider = enemy.GetComponent<Collider2D>();
                if (collider == null || !collider.isActiveAndEnabled) continue;
                float distance = Vector2.Distance(hero.transform.position, collider.bounds.center);
                float score = distance + (enemy.IsInvincible ? 60 : 0);
                if (distance < 60 && score < bestScore) { target = enemy; bounds = collider.bounds; nearest = distance; bestScore = score; }
            }
            if (UnityEngine.SceneManagement.SceneManager.GetActiveScene().name.StartsWith("GG_Mantis_Lords",StringComparison.Ordinal))
            {
                UpdateMantisInput(hero, target, bounds);
                UpdateMantisShield(hero, mc);
                UpdateMantisLoadout(hero, target, bounds, mc);
                return;
            }
            if(UnityEngine.SceneManagement.SceneManager.GetActiveScene().name=="GG_Hornet_1")
            {UpdateHornetInput(hero,target,bounds,mc);return;}
            autoFocus = PlayerData.instance.health < PlayerData.instance.maxHealth && (PlayerData.instance.MPCharge >= 33 || hero.cState.focusing)
                && hero.cState.onGround && (target == null || Mathf.Abs(bounds.center.x - hero.transform.position.x) > 9)
                && Physics2D.OverlapCircle(hero.transform.position, 4, 1 << 22) == null;
            if (target == null || autoFocus) return;
            float dx = bounds.center.x - hero.transform.position.x, dy = bounds.center.y - hero.transform.position.y;
            float now = Time.time;
            int side = dx >= 0 ? 1 : -1;
            if ((mc.HeldFlags & Proto.HeldBow) != 0)
            {
                autoMove = Mathf.Abs(dx) < 5 ? -side : Mathf.Abs(dx) > 10 ? side : 0;
                float ticks = nearest * Coords.K / 3;
                Vector3 lead = target.GetComponent<Rigidbody2D>() is Rigidbody2D body ? (Vector3)body.linearVelocity * (ticks / 20) : Vector3.zero;
                AimOverride = (Vector2)(bounds.center + lead + Vector3.up * (.025f * ticks * ticks / Coords.K));
                autoAttack = now % 1.4f < 1.1f;
                return;
            }
            if ((mc.HeldFlags & Proto.HeldSword) == 0) return;
            if (dy > 3 && Mathf.Abs(dx) < 2.5f)
            {
                autoMove = hero.cState.facingRight ? 1 : -1;
                if (Physics2D.Raycast(hero.transform.position, Vector2.right * autoMove, 3, LayerMask.GetMask("Terrain"))) autoMove = -autoMove;
                if (now >= nextAutoDash) { dashUntil = now + .06f; nextAutoDash = now + 1.8f; }
                autoDash = now < dashUntil;
                return;
            }
            autoMove = Mathf.Abs(dx) > bounds.extents.x + 1.1f || hero.cState.facingRight != (side > 0) ? side : 0;
            autoLook = !hero.cState.onGround && dy < -.6f ? -1 : dy > 1.2f ? 1 : 0;
            if (!hero.cState.dashing && Mathf.Abs(dx) < bounds.extents.x + 2.5f && Mathf.Abs(dy) < bounds.extents.y + 2.5f && now >= nextAutoAttack)
            { attackUntil = now + .14f; nextAutoAttack = now + .43f; }
            autoAttack = now < attackUntil;
            if (hero.cState.onGround && Mathf.Abs(dx) < bounds.extents.x + 3 && now >= nextAutoJump)
            { jumpUntil = now + .16f; nextAutoJump = now + 1.4f; }
            if (Mathf.Abs(dx) > 12 && now >= nextAutoDash)
            { dashUntil = now + .06f; nextAutoDash = now + 1.8f; }
            autoJump = now < jumpUntil; autoDash = now < dashUntil;
        }

        private void UpdateHornetInput(HeroController hero,HealthManager target,Bounds bounds,McState mc)
        {
            if(Current.HandPlacedTnt && handBuildIndex<3){HandBuild(hero,mc);return;}
            if(target==null) return;
            float now=Time.time,x=hero.transform.position.x,y=hero.transform.position.y;
            float dx=bounds.center.x-x,dy=bounds.center.y-y;
            int side=dx>=0 ? 1 : -1;
            string state=target.GetComponents<PlayMakerFSM>().FirstOrDefault(f=>f.FsmName=="Control")?.ActiveStateName ?? "";
            bool recover=state=="Idle" || state=="Stop" || state=="Dmg Idle" || state=="Land" || state=="Hard Land"
                || state.Contains("Recover") || state.StartsWith("Stun",StringComparison.Ordinal);
            bool sphere=state.Contains("Sphere");
            float spacing=sphere ? 6 : recover ? bounds.extents.x+2.1f : 5;
            autoMove=Mathf.Abs(dx)>spacing+1 ? side : Mathf.Abs(dx)<spacing-.4f ? -side : 0;
            if(x<14.5f && autoMove<0 || x>41 && autoMove>0) autoMove=0;
            Vector2 aim=target.transform.position;
            float nearest=Mathf.Abs(dx);
            bool projectile=false;
            foreach(var hazard in Physics2D.OverlapCircleAll(hero.transform.position,14,(1<<17)|(1<<22)))
            {
                if(!hazard.name.Contains("Needle") && !hazard.name.Contains("Sphere Ball")) continue;
                projectile=true;float distance=Mathf.Abs(hazard.bounds.center.x-x);
                if(distance<nearest){nearest=distance;aim=hazard.bounds.center;}
            }
            autoBlock=!recover || projectile || Mathf.Abs(dx)<bounds.extents.x+1.3f;
            AimOverride=aim;
            if((state=="ADash Antic" || state=="A Dash") && Mathf.Abs(dx)<4)
            {
                autoMove=x<27 ? 1 : -1;
                if(now>=nextAutoDash){dashUntil=now+.07f;nextAutoDash=now+1.65f;}
            }
            autoDash=now<dashUntil;
            if(Current.HandPlacedTnt && (target.hp<=60 || handIgnitionStarted>0))
            {
                autoAttack=false;autoBlock=true;bowUntil=0;
                if(handIgnitionStarted==0)
                {
                    HandSlot(1);autoMove=Mathf.Abs(x-22.5f)>.3f ? (x<22.5f ? 1 : -1) : 0;
                    if(Mathf.Abs(x-22.5f)<.8f && dx < -7 && !projectile && !hero.cState.attacking)
                    {handIgnitionStarted=now;requests.Add(new{t=Time.realtimeSinceStartup-started,handLever=true});}
                }
                if(handIgnitionStarted>0)
                {
                    float age=now-handIgnitionStarted;
                    if(age<.55f)
                    {
                        HandSlot(2);autoMove=0;autoDash=false;autoBlock=age>=.22f && age<.27f;
                        AimOverride=new Vector2((float)((handTntX-.5-Coords.OffsetX)/Coords.K),(handBaseY+1.3f)/Coords.K);
                    }
                    else
                    {
                        HandSlot(1);autoMove=x<31.5f ? 1 : 0;
                        if(age>=3.3f) AimOverride=new Vector2(x-10,y);
                        if(age<1.5f && hero.cState.onGround) jumpUntil=now+.22f;
                        if(x<29 && now>=nextAutoDash){dashUntil=now+.07f;nextAutoDash=now+1.65f;}
                        autoDash=now<dashUntil;
                    }
                }
                HandHop(hero);autoJump=now<jumpUntil;
                return;
            }
            bool facing=hero.cState.facingRight==(side>0);
            if(recover && !projectile && !autoDash && (mc.HeldFlags&Proto.HeldSword)!=0)
            {
                autoBlock=false;
                if(!facing && !hero.cState.attacking) autoMove=side;
                autoLook=dy>1.2f ? 1 : !hero.cState.onGround && dy<-.6f ? -1 : 0;
                if(facing && Mathf.Abs(dx)<bounds.extents.x+3 && Mathf.Abs(dy)<bounds.extents.y+2 && now>=nextAutoAttack)
                {attackUntil=now+.12f;nextAutoAttack=now+.27f;}
                autoAttack=now<attackUntil;
            }
            if(!Current.HandPlacedTnt || target.hp>100) UpdateMantisLoadout(hero,target,bounds,mc);
            else HandSlot(1);
            if(Current.HandPlacedTnt){HandHop(hero);autoJump=now<jumpUntil;}
        }

        private void HandSlot(int slot)
        {
            if(handCurrentSlot==slot && Time.time<handNextSlot)return;
            SharedLink.Instance.PushInput(Proto.InKey,(ushort)(29+slot),1);
            SharedLink.Instance.PushInput(Proto.InKey,(ushort)(29+slot),0);
            handCurrentSlot=slot;handNextSlot=Time.time+.2f;
            requests.Add(new{t=Time.realtimeSinceStartup-started,slot,handPlacementInput=true});
        }
        private void HandBuild(HeroController hero,McState mc)
        {
            HandSlot(handBuildIndex<2 ? 4 : 6);
            if((mc.HeldFlags&(Proto.HeldSword|Proto.HeldBow))!=0)return;
            if(handBuildStarted==0)
            {
                handBuildStarted=Time.time;
                handTntX=(int)Math.Floor(Coords.OffsetX+25*Coords.K);
                handBaseY=Mathf.CeilToInt(hero.GetComponent<Collider2D>().bounds.min.y*Coords.K);
                requests.Add(new{t=Time.realtimeSinceStartup-started,handPlacement=handBuildIndex});
            }
            float age=Time.time-handBuildStarted;
            float aimX=(float)((handTntX-(handBuildIndex==0 ? 0 : 1)+.5-Coords.OffsetX)/Coords.K);
            float aimY=handBuildIndex<2 ? hero.GetComponent<Collider2D>().bounds.min.y-.05f : (handBaseY+1)/Coords.K+.02f;
            AimOverride=new Vector2(aimX,aimY);
            autoMove=0;autoBlock=age>=.22f && age<.37f;
            if(age>=.55f){handBuildIndex++;handBuildStarted=0;if(handBuildIndex==3)HandSlot(1);}
        }
        private void HandHop(HeroController hero)
        {
            if(autoMove==0 || !hero.cState.onGround || Time.time<nextAutoJump)return;
            Vector2 feet=hero.GetComponent<Collider2D>().bounds.center;
            var obstacle=Physics2D.Raycast(feet,Vector2.right*autoMove,1.1f,LayerMask.GetMask("Terrain"));
            if(obstacle.collider!=null && obstacle.collider.name.StartsWith("HollowCraft blocks ",StringComparison.Ordinal))
            {jumpUntil=Time.time+.18f;nextAutoJump=Time.time+1;}
        }

        private static bool CanNavigate(HeroController hero) => hero != null && PlayerData.instance.health > 0
            && hero.acceptingInput && !hero.controlReqlinquished && !hero.cState.dead && !hero.cState.transitioning
            && GameManager.instance.gameState == GlobalEnums.GameState.PLAYING;

        private void UpdateMantisInput(HeroController hero, HealthManager target, Bounds bounds)
        {
            // Test input only: react to native tells without changing the boss or the player's damage rules.
            float now = Time.time, x = hero.transform.position.x, y = hero.transform.position.y;
            var body=hero.GetComponent<Rigidbody2D>();
            Bounds player=hero.GetComponent<Collider2D>().bounds;
            bool dash = false, falling = false, urgent=false,dropSequence=false;
            int incomingDashDirection=0, fallingId=0;
            float fallingX = x, nearestDrop=100;
            foreach (var enemy in observedEnemies)
            {
                if (enemy == null || enemy.hp <= 0 || !enemy.name.StartsWith("Mantis Lord", StringComparison.Ordinal)
                    || !ReferenceEquals(enemy.GetComponent<IHitResponder>(), enemy)) continue;
                string state = enemy.GetComponent<PlayMakerFSM>()?.ActiveStateName;
                dropSequence|=state!=null && state.StartsWith("Dstab",StringComparison.Ordinal);
                dash |= state == "Dash Antic" || state == "Dash Attack";
                float enemyDx=enemy.transform.position.x-x,enemyDy=enemy.transform.position.y-y;
                if ((state == "Dstab Arrive" || state == "Dstab Attack") && Mathf.Abs(enemyDx)<nearestDrop)
                { falling=true;fallingX=enemy.transform.position.x;nearestDrop=Mathf.Abs(enemyDx);fallingId=enemy.GetInstanceID(); }
                urgent |= state=="Dstab Attack" && Mathf.Abs(enemyDx)<1.8f && enemyDy<6 && enemyDy>-2;
                if(state=="Dash Attack" && Mathf.Abs(enemyDx)<8f && player.min.y<8.6f)
                {urgent=true;incomingDashDirection=enemyDx>0 ? 1 : -1;}
            }
            var hazards = Physics2D.OverlapCircleAll(hero.transform.position, 11, (1 << 17) | (1 << 22));
            bool shotThreat=false,hasShot=false;
            foreach(var shot in hazards)
            {
                if(!shot.name.StartsWith("Shot Mantis Lord",StringComparison.Ordinal)) continue;
                hasShot=true;
                var shotBody=shot.attachedRigidbody;
                Vector2 velocity=shotBody!=null ? shotBody.linearVelocity : Vector2.zero;
                Vector2 shotPosition=shot.bounds.center;int shotId=shot.GetInstanceID();
                if(mantisShots.TryGetValue(shotId,out var previous) && now-previous.time<.25f)
                {
                    if(now-previous.time>=.04f)
                    {
                        velocity=(shotPosition-previous.position)/(now-previous.time);
                        mantisShots[shotId]=(shotPosition,velocity,now);
                    }
                    else velocity=previous.velocity;
                }
                else mantisShots[shotId]=(shotPosition,velocity,now);
                if(mantisShots.Count>64) mantisShots.Clear();
                shotThreat|=Mathf.Abs(shotPosition.x-player.center.x)<5 && Mathf.Abs(shotPosition.y-player.center.y)<3.8f;
                for(float t=0;t<=.5f;t+=.1f)
                {
                    Vector2 predicted=(Vector2)shot.bounds.center+velocity*t;
                    float py=hero.cState.onGround ? player.center.y : Mathf.Max(6.65f,player.center.y+body.linearVelocity.y*t-23.7f*t*t);
                    float px=player.center.x+(dropSequence ? body.linearVelocity.x*t : 0);
                    bool intersects=Mathf.Abs(predicted.x-px)<shot.bounds.extents.x+player.extents.x+.45f
                        && Mathf.Abs(predicted.y-py)<shot.bounds.extents.y+player.extents.y+.35f;
                    shotThreat|=intersects;
                    urgent|=intersects && t<=.1f;
                }
            }
            bool airJumpUsed=(bool)(MantisAirJumpUsed?.GetValue(hero)??true);
            if(dropSequence)
            {
                if(now>=mantisDropUntil) mantisDropDirection=x<30 ? 1 : -1;
                mantisDropUntil=now+.2f;
            }
            dropSequence|=now<mantisDropUntil;
            if(!falling) mantisFallingId=0;
            if(falling && fallingId!=mantisFallingId)
            {
                float left=x-22.7f,right=37.3f-x;
                foreach(var enemy in observedEnemies)
                {
                    if(enemy==null || enemy.hp<=0 || !ReferenceEquals(enemy.GetComponent<IHitResponder>(),enemy)) continue;
                    string state=enemy.GetComponent<PlayMakerFSM>()?.ActiveStateName;
                    if(state!="Dstab Land" || !(enemy.GetComponent<Collider2D>() is Collider2D groundEnemy)) continue;
                    Bounds obstacle=groundEnemy.bounds;
                    if(obstacle.center.x<x) left=Mathf.Min(left,x-obstacle.max.x-player.extents.x);
                    else right=Mathf.Min(right,obstacle.min.x-x-player.extents.x);
                }
                mantisDropDirection=right>left ? 1 : -1;mantisFallingId=fallingId;
            }
            bool dropOverhead=falling && nearestDrop<2.5f;
            if (!dropOverhead && (dash || shotThreat) && (hero.cState.onGround || !airJumpUsed && body.linearVelocity.y<1) && now >= nextAutoJump)
            { jumpUntil = now + (hero.cState.onGround ? shotThreat ? .55f : .35f : .22f); nextAutoJump = now + (hero.cState.onGround ? .7f : .5f); }
            autoJump = now < jumpUntil;
            autoFocus=false;
            if(now<mantisEscapeUntil) autoMove=mantisEscapeDirection;
            if (falling)
            {
                autoMove = Mathf.Abs(fallingX-x)<3.4f ? mantisDropDirection : 0;
                if(x<22.8f && autoMove<0 || x>37.2f && autoMove>0) autoMove=0;
            }
            if(urgent && now>=nextAutoDash)
            {
                int direction=incomingDashDirection!=0 ? incomingDashDirection : autoMove!=0 ? autoMove : x<30 ? 1 : -1;
                float end=x+direction*4.8f;
                bool occupied=observedEnemies.Any(e=>e!=null && e.hp>0 && ReferenceEquals(e.GetComponent<IHitResponder>(),e)
                    && e.GetComponent<PlayMakerFSM>()?.ActiveStateName is string state && state.StartsWith("Dstab",StringComparison.Ordinal)
                    && Mathf.Abs(e.transform.position.x-end)<2.3f);
                if(end>=22.7f && end<=37.3f && !occupied)
                {
                    autoMove=direction;mantisEscapeDirection=direction;mantisEscapeUntil=now+.23f;
                    dashUntil=now+.07f;nextAutoDash=now+1.65f;
                }
            }
            autoDash=now<dashUntil;
            bool reachable = target != null && bounds.center.x >= 22 && bounds.center.x <= 38 && bounds.center.y < 15;
            if (!reachable)
            {
                if(!dropSequence && now>=mantisEscapeUntil) autoMove=hasShot ? 0 : Mathf.Abs(x-30)>.6f ? (x<30 ? 1 : -1) : 0;
                return;
            }
            float dx = bounds.center.x - x, dy = bounds.center.y - y;
            int side = dx >= 0 ? 1 : -1;
            bool facing=hero.cState.facingRight==(side>0);
            if(!dropSequence && now>=mantisEscapeUntil)
                autoMove=dash ? 0 : Mathf.Abs(dx)>bounds.extents.x+2.2f || !facing && !hero.cState.attacking ? side : 0;
            else if(!falling && now>=mantisEscapeUntil)
                autoMove=Mathf.Abs(dx)>bounds.extents.x+1.5f || !facing && !hero.cState.attacking ? side : 0;
            if (!dropSequence && now>=mantisEscapeUntil && (x < 23 && autoMove < 0 || x > 37 && autoMove > 0)) autoMove = -autoMove;
            autoLook = !hero.cState.onGround && dy < -.6f ? -1 : dy > 1.2f ? 1 : 0;
            if (facing && !urgent && !(falling && nearestDrop<3.4f) && !hero.cState.dashing && Mathf.Abs(dx) < bounds.extents.x + 2.5f && Mathf.Abs(dy) < bounds.extents.y + (hero.cState.onGround ? 2.5f : 4f) && now >= nextAutoAttack)
            { attackUntil = now + .14f; nextAutoAttack = now + .27f; }
            autoAttack = facing && !urgent && now < attackUntil;
        }

        private void UpdateMantisLoadout(HeroController hero, HealthManager target, Bounds bounds, McState mc)
        {
            float now = Time.time;
            bool bow = (mc.HeldFlags & Proto.HeldBow) != 0;
            bool crossbow = (mc.HeldFlags & Proto.HeldCrossbow) != 0;
            if(crossbow) crossbowLoaded=mc.Has(Proto.McCrossbowLoaded);
            if(crossbowReloading && now>=bowUntil && !bow) crossbowReloading=false;
            bool safeReload = !autoBlock && !hero.cState.attacking && !hero.cState.dashing && hero.cState.onGround
                && (target==null || Mathf.Abs(bounds.center.x-hero.transform.position.x)>4)
                && !observedEnemies.Any(e=>e!=null && e.hp>0 && e.GetComponents<PlayMakerFSM>().Any(f=>f.FsmName=="Mantis Lord"
                    && (f.ActiveStateName=="Dash Antic" || f.ActiveStateName=="Dash Attack" || f.ActiveStateName=="Dstab Arrive" || f.ActiveStateName=="Dstab Attack" || f.ActiveStateName=="Throw Antic")));
            if(!crossbowLoaded && safeReload && !crossbowReloading && now>=nextBowAt)
            {crossbowReloading=true;bowStarted=now;bowUntil=now+.85f;nextBowAt=bowUntil+.5f;}
            if(crossbowReloading && crossbow && crossbowLoaded) {crossbowReloading=false;bowUntil=0;}
            if (crossbowLoaded && target != null && now >= nextBowAt && !hero.cState.attacking && !autoBlock && hero.cState.onGround)
            {
                string state = target.GetComponents<PlayMakerFSM>().FirstOrDefault(f => f.FsmName == "Mantis Lord" || f.FsmName=="Control")?.ActiveStateName;
                if (state == "Arrive" || target.name.StartsWith("Hornet",StringComparison.Ordinal) && (state=="Idle" || state=="Throw Recover" || state=="Stun Land"))
                { bowStarted=now;bowUntil = now + .45f; nextBowAt = now + 2; }
            }
            if (autoBlock && bow) {bowUntil=0;crossbowReloading=false;}
            int desired = now < bowUntil ? 9 : 1;
            if ((desired == 9) != bow && now >= nextAutoSlot)
            {
                SharedLink.Instance.PushInput(Proto.InKey, (ushort)(29 + desired), 1);
                SharedLink.Instance.PushInput(Proto.InKey, (ushort)(29 + desired), 0);
                requests.Add(new { t = Time.realtimeSinceStartup - started, step = index, slot = desired, automatic = true });
                nextAutoSlot = now + .15f;
            }
            if (desired == 9 || bow)
            {
                autoFocus = false;
                autoAttack = bow && !autoBlock && now < bowUntil - .05f && (crossbowReloading || crossbowLoaded && now>=bowStarted+.18f);
                if(crossbowReloading && safeReload) autoMove=0;
                if (target != null && !autoBlock)
                {
                    float ticks = Vector2.Distance(hero.transform.position,bounds.center) * Coords.K / 3.15f;
                    Vector3 lead = target.GetComponent<Rigidbody2D>() is Rigidbody2D rb ? (Vector3)rb.linearVelocity * (ticks / 20) : Vector3.zero;
                    AimOverride = (Vector2)(bounds.center + lead + Vector3.up * (.025f*ticks*ticks/Coords.K));
                }
            }
        }
        private void UpdateMantisShield(HeroController hero, McState mc)
        {
            if (!mc.Has(Proto.McOffhandShield) || hero.cState.attacking) return;
            Vector2 position = hero.GetComponent<Collider2D>().bounds.center;
            int dangerSides = 0, direction = 0;
            float closest=float.PositiveInfinity;
            foreach (HealthManager enemy in observedEnemies)
            {
                if (enemy == null || enemy.hp <= 0 || enemy.GetComponent<IHitResponder>() as HealthManager != enemy) continue;
                string state = enemy.GetComponents<PlayMakerFSM>().FirstOrDefault(f => f.FsmName == "Mantis Lord")?.ActiveStateName ?? "";
                if (state != "Dash Arrive" && state != "Dash Antic" && state != "Dash Attack" && state != "Throw Antic" && state != "Throw") continue;
                float dx = enemy.transform.position.x - position.x;
                if (Mathf.Abs(dx) > 12) continue;
                int side=dx>=0 ? 1 : -1;dangerSides|=side>0 ? 1 : 2;
                if(Mathf.Abs(dx)<closest){closest=Mathf.Abs(dx);direction=side;}
            }
            foreach (Collider2D shot in Physics2D.OverlapCircleAll(position, 20, (1 << 17) | (1 << 22)))
            {
                if (!shot.name.StartsWith("Shot Mantis Lord", StringComparison.Ordinal)) continue;
                Vector2 delta = (Vector2)shot.bounds.center - position;
                int side=delta.x>=0 ? 1 : -1;dangerSides|=side>0 ? 1 : 2;
                float score=Mathf.Abs(delta.x);
                if(score>2.5f && mantisShots.TryGetValue(shot.GetInstanceID(),out var tracked) && delta.x*tracked.velocity.x>0) score+=20;
                if(score<closest){closest=score;direction=side;}
            }
            if (dangerSides == 0)
            {
                if(Time.time<guardUntil) {autoBlock=true;autoAttack=false;AimOverride=position+Vector2.right*guardDirection*10;}
                return;
            }
            guardUntil=Time.time+.25f;guardDirection=direction;
            autoBlock = true; autoAttack = false;
            AimOverride = position + Vector2.right * direction * 10;
            bool fallingClose=observedEnemies.Any(e=>e!=null && e.hp>0 && Mathf.Abs(e.transform.position.x-position.x)<2.5f
                && e.GetComponent<PlayMakerFSM>()?.ActiveStateName is string state && (state=="Dstab Arrive" || state=="Dstab Attack"));
            if(dangerSides!=3 && mc.Has(Proto.McShieldReady) && hero.cState.onGround && !hero.cState.jumping && !fallingClose)
            {autoJump=false;jumpUntil=0;nextAutoJump=Time.time;}
        }
        public void AfterFrame(HeroController hero)
        {
            if (steps == null || pendingDamage == 0 || hero == null) return;
            int amount = pendingDamage; pendingDamage = 0;
            int before = PlayerData.instance.health;
            GameObject source = null;
            if (Current.DamageSide != 0) {
                source = new GameObject("Shield validation impact");
                source.transform.position = hero.GetComponent<Collider2D>().bounds.center + Vector3.right * Current.DamageSide * 2;
            }
            hero.TakeDamage(source, Current.DamageSide>0 ? GlobalEnums.CollisionSide.right : GlobalEnums.CollisionSide.left, amount, 1);
            if (source != null) UnityEngine.Object.Destroy(source, 1);
            damage.Add(new { t = Time.realtimeSinceStartup - started, step = index, before, after = PlayerData.instance.health,
                hero.cState.invulnerable, hero.cState.recoilFrozen, hero.cState.recoiling });
        }
        public void RecordRenderPose(HeroController hero,Vector3 feet,bool native)
        {
            if(Current?.TrackRenderPose!=true || !(Render.BlockRenderer.Instance.AvatarPosition is Vector3 avatar)) return;
            var body=hero.GetComponent<Rigidbody2D>();var position=hero.transform.position;
            visualFrames.Add(new VisualFrame {t=Time.realtimeSinceStartup-started,step=index,native=native,
                spriteX=position.x,spriteY=position.y,bodyX=body.position.x,bodyY=body.position.y,
                feetOffset=body.position.y-feet.y,avatarX=avatar.x,avatarY=avatar.y,interpolation=(int)body.interpolation});
        }

        public void CaptureAfterRender()
        {
            if(presentationMode && Current!=null && !Current.Capture)
            {
                if(renderContext==null)
                {
                    var main=GameCameras.instance.mainCamera;
                    var low=main.ViewportToWorldPoint(new Vector3(0,0,Mathf.Abs(Coords.Depth-main.transform.position.z)));
                    var high=main.ViewportToWorldPoint(new Vector3(1,1,Mathf.Abs(Coords.Depth-main.transform.position.z)));
                    renderContext=new {width=Screen.width,height=Screen.height,completion="Native FrameTimingManager; automatic rendering; no ReadPixels or Camera.Render",
                        frameTimingEnabled=FrameTimingManager.IsFeatureEnabled(),cpuRecorderValid=cpuTimingRecorder.Valid,gpuRecorderValid=gpuTimingRecorder.Valid,
                        cpuTimerFrequency=FrameTimingManager.GetCpuTimerFrequency(),SystemInfo.graphicsDeviceName,SystemInfo.graphicsDeviceType,SystemInfo.processorType,SystemInfo.systemMemorySize,
                        Application.targetFrameRate,QualitySettings.vSyncCount,Coords.K,Coords.OffsetX,Coords.PlaneZ,Coords.Depth,
                        worldMin=new[]{low.x,low.y},worldMax=new[]{high.x,high.y},main.orthographicSize,main.aspect};
                }
                FrameTimingManager.CaptureFrameTimings();
                int count=(int)FrameTimingManager.GetLatestTimings((uint)frameTimings.Length,frameTimings);
                for(int i=count-1;i>=0;i--)
                    if(frameTimings[i].frameStartTimestamp>lastNativeFrame)
                    {
                        lastNativeFrame=frameTimings[i].frameStartTimestamp;
                        nativeFrames.Add(new NativeFrameSample {t=Time.realtimeSinceStartup-started,step=index,cameraFrames=nativeCameraFrames,timing=frameTimings[i]});
                    }
            }
            bool measure=Current?.RenderOnly==true && pendingCapture==null;
            if(pendingCapture==null && !measure) return;
            string path=pendingCapture;pendingCapture=null;
            long began=System.Diagnostics.Stopwatch.GetTimestamp();
            if(measure && renderTarget==null)
            {
                renderTarget=new RenderTexture(1920,1080,24,RenderTextureFormat.ARGB32);renderTarget.Create();
                renderPixel=new Texture2D(1,1,TextureFormat.RGB24,false);
                renderCameras=UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                    .Where(c=>c.gameObject.scene.IsValid()).OrderBy(c=>c.depth).ToArray();
                var main=GameCameras.instance.mainCamera;
                var low=main.ViewportToWorldPoint(new Vector3(0,0,Mathf.Abs(Coords.Depth-main.transform.position.z)));
                var high=main.ViewportToWorldPoint(new Vector3(1,1,Mathf.Abs(Coords.Depth-main.transform.position.z)));
                renderContext=new {width=1920,height=1080,completion="Synchronous1pixelReadPixels; no PNG encoding",avatarTextureDiagnostics=false,SystemInfo.graphicsDeviceName,SystemInfo.processorType,SystemInfo.systemMemorySize,
                    Application.targetFrameRate,QualitySettings.vSyncCount,Coords.K,Coords.OffsetX,Coords.PlaneZ,Coords.Depth,
                    cameraPosition=new[]{main.transform.position.x,main.transform.position.y,main.transform.position.z},worldMin=new[]{low.x,low.y},worldMax=new[]{high.x,high.y},main.orthographicSize,main.aspect,
                    cameraRotation=new[]{main.transform.eulerAngles.x,main.transform.eulerAngles.y,main.transform.eulerAngles.z},cameras=renderCameras.Select(c=>c.name).ToArray()};
            }
            var target=measure ? renderTarget : RenderTexture.GetTemporary(1920,1080,24,RenderTextureFormat.ARGB32);
            var previous=RenderTexture.active;Texture2D pixels=null;
            try
            {
                RenderTexture.active=target;GL.Clear(true,true,Color.black);
                var cameras=measure ? renderCameras : UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                    .Where(c=>c.gameObject.scene.IsValid()).OrderBy(c=>c.depth).ToArray();
                int hudLayers=cameras.FirstOrDefault(c=>c.name=="HudCamera")?.cullingMask ?? 0;
                if(!measure && captureIndex==1) File.WriteAllText(Path.Combine(captureDirectory,"cameras.json"),JsonConvert.SerializeObject(cameras.Select((c,i)=>new {
                    index=i,c.name,c.enabled,active=c.gameObject.activeInHierarchy,c.depth,c.cullingMask,c.targetDisplay,clear=c.clearFlags.ToString(),
                    target=c.targetTexture?.name,c.orthographic,c.orthographicSize,rect=new[]{c.rect.x,c.rect.y,c.rect.width,c.rect.height},
                    scripts=c.GetComponents<MonoBehaviour>().Select(s=>s.GetType().FullName)})));
                if(!measure && captureIndex==1 && Current?.DumpVisuals==true)
                    File.WriteAllText(Path.Combine(captureDirectory,"hud-renderers.json"),JsonConvert.SerializeObject(
                        UnityEngine.Object.FindObjectsByType<Renderer>(FindObjectsSortMode.None)
                        .Where(r=>r.enabled && r.gameObject.activeInHierarchy && (hudLayers & (1<<r.gameObject.layer))!=0)
                        .Select(r=>new {r.name,r.gameObject.layer,width=r.bounds.size.x,height=r.bounds.size.y,
                            shader=r.sharedMaterial?.shader?.name,sprite=r.GetComponent<tk2dBaseSprite>()?.GetCurrentSpriteDef()?.name,
                            tint=r.GetComponent<tk2dBaseSprite>()?.color.ToString(),materialColor=r.sharedMaterial!=null && r.sharedMaterial.HasProperty("_Color") ? r.sharedMaterial.color.ToString() : null})));
                pixels=measure ? renderPixel : new Texture2D(1920,1080,TextureFormat.RGB24,false);
                int rendered=0;
                foreach(var camera in cameras.Where(c=>c==GameCameras.instance.mainCamera || c.gameObject.activeInHierarchy && c.enabled))
                {
                    rendered++;
                    if(camera.targetTexture!=null) { camera.Render();continue; }
                    var old=camera.targetTexture;
                    try { camera.targetTexture=target;camera.Render(); }
                    finally { camera.targetTexture=old; }
                    if(!measure && captureIndex==1 && Current?.DumpVisuals==true)
                    {
                        string checks=Path.Combine(captureDirectory,"camera-checks");System.IO.Directory.CreateDirectory(checks);
                        RenderTexture.active=target;pixels.ReadPixels(new Rect(0,0,1920,1080),0,0);pixels.Apply();
                        File.WriteAllBytes(Path.Combine(checks,Array.IndexOf(cameras,camera)+".png"),pixels.EncodeToPNG());
                    }
                }
                Render.Overlay.Instance?.Capture(target);
                RenderTexture.active=target;
                if(measure)
                {
                    // Complete the GPU work without full-frame readback or image compression in the timed loop.
                    pixels.ReadPixels(new Rect(0,0,1,1),0,0,false);
                    long end=System.Diagnostics.Stopwatch.GetTimestamp();double ms=1000.0/System.Diagnostics.Stopwatch.Frequency;
                    renderedFrames.Add(new RenderSample {t=Time.realtimeSinceStartup-started,step=index,cameras=rendered,timeScale=Time.timeScale,
                        engineMs=Time.unscaledDeltaTime*1000.0,statusMs=HollowCraftRuntime.StatusMilliseconds,
                        physicsMs=PlayerBridge.FramePhysicsMilliseconds,
                        runtimeMs=HollowCraftRuntime.FrameMilliseconds,probeMs=HollowCraftRuntime.ProbeMilliseconds,
                        drainMs=HollowCraftRuntime.DrainMilliseconds,replicaMs=HollowCraftRuntime.ReplicaMilliseconds,
                        intervalMs=lastRenderTick==0 ? 0 : (end-lastRenderTick)*ms,renderMs=(end-began)*ms});
                    lastRenderTick=end;return;
                }
                pixels.ReadPixels(new Rect(0,0,1920,1080),0,0);pixels.Apply();
                File.WriteAllBytes(path,pixels.EncodeToPNG());
                if(Current?.TrackStory==true)
                    foreach(var mirror in UnityEngine.Object.FindObjectsByType<PlanarRealtimeReflection>(FindObjectsSortMode.None))
                        if(mirror.GetComponent<Renderer>()?.sharedMaterial?.GetTexture("_ReflectionTex") is RenderTexture reflection)
                        {
                            var reflected=new Texture2D(reflection.width,reflection.height,TextureFormat.RGBA32,false);
                            try {
                                RenderTexture.active=reflection;reflected.ReadPixels(new Rect(0,0,reflection.width,reflection.height),0,0);reflected.Apply();
                                File.WriteAllBytes(Path.ChangeExtension(path,"reflection-"+mirror.GetInstanceID()+".png"),reflected.EncodeToPNG());
                            }
                            finally { UnityEngine.Object.Destroy(reflected); }
                        }
            }
            catch(Exception error) { Cancel("Offscreen capture failed: "+error.Message); }
            finally { RenderTexture.active=previous;if(!measure) {if(pixels!=null) UnityEngine.Object.Destroy(pixels);RenderTexture.ReleaseTemporary(target);} }
        }

        private void DumpVisuals()
        {
            HeroController hero = HeroController.instance;
            var library = hero.GetComponent<tk2dSpriteAnimator>().Library;
            Func<Transform, string> path = null;
            path = t => t.parent == null ? t.name : path(t.parent) + "/" + t.name;
            object Describe(GameObject obj) => obj == null ? null : new {
                obj.name, path = path(obj.transform), active = obj.activeInHierarchy,
                renderers = obj.GetComponentsInChildren<Renderer>(true).Select(r => new {
                    path = path(r.transform), type = r.GetType().Name, r.enabled,
                    r.forceRenderingOff, r.gameObject.layer,
                    sprite = r.GetComponent<tk2dSprite>()?.CurrentSprite?.name,
                    collection = r.GetComponent<tk2dBaseSprite>()?.Collection?.name,
                    spriteId = r.GetComponent<tk2dBaseSprite>()?.spriteId,
                    vertices = r.GetComponent<tk2dBaseSprite>()?.GetCurrentSpriteDef()?.positions.Select(p=>new {p.x,p.y,p.z}) }),
                animators = obj.GetComponentsInChildren<tk2dSpriteAnimator>(true).Select(a => new {
                    path = path(a.transform), library = a.Library?.name, sameLibrary = a.Library == library,
                    clip = a.CurrentClip?.name, defaultClip = a.DefaultClip?.name, clips = a.Library?.clips.Select(c => c.name) }) };
            var prefabs = new Dictionary<string, object>();
            foreach (string fieldName in new[] { "heroDeathPrefab", "spikeDeathPrefab", "acidDeathPrefab", "corpsePrefab", "cutscenePrefab", "sharpShadowPrefab" })
            {
                var field = typeof(HeroController).GetField(fieldName, System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic);
                if (field != null && field.GetValue(hero) is GameObject obj) prefabs[fieldName] = Describe(obj);
            }
            var objects = UnityEngine.Object.FindObjectsByType<tk2dSpriteAnimator>(FindObjectsInactive.Include, FindObjectsSortMode.None)
                .Where(a => a.Library == library || System.Text.RegularExpressions.Regex.IsMatch(a.name, "Knight|Shade|Reflection|Ghost", System.Text.RegularExpressions.RegexOptions.IgnoreCase))
                .Select(a => Describe(a.gameObject));
            var fsms = hero.GetComponentsInChildren<PlayMakerFSM>(true).Select(f => new {
                path = path(f.transform), f.FsmName, f.ActiveStateName,
                integers = f.FsmVariables.IntVariables.Select(v => new { v.Name, v.Value }),
                transitions = f.Fsm.GlobalTransitions.Select(t => new { t.EventName, t.ToState }),
                states = f.FsmStates.Select(s => new { s.Name, actions = s.Actions.Select(a => a.GetType().FullName) }) });
            var staticSprite=hero.cutscenePrefab?.GetComponent<tk2dBaseSprite>();
            var staticFrames=library.clips.Where(c=>c.frames!=null).SelectMany(c=>c.frames.Select((f,i)=>new {clip=c.name,index=i,f}))
                .Where(p=>staticSprite!=null && p.f.spriteCollection==staticSprite.Collection && p.f.spriteId==staticSprite.spriteId)
                .Select(p=>new {p.clip,p.index});
            var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            var sceneFsms=UnityEngine.Object.FindObjectsByType<PlayMakerFSM>(FindObjectsInactive.Include,FindObjectsSortMode.None)
                .Where(f=>f.gameObject.scene==scene).Select(f=>new {path=path(f.transform),f.FsmName,f.ActiveStateName,
                    states=f.FsmStates.Select(s=>new {s.Name,transitions=s.Transitions.Select(t=>new {t.EventName,t.ToState}),
                        actions=s.Actions.Select(a=>new {type=a.GetType().FullName,fields=a.GetType().GetFields(System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.Public)
                            .ToDictionary(v=>v.Name,v=>v.GetValue(a)?.ToString())})})});
            File.WriteAllText(Path.Combine(Directory, "hollowcraft-visual-inventory.json"), JsonConvert.SerializeObject(new {
                prefabs, objects, fsms, staticFrames, sceneFsms, rawNailDamage = PlayerData.instance.nailDamage, nailDamage = PlayerData.instance.GetInt("nailDamage") }));
        }
        private void ReleaseSlot()
        {
            if (slotDown == 0) return;
            SharedLink.Instance.PushInput(Proto.InKey, (ushort)(29 + slotDown), 0);
            slotDown = 0;
        }
        private void WriteResult(object result)
        {
            string path = Path.Combine(Directory, "hollowcraft-probe-result.json");
            File.WriteAllText(path + ".tmp", JsonConvert.SerializeObject(result));
            if (File.Exists(path)) File.Replace(path + ".tmp", path, null);
            else File.Move(path + ".tmp", path);
        }
    }
}
