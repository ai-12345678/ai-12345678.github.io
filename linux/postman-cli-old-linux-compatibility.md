# 旧 Linux 环境运行 Postman CLI、Node.js 与 Python 3：动态加载器兼容方案

本文覆盖三类程序：pkg 单文件 Postman CLI、普通 Node.js ELF、Miniforge3 中的 Python 3。前者通常需要保持自身可执行文件身份，后两者可以优先尝试显式调用动态加载器；所有方案均需检查运行库匹配。

## 问题背景

在较老的 Linux 环境中直接运行 `postman-cli`，可能出现以下错误：

```text
./postman-cli: /usr/lib64/libstdc++.so.6: version `CXXABI_1.3.11' not found
./postman-cli: /usr/lib64/libstdc++.so.6: version `GLIBCXX_3.4.14' not found
./postman-cli: /usr/lib64/libstdc++.so.6: version `GLIBCXX_3.4.19' not found
```

这说明 `postman-cli` 加载了系统自带的旧版 `libstdc++.so.6`，无法满足程序需要的符号版本。

当前机器已经准备了新版 GCC Runtime：

```text
/home/gcc-10/lib
```

目标是让 `postman-cli` 使用该目录中的动态加载器和运行库，而不是系统默认版本。

## 现象对比

普通 Node.js ELF 程序可以显式通过新版动态加载器启动：

```bash
exec /home/gcc-10/lib/ld-linux-x86-64.so.2 \
  --library-path /home/gcc-10/lib \
  /home/node-v22.12.0-linux-x64/bin/node \
  "$@"
```

但用同样方式启动 `postman-cli`：

```bash
exec /home/gcc-10/lib/ld-linux-x86-64.so.2 \
  --library-path /home/gcc-10/lib \
  /home/postman-cli
```

可能报错：

```text
Pkg: Error reading from file.
```

## 根因

`postman-cli` 是通过 `pkg` 打包的 Node.js 单文件程序。它不仅包含 ELF 和 Node Runtime，还在文件尾部附加了 JavaScript、Snapshot 和资源文件：

```text
postman-cli
├── ELF Header
├── Node Runtime
├── Native Code
└── pkg payload
    ├── JavaScript
    ├── Snapshot
    └── Resources
```

程序启动后，`pkg` Runtime 需要基于当前的主程序定位当前可执行文件，并从文件尾部读取 payload。

如果把 `ld-linux-x86-64.so.2` 作为 `exec` 的目标程序：

```text
Shell
  └── exec ld-linux
        └── 加载 postman-cli
              └── pkg Runtime
                    └── 基于当前主程序定位到 ld-linux
                          └── 尝试从 ld-linux 读取 payload（失败）
```

此时主程序入口是动态加载器。`pkg` Runtime 可能将 `ld-linux` 识别为当前可执行文件，并错误地从 `ld-linux` 文件尾部读取 payload，最终导致读取失败。

## 核心结论

不要使用下面的方式启动 `postman-cli`：

```bash
exec /home/gcc-10/lib/ld-linux-x86-64.so.2 \
  --library-path /home/gcc-10/lib \
  /home/postman-cli
```

推荐修改副本 ELF Header 中的 `PT_INTERP`，让 Kernel 在直接执行 `postman-cli` 时自动选择新的动态加载器：

```text
Shell
  └── exec /home/postman-cli.compat
        └── Kernel 读取 PT_INTERP
              └── /home/pm-ld.so
                    └── postman-cli.compat
                          └── pkg 读取自身 payload
```

这样，Shell 直接执行的仍然是 `postman-cli.compat`，能够最大程度保持 `pkg` 单文件程序原有的启动语义。

## 修改步骤

### 1. 设置路径

```bash
POSTMAN_DIR=/home
RUNTIME_DIR=/home/gcc-10/lib
```

### 2. 检查文件和动态加载器

```bash
test -x "$POSTMAN_DIR/postman-cli"
test -x "$RUNTIME_DIR/ld-linux-x86-64.so.2"

readelf -lW "$POSTMAN_DIR/postman-cli" |
  grep 'Requesting program interpreter'
```

预期原始 Interpreter 为：

```text
[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]
```

### 3. 创建动态加载器短链接

原 Interpreter 字符串长度有限，因此使用较短的固定路径：

```bash
ln -sfn \
  "$RUNTIME_DIR/ld-linux-x86-64.so.2" \
  /home/pm-ld.so
```

### 4. 复制兼容版本

保留原文件，不要直接修改：

```bash
cp -a \
  "$POSTMAN_DIR/postman-cli" \
  "$POSTMAN_DIR/postman-cli.compat"
