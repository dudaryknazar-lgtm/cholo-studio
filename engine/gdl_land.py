"""
GDL (Game Design Language) — Parser & Interpreter
Syntax inspired by Python/Lua but tailored for games.

Example:
    scene Main {
        bg_color = #1a1a2e
        gravity  = vec2(0, 980)

        on start {
            player.position = vec2(100, 200)
            show_text("Hello!")
        }
        on update {
            if key_pressed("left") { player.move(-2, 0) }
        }
    }

    character Hero {
        hp = 20; atk = 8; speed = 3
        sprite = "hero_walk"
        on interact { start_dialog(["Hello!", "Bye!"]) }
    }

    battle Slime {
        hp = 30; atk = 5
        attacks = [
            bullet { speed=120; pattern="wave"; count=5 }
        ]
        mercy_condition { return player_mercy >= 2 }
    }
"""
import re, math, os, json
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────
#  TOKENS
# ─────────────────────────────────────────────
class TT:  # Token Types
    NUM    = 'NUM'
    STR    = 'STR'
    ID     = 'ID'
    HASH_COLOR = 'HASH_COLOR'  # #rrggbb
    LBRACE = '{';  RBRACE = '}'
    LBRACKET='[';   RBRACKET=']'
    LPAREN = '(';   RPAREN = ')'
    EQ     = '=';   EQEQ   = '=='
    NEQ    = '!=';  LT     = '<'
    GT     = '>';   LTE    = '<='
    GTE    = '>=';  AND    = 'and'
    OR     = 'or';  NOT    = 'not'
    PLUS   = '+';   MINUS  = '-'
    STAR   = '*';   SLASH  = '/'
    PERCENT='%';    DOT    = '.'
    COMMA  = ',';   SEMI   = ';'
    COLON  = ':';   ARROW  = '->'
    NEWLINE= 'NL';  EOF    = 'EOF'
    # Keywords
    SCENE='scene'; CHARACTER='character'; BATTLE='battle'
    ON='on'; IF='if'; ELSE='else'; ELIF='elif'
    WHILE='while'; FOR='for'; IN='in'
    RETURN='return'; BREAK='break'; CONTINUE='continue'
    LET='let'; FUNC='func'; DIALOG_TREE='dialog_tree'
    TRUE='true'; FALSE='false'; NULL='null'
    IMPORT='import'; TEMPLATE='template'

KEYWORDS = {
    'scene','character','battle','on','if','else','elif',
    'while','for','in','return','break','continue',
    'let','func','dialog_tree','true','false','null',
    'and','or','not','import','template',
    'vec2','vec3','color','rect',
}

class Token:
    __slots__ = ('type','value','line')
    def __init__(self, t, v, line=0):
        self.type=t; self.value=v; self.line=line
    def __repr__(self): return f"Token({self.type},{self.value!r})"

