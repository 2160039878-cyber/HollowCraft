package dev.hollowcraft.client.mixin;

import dev.hollowcraft.client.HostClient;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.AbstractClientPlayer;
import net.minecraft.core.ClientAsset;
import net.minecraft.resources.Identifier;
import net.minecraft.world.entity.player.PlayerModelType;
import net.minecraft.world.entity.player.PlayerSkin;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(AbstractClientPlayer.class)
public abstract class SteveSkinMixin {
    private static final PlayerSkin HOLLOWCRAFT_STEVE = new PlayerSkin(
        new ClientAsset.ResourceTexture(Identifier.withDefaultNamespace("entity/player/wide/steve")),
        null, null, PlayerModelType.WIDE, true);

    @Inject(method = "getSkin", at = @At("HEAD"), cancellable = true)
    private void hollowcraft$steve(CallbackInfoReturnable<PlayerSkin> callback) {
        if ((Object)this == Minecraft.getInstance().player && HostClient.tookOver())
            callback.setReturnValue(HOLLOWCRAFT_STEVE);
    }
}
