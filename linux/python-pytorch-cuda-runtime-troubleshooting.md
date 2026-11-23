# 老旧 Linux 上 Python、PyTorch 与 CUDA 工具链兼容性排障知识库

更新日期：2026-11-19（UTC+8）

适用场景：uv Python / 虚拟环境、PyTorch、vLLM、Triton、FlashAttention、ModelScope 在老旧 Linux 上出现动态库版本缺失、子进程崩溃或编译工具卡住。

本文统一以 **/home/ec2** 为工作根目录。示例是迁移后的执行模板，不代表已经在目标服务器执行。原始排障发生在其他用户目录；其中成功经验可以复用，但服务器的库版本和工具路径必须重新验证。

## 1. 先理解问题属于哪一层

| 现象 | 所属层 | 优先处理 |
| --- | --- | --- |
| GLIBC_2.18 not found | glibc / 动态加载器 | 确认 Python 使用的 loader 和 libc |
| CXXABI_1.3.8 / GLIBCXX_* not found | C++ 运行库 | 确认实际加载的 libstdc++.so.6 |
| pthread_cond_destroy relocation error | loader 与 glibc 家族混用 | 配对 loader、libc、libpthread |
| pip 调 uname -rs 时 SIGSEGV | 系统子进程的运行环境 | 清除继承的 LD_LIBRARY_PATH 等变量 |
| nvcc / ptxas --version 长时间不返回 | 工具自身启动 / 库加载 | 先单独验证工具，不继续等待模型启动 |
| Found no NVIDIA driver | 驱动库 / GPU 可见性 | 检查 libcuda.so.1 和 GPU 访问 |
| Guessing wheel URL 后下载失败 | 网络 / wheel 发布情况 | 分开检查连接和安装包是否存在 |
| CUDA out of memory | 显存 | 调整模型、并行、音频 profiling 和容量 |
| vLLM shared memory broadcast 等待 | worker 尚未完成 | 检查 worker、子进程和前面的首个错误 |

核心原则：先修复最早发生的错误，再处理最后的汇总异常。不要把每次问题都归因于 Python 包版本，也不要用重装 Torch 代替库加载诊断。

## 2. 目录约定与前提

| 路径 | 用途 |
| --- | --- |
| /home/ec2/.venv-model | 已创建的 Python 虚拟环境 |
| /home/ec2/.venv-model/bin/python-hy | 模型推理使用的独立 Python ELF 副本 |
| /home/ec2/.venv-model/bin/python-hy-pip | 安装和下载使用的独立 Python ELF 副本 |
| /home/ec2/bin | patchelf、包装脚本 |
| /home/ec2/models | 模型文件 |
| /home/ec2/packages | pip 下载包、构建产物 |
| /home/ec2/logs | 启动、安装、诊断日志 |
| /home/ec2/tmp | 临时文件 |
| /home/ec2/cuda-12.9 | 可选的 CUDA Toolkit 12.9 安装目录 |
| /home/ec2/knowledge-base | 本知识库 |

本案例已有一套独立运行库：

- loader：/opt/compiler/gcc-12/lib64/ld-linux-x86-64.so.2
- libc、libpthread、libstdc++ 等：/opt/compiler/gcc-12/lib64
- GCC / G++：/opt/compiler/gcc-12/bin/gcc、/opt/compiler/gcc-12/bin/g++
- NVIDIA 驱动库搜索目录：/lib64、/usr/lib64

**这些 /opt 路径是既有基础设施，本文不把它们机械替换成 /home/ec2。** 如果新机器没有这套完整环境，必须先准备匹配的新运行库和工具链；目录名字叫 gcc-12 不代表其中天然包含新版 glibc。不能只复制一个 libc.so.6 或建立空目录来替代。

原案例还存在跨目录软链接，迁移时必须检查真实目标；拷贝一个 lib64 目录未必得到完整运行环境。

准备工作目录：