```

### 5. 原位修改 `PT_INTERP`

将：

```text
/lib64/ld-linux-x86-64.so.2
```

替换为：

```text
/home/pm-ld.so
```

并使用 `\0` 补齐剩余空间：

```bash
perl -0777 -i -pe '
s{\Q/lib64/ld-linux-x86-64.so.2\E}{
  "/home/pm-ld.so" .
  "\0" x (
    length("/lib64/ld-linux-x86-64.so.2") -
    length("/home/pm-ld.so")
  )
}e
' "$POSTMAN_DIR/postman-cli.compat"
```

这里必须进行等长度原位替换，不能插入或删除字节。否则可能改变 `pkg` payload 的文件偏移，使内嵌资源无法读取。

## 验证

### 1. 验证 Interpreter

```bash
readelf -lW "$POSTMAN_DIR/postman-cli.compat" |
  grep 'Requesting program interpreter'
```

预期结果：

```text
[Requesting program interpreter: /home/pm-ld.so]
```

### 2. 验证动态库来源

```bash
LD_LIBRARY_PATH="$RUNTIME_DIR" \
  ldd "$POSTMAN_DIR/postman-cli.compat" |
  grep -E 'libstdc\+\+|libgcc_s'
```

确认 `libstdc++.so.6` 和 `libgcc_s.so.1` 来自：

```text
/home/gcc-10/lib
```

### 3. 验证 Postman CLI

```bash
LD_LIBRARY_PATH="$RUNTIME_DIR" \
  "$POSTMAN_DIR/postman-cli.compat" --version
```

此时不要再显式调用 `ld-linux-x86-64.so.2`。

## 最终包装脚本

可以创建 `/home/postman-cli.sh`：

```sh
#!/bin/sh

RUNTIME_DIR=/home/gcc-10/lib
POSTMAN_BIN=/home/postman-cli.compat

export LD_LIBRARY_PATH="$RUNTIME_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec "$POSTMAN_BIN" "$@"
```

增加执行权限：

```bash
chmod +x /home/postman-cli.sh
```

使用示例：

```bash
/home/postman-cli.sh --version

/home/postman-cli.sh collection run postman/collections/speech-split \
  -e postman/environments/dev.environment.yaml \
  --verbose
```

## 注意事项

- 保留原始 `/home/postman-cli`，只修改复制后的兼容版本。
- 新 Interpreter 路径不能长于原路径，否则无法安全地原位替换。
- 不要使用会改变文件布局的方式修改这个 `pkg` 单文件程序。
- `PT_INTERP` 决定使用哪个动态加载器，`LD_LIBRARY_PATH` 决定优先从哪里加载共享库，两者作用不同。
- 升级 `postman-cli` 后，应从新的原始文件重新生成 `postman-cli.compat`。
- 如果仍出现 `GLIBC_*` 缺失，说明问题已超出 `libstdc++` 范畴，还需要检查新版 Runtime 与系统 glibc、内核之间的兼容性。

## Postman CLI 小结

本方案的关键是：

> 对于 `pkg` 打包的 Node.js 单文件程序，让 Kernel 通过 ELF `PT_INTERP` 选择新的动态加载器，不要把动态加载器本身作为程序入口执行。

最终运行方式为：

```bash
LD_LIBRARY_PATH=/home/gcc-10/lib \
  exec /home/postman-cli.compat "$@"
