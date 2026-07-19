from dataclasses import dataclass, field
from typing import List, Optional, Any, Union
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lexer_module.token import Token

@dataclass
class Expression:
    """ Базовый класс для всех узлов выражений в AST. """
    line: int
    col: int
    cached_type: Optional[str] = field(default=None, init=False)


@dataclass
class Identifier(Expression):
    name: str


@dataclass
class Literal(Expression):
    value: Any  # int, float, str, bool, None


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
class MacroCall(Expression):
    """
    Вызов макроса (например: print!(x) или директива @inline).
    """
    name: str
    arguments: List[Expression]
    is_directive: bool = False  # True если @macro, False если имя!


@dataclass
class MemberAccess(Expression):
    object: Expression
    member: str


@dataclass
class Assignment(Expression):
    target: Expression
    value: Expression
    operator: str = '='


@dataclass
class TagAnnotation(Expression):
    name: str
    arguments: List[Expression]


@dataclass
class Conditional(Expression):
    condition: Expression
    then_expr: Expression
    else_expr: Expression


@dataclass
class Statement:
    """ Базовый класс для всех инструкций. """
    line: int
    col: int


@dataclass
class ExpressionStatement(Statement):
    expression: Expression


@dataclass
class VariableDeclaration(Statement):
    modifier: Optional[str]      # const, static, public, private
    type: str
    name: str
    initializer: Optional[Expression]
    tag: Optional[TagAnnotation] = None
    is_unwait: bool = False
    unwait_default: Optional[Expression] = None


@dataclass
class Parameter:
    type: str
    name: str


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
    init: Optional[Statement]
    condition: Optional[Expression]
    update: Optional[Expression]
    body: List[Statement]


@dataclass
class ForEachLoop(Statement):
    item_decl: Statement
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
    type_params: List[str] = field(default_factory=list)


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


@dataclass
class TypeOfExpression(Expression):
    argument: Expression


@dataclass
class FieldsExpression(Expression):
    argument: Expression


@dataclass
class MethodsExpression(Expression):
    argument: Expression


@dataclass
class GlobalCBlock(Statement):
    code: str


@dataclass
class MethodDeclaration(Statement):
    return_type: Optional[str]
    name: str
    parameters: List[Parameter]
    body: List[Statement]
    return_memory: Optional[str] = None
    modifier: Optional[str] = None
    type_params: List[str] = field(default_factory=list)
    is_override: bool = False
    is_abstract: bool = False
    is_async: bool = False


@dataclass
class AwaitExpression(Expression):
    expression: Expression


@dataclass
class PropertyDeclaration:
    name: str
    type: str
    getter: Optional[MethodDeclaration]
    setter: Optional[MethodDeclaration]


@dataclass
class ClassDeclaration(Statement):
    name: str
    extends: Optional[str]
    methods: List[MethodDeclaration]
    type_params: List[str] = field(default_factory=list)
    fields: List[VariableDeclaration] = field(default_factory=list)
    wait_fields: List[VariableDeclaration] = field(default_factory=list)
    super_args: List[Expression] = field(default_factory=list)
    all_methods: List[MethodDeclaration] = field(default_factory=list)
    static_fields: List[VariableDeclaration] = field(default_factory=list)
    static_methods: List[MethodDeclaration] = field(default_factory=list)
    properties: List[PropertyDeclaration] = field(default_factory=list)
    is_sealed: bool = False
    is_abstract: bool = False
    impl_interfaces: List[str] = field(default_factory=list)


@dataclass
class SuperCall(Expression):
    method: Optional[str]
    arguments: List[Expression]


@dataclass
class InterfaceDeclaration(Statement):
    name: str
    methods: List[MethodDeclaration]


@dataclass
class ImplDeclaration(Statement):
    class_name: str
    interface_name: str
    methods: List[MethodDeclaration]


@dataclass
class ExprCode:
    code: str           # C++ код
    raw_type: str       # C++ тип (например, 'ely_value*')
    ely_type: str       # Ely тип (например, 'int')
    
    @property
    def is_wrapped(self) -> bool:
        return self.raw_type == 'ely_value*'
    
    @property
    def is_native(self) -> bool:
        return not self.is_wrapped and self.raw_type != 'void'