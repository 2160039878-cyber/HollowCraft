package dev.hollowcraft.world;

import dev.hollowcraft.link.HostLink;
import it.unimi.dsi.fastutil.longs.Long2IntOpenHashMap;
import java.util.List;
import java.util.Optional;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ServerExplosion;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;

/**
 * Minecraft explosions (TNT, creepers, fireballs, beds...) blowing up REPO's ground and rock as if
 * they were blocks of what they're made of: the blast is soaked up by them like by those blocks
 * (dirt gives way, stone holds more, buildings stop it), and what it reaches becomes that block for
 * the explosion to break the normal way (drops and all), dug out of REPO. Native geometry is cut in place without generating neighbouring terrain blocks.
 *
 * Needs REPO's geometry around the blast, which only the host's Minecraft has (the integrated
 * server shares its HostCollision): a guest's explosions far from the host leave REPO alone.
 */
public final class HostDigBlast {
	/** Blast resistance of what can't be dug (buildings): stops a blast like obsidian. */
	private static final float BUILDING_RESISTANCE = 1200.0F;
	private static final double[] SAMPLE = { 0.2, 0.5, 0.8 };
	private static final HostLink.HostState SKY = new HostLink.HostState();

	private final ServerLevel level;
	private final int world;
	private final HostLink.Scope scope;
	private final HostDig.Probe probe;
	private final Long2IntOpenHashMap cells = new Long2IntOpenHashMap(); // cell -> material, 0 none, KEEP

	private HostDigBlast(ServerLevel level, int world, Vec3 center, float radius) {
		this.level = level;
		this.world = world;
		this.scope = SKY.scope();
		double reach = radius * 1.4 + 2.0; // rays go up to 1.3 x radius
		this.probe = new HostDig.Probe().around(center.x - reach, center.y - reach, center.z - reach, center.x + reach, center.y + reach, center.z + reach);
		this.cells.defaultReturnValue(Integer.MIN_VALUE);
	}

	/** For an explosion about to go off: null unless REPO's geometry around it is known. */
	public static @Nullable HostDigBlast begin(ServerExplosion explosion) {
		Vec3 c = explosion.center();
		if (!HostDig.destruction || !HostCollision.active() || !HostCollision.isKnown((int) Math.floor(c.x), (int) Math.floor(c.y), (int) Math.floor(c.z)) || !HostLink.readSkyState(SKY)) {
			return null;
		}
		return new HostDigBlast(explosion.level(), SKY.worldId, c, explosion.radius());
	}

	/**
	 * What REPO geometry fills this cell as far as a blast cares: a Proto.DIG_* material if any of
	 * it is diggable ground or rock (even a little: the surface layer goes too), KEEP for a building,
	 * 0 for nothing (or already dug, or a Minecraft block there, which the blast handles itself).
	 */
	private int material(BlockPos pos) {
		long key = pos.asLong();
		int known = this.cells.get(key);
		if (known != Integer.MIN_VALUE) {
			return known;
		}
		int result = 0;
		if (!HostDig.isDug(this.level, this.world, pos)) {
			for (HostTri triangle : this.probe.tris) {
				if (!triangle.intersectsCell(pos.getX(), pos.getY(), pos.getZ())) continue;
				if (!triangle.diggable) { this.cells.put(key, HostDig.KEEP); return HostDig.KEEP; }
				result = triangle.material > 0 ? triangle.material : dev.hollowcraft.link.Proto.DIG_STONE;
			}
			if (result > 0) { this.cells.put(key, result); return result; }
			for (double sy : SAMPLE) {
				for (double sz : SAMPLE) {
					for (double sx : SAMPLE) {
						int r = this.probe.test(pos.getX() + sx, pos.getY() + sy, pos.getZ() + sz);
						if (r == HostDig.KEEP) {
							result = HostDig.KEEP;
							break;
						}
						if (r > HostDig.AIR && result == 0) {
							result = HostDig.underground(r, Math.max(this.probe.depth, 0.5));
						}
					}
				}
			}
		}
		this.cells.put(key, result);
		return result;
	}

	/** The explosion's ray reached this cell: how much REPO geometry there soaks up. */
	public Optional<Float> resistance(BlockPos pos, Optional<Float> vanilla) {
		int m = material(pos);
		if (m == HostDig.KEEP) {
			return Optional.of(BUILDING_RESISTANCE);
		}
		return m > 0 ? Optional.of(Math.max(vanilla.orElse(0f), HostDig.materialState(m).getBlock().getExplosionResistance())) : vanilla;
	}

	/**
	 * The cells the explosion will break: REPO geometry in them becomes the block it's made of
	 * (dug out of REPO), so the explosion breaks it like any block.
	 */
	public void materialize(List<BlockPos> targets, boolean breaksBlocks) {
		if (!breaksBlocks || !scope.equals(HostLink.captureScope())) {
			return;
		}
		for (BlockPos pos : targets) {
			int m = material(pos);
			if (m <= 0) {
				continue;
			}
			HostDig.markDug(this.level, this.world, pos);
		}
	}

}
