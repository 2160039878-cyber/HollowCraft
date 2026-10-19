using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using GlobalEnums;
using HollowCraft.Link;
using MonoMod.RuntimeDetour;
using MonoMod.Utils;
using UnityEngine;

namespace HollowCraft
{
    internal sealed class PlayerBridge : IDisposable
    {
        private const BindingFlags ControllerMembers = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        private static readonly FieldInfo DoubleJumped = typeof(HeroController).GetField("doubleJumped", ControllerMembers);
        private static readonly FieldInfo AcceptingInput = typeof(HeroController).GetField("acceptingInput", ControllerMembers);
        private static readonly FieldInfo JumpSteps = typeof(HeroController).GetField("jump_steps", ControllerMembers);
        private static readonly FieldInfo JumpedSteps = typeof(HeroController).GetField("jumped_steps", ControllerMembers);
        private static readonly FieldInfo DoubleJumpSteps = typeof(HeroController).GetField("doubleJump_steps", ControllerMembers);
        private static readonly FieldInfo NailChargeTimer = typeof(HeroController).GetField("nailChargeTimer", ControllerMembers);
        private static readonly MethodInfo CanAttack = typeof(HeroController).GetMethod("CanAttack", ControllerMembers);
        private static readonly MethodInfo DoAttack = typeof(HeroController).GetMethod("DoAttack", ControllerMembers);
        private static readonly MethodInfo ResetMotion = typeof(HeroController).GetMethod("ResetMotion", ControllerMembers);
        private readonly ControlState control = new ControlState();
        private readonly Dictionary<int, bool> keys = new Dictionary<int, bool>();
        private readonly ConditionalWeakTable<IEnumerator, object> pauseIterators = new ConditionalWeakTable<IEnumerator, object>();
        private readonly Hook pauseHook;
        private HeroController hero;
        private Rigidbody2D body;
        private Collider2D collider;
        private tk2dSpriteAnimator animator;
        private PlayMakerFSM slashDamage;
        private McState minecraft;
        private readonly McState physicsReply = new McState();
        private HostState physicsRequest;
        private float gravity;
        private bool gravityOverridden;
        private float feetOffset;
        private bool external;
        private bool inputBlocked;
        private bool connected;
        private uint jumpSeq;
        private uint jumpPressSeq;
        private uint physicsTick, jumpPressTick, jumpReleaseTick;
        private bool jumpHeld;
        private float jumpStartedAt, jumpHeldSeconds;
        private bool mouseDown;
        private bool rightDown;
        private bool shieldDown;
        private int swingDamage;
        private bool readyForControl;
        private bool nativeUi;
        private int pauseBlockedUntil;
        private sealed class ShieldHit
        {
            public GameObject Source;
            public CollisionSide Side;
            public int Amount, Hazard;
            public float Deadline, RecoilSpeed;
        }
        private readonly Dictionary<uint, ShieldHit> shieldHits = new Dictionary<uint, ShieldHit>();
        private readonly Dictionary<int, float> shieldContacts = new Dictionary<int, float>();
        private readonly List<uint> expiredShieldHits = new List<uint>();
        private uint shieldSequence;
        private bool replayingShield;
        public int ShieldBlocks { get; private set; }
        public object LastShield { get; private set; }
        private bool ShieldUsing => connected && minecraft != null && minecraft.Has(Proto.McShieldUsing);
        private bool ShieldInput => Input.GetMouseButton(1) || RuntimeProbe.ShieldHeld;
        private bool WantsShield => ShieldInput && minecraft != null && minecraft.Has(Proto.McOffhandShield)
            && (minecraft.HeldFlags & (Proto.HeldSword | Proto.HeldBow)) != 0;
        public bool ModalBlocked { get; set; }
        public object LastPauseDecision { get; private set; }
        public void SuppressPause() => pauseBlockedUntil = Time.frameCount + 2;
        public bool NativeControl { get; private set; } = true;
        public bool PhysicsTimedOut { get; private set; }
        public int PhysicsTimeouts { get; private set; }
        public double MaxPhysicsWaitMilliseconds { get; private set; }
        private static int physicsTimingFrame=-1;
        private static double physicsMilliseconds;
        internal static double FramePhysicsMilliseconds => physicsTimingFrame==Time.frameCount ? physicsMilliseconds : 0;
        public object LastPhysicsTimeout { get; private set; }
        public bool ScreenOpen => minecraft != null && minecraft.Has(Proto.McScreenOpen);
        public Vector3 Feet => hero == null ? Vector3.zero : new Vector3(body.position.x, body.position.y - feetOffset, Coords.Depth);
        public Vector3 RenderFeet => hero == null ? Vector3.zero : new Vector3(hero.transform.position.x, hero.transform.position.y - feetOffset, Coords.Depth);

