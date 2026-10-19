using System;
using System.IO;
using HollowCraft.Link;
using HollowCraft.Render;
using HollowCraft.World;
using UnityEngine;
using UnitySceneManager = UnityEngine.SceneManagement.SceneManager;

namespace HollowCraft
{
    internal sealed class HollowCraftRuntime : MonoBehaviour
    {
        private readonly McState minecraft = new McState();
        private readonly McState incoming = new McState();
        private readonly RoomSlots rooms = new RoomSlots();
        private HostState host;
        private PlayerBridge player;
        private CollisionExporter collision;
        private CombatBridge combat;
        private Overlay overlay;
        private readonly PlacementPreview placement = new PlacementPreview();
        private Renderer originalRenderer;
        private SteveRig localSteve;
        private readonly ProtagonistReplicas replicas = new ProtagonistReplicas();
        private HeroController hero;
        private string scene;
        private int sceneHandle = int.MinValue;
        private ulong peerInstance;
        private bool sceneWasReady, runtimeReady, sceneGameplay;
        private bool failed, hadConnection, wasEverConnected;
        private bool pausedByBridge;
        private float previousTimeScale = 1;
        private float nextReport;
        private string error = "";
        private int frames;
        private float reportStarted;
        private RuntimeProbe probe;
        private bool initialSaveAttempted;
        private bool saveSlotsRefreshed;
        private Checkpoints checkpoints;
        private RecoveryTools recovery;
        private uint loadGeneration;
        private float physicsRecoveryUntil;
        private int statusWriteFailures;
        private System.Threading.Tasks.Task statusWriter=System.Threading.Tasks.Task.CompletedTask;

