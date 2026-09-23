# 终端模拟器与 PTY 的边界

## 1. 整体关系

```text
键盘 / 屏幕
    │
    ▼
Terminal Emulator
    │
    │ 字节流
    ▼
PTY master
    ║
PTY slave
    │
    ▼
shell / vim / claude / codex
```

> **终端模拟器负责“显示和键盘编码”，PTY/TTY 负责“字节传输和 Unix 终端语义”。**

## 2. 终端模拟器负责什么

- 显示文字、颜色、光标和清屏
- 解析 ANSI / VT 控制序列
- 保存 screen / scrollback
- 把键盘操作编码成字节

例如：

```text
Ctrl+C   → 0x03
↑        → ESC [ A
```

程序输出：

```text
\x1b[31mhello\x1b[0m
```

终端模拟器会把它显示成红色的 `hello`。

## 3. PTY / TTY 负责什么

PTY 是内核提供的伪终端：

```text
PTY master  <====>  PTY slave
```

主要负责：

- 字节传输
- canonical / raw mode
- echo
- window size
- foreground process group
- job control
- 控制字符与信号处理

应用通常连接 PTY slave：

```text
stdin  ─┐
stdout ─┼── PTY slave
stderr ─┘
```

终端程序、tmux、Herdr Server 等通常持有 PTY master。

## 4. 两个典型例子

### 输出颜色

```text
应用
  ↓
"\x1b[31mhello"
  ↓
PTY：只传字节
  ↓
Terminal Emulator：解析 ANSI
  ↓
显示红色 hello
```

### Ctrl+C

```text
用户按 Ctrl+C
      ↓
Terminal Emulator：生成 0x03
      ↓
PTY / TTY：转换为 SIGINT
      ↓
foreground process group
```

## 5. Scrollback 属于谁

Scrollback **不属于 PTY**。

PTY 只负责实时传输字节；终端模拟器或 tmux / Herdr 这类服务端负责维护：

```text
screen + scrollback
```

## 6. Herdr 中的关系

```text
本地 Terminal
      │
Herdr Client
      │
    socket
      │
Herdr Server
      │
screen + scrollback
      │
   PTY master
      ║
   PTY slave
      │
shell / claude / codex
```

Client 退出后，Server、PTY、shell、Claude/Codex 仍然可以继续运行。

重新执行 `herdr --session xxx` 时，本质上是：

```text
新 Client
   ↓
重新 attach 到原 Server
   ↓
恢复 screen / scrollback 显示
   ↓
继续使用原来的 PTY 和进程
```

## 7. 一句话总结

```text
Terminal Emulator
= 显示 + ANSI解析 + 键盘编码 + scrollback

PTY / TTY
= 字节传输 + termios + job control + signal

Herdr Server
= PTY owner + terminal state + session/pane 管理
```

> **终端模拟器决定“终端长什么样”，PTY/TTY 决定“终端字节如何传输以及 Unix 终端控制语义如何工作”。**
