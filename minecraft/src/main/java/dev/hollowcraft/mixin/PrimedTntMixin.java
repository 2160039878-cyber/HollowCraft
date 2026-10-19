package dev.hollowcraft.mixin;

import dev.hollowcraft.link.HostLink;
import dev.hollowcraft.world.HostCollision;
import net.minecraft.world.entity.item.PrimedTnt;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(PrimedTnt.class)
public abstract class PrimedTntMixin {
    @Unique private static final String HOLLOWCRAFT_ROOM_TAG = "hollowcraft_tnt_room:";
    @Unique private Integer hollowcraft$room;
    @Unique private double hollowcraft$plane;

    @Inject(method = "tick", at = @At("HEAD"), cancellable = true)
    private void hollowcraft$keepInRoom(CallbackInfo callback) {
        PrimedTnt tnt = (PrimedTnt)(Object)this;
        var state = new HostLink.HostState();
        boolean ready = HostLink.active() && HostLink.readSkyState(state) && state.inGame()
            && !state.loading() && !state.menuOpen() && HostCollision.matches(state.collisionEpoch);
        if (hollowcraft$room == null) {
            String saved = tnt.entityTags().stream().filter(t -> t.startsWith(HOLLOWCRAFT_ROOM_TAG)).findFirst().orElse(null);
            if (saved != null) {
                try {
                    String[] parts = saved.substring(HOLLOWCRAFT_ROOM_TAG.length()).split(":", 2);
                    int room = Integer.parseUnsignedInt(parts[0]);
                    double plane = Double.parseDouble(parts[1]);
                    if (room == 0 || !Double.isFinite(plane)) throw new IllegalArgumentException("Invalid TNT room");
                    hollowcraft$room = room; hollowcraft$plane = plane;
                } catch (IllegalArgumentException | IndexOutOfBoundsException invalid) {
                    callback.cancel(); return;
                }
            } else {
                if (!ready || state.worldId == 0 || !Double.isFinite(state.z)
                    || Math.abs(tnt.getX() - state.x) > 256 || Math.abs(tnt.getZ() - state.z) > 8) return;
                hollowcraft$room = state.worldId; hollowcraft$plane = state.z;
                tnt.addTag(HOLLOWCRAFT_ROOM_TAG + Integer.toUnsignedString(state.worldId) + ":" + Double.toHexString(state.z));
            }
        }
        // Keep the native fuse and XY motion, but do not simulate a room whose HK geometry is unloaded.
        if (!ready || state.worldId != hollowcraft$room) { callback.cancel(); return; }
        hollowcraft$flatten(tnt);
    }

    @Inject(method = "tick", at = @At("RETURN"))
    private void hollowcraft$keepOnPlane(CallbackInfo callback) {
        if (hollowcraft$room != null) hollowcraft$flatten((PrimedTnt)(Object)this);
    }

    @Unique private void hollowcraft$flatten(PrimedTnt tnt) {
        tnt.setPos(tnt.getX(), tnt.getY(), hollowcraft$plane);
        var velocity = tnt.getDeltaMovement();
        tnt.setDeltaMovement(velocity.x, velocity.y, 0);
    }
}
