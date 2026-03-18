"""
GDL Studio - Game Engine Core
Entity-Component-System, Physics, Animation, Input, Audio, Scene
"""
import math, time, json, os, sys, uuid, copy, threading
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Dict, List, Tuple
from enum import Enum, auto

# ─────────────────────────────────────────────
#  MATH
# ─────────────────────────────────────────────
class Vec2:
    __slots__ = ('x','y')
    def __init__(self, x=0.0, y=0.0):
        self.x = float(x); self.y = float(y)
    def __add__(self, o): return Vec2(self.x+o.x, self.y+o.y)
    def __sub__(self, o): return Vec2(self.x-o.x, self.y-o.y)
    def __mul__(self, s): return Vec2(self.x*s, self.y*s)
    def __rmul__(self, s): return self.__mul__(s)
    def __truediv__(self, s): return Vec2(self.x/s, self.y/s)
    def __neg__(self): return Vec2(-self.x, -self.y)
    def __eq__(self, o): return abs(self.x-o.x)<1e-6 and abs(self.y-o.y)<1e-6
    def __repr__(self): return f"Vec2({self.x:.2f},{self.y:.2f})"
    def length(self): return math.sqrt(self.x**2 + self.y**2)
    def length_sq(self): return self.x**2 + self.y**2
    def normalized(self):
        l = self.length()
        return Vec2(self.x/l, self.y/l) if l > 1e-9 else Vec2()
    def dot(self, o): return self.x*o.x + self.y*o.y
    def cross(self, o): return self.x*o.y - self.y*o.x
    def lerp(self, o, t): return Vec2(self.x+(o.x-self.x)*t, self.y+(o.y-self.y)*t)
    def rotate(self, angle):
        c,s = math.cos(angle), math.sin(angle)
        return Vec2(self.x*c - self.y*s, self.x*s + self.y*c)
    def perpendicular(self): return Vec2(-self.y, self.x)
    def to_tuple(self): return (self.x, self.y)
    def to_int_tuple(self): return (int(self.x), int(self.y))
    def copy(self): return Vec2(self.x, self.y)
    def distance_to(self, o): return (self - o).length()
    @staticmethod
    def zero(): return Vec2(0,0)
    @staticmethod
    def one(): return Vec2(1,1)
    @staticmethod
    def up(): return Vec2(0,-1)
    @staticmethod
    def down(): return Vec2(0,1)
    @staticmethod
    def left(): return Vec2(-1,0)
    @staticmethod
    def right(): return Vec2(1,0)

@dataclass
class Rect2:
    x: float = 0; y: float = 0; w: float = 0; h: float = 0
    @property
    def left(self): return self.x
    @property
    def right(self): return self.x + self.w
    @property
    def top(self): return self.y
    @property
    def bottom(self): return self.y + self.h
    @property
    def center(self): return Vec2(self.x + self.w/2, self.y + self.h/2)
    def intersects(self, o):
        return (self.left < o.right and self.right > o.left and
                self.top < o.bottom and self.bottom > o.top)
    def contains_point(self, p):
        return self.left <= p.x <= self.right and self.top <= p.y <= self.bottom
    def expand(self, amount):
        return Rect2(self.x-amount, self.y-amount, self.w+amount*2, self.h+amount*2)

# ─────────────────────────────────────────────
#  COMPONENTS (ECS)
# ─────────────────────────────────────────────
class Component:
    """Base class for all components"""
    def __init__(self):
        self.entity = None   # set by Entity when attached
        self.enabled = True

class Transform(Component):
    def __init__(self, x=0, y=0):
        super().__init__()
        self.position = Vec2(x, y)
        self.rotation = 0.0   # radians
        self.scale    = Vec2(1, 1)
        self._prev_position = Vec2(x, y)

    def translate(self, dx, dy):
        self.position.x += dx
        self.position.y += dy

    def look_at(self, target: Vec2):
        diff = target - self.position
        self.rotation = math.atan2(diff.y, diff.x)

class SpriteRenderer(Component):
    def __init__(self, texture_name="", color=(255,255,255), width=32, height=32):
        super().__init__()
        self.texture_name = texture_name
        self.color        = color
        self.width        = width
        self.height       = height
        self.flip_x       = False
        self.flip_y       = False
        self.alpha        = 255
        self.layer        = 0
        self.offset       = Vec2(0, 0)
        self.visible      = True

