package dev.hollowcraft.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import dev.hollowcraft.link.Proto;
import dev.hollowcraft.link.HostLink;
import dev.hollowcraft.world.HostDigBlast;
import java.util.List;
import java.util.Optional;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.Explosion;
import net.minecraft.world.level.ExplosionDamageCalculator;
import net.minecraft.world.level.ServerExplosion;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.FluidState;
import org.jspecify.annotations.Nullable;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyVariable;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Minecraft explosions in REPO's world: they blow REPO's ground and rock apart like blocks
 * (HostDigBlast), and REPO feels them (loose objects are thrown and people knocked away).
 */
@Mixin(ServerExplosion.class)
public abstract class ServerExplosionMixin {
	@Unique
	private @Nullable HostDigBlast hollowcraft$blast;
	@Unique private HostLink.Scope hollowcraft$scope;

	@Inject(method = "explode", at = @At("HEAD"))
	private void hollowcraft$begin(CallbackInfoReturnable<Integer> cir) {
		hollowcraft$scope = HostLink.captureScope();
		var self = (ServerExplosion)(Object)this;
		var state = new HostLink.HostState();
		if (!HostLink.readSkyState(state) || !state.scope().equals(hollowcraft$scope)
			|| Math.abs(self.center().x - state.x) > 256 || Math.abs(self.center().z - state.z) > 8
			|| !dev.hollowcraft.world.HostCollision.matches(state.collisionEpoch)) hollowcraft$scope = null;
		this.hollowcraft$blast = hollowcraft$scope == null ? null : HostDigBlast.begin((ServerExplosion) (Object) this);
	}

	@WrapOperation(
		method = "calculateExplodedPositions",
		at = @At(
			value = "INVOKE",
			target = "Lnet/minecraft/world/level/ExplosionDamageCalculator;getBlockExplosionResistance(Lnet/minecraft/world/level/Explosion;Lnet/minecraft/world/level/BlockGetter;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/material/FluidState;)Ljava/util/Optional;"
		)
	)
	private Optional<Float> hollowcraft$hostResists(
		ExplosionDamageCalculator calculator, Explosion explosion, BlockGetter level, BlockPos pos, BlockState block, FluidState fluid, Operation<Optional<Float>> original
	) {
		Optional<Float> vanilla = original.call(calculator, explosion, level, pos, block, fluid);
		return this.hollowcraft$blast != null ? this.hollowcraft$blast.resistance(pos, vanilla) : vanilla;
	}

	@ModifyVariable(method = "explode", at = @At("STORE"), ordinal = 0)
	private List<BlockPos> hollowcraft$hostBreaks(List<BlockPos> targets) {
		if (this.hollowcraft$blast != null) {
			ServerExplosion self = (ServerExplosion) (Object) this;
			this.hollowcraft$blast.materialize(targets, self.getBlockInteraction() != Explosion.BlockInteraction.KEEP
				&& self.getBlockInteraction() != Explosion.BlockInteraction.TRIGGER_BLOCK);
		}
		return targets;
	}

	@Inject(method = "explode", at = @At("RETURN"))
	private void hollowcraft$tellHost(CallbackInfoReturnable<Integer> cir) {
		if (this.hollowcraft$blast != null) {
			this.hollowcraft$blast = null;
		}
		if (!HostLink.active()) {
			return;
		}
		ServerExplosion self = (ServerExplosion) (Object) this;
		var center = self.center();
		dev.hollowcraft.RedstoneProbe.exploded(center.x, center.y, center.z, self.radius());
		HostLink.pushEvent(hollowcraft$scope, Proto.EV_EXPLOSION, 0, (float) center.x, (float) center.y, (float) center.z, self.radius(), 0, 0);
	}
}
