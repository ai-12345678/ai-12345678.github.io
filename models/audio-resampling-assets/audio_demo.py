#!/usr/bin/env python3
"""重采样、滤波、混音教学实验。安装 numpy scipy matplotlib 后运行。
用法：python3 audio_demo.py --out demo_output [--font 中文字体路径]
生成8张图及计算结果JSON；所有图均来自实际数组计算。
"""
from pathlib import Path
import argparse
import json
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from scipy.signal import resample_poly, freqz

BLUE, ORANGE, GREEN, GRAY = '#2266b5', '#d95e24', '#178068', '#778595'

def setup(font):
    if font:
        font_manager.fontManager.addfont(font)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=font).get_name()
    plt.rcParams.update({'font.size': 12, 'axes.titlesize': 14, 'axes.labelsize': 12,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.unicode_minus': False, 'figure.facecolor': 'white'})

def save(fig, path):
    fig.savefig(path, dpi=170, bbox_inches='tight', facecolor='white')
    plt.close(fig)

def tidy(ax, xlabel, ylabel='振幅'):
    ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
    ax.grid(alpha=.18)

def amplitude_at(x, fs, f):
    # 本实验窗口包含整数个周期；投影给出正弦分量的峰值振幅。
    n = np.arange(len(x))
    return float(2 * abs(np.dot(x, np.exp(-2j*np.pi*f*n/fs))) / len(x))

def spectrum(x, fs):
    n = len(x)
    a = np.abs(np.fft.rfft(x)) / n
    if n % 2 == 0:
        a[1:-1] *= 2
    else:
        a[1:] *= 2
    return np.fft.rfftfreq(n, 1/fs), a

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', default='demo_output')
    p.add_argument('--font', default=None)
    args = p.parse_args()
    root = Path(args.out); root.mkdir(parents=True, exist_ok=True)
    setup(args.font)
    stats = {}

    # 01 同一个连续函数，用两种采样时间网格观察。
    fig, axs = plt.subplots(2, 1, figsize=(9, 6.5), layout='constrained')
    dense = np.linspace(0, .001, 1500)
    for ax, fs, c in zip(axs, [16000, 48000], [BLUE, ORANGE]):
        t = np.arange(fs//1000)/fs
        ax.plot(dense*1000, .8*np.cos(2*np.pi*1000*dense), color=GRAY, alpha=.6, label='同一个1 kHz余弦函数')
        ax.scatter(t*1000, .8*np.cos(2*np.pi*1000*t), color=c, s=38, zorder=3, label=f'{fs//1000} kHz采样点')
        ax.set_title(f'相同的1 ms区间：[0, 1 ms)，{len(t)}个采样点')
        ax.set_xlim(-.01, 1); ax.set_ylim(-1, 1); ax.legend(fontsize=10, loc='upper right')
        tidy(ax, '时间（ms）')
    fig.suptitle('重采样：改变点的密度，保持相同时间区间', fontsize=17)
    save(fig, root/'01_resampling_grid.png')
    stats['sample_counts_1s'] = {'16000_to_48000': [16000, 48000], '48000_to_16000': [48000, 16000]}

    # 02 线性插值局部手算；不是完整音频转换器。
    t = np.array([0., 62.5]); x = np.array([0., .9])
    newt = np.array([0, 62.5/3, 2*62.5/3, 62.5])
    y = np.interp(newt, t, x)
    assert np.allclose(y, [0, .3, .6, .9])
    fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
    ax.plot(newt, y, color=GRAY, linewidth=2)
    ax.scatter(t, x, s=120, color=BLUE, label='原采样点', zorder=4)
    ax.scatter(newt[1:3], y[1:3], s=100, color=ORANGE, marker='D', label='插值计算的新点', zorder=4)
    for a,b in zip(newt,y):
        ax.annotate(f'{a:.2f} μs\n值={b:.1f}', (a,b), xytext=(0,17), textcoords='offset points', ha='center', fontsize=12)
    ax.set_xlim(-7, 70); ax.set_ylim(-.12, 1.18); ax.legend(loc='lower right')
    tidy(ax, '时间（μs）'); ax.set_title('升采样局部演示：16 kHz → 48 kHz，插入0.3和0.6')
    save(fig, root/'02_upsampling_interpolation.png')
    stats['linear_interpolation'] = y.tolist()

    # 03 中心对齐3点低通，再按3倍抽取。边界按0补齐。
    x = np.array([0,.4,.8,.4,0,-.4,-.8,-.4,0.])
    h = np.array([.25,.5,.25])
    lp = np.convolve(x,h,mode='same')
    down = lp[::3]
    assert np.allclose(down, [.1,.4,-.6])
    fig, axs = plt.subplots(3,1,figsize=(9,8),layout='constrained')
    for ax,v,c,title in zip(axs,[x,lp,down],[GRAY,BLUE,GREEN],
             ['原数组：9个点','3点低通：每个点重新加权计算','抽取n=0、3、6：只留下3个点']):
        n = np.arange(len(v)) if len(v)==9 else np.array([0,3,6])
        ax.plot(n,v,'o-',color=c)
        for a,b in zip(n,v): ax.annotate(f'{b:.1f}',(a,b),xytext=(0,10),textcoords='offset points',ha='center',fontsize=11)
        ax.set_ylim(-1,1.05); ax.set_xlim(-.4,8.4); ax.set_xticks(np.arange(9)); ax.set_title(title)
        tidy(ax,'原采样点编号n')
    fig.suptitle('降采样手算：低通计算后再抽取（教学滤波器）',fontsize=17)
    save(fig,root/'03_downsampling_calculation.png')
    stats['toy_downsample'] = {'original':x.tolist(),'filtered':lp.tolist(),'output':down.tolist()}

    # 04 实际48k→16k防混叠。用余弦避免负频折返的相位说明。
    fs=48000; t=np.arange(fs*2)/fs
    x=.6*np.cos(2*np.pi*1000*t)+.3*np.cos(2*np.pi*10000*t)
    raw=x[::3]
    safe=resample_poly(x,1,3,window=('kaiser',8.6))
    # 取中间1秒，排除有限长度滤波的起止边界瞬态。
    chunks=[x[fs//2:fs*3//2],raw[8000:24000],safe[8000:24000]]
    fig,axs=plt.subplots(3,1,figsize=(9,8),layout='constrained')
    for ax,v,rate,c,title in zip(axs,chunks,[48000,16000,16000],[BLUE,ORANGE,GREEN],
           ['原始48 kHz：1 kHz + 10 kHz','直接每3点取1点：10 kHz折返成6 kHz','经过防混叠重采样：保留1 kHz，削弱10 kHz']):
        f,a=spectrum(v,rate)
        ax.plot(f/1000,a,color=c,lw=1.8)
        ax.set_xlim(0,12); ax.set_ylim(-.015,.68); ax.set_xticks(np.arange(0,13,2)); ax.set_title(title)
        if rate==16000:
            ax.axvspan(8,12,color=GRAY,alpha=.12); ax.axvline(8,color=GRAY,ls='--')
            ax.text(10,.48,'输出无法表示\n8 kHz以上',ha='center',color=GRAY,fontsize=11)
        for freq in [1,6,10]:
            if freq*1000<rate/2 and amplitude_at(v,rate,freq*1000)>.02:
                amp=amplitude_at(v,rate,freq*1000)
                ax.annotate(f'{freq} kHz\n振幅≈{amp:.2f}',(freq,amp),xytext=(16,-12),textcoords='offset points',fontsize=11)
        tidy(ax,'频率（kHz）','单边峰值振幅')
    fig.suptitle('为什么降采样前要低通：避免凭空出现6 kHz',fontsize=17)
    save(fig,root/'04_aliasing_comparison.png')
    stats['anti_alias']={'raw_1khz':amplitude_at(chunks[1],16000,1000),
                         'raw_6khz':amplitude_at(chunks[1],16000,6000),
                         'safe_1khz':amplitude_at(chunks[2],16000,1000),
                         'safe_6khz':amplitude_at(chunks[2],16000,6000)}
    assert abs(stats['anti_alias']['raw_6khz']-.3)<1e-8
    assert abs(stats['anti_alias']['safe_1khz']-.6)<.01
    assert stats['anti_alias']['safe_6khz']<.001

    # 05、06 使用同一3点教学滤波器，图与手算完全一致。
    fs=16000; t=np.arange(fs//2)/fs
    x=.6*np.cos(2*np.pi*200*t)+.3*np.cos(2*np.pi*7000*t)
    kernels={'lowpass':h,'highpass':np.array([-.25,.5,-.25])}
    for kind,name,c,num in [('lowpass','低通',BLUE,'05'),('highpass','高通',GREEN,'06')]:
        filt=np.convolve(x,kernels[kind],mode='same')
        fig,axs=plt.subplots(3,1,figsize=(9,8.5),layout='constrained')
        ix=(t>=.1)&(t<=.102)
        axs[0].plot((t[ix]-.1)*1000,x[ix],color=GRAY,label='输入：200 Hz + 7 kHz',marker='.',ms=4)
        axs[0].plot((t[ix]-.1)*1000,filt[ix],color=c,label=f'{name}输出',marker='.',ms=4)
        axs[0].set_ylim(-1,1); axs[0].legend(fontsize=10); axs[0].set_title('时域：同一段2 ms波形');tidy(axs[0],'相对时间（ms）')
        # 0.25秒包含整数个200Hz和7kHz周期，边界已剔除。
        sli=slice(1600,5600)
        for v,col,lab in [(x[sli],GRAY,'输入'),(filt[sli],c,'输出')]:
            f,a=spectrum(v,fs);axs[1].plot(f/1000,a,color=col,label=lab)
        axs[1].set_xlim(0,8);axs[1].set_ylim(0,.66);axs[1].legend(fontsize=10);axs[1].set_title('频域：两种频率受到不同程度的削弱');tidy(axs[1],'频率（kHz）','单边峰值振幅')
        f=np.linspace(0,8000,1000)
        gain=np.cos(np.pi*f/fs)**2 if kind=='lowpass' else np.sin(np.pi*f/fs)**2
        axs[2].plot(f/1000,gain,color=c,lw=2)
        for freq in [200,7000]:
            g=math.cos(math.pi*freq/fs)**2 if kind=='lowpass' else math.sin(math.pi*freq/fs)**2
            axs[2].scatter(freq/1000,g,color=c,s=50)
            axs[2].annotate(f'{freq} Hz：{g:.4f}',(freq/1000,g),xytext=(10,8),textcoords='offset points',fontsize=11)
        axs[2].set_xlim(0,8.8);axs[2].set_ylim(-.05,1.16);axs[2].set_title('频率响应：增益1表示保留，增益0表示完全抑制');tidy(axs[2],'频率（kHz）','振幅增益')
        fig.suptitle(f'{name}教学Demo：逐点加权，得到不同的频率响应',fontsize=17)
        save(fig,root/f'{num}_{kind}.png')
        stats[kind]={'gain_200hz':float(math.cos(math.pi*200/fs)**2 if kind=='lowpass' else math.sin(math.pi*200/fs)**2),
                     'gain_7000hz':float(math.cos(math.pi*7000/fs)**2 if kind=='lowpass' else math.sin(math.pi*7000/fs)**2),
                     'output_amp_200hz':amplitude_at(filt[sli],fs,200),
                     'output_amp_7000hz':amplitude_at(filt[sli],fs,7000)}

    # 07 混合数组，包括相消点。
    left=np.array([0,.6,0,-.6,0]);right=np.array([.2,.2,-.2,.6,0]);mono=.5*left+.5*right
    assert np.allclose(mono,[.1,.4,-.1,0,0])
    fig,axs=plt.subplots(3,1,figsize=(9,7.5),layout='constrained')
    for ax,v,c,title in zip(axs,[left,right,mono],[BLUE,ORANGE,GREEN],['左声道L','右声道R','单声道M = 0.5L + 0.5R']):
        n=np.arange(5);ax.plot(n,v,'o-',color=c)
        for a,b in zip(n,v):ax.annotate(f'{b:.1f}',(a,b),xytext=(0,12),textcoords='offset points',ha='center',fontsize=11)
        ax.set_xticks(n);ax.set_ylim(-.85,.9);ax.axhline(0,color=GRAY,lw=.8);ax.set_title(title);tidy(ax,'同一时刻的采样编号n')
    axs[2].annotate('n=3：-0.6和+0.6相消',(3,0),xytext=(1.5,-.62),arrowprops={'arrowstyle':'->','color':GREEN},fontsize=11)
    fig.suptitle('多声道混合：同一时刻对齐后加权相加',fontsize=17)
    save(fig,root/'07_channel_mix.png')
    stats['mix']={'left':left.tolist(),'right':right.tolist(),'mono':mono.tolist()}

    # 08 非整数比：新点落在原网格的两个点之间。
    n=np.arange(5);x=np.array([0,.4,.8,.4,0]);pos=44100/16000
    value=np.interp(pos,n,x)
    assert abs(value-.4975)<1e-12
    fig,ax=plt.subplots(figsize=(9,5),layout='constrained')
    ax.plot(n,x,'o-',color=BLUE,label='假设低通处理后的原网格数值')
    ax.scatter([pos],[value],color=ORANGE,s=120,marker='D',zorder=4,label='输出第1点的位置')
    ax.axvline(pos,color=ORANGE,ls='--');ax.axvspan(2,3,color=ORANGE,alpha=.08)
    ax.annotate('位置=2.75625\n线性插值值=0.4975',(pos,value),xytext=(.8,.98),arrowprops={'arrowstyle':'->'},fontsize=13)
    ax.set_ylim(-.08,1.15);ax.set_xlim(-.2,4.2);ax.set_xticks(n);ax.legend(loc='lower left',fontsize=10)
    ax.set_title('44.1 kHz → 16 kHz：新时间点往往落在旧点之间')
    tidy(ax,'在原采样网格中的位置（可为小数）')
    save(fig,root/'08_fractional_resampling.png')
    stats['fractional_position']={'position':pos,'fraction':pos-2,'linear_value':float(value),'up':160,'down':441}

    # 真实转换的点数/时长核对。
    src=np.cos(2*np.pi*1000*np.arange(4410)/44100)
    dst=resample_poly(src,160,441)
    assert len(dst)==1600
    stats['actual_fractional_resample']={'input_count':len(src),'output_count':len(dst),'input_seconds':len(src)/44100,'output_seconds':len(dst)/16000}
    # 对常量、交替变化的教学滤波器作内区间核对。
    const=np.ones(20); alt=(-1.)**np.arange(20)
    assert np.allclose(np.convolve(const,h,'same')[1:-1],1)
    assert np.allclose(np.convolve(alt,h,'same')[1:-1],0)
    assert np.allclose(np.convolve(const,kernels['highpass'],'same')[1:-1],0)
    assert np.allclose(np.convolve(alt,kernels['highpass'],'same')[1:-1],alt[1:-1])
    (root/'calculation_results.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False,indent=2))
    print('计算核对通过；8张图已生成。')

if __name__=='__main__':
    main()
