
import os, sys
from typing import Optional, Any, Tuple
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lexer_module import *
from parser import *
from parser.rules import ely_grammar
from parser.earley_core import EarleyState, ElyEarleyParser, Grammar, ParseNode, Rule 

class Parser:
    def __init__(self):
        RED = '\033[91m'
        YELLOW = '\033[93m'
        CYAN = '\033[96m'
        BOLD = '\033[1m'
        RESET = '\033[0m'

class ElyOrchestrator:
    def __init__(self, grammar: Grammar):
        """
        Инициализация оркестратора. На данном этапе настраивает синтаксический движок Эрли.
        """
        self.grammar = grammar
        self.parser = ElyEarleyParser(self.grammar)

    def run(self, source_code: str, context: Optional[Any] = None) -> Tuple[Optional[ParseNode], Any]:
        """
        Основной конвейер обработки Ely-кода.
        
        Проходит фазы:
        1. Preprocessing (Фиксация макросов и директив сборки) -> Вход: str, Выход: str
        2. Lexing (Токенизация очищенного исходника)       -> Вход: str, Выход: List[Token]
        3. Filtering (Очистка от EOF для ядра Эрли)        -> Вход: List[Token], Выход: List[Token]
        4. Parsing (Построение CST дерева разбора)          -> Вход: List[Token], Выход: ParseNode
        
        Возвращает:
            Tuple[ParseNode, CompilerContext]: Дерево CST и финальное состояние контекста.
        """
        # Если контекст не передан извне (например, при пакетной сборке файлов), создаем новый
        if context is None:
            context = CompilerContext()

        # Фаза 1: Препроцессинг (Fixed-Point Expansion)
        # Раскрываем инлайновые/структурные макросы и регистрируем типы
        preprocessor = ElyPreprocessor(context, Lexer)
        expanded_source, updated_context = preprocessor.process(source_code)

        # Фаза 2: Финальный Лексический Анализ
        # Токенизируем уже чистый, развернутый код
        lexer = Lexer(expanded_source)
        tokens = lexer.tokenize(debug=updated_context.debug_mode)

        # Фаза 3: Фильтрация потока
        # Убираем маркеры EOF для бесперебойной работы Earley-движка
        pure_tokens = [t for t in tokens if t.type != TokenType.EOF]

        # Фаза 4: Синтаксический Анализ (Генерация CST)
        parse_tree, error = self.parser.parse(pure_tokens)

        if error:
            # Ловим ошибку парсинга и выбрасываем информативное исключение,
            # чтобы вызывающий код (или CLI компилятора) мог её обработать
            raise SyntaxError(f"[Ely Compilation Error]\n{error}")

        return parse_tree, updated_context

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

    @HELLOWORLD "Hello, world!"

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
        cst.print_tree()
        
        print(f"\nЗарегистрированные примитивы: {final_context.primitive_types}")
        print(f"Режим отладки: {final_context.debug_mode}")

    except SyntaxError as e:
        print(e)
    except RuntimeError as e:
        print(f"[Runtime Error During Preprocessing]: {e}")