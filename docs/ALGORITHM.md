# 算法：M1 前端与 M2 默认彩色 tail

本实现由 Python/NumPy 重新表达恢复的数学，不导入研究模块、DLL、机器码下放文本或捕获。当前仅支持 RGGB、偶数尺寸至少 8×8、每边 2 像素边界和默认 HiFi。输入是完整传感器 CFA，输出为 (rawH-4, rawW-4, 3) 的 RGB16。

## 单位与阶段

| 阶段 | 数据 | 单位/有效区域 |
|---|---|---|
| load_raw | uint16 H×W | 原始传感器码值；黑电平尚未扣除 |
| normalize_cfa | float32 H×W×3 | 仅原生 CFA 槽有效，缺失通道为 0；允许高光 >1 |
| prepare_cfa16 | uint16 H×W | 黑电平已扣除，白点缩放到 65535，仅在这里饱和量化 |
| pass1 | uint16 (H-4)×(W-4)×3 | 全部 G 和原生 R/B 有效，其它通道为 0 |
| pass2 | 同上 | 仅精修原生 G；保留其它样本 |
| pass3 | 同上 | 在非 G 站点补相反 R/B |
| pass4 | 同上 | 在 G 站点补 R/B；全部 RGB 有效 |

`RawImage.black/white` 保留传感器来源；输出 RGB16 的处理黑电平是 0、白点是 65535。后续 tail 应直接除以 65535，不能再次扣除原始黑电平。

## 归一化

电平顺序为 R,G1,G2,B。G 的黑白电平分别取两个绿相位的整数向下平均，先转换成 Python int，避免 uint16 相加溢出。

`n[c] = float32(max(sensor-black[c],0)) * float32(1/(white[c]-black[c]))`。

float32 输出不在 1 处截断。进入 HiFi 的准备值为 `floor(clip(n,0,1)*65535+0.5)`。这一次量化建立统一的工作单位；后续 pass 都使用 `epsilon = float32(65535)*float32(1e-5)`。

参考前端使用一次 `float32(65535/(white-black))` 直接乘传感器值；本实现保留可检查的线性 float 阶段后再量化，两次乘法的舍入可能产生 1 码差。本轮三个样本 prepared CFA 最大差均为 1；没有引入坐标、样本身份或查表补丁。

## Pass1：缺失 G

仅在 R/B 站点计算。选取 7×7 范围内的轴向、对角及 knight 邻点。±3 超出传感器范围时沿同一 CFA 相位折回到内侧 ±1，不使用通用镜像 padding。

每条轴取 `(g-3,c-2,g-1,C,g+1,c+2,g+3)`。构造五个相邻比值：

- `r0=(g-1+g+1+e)/(2C+e)`；
- `r-1=(2g-1+e)/(C+c-2+e)`，正侧同理；
- `r-3=(g-3+g-1+e)/(2c-2+e)`，正侧同理。

方向成本是 `|r-3-r-1|+|r-1-r0|+2(|r-1-r+1|+1e-5)+|r0-r+1|+|r+3-r+1|`。跨轴及对角比值参与成本修正。这里加的 1e-5 是无量纲比值的稳定项，与工作码值 epsilon 区别使用。

方向候选同时利用轴向 G 均值、同色二阶差、反绝对差权重、局部 G/C 比例修正和 0.2 的二阶预测项。两个方向最终按修正成本的平方倒数归一化融合。完整的对称公式见 `demosaic.py::_green_initial`；没有保留寄存器、机器地址或 SIMD 指令结构。结果饱和到 0..65535 后向零截断。

## Pass2：原生 G 精修

使用 pass1 已初始化 G 的 3×3 九点，其中 N/S/W/E 是插值得到的 G，不能用这些位置的原始 CFA 颜色替代。

四个方向的二阶误差为 `d = abs((g_minus+g_plus)/2-center)`。每个邻点的权重为 `e/(e+abs(g-center)+d_direction)`；中心权重为 `e/(e+0.25*min(d))`。九点加权平均后截断到 uint16。

只处理输出区域内每边再留 2 像素的原生 G。递推轨迹以从上到下的完整行顺序原地更新；同一行的写点相隔 2 像素，可向量化，各行保留依赖。此顺序与 chunk_rows 无关，也不复制参考 24-task 计划。

### 路线 B 的有界反馈融合