# ─────────────────────────────────────────────
#  LEXER
# ─────────────────────────────────────────────
class Lexer:
    def __init__(self, source: str):
        self.src  = source
        self.pos  = 0
        self.line = 1
        self.tokens: List[Token] = []

    def error(self, msg):
        raise SyntaxError(f"[GDL Lexer] Line {self.line}: {msg}")

    def peek(self, offset=0):
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else '\0'

    def advance(self):
        ch = self.src[self.pos]; self.pos += 1
        if ch == '\n': self.line += 1
        return ch

    def skip_whitespace_and_comments(self):
        while self.pos < len(self.src):
            ch = self.peek()
            if ch in ' \t\r': self.advance()
            elif ch == '\n':
                self.tokens.append(Token(TT.NEWLINE, '\n', self.line))
                self.advance()
            elif ch == '-' and self.peek(1) == '-':  # -- comment
                while self.pos < len(self.src) and self.peek() != '\n':
                    self.advance()
            elif ch == '/' and self.peek(1) == '/':
                while self.pos < len(self.src) and self.peek() != '\n':
                    self.advance()
            elif ch == '/' and self.peek(1) == '*':
                self.advance(); self.advance()
                while self.pos < len(self.src):
                    if self.peek() == '*' and self.peek(1) == '/':
                        self.advance(); self.advance(); break
                    self.advance()
            else:
                break

    def read_string(self, delim):
        s = ''
        self.advance()  # skip opening quote
        while self.pos < len(self.src):
            ch = self.advance()
            if ch == delim: break
            if ch == '\\':
                esc = self.advance()
                ch  = {'n':'\n','t':'\t','r':'\r','\\':'\\',
                        "'":"'",'"':'"'}.get(esc, esc)
            s += ch
        return s

    def read_number(self):
        s = ''
        while self.pos < len(self.src) and (self.peek() in '0123456789._'):
            if self.peek() == '_': self.advance(); continue
            s += self.advance()
        return float(s) if '.' in s else int(s)

    def read_id(self):
        s = ''
        while self.pos < len(self.src) and (self.peek().isalnum() or self.peek() == '_'):
            s += self.advance()
        return s

    def tokenize(self) -> List[Token]:
        singles = {'{':TT.LBRACE,'}':TT.RBRACE,'[':TT.LBRACKET,
                   ']':TT.RBRACKET,'(':TT.LPAREN,')':TT.RPAREN,
                   '.':TT.DOT,',':TT.COMMA,';':TT.SEMI,':':TT.COLON,
                   '+':TT.PLUS,'*':TT.STAR,'%':TT.PERCENT}
        while self.pos < len(self.src):
            self.skip_whitespace_and_comments()
            if self.pos >= len(self.src): break
            ch = self.peek(); ln = self.line
            # strings
            if ch in ('"', "'"):
                s = self.read_string(ch)
                self.tokens.append(Token(TT.STR, s, ln)); continue
            # numbers
            if ch.isdigit() or (ch == '-' and self.peek(1).isdigit()):
                if ch == '-': self.advance()
                n = self.read_number()
                self.tokens.append(Token(TT.NUM, -n if ch=='-' else n, ln)); continue
            # hex color
            if ch == '#' and self.pos+7 <= len(self.src) and \
               all(c in '0123456789abcdefABCDEF' for c in self.src[self.pos+1:self.pos+7]):
                self.advance()
                hx = self.src[self.pos:self.pos+6]; self.pos += 6
                r,g,b = int(hx[0:2],16),int(hx[2:4],16),int(hx[4:6],16)
                self.tokens.append(Token(TT.HASH_COLOR,(r,g,b),ln)); continue
            # identifiers / keywords
            if ch.isalpha() or ch == '_':
                ident = self.read_id()
                tt = ident if ident in KEYWORDS else TT.ID
                val = {'true':True,'false':False,'null':None}.get(ident, ident)
                self.tokens.append(Token(tt, val, ln)); continue
            # two-char operators
            if ch == '=' and self.peek(1) == '=': self.advance();self.advance();self.tokens.append(Token(TT.EQEQ,'==',ln));continue
            if ch == '!' and self.peek(1) == '=': self.advance();self.advance();self.tokens.append(Token(TT.NEQ,'!=',ln));continue
            if ch == '<' and self.peek(1) == '=': self.advance();self.advance();self.tokens.append(Token(TT.LTE,'<=',ln));continue
            if ch == '>' and self.peek(1) == '=': self.advance();self.advance();self.tokens.append(Token(TT.GTE,'>=',ln));continue
            if ch == '-' and self.peek(1) == '>': self.advance();self.advance();self.tokens.append(Token(TT.ARROW,'->',ln));continue
            if ch == '/': self.advance();self.tokens.append(Token(TT.SLASH,'/',ln));continue
            if ch == '-': self.advance();self.tokens.append(Token(TT.MINUS,'-',ln));continue
            if ch == '<': self.advance();self.tokens.append(Token(TT.LT,'<',ln));continue
            if ch == '>': self.advance();self.tokens.append(Token(TT.GT,'>',ln));continue
            if ch == '=': self.advance();self.tokens.append(Token(TT.EQ,'=',ln));continue
            # singles
            if ch in singles: self.advance();self.tokens.append(Token(singles[ch],ch,ln));continue
            self.error(f"Unknown character: {ch!r}")
        self.tokens.append(Token(TT.EOF, None, self.line))
        return self.tokens

# ─────────────────────────────────────────────
#  AST NODES
# ─────────────────────────────────────────────
class Node:
    pass

class NumberLit(Node):
    def __init__(self, v): self.v = v

class StringLit(Node):
    def __init__(self, v): self.v = v

class BoolLit(Node):
    def __init__(self, v): self.v = v

class NullLit(Node):
    pass

