"""Rego Lexer — Tokenization of Rego source code.

High-performance scanner with pre-compiled regex patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator

from npa.ast.types import Location


class TokenType(Enum):
    # Literals
    NULL = auto()
    TRUE = auto()
    FALSE = auto()
    NUMBER = auto()
    STRING = auto()
    RAW_STRING = auto()

    # Identifiers & Keywords
    IDENT = auto()
    PACKAGE = auto()
    IMPORT = auto()
    AS = auto()
    DEFAULT = auto()
    NOT = auto()
    WITH = auto()
    IF = auto()
    CONTAINS = auto()
    EVERY = auto()
    IN = auto()
    SOME = auto()
    ELSE = auto()

    # Operators
    ASSIGN = auto()        # :=
    EQ = auto()            # ==
    NEQ = auto()           # !=
    UNIFY = auto()         # =
    LT = auto()            # <
    LTE = auto()           # <=
    GT = auto()            # >
    GTE = auto()           # >=

    # Delimiters
    LPAREN = auto()        # (
    RPAREN = auto()        # )
    LBRACKET = auto()      # [
    RBRACKET = auto()      # ]
    LBRACE = auto()        # {
    RBRACE = auto()        # }
    DOT = auto()           # .
    COMMA = auto()         # ,
    SEMICOLON = auto()     # ;
    COLON = auto()         # :
    PIPE = auto()          # |

    # Arithmetic
    PLUS = auto()
    MINUS = auto()
    MUL = auto()
    DIV = auto()
    MOD = auto()
    AMPERSAND = auto()     # &

    # Special
    COMMENT = auto()
    NEWLINE = auto()
    EOF = auto()
    ILLEGAL = auto()


KEYWORDS: dict[str, TokenType] = {
    "null": TokenType.NULL,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "package": TokenType.PACKAGE,
    "import": TokenType.IMPORT,
    "as": TokenType.AS,
    "default": TokenType.DEFAULT,
    "not": TokenType.NOT,
    "with": TokenType.WITH,
    "if": TokenType.IF,
    "contains": TokenType.CONTAINS,
    "every": TokenType.EVERY,
    "in": TokenType.IN,
    "some": TokenType.SOME,
    "else": TokenType.ELSE,
}


@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    value: str
    location: Location


# Pre-compiled patterns for performance
_RE_NUMBER = re.compile(r"-?(?:0[xXoObB][0-9a-fA-F_]+|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)")
_RE_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_RE_RAW_STRING = re.compile(r'`[^`]*`')
_RE_IDENT = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_RE_COMMENT = re.compile(r"#[^\n]*")
_RE_WHITESPACE = re.compile(r"[ \t\r]+")

# Two-char operators (checked first)
_TWO_CHAR_OPS: dict[str, TokenType] = {
    ":=": TokenType.ASSIGN,
    "==": TokenType.EQ,
    "!=": TokenType.NEQ,
    "<=": TokenType.LTE,
    ">=": TokenType.GTE,
}

# Single-char tokens
_SINGLE_CHAR: dict[str, TokenType] = {
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    ".": TokenType.DOT,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
    ":": TokenType.COLON,
    "|": TokenType.PIPE,
    "=": TokenType.UNIFY,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.MUL,
    "/": TokenType.DIV,
    "%": TokenType.MOD,
    "&": TokenType.AMPERSAND,
}


class LexerError(Exception):
    def __init__(self, msg: str, location: Location) -> None:
        super().__init__(f"{location}: {msg}")
        self.location = location


def tokenize(source: str, filename: str = "") -> Iterator[Token]:
    """Tokenize Rego source code into a stream of tokens."""
    pos = 0
    row = 1
    col = 1
    length = len(source)

    while pos < length:
        ch = source[pos]

        # Whitespace (not newline)
        m = _RE_WHITESPACE.match(source, pos)
        if m:
            skip = m.end() - pos
            col += skip
            pos = m.end()
            continue

        # Newline
        if ch == "\n":
            yield Token(TokenType.NEWLINE, "\n", Location(filename, row, col, pos))
            pos += 1
            row += 1
            col = 1
            continue

        loc = Location(filename, row, col, pos)

        # Comment
        m = _RE_COMMENT.match(source, pos)
        if m:
            yield Token(TokenType.COMMENT, m.group(), loc)
            pos = m.end()
            col += m.end() - m.start()
            continue

        # String
        if ch == '"':
            m = _RE_STRING.match(source, pos)
            if not m:
                raise LexerError("Unterminated string", loc)
            yield Token(TokenType.STRING, m.group(), loc)
            advance = m.end() - pos
            pos = m.end()
            col += advance
            continue

        # Raw string
        if ch == '`':
            m = _RE_RAW_STRING.match(source, pos)
            if not m:
                raise LexerError("Unterminated raw string", loc)
            yield Token(TokenType.RAW_STRING, m.group(), loc)
            advance = m.end() - pos
            pos = m.end()
            col += advance
            continue

        # Two-char operators
        if pos + 1 < length:
            two = source[pos:pos + 2]
            if two in _TWO_CHAR_OPS:
                yield Token(_TWO_CHAR_OPS[two], two, loc)
                pos += 2
                col += 2
                continue

        # Number (must check before ident for negative numbers)
        if ch.isdigit() or (ch == '-' and pos + 1 < length and source[pos + 1].isdigit()):
            m = _RE_NUMBER.match(source, pos)
            if m:
                yield Token(TokenType.NUMBER, m.group(), loc)
                advance = m.end() - pos
                pos = m.end()
                col += advance
                continue

        # Identifier / Keyword
        m = _RE_IDENT.match(source, pos)
        if m:
            word = m.group()
            tt = KEYWORDS.get(word, TokenType.IDENT)
            yield Token(tt, word, loc)
            advance = m.end() - pos
            pos = m.end()
            col += advance
            continue

        # Single-char token
        if ch in _SINGLE_CHAR:
            yield Token(_SINGLE_CHAR[ch], ch, loc)
            pos += 1
            col += 1
            continue

        raise LexerError(f"Unexpected character: {ch!r}", loc)

    yield Token(TokenType.EOF, "", Location(filename, row, col, pos))
