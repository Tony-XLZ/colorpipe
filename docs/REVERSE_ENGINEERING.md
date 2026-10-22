# 目标程序逆向档案：Iridient O-Transformer 4.5（Win64）

本文件记录**被研究对象**（闭源转换器）的可观察结构与输出契约，用于解释 `colorpipe` 的设计取舍和覆盖边界。
它不是 colorpipe 的实现文档（见 [ARCHITECTURE](ARCHITECTURE.md)、[ALGORITHM](ALGORITHM.md)），也不含任何被研究程序的代码、反编译文本、厂商 profile 或用户照片。

## 0. 证据等级与方法

| 等级 | 含义 | 本文用法 |
|---|---|---|
| 观察 | 由文件字节、PE 结构、RTTI、字符串、注册表、用户自有输出文件直接读出 | 表内默认 |
| 推断 | 由类名/符号/调用形态推得，未经动态确认 | 显式标注「推断」 |

方法：只读静态检查（PE 头与节表、导入表、ASCII/UTF-16 字符串、MSVC RTTI 类名）、阅读随程序分发的 Lightroom 插件字节码常量、读取本机注册表设置项、解析用户自己用该程序导出的 DNG 容器字段。
未做：修改/打补丁、绕过许可或水印、把反编译文本带入本仓库、再分发任何厂商二进制或 profile。

分析对象：

| 文件 | 大小 | SHA256 |
|---|---|---|
| `Iridient O-Transformer.exe` | 37,338,920 | `ca5659131398f04d425afa47f6bf937051b24ee6e671f5749bcc21ea8ce1658d` |
| `libraw.dll` | 1,497,384 | `bb7ac84ac8b92e8188d9ddc287d8935c01b4c64b9295dc8745f6a25f60129867` |

## 1. 二进制身份

- PE32+ / x64，14 个节；`.text` 约 21 MB，`.rdata` 约 11 MB，`.xdata` 约 1.8 MB（C++ 异常表），另有 `IPPCODE` / `IPPDATA` 静态库节。非 .NET，无托管元数据。
- 版本资源：`4.5`，`(c) 2004-2026 Iridient Digital, Inc.`。
- 应用主类 RTTI 为 `IridientXTransformerApp`。该产品与同厂商 Fujifilm 版 X-Transformer 共享代码库（推断：主类名未随产品改名）。

## 2. 技术栈（版本均由程序内字符串/RTTI 直接观察）

| 组件 | 证据 | 链接形态 |
|---|---|---|
| wxWidgets 3.1.1 | `wx*` RTTI、`XRC_resource/...wxWidgets-3.1.1...`、`wx/ipcbase.h` 等源路径 | 静态 |
| OpenCV 4.12.0 | `cv::` 符号、编译期路径 `opencv-4.12.0\modules\...`、含 OpenCL 后端与 AVX2 分派 | 静态 |
| Adobe DNG SDK 1.7.1 | `Adobe DNG SDK v1.7.1`、`dng_*` RTTI、`libjpeg 9d (used by DNG SDK)`、JXL 任务符号 | 静态 |
| LibRaw 0.22.0-Release | `0.22.0-Release`、`libraw.dll` 导入 | 动态 |
| Intel IPP | `IPPCODE` / `IPPDATA` 节 | 静态 |
| tinyxml2 | `XMLComment@tinyxml2` RTTI | 静态 |
| OpenCL | `opencl.dll` 导入、`clCreate*` / `clBuildProgram` 字符串 | 可选动态 |

注意：DNG SDK 与 IPP 都是**不可再分发的商业许可组件**。本仓库不包含、不链接、也不移植它们；`colorpipe` 的 TIFF/DNG 写入器是独立实现（见 [LEGAL](LEGAL.md)）。

## 3. 应用层结构（RTTI 观察）

DNG 适配层（在 DNG SDK 之上包一层自有 host/writer）：

- `bg_dng_host`、`bg_dng_image_writer`、`bg_dng_buffer_image`、`bg_dng_file_stream`、`bg_dng_abort_sniffer`

镜头校正（Adobe LCP 语义：几何 warp + 径向晕影）：

- `bg_lcp_filter_warp`、`bg_lcp_inplace_vignette`、`bg_lcp_warp_params_fisheye`、`bg_dng_warp_params_rectilinear`、`bg_dng_resample_ginseng`

自有 float32 图像算子（均以实现 `cv::ParallelLoopBody` 的 `*_ParallelProcess` 类承载）：

