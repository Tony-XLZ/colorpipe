# 限制（v1）

当前完成 M0–M4 的本地工程验收，提供单输入默认 HiFi CLI 和 wheel/sdist。M1 三个真实样本的 RGB PSNR 为 94.64 / 92.47 / 105.60 dB，最大误差为 198 / 191 / 128，全部通过严格 <200 门槛。M2 最终 tail RGB PSNR 为 92.58 / 92.07 / 105.50 dB，最大误差为 728 / 510 / 176，固定矩阵平均 ΔE00 为 0.00603 / 0.00828 / 0.00104；M3 保留这些像素，不把 profile 处理烘入其中。M4 安装版完整回归 175 项通过，三个 CLI 的 DNG 与 M3 整文件相同。

P1 性能优化后的独立安装包完整回归为 197 项全部通过；没有改变上述指标或真实 DNG 字节。只调整数组访问、五点排序和默认 tail 行块大小，M1 自有行序及反馈稳定化不变。

M1 只支持 RGGB、偶数尺寸至少 8×8、每边 2 像素和默认 HiFi；v3 仍未实现。pass2 保留自有全局从上到下行序，增加冻结/递推候选的有界中点融合；pass4 对颜色变化使用同一 128 码幅度限制。128 限制的是相对自有递推估计的改动，不是相对 oracle 的误差上限。该路线 B 稳定化是新增算法差异，PSNR 比未融合版本低，50MP 最大误差从 46 增至 128；不承诺其它图像、ISO 或参考调度也满足 <200。生产不读取原任务计划或参考像素，不使用样本身份或坐标补丁。float CFA 高光可 >1，进入 HiFi 时才饱和到 uint16；可选 gamma 分支不在本轮范围。

M0 有界支持：OM Digital Solutions / OM-1MarkII、little-endian IIRO、OM SYSTEM MakerNote、12/14 位、完整传感器 RGGB。ValidBits/CropLeft/CropTop 的第二个 SHORT 必须为 0；WB 两个绿参考必须一致。不满足这些条件时明确拒绝。真实图像验证仅涵盖三个交接样本，均为 ISO200；其它 ISO 仅验证读取逻辑，尚无真实图像验收。

M2 只实现默认 HiFi 的彩色 tail，ISO/pixel_scale/WB 缺失时拒绝，不默认补值。Tone 直接计算连续曲线及其逆函数，滤波用标准 float32 除法，RL 使用自有行条带。活动边缘复制、全部活动 G 的还原，与参考的物理 padding/连续前缀拷贝有差异。同输入 tail 最大误差为 6 / 5 / 49，50MP 内域为 5；这些诊断不能代替从 RAW 开始的端到端结果。

M2 的 ΔE00 使用参考 DNG 的固定 ForwardMatrix2、CameraCalibration2、AnalogBalance、AsShotNeutral 转到 D50 Lab，对全部活动像素计算。不含双光源插值、DCP HueSatMap/LookTable、渲染 tone 或曝光拟合，不能宣称是 Lightroom/darktable 最终外观验收。两个 20MP 样本各有 2 个像素的 ΔE00≥2，最高约 2.08 / 2.47；平均和 p95 通过不等于每个像素均低于 2。ORI 的中间阶段使用便携研究数学参考，尚无对应的直接原生阶段捕获；最终三个样本均直接对照现有原 DNG 像素。

M2 补齐了 SSIM>0.98 的交接检查，三个值为 0.999999546 / 0.999999352 / 0.999999970。使用完整分辨率、7×7 均匀窗口和 RGB 通道等权平均；标准 SSIM 的窗口中心不包含外圈 3 像素，该圈仍进入相邻窗口。PSNR、最大误差与 ΔE 的全幅统计域保持不变。SSIM 也是 camera-linear 像素检查，不是完整 DCP 渲染外观。

生产使用传感器白电平，与相机通道白点分别记录；HiFi 入口饱和量化，更多高光策略尚未验证。焦平面对角线必须存在；未知值不会默认成 2。

M3 要求用户显式提供有界 classic SDR 三通道 DCP，不支持未知扩展、链式 profile、非单调 tone curve 或禁止嵌入的 profile。真实外观只验证了本机身的用户 Adobe Standard；其它 profile 的合成字段测试不能代替真实色彩验收。三个真实样本方向均为 1，方向 6 只做 tag/像素契约的合成验证。机身参考校准和基线标量限于当前已验证范围，不扩展为通用相机数据库。

RawTherapee 5.13 的完整可用 DCP 对照 PSNR 为 76.61 / 76.09 / 89.18 dB，RGB 最大差为 2063 / 1998 / 749，平均 ΔE00 为 0.01252 / 0.01434 / 0.00197；最大 ΔE00 仍为 4.19627 / 4.40328 / 1.87294。均值/p95 通过不等于所有像素误差均很小。此处是共同 sRGB 输出的 D65 Lab；不与 M2 固定 D50 矩阵指标混用。源 DCP 没有显式 tone curve 或 baseline offset；tone 开关验证的是 RawTherapee 的 Adobe copyright 默认曲线行为。darktable 5.6.2 的成功导出证明读取兼容，不声称同样应用完整 DCP LUT；也不扩展为 Lightroom 或任意版本软件的验收。

DNG 为 classic TIFF、小于 4 GiB、无压缩，不带预览。完整文件以同目录临时文件及独占硬链接发布，要求文件系统支持硬链接；出错不会回退为覆盖式写入。完整 Exif/GPS/MakerNote/XMP 不保留，逐字段边界见 METADATA_DIFFERENCES。M4 完成本地打包/安装和资产来源检查；远程 CI、其它平台/版本实测及发布前法律/专利审查仍未完成。源码兼容 Python 3.11 语法不等于已完成该版本运行验收。

- **彩色-only**：不做 B&W 10 模式。
- **OM-1 Mark II 优先**：其它机身未验证。
- **默认设置**：NR/锐化/Clarity 非默认档位不在 v1；不支持的设置明确报错。
- **视觉等价**：不承诺与 Iridient O-Transformer 逐 bit 相同。
- **镜头**：v1 可以不做；20MP 的 dist/CA/vignette 是 v0.4。
- **DCP**：用户提供；仓库不包含 Adobe/Iridient profile。
- **DNG**：16-bit 无压缩；不做 8/12-bit、压缩、预览。
- **元数据**：关键 tag 正确；不追求完整 EXIF/XMP 恒等。
- **性能**：本机 P1 三轮 CLI 中位数 8.17 / 8.12 / 23.07 秒，全部九次通过 10 / 10 / 40 秒目标；50MP 最大峰值 working set 1.642 GB、commit 1.669 GB，低于十进制 2 GB。仅为 i7-14650HX / Windows / Python 3.14 的三样本结果；不保证其它硬件、冷缓存、RAW、ISO、profile 或多线程表现。详细范围见 PERFORMANCE。
- **平台**：Windows x64 优先；其它平台未验证。
