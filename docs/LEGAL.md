# 法律、许可与来源

本项目是非官方的独立 NumPy/Python 实现；算法研究包含对专有转换器的只读逆向研究，不声称 clean-room。以下保留各里程碑的来源记录。工程资产排除与 MIT 声明不等于完整法律/专利审查结论。公开导出只含本项目源码、合成测试、通用验证工具和文档；没有将原研究 Git 历史、参考实现或私有图像带入新仓库。历史 `out/` 报告位于原工作区，不随公开项目分发。

## 2026-10-22 P1 性能来源记录

本轮在已有 NumPy 实现内调整邻域取数、五点比较交换和行块暂存，没有新增依赖或原生二进制。排序网络由合成排列/二值输入验证，与 M4 自有实现的阶段字节对照；未引入研究项目的 SIMD、任务调度、机器码或厂商常量。HiFi 行序、反馈限制和浮点公式保持原样。

基准工具仅调用用户 RAW/DCP 的公开转换接口，并通过公开 Windows 进程计数器读取资源峰值；它不调用原转换器，也不将捕获/参考 DNG 像素作为转换输入。各环境自产 DNG 完成后再对照已有文件哈希。日志、用户 DCP 的嵌入输出和性能试验均保留在本地忽略目录。工程优化不改变先前记录的法律/专利审查边界。

## 2026-10-22 M4 工程发行记录

发行物是本项目的纯 Python wheel 和源码包。默认依赖为 NumPy/rawpy，由 pip 分别安装上游发行包；本项目 wheel 不包含 LibRaw、原生库或其它依赖实现。tifffile/Pillow/scikit-image 仅为开发验证依赖。实际安装环境的包版本、声明许可及许可文件路径另记录在 `out/m4/installed-license-inventory.json`；该清单不是将全部依赖再分发为一个可执行文件的合规审查。

wheel 与 sdist 均包含本项目 MIT LICENSE、第三方通知及 Markdown 项目说明。sdist 补齐文档、合成测试、测试辅助文件和只读取用户本地材料的验证工具。实际归档通过 `tools/validate_distribution.py` 检查，拒绝 RAW/ORI/DNG/DCP、二进制、捕获/输出目录、缓存、研究交接目录及异常路径；报告与 SHA 为 `out/m4/distribution-validation.json`。源码及工具中保留来源文字与路径示例，没有包含相应参考实现或私有文件。CI 不提供真实照片或厂商 profile。

核对实际 rawpy 0.27.1 的 dist-info：其自身 LICENSE 为 MIT，LICENSE.LibRaw 为 LGPL-2.1；NumPy 及其它上游 wheel 自带附属许可/通知。Pillow 13.0.0 元数据使用 MIT-CMU，未沿用旧清单的 HPND 名称。这些依赖的独立许可不会被本项目 MIT 声明替代；如另行制作可执行文件或捆绑依赖，需要对其实际文件另行审查。本轮没有生成该类捆绑包。

这次完成本地工程打包和资产来源检查，没有上传索引、推送远程或宣称法律/专利问题已获结论。算法逆向及机身常量的来源记录继续保留；发布前法律/专利审查仍待完成，不使用 clean-room 声称。

## 2026-10-22 M3 来源记录

DNG/TIFF 字段编解码、目录构造、用户 DCP 校验和写入器均为本项目实现，依据公开 DNG/TIFF 字段约定及只读交接语义。没有使用 DNG SDK、复制 DNG 模板或厂商 writer 实现。生产仅嵌入调用者明确提供的 DCP；保留其 copyright/embed policy，policy=2 时拒绝。不捆绑、自动搜索或抽取用户软件中的 profile。

OM-1 Mark II 的小规模校准元数据依据交接的 `decoder_writer_parent/resources/camera_calibration.json`（SHA256 `9f34dd2ee32432e0b7c4df393d166664c1e91e8c851b7640585de21526f2227c`）。仅实现该机身互操作所需的三个参考增益 `(2.2030935287475586,1,1.8202753067016602)`、源日光 WB 比值公式、四位小数舍入和默认基线 0.37/1.25/1.5/1；没有复制资源 JSON、机身常量表、profile LUT 或私有 payload。增益只在匹配 Adobe 校准签名时使用。来源、必要性与真实样本边界已记录，仍不据此宣称已完成发布前法律审查。

本地真实验收由用户提供 Adobe Standard DCP（120664 字节，SHA256 `2ab8a3f338a15433040e523ed5fbd732398b5bfe15c3a0058290c6bc4fc08367`）；原文件只读、不复制进仓库。生成 DNG、DCP payload 哈希和渲染图仅在被忽略的 `out/`。`.gitignore` 另排除 `.dcp/.DCP`。仓库内 profile 测试由小型合成矩阵/数据生成，不含厂商资产。

RawTherapee 5.13、darktable 5.6.2 仅作外部 CLI 验收，不被生产代码调用或作为发行依赖。官方发行包、提取工具、为核对 PP3 键名而只读的上游源文件均保存在工作区 D 盘的忽略缓存，不进入 Git。只使用公开参数和文件接口，没有复制其 GPL 实现到 MIT 生产源码。外部应用自己的许可证仍适用于其独立分发包。

## 2026-10-22 M2 来源记录

默认 tail 以独立公式实现：连续 tone 与闭式逆函数、排序后的邻域中值引导、标准 float32 九点加权、公式生成 Gaussian PSF、两次仅 G 的 Richardson–Lucy。没有复制 LUT、SIMD/任务/内存布局或厂商二进制；生产源码只依赖 NumPy，不读取研究文件或 DCP。