- `Bilateral_ParallelProcess`、`BoxFilter_ParallelProcess`、`Convolve_32F_ParallelProcess`、`Dilate_32F_ParallelProcess`、`Dist_32F_ParallelProcess`、`ApplyEdgeMask_32F_ParallelProcess`、`ToneCurve16U_ParallelProcess`
- 算术族：`Add_32F` / `Sub_32F` / `AddC_32F` / `MulC_32F` / `MulCAddC_32F` / `MulCAddC_Clip_32F` / `AddWeighted_32F` / `Pow_32F` / `Clip_32F` / `Blend_32F`

进程与单实例：

- `IridientServer`、`IridientClient`、`IridientConnection`（推断：基于 wxIPC 的单实例转发，用于把第二次启动的文件参数交给已运行实例）。

## 4. 外部接口

### 4.1 Lightroom 插件（随程序分发的 Lua 5.1 字节码）

可观测量（字节码常量与文件名）：

- 插件把待处理主文件写入插件目录下的 `IridientOTransformerTemp.xml`，元素含 `masterRawFilePath`；随后以 `openFilesInApp` 拉起 `Iridient O-Transformer.exe`（推断：传入该 XML 或占位文件）。
- 默认文件名规则：后缀 `-IridientEdit`；默认子目录 `IridientOTransformerImages`。
- 转换完成后轮询输出文件大小/属性，再通过 `withWriteAccessDo` 导入目录。
- 插件目录还含 `LaunchHelper.txt`（占位文本）与 `LaunchIridientOTransformer.lua`（仅用于打开设置界面）。

即：**程序的外部批处理入口是「XML 文件清单 + 启动参数」，而非命令行开关**。程序内未见 `--xxx` 形式的参数解析字符串。

### 4.2 设置存储

- 注册表：`HKCU\Software\Iridient Digital\Iridient O-Transformer`，分组键为 `dngOptions`、`rawOptions`、`fileNameOptions`、`saveToOptions`、窗口位置等。
- 预设：`%APPDATA%\Iridient O-Transformer\Presets\*.iotp`（观察为非纯文本容器）。
- 程序内可读出的配置路径共 56 条，例如：
  `/dngOptions/{bitDepth,compressionOptionV4,compressionType,cameraProfileType,previewSize,previewQuality,preserveExif,preserveMakernote,preserveIptcXmp,lockOutputFile,overwriteMake,overwriteModel,...}`
  `/rawOptions/{rawProcessTypeV4,combinePixelShift,sharpeningLevelV2,sharpeningMaskingLevel,luminanceNoiseReductionLevelV2,colorNoiseReductionLevelV2,clarityLevel,lensCorrectionsType,useLensDistortionCorrection,useLensChromaticAberrationCorrection,useLensVignettingCorrection,...}`
  `/fileNameOptions/{part1..part4,caseFormat,dateFormat,separatorFormat,sequenceStart,sequenceDigits,sequenceIncrement,extFormat}`
  `/saveToOptions/{saveToLocation,folderPath,preserveSubfolders,saveToSubfolderName,openWithApp,openWithAppPath}`

这些键名是本项目对照「同一设置语义」的唯一依据；`colorpipe` 不读写注册表，也不实现该设置面板。

### 4.3 许可与日志（仅记录，不实现）

- 许可文件 `IridientOTransformer.idLicense`（XML/plist，含 Paddle 订单字段与签名）；未注册时导出加水印。
- 程序内有 `Iridient O-Transformer Log` 日志标识。
- 本仓库不实现、不绕过、不分析其签名校验；`colorpipe` 与该许可体系无关。

## 5. DNG 输出契约（对用户自产样本的实测）

样本：本机由该程序导出的 20MP 与 50MP DNG（OM-1 Mark II，16-bit，未压缩，默认 HiFi，Adobe Standard profile）。

