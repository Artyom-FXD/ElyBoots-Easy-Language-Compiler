
import os, sys
from typing import Optional, Any, Tuple
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lexer_module import *
from parser import *
from parser.ast_builder import ASTBuilder, dump_ast
from parser.rules import ely_grammar
from parser.earley_core import EarleyState, ElyEarleyParser, Grammar, ParseNode, Rule 

class Parser:
    def __init__(self):
        RED = '\033[91m'
        YELLOW = '\033[93m'
        CYAN = '\033[96m'
        BOLD = '\033[1m'
        RESET = '\033[0m'

from ast_builder import ASTBuilder

class ElyOrchestrator:
    def __init__(self, grammar: Grammar):
        self.grammar = grammar
        self.parser = ElyEarleyParser(self.grammar)
        self.ast_builder = ASTBuilder()

    def run(self, source_code: str, context: Optional[Any] = None):
        if context is None:
            context = CompilerContext()

        # Фаза 1: Препроцессинг
        preprocessor = ElyPreprocessor(context, Lexer)
        expanded_source, updated_context = preprocessor.process(source_code)

        # Фаза 2: Токенизация
        lexer = Lexer(expanded_source)
        tokens = lexer.tokenize(debug=updated_context.debug_mode)
        pure_tokens = [t for t in tokens if t.type != TokenType.EOF]

        # Фаза 3: Генерация CST (Earley Parse)
        cst, error = self.parser.parse(pure_tokens)
        if error:
            raise SyntaxError(f"[EBT ERROR]\n{error}")
        if updated_context.debug_mode:
            cst.print_tree()

        # Фаза 4: Трансформация CST -> AST
        ast = self.ast_builder.build(cst)

        if updated_context.debug_mode:
            dump_ast(ast)

        return ast, updated_context

if __name__ == "__main__": 
    
    
    example_code = """#typedef vector;
    #debug true;

    cCode {
        int Cint = 3;
    }

    abstract class Animal {
        wait str name;
        wait bool haveWool;

        abstract void func say();
    }

    Animal class Cat {
        super(name, haveWool);

        sealed void func  say() {
            print(f"Cat {name} says meow :3");
        }
    }

    @HELLOWORLD {"Hello,"+"world!"}

    %FuncDecl hi quotes(\"\"\"
        print("Hi!");
    \"\"\");

    public static hi int func main() {
        const int a = 5;
        b = 12.5;
        ba = b + a;
        bas = str(ba);
        c = HELLOWORLD;
        arr<int> arr1 = [0, 4];
        arr arr2 = ["hello", 'w', true];
        dict<str, any> bibi = {
            "name": "Kitten",
            "weight": 3,
        };
        dict bebe = {
            "age" : 0,
            2: false
        };
        Cat kitty = new Cat("Kitty");
        kitty.say();
        print(f"{c} I'm Ely!");
    }
    """

    parser = ElyOrchestrator(ely_grammar)
    try:
        print("--- СБОРКА ПРОЕКТА ЗАПУЩЕНА ---")
        # Получаем готовое дерево CST и контекст за один вызов
        cst, final_context = parser.run(example_code)
        
        print("\n--- ДЕРЕВО CST УСПЕШНО ПОСТРОЕНО ---")
        # dump_ast(cst)
        
        print(f"\nЗарегистрированные примитивы: {final_context.primitive_types}")
        print(f"Режим отладки: {final_context.debug_mode}")

    except SyntaxError as e:
        print(e)
    except RuntimeError as e:
        print(f"[Runtime Error During Preprocessing]: {e}")