# 构建、安装与验证

Python 3.11+。本地真实样本与性能验收使用 Windows x64 / CPython 3.14.0。仓库可独立构建、安装和运行公开合成测试，无需研究交接目录。以下命令在仓库根执行，照片、profile 和可选研究资料均由使用者自行提供。

## 开发环境

`.[dev]` 解析适合平台的依赖。`requirements-m0.txt` 固定历史 Windows/Python 3.14 验收环境，不作为 Python 3.11 的通用锁文件。

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q --ignore=tests/integration
```

Windows PowerShell 可直接调用环境入口：

```powershell
New-Item -ItemType Directory -Force .cache/tmp, .cache/pip | Out-Null
$env:TEMP = (Resolve-Path .cache/tmp).Path
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = (Resolve-Path .cache/pip).Path
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OPENBLAS_NUM_THREADS = '1'
py -3 -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -e '.[dev]'
& ./.venv/Scripts/python.exe -m pytest -q --ignore=tests/integration --basetemp=.cache/pytest
```

公开合成测试 185 项。普通 pytest 还会发现 12 项真实集成用例，缺少外部输入时跳过。生产仅需 NumPy/rawpy；度量及预览工具需要 dev 依赖。

## 构建发行物

使用独立构建环境：

```sh
python -m venv .cache/build-venv
.cache/build-venv/bin/python -m pip install -r requirements-build.txt
.cache/build-venv/bin/python -m build --no-isolation --outdir dist
.cache/build-venv/bin/python -m twine check --strict dist/colorpipe-0.1.0.tar.gz dist/colorpipe-0.1.0-py3-none-any.whl
.cache/build-venv/bin/python tools/validate_distribution.py dist/colorpipe-0.1.0.tar.gz dist/colorpipe-0.1.0-py3-none-any.whl --report out/distribution-validation.json
```

Windows 解释器路径改为 `.cache/build-venv/Scripts/python.exe`。默认 build 先生成 sdist，再从 sdist 构建 wheel，检查源码包缺文件。固定构建工具不保证归档时间戳或整包 bit-for-bit 可复现。

wheel 仅含生产模块、元数据、MIT 和第三方通知。sdist 另含文档、测试/辅助文件、验证工具、fixture 模板及 CI。`MANIFEST.in` 和归档检查排除 RAW/ORI/DNG/DCP、捕获、缓存、二进制和交接材料。归档工具检查 SPDX/长说明、依赖、入口、版本和成员路径。

## 安装并测试 wheel

先审查归档，再解压到新的专用目录。Linux 示例：

```sh
python -m venv .cache/install-venv
INSTALL_PYTHON="$(pwd)/.cache/install-venv/bin/python"
"$INSTALL_PYTHON" -m pip install './dist/colorpipe-0.1.0-py3-none-any.whl[dev]'
"$INSTALL_PYTHON" -m pip check
"$INSTALL_PYTHON" -I -c "import colorpipe; assert 'site-packages' in colorpipe.__file__; print(colorpipe.__file__)"
"$INSTALL_PYTHON" -I -m colorpipe --version
mkdir -p .cache/sdist
tar -xf dist/colorpipe-0.1.0.tar.gz -C .cache/sdist
cd .cache/sdist/colorpipe-0.1.0
mkdir -p .cache
COLORPIPE_TEST_INSTALLED=1 "$INSTALL_PYTHON" -I -m pytest -q --ignore=tests/integration --basetemp=.cache/installed-pytest
```

Windows 将 `$installPython` 设为安装环境的绝对解释器路径，并设置 `$env:COLORPIPE_TEST_INSTALLED='1'`。进入解压目录后先执行 `New-Item -ItemType Directory -Force .cache | Out-Null`，因为 pytest 的 basetemp 不会自动创建缺失的父目录。该环境变量关闭 conftest 的 src 注入，确保测试已安装的 wheel；测试辅助文件仍来自 sdist。不要使用 editable 安装或 PYTHONPATH 替代这一步。

## 可选真实图像回归

复制 `tests/fixtures.example.json` 到被忽略的 `fixtures.json`，填写本地 RAW 路径。模板保留三张历史验证图的 SHA/预期元数据；使用其它图时须更新这些预期，不能将历史断言直接套用到新图。

12 项历史集成用例需要原研究清单与对应私有参考文件，公开仓库不分发这些文件。只有 RAW/DCP 时仍可独立转换、检查元数据和运行基准，但不能复现历史 oracle 对照。具备只读参考资料时：

```sh
python -m pytest -c pyproject.toml --confcutdir=. tests -q --fixture-config fixtures.json \
  --reference-root /path/to/references/decoder_writer \
  --m1-stage-index /path/to/references/three_raw_stages.json \
  --m2-acceptance /path/to/references/parent_acceptance.json \
  --m2-oracles /path/to/references/portable-oracles \
  --m2-native-stages /path/to/references/native-stages.json \
  --m3-profile /path/to/user-supplied.dcp \
  --basetemp=.cache/real-pytest --junitxml=out/real-pytest.xml
```

显式指定本项目的配置、测试目录和 conftest 边界，避免外部参考路径影响 pytest 根目录发现。工具均有 `--help`。`validate_m0/1/2/3.py` 独立预测后再读取参考。`build_m2_test_oracles.py` 依赖用户提供的外部研究源，仅用于测试，不是构建或运行依赖。`render_m3.py` 需要自行提供的 RawTherapee/darktable CLI。参考只读，输出写入明确指定的新目录。

## CI 与发行身份

CI 配置 Windows/Linux × Python 3.11/3.14，构建并检查归档、测试安装后的 wheel。CI 不包含私有照片、DCP、oracle 或外部渲染器。实际远程状态以 GitHub Actions 为准；公开合成测试通过不等于跨平台真实图像验收。

首个公开版本 0.1.0 导出自优化里程碑 `perf-hifi`。较早未优化的同版本本地包不是此发行物；请使用新 venv 或 --force-reinstall，并以发行资产 SHA256 确认身份。性能与来源见 [PERFORMANCE](PERFORMANCE.md)、[LEGAL](LEGAL.md)。
