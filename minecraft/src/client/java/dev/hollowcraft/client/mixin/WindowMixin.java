package dev.hollowcraft.client.mixin;

import com.mojang.blaze3d.platform.Window;
import dev.hollowcraft.client.HostClient;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyArg;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import org.lwjgl.sdl.SDLVideo;

/** The MC window is hidden while linked; REPO has the real focus, so pretend we do too. */
@Mixin(Window.class)
public abstract class WindowMixin {
	@ModifyArg(method = "createWindow", at = @At(value = "INVOKE",
		target = "Lcom/mojang/renderpearl/api/device/GpuBackend;createWindow(Ljava/lang/String;IIJ)J"), index = 3)
	private long hollowcraft$initiallyHidden(long flags) {
		return Boolean.getBoolean("hollowcraft.startHidden") && !Boolean.getBoolean("hollowcraft.showWindow")
			? flags | SDLVideo.SDL_WINDOW_HIDDEN : flags;
	}

	@Inject(method = "isFocused", at = @At("HEAD"), cancellable = true)
	private void hollowcraft$focused(CallbackInfoReturnable<Boolean> cir) {
		if (HostClient.tookOver()) {
			// Focused while REPO is connected; if REPO goes away, act unfocused so MC
			// never tries to grab the (hidden) mouse.
			cir.setReturnValue(HostClient.linked());
		}
	}

	@Inject(method = "isIconified", at = @At("HEAD"), cancellable = true)
	private void hollowcraft$notIconified(CallbackInfoReturnable<Boolean> cir) {
		if (HostClient.linked()) {
			cir.setReturnValue(false);
		}
	}
}
