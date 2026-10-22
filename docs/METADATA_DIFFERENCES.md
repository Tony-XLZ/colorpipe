# M3 元数据与容器差异

本项目从用户 RAW 独立计算 camera-linear RGB16，再从零构造 little-endian classic TIFF/DNG。不会套用参考 DNG 模板、移植旧指针或携带整块 MakerNote。用户 DCP 仅在用户指定且允许嵌入时写入输出，仓库不包含厂商 profile。

## 三个交接样本的关键语义

`tools/validate_m3.py` 对 20MP ORF、20MP ORI、50MP ORF 各核对 36 项关键 tag：尺寸、16 位三通道、无压缩、LinearRaw、相机身份、方向、black/white、裁切、矩阵、白平衡、曝光基线和 profile 名称/签名。比较有理数的值，不要求等值分子/分母或文件布局一致。用户 DCP 的 15 项字段另按类型、数量和规范 little-endian 数值字节逐项校验。

| 项目 | 本实现 | 参考/说明 |
|---|---|---|
| 图像域 | 5216×3908 / 8168×6128，RGB16 LinearRaw | 与参考活动处理域一致；不是 CFA DNG |
| BlackLevel / WhiteLevel | 0 / 65535，三个通道 | 已去黑和缩放，不能写源传感器黑电平 |
| DefaultCropOrigin / Size | 20MP：(10,10)/(5184,3888)；50MP：(4,4)/(8160,6120) | 源相机裁切减去处理边界的原点；与参考一致 |
| Orientation | 复制源 tag，像素不旋转 | 三个真实样本均为 1；方向 6 由合成测试覆盖 |
| AsShotNeutral | G/WB，half-up 到六位小数，分母 1000000 | 与三个参考字段一致；也使用显式 WB 覆盖值 |
| CameraCalibration1/2 | Adobe 签名时由源日光 WB 和有界机身参考增益求对角矩阵，四位小数 | 三个样本均为 diag(0.9691,1,1.0591)，与参考一致 |
| CameraCalibrationSignature | 用户 profile 的 ProfileCalibrationSignature | 匹配时使用相应校准；无该签名时写单位校准 |
| BaselineExposure / Noise / Sharpness | 0.37 / 1.25 / 1.5 | 当前 OM-1 Mark II 默认范围的交接值，与参考一致 |
| 用户 DCP | 原字段类型/数量/数值完整保留，包括 copyright 和 embed policy | 不把 DCP tone、HueSatMap 或 LookTable 烘入线性像素 |

## 有意保留的容器差异

- `Software` 为 `colorpipe 0.1.0`；strip、Exif 目录与字段偏移重新分配，不与参考相等。
- `DNGVersion` 同为 1.4；`DNGBackwardVersion` 为 1.2，参考为 1.1。当前输出明确携带 1.2 profile 字段；不宣称支持旧于 1.2 的读取器。
- `WhiteLevel` 使用 LONG[3]，参考为 SHORT[3]，数值均为 65535。零黑电平、单位 AnalogBalance/LinearResponseLimit 可用不同的等值有理数表示。
- 保留源拍摄时间、曝光时间、光圈、焦距、曝光补偿、镜头名称、ISO 与处理域像素尺寸。Exif 指针全部重建；不做完整 Exif 字段或二进制恒等。
- 不移植参考的 GPS、机身序列号、DNGPrivateData/MakerNote、XMP、LensInfo、AntiAliasStrength、ShadowScale、BestQualityScale、NoiseReductionApplied。没有实现镜头像素校正，因此不会写虚假的 already-applied 声明。

每个样本的 `metadata.container_differences` 保存类型/数量/语义差异清单，不是全部原始字节差异清单。预览、缩略图、压缩、BigTIFF 和 opaque 厂商目录不在本轮范围。

## DCP 与读取器的覆盖边界

解析器支持有界 classic SDR 三通道 DCP：单/双光源矩阵、ForwardMatrix、HueSatMap、LookTable、单调 tone curve、编码及曝光/黑色渲染参数。拒绝未知高位 profile tag、链式 profile 目录、损坏指针、非有限值、无效矩阵或表维度；embed policy=2 时拒绝写入。不会搜索用户软件安装目录或自动选择另一个 profile。

三个真实样本使用用户提供的 Adobe Standard。其包含双光源、HueSatMap、LookTable，但没有显式 ProfileToneCurve 或 BaselineExposureOffset。RawTherapee 的 tone 选项可能依据 Adobe copyright 应用其默认曲线；这属于外部渲染器行为，不是本仓库分发的 LUT。完整外观验证与固定矩阵 ΔE 分开记录。darktable 的成功导出只用于证明 DNG 能读取，不据此声称它应用了同一套 DCP LUT。

输出先写同目录临时文件、flush/fsync，再以独占硬链接发布；已有文件或最终符号链接会拒绝。需要支持硬链接的文件系统（本轮 D 盘）；失败时清理本次临时文件，不覆盖其他文件，也不静默改用覆盖式写入。
