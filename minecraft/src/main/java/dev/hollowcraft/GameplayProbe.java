package dev.hollowcraft;

import com.google.gson.Gson;
import dev.hollowcraft.link.HostLink;
import dev.hollowcraft.world.HostCollision;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.projectile.arrow.AbstractArrow;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.properties.AttachFace;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

/** Explicit local development requests; observes real item use and placement without replacing their logic. */
public final class GameplayProbe {
    private static final boolean ENABLED=Boolean.getBoolean("hollowcraft.testMode");
    private static final Path REQUEST=Path.of("hollowcraft-gameplay-probe.request");
    private static final Path RESULT=Path.of("hollowcraft-gameplay-probe-result.json");
    private static final ArrayList<Object> samples=new ArrayList<>();
    private static HostLink.Scope sampleScope;
    private static long started, nextPoll;
    private GameplayProbe() { }

    public static void tick(MinecraftServer server) {
        if (!ENABLED || !HostLink.active() || server.getPlayerList().getPlayers().isEmpty()) return;
        var state=new HostLink.HostState();
        if (!HostLink.readSkyState(state) || !state.inGame() || state.loading()) return;
        var player=server.getPlayerList().getPlayers().getFirst();
        try {
            if (System.currentTimeMillis()>=nextPoll) {
                nextPoll=System.currentTimeMillis()+250;
                if (Files.exists(REQUEST)) {
                    if (Files.size(REQUEST)>32) throw new IllegalArgumentException("Oversized gameplay probe");
                    String request=Files.readString(REQUEST).trim();Files.delete(REQUEST);
                    if (request.startsWith("blocks ")) {
                        String[] fields=request.split("\\s+");
                        if(fields.length!=3) throw new IllegalArgumentException("Expected block coordinates");
                        int x=Integer.parseInt(fields[1]),y=Integer.parseInt(fields[2]),z=(int)Math.floor(state.z);
                        if(Math.abs(x-state.x)>64 || Math.abs(y-state.y)>64)
                            throw new IllegalArgumentException("Block inspection outside player neighbourhood");
                        var blocks=new ArrayList<Object>();
                        for(int dx=-1;dx<=6;dx++) for(int dy=-1;dy<=1;dy++) {
                            var pos=new BlockPos(x+dx,y+dy,z);
                            if(!HostCollision.isKnown(pos.getX(),pos.getY(),pos.getZ()))
                                throw new IllegalStateException("Block inspection area not streamed");
                            blocks.add(Map.of("x",pos.getX(),"y",pos.getY(),"z",z,
                                "state",player.level().getBlockState(pos).toString(),
                                "dug",dev.hollowcraft.world.HostDig.isDug(player.level(),state.worldId,pos)));
                        }
                        write(Map.of("world",state.worldId,"epoch",state.collisionEpoch,"blocks",blocks));
                    }
                    else if (request.equals("explosion-formula")) {
                        var calculator=new net.minecraft.world.level.ExplosionDamageCalculator();
                        var cases=new ArrayList<Object>();
                        for(float power:new float[]{1,4}) for(float distance:new float[]{0,.1f,.5f,1.25f,2,4,6,8})
                            for(float exposure:new float[]{0,.125f,.5f,1}) {
                                if(distance>power*2) continue;
                                var centre=player.position().add(distance,0,0);
                                var explosion=new net.minecraft.world.level.ServerExplosion(player.level(),null,null,calculator,
                                    centre,power,false,net.minecraft.world.level.Explosion.BlockInteraction.KEEP);
                                cases.add(Map.of("power",power,"distance",distance,"exposure",exposure,
                                    "nativeDamage",calculator.getEntityDamageAmount(explosion,player,exposure)));
                            }
                        write(Map.of("cases",cases,"health",player.getHealth()));
                    }
                    else if (request.equals("lever")) write(lever(player,state));
                    else if (request.equals("sisters-kit")) {
                        var inventory=player.getInventory();
                        if (!inventory.getItem(8).is(Items.CROSSBOW)) {
                            if (!inventory.getItem(8).is(Items.BOW)) throw new IllegalStateException("Expected original bow slot");
                            int slot=-1;
                            for(int i=0;i<36;i++) if(inventory.getItem(i).is(Items.CROSSBOW)){slot=i;break;}
                            if(slot<0) throw new IllegalStateException("Refill a real crossbow before arranging the loadout");
                            var bow=inventory.getItem(8);
                            inventory.setItem(8,inventory.getItem(slot));inventory.setItem(slot,bow);
                        }
                        if(!player.getOffhandItem().is(Items.SHIELD)) throw new IllegalStateException("Offhand shield missing");
                        player.getOffhandItem().enchant(player.registryAccess().lookupOrThrow(net.minecraft.core.registries.Registries.ENCHANTMENT)
                            .getOrThrow(net.minecraft.world.item.enchantment.Enchantments.UNBREAKING),3);
                        var enchants=player.registryAccess().lookupOrThrow(net.minecraft.core.registries.Registries.ENCHANTMENT);
                        inventory.getItem(8).enchant(enchants.getOrThrow(net.minecraft.world.item.enchantment.Enchantments.QUICK_CHARGE),3);
                        inventory.getItem(8).enchant(enchants.getOrThrow(net.minecraft.world.item.enchantment.Enchantments.PIERCING),4);
                        if(!inventory.getItem(7).is(Items.OAK_BUTTON)) throw new IllegalStateException("Expected original button slot");
                        var oldButton=inventory.getItem(7);inventory.setItem(7,ItemStack.EMPTY);inventory.add(oldButton);
                        var potion=new ItemStack(Items.POTION);
                        potion.set(net.minecraft.core.component.DataComponents.POTION_CONTENTS,
                            new net.minecraft.world.item.alchemy.PotionContents(net.minecraft.world.item.alchemy.Potions.STRONG_STRENGTH));
                        inventory.setItem(7,potion);
                        player.containerMenu.broadcastChanges();
                        write(Map.of("kit","native crossbow + Unbreaking III shield","potion","Strength II (native item, not yet consumed)","crossbowEnchantments","Quick Charge III, Piercing IV","charged",net.minecraft.world.item.CrossbowItem.isCharged(inventory.getItem(8)),
                            "ammo",inventory.countItem(Items.ARROW),"health",player.getHealth()));
                    }
                    else if (request.equals("inventory")) {
                        var slots=new ArrayList<Object>();
                        for(int i=0;i<9;i++) {
                            var stack=player.getInventory().getItem(i);
                            slots.add(Map.of("slot",i+1,"item",BuiltInRegistries.ITEM.getKey(stack.getItem()).toString(),"count",stack.getCount()));
                        }
                        write(Map.of("hotbar",slots));
                    }
                    else if (request.equals("status")) {
                        var tnt = new ArrayList<Object>();
                        for (var entity : player.level().getAllEntities())
                            if (entity instanceof net.minecraft.world.entity.item.PrimedTnt primed)
                                tnt.add(Map.of("id", primed.getId(), "x", primed.getX(), "y", primed.getY(), "z", primed.getZ(),
                                    "fuse", primed.getFuse(), "tags", primed.entityTags().stream().filter(t -> t.startsWith("hollowcraft_tnt_room:")).toList()));
                        write(Map.of("arrows", player.getInventory().countItem(Items.ARROW),
                            "held", BuiltInRegistries.ITEM.getKey(player.getMainHandItem().getItem()).toString(), "health", player.getHealth(),
                            "maxHealth", player.getMaxHealth(), "creative", player.isCreative(), "tnt", tnt,
                            "crossbowCharged",net.minecraft.world.item.CrossbowItem.isCharged(player.getMainHandItem()),
                            "offhand",BuiltInRegistries.ITEM.getKey(player.getOffhandItem().getItem()).toString(),"shieldWear",player.getOffhandItem().getDamageValue(),
                            "strength",player.hasEffect(net.minecraft.world.effect.MobEffects.STRENGTH) ? player.getEffect(net.minecraft.world.effect.MobEffects.STRENGTH).getAmplifier()+1 : 0));
                    }
                    else if (request.equals("sample")) { samples.clear();started=player.level().getGameTime();sampleScope=state.scope(); }
                    else throw new IllegalArgumentException("Unknown gameplay probe");
                }
            }
            if (sampleScope==null) return;
            if (!sampleScope.equals(state.scope())) { write(Map.of("cancelled",true,"reason","scope changed","samples",samples));sampleScope=null;return; }
            long tick=player.level().getGameTime()-started;
            var arrows=new ArrayList<Object>();
            for (var entity:player.level().getAllEntities()) if (entity instanceof AbstractArrow arrow)
                arrows.add(Map.of("id",arrow.getId(),"x",arrow.getX(),"y",arrow.getY(),"z",arrow.getZ(),"removed",arrow.isRemoved(),
                    "vx",arrow.getDeltaMovement().x,"vy",arrow.getDeltaMovement().y));
            var sample=new LinkedHashMap<String,Object>(Map.of("tick",tick,"health",player.getHealth(),"hurtTime",player.hurtTime,"using",player.isUsingItem(),
                "useTicks",player.getTicksUsingItem(),"held",BuiltInRegistries.ITEM.getKey(player.getMainHandItem().getItem()).toString(),
                "arrows",arrows,"playerX",player.getX(),"playerY",player.getY(),"ammo",player.getInventory().countItem(Items.ARROW)));
            sample.put("tntCount",player.getInventory().countItem(Items.TNT));
            sample.put("leverCount",player.getInventory().countItem(Items.LEVER));
            samples.add(sample);
            if (tick>=400) { write(Map.of("complete",true,"samples",samples));sampleScope=null; }
        } catch(Exception error) {
            sampleScope=null;
            try { write(Map.of("error",error.toString())); } catch(Exception ignored) { HollowCraft.LOG.error("Gameplay probe failed",error); }
        }
    }

