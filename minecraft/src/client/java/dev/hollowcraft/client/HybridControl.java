package dev.hollowcraft.client;

import dev.hollowcraft.link.HostLink;
import dev.hollowcraft.HollowCraft;
import dev.hollowcraft.link.Proto;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import dev.hollowcraft.world.CalibratedMotion;
import net.minecraft.world.entity.MoverType;
import net.minecraft.world.phys.Vec3;

/** Transfers one player's physical state; it never resets the shared air-jump budget. */
public final class HybridControl {
    private static int controlSeq = -1;
    private static int jumpSeq;
    private static boolean nativeControl;
    private static final CalibratedMotion motion = new CalibratedMotion();
    private static int motionPressSeq = -1;
    private static int motionTick, motionPressTick, pendingAirTick, pendingAirPress;
    private static int appliedPhysicsTick;
    private static boolean pendingAir;
    private static final boolean TEST = Boolean.getBoolean("hollowcraft.testMode");
    private static int loggedRelease = -1;
    private static long profileWarningAt;
    private HybridControl() { }

    public static int acknowledgedControl() { return controlSeq; }
    public static int acknowledgedPhysics() { return appliedPhysicsTick; }
    public static void reset() { controlSeq = -1; jumpSeq = HostClient.sky().jumpSeq; }

    public static boolean calibrated(LocalPlayer player) {
        var state = HostClient.sky();
        return HostClient.linked() && !state.nativeControl() && state.inGame() && !state.loading() && !state.menuOpen()
            && Minecraft.getInstance().gui.screen() == null && !player.isInWater() && !player.isInLava()
            && !player.onClimbable() && !player.isFallFlying() && !player.getAbilities().flying && !player.isPassenger()
            && Double.isFinite(state.runSpeed) && state.runSpeed >= 0 && state.runSpeed <= 1000
            && Float.isFinite(state.moveX) && Float.isFinite(state.jumpHeldSeconds) && state.jumpHeldSeconds >= 0 && state.jumpHeldSeconds <= 3600
            && Double.isFinite(state.jumpVelocity) && state.jumpVelocity > 0 && state.jumpVelocity <= 1000
            && Double.isFinite(state.gravity) && state.gravity > 0 && state.gravity <= 2000
            && Double.isFinite(state.maxFall) && state.maxFall > 0 && state.maxFall <= 1000
            && Float.isFinite(state.fixedStep) && state.fixedStep >= .005f && state.fixedStep <= .05f
            && Float.isFinite(state.jumpHold) && state.jumpHold >= 0 && state.jumpHold <= 2
            && Float.isFinite(state.jumpMin) && state.jumpMin >= 0 && state.jumpMin <= state.jumpHold
            && Float.isFinite(state.doubleHold) && state.doubleHold >= 0 && state.doubleHold <= 2
            && Float.isFinite(state.doubleDelay) && state.doubleDelay >= 0 && state.doubleDelay <= 1;
    }

    public static void groundJump(LocalPlayer player) {
        if (!calibrated(player)) return;
        var state = HostClient.sky();
        motionPressTick = motionPressSeq == state.jumpPressSeq ? state.physicsTick : state.jumpPressTick;
        motionPressSeq = state.jumpPressSeq;
        motionTick = motionPressTick;
        pendingAir = false;
        motion.jump(false);
        player.setOnGround(false);
        if (TEST) HollowCraft.LOG.info("HollowCraft motion ground: press={}, tick={}, observed={}, y={}",
            motionPressSeq, motionPressTick, state.physicsTick, player.getY());
        player.setDeltaMovement(player.getDeltaMovement().x, state.jumpVelocity / 20, 0);
    }

    private static void release(HostLink.HostState state) {
        if ((state.flags & Proto.SKY_JUMP_HELD) != 0 || state.jumpPressSeq != motionPressSeq) return;
        double duration = Math.max(0, state.jumpReleaseTick - motionPressTick) * (double)state.fixedStep;
        if (TEST && loggedRelease != motionPressSeq) {
            loggedRelease = motionPressSeq;
            HollowCraft.LOG.info("HollowCraft motion release: press={}, duration={}, integrated={}",
                motionPressSeq, duration, motion.elapsedSeconds());
        }
        motion.release(duration);
    }

    public static Vec3 position(LocalPlayer player, float partial) {
        // A menu freezes the physical pose; switching back to interpolation would report an earlier airborne position.
        return calibrated(player) || HostClient.shouldPause() ? player.position() : player.getPosition(partial);
    }

    public static int motionState(LocalPlayer player) {
        return calibrated(player) ? motion.snapshot() : 0;
    }

    public static double velocityY(LocalPlayer player) {
        return calibrated(player) ? motion.velocityY() : player.getDeltaMovement().y * 20;
    }

    private static void movement(LocalPlayer player) {
        var state = HostClient.sky();
        // Never simulate beyond an observed host physics boundary: a later release cannot undo predicted ascent.
        long ticks = Integer.toUnsignedLong(state.physicsTick - motionTick);
        if (ticks > 50) {
            motionTick = state.physicsTick; pendingAir = false;
            motion.restore(player.getDeltaMovement().y * 20, 0);
            return;
        }
        while (motionTick != state.physicsTick) {
            if (pendingAir && motionTick - pendingAirTick >= 0) {
                motionPressTick = pendingAirTick; motionPressSeq = pendingAirPress; pendingAir = false;
                motion.jump(true);
            }
            release(state);
            double y = motion.advance(state.fixedStep, state.fixedStep, state.gravity, state.maxFall, true);
            player.move(MoverType.SELF, new Vec3(Math.clamp(state.moveX, -1, 1) * state.runSpeed * state.fixedStep, y, 0));
            motion.collide(player.onGround(), player.verticalCollision && !player.onGround());
            motionTick++;
        }
        appliedPhysicsTick = motionTick;
    }

