package dev.hollowcraft.client.mixin;

import dev.hollowcraft.client.HostClient;
import net.minecraft.client.gui.Gui;
import net.minecraft.client.gui.screens.Screen;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Report a modal screen before its first layout/render can delay the physics acknowledgement. */
@Mixin(Gui.class)
public abstract class ScreenMixin {
	@Inject(method = "setScreen(Lnet/minecraft/client/gui/screens/Screen;)V", at = @At("HEAD"))
	private void hollowcraft$screenOpening(Screen screen, CallbackInfo callback) {
		if (screen != null) HostClient.screenOpening(screen);
	}
}
