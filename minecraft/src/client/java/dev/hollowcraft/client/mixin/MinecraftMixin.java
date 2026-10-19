package dev.hollowcraft.client.mixin;

import dev.hollowcraft.client.HostClient;
import com.llamalad7.mixinextras.injector.ModifyExpressionValue;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import org.objectweb.asm.Opcodes;

@Mixin(Minecraft.class)
public abstract class MinecraftMixin {
	@ModifyExpressionValue(method="startUseItem",at=@At(value="FIELD",target="Lnet/minecraft/client/Minecraft;hitResult:Lnet/minecraft/world/phys/HitResult;",opcode=Opcodes.GETFIELD))
	private net.minecraft.world.phys.HitResult hollowcraft$rangedAttack(net.minecraft.world.phys.HitResult hit) {
		Minecraft mc=(Minecraft)(Object)this;
		if(!HostClient.linked() || mc.player==null || !dev.hollowcraft.client.InputBridge.rangedAttack()) return hit;
		var item=mc.player.getMainHandItem().getItem();
		if(!(item instanceof net.minecraft.world.item.BowItem || item instanceof net.minecraft.world.item.CrossbowItem)) return hit;
		// The host attack key draws/fires the weapon; block interaction remains on the use key.
		return net.minecraft.world.phys.BlockHitResult.miss(mc.player.getEyePosition(),net.minecraft.core.Direction.UP,mc.player.blockPosition());
	}
	@Inject(method = "handleKeybinds", at = @At(value = "NEW", target = "net/minecraft/client/gui/screens/inventory/InventoryScreen"))
	private void hollowcraft$inventoryOpening(CallbackInfo callback) {
		// The first screen construction can load classes before Gui.setScreen is entered.
		HostClient.screenOpening();
	}

	@Inject(method = "isPaused", at = @At("HEAD"), cancellable = true)
	private void hollowcraft$pauseBoth(CallbackInfoReturnable<Boolean> callback) {
		if (HostClient.shouldPause()) callback.setReturnValue(true);
	}
	@ModifyExpressionValue(method="runTick", at=@At(value="INVOKE", target="Lnet/minecraft/client/gui/Gui;isPausing()Z"))
	private boolean hollowcraft$pauseTimer(boolean original) {
		return original || HostClient.shouldPause();
	}
	@ModifyExpressionValue(method="tick", at=@At(value="FIELD", target="Lnet/minecraft/client/Minecraft;pause:Z", opcode=Opcodes.GETFIELD))
	private boolean hollowcraft$pauseCurrentTick(boolean original) {
		return original || HostClient.shouldPause();
	}
	@Inject(method = "runTick", at = @At("HEAD"))
	private void hollowcraft$beginFrame(boolean advanceGameTime, CallbackInfo ci) {
		HostClient.beginFrame();
	}

	@Inject(
		method = "renderFrame",
		at = @At(value = "INVOKE", target = "Lnet/minecraft/client/renderer/GameRenderer;render()V", shift = At.Shift.AFTER)
	)
	private void hollowcraft$afterRender(boolean advanceGameTime, CallbackInfo ci) {
		HostClient.afterRender();
	}

	@Inject(method = "renderFrame", at = @At("TAIL"))
	private void hollowcraft$pace(boolean advanceGameTime, CallbackInfo ci) {
		HostClient.paceFrame();
	}
}