        public PlayerBridge()
        {
            if (DoubleJumped == null || AcceptingInput == null || JumpSteps == null || JumpedSteps == null || DoubleJumpSteps == null || NailChargeTimer == null || CanAttack == null || DoAttack == null || ResetMotion == null)
                throw new MissingMemberException("The selected Hollow Knight controller is incompatible");
            On.HeroController.FixedUpdate += FixedUpdate;
            On.HeroController.LookForInput += LookForInput;
            On.HeroController.CanAttack += NativeCanAttack;
            On.HeroController.CanNailCharge += NativeCanNailCharge;
            On.HeroController.CanNailArt += NativeCanNailArt;
            On.HeroController.DoDoubleJump += DoubleJump;
            On.HeroController.Bounce += Bounce;
            On.HeroController.AffectedByGravity += NativeGravity;
            On.HeroController.TakeDamage += ShieldDamage;
            MethodInfo pauseStep=typeof(GameManager).GetMethod("PauseGameToggle",ControllerMembers)?.GetStateMachineTarget();
            if (pauseStep==null) throw new MissingMethodException("Native pause state machine is unavailable");
            pauseHook=new Hook(pauseStep,(Func<Func<IEnumerator,bool>,IEnumerator,bool>)PauseStep);
            Modding.ModHooks.GetPlayerIntHook += PlayerInt;
            Modding.ModHooks.AttackHook += BeginAttack;
        }

        public void SetHero(HeroController current)
        {
            if (hero == current) return;
            RestoreGravity();
            hero = current;
            if (hero == null) return;
            body = hero.GetComponent<Rigidbody2D>();
            collider = hero.GetComponent<Collider2D>();
            animator = hero.GetComponent<tk2dSpriteAnimator>();
            slashDamage = Array.Find(hero.GetComponentsInChildren<PlayMakerFSM>(true), f => f.FsmName == "Set Slash Damage");
            if (body == null || collider == null) throw new InvalidOperationException("Missing native player body");
            if (slashDamage == null) throw new MissingMemberException("Missing native slash damage state machine");
            feetOffset = hero.transform.position.y - collider.bounds.min.y;
            Coords.K = 1.8f / Mathf.Max(.25f, collider.bounds.size.y);
            Coords.Depth = hero.transform.position.z;
            Render.Materials.BindHero(hero.GetComponent<Renderer>()?.sharedMaterial);
            Log.Info($"Player calibration: {Coords.K:F3} blocks/unit, collider {collider.bounds.size}");
        }

        private bool Busy()
        {
            if (hero == null) return true;
            var state = hero.cState;
            return state.dead || state.transitioning || state.attacking || state.dashing || state.superDashing ||
                state.recoiling || state.recoilFrozen || state.focusing || state.nailCharging || !(bool)AcceptingInput.GetValue(hero)
                || hero.controlReqlinquished;
        }

