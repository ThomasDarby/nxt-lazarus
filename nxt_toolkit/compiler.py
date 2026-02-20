"""Compiler for the NXT Toolkit DSL.

Pipeline: Source → Lexer → Parser → AST → NXCEmitter → .nxc text → nbc → .rxe

The DSL is a simplified Python-like language:

    # Obstacle Avoider
    forever:
        if ultrasonic(4) < 30:
            motor(B).off()
            motor(C).off()
            wait(1000)
        else:
            motor(B).on(75)
            motor(C).on(75)
        end
    end
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Union


# ─── Lexer ──────────────────────────────────────────────────────────────────

class TokenType:
    NUMBER   = "NUMBER"
    STRING   = "STRING"
    IDENT    = "IDENT"
    KEYWORD  = "KEYWORD"
    OP       = "OP"
    LPAREN   = "LPAREN"
    RPAREN   = "RPAREN"
    DOT      = "DOT"
    COLON    = "COLON"
    COMMA    = "COMMA"
    ASSIGN   = "ASSIGN"
    COMPARE  = "COMPARE"
    NEWLINE  = "NEWLINE"
    EOF      = "EOF"

KEYWORDS = {
    "if", "else", "end", "repeat", "forever", "and", "or", "not",
    "motor", "touch", "light", "sound", "ultrasonic",
    "on", "off", "coast",
    "play_tone", "display", "clear_screen", "wait",
    "A", "B", "C",
    "def",
}

@dataclass
class Token:
    type: str
    value: object
    line: int
    col: int


def lex(source: str) -> list[Token]:
    """Tokenize DSL source code into a list of tokens."""
    tokens = []
    lines = source.split("\n")

    for lineno, line in enumerate(lines, 1):
        col = 0
        # Strip comment
        comment_pos = line.find("#")
        if comment_pos >= 0:
            line = line[:comment_pos]
        line = line.rstrip()
        if not line.strip():
            continue

        i = 0
        while i < len(line):
            ch = line[i]

            # Whitespace
            if ch in " \t":
                i += 1
                continue

            # String literal
            if ch == '"':
                j = i + 1
                while j < len(line) and line[j] != '"':
                    j += 1
                if j >= len(line):
                    raise SyntaxError(f"Line {lineno}: unterminated string")
                tokens.append(Token(TokenType.STRING, line[i+1:j], lineno, i))
                i = j + 1
                continue

            # Number
            if ch.isdigit() or (ch == '-' and i + 1 < len(line) and line[i+1].isdigit()
                                and (not tokens or tokens[-1].type in
                                     (TokenType.OP, TokenType.LPAREN, TokenType.COMMA,
                                      TokenType.ASSIGN, TokenType.COMPARE, TokenType.COLON,
                                      TokenType.KEYWORD))):
                j = i + 1 if ch == '-' else i
                while j < len(line) and line[j].isdigit():
                    j += 1
                tokens.append(Token(TokenType.NUMBER, int(line[i:j]), lineno, i))
                i = j
                continue

            # Comparison operators (must check before single-char)
            if line[i:i+2] in ("==", "!=", "<=", ">="):
                tokens.append(Token(TokenType.COMPARE, line[i:i+2], lineno, i))
                i += 2
                continue
            if ch in "<>":
                tokens.append(Token(TokenType.COMPARE, ch, lineno, i))
                i += 1
                continue

            # Assignment
            if ch == "=" and (i + 1 >= len(line) or line[i+1] != "="):
                tokens.append(Token(TokenType.ASSIGN, "=", lineno, i))
                i += 1
                continue

            # Arithmetic operators
            if ch in "+-*/%":
                tokens.append(Token(TokenType.OP, ch, lineno, i))
                i += 1
                continue

            # Punctuation
            if ch == "(":
                tokens.append(Token(TokenType.LPAREN, "(", lineno, i))
                i += 1
                continue
            if ch == ")":
                tokens.append(Token(TokenType.RPAREN, ")", lineno, i))
                i += 1
                continue
            if ch == ".":
                tokens.append(Token(TokenType.DOT, ".", lineno, i))
                i += 1
                continue
            if ch == ":":
                tokens.append(Token(TokenType.COLON, ":", lineno, i))
                i += 1
                continue
            if ch == ",":
                tokens.append(Token(TokenType.COMMA, ",", lineno, i))
                i += 1
                continue

            # Identifiers and keywords
            if ch.isalpha() or ch == "_":
                j = i
                while j < len(line) and (line[j].isalnum() or line[j] == "_"):
                    j += 1
                word = line[i:j]
                if word in KEYWORDS:
                    tokens.append(Token(TokenType.KEYWORD, word, lineno, i))
                else:
                    tokens.append(Token(TokenType.IDENT, word, lineno, i))
                i = j
                continue

            raise SyntaxError(f"Line {lineno}, col {i}: unexpected character '{ch}'")

        tokens.append(Token(TokenType.NEWLINE, "\\n", lineno, len(line)))

    tokens.append(Token(TokenType.EOF, None, len(lines) + 1, 0))
    return tokens


# ─── AST Nodes ──────────────────────────────────────────────────────────────

@dataclass
class NumberLit:
    value: int

@dataclass
class StringLit:
    value: str

@dataclass
class VarRef:
    name: str

@dataclass
class BinOp:
    op: str  # +, -, *, /, %
    left: object
    right: object

@dataclass
class UnaryNeg:
    expr: object

@dataclass
class CompareExpr:
    op: str  # <, >, ==, !=, <=, >=
    left: object
    right: object

@dataclass
class SensorCall:
    sensor_type: str  # "touch", "light", "sound", "ultrasonic"
    port: int  # 1-4

@dataclass
class Assignment:
    name: str
    expr: object

@dataclass
class MotorOn:
    port: str  # "A", "B", "C"
    power: object  # expression

@dataclass
class MotorOff:
    port: str

@dataclass
class MotorCoast:
    port: str

@dataclass
class PlayTone:
    freq: object
    duration: object

@dataclass
class Display:
    text: object
    line: object

@dataclass
class ClearScreen:
    pass

@dataclass
class Wait:
    milliseconds: object

@dataclass
class IfElse:
    condition: object
    then_body: list
    else_body: list  # may be empty

@dataclass
class Repeat:
    count: object
    body: list

@dataclass
class Forever:
    body: list

@dataclass
class FuncDef:
    name: str
    params: list  # parameter names (strings)
    body: list

@dataclass
class FuncCallStmt:
    name: str
    args: list  # expression nodes


# ─── Parser ─────────────────────────────────────────────────────────────────

class Parser:
    """Recursive descent parser for the NXT DSL."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def error(self, msg):
        tok = self.peek()
        raise SyntaxError(f"Line {tok.line}: {msg} (got {tok.type} '{tok.value}')")

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def skip_newlines(self):
        while self.peek().type == TokenType.NEWLINE:
            self.advance()

    def expect(self, type_, value=None):
        tok = self.advance()
        if tok.type != type_:
            raise SyntaxError(
                f"Line {tok.line}: expected {type_}"
                f"{' ' + repr(value) if value else ''}, "
                f"got {tok.type} '{tok.value}'")
        if value is not None and tok.value != value:
            raise SyntaxError(
                f"Line {tok.line}: expected '{value}', got '{tok.value}'")
        return tok

    def parse(self):
        """Parse the entire program into function definitions and main statements.

        Returns:
            (func_defs, main_stmts) — function definitions are collected
            separately so they can be compiled as separate clumps.
        """
        self.skip_newlines()
        func_defs = []
        main_stmts = []
        while True:
            self.skip_newlines()
            tok = self.peek()
            if tok.type == TokenType.EOF:
                break
            if tok.type == TokenType.KEYWORD and tok.value == "def":
                func_defs.append(self.parse_func_def())
            else:
                main_stmts.append(self.parse_statement())
        return func_defs, main_stmts

    def parse_body(self, top_level=False) -> list:
        """Parse statements until 'end', 'else', or EOF."""
        stmts = []
        while True:
            self.skip_newlines()
            tok = self.peek()
            if tok.type == TokenType.EOF:
                if not top_level:
                    raise SyntaxError(f"Line {tok.line}: unexpected end of file (missing 'end'?)")
                break
            if tok.type == TokenType.KEYWORD and tok.value in ("end", "else"):
                break
            stmts.append(self.parse_statement())
        return stmts

    def parse_statement(self):
        tok = self.peek()

        # forever:
        if tok.type == TokenType.KEYWORD and tok.value == "forever":
            return self.parse_forever()

        # repeat N:
        if tok.type == TokenType.KEYWORD and tok.value == "repeat":
            return self.parse_repeat()

        # if COND:
        if tok.type == TokenType.KEYWORD and tok.value == "if":
            return self.parse_if()

        # motor(X).on(power) / motor(X).off() / motor(X).coast()
        if tok.type == TokenType.KEYWORD and tok.value == "motor":
            return self.parse_motor()

        # play_tone(freq, dur)
        if tok.type == TokenType.KEYWORD and tok.value == "play_tone":
            return self.parse_play_tone()

        # display(text, line)
        if tok.type == TokenType.KEYWORD and tok.value == "display":
            return self.parse_display()

        # clear_screen()
        if tok.type == TokenType.KEYWORD and tok.value == "clear_screen":
            return self.parse_clear_screen()

        # wait(ms)
        if tok.type == TokenType.KEYWORD and tok.value == "wait":
            return self.parse_wait()

        # Function call or assignment: name(...) vs name = expr
        if tok.type == TokenType.IDENT:
            # Look ahead: LPAREN means function call, ASSIGN means assignment
            next_tok = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            if next_tok and next_tok.type == TokenType.LPAREN:
                return self.parse_func_call_stmt()
            return self.parse_assignment()

        self.error("unexpected token")

    def parse_forever(self):
        self.expect(TokenType.KEYWORD, "forever")
        self.expect(TokenType.COLON)
        self.skip_newlines()
        body = self.parse_body()
        self.expect(TokenType.KEYWORD, "end")
        return Forever(body=body)

    def parse_repeat(self):
        self.expect(TokenType.KEYWORD, "repeat")
        count = self.parse_expr()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        body = self.parse_body()
        self.expect(TokenType.KEYWORD, "end")
        return Repeat(count=count, body=body)

    def parse_if(self):
        self.expect(TokenType.KEYWORD, "if")
        cond = self.parse_condition()
        self.expect(TokenType.COLON)
        self.skip_newlines()
        then_body = self.parse_body()
        else_body = []
        if self.peek().type == TokenType.KEYWORD and self.peek().value == "else":
            self.advance()  # consume 'else'
            # Optional colon after else
            if self.peek().type == TokenType.COLON:
                self.advance()
            self.skip_newlines()
            else_body = self.parse_body()
        self.expect(TokenType.KEYWORD, "end")
        return IfElse(condition=cond, then_body=then_body, else_body=else_body)

    def parse_motor(self):
        self.expect(TokenType.KEYWORD, "motor")
        self.expect(TokenType.LPAREN)
        port_tok = self.expect(TokenType.KEYWORD)
        if port_tok.value not in ("A", "B", "C"):
            raise SyntaxError(f"Line {port_tok.line}: invalid motor port '{port_tok.value}'")
        port = port_tok.value
        self.expect(TokenType.RPAREN)
        self.expect(TokenType.DOT)
        method_tok = self.advance()
        if method_tok.type != TokenType.KEYWORD or method_tok.value not in ("on", "off", "coast"):
            raise SyntaxError(
                f"Line {method_tok.line}: expected 'on', 'off', or 'coast', "
                f"got '{method_tok.value}'")

        if method_tok.value == "on":
            self.expect(TokenType.LPAREN)
            power = self.parse_expr()
            self.expect(TokenType.RPAREN)
            return MotorOn(port=port, power=power)
        else:
            self.expect(TokenType.LPAREN)
            self.expect(TokenType.RPAREN)
            if method_tok.value == "off":
                return MotorOff(port=port)
            else:
                return MotorCoast(port=port)

    def parse_play_tone(self):
        self.expect(TokenType.KEYWORD, "play_tone")
        self.expect(TokenType.LPAREN)
        freq = self.parse_expr()
        self.expect(TokenType.COMMA)
        dur = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return PlayTone(freq=freq, duration=dur)

    def parse_display(self):
        self.expect(TokenType.KEYWORD, "display")
        self.expect(TokenType.LPAREN)
        text = self.parse_expr()
        self.expect(TokenType.COMMA)
        line = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return Display(text=text, line=line)

    def parse_clear_screen(self):
        self.expect(TokenType.KEYWORD, "clear_screen")
        self.expect(TokenType.LPAREN)
        self.expect(TokenType.RPAREN)
        return ClearScreen()

    def parse_wait(self):
        self.expect(TokenType.KEYWORD, "wait")
        self.expect(TokenType.LPAREN)
        ms = self.parse_expr()
        self.expect(TokenType.RPAREN)
        return Wait(milliseconds=ms)

    def parse_assignment(self):
        name_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.ASSIGN)
        expr = self.parse_expr()
        return Assignment(name=name_tok.value, expr=expr)

    def parse_func_def(self):
        """Parse: def name(param1, param2): ... end  (or def name: ... end)"""
        self.expect(TokenType.KEYWORD, "def")
        name_tok = self.expect(TokenType.IDENT)
        params = []
        if self.peek().type == TokenType.LPAREN:
            self.advance()  # consume (
            if self.peek().type != TokenType.RPAREN:
                param_tok = self.expect(TokenType.IDENT)
                params.append(param_tok.value)
                while self.peek().type == TokenType.COMMA:
                    self.advance()  # consume ,
                    param_tok = self.expect(TokenType.IDENT)
                    params.append(param_tok.value)
            self.expect(TokenType.RPAREN)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        body = self.parse_body()
        self.expect(TokenType.KEYWORD, "end")
        return FuncDef(name=name_tok.value, params=params, body=body)

    def parse_func_call_stmt(self):
        """Parse: name(arg1, arg2, ...)"""
        name_tok = self.expect(TokenType.IDENT)
        self.expect(TokenType.LPAREN)
        args = []
        if self.peek().type != TokenType.RPAREN:
            args.append(self.parse_expr())
            while self.peek().type == TokenType.COMMA:
                self.advance()
                args.append(self.parse_expr())
        self.expect(TokenType.RPAREN)
        return FuncCallStmt(name=name_tok.value, args=args)

    def parse_condition(self):
        """Parse a comparison expression: expr (< | > | == | != | <= | >=) expr"""
        left = self.parse_expr()
        tok = self.peek()
        if tok.type != TokenType.COMPARE:
            self.error("expected comparison operator")
        op = self.advance().value
        right = self.parse_expr()
        return CompareExpr(op=op, left=left, right=right)

    def parse_expr(self):
        """Parse an arithmetic expression: term ((+ | -) term)*"""
        left = self.parse_term()
        while self.peek().type == TokenType.OP and self.peek().value in ("+", "-"):
            op = self.advance().value
            right = self.parse_term()
            left = BinOp(op=op, left=left, right=right)
        return left

    def parse_term(self):
        """Parse: factor ((* | / | %) factor)*"""
        left = self.parse_factor()
        while self.peek().type == TokenType.OP and self.peek().value in ("*", "/", "%"):
            op = self.advance().value
            right = self.parse_factor()
            left = BinOp(op=op, left=left, right=right)
        return left

    def parse_factor(self):
        """Parse: number | string | variable | sensor_call | (expr) | -factor"""
        tok = self.peek()

        if tok.type == TokenType.NUMBER:
            self.advance()
            return NumberLit(value=tok.value)

        if tok.type == TokenType.STRING:
            self.advance()
            return StringLit(value=tok.value)

        if tok.type == TokenType.LPAREN:
            self.advance()
            expr = self.parse_expr()
            self.expect(TokenType.RPAREN)
            return expr

        if tok.type == TokenType.OP and tok.value == "-":
            self.advance()
            inner = self.parse_factor()
            if isinstance(inner, NumberLit):
                return NumberLit(value=-inner.value)
            return UnaryNeg(expr=inner)

        # Sensor calls: touch(port), light(port), sound(port), ultrasonic(port)
        if tok.type == TokenType.KEYWORD and tok.value in ("touch", "light", "sound", "ultrasonic"):
            return self.parse_sensor_call()

        if tok.type == TokenType.IDENT:
            self.advance()
            return VarRef(name=tok.value)

        self.error("expected expression")

    def parse_sensor_call(self):
        sensor_tok = self.advance()
        self.expect(TokenType.LPAREN)
        port_tok = self.expect(TokenType.NUMBER)
        port = port_tok.value
        if port < 1 or port > 4:
            raise SyntaxError(f"Line {port_tok.line}: sensor port must be 1-4, got {port}")
        self.expect(TokenType.RPAREN)
        return SensorCall(sensor_type=sensor_tok.value, port=port)