        private void Awake()
        {
            try
            {
                Application.runInBackground = true;
                if (!SharedLink.Instance.Create()) throw new InvalidOperationException("Cannot create shared memory");
                player = new PlayerBridge();
                // The offscreen actor fixture owns its tracker; a second Play hook would contaminate its native baseline.
                if (!HollowCraftMod.ActorFixture) replicas.Install();
                collision = new CollisionExporter();
                TerrainCutter.Instance.Committed += collision.Invalidate;
                combat = new CombatBridge(SharedLink.Instance.Session, player);
                checkpoints = gameObject.AddComponent<Checkpoints>();
                recovery = new RecoveryTools(checkpoints, RecoverAt);
                overlay = gameObject.AddComponent<Overlay>();
                host.ViewportW = 960; host.ViewportH = 540; host.GameHour = 12;
                host.MaxHealth = host.Health = 5; host.ControlSeq = 1;
                reportStarted = Time.realtimeSinceStartup;
                if (Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test") >= 0)
                {
                    probe = new RuntimeProbe(recovery, RecoverAt);
                    gameObject.AddComponent<CinematicProbe>();
                }
            }
            catch (Exception exception) { Fail(exception); }
        }

        internal static double StatusMilliseconds { get; private set; }
        internal static double FrameMilliseconds, ProbeMilliseconds, DrainMilliseconds, ReplicaMilliseconds;
        private void Update()
        {
            StatusMilliseconds=0;
            FrameMilliseconds=ProbeMilliseconds=DrainMilliseconds=ReplicaMilliseconds=0;
            bool measure=probe?.MeasuringRender==true;
            long began=measure ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;
            if (failed) return;
            try
            {
                var link = SharedLink.Instance;
                link.Heartbeat();
                if (player.PhysicsTimedOut)
                {
                    probe?.Cancel("Minecraft physics timed out");
                    player.RecoverPhysics();
                    host.TeleportSeq++;
                    physicsRecoveryUntil = Time.realtimeSinceStartup + 3;
                }
                bool connected = link.McAlive();
                bool peerChanged = connected && wasEverConnected && (!hadConnection || peerInstance != link.McInstance);
                if (connected) peerInstance = link.McInstance;
                if (connected != hadConnection)
                {
                    hadConnection = connected;
                    wasEverConnected |= connected;
                    if (!connected) probe?.Cancel("Minecraft disconnected");
                    Log.Info(connected ? "Minecraft connected" : "Minecraft disconnected");
                }
                if (connected && link.ReadMcState(incoming)) minecraft.CopyFrom(incoming);
                GameManager game = GameManager.instance;
                bool gameplayScene = game != null && game.IsGameplayScene();
                HeroController current = gameplayScene ? HeroController.instance : null;
                bool gameplay = current != null && gameplayScene;
                if (!gameplay && !saveSlotsRefreshed && UIManager.instance != null && game != null)
                {
                    var ui = UIManager.instance;
                    var buttons = new[] { ui.slotOne, ui.slotTwo, ui.slotThree, ui.slotFour };
                    bool available = true;
                    foreach (var button in buttons) available &= button != null && button.saveFileState != UnityEngine.UI.SaveSlotButton.SaveFileStates.OperationInProgress;
                    if (available)
                    {
                        // The base game can cache empty slots before the API has registered the isolated filename hook.
                        foreach (var button in buttons) { button.ClearCache(); button.Prepare(game); }
                        saveSlotsRefreshed = true;
                        if (probe != null && int.TryParse(Environment.GetEnvironmentVariable("HOLLOWCRAFT_TEST_PROFILE"), out int testSlot)
                            && testSlot >= 1 && testSlot <= 4) game.LoadGameFromUI(testSlot);
                    }
                }
                var activeScene = UnitySceneManager.GetActiveScene();
                bool newLoad = loadGeneration != checkpoints.LoadGeneration;
                if (newLoad) { loadGeneration = checkpoints.LoadGeneration; rooms.Invalidate(); initialSaveAttempted = false; }
                if (sceneHandle != activeScene.handle || gameplay != sceneGameplay || peerChanged || newLoad)
                {
                    probe?.Cancel("scene or peer changed");
                    if (sceneHandle != activeScene.handle || gameplay != sceneGameplay) sceneWasReady = false;
                    sceneGameplay = gameplay;
                    scene = activeScene.name;
                    sceneHandle = activeScene.handle;
                    host.WorldId = gameplay ? rooms.Select(scene) : 0;
                    ResetRoomLink();
                    Log.Info($"Scene {scene}: world {host.WorldId}, epoch {host.CollisionEpoch}");
                }
                if (hero != current)
                {
                    if (originalRenderer != null) originalRenderer.forceRenderingOff = false;
                    localSteve?.Dispose(); localSteve = null;
                    replicas.Clear();
                    hero = current;
                    originalRenderer = hero != null ? hero.GetComponent<Renderer>() : null;
                    player.SetHero(hero);
                    if (hero != null) localSteve = new SteveRig();
                }
                bool stateReady = checkpoints.Ready && gameplay && connected && link.Matches(minecraft) && minecraft.Has(Proto.McInWorld)
                    && minecraft.TeleportAck == host.TeleportSeq;
                bool peerScreen = stateReady && minecraft.Has(Proto.McScreenOpen);
                if (recovery.BlocksInput) player.SuppressPause();
                recovery.Frame(hero,host,stateReady,peerScreen);
                player.ModalBlocked=recovery.BlocksInput;
                stateReady = stateReady && link.Matches(minecraft) && minecraft.TeleportAck == host.TeleportSeq;
                bool wantsPause = gameplay && (recovery.BlocksInput || checkpoints.Saving || peerScreen || (sceneWasReady && !stateReady) || !RuntimeProbe.HasInputFocus);
                if (wantsPause)
                {
                    if (!pausedByBridge || Time.timeScale != 0) previousTimeScale = Time.timeScale;
                    Time.timeScale = 0;
                    pausedByBridge = true;
                }
                else if (!wantsPause && pausedByBridge)
                {
                    Time.timeScale = previousTimeScale;
                    pausedByBridge = false;
                }
                bool nativeMenu = recovery.BlocksInput || checkpoints.Saving || !gameplay || (game != null && game.isPaused);
                host.Flags = gameplay ? Proto.HostInGame : Proto.HostLoading | Proto.HostMenuOpen | Proto.HostNativeControl;
                if (nativeMenu || !RuntimeProbe.HasInputFocus) host.Flags |= Proto.HostMenuOpen;
                if (gameplay)
                {
                    long probeBegan=measure ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;
                    probe?.Frame(hero, host, minecraft, player.NativeControl, stateReady, combat.ActorCount);
                    if(measure) ProbeMilliseconds=(System.Diagnostics.Stopwatch.GetTimestamp()-probeBegan)*1000.0/System.Diagnostics.Stopwatch.Frequency;
                    player.Frame(minecraft, stateReady, nativeMenu, ref host);
                    collision.Update(Coords.ToMcF(player.Feet));
                    if (stateReady && !nativeMenu && !peerScreen && !pausedByBridge && RuntimeProbe.HasInputFocus)
                        combat.Frame(host.WorldId, host.CollisionEpoch, hero);
                    if (stateReady && !nativeMenu && !peerScreen) probe?.AfterFrame(hero);
                }
                link.WriteHostState(host);
				long drainBegan=measure ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;
				if (gameplay) BlockRenderer.Instance.Drain(); else link.DiscardRender();
                if (gameplay) TerrainCutter.Instance.Frame();
                if(measure) DrainMilliseconds=(System.Diagnostics.Stopwatch.GetTimestamp()-drainBegan)*1000.0/System.Diagnostics.Stopwatch.Frequency;
                bool ready = stateReady && BlockRenderer.Instance.HasAvatar;
                runtimeReady = ready;
                sceneWasReady |= ready;
                if (ready && !initialSaveAttempted && hero.acceptingInput && hero.cState.onGround && game.profileID >= 0)
                {
                    initialSaveAttempted = true;
                    if (!checkpoints.HasCommitted(game.profileID))
                        game.SaveGame(saved => Log.Info(saved ? "Initial sandbox save created" : "Initial sandbox save failed"));
                }
                BlockRenderer.Instance.Root.SetActive(ready);
                placement.Frame(ready && !player.NativeControl && !nativeMenu && !peerScreen);
                if (overlay != null)
                {
                    overlay.Pull(); overlay.Show = ready && (host.Flags & Proto.HostMenuOpen)==0;
                    overlay.ShowCursor = peerScreen;
                    Vector3 mouse = Input.mousePosition;
                    overlay.Cursor = new Vector2Int(Mathf.RoundToInt(mouse.x * host.ViewportW / Screen.width),
                        Mathf.RoundToInt((Screen.height - mouse.y) * host.ViewportH / Screen.height));
                }
                frames++;
                if (Time.realtimeSinceStartup >= nextReport)
                {
                    long statusStart=System.Diagnostics.Stopwatch.GetTimestamp();
                    nextReport = Time.realtimeSinceStartup + 1;
                    string path = Path.Combine(Application.persistentDataPath, "hollowcraft-runtime.json");
                    WriteStatus(path, Newtonsoft.Json.JsonConvert.SerializeObject(new {
                        connected, gameplay, ready, scene, world = host.WorldId, epoch = host.CollisionEpoch,
                        player.PhysicsTimeouts, player.MaxPhysicsWaitMilliseconds,
                        player.LastPhysicsTimeout,
                        statusWriteFailures,
                        native = player.NativeControl, heldItem = minecraft.HeldItem, heldFlags = minecraft.HeldFlags,
                        shieldBlocks = player.ShieldBlocks, lastShield = player.LastShield, minecraftFlags = minecraft.Flags,
                        attackDamage = minecraft.AttackDamage, teleport = host.TeleportSeq, teleportAck = minecraft.TeleportAck,
                        mcX = minecraft.X, mcY = minecraft.Y, collisionPending = collision.Pending,
                        meshes = BlockRenderer.Instance.SectionCount, avatar = BlockRenderer.Instance.HasAvatar,
                        terrainCuts = TerrainCutter.Instance.CutCount, terrainPending = TerrainCutter.Instance.Pending,
                        cutColliders = TerrainCutter.Instance.CutColliderCount,
                        playerExplosion = combat.LastPlayerExplosion,
                        actorCount = combat.ActorCount,
                        timeScale = Time.timeScale, pausedByBridge, nativeMenu, focused = Application.isFocused,
                        RuntimeProbe.BackgroundInput,
                        heroInput = hero != null && hero.acceptingInput, heroState = hero != null ? hero.hero_state.ToString() : "none",
                        moveX = host.MoveX, controlSeq = host.ControlSeq, controlAck = minecraft.ControlAck,
                        heroX = hero != null ? hero.transform.position.x : 0, heroY = hero != null ? hero.transform.position.y : 0,
                        colliderMinY = hero != null ? hero.GetComponent<Collider2D>().bounds.min.y : 0,
                        colliderHeight = hero != null ? hero.GetComponent<Collider2D>().bounds.size.y : 0,
                        heroScaleY = hero != null ? hero.transform.lossyScale.y : 0,
                        gravityScale = hero != null ? hero.GetComponent<Rigidbody2D>().gravityScale : 0,
                        animation = hero != null ? hero.GetComponent<tk2dSpriteAnimator>()?.CurrentClip?.name : null,
                        animationTime = host.AnimationTime, animationDuration = host.AnimationDuration,
                        meanFps = frames / Math.Max(.001f, Time.realtimeSinceStartup - reportStarted),
                        checkpointReady = checkpoints.Ready, checkpointSaving = checkpoints.Saving, checkpointError = checkpoints.Error,
                        avatarDiagnostics = probe != null && !probe.MeasuringRender ? BlockRenderer.Instance.AvatarDiagnostics : null,
                        visibleReplicas = replicas.ReplacedCount,
                        recoveryOpen = recovery.BlocksInput, recoveryBusy = recovery.Busy, recoveryStatus = recovery.Status, safePoints = recovery.SafePoints,
                        safetyCheck = probe != null ? recovery.LastSafetyCheck : null,
                        recoveryChecks = probe != null ? recovery.CandidateChecks : null,
                        pauseDisabled = PlayerData.instance != null && PlayerData.instance.GetBool("disablePause"),
                        timeSlowed = game != null && game.TimeSlowed,
                        pauseAllowed = game != null && game.inputHandler != null && game.inputHandler.pauseAllowed,
                        inputHandlerAccepting = game != null && game.inputHandler != null ? typeof(InputHandler).GetField("acceptingInput",System.Reflection.BindingFlags.Instance|System.Reflection.BindingFlags.Public|System.Reflection.BindingFlags.NonPublic)?.GetValue(game.inputHandler) : null,
                        pauseDecision = probe != null ? player.LastPauseDecision : null,
                        gameState = game != null ? game.gameState.ToString() : null,
                        profile = Application.persistentDataPath
                    }));
                    StatusMilliseconds=(System.Diagnostics.Stopwatch.GetTimestamp()-statusStart)*1000.0/System.Diagnostics.Stopwatch.Frequency;
                }
            }
            catch (Exception exception) { Fail(exception); }
            finally { if(measure) FrameMilliseconds=(System.Diagnostics.Stopwatch.GetTimestamp()-began)*1000.0/System.Diagnostics.Stopwatch.Frequency; }
        }

        private void WriteStatus(string path, string json)
        {
            if(!statusWriter.IsCompleted) return;
            // The snapshot is already serialized; diagnostic filesystem latency must not stall gameplay.
            statusWriter=System.Threading.Tasks.Task.Run(()=>
            {
                try
                {
                    File.WriteAllText(path + ".tmp", json);
                    if (File.Exists(path)) File.Replace(path + ".tmp", path, null);
                    else File.Move(path + ".tmp", path);
                }
                catch(Exception error) when(error is IOException || error is UnauthorizedAccessException)
                {System.Threading.Interlocked.Increment(ref statusWriteFailures);}
            });
        }

        private void LateUpdate()
        {
            // Native hit-stop coroutines may restore time after Update; remember their requested scale without unpausing the bridge.
            if (pausedByBridge && Time.timeScale != 0) { previousTimeScale = Time.timeScale; Time.timeScale = 0; }
            if (failed || hero == null || originalRenderer == null) return;
            bool measure=probe?.MeasuringRender==true;
            long began=measure ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;
            Vector3 renderFeet=player.RenderFeet;
            if(!HollowCraftMod.ActorFixture) replicas.Frame(hero, renderFeet);
            BlockRenderer.Instance.PlaceAvatar(renderFeet, runtimeReady && originalRenderer.enabled && hero.gameObject.activeInHierarchy,originalRenderer.gameObject.layer);
            originalRenderer.forceRenderingOff = true;
            localSteve.Show(!runtimeReady && originalRenderer.enabled && hero.gameObject.activeInHierarchy);
            if (!runtimeReady) localSteve.Frame(renderFeet, Coords.K, hero.cState.facingRight,
                hero.GetComponent<tk2dSpriteAnimator>(), originalRenderer, Color.white);
            if(measure) ReplicaMilliseconds=(System.Diagnostics.Stopwatch.GetTimestamp()-began)*1000.0/System.Diagnostics.Stopwatch.Frequency;
            probe?.RecordRenderPose(hero,player.Feet,player.NativeControl);
            probe?.CaptureAfterRender();
        }
        private void ResetRoomLink()
        {
            host.CollisionEpoch++; host.TeleportSeq++;
            SharedLink.Instance.SetScope(host.WorldId,host.CollisionEpoch);
            TerrainCutter.Instance.Clear(); collision.Reset(host.CollisionEpoch); combat.Clear();
            BlockRenderer.Instance.ClearAll(); DugBlocks.SetWorld(host.WorldId); DugBlocks.Clear(); player.ResetLink();
        }
        private void RecoverAt(Vector2 position) { player.Teleport(position); ResetRoomLink(); }

        private void Fail(Exception exception)
        {
            failed = true; error = exception.Message;
            probe?.Cancel("runtime failure");
            Log.Error(exception.ToString());
            if (originalRenderer != null) originalRenderer.forceRenderingOff = false;
            localSteve?.Dispose(); localSteve = null;
            replicas.Dispose();
            player?.Dispose();
            collision?.Stop();
            TerrainCutter.Instance.Clear();
            if (pausedByBridge) { Time.timeScale = previousTimeScale; pausedByBridge = false; }
        }

        private void OnGUI()
        {
            if (!failed && GameManager.instance != null && GameManager.instance.IsCinematicScene()) return;
            string message = failed ? "HollowCraft错误：" + error : !hadConnection ? "HollowCraft：等待独立Minecraft实例"
                : Time.realtimeSinceStartup < physicsRecoveryUntil && !runtimeReady ? "Minecraft 响应超时，正在恢复"
                : !minecraft.Has(Proto.McInWorld) ? "HollowCraft：正在载入Minecraft世界" : null;
            if (message != null) GUI.Label(new Rect(12, Screen.height - 34, Screen.width - 24, 26), message);
            if (checkpoints != null && checkpoints.Error != null) GUI.Label(new Rect(12, Screen.height - 62, Screen.width - 24, 26), "存档检查点失败：" + checkpoints.Error);
            recovery?.OnGUI();
        }

        private void OnApplicationQuit()
        {
            probe?.Cancel("game exiting");
            collision?.Stop();
            TerrainCutter.Instance.Clear();
            if (!failed) player?.Dispose();
            if (pausedByBridge) Time.timeScale = previousTimeScale;
            SharedLink.Instance.Close();
            localSteve?.Dispose();
            replicas.Dispose();
        }
    }
}
