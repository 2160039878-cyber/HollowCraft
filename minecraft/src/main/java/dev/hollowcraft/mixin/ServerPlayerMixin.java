package dev.hollowcraft.mixin;

import dev.hollowcraft.HollowCraft;
import dev.hollowcraft.combat.HostCombat;
import dev.hollowcraft.combat.HostActorEntity;
import dev.hollowcraft.link.Proto;
import dev.hollowcraft.link.HostLink;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.server.level.ServerPlayer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ServerPlayer.class)
public abstract class ServerPlayerMixin {
	/** Critical hits on a REPO actor are flagged so REPO can play them up. */
	@Inject(method = "crit", at = @At("HEAD"))
	private void hollowcraft$critHost(Entity entity, CallbackInfo ci) {
		if (entity instanceof HostActorEntity proxy) {
			proxy.markCritical();
		}
	}

	/** Dying in Minecraft is dying in REPO: the host's through the link, a guest's through theirs. */
	@Inject(method = "die", at = @At("HEAD"), cancellable = true)
	private void hollowcraft$diesInHost(DamageSource source, CallbackInfo ci) {
		ServerPlayer self = (ServerPlayer) (Object) this;
		if (HostLink.active()) {
			self.setHealth(1.0F);
			ci.cancel();
			return;
		}
		int attacker = HostCombat.attackerFormId(source);
		if (!dev.hollowcraft.net.RepoNet.isHost(self)) {
			if (net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.canSend(self, dev.hollowcraft.net.RepoNet.Died.TYPE)) {
				net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking.send(self, new dev.hollowcraft.net.RepoNet.Died(attacker));
			}
			HollowCraft.LOG.info("HollowCraft: guest {} died ({}); telling their REPO", self.getPlainTextName(), source.getMsgId());
			return;
		}
		if (HostLink.active()) {
			HostLink.pushEvent(Proto.EV_PLAYER_DIED, attacker, 0, 0, 0, 0, 0);
			HollowCraft.LOG.info("HollowCraft: player died ({}); telling REPO", source.getMsgId());
		}
	}
}