# ─── NXC Emitter ─────────────────────────────────────────────────────────────

class NXCEmitter:
    """Walk the AST and emit NXC (Not eXactly C) source code."""

    LCD_LINES = {
        1: "LCD_LINE1", 2: "LCD_LINE2", 3: "LCD_LINE3", 4: "LCD_LINE4",
        5: "LCD_LINE5", 6: "LCD_LINE6", 7: "LCD_LINE7", 8: "LCD_LINE8",
    }

    MOTOR_PORTS = {"A": "OUT_A", "B": "OUT_B", "C": "OUT_C"}

    SENSOR_PORTS = {1: "IN_1", 2: "IN_2", 3: "IN_3", 4: "IN_4"}

    def emit(self, func_defs: list, main_stmts: list) -> str:
        """Emit a complete NXC source file from parsed AST."""
        self._variables: set[str] = set()
        self._sensors: dict[tuple[str, int], None] = {}  # (type, port) → None
        self._func_params: dict[str, list[str]] = {}
        self._lines: list[str] = []

        # Register function parameter names so prescan doesn't treat them as globals
        for fdef in func_defs:
            self._func_params[fdef.name] = fdef.params

        # Pre-scan to collect variables and sensors used
        for fdef in func_defs:
            self._prescan_stmts(fdef.body, exclude_vars=set(fdef.params))
        self._prescan_stmts(main_stmts)

        # Emit function definitions
        for fdef in func_defs:
            self._emit_func_def(fdef)
            self._lines.append("")

        # Emit task main
        self._lines.append("task main() {")

        # Sensor setup at top of main
        for sensor_type, port in self._sensors:
            nxc_port = self.SENSOR_PORTS[port]
            if sensor_type == "touch":
                self._lines.append(f"  SetSensorTouch({nxc_port});")
            elif sensor_type == "light":
                self._lines.append(f"  SetSensorLight({nxc_port});")
            elif sensor_type == "sound":
                self._lines.append(f"  SetSensorSound({nxc_port});")
            elif sensor_type == "ultrasonic":
                self._lines.append(f"  SetSensorLowspeed({nxc_port});")

        # Variable declarations at top of main
        for var in sorted(self._variables):
            self._lines.append(f"  int {var};")

        if self._sensors or self._variables:
            self._lines.append("")

        # Main body statements
        for stmt in main_stmts:
            self._emit_stmt(stmt, indent=1)

        self._lines.append("}")
        return "\n".join(self._lines) + "\n"

    # ── Pre-scan ─────────────────────────────────────────────────────────

    def _prescan_stmts(self, stmts: list, exclude_vars: set[str] | None = None):
        """Walk statements to collect variable names and sensor ports."""
        for stmt in stmts:
            self._prescan_node(stmt, exclude_vars or set())

    def _prescan_node(self, node, exclude_vars: set[str]):
        if isinstance(node, Assignment):
            if node.name not in exclude_vars:
                self._variables.add(node.name)
            self._prescan_node(node.expr, exclude_vars)
        elif isinstance(node, SensorCall):
            self._sensors[(node.sensor_type, node.port)] = None
        elif isinstance(node, BinOp):
            self._prescan_node(node.left, exclude_vars)
            self._prescan_node(node.right, exclude_vars)
        elif isinstance(node, UnaryNeg):
            self._prescan_node(node.expr, exclude_vars)
        elif isinstance(node, CompareExpr):
            self._prescan_node(node.left, exclude_vars)
            self._prescan_node(node.right, exclude_vars)
        elif isinstance(node, MotorOn):
            self._prescan_node(node.power, exclude_vars)
        elif isinstance(node, PlayTone):
            self._prescan_node(node.freq, exclude_vars)
            self._prescan_node(node.duration, exclude_vars)
        elif isinstance(node, Display):
            self._prescan_node(node.text, exclude_vars)
            self._prescan_node(node.line, exclude_vars)
        elif isinstance(node, Wait):
            self._prescan_node(node.milliseconds, exclude_vars)
        elif isinstance(node, IfElse):
            self._prescan_node(node.condition, exclude_vars)
            for s in node.then_body:
                self._prescan_node(s, exclude_vars)
            for s in node.else_body:
                self._prescan_node(s, exclude_vars)
        elif isinstance(node, Repeat):
            self._prescan_node(node.count, exclude_vars)
            for s in node.body:
                self._prescan_node(s, exclude_vars)
        elif isinstance(node, Forever):
            for s in node.body:
                self._prescan_node(s, exclude_vars)
        elif isinstance(node, FuncCallStmt):
            for arg in node.args:
                self._prescan_node(arg, exclude_vars)

    # ── Expression emission ──────────────────────────────────────────────

    def _emit_expr(self, node) -> str:
        """Recursively convert an expression AST node to an NXC string."""
        if isinstance(node, NumberLit):
            return str(node.value)
        if isinstance(node, StringLit):
            escaped = node.value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        if isinstance(node, VarRef):
            return node.name
        if isinstance(node, UnaryNeg):
            return f"(-{self._emit_expr(node.expr)})"
        if isinstance(node, BinOp):
            left = self._emit_expr(node.left)
            right = self._emit_expr(node.right)
            return f"({left} {node.op} {right})"
        if isinstance(node, SensorCall):
            nxc_port = self.SENSOR_PORTS[node.port]
            if node.sensor_type == "ultrasonic":
                return f"SensorUS({nxc_port})"
            return f"Sensor({nxc_port})"
        raise ValueError(f"Unknown expression node: {type(node).__name__}")

    # ── Statement emission ───────────────────────────────────────────────

    def _emit_stmt(self, stmt, indent: int = 0):
        """Emit NXC lines for a statement."""
        pad = "  " * indent

        if isinstance(stmt, Assignment):
            expr = self._emit_expr(stmt.expr)
            self._lines.append(f"{pad}{stmt.name} = {expr};")

        elif isinstance(stmt, MotorOn):
            port = self.MOTOR_PORTS[stmt.port]
            power = self._emit_expr(stmt.power)
            self._lines.append(f"{pad}OnFwd({port}, {power});")

        elif isinstance(stmt, MotorOff):
            port = self.MOTOR_PORTS[stmt.port]
            self._lines.append(f"{pad}Off({port});")

        elif isinstance(stmt, MotorCoast):
            port = self.MOTOR_PORTS[stmt.port]
            self._lines.append(f"{pad}Float({port});")

        elif isinstance(stmt, PlayTone):
            freq = self._emit_expr(stmt.freq)
            dur = self._emit_expr(stmt.duration)
            self._lines.append(f"{pad}PlayTone({freq}, {dur});")

        elif isinstance(stmt, Display):
            text = self._emit_expr(stmt.text)
            line_expr = stmt.line
            # If the line is a constant, use the LCD_LINE constant directly
            if isinstance(line_expr, NumberLit) and line_expr.value in self.LCD_LINES:
                lcd_line = self.LCD_LINES[line_expr.value]
                self._lines.append(f"{pad}TextOut(0, {lcd_line}, {text});")
            else:
                # Compute Y from line number: (8 - line) * 8
                line_val = self._emit_expr(line_expr)
                self._lines.append(f"{pad}TextOut(0, (8 - {line_val}) * 8, {text});")

        elif isinstance(stmt, ClearScreen):
            self._lines.append(f"{pad}ClearScreen();")

        elif isinstance(stmt, Wait):
            ms = self._emit_expr(stmt.milliseconds)
            self._lines.append(f"{pad}Wait({ms});")

        elif isinstance(stmt, IfElse):
            cond = self._emit_condition(stmt.condition)
            self._lines.append(f"{pad}if ({cond}) {{")
            for s in stmt.then_body:
                self._emit_stmt(s, indent + 1)
            if stmt.else_body:
                self._lines.append(f"{pad}}} else {{")
                for s in stmt.else_body:
                    self._emit_stmt(s, indent + 1)
            self._lines.append(f"{pad}}}")

        elif isinstance(stmt, Repeat):
            count = self._emit_expr(stmt.count)
            self._lines.append(f"{pad}repeat({count}) {{")
            for s in stmt.body:
                self._emit_stmt(s, indent + 1)
            self._lines.append(f"{pad}}}")

        elif isinstance(stmt, Forever):
            self._lines.append(f"{pad}while(true) {{")
            for s in stmt.body:
                self._emit_stmt(s, indent + 1)
            self._lines.append(f"{pad}}}")

        elif isinstance(stmt, FuncCallStmt):
            args = ", ".join(self._emit_expr(a) for a in stmt.args)
            self._lines.append(f"{pad}{stmt.name}({args});")

        else:
            raise ValueError(f"Unknown statement: {type(stmt).__name__}")

    def _emit_condition(self, node) -> str:
        """Emit a comparison expression as an NXC condition string."""
        if isinstance(node, CompareExpr):
            left = self._emit_expr(node.left)
            right = self._emit_expr(node.right)
            return f"{left} {node.op} {right}"
        raise ValueError("Condition must be a CompareExpr")

    # ── Function definition ──────────────────────────────────────────────

    def _emit_func_def(self, fdef: FuncDef):
        """Emit an NXC function (sub/void) definition."""
        params = ", ".join(f"int {p}" for p in fdef.params)
        self._lines.append(f"void {fdef.name}({params}) {{")
        for stmt in fdef.body:
            self._emit_stmt(stmt, indent=1)
        self._lines.append("}")


