export const CALC_EXPR_MAX = 160;
export const CALC_HISTORY_MAX = 20;

export type AngleMode = "deg" | "rad";

export type CalcHistoryItem = {
  expr: string;
  result: string;
};

export type CalcResult = { ok: true; value: number; display: string } | { ok: false; error: string };

const FUNCTIONS = new Set(["sin", "cos", "tan", "log", "ln", "exp", "sqrt", "abs", "inv"]);
const CONSTANTS: Record<string, number> = { pi: Math.PI, π: Math.PI, e: Math.E };

const PAPER_WORDS = /\b(the|this|that|homework|assignment|explain|because|please|essay|paper|paragraph)\b/i;

export function looksLikeSchoolPaper(raw: string): boolean {
  const text = raw || "";
  if (/[\r\n]/.test(text)) return true;
  if (text.length > CALC_EXPR_MAX) return true;
  const words = text.match(/[A-Za-z]{3,}/g) || [];
  const unknown = words.filter((word) => !FUNCTIONS.has(word.toLowerCase()) && !(word.toLowerCase() in CONSTANTS));
  if (unknown.length >= 2) return true;
  if (PAPER_WORDS.test(text)) return true;
  return false;
}

export function formatCalcNumber(value: number): string {
  if (!Number.isFinite(value)) return "Error";
  if (Object.is(value, -0)) return "0";
  if (Math.abs(value) < 1e-12) return "0";
  if (Math.abs(value - Math.round(value)) < 1e-10 && Math.abs(value) < 1e15) {
    return String(Math.round(value));
  }
  const asExp = value.toExponential(10).replace(/\.?0+e/, "e").replace(/e\+/, "e");
  const asFixed = value.toPrecision(12).replace(/\.?0+$/, "");
  return asFixed.includes("e") ? asExp : asFixed;
}

type Tok =
  | { kind: "num"; value: number }
  | { kind: "id"; value: string }
  | { kind: "op"; value: string }
  | { kind: "lparen" }
  | { kind: "rparen" }
  | { kind: "bang" }
  | { kind: "deg" }
  | { kind: "eof" };

function tokenize(source: string): Tok[] {
  const tokens: Tok[] = [];
  let i = 0;
  const s = source.replace(/×/g, "*").replace(/÷/g, "/").replace(/·/g, "*").replace(/−/g, "-");
  while (i < s.length) {
    const ch = s[i]!;
    if (/\s/.test(ch)) {
      i += 1;
      continue;
    }
    if (ch === "," ) {
      throw new Error("Use one expression line.");
    }
    if (/[0-9.]/.test(ch)) {
      const match = s.slice(i).match(/^\d*\.?\d+(?:[eE][+-]?\d+)?/);
      if (!match) throw new Error("Bad number.");
      tokens.push({ kind: "num", value: Number(match[0]) });
      i += match[0].length;
      continue;
    }
    if (/[A-Za-zπ]/.test(ch)) {
      const match = s.slice(i).match(/^[A-Za-zπ]+/);
      tokens.push({ kind: "id", value: (match?.[0] || ch).toLowerCase() });
      i += match?.[0].length || 1;
      continue;
    }
    if (ch === "(") {
      tokens.push({ kind: "lparen" });
      i += 1;
      continue;
    }
    if (ch === ")") {
      tokens.push({ kind: "rparen" });
      i += 1;
      continue;
    }
    if (ch === "!") {
      tokens.push({ kind: "bang" });
      i += 1;
      continue;
    }
    if (ch === "°") {
      tokens.push({ kind: "deg" });
      i += 1;
      continue;
    }
    if ("+-*/^%".includes(ch)) {
      tokens.push({ kind: "op", value: ch });
      i += 1;
      continue;
    }
    throw new Error("Unexpected character.");
  }
  tokens.push({ kind: "eof" });
  return insertImplicitMultiply(tokens);
}

function insertImplicitMultiply(tokens: Tok[]): Tok[] {
  const out: Tok[] = [];
  for (let i = 0; i < tokens.length; i += 1) {
    const prev = out[out.length - 1];
    const cur = tokens[i]!;
    if (prev && shouldMultiply(prev, cur)) out.push({ kind: "op", value: "*" });
    out.push(cur);
  }
  return out;
}

function shouldMultiply(prev: Tok, cur: Tok): boolean {
  const left = prev.kind === "num" || prev.kind === "rparen" || prev.kind === "bang" || prev.kind === "deg" || prev.kind === "id";
  const right = cur.kind === "num" || cur.kind === "lparen" || cur.kind === "id";
  if (!(left && right)) return false;
  if (prev.kind === "id" && cur.kind === "lparen") return false;
  return true;
}

function factorial(n: number): number {
  if (!Number.isFinite(n) || n < 0 || Math.abs(n - Math.round(n)) > 1e-9) {
    throw new Error("n! needs a whole number ≥ 0.");
  }
  const k = Math.round(n);
  if (k > 170) throw new Error("n! is too large.");
  let acc = 1;
  for (let i = 2; i <= k; i += 1) acc *= i;
  return acc;
}

