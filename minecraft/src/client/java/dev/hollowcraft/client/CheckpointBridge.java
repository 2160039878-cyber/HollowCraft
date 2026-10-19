package dev.hollowcraft.client;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import dev.hollowcraft.HollowCraft;
import dev.hollowcraft.link.HostLink;
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.FileSystemException;
import java.nio.file.AccessDeniedException;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.world.level.storage.LevelResource;

/** Local checkpoint commands are scoped to the live HK process and contain no request-supplied paths. */
public final class CheckpointBridge {
    private static final Gson JSON = new Gson();
    private static final Path ROOT = checkpointRoot();
    private static final Map<Path, Long> blockedReads = new LinkedHashMap<>();
    private static Path checkpointRoot() {
        String configured = System.getProperty("hollowcraft.profile");
        Path profile = configured == null
            ? Path.of(System.getProperty("user.home"), "AppData", "LocalLow", "HollowCraft", "HollowCraftHK")
            : Path.of(configured);
        if (!profile.isAbsolute() || profile.toString().startsWith("\\\\"))
            throw new IllegalArgumentException("HollowCraft profile must be an absolute local path");
        return profile.normalize().resolve("hollowcraft-checkpoints");
    }
    private record Request(String id, String session, int slot, String checkpoint, boolean fresh) { }
    private record Applied(String id, String world) { }
    private record Response(String id, String status, String error, int files) { }
    private record RestoreRequest(String id, String session, int world, int epoch) { }
    private record RestoreResponse(String id, String status, String error, int world, int epoch, int revision) { }
    private static Request selection;
    private static String worldName, savedId;
    private static boolean opening, prepared, ready;
    private static long nextPoll;
    private static volatile boolean saving;
    private static String restoredId;
    private static volatile boolean restoring;
    private CheckpointBridge() { }

