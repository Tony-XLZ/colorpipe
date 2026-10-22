# 公开验证说明

本次独立包重新安装后的 197 项回归与输出身份结果见 [RELEASE](RELEASE.md)。

本文件保留按阶段书写的历史验收记录。较早段落中的未完成事项描述当时状态，当前范围以 README 和末尾 P1 为准。导出来源为优化里程碑 `perf-hifi` / 本地提交 `b078c3f079bcbdd47db32f11409737483ca7aac5`；该提交不在公开仓库的新历史中。

真实样本、DCP、原始参考代码/捕获和完整报告不公开；`out/` 与 `.cache/` 是原工作区私有证据位置，并非公开下载链接。下列真实数值为本机三样本记录，外部读者需要相同的授权资料才能重做 oracle 对照。公开仓库独立构建/运行及 185 项合成测试不需要这些资料。

# 进度

## 里程碑

- [x] M0 解码：LibRaw → CFA + metadata（三个本地样本验收）
- [x] M1 归一化 + HiFi 4-pass（三个真实样本均通过严格 max<200）
- [x] M2 默认彩色 tail（三个真实 RAW 的阶段、最终像素、SSIM 与固定矩阵 ΔE00 验收）
- [x] M3 DNG writer、用户 DCP、元数据与外部读取/渲染（三个真实样本）
- [ ] M4 CLI + 测试 + 文档

## 记录

| 日期 | 阶段 | 结果 | PSNR/ΔE | 备注 |
|---|---|---|---|---|
| 2026-10-22 | M0 | 50 项测试通过；三个真实 RAW 的 CFA 全幅零差异，12 项参考元数据一致 | CFA PSNR=∞，最大误差=0；ΔE 不适用于本阶段 | Python 3.14.0 / rawpy 0.27.1 / LibRaw 0.22.1 |
| 2026-10-22 | M1 初次验收 | 归一化和四 pass 实现；严格验收 2/3 | RGB PSNR 108.75 / 106.76 / 118.05 dB；max 285 / 193 / 46 | 历史 RED；70 passed / 1 failed；结果保留 |
| 2026-10-22 | M1 修正验收 | 保留自有确定性行序，加入全图统一反馈稳定化；严格验收 3/3 | RGB PSNR 94.64 / 92.47 / 105.60 dB；max 198 / 191 / 128 | 74 passed；未放宽 max<200，未加入坐标或样本补丁 |
| 2026-10-22 | M2 | 默认 WB/tone/filter/G+diff/G-only RL/逆 tone/量化；三个 RAW 验收 3/3 | RGB PSNR 92.58 / 92.07 / 105.50 dB；max 728 / 510 / 176；平均 ΔE00 0.00603 / 0.00828 / 0.00104 | 116 passed；M1 max<200 继续单独通过；ΔE 为固定 D50 矩阵诊断 |
| 2026-10-22 | M2 补充验收 | 补齐 SSIM 门槛并重跑三个 RAW；全部指标复现 | SSIM 0.999999546 / 0.999999352 / 0.999999970；PSNR/max/ΔE 不变 | M0–M2 124 passed；24 个阶段文件 SHA 相同 |
| 2026-10-22 | M3 | 三个 DNG 回读零差异；36 项关键 tag、15 项 DCP payload；RawTherapee/darktable 实际导出 | 完整 DCP 渲染 PSNR 76.61 / 76.09 / 89.18 dB；RGB max 2063 / 1998 / 749；平均 ΔE00 0.01252 / 0.01434 / 0.00197 | 全量 160 passed；最终单测 149 passed；M1/M2 不回归 |
| | M4 | | | |

## 已知差异

- 参考实现是逐 bit；路线 B 是视觉等价。
- 不复制 task order / 64B pitch / FMA 分组。
- 完整 EXIF/XMP 不追求恒等。

## M0 实测

所有尺寸按宽×高。完整 CFA 在解码后保持传感器码值；处理尺寸仅报告每边去掉 2 像素后的结果，本阶段未裁切、旋转、去黑或插值。

| 样本 | 完整 CFA | 处理尺寸 | 有效位深 | 四相位黑/白电平（各相位相同） | ISO | WB（R,G,B，G=1） |
|---|---|---|---|---|---|---|
| P7262257.ORF | 5220×3912 | 5216×3908 | 12 | 254 / 4095 | 200 | 2.75, 1, 1.4296875 |
| P7262256.ORI | 5220×3912 | 5216×3908 | 12 | 254 / 4095 | 200 | 2.3046875, 1, 1.734375 |
| P7262256.ORF | 8172×6132 | 8168×6128 | 14 | 1016 / 16383 | 200 | 2.3046875, 1, 1.734375 |

- 三个样本均为 RGGB；源文件、参考元数据和参考 CFA 均校验 SHA-256。
- 共比较 90,951,984 个传感器样本，三个样本的 mismatches=0、max_abs=0、MSE=0、PSNR=∞。这些是解码指标，不代表最终 DNG 的视觉验收。
- 相机建议裁切（x,y,w,h）：20MP 为 (12,12,5184,3888)，50MP 为 (6,6,8160,6120)，与去马赛克边界不同。
- 焦平面对角线来自 MakerNote Equipment 0x0103，三个源文件均为 2160/100 mm；pixel_scale=43.2/21.6=2。不是固定默认值。
- 50MP 的 LibRaw 相机通道白点为 16380；传感器 ValidBits 上限为 16383。M0 使用后者与参考传感器码值保持同一量纲，单独保留前者。
- 原始 WB 的第四项 0 是 LibRaw 未使用项；RGB 与源 MakerNote 验证后才对外提供。

复现命令见 README。机器相关报告位于 `out/m0/validation.json`，JUnit 位于 `out/m0/pytest.xml`；均被 Git 忽略，不分发用户图像或原始参考材料。

## M0 修复与证据

- 从完整 `raw_image` 解码并复制 buffer，关闭 rawpy 后数组仍有效；根据 `raw_color` 的完整传感器坐标和 EXIF 双重验证 RGGB。
- 将 LibRaw RGBG 通道电平转换成 R,G1,G2,B；验证 MakerNote 的 12→14 位单位转换，明确拒绝不一致值。
- 将白平衡传入 RawImage；从源 EXIF 读取 ISO，从焦平面对角线计算 pixel_scale；合成测试使用 ISO800 / pixel_scale2.4，防止硬编码回归。
- 元数据读取有文件及 MakerNote 边界检查，未知机身/CFA、缺失标签、非正 WB、无效分母和不支持的字段形式均报错。
- ValidBits/CropLeft/CropTop 实际是 SHORT[2]；支持第二项为 0 的已验证形式，对其它形式明确拒绝。
- 47 项不依赖用户照片的测试 + 3 项真实 RAW 集成测试通过。初始失败、SHORT[2]、WB 通道映射回归失败和 pytest 参数冲突日志保留在工作区 `.cache/`。

