#!/usr/bin/env python3
"""1 秒音频生成 98×80 Log Fbank；参数和 fbank_step_by_step.py 一致。"""
from pathlib import Path
import numpy as np
import wave
from fbank_step_by_step import FS, N_FFT, FRAME_SIZE, mel_filterbank, EPS

HERE = Path(__file__).resolve().parent
n = np.arange(FS)
# 3 段不同的声音，观察频率随时间变化
freq = np.where(n < FS//3, 300, np.where(n < 2*FS//3, 1000, 2000))
x = np.sin(2*np.pi*np.cumsum(freq)/FS) * 0.5
pcm = np.rint(32767*x).astype('<i2')
with wave.open(str(HERE/'tone_1second_three_phases.wav'), 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(FS)
    wav.writeframes(pcm.tobytes())
signal = pcm.astype(np.float64)/32768
hop = FS * 10 // 1000
hann = 0.5 - 0.5 * np.cos(2*np.pi*np.arange(FRAME_SIZE)/FRAME_SIZE)
freqs, hz_nodes, H = mel_filterbank()
power_rows, log_rows = [], []
for start in range(0, len(signal) - FRAME_SIZE + 1, hop):
    frame = signal[start:start+FRAME_SIZE] * hann
    power = np.abs(np.fft.rfft(frame, n=N_FFT))**2
    power_rows.append(power)
    log_rows.append(np.log(np.maximum(H@power, EPS)))
P, F = np.array(power_rows), np.array(log_rows)
assert P.shape == (98,257) and F.shape == (98,80)
np.save(HERE/'power_spectrum_98x257.npy',P)
np.save(HERE/'log_fbank_98x80.npy',F)
print("STFT power:", P.shape, "Log Fbank:", F.shape)
try:
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2,1,figsize=(12,7))
    axes[0].imshow(10*np.log10(np.maximum(P.T, 1e-10)),origin='lower',aspect='auto',extent=(0,.98,0,8000))
    axes[0].set(title='98 × 257 STFT Power',ylabel='Frequency (Hz)')
    axes[1].imshow(F.T,origin='lower',aspect='auto',extent=(0,.98,0,80))
    axes[1].set(title='98 × 80 Log Fbank',ylabel='Mel band',xlabel='Time (s)')
    fig.tight_layout()
    fig.savefig(HERE/'fbank_98x80.png',dpi=140)
    plt.close(fig)
except ImportError:
    print("matplotlib not installed, skip image")
