# Zipformer 唤醒词方案使用手册

本文基于 `sherpa-onnx` 官方 Zipformer KWS（Keyword Spotting）方案，整理模型选择、环境安装、模型下载、唤醒词测试、自定义中文唤醒词、参数调优、INT8 推理、设备部署与排障步骤。

本文沿用已有项目目录与脚本：

```bash
cd /tmp/wakenet
```

命令中的 `kws_demo.py`、`download_zipformer_kws.sh`、`requirements-kws.txt`、`requirements-kws-quantization.txt` 和 `python313/` 是原项目已有文件或环境，并非本篇文档附带的脚本。迁移到其他机器时，需要先准备对应文件，并按实际路径修改命令。

## 1. 整体方案

实时音频经过声学特征提取、Zipformer Encoder、Decoder / Joiner 和关键词搜索，输出唤醒事件。Encoder 编码音频特征；Decoder 使用历史 token；Joiner 结合两者产生 token 分数；关键词搜索根据指定 token 序列判断是否命中。

添加新的唤醒词通常不需要重新训练模型，而是先通过 `text2token` 将文字转换为模型支持的 token 序列，再交给 `KeywordSpotter`：

1. 将唤醒词写入 `keywords_raw.custom.txt`。
2. 使用模型对应的 `tokens.txt` 和 token 类型进行转换。
3. 得到 `keywords.custom.txt`。
4. 推理时显式传入 `--keywords-file`。

这适合作为设备侧可配置唤醒词的基础方案；实际唤醒效果仍需要在目标设备上评估。

## 2. 模型选择

本手册使用以下两个模型包作为示例：

| 模型 | 语言 | Chunk | 使用建议 |
| --- | --- | --- | --- |
| `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20` | 中文 + 英文 | 8 / 16 | 本项目默认模型，优先测试 chunk-8 |
| `sherpa-onnx-kws-zipformer-wenetspeech-3.3M-2024-01-01` | 中文 | 16 | 中文单语备选，需评估延迟与准确率 |

默认组合：

```text
zh-en 模型 + chunk-8
INT8 encoder + FP32 decoder + INT8 joiner
CPU provider
```

官方资料：