M0 完成后推进了 M1；M1 及本轮 M2 的实现和验收记录如下，M3–M4 仍未完成。

## M1 修正后的全幅阶段结果

每格为 PSNR dB / 最大绝对差。除 normalize 使用峰值 1 外，其它阶段峰值均为 65535。统计包含完整处理域及全部边界，无误差 mask；pass3 只比较该阶段新补的相反 R/B 通道。

| 阶段 | P7262257.ORF | P7262256.ORI | P7262256.ORF 50MP |
|---|---|---|---|
| 线性归一化（量化参考） | 107.13 / 7.632e-6 | 106.90 / 7.665e-6 | 107.12 / 7.636e-6 |
| prepared CFA16 | 148.53 / 1 | 129.82 / 1 | 136.12 / 1 |
| pass1 G | 135.28 / 1 | 125.65 / 2 | 130.36 / 2 |
| pass2 G | 93.72 / 187 | 93.78 / 191 | 109.58 / 118 |
| pass3 opposite R/B | 124.62 / 52 | 110.61 / 96 | 116.26 / 46 |
| pass4 全 RGB | 94.64 / 198 | 92.47 / 191 | 105.60 / 128 |

线性归一化以 `prepared.cfa16/65535` 为量化后的同阶段基线：满足 PSNR>60，但不是尚未捕获的原始 float CFA oracle；没有与后级 0x31560 RGB float 平面混比。最终 RGB 的三个 PSNR 均超过 40 dB，三个最大误差均严格 <200。共比较 272,465,280 个 RGB 通道样本，**误差 ≥200 的样本数为 0**；包括所有边界、任务交界行和通道。

| 最终 RGB 分通道最大差 | R | G | B | 全幅 MAE | 全幅 RMSE |
|---|---|---|---|---|---|
| P7262257.ORF | 130 | 187 | 198 | 0.220883 | 1.214199 |
| P7262256.ORI | 132 | 191 | 136 | 0.312080 | 1.558874 |
| P7262256.ORF 50MP | 106 | 118 | 128 | 0.041129 | 0.343746 |

## M1 修正方法与已知差异

- 原有九点核的方向、二阶系数和反绝对差权重没有算术错误。20MP ORF 初次验收的 G=285、B=261 主要由原地反馈的行序差异引起。原始失败位置为输出 (y=2324,x=3679)，对应 RAW y=2326 的参考任务起点；坐标仅用于诊断，没有进入生产代码。
- 保留原有全局从上到下递推轨迹 `R`。使用相同九点核另算冻结 pass1 邻域候选 `J`，最终 G 为 `R+clip((J-R)/2,-128,128)`，再截断为 uint16。融合输出不反馈到递推轨迹，因此没有替换为参考行序。只需保留独立 G 平面和上一行原始快照。
- pass3 只依赖未被 pass2 改动的非 G 站点，阶段输出与初次验收逐样本相同。pass4 分别计算递推中心和融合中心的颜色比值，再将颜色改动限制到递推估计的 ±128 码，防止 G 的小变化被权重放大。原生 R/B、边界回退、归一化和 pass1 保持原有契约。
- 128 是 16 位工作域中半个 8 位步长，作为所有样本/位深/位置统一的改动幅度。它限制相对本实现递推锚的变化，**不是相对 oracle 的误差限值**。验收仍独立使用原有 PSNR>60 / RGB PSNR>40 / RGB max<200，没有 mask、xfail、裁边或更宽门槛。
- 这是路线 B 新增的有界反馈融合，不能宣称是原核的逐 bit 重现。均匀冻结、均匀减弱反馈、无界中点和只限制 G 的试验均不能通过完整 RGB 门槛；这些探针保留在工作区 `.cache/`，没有成为按样本选择的生产分支。
- 稳定化改善峰值误差，同时增加了相对参考的小残差：最终 RGB PSNR 从 108.75 / 106.76 / 118.05 降至 94.64 / 92.47 / 105.60 dB；50MP 最大误差从 46 增至 128。没有声称全部指标同时改善，也不承诺任意新图像、ISO 或参考调度满足 <200。
- 仅在测试工具中，使用**本实现独立预测的 pass1 G**重放 manifest 的观测行序：未融合九点核的三个样本 pass2 最大误差仍均为 2，PSNR 为 132.23、124.82、128.54 dB。该结果不包含新增稳定化，不是生产验收结果；没有注入参考 G，也不提供生产调度选项。
- prepared CFA 的 1 码差来自线性 float 阶段后的再次量化与参考直接缩放的舍入差；pass1 的 1–2 码差还包含正常 float32 求和重排和截断影响。没有复刻 SIMD/FMA 或精确运算分组。
- 已修正电平 uint16 加法溢出、输入 shape/dtype 验证、工作 epsilon 单位，以及后续 tail 再次减黑的错误接口说明。
- 交接摘要的 0x31560 阶段归属、pass1 单条 0.375 公式及 pass2 的 0.66 描述与验证数值参考不符；修正公式见 ALGORITHM。

M1 现已完成三个交接样本的阶段验收。M2 默认 tail、DCP/DNG 色彩和最终 ΔE 仍在后续范围；本轮不把线性去马赛克指标当作最终 DNG 验收。

## M1 复现与产物

