# GoYacc：词法分析、语法分析与 AST 的工作原理

> 以 Go 的 `mini-express` 布尔表达式解析器为例，理解 Nex、GoYacc、Lexer、Parser、语义值和 AST 的关系。

## 1. 先建立整体认识

**GoYacc 是语法解析器生成器，不是表达式的执行器。**

开发阶段，GoYacc 将 `grammar.y` 中的文法规则转换为 Go 解析器代码，并把规则中 `{ ... }` 的 Go 语义动作嵌入生成的 `parser.go`。生成代码时不会执行这些动作；程序运行期间，解析器按照规则进行归约（Reduce）时才执行对应动作。

```text
开发阶段

lexer.nex ── nex ──────> lexer.nn.go（词法分析代码）
grammar.y ── goyacc ───> parser.go（解析状态机、解析表和语义动作）

运行阶段

表达式字符串
    │
    ▼
Lexer.Lex()：识别 Token
    │
    ▼
Parser：移进（Shift）/归约（Reduce）
    │
    └── 归约时执行 grammar.y 的 Go 语义动作
              │
              ▼
       AST 根节点，或直接计算得到的值
              │
              ▼（如果得到 AST）
         root.Eval() 求值
```

这里的 Token 并不一定先一次性生成完整列表：在常见的 GoYacc 实现中，`yyParse()` 会在解析过程中按需调用 `Lex()` 获取 Token。

## 2. Lexer 与 Parser 如何连接

GoYacc 生成的解析器要求词法分析器满足 `yyLexer` 接口：

```go
type yyLexer interface {
    Lex(*yySymType) int
    Error(string)
}
```

- `Lex()`：返回一个 Token 的类型，并通过 `*yySymType` 传递其语义值，例如标识符的名称。
- `Error()`：供解析器报告语法错误。

解析入口通常是：

```go
func yyParse(yylex yyLexer) int
```

**`yylex` 是生成代码中的参数名，类型是 `yyLexer` 接口，不是 Go 内置变量，也不是指针类型参数。**

实际传入的对象通常是 `*Lexer`，例如：

```go
lexer := &Lexer{input: expression}
status := yyParse(lexer)
```

Go 的接口参数按值传递，但是该接口值保存着指向原始 `Lexer` 对象的指针，所以在解析器内部通过类型断言取得 `*Lexer` 后，可以修改同一个对象的字段。

```text
yyParse(lexer)
           │
           ▼
yylex（yyLexer 接口值）
           │
           └── 动态类型：*Lexer
                     │
                     ▼
               原来的 Lexer 实例
```

> **注意：**传入值不被强制要求是指针，只需实现 `yyLexer` 接口。但为了保存词法分析的可变状态和解析结果，实际项目中通常使用指针。

## 3. `{ ... }`、`$$`、`$1` 究竟是什么

例如：

```yacc
expr:
    expr AND expr {
        $$ = AndExpr{
            left:  $1,
            right: $3,
        }
    }
;
```

这条规则表示：把 `expr AND expr` 归约为一个 `expr`，同时构建 `AndExpr` 节点。

| 记号 | 含义 |
|---|---|
| `$1` | 产生式右侧第 1 个符号的语义值，此处为左子表达式 |
| `$2` | 产生式右侧第 2 个符号的语义值，此处对应 `AND`，本例未使用 |
| `$3` | 产生式右侧第 3 个符号的语义值，此处为右子表达式 |
| `$$` | 当前产生式左侧非终结符的语义值，也就是本次归约的输出 |
| `{ ... }` | 归约到这条规则时要执行的 Go 语义动作 |

生成的 `parser.go` 中会包含等效于如下伪代码的逻辑（**仅为概念示意，不代表生成文件的精确结构**）：

```go
// 当前规则归约时执行
current.expr = AndExpr{
    left:  rhs[1].expr,
    right: rhs[3].expr,
}
```