    public static void afterTravel(LocalPlayer player) {
        if (!calibrated(player)) return;
        if (player.onGround()) pendingAir = false;
        var state = HostClient.sky();
        // Vanilla collision/block callbacks have run; do not apply its second gravity/drag curve to the calibrated jump.
        player.setDeltaMovement(player.horizontalCollision ? 0 : Math.clamp(state.moveX, -1, 1) * state.runSpeed / 20,
            motion.velocityY() / 20, 0);
        player.resetFallDistance();
    }

    public static float heldAttackDamage(LocalPlayer player, net.minecraft.world.item.ItemStack stack) {
        double[] values = {player.getAttributeBaseValue(net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_DAMAGE), 0, 1};
        java.util.function.BiConsumer<net.minecraft.core.Holder<net.minecraft.world.entity.ai.attributes.Attribute>,
            net.minecraft.world.entity.ai.attributes.AttributeModifier> accumulate = (attribute, modifier) -> {
            if (!attribute.equals(net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_DAMAGE)) return;
            switch (modifier.operation()) {
                case ADD_VALUE -> values[0] += modifier.amount();
                case ADD_MULTIPLIED_BASE -> values[1] += modifier.amount();
                case ADD_MULTIPLIED_TOTAL -> values[2] *= 1 + modifier.amount();
            }
        };
        stack.forEachModifier(net.minecraft.world.entity.EquipmentSlot.MAINHAND, accumulate);
        for(var effect : player.getActiveEffects())
            effect.getEffect().value().createModifiers(effect.getAmplifier(), accumulate);
        return (float)Math.clamp(values[0] * (1 + values[1]) * values[2], 0, 1000);
    }

    public static void frame(Minecraft minecraft, HostLink.HostState state) {
        var player = minecraft.player;
        if (player == null || !state.inGame() || state.loading()) return;
        if (!Double.isFinite(state.x) || !Double.isFinite(state.y) || !Double.isFinite(state.z)
            || !Double.isFinite(state.velocityX) || !Double.isFinite(state.velocityY)
            || (state.motionState & ~CalibratedMotion.STATE_MASK) != 0) return;
        boolean profile = calibrated(player);
        if (TEST && !profile && !state.nativeControl() && !state.menuOpen() && System.currentTimeMillis() >= profileWarningAt) {
            profileWarningAt = System.currentTimeMillis() + 1000;
            HollowCraft.LOG.warn("HollowCraft calibration blocked: water={} lava={} climb={} fallFlying={} flying={} passenger={} screen={} tick={}/{} fixed={} jump={} min={} hold={} gravity={} fall={}",
                player.isInWater(), player.isInLava(), player.onClimbable(), player.isFallFlying(), player.getAbilities().flying, player.isPassenger(),
                minecraft.gui.screen() == null ? "none" : minecraft.gui.screen().getClass().getSimpleName(), state.physicsTick, appliedPhysicsTick,
                state.fixedStep, state.jumpVelocity, state.jumpMin, state.jumpHold, state.gravity, state.maxFall);
        }
        if (profile) motion.profile(state.jumpVelocity, state.jumpHold, state.jumpMin, state.doubleHold, state.doubleDelay);
        boolean changed = controlSeq != state.controlSeq || nativeControl != state.nativeControl();
        if (changed || state.nativeControl()) {
            player.setPos(state.x, state.y, state.z);
            player.xo = state.x; player.yo = state.y; player.zo = state.z;
            player.setDeltaMovement(state.velocityX / 20, state.velocityY / 20, 0);
            player.setOnGround((state.flags & Proto.SKY_ON_GROUND) != 0);
            appliedPhysicsTick = state.physicsTick;
            if (changed) player.resetFallDistance();
            if (changed) {
                motionPressSeq = state.jumpPressSeq; motionPressTick = motionTick = state.physicsTick; pendingAir = false;
                motion.restore(state.velocityY, state.motionState);
            }
        } else {
            player.setPos(player.getX(), player.getY(), state.z);
            Vec3 velocity = player.getDeltaMovement();
            player.setDeltaMovement(velocity.x, velocity.y, 0);
        }
        player.setNoGravity(state.nativeControl());
        if (calibrated(player)) release(state);
        if (state.jumpSeq != jumpSeq) {
            jumpSeq = state.jumpSeq;
            if (!state.nativeControl() && state.airJumpUsed != 0
                && (state.flags & Proto.SKY_CAN_DOUBLE_JUMP) != 0 && Double.isFinite(state.jumpVelocity)) {
                if (calibrated(player)) {
                    pendingAirTick = state.jumpPressTick; pendingAirPress = state.jumpPressSeq; pendingAir = true;
                }
                else {
                    Vec3 velocity = player.getDeltaMovement();
                    player.setDeltaMovement(velocity.x, Math.clamp(state.jumpVelocity / 20, 0.1, 3.0), 0);
                }
                player.resetFallDistance();
            }
        }
        if (profile && (state.flags & Proto.SKY_JUMP_HELD) != 0 && state.jumpPressSeq != motionPressSeq && player.onGround())
            player.jumpFromGround();
        nativeControl = state.nativeControl();
        controlSeq = state.controlSeq;
        if (profile) { movement(player); afterTravel(player); }
        else { motionTick = state.physicsTick; pendingAir = false; }
    }
}