    private static Object lever(ServerPlayer player,HostLink.HostState state) {
        var level=player.level();BlockPos position=null;
        for(int dy=2;dy<=12 && position==null;dy++) {
            var candidate=BlockPos.containing(state.x+4,state.y+dy,state.z);
            // Only the side-view plane is streamed. Adjacent depth cells may legitimately be unknown.
            boolean empty=HostCollision.isKnown(candidate.getX(),candidate.getY(),candidate.getZ())
                && HostCollision.isKnown(candidate.getX(),candidate.getY()-1,candidate.getZ());
            for(var p:BlockPos.betweenClosed(candidate.offset(-1,-2,-1),candidate.offset(1,1,1)))
                empty &= level.isEmptyBlock(p) && !HostCollision.hasGeometry(p);
            if(empty)position=candidate;
        }
        if(position==null)throw new IllegalStateException("No empty known area for reversible placement check");
        var support=position.below();
        var hit=new BlockHitResult(Vec3.atCenterOf(support).add(0,.5,0),Direction.UP,support,false);
        var item=(BlockItem)Items.LEVER;
        var floorLever=Blocks.LEVER.defaultBlockState().setValue(BlockStateProperties.ATTACH_FACE,AttachFace.FLOOR);
        var result=new LinkedHashMap<String,Object>();
        result.put("position",new int[]{position.getX(),position.getY(),position.getZ()});
        try {
            result.put("airCanSurvive",floorLever.canSurvive(level,position));
            var floatingContext=new BlockPlaceContext(player,InteractionHand.MAIN_HAND,new ItemStack(Items.LEVER),hit);
            result.put("airPlacementResult",item.place(floatingContext).toString());
            boolean floatingPlaced=level.getBlockState(floatingContext.getClickedPos()).is(Blocks.LEVER);
            result.put("airPlaced",floatingPlaced);
            if(floatingPlaced) level.setBlock(floatingContext.getClickedPos(),Blocks.AIR.defaultBlockState(),2);
            level.setBlock(support,Blocks.STONE.defaultBlockState(),3);
            result.put("stoneCanSurvive",floorLever.canSurvive(level,position));
            result.put("stonePlacementResult",item.place(new BlockPlaceContext(player,InteractionHand.MAIN_HAND,new ItemStack(Items.LEVER),hit)).toString());
            boolean placed=level.getBlockState(position).is(Blocks.LEVER);result.put("stonePlaced",placed);
            level.setBlock(support,Blocks.AIR.defaultBlockState(),2);
            boolean survives=floorLever.canSurvive(level,position);result.put("survivesWithoutSupport",survives);
            result.put("passed",!floatingPlaced && placed && !survives && !(boolean)result.get("airCanSurvive") && (boolean)result.get("stoneCanSurvive"));
        } finally {
            level.setBlock(position,Blocks.AIR.defaultBlockState(),2);
            level.setBlock(support,Blocks.AIR.defaultBlockState(),3);
        }
        return result;
    }

    private static void write(Object value) throws java.io.IOException { Files.writeString(RESULT,new Gson().toJson(value)); }
}
