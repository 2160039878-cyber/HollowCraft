using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace HollowCraft
{
    internal static class CheckpointFiles
    {
        public static string DirectoryFor(string root, int slot, string id)
        {
            if (slot < 1 || slot > 4 || !Guid.TryParseExact(id, "N", out _))
                throw new InvalidDataException("Invalid checkpoint identity");
            return Path.Combine(root, "slot-" + slot, id);
        }

        public static void Write(string path, byte[] bytes)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            string temporary = path + ".new-" + Guid.NewGuid().ToString("N");
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                stream.Write(bytes, 0, bytes.Length);
                stream.Flush(true);
            }
            if (File.Exists(path)) File.Replace(temporary, path, null);
            else File.Move(temporary, path);
        }

        public static string Hash(string path)
        {
            using (var input = File.OpenRead(path))
            using (var hash = SHA256.Create())
                return BitConverter.ToString(hash.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
        }

        public static string ReadControl(string path, bool deferBusy = false)
        {
            try
            {
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                using (var reader = new StreamReader(stream, Encoding.UTF8))
                {
                    if (stream.Length > 65536) throw new InvalidDataException("Oversized checkpoint control file");
                    return reader.ReadToEnd();
                }
            }
            catch (FileNotFoundException) { return null; }
            catch (DirectoryNotFoundException) { return null; }
            catch (IOException error) when (deferBusy && ((error.HResult & 65535) == 32 || (error.HResult & 65535) == 33))
            { return null; } // The polling caller owns the timeout; a busy reader must not block atomic replacement.
        }

        public static void Restore(string checkpoint, string destination, string expectedHash)
        {
            if (new FileInfo(checkpoint).Length > 32 * 1024 * 1024 || Hash(checkpoint) != expectedHash)
                throw new InvalidDataException("Checkpoint checksum mismatch");
            Write(destination, File.ReadAllBytes(checkpoint));
        }
    }
}
