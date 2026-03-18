"""
GDL Studio — Pygame Renderer + Game Runtime
Full rendering pipeline: sprites, tilemaps, particles, lighting, UI, battle, dialog
"""
import pygame, math, os, sys, time
from engine.core import (
    Vec2, Rect2, Entity, Scene, Component, Engine, Resources,
    Transform, SpriteRenderer, Animator, Rigidbody, Collider,
    Camera, Light, ParticleEmitter, AudioSource, Script,
    TilemapRenderer, DialogSystem, BattleSystem, Input,
    Animation
)

pygame.init()
if pygame.mixer:
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.mixer.init()

# ──────────────────────────────────────
#  TWEEN SYSTEM
# ──────────────────────────────────────
class Tween:
    EASES = {
        'linear':   lambda t: t,
        'ease_in':  lambda t: t*t,
        'ease_out': lambda t: 1-(1-t)*(1-t),
        'ease_io':  lambda t: t*t*(3-2*t),
        'bounce':   lambda t: abs(math.sin(t*math.pi*2.5)*(1-t)),
        'elastic':  lambda t: math.sin(13*math.pi/2*t)*pow(2,10*(t-1)) if t>0 else 0,
    }

    def __init__(self, obj, attr, start, end, duration, ease='ease_out', on_end=None, delay=0):
        self.obj=obj; self.attr=attr; self.start=start; self.end=end
        self.duration=duration; self.ease=self.EASES.get(ease, lambda t:t)
        self.on_end=on_end; self.delay=delay; self._t=0; self.done=False

    def update(self, dt):
        if self.done: return
        self.delay -= dt
        if self.delay > 0: return
        self._t = min(1.0, self._t + dt/max(self.duration,0.001))
        val = self.start + (self.end-self.start)*self.ease(self._t)
        try: setattr(self.obj, self.attr, val)
        except: pass
        if self._t >= 1.0:
            self.done = True
            if self.on_end: self.on_end()

class TweenManager:
    def __init__(self): self._tweens: list = []
    def add(self, *args, **kwargs) -> Tween:
        t = Tween(*args, **kwargs); self._tweens.append(t); return t
    def update(self, dt):
        self._tweens = [t for t in self._tweens if not t.done]
        for t in self._tweens: t.update(dt)