function trig(name: string, x: number, mode: AngleMode): number {
  const radians = mode === "deg" ? (x * Math.PI) / 180 : x;
  if (name === "sin") return Math.sin(radians);
  if (name === "cos") return Math.cos(radians);
  const c = Math.cos(radians);
  if (Math.abs(c) < 1e-12) throw new Error("tan is undefined.");
  return Math.tan(radians);
}

class Parser {
  private i = 0;
  constructor(
    private tokens: Tok[],
    private mode: AngleMode,
  ) {}

  peek(): Tok {
    return this.tokens[this.i] || { kind: "eof" };
  }

  take(): Tok {
    const tok = this.peek();
    this.i += 1;
    return tok;
  }

  parse(): number {
    const value = this.expr();
    if (this.peek().kind !== "eof") throw new Error("Extra input.");
    return value;
  }

  expr(): number {
    let value = this.term();
    while (this.peek().kind === "op" && (this.peek() as { value: string }).value && "+-".includes((this.peek() as { kind: "op"; value: string }).value)) {
      const op = (this.take() as { kind: "op"; value: string }).value;
      const right = this.term();
      value = op === "+" ? value + right : value - right;
    }
    return value;
  }

  term(): number {
    let value = this.power();
    while (this.peek().kind === "op" && "*/".includes((this.peek() as { kind: "op"; value: string }).value || "")) {
      const op = (this.take() as { kind: "op"; value: string }).value;
      const right = this.power();
      if (op === "/" && right === 0) throw new Error("Division by zero.");
      value = op === "/" ? value / right : value * right;
    }
    return value;
  }

  power(): number {
    const value = this.unary();
    if (this.peek().kind === "op" && (this.peek() as { kind: "op"; value: string }).value === "^") {
      this.take();
      return value ** this.power();
    }
    return value;
  }

  unary(): number {
    if (this.peek().kind === "op" && (this.peek() as { kind: "op"; value: string }).value === "+") {
      this.take();
      return this.unary();
    }
    if (this.peek().kind === "op" && (this.peek() as { kind: "op"; value: string }).value === "-") {
      this.take();
      return -this.unary();
    }
    return this.postfix();
  }

  postfix(): number {
    let value = this.primary();
    for (;;) {
      if (this.peek().kind === "bang") {
        this.take();
        value = factorial(value);
        continue;
      }
      if (this.peek().kind === "deg") {
        this.take();
        if (this.mode === "rad") value = (value * Math.PI) / 180;
        continue;
      }
      if (this.peek().kind === "op" && (this.peek() as { kind: "op"; value: string }).value === "%") {
        this.take();
        value = value / 100;
        continue;
      }
      break;
    }
    return value;
  }

  primary(): number {
    const tok = this.peek();
    if (tok.kind === "num") {
      this.take();
      return tok.value;
    }
    if (tok.kind === "id") {
      this.take();
      const name = tok.value;
      if (name in CONSTANTS && this.peek().kind !== "lparen") return CONSTANTS[name]!;
      if (this.peek().kind === "lparen") {
        this.take();
        const arg = this.expr();
        if (this.peek().kind !== "rparen") throw new Error("Missing ).");
        this.take();
        return this.call(name, arg);
      }
      if (name in CONSTANTS) return CONSTANTS[name]!;
      throw new Error(`Unknown name: ${name}`);
    }
    if (tok.kind === "lparen") {
      this.take();
      const value = this.expr();
      if (this.peek().kind !== "rparen") throw new Error("Missing ).");
      this.take();
      return value;
    }
    throw new Error("Expected a number.");
  }

  call(name: string, arg: number): number {
    if (name === "sin" || name === "cos" || name === "tan") return trig(name, arg, this.mode);
    if (name === "sqrt") {
      if (arg < 0) throw new Error("sqrt of a negative.");
      return Math.sqrt(arg);
    }
    if (name === "log") {
      if (arg <= 0) throw new Error("log needs a positive number.");
      return Math.log10(arg);
    }
    if (name === "ln") {
      if (arg <= 0) throw new Error("ln needs a positive number.");
      return Math.log(arg);
    }
    if (name === "exp") return Math.exp(arg);
    if (name === "abs") return Math.abs(arg);
    if (name === "inv") {
      if (arg === 0) throw new Error("Division by zero.");
      return 1 / arg;
    }
    throw new Error(`Unknown function: ${name}`);
  }
}

export function evaluateExpression(raw: string, mode: AngleMode = "deg"): CalcResult {
  const source = (raw || "").trim();
  if (!source) return { ok: false, error: "Enter an expression." };
  if (looksLikeSchoolPaper(source)) {
    return { ok: false, error: "Paste one expression, not a paper." };
  }
  try {
    const value = new Parser(tokenize(source), mode).parse();
    if (!Number.isFinite(value)) return { ok: false, error: "Error" };
    return { ok: true, value, display: formatCalcNumber(value) };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : "Error" };
  }
}

export function pushCalcHistory(items: CalcHistoryItem[], next: CalcHistoryItem): CalcHistoryItem[] {
  return [next, ...items.filter((item) => item.expr !== next.expr || item.result !== next.result)].slice(0, CALC_HISTORY_MAX);
}