class Animator(Component):
    """Frame-based sprite animation"""
    def __init__(self):
        super().__init__()
        self.animations: Dict[str, 'Animation'] = {}
        self.current_anim: Optional[str]  = None
        self.current_frame: int           = 0
        self._timer: float                = 0.0
        self.playing: bool                = True
        self.loop: bool                   = True
        self._on_end: Optional[Callable]  = None

    def add_animation(self, name: str, anim: 'Animation'):
        self.animations[name] = anim

    def play(self, name: str, force_restart=False, on_end=None):
        if name not in self.animations:
            return
        if self.current_anim == name and not force_restart:
            return
        self.current_anim  = name
        self.current_frame = 0
        self._timer        = 0.0
        self.playing       = True
        self._on_end       = on_end

    def stop(self):
        self.playing = False

    def update(self, dt: float):
        if not self.playing or self.current_anim is None:
            return
        anim = self.animations.get(self.current_anim)
        if not anim or len(anim.frames) == 0:
            return
        self._timer += dt
        spf = 1.0 / anim.fps
        while self._timer >= spf:
            self._timer -= spf
            self.current_frame += 1
            if self.current_frame >= len(anim.frames):
                if anim.loop:
                    self.current_frame = 0
                else:
                    self.current_frame = len(anim.frames) - 1
                    self.playing = False
                    if self._on_end:
                        self._on_end()
                    break

    @property
    def current_texture(self):
        if self.current_anim is None:
            return None
        anim = self.animations.get(self.current_anim)
        if not anim or len(anim.frames) == 0:
            return None
        idx = min(self.current_frame, len(anim.frames)-1)
        return anim.frames[idx]

@dataclass
class Animation:
    frames: List[str]       # list of texture names
    fps: float = 12.0
    loop: bool = True

class Rigidbody(Component):
    def __init__(self):
        super().__init__()
        self.velocity        = Vec2(0, 0)
        self.acceleration    = Vec2(0, 0)
        self.mass            = 1.0
        self.gravity_scale   = 1.0
        self.drag            = 0.02        # linear drag 0-1
        self.angular_drag    = 0.05
        self.angular_velocity= 0.0
        self.is_kinematic    = False       # kinematic = not affected by forces
        self.is_static       = False       # static = never moves
        self.use_gravity     = True
        self.freeze_x        = False
        self.freeze_y        = False
        self.bounce          = 0.0         # 0=no bounce, 1=perfect bounce
        self.friction        = 0.8
        self._forces: List[Vec2] = []

    def add_force(self, force: Vec2):
        self._forces.append(force)

    def add_impulse(self, impulse: Vec2):
        self.velocity = self.velocity + impulse * (1.0 / max(self.mass, 0.001))

    def set_velocity(self, x, y):
        self.velocity = Vec2(x, y)

class Collider(Component):
    def __init__(self, kind="box", w=32, h=32, radius=16):
        super().__init__()
        self.kind     = kind      # "box" | "circle" | "trigger"
        self.width    = w
        self.height   = h
        self.radius   = radius
        self.offset   = Vec2(0, 0)
        self.is_trigger = (kind == "trigger")
        self.layer    = 0
        self.mask     = 0xFFFF     # which layers to collide with
        self._on_enter: List[Callable] = []
        self._on_stay : List[Callable] = []
        self._on_exit : List[Callable] = []
        self._contacts: set = set()

    def on_collision_enter(self, fn): self._on_enter.append(fn)
    def on_collision_stay (self, fn): self._on_stay .append(fn)
    def on_collision_exit (self, fn): self._on_exit .append(fn)

    def get_rect(self, pos: Vec2) -> Rect2:
        return Rect2(pos.x + self.offset.x - self.width/2,
                     pos.y + self.offset.y - self.height/2,
                     self.width, self.height)

class Camera(Component):
    def __init__(self):
        super().__init__()
        self.zoom         = 1.0
        self.follow_target= None        # entity to follow
        self.follow_speed = 5.0
        self.deadzone     = Vec2(60,40)
        self.bounds       = None        # Rect2 | None
        self.shake_amount = 0.0
        self.shake_decay  = 8.0
        self._shake_offset= Vec2()
        self.bg_color     = (20, 20, 30)
        self._offset      = Vec2(0, 0)

    def shake(self, amount=8.0):
        self.shake_amount = amount

    def update(self, dt, screen_w, screen_h):
        # follow
        if self.follow_target:
            t = self.follow_target.get(Transform)
            if t:
                target = t.position - Vec2(screen_w, screen_h) * 0.5 / self.zoom
                self._offset = self._offset.lerp(target, min(1.0, self.follow_speed * dt))
        # clamp to bounds
        if self.bounds:
            self._offset.x = max(self.bounds.x,
                                 min(self._offset.x, self.bounds.right - screen_w/self.zoom))
            self._offset.y = max(self.bounds.y,
                                 min(self._offset.y, self.bounds.bottom - screen_h/self.zoom))
        # shake
        if self.shake_amount > 0:
            import random
            self._shake_offset = Vec2(random.uniform(-1,1), random.uniform(-1,1)) * self.shake_amount
            self.shake_amount  = max(0, self.shake_amount - self.shake_decay * dt)
        else:
            self._shake_offset = Vec2()

    def world_to_screen(self, world: Vec2, screen_w, screen_h) -> Vec2:
        return (world - self._offset) * self.zoom + self._shake_offset

    def screen_to_world(self, screen: Vec2, screen_w, screen_h) -> Vec2:
        return (screen - self._shake_offset) / self.zoom + self._offset