    private static Path bridge(String name) { return ROOT.resolve("bridge").resolve(name + ".json"); }
    private static boolean validId(String id) { return id != null && id.matches("[a-f0-9]{32}"); }
    private static void validate(Request request) throws IOException {
        if (!validId(request.id()) || request.slot() < 1 || request.slot() > 4
            || (request.checkpoint() != null && !validId(request.checkpoint()))) throw new IOException("Invalid checkpoint identity");
    }
    private static Path checkpoint(int slot, String id) throws IOException {
        if (slot < 1 || slot > 4 || !validId(id)) throw new IOException("Invalid checkpoint path");
        return ROOT.resolve("slot-" + slot).resolve(id);
    }
    private static <T> T read(Path path, Class<T> type) throws IOException {
        try {
            if (!Files.isRegularFile(path)) { blockedReads.remove(path); return null; }
            if (Files.size(path) > 65536) throw new IOException("Oversized checkpoint control file");
            String text = Files.readString(path);
            blockedReads.remove(path);
            return JSON.fromJson(text, type);
        } catch (FileSystemException error) {
            if (error instanceof AccessDeniedException) throw error;
            long now = System.nanoTime();
            Long first = blockedReads.putIfAbsent(path, now);
            if (first != null && now - first >= 1_000_000_000L) throw error;
            HollowCraft.LOG.debug("Deferring busy checkpoint control read: {}", path.getFileName());
            return null;
        }
    }
    private static void write(Path path, Object value) throws IOException {
        Files.createDirectories(path.getParent());
        Path temporary = path.resolveSibling(path.getFileName() + ".new");
        Files.writeString(temporary, JSON.toJson(value), StandardCharsets.UTF_8);
        try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE)) { channel.force(true); }
        Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }
    private static Request request(String name) throws IOException {
        Request value = read(bridge(name), Request.class);
        if (value == null || !String.format("%016x", HostClient.sky().session).equals(value.session())) return null;
        validate(value);
        return value;
    }

    public static void frame(Minecraft minecraft) {
        long now = System.nanoTime();
        if (now < nextPoll) return;
        nextPoll = now + 100_000_000;
        try {
            Request wanted = request("selection");
            if (wanted == null) return;
            if (selection == null || !selection.id().equals(wanted.id())) {
                if (saving) return;
                selection = wanted; opening = prepared = ready = false;
                if (minecraft.level != null) minecraft.disconnect(new TitleScreen(), false);
                Applied applied = read(bridge("applied"), Applied.class);
                worldName = "HollowCraft-" + wanted.slot() + "-" + wanted.id();
                Path world = minecraft.getLevelSource().getLevelPath(worldName);
                if (applied != null && wanted.id().equals(applied.id()) && worldName.equals(applied.world()) && Files.isDirectory(world)) {
                    prepared = true; // Same request after a backend restart: resume its working world.
                } else if (wanted.checkpoint() != null) {
                    Path snapshot = checkpoint(wanted.slot(), wanted.checkpoint());
                    verifyTree(snapshot.resolve("minecraft"), snapshot.resolve("minecraft-files.json"));
                    copyTree(snapshot.resolve("minecraft"), world);
                    write(bridge("applied"), new Applied(wanted.id(), worldName));
                    prepared = true;
                } else {
                    Path legacy = minecraft.getLevelSource().getLevelPath(HollowCraft.WORLD_NAME);
                    if (!wanted.fresh() && wanted.slot() == 1 && Files.isDirectory(legacy)) copyTree(legacy, world);
                    if (Files.isDirectory(world)) write(bridge("applied"), new Applied(wanted.id(), worldName));
                    prepared = true;
                }
            }
            if (!prepared) return;
            if (!opening) opening = MirrorWorld.openWhenReady(minecraft, worldName);
            if (!ready && opening && minecraft.player != null && minecraft.getSingleplayerServer() != null) {
                ready = true;
                write(bridge("applied"), new Applied(selection.id(), worldName));
                write(bridge("selection-status"), new Response(selection.id(), "ready", null, 0));
            }
            restoreRoom(minecraft);
            Request save = request("save");
            var server = minecraft.getSingleplayerServer();
            if (!ready || save == null || save.id().equals(savedId) || saving || server == null || !server.isPaused()) return;
            if (save.slot() != selection.slot()) throw new IOException("Checkpoint slot does not match the loaded world");
            savedId = save.id(); saving = true;
            server.execute(() -> {
                try {
                    var host = new HostLink.HostState();
                    if (!HostLink.readSkyState(host) || !String.format("%016x", host.session).equals(save.session()))
                        throw new IOException("Host session changed before checkpoint save");
                    Path target = checkpoint(save.slot(), save.id());
                    int fileCount;
                    if (Files.isRegularFile(target.resolve("minecraft-files.json"), LinkOption.NOFOLLOW_LINKS)) {
                        // A backend restart can replay the last completed request. Keep that snapshot immutable.
                        fileCount = verifyTree(target.resolve("minecraft"), target.resolve("minecraft-files.json"));
                    } else {
                        server.saveEverything(false, true, true);
                        Map<String, String> files = copyTree(server.getWorldPath(LevelResource.ROOT), target.resolve("minecraft"));
                        write(target.resolve("minecraft-files.json"), files);
                        fileCount = files.size();
                    }
                    write(bridge("save-status"), new Response(save.id(), "ready", null, fileCount));
                } catch (Exception e) { fail("save-status", save.id(), e); }
                finally { saving = false; }
            });
        } catch (Exception e) {
            prepared = false;
            fail("selection-status", selection == null ? "" : selection.id(), e);
        }
    }

    private static void restoreRoom(Minecraft minecraft) throws IOException {
        var server=minecraft.getSingleplayerServer();
        if (!ready || saving || restoring || server==null || !server.isPaused()) return;
        RestoreRequest request=read(bridge("restore-room"),RestoreRequest.class);
        if (request==null || !validId(request.id()) || request.world()<1 || request.world()>4096 || request.id().equals(restoredId)) return;
        var host=HostClient.sky();
        if (!String.format("%016x",host.session).equals(request.session()) || request.world()!=host.worldId || request.epoch()!=host.collisionEpoch) return;
        restoredId=request.id(); restoring=true;
        server.execute(() -> {
            try {
                var current=new HostLink.HostState();
                if (!HostLink.readSkyState(current) || !String.format("%016x",current.session).equals(request.session())
                    || current.worldId!=request.world() || current.collisionEpoch!=request.epoch() || !current.menuOpen())
                    throw new IOException("Room changed before restore");
                int revision=dev.hollowcraft.world.RoomVersions.restore(server,request.world(),request.id());
                write(bridge("restore-room-status"),new RestoreResponse(request.id(),"ready",null,request.world(),request.epoch(),revision));
            } catch (Exception e) {
                HollowCraft.LOG.error("Room restore failed",e);
                try { write(bridge("restore-room-status"),new RestoreResponse(request.id(),"error",e.getMessage(),request.world(),request.epoch(),0)); }
                catch (IOException io) { HollowCraft.LOG.error("Unable to report room restore failure",io); }
            } finally { restoring=false; }
        });
    }

    private static void fail(String file, String id, Exception error) {
        HollowCraft.LOG.error("HollowCraft checkpoint failed: {}", error.toString());
        try { write(bridge(file), new Response(id, "error", error.getMessage(), 0)); }
        catch (IOException writeError) { HollowCraft.LOG.error("Unable to report checkpoint failure", writeError); }
    }
    private static String hash(Path file) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(file)) {
            byte[] buffer = new byte[65536];
            int count;
            while ((count = input.read(buffer)) >= 0) if (count > 0) hash.update(buffer, 0, count);
        }
        return HexFormat.of().formatHex(hash.digest());
    }
    private static Map<String, String> copyTree(Path source, Path destination) throws Exception {
        source = source.toRealPath();
        if (Files.exists(destination)) throw new IOException("Checkpoint destination already exists; preserved for recovery");
        Files.createDirectories(destination);
        Map<String, String> manifest = new LinkedHashMap<>();
        try (var paths = Files.walk(source)) {
            for (Path file : (Iterable<Path>)paths::iterator) {
                if (file.equals(source) || Files.isDirectory(file, LinkOption.NOFOLLOW_LINKS)) continue;
                if (file.getFileName().toString().equals("session.lock")) continue;
                if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || !file.toRealPath().startsWith(source))
                    throw new IOException("World snapshot contains an unsupported link");
                Path relative = source.relativize(file), target = destination.resolve(relative);
                Files.createDirectories(target.getParent());
                Files.copy(file, target);
                manifest.put(relative.toString().replace('\\', '/'), hash(target));
            }
        }
        return manifest;
    }
    private static int verifyTree(Path source, Path manifest) throws Exception {
        if (Files.size(manifest) > 16 * 1024 * 1024) throw new IOException("Oversized world manifest");
        JsonObject files = JSON.fromJson(Files.readString(manifest), JsonObject.class);
        if (files == null || !files.has("level.dat")) throw new IOException("Incomplete world checkpoint");
        for (var entry : files.entrySet()) {
            Path file = source.resolve(entry.getKey()).normalize();
            if (!file.startsWith(source) || !Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)
                || !hash(file).equals(entry.getValue().getAsString())) throw new IOException("World checkpoint checksum mismatch: " + entry.getKey());
        }
        try (var paths = Files.walk(source)) {
            for (Path file : (Iterable<Path>)paths::iterator) {
                if (Files.isDirectory(file, LinkOption.NOFOLLOW_LINKS)) continue;
                if (!files.has(source.relativize(file).toString().replace('\\', '/')))
                    throw new IOException("Unlisted file in world checkpoint");
            }
        }
        return files.size();
    }
}