- [预训练 KWS 模型列表](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html)
- [KWS 模型下载](https://github.com/k2-fsa/sherpa-onnx/releases/tag/kws-models)
- [sherpa-onnx 源码](https://github.com/k2-fsa/sherpa-onnx)

模型是否适合实际设备，最终由实时率、CPU、内存、误唤醒和漏唤醒测试决定。

## 3. 音频要求

采集与文件测试建议统一为：

| 参数 | 建议值 |
| --- | --- |
| 采样率 | 16000 Hz |
| 声道 | 单声道 Mono |
| 采集 / 文件 PCM 格式 | signed 16-bit little-endian，`s16le` |
| 文件容器 | WAV；裸 PCM 需额外知道采样率、声道和格式 |

转码示例：

```bash
ffmpeg -i input.mp3 \
  -ar 16000 \
  -ac 1 \
  -c:a pcm_s16le \
  -y output.wav
```

检查音频：

```bash
ffprobe -v error \
  -select_streams a:0 \
  -show_entries stream=sample_rate,channels,codec_name,sample_fmt \
  -of default=noprint_wrappers=1 \
  output.wav
```

期望输出：

```text
codec_name=pcm_s16le
sample_fmt=s16
sample_rate=16000
channels=1
```

`PCM s16le` 是采集或文件格式。调用 Python `accept_waveform()` 时，应将 int16 样本转换为归一化浮点样本，例如 `samples.astype(numpy.float32) / 32768.0`，不要把未经转换的 PCM 字节直接当作浮点波形传入。

## 4. Python 环境

### 4.1 安装推理依赖

检查项目解释器：

```bash
./python313/bin/python3 --version
```

建议显式指定镜像，并用 `--isolated` 忽略本机 pip 配置和 `PIP_EXTRA_INDEX_URL`：

```bash
./python313/bin/python3 -m pip install \
  --isolated \
  --index-url https://mirrors.bfsu.edu.cn/pypi/web/simple \
  -r ./requirements-kws.txt
```

北外镜像没有对应包时，切换清华镜像：

```bash
./python313/bin/python3 -m pip install \
  --isolated \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  -r ./requirements-kws.txt
```

也可以使用官方 PyPI：

```bash
./python313/bin/python3 -m pip install \
  --isolated \
  --index-url https://pypi.org/simple \
  -r ./requirements-kws.txt
```

项目依赖应包含 `sherpa-onnx`、`numpy`、`soundfile`，以及 `text2token` CLI 使用的 `click`。`--isolated` 可以避免失效的 NVIDIA 额外源导致 `pypi.ngc.nvidia.com: NameResolutionError`。

### 4.2 离线安装

在与目标机器 Python 版本、操作系统和架构相匹配的联网环境下载 wheel：

```bash
./python313/bin/python3 -m pip download \
  --isolated \
  --index-url https://pypi.org/simple \
  --dest wheels \
  -r requirements-kws.txt
```

将 `wheels/` 复制到目标机器后安装：

```bash
./python313/bin/python3 -m pip install \
  --no-index \
  --find-links ./wheels \
  -r requirements-kws.txt
```

### 4.3 验证安装

```bash
./python313/bin/python3 - <<'PY'
import sys
import sherpa_onnx
import numpy
import soundfile

print("python:", sys.executable)
print("sherpa_onnx:", sherpa_onnx.__version__)
print("numpy:", numpy.__version__)
print("soundfile:", soundfile.__version__)
print("KeywordSpotter:", sherpa_onnx.KeywordSpotter)
PY
```

本项目针对 `sherpa-onnx 1.13.x` 使用公开的 `sherpa_onnx.KeywordSpotter(...)` 构造方式。不要将顶层模块必须存在 `sherpa_onnx.KeywordSpotterConfig` 作为安装成功条件；遇到该属性不存在时，使用项目中兼容的 `kws_demo.py`。

### 4.4 量化依赖

使用官方 INT8 权重无需自行量化。只有需要实验性地量化 ONNX 时，才安装额外依赖：

```bash
./python313/bin/python3 -m pip install \
  --isolated \
  --index-url https://mirrors.bfsu.edu.cn/pypi/web/simple \
  -r ./requirements-kws-quantization.txt
```

该文件会递归安装 `requirements-kws.txt`，仍然需要能够获取 `sherpa-onnx`。

## 5. 下载模型

中英模型：

```bash
chmod +x download_zipformer_kws.sh
./download_zipformer_kws.sh zh-en models/zipformer-kws
```

中文单语模型：

```bash
./download_zipformer_kws.sh wenetspeech models/zipformer-kws-zh
```

官方下载目录：

```text
https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/
```

检查文件：

```bash
find models/zipformer-kws -maxdepth 2 -type f -print | sort
```

中英模型通常包含：

```text
encoder-*-chunk-8*.onnx
encoder-*-chunk-16*.onnx
decoder-*-chunk-8*.onnx
decoder-*-chunk-16*.onnx
joiner-*-chunk-8*.onnx
joiner-*-chunk-16*.onnx
tokens.txt
en.phone
test_wavs/keywords.txt
test_wavs/*.wav
```

中文单语模型通常包含 chunk-16 的 encoder、decoder、joiner，以及 `tokens.txt` 和 `keywords.txt`。

**encoder、decoder、joiner 和 tokens.txt 必须来自同一个模型包，并选择匹配的模型配置。** 不要跨模型混用词表，也不要将为另一种 token 类型生成的关键词文件直接拿来使用。

## 6. 跑通官方 Demo

先使用官方测试音频验证模型和环境：

```bash
./python313/bin/python3 kws_demo.py \
  --model-dir models/zipformer-kws \
  --audio models/zipformer-kws/test_wavs/zh_3.wav
```

显式指定官方关键词文件：

```bash
./python313/bin/python3 kws_demo.py \
  --model-dir models/zipformer-kws \
  --keywords-file models/zipformer-kws/test_wavs/keywords.txt \
  --audio models/zipformer-kws/test_wavs/zh_3.wav
```

项目脚本自动发现模型文件，优先选择 chunk-8 INT8 encoder / joiner。以下输出格式属于项目 Demo：

命中：

```json
{"keyword": "文森特卡索", "event": 1}
```

未命中：

```json
{"keyword": null, "event": 0}
```

先确认官方测试音频能命中对应关键词，再测试自己的录音。

## 7. 添加自定义中文唤醒词

### 7.1 中英模型：phone+ppinyin

创建原始关键词文件：

```bash
MODEL=models/zipformer-kws

cat > "$MODEL/keywords_raw.custom.txt" <<'KWEOF'
你好小度 @你好小度
打开空调 @打开空调
小度小度 @小度小度
KWEOF
```

每行一个关键词，`@` 后保留输出名称。本项目使用 `phone+ppinyin` 时，`@` 后的名称不要包含空格，英文名称中的空格可替换为下划线。

转换为 token 序列：

```bash
./python313/bin/sherpa-onnx-cli text2token \
  --tokens "$MODEL/tokens.txt" \
  --tokens-type phone+ppinyin \
  --lexicon "$MODEL/en.phone" \
  "$MODEL/keywords_raw.custom.txt" \
  "$MODEL/keywords.custom.txt"
```

检查生成文件：

```bash
cat "$MODEL/keywords.custom.txt"
```

文件应包含模型支持的拼音 / 音素 token 和 `@你好小度` 等输出名称。实际 token 以转换工具生成的结果为准，不要照着示意拼音手写。

使用包含自定义唤醒词的录音测试：

```bash
./python313/bin/python3 kws_demo.py \
  --model-dir "$MODEL" \
  --keywords-file "$MODEL/keywords.custom.txt" \
  --audio test.wav
```

官方 `zh_3.wav` 不一定包含你新增的唤醒词；验证自定义词应使用相应的真实录音。

### 7.2 中文单语模型：ppinyin

WenetSpeech 中文单语模型使用 `ppinyin`，无需 `en.phone`：

```bash
MODEL=models/zipformer-kws-zh

cat > "$MODEL/keywords_raw.custom.txt" <<'KWEOF'
你好军哥 @你好军哥
你好问问 @你好问问
小爱同学 @小爱同学
KWEOF

./python313/bin/sherpa-onnx-cli text2token \
  --tokens "$MODEL/tokens.txt" \
  --tokens-type ppinyin \
  "$MODEL/keywords_raw.custom.txt" \
  "$MODEL/keywords.custom.txt"

./python313/bin/python3 kws_demo.py \
  --model-dir "$MODEL" \
  --keywords-file "$MODEL/keywords.custom.txt" \
  --audio test.wav
```

### 7.3 常见加词错误

| 错误 | 正确处理 |
| --- | --- |
| 直接将汉字写入最终 `keywords.txt` | 先通过 `text2token` 转换 |
| 混用不同模型的 `tokens.txt` | 使用当前模型包的词表 |
| 中英模型使用中文单语模型生成的关键词 | 按当前模型的 token 类型重新转换 |
| 生成文件后未传入 `--keywords-file` | 显式指定自定义关键词文件 |
| `sherpa-onnx-cli` 找不到 | 检查是否使用同一个虚拟环境 |

检查 CLI：

```bash
./python313/bin/python3 -m pip show sherpa-onnx
./python313/bin/sherpa-onnx-cli --help
```

安装包没有 CLI 时，可在对应 sherpa-onnx 源码目录检查转换脚本：

```bash
python3 scripts/text2token.py --help
```

## 8. 调整误唤醒和漏唤醒

### 8.1 全局触发阈值

本项目可先从 `0.25` 开始，再使用真实录音调整：

```bash
./python313/bin/python3 kws_demo.py \
  --model-dir "$MODEL" \
  --keywords-file "$MODEL/keywords.custom.txt" \
  --audio test.wav \
  --keywords-threshold 0.35
```

| 调整 | 通常的影响 |
| --- | --- |
| 提高 threshold | 更难触发，误唤醒可能下降，漏唤醒可能上升 |
| 降低 threshold | 更容易触发，漏唤醒可能下降，误唤醒可能上升 |

阈值是搜索 / 触发参数，不应直接解读为经过校准的正确概率。

### 8.2 为每个关键词单独设置参数

可在原始关键词文件中附加 boosting score 和 trigger threshold：

```text
你好小度 :1.5 #0.35 @你好小度
打开空调 :1.0 #0.25 @打开空调
```

| 写法 | 含义 |
| --- | --- |
| `:1.5` | boosting score，提高该词在搜索中保留的倾向 |
| `#0.35` | 该词自己的触发阈值，越高通常越难触发 |
| `@你好小度` | 命中时返回的名称 |

编辑后再次运行 `text2token`，生成新的 `keywords.custom.txt`。词级参数覆盖对应的全局默认值；没有设置的项目继续使用全局值。

容易误触的词可提高 threshold；难唤醒的词可实验性地提高 boosting score 或降低 threshold，每次调整后都应重新测试正负样本。

## 9. 测试集与调参方法

不要只用一条录音判断效果。建议同时准备：

| 数据 | 覆盖范围 |
| --- | --- |
| 正样本 | 男声、女声、不同说话人、近场、远场、不同音量、噪声和语速 |
| 负样本 | 普通聊天、相似发音、电视 / 视频声音、环境噪声、长时间背景音 |
| 真机专项 | TTS 播放、音乐播放、双讲、麦克风方向和不同距离 |

记录以下指标：

- **FRR（漏唤醒率）**：未检测到的有效唤醒次数 / 有效唤醒总次数。
- **误唤醒次数 / 小时**：负样本误触次数 / 负样本时长；连续监听设备更适合用这个口径。
- 若采用 **FAR（误接受率）**，需明确其分母，例如负样本片段总数，避免与“次数 / 小时”混用。
- **触发延迟**：明确起点，例如唤醒词说完到事件输出的时间。
- **性能**：CPU、RSS、峰值内存、实时率和持续运行稳定性。

目标是在可接受的漏唤醒率下，尽量降低误唤醒。优先检查音频、token、threshold、boosting score 和真实负样本，再判断是否需要换模型或微调。

## 10. INT8 推理与官方 CLI

设备侧优先测试官方量化组合：

```text
encoder.int8.onnx
decoder.onnx
joiner.int8.onnx
```

不要默认自行量化 decoder。使用官方 INT8 权重不需要安装量化工具。

先检查当前安装版本是否提供 CLI：

```bash
./python313/bin/sherpa-onnx-keyword-spotter --help
```

中英模型 chunk-8 INT8 推理示例：

```bash
MODEL=models/zipformer-kws

./python313/bin/sherpa-onnx-keyword-spotter \
  --encoder "$MODEL/encoder-epoch-13-avg-2-chunk-8-left-64.int8.onnx" \
  --decoder "$MODEL/decoder-epoch-13-avg-2-chunk-8-left-64.onnx" \
  --joiner "$MODEL/joiner-epoch-13-avg-2-chunk-8-left-64.int8.onnx" \
  --tokens "$MODEL/tokens.txt" \
  --keywords-file "$MODEL/keywords.custom.txt" \
  --provider cpu \
  --num-threads 2 \
  test.wav
```

文件名以实际模型包为准。如果当前 CLI 要求 `--wav`，按 `--help` 将最后一行改为 `--wav test.wav`。不同版本或安装方式的 CLI 可用性与参数可能不同。

## 11. Chunk-8 与 Chunk-16

Chunk 表示流式模型每次处理的一组特征帧，其具体时间跨度与特征帧移、下采样和模型配置有关。

较小 chunk 通常减少等待一批音频的时间，但实际触发延迟还包括音频缓冲、计算时间、搜索和尾部判定，不能只凭 chunk 数值推算最终延迟。也不能仅根据 chunk-16 就认定模型有更多左侧上下文，左侧上下文需查看 `left-*` 等模型配置。

本项目优先比较中英模型 chunk-8 和 chunk-16 的真机结果。中文单语模型作为另一组选项独立评估。

## 12. 设备侧运行方式

`KeywordSpotter` 应作为长生命周期对象，启动时加载一次模型并创建 stream，然后持续送入音频。

运行步骤：

1. 创建 `KeywordSpotter`。
2. 创建 stream。
3. 将 PCM 转换为 API 需要的浮点波形后调用 `accept_waveform()`。
4. 只要 stream 可解码，就持续调用 `decode_stream()`。
5. 调用 `get_result()` 检查关键词。
6. 命中后按应用状态处理唤醒事件，并调用 `reset_stream()`。
7. 继续监听后续音频。

不要每收到一个 PCM block 就重新创建 `KeywordSpotter`，也不要每块都重置 stream；这样会丢失流式上下文并增加模型加载开销。

音频采集应连续、采样率正确；线程阻塞或丢块也会影响唤醒效果。音频文件结束时，应按对应版本示例完成尾部处理，避免遗漏末尾关键词。

## 13. 推荐设备配置

| 平台 | 第一版配置 | 后续评估 |
| --- | --- | --- |
| Linux / ARM 开发板 | CPU + 官方 INT8 encoder / joiner，先测试 2 个线程 | 对比 1 / 2 / 4 线程的实时率与 CPU |
| Android | CPU + INT8 | 当前构建与设备支持时，再评估 NNAPI 等加速方式 |
| macOS / iOS | 先使用 CPU 跑通模型和关键词 | 当前构建支持时，再评估 CoreML provider |

是否能启用某个 provider，取决于 sherpa-onnx / ONNX Runtime 构建、模型算子与设备支持。先验证 CPU 基线，再测加速路径。

ARM/Linux 开发板可从以下配置开始：

| 项目 | 初始配置 |
| --- | --- |
| 模型 | `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20` |
| Chunk | 8 |
| 权重 | INT8 encoder + FP32 decoder + INT8 joiner |
| Provider | CPU |
| 输入采集 | 16 kHz / Mono / PCM s16le |
| 线程 | 先 2，再对比 1 / 4 |
| 关键词 | `text2token` 生成 |
| Threshold | 从项目默认值 0.25 开始 |
| 调优依据 | 真机 FRR、误唤醒次数 / 小时、延迟与性能 |

## 14. 与 AEC、降噪、VAD、ASR 的组合

设备可采用：

1. 麦克风采集音频。
2. 按实际环境进行 AEC / 降噪等前端处理。
3. KWS 持续监听。
4. 唤醒成功后进入交互状态。
5. VAD 为 ASR 切句。
6. ASR → LLM → TTS。
7. 交互结束后回到监听状态。

KWS 不必依赖前置 VAD。硬性用 VAD 截断 KWS 输入，可能丢失轻声、词首或词尾；如为省电增加门控，应保留前后缓冲并验证漏唤醒影响。VAD 更常用于唤醒后的语音切句。

在远场、播放音乐、TTS 播放和噪声环境中，AEC / 降噪可能影响唤醒效果。AEC 需要合适的播放参考信号与时序对齐；过强降噪可能削弱语音。应比较处理前后的真实正负样本结果，再决定是否启用与如何配置。

`reset_stream()` 重置 KWS 搜索状态，不等于整个应用切换到 ASR。是否继续检测唤醒、是否允许打断 TTS、何时恢复监听，应由应用状态机控制。

## 15. 快速排障

检查解释器、包来源和版本：

```bash
./python313/bin/python3 -V

./python313/bin/python3 - <<'PY'
import sherpa_onnx
print(sherpa_onnx.__file__)
print(sherpa_onnx.__version__)
print(sherpa_onnx.KeywordSpotter)
PY
```

检查模型和 CLI：

```bash
find models/zipformer-kws -maxdepth 2 -type f -print | sort
./python313/bin/sherpa-onnx-cli --help
./python313/bin/sherpa-onnx-keyword-spotter --help
```

| 现象 | 排查方向 |
| --- | --- |
| NVIDIA pip 源解析失败 | 使用 `--isolated --index-url` |
| 顶层 `KeywordSpotterConfig` 不存在 | 使用公开 `KeywordSpotter(...)` 与项目兼容 Demo |
| 官方测试音频不能命中 | 检查文件完整性、模型配置、tokens 和官方关键词文件 |
| 自定义词不能命中 | 检查 token 类型、转换结果、`--keywords-file` 与测试录音 |
| 误唤醒较多 | 用真实负样本测试，调整词级 threshold / boosting score |
| 轻声、远场漏唤醒 | 检查音频幅度、前置 VAD、前端处理与采集丢块 |
| 每块音频都无法形成稳定检测 | 检查是否重复创建或重置 spotter / stream |
| CPU 或延迟过高 | 对比 chunk、INT8、线程数和音频缓冲 |

## 16. 落地与验收顺序

1. 跑通官方模型与官方测试音频。
2. 生成并验证自定义中文唤醒词 token。
3. 在目标设备接入连续音频流。
4. 评估 chunk-8 INT8 的实时率、CPU 和内存。
5. 建立真实正负样本集，记录 FRR 和误唤醒次数 / 小时。
6. 比较 AEC / 降噪前后的唤醒表现。
7. 调整阈值、boosting score 和应用状态机。
8. 现有方案仍无法满足验收要求时，再进入数据采集、模型微调与自定义模型阶段。