只读数学参考及 SHA256：

| 文件 | SHA256 |
|---|---|
| phase6/tail_50mp_parent/tail.py | 314497ec891d9cd43826ed3ae2ae69b136861171e7cb9233978696a7f06c457f |
| phase6/tail_50mp_parent/rl.py | 7302d5ae45059bda642647cb1932e6b34d32179d6f5fc94908510b241a3722c4 |
| phase6/tail_50mp_parent/filter_adapter.py | cd084777fe364815fa3a71ffa0c41f8e793373f8f7b080198608e36a6592a898 |
| phase6/tail_50mp_parent/planar_layout.py | a38a719a44b129c968f604c27a9b5863c43471f91bf871c55bbf1a2dca60b84c |
| phase4/filter_reference/filter_reference.py | 4f51b112ebd5035bcb37cd07df6394d2154f664c8c6b0c66e33e64212cec6cfb |

隔离的 `tools/build_m2_test_oracles.py` 仅用于生成测试阶段基线：从只读研究实现取数学，在它已校验的 pre-tail fixture 上执行，并用 NumPy 替代硬件 RCP/FMA helper；未调用目标 EXE、私有 DLL 或机器码。测试用的 OS logf 属于公开系统数学原语；生产 tone 不使用此路径。预测文件只写本工作区 D 盘。研究代码没有进入发行源码，生成阶段、用户 RAW/DNG、DCP、捕获均被 Git 忽略。

ΔE 工具依据公开 DNG 矩阵转换公式，只读取参考 DNG 的矩阵/白平衡数值用于测试；没有复制 profile payload。CIEDE2000 使用已有 dev 依赖 scikit-image 0.26.0，确认测试引用 Sharma/Wu/Dalal 的公开数值对；来源链接与度量边界见 PROGRESS。M2 没有增加生产依赖或改变现有再分发许可边界。

## 2026-10-22 M1 来源记录

HiFi 四 pass 以新的对称数学和 NumPy 数组操作实现，没有复制寄存器/地址结构、机器码下放文本、厂商 LUT 或二进制。只读数值参考用于推导方向比值、九点权重及颜色恢复公式；研究材料不进入发行包。测试像素 oracle 仅在独立预测完成后读取。

M1 验收修正新增冻结/递推估计的有界中点融合，以及 pass4 的颜色反馈幅度约束。这是本项目新增的路线 B 稳定化，公式见 ALGORITHM；不是从研究任务计划或厂商实现恢复的步骤。生产仅根据本次输入计算两个估计，使用统一 128 码幅度，不读取测试 manifest、参考像素、文件身份或位置清单。未新增依赖或复制研究代码。

只读参考来源及 SHA256：

| 文件（原研究 phase6） | SHA256 |
|---|---|
| demosaic_other_passes/demosaic.c | 4953cbf73904b2b8d177fc3d71fe9fc7affae7d2269b3bd5d07bdae832174b8d |
| demosaic_other_passes/green_lowered.h | 1b65cbf67230284215a95f8d086fb9a19bf13d1e37d958fd4839f770af98556e |
| demosaic_pass2/numeric.c | cede33a37d2987234743a80eca046666a0df82e93bfa3da1a384d5607d687192 |

还只读核对了 phase3/ghidra/out/decompiled/0x14001dcf0.c（SHA256 b1db619df76ed4b0c376c305eeee7d986704f8c14339cf66648938d523fe449b），仅用来理解数学语义；没有将其文本带入项目。M1 没有新增生产依赖；分发许可/算法来源审查仍属于发布前事项。

许可摘要（研究交接的约束已落实到本仓库文档，使用源码包无需交接目录）：

要点：

- 本仓库代码：MIT（见 `LICENSE`）。
- LibRaw：上游 LGPL-2.1 / CDDL；本次 rawpy wheel 携带 LGPL-2.1 文本，依赖的实际通知/来源见 THIRD_PARTY_NOTICES。
- 本实现未使用 Adobe DNG SDK。
- **不要**提交 Adobe/Iridient DCP、原程序 EXE/DLL、反编译文本、用户 RAW/捕获图。
- 逆向算法/常量的再分发需法律审查；本文件不是法律意见。

发布前检查：

- [x] `THIRD_PARTY_NOTICES.md` 依赖清单（工程归档审查与法律结论分开）
- [x] 本项目 wheel/sdist 无 vendor DCP/EXE/DLL
- [x] 本项目 wheel/sdist 无用户 RAW/DNG 或捕获
- [x] README 写明非官方、无担保
- [ ] 律师审查（如商业化）

## 2026-10-22 M0 来源记录

新增解码使用 PyPI rawpy 0.27.1 / LibRaw 0.22.1；没有调用原转换器或导入研究模块。TIFF/EXIF/MakerNote 读取器根据字段规格重新实现，不复制参考项目的 guard、解码桥、资源或 DLL；公开字段定义来源见 ARCHITECTURE。pixel_scale 公式和 12/14 位黑电平单位参考只读交接材料，并通过三个本地 RAW 验证。

参考 CFA 和 metadata 只由本地测试工具读取；输入图像、捕获、DCP、源 MakerNote 二进制均未加入仓库。CLI 检查输出不暴露机身序列号等无关 EXIF。移除了包说明中没有过程证据支撑的 clean-room 表述。本记录不是完整法律/专利审查，不据此宣称已满足发布审核。
