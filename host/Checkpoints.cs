using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using HollowCraft.Link;
using Newtonsoft.Json;
using UnityEngine;

namespace HollowCraft
{
    internal sealed class Checkpoints : MonoBehaviour
    {
        private const string SelectionTimeout = "Minecraft world load timed out; committed checkpoint retained";
        private sealed class Request
        {
            public string id, session, checkpoint;
            public int slot;
            public bool fresh;
        }
        private sealed class Response { public string id, status, error; public int files; }
        private sealed class Manifest { public int schema = 1, slot; public string id, saveHash, modsHash, roomsHash, worldManifestHash; }
        private sealed class Save
        {
            public On.GameManager.orig_SaveGame_int_Action1 Original;
            public GameManager Game;
            public Action<bool> Callback;
            public Request Request;
            public bool? NativeResult;
            public int Phase, Frame;
            public float Started;
        }
        private readonly Queue<Save> queue = new Queue<Save>();
        private Request selected;
        private Save saving;
        private string pendingFilename;
        private float nextPoll;
        private float selectionStarted;
        public uint LoadGeneration { get; private set; }
        public bool Ready { get; private set; }
        public bool Saving => saving != null || queue.Count != 0;
        public string Error { get; private set; }
        public static Checkpoints Instance { get; private set; }
        private string Root => Path.Combine(Application.persistentDataPath, "hollowcraft-checkpoints");
        private string Bridge(string name) => Path.Combine(Root, "bridge", name + ".json");
        private string Current(int slot) => Path.Combine(Root, "slot-" + slot, "current.json");
        private string SlotFile(int slot) => Path.Combine(Application.persistentDataPath, $"hollowcraft-{slot}.dat");
        private string RoomsFile(int slot) => Path.Combine(Application.persistentDataPath, $"hollowcraft-rooms-{slot}.json");
        private string ModsFile(int slot) => Path.Combine(Application.persistentDataPath, $"user{slot}.modded.json");

        private void Awake()
        {
            Instance = this;
            On.GameManager.SaveGame_int_Action1 += SaveGame;
            On.GameManager.LoadGame += LoadGame;
            On.GameManager.StartNewGame += StartNewGame;
        }

        public static string SaveFilename(int slot) => Instance?.saving?.Request.slot == slot && Instance.pendingFilename != null
            ? Instance.pendingFilename : $"hollowcraft-{slot}.dat";
        public bool HasCommitted(int slot) => File.Exists(Current(slot));
        private static void Json(string path, object value) => CheckpointFiles.Write(path, Encoding.UTF8.GetBytes(JsonConvert.SerializeObject(value)));
        private static T Read<T>(string path, bool deferBusy = false)
        {
            string text = CheckpointFiles.ReadControl(path, deferBusy);
            return text == null ? default : JsonConvert.DeserializeObject<T>(text);
        }
        private Request NewRequest(int slot) => new Request { slot = slot, id = Guid.NewGuid().ToString("N"), session = SharedLink.Instance.Session.ToString("x16") };

        private void Select(int slot, bool fresh)
        {
            if (Saving) throw new InvalidOperationException("A checkpoint save is still in progress");
            var request = NewRequest(slot);
            CheckpointFiles.DirectoryFor(Root, slot, request.id);
            Manifest manifest = fresh ? null : Read<Manifest>(Current(slot));
            if (manifest != null)
            {
                if (manifest.schema != 1 || manifest.slot != slot) throw new InvalidDataException("Invalid checkpoint manifest");
                string source = CheckpointFiles.DirectoryFor(Root, slot, manifest.id);
                if (CheckpointFiles.Hash(Path.Combine(source, "minecraft-files.json")) != manifest.worldManifestHash)
                    throw new InvalidDataException("Minecraft manifest checksum mismatch");
                CheckpointFiles.Restore(Path.Combine(source, "hollowcraft.dat"), SlotFile(slot), manifest.saveHash);
                if (manifest.modsHash != null) CheckpointFiles.Restore(Path.Combine(source, "mods.json"), ModsFile(slot), manifest.modsHash);
                if (manifest.roomsHash != null) CheckpointFiles.Restore(Path.Combine(source, "rooms.json"), RoomsFile(slot), manifest.roomsHash);
                request.checkpoint = manifest.id;
            }
            request.fresh = fresh;
            selected = request; Ready = false; Error = null; LoadGeneration++;
            selectionStarted = Time.realtimeSinceStartup;
            Json(Bridge("selection"), request);
        }

