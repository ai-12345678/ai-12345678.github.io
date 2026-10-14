#!/usr/bin/env python3
"""从 25 ms 的真实 PCM s16le 样本逐步计算 80 维 Log-Mel Fbank。
依赖: numpy, matplotlib（只用于绘图，可选）。
用法: python3 fbank_step_by_step.py
"""
from __future__ import annotations

from pathlib import Path
import csv
import wave
import numpy as np

HERE = Path(__file__).resolve().parent
FS = 16000
DURATION_MS = 25
FRAME_SIZE = FS * DURATION_MS // 1000  # 400
N_FFT = 512
N_BINS = N_FFT // 2 + 1  # 257
N_MELS = 80
EPS = 1e-10


def hz_to_mel(f_hz: np.ndarray) -> np.ndarray:
    """HTK Mel 标度，f 单位 Hz。"""
    return 2595.0 * np.log10(1.0 + f_hz / 700.0)


def mel_to_hz(mel: np.ndarray) -> np.ndarray:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def make_pcm() -> np.ndarray:
    n = np.arange(FRAME_SIZE)
    x = (0.55 * np.sin(2 * np.pi * 1000 * n / FS)
         + 0.25 * np.sin(2 * np.pi * 2000 * n / FS + np.pi / 4))
    # 量化为 little-endian int16 PCM，模拟麦克风写入的 PCM
    return np.clip(np.rint(x * 32767), -32768, 32767).astype('<i2')