```

从 Kernel 的视角看，两种启动方式的关键区别是：

- 执行 `exec /home/postman-cli.compat` 时，Kernel 视角中的可执行文件是 `/home/postman-cli.compat`。随后 Kernel 根据该 ELF 的 `PT_INTERP` 再加载指定的动态加载器。
- 执行 `exec /home/gcc-10/lib/ld-linux-x86-64.so.2 xxxx` 时，Kernel 视角中的可执行文件是 `/home/gcc-10/lib/ld-linux-x86-64.so.2`，而 `xxxx` 只是传递给动态加载器的参数。

注意：`pkg` 拿到的是 `/proc/self/exe` 指向的路径，然后打开这个路径对应的文件，在文件中按照偏移读取 prelude 和 payload。

| 项目 | 写法 A：`exec ./postman-cli` | 写法 B：`exec ld.so --library-path ... ./postman-cli` |
|---|---|---|
| `/proc/self/exe` | `postman-cli` | `ld.so` |


## Node.js：通过 exec 启动普通 ELF

上述 Postman CLI 的特殊问题，主要来自 pkg 单文件程序对自身可执行文件的定位。普通 Node.js 和 Python 3 动态链接 ELF 通常可以直接交给指定的动态加载器启动，**无须先修改 PT_INTERP**。

### 1. 先确认新 Runtime 是否完整

下文沿用机器上的路径作为示例；目录名包含 gcc-10 **不代表** 其中的 GLIBC 版本。实际使用前必须核验动态加载器与运行库来源：

~~~bash
RUNTIME_DIR=/home/gcc-10/lib
LOADER="$RUNTIME_DIR/ld-linux-x86-64.so.2"

test -x "$LOADER"
"$LOADER" --version | head -n 1

# 若目标是解决 GLIBC_2.28 等缺失，必须有兼容的 libc.so.6
test -e "$RUNTIME_DIR/libc.so.6" || echo "未发现新版 libc.so.6：仅升级 GCC/libstdc++ 不能解决 GLIBC_* 错误"
~~~

- 缺少 CXXABI_*、GLIBCXX_* 符号，通常优先检查 libstdc++.so.6；缺少 GLIBC_* 符号，需要检查 libc.so.6 等 GLIBC 组件。
- 不能只替换 ld-linux 而继续混用不匹配的 libc。新加载器、新 libc 及相关运行库应来自兼容的完整运行时。
- 老系统内核、CPU 指令集、NSS/线程库以及第三方 native 扩展也可能影响兼容性。不要直接覆盖系统 /lib64 下的库。

### 2. Node.js 直接验证

~~~bash
RUNTIME_DIR=/home/gcc-10/lib
LOADER="$RUNTIME_DIR/ld-linux-x86-64.so.2"
NODE_BIN=/home/node-v22.12.0-linux-x64/bin/node

# 查看库的实际解析路径；确认 libc、libstdc++ 等来自预期目录
"$LOADER" --library-path "$RUNTIME_DIR" --list "$NODE_BIN"

# 启动 Node.js
"$LOADER" --library-path "$RUNTIME_DIR" \
  "$NODE_BIN" --version

# 运行一段 JS
"$LOADER" --library-path "$RUNTIME_DIR" \
  "$NODE_BIN" -e 'console.log(process.version)'
~~~

### 3. Node.js 的 exec 包装脚本

创建 /home/node-compat.sh：

~~~bash
#!/usr/bin/env bash
set -e

RUNTIME_DIR=/home/gcc-10/lib
NODE_BIN=/home/node-v22.12.0-linux-x64/bin/node

exec "$RUNTIME_DIR/ld-linux-x86-64.so.2" \
  --library-path "$RUNTIME_DIR" \
  "$NODE_BIN" "$@"
~~~

~~~bash
chmod +x /home/node-compat.sh

/home/node-compat.sh --version
/home/node-compat.sh /path/to/app.js
~~~

这里的 exec 将**包装脚本的 Shell 进程**替换为动态加载器进程。它不会修改 Node 二进制文件；如果直接在交互式 Shell 中执行 exec，Node 退出后该 Shell 也会退出。

**边界**：直接启动加载器后，/proc/self/exe 可能指向 ld-linux 而不是 node。对于依赖 process.execPath、自身路径或需要重新启动 Node 的 npm 工具链，不能只凭 node --version 正常就认定兼容；还需要验证完整业务及子进程。子进程重新 exec 普通 node 二进制时，并不会自动沿用父进程指定的加载器。

## Python 3：Miniforge3 + exec 指定动态加载器

适用于独立 Conda 环境里的普通 CPython ELF，例如 Python 3.12。**Miniforge3 只负责安装 Python/包，不会自动升级操作系统 GLIBC。**

### 1. 创建或激活独立环境

~~~bash
# 假设已经安装 Miniforge3
conda activate kws

command -v python3
python3 --version
echo "$CONDA_PREFIX"
ldd --version | head -n 1
~~~

以下示例要求已激活环境，并假设当前环境安装的是 Python 3.12。若实际是其他版本，相应调整可执行文件名。

### 2. 使用新加载器测试 Python 3

~~~bash
RUNTIME_DIR=/home/gcc-10/lib
LOADER="$RUNTIME_DIR/ld-linux-x86-64.so.2"
PYTHON_BIN="$CONDA_PREFIX/bin/python3.12"
LIB_PATH="$RUNTIME_DIR:$CONDA_PREFIX/lib"

test -x "$PYTHON_BIN"
"$LOADER" --library-path "$LIB_PATH" --list "$PYTHON_BIN"

"$LOADER" --library-path "$LIB_PATH" "$PYTHON_BIN" - <<'PY'
import ctypes
import sys

libc = ctypes.CDLL(None)
libc.gnu_get_libc_version.restype = ctypes.c_char_p
print("Python:", sys.version.split()[0])
print("Runtime GLIBC:", libc.gnu_get_libc_version().decode())
print("sys.executable:", sys.executable)
PY
~~~

重点查看运行中的 GLIBC 版本，而不只是宿主机 ldd --version。测试时还应核对 --list 的 libc.so.6 路径是否符合预期。

### 3. Python 3 的 exec 包装脚本

创建 /home/python3-compat.sh：

~~~bash
#!/usr/bin/env bash
set -e

if [ -z "$CONDA_PREFIX" ]; then
  echo "请先执行 conda activate kws" >&2
  exit 1
fi

RUNTIME_DIR=/home/gcc-10/lib
PYTHON_BIN="$CONDA_PREFIX/bin/python3.12"
LIB_PATH="$RUNTIME_DIR:$CONDA_PREFIX/lib"

exec "$RUNTIME_DIR/ld-linux-x86-64.so.2" \
  --library-path "$LIB_PATH" \
  "$PYTHON_BIN" "$@"
~~~

~~~bash
chmod +x /home/python3-compat.sh

/home/python3-compat.sh --version
/home/python3-compat.sh -c 'print("hello from Python")'
/home/python3-compat.sh /path/to/train.py
~~~

### 4. 验证 pip 的 manylinux 识别与 PyTorch 安装

PyTorch 等 Linux Wheel 往往带有 manylinux_x_y_x86_64 标签。例如 manylinux_2_28_x86_64 表示要求 GLIBC 2.28 或更高。仅仅使用 Python 3.12 并不代表满足该要求。

~~~bash
# 查看当前运行方式识别到的平台标签
/home/python3-compat.sh -m pip debug --verbose |
  grep -m 1 manylinux_2_28_x86_64

# 安装示例：按平台、驱动和官方索引选择实际适用的包
/home/python3-compat.sh -m pip install \
  torch==2.10.0 \
  torchvision==0.25.0 \
  torchaudio==2.10.0

# 包安装后进行 import 与运行时验证
/home/python3-compat.sh - <<'PY'
import torch
print("torch:", torch.__version__)
print("torch CUDA runtime:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
PY
~~~

**特别注意 pip 的子进程**：pip 的 PEP 517 构建隔离、编译扩展和其他工具可能通过 sys.executable 或 shebang 再启动 Python。此时新进程通常会依照原始 Python ELF 的 PT_INTERP 使用系统加载器，无法保证继承本脚本的加载器配置。所以：

- 优先使用与架构、Python ABI 和运行时兼容的预编译 Wheel，减少本地编译。
- 检查 pip debug 的标签、torch import、CUDA 初始化和实际模型推理/训练；只看 pip install 成功并不足够。
- 若涉及复杂 native 扩展、多个进程或正式部署，优先使用具有兼容 GLIBC 的容器/系统镜像，或在隔离环境中审慎评估 PT_INTERP 修改方案。

## Node.js / Python 3 与 Postman CLI 的方案对比

| 程序 | 显式 exec ld-linux --library-path | 修改 PT_INTERP | 主要限制 |
|---|---|---|---|
| 普通 Node.js ELF | 通常可行，适合单进程验证 | 可在副本上测试 | 自定位、process.execPath 和子进程需要验证 |
| Miniforge3 / Python 3 ELF | 通常可行，适合单进程验证 | 可在独立环境内测试 | pip 构建隔离、sys.executable、扩展库及子进程 |
| pkg 打包的 Postman CLI | 不推荐，可能导致读取 payload 失败 | 推荐保留文件布局的原位替换 | /proc/self/exe 必须仍指向包含 payload 的程序文件 |

这里有两个独立的机制：

1. **exec + 指定 ld-linux**：不改 ELF，只影响本次启动；对应的 /proc/self/exe 通常是加载器。
2. **直接 exec 程序 + PT_INTERP**：由 Kernel 按 ELF 内的解释器路径启动，/proc/self/exe 通常仍是目标程序；更适合要求识别自身文件的程序，但修改 ELF 具有风险。

若用 patchelf 测试普通 ELF，也请先保留副本，并使用 patchelf --print-interpreter 和 readelf -lW 检验。不要将普通 ELF 的 patchelf 修改方式直接照搬到带追加 payload 的 pkg 单文件可执行文件。

参考：[ld.so 手册](https://man7.org/linux/man-pages/man8/ld.so.8.html)（--library-path、--list、--verify）；[Python Packaging 平台标签规范](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)（manylinux）。