```bash
mkdir -p /home/ec2/bin /home/ec2/models /home/ec2/packages \
  /home/ec2/logs /home/ec2/tmp /home/ec2/knowledge-base
```

## 3. 原理：四种路径不要混淆

### 3.1 ELF interpreter

ELF 可执行文件记录的动态加载器路径，例如：

```text
/opt/compiler/gcc-12/lib64/ld-linux-x86-64.so.2
```

内核启动动态链接的 Python 时，首先使用该 loader。它不是 Python 的模块搜索路径，也不是虚拟环境配置。

### 3.2 RPATH / RUNPATH

ELF 内部记录的共享库搜索目录。

- patchelf --set-rpath 通常写入 DT_RUNPATH。
- --force-rpath 与 --set-rpath 配合使用，写入 DT_RPATH。
- RUNPATH 对直接依赖生效，间接依赖需要自己的搜索路径；RPATH 可以作用于更深的依赖链。
- RPATH 的依赖链传播指共享库依赖，不是把设置传播给 exec 启动的独立子进程。
- RPATH 优先级更强，可能选中非预期的同名库，因此仍要检查实际映射。

### 3.3 LD_LIBRARY_PATH

环境变量。Python 的子进程默认会继承。

把新版 glibc 目录放进去，可能让 Python 正常，却让系统 uname、gcc、sh、curl 使用原有 loader 加载新版 libc，发生崩溃或卡住。

因此：

> 为一个进程修复库加载，不等于可以把同一套动态库环境传给全部子进程。

不要把这个案例中的 glibc 目录直接全局写进 /etc/profile 或所有终端的启动配置。

### 3.4 CC / CXX / CUDA_HOME / TRITON_PTXAS_PATH

| 配置 | 指向什么 | 解决什么 |
| --- | --- | --- |
| CC | C 编译器程序或包装程序 | 选择 host C 编译器 |
| CXX | C++ 编译器程序或包装程序 | 选择 host C++ 编译器 |
| CUDAHOSTCXX | 部分 CUDA 构建系统识别的 host C++ 编译器 | 是否生效取决于构建系统 |
| CUDA_HOME | 完整 CUDA Toolkit 根目录 | nvcc、头文件和开发库定位 |
| TRITON_PTXAS_PATH | 可执行的 ptxas 或包装程序 | Triton PTX 汇编工具定位 |

设置 CC 不会改变 Python 的 loader。设置 TRITON_PTXAS_PATH 不会安装 nvcc，也不能替代完整 Toolkit。

## 4. 先采集环境，避免盲目修改

系统命令使用干净环境运行：

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT /usr/bin/uname -rs

env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /usr/bin/ldd --version

env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT nvidia-smi
```

如果 uname、ldd 不在 /usr/bin，先通过 command -v 查实际位置。

检查工具和库：

```bash
ls -l /opt/compiler/gcc-12/lib64/ld-linux-x86-64.so.2 \
  /opt/compiler/gcc-12/lib64/libc.so.6 \
  /opt/compiler/gcc-12/lib64/libstdc++.so.6

readlink -f /opt/compiler/gcc-12/lib64/ld-linux-x86-64.so.2

/home/ec2/bin/patchelf --version
/home/ec2/bin/patchelf --help

readelf -l /home/ec2/.venv-model/bin/python
readelf -d /home/ec2/.venv-model/bin/python
```

记录 Python、Torch、驱动、Toolkit、编译器五类版本，分别判断，不只看 nvidia-smi 的 CUDA Version。

## 5. 修复 Python：创建独立 ELF 副本

### 5.1 为什么复制

虚拟环境的 bin/python 可能是软链接，直接修改可能影响 uv 管理的底层解释器。复制实际 ELF 到当前虚拟环境，保留原始 Python，专门为模型任务修复副本。

这只改变程序的启动和动态链接配置；不会升级 Python、安装依赖、修复所有第三方工具。

前提：虚拟环境已存在、原始 Python ELF 没有损坏、patchelf 已放到 /home/ec2/bin/patchelf 并可执行。下面步骤只在首次创建时运行；不要覆盖已验证的副本。

```bash
cp -L --no-clobber /home/ec2/.venv-model/bin/python \
  /home/ec2/.venv-model/bin/python-hy
