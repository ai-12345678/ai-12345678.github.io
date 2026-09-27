# 编程语言对象与数据建模方式

主流编程语言中，可以把对象与数据的构造方式压缩为下面四类：

| 模型 | 代表语言 | 核心思路 |
| --- | --- | --- |
| 类实例化 | Java / C++ / C# / Kotlin / Python / Ruby | `Class → instance` |
| 原型委托 | JavaScript / Self / Lua（近似） | `object → prototype object` |
| 组合 | Go / Rust / Swift | `Type A + Type B → Type C` |
| 数据结构 / Value Type | C / Go / Rust / Swift / C# | 按字段定义结构，再创建值或对象 |

## 原型委托

原型对象可以看成当前对象的“父对象、祖先对象”，但这种父子关系本质上不是类继承，而是属性查找时的委托关系。子对象以某个已有对象作为自己的原型；当自身找不到某个属性时，就沿着原型链继续向上查找。

例如：

```javascript
const parent = {
  x: 1
};

const child = Object.create(parent);

console.log(child.x); // 1
```

可以理解为：

```text
child
  ↓ [[Prototype]]
parent
  ↓ [[Prototype]]
Object.prototype
  ↓
null
```

`child` 自身没有 `x`，因此访问 `child.x` 时会沿原型链委托给 `parent` 查找。

## 快速理解

```text
C++ / Java   → 类与继承 → 实例
JavaScript   → 对象 → 原型对象
Go / Rust    → struct + 组合 + interface / trait
C / Rust 等  → struct / record / value
```

这四类不是互斥分类。一门语言通常同时支持多种机制，例如 C++ 同时支持 class、继承、组合和 struct；Go 同时使用 struct、组合和 interface；Rust 同时使用 struct、组合和 trait。

其中 `trait / mixin` 更适合看作“组合行为”的机制，`record / ADT` 更适合看作“数据建模”的扩展，而 Python / Ruby 的动态 class 仍属于类实例化模型。
