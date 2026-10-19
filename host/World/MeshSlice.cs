// Adapted from RepoCraft MeshCutter; see THIRD-PARTY-NOTICES.md and vendor licenses.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace HollowCraft.World
{
    internal sealed class MeshSlice
    {
		private sealed class MeshData
		{
			public Vector3[] Pos;
			public Vector3[] Nrm;
			public Vector4[] Tan;
			public Color32[] Col;
			public Vector4[][] Uv = new Vector4[4][];
			public int[][] Sub; // triangle lists
			public bool Failed;
		}

        private readonly Dictionary<Mesh, MeshData> data = new Dictionary<Mesh, MeshData>();
        public void Clear() => data.Clear();
        public Mesh Build(Mesh original, Matrix4x4 l2w, List<Clip.Box> boxes)
        {
            var src = Read(original);
            if (src == null || src.Failed) throw new InvalidOperationException("Unreadable terrain mesh " + original.name);
			var pos = new List<Vector3>();
			var nrm = src.Nrm != null ? new List<Vector3>() : null;
			var tan = src.Tan != null ? new List<Vector4>() : null;
			var col = src.Col != null ? new List<Color32>() : null;
			var uv = new List<Vector4>[4];
			for (int c = 0; c < 4; c++)
			{
				uv[c] = src.Uv[c] != null ? new List<Vector4>() : null;
			}
			var subs = new List<int>[src.Sub.Length];
			var pieces = new List<List<Clip.Vert>>();
			var near = new List<Clip.Box>();
			int cutCount = 0;
			for (int s = 0; s < src.Sub.Length; s++)
			{
				var tris = src.Sub[s];
				var output = subs[s] = new List<int>(tris.Length);
				for (int i = 0; i + 2 < tris.Length; i += 3)
				{
					int ia = tris[i], ib = tris[i + 1], ic = tris[i + 2];
					Vector3 a = Coords.ToMcF(l2w.MultiplyPoint3x4(src.Pos[ia])), b = Coords.ToMcF(l2w.MultiplyPoint3x4(src.Pos[ib])), c = Coords.ToMcF(l2w.MultiplyPoint3x4(src.Pos[ic]));
					Vector3 tlo = Vector3.Min(a, Vector3.Min(b, c)), thi = Vector3.Max(a, Vector3.Max(b, c));
					near.Clear();
					foreach (var box in boxes)
					{
						if (thi.x >= box.LoX && tlo.x <= box.HiX && thi.y >= box.LoY && tlo.y <= box.HiY && thi.z >= box.LoZ && tlo.z <= box.HiZ)
						{
							near.Add(box);
						}
					}
					if (near.Count == 0)
					{
						int baseIndex = pos.Count;
						Emit(src, ia, ib, ic, 1, 0, 0, pos, nrm, tan, col, uv);
						Emit(src, ia, ib, ic, 0, 1, 0, pos, nrm, tan, col, uv);
						Emit(src, ia, ib, ic, 0, 0, 1, pos, nrm, tan, col, uv);
						output.Add(baseIndex);
						output.Add(baseIndex + 1);
						output.Add(baseIndex + 2);
						continue;
					}
					pieces.Clear();
					Clip.Subtract(Clip.FromTriangle(a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z), near, pieces);
					cutCount++;
					foreach (var piece in pieces)
					{
						int first = pos.Count;
						foreach (var v in piece)
						{
							Emit(src, ia, ib, ic, v.B0, v.B1, v.B2, pos, nrm, tan, col, uv);
						}
						for (int k = 1; k + 1 < piece.Count; k++)
						{
							output.Add(first);
							output.Add(first + k);
							output.Add(first + k + 1);
						}
					}
				}
			}
			if (cutCount == 0)
			{
				return null;
			}
			var mesh = new Mesh { name = original.name + " (HollowCraft cut)" };
			mesh.Clear();
			mesh.indexFormat = pos.Count > 65000 ? IndexFormat.UInt32 : IndexFormat.UInt16;
			mesh.SetVertices(pos);
			if (nrm != null) mesh.SetNormals(nrm);
			if (tan != null) mesh.SetTangents(tan);
			if (col != null) mesh.SetColors(col);
			for (int c = 0; c < 4; c++)
			{
				if (uv[c] != null) mesh.SetUVs(c, uv[c]);
			}
			mesh.subMeshCount = subs.Length;
			for (int s = 0; s < subs.Length; s++)
			{
				mesh.SetTriangles(subs[s], s, false);
			}
			mesh.RecalculateBounds();
			return mesh;
		}
		private static void Emit(MeshData d, int a, int b, int c, float wa, float wb, float wc, List<Vector3> pos, List<Vector3> nrm, List<Vector4> tan, List<Color32> col, List<Vector4>[] uv)
		{
			pos.Add(d.Pos[a] * wa + d.Pos[b] * wb + d.Pos[c] * wc);
			nrm?.Add((d.Nrm[a] * wa + d.Nrm[b] * wb + d.Nrm[c] * wc).normalized);
			if (tan != null)
			{
				Vector4 t = d.Tan[a] * wa + d.Tan[b] * wb + d.Tan[c] * wc;
				Vector3 t3 = new Vector3(t.x, t.y, t.z).normalized;
				tan.Add(new Vector4(t3.x, t3.y, t3.z, d.Tan[a].w));
			}
			if (col != null)
			{
				Color ca = d.Col[a], cb = d.Col[b], cc = d.Col[c];
				col.Add(ca * wa + cb * wb + cc * wc);
			}
			for (int ch = 0; ch < 4; ch++)
			{
				var u = d.Uv[ch];
				if (u != null)
				{
					uv[ch].Add(u[a] * wa + u[b] * wb + u[c] * wc);
				}
			}
		}

		// ---- reading a mesh (CPU if it's readable, GPU readback otherwise) ------------------------

		private MeshData Read(Mesh mesh)
		{
			if (data.TryGetValue(mesh, out var d))
			{
				return d;
			}
			d = new MeshData();
			data[mesh] = d;
			try
			{
				if (mesh.isReadable)
				{
					ReadCpu(mesh, d);
				}
				else
				{
					ReadGpu(mesh, d);
				}
			}
			catch (Exception e)
			{
				d.Failed = true;
				Log.Warn($"mesh cutter: couldn't read {mesh.name} ({e.Message}); it isn't cut");
			}
			if (d.Failed) throw new InvalidOperationException("Cannot read terrain mesh " + mesh.name);
			return d;
		}

		private static void ReadCpu(Mesh mesh, MeshData d)
		{
			d.Pos = mesh.vertices;
			var n = mesh.normals;
			d.Nrm = n != null && n.Length == d.Pos.Length ? n : null;
			var t = mesh.tangents;
			d.Tan = t != null && t.Length == d.Pos.Length ? t : null;
			var c = mesh.colors32;
			d.Col = c != null && c.Length == d.Pos.Length ? c : null;
			for (int ch = 0; ch < 4; ch++)
			{
				var list = new List<Vector4>();
				mesh.GetUVs(ch, list);
				d.Uv[ch] = list.Count == d.Pos.Length ? list.ToArray() : null;
			}
			d.Sub = new int[mesh.subMeshCount][];
			for (int s = 0; s < mesh.subMeshCount; s++)
			{
				d.Sub[s] = mesh.GetSubMesh(s).topology == MeshTopology.Triangles ? mesh.GetTriangles(s) : new int[0];
			}
		}

		private static void ReadGpu(Mesh mesh, MeshData d)
		{
			int vertexCount = mesh.vertexCount;
			var attrs = mesh.GetVertexAttributes();
			var streams = new Dictionary<int, byte[]>();
			foreach (var a in attrs)
			{
				if (streams.ContainsKey(a.stream))
				{
					continue;
				}
				using (var vb = mesh.GetVertexBuffer(a.stream))
				{
					var bytes = new byte[vb.count * vb.stride];
					vb.GetData(bytes);
					streams[a.stream] = bytes;
				}
			}
			foreach (var a in attrs)
			{
				byte[] buf = streams[a.stream];
				int stride = mesh.GetVertexBufferStride(a.stream);
				int offset = mesh.GetVertexAttributeOffset(a.attribute);
				switch (a.attribute)
				{
					case VertexAttribute.Position:
						d.Pos = new Vector3[vertexCount];
						for (int i = 0; i < vertexCount; i++) d.Pos[i] = Decode(buf, i * stride + offset, a.format, a.dimension);
						break;
					case VertexAttribute.Normal:
						d.Nrm = new Vector3[vertexCount];
						for (int i = 0; i < vertexCount; i++) d.Nrm[i] = Decode(buf, i * stride + offset, a.format, a.dimension);
						break;
					case VertexAttribute.Tangent:
						d.Tan = new Vector4[vertexCount];
						for (int i = 0; i < vertexCount; i++) d.Tan[i] = Decode(buf, i * stride + offset, a.format, a.dimension);
						break;
					case VertexAttribute.Color:
						d.Col = new Color32[vertexCount];
						for (int i = 0; i < vertexCount; i++)
						{
							Vector4 c = Decode(buf, i * stride + offset, a.format, a.dimension);
							d.Col[i] = new Color(c.x, c.y, c.z, a.dimension > 3 ? c.w : 1f);
						}
						break;
					case VertexAttribute.TexCoord0:
					case VertexAttribute.TexCoord1:
					case VertexAttribute.TexCoord2:
					case VertexAttribute.TexCoord3:
					{
						int ch = a.attribute - VertexAttribute.TexCoord0;
						var uv = d.Uv[ch] = new Vector4[vertexCount];
						for (int i = 0; i < vertexCount; i++) uv[i] = Decode(buf, i * stride + offset, a.format, a.dimension);
						break;
					}
				}
			}
			if (d.Pos == null)
			{
				throw new InvalidOperationException("no positions");
			}
			int[] indices;
			using (var ib = mesh.GetIndexBuffer())
			{
				indices = new int[ib.count];
				if (mesh.indexFormat == IndexFormat.UInt16)
				{
					var shorts = new ushort[ib.count];
					ib.GetData(shorts);
					for (int i = 0; i < shorts.Length; i++) indices[i] = shorts[i];
				}
				else
				{
					ib.GetData(indices);
				}
			}
			d.Sub = new int[mesh.subMeshCount][];
			for (int s = 0; s < mesh.subMeshCount; s++)
			{
				var sm = mesh.GetSubMesh(s);
				if (sm.topology != MeshTopology.Triangles)
				{
					d.Sub[s] = new int[0];
					continue;
				}
				var list = new int[sm.indexCount];
				for (int i = 0; i < sm.indexCount; i++)
				{
					list[i] = indices[sm.indexStart + i] + sm.baseVertex;
				}
				d.Sub[s] = list;
			}
		}

		private static Vector4 Decode(byte[] b, int at, VertexAttributeFormat format, int dim)
		{
			var v = new Vector4(0, 0, 0, 1);
			for (int i = 0; i < dim && i < 4; i++)
			{
				float x;
				switch (format)
				{
					case VertexAttributeFormat.Float32: x = BitConverter.ToSingle(b, at + i * 4); break;
					case VertexAttributeFormat.Float16: x = Mathf.HalfToFloat(BitConverter.ToUInt16(b, at + i * 2)); break;
					case VertexAttributeFormat.UNorm8: x = b[at + i] / 255f; break;
					case VertexAttributeFormat.SNorm8: x = Mathf.Max((sbyte)b[at + i] / 127f, -1f); break;
					case VertexAttributeFormat.UNorm16: x = BitConverter.ToUInt16(b, at + i * 2) / 65535f; break;
					case VertexAttributeFormat.SNorm16: x = Mathf.Max(BitConverter.ToInt16(b, at + i * 2) / 32767f, -1f); break;
					case VertexAttributeFormat.UInt8: x = b[at + i]; break;
					case VertexAttributeFormat.SInt8: x = (sbyte)b[at + i]; break;
					case VertexAttributeFormat.UInt16: x = BitConverter.ToUInt16(b, at + i * 2); break;
					case VertexAttributeFormat.SInt16: x = BitConverter.ToInt16(b, at + i * 2); break;
					case VertexAttributeFormat.UInt32: x = BitConverter.ToUInt32(b, at + i * 4); break;
					case VertexAttributeFormat.SInt32: x = BitConverter.ToInt32(b, at + i * 4); break;
					default: x = 0f; break;
				}
				v[i] = x;
			}
			return v;
		}
	}
}
