package dev.hollowcraft.mixin;

import dev.hollowcraft.link.HostLink;
import dev.hollowcraft.link.Proto;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.entity.LivingEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(LivingEntity.class)
public abstract class PlayerHealthMixin {
    @Inject(method = "hurtServer", at = @At("HEAD"), cancellable = true)
    private void hollowcraft$skipMirroredDamage(ServerLevel level, DamageSource source, float amount, CallbackInfoReturnable<Boolean> callback) {
        if ((Object)this instanceof ServerPlayer && HostLink.active()
            && (source.is(net.minecraft.world.damagesource.DamageTypes.FALL)
                || source.is(net.minecraft.tags.DamageTypeTags.IS_EXPLOSION))) {
            // HK has no ordinary fall damage and owns blast damage. Cancel before vanilla broadcasts hurt/knockback.
            callback.setReturnValue(false);
        }
    }

    @Inject(method = "actuallyHurt", at = @At("HEAD"), cancellable = true)
    private void hollowcraft$authoritativeHealth(ServerLevel level, DamageSource source, float amount, CallbackInfo callback) {
        if (!((Object)this instanceof ServerPlayer) || !HostLink.active()) return;
        callback.cancel();
        if (source.is(net.minecraft.tags.DamageTypeTags.IS_EXPLOSION)) return;
        HostLink.HostState state = new HostLink.HostState();
        if (!HostLink.readSkyState(state) || state.menuOpen() || state.loading()) return;
        if (source.is(net.minecraft.world.damagesource.DamageTypes.FALL)) return;
        if (Float.isFinite(amount) && amount > 0)
            HostLink.pushEvent(state.scope(), Proto.EV_PLAYER_HURT, 0, amount, 0, 0, 0, 0, 0);
    }
}