- `out/m1/feedback-stable/validation.json`：最新阶段及通道指标、输入/参考 SHA、源码 SHA、耗时、稳定化参数和测试专用行序诊断。所有预测先从真实 RAW 独立生成，再打开参考像素。
- `out/m1/feedback-stable/diagnostic_crops.png`：三个当前最差残差位置的 100% 参考/预测/128 倍误差图；相同 WB/gamma，无 DCP，不代表最终 DNG 色彩。
- `out/m1/feedback-stable/edges/diagnostic_crops.png`：参考 G 的 16 像素网格上最大轴向梯度位置；选择方法和坐标在同目录 `locations.json`。与最差位置两组裁切均未观察到明显新增拉链或伪色；该判断仅覆盖所示局部及显示变换。
- `out/m1/feedback-stable-pytest.xml`：74 项完整测试全部通过，包括原 M0 三个真实样本与 M1 三个严格验收。新增三项合成回归覆盖冻结快照、递推轨迹不被融合污染，以及颜色权重放大；先 RED 后 GREEN，日志位于 `.cache/m1-stability-red.log`。
- 独立工具和集成测试分别从三个 RAW 完整预测一次，两次运行的 prepared CFA、pass1/2/3/4 输出 SHA-256 全部一致；prepared CFA、pass1、pass3 也与历史未融合版本的输出 SHA-256 一致。
- 历史初始 RED、失败输出与指标保留在 `out/m1/attempt01/`、`out/m1/final/`、`out/m1/pytest.xml` 和工作区 `.cache/`。报告和图像均被 Git 忽略，用户 RAW 不进入仓库。

复现命令见 README。当前四 pass 数学约 4–5 秒/20MP、12–13 秒/50MP（不含解码、验证和文件写入；具体耗时见报告）；多保留一个 uint16 G 平面，没有新增生产依赖。

## M2 全幅阶段结果

M2 从三个真实 RAW 重新解码并运行当前 M1，再进入默认 tail。所有活动像素、边界和通道均纳入统计，共 90,821,760 个像素、272,465,280 个 RGB 通道样本。没有坐标修补或误差 mask。M1 行序与稳定化未改动；本轮重新得到其最大误差 198 / 191 / 128，继续严格 <200。

下表每格为 PSNR dB / 最大绝对差。float 阶段峰值为 1，最终 uint16 阶段峰值为 65535。float 行对照隔离生成的**便携研究数学参考**；最终 RGB 直接对照 `tail_50mp_recheck/parent_acceptance.json` 的 plain20 / ori20 / orf50 对应原 DNG 像素。

| 阶段 | P7262257.ORF | P7262256.ORI | P7262256.ORF 50MP |
|---|---|---|---|
| normalized RGB | 94.64 / 0.00302128 | 92.47 / 0.00291447 | 105.60 / 0.00195315 |
| WB + forward tone | 83.94 / 0.01211566 | 80.14 / 0.01950103 | 93.47 / 0.00621042 |
| filtered RGB | 84.42 / 0.01368421 | 80.91 / 0.02028694 | 95.67 / 0.00545251 |
| G/DR/DB | 89.21 / 0.00684184 | 85.91 / 0.01023611 | 100.33 / 0.00262135 |
| G-only RL 后 | 87.88 / 0.00778109 | 85.07 / 0.01023611 | 99.46 / 0.00262135 |
| inverse tone / undo WB | 92.60 / 0.01112002 | 92.08 / 0.00778210 | 105.63 / 0.00267273 |
| 最终 RGB16 / 原 DNG | **92.58 / 728** | **92.07 / 510** | **105.50 / 176** |

`filtered_rgb` 的参考由便携的 RL 前 G/DR/DB 代数恢复，可能额外含一次 float32 舍入；报告明确标记推导来源，没有当成直接原生捕获。其余五个 float 阶段保存完整独立参考文件和 SHA。

| 最终 RGB 分通道最大差 | R | G | B | MAE | RMSE |
|---|---|---|---|---|---|
| P7262257.ORF | 489 | 728 | 400 | 0.323563 | 1.539182 |
| P7262256.ORI | 510 | 366 | 326 | 0.395550 | 1.632090 |
| P7262256.ORF 50MP | 95 | 176 | 113 | 0.049423 | 0.347779 |

M2 按交接的 tail/最终像素目标检查 PSNR>40、平均 ΔE00<2、p95<4。交接的 max<200 是 T2 去马赛克门槛，本轮对 M1 独立保持；tail 最大误差如实报告，没有把 728/510 宣称为 <200，也没有修改原 M1 断言。

## M2 ΔE00 的定义与结果

相机 RGB 没有直接当作 sRGB 输入 Lab。测试读取各参考 DNG 的 ForwardMatrix2、CameraCalibration2、AnalogBalance、AsShotNeutral，固定使用第二组矩阵：

```text
I = inverse(diag(AnalogBalance) * CameraCalibration2)
reference_neutral = I * AsShotNeutral
camera_to_XYZ_D50 = ForwardMatrix2 * diag(1/reference_neutral) * I
```

