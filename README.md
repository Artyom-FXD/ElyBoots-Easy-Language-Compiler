<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>Easy Language — современный язык программирования</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700&display=swap" rel="stylesheet">
    <style>
        /* Базовые сбросы */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            cursor: default;
        }

        

        body {
            font-family: 'Inter', 'Nata Sans', sans-serif;
            background-color: #000000;
            transition: background-color 5s ease;
            color: #f0f0f0;
            line-height: 1.5;
        }

        a {
            text-decoration: none;
            cursor: pointer;
        }

        /* Заглушка для фиксированной шапки */
        .black-header-supp {
            height: 8rem;
        }

        .container {
            max-width: 1300px;
            margin: 0 auto;
            padding: 0 1.5rem;
        }

        /* ========== ШАПКА ========== */
        header {
            width: 80vw;
            height: 3rem;
            background-color: rgba(0, 0, 0, 0.25);
            backdrop-filter: blur(20px);
            border-radius: 1rem;
            position: fixed;
            top: 1rem;
            left: 10vw;
            right: 10vw;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 1rem;
            z-index: 100;
            transition: 0.35s;
        }

        .header-invisible {
            background: none;
            backdrop-filter: none;
            top: 0.5rem;
        }

        .logo-text {
            font-size: 1.8rem;
            font-weight: 700;
            color: #ffbb0f;
            letter-spacing: 1px;
        }

        .header-btns {
            display: flex;
            gap: 1rem;
        }

        .header-btn {
            padding: 0.5rem 1rem;
            border-radius: 1rem;
            background: transparent;
            border: none;
            color: #fff;
            font-size: 1rem;
            font-weight: 500;
            transition: 0.35s;
            cursor: pointer;
        }

        .btn-orange { --shadow-color: #ffbb0f; }
        .btn-green  { --shadow-color: #b3ff77; }
        .btn-red    { --shadow-color: #ff4444; }

        .header-btn:hover {
            transform: translateY(-0.5em);
            text-shadow: var(--shadow-color) 0 3px 25px;
            color: var(--shadow-color);
        }

        /* ========== ПРИВЕТСТВЕННЫЙ БЛОК ========== */
        .white-with-logo {
            background-color: #ffffff;
            filter: blur(1.25px);
            box-shadow: #fff 0 0 15px;
            height: 55em;
            display: flex;
            align-items: center;
            justify-content: space-evenly;
            padding-left: 6rem;
            overflow: hidden;
            position: relative;
            margin-bottom: 2rem;
        }

        .wwl-text h1 {
            font-size: 4rem;
            font-weight: 800;
            color: #000;
            animation: appear4s 3s;
        }
        .wwl-text h4 {
            font-size: 1.5rem;
            font-style: oblique;
            color: #333;
            animation: appear4s 3s;
        }

        .logo-slider {
            font-size: 8rem;
            font-weight: 800;
            color: #ffbb0f;
            text-shadow: 0 0 15px #ffbb0f;
            animation: slideUpDeco 2s;
        }

        .mobile-scrolldown {
            display: none;
            border-radius: 2rem;
            min-width: 2rem;
            height: 2rem;
            background-color: rgba(0, 0, 0, 0.169);
            backdrop-filter: blur(20px);
            font-size: 2rem;
            position: fixed;
            bottom: 1rem;
            right: 1rem;
            color: #ffbb0f;
            border: none;
            box-shadow: #ffbb0f 0 0 15px;
            cursor: pointer;
            z-index: 100;
            transition: 0.35s;
            padding: 0.25rem;
            line-height: 1;
        }
        .mobile-scrolldown:hover {
            transform: translateY(-0.25rem);
            box-shadow: #ffbb0f 0 0 25px;
        }

        /* ========== ОБЩИЕ СТИЛИ ДЛЯ КАРТОЧЕК ========== */
        .card {
            background: rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(6px);
            border-radius: 1rem;
            padding: 1.5rem;
            border: 1px solid rgba(255, 187, 15, 0.3);
            transition: all 0.3s ease;
        }
        .card:hover {
            transform: translateY(-0.25rem);
            border-color: #ffbb0f;
            box-shadow: 0 5px 20px rgba(255, 187, 15, 0.2);
            backdrop-filter: blur(4px);
        }
        .card h3 {
            color: #ffbb0f;
            margin-bottom: 0.5rem;
            font-size: 1.3rem;
        }

        /* Сетки */
        .grid-2col {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 2rem;
            margin: 2rem 0;
        }

        .feature-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1.5rem;
            margin: 2rem 0;
        }

        /* Таблицы */
        .api-table {
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            background: rgba(0,0,0,0.3);
            backdrop-filter: blur(4px);
            border-radius: 1rem;
            overflow: hidden;
        }
        .api-table th, .api-table td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid rgba(255,187,15,0.2);
        }
        .api-table th {
            color: #ffbb0f;
            font-weight: 600;
        }

        /* Стили для кода */
        pre, code {
            font-family: 'JetBrains Mono', monospace;
            background: #1e1e2a;
            border-radius: 0.5rem;
            padding: 0.2rem 0.4rem;
        }
        pre {
            padding: 1rem;
            overflow-x: auto;
            border-left: 3px solid #ffbb0f;
            margin: 1rem 0;
        }

        /* Карточки участников */
        .main-devs {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 1.5rem;
            list-style: none;
            margin: 2rem 0;
        }
        .main-dev {
            width: 12rem;
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(6px);
            border-radius: 1rem;
            padding: 1rem;
            text-align: center;
            transition: 0.5s;
            filter: blur(1px);
        }
        .main-dev:hover {
            transform: translateY(-0.35rem);
            box-shadow: 0 5px 15px #ffbb0f;
            filter: blur(0.25px);
            backdrop-filter: blur(3px);
        }
        .avatar {
            width: 100px;
            height: 100px;
            background: #ffbb0f33;
            border-radius: 50%;
            margin: 0 auto 0.8rem;
            background-size: cover;
            background-position: center;
        }
        .dev-desc {
            font-size: 0.9rem;
            opacity: 0.8;
        }

        /* Проекты */
        .prjs {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 1.5rem;
            list-style: none;
            padding: 1rem;
            margin: 1rem 0;
        }
        .prj-container {
            width: 200px;
            background: rgba(0,0,0,0.5);
            backdrop-filter: blur(6px);
            border-radius: 1rem;
            padding: 1rem;
            text-align: center;
            transition: 0.3s;
            border: 1px solid rgba(255,187,15,0.2);
        }
        .prj-container:hover {
            transform: translateY(-0.25rem);
            border-color: #ffbb0f;
            box-shadow: 0 5px 15px rgba(255,187,15,0.3);
            backdrop-filter: blur(4px);
        }
        .prj-image {
            width: 80px;
            height: 80px;
            background: #ffbb0f33;
            border-radius: 50%;
            margin: 0 auto 1rem;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2rem;
            color: #ffbb0f;
        }
        .prj-name {
            color: #ffbb0f;
            margin-bottom: 0.5rem;
            font-size: 1.2rem;
        }
        .prj-desc {
            font-size: 0.85rem;
            opacity: 0.9;
        }

        /* Анимации */
        @keyframes slideUpDeco {
            0% { transform: translateY(1024px); }
            100% {}
        }
        @keyframes appear4s {
            0% { opacity: 0; }
            50% { opacity: 0; }
            100% {}
        }

        hr {
            border-color: rgba(255,187,15,0.3);
            margin: 2rem 0;
        }
        footer {
            text-align: center;
            padding: 2rem;
            opacity: 0.7;
            font-size: 0.9rem;
        }

        * {
            filter: blur(0.025em);
        }

        /* Адаптивность */
        @media (max-width: 1090px) {
            .black-header-supp, .header-btns {
                display: none;
            }
            header {
                width: 6rem;
                height: 6rem;
                border-radius: 15rem;
                top: auto;
                bottom: 2rem;
                left: auto;
                right: 2rem;
                background: rgba(0,0,0,0.5);
                backdrop-filter: blur(20px);
                overflow: visible;
            }
            .logo-text {
                font-size: 1.8rem;
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                white-space: nowrap;
            }
            .header-btns {
                display: none;
                position: fixed;
                right: 7rem;
                bottom: 2rem;
                flex-direction: column;
                gap: 0.5rem;
                background: rgba(0,0,0,0.5);
                backdrop-filter: blur(20px);
                padding: 0.5rem;
                border-radius: 2rem;
            }
            header:hover .header-btns {
                display: flex;
            }
            .header-btn {
                width: 5rem;
                text-align: center;
                font-size: 0.8rem;
                padding: 0.5rem;
            }
            .white-with-logo {
                height: 100vh;
                padding-left: 1rem;
                flex-direction: column;
                text-align: center;
            }
            .wwl-text h1 {
                font-size: 2.5rem;
            }
            .logo-slider {
                font-size: 5rem;
            }
            .mobile-scrolldown {
                display: block;
            }
            .grid-2col {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
<!-- Приветственный блок -->
<section class="white-with-logo">
    <div class="wwl-text">
        <h1>Easy Language</h1>
        <h4>быстрый, современный, открытый</h4>
    </div>
    <div class="logo-slider">Easy</div>
    <button class="mobile-scrolldown" id="mobileScrollDown">↓</button>
</section>

<div class="container">
    <!-- О языке (краткие карточки) -->
    <h1 id="about" class="section-title">О языке Easy</h1>
    <div class="grid-2col">
        <div class="card">
            <h3>Статическая типизация</h3>
            <p>Безопасность типов на этапе компиляции. Вывод типов через <code>var</code>. Никаких неожиданных ошибок во время выполнения.</p>
        </div>
        <div class="card">
            <h3>Молниеносная компиляция</h3>
            <p>Благодаря Tiny C Compiler (TCC) компиляция происходит со скоростью сотни тысяч строк в секунду. Идеально для быстрого цикла разработки.</p>
        </div>
        <div class="card">
            <h3>Встроенные коллекции</h3>
            <p>Динамические массивы (<code>arr&lt;T&gt;</code>) и словари (<code>dict&lt;K,V&gt;</code>) с удобными методами: <code>push</code>, <code>pop</code>, <code>len</code>, доступ по индексу и ключу.</p>
        </div>
        <div class="card">
            <h3>Обобщения (дженерики)</h3>
            <p>Пишите обобщённые функции и структуры. Типы выводятся из аргументов. Реализована мономорфизация — каждая специализация генерирует оптимальный код.</p>
        </div>
        <div class="card">
            <h3>Обработка ошибок</h3>
            <p>Блоки <code>asafe</code> / <code>except</code> / <code>throw</code> — понятный механизм исключений, знакомый по современным языкам.</p>
        </div>
        <div class="card">
            <h3>F-строки</h3>
            <p>Интерполяция выражений прямо в строке: <code>f"Привет, {name}!"</code>. Автоматическое преобразование в строку массивов, словарей, чисел.</p>
        </div>
        <div class="card">
            <h3>Модульность</h3>
            <p>Сборка проектов через <code>manager.json</code>. Модули компилируются в динамические библиотеки (<code>.dll</code>/<code>.so</code>) и могут переиспользоваться.</p>
        </div>
        <div class="card">
            <h3>Будущий сборщик мусора</h3>
            <p>В следующем релизе — автоматическое управление памятью для строк, массивов, словарей и объектов. Забудьте о ручном <code>free</code>.</p>
        </div>
    </div>

    <!-- Синтаксис и примеры -->
    <h1>Синтаксис и примеры</h1>
    <pre><code>// Hello, World!
public func main() -> int {
    println("Hello, World!");
    return 0;
}</code></pre>

    <!-- Проекты -->
    <h1 id="projects">В EasyBoots входят</h1>
    <ul class="prjs">
        <li><div class="prj-container"><div class="prj-image">EBT</div><h3 class="prj-name">EasyBoots</h3><p class="prj-desc">Компилятор, сборка проектов, поддержка модулей.</p></div></li>
        <li><div class="prj-container"><div class="prj-image">DOC</div><h3 class="prj-name">Документация</h3><p class="prj-desc">Полное руководство, справочник API, примеры.</p></div></li>
        <li><div class="prj-container"><div class="prj-image">TCC</div><h3 class="prj-name">TCC</h3><p class="prj-desc">Компилятор для трансляции из промежуточного представления</p></div></li>
        <li><div class="prj-container"><div class="prj-image">STD</div><h3 class="prj-name">Стандартная библиотека</h3><p class="prj-desc">Исходный код runtime, документация по функциям.</p></div></li>
        <li><div class="prj-container"><div class="prj-image">GIT</div><h3 class="prj-name">GitHub</h3><p class="prj-desc">Исходный код, issues, pull requests, гайды. Не входит в состав, но напрямую относится.</p></div></li>
    </ul>

    <!-- Полная стандартная библиотека -->
    <h1>Стандартная библиотека Easy</h1>
    <p>Все встроенные функции доступны без <code>using</code> и написаны в стиле <strong>camelCase</strong>.</p>

    <h3>1. Консольный ввод/вывод</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th><th>Пример</th></tr>
        <tr><td><code>print(str)</code></td><td>Выводит строку без перевода строки</td><td><code>print("Hello")</code></td></tr>
        <tr><td><code>println(str)</code></td><td>Выводит строку с переводом строки</td><td><code>println("World")</code></td></tr>
        <tr><td><code>println(int)</code></td><td>Выводит число</td><td><code>println(42)</code></td></tr>
        <tr><td><code>println(bool)</code></td><td>Выводит true/false</td><td><code>println(true)</code></td></tr>
        <tr><td><code>println(arr&lt;T&gt;)</code></td><td>Выводит массив в формате JSON</td><td><code>println([1,2,3])</code> → <code>[1,2,3]</code></td></tr>
        <tr><td><code>println(dict&lt;K,V&gt;)</code></td><td>Выводит словарь в формате JSON</td><td><code>println({"x":5})</code> → <code>{"x":5}</code></td></tr>
        <tr><td><code>input()</code></td><td>Читает строку из stdin</td><td><code>str s = input()</code></td></tr>
        <tr><td><code>inputPrompt(str)</code></td><td>Выводит приглашение и читает строку</td><td><code>str name = inputPrompt("Name: ")</code></td></tr>
    </table>

    <h3>2. Преобразования типов</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th><th>Пример</th></tr>
        <tr><td><code>strToInt(str)</code></td><td>Строка → int</td><td><code>int x = strToInt("123")</code></td></tr>
        <tr><td><code>strToUint(str)</code></td><td>Строка → uint</td><td><code>uint u = strToUint("42")</code></td></tr>
        <tr><td><code>strToMore(str)</code></td><td>Строка → more (long long)</td><td><code>more m = strToMore("9223372036854775807")</code></td></tr>
        <tr><td><code>strToUm(str)</code></td><td>Строка → umore</td><td><code>umore um = strToUm("18446744073709551615")</code></td></tr>
        <tr><td><code>strToFlt(str)</code></td><td>Строка → flt (float)</td><td><code>flt f = strToFlt("3.14")</code></td></tr>
        <tr><td><code>strToDouble(str)</code></td><td>Строка → double</td><td><code>double d = strToDouble("3.14159")</code></td></tr>
        <tr><td><code>intToStr(int)</code></td><td>int → строка</td><td><code>str s = intToStr(42)</code></td></tr>
        <tr><td><code>uintToStr(uint)</code></td><td>uint → строка</td><td><code>str s = uintToStr(42u)</code></td></tr>
        <tr><td><code>moreToStr(more)</code></td><td>more → строка</td><td><code>str s = moreToStr(123456789LL)</code></td></tr>
        <tr><td><code>umoreToStr(umore)</code></td><td>umore → строка</td><td><code>str s = umoreToStr(987654321ULL)</code></td></tr>
        <tr><td><code>fltToStr(flt)</code></td><td>flt → строка</td><td><code>str s = fltToStr(3.14f)</code></td></tr>
        <tr><td><code>doubleToStr(double)</code></td><td>double → строка</td><td><code>str s = doubleToStr(2.71828)</code></td></tr>
        <tr><td><code>boolToStr(bool)</code></td><td>bool → "true"/"false"</td><td><code>str s = boolToStr(true)</code></td></tr>
    </table>

    <h3>3. Строковые функции</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th><th>Пример</th></tr>
        <tr><td><code>len(str)</code></td><td>Длина строки</td><td><code>int n = len("hello")</code></td></tr>
        <tr><td><code>dup(str)</code></td><td>Копия строки</td><td><code>str s = dup("text")</code></td></tr>
        <tr><td><code>concat(str, str)</code></td><td>Конкатенация</td><td><code>str s = concat("Hello", "World")</code></td></tr>
        <tr><td><code>cmp(str, str)</code></td><td>Сравнение (0 – равны)</td><td><code>int r = cmp("abc", "abd")</code></td></tr>
        <tr><td><code>substr(str, start, len)</code></td><td>Подстрока</td><td><code>str s = substr("hello", 1, 2)</code> → "el"</td></tr>
        <tr><td><code>trim(str)</code></td><td>Удаление пробелов по краям</td><td><code>str s = trim("  abc  ")</code> → "abc"</td></tr>
        <tr><td><code>replace(str, old, new)</code></td><td>Замена подстроки</td><td><code>str s = replace("ababa", "ab", "c")</code> → "cba"</td></tr>
    </table>

    <h3>4. Математика</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>abs(int)</code></td><td>Абсолютное значение</td></tr>
        <tr><td><code>absMore(more)</code></td><td>Абсолютное значение для more</td></tr>
        <tr><td><code>fabs(double)</code></td><td>Абсолютное значение для double</td></tr>
        <tr><td><code>min(int, int)</code></td><td>Минимум</td></tr>
        <tr><td><code>max(int, int)</code></td><td>Максимум</td></tr>
        <tr><td><code>pow(double, double)</code></td><td>Возведение в степень</td></tr>
        <tr><td><code>sqrt(double)</code></td><td>Квадратный корень</td></tr>
        <tr><td><code>sin(double), cos(double), tan(double)</code></td><td>Тригонометрия</td></tr>
        <tr><td><code>rand()</code></td><td>Случайное число (0..32767)</td></tr>
        <tr><td><code>srand(uint)</code></td><td>Установка seed</td></tr>
        <tr><td><code>randDouble()</code></td><td>Случайное double [0..1)</td></tr>
    </table>

    <h3>5. Время</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>sleep(uint)</code></td><td>Пауза в миллисекундах</td></tr>
        <tr><td><code>timeNow()</code></td><td>Текущее время (секунды с эпохи)</td></tr>
        <tr><td><code>timeDiff(more, more)</code></td><td>Разница в секундах (double)</td></tr>
    </table>

    <h3>6. Файлы</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>fileOpen(str, str)</code></td><td>Открыть файл (режим "r", "w", "rb", "wb")</td></tr>
        <tr><td><code>fileClose(File)</code></td><td>Закрыть файл</td></tr>
        <tr><td><code>fileWrite(File, str, int)</code></td><td>Записать данные (строка, длина)</td></tr>
        <tr><td><code>fileRead(File, int*)</code></td><td>Прочитать данные (возвращает строку, размер через указатель)</td></tr>
        <tr><td><code>fileExists(str)</code></td><td>Проверка существования</td></tr>
        <tr><td><code>fileReadAll(str, int*)</code></td><td>Прочитать весь файл</td></tr>
        <tr><td><code>fileRemove(str)</code></td><td>Удалить файл</td></tr>
        <tr><td><code>fileRename(str, str)</code></td><td>Переименовать</td></tr>
    </table>

    <h3>7. Пути</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>pathJoin(str, str)</code></td><td>Объединить пути</td></tr>
        <tr><td><code>pathBasename(str)</code></td><td>Имя файла из пути</td></tr>
        <tr><td><code>pathDirname(str)</code></td><td>Директория из пути</td></tr>
        <tr><td><code>pathIsAbsolute(str)</code></td><td>Проверка на абсолютный путь</td></tr>
    </table>

    <h3>8. Динамические библиотеки</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>loadLibrary(str)</code></td><td>Загрузить DLL/so (возвращает указатель)</td></tr>
        <tr><td><code>getFunction(any, str)</code></td><td>Получить функцию по имени</td></tr>
        <tr><td><code>closeLibrary(any)</code></td><td>Выгрузить библиотеку</td></tr>
        <tr><td><code>callIntInt(any, int, int)</code></td><td>Вызвать функцию <code>int func(int, int)</code></td></tr>
        <tr><td><code>callDoubleDouble(any, double)</code></td><td>Вызвать <code>double func(double)</code></td></tr>
        <tr><td><code>callDoubleDoubleDouble(any, double, double)</code></td><td>Вызвать <code>double func(double, double)</code></td></tr>
        <tr><td><code>callStrVoid(any)</code></td><td>Вызвать <code>char* func(void)</code></td></tr>
    </table>

    <h3>9. Методы массивов <code>arr&lt;T&gt;</code></h3>
    <table class="api-table">
        <tr><th>Метод</th><th>Описание</th><th>Пример</th></tr>
        <tr><td><code>push(T)</code></td><td>Добавить элемент в конец</td><td><code>a.push(10)</code></td></tr>
        <tr><td><code>pop()</code></td><td>Удалить последний элемент и вернуть его</td><td><code>int x = a.pop()</code></td></tr>
        <tr><td><code>len()</code></td><td>Длина массива</td><td><code>int n = a.len()</code></td></tr>
        <tr><td><code>insert(int, T)</code></td><td>Вставить элемент по индексу</td><td><code>a.insert(1, 99)</code></td></tr>
        <tr><td><code>remove(T)</code></td><td>Удалить первое вхождение значения</td><td><code>a.remove(42)</code></td></tr>
        <tr><td><code>index(T)</code></td><td>Найти индекс первого вхождения (-1 если нет)</td><td><code>int i = a.index(5)</code></td></tr>
    </table>

    <!-- DictServer модуль -->
    <h1>Модуль DictServer (работа с JSON)</h1>
    <p>Подключается через <code>using DictServer;</code>. Тип <code>DictHost</code> – непрозрачный указатель на словарь.</p>

    <h3>Загрузка и сохранение</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>load(str)</code></td><td>Загружает JSON из файла, возвращает DictHost</td></tr>
        <tr><td><code>save(DictHost, str)</code></td><td>Сохраняет словарь в файл</td></tr>
    </table>

    <h3>Получение значений</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>getStr(DictHost, str)</code></td><td>Возвращает строку по ключу</td></tr>
        <tr><td><code>getInt(DictHost, str)</code></td><td>Возвращает int</td></tr>
        <tr><td><code>getBool(DictHost, str)</code></td><td>Возвращает bool</td></tr>
        <tr><td><code>getDouble(DictHost, str)</code></td><td>Возвращает double</td></tr>
        <tr><td><code>getObj(DictHost, str)</code></td><td>Возвращает вложенный словарь (DictHost)</td></tr>
    </table>

    <h3>Установка значений</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>setStr(DictHost, str, str)</code></td><td>Устанавливает строку</td></tr>
        <tr><td><code>setInt(DictHost, str, int)</code></td><td>Устанавливает целое</td></tr>
        <tr><td><code>setBool(DictHost, str, bool)</code></td><td>Устанавливает булево</td></tr>
        <tr><td><code>setDouble(DictHost, str, double)</code></td><td>Устанавливает вещественное</td></tr>
        <tr><td><code>setObj(DictHost, str, DictHost)</code></td><td>Устанавливает вложенный словарь</td></tr>
    </table>

    <h3>Управление ключами и сериализация</h3>
    <table class="api-table">
        <tr><th>Функция</th><th>Описание</th></tr>
        <tr><td><code>del(DictHost, str)</code></td><td>Удаляет ключ</td></tr>
        <tr><td><code>has(DictHost, str)</code></td><td>Проверяет существование ключа</td></tr>
        <tr><td><code>keys(DictHost)</code></td><td>Возвращает массив строк с ключами</td></tr>
        <tr><td><code>toJson(DictHost)</code></td><td>Возвращает JSON-представление словаря</td></tr>
        <tr><td><code>parse(str)</code></td><td>Парсит JSON в DictHost</td></tr>
        <tr><td><code>freeDict(DictHost)</code></td><td>Освобождает память</td></tr>
    </table>

    <!-- Модули и компилятор -->
    <h1>Модули и компилятор EasyBoots</h1>
    <div class="grid-2col">
        <div class="card">
            <h3>Сборка проекта</h3>
            <p>Файл <code>manager.json</code> задаёт точку входа, имя выходного файла, модули и дополнительные библиотеки.</p>
            <pre><code>{
    "name": "ProjectName",
    "libs": {},
    "modules": {
        "DictServer": "./modules/math.e"
    },
    "enter": "main.e",
    "stx": {
        "processType": "console"
    },
    "output": {
        "folder-modules": {
            "modules": "*"
        },
        "enter": {
            "name": "app.exe",
            "type": "exe"
        }
    }
}</code></pre>
            <p>Команда: <code>python easyboots.py build</code> — создаёт исполняемый файл в папке <code>output/</code>.</p>
        </div>
        <div class="card">
            <h3>Создание модуля</h3>
            <p>Объявите публичные функции с модификатором <code>public</code>:</p>
            <pre><code>// math.e
public func add(a: int, b: int) -> int {
    return a + b;
}</code></pre>
            <p>Используйте <code>using math;</code> в основном коде. Компилятор сгенерирует заголовочный файл и динамическую библиотеку.</p>
        </div>
    </div>

    <hr>
    <footer>
        <p>Easy Language — свободное программное обеспечение (лицензия MIT).<br>
        Компилятор EasyBoots и стандартная библиотека распространяются под MIT с исключением.<br>
        TCC в комплекте — LGPL 2.1.<br>
        Создано сообществом 2nd Age. 2026</p>
    </footer>
</div>

<script>
    (function() {
        const header = document.getElementById('header');
        const aboutBtn = document.getElementById('aboutBtn');
        const featuresBtn = document.getElementById('featuresBtn');
        const projectsBtn = document.getElementById('projectsBtn');
        const scrolldownBtn = document.getElementById('mobileScrollDown');
        const joinUsDev = document.getElementById('joinUsDev'); // не используется, но оставим

        function scrollToElement(el, offset = 80) {
            if (!el) return;
            const rect = el.getBoundingClientRect();
            const scrollTop = window.pageYOffset + rect.top - offset;
            window.scrollTo({ top: scrollTop, behavior: 'smooth' });
        }

        if (aboutBtn) aboutBtn.addEventListener('click', () => scrollToElement(document.getElementById('about'), 80));
        if (featuresBtn) featuresBtn.addEventListener('click', () => scrollToElement(document.querySelector('.feature-grid'), 80));
        if (projectsBtn) projectsBtn.addEventListener('click', () => scrollToElement(document.getElementById('projects'), 80));
        if (scrolldownBtn) scrolldownBtn.addEventListener('click', () => scrollToElement(document.getElementById('about'), 80));

        // Смена фона
        const colorsBG = [
            '#1f1a0f', '#231f12', '#1e2a0f', '#2a1a1a', '#1d1a2a', '#0a0a0f',
            '#2a241a', '#2a2a1a', '#2a1a24'
        ];
        let cur = 0;
        setInterval(() => {
            document.body.style.backgroundColor = colorsBG[cur];
            cur = (cur + 1) % colorsBG.length;
        }, 1000);

        // Изменение шапки при скролле
        window.addEventListener('scroll', () => {
            if (window.scrollY < 100) {
                header.classList.add('header-invisible');
            } else {
                header.classList.remove('header-invisible');
            }
        });
    })();
</script>
</body>
</html>