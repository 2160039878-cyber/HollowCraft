package dev.hollowcraft.combat;

import dev.hollowcraft.link.Proto;
import java.util.ArrayDeque;
import net.minecraft.network.syncher.EntityDataAccessor;
import net.minecraft.network.syncher.EntityDataSerializers;
import net.minecraft.network.syncher.SynchedEntityData;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityDimensions;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.HumanoidArm;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Pose;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;

/**
 * An invisible stand-in for one REPO actor, so Minecraft's own combat (swords, crits, sweeps,
 * enchantments, attack cooldown, bows, tridents) can target and hit REPO NPCs. What it receives is
 * forwarded to the real actor; its own health never drops.
 */
public class HostActorEntity extends LivingEntity {
	public dev.hollowcraft.link.HostLink.Scope scope;
	private static final EntityDataAccessor<Integer> FORM_ID = SynchedEntityData.defineId(HostActorEntity.class, EntityDataSerializers.INT);
	private static final EntityDataAccessor<Float> WIDTH = SynchedEntityData.defineId(HostActorEntity.class, EntityDataSerializers.FLOAT);
	private static final EntityDataAccessor<Float> HEIGHT = SynchedEntityData.defineId(HostActorEntity.class, EntityDataSerializers.FLOAT);

	// Keep impacts separate: hits from opposite sides cannot share one shield direction.
	private record PendingHit(DamageSource source, float[] values) { }
	private final ArrayDeque<PendingHit> pendingHits = new ArrayDeque<>();

	public HostActorEntity(EntityType<? extends HostActorEntity> type, Level level) {
		super(type, level);
		this.setNoGravity(true);
		this.noPhysics = true;
		this.setInvisible(true);
		this.setSilent(true);
	}

	public int formId() {
		return this.entityData.get(FORM_ID);
	}

	public void setFormId(int formId) {
		this.entityData.set(FORM_ID, formId);
	}

	@Override
	protected void defineSynchedData(SynchedEntityData.Builder builder) {
		super.defineSynchedData(builder);
		builder.define(FORM_ID, 0);
		builder.define(WIDTH, 0.6F);
		builder.define(HEIGHT, 1.8F);
	}

	public void setSize(float width, float height) {
		if (Math.abs(this.entityData.get(WIDTH) - width) > 0.01F || Math.abs(this.entityData.get(HEIGHT) - height) > 0.01F) {
			this.entityData.set(WIDTH, width);
			this.entityData.set(HEIGHT, height);
			this.refreshDimensions();
		}
	}

	@Override
	public void onSyncedDataUpdated(EntityDataAccessor<?> accessor) {
		super.onSyncedDataUpdated(accessor);
		if (WIDTH.equals(accessor) || HEIGHT.equals(accessor)) {
			this.refreshDimensions();
		}
	}

	@Override
	protected EntityDimensions getDefaultDimensions(Pose pose) {
		return EntityDimensions.scalable(this.entityData.get(WIDTH), this.entityData.get(HEIGHT));
	}

	@Override
	protected void actuallyHurt(ServerLevel level, DamageSource source, float dmg) {
		// Minecraft has applied everything (crit, sharpness, strength, cooldown, invulnerability
		// frames). Hand the result to REPO instead of lowering our own health.
		if (scope == null || !scope.equals(dev.hollowcraft.link.HostLink.captureScope()) || this.isInvulnerableTo(level, source) || dmg <= 0.0F) {
			return;
		}
		int flags = source.getDirectEntity() instanceof Projectile ? Proto.HIT_PROJECTILE : 0;
		if (source.is(net.minecraft.tags.DamageTypeTags.IS_FIRE)) flags |= Proto.HIT_FIRE;
		Vec3 origin = source.getSourcePosition();
		Vec3 direction = source.getDirectEntity() instanceof Projectile projectile ? projectile.getDeltaMovement()
			: origin != null ? this.position().subtract(origin) : Vec3.ZERO;
		double length = Math.hypot(direction.x, direction.y);
		float dx = length > 1e-6 && Double.isFinite(length) ? (float)(direction.x / length) : 0;
		float dy = length > 1e-6 && Double.isFinite(length) ? (float)(direction.y / length) : 0;
		pendingHits.addLast(new PendingHit(source, new float[] {dmg, dx, dy, 0,
			Float.intBitsToFloat(flags), Float.intBitsToFloat(weaponClass(source))}));
		this.getCombatTracker().recordDamage(source, dmg);
	}

	@Override
	public void knockback(double power, double xd, double zd, DamageSource source, float damage, boolean comesFromEffect) {
		// The native attack adds knockback after actuallyHurt; attach it to that impact.
		for (var it = pendingHits.descendingIterator(); it.hasNext();) {
			PendingHit hit = it.next();
			if (hit.source() == source) {
				hit.values()[3] = Math.max(hit.values()[3], (float)power);
				break;
			}
		}
	}

	/** Player.crit() was called on us this tick. */
	public void markCritical() {
		PendingHit hit = pendingHits.peekLast();
		if (hit != null) hit.values()[4] = Float.intBitsToFloat(Float.floatToRawIntBits(hit.values()[4]) | Proto.HIT_CRITICAL);
	}

	/** Which kind of REPO weapon impact this hit should look and sound like. */
	private static int weaponClass(DamageSource source) {
		if (source.getDirectEntity() instanceof net.minecraft.world.entity.projectile.arrow.ThrownTrident) {
			return Proto.WEAPON_PIERCE;
		}
		if (source.getDirectEntity() instanceof Projectile) {
			return Proto.WEAPON_ARROW;
		}
		ItemStack weapon = source.getWeaponItem();
		if (weapon == null && source.getEntity() instanceof LivingEntity attacker) {
			weapon = attacker.getMainHandItem();
		}
		if (weapon == null || weapon.isEmpty()) {
			return Proto.WEAPON_UNARMED;
		}
		if (weapon.is(ItemTags.SWORDS)) {
			return Proto.WEAPON_BLADE;
		}
		if (weapon.is(ItemTags.AXES)) {
			return Proto.WEAPON_AXE;
		}
		if (weapon.is(Items.TRIDENT)) {
			return Proto.WEAPON_PIERCE;
		}
		return Proto.WEAPON_BLUNT;
	}

	/** Returns one impact (damage, direction XY, push strength, flags, weapon). */
	public float[] takeHit() {
		PendingHit hit = pendingHits.pollFirst();
		return hit == null ? null : hit.values();
	}

	@Override
	public void tick() {
		// Position and rotation come from REPO (HostCombat); keep hurt timers and fire ticking.
		this.baseTick();
		this.setHealth(this.getMaxHealth());
	}

	@Override
	public boolean isPushable() {
		return false;
	}

	@Override
	public boolean ignoreExplosion(net.minecraft.world.level.Explosion explosion) {
		return true; // Hollow Knight applies the single authoritative blast event.
	}

	@Override
	protected void doPush(Entity entity) {
	}

	@Override
	public boolean canBeCollidedWith(@Nullable Entity other) {
		return false;
	}

	@Override
	public boolean shouldShowName() {
		return false;
	}

	@Override
	public boolean shouldBeSaved() {
		return false;
	}

	@Override
	protected @Nullable SoundEvent getHurtSound(DamageSource source) {
		return null; // REPO plays the NPC's own pain sounds
	}

	@Override
	protected @Nullable SoundEvent getDeathSound() {
		return null;
	}

	@Override
	public HumanoidArm getMainArm() {
		return HumanoidArm.RIGHT;
	}
}
