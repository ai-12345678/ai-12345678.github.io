# 编程语言对象与数据建模方式

主流编程语言中，可以把对象与数据的构造方式压缩为下面四类：

| 模型 | 代表语言 | 核心思路 |
| --- | --- | --- |
| 类实例化 | Java / C++ / C# / Kotlin / Python / Ruby | `Class → instance` |
| 原型委托 | JavaScript / Self / Lua（近似） | `object → prototype object` |
| 组合 | Go / Rust / Swift | `Type A + Type B → Type C` |
| 数据结构 / Value Type | C / Go / Rust / Swift / C# | 按字段定义结构，再创建值或对象 |

## 快速理解

```text
C++ / Java   → 类与继承 → 实例
JavaScript   → 对象 → 原型对象
Go / Rust    → struct + 组合 + interface / trait
C / Rust 等  → struct / record / value
```

这四类不是互斥分类。一门语言通常同时支持多种机制，例如 C++ 同时支持 class、继承、组合和 struct；Go 同时使用 struct、组合和 interface；Rust 同时使用 struct、组合和 trait。

其中 `trait / mixin` 更适合看作“组合行为”的机制，`record / ADT` 更适合看作“数据建模”的扩展，而 Python / Ruby 的动态 class 仍属于类实例化模型。