# ─── nbc Integration ────────────────────────────────────────────────────────

class CompileError(Exception):
    """Raised when the nbc compiler fails or is not found."""
    pass


def _find_nbc() -> str:
    """Locate the nbc compiler binary.

    Search order:
    1. NBC_PATH environment variable
    2. Bundled with the app (PyInstaller or next to compiler.py)
    3. System PATH
    """
    # 1. Environment variable
    env_path = os.environ.get("NBC_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2. Bundled with app — check PyInstaller _MEIPASS and project-relative paths
    search_dirs = []

    # PyInstaller bundle
    meipass = getattr(__import__("sys"), "_MEIPASS", None)
    if meipass:
        search_dirs.append(meipass)

    # Next to this file (development mode)
    this_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs.append(os.path.join(this_dir, os.pardir))  # project root
    search_dirs.append(this_dir)

    for d in search_dirs:
        candidate = os.path.join(d, "nbc")
        if os.path.isfile(candidate):
            return candidate

    # 3. System PATH
    system_nbc = shutil.which("nbc")
    if system_nbc:
        return system_nbc

    raise CompileError(
        "nbc compiler not found. Install it or set NBC_PATH environment variable."
    )


def _find_nbc_include() -> str:
    """Locate the nbc include directory (containing NXCDefs.h)."""
    # Check next to the nbc binary first
    try:
        nbc_path = _find_nbc()
    except CompileError:
        nbc_path = None

    search_dirs = []

    if nbc_path:
        search_dirs.append(os.path.dirname(nbc_path))

    # PyInstaller bundle
    meipass = getattr(__import__("sys"), "_MEIPASS", None)
    if meipass:
        search_dirs.append(os.path.join(meipass, "nbc_include"))
        search_dirs.append(meipass)

    # Next to this file (development mode)
    this_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs.append(os.path.join(this_dir, os.pardir, "nbc_include"))
    search_dirs.append(os.path.join(this_dir, "nbc_include"))

    # System-wide
    search_dirs.append("/usr/local/include/nbc")

    for d in search_dirs:
        candidate = os.path.join(d, "NXCDefs.h")
        if os.path.isfile(candidate):
            return d

    raise CompileError(
        "NXC include files (NXCDefs.h) not found. "
        "Ensure nbc_include/ is present next to the nbc binary."
    )


def _run_nbc(nxc_source: str, output_path: str):
    """Write NXC source to a temp file and compile it with nbc.

    Raises:
        CompileError: If nbc fails or is not found.
    """
    nbc_path = _find_nbc()
    include_dir = _find_nbc_include()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".nxc", delete=False
    ) as f:
        f.write(nxc_source)
        nxc_path = f.name

    try:
        result = subprocess.run(
            [nbc_path, nxc_path, f"-O={output_path}", f"-I={include_dir}",
             "-v=105"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            # Extract error lines from stderr/stdout (nbc writes to stdout)
            error_output = result.stderr or result.stdout or "Unknown error"
            # Filter out status lines to show only errors
            error_lines = [
                line for line in error_output.splitlines()
                if not line.startswith("# Status:")
            ]
            error_msg = "\n".join(error_lines).strip()
            if not error_msg:
                error_msg = error_output.strip()
            raise CompileError(f"nbc compilation failed:\n{error_msg}")
    except FileNotFoundError:
        raise CompileError(f"nbc compiler not found at: {nbc_path}")
    except subprocess.TimeoutExpired:
        raise CompileError("nbc compilation timed out (30s)")
    finally:
        os.unlink(nxc_path)


# ─── Public API ─────────────────────────────────────────────────────────────

def compile_source(source: str, output_path: str) -> str:
    """Compile NXT DSL source code to an .rxe file.

    Pipeline: DSL → Lexer → Parser → AST → NXCEmitter → .nxc → nbc → .rxe

    Args:
        source: The DSL source code string.
        output_path: Path to write the .rxe file.

    Returns:
        The output path.

    Raises:
        SyntaxError: If the DSL source has syntax errors.
        CompileError: If NXC compilation (nbc) fails.
    """
    tokens = lex(source)
    parser = Parser(tokens)
    func_defs, main_stmts = parser.parse()

    emitter = NXCEmitter()
    nxc_source = emitter.emit(func_defs, main_stmts)
    _run_nbc(nxc_source, output_path)

    return output_path