def save_audio(pcm: np.ndarray) -> None:
    (HERE / 'tone_25ms_s16le.pcm').write_bytes(pcm.tobytes())
    with wave.open(str(HERE / 'tone_25ms_16k_mono.wav'), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(FS)
        wav.writeframes(pcm.tobytes())


def mel_filterbank() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # 80 个三角滤波器需要 82 个边界/中心节点（两侧额外边界）
    mel_points = np.linspace(hz_to_mel(np.array(0.0)), hz_to_mel(np.array(FS/2)), N_MELS + 2)
    hz_points = mel_to_hz(mel_points)    # (82,)
    freq_bins = np.fft.rfftfreq(N_FFT, 1 / FS)  # (257,), [0,31.25,...,8000]
    H = np.zeros((N_MELS, N_BINS), dtype=np.float64)
    for m in range(N_MELS):
        left, center, right = hz_points[m:m+3]
        rise = (freq_bins - left) / (center - left)
        fall = (right - freq_bins) / (right - center)
        H[m, :] = np.maximum(0.0, np.minimum(rise, fall))
    return freq_bins, hz_points, H


def save_csv(name: str, header: list[str], rows) -> None:
    with (HERE / name).open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> None:
    pcm = make_pcm()
    save_audio(pcm)
    # 原始 PCM 整数转归一化 float；避免 -32768/32767 非对称性
    x = pcm.astype(np.float64) / 32768.0                    # (400,)
    n = np.arange(FRAME_SIZE)
    hann = 0.5 - 0.5 * np.cos(2 * np.pi * n / FRAME_SIZE)  # 周期 Hann
    x_windowed = x * hann                                 # (400,)
    x_zero_padded = np.pad(x_windowed, (0, N_FFT-FRAME_SIZE))

    # N_FFT=512；输入为实信号，rfft 返回 257 个非负频率点
    X = np.fft.rfft(x_windowed, n=N_FFT)  # (257,), 与先补零到512等价
    magnitude = np.abs(X)
    power = magnitude ** 2               # 本 demo 不除以 NFFT，也不做单边加倍

    freqs, mel_points_hz, H = mel_filterbank()  # H: (80,257)
    energies = H @ power                       # (80,)
    log_fbank = np.log(np.maximum(energies, EPS))  # 自然对数，不是 log10 / dB

    assert len(pcm) == 400 and len(X) == 257
    assert H.shape == (80, 257) and energies.shape == log_fbank.shape == (80,)
    assert np.all(energies >= 0)
    assert np.all(np.isfinite(log_fbank))
    assert np.allclose(np.fft.rfft(x_zero_padded), X)
    assert np.allclose(energies, np.array([np.sum(H[m]*power) for m in range(80)]))
    assert np.max(np.abs(np.fft.irfft(X, n=512)[:400] - x_windowed)) < 1e-12

    np.savez_compressed(HERE / 'fbank_intermediates.npz',
        pcm_s16=pcm, x=x, hann=hann, x_windowed=x_windowed,
        x_zero_padded=x_zero_padded, fft_complex=X, magnitude=magnitude,
        power=power, freq_hz=freqs, mel_nodes_hz=mel_points_hz,
        mel_weights=H, mel_energy=energies, log_fbank=log_fbank)

    save_csv('fft_257_bins.csv', ['k', 'Hz', 'FFT_real', 'FFT_imag', 'magnitude', 'power'],
        ((k, freqs[k], X[k].real, X[k].imag, magnitude[k], power[k]) for k in range(N_BINS)))
    save_csv('fbank_80_bins.csv', ['filter_index_1based','left_Hz','center_Hz','right_Hz','energy','ln_energy'],
        ((m+1, *mel_points_hz[m:m+3], energies[m], log_fbank[m]) for m in range(N_MELS)))
    save_csv('mel_weights_80x257.csv', ['mel_filter_1based'] + [f'k{k}_{freqs[k]:.2f}Hz' for k in range(N_BINS)],
        ((m+1, *H[m, :]) for m in range(N_MELS)))

    # 选择中心频率最靠近 1000 Hz 的滤波器，展开其每个非零权重点的乘法
    chosen = int(np.argmin(np.abs(mel_points_hz[1:-1] - 1000)))
    active = np.where(H[chosen] > 0)[0]
    save_csv('filter_near_1khz_detail.csv', ['k','freq_Hz','FFT_real','FFT_imag','power','filter_weight','weighted_power'],
        ((k, freqs[k], X[k].real, X[k].imag, power[k], H[chosen,k], power[k] * H[chosen,k]) for k in active))

    lines = []
    def report(line):
        lines.append(str(line))
        print(line)

    report('=== 25 ms PCM -> 80 维 Log Fbank，逐步数值输出 ===')
    report(f'采样率={FS} Hz; 时长={DURATION_MS} ms; 样本数={FRAME_SIZE}; FFT={N_FFT}; 频点={N_BINS}; mel={N_MELS}')
    report('输入信号：0.55*sin(2*pi*1000*t)+0.25*sin(2*pi*2000*t+pi/4)，然后量化为 int16。')
    report('\n步骤1：前 8 个原始 PCM（int16）与归一化 x[n]')
    for i in range(8):
        report(f'  n={i:2d}  pcm={int(pcm[i]):6d}  x={x[i]:+.9f}')
    report('\n步骤2：前 8 个 Hann 权重及加窗值 x[n]*w[n]')
    for i in range(8):
        report(f'  n={i:2d}  w={hann[i]:.9f}  xw={x_windowed[i]:+.9f}')
    report('\n步骤3：FFT 数值：k, Hz, 复数 X[k], 功率 |X[k]|^2')
    for k in [0, 1, 2, 31, 32, 33, 63, 64, 65, 256]:
        report(f'  k={k:3d}, f={freqs[k]:8.2f} Hz, X={X[k].real:+.7f}{X[k].imag:+.7f}j, P={power[k]:.7f}')
    report('\n步骤4：Mel 滤波器中心点（前 5 个）')
    for m in range(5):
        a,b,c = mel_points_hz[m:m+3]
        report(f'  filter {m+1:2d}: left={a:.5f} Hz, center={b:.5f} Hz, right={c:.5f} Hz, E={energies[m]:.9f}, logE={log_fbank[m]:.9f}')
    report(f'\n步骤5：展开第 {chosen+1} 个滤波器（最靠近 1 kHz，中心={mel_points_hz[chosen+1]:.5f} Hz）的逐频点计算')
    for k in active:
        report(f'  k={k:3d} ({freqs[k]:8.2f} Hz): P={power[k]:12.6f} × H={H[chosen,k]:.7f} = {power[k]*H[chosen,k]:12.6f}')
    report(f'  加权和 E[{chosen+1}] = {energies[chosen]:.9f}')
    report(f'  自然对数 ln(max(E,1e-10)) = {log_fbank[chosen]:.9f}')
    report('\n步骤6：80 维 Log Fbank（每行 10 维，索引从1开始）')
    for start in range(0, 80, 10):
        report(f'  {start+1:02d}~{start+10:02d}: ' + ' '.join(f'{v:+.5f}' for v in log_fbank[start:start+10]))
    report('\n验证: (400,) -> (512,) -> (257,) -> (257,) -> (80,) -> (80,)，IFFT 验证通过')
    (HERE / 'numeric_trace.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')

    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(5, 1, figsize=(10.8, 14), constrained_layout=True)
        ms = np.arange(FRAME_SIZE) / FS * 1000
        axes[0].plot(ms, x, label='Original PCM / 32768', linewidth=1)
        axes[0].plot(ms, x_windowed, label='After periodic Hann', linewidth=1, alpha=.8)
        axes[0].set(title='1. 25 ms PCM frame and windowing', xlabel='Time (ms)', ylabel='Amplitude')
        axes[0].legend(loc='upper right', fontsize=8)
        axes[1].plot(freqs, power)
        axes[1].set(title='2. Power spectrum: 257 positive-frequency bins', xlabel='Frequency (Hz)', ylabel='|FFT|^2', xlim=(0, 4000))
        for m in [0, 5, 15, 28, 45, 60, 79]:
            axes[2].plot(freqs, H[m], label=f'filter {m+1}')
        axes[2].set(title='3. Selected triangular Mel filters (7 of 80)', xlabel='Frequency (Hz)', ylabel='Weight', xlim=(0, 8000))
        axes[2].legend(ncol=4, fontsize=8)
        axes[3].plot(np.arange(1, 81), energies)
        axes[3].set(title='4. 80-dimensional linear Mel-band energies', xlabel='Mel filter index (1..80)', ylabel='Energy')
        axes[4].plot(np.arange(1, 81), log_fbank)
        axes[4].set(title='5. 80-dimensional Log Fbank (natural log)', xlabel='Mel filter index (1..80)', ylabel='ln(max(E,1e-10))')
        fig.savefig(HERE / 'fbank_stages.png', dpi=160)
        plt.close(fig)
    except ImportError:
        print('matplotlib 未安装，跳过绘图（其它结果全部正常生成）。')


if __name__ == '__main__':
    main()