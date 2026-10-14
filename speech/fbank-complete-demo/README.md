# Fbank 可复现实验
本文关联 [完整教程](../fbank-feature-extraction-complete.html)。

在仓库根目录运行：

```bash
python3 -m pip install numpy matplotlib
python3 speech/fbank-complete-demo/fbank_step_by_step.py
python3 speech/fbank-complete-demo/fbank_multiframe_demo.py
```

- 单帧脚本生成 400 点 PCM/WAV、257 点 FFT CSV、80×257 Mel 权重、80 维 Fbank CSV、数值 trace 以及各阶段示意图。
- 多帧脚本从 1 秒音频生成 98×257 功率谱、98×80 Log Fbank，并保存为 NPY。
- 仓库内预置了示例 CSV 和 SVG 图，二进制 WAV/NPY/PNG 可通过上面的脚本本地生成。
- 两个脚本使用教学配置：16 kHz、25 ms、10 ms 帧移、周期 Hann、512 FFT、HTK Mel、80 个频带、自然对数。
