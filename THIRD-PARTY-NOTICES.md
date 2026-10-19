# HollowCraft third-party notices

The shared-memory transport, Minecraft rendering/collision export, and triangle-clipping code
are adapted from [RepoCraft](https://github.com/petmav/RepoCraft/tree/eaa90c39ddaeb5e187ba56d56f306f91922d361a),
which includes work from [SkyCraft](https://github.com/chasmlol/SkyCraft).
Their original copyright and MIT terms remain in `LICENSE` and `licenses/RepoCraft/LICENSE`.
The unmodified upstream distribution notice is archived under `licenses/RepoCraft/`;
it describes RepoCraft's distribution, rather than the contents of this project.

| Dependency | Version used | License file |
|---|---|---|
| Hollow Knight Modding API | SFGrenade/api commit `468f579f25e63da2188f39fe5ece15c25d2854d7` | `licenses/HK-Modding-API/LICENSE` (MIT) |
| Fabric Loader | 0.19.5 | `licenses/Fabric-Loader-0.19.5/LICENSE_fabric-loader` (Apache-2.0) |
| Fabric API | 0.161.0+26.3 | `licenses/Fabric-API-0.161.0+26.3/LICENSE-fabric-api` (Apache-2.0) |

[HalfCraft](https://github.com/whiskydumb/halfcraft/tree/24141e9c4ac22440805cd947efa760e2c69a1247)
is a design reference for actor proxies and explosion ownership. Game-specific dependencies,
Discord presence, and remote multiplayer publishing from the upstream adaptation are not used.

Hollow Knight and Minecraft assets retain their respective owners' rights.
The project uses the user's isolated game copies; source files and mod binaries do not include a full game distribution.

The Gradle wrapper is distributed under Apache-2.0; its bundled license is retained in `licenses/Gradle/LICENSE`.
This public source snapshot excludes game textures, cinematics, game assemblies, saves and runtime distributions. `tools/Import-LocalAssets.ps1` reads required textures from the developer's existing local inputs.
