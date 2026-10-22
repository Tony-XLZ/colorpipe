# 独立优化版 0.1.0 验证

2026-10-22 从优化里程碑 `perf-hifi` 导出为独立项目。新 Git 历史仅包含当前公开文件，原工作仓库保持不变。个人工作站路径改为模板；16 个生产模块与原优化版的可执行 AST 相同，仅替换部分模块说明的文档引用。项目可自行构建、安装及运行公开测试，不需要研究交接目录。

## 本次独立包验证

- 从本项目 sdist 构建纯 Python wheel，twine 严格元数据检查及实际归档资产检查通过。
- 新 venv 普通安装 wheel，默认依赖 NumPy 2.5.4 / rawpy 0.27.1；pip check 通过，模块确实来自 site-packages。
- 添加已验证的 dev 依赖，从解压的 sdist 使用 `python -I -B` 测试已安装 wheel：**197 passed，0 failed，0 errors，0 skipped，417.84 秒**。
- 其中公开合成测试 185 项，私有真实 M0–M3 集成用例 12 项。九份 M1/M2/M3 报告与优化基线的阶段指标/哈希一致，M1 严格 max<200、M2 PSNR/SSIM/ΔE 及 M3 元数据/profile 门槛不变。
- 54 个生产/测试/工具 Python 文件与实际测试的 sdist 一致；16 个生产模块在工作树、wheel 和安装环境中逐字节一致。
- 在仅默认依赖的环境中另执行三个真实 CLI 转换，三个 DNG 整文件 SHA256 与优化基线一致。此次为转换/输出身份检查；性能数值仍采用 [PERFORMANCE](PERFORMANCE.md) 的独立受控三轮测量，不将并发打包期间的 smoke 运行作为性能复验。
- 公开文件的照片/profile/二进制排除、常见凭据格式、个人路径及本地 Markdown 链接检查通过。

完整 JUnit、阶段报告、归档检查和绑定记录保存在本地忽略目录 `out/`，不公开用户图像或参考资料。此摘要公开测试方法及结论；它不使私有真实基线变为可公开复现数据。构建命令和私有集成输入说明见 [BUILDING](BUILDING.md)。

## GitHub CI

GitHub 发布验证补充：首次远程矩阵的构建/归档检查通过，合成用例因新解压目录缺少 `.cache` 父目录而出现 fixture 初始化错误。现由工作流显式创建该目录，并同步修正安装包测试命令；生产模块、测试断言与数值门槛不变。远程 Windows/Linux × Python 3.11/3.14 的实际结果见 [GitHub Actions](https://github.com/Tony-XLZ/colorpipe/actions/workflows/ci.yml)，这些合成结果不扩展为跨平台真实图像验收。

## 输出身份

| 样本 | 最终 DNG SHA256 |
|---|---|
| 20MP ORF | 1406094e0f86c7468abdc6bc6e2bb3a0ed40042926a7136336510cd7d52614f9 |
| 20MP ORI | 0208d3a36306fa84b78b4869d35b9ad70f05f8846dd3ec757ceb04fb3d061566 |
| 50MP ORF | 619d5a2feb91819bba7a8a4151fcb514e6c387216fa89d7a1c61b4322c876599 |

发行资产由 wheel、sdist 和单独的 SHA256SUMS 组成；校验和在最后构建后生成，避免在归档内部嵌入自身哈希。未发布到 PyPI。GitHub Actions 的平台矩阵状态以实际远程记录为准，不将本机验收冒充远程 CI 或其它平台的真实图像验收。