class ColorLit(Node):
    def __init__(self, rgb): self.rgb = rgb

class VecLit(Node):
    def __init__(self, args): self.args = args  # list of expr nodes

class Identifier(Node):
    def __init__(self, name): self.name = name

class ListLit(Node):
    def __init__(self, items): self.items = items

class DictLit(Node):
    def __init__(self, pairs): self.pairs = pairs  # [(key,val)]

class BinOp(Node):
    def __init__(self, left, op, right): self.left=left;self.op=op;self.right=right

class UnaryOp(Node):
    def __init__(self, op, expr): self.op=op;self.expr=expr

class Assign(Node):
    def __init__(self, target, value): self.target=target;self.value=value

class Attr(Node):
    def __init__(self, obj, attr): self.obj=obj;self.attr=attr

class Index(Node):
    def __init__(self, obj, idx): self.obj=obj;self.idx=idx

class Call(Node):
    def __init__(self, func, args, kwargs=None):
        self.func=func;self.args=args;self.kwargs=kwargs or {}

class Block(Node):
    def __init__(self, stmts): self.stmts = stmts

class IfStmt(Node):
    def __init__(self, cond, body, elifs=None, else_body=None):
        self.cond=cond;self.body=body;self.elifs=elifs or [];self.else_body=else_body

class WhileStmt(Node):
    def __init__(self, cond, body): self.cond=cond;self.body=body

class ForStmt(Node):
    def __init__(self, var, iterable, body): self.var=var;self.iterable=iterable;self.body=body

class ReturnStmt(Node):
    def __init__(self, value=None): self.value=value

class BreakStmt(Node): pass
class ContinueStmt(Node): pass

class FuncDef(Node):
    def __init__(self, name, params, body): self.name=name;self.params=params;self.body=body

class OnBlock(Node):
    def __init__(self, event, body): self.event=event;self.body=body

class SceneDecl(Node):
    def __init__(self, name, body): self.name=name;self.body=body

class CharacterDecl(Node):
    def __init__(self, name, body): self.name=name;self.body=body

class BattleDecl(Node):
    def __init__(self, name, body): self.name=name;self.body=body

class DialogTreeDecl(Node):
    def __init__(self, name, nodes): self.name=name;self.nodes=nodes

class TemplateDecl(Node):
    def __init__(self, name, body): self.name=name;self.body=body

class ImportStmt(Node):
    def __init__(self, path): self.path=path

