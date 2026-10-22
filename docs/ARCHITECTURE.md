# 架构

```text
CLI (cli.py)
  -> decode.load_raw        LibRaw/rawpy -> CFA + metadata
  -> normalize.normalize_cfa black/white -> float32 native-site planes
  -> demosaic.demosaic      HiFi 4-pass (v3 unsupported)
  -> tail.run_tail          WB/tone/filter/G+diff/RL/quantize
  -> writer.write_dng       16-bit uncompressed DNG + tags + user DCP
```

## 数据流

- `RawImage`：CFA、black/white、pattern、crop、ISO、pixel_scale、metadata。
- `normalize`：保留“哪些是实测、哪些是插值”的信息；缺失站点为 0。
- `demosaic`：输出 interleaved RGB16。
- `tail`：G + 色差表示，RL 只作用 G。
- `writer`：camera-linear RGB DNG。

## M0 已实现契约

- `decode.load_raw` 只调用 rawpy 的解包，复制完整 `raw_image`，不调用 postprocess、不旋转、不归一化、不裁切。
- `metadata.read_orf_metadata` 用新的有界 TIFF/EXIF/MakerNote 读取器获取必需字段，不导入研究项目。像素解包仍完全交给 LibRaw。
- `RawImage.width/height` 总是完整 CFA 尺寸；`processing_size` 仅计算每边 2 像素边界后的宽高；`camera_crop` 独立保存源 MakerNote 的 x,y,w,h；LibRaw 可见区域记在 metadata 中。
- `black/white` 按 R,G1,G2,B 排列。LibRaw 通道编号通过完整传感器原点的 `raw_color` 映射到这个顺序，不通过 `color_desc` 字符串猜 Bayer 布局。
- MakerNote BlackLevel2 的 12 位单位乘以 2^(ValidBits-12)，与 LibRaw 黑电平逐相位核对。传感器白电平取 2^ValidBits-1，并核对 LibRaw white_level；camera_white_level_per_channel 作为独立相机白点保留。
- `wb` 从源 WB_RBLevels 的 R/B/G1/G2 读取，要求两个绿参考相同且为正，转换为 G=1 的 RGB，并与 LibRaw 的有效 RGB 倍率交叉检查；未使用的第四项不参与有效性检查。
- `iso` 来自 EXIF 0x8827；`pixel_scale = 43.2 / FocalPlaneDiagonal_mm`，对角线来自 Equipment 0x0103 的有理数。
- M0 的缺失/不支持元数据明确拒绝；单元测试中的合成 RawImage 可使用 None 表达未知 ISO/WB/scale，不编造默认值。

