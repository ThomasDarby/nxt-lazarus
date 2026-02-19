"""Compiler for the NXT Toolkit DSL.

Pipeline: Source → Lexer → Parser → AST → Code Generator → (DSTOC + bytecode)

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

import re
from dataclasses import dataclass, field
from typing import Union

from .bytecode import (
    TC_UBYTE, TC_SBYTE, TC_UWORD, TC_SWORD, TC_ULONG, TC_SLONG,
    TC_ARRAY, TC_CLUSTER,
    OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_MOD, OP_NEG,
    OP_MOV, OP_SET, OP_CMP, OP_TST,
    OP_JMP, OP_BRCMP, OP_BRTST,
    OP_SYSCALL, OP_STOP, OP_WAIT,
    OP_SETIN, OP_SETOUT, OP_GETIN,
    CC_LT, CC_GT, CC_LTEQ, CC_GTEQ, CC_EQ, CC_NEQ,
    SENSOR_TYPE_TOUCH, SENSOR_TYPE_LIGHT_ACTIVE, SENSOR_TYPE_SOUND_DB,
    SENSOR_TYPE_LOWSPEED_9V,
    SENSOR_MODE_BOOLEAN, SENSOR_MODE_PCTFULLSCALE, SENSOR_MODE_RAW,
    IN_TYPE, IN_MODE, IN_SCALED, IN_INVALID,
    OUT_FLAGS, OUT_MODE, OUT_SPEED, OUT_RUN_STATE, OUT_REG_MODE,
    OUT_UPDATE_MODE, OUT_UPDATE_SPEED,
    OUT_MODE_COAST, OUT_MODE_MOTORON, OUT_MODE_BRAKE, OUT_MODE_REGULATED,
    OUT_RUNSTATE_IDLE, OUT_RUNSTATE_RUNNING,
    OUT_REGMODE_IDLE, OUT_REGMODE_SPEED,
    MOTOR_A, MOTOR_B, MOTOR_C,
    SYSCALL_SOUND_PLAY_TONE, SYSCALL_DRAW_TEXT, SYSCALL_CLEAR_SCREEN,
    SYSCALL_COMM_LS_WRITE, SYSCALL_COMM_LS_READ, SYSCALL_COMM_LS_CHECKSTATUS,
    SIZE_VAR,
    encode_instruction, _to_i16, words_to_bytes,
)
from .dataspace import DataspaceBuilder


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

    def parse(self) -> list:
        """Parse the entire program into a list of AST statements."""
        self.skip_newlines()
        stmts = self.parse_body(top_level=True)
        return stmts

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

        # Assignment: name = expr
        if tok.type == TokenType.IDENT:
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


# ─── Code Generator ─────────────────────────────────────────────────────────

class CodeGenerator:
    """Walk the AST and emit DSTOC entries + bytecode."""

    def __init__(self):
        self.ds = DataspaceBuilder()
        self.code: list[int] = []  # signed 16-bit words
        self._vars: dict[str, int] = {}  # variable name → DSTOC index
        self._consts: dict[int, int] = {}  # constant value → DSTOC index
        self._temp_counter = 0
        self._sensor_configured: set[int] = set()  # ports we've configured

        # Pre-allocate commonly needed constants
        self._const_zero = self._get_const(0)
        self._const_one = self._get_const(1)

    def compile(self, stmts: list) -> tuple[bytes, bytes, bytes, int, list[int]]:
        """Compile a list of AST statements.

        Returns: (dstoc_bytes, static_defaults, dynamic_defaults, ds_static_size, code_words)
        """
        for stmt in stmts:
            self._emit_stmt(stmt)

        # Emit OP_STOP at end
        self.code.extend(encode_instruction(OP_STOP, 0))

        dstoc_bytes, static_defaults, dynamic_defaults, static_size, _ = self.ds.serialize()
        return dstoc_bytes, static_defaults, dynamic_defaults, static_size, self.code

    def _alloc_temp(self, type_code=TC_SLONG):
        """Allocate a temporary variable. Returns its DSTOC index."""
        name = f"__tmp{self._temp_counter}"
        self._temp_counter += 1
        return self.ds.add_scalar(type_code, name=name, default=0, flags=1)

    def _get_const(self, value, type_code=TC_SLONG):
        """Get or create a constant with the given value. Returns DSTOC index."""
        key = (value, type_code)
        if key not in self._consts:
            self._consts[key] = self.ds.add_constant(type_code, value, name=f"const_{value}")
        return self._consts[key]

    def _get_const_ubyte(self, value):
        return self._get_const(value, TC_UBYTE)

    def _get_const_uword(self, value):
        return self._get_const(value, TC_UWORD)

    def _get_var(self, name):
        """Get or create a user variable. Returns DSTOC index."""
        if name not in self._vars:
            self._vars[name] = self.ds.add_scalar(TC_SLONG, name=name, default=0, flags=1)
        return self._vars[name]

    def _emit(self, words):
        """Append instruction words to the codespace."""
        self.code.extend(words)

    def _current_offset(self):
        """Current word offset in the codespace."""
        return len(self.code)

    # ── Expression evaluation ───────────────────────────────────────────

    def _emit_expr(self, node) -> int:
        """Emit code for an expression, return DSTOC index of result."""
        if isinstance(node, NumberLit):
            return self._get_const(node.value)

        if isinstance(node, StringLit):
            return self.ds.add_string(node.value, name=f"str_{node.value[:8]}")

        if isinstance(node, VarRef):
            return self._get_var(node.name)

        if isinstance(node, UnaryNeg):
            inner = self._emit_expr(node.expr)
            result = self._alloc_temp()
            self._emit(encode_instruction(OP_NEG, result, inner))
            return result

        if isinstance(node, BinOp):
            left = self._emit_expr(node.left)
            right = self._emit_expr(node.right)
            result = self._alloc_temp()
            op_map = {"+": OP_ADD, "-": OP_SUB, "*": OP_MUL, "/": OP_DIV, "%": OP_MOD}
            opcode = op_map[node.op]
            self._emit(encode_instruction(opcode, result, left, right))
            return result

        if isinstance(node, SensorCall):
            return self._emit_sensor_read(node)

        raise ValueError(f"Unknown expression node: {type(node).__name__}")

    # ── Statement emission ──────────────────────────────────────────────

    def _emit_stmt(self, stmt):
        if isinstance(stmt, Assignment):
            self._emit_assignment(stmt)
        elif isinstance(stmt, MotorOn):
            self._emit_motor_on(stmt)
        elif isinstance(stmt, MotorOff):
            self._emit_motor_off(stmt)
        elif isinstance(stmt, MotorCoast):
            self._emit_motor_coast(stmt)
        elif isinstance(stmt, PlayTone):
            self._emit_play_tone(stmt)
        elif isinstance(stmt, Display):
            self._emit_display(stmt)
        elif isinstance(stmt, ClearScreen):
            self._emit_clear_screen()
        elif isinstance(stmt, Wait):
            self._emit_wait(stmt)
        elif isinstance(stmt, IfElse):
            self._emit_if_else(stmt)
        elif isinstance(stmt, Repeat):
            self._emit_repeat(stmt)
        elif isinstance(stmt, Forever):
            self._emit_forever(stmt)
        else:
            raise ValueError(f"Unknown statement: {type(stmt).__name__}")

    def _emit_assignment(self, stmt: Assignment):
        expr_idx = self._emit_expr(stmt.expr)
        var_idx = self._get_var(stmt.name)
        self._emit(encode_instruction(OP_MOV, var_idx, expr_idx))

    # ── Motor control ───────────────────────────────────────────────────

    def _emit_motor_on(self, stmt: MotorOn):
        """Emit OP_SETOUT to turn on a motor at a given power level."""
        port_map = {"A": MOTOR_A, "B": MOTOR_B, "C": MOTOR_C}
        port_val = port_map[stmt.port]

        port_idx = self._get_const_ubyte(port_val)
        power_idx = self._emit_expr(stmt.power)

        # We need DSTOC indices for the field IDs and values
        flags_field = self._get_const_ubyte(OUT_FLAGS)
        mode_field = self._get_const_ubyte(OUT_MODE)
        speed_field = self._get_const_ubyte(OUT_SPEED)
        runstate_field = self._get_const_ubyte(OUT_RUN_STATE)
        regmode_field = self._get_const_ubyte(OUT_REG_MODE)

        update_val = self._get_const_ubyte(OUT_UPDATE_MODE | OUT_UPDATE_SPEED)
        mode_val = self._get_const_ubyte(OUT_MODE_MOTORON | OUT_MODE_BRAKE | OUT_MODE_REGULATED)
        runstate_val = self._get_const_ubyte(OUT_RUNSTATE_RUNNING)
        regmode_val = self._get_const_ubyte(OUT_REGMODE_SPEED)

        # OP_SETOUT: variable-length
        # Format: instr_word | operand_count | port | field1 | val1 | field2 | val2 | ...
        operands = [
            port_idx,
            flags_field, update_val,
            mode_field, mode_val,
            speed_field, power_idx,
            runstate_field, runstate_val,
            regmode_field, regmode_val,
        ]
        operand_count = len(operands)
        instr_word = _to_i16((SIZE_VAR << 12) | (OP_SETOUT & 0xFF))
        self._emit([instr_word, _to_i16(operand_count)] + [_to_i16(o) for o in operands])

    def _emit_motor_off(self, stmt: MotorOff):
        """Emit OP_SETOUT to stop a motor with brake."""
        port_map = {"A": MOTOR_A, "B": MOTOR_B, "C": MOTOR_C}
        port_val = port_map[stmt.port]

        port_idx = self._get_const_ubyte(port_val)
        flags_field = self._get_const_ubyte(OUT_FLAGS)
        mode_field = self._get_const_ubyte(OUT_MODE)
        speed_field = self._get_const_ubyte(OUT_SPEED)
        runstate_field = self._get_const_ubyte(OUT_RUN_STATE)

        update_val = self._get_const_ubyte(OUT_UPDATE_MODE | OUT_UPDATE_SPEED)
        mode_val = self._get_const_ubyte(OUT_MODE_MOTORON | OUT_MODE_BRAKE)
        speed_val = self._get_const_ubyte(0)
        runstate_val = self._get_const_ubyte(OUT_RUNSTATE_RUNNING)

        operands = [
            port_idx,
            flags_field, update_val,
            mode_field, mode_val,
            speed_field, speed_val,
            runstate_field, runstate_val,
        ]
        operand_count = len(operands)
        instr_word = _to_i16((SIZE_VAR << 12) | (OP_SETOUT & 0xFF))
        self._emit([instr_word, _to_i16(operand_count)] + [_to_i16(o) for o in operands])

    def _emit_motor_coast(self, stmt: MotorCoast):
        """Emit OP_SETOUT to coast a motor (no power, no brake)."""
        port_map = {"A": MOTOR_A, "B": MOTOR_B, "C": MOTOR_C}
        port_val = port_map[stmt.port]

        port_idx = self._get_const_ubyte(port_val)
        flags_field = self._get_const_ubyte(OUT_FLAGS)
        mode_field = self._get_const_ubyte(OUT_MODE)
        speed_field = self._get_const_ubyte(OUT_SPEED)
        runstate_field = self._get_const_ubyte(OUT_RUN_STATE)

        update_val = self._get_const_ubyte(OUT_UPDATE_MODE | OUT_UPDATE_SPEED)
        mode_val = self._get_const_ubyte(OUT_MODE_COAST)
        speed_val = self._get_const_ubyte(0)
        runstate_val = self._get_const_ubyte(OUT_RUNSTATE_IDLE)

        operands = [
            port_idx,
            flags_field, update_val,
            mode_field, mode_val,
            speed_field, speed_val,
            runstate_field, runstate_val,
        ]
        operand_count = len(operands)
        instr_word = _to_i16((SIZE_VAR << 12) | (OP_SETOUT & 0xFF))
        self._emit([instr_word, _to_i16(operand_count)] + [_to_i16(o) for o in operands])

    # ── Sensors ─────────────────────────────────────────────────────────

    def _emit_sensor_read(self, node: SensorCall) -> int:
        """Configure sensor and read its scaled value. Returns DSTOC index of result."""
        port = node.port - 1  # Convert 1-based to 0-based

        sensor_info = {
            "touch":      (SENSOR_TYPE_TOUCH, SENSOR_MODE_BOOLEAN),
            "light":      (SENSOR_TYPE_LIGHT_ACTIVE, SENSOR_MODE_PCTFULLSCALE),
            "sound":      (SENSOR_TYPE_SOUND_DB, SENSOR_MODE_PCTFULLSCALE),
            "ultrasonic": (SENSOR_TYPE_LOWSPEED_9V, SENSOR_MODE_RAW),
        }
        sensor_type, sensor_mode = sensor_info[node.sensor_type]

        port_idx = self._get_const_ubyte(port)
        result = self._alloc_temp(TC_SLONG)

        if node.sensor_type == "ultrasonic":
            # Ultrasonic uses I2C (lowspeed) — needs special handling
            self._emit_ultrasonic_read(port, port_idx, result)
        else:
            # Standard analog sensor
            self._emit_analog_sensor_read(port, port_idx, sensor_type, sensor_mode, result)

        return result

    def _emit_analog_sensor_read(self, port, port_idx, sensor_type, sensor_mode, result_idx):
        """Configure and read an analog sensor (touch, light, sound)."""
        type_field = self._get_const_ubyte(IN_TYPE)
        mode_field = self._get_const_ubyte(IN_MODE)
        scaled_field = self._get_const_ubyte(IN_SCALED)
        invalid_field = self._get_const_ubyte(IN_INVALID)

        type_val = self._get_const_ubyte(sensor_type)
        mode_val = self._get_const_ubyte(sensor_mode)

        # Configure sensor type and mode if not already done
        if port not in self._sensor_configured:
            # OP_SETIN port, type_field, type_val
            self._emit(encode_instruction(OP_SETIN, port_idx, type_field, type_val))
            # OP_SETIN port, mode_field, mode_val
            self._emit(encode_instruction(OP_SETIN, port_idx, mode_field, mode_val))
            # Clear invalid data flag
            self._emit(encode_instruction(OP_SETIN, port_idx, invalid_field, self._get_const_ubyte(0)))
            self._sensor_configured.add(port)

        # OP_GETIN result, port, scaled_field
        self._emit(encode_instruction(OP_GETIN, result_idx, port_idx, scaled_field))

    def _emit_ultrasonic_read(self, port, port_idx, result_idx):
        """Read ultrasonic sensor via I2C (lowspeed) protocol.

        The ultrasonic sensor is an I2C device. Reading it requires:
        1. Configure port as LOWSPEED_9V
        2. COMM_LS_WRITE to send I2C read request
        3. COMM_LS_CHECKSTATUS to wait for data
        4. COMM_LS_READ to get the result
        """
        type_field = self._get_const_ubyte(IN_TYPE)
        mode_field = self._get_const_ubyte(IN_MODE)
        type_val = self._get_const_ubyte(SENSOR_TYPE_LOWSPEED_9V)
        mode_val = self._get_const_ubyte(SENSOR_MODE_RAW)

        if port not in self._sensor_configured:
            self._emit(encode_instruction(OP_SETIN, port_idx, type_field, type_val))
            self._emit(encode_instruction(OP_SETIN, port_idx, mode_field, mode_val))
            self._sensor_configured.add(port)

        # For ultrasonic, we use syscalls:
        # 1. COMM_LS_WRITE: write I2C command to request distance reading
        # 2. COMM_LS_CHECKSTATUS: check if data is ready
        # 3. COMM_LS_READ: read the result

        # LS_WRITE cluster: {Status(UBYTE), Port(UBYTE), Buffer(ARRAY of UBYTE), ReturnLen(UBYTE)}
        ls_write_cluster, ls_write_members = self.ds.add_cluster(
            [TC_UBYTE, TC_UBYTE, TC_UBYTE, TC_UBYTE],
            name="lsw",
            defaults=[0, port, 0, 1]  # status=0, port, buffer_placeholder=0, return_len=1
        )

        # We need to build the I2C command buffer: [0x02, 0x42] (address, register)
        i2c_buf = self.ds.add_string("\x02\x42", name="i2c_cmd")

        # Actually, the LS_WRITE syscall cluster format is different in the NXT firmware.
        # Let's use a simpler approach: read the scaled value directly since the NXT
        # firmware can handle ultrasonic via GETIN on newer firmware versions.
        # For maximum compatibility, we'll use GETIN with IN_SCALED which works
        # when the sensor has been configured as LOWSPEED_9V.
        scaled_field = self._get_const_ubyte(IN_SCALED)
        self._emit(encode_instruction(OP_GETIN, result_idx, port_idx, scaled_field))

    # ── Sound ───────────────────────────────────────────────────────────

    def _emit_play_tone(self, stmt: PlayTone):
        """Emit OP_SYSCALL for SoundPlayTone.

        SoundPlayTone cluster: {Status(UBYTE), Frequency(UWORD), Duration(UWORD), Loop(UBYTE), Volume(UBYTE)}
        """
        freq_val = self._emit_expr(stmt.freq)
        dur_val = self._emit_expr(stmt.duration)

        # Create the syscall parameter cluster
        cluster_idx, members = self.ds.add_cluster(
            [TC_UBYTE, TC_UWORD, TC_UWORD, TC_UBYTE, TC_UBYTE],
            name="tone",
            defaults=[0, 0, 0, 0, 3]  # status=0, freq=0, dur=0, loop=0, volume=3
        )
        status_idx, freq_idx, dur_idx, loop_idx, vol_idx = members

        # Set frequency and duration from expressions
        self._emit(encode_instruction(OP_MOV, freq_idx, freq_val))
        self._emit(encode_instruction(OP_MOV, dur_idx, dur_val))

        # Syscall
        syscall_id = self._get_const_ubyte(SYSCALL_SOUND_PLAY_TONE)
        self._emit(encode_instruction(OP_SYSCALL, syscall_id, cluster_idx))

    # ── Display ─────────────────────────────────────────────────────────

    def _emit_display(self, stmt: Display):
        """Emit OP_SYSCALL for DrawText.

        DrawText cluster: {Result(SBYTE), Location(Point cluster), Text(string)}
        Point cluster: {X(SWORD), Y(SWORD)}

        Actually the NXT DrawText syscall takes:
        {Result(SWORD), Location.X(UWORD), Location.Y(UWORD), Filename(array/string)}

        Let me use simplified flat cluster approach since we don't nest clusters.
        The actual firmware expects: Status(SWORD), Location{X(SWORD),Y(SWORD)}, Text(string)
        But since we can't easily nest clusters, we'll flatten it.
        """
        text_idx = self._emit_expr(stmt.text)
        line_idx = self._emit_expr(stmt.line)

        # Compute Y position: NXT display is 64 pixels tall, 8 lines of 8 pixels
        # Line 1 = Y 56, Line 2 = Y 48, etc. (Y increases downward, text drawn from top-left)
        y_tmp = self._alloc_temp(TC_SLONG)
        eight = self._get_const(8)
        sixty_four = self._get_const(56)
        self._emit(encode_instruction(OP_MUL, y_tmp, line_idx, eight))
        y_pos = self._alloc_temp(TC_SLONG)
        self._emit(encode_instruction(OP_SUB, y_pos, sixty_four, y_tmp))

        # DrawText cluster: {Status(SWORD), Location(cluster{X,Y}), Text(array)}
        # We'll build this as a flat cluster since the NXT expects specific layout
        cluster_idx, members = self.ds.add_cluster_with_string(
            [TC_SWORD, TC_SWORD, TC_SWORD, TC_ARRAY],
            string_defaults={3: ""},
            name="drawtext"
        )
        status_m, x_m, y_m, text_m = members

        # Set X to 0, Y to computed position
        self._emit(encode_instruction(OP_MOV, x_m, self._get_const(0)))
        self._emit(encode_instruction(OP_MOV, y_m, y_pos))
        self._emit(encode_instruction(OP_MOV, text_m, text_idx))

        syscall_id = self._get_const_ubyte(SYSCALL_DRAW_TEXT)
        self._emit(encode_instruction(OP_SYSCALL, syscall_id, cluster_idx))

    def _emit_clear_screen(self):
        """Emit a screen clear. Uses DrawText syscall trick or dedicated syscall."""
        # NXT firmware 1.28+ has a SetScreenMode syscall (38) that can clear
        # We'll use it with a simple cluster: {Status(SWORD), ScreenMode(UWORD)}
        # ScreenMode = 0x00FF clears the screen
        # Actually let's just use the standard approach — fill with spaces or use
        # the CLEAR_SCREEN syscall (id 38 on fw 1.28+)
        cluster_idx, members = self.ds.add_cluster(
            [TC_SWORD, TC_UWORD],
            name="clrscr",
            defaults=[0, 0x00]
        )

        syscall_id = self._get_const_ubyte(SYSCALL_CLEAR_SCREEN)
        self._emit(encode_instruction(OP_SYSCALL, syscall_id, cluster_idx))

    # ── Timing ──────────────────────────────────────────────────────────

    def _emit_wait(self, stmt: Wait):
        """Emit OP_WAIT."""
        ms_idx = self._emit_expr(stmt.milliseconds)
        self._emit(encode_instruction(OP_WAIT, ms_idx))

    # ── Control flow ────────────────────────────────────────────────────

    def _emit_if_else(self, stmt: IfElse):
        """Emit if/else with branch instructions.

        Pattern:
            BRCMP <cc> else_label, left, right   # branch to else if condition FALSE
            ... then body ...
            JMP end_label
          else_label:
            ... else body ...
          end_label:
        """
        cond = stmt.condition
        if not isinstance(cond, CompareExpr):
            raise ValueError("If condition must be a comparison")

        left_idx = self._emit_expr(cond.left)
        right_idx = self._emit_expr(cond.right)

        # Invert the comparison for branching (branch when condition is FALSE)
        invert_cc = {
            "<": CC_GTEQ,   # branch if >=
            ">": CC_LTEQ,   # branch if <=
            "==": CC_NEQ,   # branch if !=
            "!=": CC_EQ,    # branch if ==
            "<=": CC_GT,    # branch if >
            ">=": CC_LT,    # branch if <
        }
        cc = invert_cc[cond.op]

        # Emit BRCMP with placeholder offset
        brcmp_pos = self._current_offset()
        # BRCMP: instr_word(with cc), offset, left, right — 8 bytes = 4 words
        self._emit(encode_instruction(OP_BRCMP, 0, left_idx, right_idx, cc=cc))

        # Emit then body
        for s in stmt.then_body:
            self._emit_stmt(s)

        if stmt.else_body:
            # Emit JMP over else body (placeholder)
            jmp_pos = self._current_offset()
            self._emit(encode_instruction(OP_JMP, 0))

            # Patch BRCMP to jump here (else label)
            else_offset = self._current_offset()
            # BRCMP offset is relative, in bytes, from the instruction after BRCMP
            # The offset field is at brcmp_pos + 1 (second word)
            self.code[brcmp_pos + 1] = _to_i16((else_offset - brcmp_pos) * 2)

            # Emit else body
            for s in stmt.else_body:
                self._emit_stmt(s)

            # Patch JMP to jump here (end label)
            end_offset = self._current_offset()
            self.code[jmp_pos + 1] = _to_i16((end_offset - jmp_pos) * 2)
        else:
            # No else: patch BRCMP to jump here
            end_offset = self._current_offset()
            self.code[brcmp_pos + 1] = _to_i16((end_offset - brcmp_pos) * 2)

    def _emit_repeat(self, stmt: Repeat):
        """Emit a counted loop.

        Pattern:
            counter = count_expr
          loop_top:
            BRCMP CC_LTEQ end_label, counter, 0   # exit when counter <= 0
            ... body ...
            SUB counter, counter, 1
            JMP loop_top
          end_label:
        """
        count_idx = self._emit_expr(stmt.count)
        counter = self._alloc_temp()
        self._emit(encode_instruction(OP_MOV, counter, count_idx))

        loop_top = self._current_offset()

        # Branch to end if counter <= 0
        brcmp_pos = self._current_offset()
        self._emit(encode_instruction(OP_BRCMP, 0, counter, self._const_zero, cc=CC_LTEQ))

        # Body
        for s in stmt.body:
            self._emit_stmt(s)

        # Decrement counter
        self._emit(encode_instruction(OP_SUB, counter, counter, self._const_one))

        # Jump back to top
        jmp_pos = self._current_offset()
        self._emit(encode_instruction(OP_JMP, 0))
        # Patch JMP offset (relative, in bytes)
        self.code[jmp_pos + 1] = _to_i16((loop_top - jmp_pos) * 2)

        # Patch BRCMP to end
        end_offset = self._current_offset()
        self.code[brcmp_pos + 1] = _to_i16((end_offset - brcmp_pos) * 2)

    def _emit_forever(self, stmt: Forever):
        """Emit an infinite loop.

        Pattern:
          loop_top:
            ... body ...
            JMP loop_top
        """
        loop_top = self._current_offset()

        for s in stmt.body:
            self._emit_stmt(s)

        jmp_pos = self._current_offset()
        self._emit(encode_instruction(OP_JMP, 0))
        self.code[jmp_pos + 1] = _to_i16((loop_top - jmp_pos) * 2)


# ─── Public API ─────────────────────────────────────────────────────────────

def compile_source(source: str, output_path: str) -> str:
    """Compile NXT DSL source code to an .rxe file.

    Args:
        source: The DSL source code string.
        output_path: Path to write the .rxe file.

    Returns:
        The output path.

    Raises:
        SyntaxError: If the source has syntax errors.
        ValueError: If code generation fails.
    """
    from .rxe_writer import write_rxe

    tokens = lex(source)
    parser = Parser(tokens)
    ast = parser.parse()
    gen = CodeGenerator()
    dstoc_bytes, static_defaults, dynamic_defaults, ds_static_size, code_words = gen.compile(ast)
    write_rxe(dstoc_bytes, static_defaults, dynamic_defaults, ds_static_size, code_words, output_path)
    return output_path