# ─────────────────────────────────────────────
#  PARSER
# ─────────────────────────────────────────────
class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = [t for t in tokens if t.type != TT.NEWLINE]
        self.pos    = 0

    def error(self, msg):
        t = self.current()
        raise SyntaxError(f"[GDL Parser] Line {t.line}: {msg} (got {t.type}={t.value!r})")

    def current(self) -> Token: return self.tokens[min(self.pos, len(self.tokens)-1)]
    def peek(self, offset=1): return self.tokens[min(self.pos+offset, len(self.tokens)-1)]
    def advance(self) -> Token:
        t = self.current(); self.pos+=1; return t

    def expect(self, *types) -> Token:
        t = self.current()
        if t.type not in types:
            self.error(f"Expected {types}")
        return self.advance()

    def match(self, *types) -> bool:
        if self.current().type in types:
            self.advance(); return True
        return False

    def check(self, *types) -> bool:
        return self.current().type in types

    # ── Top-level ──
    def parse(self) -> Block:
        stmts = []
        while not self.check(TT.EOF):
            stmts.append(self.parse_top())
        return Block(stmts)

    def parse_top(self) -> Node:
        t = self.current()
        if t.type == 'scene':      return self.parse_scene()
        if t.type == 'character':  return self.parse_character()
        if t.type == 'battle':     return self.parse_battle()
        if t.type == 'dialog_tree':return self.parse_dialog_tree()
        if t.type == 'template':   return self.parse_template()
        if t.type == 'import':     return self.parse_import()
        if t.type == 'func':       return self.parse_func()
        return self.parse_stmt()

    def parse_scene(self) -> SceneDecl:
        self.advance()
        name = self.expect(TT.ID).value
        body = self.parse_block()
        return SceneDecl(name, body)

    def parse_character(self) -> CharacterDecl:
        self.advance()
        name = self.expect(TT.ID).value
        body = self.parse_block()
        return CharacterDecl(name, body)

    def parse_battle(self) -> BattleDecl:
        self.advance()
        name = self.expect(TT.ID).value
        body = self.parse_block()
        return BattleDecl(name, body)

    def parse_dialog_tree(self) -> DialogTreeDecl:
        self.advance()
        name = self.expect(TT.ID).value
        self.expect(TT.LBRACE)
        nodes = []
        while not self.check(TT.RBRACE) and not self.check(TT.EOF):
            speaker = self.expect(TT.ID).value
            self.expect(TT.COLON)
            texts = [self.expect(TT.STR).value]
            while self.check(TT.COMMA):
                self.advance()
                texts.append(self.expect(TT.STR).value)
            nodes.append((speaker, texts))
            self.match(TT.SEMI)
        self.expect(TT.RBRACE)
        return DialogTreeDecl(name, nodes)

    def parse_template(self) -> TemplateDecl:
        self.advance()
        name = self.expect(TT.ID).value
        body = self.parse_block()
        return TemplateDecl(name, body)

    def parse_import(self) -> ImportStmt:
        self.advance()
        path = self.expect(TT.STR).value
        return ImportStmt(path)

    def parse_func(self) -> FuncDef:
        self.advance()
        name   = self.expect(TT.ID).value
        self.expect(TT.LPAREN)
        params = []
        while not self.check(TT.RPAREN):
            params.append(self.expect(TT.ID).value)
            if not self.check(TT.RPAREN): self.expect(TT.COMMA)
        self.expect(TT.RPAREN)
        body = self.parse_block()
        return FuncDef(name, params, body)

    def parse_block(self) -> Block:
        self.expect(TT.LBRACE)
        stmts = []
        while not self.check(TT.RBRACE) and not self.check(TT.EOF):
            stmts.append(self.parse_top_or_stmt())
        self.expect(TT.RBRACE)
        return Block(stmts)

    def parse_top_or_stmt(self):
        t = self.current()
        if t.type == 'on':   return self.parse_on()
        if t.type == 'func': return self.parse_func()
        return self.parse_stmt()

    def parse_on(self) -> OnBlock:
        self.advance()
        event = self.current().value; self.advance()
        body  = self.parse_block()
        return OnBlock(event, body)

    def parse_stmt(self) -> Node:
        t = self.current()
        if t.type == 'if':      return self.parse_if()
        if t.type == 'while':   return self.parse_while()
        if t.type == 'for':     return self.parse_for()
        if t.type == 'return':  self.advance(); return ReturnStmt(self.parse_expr() if not self.check(TT.RBRACE,TT.SEMI,TT.EOF) else None)
        if t.type == 'break':   self.advance(); return BreakStmt()
        if t.type == 'continue':self.advance(); return ContinueStmt()
        if t.type == 'let':
            self.advance()
            name = self.expect(TT.ID).value
            self.expect(TT.EQ)
            val  = self.parse_expr()
            self.match(TT.SEMI)
            return Assign(Identifier(name), val)
        # assignment or expression
        expr = self.parse_expr()
        if self.check(TT.EQ):
            self.advance()
            val = self.parse_expr()
            self.match(TT.SEMI)
            return Assign(expr, val)
        self.match(TT.SEMI)
        return expr

    def parse_if(self) -> IfStmt:
        self.advance()
        cond   = self.parse_expr()
        body   = self.parse_block()
        elifs  = []
        else_b = None
        while self.check('elif'):
            self.advance(); ec = self.parse_expr(); eb = self.parse_block()
            elifs.append((ec,eb))
        if self.check('else'):
            self.advance(); else_b = self.parse_block()
        return IfStmt(cond, body, elifs, else_b)

    def parse_while(self) -> WhileStmt:
        self.advance(); cond = self.parse_expr(); body = self.parse_block()
        return WhileStmt(cond, body)

    def parse_for(self) -> ForStmt:
        self.advance(); var = self.expect(TT.ID).value
        self.expect('in'); itr = self.parse_expr(); body = self.parse_block()
        return ForStmt(var, itr, body)

    # ── Expressions ──
    def parse_expr(self): return self.parse_or()
    def parse_or(self):
        l = self.parse_and()
        while self.check('or'): op=self.advance().type; r=self.parse_and(); l=BinOp(l,op,r)
        return l
    def parse_and(self):
        l = self.parse_not()
        while self.check('and'): op=self.advance().type; r=self.parse_not(); l=BinOp(l,op,r)
        return l
    def parse_not(self):
        if self.check('not'): self.advance(); return UnaryOp('not', self.parse_not())
        return self.parse_cmp()
    def parse_cmp(self):
        l = self.parse_add()
        while self.check(TT.EQEQ,TT.NEQ,TT.LT,TT.GT,TT.LTE,TT.GTE):
            op=self.advance().type; r=self.parse_add(); l=BinOp(l,op,r)
        return l
    def parse_add(self):
        l = self.parse_mul()
        while self.check(TT.PLUS, TT.MINUS):
            op=self.advance().type; r=self.parse_mul(); l=BinOp(l,op,r)
        return l
    def parse_mul(self):
        l = self.parse_unary()
        while self.check(TT.STAR,TT.SLASH,TT.PERCENT):
            op=self.advance().type; r=self.parse_unary(); l=BinOp(l,op,r)
        return l
    def parse_unary(self):
        if self.check(TT.MINUS): self.advance(); return UnaryOp('-', self.parse_unary())
        return self.parse_postfix()
    def parse_postfix(self):
        node = self.parse_primary()
        while True:
            if self.check(TT.DOT):
                self.advance(); attr = self.advance().value; node = Attr(node, attr)
            elif self.check(TT.LBRACKET):
                self.advance(); idx=self.parse_expr(); self.expect(TT.RBRACKET)
                node = Index(node, idx)
            elif self.check(TT.LPAREN):
                self.advance(); args=[]; kwargs={}
                while not self.check(TT.RPAREN):
                    if self.check(TT.ID) and self.peek().type == TT.EQ:
                        k=self.advance().value; self.advance(); v=self.parse_expr()
                        kwargs[k]=v
                    else:
                        args.append(self.parse_expr())
                    if not self.check(TT.RPAREN): self.expect(TT.COMMA)
                self.expect(TT.RPAREN)
                node = Call(node, args, kwargs)
            else:
                break
        return node

    def parse_primary(self):
        t = self.current()
        if t.type == TT.NUM:     self.advance(); return NumberLit(t.value)
        if t.type == TT.STR:     self.advance(); return StringLit(t.value)
        if t.type == 'true':     self.advance(); return BoolLit(True)
        if t.type == 'false':    self.advance(); return BoolLit(False)
        if t.type == 'null':     self.advance(); return NullLit()
        if t.type == TT.HASH_COLOR: self.advance(); return ColorLit(t.value)
        if t.type == 'vec2':
            self.advance(); self.expect(TT.LPAREN)
            args = [self.parse_expr()]
            self.expect(TT.COMMA); args.append(self.parse_expr())
            self.expect(TT.RPAREN); return VecLit(args)
        if t.type == TT.ID:
            self.advance(); return Identifier(t.value)
        if t.type == TT.LBRACKET:
            self.advance(); items=[]
            while not self.check(TT.RBRACKET):
                items.append(self.parse_expr())
                if not self.check(TT.RBRACKET): self.expect(TT.COMMA)
            self.expect(TT.RBRACKET); return ListLit(items)
        if t.type == TT.LPAREN:
            self.advance(); e = self.parse_expr(); self.expect(TT.RPAREN); return e
        self.error(f"Unexpected token in expression")

