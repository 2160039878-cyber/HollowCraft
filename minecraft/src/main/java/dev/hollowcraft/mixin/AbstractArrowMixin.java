package dev.hollowcraft.mixin;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import dev.hollowcraft.combat.HostActorEntity;
import dev.hollowcraft.link.Proto;
import dev.hollowcraft.link.HostLink;
import dev.hollowcraft.world.HostClip;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.projectile.arrow.AbstractArrow;
import net.minecraft.world.entity.projectile.arrow.Arrow;
import net.minecraft.world.entity.projectile.arrow.SpectralArrow;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.Vec3;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.BlockHitResult;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/**
 * Arrows and tridents hit REPO's exact surfaces. They then stick where they hit: the block state
 * there is air, the same as what they recorded on impact, so vanilla never makes them fall out.
 */
@Mixin(AbstractArrow.class)
public abstract class AbstractArrowMixin {
	@Unique private HostLink.Scope hollowcraft$flightScope;
	@Unique private double hollowcraft$flightPlane;

	@Inject(method = "tick", at = @At("HEAD"), cancellable = true)
	private void hollowcraft$sideViewArrow(CallbackInfo callback) {
		AbstractArrow arrow = (AbstractArrow)(Object)this;
		if (hollowcraft$flightScope == null) {
			if (!HostLink.active() || !(arrow.getOwner() instanceof net.minecraft.world.entity.player.Player)) return;
			var state = new HostLink.HostState();
			if (!HostLink.readSkyState(state) || !state.inGame() || state.loading() || !Double.isFinite(state.z)) return;
			String stamp="hollowcraft_arrow_"+Long.toUnsignedString(state.session,16)+"_"+state.worldId+"_"+state.collisionEpoch;
			if (arrow.entityTags().stream().anyMatch(tag -> tag.startsWith("hollowcraft_arrow_") && !tag.equals(stamp))) {
				arrow.discard(); callback.cancel(); return;
			}
			arrow.addTag(stamp);
			hollowcraft$flightScope = state.scope(); hollowcraft$flightPlane = state.z;
		}
		if (!HostLink.active() || !hollowcraft$flightScope.equals(HostLink.captureScope())) {
			arrow.discard(); callback.cancel(); return;
		}
		// Vanilla bow spread has a depth component. Keep the real projectile on the shared side-view combat plane.
		arrow.setPos(arrow.getX(), arrow.getY(), hollowcraft$flightPlane);
		Vec3 velocity = arrow.getDeltaMovement();
		arrow.setDeltaMovement(velocity.x, velocity.y, 0);
	}

	@WrapOperation(
		method = "tick",
		at = @At(value = "INVOKE", target = "Lnet/minecraft/world/level/Level;clipIncludingBorder(Lnet/minecraft/world/level/ClipContext;)Lnet/minecraft/world/phys/BlockHitResult;")
	)
	private BlockHitResult hollowcraft$hitHost(Level level, ClipContext context, Operation<BlockHitResult> original) {
		return HostClip.refine(context.getFrom(), context.getTo(), original.call(level, context), HostClip.Use.PROJECTILE);
	}

	@Unique
	private Vec3 hollowcraft$hitAt;

	@Inject(method = "onHitEntity", at = @At("HEAD"))
	private void hollowcraft$rememberHit(EntityHitResult hitResult, CallbackInfo ci) {
		this.hollowcraft$hitAt = hitResult.getLocation();
	}

	/**
	 * Where Minecraft counts an arrow as stuck in a creature (it hurt it and didn't pierce): if that
	 * creature is a REPO NPC's stand-in, REPO pins the arrow to the NPC's skeleton.
	 */
	@WrapOperation(method = "onHitEntity", at = @At(value = "INVOKE", target = "Lnet/minecraft/world/entity/LivingEntity;setArrowCount(I)V"))
	private void hollowcraft$stickInHostActor(LivingEntity mob, int count, Operation<Void> original) {
		original.call(mob, count);
		if (!(mob instanceof HostActorEntity actor) || this.hollowcraft$hitAt == null || !HostLink.active()) {
			return;
		}
		AbstractArrow self = (AbstractArrow) (Object) this;
		Vec3 v = self.getDeltaMovement();
		float yaw = (float) (Mth.atan2(v.x, v.z) * Mth.RAD_TO_DEG);
		float pitch = (float) (Mth.atan2(v.y, v.horizontalDistance()) * Mth.RAD_TO_DEG);
		int texture = self instanceof SpectralArrow ? 2 : self instanceof Arrow tippable && tippable.getColor() > 0 ? 1 : 0;
		Vec3 at = this.hollowcraft$hitAt;
		HostLink.pushEvent(actor.scope, Proto.EV_ARROW_STUCK, actor.formId(), (float) at.x, (float) at.y, (float) at.z, yaw, Float.floatToRawIntBits(pitch), texture);
	}
}