字段身份参考：[rawpy API](https://letmaik.github.io/rawpy/api/rawpy.RawPy.html)、[Olympus 标签表](https://exiftool.org/TagNames/Olympus.html)。像素尺度公式、黑电平单位和比较基线来自只读交接研究材料，实测范围见 PROGRESS。

## 验证边界

`tools/validate_m0.py` 是本地验收工具。它验证用户 RAW 身份、读取研究 `artifact_manifest.json` 定位并校验参考元数据/CFA、逐块全幅比较；这些读取均不进入 `src/colorpipe`。生产 `--inspect` 只接收一个 RAW 路径，不接收 oracle 或参考目录。

## M1 已实现

`normalize_cfa` 输出完整传感器域的稀疏 float32 RGB；原生值按 R/G/B 电平去黑缩放，缺失通道为 0，不截高光。`prepare_cfa16` 在进入 HiFi 时统一量化为 0..65535，随后 pass1/2/3/4 全部使用该工作单位。

`demosaic` / `demosaic_hifi` 返回裁掉每边 2 像素的 RGB16，可接收阶段回调。回调数组仅借用：pass2/3/4 会继续修改同一 RGB buffer。归一化输入和原始 CFA 保持不变。

Pass1 的采样跨 7×7，按同 CFA 相位折叠 ±3 边界。Pass2 的递推轨迹仍按全局从上到下行序原地更新 G；单行内不同 native-G 写点的读集合互不依赖，可以向量化。同时用一行原始快照计算冻结邻域候选，对两者中点做相对递推值 ±128 码的有界融合。保留一个独立 uint16 G 平面作为递推轨迹，融合值不反馈到该轨迹。

Pass3 只读取未被 pass2 改动的非 G 站点，输出与未融合版本相同。Pass4 分别以融合 G 和递推 G 为中心计算颜色比值，将颜色变化限制在递推估计的 ±128 码内；无需第二个 RGB buffer。原生 R/B 和边界回退保持其原有契约。chunk_rows 只影响暂存大小，测试验证不同块大小输出相同。

本轮源码仅依赖 NumPy。`tools/validate_m1.py` 在独立预测全部写盘后，才打开参考像素比较；参考路径与哈希来自 stage index 和原 manifest。测试专用的观测行序诊断与生产逻辑分离，不能将该诊断的较低残差当成生产结果。

M1 输出已经去黑/缩放，后续 tail 只能按 RGB16/65535 转 float；`RawImage.black/white` 是来源元数据，不能再次应用。算法详见 ALGORITHM；三个全幅样本通过严格 max<200，指标和稳定化代价见 PROGRESS。

## M2 已实现

`tail.run_tail` 只接受 M1 的 RGB16 和本次输入的元数据。`tone.py` 从连续曲线及闭式逆函数生成 LUT；`filter.py` 实现有限值域的中值引导九点滤波；`rl.py` 使用自有条带与 4 像素 halo 对 G 做两次 RL。生产仍只依赖 NumPy，没有研究模块、原二进制或捕获路径。

工作域为独立 float32 HWC buffer；低通后原地转成 G/DR/DB，再仅替换 G。逆变换覆盖全部活动像素，最后输出 uint16。输入与源 black/white 保持不变；源宽度、ISO、pixel_scale 决定 RL，而小图 ISO 加倍只影响滤波。

`tools/build_m2_test_oracles.py` 是隔离的测试工具：只读研究实现，在其已校验的参考前端输入上生成阶段基线，硬件倒数/FMA helper 被 NumPy 数学替换，不执行目标代码。该工具不属于生产依赖。`validate_m2.py` 从真实 RAW 独立完成 M1+M2 后，才读取阶段和原 DNG 像素；原生阶段与便携数值阶段分别标记。`diagnose_m2_tail.py` 的参考前端同输入实验仅用于拆分 M1 传播和 tail 核差异，不算生产验收。

ΔE 是验证工具使用参考 DNG 的固定 ForwardMatrix2、CameraCalibration2、AnalogBalance 和 AsShotNeutral 计算的 D50 Lab / CIEDE2000。没有用相机 RGB 直接冒充 sRGB，也不声称包含 DCP 的双光源插值、HueSatMap、LookTable 或最终渲染；计算定义与数值见 PROGRESS。

## M3 写入与转换入口

`pipeline.py` 组合已有 M0–M2 数学及 writer；CLI 的单输入转换入口调用同一函数，`--inspect` 保留原有行为。用户必须显式提供 DCP，预检失败时不解码 RAW，不静默寻找或替换 profile。

`tiff.py` 是有界的 typed classic TIFF 字段/目录编解码器，`dcp.py` 校验用户 classic SDR 三通道 profile。`writer.py` 构造新的 root/Exif 目录及 payload，保留全部后 tail 像素；原子发布完整文件并拒绝覆盖。没有 DNG SDK 或厂商 writer 二进制依赖。

`validate_m3.py` 完成独立 RAW 预测后，再读取测试 oracle，分别检查像素回读、M1/M2 门槛、36 项关键元数据与用户 DCP 字段字节。`render_m3.py` 在独立设置/缓存目录中调用官方 RawTherapee/darktable CLI；前者验证完整可用 DCP 处理及 profile 内嵌/显式两种路径，后者验证读取。两者只属于可选的外部验收工具。全部运行产物在 `out/`，不会作为生产输入。

## 确定性

- v1 单线程；同一输入同一设置输出确定。
- 不复制原程序的 task order/64B pitch；路线 B 只要求视觉等价。

## 参考

- [算法与阶段契约](ALGORITHM.md)
- [构建和测试](BUILDING.md)
- [验证记录](PROGRESS.md)
- [来源](LEGAL.md)
