# 默认 HiFi 性能验证

P1 仅优化既有默认流程的数组访问与暂存。目标沿用交接：单线程 20MP<10 秒、50MP<40 秒、50MP 峰值内存<2 GB。数值门槛保持原样；不以误差增加交换速度。

## 测量方法

`tools/benchmark.py` 用独立解释器进程执行每次 RAW→DNG，支持多个 `--python` 指定冻结基线与候选环境，轮次间反转运行顺序。每个样本每个环境默认三轮；设置 OPENBLAS/OMP/MKL_NUM_THREADS=1。父进程核对用户 RAW 身份，worker 只将用户 RAW、DCP 和新输出交给生产转换；完成后再计算文件哈希并与已有报告比较。不同运行若输出或源码身份变化，报告失败。

`conversion_seconds` 从调用 `convert_raw` 到返回，包含解码、元数据与 profile 校验、全部像素运算和 DNG 写盘；没有阶段回调或 cProfile。它不含 Python 启动、导入、峰值内存读取及输出哈希。`worker_wall_seconds` 包含这些额外操作，不能冒充纯 CLI 延迟；完整 CLI 另行计时。

Windows 使用公开的 GetProcessMemoryInfo 读取进程生命周期峰值 working set 和 peak pagefile usage（commit）；不是在转换结束后只读取当前内存。字段定义见 [Microsoft 文档](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex)。RSS/working set 表示驻留物理页，commit 也单独记录。阈值采用十进制 2,000,000,000 字节，并同时展示 MiB/GiB。计数含该进程的导入与输入；不含父进程、其它应用或系统文件缓存。Unix 实现以 getrusage 提供峰值 RSS，本轮没有据此声称已做 Unix 实测。

## 复现

将需比较的两个 wheel 分别安装到独立 venv；下例解释器路径均为占位示例。复制 fixtures 模板到 fixtures.json 并填写本地路径。单环境测量可只传一个 --python。临时文件/缓存使用自己指定的目录。

```powershell
& ./.venv/Scripts/python.exe -B tools/benchmark.py `
  --fixtures fixtures.json `
  --profile '/path/to/user-supplied.dcp' `
  --python '.cache/baseline-venv/Scripts/python.exe' `
  --python '.venv/Scripts/python.exe' `
  --repeats 3 --expected-report out/m3/final/validation.json `
  --out out/performance/new-run
```

`--out` 必须是新目录。`--expected-report` 可省略，此时只检查每个环境自身的重复确定性，不声称与 M3 等价。可重复 `--case` 限定样本。工具的 PASS 表示输出/源码一致性检查通过，性能目标要另核对时间和峰值。JSON、独立 worker 日志及 DNG 均保留；失败也不删除输出。

剖析可另外使用 `python -m cProfile -o out/profile.pstats -m colorpipe input.orf new.dng --profile user.dcp`；该时间用于定位，不与无剖析的验收时间混算。初次 20MP 剖析的 16.97 秒中，滤波约 8.96 秒，通用五点排序约 5.13 秒；首轮排序/取数修正后约 10.83 秒，滤波约 2.42 秒。具体剖析、分块试验和最终数据位于 PROGRESS 指向的本地报告。

## 本机三轮交替 A/B

Intel Core i7-14650HX、16 核/24 逻辑处理器、约 16 GB RAM、Windows x64；CPython 3.14.0 / NumPy 2.5.4 / rawpy 0.27.1 / LibRaw 0.22.1。每次仅运行一个转换进程，M4 冻结安装环境与优化源码环境交替执行，均为单线程配置；不是清空系统缓存后的冷启动测试。

| 样本 | M4 API 中位秒 | 优化 API 中位秒 | 优化范围秒 | 加速倍数 |
|---|---|---|---|---|
| P7262257.ORF | 16.5914 | 7.9329 | 7.8185–7.9362 | 2.09 |
| P7262256.ORI | 16.6157 | 7.9693 | 7.8563–8.1621 | 2.08 |
| P7262256.ORF 50MP | 55.5197 | 23.5528 | 22.5942–27.1137 | 2.36 |

18 次输出全部与 M3 的相应 DNG 整文件 SHA 相同，每个环境各样本的三次源码身份/输出均一致。50MP 优化版三次最大 working set 为 **1,642,192,896 字节（约 1566.1 MiB / 1.529 GiB）**，峰值 commit 为 **1,669,103,616 字节（约 1591.8 MiB / 1.555 GiB）**，都低于 2,000,000,000。优化主要降低耗时，峰值内存仍与 M4 同一量级，不能宣称显著降低内存。

详细 A/B 为 `out/performance/ab-three-runs/benchmark.json`，硬件记录为 `out/performance/hardware.json`。源码与最终安装 wheel 的绑定、完整 CLI 墙钟及数值回归另见 PROGRESS。

## 安装版完整 CLI

另在全新 venv 普通安装优化 wheel，仅有默认 NumPy/rawpy 运行依赖；从空目录调用 console 入口，每个样本三次。使用父进程 perf_counter 在 subprocess.run 前后计时，SHA 在计时结束后计算。该口径包含启动、导入、参数校验、转换、写盘与正常退出。

| 样本 | CLI 中位秒 | 三次范围秒 | 严格目标秒 |
|---|---|---|---|
| P7262257.ORF | 8.1741 | 8.0971–8.9724 | <10 |
| P7262256.ORI | 8.1156 | 8.1042–8.1283 | <10 |
| P7262256.ORF 50MP | 23.0656 | 22.9161–23.1485 | <40 |

九次全部通过时间目标，且整文件 SHA 与 M3 相同。记录为 `out/performance/cli/validation.json`，包含确切入口、命令、返回码、运行时间、模块身份与 DNG 哈希。这里没有将 worker 包含额外证明操作的墙钟当作 CLI 耗时，也没有把 cProfile 时间混入表格。

## 保持的数值契约

五点比较交换网络只做 minimum/maximum；有限的 float32 输入保持原有顺序统计值。图像 halo 仍是物理边缘复制，输入检查先遍历各源条带一次。HiFi pass1 内域的规则奇偶采样用切片替代高级索引，边缘沿用原取样规则；pass2 递推/冻结融合、pass4 反馈限幅、全部权重与浮点加法次序不变。默认 tail 行块为 16。

合成测试固定 M4 的 float32/uint16 阶段字节；真实验证保持 M1 严格 max<200、M2 的 PSNR/SSIM/ΔE 及 M3 的 DNG/元数据/profile 检查。当前单机、三样本结果不能外推到其它硬件、RAW、ISO、profile 或多线程性能。较早 M4 包与其证据保存在原工作区；公开仓库的 dist/ 是当前优化版构建目录。

首个公开版本 0.1.0 来自此优化里程碑。已有同版本的历史本地包时，请使用新的 venv 或 --force-reinstall，并核对发行资产 SHA256。上述性能数字是原优化验收记录，不是每次 CI 的测量值；依赖复现见 BUILDING。
