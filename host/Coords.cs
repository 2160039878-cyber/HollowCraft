using UnityEngine;

namespace HollowCraft
{
    internal static class Coords
    {
        public static float K = 1.2f;
        public static double OffsetX;
        public static double PlaneZ = 0.5;
        public static float Depth;
        public static Vector3 ToMcF(Vector3 value) => new Vector3(
            (float)(value.x * K + OffsetX), value.y * K, (float)(PlaneZ - (value.z - Depth) * K));
        public static void ToMc(Vector3 value, out double x, out double y, out double z)
        {
            x = value.x * (double)K + OffsetX;
            y = value.y * (double)K;
            z = PlaneZ - (value.z - Depth) * (double)K;
        }
        public static Vector3 ToUnity(double x, double y, double z) => new Vector3(
            (float)((x - OffsetX) / K), (float)(y / K), Depth + (float)((PlaneZ - z) / K));
        public static Vector3 ToUnity(Vector3 value) => ToUnity(value.x, value.y, value.z);
    }
}
