# macOS ADB Shell 方向键与 Tab 补全失效：TTY Raw 模式修复

> 适用场景：macOS（iTerm2 / Terminal.app）、Zsh，`adb devices` 已正常识别 Android 设备，但进入 `adb shell` 后方向键、历史命令与 Tab 补全异常。本文记录一次实际定位并修复的方法。**该方案解决的是终端交互链路问题，不适用于所有 ADB 连接故障。**

## 1. 故障表现

在 macOS 终端中执行：

```bash
adb shell
# 或
adb shell -tt bash -i
```

可能出现：

- 按方向键时，屏幕出现 `^[[D`（左键）、`^[[C`（右键））、`^[[A`（上键））等转义序列。
- Tab 无法按预期补全，历史命令无法用上下方向键浏览。
- 输入可能出现重复回显、需要按 Enter 才能传到远端等现象。
- `adb devices -l` 显示设备为 `device`，说明连接正常，但**不代表交互式终端配置正常**。

这些现象需要区分：本地 TTY 输入模式、ADB 是否请求远端 PTY，以及远端 Shell 的行编辑能力都可能影响结果。

## 2. 直接可用的修复函数（推荐）

把以下函数放进 Mac 的 `~/.zshrc`：

```zsh
# 使用本地 TTY raw 模式，转发按键到 Android 交互式 Bash
adb_() (
    local saved_tty

    saved_tty=$(stty -g </dev/tty) || return 1
    trap 'stty "$saved_tty" </dev/tty' EXIT

    stty raw -echo </dev/tty || return 1
    adb "$@" shell -tt bash -i
)
```

重新加载配置并连接：

```zsh
source ~/.zshrc
adb_
```

如果有多台设备，可沿用 ADB 的 `-s` 参数：

```zsh
adb_ -s YOUR_DEVICE_SERIAL
```

**注意：普通 Android 系统未必内置 Bash。** 若提示 `bash: not found`、`No such file or directory` 或无法启动 Bash，请把函数最后一行改成：

```zsh
adb "$@" shell -tt sh -i
```

其中 `sh` 的历史命令、Tab 补全等能力依赖设备内置的 Shell；即使 TTY 已正确传输，也不保证与 Bash 的 Readline 完全一致。

### 2.1 临时使用，无需修改配置

```zsh
(
    saved_tty=$(stty -g </dev/tty) || exit 1
    trap 'stty "$saved_tty" </dev/tty' EXIT

    stty raw -echo </dev/tty || exit 1
    adb shell -tt bash -i
)
```

如果设备没有 Bash，同样将最后一行改成 `adb shell -tt sh -i`。

### 2.2 为什么不要只写下面的函数

```zsh
adb_() {
    saved_tty=$(stty -g)
    trap 'stty "$saved_tty"' EXIT
    stty raw -echo
    # adb shell -tt bash -i
}
```

这段代码存在两处问题：

1. `adb shell` 被注释，实际上没有启动远端交互式 Shell。
2. `trap EXIT` 写在普通函数体内，其触发时机、作用域与 Shell 的具体语义有关；如果恢复逻辑未按预期运行，本地终端可能留在 `raw -echo` 模式。

改用 `adb_() ( ... )` 相当于给函数体显式创建子 Shell，`EXIT` trap 随子 Shell 结束而执行，能够明确限定清理动作的生命周期。不要依赖某个 Shell 对普通函数内 `EXIT` trap 的特殊处理。

### 2.3 使用 Wi-Fi 无线调试

Android 11 及以上支持通过配对码建立无线 ADB 连接。先让 Mac 和 Android 手机连到同一个 Wi-Fi，并在 Mac 上使用新版 Android SDK Platform-Tools。

1. 在手机上打开 **设置 → 开发者选项 → 无线调试**，选择 **使用配对码配对设备**。保持弹窗打开，使用弹窗显示的 IP 地址和端口运行 `adb pair`，然后输入手机显示的 6 位配对码。

   ```bash
   adb pair 192.168.1.50:37123
   adb devices -l
   ```

2. 配对成功后，如果 `adb devices -l` 已显示无线设备且状态为 `device`，即可使用。如果没有自动连上，返回手机的**无线调试主页面**，用该页面显示的「IP 地址和端口」手动连接。

   ```bash
   adb connect 192.168.1.50:41867
   adb devices -l
   ```

   上面的地址是示例。配对弹窗提供 `adb pair` 所需的端口，无线调试主页面提供 `adb connect` 所需的端口。如果手动连接超时，请确认手机和 Mac 仍在同一 Wi-Fi，且网络允许设备之间直接通信。