# ─────────────────────────────────────────────
#  INTERPRETER / RUNTIME
# ─────────────────────────────────────────────
class GDLReturn(Exception):
    def __init__(self, val): self.val = val
class GDLBreak(Exception):   pass
class GDLContinue(Exception): pass

class GDLObject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    def __repr__(self):
        return f"GDLObject({self.__dict__})"

class Interpreter:
    def __init__(self, engine_scene=None):
        self.scene = engine_scene
        self._global_env: Dict[str, Any] = {}
        self._call_stack: List[Dict] = [self._global_env]
        self._scene_defs: Dict[str,dict] = {}
        self._char_defs:  Dict[str,dict] = {}
        self._battle_defs:Dict[str,dict] = {}
        self._dialog_defs:Dict[str,list] = {}
        self._templates:  Dict[str,dict] = {}
        self._events:     Dict[str, list] = {}  # event -> [callable]
        self._setup_builtins()

    def _setup_builtins(self):
        import math as _math
        env = self._global_env
        # Math
        env['abs']   = abs
        env['min']   = min
        env['max']   = max
        env['sqrt']  = _math.sqrt
        env['sin']   = _math.sin
        env['cos']   = _math.cos
        env['floor'] = _math.floor
        env['ceil']  = _math.ceil
        env['round'] = round
        env['pi']    = _math.pi
        env['rand']  = lambda: __import__('random').random()
        env['rand_range'] = lambda a,b: __import__('random').uniform(a,b)
        env['rand_int']   = lambda a,b: __import__('random').randint(int(a),int(b))
        env['lerp']  = lambda a,b,t: a+(b-a)*t
        env['clamp'] = lambda v,mn,mx: max(mn, min(mx, v))
        # Game builtins (hooked to engine at runtime)
        env['print']    = lambda *a: print('[GDL]', *a)
        env['log']      = lambda *a: print('[GDL LOG]', *a)
        env['vec2']     = lambda x=0,y=0: GDLObject(x=float(x),y=float(y),
                                                     length=lambda: _math.hypot(float(x),float(y)))
        env['color']    = lambda r,g,b,a=255: (int(r),int(g),int(b),int(a))
        env['show_text']= self._builtin_show_text
        env['play_sound']= self._builtin_play_sound
        env['play_music']= self._builtin_play_music
        env['stop_music']= self._builtin_stop_music
        env['load_scene']= self._builtin_load_scene
        env['spawn']    = self._builtin_spawn
        env['destroy']  = self._builtin_destroy
        env['find']     = self._builtin_find
        env['key_pressed']= lambda k: False  # replaced at runtime
        env['key_held']   = lambda k: False
        env['mouse_pos']  = lambda: GDLObject(x=0,y=0)
        env['start_battle']= self._builtin_start_battle
        env['start_dialog']= self._builtin_start_dialog
        env['wait']     = lambda s: None
        env['camera_shake']= self._builtin_camera_shake
        env['set_gravity'] = lambda x,y: setattr(self.scene.physics,'gravity',
                                                  __import__('engine.core',fromlist=['Vec2']).Vec2(x,y)) if self.scene else None
        env['emit_particles']= self._builtin_emit_particles
        env['tween']    = self._builtin_tween
        env['true']  = True
        env['false'] = False
        env['null']  = None

    # builtins
    def _builtin_show_text(self, text, *a, **kw):
        print(f"[GDL DIALOG] {text}")
        if self.scene:
            ents = [e for e in self.scene.entities if e.has(__import__('engine.core',fromlist=['DialogSystem']).DialogSystem)]
            if ents:
                ents[0].get(__import__('engine.core',fromlist=['DialogSystem']).DialogSystem).start([str(text)])

    def _builtin_play_sound(self, name, *a, **kw):
        from engine.core import Resources
        snd = Resources.load_sound(str(name))
        if snd:
            try: snd.play()
            except: pass

    def _builtin_play_music(self, name, loop=True):
        try:
            import pygame
            path = str(name)
            if os.path.exists(path):
                pygame.mixer.music.load(path)
                pygame.mixer.music.play(-1 if loop else 0)
        except: pass

    def _builtin_stop_music(self):
        try:
            import pygame; pygame.mixer.music.stop()
        except: pass

    def _builtin_load_scene(self, name):
        from engine.core import Engine
        if Engine.get(): Engine.get().load_scene(str(name))

    def _builtin_spawn(self, template_name, x=0, y=0):
        pass  # connected to engine spawn

    def _builtin_destroy(self, entity):
        if self.scene and hasattr(entity,'_engine_ref'):
            self.scene.remove_entity(entity._engine_ref)

    def _builtin_find(self, name):
        if self.scene:
            return self.scene.find(str(name))
        return None

    def _builtin_start_battle(self, name, *a):
        print(f"[GDL] Starting battle: {name}")

    def _builtin_start_dialog(self, lines_or_name, speaker=""):
        if isinstance(lines_or_name, list):
            lines = [str(l) for l in lines_or_name]
        else:
            tree = self._dialog_defs.get(str(lines_or_name))
            lines = [t for _, texts in (tree or []) for t in texts]
        print(f"[GDL DIALOG] {speaker}: {lines}")

    def _builtin_camera_shake(self, amount=8.0):
        if self.scene:
            cam = self.scene.get_camera()
            if cam: cam.shake(amount)

    def _builtin_emit_particles(self, entity_name, count=20):
        if self.scene:
            e = self.scene.find(str(entity_name))
            if e:
                from engine.core import ParticleEmitter
                pe = e.get(ParticleEmitter)
                if pe: pe.emit_burst(int(count))

    def _builtin_tween(self, obj, prop, target, duration=1.0, easing="linear"):
        pass  # real tween system connected in runtime

    # ── Environment ──
    def env(self): return self._call_stack[-1]
    def push_env(self, parent=None): self._call_stack.append(dict(parent or self.env()))
    def pop_env(self):
        if len(self._call_stack) > 1: self._call_stack.pop()
    def get_var(self, name):
        for env in reversed(self._call_stack):
            if name in env: return env[name]
        return None
    def set_var(self, name, val): self.env()[name] = val

    # ── Execute ──
    def execute(self, source: str, filename="<gdl>"):
        try:
            tokens = Lexer(source).tokenize()
            ast    = Parser(tokens).parse()
            return self.eval_block(ast)
        except (SyntaxError, RuntimeError) as e:
            print(f"[GDL Error] {e}")
            return None

    def eval_block(self, block: Block):
        result = None
        for stmt in block.stmts:
            result = self.eval_node(stmt)
        return result

    def eval_node(self, node: Node):
        if isinstance(node, NumberLit): return node.v
        if isinstance(node, StringLit): return node.v
        if isinstance(node, BoolLit):   return node.v
        if isinstance(node, NullLit):   return None
        if isinstance(node, ColorLit):  return node.rgb
        if isinstance(node, VecLit):
            args = [self.eval_node(a) for a in node.args]
            from engine.core import Vec2
            return Vec2(*args) if len(args)==2 else args
        if isinstance(node, Identifier):
            v = self.get_var(node.name)
            if v is None and node.name not in self.env():
                return None  # undefined
            return v
        if isinstance(node, ListLit):   return [self.eval_node(i) for i in node.items]
        if isinstance(node, DictLit):   return {self.eval_node(k):self.eval_node(v) for k,v in node.pairs}
        if isinstance(node, BinOp):     return self.eval_binop(node)
        if isinstance(node, UnaryOp):   return self.eval_unary(node)
        if isinstance(node, Assign):    return self.eval_assign(node)
        if isinstance(node, Attr):      return self.eval_attr(node)
        if isinstance(node, Index):
            obj = self.eval_node(node.obj); idx = self.eval_node(node.idx)
            if isinstance(obj, (list, tuple)): return obj[int(idx)]
            if isinstance(obj, dict): return obj.get(idx)
            return None
        if isinstance(node, Call):      return self.eval_call(node)
        if isinstance(node, IfStmt):    return self.eval_if(node)
        if isinstance(node, WhileStmt): return self.eval_while(node)
        if isinstance(node, ForStmt):   return self.eval_for(node)
        if isinstance(node, ReturnStmt):
            raise GDLReturn(self.eval_node(node.value) if node.value else None)
        if isinstance(node, BreakStmt):    raise GDLBreak()
        if isinstance(node, ContinueStmt): raise GDLContinue()
        if isinstance(node, FuncDef):   return self.eval_funcdef(node)
        if isinstance(node, OnBlock):   return self.eval_on(node)
        if isinstance(node, SceneDecl):    return self.eval_scene(node)
        if isinstance(node, CharacterDecl):return self.eval_character(node)
        if isinstance(node, BattleDecl):   return self.eval_battle(node)
        if isinstance(node, DialogTreeDecl):self._dialog_defs[node.name]=node.nodes; return None
        if isinstance(node, TemplateDecl): self._templates[node.name]=node; return None
        if isinstance(node, ImportStmt):   return self.eval_import(node)
        if isinstance(node, Block):     return self.eval_block(node)
        return None

    def eval_binop(self, node):
        l = self.eval_node(node.left); r = self.eval_node(node.right)
        op= node.op
        if op == TT.PLUS:  return l + r
        if op == TT.MINUS: return l - r
        if op == TT.STAR:  return l * r
        if op == TT.SLASH: return l / r if r != 0 else 0
        if op == TT.PERCENT: return l % r if r != 0 else 0
        if op == TT.EQEQ: return l == r
        if op == TT.NEQ:   return l != r
        if op == TT.LT:    return l < r
        if op == TT.GT:    return l > r
        if op == TT.LTE:   return l <= r
        if op == TT.GTE:   return l >= r
        if op == 'and':    return bool(l) and bool(r)
        if op == 'or':     return bool(l) or bool(r)

    def eval_unary(self, node):
        v = self.eval_node(node.expr)
        if node.op == '-':   return -v
        if node.op == 'not': return not bool(v)

    def eval_assign(self, node):
        val = self.eval_node(node.value)
        target = node.target
        if isinstance(target, Identifier):
            self.set_var(target.name, val)
        elif isinstance(target, Attr):
            obj  = self.eval_node(target.obj)
            if obj is not None:
                setattr(obj, target.attr, val)
        elif isinstance(target, Index):
            obj = self.eval_node(target.obj); idx=self.eval_node(target.idx)
            obj[int(idx) if isinstance(idx,(int,float)) else idx] = val
        return val

    def eval_attr(self, node):
        obj = self.eval_node(node.obj)
        if obj is None: return None
        return getattr(obj, node.attr, None)

    def eval_call(self, node):
        func  = self.eval_node(node.func)
        args  = [self.eval_node(a) for a in node.args]
        kwargs= {k: self.eval_node(v) for k,v in node.kwargs.items()}
        if callable(func):
            try: return func(*args, **kwargs)
            except Exception as e: print(f"[GDL Call] {e}"); return None
        if isinstance(func, FuncDef): return self.call_func(func, args, kwargs)
        return None

    def call_func(self, fdef, args, kwargs):
        self.push_env()
        for i,p in enumerate(fdef.params):
            self.set_var(p, args[i] if i < len(args) else kwargs.get(p))
        try: return self.eval_block(fdef.body)
        except GDLReturn as r: return r.val
        finally: self.pop_env()

    def eval_funcdef(self, node):
        self.set_var(node.name, node)
        return node

    def eval_on(self, node):
        event = node.event
        if event not in self._events:
            self._events[event] = []
        def handler(*args):
            self.push_env()
            try: self.eval_block(node.body)
            except GDLReturn: pass
            finally: self.pop_env()
        self._events[event].append(handler)
        return None

    def fire_event(self, event, *args):
        for fn in self._events.get(event, []):
            fn(*args)

    def eval_if(self, node):
        if self.eval_node(node.cond):
            return self.eval_block(node.body)
        for cond,body in node.elifs:
            if self.eval_node(cond):
                return self.eval_block(body)
        if node.else_body:
            return self.eval_block(node.else_body)

    def eval_while(self, node):
        while self.eval_node(node.cond):
            try: self.eval_block(node.body)
            except GDLBreak: break
            except GDLContinue: continue

    def eval_for(self, node):
        itr = self.eval_node(node.iterable)
        if itr is None: return
        for item in (itr if hasattr(itr,'__iter__') else range(int(itr))):
            self.set_var(node.var, item)
            try: self.eval_block(node.body)
            except GDLBreak: break
            except GDLContinue: continue

    def eval_scene(self, node):
        data = {'name': node.name, 'props': {}, 'events': {}}
        self._scene_defs[node.name] = data
        self.push_env()
        self.set_var('__scene__', node.name)
        self.eval_block(node.body)
        data['env'] = dict(self.env())
        self.pop_env()
        return data

    def eval_character(self, node):
        data = {'name': node.name}
        self._char_defs[node.name] = data
        self.push_env()
        self.eval_block(node.body)
        data['env'] = dict(self.env())
        self.pop_env()
        return data

    def eval_battle(self, node):
        data = {'name': node.name}
        self._battle_defs[node.name] = data
        self.push_env()
        self.eval_block(node.body)
        data['env'] = dict(self.env())
        self.pop_env()
        return data

    def eval_import(self, node):
        path = node.path
        if not path.endswith('.gdl'): path += '.gdl'
        if os.path.exists(path):
            with open(path) as f:
                self.execute(f.read(), path)
        else:
            print(f"[GDL] Import not found: {path}")
        return None

def compile_gdl(source: str) -> dict:
    """Parse GDL source and return AST + metadata"""
    interp = Interpreter()
    interp.execute(source)
    return {
        'scenes':    interp._scene_defs,
        'characters':interp._char_defs,
        'battles':   interp._battle_defs,
        'dialogs':   interp._dialog_defs,
        'templates': interp._templates,
    }