```

使用清理后的环境执行 patchelf：

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/bin/patchelf \
  --set-interpreter /opt/compiler/gcc-12/lib64/ld-linux-x86-64.so.2 \
  --set-rpath /opt/compiler/gcc-12/lib64:/lib64:/usr/lib64 \
  /home/ec2/.venv-model/bin/python-hy
```

### 5.2 先不用 LD_LIBRARY_PATH 验证

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/.venv-model/bin/python-hy - <<'PY'
import sys
import subprocess
import torch

print("Python:", sys.executable, flush=True)
print("venv prefix:", sys.prefix, flush=True)
print("Torch:", torch.__version__, flush=True)
print("Torch CUDA:", torch.version.cuda, flush=True)
print("GPU 可用:", torch.cuda.is_available(), flush=True)
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0), flush=True)
print("uname:", subprocess.check_output(
    ["uname", "-rs"], text=True, timeout=10).strip(), flush=True)
PY
```

同时验证 Torch 和 uname，避免“主进程正常，子进程崩溃”。

### 5.3 如果取消环境变量后又缺 CXXABI

可以在第二个独立副本上尝试 DT_RPATH，不直接覆盖已有推理解释器：

```bash
cp -L --no-clobber /home/ec2/.venv-model/bin/python-hy \
  /home/ec2/.venv-model/bin/python-hy-pip

env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/bin/patchelf \
  --force-rpath \
  --set-rpath /opt/compiler/gcc-12/lib64:/lib64:/usr/lib64 \
  /home/ec2/.venv-model/bin/python-hy-pip
```

把 5.2 的命令改用 python-hy-pip 重试。使用下面命令检查 RPATH / RUNPATH：

```bash
readelf -d /home/ec2/.venv-model/bin/python-hy-pip
```

这是针对间接依赖的修复候选，不保证对所有 Python 扩展成立。若仍失败，查看下一节的实际映射。确认 sys.prefix 指向 /home/ec2/.venv-model，避免安装进入错误环境。

### 5.4 老版本 patchelf 的误导性错误

案例中老版本支持 --set-rpath，不支持 --add-rpath。使用不存在的选项可能得到：

```text
stat: No such file or directory
```

即使最后的 Python 文件存在，也要检查 --help，确认是否把未知选项当成文件名处理。--set-rpath 会替换原搜索路径；修改前保留原值，需要时把必要目录一并写入。

如果修改后出现 needed by python 的异常库名 x，不要建立名为 x 的假库绕过。停止使用损坏副本，从健康原件重新复制；仅凭该错误不能确定是缺包还是 ELF 被错误修改。

## 6. 看实际加载了哪个库

### 6.1 loader 的依赖检查

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /opt/compiler/gcc-12/lib64/ld-linux-x86-64.so.2 \
  --library-path /opt/compiler/gcc-12/lib64:/lib64:/usr/lib64 \
  --list /home/ec2/.venv-model/bin/python-hy
```

这主要列出启动时依赖；Python 扩展通过 dlopen 加载的库还需在导入后检查。

### 6.2 导入 Torch 后检查映射

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/.venv-model/bin/python-hy-pip - <<'PY'
import torch