原地反馈会把任务交界处的行序差异放大。旧版全局递推在 20MP ORF 上出现 285 码最大 G 残差。直接冻结全部邻域又会使该样本最大 G 残差增到 1132；统一降低递推反馈也会引入其它大误差。因此保留完整递推轨迹作为锚，同时增加一个冻结候选，再限制融合改动。

令 `S` 为 pass1 G，`F` 为上面的九点数学。每行按同一顺序计算：

```text
R[y] = F(R[y-1], S[y], S[y+1])    # 原有确定性递推；R/J 均先截断为 uint16
J[y] = F(S[y-1], S[y], S[y+1])    # 同一九点核，邻域取 pass1 快照
G[y] = uint16(R[y] + clip((J[y]-R[y])/2, -128, 128))
```

上述差值均先转 float32，避免 uint16 相减溢出。`R` 保存在独立 G 平面中；融合输出不反馈到 `R`，因此原有确定性行序及其数值轨迹保持不变。冻结候选只需保留上一行的原始快照。非原生 G、未精修边界和 R/B 都不参与融合。

128 是 16 位工作域中半个 8 位步长 `65536/256/2`，作为全图统一的改动幅度；每个样本、每个位深和每个位置使用同一规则。它不限制相对参考图的误差，也不保证未知图像通过 max<200；严格门槛仍由全幅验收独立检查。

这是路线 B 新增的稳定化数学，不能宣称是原核的逐 bit 重现。原有方向集、二阶系数、反绝对差权重和乘性颜色比值仍保留。测试工具的观测行序诊断只运行未融合九点核，用来区分数值核与调度影响，不能把诊断结果作为生产验收。

## Pass3/4：G 引导的乘性颜色恢复

四邻点权重为 `wi=e/(abs(Gi-Gc)+e)`，归一化后计算 `Gbar=sum(wi*Gi)` 和 `Cbar=sum(wi*Ci)`。

颜色输出为 `Cbar * (Gc+e)/(e+0.3*Gc+0.7*Gbar)`，饱和后截断。必须使用乘性比值，不能替换成简单均值或 R-G 加性色差。

- pass3：在 R/B 站点用对角四邻点恢复相反颜色；图像边界的 G 引导来自完整准备 CFA 的对应原生 G。
- pass4：在 G 站点用 N/W/E/S 四邻点恢复 R/B；边界退回原生 CFA 的横向/纵向均值。

Pass3 读取的中心及对角点都是非 G 站点，其 G 不在 pass2 写集中，所以输出与原有递推版本相同。Pass4 的四邻点也都是非 G 站点，只有中心 G 受融合影响。利用这一点，以 `R[y]` 和融合 `G[y]` 分别代入相同的颜色比值公式，得到 `C_recursive` 和 `C_fused`，最终采用：

```text
C = uint16(C_recursive + clip(C_fused-C_recursive, -128, 128))
```

这一步抑制融合后的 G 经反绝对差权重放大成颜色跳变。单独对 G 做有界融合而不约束颜色，在本轮三个样本中会出现新的 RGB 大残差，不能省略此约束。边界继续使用原 CFA 均值，不经过该修正。

边界、任务交界行和所有通道都纳入全幅指标，没有裁掉误差较大的点。

## 对交接摘要的修正

- `0x31560` 是去马赛克后的 RGB16→float 准备；不是 CFA 解码器，也不是本轮归一化参考的同阶段 float oracle。
- pass1 的完整方向比值、对角参考和二阶预测不能由摘要的单条 0.375 候选式替代。
- pass2 数值核使用九点权重及中心 `0.25*min(d)`，不是摘要所写的 0.66 软选择。

这些修正来自只读数值参考及三个真实 RAW 的逐阶段验证。归一化的比较基线是 `prepared.cfa16/65535`，属于量化后的同阶段参考，不能据此宣称与未捕获的前端 float 值逐 bit 相同。

## M2：默认彩色 tail 的输入与设置

`tail.run_tail(rgb16, raw, settings, stage_callback=None, *, chunk_rows=16)` 接收 M1 的完整处理域 RGB16，返回同尺寸 RGB16。先乘 `float32(1/65535)`，不再应用传感器 black/white。必须有真实 ISO、pixel_scale 和 WB（WB 可由显式设置覆盖）；缺失值报错。M2 仅验证默认 HiFi、曝光 0、16-bit；v3 明确拒绝。