        public void Frame(McState state, bool peerAlive, bool menu, ref HostState host)
        {
            minecraft = state;
            connected = peerAlive && state.Has(Proto.McInWorld);
            if (!connected) { shieldHits.Clear(); shieldContacts.Clear(); }
            if (hero == null) return;
            expiredShieldHits.Clear();
            foreach (var hit in shieldHits) if (Time.realtimeSinceStartup >= hit.Value.Deadline) expiredShieldHits.Add(hit.Key);
            foreach (uint id in expiredShieldHits) ResolveShield(id, 0, -1, -1);
            nativeUi = menu || ModalBlocked || !hero.acceptingInput || hero.controlReqlinquished || hero.cState.dead || hero.cState.transitioning;
            inputBlocked = !connected || nativeUi || ScreenOpen || !RuntimeProbe.HasInputFocus;
            if (ScreenOpen || ModalBlocked) SuppressPause();
            if (nativeUi) host.Flags |= Proto.HostMenuOpen;
            bool ready = connected && state.TeleportAck == host.TeleportSeq;
            readyForControl = ready;
            bool busy = Busy();
            if (!hero.cState.attacking) swingDamage = 0;
            bool grounded = external ? state.Has(Proto.McOnGround) : hero.cState.onGround;
            if (grounded) control.Land();
            if (!external && (bool)DoubleJumped.GetValue(hero)) control.ConsumeAirJump();
            SetNativeControl(!ready || control.Owner == MovementOwner.Knight || busy);
            external = !NativeControl && !inputBlocked && state.ControlAck == control.Generation;
            if (!external) RestoreGravity();

            Vector3 feet = Feet;
            Coords.ToMc(feet, out host.PosX, out host.PosY, out host.PosZ);
            host.VelocityX = body.velocity.x * Coords.K;
            host.VelocityY = body.velocity.y * Coords.K;
            host.ControlSeq = control.Generation;
            host.AirJumpUsed = control.AirJumpUsed ? 1u : 0u;
            host.JumpVelocity = hero.JUMP_SPEED * Coords.K;
            var data = PlayerData.instance;
            host.RunSpeed = (hero.cState.inWalkZone ? hero.WALK_SPEED
                : data.GetBool("equippedCharm_37") && grounded
                    ? (data.GetBool("equippedCharm_31") ? hero.RUN_SPEED_CH_COMBO : hero.RUN_SPEED_CH) : hero.RUN_SPEED) * Coords.K;
            host.Gravity = Math.Abs(Physics2D.gravity.y * hero.DEFAULT_GRAVITY) * Coords.K;
            host.MaxFall = hero.MAX_FALL_VELOCITY * Coords.K;
            host.FixedStep = Time.fixedDeltaTime;
            host.JumpHold = (hero.JUMP_STEPS + 1) * host.FixedStep;
            host.JumpMin = hero.JUMP_STEPS_MIN * host.FixedStep;
            host.DoubleDelay = 4 * host.FixedStep;
            host.DoubleHold = Math.Max(0, hero.DOUBLE_JUMP_STEPS - 3) * host.FixedStep;
            host.RemainingHold = hero.cState.jumping ? Math.Max(0, hero.JUMP_STEPS + 1 - (int)JumpSteps.GetValue(hero)) * host.FixedStep : 0;
            host.RemainingMin = hero.cState.jumping ? Math.Max(0, hero.JUMP_STEPS_MIN - (int)JumpedSteps.GetValue(hero)) * host.FixedStep : 0;
            host.Flags |= NativeControl ? Proto.HostNativeControl : 0;
            host.Flags |= grounded ? Proto.HostOnGround : 0;
            host.Flags |= PlayerData.instance.GetBool("hasDoubleJump") ? Proto.HostCanDoubleJump : 0;
            host.Health = PlayerData.instance.health;
            host.MaxHealth = PlayerData.instance.maxHealth;
            var clip = animator?.CurrentClip;
            host.AnimationName = clip?.name ?? "Idle";
            host.AnimationTime = Render.SteveRig.ClipTime(animator);
            host.AnimationDuration = clip != null && clip.frames != null && clip.fps > 0 ? clip.frames.Length / clip.fps : 1;
            host.AnimationLoop = clip != null && (clip.wrapMode == tk2dSpriteAnimationClip.WrapMode.Loop
                || clip.wrapMode == tk2dSpriteAnimationClip.WrapMode.LoopSection || clip.wrapMode == tk2dSpriteAnimationClip.WrapMode.PingPong) ? 1u : 0u;

            var input = GameManager.instance.inputHandler.inputActions;
            bool heldNow = !inputBlocked && input.jump.IsPressed;
            if (heldNow && !jumpHeld) { jumpStartedAt = Time.time; jumpPressSeq++; jumpHeldSeconds = 0; jumpPressTick = physicsTick; }
            if (heldNow || jumpHeld) jumpHeldSeconds = Mathf.Clamp(Time.time - jumpStartedAt, 0, 3600);
            if (!heldNow && jumpHeld) jumpReleaseTick = physicsTick;
            jumpHeld = heldNow;
            if (jumpHeld) host.Flags |= Proto.HostJumpHeld;
            host.JumpHeldSeconds = jumpHeldSeconds; host.JumpPressSeq = jumpPressSeq;
            host.PhysicsTick = physicsTick; host.JumpPressTick = jumpPressTick; host.JumpReleaseTick = jumpReleaseTick;
            host.MotionState = ((uint)(int)JumpSteps.GetValue(hero) & 255)
                | (((uint)(int)JumpedSteps.GetValue(hero) & 255) << 8)
                | (((uint)(int)DoubleJumpSteps.GetValue(hero) & 255) << 16)
                | (hero.cState.jumping ? Proto.MotionJump : 0) | (hero.cState.doubleJumping ? Proto.MotionDoubleJump : 0);
            host.MoveX = inputBlocked ? 0 : input.moveVector.Vector.x;
            Vector3 mouse = Input.mousePosition;
            Camera camera = GameCameras.instance != null ? GameCameras.instance.mainCamera : Camera.main;
            Vector3 aim = camera != null ? camera.ScreenToWorldPoint(new Vector3(mouse.x, mouse.y,
                Mathf.Abs(camera.transform.position.z - Coords.Depth))) : feet + Vector3.right;
            if (RuntimeProbe.AimOverride is Vector2 probeAim) aim = probeAim;
            host.AimX = aim.x * Coords.K + Coords.OffsetX;
            host.AimY = aim.y * Coords.K;
            double dx = host.AimX - host.PosX, dy = host.AimY - (host.PosY + 1.62);
            // A raised Minecraft shield follows aim while HK movement can retreat in the opposite direction.
            host.Yaw = NativeControl && !WantsShield && !ShieldUsing ? (hero.cState.facingRight ? -90 : 90) : (dx >= 0 ? -90 : 90);
            host.Pitch = NativeControl ? 0 : (float)(-Math.Atan2(dy, Math.Abs(dx)) * 180 / Math.PI);

            if (ready) RouteInput(ref host, input.jump.IsPressed, input.jump.WasPressed, input.attack.IsPressed);
            else Release();
            host.JumpSeq = jumpSeq;
            host.AirJumpUsed = control.AirJumpUsed ? 1u : 0u;
            physicsRequest = host;
        }

