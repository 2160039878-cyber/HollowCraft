package dev.hollowcraft.client.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import dev.hollowcraft.client.HybridControl;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.MoverType;
import net.minecraft.world.phys.Vec3;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(LivingEntity.class)
public abstract class CalibratedMovementMixin {
    @Inject(method="jumpFromGround", at=@At("TAIL"))
    private void hollowcraft$groundJump(CallbackInfo callback) {
        if ((Object)this instanceof LocalPlayer player) HybridControl.groundJump(player);
    }

    @WrapOperation(method="handleRelativeFrictionAndCalculateMovement",
        at=@At(value="INVOKE", target="Lnet/minecraft/world/entity/LivingEntity;move(Lnet/minecraft/world/entity/MoverType;Lnet/minecraft/world/phys/Vec3;)V"))
    private void hollowcraft$move(LivingEntity entity, MoverType type, Vec3 movement, Operation<Void> original) {
        // The linked player's native-rate collision steps run on the client thread between ordinary item/world ticks.
        if (!(entity instanceof LocalPlayer player) || !HybridControl.calibrated(player)) original.call(entity, type, movement);
    }

    @Inject(method="travel", at=@At("TAIL"))
    private void hollowcraft$afterTravel(Vec3 input, CallbackInfo callback) {
        if ((Object)this instanceof LocalPlayer player) HybridControl.afterTravel(player);
    }
}