3. 连接后，从 `adb devices -l` 的输出中复制无线设备的序列号，传给本文的 `adb_` 函数。下面用手动连接后常见的 `IP:端口` 格式举例。

   ```zsh
   adb_ -s 192.168.1.50:41867
   ```

   如果手机没有 Bash，按上文将函数最后一行改为使用 `sh -i`。连接地址或端口变化后，重新查看无线调试主页面。

Android 10 及以下需先用 USB 建立连接。在手机上开启并授权 USB 调试，确认设备状态为 `device`，然后执行 `adb -d tcpip 5555`（仅连接一台 USB 设备时）。拔掉数据线后，用 `adb connect 手机IP:5555` 连接，再用 `adb devices -l` 确认。

具体要求见 [Android 官方无线 ADB 文档](https://developer.android.com/tools/adb#connect-to-a-device-over-wi-fi)。

## 3. 原理：为什么 Raw 模式有效

输入链路可以简化为：

```text
方向键 / Tab
    │  iTerm2 将按键编码为字节（例如左键 ESC [ D）
    ▼
macOS 本地 PTY / TTY（termios）
    │  cooked/canonical 模式可能按行缓冲、回显或处理控制字符
    ▼
adb 客户端
    │  USB / TCP 连接
    ▼
Android adbd
    │  adb shell -tt 请求远端 PTY
    ▼
Android 远端 PTY / TTY
    ▼
bash -i / sh -i
    │  远端 Shell 的行编辑器解释方向键、Tab
    ▼
远端执行与回显
```

终端模拟器负责将方向键编码为 `ESC [ D` 等字节；**不负责替 Bash 补全命令**。真正处理历史记录、光标移动、Tab 补全的是运行在远端的交互式 Shell（例如 Bash 的 Readline）。

关键配置分别是：

| 配置 | 作用 | 可能造成的现象 |
| --- | --- | --- |
| `stty raw` | 将本地终端切换为更接近逐字节透传的模式，关闭规范模式下的按行缓冲等处理 | 远端可更及时收到方向键、Tab、控制字符 |
| `stty -echo` | 关闭本地 TTY 的输入回显 | 避免本地先显示一遍、远端再显示一遍 |
| `adb shell -tt` | 强制请求远端 PTY | 远端交互式 Shell 获得 TTY 语义 |
| `bash -i` | 启动交互式 Bash | Bash / Readline 可以处理补全和历史命令 |
| `trap ... EXIT` | 结束时恢复原始 TTY 设置 | 避免退出 ADB 后本地终端失去正常输入状态 |
| `( ... )` | 在子 Shell 中限定状态与 trap 的作用域 | 不把清理逻辑留在父 Shell |

因此，**这不是“方向键在本地被显示一次、远端又显示一次”的必然结论**。是否重复回显，要结合本地 TTY 的 `echo` 标志、远端 TTY 的 `echo` 标志以及实际回显链路来确认。

> `stty raw` 同时改变本地 TTY 对某些控制字符和信号的处理方式。进入远端会话后，Ctrl+C 等按键是否能中断远端程序，还取决于 ADB 转发与远端 TTY 的配置。通常使用 `exit` 正常退出更易验证清理流程。

## 4. 为什么要用子 Shell 和 EXIT trap

推荐写法：

```zsh
adb_() (
    local saved_tty
    saved_tty=$(stty -g </dev/tty) || return 1
    trap 'stty "$saved_tty" </dev/tty' EXIT
    stty raw -echo </dev/tty || return 1
    adb "$@" shell -tt bash -i
)
```

执行顺序：

1. `stty -g` 保存本地终端原始 termios 设置。
2. 安装 `EXIT` trap，确保走正常 Shell 退出路径时执行恢复。
3. `stty raw -echo` 切换本地输入模式，避免规范模式阻碍逐字节交互。
4. `adb ... shell -tt bash -i` 启动远端 PTY 与交互式 Shell。
5. 输入 `exit` 退出 Android Shell，ADB 随之结束。
6. 子 Shell 结束，trap 执行 `stty "$saved_tty"`，恢复原来的本地终端状态。

`adb_() ( ... )` 与下面这种写法在这个目的上等价：

```zsh
adb_() {
    (
        # 保存 TTY、配置 trap、切换 raw、运行 adb
    )
}
```

这里的子 Shell 隔离的是 Shell 的变量与 trap 作用域；**`stty` 修改的是同一个终端设备的内核状态，不会因为创建子 Shell 就自动撤销**，所以恢复 TTY 的 trap 仍然必不可少。

## 5. 故障排查与验证

### 5.1 先区分“设备连接失败”和“TTY 交互失败”

```bash
type -a adb
adb version
adb devices -l
```

| 输出 | 解释与建议 |
| --- | --- |
| `device` | 设备已连接，继续检查交互式 Shell 与 TTY |
| `unauthorized` | 在手机上确认 USB 调试授权 |
| `offline` | 重启 ADB 服务或重新连接 USB |
| 列表为空 | 检查数据线、USB 模式、调试开关、端口 |
| `device` 但方向键显示 `^[[D` | 优先按本文检查本地 TTY、远端 PTY、Shell 行编辑能力 |

连接异常可尝试：

```bash
adb kill-server
adb start-server
adb devices -l
```

### 5.2 验证远端是否存在 Bash

```bash
adb shell 'command -v bash; echo "default_shell=$0"'
```

若 `command -v bash` 没有返回可执行文件路径，可以改用 `sh -i`；不要把“Bash 不存在”误判为 TTY 故障。

### 5.3 检查本地与远端 TTY

在本地 Zsh 中：

```bash
echo "$TERM"
stty -a </dev/tty
```

在 Android 交互式 Shell 中：

```bash
echo "$0"
echo "$-"
stty -a
stty size
```

排查要点：

- 交互式 Shell 通常会在 `$-` 中包含 `i`；实际行为依 Shell 而异。
- 远端 `stty size` 如果返回 `0 0`，表示窗口尺寸没有正确传播，可能影响全屏程序和行编辑显示；但**不一定是方向键/Tab 异常的根因**。
- 如果 Raw 模式后仍输出 `^[[A` 等序列，检查远端是否真的运行交互式 Bash、Shell 是否具备对应的行编辑与补全能力，以及 `TERM` 是否与终端兼容。

### 5.4 建议的实际验证步骤

1. 在本地执行 `stty -g </dev/tty`，记下原始终端模式。
2. 执行 `adb_` 并进入 Android Shell。
3. 输入两条命令，按上方向键检查是否能召回上一条。
4. 输入一个可补全的命令前缀，按 Tab 测试。
5. 输入 `exit` 返回 macOS，再运行 `stty -a </dev/tty` 检查本地输入是否恢复正常。

> 本文函数基于实际问题中采用的 `raw -echo + adb shell -tt bash -i` 修复思路整理；不同 Android ROM、ADB 版本与远端 Shell 可能需要单独验证，不能承诺所有设备表现完全一致。

## 6. 紧急恢复本地终端

若执行 `stty raw -echo` 后直接退出、终端不回显，优先尝试在**同一个终端窗口**输入以下命令（即使看不见输入，也可尝试键入）：

```bash
stty sane </dev/tty
reset
```

如果仍无效，打开另一个终端窗口重新连接，或直接关闭受影响窗口、重新打开终端。今后统一通过包含 `EXIT` trap 的函数进入 Raw 模式，降低遗留问题的概率。

## 7. 可复用结论

- 先用 `adb devices -l` 排除设备连接问题，再诊断交互式 TTY。
- 对“设备在线，但远端 Bash 收不到逐字节按键”的场景，可尝试 **本地 `stty raw -echo` + 远端 `adb shell -tt`**。
- 通过 `adb_() ( ... )` 和 `trap ... EXIT` 在退出时恢复本地终端状态。
- 远端系统不保证自带 Bash，必要时改成 `sh -i`；Shell 不支持补全时，Raw 模式不能凭空增加补全功能。

## 相关阅读

- [终端模拟器与 PTY 的边界](./terminal-emulator-pty-boundary.html)
- [Herdr 与 PTY 原理](./herdr-pty.html)
- [Android Debug Bridge（官方文档）](https://developer.android.com/tools/adb)
- [Bash Readline 交互原理（GNU）](https://www.gnu.org/software/bash/manual/html_node/Readline-Interaction.html)
