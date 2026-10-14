"""从单声道 16 kHz WAV 计算 Log-Mel Fbank，保存 NPY 与热力图。
用法: python fbank_assets/reproduce_fbank.py fbank_assets/audio/tone_sequence.wav
依赖: pip install numpy librosa matplotlib soundfile
"""
from pathlib import Path
import sys
import numpy as np
import librosa
import soundfile as sf
import matplotlib.pyplot as plt

source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fbank_assets/audio/tone_sequence.wav")
y, sr = sf.read(source)
if y.ndim != 1 or sr != 16000:
    raise ValueError("输入必须是 16 kHz 单声道 WAV")
frame_len, hop, n_fft, n_mels = 400, 160, 512, 80
frames = librosa.util.frame(y, frame_length=frame_len, hop_length=hop)
frames = frames * np.hanning(frame_len)[:, None]
power = np.abs(np.fft.rfft(frames, n=n_fft, axis=0)) ** 2
mel = librosa.filters.mel(sr=sr, n_fft=n_fft, n_mels=n_mels,
                          fmin=20, fmax=sr/2, htk=False, norm="slaney")
fbank = np.log(np.maximum(mel @ power, 1e-10)).T.astype(np.float32)
print("采样点:", len(y), "Fbank shape:", fbank.shape)
output = source.with_name(source.stem + "_fbank.npy")
np.save(output, fbank)
print("保存:", output)
fig, ax = plt.subplots(figsize=(10, 4))
im = ax.imshow(fbank.T, origin="lower", aspect="auto",
               extent=(0, (fbank.shape[0]-1)*hop/sr, 0, n_mels), cmap="magma")
ax.set(xlabel="时间 (s)", ylabel="Mel 频带序号", title="Log-Mel Fbank")
fig.colorbar(im, ax=ax, label="ln(power)")
fig.tight_layout()
fig.savefig(source.with_name(source.stem + "_fbank.png"), dpi=150)
print("绘图完成")
