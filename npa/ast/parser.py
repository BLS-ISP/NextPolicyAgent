"""Rego Parser — Recursive descent parser for Rego v1.

Parses token streams into AST Module structures.
"""

from __future__ import annotations

from typing import Any

from npa.ast.lexer import Token, TokenType, LexerError, tokenize
from npa.ast.types import (
    Annotations,
    ArrayComprehension,
    Body,
    Call,
    Comment,
    Every,
    Expr,
    Import,
    Location,
    Module,
    ObjectComprehension,
    Package,
    Ref,
    Rule,
    RuleHead,
    RuleKind,
    SetComprehension,
    Term,
    TermKind,
    With,
    array_term,
    bool_term,
    null_term,
    num_term,
    object_term,
    ref_term,
    set_term,
    str_term,
    var_term,
)

MAX_RECURSION_DEPTH = 100_000


class ParseError(Exception):
    def __init__(self, msg: str, location: Location) -> None:
        super().__init__(f"{location}: {msg}")
        self.location = location


class Parser:
    """Recursive descent parser for Rego v1 policy language."""

    def __init__(self, source: str, filename: str = "") -> None:
        self._filename = filename
        self._tokens: list[Token] = []
        self._pos = 0
        self._depth = 0
        self._comments: list[Comment] = []
        self._errors: list[ParseError] = []
        self._annotations_by_line: dict[int, Annotations] = {}

        # Tokenize and filter newlines/comments used later
        for tok in tokenize(source, filename):
            if tok.type == TokenType.COMMENT:
                self._comments.append(Comment(tok.value, tok.location))
            else:
                self._tokens.append(tok)

        # Pre-parse METADATA annotation blocks from comments
        self._parse_annotations_from_comments()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _parse_annotations_from_comments(self) -> None:
        """Extract METADATA annotation blocks from comments.

        OPA METADATA blocks look like:
            # METADATA
            # title: My Rule
            # description: Does something
            # scope: rule
            # entrypoint: true
        The annotation attaches to the rule immediately following the block.
        """
        i = 0
        while i < len(self._comments):
            text = self._comments[i].text.strip()
            if text == "# METADATA" or text == "#METADATA":
                metadata_start = self._comments[i].location.row
                i += 1
                fields: dict[str, str] = {}
                end_row = metadata_start
                while i < len(self._comments):
                    line = self._comments[i].text
                    # Strip leading "# " prefix
                    stripped = line.lstrip("#").strip()
                    if not stripped or ":" not in stripped:
                        break
                    key, _, val = stripped.partition(":")
                    fields[key.strip().lower()] = val.strip()
                    end_row = self._comments[i].location.row
                    i += 1
                # Annotation target = the line right after the block
                target_line = end_row + 1
                ann = Annotations(
                    title=fields.get("title", ""),
                    description=fields.get("description", ""),
                    scope=fields.get("scope", "rule"),
                    entrypoint=fields.get("entrypoint", "").lower() == "true",
                    custom={k: v for k, v in fields.items()
                            if k not in ("title", "description", "scope", "entrypoint")},
                    location=Location(row=metadata_start, col=1),
                )
                self._annotations_by_line[target_line] = ann
            else:
                i += 1

    def _get_annotation_for_line(self, line: int) -> Annotations | None:
        """Get annotation for a rule starting at the given line."""
        # Check the exact line and a few lines before (in case of whitespace)
        for offset in range(0, 4):
            ann = self._annotations_by_line.get(line - offset)
            if ann is not None:
                return ann
        return None

    def _enter(self) -> None:
        self._depth += 1
        if self._depth > MAX_RECURSION_DEPTH:
            raise ParseError("Maximum recursion depth exceeded", self._peek().location)

    def _leave(self) -> None:
        self._depth -= 1

    def _peek(self) -> Token:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return self._tokens[-1]  # EOF

    def _advance(self) -> Token:
        tok = self._peek()
        if tok.type != TokenType.EOF:
            self._pos += 1
        return tok

    def _expect(self, tt: TokenType) -> Token:
        tok = self._advance()
        if tok.type != tt:
            raise ParseError(f"Expected {tt.name}, got {tok.type.name} ({tok.value!r})", tok.location)
        return tok

    def _match(self, *types: TokenType) -> Token | None:
        if self._peek().type in types:
            return self._advance()
        return None

    def _skip_newlines(self) -> None:
        while self._peek().type == TokenType.NEWLINE:
            self._advance()

    def _at(self, *types: TokenType) -> bool:
        return self._peek().type in types

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def parse(self) -> Module:
        """Parse a complete Rego module."""
        self._skip_newlines()

        # Package
        pkg = self._parse_package()
        self._skip_newlines()

        # Imports
        imports: list[Import] = []
        while self._at(TokenType.IMPORT):
            imports.append(self._parse_import())
            self._skip_newlines()

        # Rules
        rules: list[Rule] = []
        while not self._at(TokenType.EOF):
            self._skip_newlines()
            if self._at(TokenType.EOF):
                break
            rule = self._parse_rule()
            if rule:
                rules.append(rule)
            self._skip_newlines()

        return Module(
            package=pkg,
            imports=imports,
            rules=rules,
            comments=self._comments,
            location=Location(self._filename, 1, 1, 0),
        )

    # -----------------------------------------------------------------------
    # Package & Import
    # -----------------------------------------------------------------------

    def _parse_package(self) -> Package:
        tok = self._expect(TokenType.PACKAGE)
        ref = self._parse_dotted_ref()
        return Package(path=ref, location=tok.location)

    def _parse_import(self) -> Import:
        tok = self._expect(TokenType.IMPORT)
        # Import paths can contain keywords (e.g., import future.keywords.in)
        ref = self._parse_import_ref()
        alias = ""
        if self._match(TokenType.AS):
            alias_tok = self._expect(TokenType.IDENT)
            alias = alias_tok.value
        return Import(path=ref, alias=alias, location=tok.location)

    def _parse_import_ref(self) -> Ref:
        """Parse an import path that may contain keywords as path components."""
        # Accept IDENT or keywords after dots
        _KW_TOKENS = {
            TokenType.IN, TokenType.IF, TokenType.CONTAINS, TokenType.EVERY,
            TokenType.NOT, TokenType.SOME, TokenType.AS, TokenType.DEFAULT,
            TokenType.ELSE, TokenType.PACKAGE, TokenType.IMPORT,
        }
        first = self._advance()
        if first.type != TokenType.IDENT and first.type not in _KW_TOKENS:
            raise ParseError(f"Expected identifier in import path, got {first.type.name}", first.location)
        terms = [str_term(first.value, first.location)]
        while self._match(TokenType.DOT):
            part = self._advance()
            if part.type != TokenType.IDENT and part.type not in _KW_TOKENS:
                raise ParseError(f"Expected identifier in import path, got {part.type.name}", part.location)
            terms.append(str_term(part.value, part.location))
        return Ref(tuple(terms))

    def _parse_dotted_ref(self) -> Ref:
        """Parse a dotted reference: data.foo.bar"""
        first = self._expect(TokenType.IDENT)
        terms = [str_term(first.value, first.location)]
        while self._match(TokenType.DOT):
            part = self._expect(TokenType.IDENT)
            terms.append(str_term(part.value, part.location))
        return Ref(tuple(terms))

    # -----------------------------------------------------------------------
    # Rules
    # -----------------------------------------------------------------------

    def _parse_rule(self) -> Rule | None:
        self._enter()
        try:
            # Default rule
            if self._at(TokenType.DEFAULT):
                return self._parse_default_rule()

            loc = self._peek().location

            # Rule head
            head = self._parse_rule_head()
            if head is None:
                # Skip unknown token
                self._advance()
                return None

            # Determine rule kind
            kind = self._infer_rule_kind(head)

            # Optional "if" keyword
            has_if = self._match(TokenType.IF) is not None

            # Rule body
            body = Body(location=loc)
            if self._match(TokenType.LBRACE):
                body = self._parse_body()
                self._expect(TokenType.RBRACE)
            elif has_if:
                body = self._parse_inline_body()

            # Else clauses
            else_rules: list[Rule] = []
            while self._at(TokenType.ELSE):
                else_rules.append(self._parse_else_clause())

            return Rule(
                kind=kind,
                head=head,
                body=body,
                else_rules=else_rules,
                annotations=self._get_annotation_for_line(loc.row),
                location=loc,
            )
        finally:
            self._leave()

    def _parse_default_rule(self) -> Rule:
        tok = self._advance()  # consume 'default'
        name_tok = self._expect(TokenType.IDENT)
        self._expect(TokenType.UNIFY)
        value = self._parse_term()
        return Rule(
            kind=RuleKind.DEFAULT,
            head=RuleHead(name=name_tok.value, value=value, location=name_tok.location),
            default=True,
            location=tok.location,
        )

    def _parse_rule_head(self) -> RuleHead | None:
        if not self._at(TokenType.IDENT):
            return None

        name_tok = self._advance()
        name = name_tok.value

        # Function args: f(x, y)
        args: list[Term] = []
        if self._match(TokenType.LPAREN):
            args = self._parse_term_list(TokenType.RPAREN)
            self._expect(TokenType.RPAREN)

        # Key: rule[key]
        key: Term | None = None
        if self._match(TokenType.LBRACKET):
            key = self._parse_term()
            self._expect(TokenType.RBRACKET)

        # "contains" keyword for partial set
        is_contains = self._match(TokenType.CONTAINS) is not None
        if is_contains:
            value = self._parse_term()
            return RuleHead(name=name, value=value, args=tuple(args), contains=True, location=name_tok.location)

        # Value assignment: = value or := value
        value: Term | None = None
        assign = False
        if self._match(TokenType.ASSIGN):
            assign = True
            value = self._parse_term()
        elif self._match(TokenType.UNIFY):
            value = self._parse_term()

        return RuleHead(
            name=name,
            key=key,
            value=value,
            args=tuple(args),
            assign=assign,
            location=name_tok.location,
        )

    def _infer_rule_kind(self, head: RuleHead) -> RuleKind:
        if head.args and not head.contains:
            return RuleKind.FUNCTION
        if head.contains:
            return RuleKind.PARTIAL_SET
        if head.key is not None:
            return RuleKind.PARTIAL_OBJECT
        return RuleKind.COMPLETE

    def _parse_else_clause(self) -> Rule:
        tok = self._expect(TokenType.ELSE)
        value: Term | None = None
        if self._match(TokenType.UNIFY) or self._match(TokenType.ASSIGN):
            value = self._parse_term()

        body = Body(location=tok.location)
        if self._match(TokenType.IF):
            if self._match(TokenType.LBRACE):
                body = self._parse_body()
                self._expect(TokenType.RBRACE)
            else:
                body = self._parse_inline_body()
        elif self._match(TokenType.LBRACE):
            body = self._parse_body()
            self._expect(TokenType.RBRACE)

        return Rule(
            kind=RuleKind.COMPLETE,
            head=RuleHead(name="", value=value, location=tok.location),
            body=body,
            location=tok.location,
        )

    # -----------------------------------------------------------------------
    # Body & Expressions
    # -----------------------------------------------------------------------

    def _parse_body(self, stop_tokens: tuple[TokenType, ...] = (TokenType.RBRACE,)) -> Body:
        self._enter()
        try:
            self._skip_newlines()
            exprs: list[Expr] = []
            idx = 0
            end_tokens = (*stop_tokens, TokenType.EOF)
            while not self._at(*end_tokens):
                expr = self._parse_expr(idx)
                if expr:
                    exprs.append(expr)
                    idx += 1
                self._skip_newlines()
                # Separator: semicolon or newline
                self._match(TokenType.SEMICOLON)
                self._skip_newlines()
            return Body(exprs=exprs)
        finally:
            self._leave()

    def _parse_inline_body(self) -> Body:
        """Parse a single-line body (after 'if' without braces)."""
        expr = self._parse_expr(0)
        return Body(exprs=[expr] if expr else [])

    def _parse_expr(self, index: int) -> Expr | None:
        self._enter()
        try:
            loc = self._peek().location

            # Negation
            negated = self._match(TokenType.NOT) is not None

            # "some" declaration
            if self._at(TokenType.SOME):
                return self._parse_some_expr(index, negated, loc)

            # "every" expression
            if self._at(TokenType.EVERY):
                return self._parse_every_expr(index, negated, loc)

            # Regular expression: term (operator term)?
            lhs = self._parse_term()

            # Binary operator?
            op_tok = self._match(
                TokenType.UNIFY, TokenType.EQ, TokenType.NEQ,
                TokenType.LT, TokenType.LTE, TokenType.GT, TokenType.GTE,
                TokenType.ASSIGN,
            )
            if op_tok:
                rhs = self._parse_term()
                op_ref = Ref((str_term(op_tok.value, op_tok.location),))
                call = Call(op_ref, (lhs, rhs))
                term = Term(TermKind.CALL, call, loc)
            elif self._match(TokenType.IN):
                # Standalone "x in collection" → internal.member_2(x, collection)
                rhs = self._parse_term()
                op_ref = Ref((str_term("internal.member_2", loc),))
                call = Call(op_ref, (lhs, rhs))
                term = Term(TermKind.CALL, call, loc)
            else:
                term = lhs

            # With modifiers
            withs = self._parse_with_modifiers()

            return Expr(
                terms=term,
                negated=negated,
                index=index,
                with_modifiers=tuple(withs),
                location=loc,
            )
        finally:
            self._leave()

    def _parse_some_expr(self, index: int, negated: bool, loc: Location) -> Expr:
        self._advance()  # consume 'some'
        terms: list[Term] = [self._parse_term()]
        while self._match(TokenType.COMMA):
            terms.append(self._parse_term())
        # "some x in collection" → internal.member_2(x, collection)
        # "some k, v in collection" → internal.member_3(k, v, collection)
        if self._match(TokenType.IN):
            domain = self._parse_term()
            if len(terms) == 1:
                op_ref = Ref((str_term("internal.member_2", loc),))
                call = Call(op_ref, (terms[0], domain))
            else:
                op_ref = Ref((str_term("internal.member_3", loc),))
                call = Call(op_ref, (terms[0], terms[1], domain))
            term = Term(TermKind.CALL, call, loc)
            return Expr(
                terms=term,
                negated=negated,
                index=index,
                location=loc,
            )
        # Bare "some x" — just declare variable (treat as local binding)
        return Expr(terms=terms[0] if len(terms) == 1 else terms[0], negated=negated, index=index, location=loc)

    def _parse_every_expr(self, index: int, negated: bool, loc: Location) -> Expr:
        self._advance()  # consume 'every'
        key = var_term("$_key")
        value = self._parse_term()
        if self._match(TokenType.COMMA):
            key = value
            value = self._parse_term()
        self._expect(TokenType.IN)
        domain = self._parse_term()
        self._expect(TokenType.LBRACE)
        body = self._parse_body()
        self._expect(TokenType.RBRACE)
        every = Every(key=key, value=value, domain=domain, body=body)
        term = Term(TermKind.EVERY, every, loc)
        return Expr(terms=term, negated=negated, index=index, location=loc)

    def _parse_with_modifiers(self) -> list[With]:
        withs: list[With] = []
        while self._at(TokenType.WITH):
            tok = self._advance()
            target = self._parse_ref_or_term()
            self._expect(TokenType.AS)
            value = self._parse_term()
            withs.append(With(target=target, value=value, location=tok.location))
        return withs

    # -----------------------------------------------------------------------
    # Terms
    # -----------------------------------------------------------------------

    def _parse_term(self) -> Term:
        """Parse a term (value expression)."""
        self._enter()
        try:
            return self._parse_or_expr()
        finally:
            self._leave()

    def _parse_or_expr(self) -> Term:
        lhs = self._parse_and_expr()
        while self._match(TokenType.PIPE):
            rhs = self._parse_and_expr()
            op_ref = Ref((str_term("|"),))
            lhs = Term(TermKind.CALL, Call(op_ref, (lhs, rhs)), lhs.location)
        return lhs

    def _parse_and_expr(self) -> Term:
        lhs = self._parse_arith_expr()
        while self._match(TokenType.AMPERSAND):
            rhs = self._parse_arith_expr()
            op_ref = Ref((str_term("&"),))
            lhs = Term(TermKind.CALL, Call(op_ref, (lhs, rhs)), lhs.location)
        return lhs

    def _parse_arith_expr(self) -> Term:
        lhs = self._parse_mul_expr()
        while self._at(TokenType.PLUS, TokenType.MINUS):
            op_tok = self._advance()
            rhs = self._parse_mul_expr()
            op_ref = Ref((str_term(op_tok.value),))
            lhs = Term(TermKind.CALL, Call(op_ref, (lhs, rhs)), lhs.location)
        return lhs

    def _parse_mul_expr(self) -> Term:
        lhs = self._parse_unary_expr()
        while self._at(TokenType.MUL, TokenType.DIV, TokenType.MOD):
            op_tok = self._advance()
            rhs = self._parse_unary_expr()
            op_ref = Ref((str_term(op_tok.value),))
            lhs = Term(TermKind.CALL, Call(op_ref, (lhs, rhs)), lhs.location)
        return lhs

    def _parse_unary_expr(self) -> Term:
        if self._at(TokenType.MINUS):
            tok = self._advance()
            operand = self._parse_postfix_expr()
            op_ref = Ref((str_term("minus_unary"),))
            return Term(TermKind.CALL, Call(op_ref, (operand,)), tok.location)
        return self._parse_postfix_expr()

    def _parse_postfix_expr(self) -> Term:
        """Parse a primary followed by optional postfix: [index], .field, (args)."""
        term = self._parse_primary()

        while True:
            if self._match(TokenType.DOT):
                field = self._expect(TokenType.IDENT)
                # Build ref from existing term
                if term.kind == TermKind.REF:
                    ref: Ref = term.value
                    new_terms = list(ref.terms) + [str_term(field.value, field.location)]
                    term = Term(TermKind.REF, Ref(tuple(new_terms)), term.location)
                else:
                    term = Term(
                        TermKind.REF,
                        Ref((term, str_term(field.value, field.location))),
                        term.location,
                    )
            elif self._match(TokenType.LBRACKET):
                idx_term = self._parse_term()
                self._expect(TokenType.RBRACKET)
                if term.kind == TermKind.REF:
                    ref = term.value
                    new_terms = list(ref.terms) + [idx_term]
                    term = Term(TermKind.REF, Ref(tuple(new_terms)), term.location)
                else:
                    term = Term(TermKind.REF, Ref((term, idx_term)), term.location)
            elif self._match(TokenType.LPAREN):
                args = self._parse_term_list(TokenType.RPAREN)
                self._expect(TokenType.RPAREN)
                if term.kind == TermKind.REF:
                    term = Term(TermKind.CALL, Call(term.value, tuple(args)), term.location)
                else:
                    ref = Ref((term,))
                    term = Term(TermKind.CALL, Call(ref, tuple(args)), term.location)
            else:
                break

        return term

    def _parse_primary(self) -> Term:
        """Parse a primary term: literal, variable, array, object, set, comprehension, paren."""
        tok = self._peek()

        match tok.type:
            case TokenType.NULL:
                self._advance()
                return null_term(tok.location)

            case TokenType.TRUE:
                self._advance()
                return bool_term(True, tok.location)

            case TokenType.FALSE:
                self._advance()
                return bool_term(False, tok.location)

            case TokenType.NUMBER:
                self._advance()
                return self._parse_number(tok)

            case TokenType.STRING:
                self._advance()
                return str_term(self._unescape_string(tok.value), tok.location)

            case TokenType.RAW_STRING:
                self._advance()
                return str_term(tok.value[1:-1], tok.location)

            case TokenType.IDENT:
                self._advance()
                return self._make_var_or_ref(tok)

            case TokenType.CONTAINS:
                # 'contains' can also be used as a builtin function name
                self._advance()
                return self._make_var_or_ref(tok)

            case TokenType.LBRACKET:
                return self._parse_array_or_comprehension()

            case TokenType.LBRACE:
                return self._parse_object_set_or_comprehension()

            case TokenType.LPAREN:
                self._advance()
                inner = self._parse_term()
                self._expect(TokenType.RPAREN)
                return inner

            case _:
                raise ParseError(f"Unexpected token: {tok.type.name} ({tok.value!r})", tok.location)

    def _make_var_or_ref(self, tok: Token) -> Term:
        """An identifier becomes a Var. If it's data/input, it starts a Ref."""
        if tok.value in ("data", "input"):
            return Term(TermKind.REF, Ref((str_term(tok.value, tok.location),)), tok.location)
        return var_term(tok.value, tok.location)

    def _parse_number(self, tok: Token) -> Term:
        v = tok.value
        try:
            if "." in v or "e" in v.lower():
                return num_term(float(v), tok.location)
            if v.startswith(("0x", "0X")):
                return num_term(int(v, 16), tok.location)
            if v.startswith(("0o", "0O")):
                return num_term(int(v, 8), tok.location)
            if v.startswith(("0b", "0B")):
                return num_term(int(v, 2), tok.location)
            return num_term(int(v), tok.location)
        except ValueError as e:
            raise ParseError(f"Invalid number: {v}", tok.location) from e

    def _unescape_string(self, raw: str) -> str:
        """Unescape a JSON-style quoted string."""
        # Strip surrounding quotes and process escape sequences
        inner = raw[1:-1]
        result: list[str] = []
        i = 0
        while i < len(inner):
            if inner[i] == '\\' and i + 1 < len(inner):
                ch = inner[i + 1]
                match ch:
                    case 'n':
                        result.append('\n')
                    case 't':
                        result.append('\t')
                    case 'r':
                        result.append('\r')
                    case '\\':
                        result.append('\\')
                    case '"':
                        result.append('"')
                    case '/':
                        result.append('/')
                    case 'u' if i + 5 < len(inner):
                        hex_val = inner[i + 2:i + 6]
                        result.append(chr(int(hex_val, 16)))
                        i += 4
                    case _:
                        result.append('\\')
                        result.append(ch)
                i += 2
            else:
                result.append(inner[i])
                i += 1
        return "".join(result)

    def _parse_array_or_comprehension(self) -> Term:
        """Parse [items] or [term | body]."""
        tok = self._advance()  # consume [
        self._skip_newlines()

        if self._at(TokenType.RBRACKET):
            self._advance()
            return array_term([], tok.location)

        first = self._parse_and_expr()
        self._skip_newlines()

        # Array comprehension: [term | body]
        if self._match(TokenType.PIPE):
            body = self._parse_body(stop_tokens=(TokenType.RBRACKET,))
            self._expect(TokenType.RBRACKET)
            comp = ArrayComprehension(term=first, body=body)
            return Term(TermKind.ARRAY_COMPREHENSION, comp, tok.location)

        # Regular array
        items = [first]
        while self._match(TokenType.COMMA):
            self._skip_newlines()
            if self._at(TokenType.RBRACKET):
                break
            items.append(self._parse_term())
            self._skip_newlines()
        self._expect(TokenType.RBRACKET)
        return array_term(items, tok.location)

    def _parse_object_set_or_comprehension(self) -> Term:
        """Parse {pairs}, {items} (set), {k: v | body} or {v | body}."""
        tok = self._advance()  # consume {
        self._skip_newlines()

        if self._at(TokenType.RBRACE):
            self._advance()
            return set_term([], tok.location)

        first = self._parse_and_expr()
        self._skip_newlines()

        # Object: {key: value, ...} or {key: value | body}
        if self._match(TokenType.COLON):
            value = self._parse_and_expr()
            self._skip_newlines()

            # Object comprehension
            if self._match(TokenType.PIPE):
                body = self._parse_body(stop_tokens=(TokenType.RBRACE,))
                self._expect(TokenType.RBRACE)
                comp = ObjectComprehension(key=first, value=value, body=body)
                return Term(TermKind.OBJECT_COMPREHENSION, comp, tok.location)

            # Regular object
            pairs: list[tuple[Term, Term]] = [(first, value)]
            while self._match(TokenType.COMMA):
                self._skip_newlines()
                if self._at(TokenType.RBRACE):
                    break
                k = self._parse_term()
                self._expect(TokenType.COLON)
                v = self._parse_term()
                pairs.append((k, v))
                self._skip_newlines()
            self._expect(TokenType.RBRACE)
            return object_term(pairs, tok.location)

        # Set comprehension: {term | body}
        if self._match(TokenType.PIPE):
            body = self._parse_body(stop_tokens=(TokenType.RBRACE,))
            self._expect(TokenType.RBRACE)
            comp = SetComprehension(term=first, body=body)
            return Term(TermKind.SET_COMPREHENSION, comp, tok.location)

        # Regular set: {a, b, c}
        items = [first]
        while self._match(TokenType.COMMA):
            self._skip_newlines()
            if self._at(TokenType.RBRACE):
                break
            items.append(self._parse_term())
            self._skip_newlines()
        self._expect(TokenType.RBRACE)
        return set_term(items, tok.location)

    def _parse_ref_or_term(self) -> Term:
        return self._parse_term()

    def _parse_term_list(self, end: TokenType) -> list[Term]:
        """Parse comma-separated terms until end token."""
        terms: list[Term] = []
        self._skip_newlines()
        if self._at(end):
            return terms
        terms.append(self._parse_term())
        while self._match(TokenType.COMMA):
            self._skip_newlines()
            if self._at(end):
                break
            terms.append(self._parse_term())
        return terms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_module(source: str, filename: str = "") -> Module:
    """Parse Rego source code into a Module AST."""
    parser = Parser(source, filename)
    return parser.parse()


def parse_query(source: str, filename: str = "") -> Body:
    """Parse a standalone query (body)."""
    # Wrap in a synthetic module to reuse the parser
    wrapped = f"package __query__\n__result__ = true {{ {source} }}"
    module = parse_module(wrapped, filename)
    if module.rules:
        return module.rules[0].body
    return Body()
