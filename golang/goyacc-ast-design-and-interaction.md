# GoYacc 与 AST：设计与交互流程

**核心认知：先设计语言语法和 AST 结构，再用 Yacc 生成 Parser，最后由 Go 执行 AST。**

| 层次 | 关注点 | 由谁负责 |
| --- | --- | --- |
| Grammar（语法） | 什么输入合法：函数调用、&&、\|\|、!、括号 | 开发者在 .y 中定义 |
| AST（数据模型） | 合法表达式转换成什么节点、如何连接 | 开发者用 Go interface / struct 定义 |
| Parser（识别） | 按 LR 分析表读取 Token、移进、归约 | goyacc 自动生成 |
| Eval（执行） | 调用业务函数、短路求值、返回结果 | 开发者实现 |

## 01 先确定表达式语言（Grammar）

示例输入：funcA() && (funcB() || !funcC())。其核心语法只需定义函数调用、与、或、非、括号。

~~~yacc
expr:
      IDENT '(' ')'     { $$ = CallExpr{name: $1} }
    | expr AND expr    { $$ = AndExpr{left: $1, right: $3} }
    | expr OR expr     { $$ = OrExpr{left: $1, right: $3} }
    | '!' expr         { $$ = NotExpr{inner: $2} }
    | '(' expr ')'     { $$ = $2 }
    ;
~~~

这里每个 { ... } 只属于前面的那条产生式。语义动作既可以创建节点，也可以直接透传已有节点（如括号规则）。

## 02 设计 AST：统一接口 + 不同节点类型

~~~go
type Expr interface { Eval(*Context, FuncMap) (bool, error) }
type CallExpr struct { name string }
type AndExpr struct { left, right Expr }
type OrExpr  struct { left, right Expr }
type NotExpr struct { inner Expr }
~~~

left/right 是接口字段，可持有 CallExpr、AndExpr 等具体节点的值或指针，前提是该具体类型实现了 Expr。AST 不要求所有节点都是二叉节点。

## 03 语法与 AST 的映射关系

| 归约规则 | AST 结果 |
| --- | --- |
| IDENT ( ) | CallExpr(funcA) |
| expr AND expr | AndExpr{left: 子树1, right: 子树2} |
| expr OR expr | OrExpr{left: 子树1, right: 子树2} |
| ! expr | NotExpr{inner: 子树} |
| ( expr ) | 直接返回括号中的子树，不必新建节点 |

## 04 生成与运行：谁调用谁？

开发时：expr.y → goyacc → parser.go（LR 状态表 + 语义动作）。运行时：

~~~text
main → yyParse(lexer) → lexer.Lex() → Token
     → Shift / Reduce → 执行 .y 中的 Go 语义动作
     → 得到 Expr 根节点 → root.Eval(ctx, funcs)
~~~

特别注意：是 yyParse 主动调用 Lex()；Yacc 不会在运行时再次读取 .y 文件，也不负责自动编写 AST 的 Go 结构体。

## 05 必须掌握的接口、结构和语义值

| 对象 / 声明 | 核心作用 |
| --- | --- |
| yyLexer：Lex(*yySymType) int；Error(string) | 必须由自定义 Lexer 实现；Lex 每次返回一个 Token |
| yyParse(yylex yyLexer) int | goyacc 生成；返回解析状态码（0 表示成功） |
| %union、%token、%type | 规定语义值字段、Token、非终结符使用的字段 |
| `$1`、`$2`、`$3`、`$$` | 分别是产生式右侧语义值、当前归约结果 |
| top: expr | 常用于将最终 expr 保存为根节点或计算结果 |

~~~yacc
// .y 中的起始规则（假设 %type <node> expr）
top: expr { yylex.(*Lexer).root = $1 } ;
~~~

~~~go
// 自己实现的 Lexer 上保存结果
type Lexer struct { root Expr /* scanner、err 等 */ }

lexer := &Lexer{/* 初始化扫描器 */}
if yyParse(lexer) != 0 { /* 处理错误 */ }
root := lexer.root
result, err := root.Eval(ctx, funcs)
~~~

## 06 工程实践：三个最重要的边界

- **解析 ≠ 执行**：yyParse 归约时通常只建树；root.Eval() 才递归调用业务函数，并正确实现 && / || 短路。
- **语法合法 ≠ 业务合法**：函数存在性、参数类型、返回类型等需要单独进行语义检查。
- **解析结果因场景而异**：规则引擎保存 Expr 根节点；简单计算器也可在归约时直接计算 int。

**一句话总结：Grammar 定合法性，AST 定结构，Yacc 定归约时机，Go 语义动作负责建树，Eval 负责执行。**
