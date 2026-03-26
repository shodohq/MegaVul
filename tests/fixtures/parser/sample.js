/**
 * tests/fixtures/parser/sample.js
 *
 * ParserJavaScript の単体テスト用合成フィクスチャ。
 * 各関数種別を1ファイルに網羅する。
 *
 * 期待される抽出関数（計8つ）:
 *   1. greet               — function_declaration, 1 param
 *   2. add                 — function_declaration, 2 params
 *   3. multiply            — function_expression (const への代入)
 *   4. square              — arrow_function (const への代入)
 *   5. Counter.constructor — method_definition, 1 param
 *   6. Counter.increment   — method_definition, 1 param
 *   7. Counter.reset       — method_definition, 0 params
 *   8. merge               — function_declaration, rest parameter
 */

// (1) function_declaration — 引数1つ
function greet(name) {
    return "Hello, " + name;
}

// (2) function_declaration — 引数2つ
function add(a, b) {
    return a + b;
}

// (3) function_expression — const に代入
const multiply = function(x, y) {
    return x * y;
};

// (4) arrow_function — const に代入、ブロックボディ
const square = (n) => {
    return n * n;
};

// (5)(6)(7) class の method_definition
class Counter {
    constructor(start) {
        this.count = start;
    }

    increment(step) {
        this.count += step;
        return this.count;
    }

    reset() {
        this.count = 0;
    }
}

// (8) function_declaration — rest parameter
function merge(target, ...sources) {
    return Object.assign(target, ...sources);
}