        private void RouteInput(ref HostState host, bool jumpHeld, bool jumpPressed, bool attackHeld)
        {
            var link = SharedLink.Instance;
            if (nativeUi) { Release(); return; }
            if (!RuntimeProbe.HasInputFocus) { Release(); return; }
            if (inputBlocked && !ScreenOpen) { Release(); return; }
            if (Input.GetKeyDown(KeyCode.F7)) link.PushInput(Proto.InRefill, 0, 0);
            if (Input.GetKeyDown(KeyCode.E)) { link.PushInput(Proto.InKey, 8, 1); link.PushInput(Proto.InKey, 8, 0); }
            for (int i = 0; i < 9; i++) Key(30 + i, Input.GetKey(KeyCode.Alpha1 + i));
            float wheel = Input.mouseScrollDelta.y;
            if (wheel != 0) link.PushInput(Proto.InScroll, 0, Mathf.RoundToInt(wheel * 120));
            Vector3 mouse = Input.mousePosition;
            link.PushInput(Proto.InCursor, 0, Mathf.RoundToInt(mouse.x * host.ViewportW / Screen.width),
                Mathf.RoundToInt((Screen.height - mouse.y) * host.ViewportH / Screen.height));
            bool left = Input.GetMouseButton(0), right = ShieldInput;
            if (ScreenOpen)
            {
                ShieldButton(false);
                if (Input.GetKeyDown(KeyCode.Escape)) { link.PushInput(Proto.InKey, 41, 1); link.PushInput(Proto.InKey, 41, 0); }
                Button(1, left, ref mouseDown); Button(3, right, ref rightDown);
                Key(225, Input.GetKey(KeyCode.LeftShift));
                return;
            }
            if (inputBlocked) { Release(); return; }
            if (NativeControl)
            {
                Key(26, false); Key(22, false); Key(44, false);
                Key(225, false); Key(224, false);
                Button(1, false, ref mouseDown);
                Button(3, false, ref rightDown);
                ShieldButton(right && minecraft.Has(Proto.McOffhandShield) && !hero.cState.attacking && !hero.cState.focusing);
                if (Input.GetMouseButtonDown(0) && (bool)CanAttack.Invoke(hero, null)) DoAttack.Invoke(hero, null);
            }
            else
            {
                bool facingRight = host.Yaw < 0;
                Key(26, facingRight ? host.MoveX > .1f : host.MoveX < -.1f);
                Key(22, facingRight ? host.MoveX < -.1f : host.MoveX > .1f);
                Key(44, jumpHeld);
                Key(225, Input.GetKey(KeyCode.LeftShift)); Key(224, Input.GetKey(KeyCode.LeftControl));
                bool bow = (minecraft.HeldFlags & Proto.HeldBow) != 0;
                bool shield = bow && right && minecraft.Has(Proto.McOffhandShield);
                Button(1, !bow && (left || attackHeld), ref mouseDown);
                if (!shield) ShieldButton(false);
                Button(3, bow ? attackHeld && !shield : right, ref rightDown);
                if (shield) ShieldButton(true);
                if (jumpPressed && control.TryAirJump(PlayerData.instance.GetBool("hasDoubleJump"), minecraft.Has(Proto.McOnGround))) jumpSeq++;
            }
        }

