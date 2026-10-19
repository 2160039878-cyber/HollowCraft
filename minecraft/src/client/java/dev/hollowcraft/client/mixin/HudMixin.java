package dev.hollowcraft.client.mixin;

import dev.hollowcraft.client.HostClient;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.Hud;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(Hud.class)
public abstract class HudMixin {
    @Shadow private void extractItemHotbar(GuiGraphicsExtractor graphics, DeltaTracker delta) { }

    @Inject(method = "extractHotbarAndDecorations", at = @At("HEAD"), cancellable = true)
    private void hollowcraft$hotbar(GuiGraphicsExtractor graphics, DeltaTracker delta, CallbackInfo callback) {
        if (!HostClient.linked()) return;
        // Health, armour, healing and the resource meter are owned by Hollow Knight.
        extractItemHotbar(graphics, delta);
        callback.cancel();
    }

    @Inject(method = "extractCrosshair", at = @At("HEAD"), cancellable = true)
    private void hollowcraft$crosshair(GuiGraphicsExtractor graphics, DeltaTracker delta, CallbackInfo callback) {
        if (HostClient.linked()) callback.cancel();
    }
}