WB 比例为 `ratios=wb/max(wb)`。正向 tone 前先乘比例，逆 tone 后除回比例。所有通道和全部活动像素都处理，不读参考图或任务计划。

## M2 Tone：公式生成正向和逆向 LUT

令 `T=max(1,max(wb))`、`a=2^3.5`、`r=min(7.5,max(1.02607,log2(T))+3.5)`。以二分法求正根 `k`：

```text
log(1+(2^r-1)*k)/k = a-1
f(u) = a*u                              if a*u <= 1
       1 + log(1+k*(a*u-1))/k           otherwise
tone(x) = (f(T*x)/f(T))^(5/12)
```

本实现直接以 float64 计算连续曲线，并用分段线性/指数闭式求逆。分别在 65536 个位置采样、half-up 量化到 uint16，固定端点 0 和 65535；缓存的 LUT 只读。没有复制原 LUT，也不复刻参考的 1024 结点抛物端点三次样条或 OS `logf` 舍入。这是明确的路线 B 数值差异；同输入全幅对照见 PROGRESS。

正向查表索引为 `floor(clip(n*ratios,0,1)*65535+0.5)`，查表结果转回 float32/65535。逆向使用同样的索引规则。

## M2：3×3 中值引导滤波

每个通道独立处理，顺序 G、R、B。对中心和十字四邻点、中心和对角四邻点分别排序，得到中值 `mx/md`、第二小和第二大值。

性能实现使用九次比较交换的五点排序网络（逐元素 minimum/maximum），替代对每个像素调用通用短数组排序。120 种严格顺序及 32 种二值输入均与完整排序一致；非有限输入在排序前统一拒绝。每个源像素只验证一次，随后以带真实 halo 的行块及切片读取九邻域，复制只发生在物理图像边缘。权重、加法顺序和 float32 舍入不变；默认 tail 行块由 32 改为 16，只调整暂存大小。

- 中心同时为两个集合的最大值时，选与中心更近的中值（相等选十字），`q=(2*m+second_high)/3`。
- 中心同时为两个集合的最小值、且不是前一分支时，`q=(2*m+second_low)/3`。
- 令 `delta=max(abs(center-q)-abs(mx-md),0)`；`guide=q*t+center*(1-t)`，其中 `t=min(delta/B,1)`。非极值时 guide=center。
- 九点权重 `wi=1/(abs(pi-guide)+1/A)`，输出为加权平均，饱和至 0..1。使用普通 float32 除法与求和，不仿真 VRCPPS 或 SIMD 分组。

`A=4096/s`、`B=0.25/s`。选择 s 的 ISO 上界与数值为：200→1，400→1.19，800→1.41，1600→1.68，3200→2，6400→2.38，12800→2.83，25600→3.36，51200→4，102400→4.76，204800→5.66；更高为 **6.73**。处理像素数小于 17,000,000 时，选择滤波参数前先把 ISO 加倍；不改源元数据，也不改变 RL 的 ISO 判断。

边界复制活动图像的实际边缘，不引入参考的 64B pitch 零 padding；分块仍从完整源平面读取邻域，不把 chunk 边缘当图像边缘。输入 float32 必须有限且位于 0..1。

## M2：G/色差与仅 G 的两次 RL

低通 RGB 转为 `[G, DR, DB]`，其中 `DR=0.5*(R-G)+0.5`、`DB=0.5*(B-G)+0.5`。仅在真实源 ISO<12800 时对第 0 通道运行两次 Richardson–Lucy，两个色差平面逐 bit 保留。

令 `v=传感器原始宽度*pixel_scale/4000`，`sigma=0.4`（v<=1），否则 `sigma=0.2*(sqrt(v)+1)`。再乘源 ISO 档位因子：≤400 为 1、≤800 为 0.9、≤1600 为 0.8、≤3200 为 0.7、≤6400 为 0.6、<12800 为 0.5。这里使用传感器宽度，不使用裁掉每边 2 像素的处理宽度。

PSF 是归一化的 `3×3 exp(-(dx²+dy²)/(2*sigma²))`。从观测 G 初始化估计，迭代：

```text
blur = PSF * estimate
ratio = observed/blur                   if abs(blur) > 0.5/65535, else 0
estimate *= PSF * ratio
```