# ──────────────────────────────────────
#  RENDERER
# ──────────────────────────────────────
class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.sw, self.sh = screen.get_size()
        self._debug = False
        self._light_surf: pygame.Surface = None
        self._use_lighting = False
        self._font_cache: dict = {}
        self._surf_cache:  dict = {}

    def get_font(self, size=14, name=None) -> pygame.font.Font:
        key = (name, size)
        if key not in self._font_cache:
            if name and os.path.exists(name):
                self._font_cache[key] = pygame.font.Font(name, size)
            else:
                self._font_cache[key] = pygame.font.SysFont('consolas,monospace', size)
        return self._font_cache[key]

    def world_to_screen(self, world_pos: Vec2, cam: Camera) -> pygame.Vector2:
        sp = cam.world_to_screen(world_pos, self.sw, self.sh)
        return pygame.Vector2(sp.x, sp.y)

    def clear(self, color=(20,20,30)):
        self.screen.fill(color)

    def draw_scene(self, scene: Scene):
        cam = scene.get_camera()
        if not cam:
            cam_entity = Entity("_DefaultCam")
            cam_entity.add(Camera())
            cam = cam_entity.get(Camera)

        # Tilemap (background layer)
        for e in scene.entities:
            tm = e.get(TilemapRenderer)
            if tm and tm.layer < 0:
                self._draw_tilemap(tm, e.get(Transform), cam)

        # Sort entities by layer and Y position
        renderable = [(e, e.get(SpriteRenderer)) for e in scene.entities
                      if e.active and e.get(SpriteRenderer) and e.get(SpriteRenderer).visible]
        renderable.sort(key=lambda x: (x[1].layer, x[0].transform.position.y))

        # Draw entities
        for e, sr in renderable:
            self._draw_sprite(e, sr, cam)

        # Particles
        for e in scene.entities:
            if e.active:
                pe = e.get(ParticleEmitter)
                if pe: self._draw_particles(pe, cam)

        # Tilemap (foreground layer)
        for e in scene.entities:
            tm = e.get(TilemapRenderer)
            if tm and tm.layer >= 0:
                self._draw_tilemap(tm, e.get(Transform), cam)

        # Lighting pass
        if self._use_lighting:
            self._draw_lighting(scene, cam)

        # UI / Dialog / Battle (screen space)
        for e in scene.entities:
            if e.active:
                dlg = e.get(DialogSystem)
                if dlg and dlg.active:
                    self._draw_dialog(dlg)
                bat = e.get(BattleSystem)
                if bat and bat.state != BattleSystem.State.IDLE:
                    self._draw_battle(bat)

        # Debug
        if self._debug:
            self._draw_debug(scene, cam)

    def _draw_sprite(self, e: Entity, sr: SpriteRenderer, cam: Camera):
        tr = e.get(Transform)
        if not tr: return

        # Animator
        anim = e.get(Animator)
        tex_name = (anim.current_texture if anim else None) or sr.texture_name

        pos = cam.world_to_screen(tr.position + sr.offset, self.sw, self.sh)
        w   = int(sr.width  * tr.scale.x * cam.zoom)
        h   = int(sr.height * tr.scale.y * cam.zoom)
        if w <= 0 or h <= 0: return

        # Frustum cull
        if pos.x + w < 0 or pos.x - w > self.sw or pos.y + h < 0 or pos.y - h > self.sh:
            return

        surf = None
        if tex_name:
            surf = Resources.load_texture(tex_name)
        if surf:
            surf_scaled = pygame.transform.scale(surf, (w, h))
            if sr.flip_x or sr.flip_y:
                surf_scaled = pygame.transform.flip(surf_scaled, sr.flip_x, sr.flip_y)
            if tr.rotation != 0:
                surf_scaled = pygame.transform.rotate(surf_scaled, -math.degrees(tr.rotation))
            if sr.alpha < 255:
                surf_scaled.set_alpha(sr.alpha)
            rect = surf_scaled.get_rect(center=(int(pos.x), int(pos.y)))
            self.screen.blit(surf_scaled, rect)
        else:
            # Colored rectangle
            color = (*sr.color[:3], min(255, sr.alpha)) if len(sr.color)==3 else sr.color
            rect = pygame.Rect(int(pos.x - w//2), int(pos.y - h//2), w, h)
            surf_r = pygame.Surface((w, h), pygame.SRCALPHA)
            surf_r.fill(color)
            if tr.rotation != 0:
                surf_r = pygame.transform.rotate(surf_r, -math.degrees(tr.rotation))
            self.screen.blit(surf_r, surf_r.get_rect(center=rect.center))

    def _draw_tilemap(self, tm: TilemapRenderer, tr: Transform, cam: Camera):
        ox = tr.position.x if tr else 0
        oy = tr.position.y if tr else 0
        tw = int(tm.tile_width  * cam.zoom)
        th = int(tm.tile_height * cam.zoom)
        for (tx, ty), tile in tm.tiles.items():
            wx = ox + tx * tm.tile_width
            wy = oy + ty * tm.tile_height
            sp = cam.world_to_screen(Vec2(wx, wy), self.sw, self.sh)
            sx, sy = int(sp.x), int(sp.y)
            if sx + tw < 0 or sx > self.sw or sy + th < 0 or sy > self.sh:
                continue
            color = tile.get('color', (80,80,150))
            tex   = tile.get('tex', '')
            surf  = Resources.load_texture(tex) if tex else None
            if surf:
                scaled = pygame.transform.scale(surf, (tw, th))
                self.screen.blit(scaled, (sx, sy))
            else:
                pygame.draw.rect(self.screen, color, (sx, sy, tw, th))

    def _draw_particles(self, pe: ParticleEmitter, cam: Camera):
        for p in pe._particles:
            t = p['life']
            r = int(pe.size_start + (pe.size_end - pe.size_start) * (1-t))
            if r <= 0: continue
            cr = tuple(int(pe.color_start[i] + (pe.color_end[i]-pe.color_start[i])*(1-t))
                       for i in range(3))
            alpha = int(255 * t)
            sp = cam.world_to_screen(Vec2(p['x'], p['y']), self.sw, self.sh)
            s  = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*cr, alpha), (r, r), r)
            self.screen.blit(s, (int(sp.x)-r, int(sp.y)-r))

    def _draw_lighting(self, scene: Scene, cam: Camera):
        if not self._light_surf or self._light_surf.get_size() != self.screen.get_size():
            self._light_surf = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        self._light_surf.fill((0,0,0,200))  # ambient darkness
        for e in scene.entities:
            if not e.active: continue
            lt = e.get(Light)
            if not lt: continue
            tr = e.get(Transform)
            if not tr: continue
            sp = cam.world_to_screen(tr.position, self.sw, self.sh)
            r  = int(lt.radius * cam.zoom)
            for rr in range(r, 0, -2):
                a = int(200 * (1 - rr/r) * lt.intensity)
                c = (*lt.color, a)
                pygame.draw.circle(self._light_surf, c, (int(sp.x), int(sp.y)), rr)
        # blend
        self._light_surf.set_alpha(220)
        self.screen.blit(self._light_surf, (0,0), special_flags=pygame.BLEND_RGBA_SUB)

    def _draw_dialog(self, dlg: DialogSystem):
        sw, sh = self.screen.get_size()
        bh = 140
        by = sh - bh - 16
        bx = 20
        bw = sw - 40
        # box background
        surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
        surf.fill((0,0,0,230))
        pygame.draw.rect(surf, (255,255,255,200), (0,0,bw,bh), 2)
        self.screen.blit(surf, (bx, by))
        # portrait
        px = bx + 12
        if dlg.portrait_texture:
            pt = Resources.load_texture(dlg.portrait_texture)
            if pt:
                ps = pygame.transform.scale(pt, (80, 80))
                self.screen.blit(ps, (px, by+30))
        # speaker name
        fn = self.get_font(20)
        if dlg.speaker:
            label = fn.render(f"  {dlg.speaker}  ", True, (255,255,255), (30,30,30))
            self.screen.blit(label, (bx+8, by-22))
        # text (Undertale typewriter)
        ft = self.get_font(18)
        text = dlg.visible_text
        tx = bx + (100 if dlg.portrait_texture else 16)
        ty = by + 16
        max_w = bw - (tx - bx) - 16
        words = text.split(' ')
        line = ''
        for word in words:
            test = line + word + ' '
            if ft.size(test)[0] > max_w:
                surf_t = ft.render(line, True, dlg.text_color)
                self.screen.blit(surf_t, (tx, ty)); ty += 26; line = ''
            line += word + ' '
        if line:
            surf_t = ft.render(line, True, dlg.text_color)
            self.screen.blit(surf_t, (tx, ty))
        # arrow blink
        if dlg._char_idx >= len(dlg.lines[dlg._line_idx] if dlg._line_idx < len(dlg.lines) else ''):
            if int(time.time()*4) % 2 == 0:
                arr = ft.render('▼', True, (200,200,200))
                self.screen.blit(arr, (bx+bw-28, by+bh-26))

    def _draw_battle(self, bat: BattleSystem):
        sw, sh = self.screen.get_size()
        # Dark overlay
        overlay = pygame.Surface((sw,sh), pygame.SRCALPHA); overlay.fill((0,0,0,180))
        self.screen.blit(overlay,(0,0))

        # Battle UI
        panel_w, panel_h = 600, 400
        px = (sw - panel_w) // 2; py = (sh - panel_h) // 2
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((10,10,20,240))
        pygame.draw.rect(panel,(255,255,255,200),(0,0,panel_w,panel_h),2)
        self.screen.blit(panel,(px,py))

        f = self.get_font(18); fb = self.get_font(22)

        # Enemy name + HP
        self.screen.blit(fb.render(bat.enemy_name, True, (255,200,100)), (px+20,py+15))
        hp_pct = bat.enemy_hp / max(bat.enemy_max_hp,1)
        pygame.draw.rect(self.screen,(60,60,60),(px+20,py+45,300,12))
        pygame.draw.rect(self.screen,(80,220,80),(px+20,py+45,int(300*hp_pct),12))
        self.screen.blit(f.render(f"HP: {bat.enemy_hp}/{bat.enemy_max_hp}",True,(200,255,200)),(px+330,py+42))

        # Player HP
        php = bat.player_hp/max(bat.player_max_hp,1)
        pygame.draw.rect(self.screen,(60,60,60),(px+20,py+65,200,10))
        pygame.draw.rect(self.screen,(255,180,60),(px+20,py+65,int(200*php),10))
        self.screen.blit(f.render(f"♥ {bat.player_hp}/{bat.player_max_hp}",True,(255,150,150)),(px+230,py+62))

        # Message
        msg_surf = f.render(bat.message, True, (220,220,220))
        self.screen.blit(msg_surf, (px+20, py+90))

        if bat.state == BattleSystem.State.PLAYER:
            # Action buttons
            for i, act in enumerate(bat.actions):
                cx = px + 30 + i*140; cy = py + panel_h - 60
                color = (255,200,50) if i==bat.selected_action else (80,80,100)
                pygame.draw.rect(self.screen,color,(cx,cy,120,36),0 if i==bat.selected_action else 2,6)
                lbl = fb.render(act, True, (0,0,0) if i==bat.selected_action else (200,200,200))
                self.screen.blit(lbl,(cx+10,cy+7))

        elif bat.state == BattleSystem.State.ENEMY:
            # Bullet box
            br = bat.box_rect
            bx2 = px + (panel_w - br.w)//2; by2 = py + 130
            bat.box_rect = Rect2(bx2, by2, br.w, br.h)
            pygame.draw.rect(self.screen,(255,255,255),(bx2,by2,int(br.w),int(br.h)),2)
            # Soul
            sx = bx2 + bat.soul_pos.x; sy = by2 + bat.soul_pos.y
            pygame.draw.polygon(self.screen,(255,50,50),
                [(sx,sy-8),(sx-6,sy+4),(sx+6,sy+4)])
            # Bullets
            for b in bat.bullets:
                sc_x = bx2 + b['x']; sc_y = by2 + b['y']
                pygame.draw.circle(self.screen,(255,255,100),(int(sc_x),int(sc_y)),int(b['r']))
            # Timer bar
            t_frac = max(0, bat.turn_timer/3.0)
            pygame.draw.rect(self.screen,(60,60,60),(px+20,py+300,560,8))
            pygame.draw.rect(self.screen,(100,180,255),(px+20,py+300,int(560*t_frac),8))

        elif bat.state in (BattleSystem.State.VICTORY, BattleSystem.State.DEFEAT):
            col = (255,255,100) if bat.state==BattleSystem.State.VICTORY else (255,80,80)
            msg = "✨ YOU WIN!" if bat.state==BattleSystem.State.VICTORY else "💀 GAME OVER"
            big = self.get_font(36)
            lbl = big.render(msg, True, col)
            self.screen.blit(lbl, (px + (panel_w-lbl.get_width())//2, py+150))

    def _draw_debug(self, scene: Scene, cam: Camera):
        f = self.get_font(11)
        for e in scene.entities:
            if not e.active: continue
            tr = e.get(Transform)
            col = e.get(Collider)
            rb  = e.get(Rigidbody)
            if not tr: continue
            sp = cam.world_to_screen(tr.position, self.sw, self.sh)
            # name
            self.screen.blit(f.render(e.name, True, (0,255,255)),(int(sp.x),int(sp.y)-14))
            # collider outline
            if col:
                if col.kind == 'circle':
                    r = int(col.radius * cam.zoom)
                    pygame.draw.circle(self.screen,(0,255,0),(int(sp.x),int(sp.y)),r,1)
                else:
                    w2 = int(col.width*cam.zoom/2); h2 = int(col.height*cam.zoom/2)
                    pygame.draw.rect(self.screen,(0,255,0),(int(sp.x)-w2,int(sp.y)-h2,w2*2,h2*2),1)
            # velocity arrow
            if rb and rb.velocity.length() > 1:
                vn = rb.velocity.normalized()*20
                ex = int(sp.x+vn.x); ey = int(sp.y+vn.y)
                pygame.draw.line(self.screen,(255,100,0),(int(sp.x),int(sp.y)),(ex,ey),2)

    def draw_text(self, text, x, y, color=(255,255,255), size=16, anchor='topleft'):
        f   = self.get_font(size)
        sur = f.render(str(text), True, color)
        r   = sur.get_rect(**{anchor: (x,y)})
        self.screen.blit(sur, r)

    def draw_rect(self, rect: Rect2, color, filled=True, border=0):
        r = pygame.Rect(int(rect.x), int(rect.y), int(rect.w), int(rect.h))
        if filled:
            pygame.draw.rect(self.screen, color, r, border_radius=border)
        else:
            pygame.draw.rect(self.screen, color, r, 1, border_radius=border)

    def draw_circle(self, cx, cy, r, color, filled=True):
        pygame.draw.circle(self.screen, color, (int(cx),int(cy)), int(r), 0 if filled else 1)

    def draw_line(self, x1, y1, x2, y2, color, width=1):
        pygame.draw.line(self.screen, color, (int(x1),int(y1)), (int(x2),int(y2)), width)

# ──────────────────────────────────────
#  GAME RUNTIME
# ──────────────────────────────────────
class GameRuntime:
    def __init__(self, scene: Scene, width=800, height=600,
                 title="GDL Game", fps=60, fullscreen=False):
        flags = pygame.FULLSCREEN if fullscreen else pygame.RESIZABLE
        self.screen   = pygame.display.set_mode((width, height), flags)
        pygame.display.set_caption(title)
        pygame.display.set_icon(self._make_icon())
        self.scene    = scene
        self.renderer = Renderer(self.screen)
        self.tweens   = TweenManager()
        self.clock    = pygame.time.Clock()
        self.fps      = fps
        self.running  = False
        self._on_start:  list = []
        self._on_update: list = []
        Resources.init_pygame()
        Resources.search_paths.extend(['assets','assets/textures','assets/sounds'])

    def _make_icon(self):
        icon = pygame.Surface((32,32))
        icon.fill((233,69,96))
        pygame.draw.polygon(icon,(255,255,255),[(16,4),(6,28),(26,28)])
        return icon

    def on_start(self, fn): self._on_start.append(fn)
    def on_update(self, fn): self._on_update.append(fn)

    def run(self):
        self.running = True
        # Connect Input to GDL builtins
        for e in self.scene.entities:
            scr = e.get(Script)
            if scr and hasattr(scr,'_interp'):
                interp = scr._interp
                interp._global_env['key_pressed'] = lambda k: Input.is_key_pressed(ord(k[0]) if isinstance(k,str) else k)
                interp._global_env['key_held']    = lambda k: Input.is_key_down(ord(k[0]) if isinstance(k,str) else k)
                interp._global_env['mouse_pos']   = lambda: Input.mouse_pos()
                interp._global_env['tween']       = lambda obj,attr,start,end,dur,ease='ease_out': self.tweens.add(obj,attr,start,end,dur,ease)

        # Start hooks
        for fn in self._on_start: fn(self.scene)

        while self.running:
            dt = min(self.clock.tick(self.fps) / 1000.0, 0.05)
            Input.begin_frame()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    Input.key_event(event.key, True)
                    # Battle input
                    self._handle_battle_input(event.key)
                    # Dialog advance
                    if event.key in (pygame.K_z, pygame.K_RETURN, pygame.K_SPACE):
                        self._handle_dialog_advance()
                elif event.type == pygame.KEYUP:
                    Input.key_event(event.key, False)
                elif event.type == pygame.MOUSEMOTION:
                    Input.mouse_move(*event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    Input.mouse_event(event.button-1, True)
                elif event.type == pygame.MOUSEBUTTONUP:
                    Input.mouse_event(event.button-1, False)
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                    self.renderer.screen = self.screen
                    self.renderer.sw, self.renderer.sh = event.size

            # Update callbacks
            for fn in self._on_update: fn(self.scene, dt)
            # Scene update
            self.scene.update(dt)
            # Tweens
            self.tweens.update(dt)
            # Battle soul movement
            self._update_battle_soul(dt)

            # Render
            cam = self.scene.get_camera()
            bg  = cam.bg_color if cam else self.scene.bg_color
            self.renderer.clear(bg)
            self.renderer.draw_scene(self.scene)
            # HUD
            self._draw_hud()
            pygame.display.flip()

        pygame.quit()

    def _handle_battle_input(self, key):
        for e in self.scene.entities:
            bat = e.get(BattleSystem)
            if not bat or bat.state != BattleSystem.State.PLAYER: continue
            if key == pygame.K_LEFT:  bat.selected_action = (bat.selected_action-1)%len(bat.actions)
            if key == pygame.K_RIGHT: bat.selected_action = (bat.selected_action+1)%len(bat.actions)
            if key in (pygame.K_z, pygame.K_RETURN):
                act = bat.actions[bat.selected_action]
                if act == 'FIGHT': bat.fight()
                elif act == 'MERCY': bat.spare()
                elif act == 'ACT': bat.message = "* You try to ACT..."; bat._start_enemy_turn()
                elif act == 'ITEM': bat.message = "* No items!"

    def _update_battle_soul(self, dt):
        for e in self.scene.entities:
            bat = e.get(BattleSystem)
            if not bat or bat.state != BattleSystem.State.ENEMY: continue
            spd = bat.soul_speed * dt
            sp  = bat.soul_pos
            box = bat.box_rect
            if Input.is_key_down(pygame.K_LEFT):  sp.x = max(0, sp.x-spd)
            if Input.is_key_down(pygame.K_RIGHT): sp.x = min(box.w, sp.x+spd)
            if Input.is_key_down(pygame.K_UP):    sp.y = max(0, sp.y-spd)
            if Input.is_key_down(pygame.K_DOWN):  sp.y = min(box.h, sp.y+spd)

    def _handle_dialog_advance(self):
        for e in self.scene.entities:
            dlg = e.get(DialogSystem)
            if dlg and dlg.active: dlg.advance()

    def _draw_hud(self):
        sw, sh = self.screen.get_size()
        f = self.renderer.get_font(13)
        fps_surf = f.render(f"FPS: {int(self.clock.get_fps())}", True, (150,150,150))
        self.screen.blit(fps_surf, (sw-80, 4))

def run_scene(scene: Scene, **kwargs):
    """Convenience function to run a scene"""
    rt = GameRuntime(scene, **kwargs)
    rt.run()
