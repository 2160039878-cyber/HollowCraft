using System;
using System.Collections.Generic;
using Modding;
using UnityEngine;

namespace HollowCraft
{
    public sealed class HollowCraftMod : Mod
    {
        public HollowCraftMod() : base("HollowCraft") { }
        public override string GetVersion() => "0.1.0-dev (HK 1.5.12620)";
        private static bool TestForms => Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test") >= 0
            && Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test-forms") >= 0;
        private static bool TestDream => Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test") >= 0
            && Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test-dream") >= 0;
        private static bool TestRadiance => Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test") >= 0
            && Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test-radiance") >= 0;
        private static bool TestStatic => Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test") >= 0
            && Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test-static") >= 0;
        private static bool TestAbyss => Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test") >= 0
            && Array.IndexOf(Environment.GetCommandLineArgs(), "-hollowcraft-test-abyss") >= 0;
        internal static bool ActorFixture => TestForms || TestDream || TestRadiance || TestStatic || TestAbyss;
        public override List<(string, string)> GetPreloadNames() => TestDream
            ? new List<(string, string)> { ("RestingGrounds_07", "Dream Moth/Knight Dummy") }
            : TestRadiance ? new List<(string, string)> { ("Dream_Final_Boss", "Knight Ball") }
            : TestAbyss ? new List<(string, string)> { ("Abyss_15", "Dream Enter Abyss/Knight Dummy") }
            : TestForms ? new List<(string, string)> { ("GG_Radiance", "Boss Control/Shade_Lord"), ("GG_Radiance", "Boss Control/Shade Lord Hand") } : null;
        public override void Initialize() => Initialize(null);
        public override void Initialize(Dictionary<string, Dictionary<string, GameObject>> preloadedObjects)
        {
            ModHooks.GetSaveFileNameHook += Checkpoints.SaveFilename;
            ModHooks.NewGameHook += () => PlayerData.instance.hasDoubleJump = true;
            var root = new GameObject("HollowCraft runtime");
            UnityEngine.Object.DontDestroyOnLoad(root);
            root.AddComponent<HollowCraftRuntime>();
            if (TestForms) root.AddComponent<LiveFormProbe>().PreloadedObjects = preloadedObjects;
            if (TestDream) { var probe=root.AddComponent<LiveFormProbe>();probe.DreamOnly=true;probe.PreloadedObjects=preloadedObjects; }
            if (TestRadiance) { var probe=root.AddComponent<LiveFormProbe>();probe.RadianceOnly=true;probe.PreloadedObjects=preloadedObjects; }
            if (TestStatic) root.AddComponent<LiveFormProbe>().StaticOnly=true;
            if (TestAbyss) {var probe=root.AddComponent<LiveFormProbe>();probe.AbyssOnly=true;probe.PreloadedObjects=preloadedObjects;}
            HollowCraft.Log.Info("Mod entry point registered; runtime initialization is reported separately");
        }
    }

    internal static class Log
    {
        public static void Info(string message) => Modding.Logger.Log("[HollowCraft] " + message);
        public static void Warn(string message) => Modding.Logger.LogWarn("[HollowCraft] " + message);
        public static void Error(string message) => Modding.Logger.LogError("[HollowCraft] " + message);
        public static void Debug(string message) => Modding.Logger.LogFine("[HollowCraft] " + message);
    }
}