class Light(Component):
    def __init__(self):
        super().__init__()
        self.color      = (255, 220, 160)
        self.radius     = 200
        self.intensity  = 1.0
        self.kind       = "point"    # "point" | "directional" | "ambient"
        self.direction  = Vec2(0, 1)

class ParticleEmitter(Component):
    def __init__(self):
        super().__init__()
        self.rate         = 20          # particles/sec
        self.lifetime     = 1.0
        self.speed        = Vec2(50, 100)
        self.gravity      = Vec2(0, 98)
        self.color_start  = (255, 200, 50)
        self.color_end    = (255, 50, 0)
        self.size_start   = 6.0
        self.size_end     = 0.0
        self.angle_spread = math.pi * 2
        self.direction    = Vec2(0, -1)
        self.burst        = False
        self.burst_count  = 30
        self.local_space  = True
        self._particles:  List[dict] = []
        self._emit_timer  = 0.0
        self.active       = True

    def emit_burst(self, count=None):
        import random
        n = count or self.burst_count
        tr = self.entity.get(Transform) if self.entity else None
        ox, oy = (tr.position.x, tr.position.y) if tr else (0,0)
        for _ in range(n):
            angle = math.atan2(self.direction.y, self.direction.x) + random.uniform(
                -self.angle_spread/2, self.angle_spread/2)
            spd = random.uniform(self.speed.x, self.speed.y)
            self._particles.append({
                'x': ox, 'y': oy,
                'vx': math.cos(angle)*spd, 'vy': math.sin(angle)*spd,
                'life': 1.0, 'max_life': self.lifetime + random.uniform(-0.2,0.2),
                't': 0.0
            })

    def update(self, dt):
        import random
        if self.active and not self.burst:
            self._emit_timer += dt
            spf = 1.0 / max(self.rate, 1)
            while self._emit_timer >= spf:
                self._emit_timer -= spf
                self.emit_burst(1)

        tr = self.entity.get(Transform) if self.entity else None
        ox, oy = (tr.position.x, tr.position.y) if tr else (0,0)

        alive = []
        for p in self._particles:
            p['t']  += dt
            p['life'] = 1.0 - p['t'] / max(p['max_life'], 0.001)
            if p['life'] <= 0:
                continue
            p['vx'] += self.gravity.x * dt
            p['vy'] += self.gravity.y * dt
            p['x']  += p['vx'] * dt
            p['y']  += p['vy'] * dt
            alive.append(p)
        self._particles = alive

class AudioSource(Component):
    def __init__(self):
        super().__init__()
        self.clip       = ""
        self.volume     = 1.0
        self.pitch      = 1.0
        self.loop       = False
        self.play_on_start = False
        self.spatial    = True
        self.max_dist   = 500.0
        self._playing   = False

class Script(Component):
    """Attach a GDL script file to an entity"""
    def __init__(self, script_path=""):
        super().__init__()
        self.script_path = script_path
        self._env: dict = {}
        self._on_start:  Optional[Callable] = None
        self._on_update: Optional[Callable] = None
        self._on_collision: Optional[Callable] = None
        self._on_destroy: Optional[Callable] = None