**`$$` 不是固定的 AST，也不是固定的计算结果。** 它的实际类型由 `%union`、`%type` 等声明决定。例如：

```yacc
%union {
    expr Expr
    name string
}

%token <name> IDENT
%type <expr> expr
```

这表明 `IDENT` 携带 `string` 语义值，而 `expr` 携带 `Expr` 语义值。

## 4. 子规则的 `$$` 如何传给上层规则的 `$1`

```yacc
input:
    expr {
        yylex.(*Lexer).root = $1
    }
;

expr:
    IDENT '(' ')' {
        $$ = CallExpr{name: $1}
    }
  | expr AND expr {
        $$ = AndExpr{left: $1, right: $3}
    }
;
```

以 `func1() && func2()` 为例：

```text
func1() ──归约──> expr
                     $$ = CallExpr{name: "func1"}

func2() ──归约──> expr
                     $$ = CallExpr{name: "func2"}

expr AND expr ──归约──> expr
                           $$ = AndExpr{
                               left:  CallExpr{name: "func1"},
                               right: CallExpr{name: "func2"},
                           }

input: expr
       └── $1 = 上一步得到的 AndExpr
                   │
                   ▼
              lexer.root = $1
```

**本质：子规则的 `$$`，在上层规则中会成为对应位置的 `$1`、`$2`、`$3` 等语义值。** 这些编号是相对于每条产生式独立定义的。

## 5. 为什么通常通过 `lexer.root` 取得结果

`yyParse()` 返回的是解析状态码，不是 AST 根节点：

```go
func yyParse(yylex yyLexer) int
```

如果希望从外部取得 AST，可以自行在 Lexer 对象中定义 `root` 字段，并在起始规则的语义动作中显式赋值：

```go
type Lexer struct {
    input string
    root  Expr
    err   error
}
```

```yacc
input:
    expr { yylex.(*Lexer).root = $1 }
;
```

典型调用过程：

```go
// 1. 为此次解析创建独立实例
lexer := &Lexer{input: expression}

// 2. 解析并执行 grammar.y 中的归约动作
status := yyParse(lexer)

// 3. 检查状态、错误和解析结果
if status != 0 || lexer.err != nil || lexer.root == nil {
    // 返回解析错误；实际项目应保留 lexer.err 的详细信息
}

// 4. 获取 AST 根节点
root := lexer.root

// 5. 针对业务上下文执行 AST
result, err := root.Eval(ctx, funcs)
```

这里有三个重要结论：

1. `yyParse()` **不会自动**向 `lexer.root` 写入结果。写入行为来自 `grammar.y` 中的自定义语义动作。
2. 每个解析任务创建一个独立的 Lexer/Parser 上下文，便于状态隔离；但这是一种设计选择，而非 GoYacc 的强制规定。
3. 相较于将结果放入包级全局变量，保存在单次解析使用的对象中更适合并发场景；当然，并发访问同一个可变 Lexer 实例仍需避免或同步。

### Nex 分支中的实际类型

如果词法分析器由 Nex 自动生成，项目可能另有包装类型：

```go
type ParserLexer struct {
    *Lexer // Nex 生成的 Lexer
    root Expr
    err  error
}
```

则对应语义动作应写为：

```yacc
input:
    expr { yylex.(*ParserLexer).root = $1 }
;
```

此时保存结果的是 `ParserLexer.root`，而不是 Nex 生成的 `Lexer` 自身的字段。整体原理完全一样。

## 6. Yacc 不一定需要构建 AST

Yacc 的语义动作可以构建数据结构，也可以**直接计算结果**。

### 方案 A：构建 AST

```yacc
expr:
    expr AND expr {
        $$ = AndExpr{left: $1, right: $3}
    }
;
```

此时 `$$` 是 `Expr`，解析完成后可以复用 AST，针对不同的 Context 求值。

### 方案 B：直接计算一个整数