        private void LoadGame(On.GameManager.orig_LoadGame original, GameManager game, int slot, Action<bool> callback)
        {
            try { Select(slot, false); original(game, slot, callback); }
            catch (Exception e) { Error = e.Message; Log.Error("Checkpoint load: " + e); callback?.Invoke(false); }
        }
        private void StartNewGame(On.GameManager.orig_StartNewGame original, GameManager game, bool permadeath, bool bossRush)
        {
            try { Select(game.profileID, true); original(game, permadeath, bossRush); }
            catch (Exception e) { Error = e.Message; Log.Error("New sandbox: " + e); }
        }
        private void SaveGame(On.GameManager.orig_SaveGame_int_Action1 original, GameManager game, int slot, Action<bool> callback)
        {
            if (slot < 1 || slot > 4) { callback?.Invoke(false); return; }
            queue.Enqueue(new Save { Original = original, Game = game, Callback = callback, Request = NewRequest(slot), Started = Time.realtimeSinceStartup });
        }

        private void Update()
        {
            try
            {
                if (Time.realtimeSinceStartup >= nextPoll)
                {
                    nextPoll = Time.realtimeSinceStartup + .1f;
                    Response response = Read<Response>(Bridge("selection-status"), true);
                    if (response != null) Ready = selected != null && response.id == selected.id && response.status == "ready";
                    // Loading keeps polling after its timeout; a matching late success resolves only that error.
                    if (Ready && Error == SelectionTimeout) Error = null;
                    if (selected != null && response?.id == selected.id && response.status == "error") Error = response.error;
                    if (selected != null && !Ready && Time.realtimeSinceStartup - selectionStarted > 120 && Error == null)
                        Error = SelectionTimeout;
                }
                if (saving == null && queue.Count != 0)
                {
                    saving = queue.Dequeue(); saving.Frame = Time.frameCount;
                }
                if (saving == null) return;
                if (Time.realtimeSinceStartup - saving.Started > 120) throw new IOException("Minecraft checkpoint timed out; previous checkpoint retained");
                Request request = saving.Request;
                string directory = CheckpointFiles.DirectoryFor(Root, request.slot, request.id);
                if (saving.Phase == 0 && Ready && Time.frameCount > saving.Frame + 2)
                {
                    Directory.CreateDirectory(directory);
                    pendingFilename = Path.GetRelativePath(Application.persistentDataPath, Path.Combine(directory, "hollowcraft.dat"));
                    saving.Phase = 1;
                    Save current = saving;
                    current.Original(current.Game, request.slot, result => current.NativeResult = result);
                }
                if (saving.Phase == 1 && saving.NativeResult.HasValue)
                {
                    pendingFilename = null;
                    if (!saving.NativeResult.Value) throw new IOException("Hollow Knight save failed; previous checkpoint retained");
                    if (File.Exists(ModsFile(request.slot))) File.Copy(ModsFile(request.slot), Path.Combine(directory, "mods.json"));
                    if (File.Exists(RoomsFile(request.slot))) File.Copy(RoomsFile(request.slot), Path.Combine(directory, "rooms.json"));
                    Json(Bridge("save"), request);
                    saving.Phase = 2;
                }
                if (saving.Phase != 2) return;
                Response saved = Read<Response>(Bridge("save-status"), true);
                if (saved?.id != request.id) return;
                if (saved.status == "error") throw new IOException(saved.error);
                if (saved.status != "ready") return;
                if (saved.files < 1 || !File.Exists(Path.Combine(directory, "minecraft", "level.dat")))
                    throw new InvalidDataException("Minecraft snapshot is incomplete");
                var manifest = new Manifest { slot = request.slot, id = request.id,
                    saveHash = CheckpointFiles.Hash(Path.Combine(directory, "hollowcraft.dat")),
                    modsHash = File.Exists(Path.Combine(directory, "mods.json")) ? CheckpointFiles.Hash(Path.Combine(directory, "mods.json")) : null,
                    roomsHash = File.Exists(Path.Combine(directory, "rooms.json")) ? CheckpointFiles.Hash(Path.Combine(directory, "rooms.json")) : null };
                manifest.worldManifestHash = CheckpointFiles.Hash(Path.Combine(directory, "minecraft-files.json"));
                Json(Path.Combine(directory, "manifest.json"), manifest);
                CheckpointFiles.Restore(Path.Combine(directory, "hollowcraft.dat"), SlotFile(request.slot), manifest.saveHash);
                Json(Current(request.slot), manifest); // Commit pointer is the final write after both games have saved successfully.
                Log.Info($"Committed checkpoint {request.id} for slot {request.slot} ({saved.files} Minecraft files)");
                Finish(true);
            }
            catch (Exception e) { Error = e.Message; Log.Error("Checkpoint: " + e); Finish(false); }
        }
        private void Finish(bool success)
        {
            if (success) Error = null;
            Save finished = saving; saving = null; pendingFilename = null;
            finished?.Callback?.Invoke(success);
        }
        private void OnDestroy()
        {
            On.GameManager.SaveGame_int_Action1 -= SaveGame;
            On.GameManager.LoadGame -= LoadGame;
            On.GameManager.StartNewGame -= StartNewGame;
            if (Instance == this) Instance = null;
        }
    }
}
