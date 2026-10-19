# HollowCraft

Minecraft × Hollow Knight：在《空洞骑士》的横版世界中，以3D史蒂夫进行建造、剑术、远程战斗和红石爆破。

本仓库公开模组源码、71套共享动作、构建工具和定向回归脚本。**这是源码发布**，不包含游戏本体、游戏程序集、Minecraft运行时、存档、原版纹理、处理后的效果贴图或预渲染影片。

## 功能

- HK负责场景、敌人、血量、无敌帧、护符、灵魂和最终渲染；独立Minecraft实例运行真实方块、红石、TNT及物品逻辑。
- 剑使用HK原生移动、命中窗口、上斩、下劈和已解锁能力；其他物品保持校准后的HK移动速度与跳跃高度。
- 原生Minecraft弓/弩、盾牌、附魔与耐久。弓箭用攻击键蓄力，鼠标瞄准。
- 拉杆需要支撑；TNT影响敌我和原生地形，显示与碰撞成对更新，房间/建筑/背包绑定检查点。
- 史蒂夫覆盖普通动作以及坐姿、倒影、梦境、深渊、死亡碎片、辐光与神居的主角替身。
- 已制作9部含主角的替换影片；16个原生影片标识中，另7部无主角影片保留。影片素材不在源码仓库中。

## 实测基线

| 组件 | 版本 |
|---|---|
| 平台 | Windows，本地单人 |
| Hollow Knight | 1.5.12620 / Unity 6 |
| Modding API | 78；参考`SFGrenade/api`提交`468f579f25e63da2188f39fe5ece15c25d2854d7` |
| HK插件目标 | .NET Standard 2.1 |
| Minecraft Java | 26.3 |
| Fabric Loader / API | 0.19.5 / 0.161.0+26.3 |
| JDK / 开发工具 | JDK 25 / .NET SDK 10 / Gradle 9.7.1 |
| 桥接协议 | 25，两端必须配套构建 |

早期方案的HK 1.5.78 / API 77不是最终运行基线；其它版本未验证。

## 构建前置

使用自己合法取得的游戏和相应Modding API，在独立副本中开发。`GameManagedDir`指向该副本的`hollow_knight_Data/Managed`；Modding API引用文件位于其它目录时，另传`ModApiDir`，默认使用`GameManagedDir`。

本地还需要`assets/steve/steve.png`、`void-hand-06.png`至`void-hand-10.png`。Blender工具使用`diamond_sword.png`。这些贴图不属于本仓库的MIT代码授权范围，已被Git忽略。

如果已有相应HollowCraft开发版，可从自己的本地模组读取六张嵌入图片，并从自己的Minecraft客户端JAR读取钻石剑纹理：

```powershell
pwsh -File tools/Import-LocalAssets.ps1 `
  -HollowCraftDll 'X:/HollowCraft/hollow_knight_Data/Managed/Mods/HollowCraft/HollowCraft.dll' `
  -MinecraftClientJar 'X:/Minecraft/minecraft-client.jar'
```

导入工具需要PowerShell 7.4+，只读取指定的本地输入，拒绝覆盖不同内容的贴图。**缺少这些本地开发资源时，干净克隆不能直接生成完整模组。** 本仓库不提供资源下载或游戏认证绕过。

本次为纯文本源码发布，Gradle Wrapper JAR不随仓库提供。安装官方Gradle 9.7.1后，在首次构建时生成Wrapper；生成文件和构建缓存均不提交到仓库。

```powershell
dotnet build host/HollowCraft.csproj -c Release `
  -p:GameManagedDir='X:/HollowCraft/hollow_knight_Data/Managed'

$env:JAVA_HOME='X:/JDK25'
Push-Location minecraft
gradle wrapper --gradle-version 9.7.1 --distribution-type bin `
  --gradle-distribution-sha256-sum acd53f1edaf02f1a8ff99879f8a34b302661a057d9b063ae9e35b552f804d20a
./gradlew.bat --no-daemon jar
Pop-Location
```

产物为`host/bin/Release/netstandard2.1/HollowCraft.dll`和`minecraft/build/libs/hollowcraft-0.1.1.jar`。

## 目录与工具

| 路径 | 内容 |
|---|---|
| `host/` | HK桥接、控制、伤害、地形、检查点和角色渲染 |
| `minecraft/src/` | Fabric客户端/服务端及原生物品、碰撞适配 |
| `assets/steve/` | 模型、动作和专用角色几何映射JSON |
| `tools/` | 本地启动、资源处理、Blender制作和打包 |
| `tools/portable/` | 独立副本安装、启动、归档卸载和恢复脚本 |
| `tests/` | 核心规则与实际遥测的定向检查 |
| `licenses/` | 上游许可证及归属 |

`tools/export_backend.py`导出Loom已经解析完成的本地运行时；`tools/build_portable.py`组合明确提供的本地游戏、API、影片和校验清单。这些输入不随仓库提供。

`tools/render_*cinematic.py`依赖本地源帧、遮罩、背景板与追踪文件。公开快照排除了`assets/cinematics/`，制作脚本不能在干净克隆中直接生成影片。

## 操作

沿用HK移动、跳跃、攻击和冲刺键位；`1–9/滚轮`换物品，`E`打开背包，鼠标挖掘/放置/瞄准。弓箭通过HK攻击键蓄力；装备副手盾后按使用键格挡。`F8`打开房间还原和安全返回工具。

## 验证范围

项目以隔离存档和分阶段场景验收，未完成连续新档全流程或全部房间验证。开发探针只在明确的测试模式运行，可准备剧情入口、奖励状态或Boss末期；部分剧情测试使用临时保护。普通启动不会自动战斗。黄蜂无伤演示是单独验证的自动按键实机片段。

核心检查：`dotnet run --project tests/CoreChecks.csproj`。`tests/analyze_*.py`需要各自对应的真实遥测文件；私人存档、日志与录像不随仓库发布。

## 致谢与授权

复用了[RepoCraft](https://github.com/petmav/RepoCraft)及其上游[SkyCraft](https://github.com/chasmlol/SkyCraft)，并参考[HalfCraft](https://github.com/whiskydumb/halfcraft)的代理和爆炸归属设计。版权及许可证保留在`LICENSE`、`THIRD-PARTY-NOTICES.md`与`licenses/`。

代码以MIT许可提供；Hollow Knight、Minecraft及其原版/派生游戏资源保留各权利人的权利。这是非官方实验模组。开发与素材制作包含GPT-6 Astra辅助工作；历史目标计数和API等价费用估算不等于实际账单。
