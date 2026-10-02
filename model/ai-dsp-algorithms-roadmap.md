# 人工智能、DSP 与算法学习笔记

以语音与端侧 AI 为贯穿案例，按「基础概念 → 小实验 → 工程应用」逐个记录。DSP 在这里指数字信号处理；DSP 处理器是另一层硬件实现。

## 学习顺序与记录状态

| 顺序 | 主题 | 本次记录 |
| --- | --- | --- |
| 01 | 采样、量化、混叠与 PCM | [DSP 入门笔记](dsp-01-sampling.html) |
| 02 | 算法复杂度与滑动窗口 | [算法入门笔记](algorithms-01-complexity.html) |
| 03 | 人工智能、机器学习与模型评估 | [AI 入门笔记](ai-01-learning-basics.html) |
| 04 | 向量、矩阵、概率与梯度 | 待写 |
| 05 | 卷积、冲激响应与 FIR 滤波 | 待写 |
| 06 | DFT、FFT、频谱与窗函数 | 待写 |
| 07 | STFT、Mel 频谱与音频特征 | 待写 |
| 08 | 线性回归、损失函数与梯度下降 | 待写 |
| 09 | 神经网络、反向传播与优化 | 待写 |
| 10 | CNN、注意力与 Transformer | 待写 |
| 11 | VAD、关键词检测与语音识别 | 待写 |
| 12 | ONNX、量化与端侧部署 | 待写 |

前三篇是概念入口，后续从数学与信号处理基础展开。每次完成一篇后更新此表；「待写」表示尚未完成，没有预先创建空文章。

## 每篇笔记怎么写

1. 要解决的问题与先修知识。
2. 直观解释、符号含义和适用条件。
3. 一个可以运行的小实验。
4. 常见误区与工程取舍。
5. 自测题、参考资料和下一步。

运行示例得到的结果与预期结果分别记录；尚未实测的模型性能不写成结论。

## 已有资料如何衔接

- [Zipformer 唤醒词方案](zipformer-kws-guide.html)：完成音频特征与关键词检测基础后阅读。
- [I2S 时钟与数据原始笔记](https://github.com/ai-12345678/ai-12345678.github.io/blob/main/Embodied-AI/i2s_clock_data_summary.md)：用于理解采样后的 PCM 如何通过硬件接口传输。

## 参考资料

- [MIT 6.003 Signals and Systems](https://ocw.mit.edu/courses/6-003-signals-and-systems-fall-2011/)
- [MIT 6.006 Introduction to Algorithms](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-fall-2011/)
- [动手学深度学习](https://zh.d2l.ai/)

下一篇计划：向量、矩阵、概率与梯度。后续笔记需要在继续学习时逐篇补充。