```yacc
%union {
    num int
}

%token <num> NUMBER
%type <num> expr

%%

input:
    expr { yylex.(*Lexer).result = $1 }
;

expr:
    NUMBER         { $$ = $1 }
  | expr '+' expr  { $$ = $1 + $3 }
;
```

此时 `Lexer` 需要有整数结果字段，例如 `result int`。输入 `10 + 20 + 30`，最终 `result` 是 `60`，不需要构建 AST。

> 上面为语义值示例。实际计算器还应设置运算符的结合性和优先级（如 `%left '+'`），并由 Lexer 正确填充 `NUMBER` 的整数语义值。

| 比较项 | 直接计算 | 构建 AST |
|---|---|---|
| `$$` 保存 | `int`、`bool` 等 | `Expr` 等节点 |
| 最终结果 | 计算值 | AST 根节点 |
| 运算发生在 | 解析归约时 | 后续 `Eval()` 时 |
| 重复执行同一表达式 | 通常需要重新解析 | 可以复用 AST |
| 常见场景 | 简单计算器 | 规则引擎、表达式引擎、编译器 |

## 7. 为什么使用 Go Interface 构建 AST

定义统一的节点接口：

```go
type Expr interface {
    Eval(*Context, FuncMap) (bool, error)
}
```

不同节点具有不同的具体结构：

```go
type CallExpr struct {
    name string
}

type AndExpr struct {
    left  Expr
    right Expr
}

type OrExpr struct {
    left  Expr
    right Expr
}

type NotExpr struct {
    inner Expr
}
```

只要它们均实现 `Eval()`，就可以作为 `Expr` 使用：

```text
func1() && (func2() || func3())

             AndExpr
            /       \
       CallExpr     OrExpr
        func1      /      \
              CallExpr  CallExpr
               func2     func3
```

从根节点调用：

```go
result, err := root.Eval(ctx, funcs)
```

Go 根据接口持有的具体类型执行相应的 `Eval()`；节点内部再递归调用子节点的 `Eval()`，可以实现 `&&` 和 `||` 的短路求值。

这种由多种具体节点类型组成的树，可以称为**异构 AST（Heterogeneous AST）**。`Expr` 是接口类型，不等价于“指向根节点的指针”：它既可以保存结构体值，也可以保存结构体指针。

## 8. AST 递归结构是否一定需要指针

**不要求所有节点使用显式指针，但必须避免无限大小的直接递归值。**

例如，下列定义非法：

```go
// 非法：Node 的大小会无限递归
type Node struct {
    child Node
}
```

可以使用指针或接口等间接表示：

```go
type Node struct {
    child *Node
}
```

```go
type AndExpr struct {
    left  Expr
    right Expr
}
```

也可以通过切片承载子节点：

```go
type Node struct {
    children []Node
}
```

而下面直接存储具体的 `CallExpr` 值是合法的，因为接口字段是固定大小的：

```go
root := AndExpr{
    left:  CallExpr{name: "func1"},
    right: CallExpr{name: "func2"},
}
```

## 9. 最后总结

| 组件或概念 | 作用 |
|---|---|
| Nex | 根据 `.nex` 生成 Go 词法分析器 |
| GoYacc | 根据 `.y` 生成 Go 语法解析器 |
| `Lex()` | 识别下一个 Token 及其语义值 |
| `yyParse()` | 驱动解析状态机，返回解析状态码 |
| `{ ... }` | 在规则归约时执行 Go 语义动作 |
| `$1` / `$2` / `$3` | 当前规则右侧各符号的语义值 |
| `$$` | 当前规则左侧非终结符的语义值 |
| `lexer.root` | 按项目约定保存 AST 根节点（非内置机制） |
| `Expr` 接口 | 抽象不同的 AST 节点类型 |
| `root.Eval()` | 从根节点递归执行整棵 AST |

**一句话：GoYacc 生成解析器，Lexer 识别 Token，Parser 根据语法规则归约，语义动作产生 AST 或直接结果；如果生成的是 AST，则可通过 Go Interface 和递归 `Eval()` 完成表达式执行。**