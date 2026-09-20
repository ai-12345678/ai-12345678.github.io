# 技术文档

这里集中整理 Kubernetes、Linux 与基础设施相关的学习笔记。所有页面均以 Markdown 维护，并由 MkDocs 统一生成网站。

## Kubernetes

- [Kubernetes Context 简介](kubernetes/context.md)：理解集群、身份与默认命名空间的组合。
- [Kubernetes 扩展体系](kubernetes/extensions.md)：梳理控制面、调度器与节点侧扩展接口。
- [Deployment 创建时序](kubernetes/deployment-create-sequence.md)：从 `kubectl apply` 到 ReplicaSet 创建。
- [Pod 创建与调度时序](kubernetes/pod-create-scheduling-sequence.md)：从 Pod 创建到 kubelet 启动工作负载。

## Linux

- [SSH ProxyCommand + Auth 访问架构](linux/ssh-proxycommand-auth-architecture.md)
- [下载文件为什么有时需要 chmod +x](linux/chmod-x-download-permissions.md)
- [Herdr 使用笔记](linux/herdr-usage.md)
- [Postman CLI 旧 Linux 兼容方案](linux/postman-cli-old-linux-compatibility.md)

