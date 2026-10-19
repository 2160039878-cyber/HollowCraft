using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using UnityEngine;

namespace HollowCraft.World
{
    internal sealed class RoomSlots
    {
        private string path => Path.Combine(Application.persistentDataPath, $"hollowcraft-rooms-{GameManager.instance.profileID}.json");
        private Dictionary<string, int> slots;
        public void Invalidate() => slots = null;
        public uint Select(string scene)
        {
            if (string.IsNullOrEmpty(scene) || scene.Length > 200) throw new ArgumentException("Invalid scene identity");
            if (slots == null)
            {
                string legacy = Path.Combine(Application.persistentDataPath, "hollowcraft-rooms.json");
                if (GameManager.instance.profileID == 1 && !File.Exists(path) && File.Exists(legacy)) File.Copy(legacy, path);
                slots = File.Exists(path) ? JsonConvert.DeserializeObject<Dictionary<string, int>>(File.ReadAllText(path))
                    : new Dictionary<string, int>();
                if (slots == null || slots.Count > 4096) throw new InvalidDataException("Invalid room slot map");
                var seen = new HashSet<int>();
                foreach (int value in slots.Values)
                    if (value < 0 || value >= 4096 || !seen.Add(value)) throw new InvalidDataException("Duplicate or invalid room slot");
            }
            if (!slots.TryGetValue(scene, out int slot))
            {
                slot = 0;
                foreach (int value in slots.Values) slot = Math.Max(slot, value + 1);
                if (slot >= 4096) throw new InvalidOperationException("Room slot capacity exceeded");
                slots.Add(scene, slot);
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                string temp = path + ".new";
                File.WriteAllText(temp, JsonConvert.SerializeObject(slots));
                if (File.Exists(path)) File.Replace(temp, path, path + ".bak");
                else File.Move(temp, path);
            }
            Coords.OffsetX = (slot % 16) * 1024.0;
            Coords.PlaneZ = (slot / 16) * 1024.0 + .5;
            return (uint)slot + 1;
        }
    }
}