print("Torch:", torch.__version__)
print("CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    torch.cuda.init()
paths = set()
with open("/proc/self/maps") as f:
    for line in f:
        if any(x in line for x in (
            "libc.so", "libc-", "libstdc++", "libpthread", "libcuda.so")):
            paths.add(line.split()[-1])
print("\n".join(sorted(paths)))
PY
```

### 6.3 需要更详细日志时

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  LD_DEBUG=libs,versions \
  /home/ec2/.venv-model/bin/python-hy-pip \
  -c 'import torch; print(torch.cuda.is_available())' \
  > /home/ec2/logs/python-loader.log 2>&1
```

只在诊断时启用。日志很大，不应作为长期启动配置。

## 7. pip、uv 和 CLI 的正确使用

### 7.1 uv 管理的 Python 不应直接改全局包

externally-managed-environment 表示基础 Python 被管理。使用虚拟环境，并显式调用虚拟环境解释器：

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/.venv-model/bin/python-hy-pip -m pip --version
```

不把 --break-system-packages 当成虚拟环境安装的常规修复方案。

### 7.2 pip 因 uname SIGSEGV 失败

堆栈：

```text
pip -> distro -> subprocess.check_output(("uname", "-rs"))
CalledProcessError: ... SIGSEGV
```

表明 pip 在准备网络会话和 User-Agent 时调用 uname，尚未下载或编译目标包。结合本案例，优先排查 uname 继承新版 glibc 路径。

处理顺序：

1. 使用 5.2 同时验证 Torch 和 uname。
2. 取消 LD_LIBRARY_PATH / LD_PRELOAD / LD_AUDIT。
3. 使用验证通过的 python-hy-pip。
4. 需要时按 5.3 配置 RPATH。
5. 再重试 pip。

--disable-pip-version-check 只能关闭版本检查，不会阻止正常下载会话构造 User-Agent，也不能单独修复 uname 崩溃。

### 7.3 ModelScope 等命令仍用原解释器

bin/modelscope 通常是有 shebang 的 Python 启动脚本。即使另一个 Python 已修复，直接执行 modelscope 仍可能走原解释器。

检查：

```bash
head -n 1 /home/ec2/.venv-model/bin/modelscope
```

对于已安装的 Python CLI 脚本，显式指定修复后的解释器：

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/.venv-model/bin/python-hy-pip \
  /home/ec2/.venv-model/bin/modelscope \
  download \
  --model Qwen/Qwen3-TTS-12Hz-1.7B-Base \
  --local_dir /home/ec2/models/Qwen3-TTS-12Hz-1.7B-Base
```

该写法适用于这个文本 Python 启动脚本，不适用于任意二进制 CLI。

GLIBC_2.18 not found 来自 cryptography/_rust.abi3.so 时，先确认 Python 实际加载的 libc，不要第一时间降级 cryptography 或替换系统 libc。

### 7.4 alias 为什么不够

alias 只影响当前 shell 的命令展开。程序内部的 sys.executable、os.execv 和 multiprocessing 子进程不会自动使用 shell alias。

需要让真正运行的 ELF 本身配置正确，并确认 sys.executable 指向修复后的副本。

## 8. GCC：运行库目录和编译器不是一回事

/opt/compiler/gcc-12/lib64 提供运行库，并不等于当前 CC 已经是 GCC 12。

本案例有两种不同需求：

| 任务 | 用法 |
| --- | --- |
| 之前的 Triton 小型 C 辅助模块 | 曾通过清理环境后调用系统 /bin/gcc 解决 |
| FlashAttention / PyTorch C++ 扩展 | 应验证满足构建要求的 C++ 工具链，可测试 GCC 12 |

先验证 GCC 12：

```bash
timeout 15s env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /opt/compiler/gcc-12/bin/gcc --version

timeout 15s env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /opt/compiler/gcc-12/bin/g++ --version
```

如果正常，可创建清理环境的包装程序。只依赖 Python 标准库，不修改第三方源码：

```bash
cat > /home/ec2/bin/hy-cc <<'PY'
#!/home/ec2/.venv-model/bin/python-hy-pip
import os
import sys

env = os.environ.copy()
for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT"):
    env.pop(key, None)
tool = "/opt/compiler/gcc-12/bin/gcc"
os.execve(tool, [tool, *sys.argv[1:]], env)
PY

cat > /home/ec2/bin/hy-cxx <<'PY'
#!/home/ec2/.venv-model/bin/python-hy-pip
import os
import sys

env = os.environ.copy()
for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT"):
    env.pop(key, None)
tool = "/opt/compiler/gcc-12/bin/g++"
os.execve(tool, [tool, *sys.argv[1:]], env)
PY

chmod +x /home/ec2/bin/hy-cc /home/ec2/bin/hy-cxx
```

验证包装程序：

```bash
timeout 15s /home/ec2/bin/hy-cc --version
timeout 15s /home/ec2/bin/hy-cxx --version
```

如果 GCC 12 清除变量后不能启动，不要先把这两个包装程序放进正式构建。它自己的 loader、cc1、cc1plus、collect2 和 linker 也可能需要完整环境。仅包装 gcc 主程序不保证所有编译子进程可用。

原案例系统 GCC 遇到 C99 for 循环语法错误时，在专用 C 包装器中添加过 -std=gnu99。这不应机械加入 C++ 编译器；FlashAttention 的 C++ 标准由构建系统决定。

## 9. Triton ptxas 卡住的处理

### 9.1 判断是不是“真的在编译”

如果进程树持续出现 ptxas --version，数分钟不退出，这不是正常的 PTX 内核编译进度，应优先检查 ptxas 自身启动。

```bash
ps -eo pid,ppid,stat,etime,pcpu,wchan:28,args --forest \
  | grep -E 'VLLM|ptxas|nvcc|cc1|gcc|g\+\+' \
  | grep -v grep
```

先直接验证：

```bash
timeout 15s env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/.venv-model/lib/python3.12/site-packages/triton/backends/nvidia/bin/ptxas \
  --version
```

如果直接运行仍失败，而显式新 loader 可以运行，则使用以下包装方式。

### 9.2 只为 ptxas 指定 loader

```bash
cat > /home/ec2/bin/hy-ptxas <<'PY'
#!/home/ec2/.venv-model/bin/python-hy-pip
import os
import sys

env = os.environ.copy()
for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT"):
    env.pop(key, None)

loader = "/opt/compiler/gcc-12/lib64/ld-linux-x86-64.so.2"
tool = (
    "/home/ec2/.venv-model/lib/python3.12/site-packages/"
    "triton/backends/nvidia/bin/ptxas"
)
os.execve(loader, [
    loader,
    "--library-path", "/opt/compiler/gcc-12/lib64:/lib64:/usr/lib64",
    tool,
    *sys.argv[1:],
], env)
PY

chmod +x /home/ec2/bin/hy-ptxas
timeout 15s /home/ec2/bin/hy-ptxas --version
```

验证通过后，在模型进程的启动环境指定：

```bash
export TRITON_PTXAS_PATH=/home/ec2/bin/hy-ptxas
```

原案例通过显式 loader 获得 ptxas 12.8 的版本输出。这个结果说明工具能够启动，不代表全部 GPU 内核编译、驱动兼容性和推理都已经验证。

## 10. CUDA：驱动、Torch runtime、Toolkit 分开管理

### 10.1 三个 CUDA 版本为什么不同

| 命令 / 字段 | 含义 |
| --- | --- |
| nvidia-smi 的 CUDA Version | 驱动报告的 CUDA 支持级别，不是本地 nvcc 版本 |
| torch.version.cuda | Torch 构建时使用的 CUDA 版本 |
| nvcc --version | 本地 Toolkit 的编译器版本 |

原案例：驱动 535.161.07，Torch 2.13.0+cu129，本地 nvcc 12.2。torch.cuda.is_available() 为 True 只证明基础初始化成功，不保证后续新 PTX、新 API 和所有算子都可运行。

CUDA 12.x 的小版本兼容存在限制；不要直接根据 CUDA available=True 认定驱动完全满足新 Toolkit。若出现 unsupported PTX version、driver too old 等错误，另查官方兼容性要求。

### 10.2 诊断 nvcc 超时

```bash
timeout 15s env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /usr/local/cuda/bin/nvcc --version
```

如果不成功，先通过 file 检查目标类型：

```bash
file /usr/local/cuda/bin/nvcc
```

仅当它是可执行 ELF，才尝试新 loader：

```bash
timeout 15s env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /opt/compiler/gcc-12/lib64/ld-linux-x86-64.so.2 \
  --library-path /opt/compiler/gcc-12/lib64:/lib64:/usr/lib64 \
  /usr/local/cuda/bin/nvcc --version
```

显式 loader 启动 nvcc 并不保证它随后调用的 cicc、ptxas、host compiler 全部正常。完整编译需要额外验证。

### 10.3 可选：独立安装 Toolkit 12.9.1

作用：让本地开发工具版本接近 Torch cu129，减少构建时的版本差异。不是当前所有错误的必选修复；先确认服务器操作系统和 glibc 满足官方安装要求。

保留已有 12.2，安装到 /home/ec2/cuda-12.9。以下命令仅选择 Toolkit，不安装驱动。

```bash
cd /home/ec2/packages

env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  curl -fL --retry 3 --connect-timeout 30 \
  -o cuda_12.9.1_575.57.08_linux.run \
  https://developer.download.nvidia.com/compute/cuda/12.9.1/local_installers/cuda_12.9.1_575.57.08_linux.run

env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  sh /home/ec2/packages/cuda_12.9.1_575.57.08_linux.run --check

mkdir -p /home/ec2/tmp/cuda-install

env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  sh /home/ec2/packages/cuda_12.9.1_575.57.08_linux.run \
  --silent \
  --toolkit \
  --toolkitpath=/home/ec2/cuda-12.9 \
  --tmpdir=/home/ec2/tmp/cuda-install
```

安装后：

```bash
timeout 15s env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/cuda-12.9/bin/nvcc --version
```

如果安装器因编译器 / glibc / 发行版检查失败，查看 /var/log/cuda-installer.log；不要直接靠 --override 假设能解决 ABI 不兼容。

如果需要新 loader 才能运行新版 nvcc，还需要按实际子工具布局设计包装或修复环境。本文不提供“对 nvcc 主程序套 loader 即保证源码编译成功”的承诺。

## 11. FlashAttention 安装失败的分阶段处理

### 11.1 阶段一：metadata 导入 Torch 失败

```text
Preparing metadata ...
ImportError: /lib64/libstdc++.so.6: CXXABI_1.3.8 not found
```

先修复 Python / Torch 导入。不是 FlashAttention CUDA 内核编译错误。

--no-build-isolation 表示复用当前环境的构建依赖；需要当前环境已安装可用的 Torch、setuptools、wheel、packaging、ninja 等依赖。它不会修复 loader。

### 11.2 阶段二：猜测预编译 wheel 地址

```text
Guessing wheel URL: ...cu12torch2.13cxx11abiTRUE-cp312...
Remote end closed connection without response
```

这是尝试下载预编译包时的连接失败；单凭这个异常不能判断目标文件存在。

本次排障查询 v2.8.3.post2 发布附件时，没有看到 Torch 2.13 对应 wheel。这个结论是当时的附件快照，后续使用时应重新检查官方 Release。安装脚本能够拼接出 URL，不代表官方发布了该文件。

检查匹配项：

- Python：cp312。
- Torch：2.13。
- CUDA wheel 标记：cu12。
- C++ ABI：与 torch._C._GLIBCXX_USE_CXX11_ABI 一致。
- 架构：linux_x86_64。

不要把 Torch 2.8 的 wheel 重命名为 Torch 2.13 后安装。换 pip 镜像也不一定影响 setup.py 内部直接访问 GitHub 的下载。

### 11.3 阶段三：明确尝试源码构建

前提：

1. python-hy-pip 能导入 Torch，并正常运行 uname。
2. CUDA Toolkit 完整，nvcc、头文件和开发库可用。
3. hy-cc、hy-cxx 能工作，C++ 标准与工具链满足当前 Torch 要求。
4. 系统运行库能支持这些编译工具及其子工具。
5. 尚未假定 FlashAttention 2.8.3.post2 源码兼容 Torch 2.13。

在上述条件满足、12.9 已安装到示例位置后，可使用以下构建模板：

```bash
set -o pipefail

env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  CUDA_HOME=/home/ec2/cuda-12.9 \
  PATH=/home/ec2/cuda-12.9/bin:$PATH \
  CC=/home/ec2/bin/hy-cc \
  CXX=/home/ec2/bin/hy-cxx \
  CUDAHOSTCXX=/home/ec2/bin/hy-cxx \
  FLASH_ATTENTION_FORCE_BUILD=TRUE \
  MAX_JOBS=2 \
  TMPDIR=/home/ec2/tmp \
  /home/ec2/.venv-model/bin/python-hy-pip \
  -m pip --disable-pip-version-check install \
  'flash-attn==2.8.3.post2' \
  --no-cache-dir \
  --no-build-isolation \
  --no-deps \
  --verbose \
  2>&1 | tee /home/ec2/logs/flash-attn-build.log
```

说明：

- FORCE_BUILD=TRUE 跳过猜测 wheel 的下载，直接尝试源码构建。
- --no-deps 保留当前 Torch 等运行依赖；缺少依赖时需单独补齐。
- MAX_JOBS=2 限制编译并发；根据实际内存调整，不保证一定不 OOM。
- CUDAHOSTCXX 是否被具体构建流程采用，需要看实际 nvcc 命令，不能仅凭变量已设置认定生效。
- PATH 和 CUDA_HOME 只能选择工具，不会修复工具的动态加载问题。
- 该模板未在目标机器完成源码构建验证。失败时找日志里的首个编译错误。

只有运行程序明确需要独立 flash-attn 包时，才进行这一步；安装它不等于自动改变 vLLM 实际选择的 attention backend。

## 12. 模型启动慢：和运行库问题分开处理

### 12.1 先确定最后在做什么

```bash
ps -eo pid,ppid,stat,etime,pcpu,wchan:28,args --forest \
  | grep -E 'VLLM|python-hy|ptxas|nvcc|cc1|gcc' \
  | grep -v grep

nvidia-smi

tail -n 100 /home/ec2/logs/hy-vllm-startup.log
```

| 观察 | 下一步 |
| --- | --- |
| ptxas --version 长时间不退出 | 第 9 节 |
| gcc / g++ 启动崩溃 | 第 8 节 |
| worker 明确 OOM | 检查显存、音频 profiling 和容量 |
| CPU / GPU 持续工作、日志有进展 | 可能在加载 / 编译，继续观察具体任务 |
| 只有 shared memory broadcast 等待 | 查 worker；这行不是根因 |

### 12.2 audio-items 和显存

Hy-SimulMT 的 launcher 曾默认允许 1024 个 audio items，vLLM 启动 profiling 会受多模态配置影响。初次整段音频测试可以降低限制，减轻 profiling 压力。

但 audio-items 是**每个请求的音频项目数量**，不是秒数。流式同传请求可能包含历史音频和新块；设置为 1 可能使网页预检或后续请求失败。按实际最大请求设置，不能只为快启动无限压低。

max-num-seqs 是并行序列容量，max-model-len 是单序列上下文容量，max-num-batched-tokens 是单次调度的 token 预算，不能互相当成音频时长。

关闭详细 DEBUG / Dynamo 日志有助于减少干扰；它不能修复真实工具卡死。--enforce-eager 也不等于所有 Triton 编译都关闭。

## 13. 修复后的验收顺序

不要只验证 python --version。按下面顺序推进，每一层成功后再进入下一层：

1. Python：版本、sys.executable、sys.prefix。
2. 动态库：导入 Torch / cryptography，确认 libc 和 libstdc++ 实际路径。
3. 系统子进程：同一 Python 中执行 uname，不能崩溃或超时。
4. GPU：torch.cuda.is_available()、设备名、最小张量计算。
5. 编译工具：gcc、g++、nvcc、ptxas --version 都能退出。
6. 构建：如果业务需要，验证一次真实扩展或 Triton 内核编译。
7. 服务：vLLM 启动完成后，检查 /v1/models 和真实音频请求。
8. 长时间运行：按实际并发、历史音频规模、显存预算验证。

最小 GPU 运算：

```bash
env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT \
  /home/ec2/.venv-model/bin/python-hy-pip - <<'PY'
import torch

assert torch.cuda.is_available(), "CUDA 初始化失败"
a = torch.ones((256, 256), device="cuda")
b = a @ a
torch.cuda.synchronize()
print("GPU:", torch.cuda.get_device_name(0))
print("结果:", b[0, 0].item())
assert b[0, 0].item() == 256.0
PY
```

该测试验证一个基础 GPU 运算，不代表 FlashAttention 或全部模型算子已通过。

服务端口已监听且初始化完成后：

```bash
curl -fsS --max-time 10 http://127.0.0.1:8800/v1/models
```

## 14. 已知验证范围与回退

| 方法 / 状态 | 本案例的证据 |
| --- | --- |
| Python 副本设置 interpreter、库路径 | 此前排障成功恢复 Python / Torch 导入 |
| 加入系统驱动库搜索目录 | 此前 cuInit=0、CUDA available=True |
| 清理系统编译器的继承环境 | 此前修复过 GCC 子进程问题 |
| ptxas 显式指定新 loader | 此前版本查询从卡住恢复到正常输出 |
| nvcc 版本查询 | 已取得本地 Toolkit 12.2 版本输出；没有明确记录是哪条尝试命令成功 |
| DT_RPATH 安装专用 Python | 后续提出的修复候选，需在目标机器验证 |
| Toolkit 12.9 新目录安装 | 安装方案，未获得成功安装确认 |
| FlashAttention + Torch 2.13 源码构建 | 未获得成功确认 |
| 本文 /home/ec2 路径 | 迁移模板，未连接目标主机执行 |

回退原则：

- 保留 bin/python 原件，使用独立副本。
- 已有推理解释器正常时，不直接覆盖它。
- wrapper 验证失败就取消相应 CC / CXX / TRITON_PTXAS_PATH。
- 只在已验证的进程范围内设置变量，不把私有 glibc 路径全局扩散。
- 不覆盖 /lib64/libc.so.6，不替换系统 loader。
- 新机器上不能仅复制虚拟环境就假设可运行：uv 基础 Python 路径、软链接、shebang、pyvenv.cfg 和运行库位置都可能绑定原机器。优先在目标位置重新创建环境、重装依赖，再复制并修复独立解释器。
- 如果老旧系统反复需要修复多个工具，优先考虑受支持的新系统或容器环境。容器统一用户态运行库，但仍依赖宿主机驱动和 GPU 访问条件。

## 15. 参考资料

以下官方资料用于解释工具机制；本文具体故障结论另以案例日志为依据。

1. [Linux ld.so：loader、搜索路径、RPATH 与 RUNPATH](https://man7.org/linux/man-pages/man8/ld.so.8.html)
2. [patchelf 官方项目](https://github.com/NixOS/patchelf)
3. [patchelf 参数手册](https://github.com/NixOS/patchelf/blob/master/patchelf.1)
4. [FlashAttention 官方项目](https://github.com/Dao-AILab/flash-attention)
5. [FlashAttention v2.8.3.post2 构建脚本](https://github.com/Dao-AILab/flash-attention/blob/v2.8.3.post2/setup.py)
6. [FlashAttention v2.8.3.post2 发布附件](https://github.com/Dao-AILab/flash-attention/releases/tag/v2.8.3.post2)
7. [CUDA Toolkit 12.9.1 Linux 安装说明](https://docs.nvidia.com/cuda/archive/12.9.1/cuda-installation-guide-linux/index.html)
8. [NVIDIA CUDA 兼容性说明](https://docs.nvidia.com/deploy/cuda-compatibility/)
9. [uv Python 管理说明](https://docs.astral.sh/uv/concepts/python-versions/)

