package dev.hollowcraft.client.render;

import com.google.gson.Gson;
import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;
import dev.hollowcraft.HollowCraft;
import dev.hollowcraft.client.HostClient;
import dev.hollowcraft.link.HostLink;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.model.player.PlayerModel;
import net.minecraft.client.renderer.entity.state.ArmedEntityRenderState;
import net.minecraft.client.renderer.entity.state.EntityRenderState;
import net.minecraft.client.renderer.entity.state.LivingEntityRenderState;

/** One curve set is also consumed by the Blender rig and the local Unity replicas. */
public final class NativePose {
    public static boolean capturingAvatar;
    private static final class Motion {
        boolean hideHeld;
        Map<String, float[][]> tracks;
    }
    private static final class Definitions {
        int schema;
        Map<String, Motion> poses;
        Map<String, String> aliases;
    }
    private static final Definitions DATA = load();
    private static final Set<String> UNMAPPED = new HashSet<>();
    private NativePose() { }

    private static Definitions load() {
        var stream = NativePose.class.getResourceAsStream("/assets/hollowcraft/steve/poses.json");
        if (stream == null) throw new IllegalStateException("Steve motion curves are missing");
        try (var reader = new InputStreamReader(stream, StandardCharsets.UTF_8)) {
            var data = new Gson().fromJson(reader, Definitions.class);
            if (data.schema != 1 || data.poses == null || data.aliases == null || !data.poses.containsKey("idle"))
                throw new IllegalStateException("Invalid Steve motion curves");
            for (var motion : data.poses.values()) for (var curve : motion.tracks.values()) {
                if (curve.length < 2 || curve[0][0] != 0 || curve[curve.length-1][0] != 1)
                    throw new IllegalStateException("Invalid motion endpoints");
                float previous = -1;
                for (var key : curve) {
                    if (key.length != 2 || !Float.isFinite(key[0]) || !Float.isFinite(key[1]) || key[0] <= previous)
                        throw new IllegalStateException("Invalid motion keyframe");
                    previous = key[0];
                }
            }
            return data;
        } catch (java.io.IOException e) { throw new IllegalStateException("Cannot read Steve motion curves", e); }
    }
    private static Motion motion(HostLink.HostState host) {
        String name = DATA.aliases.get(host.animationName);
        if (name == null) {
            if (!host.animationName.isEmpty() && UNMAPPED.add(host.animationName))
                HollowCraft.LOG.warn("HollowCraft: no body motion mapped for native clip {}", host.animationName);
            name = "idle";
        }
        return DATA.poses.get(name);
    }
    private static float phase(HostLink.HostState host) {
        if (!Float.isFinite(host.animationTime) || !Float.isFinite(host.animationDuration) || host.animationDuration <= 0) return 0;
        float t = Math.max(0, host.animationTime / host.animationDuration);
        return host.animationLoop != 0 ? t - (float)Math.floor(t) : Math.min(1, t);
    }
    static float sample(float[][] curve, float t) {
        if (t <= curve[0][0]) return curve[0][1];
        for (int i=1; i<curve.length; i++) {
            if (t <= curve[i][0]) {
                float u = (t-curve[i-1][0]) / (curve[i][0]-curve[i-1][0]);
                return curve[i-1][1] + (curve[i][1]-curve[i-1][1]) * u*u*(3-2*u);
            }
        }
        return curve[curve.length-1][1];
    }
    private static float value(Motion motion, String channel, float t, float fallback) {
        float[][] curve = motion.tracks.get(channel);
        return curve == null ? fallback : sample(curve, t);
    }
    public static void root(PoseStack stack, EntityRenderState state) {
        // The vanilla 32-pixel model is 1.875 blocks after the player renderer's scale; match the 1.8-block body.
        var host = HostClient.sky();
        if (state instanceof LivingEntityRenderState living) {
            // Render a three-quarter profile so flat held-item models remain visible from the side camera.
            living.bodyRot = host.yaw < 0 ? -65 : 65;
            living.yRot = 0;
            if (host.nativeControl()) living.xRot = 0;
        }
        if (!host.nativeControl()) { stack.scale(.96f,.96f,.96f); return; }
        Motion motion = motion(host);
        float t = phase(host), facing = host.yaw < 0 ? 1 : -1;
        stack.translate(0, value(motion,"root.dy",t,0), 0);
        stack.translate(0,.9,0);
        stack.rotateDegrees(Axis.ZP, value(motion,"root.roll",t,0) * facing);
        stack.rotateDegrees(Axis.YP, value(motion,"root.yaw",t,0)+value(motion,"root.yawSide",t,0)*facing);
        stack.scale(1, value(motion,"root.sy",t,1), 1);
        stack.translate(0,-.9,0);
        stack.scale(.96f,.96f,.96f);
        if (motion.hideHeld && state instanceof ArmedEntityRenderState armed) {
            armed.rightHandItemState.clear(); armed.leftHandItemState.clear();
        }
    }
    public static void apply(PlayerModel model) {
        var host = HostClient.sky();
        if (!host.nativeControl()) return;
        Motion motion = motion(host);
        float t = phase(host);
        var player = net.minecraft.client.Minecraft.getInstance().player;
        boolean shield = player != null && player.isUsingItem() && player.getUseItem().is(net.minecraft.world.item.Items.SHIELD);
        float shieldX = model.leftArm.xRot, shieldY = model.leftArm.yRot, shieldZ = model.leftArm.zRot;
        model.root().resetPose();
        part(model.head, "head", motion, t); part(model.body, "body", motion, t);
        part(model.rightArm, "right_arm", motion, t); part(model.leftArm, "left_arm", motion, t);
        part(model.rightLeg, "right_leg", motion, t); part(model.leftLeg, "left_leg", motion, t);
        // Keep the raised face readable from the fixed side-view camera.
        if (shield) { model.leftArm.xRot = shieldX; model.leftArm.yRot = shieldY + .65f; model.leftArm.zRot = shieldZ; }
    }
    private static void part(ModelPart part, String name, Motion motion, float t) {
        part.resetPose();
        part.xRot = (float)Math.toRadians(value(motion, name+".rx",t,0));
        part.yRot = (float)Math.toRadians(value(motion, name+".ry",t,0));
        part.zRot = (float)Math.toRadians(value(motion, name+".rz",t,0));
    }
}