class TilemapRenderer(Component):
    def __init__(self):
        super().__init__()
        self.tile_width   = 32
        self.tile_height  = 32
        self.width_tiles  = 20
        self.height_tiles = 15
        self.tiles: Dict[Tuple[int,int], dict] = {}  # (tx,ty) -> {tex, color, solid}
        self.layer        = -1

    def set_tile(self, tx, ty, texture="", color=(80,80,150), solid=True):
        self.tiles[(tx,ty)] = {'tex': texture, 'color': color, 'solid': solid}

    def remove_tile(self, tx, ty):
        self.tiles.pop((tx,ty), None)

    def get_tile(self, tx, ty):
        return self.tiles.get((tx,ty))

    def world_to_tile(self, wx, wy):
        return int(wx // self.tile_width), int(wy // self.tile_height)

    def tile_to_world(self, tx, ty):
        return tx * self.tile_width, ty * self.tile_height

class DialogSystem(Component):
    """Undertale-style dialog box"""
    def __init__(self):
        super().__init__()
        self.speaker    = ""
        self.lines: List[str] = []
        self._line_idx  = 0
        self._char_idx  = 0
        self._timer     = 0.0
        self.char_delay = 0.03     # seconds per character
        self.active     = False
        self.portrait_texture = ""
        self.box_color  = (0,0,0)
        self.text_color = (255,255,255)
        self._on_end: Optional[Callable] = None

    def start(self, lines: List[str], speaker="", on_end=None):
        self.lines      = lines
        self.speaker    = speaker
        self._line_idx  = 0
        self._char_idx  = 0
        self._timer     = 0.0
        self.active     = True
        self._on_end    = on_end

    def advance(self):
        if not self.active:
            return
        line = self.lines[self._line_idx] if self._line_idx < len(self.lines) else ""
        if self._char_idx < len(line):
            self._char_idx = len(line)   # skip to end
        else:
            self._line_idx += 1
            self._char_idx  = 0
            if self._line_idx >= len(self.lines):
                self.active = False
                if self._on_end:
                    self._on_end()

    def update(self, dt):
        if not self.active:
            return
        if self._line_idx >= len(self.lines):
            return
        line = self.lines[self._line_idx]
        if self._char_idx < len(line):
            self._timer += dt
            while self._timer >= self.char_delay and self._char_idx < len(line):
                self._timer -= self.char_delay
                self._char_idx += 1

    @property
    def visible_text(self):
        if self._line_idx >= len(self.lines):
            return ""
        return self.lines[self._line_idx][:self._char_idx]

class BattleSystem(Component):
    """Turn-based battle (Undertale-style)"""
    class State(Enum):
        IDLE    = auto()
        PLAYER  = auto()
        ENEMY   = auto()
        VICTORY = auto()
        DEFEAT  = auto()

    def __init__(self):
        super().__init__()
        self.player_hp   = 20; self.player_max_hp = 20
        self.player_atk  = 10; self.player_def    = 0
        self.enemy_name  = "Monster"
        self.enemy_hp    = 100; self.enemy_max_hp = 100
        self.enemy_atk   = 5;  self.enemy_def     = 0
        self.mercy       = 0;  self.mercy_req      = 3
        self.state       = self.State.IDLE
        self.message     = ""
        self.bullets: List[dict] = []       # enemy attack bullets
        self.box_rect    = Rect2(0,0,200,150)  # bullet box
        self.soul_pos    = Vec2(100,75)     # player soul in bullet box
        self.soul_speed  = 150
        self.actions     = ["FIGHT","ACT","ITEM","MERCY"]
        self.selected_action = 0
        self.turn_timer  = 0.0
        self.enemy_patterns: List[Callable] = []
        self._pattern_idx = 0

    def start(self):
        self.state = self.State.PLAYER
        self.message = f"* {self.enemy_name} blocks the way!"

    def fight(self):
        import random
        dmg = max(0, self.player_atk - self.enemy_def + random.randint(-2,2))
        self.enemy_hp = max(0, self.enemy_hp - dmg)
        self.message  = f"* You attack for {dmg} damage!"
        if self.enemy_hp <= 0:
            self.state = self.State.VICTORY
        else:
            self._start_enemy_turn()

    def spare(self):
        self.mercy += 1
        self.message = f"* You show mercy. ({self.mercy}/{self.mercy_req})"
        if self.mercy >= self.mercy_req:
            self.state = self.State.VICTORY
            self.message = "* You spared the monster!"
        else:
            self._start_enemy_turn()

    def _start_enemy_turn(self):
        self.state = self.State.ENEMY
        self.bullets.clear()
        if self.enemy_patterns:
            pat = self.enemy_patterns[self._pattern_idx % len(self.enemy_patterns)]
            pat(self)
            self._pattern_idx += 1
        self.turn_timer = 3.0

    def update(self, dt):
        if self.state == self.State.ENEMY:
            self._update_bullets(dt)
            self.turn_timer -= dt
            if self.turn_timer <= 0:
                self.state = self.State.PLAYER
                self.bullets.clear()
                self.message = "* What will you do?"

    def _update_bullets(self, dt):
        soul = self.soul_pos
        alive = []
        for b in self.bullets:
            b['x'] += b['vx'] * dt
            b['y'] += b['vy'] * dt
            # bounce off box
            if b.get('bounce'):
                if b['x'] < self.box_rect.x+b['r'] or b['x'] > self.box_rect.right-b['r']:
                    b['vx'] *= -1
                if b['y'] < self.box_rect.y+b['r'] or b['y'] > self.box_rect.bottom-b['r']:
                    b['vy'] *= -1
            # hit soul
            dist = math.hypot(b['x']-soul.x, b['y']-soul.y)
            if dist < b['r'] + 5:
                dmg = b.get('dmg', max(1, self.enemy_atk - self.player_def))
                self.player_hp = max(0, self.player_hp - dmg)
                self.message = f"* {dmg} damage!"
                if self.player_hp <= 0:
                    self.state = self.State.DEFEAT
                b['hit'] = True
            if not b.get('hit'):
                alive.append(b)
        self.bullets = alive

# ─────────────────────────────────────────────
#  ENTITY
# ─────────────────────────────────────────────
class Entity:
    _id_counter = 0

    def __init__(self, name="Entity"):
        Entity._id_counter += 1
        self.id         = Entity._id_counter
        self.name       = name
        self.tag        = ""
        self.active     = True
        self.layer      = 0
        self._components: Dict[type, Component] = {}
        self._children:   List['Entity']        = []
        self._parent:     Optional['Entity']    = None
        self.scene:       Optional['Scene']     = None
        # always have a Transform
        self.add(Transform())

    # ── Component management ──
    def add(self, comp: Component) -> 'Entity':
        comp.entity = self
        self._components[type(comp)] = comp
        return self

    def get(self, comp_type: type) -> Optional[Component]:
        return self._components.get(comp_type)

    def has(self, comp_type: type) -> bool:
        return comp_type in self._components

    def remove(self, comp_type: type):
        self._components.pop(comp_type, None)

    def all_components(self):
        return list(self._components.values())

    # ── Hierarchy ──
    def add_child(self, child: 'Entity'):
        child._parent = self
        self._children.append(child)

    def remove_child(self, child: 'Entity'):
        child._parent = None
        self._children = [c for c in self._children if c is not child]

    @property
    def transform(self) -> Transform:
        return self._components[Transform]

    def __repr__(self):
        return f"Entity({self.id}, '{self.name}')"

    def to_dict(self):
        d = {'id': self.id, 'name': self.name, 'tag': self.tag,
             'layer': self.layer, 'active': self.active, 'components': {}}
        t = self.get(Transform)
        if t:
            d['components']['Transform'] = {
                'x': t.position.x, 'y': t.position.y,
                'rot': t.rotation, 'sx': t.scale.x, 'sy': t.scale.y}
        sr = self.get(SpriteRenderer)
        if sr:
            d['components']['SpriteRenderer'] = {
                'texture': sr.texture_name, 'color': list(sr.color),
                'w': sr.width, 'h': sr.height, 'layer': sr.layer}
        rb = self.get(Rigidbody)
        if rb:
            d['components']['Rigidbody'] = {
                'mass': rb.mass, 'gravity_scale': rb.gravity_scale,
                'drag': rb.drag, 'use_gravity': rb.use_gravity,
                'bounce': rb.bounce, 'friction': rb.friction,
                'is_kinematic': rb.is_kinematic, 'is_static': rb.is_static}
        col = self.get(Collider)
        if col:
            d['components']['Collider'] = {
                'kind': col.kind, 'w': col.width, 'h': col.height,
                'radius': col.radius, 'is_trigger': col.is_trigger}
        anim = self.get(Animator)
        if anim:
            anims_data = {}
            for aname, a in anim.animations.items():
                anims_data[aname] = {'frames': a.frames, 'fps': a.fps, 'loop': a.loop}
            d['components']['Animator'] = {'animations': anims_data, 'current': anim.current_anim}
        scr = self.get(Script)
        if scr:
            d['components']['Script'] = {'path': scr.script_path}
        pe = self.get(ParticleEmitter)
        if pe:
            d['components']['ParticleEmitter'] = {
                'rate': pe.rate, 'lifetime': pe.lifetime,
                'gravity': [pe.gravity.x, pe.gravity.y]}
        return d

# ─────────────────────────────────────────────
#  PHYSICS ENGINE
# ─────────────────────────────────────────────
class PhysicsWorld:
    def __init__(self):
        self.gravity      = Vec2(0, 980)    # pixels/s²  (like ~9.8 m/s² at 100px=1m)
        self.iterations   = 4
        self.enabled      = True
        self._collisions: List[Tuple[Entity,Entity]] = []

    def step(self, entities: List[Entity], dt: float):
        if not self.enabled:
            return
        sub_dt = dt / self.iterations
        for _ in range(self.iterations):
            self._integrate(entities, sub_dt)
            self._detect_and_resolve(entities)

    def _integrate(self, entities, dt):
        for e in entities:
            if not e.active:
                continue
            rb = e.get(Rigidbody)
            tr = e.get(Transform)
            if not rb or not tr or rb.is_static or rb.is_kinematic:
                continue
            # accumulate forces
            total_force = Vec2()
            for f in rb._forces:
                total_force = total_force + f
            rb._forces.clear()
            # gravity
            if rb.use_gravity:
                total_force = total_force + self.gravity * rb.mass * rb.gravity_scale
            # acceleration = F/m
            acc = total_force * (1.0 / max(rb.mass, 0.001))
            # integrate velocity
            rb.velocity = rb.velocity + acc * dt
            # drag
            rb.velocity = rb.velocity * (1.0 - rb.drag * dt * 60)
            # freeze axes
            if rb.freeze_x: rb.velocity.x = 0
            if rb.freeze_y: rb.velocity.y = 0
            # clamp velocity
            spd = rb.velocity.length()
            if spd > 2000: rb.velocity = rb.velocity.normalized() * 2000
            # move
            tr._prev_position = tr.position.copy()
            tr.position = tr.position + rb.velocity * dt
            # angular
            rb.angular_velocity *= (1.0 - rb.angular_drag * dt * 60)
            tr.rotation += rb.angular_velocity * dt

    def _detect_and_resolve(self, entities):
        colliders = [(e, e.get(Collider), e.get(Transform))
                     for e in entities if e.active and e.get(Collider) and e.get(Transform)]
        for i, (ea, ca, ta) in enumerate(colliders):
            for j in range(i+1, len(colliders)):
                eb, cb, tb = colliders[j]
                if not (ca.mask & (1 << cb.layer)):
                    continue
                if ca.kind == "box" and cb.kind == "box":
                    self._resolve_box_box(ea, ca, ta, eb, cb, tb)
                elif ca.kind == "circle" and cb.kind == "circle":
                    self._resolve_circle_circle(ea, ca, ta, eb, cb, tb)

    def _resolve_box_box(self, ea, ca, ta, eb, cb, tb):
        ra = ca.get_rect(ta.position)
        rb_rect = cb.get_rect(tb.position)
        if not ra.intersects(rb_rect):
            return
        self._fire_collision(ea, eb, ca, cb)
        rba = ea.get(Rigidbody)
        rbb = eb.get(Rigidbody)
        if ca.is_trigger or cb.is_trigger:
            return
        # MTV (minimum translation vector)
        ox = min(ra.right, rb_rect.right) - max(ra.left, rb_rect.left)
        oy = min(ra.bottom, rb_rect.bottom) - max(ra.top, rb_rect.top)
        if ox < oy:
            nx = 1 if ra.center.x < rb_rect.center.x else -1
            self._push(ea, rba, eb, rbb, Vec2(nx, 0), ox)
        else:
            ny = 1 if ra.center.y < rb_rect.center.y else -1
            self._push(ea, rba, eb, rbb, Vec2(0, ny), oy)

    def _resolve_circle_circle(self, ea, ca, ta, eb, cb, tb):
        diff  = tb.position - ta.position
        dist  = diff.length()
        radii = ca.radius + cb.radius
        if dist >= radii:
            return
        self._fire_collision(ea, eb, ca, cb)
        if ca.is_trigger or cb.is_trigger:
            return
        rba = ea.get(Rigidbody); rbb = eb.get(Rigidbody)
        n   = diff.normalized() if dist > 0.001 else Vec2(1,0)
        pen = radii - dist
        self._push(ea, rba, eb, rbb, n, pen)

    def _push(self, ea, rba, eb, rbb, normal, depth):
        static_a = rba is None or rba.is_static or rba.is_kinematic
        static_b = rbb is None or rbb.is_static or rbb.is_kinematic
        if static_a and static_b:
            return
        ta = ea.get(Transform); tb = eb.get(Transform)
        if static_a:
            tb.position = tb.position + normal * depth
            if rbb:
                rel_v = rbb.velocity.dot(normal)
                if rel_v < 0:
                    restitution = rbb.bounce
                    rbb.velocity = rbb.velocity - normal * (1+restitution) * rel_v
        elif static_b:
            ta.position = ta.position - normal * depth
            if rba:
                rel_v = rba.velocity.dot(-normal)
                if rel_v < 0:
                    restitution = rba.bounce
                    rba.velocity = rba.velocity + normal * (1+restitution) * rel_v
        else:
            ta.position = ta.position - normal * depth * 0.5
            tb.position = tb.position + normal * depth * 0.5
            if rba and rbb:
                rv      = rbb.velocity - rba.velocity
                v_along = rv.dot(normal)
                if v_along < 0:
                    e   = min(rba.bounce, rbb.bounce)
                    j   = -(1+e)*v_along / (1/rba.mass + 1/rbb.mass)
                    imp = normal * j
                    rba.velocity = rba.velocity - imp * (1/rba.mass)
                    rbb.velocity = rbb.velocity + imp * (1/rbb.mass)

    def _fire_collision(self, ea, eb, ca, cb):
        for fn in ca._on_enter: fn(eb)
        for fn in cb._on_enter: fn(ea)

# ─────────────────────────────────────────────
#  INPUT
# ─────────────────────────────────────────────
class Input:
    _keys_down:     set = set()
    _keys_pressed:  set = set()
    _keys_released: set = set()
    _mouse_pos:     Vec2 = Vec2()
    _mouse_buttons: set  = set()
    _mouse_pressed: set  = set()
    _mouse_released:set  = set()
    _mouse_wheel:   float= 0.0
    _axes: Dict[str, float] = {}
    _action_map: Dict[str, List[int]] = {
        'up':      [273, ord('w')],
        'down':    [274, ord('s')],
        'left':    [276, ord('a')],
        'right':   [275, ord('d')],
        'jump':    [32],               # space
        'confirm': [13, ord('z')],     # enter / z
        'cancel':  [27, ord('x')],
        'attack':  [ord('z')],
        'sprint':  [304],              # shift
    }

    @classmethod
    def begin_frame(cls):
        cls._keys_pressed  = set()
        cls._keys_released = set()
        cls._mouse_pressed  = set()
        cls._mouse_released = set()
        cls._mouse_wheel    = 0.0

    @classmethod
    def key_event(cls, key, down: bool):
        if down:
            cls._keys_pressed.add(key); cls._keys_down.add(key)
        else:
            cls._keys_released.add(key); cls._keys_down.discard(key)

    @classmethod
    def mouse_event(cls, btn, down: bool):
        if down:
            cls._mouse_pressed.add(btn); cls._mouse_buttons.add(btn)
        else:
            cls._mouse_released.add(btn); cls._mouse_buttons.discard(btn)

    @classmethod
    def mouse_move(cls, x, y): cls._mouse_pos = Vec2(x, y)

    @classmethod
    def is_key_down    (cls, key): return key in cls._keys_down
    @classmethod
    def is_key_pressed (cls, key): return key in cls._keys_pressed
    @classmethod
    def is_key_released(cls, key): return key in cls._keys_released
    @classmethod
    def is_action_down (cls, name):
        return any(cls.is_key_down(k)     for k in cls._action_map.get(name,[]))
    @classmethod
    def is_action_pressed(cls, name):
        return any(cls.is_key_pressed(k)  for k in cls._action_map.get(name,[]))
    @classmethod
    def get_axis(cls, neg_action, pos_action):
        return (-1 if cls.is_action_down(neg_action) else 0) + \
               ( 1 if cls.is_action_down(pos_action) else 0)
    @classmethod
    def mouse_pos(cls): return cls._mouse_pos.copy()
    @classmethod
    def is_mouse_down(cls, btn=0): return btn in cls._mouse_buttons
    @classmethod
    def is_mouse_pressed(cls, btn=0): return btn in cls._mouse_pressed

# ─────────────────────────────────────────────
#  RESOURCE MANAGER
# ─────────────────────────────────────────────
class ResourceManager:
    def __init__(self):
        self._textures: Dict[str, Any]  = {}
        self._sounds:   Dict[str, Any]  = {}
        self._fonts:    Dict[str, Any]  = {}
        self._data:     Dict[str, Any]  = {}
        self.search_paths: List[str]    = ['.', 'assets', 'assets/textures',
                                           'assets/sounds', 'assets/fonts']
        self._pygame_ready = False
        self._sdl  = None

    def init_pygame(self):
        try:
            import pygame
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.init()
            self._pygame_ready = True
        except ImportError:
            pass

    def _find_file(self, name: str) -> Optional[str]:
        if os.path.isabs(name) and os.path.exists(name):
            return name
        for sp in self.search_paths:
            p = os.path.join(sp, name)
            if os.path.exists(p):
                return p
        return None

    def load_texture(self, name: str):
        if name in self._textures:
            return self._textures[name]
        if not self._pygame_ready:
            return None
        try:
            import pygame
            path = self._find_file(name)
            if path:
                surf = pygame.image.load(path).convert_alpha()
                self._textures[name] = surf
                return surf
        except Exception as e:
            print(f"[Resource] Texture '{name}': {e}")
        return None

    def load_sound(self, name: str):
        if name in self._sounds:
            return self._sounds[name]
        if not self._pygame_ready:
            return None
        try:
            import pygame
            path = self._find_file(name)
            if path:
                snd = pygame.mixer.Sound(path)
                self._sounds[name] = snd
                return snd
        except Exception as e:
            print(f"[Resource] Sound '{name}': {e}")
        return None

    def load_font(self, name: str, size: int = 16):
        key = f"{name}_{size}"
        if key in self._fonts:
            return self._fonts[key]
        if not self._pygame_ready:
            return None
        try:
            import pygame
            path = self._find_file(name)
            fnt  = pygame.font.Font(path, size) if path else pygame.font.SysFont('monospace', size)
            self._fonts[key] = fnt
            return fnt
        except Exception as e:
            print(f"[Resource] Font '{name}': {e}")
        return None

    def make_colored_surface(self, w, h, color):
        if not self._pygame_ready:
            return None
        try:
            import pygame
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            surf.fill(color if len(color)==4 else (*color,255))
            return surf
        except:
            return None

Resources = ResourceManager()

# ─────────────────────────────────────────────
#  SCENE
# ─────────────────────────────────────────────
class Scene:
    def __init__(self, name="Scene"):
        self.name       = name
        self.entities:  List[Entity] = []
        self.physics    = PhysicsWorld()
        self._camera:   Optional[Entity] = None
        self._scripts:  List[Script] = []
        self.bg_color   = (20, 20, 30)
        self.tilemap:   Optional[TilemapRenderer] = None
        self._pending_add:    List[Entity] = []
        self._pending_remove: List[Entity] = []

    def add_entity(self, e: Entity) -> Entity:
        e.scene = self
        self._pending_add.append(e)
        return e

    def remove_entity(self, e: Entity):
        self._pending_remove.append(e)

    def instantiate(self, template: Entity, pos: Vec2 = None) -> Entity:
        """Clone template and add to scene"""
        import copy
        clone = copy.deepcopy(template)
        Entity._id_counter += 1
        clone.id = Entity._id_counter
        if pos:
            clone.transform.position = pos.copy()
        return self.add_entity(clone)

    def find(self, name: str) -> Optional[Entity]:
        for e in self.entities:
            if e.name == name:
                return e
        return None

    def find_by_tag(self, tag: str) -> List[Entity]:
        return [e for e in self.entities if e.tag == tag]

    def find_all(self, comp_type: type) -> List[Entity]:
        return [e for e in self.entities if e.has(comp_type)]

    def get_camera(self) -> Optional[Camera]:
        if self._camera:
            return self._camera.get(Camera)
        cams = self.find_all(Camera)
        return cams[0].get(Camera) if cams else None

    def _flush_pending(self):
        for e in self._pending_add:
            self.entities.append(e)
            # start scripts
            scr = e.get(Script)
            if scr and scr._on_start:
                try: scr._on_start()
                except Exception as ex: print(f"[Script] start error: {ex}")
        self._pending_add.clear()
        for e in self._pending_remove:
            scr = e.get(Script)
            if scr and scr._on_destroy:
                try: scr._on_destroy()
                except: pass
            self.entities = [x for x in self.entities if x is not e]
        self._pending_remove.clear()

    def update(self, dt: float):
        self._flush_pending()
        active = [e for e in self.entities if e.active]

        # physics
        self.physics.step(active, dt)

        # camera
        cam = self.get_camera()
        if cam:
            import pygame
            sw, sh = pygame.display.get_surface().get_size()
            cam.update(dt, sw, sh)

        # per-entity updates
        for e in active:
            # animator
            anim = e.get(Animator)
            if anim: anim.update(dt)
            # particles
            pe = e.get(ParticleEmitter)
            if pe: pe.update(dt)
            # dialog
            dlg = e.get(DialogSystem)
            if dlg: dlg.update(dt)
            # battle
            bat = e.get(BattleSystem)
            if bat: bat.update(dt)
            # script
            scr = e.get(Script)
            if scr and scr._on_update:
                try: scr._on_update(dt)
                except Exception as ex: print(f"[Script] update error in '{e.name}': {ex}")

    def to_dict(self):
        return {
            'name': self.name,
            'bg_color': list(self.bg_color),
            'physics': {
                'gravity_x': self.physics.gravity.x,
                'gravity_y': self.physics.gravity.y,
                'enabled': self.physics.enabled,
            },
            'entities': [e.to_dict() for e in self.entities]
        }

# ─────────────────────────────────────────────
#  ENGINE (top-level)
# ─────────────────────────────────────────────
class Engine:
    _instance = None

    def __init__(self):
        Engine._instance = self
        self.running       = False
        self.target_fps    = 60
        self.scenes: Dict[str, Scene] = {}
        self.active_scene: Optional[Scene] = None
        self._screen       = None
        self._clock        = None
        self.time_scale    = 1.0
        self.elapsed       = 0.0

    def add_scene(self, scene: Scene):
        self.scenes[scene.name] = scene
        if self.active_scene is None:
            self.active_scene = scene

    def load_scene(self, name: str):
        if name in self.scenes:
            self.active_scene = self.scenes[name]

    def quit(self):
        self.running = False

    @staticmethod
    def get() -> 'Engine':
        return Engine._instance
