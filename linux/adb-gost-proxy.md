# Android 板子通过电脑上的 GOST 代理上网

板子连接 ADB 后，访问板子端的 `127.0.0.1:18891`，由 `adb reverse` 把流量转发到电脑上的 GOST HTTP 代理。

## 电脑端

在第一个终端启动 GOST，并保持运行。

```bash
gost -L=http://127.0.0.1:18891
```

在另一个终端用 `adb devices` 查看序列号，替换下面的 `SERIAL`，再执行端口转发、校时和登录。

```bash
adb devices
SERIAL='替换为板子的序列号'
adb -s "$SERIAL" reverse tcp:18891 tcp:18891
adb -s "$SERIAL" shell "date -u -s @$(date +%s)"
adb -s "$SERIAL" shell
```

`$(date +%s)` 由电脑端的 Shell 展开为当前 Unix 时间戳。板子需要有修改系统时间的权限才能完成校时。

## 板子端

在刚进入的 ADB Shell 中设置代理。随后从此 Shell 启动的、支持代理环境变量的程序会读取这些设置。

```sh
export http_proxy=http://127.0.0.1:18891
export https_proxy=http://127.0.0.1:18891
```

`https_proxy` 的值也用 `http://`，因为客户端通过 HTTP 代理的 CONNECT 方法访问 HTTPS 网站。

## 验证

在板子上用 `date -u` 查看校时结果。若已安装 `curl`，可测试 HTTPS，预期输出 `HTTP 200`。

```sh
date -u
curl -fsS --max-time 10 -o /dev/null -w 'HTTP %{http_code}\n' https://example.com/
```

若连不上，在电脑上用 `adb -s "$SERIAL" reverse --list` 确认端口映射，并检查 GOST 是否仍在运行。