| 字段 | 50MP 样本 | 20MP 样本 |
|---|---|---|
| 容器 | classic TIFF，little-endian | 同 |
| `DNGVersion` / `DNGBackwardVersion` | 1.4.0.0 / 1.1.0.0 | 同 |
| `ImageWidth`×`ImageLength` | 8168×6128 | 5216×3908 |
| `BitsPerSample` / `SamplesPerPixel` | 16,16,16 / 3 | 同 |
| `Compression` | 1（未压缩，单 strip） | 同 |
| `PhotometricInterpretation` | 34892（LinearRaw） | 同 |
| `DefaultCropOrigin` / `DefaultCropSize` | (4,4) / 8160×6120 | (10,10) / 5184×3888 |
| `BlackLevel` / `WhiteLevel` | 0,0,0 / 65535×3 | 同 |
| `ColorMatrix1/2`、`CameraCalibration1/2` | 双光源矩阵 + diag(0.9691,1,…) | 同 |
| `AnalogBalance` / `AsShotNeutral` | 1,1,1 / 相机 WB | 同 |
| `BaselineExposure` / `Noise` / `Sharpness` | 0.37 / 1.25 / 1.5 | 同 |
| `LinearResponseLimit` / `AntiAliasStrength` / `ShadowScale` / `BestQualityScale` | 均为 1.0 | 同 |
| 内嵌 profile | `Adobe Standard`；HueSatMap 90×30×1；LookTable 36×8×16；`ProfileEmbedPolicy` 0 | 同 |
| `DNGPrivateData` | ≈1.8 MB，前缀 `Adobe\0MakN`（Adobe MakerNote 容器） | 同 |
| 预览 | 该批样本无 `SubIFD` / `PreviewImage`（预览设为 None） | 同 |
| `Software` | `Iridient O-Transformer 4.5 (Win64)` | 同 |
| 其他 | XMP 直通；Exif/GPS 目录重建；`LensInfo`、`CameraSerialNumber`、`NoiseReductionApplied=0.01` | 同 |

两点值得记录的偏差/特性：

1. 标签 `0xC68B` 规范定义为 `OriginalRawFileDigest`（原始 RAW 的 16 字节摘要），样本中写入的是原始文件名 ASCII（如 `P7262256.ORF`）。按规范读取的软件会把它当摘要，长度也不符（13 字节）。
2. 开启「应用到像素」的镜头校正样本中，几何 warp 与晕影被**烘焙进像素**，没有 `OpcodeList2/3`；同时 `DefaultCropOrigin` 由 (4,4) 变为 (10,10)，处理域包含校正后的边界扩张。这正是 `colorpipe` 不写「已校正」声明的原因（见 [METADATA_DIFFERENCES](METADATA_DIFFERENCES.md)）。

## 6. 处理链重建（观察 + 既有阶段研究）

外部可确认的链路顺序：

```text
LibRaw 解包(ORF/ORI) -> 黑/白归一化 -> HiFi 去马赛克(4 pass)
   -> 默认 tail：白平衡 / 色调曲线 / 中值引导滤波 / 仅 G 的 RL
   -> 镜头校正(可选，LCP：几何 + 色差 + 晕影)
   -> DNG SDK 封装(16-bit LinearRaw + 内嵌 profile + MakerNote 容器)
```

- 是否应用降噪/锐化由 `rawOptions` 决定；默认档位在样本中体现为 `NoiseReductionApplied=0.01` 与 `BaselineSharpness=1.5`。
- 50MP 路径（`rawProcessTypeV4` 高位档）与 20MP 默认路径共用同一容器写法，只是处理域不同。
- 算法级细节（pass 顺序、权重、反馈幅度）不在此重复：[ALGORITHM](ALGORITHM.md) 记录了本项目据此重建并验证的版本。

## 7. 与 colorpipe 的覆盖对照

| 能力 | 目标程序 | colorpipe v1 |
|---|---|---|
| 20MP 默认 HiFi（ORF/ORI） | 支持 | 支持（视觉等价，PSNR ≈92–105 dB） |
| 50MP 高分辨率 ORF | 支持 | 支持（同链路，处理域 8168×6128） |
| 16-bit 未压缩 camera-linear DNG | 支持 | 支持 |
| 用户提供 DCP 内嵌 | 支持（Adobe/Iridient 内置 profile） | 仅用户提供；不捆绑厂商 profile |
| 镜头校正（几何/CA/晕影） | 支持（LCP，可烘焙或写元数据） | 未实现（v1 范围外） |
| 非默认降噪/锐化/Clarity | 支持 | 未实现 |
| v3 / 单色 / 其他机身 | 支持 | 未实现（仅 OM-1 Mark II 验证） |
| 8/10 位、有损/无损压缩、预览 | 支持 | 未实现（固定 16-bit 未压缩、无预览） |
| EXIF/GPS/MakerNote/XMP 直通 | 支持 | 有意不写（避免伪造未实际执行的处理声明） |

## 8. 边界声明

- 本文只描述可观察行为与公开字段语义，**不包含**被研究程序的代码、反编译结果、常量表、profile 数据或任何厂商二进制。
- 本项目未使用 Adobe DNG SDK / Intel IPP / OpenCV / wxWidgets 的代码；`colorpipe` 的运行时依赖只有 NumPy 与 rawpy(LibRaw)。
- 不使用、不绕过、不再分发许可文件或水印机制；不以本文推断实现任何规避功能。
- 该档案不构成法律意见；发布前的许可/专利审查边界见 [LEGAL](LEGAL.md)。