迭代结束后绝对值不超过半码的结果置零。边界在迭代前一次性复制，外延值随后参与演化，不能每次卷积重新复制活动边界。两次迭代共四次半径 1 卷积，因此自有行条带带 4 像素 halo 即可得到完整图像操作；已与独立 float64 大画布验证，结果不随 chunk_rows 改变。不复制参考的 RL tile 几何、FMA 分组或尾部 SIMD 路径。

## M2：还原、逆 Tone 与量化

还原 `R=G+(2DR-1)`、`B=G+(2DB-1)`，G 为 RL 后结果；对全部 RGB 做逆 LUT，除回 WB 比例。`rgb_linear` 回调保留这时可能超过 1 的值；最终 half-up 饱和量化为 uint16。

全部活动 G 都采用处理后的 G，不模拟参考在未对齐宽度上的连续字节前缀拷贝。该内存布局差异只属于测试对照说明，不进入生产坐标分支。

依次提供 `normalized`、`weighted_tone`、`filtered_rgb`、`default_diff`、`default_deconvolved`、`rgb_linear`、`quantized` 七个回调。回调借用可变工作数组，需要保留阶段时自行复制；输入 RGB16 始终不变。没有写 DNG 或应用 DCP，这两项仍属于 M3。

## M2：像素、结构与色差验收

最终 camera-linear RGB16 直接对照原 parent DNG 的像素。PSNR 使用峰值 65535，最大误差和固定矩阵 D50 Lab 的 ΔE00 均包含全部活动像素与边界。阶段 float 比较的峰值为 1；便携参考和直接原生捕获分别标记来源。

SSIM 使用 scikit-image 的 7×7 均匀窗口、样本协方差、K1=0.01、K2=0.03、data_range=65535，RGB 三通道等权平均。标准 SSIM 的中心域为 `(H-6)×(W-6)`；外圈 3 像素仍进入相邻窗口，但不作为窗口中心。每个行块带 3 行 halo，只累计属于该块的中心，防止分块边界漏算或重复。没有缩图、抽样、误差 mask 或改变 PSNR/最大误差/ΔE 的全幅统计域。

验收分别检查 M1 max<200、最终 tail PSNR>40、SSIM>0.98、固定矩阵 ΔE00 平均<2 和 p95<4。SSIM 同样属于相机线性像素诊断；完整 DCP 外观及 DNG 容器兼容性由 M3 单独验证。

## M3：线性 DNG 与用户 profile

`pipeline.convert_raw(input, output, settings, stage_callback=...)` 贯通解码、归一化、四 pass、默认 tail 与 `writer.write_dng`。转换前验证设置、输出是否已有文件以及用户 DCP 的基本有效性和嵌入权限。生产不调用外部 RAW 软件，不读参考图或 DNG 模板。

DNG 写入完整处理域的 uint16 RGB，PhotometricInterpretation=LinearRaw(34892)、SamplesPerPixel=3、无压缩单 strip。black=0、white=65535；相机建议裁切从源传感器坐标转换到处理域。方向保存在 tag 中，像素不旋转。全部目录/字段偏移独立构造，写完再独占发布。

用户 DCP 按类型、数量与规范 little-endian 数值字节嵌入。白平衡写成六位小数 AsShotNeutral；Adobe 签名的机身校准为 `diag(reference_camera_gains / source_daylight_wb)`，四位小数；其它支持的无签名 profile 使用单位校准。当前机身的参考增益及基线标量来源与边界见 LEGAL，容器和元数据差异见 METADATA_DIFFERENCES。

完整 DCP 外观由测试工具调用 RawTherapee：共同的相机 WB、自动光源选择、HueSatMap、LookTable、可用 tone 与 baseline offset 选项，输出统一 RTv4_sRGB RGB16。分别比较内嵌 profile 与显式指定同一 DCP，以及本实现 DNG 与参考 DNG。另用关闭组件与固定光源端点的渲染做诊断，不把它们替代为最终结果。标准 sRGB 解码至 D65/2° Lab 后计算全幅 ΔE00；此指标与 M2 固定 D50 矩阵指标的定义不同。

字段依据 [Adobe DNG 1.7.1](https://helpx.adobe.com/content/dam/help/en/camera-raw/digital-negative/jcr_content/root/content/flex/items/position/position-par/download_section_733958301/download-1/DNG_Spec_1_7_1_0.pdf)；外部处理选项及 Adobe copyright 曲线行为见 [RawTherapee Color Management](https://rawpedia.pixls.us/color_management/)。外部软件及其代码没有进入生产依赖。