        private void Key(int code, bool down)
        {
            keys.TryGetValue(code, out bool previous);
            if (previous == down) return;
            keys[code] = down;
            SharedLink.Instance.PushInput(Proto.InKey, (ushort)code, down ? 1 : 0);
        }
        private void ShieldButton(bool down)
        {
            if (shieldDown == down) return;
            shieldDown = down;
            SharedLink.Instance.PushInput(Proto.InShieldUse, 0, down ? 1 : 0);
        }
        private static void Button(ushort code, bool down, ref bool previous)
        {
            if (previous == down) return;
            previous = down;
            SharedLink.Instance.PushInput(Proto.InMouseButton, code, down ? 1 : 0);
        }
        private void Release()
        {
            SharedLink.Instance.PushInput(Proto.InReleaseAll, 0);
            keys.Clear(); mouseDown = rightDown = shieldDown = false;
        }
        public void ResetLink()
        {
            shieldHits.Clear(); shieldContacts.Clear();
            external = readyForControl = connected = false;
            PhysicsTimedOut = false;
            inputBlocked = true;
            RestoreGravity(); Release();
        }
        public void RecoverPhysics()
        {
            if (hero != null && minecraft != null && DamageRules.Finite(minecraft.VelocityX) && DamageRules.Finite(minecraft.VelocityY))
                body.velocity = new Vector2((float)minecraft.VelocityX / Coords.K, (float)minecraft.VelocityY / Coords.K);
            ResetLink();
        }
        public void Teleport(Vector2 position)
        {
            if (hero==null || !DamageRules.Finite(position.x) || !DamageRules.Finite(position.y)) throw new InvalidOperationException("Invalid recovery position");
            ResetMotion.Invoke(hero,null);
            body.position=position;
            hero.transform.position=new Vector3(position.x,position.y,hero.transform.position.z);
            body.linearVelocity=Vector2.zero;
            ResetLink(); Physics2D.SyncTransforms();
        }
        private bool PauseStep(Func<IEnumerator,bool> original,IEnumerator iterator)
        {
            // The tiny iterator factory can be inlined before mods load. Gate the first actual MoveNext instead.
            if (!pauseIterators.TryGetValue(iterator,out _))
            {
                pauseIterators.Add(iterator,this);
                bool blocked=ScreenOpen || ModalBlocked || Time.frameCount<=pauseBlockedUntil;
                LastPauseDecision=new { blocked,peerScreen=ScreenOpen,ModalBlocked,frame=Time.frameCount,pauseBlockedUntil };
                if (blocked) return false;
            }
            return original(iterator);
        }
        private void RestoreGravity()
        {
            if (!gravityOverridden) return;
            if (body != null) body.gravityScale = gravity;
            gravityOverridden = false;
        }
        private void SetNativeControl(bool value)
        {
            if (value && !NativeControl) Release();
            NativeControl = value;
            if (value) { external = false; RestoreGravity(); }
        }
        private void NativeGravity(On.HeroController.orig_AffectedByGravity original, HeroController current, bool gravityApplies)
        {
            // Native code snapshots the current gravity before suspending it; do not let it capture our temporary zero.
            if (current == hero) RestoreGravity();
            original(current, gravityApplies);
        }
        private void FixedUpdate(On.HeroController.orig_FixedUpdate original, HeroController current)
        {
            if (current == hero && PhysicsTimedOut) { body.velocity = Vector2.zero; return; }
            if (current == hero) physicsTick++;
            // Damage and scripted actions can start after Frame; honour their ownership before this physics step.
            if (current == hero && Busy()) SetNativeControl(true);
            if (current == hero && minecraft != null && readyForControl
                && control.RequestOwner((minecraft.HeldFlags & Proto.HeldSword) != 0, Busy() || inputBlocked))
            {
                if (control.Owner == MovementOwner.Knight)
                {
                    Vector3 handoff = Coords.ToUnity(minecraft.X, minecraft.Y, Coords.PlaneZ);
                    body.position = new Vector2(handoff.x, handoff.y + feetOffset);
                    body.velocity = new Vector2((float)minecraft.VelocityX / Coords.K, (float)minecraft.VelocityY / Coords.K);
                    if (minecraft.Yaw < 0) hero.FaceRight(); else hero.FaceLeft();
                    DoubleJumped.SetValue(hero, control.AirJumpUsed);
                    RestoreJumpState(minecraft.MotionState);
                }
                SetNativeControl(control.Owner == MovementOwner.Knight);
                external = false; // Wait for the peer to acknowledge the new generation before moving its body.
                RestoreGravity();
                Log.Debug($"Control -> {control.Owner}, generation {control.Generation}");
            }
            if (current != hero || !external || minecraft == null || !connected) { original(current); return; }
            if (!gravityOverridden) { gravity = body.gravityScale; gravityOverridden = true; }
            body.gravityScale = 0;
            body.velocity = Vector2.zero;
            if (!SynchronizePhysics()) return;
            Vector3 point = Coords.ToUnity(minecraft.X, minecraft.Y, Coords.PlaneZ);
            body.MovePosition(new Vector2(point.x, point.y + feetOffset));
            body.velocity = Vector2.zero;
            hero.cState.onGround = minecraft.Has(Proto.McOnGround);
            hero.cState.falling = minecraft.VelocityY < -.1;
            RestoreJumpState(minecraft.MotionState);
            // HK's camera follows this flag. Aim can turn Steve without moving a stationary placement target.
            if (minecraft.VelocityX > .2) hero.FaceRight(); else if (minecraft.VelocityX < -.2) hero.FaceLeft();
        }
        private bool SynchronizePhysics()
        {
            var link = SharedLink.Instance;
            physicsRequest.PhysicsTick = physicsTick;
            link.WriteHostState(physicsRequest);
            long started = System.Diagnostics.Stopwatch.GetTimestamp();
            long deadline = started + System.Diagnostics.Stopwatch.Frequency / 25;
            long lastPoll=started,maxPollGap=0;
            int polls=0;
            bool ready = false, menu = false;
            while (true)
            {
                long now=System.Diagnostics.Stopwatch.GetTimestamp();
                maxPollGap=Math.Max(maxPollGap,now-lastPoll);lastPoll=now;polls++;
                if (link.ReadMcState(physicsReply) && link.Matches(physicsReply)
                    && physicsReply.ControlAck == control.Generation && physicsReply.TeleportAck == physicsRequest.TeleportSeq
                    && physicsReply.Has(Proto.McInWorld) && DamageRules.Finite(physicsReply.X) && DamageRules.Finite(physicsReply.Y))
                {
                    ready = physicsReply.PhysicsTick == physicsTick;
                    menu = physicsReply.Has(Proto.McScreenOpen);
                    if (ready || menu) { minecraft.CopyFrom(physicsReply); break; }
                }
                // A late-woken thread must check an already-published reply before declaring timeout.
                if (!link.McAlive() || System.Diagnostics.Stopwatch.GetTimestamp() >= deadline) break;
                System.Threading.Thread.Sleep(Math.Max(1,RuntimeProbe.TakePhysicsPollDelay()));
            }
            double elapsed = (System.Diagnostics.Stopwatch.GetTimestamp() - started) * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
            if(physicsTimingFrame!=Time.frameCount) {physicsTimingFrame=Time.frameCount;physicsMilliseconds=0;}
            physicsMilliseconds+=elapsed;
            MaxPhysicsWaitMilliseconds = Math.Max(MaxPhysicsWaitMilliseconds, elapsed);
            if (ready) return true;
            if (!menu)
            {
                var late=new McState();bool lateRead=link.ReadMcState(late);
                LastPhysicsTimeout = new { expectedTick = physicsTick, replyTick = physicsReply.PhysicsTick,
                expectedControl = control.Generation, replyControl = physicsReply.ControlAck,
                expectedTeleport = physicsRequest.TeleportSeq, replyTeleport = physicsReply.TeleportAck,
                scopeMatches = link.Matches(physicsReply), physicsReply.Flags, physicsReply.MotionState,
                physicsReply.FrameCounter, elapsed,polls,
                maxPollGapMilliseconds=maxPollGap*1000.0/System.Diagnostics.Stopwatch.Frequency,
                finalPollGapMilliseconds=(System.Diagnostics.Stopwatch.GetTimestamp()-lastPoll)*1000.0/System.Diagnostics.Stopwatch.Frequency,
                utcMilliseconds=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),lateRead,
                lateTick=late.PhysicsTick,lateControl=late.ControlAck,lateTeleport=late.TeleportAck,
                lateScopeMatches=lateRead && link.Matches(late),lateFlags=late.Flags,lateFrame=late.FrameCounter };
            }
            // A paused or missing peer must not consume a player simulation step or replay a late pose.
            physicsTick--;
            if (!menu) { PhysicsTimedOut = true; PhysicsTimeouts++; inputBlocked = true; Release(); }
            return false;
        }
        private void RestoreJumpState(uint state)
        {
            JumpSteps.SetValue(hero, (int)(state & 255));
            JumpedSteps.SetValue(hero, (int)((state >> 8) & 255));
            DoubleJumpSteps.SetValue(hero, (int)((state >> 16) & 255));
            hero.cState.jumping = (state & Proto.MotionJump) != 0;
            hero.cState.doubleJumping = (state & Proto.MotionDoubleJump) != 0;
        }
        private void LookForInput(On.HeroController.orig_LookForInput original, HeroController current)
        {
            if (current == hero && (!NativeControl || inputBlocked)) return;
            original(current);
        }
        private bool NativeCanAttack(On.HeroController.orig_CanAttack original, HeroController current)
        {
            // Buffered attacks also reach this gate outside LookForInput.
            if (current == hero && (inputBlocked || !NativeControl || ShieldUsing || WantsShield
                || (connected && minecraft != null && (minecraft.HeldFlags & Proto.HeldSword) == 0))) return false;
            return original(current);
        }
        private void ShieldDamage(On.HeroController.orig_TakeDamage original, HeroController current, GameObject source,
            CollisionSide side, int amount, int hazard)
        {
            if (current != hero || replayingShield || inputBlocked || source == null || amount <= 0 || amount > 1000
                || hazard != 1 || hero.cState.dead)
            { original(current, source, side, amount, hazard); return; }
            var sourceCollider=source.GetComponent<Collider2D>();
            var sourceBody=sourceCollider!=null ? sourceCollider.attachedRigidbody : null;
            int sourceId = sourceBody!=null ? sourceBody.GetInstanceID() : source.GetInstanceID();
            // Compound bodies (e.g. Mantis body + Dash Hit) repeat one impact through several DamageHero components.
            if (shieldContacts.TryGetValue(sourceId, out float until) && Time.time < until) return;
            if (!ShieldUsing || hero.cState.invulnerable || shieldHits.Count >= 64)
            { original(current, source, side, amount, hazard); return; }
            Vector2 point = sourceBody!=null ? sourceBody.position : sourceCollider!=null ? (Vector2)sourceCollider.bounds.center : source.transform.position;
            Vector2 direction = point - (Vector2)collider.bounds.center;
            if (direction.sqrMagnitude < .001f) direction = side == CollisionSide.left ? Vector2.left : Vector2.right;
            ushort code = (ushort)Mathf.FloorToInt(Mathf.Repeat(Mathf.Atan2(direction.y, direction.x) * Mathf.Rad2Deg, 360) * 50);
            if (source.name == "HollowCraft TNT blast") code |= 32768;
            shieldSequence = shieldSequence >= int.MaxValue ? 1 : shieldSequence + 1;
            shieldHits[shieldSequence] = new ShieldHit { Source = source, Side = side, Amount = amount, Hazard = hazard,
                Deadline = Time.realtimeSinceStartup + .3f, RecoilSpeed = hero.RECOIL_VELOCITY };
            if (shieldContacts.Count > 256) shieldContacts.Clear();
            shieldContacts[sourceId] = Time.time + .3f;
            SharedLink.Instance.PushInput(Proto.InShieldHit, code, amount * 400, (int)shieldSequence);
        }
        public void ResolveShield(uint request, float blocked, float wearBefore, float wearAfter)
        {
            if (!shieldHits.TryGetValue(request, out ShieldHit hit)) return;
            shieldHits.Remove(request);
            int remaining = DamageRules.Player(Math.Max(0, hit.Amount * 4 - Mathf.Clamp(blocked, 0, hit.Amount * 4)));
            int before = PlayerData.instance.health;
            if (remaining > 0 && hero != null && !hero.cState.dead)
            {
                float recoilSpeed=hero.RECOIL_VELOCITY;
                replayingShield = true;
                try { hero.RECOIL_VELOCITY=hit.RecoilSpeed;hero.TakeDamage(hit.Source, hit.Side, remaining, hit.Hazard); }
                finally { hero.RECOIL_VELOCITY=recoilSpeed;replayingShield = false; }
            }
            if (remaining < hit.Amount) ShieldBlocks++;
            LastShield = new { request, source = hit.Source != null ? hit.Source.name : null, blocked, remaining,
                wearBefore, wearAfter, before, after = PlayerData.instance.health, realtime = Time.realtimeSinceStartup };
            Log.Info("Shield resolution: " + Newtonsoft.Json.JsonConvert.SerializeObject(LastShield));
        }
        private bool NativeCanNailCharge(On.HeroController.orig_CanNailCharge original, HeroController current)
        {
            if (current == hero && (inputBlocked || !NativeControl || ShieldUsing || WantsShield || (connected && minecraft != null
                && (minecraft.HeldFlags & Proto.HeldSword) == 0 && !current.cState.nailCharging)))
            { NailChargeTimer.SetValue(current, 0f); return false; }
            return original(current);
        }
        private bool NativeCanNailArt(On.HeroController.orig_CanNailArt original, HeroController current)
        {
            if (current == hero && (inputBlocked || !NativeControl || ShieldUsing || WantsShield || control.Owner != MovementOwner.Knight))
            { NailChargeTimer.SetValue(current, 0f); return false; }
            return original(current);
        }
        private void DoubleJump(On.HeroController.orig_DoDoubleJump original, HeroController current)
        {
            if (current == hero) control.ConsumeAirJump();
            original(current);
        }
        private void Bounce(On.HeroController.orig_Bounce original, HeroController current)
        {
            original(current);
            if (current == hero) control.Land();
        }
        private void BeginAttack(AttackDirection direction)
        {
            if (connected && minecraft != null && (minecraft.HeldFlags & Proto.HeldSword) != 0)
            {
                swingDamage = DamageRules.Enemy(minecraft.AttackDamage);
                // Native slash damage is cached before the bridge is ready after loading a room.
                // Refresh through its own FSM so native charm multipliers are still applied once.
                slashDamage.SendEvent("UPDATE NAIL DAMAGE");
            }
        }
        private int PlayerInt(string name, int value)
        {
            if (name != "nailDamage" || !connected || minecraft == null) return value;
            if (swingDamage > 0 && hero != null && hero.cState.attacking) return swingDamage;
            return (minecraft.HeldFlags & Proto.HeldSword) != 0 ? DamageRules.Enemy(minecraft.AttackDamage) : value;
        }

        public void Dispose()
        {
            RestoreGravity(); Release();
            On.HeroController.FixedUpdate -= FixedUpdate;
            On.HeroController.LookForInput -= LookForInput;
            On.HeroController.CanAttack -= NativeCanAttack;
            On.HeroController.CanNailCharge -= NativeCanNailCharge;
            On.HeroController.CanNailArt -= NativeCanNailArt;
            On.HeroController.DoDoubleJump -= DoubleJump;
            On.HeroController.Bounce -= Bounce;
            On.HeroController.AffectedByGravity -= NativeGravity;
            On.HeroController.TakeDamage -= ShieldDamage;
            pauseHook?.Dispose();
            Modding.ModHooks.GetPlayerIntHook -= PlayerInt;
            Modding.ModHooks.AttackHook -= BeginAttack;
        }
    }
}