同一个转换同时用于预测和参考，转 D50、2° observer 的 Lab，再用 scikit-image 0.26.0 的 CIEDE2000（kL=kC=kH=1）。不做曝光拟合、像素筛选或 XYZ gamut clipping。均值/最大值累加 float64；p95/p99 来自完整分辨率 float32 ΔE 图，没有抽样。矩阵定义参考 [Adobe DNG 1.7.1，第 103 页](https://helpx.adobe.com/content/dam/help/en/camera-raw/digital-negative/jcr_content/root/content/flex/items/position/position-par/download_section_733958301/download-1/DNG_Spec_1_7_1_0.pdf)，ΔE 实现用 [Sharma/Wu/Dalal 的确认数据](https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/)首组 2.0425 验证。

| 样本 | 平均 ΔE00 | p95 | p99 | 最大值 | ΔE00≥2 像素数 |
|---|---|---|---|---|---|
| P7262257.ORF | 0.006029 | 0.032966 | 0.070295 | 2.081843 | 2 |
| P7262256.ORI | 0.008280 | 0.047058 | 0.109274 | 2.465148 | 2 |
| P7262256.ORF 50MP | 0.001043 | 0.006150 | 0.025385 | 0.792083 | 0 |

三个样本均通过均值和 p95 门槛，但两个 20MP 样本各有 2 个像素达到 2。该固定矩阵指标没有双光源插值、DCP HueSatMap/LookTable、渲染 tone，不能代替 M3/M4 的 DCP 应用和外部 RAW 软件外观验收。

## M2 参考覆盖与因果诊断

- 原 parent 清单保留所有阶段 SHA，但不是全部阶段像素。`build_m2_test_oracles.py` 在隔离进程中，只读研究实现和已校验的参考前端输入，生成五个 float 阶段及最终便携像素；用 NumPy 除法、float64 乘加后转 float32 替代硬件 RCP/FMA helper。未加载原代码、私有 DLL 或 DCP。生产库不导入此工具或研究代码。
- 便携参考本身与原 DNG 的最终差异为 PSNR 121.57 / 122.83 / 124.37 dB，max 3 / 5 / 5。因此不能把便携阶段称为逐 bit 原生捕获；最终验收始终使用原 DNG。
- 另核对 8 组现有原生阶段：20MP ORF 的完整 normalized RGB、G/DR/DB 和 tone-G、filtered-G；50MP 的 normalized-G、tone-G、filtered-G、RL-G。索引验证其完整 pre-tail SHA 属于当前参考输入，再验证各 blob SHA。ORI 没有对应直接原生中间捕获，保留便携阶段对照和原 DNG 最终对照的覆盖边界。
- 为区分 M1 传播与 tail 数学，在**测试专用同输入诊断**中，固定用参考 pre-tail 作为 tail 内核 fixture，独立完成全部预测后再比较原 DNG：

| 同输入 tail 诊断 | 全幅 PSNR | 全幅最大差 | 内域最大差（去 8px，仅定位） |
|---|---|---|---|
| P7262257.ORF | 117.96 | 6 | 6 |
| P7262256.ORI | 120.51 | 5 | 5 |
| P7262256.ORF 50MP | 118.66 | 49 | 5 |

50MP 的 49 码极值在右边界 (y=1,x=8167,G)，内域仅 5；与活动边缘和参考物理 padding 的语义差异相符。该实验仅隔离 tail，不能替换真实 RAW 的 728/510/176。对照表明，两个 20MP 端到端峰值主要由 M1 差异经 tone/filter/RL 的非线性传播引起。

## M2 修正及已知差异

- 明确极值替换采用邻域第二大/第二小值，避免把中心极值再次作为替换依据。滤波参数补齐小于 17MP 时加倍 ISO 的分支，以及最高 ISO 档 s=6.73；真实源 ISO 仍用于 RL cutoff。
- 继续使用已去黑的 RGB16/65535，不重复使用传感器电平；WB 和 ISO/pixel_scale 缺失明确拒绝。RL sigma 使用完整传感器宽度和真实 pixel_scale。
- RL 边界先一次性复制，再在外延上演化；重复在每次卷积处复制活动边界会产生错误。新增独立 float64 大画布回归区分这两种行为。两次 RL 只改 G，色差逐 bit 保留；chunk_rows=1 与其它值一致。
- Tone 采用连续公式及闭式逆函数，替代参考的 1024 结点样条；没有分发厂商 LUT。普通 float32 除法/求和替代 VRCPPS/FMA/SIMD 分组。
- 滤波按活动宽度复制图像边缘；还原时对全部活动 G 使用处理后的 G。没有复刻参考 64B pitch 零 padding、平面连续字节前缀拷贝或原 RL tile 几何。此差异全幅统计保留，不用坐标补丁模拟。
- 已检查最差 RGB、最差 ΔE、高反差和右下边界四组 100% 裁切，未观察到明显新增拉链或伪色；判断只覆盖这些裁切和共同 WB/gamma 显示，不是完整 DCP 外观结论。
- 三个真实样本均为 ISO200。其它 ISO 分支、黑场、常量、极值、随机边界、PSF 与 chunk 一致性由合成测试覆盖，未扩大真实照片支持范围。

## M2 产物与复现

- `out/m2/final/validation.json`：最终 3/3 PASS，全部 float/uint16 阶段指标、8 组原生阶段、矩阵 ΔE、源码/参考 SHA、耗时和设置范围。
- `out/m2/final/<样本>/`：本次 RAW 独立预测的阶段文件及全分辨率 `delta_e00.f32`；`previews/` 保存四组裁切和选择位置，仅供诊断。
- `out/m2/oracles/<配置>/index.json`：隔离便携参考的来源、SHA、阶段路径；配置为 plain20 / ori20 / orf50。各参考源在本轮后再次校验，保持只读。
- `out/m2/native-stages.json`：已有原生阶段的布局、通道、文件和身份；没有把同一 20MP 图的多个捕获误记为多个真实 RAW。
- `out/m2/kernel-diagnostic/diagnostics.json`：同输入诊断，明确标记 TEST ONLY；定位用内域指标不参与验收。
- `out/m2/pytest.xml`：116 项完整测试通过，包括 M0/M1/M2 各三个真实集成测试。新增 39 项数学/API/色度测试；初始 13 项 RED 日志保留在工作区 `.cache/m2-tail-red.log`。初次全幅运行保留在 `out/m2/attempt01/`。
- 初次、最终和完整集成测试三次分别从真实 RAW 预测，三个样本的七个 tail 阶段输出 SHA-256 全部一致；最终报告的源码/tool SHA 与本轮工作文件一致，研究源 SHA 保持不变。

基本复现见 README。原生阶段索引可用以下命令重建到新文件，再通过 `--native-stages` 提供给验证工具：

```powershell
& ./.venv/Scripts/python.exe tools/index_m2_native_stages.py `
  --acceptance '/path/to/research/phase6/tail_50mp_recheck/parent_acceptance.json' `
  --runtime20 '/path/to/research/phase6/runtime/captures' `
  --runtime50-filter '/path/to/research/phase6/runtime_50mp_filter/captures' `
  --runtime50-tail '/path/to/research/phase6/runtime_50mp_tail/captures' `
  --out out/m2/new-native-stages.json
```

`tools/diagnose_m2_tail.py` 接受相同的 fixtures/acceptance/oracles 和新 `--out`，仅重跑同输入诊断。`tools/preview_m2.py --report <validation.json> --fixtures tests/fixtures.example.json --out <新目录>` 重建裁切。新增的预测、生成参考、测试缓存均在 D 盘，未进入 Git；既有 C 盘研究材料只读。M2 无新增生产依赖。下一阶段是 M3 的 DNG writer、用户 DCP 与容器/外部软件验证。

## M2 补充验收：SSIM 与再次全幅对照

复核发现初次 M2 未将交接 T4 的 SSIM>0.98 纳入自动验收。本次补齐分块 SSIM、报告和集成断言，并从三个真实 RAW 重新生成全部 M1/M2 预测。M1 行序、反馈稳定化以及 tone/filter/RL 数学均未修改。

| 样本 | 最终 PSNR dB | 最大绝对差 | SSIM | 平均 ΔE00 | ΔE00 p95 | M1 最大差 |
|---|---|---|---|---|---|---|
| P7262257.ORF | 92.583666 | 728 | 0.999999546 | 0.006028976 | 0.032966256 | 198 |
| P7262256.ORI | 92.074583 | 510 | 0.999999352 | 0.008279944 | 0.047058171 | 191 |
| P7262256.ORF 50MP | 105.503402 | 176 | 0.999999970 | 0.001042719 | 0.006149656 | 128 |

三个样本全部通过 PSNR>40、SSIM>0.98、固定矩阵 ΔE00 平均<2 / p95<4，M1 仍独立严格满足 max<200。SSIM 使用 scikit-image 的 7×7 均匀窗口、样本协方差、K1=0.01 / K2=0.03、峰值 65535；RGB 通道均分。统计包含全部标准有效窗口中心，外圈 3 像素不作为中心但参与相邻窗口；分块使用 halo，没有漏掉块交界。PSNR、最大误差和 ΔE 仍统计全部活动像素与边界。

对三个样本逐个重算七个 tail 阶段以及 demosaic 文件 SHA-256，**24/24 与初次 M2 的 `out/m2/final/` 完全相同**。归一化、HiFi、tone、filter、RL、tail 六个生产数学模块的源码 SHA 也保持一致。最终 PSNR/最大误差/ΔE 及前述阶段表均复现；没有为通过新增检查改动像素或门槛。再次检查最差 RGB、最差 ΔE、高反差、右下边界四组 100% 裁切，未见明显新增拉链、伪色或相对色偏；检查仍限于共同 WB/gamma 显示。

已知差异继续保留：两个 20MP tail 峰值为 728 / 510；两个样本各有 2 个像素 ΔE00≥2；固定矩阵 ΔE 不含完整 DCP；ORI 缺少直接原生中间捕获；便携阶段参考不等同于逐 bit 原生阶段。此次补充验收没有改变这些覆盖边界，也没有完成 M3 DNG 容器或外部软件验收。

新增 8 项 SSIM 回归先 RED 后 GREEN，覆盖与整图计算一致、物理边界、条带交界、最小窗口和无效输入；与现有 tail/filter/RL/tone/色度测试合计 47 项定向测试通过。RED 日志保留在工作区 `.cache/m2-ssim-red.log`。

完整工作树回归 **146 passed / 0 failed / 0 skipped**，其中 M0–M2 为 124 项，包含各阶段共 9 个真实 RAW 集成用例；另 22 项是预存的 M3 合成单测，不代表 M3 已完成。完整回归耗时 306.05 秒。独立验证工具和 pytest 两次从真实 RAW 预测，全部阶段 PSNR/最大差、最终像素指标、SSIM、ΔE 均完全相同。预存 M3 的 writer/profile/metadata 改动没有纳入本次提交。

本次产物（全部位于 D 盘且被 Git 忽略）：

- `out/m2/ssim-acceptance/validation.json`：v2 三样本全幅报告，新增 SSIM 数值、定义与门槛。
- `out/m2/ssim-acceptance/baseline-comparison.json`：24 个预测文件及六个数学模块的一致性核对。
- `out/m2/ssim-acceptance/previews/`：四组裁切及位置来源。
- `out/m2/ssim-acceptance-pytest.xml`：完整工作树回归结果。
- `out/m2/ssim-acceptance/regression-comparison.json`：独立验证与 pytest 两次真实预测的指标一致性。

使用 README 的验证命令，将 `--out` 指向新的目录即可复现；其余 fixtures、parent acceptance、便携参考及原生阶段索引保持不变。

## M3：DNG、用户 profile 与转换入口

完成独立 TIFF/DNG 字段与目录构造、用户 DCP 校验/嵌入、16-bit 无压缩 LinearRaw 写入，以及单输入 `pipeline.convert_raw` / `orf2dng` 转换入口。生产只读取当前 RAW 和用户明确提供的 DCP，不调用原程序或外部渲染器，不套参考模板。先验证设置和 profile，再解码；不支持的 v3、未知 profile 扩展、embed-never 和已有输出明确报错。

三个真实样本均从 RAW 新算 M1/M2，再写 DNG。全幅回读比较共 **272,465,280 个通道样本，mismatches=0、max=0、PSNR=∞**。每个样本的 36 项关键 tag 与参考语义一致，15 项用户 DCP payload 的类型、数量和数值字节全部相同（合计 108 / 45 项）。不同有理数编码、WhiteLevel 类型、Software、Exif/strip 布局、未迁移的 GPS/XMP/MakerNote 等区别逐项写入 METADATA_DIFFERENCES。

24 个 tail/pre-tail 阶段文件 SHA 及六个生产数学模块 SHA 与 M2 基线相同。M1 的 PSNR 94.64 / 92.47 / 105.60、max 198 / 191 / 128 继续通过严格 <200；M2 的 PSNR 92.58 / 92.07 / 105.50、max 728 / 510 / 176、SSIM 和固定矩阵 ΔE 均完全复现。写入器没有改动或烘焙这些线性像素。

## M3：完整可用 DCP 渲染与外部读取

使用官方 RawTherapee **5.13** 的独立 CLI，在共同 PP3 下启用相机 WB、自动 DCP 光源、HueSatMap、LookTable、可用 tone 和 baseline offset，工作空间 ProPhoto，输出 RTv4_sRGB RGB16。没有默认处理 profile、自动曝光、锐化、降噪、重采样、裁切或 sidecar 覆盖。每个样本分别渲染本实现 DNG 的内嵌 DCP、原参考 DNG 的内嵌 DCP，以及显式指定同一用户 DCP 的本实现 DNG。

下表对照前两种完整渲染；包含完整处理域的全部像素和边界，SSIM 仍使用标准 7×7 有效窗口中心。ΔE 是 sRGB 解码到 D65/2° Lab 后的 CIEDE2000；均值/最大值累加 float64，p95/p99 使用全分辨率 float32 图，不做曝光拟合、mask 或抽样。它与 M2 固定 D50 矩阵指标采用不同色彩转换，不能直接互代。

| 样本 | PSNR dB | RGB 最大差 | SSIM | 平均 ΔE00 | p95 | 最大 ΔE00 |
|---|---|---|---|---|---|---|
| P7262257.ORF | 76.605567 | 2063 | 0.999990527 | 0.012520610 | 0.069844688 | 4.196274 |
| P7262256.ORI | 76.094531 | 1998 | 0.999977936 | 0.014344137 | 0.078715133 | 4.403280 |
| P7262256.ORF 50MP | 89.177133 | 749 | 0.999998787 | 0.001967174 | 0.012749088 | 1.872937 |

三个样本均通过 PSNR>40、SSIM>0.98、平均 ΔE00<2 / p95<4。渲染峰值差和最大 ΔE 如实保留；没有把 M1 的 <200 当作渲染后门槛，也没有声称每个像素 ΔE 都低于 2。三个样本的**内嵌与显式 DCP 渲染逐像素零差异**。

在首个 20MP ORF 上，分别关闭 HueSatMap / LookTable / tone 后，相对完整渲染的最大差为 **12587 / 8442 / 17540**，均出现实际像素变化。固定光源 1 的最大差为 5780，光源 2 与本例自动选择相同（该样本处于第二光源端）；这些探针用于证明选项/端点行为，不是中间色温插值的独立数值 oracle。用户 DCP 没有显式 ProfileToneCurve 或 BaselineExposureOffset；tone 关闭实验覆盖的是 RawTherapee 根据 Adobe copyright 采用的默认曲线，不是本仓库内置的厂商 LUT。

darktable **5.6.2** 实际解码并导出三个 DNG，得到非空、非常量 JPEG；按相机建议裁切为 5184×3888 / 5184×3888 / 8160×6120。此检查证明读取兼容，没有把 darktable 当作相同 DCP LUT 的渲染器。RawTherapee 的 TIFF 使用完整处理域 5216×3908 / 8168×6128。全部应用设置、数据库/缓存、临时文件和输出均写在本工作区 D 盘，没有调用原转换器。

已检查共同 DCP/sRGB 的整图缩略图，以及最差 RGB、最差 ΔE、高反差、右下边界四组 100% 裁切；未观察到明显新增拉链、伪色或相对色偏。该判断仅覆盖所展示区域和共同处理，不代表绝对场景色彩准确或任意其它 RAW 软件的外观。

## M3：修正、测试与证据

- 拒绝悬空输出符号链接，只解析父目录，完成文件再独占发布；并发出现的新文件保持原样。本轮 D 盘支持硬链接，不提供静默覆盖式回退。
- AsShotNeutral 改为与交接一致的六位小数，避免等值分数精度与参考字段不一致。
- 非数值 DCP 矩阵字段现在明确抛 ValueError，避免 KeyError 泄露成未处理 traceback；未知 profile 功能继续明确拒绝。
- 元数据测试工具改为遍历 tag 编码；双方同时缺失必需字段时不再误判相同。
- 外部脚本处理 Windows RawTherapee 帮助命令的 unsigned -1 退出码；实际渲染仍必须返回 0。darktable 导出路径统一使用正斜杠，避免其导出展开过程吞掉反斜杠。这两项是验收工具修正，原始失败日志保留。
- 核对 RawTherapee 的 PP3 参数名为 PostDemosaicSharpening / PostResizeSharpening；最终工具显式关闭这两项。5.13 中性配置的默认值本已关闭，额外实际渲染验证修正键名后 RGB 仍逐像素相同，证据保存为 `out/m3/recipe-check/validation.json`。

完整回归 **160 passed / 0 failed / 0 skipped**（518.96 秒），包含 M0/M1/M2/M3 各三个真实集成用例。随后补充一个无效 DCP 类型用例并修复异常类别，相关 **34 项定向测试**通过，最终全部 **149 项独立单元测试**通过。最终源码又从三个 RAW 独立完成 M3 验收，全部通过；三个最终 DNG 与已通过外部验收的 DNG 的**整文件 SHA 完全相同**，全部生产源码 SHA 与最终工作文件一致。

实际 CLI 对 20MP ORF 的转换也完成，其输出与 API 的整文件 SHA 相同。带阶段 hash/落盘观察的本次转换耗时约 17.90 / 17.39 / 58.19 秒；这不是无回调的纯转换性能基准，本轮没有宣称已达到交接的性能优化目标。

本地报告/图片均被 Git 忽略：

- `out/m3/final/validation.json`：最终三样本像素、关键 tag、DCP 字段和 M1/M2 指标。
- `out/m3/final/external-binding.json`：当前源码及最终 DNG，与外部已验收文件的完整身份绑定。
- `out/m3/attempt01/m2-regression.json`：M2 的 24 个阶段/最终指标及六个数学模块一致性；最终阶段 hash 与该次预测也完全相同。
- `out/m3/external03/validation.json`：三个外部渲染结果、应用/命令/日志 SHA、全部门槛、DCP 关闭与光源探针；同目录保存 PP3、TIFF、JPEG 和全分辨率色差图。
- `out/m3/external03/previews/`：DCP/sRGB 整图与四组裁切、位置说明。
- `out/m3/pytest.xml` / `out/m3/unit-pytest.xml`：完整回归及最终单元回归；`out/m3/environment.json` 记录包版本。
- `out/m3/cli/P7262257.dng`：真实 CLI 转换产物。

`out/m3/attempt01/`、`external01/`、`external02/` 及工作区 `.cache/m3-*-red*.log` 保留初次结果与失败证据。源 RAW、DCP、C 盘研究材料始终只读。最新复现命令见 README；可选外部验证需要用户自行提供相应官方 CLI。M3 已完成当前三个样本的有界验收；本节结束时 M4 的发行打包及材料审查尚未开展。

## M4：CLI、发行包与独立安装

修正普通安装缺少默认解码依赖的问题：NumPy/rawpy 现在是默认运行依赖；tifffile 移到 dev，Pillow 与 packaging 补入 dev，使图像检查/发行检查工具的依赖显式完整。保留 decode extra，兼容旧安装命令。增加 `python -m colorpipe` 入口，CLI/Software 共用包版本；默认设置仍为单线程 HiFi 和用户显式 DCP。

CLI 的 `--plan` 此前可接受未实现的 v3、非零 v3-mode、错误输入/输出后缀以及悬空输出符号链接，现在这些请求均明确拒绝；help 写明 profile 为转换必需，plan 不解码也不验证 profile。writer 对超过 classic TIFF 大小上限的虚拟数组提前抛 ValueError，避免在像素访问前泄露 struct.pack 溢出错误。6 个失败用例先 RED 后修正，日志为工作区 `.cache/m4/cli-red.log`；模块入口失败证据为 `module-red.log`。

基线发行包的实际构建确认缺少 Markdown 长说明、MIT 许可声明、第三方通知，sdist 还缺少文档、工具和测试辅助文件。现在 pyproject 声明 SPDX MIT/readme/license-files，MANIFEST 显式收录源码、文档、测试、路径示例与工具；wheel 只含生产模块及包元数据/许可。新增归档检查及 8 个资产/依赖回归用例，检查私有资产、路径、默认解码依赖和通知文件；基线 FAIL 与修正后 PASS 均保留，未改写失败记录。

在独立 build venv 中使用固定的 build 1.6.1 / setuptools 84.2.1 / wheel 0.48.0 / twine 7.0.0，先构建 sdist，再从 sdist 构建 wheel，两个归档均通过 `twine check --strict` 与实际成员/元数据检查。此过程不借用开发环境或研究交接目录，不承诺归档时间戳的逐 bit 重现。

全新 install venv 普通安装 wheel，实际仅有 colorpipe 0.1.0、NumPy 2.5.4、rawpy 0.27.1、pip 25.2；未安装 tifffile/Pillow/scikit-image，也无 editable/src 注入。pip check、console/module 的版本入口、help 和三个真实 CLI 转换通过。转换在空目录运行，只向生产 CLI 提供当前 RAW、用户 DCP 和新输出路径；三个生成 DNG 的整文件 SHA 与 M3 最终文件完全一致。

无阶段回调的独立 CLI 墙钟耗时为 **17.83 / 17.13 / 54.83 秒**（20MP ORF / ORI / 50MP ORF，含进程启动和写盘）。只做一次本机运行，未测峰值内存；没有宣称达到交接的 20MP<10秒、50MP<40秒优化目标。六个生产数学模块的源码 SHA 与 M3 完全相同；默认彩色数学、行序和验收门槛均未修改。

## M4：完整回归、指标与边界

在安装环境补装 dev 依赖后，从解压的 sdist 执行 `python -I -B -m pytest`，设置 `COLORPIPE_TEST_INSTALLED=1` 关闭 conftest 的源码导入。完整回归 **175 passed / 0 failed / 0 skipped**（481.92 秒），含 163 个合成/API/工具单元用例与 M0–M3 各三个真实集成用例。没有使用 editable 安装或 PYTHONPATH；实际生产模块来自独立 venv 的 site-packages，其 16 个源码文件 SHA 与工作树一致。测试辅助文件、工具与示例来自 sdist。

M1 全部阶段的指标/预测哈希与 feedback-stable 基线完全相同；M2 全部已记录阶段的指标/预测哈希、最终 RGB、SSIM 与固定矩阵 ΔE 完全复现（排除输出路径及耗时）。M3 的 **36 个阶段哈希、三个整文件 DNG SHA**与最终基线相同，像素回读仍零误差，每个样本 36 项关键 tag / 15 项用户 DCP payload 通过。

| 样本 | M1 max | tail PSNR dB | tail max | SSIM | 平均 ΔE00 | ΔE00 p95 | 最大 ΔE00 |
|---|---|---|---|---|---|---|---|
| P7262257.ORF | 198 | 92.583666 | 728 | 0.999999546 | 0.006028976 | 0.032966256 | 2.081843 |
| P7262256.ORI | 191 | 92.074583 | 510 | 0.999999352 | 0.008279944 | 0.047058171 | 2.465148 |
| P7262256.ORF 50MP | 128 | 105.503402 | 176 | 0.999999970 | 0.001042719 | 0.006149656 | 0.792083 |

此表 ΔE 为 M2 定义的固定矩阵 D50 Lab。完整 DCP 外观继续引用 M3 的共同 sRGB/D65 结果：PSNR **76.605567 / 76.094531 / 89.177133**，RGB 最大差 **2063 / 1998 / 749**，平均 ΔE00 **0.012520610 / 0.014344137 / 0.001967174**。本次未重跑外部应用；安装版与本次 M3 集成 DNG 的整文件 SHA 均相同，继承的是这些确切文件已有的 RawTherapee/darktable 验收，不扩大外观覆盖范围。

已知差异保持：路线 B 自有行序与有界反馈、解析 tone/标准运算/活动边界、ORI 原生中间阶段缺口、20MP tail 峰值与少数 ΔE≥2、元数据迁移边界和 profile/机身/ISO 有界支持。没有放宽 M1 门槛或增加坐标/样本补丁。仅配置 Windows/Linux × Python 3.11/3.14 的可选 CI，尚未推送/远程运行；本地实际平台仍是 Windows x64 / CPython 3.14.0。51 个源码/测试/工具文件通过 Python 3.11 语法解析，此检查不替代运行验收。

本地产物全部写 D 盘并被 Git 忽略：

- `dist/colorpipe-0.1.0-py3-none-any.whl`、`dist/colorpipe-0.1.0.tar.gz`：最终本地工程发行物。
- `out/m4/distribution-validation.json`：实际归档成员、依赖/许可/长说明检查与最终 SHA；`twine-check.log` 为严格元数据检查。
- `out/m4/baseline-validation-corrected.json`：原发行包缺项的 FAIL；候选归档和日志保留在 `out/m4/candidate/` 与工作区 `.cache/m4/`。
- `out/m4/installed-validation.json`：最小运行环境、实际模块路径、三个 CLI 的命令/耗时/DNG SHA；`default-install-report.json` 为 pip 安装记录。
- `out/m4/pytest.xml`、`out/m4/regression/`、`out/m4/regression-binding.json`：175 项完整结果、九份 M1–M3 指标和既有基线逐项一致性。
- `out/m4/math-source-binding.json`：六个数学模块与 M3 一致；`build-environment.txt`、`installed-environment.txt`、`installed-license-inventory.json`：完整实际环境。
- `out/m4/final-binding.json`：最终归档、安装代码、已测试代码及真实输出的绑定；最终归档重建只更新文档/通知，生产/测试/工具源码保持与完整回归相同。

README 与 BUILDING 给出无需交接目录的源码安装、构建、wheel 安装和 sdist 测试命令；真实验证仍需用户自己的本地材料。M0–M4 的当前有界工程目标完成；后续工作是性能、其它平台/版本实测与发布前法律/专利审查，v3/镜头等仍为可选新范围。本轮没有上传、推送或宣称公共发布已获法律结论。

## P1：默认 HiFi 性能优化

针对已记录的性能缺口，用冻结的 M4 安装版剖析 20MP：整段约 16.97 秒，其中 tail 11.17 秒、滤波 8.96 秒，通用五点排序约 5.13 秒。先固定 M4 的 float32 滤波结果和 uint16 HiFi 阶段字节，再进行以下三项修改：

- 五点排序改为九次逐元素比较交换，验证 120 种严格顺序和 32 种二值输入；滤波将重复九邻域检查改为每个源像素只检查一次，使用带真实 halo 的行块切片。权重与浮点加法次序保持原样。
- HiFi pass1 的内域规则奇偶采样改为切片，边缘沿用原取样。pass2 自有确定性从上到下行序、冻结/递推融合、128 反馈限制和 pass4 均未改。
- 默认 tail 行块由 32 改为 16。分块试验中所有输出哈希相同；16 行降低暂存压力，未引入图像身份或坐标特例。

新增 22 个数值/字节回归用例：10 个滤波排序与旧字节契约，12 个 HiFi 小图/边界/跨块的全部阶段契约。首个新 helper 用例先 RED，9 个旧滤波字节用例已通过，记录保留在工作区 `.cache/perf/filter-red.log`；首次修正后的 33 项定向测试通过，最终 185 项单元测试通过。未引入新依赖或第二套生产算法。

## P1：三轮时间与峰值内存

在 i7-14650HX（16 核/24 逻辑处理器、约 16 GB RAM）、Windows x64、CPython 3.14.0 / NumPy 2.5.4 / rawpy 0.27.1 / LibRaw 0.22.1 上，冻结 M4 安装版和优化源码版逐样本交替执行，第二轮反转顺序。所有转换均为单线程配置；没有 cProfile、阶段回调、冷缓存清空或并发跑另一组大图测试。

| 样本 | M4 API 中位秒 | 优化 API 中位秒 | 优化 API 范围秒 | 安装版 CLI 中位秒 | CLI 范围秒 |
|---|---|---|---|---|---|
| P7262257.ORF | 16.5914 | 7.9329 | 7.8185–7.9362 | 8.1741 | 8.0971–8.9724 |
| P7262256.ORI | 16.6157 | 7.9693 | 7.8563–8.1621 | 8.1156 | 8.1042–8.1283 |
| P7262256.ORF 50MP | 55.5197 | 23.5528 | 22.5942–27.1137 | 23.0656 | 22.9161–23.1485 |

API 统计共 18 次，包含解码/校验/处理/写盘，不含启动、导入与事后证明；完整 CLI 另在仅装默认依赖的独立 venv 中三次运行各样本，共 9 次，含启动至正常退出。API 中位耗时加速约 **2.09 / 2.08 / 2.36 倍**；不能将 worker 附加哈希/内存证明的墙钟冒充 CLI 延迟。全部优化 API 与 CLI 运行都严格满足 10 / 10 / 40 秒目标。

50MP 三次最大 working set 为 **1,642,192,896 B（1566.1 MiB / 1.529 GiB）**，峰值 commit 为 **1,669,103,616 B（1591.8 MiB / 1.555 GiB）**，两者均低于十进制 2,000,000,000 B。计数为 Windows 进程生命周期峰值，包含导入及输入；原 M4 也处于相同内存量级，本轮完成测量并显著改善时间，没有声称显著降低内存。定义、官方字段来源和复现命令见 PERFORMANCE。

## P1：完整安装回归与数值保持

优化 wheel/sdist 在独立 build venv 中构建，严格元数据与归档检查通过；新 install venv 默认安装仅需 NumPy/rawpy，console CLI 及 module 入口可用。随后按原固定依赖补装 dev，从解压的 sdist 对安装 wheel 执行 `python -I -B -m pytest`，关闭源码导入替代，**197 passed / 0 failed / 0 skipped**（379.12 秒），含 M0–M3 的 12 个真实集成用例。

三样本 M1 所有已记录阶段的指标/预测哈希、M2 所有已记录阶段/最终 RGB/SSIM/固定矩阵 ΔE 均与此前基线完全相同；仅输出路径及耗时不同。M3 的 **36 个阶段哈希、三个整文件 SHA**相同，像素回读仍零误差，每样本 36 项关键 tag 和 15 项 DCP payload 通过。18 次 A/B 与 9 次安装版 CLI 的 DNG 也逐个复核同一整文件 SHA，均一致。

| 样本 | M1 max | 最终 tail PSNR dB | tail max | SSIM | 平均 ΔE00 | p95 ΔE00 |
|---|---|---|---|---|---|---|
| P7262257.ORF | 198 | 92.583666 | 728 | 0.999999546 | 0.006028976 | 0.032966256 |
| P7262256.ORI | 191 | 92.074583 | 510 | 0.999999352 | 0.008279944 | 0.047058171 |
| P7262256.ORF 50MP | 128 | 105.503402 | 176 | 0.999999970 | 0.001042719 | 0.006149656 |

M1 严格 max<200 保持；此表 ΔE 为固定矩阵 D50，完整 DCP 外观继续沿用 M3 的 sRGB/D65 指标。未重跑外部应用，继承的是完全相同 DNG 字节的既有 RawTherapee/darktable 证据。自有行序/反馈、解析 tone、活动边缘、ORI 原生中间阶段缺口、20MP 峰值误差及少量 ΔE≥2、机身/profile/ISO 范围等已知差异均不改变。没有 mask、坐标补丁或放宽门槛。

本地产物（均在 D 盘并被 Git 忽略）：

- `out/performance/ab-three-runs/benchmark.json`：三轮交替 A/B，含每次时间、峰值、源码/环境、命令、DNG 身份；子目录保留 18 个实际 DNG 和 worker 日志。
- `out/performance/cli/validation.json`：仅默认依赖的安装版完整 CLI 三轮记录及 9 个 DNG。
- `out/performance/baseline/`、`attempt01/`、`chunk-tuning.json`：优化前后剖析、阶段尝试和分块结果；RED 日志保留在工作区 `.cache/perf/`。
- `out/performance/pytest.xml`、`unit-pytest.xml`、`regression/`、`regression-binding.json`：197 项完整结果、185 项单元结果、九份阶段报告及与既有基线的一致性。
- `out/performance/hardware.json`、`installed-environment.txt`、`default-install-report.json`、`dev-install-report.json`：硬件、依赖与安装来源。
- `out/performance/release/`、`distribution-validation.json`、`twine-check.log`、`final-binding.json`：最终优化归档、审查及与已测试代码/时间/内存/输出的绑定。

M4 的 `dist/` 归档及原报告完整保留。优化本地构建仍为未公开发布的 0.1.0，已有 M4 同版本包时须 force-reinstall 或用新 venv；不以文件名区分代码，使用提交/标签和 SHA。最终重建仅更新文档/说明，54 个生产/测试/工具 Python 文件与完整回归一致。P1 完成本机三样本的单线程性能目标，不能外推到其它硬件、冷缓存、图像/ISO/profile 或多线程；其它平台/版本实测、远程 CI 与法律/专利审查继续留待后续。
