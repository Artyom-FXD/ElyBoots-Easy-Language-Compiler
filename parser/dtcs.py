from dataclasses import dataclass, field
from typing import List, Optional, Any

# --- Выражения ---
@dataclass
class Expression:
    line: int
    col: int

@dataclass
class Identifier(Expression):
    name: str

@dataclass
class Literal(Expression):
    value: Any

@dataclass
class BinaryOp(Expression):
    left: Expression
    operator: str
    right: Expression

@dataclass
class UnaryOp(Expression):
    operator: str
    operand: Expression

@dataclass
class Call(Expression):
    callee: Expression
    arguments: List[Expression]

@dataclass
class MemberAccess(Expression):
    object: Expression
    member: str

@dataclass
class Assignment(Expression):
    target: Expression   # должно быть l-value
    value: Expression

@dataclass
class TagAnnotation(Expression):
    """Тег вида @name[args] — может стоять перед выражением или объявлением."""
    name: str
    arguments: List[Expression]   # выражения внутри скобок

@dataclass
class Conditional(Expression):
    condition: Expression
    then_expr: Expression
    else_expr: Expression

# --- Инструкции ---
@dataclass
class Statement:
    line: int
    col: int

@dataclass
class ExpressionStatement(Statement):
    expression: Expression

@dataclass
class VariableDeclaration(Statement):
    modifier: Optional[str]          # 'public' / None
    type: str
    name: str
    initializer: Optional[Expression]
    tag: Optional[TagAnnotation] = None   # если перед объявлением стоит тег (например, @opMem)

@dataclass
class Parameter:
    type: str
    name: str

@dataclass
class MethodDeclaration(Statement):
    return_type: Optional[str]
    name: str
    parameters: List[Parameter]
    body: List[Statement]
    return_memory: Optional[str] = None
    modifier: Optional[str] = None
    type_params: List[str] = field(default_factory=list)   # добавлено

@dataclass
class ClassDeclaration(Statement):
    name: str
    extends: Optional[str]
    methods: List[MethodDeclaration]
    type_params: List[str] = field(default_factory=list)   # добавлено

@dataclass
class IfStatement(Statement):
    condition: Expression
    then_body: List[Statement]
    else_body: Optional[List[Statement]]

@dataclass
class WhileLoop(Statement):
    condition: Expression
    body: List[Statement]

@dataclass
class ForLoop(Statement):
    """for (init; condition; update) body"""
    init: Optional[Statement]        # может быть объявление переменной или выражение
    condition: Optional[Expression]
    update: Optional[Expression]
    body: List[Statement]

@dataclass
class ForEachLoop(Statement):
    """for (item of iterable) body  (JS-стиль)"""
    item_decl: Statement             # обычно VariableDeclaration (let item) или просто Identifier
    iterable: Expression
    body: List[Statement]

@dataclass
class MatchStatement(Statement):
    expression: Expression
    cases: List['Case']
    default_body: Optional[List[Statement]]

@dataclass
class Case:
    value: Expression
    body: List[Statement]
    line: int = 0
    col: int = 0

@dataclass
class AsafeBlock(Statement):
    body: List[Statement]
    except_handler: Optional['ExceptHandler']

@dataclass
class ExceptHandler:
    exception_type: str
    parameter: Optional[str]
    body: List[Statement]

@dataclass
class GivebackStatement(Statement):
    value: Optional[Expression]

@dataclass
class ReturnStatement(Statement):
    value: Optional[Expression]

@dataclass
class CollapseStatement(Statement):
    name: str

@dataclass
class BreakStatement(Statement):
    pass

@dataclass
class UsingDirective(Statement):
    module: str

@dataclass
class OpMemDirective(Statement):
    memory_type: str
    data_type: str
    data_memory: Optional[str]
    expression: Expression

@dataclass
class Program:
    statements: List[Statement]

@dataclass
class StructDeclaration(Statement):
    name: str
    fields: List[VariableDeclaration]
    type_params: List[str] = field(default_factory=list)   # добавлено

@dataclass
class TypeAlias(Statement):
    name: str
    target_type: str

@dataclass
class NamespaceDeclaration(Statement):
    name: str
    body: List[Statement]

@dataclass
class ExternFunction(Statement):
    name: str
    parameters: List[Parameter]
    return_type: Optional[str]

@dataclass
class ConstDeclaration(Statement):
    name: str
    type: str
    value: Expression

@dataclass
class StaticVariable(Statement):
    name: str
    type: str
    initializer: Optional[Expression]

@dataclass
class FString(Expression):
    parts: List[Any]

# --- Новые классы для массивов и словарей ---
@dataclass
class ArrayLiteral(Expression):
    elements: List[Expression]

@dataclass
class DictPair:
    key: Expression
    value: Expression

@dataclass
class DictLiteral(Expression):
    pairs: List[DictPair]

@dataclass
class IndexExpression(Expression):
    target: Expression
    index: Expression

@dataclass
class ThrowStatement(Statement):
    value: Expression