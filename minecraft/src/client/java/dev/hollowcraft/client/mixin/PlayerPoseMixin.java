package dev.hollowcraft.client.mixin;

import dev.hollowcraft.client.render.NativePose;
import net.minecraft.client.model.player.PlayerModel;
import net.minecraft.client.renderer.entity.state.AvatarRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(PlayerModel.class)
public abstract class PlayerPoseMixin {
    // LivingEntityRenderer calls setupAnim again for held items after submitting the body.
    @Inject(method="setupAnim(Lnet/minecraft/client/renderer/entity/state/AvatarRenderState;)V", at=@At("TAIL"))
    private void hollowcraftPose(AvatarRenderState state, CallbackInfo info) {
        if (NativePose.capturingAvatar) NativePose.apply((PlayerModel)(Object)this);
    }
}
