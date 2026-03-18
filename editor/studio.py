"""
GDL Studio — Full GUI Editor
Tkinter-based editor: scene, tilemap, entity inspector, animator, GDL code, dialog, project manager
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser, simpledialog
import json, os, sys, math, time, threading, copy, re
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.core import (
    Vec2, Rect2, Entity, Scene, Engine, Resources,
    Transform, SpriteRenderer, Animator, Animation,
    Rigidbody, Collider, Camera, Light, ParticleEmitter,
    AudioSource, Script, TilemapRenderer, DialogSystem, BattleSystem
)
from engine.gdl_lang import Lexer, Parser, Interpreter, compile_gdl

# ──────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────
DARK   = '#0d0d14'
DARK2  = '#13131f'
DARK3  = '#1a1a2e'
PANEL  = '#16213e'
PANEL2 = '#0f3460'
ACCENT = '#e94560'
ACCENT2= '#f5a623'
ACCENT3= '#50fa7b'
TEXT   = '#e0e0ff'
TEXT2  = '#8888aa'
BORDER = '#2a2a4a'

# ──────────────────────────────────────
#  THEME
# ──────────────────────────────────────
def apply_theme(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=DARK2, foreground=TEXT, fieldbackground=DARK3,
                    bordercolor=BORDER, darkcolor=DARK, lightcolor=DARK3,
                    troughcolor=DARK3, selectbackground=PANEL2, selectforeground=TEXT)
    style.configure('TNotebook', background=DARK2, tabmargins=0)
    style.configure('TNotebook.Tab', background=DARK3, foreground=TEXT2,
                    padding=[10,4], borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected',DARK2)], foreground=[('selected',TEXT)])
    style.configure('TFrame',  background=DARK2)
    style.configure('TLabel',  background=DARK2, foreground=TEXT)
    style.configure('TButton', background=PANEL, foreground=TEXT2, borderwidth=1, relief='flat')
    style.map('TButton', background=[('active',PANEL2)], foreground=[('active',TEXT)])
    style.configure('Treeview', background=DARK3, foreground=TEXT2,
                    fieldbackground=DARK3, rowheight=22, borderwidth=0)
    style.map('Treeview', background=[('selected',PANEL2)], foreground=[('selected',TEXT)])
    style.configure('TScrollbar', background=DARK3, troughcolor=DARK2, borderwidth=0)
    style.configure('TPanedwindow', background=DARK2)
    style.configure('TLabelframe', background=DARK2, foreground=TEXT2,
                    bordercolor=BORDER, relief='groove')
    style.configure('TLabelframe.Label', background=DARK2, foreground=TEXT2)
    style.configure('TScale', background=DARK2, troughcolor=DARK3)
    style.configure('TCheckbutton', background=DARK2, foreground=TEXT)
    style.configure('TCombobox', fieldbackground=DARK3, background=DARK3,
                    foreground=TEXT, arrowcolor=TEXT2)
    style.configure('TEntry', fieldbackground=DARK3, foreground=TEXT, insertcolor=TEXT)
    style.configure('TSpinbox', fieldbackground=DARK3, foreground=TEXT)

# ──────────────────────────────────────
#  CANVAS SCENE EDITOR
# ──────────────────────────────────────
class SceneCanvas(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=DARK3)
        self.app = app
        self.scene: Scene = None
        self.cam_x = 0.0; self.cam_y = 0.0
        self.zoom  = 1.0
        self.tool  = 'select'          # select|draw|erase|entity|light|particle
        self.tile_color = '#4444aa'
        self.tile_texture = ''
        self.snap  = True
        self.grid_size = 32
        self._drag_start = None
        self._sel_entity: Entity = None
        self._drag_entity = False
        self._hover_tx = -1; self._hover_ty = -1

        # Toolbar
        tb = tk.Frame(self, bg=DARK2, pady=2)
        tb.pack(fill='x', side='top')
        tools = [('↖ Select','select'),('✏ Draw','draw'),('⬜ Erase','erase'),
                 ('👾 Entity','entity'),('💡 Light','light'),('✨ Particles','particle')]
        self._tool_btns = {}
        for label, t in tools:
            b = tk.Button(tb, text=label, bg=PANEL, fg=TEXT2, relief='flat',
                          padx=6, pady=2, font=('Consolas',10),
                          command=lambda t=t: self.set_tool(t))
            b.pack(side='left', padx=2)
            self._tool_btns[t] = b

        tk.Label(tb, text='  Grid:', bg=DARK2, fg=TEXT2, font=('Consolas',10)).pack(side='left')
        self._grid_var = tk.IntVar(value=32)
        tk.Spinbox(tb, from_=8, to=128, increment=8, textvariable=self._grid_var,
                   width=4, bg=DARK3, fg=TEXT, relief='flat',
                   command=lambda: setattr(self,'grid_size',self._grid_var.get())).pack(side='left')

        self._snap_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tb, text='Snap', variable=self._snap_var, bg=DARK2, fg=TEXT2,
                       selectcolor=DARK3, activebackground=DARK2,
                       command=lambda: setattr(self,'snap',self._snap_var.get())).pack(side='left',padx=4)

        # Zoom
        tk.Button(tb, text='-', bg=PANEL, fg=TEXT2, relief='flat', padx=6,
                  command=lambda: self._zoom(-0.25)).pack(side='right',padx=2)
        self._zoom_label = tk.Label(tb, text='100%', bg=DARK2, fg=TEXT2, font=('Consolas',10))
        self._zoom_label.pack(side='right')
        tk.Button(tb, text='+', bg=PANEL, fg=TEXT2, relief='flat', padx=6,
                  command=lambda: self._zoom(0.25)).pack(side='right',padx=2)
        tk.Button(tb, text='⟳', bg=PANEL, fg=TEXT2, relief='flat', padx=6,
                  command=self.reset_view).pack(side='right',padx=4)

        # Canvas
        cf = tk.Frame(self, bg=DARK3)
        cf.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(cf, bg='#050510', cursor='crosshair',
                                highlightthickness=0, relief='flat')
        vbar = ttk.Scrollbar(cf, orient='vertical', command=self.canvas.yview)
        hbar = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.pack(side='right', fill='y')
        hbar.pack(side='bottom', fill='x')
        self.canvas.pack(fill='both', expand=True)

        # Status bar
        self._status = tk.StringVar(value='Ready')
        tk.Label(self, textvariable=self._status, bg=DARK, fg=TEXT2,
                 font=('Consolas',10), anchor='w').pack(fill='x', side='bottom')

        # Bindings
        self.canvas.bind('<ButtonPress-1>',   self._on_press)
        self.canvas.bind('<B1-Motion>',       self._on_drag)
        self.canvas.bind('<ButtonRelease-1>', self._on_release)
        self.canvas.bind('<ButtonPress-2>',   self._on_mmb_press)
        self.canvas.bind('<B2-Motion>',       self._on_mmb_drag)
        self.canvas.bind('<ButtonPress-3>',   self._on_rmb)
        self.canvas.bind('<MouseWheel>',      self._on_wheel)
        self.canvas.bind('<Configure>',       lambda e: self.redraw())
        self.canvas.bind('<Motion>',          self._on_hover)
        self.bind_all('<Delete>',             self._on_delete)

        self.set_tool('select')
        self._draw_loop()

    def set_tool(self, t):
        self.tool = t
        for tt, btn in self._tool_btns.items():
            btn.config(bg=ACCENT if tt==t else PANEL,
                       fg='#000' if tt==t else TEXT2)

    def _zoom(self, delta):
        self.zoom = max(0.25, min(4.0, self.zoom + delta))
        self._zoom_label.config(text=f'{int(self.zoom*100)}%')
        self.redraw()

    def reset_view(self):
        self.cam_x=0; self.cam_y=0; self.zoom=1.0
        self._zoom_label.config(text='100%'); self.redraw()

    def load_scene(self, scene: Scene):
        self.scene = scene
        self.grid_size = 32
        self.reset_view()

    def canvas_to_world(self, cx, cy):
        return (cx / self.zoom + self.cam_x), (cy / self.zoom + self.cam_y)

    def world_to_canvas(self, wx, wy):
        return (wx - self.cam_x) * self.zoom, (wy - self.cam_y) * self.zoom

    def snap_to_grid(self, wx, wy):
        g = self.grid_size
        return round(wx/g)*g, round(wy/g)*g

    # ── Events ──
    def _on_press(self, e):
        wx, wy = self.canvas_to_world(e.x, e.y)
        if self.snap: wx,wy = self.snap_to_grid(wx,wy)
        self._drag_start = (e.x, e.y, self.cam_x, self.cam_y)

        if self.tool == 'select':
            self._sel_entity = None
            if self.scene:
                for ent in reversed(self.scene.entities):
                    tr = ent.get(Transform); sr = ent.get(SpriteRenderer)
                    if not tr or not sr: continue
                    ew = sr.width/2; eh = sr.height/2
                    ep = tr.position
                    if abs(wx-ep.x)<ew and abs(wy-ep.y)<eh:
                        self._sel_entity = ent
                        self._drag_entity = True
                        self.app.inspector.load_entity(ent)
                        break

        elif self.tool == 'draw' and self.scene:
            self._paint_tile(wx, wy)

        elif self.tool == 'erase' and self.scene:
            self._erase_tile(wx, wy)

        elif self.tool == 'entity' and self.scene:
            self._place_entity(wx, wy)

        elif self.tool == 'light' and self.scene:
            self._place_light(wx, wy)

        elif self.tool == 'particle' and self.scene:
            self._place_particle(wx, wy)

    def _on_drag(self, e):
        if not self._drag_start: return
        sx,sy,cx0,cy0 = self._drag_start
        wx, wy = self.canvas_to_world(e.x, e.y)
        if self.snap: wx,wy = self.snap_to_grid(wx,wy)

        if self.tool == 'select' and self._drag_entity and self._sel_entity:
            self._sel_entity.transform.position = Vec2(wx, wy)
            self.app.inspector.refresh_position()

        elif self.tool == 'draw' and self.scene:
            self._paint_tile(wx, wy)

        elif self.tool == 'erase' and self.scene:
            self._erase_tile(wx, wy)

    def _on_release(self, e):
        self._drag_entity = False

    def _on_mmb_press(self, e):
        self._drag_start = (e.x, e.y, self.cam_x, self.cam_y)

    def _on_mmb_drag(self, e):
        if not self._drag_start: return
        sx,sy,cx0,cy0 = self._drag_start
        self.cam_x = cx0 - (e.x - sx)/self.zoom
        self.cam_y = cy0 - (e.y - sy)/self.zoom

    def _on_rmb(self, e):
        wx,wy = self.canvas_to_world(e.x, e.y)
        if self.snap: wx,wy = self.snap_to_grid(wx,wy)
        if self.tool in ('draw','erase') and self.scene:
            self._erase_tile(wx, wy)

    def _on_wheel(self, e):
        factor = 1.1 if e.delta > 0 else 0.9
        self.zoom = max(0.1, min(8.0, self.zoom * factor))
        self._zoom_label.config(text=f'{int(self.zoom*100)}%')

    def _on_hover(self, e):
        wx, wy = self.canvas_to_world(e.x, e.y)
        g = self.grid_size
        self._hover_tx = int(wx // g)
        self._hover_ty = int(wy // g)
        self._status.set(f'World: ({wx:.0f}, {wy:.0f})  Tile: ({self._hover_tx}, {self._hover_ty})  Zoom: {self.zoom:.2f}x  Tool: {self.tool}')

    def _on_delete(self, e):
        if self._sel_entity and self.scene:
            self.scene.remove_entity(self._sel_entity)
            self.scene._flush_pending()
            self._sel_entity = None
            self.app.refresh_entity_list()

    # ── Tile/Entity actions ──
    def _get_tilemap(self) -> TilemapRenderer:
        for ent in self.scene.entities:
            tm = ent.get(TilemapRenderer)
            if tm: return tm
        # Create default tilemap entity
        e = Entity('Tilemap')
        tm = TilemapRenderer()
        e.add(tm)
        self.scene.add_entity(e)
        self.scene._flush_pending()
        return tm

    def _paint_tile(self, wx, wy):
        tm = self._get_tilemap()
        g  = self.grid_size
        tx = int(wx // g); ty = int(wy // g)
        tm.tile_width = g; tm.tile_height = g
        color = self._hex_to_rgb(self.tile_color)
        tm.set_tile(tx, ty, texture=self.tile_texture, color=color)

    def _erase_tile(self, wx, wy):
        tm = self._get_tilemap()
        g  = self.grid_size
        tx = int(wx // g); ty = int(wy // g)
        tm.remove_tile(tx, ty)

    def _place_entity(self, wx, wy):
        e = Entity('Entity')
        sr = SpriteRenderer(color=(200,100,200), width=32, height=32)
        e.add(sr)
        e.transform.position = Vec2(wx, wy)
        self.scene.add_entity(e)
        self.scene._flush_pending()
        self.app.refresh_entity_list()

    def _place_light(self, wx, wy):
        e = Entity('Light')
        lt = Light()
        e.add(lt)
        e.transform.position = Vec2(wx, wy)
        self.scene.add_entity(e)
        self.scene._flush_pending()
        self.app.refresh_entity_list()

    def _place_particle(self, wx, wy):
        e = Entity('Particles')
        pe = ParticleEmitter()
        e.add(pe)
        e.transform.position = Vec2(wx, wy)
        self.scene.add_entity(e)
        self.scene._flush_pending()
        self.app.refresh_entity_list()

    # ── Rendering ──
    def _draw_loop(self):
        self.redraw()
        self.after(33, self._draw_loop)  # ~30fps for editor

    def redraw(self):
        if not self.winfo_exists(): return
        c = self.canvas; c.delete('all')
        cw = c.winfo_width(); ch = c.winfo_height()
        if cw < 2 or ch < 2: return

        # Grid
        g  = self.grid_size * self.zoom
        ox = (-self.cam_x * self.zoom) % g
        oy = (-self.cam_y * self.zoom) % g
        grid_col = '#1a1a2e'
        for x in range(int(-g), int(cw+g), max(1,int(g))):
            xp = x + ox
            c.create_line(xp,0,xp,ch,fill=grid_col,width=1)
        for y in range(int(-g), int(ch+g), max(1,int(g))):
            yp = y + oy
            c.create_line(0,yp,cw,yp,fill=grid_col,width=1)

        # Axes
        ax, ay = self.world_to_canvas(0, 0)
        c.create_line(ax,0,ax,ch,fill='#2a2a5a',width=1,dash=(4,4))
        c.create_line(0,ay,cw,ay,fill='#2a2a5a',width=1,dash=(4,4))

        if not self.scene: return

        # Tilemap
        for ent in self.scene.entities:
            tm = ent.get(TilemapRenderer)
            if not tm: continue
            tr = ent.get(Transform)
            ox2 = tr.position.x if tr else 0
            oy2 = tr.position.y if tr else 0
            for (tx,ty), tile in tm.tiles.items():
                wx = ox2 + tx*tm.tile_width; wy = oy2 + ty*tm.tile_height
                sx,sy = self.world_to_canvas(wx, wy)
                sw2 = tm.tile_width*self.zoom; sh2 = tm.tile_height*self.zoom
                if sx+sw2 < 0 or sx > cw or sy+sh2 < 0 or sy > ch: continue
                col = self._rgb_to_hex(tile.get('color',(80,80,150)))
                c.create_rectangle(sx,sy,sx+sw2,sy+sh2,fill=col,outline='#2a2a4a')

        # Entities
        for ent in self.scene.entities:
            tr = ent.get(Transform); sr = ent.get(SpriteRenderer)
            lt = ent.get(Light); pe = ent.get(ParticleEmitter)
            if not tr: continue
            sx,sy = self.world_to_canvas(tr.position.x, tr.position.y)
            if sx < -100 or sx > cw+100 or sy < -100 or sy > ch+100: continue

            if lt:  # Light
                r = int(lt.radius * self.zoom * 0.2)
                col = self._rgb_to_hex(lt.color)
                c.create_oval(sx-r,sy-r,sx+r,sy+r,fill='',outline=col,width=1,dash=(4,2))
                c.create_oval(sx-4,sy-4,sx+4,sy+4,fill='#ffee88',outline='')

            elif pe:  # Particle emitter
                c.create_text(sx,sy,text='✨',fill=ACCENT2,font=('Arial',16))

            elif sr:  # Sprite
                ew = sr.width*self.zoom/2; eh = sr.height*self.zoom/2
                col = self._rgb_to_hex(sr.color)
                is_sel = ent is self._sel_entity
                c.create_rectangle(sx-ew,sy-eh,sx+ew,sy+eh,
                                   fill=col+'88' if not is_sel else col,
                                   outline=ACCENT if is_sel else '#555588',
                                   width=2 if is_sel else 1)
                # Collider outline
                col2 = ent.get(Collider)
                if col2:
                    if col2.kind == 'circle':
                        r = col2.radius*self.zoom
                        c.create_oval(sx-r,sy-r,sx+r,sy+r,fill='',outline='#00ff00',width=1)
                    else:
                        cw2=col2.width*self.zoom/2; ch2=col2.height*self.zoom/2
                        c.create_rectangle(sx-cw2,sy-ch2,sx+cw2,sy+ch2,fill='',outline='#00ff00',width=1)
                # Name
                c.create_text(sx,sy-eh-10,text=ent.name,fill=TEXT2,font=('Consolas',9),anchor='s')
            else:
                # Generic entity (camera etc)
                cam2 = ent.get(Camera)
                icon = '📷' if cam2 else '◆'
                c.create_text(sx,sy,text=icon,fill=TEXT,font=('Arial',16))

        # Hover tile highlight
        if self.tool in ('draw','erase') and self._hover_tx >= 0:
            g2 = self.grid_size
            hx,hy = self.world_to_canvas(self._hover_tx*g2, self._hover_ty*g2)
            hw = g2*self.zoom
            col = '#55ee5540' if self.tool=='draw' else '#ee555540'
            c.create_rectangle(hx,hy,hx+hw,hy+hw,fill=col,outline=ACCENT3 if self.tool=='draw' else ACCENT,width=1)

    def _hex_to_rgb(self, h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2],16) for i in (0,2,4))

    def _rgb_to_hex(self, rgb):
        if not rgb or len(rgb)<3: return '#444466'
        return '#{:02x}{:02x}{:02x}'.format(int(rgb[0]),int(rgb[1]),int(rgb[2]))

# ──────────────────────────────────────
#  INSPECTOR PANEL
# ──────────────────────────────────────
class Inspector(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=DARK2)
        self.app = app
        self._entity: Entity = None
        self._widgets = []
        self._vars = {}

        # Header
        hf = tk.Frame(self, bg=PANEL2, pady=4)
        hf.pack(fill='x')
        tk.Label(hf, text='🔍 Inspector', bg=PANEL2, fg=TEXT,
                 font=('Consolas',12,'bold')).pack(side='left', padx=8)
        tk.Button(hf, text='+ Add Component', bg=ACCENT, fg='#000',
                  font=('Consolas',10,'bold'), relief='flat', padx=6,
                  command=self.add_component_dialog).pack(side='right', padx=4)

        # Scroll area
        sf = tk.Frame(self, bg=DARK2)
        sf.pack(fill='both', expand=True)
        self._scroll = tk.Canvas(sf, bg=DARK2, highlightthickness=0)
        sb = ttk.Scrollbar(sf, orient='vertical', command=self._scroll.yview)
        self._scroll.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self._scroll.pack(side='left', fill='both', expand=True)
        self._inner = tk.Frame(self._scroll, bg=DARK2)
        self._scroll_id = self._scroll.create_window((0,0), window=self._inner, anchor='nw')
        self._inner.bind('<Configure>', lambda e: (
            self._scroll.configure(scrollregion=self._scroll.bbox('all')),
            self._scroll.itemconfig(self._scroll_id, width=self._scroll.winfo_width())
        ))
        self._scroll.bind('<Configure>', lambda e:
            self._scroll.itemconfig(self._scroll_id, width=e.width))
        self._scroll.bind('<MouseWheel>', lambda e:
            self._scroll.yview_scroll(-1*(e.delta//120),'units'))

    def load_entity(self, e: Entity):
        self._entity = e
        self._rebuild()

    def refresh_position(self):
        if not self._entity: return
        tr = self._entity.get(Transform)
        if tr and 'tr_x' in self._vars:
            self._vars['tr_x'].set(f'{tr.position.x:.1f}')
            self._vars['tr_y'].set(f'{tr.position.y:.1f}')

    def _rebuild(self):
        for w in self._inner.winfo_children(): w.destroy()
        self._vars.clear()
        if not self._entity:
            tk.Label(self._inner, text='No entity selected', bg=DARK2, fg=TEXT2,
                     font=('Consolas',11)).pack(pady=20)
            return

        e = self._entity
        # Entity header
        self._section_header(f'🎮 {e.name}  [id:{e.id}]')
        nf = self._row_frame()
        tk.Label(nf, text='Name', bg=DARK2, fg=TEXT2, font=('Consolas',10), width=10).pack(side='left')
        nv = tk.StringVar(value=e.name)
        def set_name(*a): e.name = nv.get()
        tk.Entry(nf, textvariable=nv, bg=DARK3, fg=TEXT, relief='flat',
                 font=('Consolas',10)).pack(side='left', fill='x', expand=True)
        nv.trace_add('write', set_name)
        tf = self._row_frame()
        tk.Label(tf, text='Tag', bg=DARK2, fg=TEXT2, font=('Consolas',10), width=10).pack(side='left')
        tv = tk.StringVar(value=e.tag)
        def set_tag(*a): e.tag = tv.get()
        tk.Entry(tf, textvariable=tv, bg=DARK3, fg=TEXT, relief='flat',
                 font=('Consolas',10)).pack(side='left', fill='x', expand=True)
        tv.trace_add('write', set_tag)

        # Transform
        tr = e.get(Transform)
        if tr: self._show_transform(tr)
        # SpriteRenderer
        sr = e.get(SpriteRenderer)
        if sr: self._show_sprite_renderer(sr)
        # Rigidbody
        rb = e.get(Rigidbody)
        if rb: self._show_rigidbody(rb)
        # Collider
        col = e.get(Collider)
        if col: self._show_collider(col)
        # Animator
        anim = e.get(Animator)
        if anim: self._show_animator(anim)
        # Camera
        cam = e.get(Camera)
        if cam: self._show_camera(cam)
        # Light
        lt = e.get(Light)
        if lt: self._show_light(lt)
        # ParticleEmitter
        pe = e.get(ParticleEmitter)
        if pe: self._show_particles(pe)
        # AudioSource
        aus = e.get(AudioSource)
        if aus: self._show_audio(aus)
        # Script
        scr = e.get(Script)
        if scr: self._show_script(scr)
        # DialogSystem
        dlg = e.get(DialogSystem)
        if dlg: self._show_dialog(dlg)
        # BattleSystem
        bat = e.get(BattleSystem)
        if bat: self._show_battle(bat)

    def _section_header(self, title, removable_comp=None):
        f = tk.Frame(self._inner, bg=PANEL2)
        f.pack(fill='x', pady=(8,0))
        tk.Label(f, text=title, bg=PANEL2, fg=TEXT,
                 font=('Consolas',10,'bold')).pack(side='left', padx=8, pady=3)
        if removable_comp:
            tk.Button(f, text='✕', bg=PANEL2, fg=ACCENT, relief='flat',
                      command=lambda: (self._entity.remove(removable_comp),
                                      self._rebuild())).pack(side='right',padx=4)

    def _row_frame(self):
        f = tk.Frame(self._inner, bg=DARK2)
        f.pack(fill='x', padx=8, pady=1)
        return f

    def _field(self, parent, label, var, width=12):
        tk.Label(parent, text=label, bg=DARK2, fg=TEXT2,
                 font=('Consolas',9), width=width, anchor='w').pack(side='left')
        e = tk.Entry(parent, textvariable=var, bg=DARK3, fg=TEXT,
                     relief='flat', font=('Consolas',9), width=10)
        e.pack(side='left', padx=2)
        return e

    def _float_var(self, key, val, on_change):
        v = tk.StringVar(value=f'{val:.3f}')
        self._vars[key] = v
        def cb(*a):
            try: on_change(float(v.get()))
            except: pass
        v.trace_add('write', cb)
        return v

    def _show_transform(self, tr):
        self._section_header('📐 Transform', Transform)
        # Position
        pf = self._row_frame()
        tk.Label(pf,text='Position',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        xv = self._float_var('tr_x', tr.position.x, lambda v: setattr(tr.position,'x',v))
        yv = self._float_var('tr_y', tr.position.y, lambda v: setattr(tr.position,'y',v))
        for lbl,var in [('X',xv),('Y',yv)]:
            tk.Label(pf,text=lbl,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=2).pack(side='left')
            tk.Entry(pf,textvariable=var,bg=DARK3,fg=TEXT,relief='flat',
                     font=('Consolas',9),width=7).pack(side='left',padx=1)
        # Rotation
        rf = self._row_frame()
        tk.Label(rf,text='Rotation',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        rv = self._float_var('tr_rot', math.degrees(tr.rotation),
                             lambda v: setattr(tr,'rotation',math.radians(v)))
        tk.Entry(rf,textvariable=rv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=7).pack(side='left')
        tk.Label(rf,text='°',bg=DARK2,fg=TEXT2,font=('Consolas',9)).pack(side='left')
        # Scale
        sf2 = self._row_frame()
        tk.Label(sf2,text='Scale',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        sxv = self._float_var('tr_sx',tr.scale.x,lambda v: setattr(tr.scale,'x',v))
        syv = self._float_var('tr_sy',tr.scale.y,lambda v: setattr(tr.scale,'y',v))
        for lbl,var in [('X',sxv),('Y',syv)]:
            tk.Label(sf2,text=lbl,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=2).pack(side='left')
            tk.Entry(sf2,textvariable=var,bg=DARK3,fg=TEXT,relief='flat',
                     font=('Consolas',9),width=7).pack(side='left',padx=1)

    def _show_sprite_renderer(self, sr):
        self._section_header('🖼 SpriteRenderer', SpriteRenderer)
        f1 = self._row_frame()
        tk.Label(f1,text='Texture',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        tv = tk.StringVar(value=sr.texture_name)
        tv.trace_add('write', lambda *a: setattr(sr,'texture_name',tv.get()))
        tk.Entry(f1,textvariable=tv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=16).pack(side='left')
        tk.Button(f1,text='📁',bg=PANEL,fg=TEXT2,relief='flat',
                  command=lambda: (tv.set(filedialog.askopenfilename(
                      filetypes=[('Images','*.png *.jpg *.bmp *.gif'),('All','*.*')]) or tv.get()))
                  ).pack(side='left')
        f2 = self._row_frame()
        tk.Label(f2,text='Size',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        wv = self._float_var('sr_w',sr.width,lambda v: setattr(sr,'width',int(v)))
        hv = self._float_var('sr_h',sr.height,lambda v: setattr(sr,'height',int(v)))
        for lbl,var in [('W',wv),('H',hv)]:
            tk.Label(f2,text=lbl,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=2).pack(side='left')
            tk.Entry(f2,textvariable=var,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=6).pack(side='left',padx=1)
        f3 = self._row_frame()
        tk.Label(f3,text='Color',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        col_hex = '#{:02x}{:02x}{:02x}'.format(*sr.color[:3])
        col_btn = tk.Button(f3,text='  ',bg=col_hex,relief='flat',width=3,
                            command=lambda: self._pick_color_for(sr, 'color', col_btn))
        col_btn.pack(side='left',padx=4)
        lv = self._float_var('sr_layer',sr.layer,lambda v: setattr(sr,'layer',int(v)))
        tk.Label(f3,text='Layer',bg=DARK2,fg=TEXT2,font=('Consolas',9)).pack(side='left',padx=(12,2))
        tk.Entry(f3,textvariable=lv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=4).pack(side='left')
        av = self._float_var('sr_alpha',sr.alpha,lambda v: setattr(sr,'alpha',max(0,min(255,int(v)))))
        tk.Label(f3,text='Alpha',bg=DARK2,fg=TEXT2,font=('Consolas',9)).pack(side='left',padx=(8,2))
        tk.Entry(f3,textvariable=av,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=4).pack(side='left')
        f4 = self._row_frame()
        fxv = tk.BooleanVar(value=sr.flip_x)
        fyv = tk.BooleanVar(value=sr.flip_y)
        fxv.trace_add('write', lambda *a: setattr(sr,'flip_x',fxv.get()))
        fyv.trace_add('write', lambda *a: setattr(sr,'flip_y',fyv.get()))
        tk.Checkbutton(f4,text='Flip X',variable=fxv,bg=DARK2,fg=TEXT2,
                       selectcolor=DARK3,activebackground=DARK2).pack(side='left',padx=4)
        tk.Checkbutton(f4,text='Flip Y',variable=fyv,bg=DARK2,fg=TEXT2,
                       selectcolor=DARK3,activebackground=DARK2).pack(side='left',padx=4)

    def _pick_color_for(self, obj, attr, btn):
        initial = getattr(obj, attr, (128,128,128))
        if isinstance(initial, (list,tuple)) and len(initial)>=3:
            hex_init = '#{:02x}{:02x}{:02x}'.format(*initial[:3])
        else: hex_init = '#808080'
        result = colorchooser.askcolor(color=hex_init, title='Choose Color')
        if result and result[0]:
            rgb = tuple(int(x) for x in result[0])
            setattr(obj, attr, rgb)
            btn.config(bg='#{:02x}{:02x}{:02x}'.format(*rgb))

    def _show_rigidbody(self, rb):
        self._section_header('⚙ Rigidbody', Rigidbody)
        fields = [('Mass','rb_mass',rb.mass,lambda v:setattr(rb,'mass',v)),
                  ('Gravity Scale','rb_gs',rb.gravity_scale,lambda v:setattr(rb,'gravity_scale',v)),
                  ('Drag','rb_drag',rb.drag,lambda v:setattr(rb,'drag',v)),
                  ('Bounce','rb_bounce',rb.bounce,lambda v:setattr(rb,'bounce',v)),
                  ('Friction','rb_fric',rb.friction,lambda v:setattr(rb,'friction',v))]
        for label,key,val,fn in fields:
            f = self._row_frame()
            tk.Label(f,text=label,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=14).pack(side='left')
            v = self._float_var(key,val,fn)
            tk.Entry(f,textvariable=v,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=8).pack(side='left')
        bools = [('Use Gravity','rb_grav',rb.use_gravity,lambda v:setattr(rb,'use_gravity',v)),
                 ('Kinematic','rb_kin',rb.is_kinematic,lambda v:setattr(rb,'is_kinematic',v)),
                 ('Static','rb_stat',rb.is_static,lambda v:setattr(rb,'is_static',v)),
                 ('Freeze X','rb_fx',rb.freeze_x,lambda v:setattr(rb,'freeze_x',v)),
                 ('Freeze Y','rb_fy',rb.freeze_y,lambda v:setattr(rb,'freeze_y',v))]
        f = self._row_frame()
        for label,key,val,fn in bools:
            bv = tk.BooleanVar(value=val)
            bv.trace_add('write',lambda *a,fn=fn,bv=bv: fn(bv.get()))
            tk.Checkbutton(f,text=label,variable=bv,bg=DARK2,fg=TEXT2,
                           selectcolor=DARK3,activebackground=DARK2,font=('Consolas',9)).pack(side='left',padx=3)

    def _show_collider(self, col):
        self._section_header('🔲 Collider', Collider)
        f1 = self._row_frame()
        tk.Label(f1,text='Kind',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        kv = tk.StringVar(value=col.kind)
        ttk.Combobox(f1,textvariable=kv,values=['box','circle','trigger'],
                     state='readonly',width=10,font=('Consolas',9)).pack(side='left')
        kv.trace_add('write',lambda *a: setattr(col,'kind',kv.get()))
        f2 = self._row_frame()
        wv = self._float_var('col_w',col.width,lambda v:setattr(col,'width',v))
        hv = self._float_var('col_h',col.height,lambda v:setattr(col,'height',v))
        rv = self._float_var('col_r',col.radius,lambda v:setattr(col,'radius',v))
        for lbl,var in [('W',wv),('H',hv),('R',rv)]:
            tk.Label(f2,text=lbl,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=2).pack(side='left')
            tk.Entry(f2,textvariable=var,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=6).pack(side='left',padx=1)
        f3 = self._row_frame()
        lv = self._float_var('col_layer',col.layer,lambda v:setattr(col,'layer',int(v)))
        tk.Label(f3,text='Layer',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        tk.Entry(f3,textvariable=lv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=4).pack(side='left')

    def _show_animator(self, anim):
        self._section_header('🎞 Animator', Animator)
        # List animations
        for aname, a in anim.animations.items():
            af = self._row_frame()
            tk.Label(af,text=aname,bg=DARK2,fg=ACCENT2,font=('Consolas',9),width=14).pack(side='left')
            tk.Label(af,text=f'{len(a.frames)} frames @ {a.fps}fps',bg=DARK2,fg=TEXT2,font=('Consolas',9)).pack(side='left')
            tk.Button(af,text='▶',bg=PANEL,fg=ACCENT3,relief='flat',padx=2,
                      command=lambda n=aname: anim.play(n,force_restart=True)).pack(side='right',padx=2)
        # Add animation
        tf = self._row_frame()
        tk.Button(tf,text='+ New Animation',bg=PANEL,fg=TEXT2,relief='flat',
                  command=lambda: self._new_animation_dialog(anim)).pack(side='left')

    def _new_animation_dialog(self, anim):
        d = tk.Toplevel(self)
        d.title('New Animation'); d.configure(bg=DARK2)
        d.grab_set()
        tk.Label(d,text='Name:',bg=DARK2,fg=TEXT).pack(padx=12,pady=(12,0),anchor='w')
        nv = tk.StringVar(value='idle')
        tk.Entry(d,textvariable=nv,bg=DARK3,fg=TEXT,relief='flat').pack(padx=12,fill='x')
        tk.Label(d,text='Frames (texture names, comma separated):',bg=DARK2,fg=TEXT).pack(padx=12,pady=(8,0),anchor='w')
        fv = tk.StringVar(value='frame1,frame2,frame3')
        tk.Entry(d,textvariable=fv,bg=DARK3,fg=TEXT,relief='flat').pack(padx=12,fill='x')
        tk.Label(d,text='FPS:',bg=DARK2,fg=TEXT).pack(padx=12,pady=(8,0),anchor='w')
        fpv = tk.StringVar(value='12')
        tk.Entry(d,textvariable=fpv,bg=DARK3,fg=TEXT,relief='flat').pack(padx=12,fill='x')
        lv = tk.BooleanVar(value=True)
        tk.Checkbutton(d,text='Loop',variable=lv,bg=DARK2,fg=TEXT,selectcolor=DARK3).pack(padx=12,anchor='w')
        def confirm():
            frames = [f.strip() for f in fv.get().split(',') if f.strip()]
            fps = float(fpv.get() or '12')
            anim.add_animation(nv.get(), Animation(frames, fps, lv.get()))
            self._rebuild(); d.destroy()
        tk.Button(d,text='Create',bg=ACCENT,fg='#000',relief='flat',command=confirm).pack(padx=12,pady=12)

    def _show_camera(self, cam):
        self._section_header('📷 Camera', Camera)
        f1 = self._row_frame()
        zv = self._float_var('cam_zoom',cam.zoom,lambda v:setattr(cam,'zoom',max(0.1,v)))
        tk.Label(f1,text='Zoom',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=14).pack(side='left')
        tk.Entry(f1,textvariable=zv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=6).pack(side='left')
        f2 = self._row_frame()
        fsv = self._float_var('cam_fs',cam.follow_speed,lambda v:setattr(cam,'follow_speed',v))
        tk.Label(f2,text='Follow Speed',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=14).pack(side='left')
        tk.Entry(f2,textvariable=fsv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=6).pack(side='left')
        f3 = self._row_frame()
        tk.Label(f3,text='BG Color',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=14).pack(side='left')
        bg_btn = tk.Button(f3,text='  ',bg='#{:02x}{:02x}{:02x}'.format(*cam.bg_color[:3]),
                           relief='flat',width=3,
                           command=lambda: self._pick_color_for(cam,'bg_color',bg_btn))
        bg_btn.pack(side='left')

    def _show_light(self, lt):
        self._section_header('💡 Light', Light)
        f1 = self._row_frame()
        rv = self._float_var('lt_r',lt.radius,lambda v:setattr(lt,'radius',v))
        iv = self._float_var('lt_i',lt.intensity,lambda v:setattr(lt,'intensity',max(0,v)))
        for lbl,var in [('Radius',rv),('Intensity',iv)]:
            tk.Label(f1,text=lbl,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
            tk.Entry(f1,textvariable=var,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=6).pack(side='left',padx=2)
        f2 = self._row_frame()
        tk.Label(f2,text='Color',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        col_btn = tk.Button(f2,text='  ',bg='#{:02x}{:02x}{:02x}'.format(*lt.color[:3]),
                            relief='flat',width=3,
                            command=lambda: self._pick_color_for(lt,'color',col_btn))
        col_btn.pack(side='left')
        kv = tk.StringVar(value=lt.kind)
        ttk.Combobox(f2,textvariable=kv,values=['point','directional','ambient'],
                     state='readonly',width=12,font=('Consolas',9)).pack(side='left',padx=8)
        kv.trace_add('write',lambda *a: setattr(lt,'kind',kv.get()))

    def _show_particles(self, pe):
        self._section_header('✨ Particle Emitter', ParticleEmitter)
        fields = [('Rate',pe.rate,lambda v:setattr(pe,'rate',v)),
                  ('Lifetime',pe.lifetime,lambda v:setattr(pe,'lifetime',v)),
                  ('Speed Min',pe.speed.x,lambda v:setattr(pe.speed,'x',v)),
                  ('Speed Max',pe.speed.y,lambda v:setattr(pe.speed,'y',v)),
                  ('Size Start',pe.size_start,lambda v:setattr(pe,'size_start',v)),
                  ('Size End',pe.size_end,lambda v:setattr(pe,'size_end',v))]
        for i,(lbl,val,fn) in enumerate(fields):
            f = self._row_frame()
            tk.Label(f,text=lbl,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=12).pack(side='left')
            v = self._float_var(f'pe_{i}',val,fn)
            tk.Entry(f,textvariable=v,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=8).pack(side='left')
        f2 = self._row_frame()
        tk.Button(f2,text='💥 Burst!',bg=ACCENT,fg='#000',relief='flat',
                  command=lambda: pe.emit_burst()).pack(side='left',padx=4)
        av = tk.BooleanVar(value=pe.active)
        av.trace_add('write',lambda *a:setattr(pe,'active',av.get()))
        tk.Checkbutton(f2,text='Active',variable=av,bg=DARK2,fg=TEXT2,
                       selectcolor=DARK3,activebackground=DARK2).pack(side='left',padx=8)

    def _show_audio(self, aus):
        self._section_header('🔊 AudioSource', AudioSource)
        f1 = self._row_frame()
        tk.Label(f1,text='Clip',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        cv = tk.StringVar(value=aus.clip)
        cv.trace_add('write',lambda *a:setattr(aus,'clip',cv.get()))
        tk.Entry(f1,textvariable=cv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=16).pack(side='left')
        tk.Button(f1,text='📁',bg=PANEL,fg=TEXT2,relief='flat',
                  command=lambda: (cv.set(filedialog.askopenfilename(
                      filetypes=[('Audio','*.wav *.ogg *.mp3'),('All','*.*')]) or cv.get()))
                  ).pack(side='left')
        f2 = self._row_frame()
        vv = self._float_var('au_vol',aus.volume,lambda v:setattr(aus,'volume',max(0,min(1,v))))
        pv = self._float_var('au_pit',aus.pitch,lambda v:setattr(aus,'pitch',max(0.1,v)))
        for lbl,var in [('Volume',vv),('Pitch',pv)]:
            tk.Label(f2,text=lbl,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=8).pack(side='left')
            tk.Entry(f2,textvariable=var,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=5).pack(side='left',padx=2)
        f3 = self._row_frame()
        lv = tk.BooleanVar(value=aus.loop)
        lv.trace_add('write',lambda *a:setattr(aus,'loop',lv.get()))
        tk.Checkbutton(f3,text='Loop',variable=lv,bg=DARK2,fg=TEXT2,
                       selectcolor=DARK3,activebackground=DARK2).pack(side='left')

    def _show_script(self, scr):
        self._section_header('📜 Script', Script)
        f1 = self._row_frame()
        tk.Label(f1,text='Script',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        sv = tk.StringVar(value=scr.script_path)
        sv.trace_add('write',lambda *a:setattr(scr,'script_path',sv.get()))
        tk.Entry(f1,textvariable=sv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=16).pack(side='left')
        tk.Button(f1,text='📁',bg=PANEL,fg=TEXT2,relief='flat',
                  command=lambda: (sv.set(filedialog.askopenfilename(
                      filetypes=[('GDL','*.gdl'),('All','*.*')]) or sv.get()))
                  ).pack(side='left')
        tk.Button(f1,text='✏',bg=PANEL,fg=ACCENT2,relief='flat',
                  command=lambda: self.app.open_script(scr.script_path)).pack(side='left',padx=2)

    def _show_dialog(self, dlg):
        self._section_header('💬 Dialog System', DialogSystem)
        f1 = self._row_frame()
        tk.Label(f1,text='Speaker',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        sv = tk.StringVar(value=dlg.speaker)
        sv.trace_add('write',lambda *a:setattr(dlg,'speaker',sv.get()))
        tk.Entry(f1,textvariable=sv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=14).pack(side='left')
        f2 = self._row_frame()
        dv = self._float_var('dlg_cd',dlg.char_delay,lambda v:setattr(dlg,'char_delay',max(0.001,v)))
        tk.Label(f2,text='Char Delay',bg=DARK2,fg=TEXT2,font=('Consolas',9),width=10).pack(side='left')
        tk.Entry(f2,textvariable=dv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=6).pack(side='left')

    def _show_battle(self, bat):
        self._section_header('⚔ Battle System', BattleSystem)
        fields = [('Enemy Name',bat.enemy_name,'enemy_name',str),
                  ('Enemy HP',bat.enemy_hp,'enemy_hp',int),
                  ('Enemy Max HP',bat.enemy_max_hp,'enemy_max_hp',int),
                  ('Enemy ATK',bat.enemy_atk,'enemy_atk',int),
                  ('Enemy DEF',bat.enemy_def,'enemy_def',int),
                  ('Mercy Req.',bat.mercy_req,'mercy_req',int)]
        for lbl,val,attr,typ in fields:
            f = self._row_frame()
            tk.Label(f,text=lbl,bg=DARK2,fg=TEXT2,font=('Consolas',9),width=14).pack(side='left')
            v = tk.StringVar(value=str(val))
            def cb(*a,attr=attr,v=v,typ=typ):
                try: setattr(bat,attr,typ(v.get()))
                except: pass
            v.trace_add('write',cb)
            tk.Entry(f,textvariable=v,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9),width=10).pack(side='left')

    def add_component_dialog(self):
        if not self._entity: return
        d = tk.Toplevel(self); d.title('Add Component'); d.configure(bg=DARK2); d.grab_set()
        comps = ['SpriteRenderer','Rigidbody','Collider','Animator','Camera',
                 'Light','ParticleEmitter','AudioSource','Script',
                 'TilemapRenderer','DialogSystem','BattleSystem']
        tk.Label(d,text='Select component:',bg=DARK2,fg=TEXT,font=('Consolas',11)).pack(padx=16,pady=(12,4),anchor='w')
        lb = tk.Listbox(d,bg=DARK3,fg=TEXT,selectbackground=PANEL2,relief='flat',
                        font=('Consolas',11),height=15)
        for c in comps: lb.insert('end', c)
        lb.pack(padx=12,pady=4,fill='both',expand=True)
        _comp_map = {
            'SpriteRenderer':SpriteRenderer,'Rigidbody':Rigidbody,'Collider':Collider,
            'Animator':Animator,'Camera':Camera,'Light':Light,
            'ParticleEmitter':ParticleEmitter,'AudioSource':AudioSource,'Script':Script,
            'TilemapRenderer':TilemapRenderer,'DialogSystem':DialogSystem,'BattleSystem':BattleSystem
        }
        def add():
            sel = lb.curselection()
            if not sel: return
            name = lb.get(sel[0])
            cls  = _comp_map.get(name)
            if cls and not self._entity.has(cls):
                self._entity.add(cls())
                self._rebuild()
            d.destroy()
        tk.Button(d,text='Add',bg=ACCENT,fg='#000',relief='flat',command=add).pack(padx=12,pady=8)

# ──────────────────────────────────────
#  CODE EDITOR
# ──────────────────────────────────────
class CodeEditor(tk.Frame):
    KEYWORDS = {'scene','character','battle','on','if','else','elif','while','for',
                'in','return','break','continue','let','func','dialog_tree',
                'true','false','null','and','or','not','import','template','vec2'}
    BUILTINS = {'show_text','play_sound','play_music','load_scene','spawn','destroy',
                'find','key_pressed','key_held','mouse_pos','start_battle',
                'start_dialog','camera_shake','emit_particles','tween','wait',
                'print','log','abs','min','max','sqrt','sin','cos','rand',
                'rand_range','rand_int','lerp','clamp','set_gravity'}

    def __init__(self, parent, app):
        super().__init__(parent, bg=DARK2)
        self.app = app

        # Toolbar
        tb = tk.Frame(self, bg=DARK, pady=2)
        tb.pack(fill='x')
        btns = [('▶ Run',self.run_code,ACCENT3,'#000'),
                ('✓ Check',self.check_syntax,ACCENT2,'#000'),
                ('💾 Save',self.save_code,PANEL,TEXT),
                ('📂 Open',self.open_file,PANEL,TEXT),
                ('🔄 Generate',self.generate_from_scene,PANEL,TEXT)]
        for txt,cmd,bg,fg in btns:
            tk.Button(tb,text=txt,command=cmd,bg=bg,fg=fg,relief='flat',
                      padx=8,pady=2,font=('Consolas',10,'bold')).pack(side='left',padx=2,pady=2)
        self._file_label = tk.Label(tb,text='Untitled.gdl',bg=DARK,fg=TEXT2,font=('Consolas',10))
        self._file_label.pack(side='right',padx=8)

        # Editor area
        ef = tk.Frame(self, bg=DARK2)
        ef.pack(fill='both', expand=True)
        # Line numbers
        self._lineno = tk.Text(ef,width=4,bg='#090912',fg='#555577',state='disabled',
                               relief='flat',font=('Consolas',12),
                               padx=4,pady=8,cursor='arrow',
                               highlightthickness=0,takefocus=0)
        self._lineno.pack(side='left',fill='y')
        # Editor
        self._text = tk.Text(ef,bg='#050510',fg='#d4d4d4',insertbackground=TEXT,
                             relief='flat',font=('Consolas',12),
                             padx=8,pady=8,undo=True,wrap='none',
                             selectbackground=PANEL2,selectforeground=TEXT,
                             highlightthickness=0,tabs=('28p',))
        sb_v = ttk.Scrollbar(ef, orient='vertical', command=self._sync_scroll)
        sb_h = ttk.Scrollbar(self, orient='horizontal', command=self._text.xview)
        self._text.configure(yscrollcommand=lambda *a:(sb_v.set(*a),self._update_lineno()),
                             xscrollcommand=sb_h.set)
        sb_v.pack(side='right', fill='y')
        self._text.pack(side='left', fill='both', expand=True)
        sb_h.pack(side='bottom', fill='x')

        # Output
        self._out = tk.Text(self,height=6,bg='#050508',fg='#aaffaa',state='disabled',
                            relief='flat',font=('Consolas',10),padx=8,pady=4,
                            highlightthickness=0)
        self._out.pack(fill='x', side='bottom')
        self._out_label = tk.Label(self,text='Console',bg=DARK,fg=TEXT2,font=('Consolas',9),anchor='w')
        self._out_label.pack(fill='x',side='bottom')

        # Syntax highlight tags
        self._text.tag_configure('keyword', foreground='#ff79c6')
        self._text.tag_configure('builtin', foreground='#8be9fd')
        self._text.tag_configure('string',  foreground='#f1fa8c')
        self._text.tag_configure('comment', foreground='#6272a4',font=('Consolas',12,'italic'))
        self._text.tag_configure('number',  foreground='#bd93f9')
        self._text.tag_configure('brace',   foreground='#ffb86c')
        self._text.tag_configure('error_line', background='#3a0000')

        self._text.bind('<KeyRelease>', self._on_key)
        self._text.bind('<Tab>', self._on_tab)
        self._current_file = None

        # Default content
        self._text.insert('1.0', self._default_script())
        self._highlight_all()
        self._update_lineno()

    def _default_script(self):
        return '''-- GDL (Game Design Language) v1.0
-- Натисни ▶ Run щоб запустити гру!

scene Main {
    bg_color = #1a1a2e
    music    = "main_theme"
    gravity  = vec2(0, 980)

    on start {
        show_text("* Ласкаво просимо до GDL Studio!")
        camera_shake(5)
    }

    on update {
        if key_pressed("escape") {
            load_scene("Menu")
        }
    }
}

character Player {
    hp     = 20
    atk    = 10
    def    = 5
    speed  = 150
    sprite = "player"

    on update {
        let dx = 0
        let dy = 0
        if key_held("left")  { dx = -speed }
        if key_held("right") { dx =  speed  }
        if key_held("up")    { dy = -speed  }
        if key_held("down")  { dy =  speed  }
        -- move(dx, dy) буде підключено до компонента
    }

    on interact(target) {
        if target.tag == "npc" {
            start_dialog(["* Привіт!", "* Як справи?"], target.name)
        }
    }
}

character Toriel {
    type        = "boss"
    hp          = 440
    atk         = 10
    def         = 12
    speed       = 0
    dialog_name = "Торіель"
    sprite      = "toriel_idle"

    on interact {
        start_dialog([
            "* Моя дитино... Ти заблукала у цих руїнах.",
            "* Не хвилюйся. Я тут, щоб допомогти.",
            "* Моє ім\\'я — Торіель. Я доглядаю за Руїнами."
        ], "Торіель")
    }
}

battle SlimeKing {
    enemy_name = "Король Слизів"
    hp         = 80
    atk        = 8
    def        = 2
    mercy_req  = 3

    attacks = [
        bullet { pattern = "wave";  speed = 100; count = 4 },
        bullet { pattern = "cross"; speed = 150; count = 6 }
    ]

    on mercy { show_text("* Слиз відпустили!") }
    on defeat { show_text("* Слиз переможений!") }
}

dialog_tree TorielIntro {
    Торіель: "* Не бійся, маленька."
    Торіель: "* Я захищу тебе."
    Гравець: "Дякую...", "Хто ти?"
}

func lerp_color(a, b, t) {
    return a + (b - a) * t
}

template BasicPlatform {
    width  = 128
    height = 32
    color  = #4444aa
    solid  = true
}
'''

    def _on_key(self, e):
        self._highlight_all()
        self._update_lineno()

    def _on_tab(self, e):
        self._text.insert('insert', '  '); return 'break'

    def _sync_scroll(self, *args):
        self._text.yview(*args)
        self._update_lineno()

    def _update_lineno(self):
        self._lineno.configure(state='normal')
        self._lineno.delete('1.0','end')
        lines = int(self._text.index('end-1c').split('.')[0])
        self._lineno.insert('1.0', '\n'.join(str(i) for i in range(1,lines+1)))
        self._lineno.configure(state='disabled')
        self._lineno.yview_moveto(self._text.yview()[0])

    def _highlight_all(self):
        text = self._text
        for tag in ('keyword','builtin','string','comment','number','brace'):
            text.tag_remove(tag,'1.0','end')
        content = text.get('1.0','end')
        # Comments
        for m in re.finditer(r'--[^\n]*|//[^\n]*', content):
            s,e = self._offset(m.start()), self._offset(m.end())
            text.tag_add('comment', s, e)
        # Strings
        for m in re.finditer(r'"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'', content):
            s,e = self._offset(m.start()), self._offset(m.end())
            text.tag_add('string', s, e)
        # Keywords
        for kw in self.KEYWORDS:
            for m in re.finditer(r'\b'+kw+r'\b', content):
                s,e = self._offset(m.start()), self._offset(m.end())
                text.tag_add('keyword', s, e)
        # Builtins
        for b in self.BUILTINS:
            for m in re.finditer(r'\b'+b+r'\b', content):
                s,e = self._offset(m.start()), self._offset(m.end())
                text.tag_add('builtin', s, e)
        # Numbers
        for m in re.finditer(r'\b\d+\.?\d*\b', content):
            s,e = self._offset(m.start()), self._offset(m.end())
            text.tag_add('number', s, e)
        # Braces
        for m in re.finditer(r'[{}()\[\]]', content):
            s,e = self._offset(m.start()), self._offset(m.end())
            text.tag_add('brace', s, e)

    def _offset(self, pos):
        content = self._text.get('1.0','end')
        line = content[:pos].count('\n') + 1
        col  = pos - content[:pos].rfind('\n') - 1
        return f'{line}.{col}'

    def run_code(self):
        code = self._text.get('1.0','end')
        self.log('▶ Running GDL...', '#50fa7b')
        try:
            result = compile_gdl(code)
            self.log(f'  Scenes: {list(result["scenes"].keys())}', '#8be9fd')
            self.log(f'  Characters: {list(result["characters"].keys())}', '#8be9fd')
            self.log(f'  Battles: {list(result["battles"].keys())}', '#8be9fd')
            self.log('✓ Script OK — Launch preview with toolbar Run button', '#50fa7b')
        except Exception as ex:
            self.log(f'✗ Error: {ex}', '#ff5555')

    def check_syntax(self):
        code = self._text.get('1.0','end')
        try:
            tokens = Lexer(code).tokenize()
            Parser(tokens).parse()
            self.log('✓ Syntax OK', '#50fa7b')
        except SyntaxError as ex:
            self.log(f'✗ Syntax error: {ex}', '#ff5555')

    def save_code(self):
        path = self._current_file or filedialog.asksaveasfilename(
            defaultextension='.gdl',
            filetypes=[('GDL Script','*.gdl'),('All','*.*')])
        if path:
            with open(path,'w',encoding='utf-8') as f:
                f.write(self._text.get('1.0','end'))
            self._current_file = path
            self._file_label.config(text=os.path.basename(path))
            self.log(f'Saved: {path}', '#f1fa8c')

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[('GDL','*.gdl'),('All','*.*')])
        if path:
            with open(path,'r',encoding='utf-8') as f:
                self._text.delete('1.0','end')
                self._text.insert('1.0',f.read())
            self._current_file = path
            self._file_label.config(text=os.path.basename(path))
            self._highlight_all()

    def generate_from_scene(self):
        scene = self.app.current_scene
        if not scene: return
        code = f'-- Auto-generated from scene "{scene.name}"\n\nscene {scene.name} {{\n'
        for e in scene.entities:
            code += f'    -- entity: {e.name}\n'
            tr = e.get(Transform)
            if tr: code += f'    place "{e.name}" at vec2({tr.position.x:.0f}, {tr.position.y:.0f})\n'
        code += '}\n'
        self._text.delete('1.0','end')
        self._text.insert('1.0',code)
        self._highlight_all()

    def log(self, msg, color='#aaffaa'):
        self._out.configure(state='normal')
        self._out.insert('end', msg+'\n', color)
        self._out.tag_configure(color, foreground=color)
        self._out.see('end')
        self._out.configure(state='disabled')

    def set_content(self, text): self._text.delete('1.0','end'); self._text.insert('1.0',text); self._highlight_all()
    def get_content(self): return self._text.get('1.0','end')

# ──────────────────────────────────────
#  MAIN APPLICATION
# ──────────────────────────────────────
class GDLStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('GDL Studio  —  Game Design Language')
        self.geometry('1400x860')
        self.configure(bg=DARK2)
        apply_theme(self)

        # Project state
        self._project_path: str = None
        self.current_scene: Scene = Scene('Main')
        self._scenes: dict = {'Main': self.current_scene}

        # Setup UI
        self._build_menu()
        self._build_toolbar()
        self._build_main()
        self._build_statusbar()

        # Setup default scene
        self._setup_default_scene()
        self.refresh_entity_list()
        self.scene_canvas.load_scene(self.current_scene)

        self.protocol('WM_DELETE_WINDOW', self._on_close)

    def _build_menu(self):
        mb = tk.Menu(self, bg=DARK2, fg=TEXT, activebackground=PANEL2,
                     activeforeground=TEXT, borderwidth=0, relief='flat')
        # File
        fm = tk.Menu(mb, tearoff=0, bg=DARK2, fg=TEXT,
                     activebackground=PANEL2, activeforeground=TEXT)
        fm.add_command(label='New Project',         command=self.new_project,    accelerator='Ctrl+N')
        fm.add_command(label='Open Project...',     command=self.open_project,   accelerator='Ctrl+O')
        fm.add_command(label='Save Project',        command=self.save_project,   accelerator='Ctrl+S')
        fm.add_command(label='Save Project As...', command=self.save_project_as)
        fm.add_separator()
        fm.add_command(label='Import Assets...',    command=self.import_assets)
        fm.add_separator()
        fm.add_command(label='Exit',                command=self._on_close)
        mb.add_cascade(label='File',   menu=fm)
        # Scene
        sm = tk.Menu(mb, tearoff=0, bg=DARK2, fg=TEXT,
                     activebackground=PANEL2, activeforeground=TEXT)
        sm.add_command(label='New Scene',           command=self.new_scene)
        sm.add_command(label='Duplicate Scene',     command=self.duplicate_scene)
        sm.add_separator()
        sm.add_command(label='Scene Settings...',   command=self.scene_settings)
        mb.add_cascade(label='Scene',  menu=sm)
        # Entity
        em = tk.Menu(mb, tearoff=0, bg=DARK2, fg=TEXT,
                     activebackground=PANEL2, activeforeground=TEXT)
        em.add_command(label='Empty Entity',    command=lambda: self._add_entity('Entity'))
        em.add_command(label='Player',          command=lambda: self._add_player())
        em.add_command(label='NPC',             command=lambda: self._add_npc())
        em.add_command(label='Tilemap',         command=lambda: self._add_tilemap())
        em.add_command(label='Camera',          command=lambda: self._add_camera())
        em.add_command(label='Light',           command=lambda: self._add_light())
        em.add_command(label='Particle System', command=lambda: self._add_particles())
        em.add_command(label='Battle Entity',   command=lambda: self._add_battle())
        mb.add_cascade(label='Entity', menu=em)
        # Build
        bm = tk.Menu(mb, tearoff=0, bg=DARK2, fg=TEXT,
                     activebackground=PANEL2, activeforeground=TEXT)
        bm.add_command(label='▶ Run Game',         command=self.run_game,    accelerator='F5')
        bm.add_separator()
        bm.add_command(label='Build Python Script', command=self.build_python)
        bm.add_command(label='Build EXE (PyInstaller)', command=self.build_exe_guide)
        mb.add_cascade(label='Build',  menu=bm)
        # View
        vm = tk.Menu(mb, tearoff=0, bg=DARK2, fg=TEXT,
                     activebackground=PANEL2, activeforeground=TEXT)
        vm.add_command(label='Toggle Debug View', command=self.toggle_debug)
        vm.add_command(label='Toggle Lighting',   command=self.toggle_lighting)
        mb.add_cascade(label='View',   menu=vm)
        self.config(menu=mb)
        # Keyboard shortcuts
        self.bind('<Control-n>', lambda e: self.new_project())
        self.bind('<Control-o>', lambda e: self.open_project())
        self.bind('<Control-s>', lambda e: self.save_project())
        self.bind('<F5>',        lambda e: self.run_game())

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=DARK, pady=4)
        tb.pack(fill='x', side='top')
        btns = [
            ('📂 Open',  self.open_project,  PANEL, TEXT2),
            ('💾 Save',  self.save_project,   PANEL, TEXT2),
            ('▶ Run',    self.run_game,        ACCENT3, '#000'),
            ('⚙ EXE',   self.build_exe_guide, ACCENT2, '#000'),
        ]
        for lbl,cmd,bg,fg in btns:
            tk.Button(tb,text=lbl,command=cmd,bg=bg,fg=fg,relief='flat',
                      padx=10,pady=3,font=('Consolas',11,'bold')).pack(side='left',padx=3)

        tk.Label(tb,text='Scene:',bg=DARK,fg=TEXT2,font=('Consolas',10)).pack(side='left',padx=(16,4))
        self._scene_var = tk.StringVar(value='Main')
        self._scene_combo = ttk.Combobox(tb,textvariable=self._scene_var,
                                          values=['Main'],state='readonly',width=14,
                                          font=('Consolas',10))
        self._scene_combo.pack(side='left')
        self._scene_combo.bind('<<ComboboxSelected>>',lambda e: self.switch_scene(self._scene_var.get()))
        tk.Button(tb,text='+',bg=PANEL,fg=ACCENT3,relief='flat',padx=6,
                  command=self.new_scene).pack(side='left',padx=2)

        self._status_var = tk.StringVar(value='GDL Studio ready.')
        tk.Label(tb,textvariable=self._status_var,bg=DARK,fg=TEXT2,
                 font=('Consolas',10)).pack(side='right',padx=12)

    def _build_main(self):
        pw = ttk.PanedWindow(self, orient='horizontal')
        pw.pack(fill='both', expand=True)

        # Left: hierarchy
        left = tk.Frame(pw, bg=DARK2, width=200)
        pw.add(left, weight=0)
        self._build_hierarchy(left)

        # Center: notebook (scene editor + code)
        center = tk.Frame(pw, bg=DARK2)
        pw.add(center, weight=3)
        nb = ttk.Notebook(center)
        nb.pack(fill='both', expand=True)
        self.notebook = nb

        # Scene tab
        scene_frame = tk.Frame(nb, bg=DARK2)
        nb.add(scene_frame, text='🗺 Scene')
        self.scene_canvas = SceneCanvas(scene_frame, self)
        self.scene_canvas.pack(fill='both', expand=True)

        # Code tab
        code_frame = tk.Frame(nb, bg=DARK2)
        nb.add(code_frame, text='📝 GDL Code')
        self.code_editor = CodeEditor(code_frame, self)
        self.code_editor.pack(fill='both', expand=True)

        # Animation tab
        anim_frame = tk.Frame(nb, bg=DARK2)
        nb.add(anim_frame, text='🎞 Animations')
        self._build_anim_panel(anim_frame)

        # Right: inspector
        right = tk.Frame(pw, bg=DARK2, width=260)
        pw.add(right, weight=0)
        self.inspector = Inspector(right, self)
        self.inspector.pack(fill='both', expand=True)

    def _build_hierarchy(self, parent):
        hdr = tk.Frame(parent, bg=PANEL2, pady=4)
        hdr.pack(fill='x')
        tk.Label(hdr,text='🌲 Hierarchy',bg=PANEL2,fg=TEXT,font=('Consolas',11,'bold')).pack(side='left',padx=8)
        tk.Button(hdr,text='+',bg=PANEL2,fg=ACCENT3,relief='flat',padx=4,
                  command=lambda: self._add_entity('Entity')).pack(side='right',padx=4)

        sf = tk.Frame(parent,bg=DARK2)
        sf.pack(fill='both',expand=True)
        self._tree = ttk.Treeview(sf, selectmode='browse', show='tree')
        sb = ttk.Scrollbar(sf,orient='vertical',command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side='right',fill='y')
        self._tree.pack(side='left',fill='both',expand=True)
        self._tree.bind('<<TreeviewSelect>>', self._on_tree_select)
        self._tree.bind('<Button-3>', self._on_tree_rmb)

        # Search
        sf2 = tk.Frame(parent,bg=DARK2)
        sf2.pack(fill='x',side='bottom',pady=2)
        tk.Label(sf2,text='🔍',bg=DARK2,fg=TEXT2).pack(side='left',padx=4)
        sv = tk.StringVar()
        sv.trace_add('write', lambda *a: self._filter_hierarchy(sv.get()))
        tk.Entry(sf2,textvariable=sv,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',9)).pack(side='left',fill='x',expand=True)

    def _build_anim_panel(self, parent):
        tk.Label(parent,text='Animation Preview',bg=DARK2,fg=TEXT2,
                 font=('Consolas',11)).pack(pady=12)
        self._anim_canvas = tk.Canvas(parent,bg='#050510',width=200,height=200,
                                      highlightthickness=0)
        self._anim_canvas.pack(pady=8)
        ctrl = tk.Frame(parent,bg=DARK2)
        ctrl.pack()
        tk.Button(ctrl,text='◀',bg=PANEL,fg=TEXT2,relief='flat',padx=8,
                  command=self._anim_prev).pack(side='left',padx=2)
        self._anim_frame_label = tk.Label(ctrl,text='Frame 0',bg=DARK2,fg=TEXT,font=('Consolas',10))
        self._anim_frame_label.pack(side='left',padx=8)
        tk.Button(ctrl,text='▶',bg=PANEL,fg=TEXT2,relief='flat',padx=8,
                  command=self._anim_next).pack(side='left',padx=2)
        tk.Button(ctrl,text='▶▶ Play',bg=ACCENT3,fg='#000',relief='flat',padx=8,
                  command=self._anim_play).pack(side='left',padx=8)
        self._anim_playing = False
        self._anim_frame   = 0
        self._anim_frames_list = []

    def _anim_prev(self):
        if self._anim_frames_list:
            self._anim_frame = (self._anim_frame-1) % len(self._anim_frames_list)
            self._anim_show()

    def _anim_next(self):
        if self._anim_frames_list:
            self._anim_frame = (self._anim_frame+1) % len(self._anim_frames_list)
            self._anim_show()

    def _anim_play(self):
        self._anim_playing = not self._anim_playing
        if self._anim_playing: self._anim_tick()

    def _anim_tick(self):
        if not self._anim_playing: return
        self._anim_next()
        self.after(83, self._anim_tick)  # ~12fps

    def _anim_show(self):
        if not self._anim_frames_list: return
        name = self._anim_frames_list[self._anim_frame]
        self._anim_frame_label.config(text=f'Frame {self._anim_frame}: {name}')

    def _build_statusbar(self):
        sb = tk.Frame(self,bg=DARK,pady=2)
        sb.pack(fill='x',side='bottom')
        tk.Label(sb,text='GDL Studio v1.0  |  Entity-Component  |  Physics  |  Animations  |  GDL Language',
                 bg=DARK,fg=TEXT2,font=('Consolas',9)).pack(side='left',padx=8)

    # ── Hierarchy ──
    def refresh_entity_list(self):
        self._tree.delete(*self._tree.get_children())
        if not self.current_scene: return
        for e in self.current_scene.entities:
            icon = '📷' if e.has(Camera) else ('💡' if e.has(Light) else
                   ('🗺' if e.has(TilemapRenderer) else
                   ('✨' if e.has(ParticleEmitter) else '🎮')))
            self._tree.insert('','end',iid=str(e.id),
                              text=f' {icon} {e.name}',
                              tags=('active' if e.active else 'inactive',))
        self._tree.tag_configure('inactive',foreground='#555577')

    def _filter_hierarchy(self, query):
        q = query.lower()
        for iid in self._tree.get_children():
            text = self._tree.item(iid,'text').lower()
            self._tree.item(iid, open=q in text)

    def _on_tree_select(self, e):
        sel = self._tree.selection()
        if not sel: return
        eid = int(sel[0])
        entity = next((e for e in self.current_scene.entities if e.id==eid), None)
        if entity:
            self.inspector.load_entity(entity)
            self.scene_canvas._sel_entity = entity

    def _on_tree_rmb(self, e):
        iid = self._tree.identify_row(e.y)
        if not iid: return
        self._tree.selection_set(iid)
        eid = int(iid)
        entity = next((e for e in self.current_scene.entities if e.id==eid), None)
        m = tk.Menu(self,tearoff=0,bg=DARK2,fg=TEXT,
                    activebackground=PANEL2,activeforeground=TEXT)
        m.add_command(label='Rename', command=lambda: self._rename_entity(entity))
        m.add_command(label='Duplicate', command=lambda: self._duplicate_entity(entity))
        m.add_separator()
        m.add_command(label='Delete', command=lambda: self._delete_entity(entity))
        m.post(e.x_root, e.y_root)

    def _rename_entity(self, e):
        name = simpledialog.askstring('Rename',f'New name for "{e.name}":',
                                       initialvalue=e.name, parent=self)
        if name: e.name=name; self.refresh_entity_list()

    def _duplicate_entity(self, e):
        clone = copy.deepcopy(e)
        Entity._id_counter += 1
        clone.id = Entity._id_counter
        clone.name = e.name + '_copy'
        clone.transform.position = Vec2(e.transform.position.x+32, e.transform.position.y)
        self.current_scene.add_entity(clone)
        self.current_scene._flush_pending()
        self.refresh_entity_list()

    def _delete_entity(self, e):
        self.current_scene.remove_entity(e)
        self.current_scene._flush_pending()
        self.inspector.load_entity(None)
        self.refresh_entity_list()

    # ── Entity presets ──
    def _add_entity(self, name):
        e = Entity(name)
        e.add(SpriteRenderer(color=(150,150,200),width=32,height=32))
        self.current_scene.add_entity(e)
        self.current_scene._flush_pending()
        self.refresh_entity_list()
        return e

    def _add_player(self):
        e = Entity('Player')
        e.tag = 'player'
        e.add(SpriteRenderer(color=(80,200,80),width=24,height=32))
        e.add(Rigidbody())
        e.add(Collider('box',24,32))
        e.add(Animator())
        e.add(AudioSource())
        e.transform.position = Vec2(100,100)
        self.current_scene.add_entity(e)
        self.current_scene._flush_pending()
        self.refresh_entity_list()
        self.inspector.load_entity(e)

    def _add_npc(self):
        e = Entity('NPC')
        e.tag = 'npc'
        e.add(SpriteRenderer(color=(200,140,80),width=24,height=36))
        e.add(Collider('box',24,36,is_trigger=True) if False else Collider('box',24,36))
        e.add(DialogSystem())
        e.add(Animator())
        self.current_scene.add_entity(e)
        self.current_scene._flush_pending()
        self.refresh_entity_list()

    def _add_tilemap(self):
        e = Entity('Tilemap')
        tm = TilemapRenderer()
        e.add(tm)
        self.current_scene.add_entity(e)
        self.current_scene._flush_pending()
        self.refresh_entity_list()

    def _add_camera(self):
        e = Entity('MainCamera')
        cam = Camera()
        cam.bg_color = (20,20,30)
        e.add(cam)
        self.current_scene.add_entity(e)
        self.current_scene._flush_pending()
        self.refresh_entity_list()

    def _add_light(self):
        e = Entity('Light')
        e.add(Light())
        e.transform.position = Vec2(200,200)
        self.current_scene.add_entity(e)
        self.current_scene._flush_pending()
        self.refresh_entity_list()

    def _add_particles(self):
        e = Entity('ParticleSystem')
        e.add(ParticleEmitter())
        e.transform.position = Vec2(200,200)
        self.current_scene.add_entity(e)
        self.current_scene._flush_pending()
        self.refresh_entity_list()

    def _add_battle(self):
        e = Entity('BossEnemy')
        e.tag = 'enemy'
        e.add(SpriteRenderer(color=(220,80,80),width=48,height=64))
        e.add(BattleSystem())
        e.add(DialogSystem())
        e.transform.position = Vec2(300,200)
        self.current_scene.add_entity(e)
        self.current_scene._flush_pending()
        self.refresh_entity_list()

    def _setup_default_scene(self):
        # Camera
        cam_e = Entity('MainCamera')
        cam_e.add(Camera())
        self.current_scene.add_entity(cam_e)
        # Player
        player = Entity('Player')
        player.tag = 'player'
        player.add(SpriteRenderer(color=(80,200,100),width=24,height=32))
        player.add(Rigidbody())
        player.add(Collider('box',22,30))
        player.add(Animator())
        player.transform.position = Vec2(200,200)
        self.current_scene.add_entity(player)
        # Ground tilemap
        tm_e = Entity('Ground')
        tm = TilemapRenderer()
        for tx in range(20):
            tm.set_tile(tx, 10, color=(60,90,60))
            tm.set_tile(tx, 11, color=(40,60,40))
        tm_e.add(tm)
        self.current_scene.add_entity(tm_e)
        # NPC
        npc = Entity('Toriel')
        npc.tag = 'npc'
        npc.add(SpriteRenderer(color=(180,100,180),width=32,height=48))
        npc.add(DialogSystem())
        npc.transform.position = Vec2(400,240)
        dlg = npc.get(DialogSystem)
        dlg.speaker = 'Торіель'
        dlg.lines   = ['* Привіт!','* Як справи?']
        self.current_scene.add_entity(npc)
        self.current_scene._flush_pending()

    # ── Scene management ──
    def new_scene(self):
        name = simpledialog.askstring('New Scene','Scene name:',
                                       initialvalue='NewScene',parent=self)
        if not name: return
        self._scenes[name] = Scene(name)
        self.current_scene = self._scenes[name]
        self._scene_combo['values'] = list(self._scenes.keys())
        self._scene_var.set(name)
        self.scene_canvas.load_scene(self.current_scene)
        self.refresh_entity_list()

    def switch_scene(self, name):
        if name in self._scenes:
            self.current_scene = self._scenes[name]
            self.scene_canvas.load_scene(self.current_scene)
            self.refresh_entity_list()

    def duplicate_scene(self):
        sc = self.current_scene
        name = sc.name + '_copy'
        new_sc = copy.deepcopy(sc)
        new_sc.name = name
        self._scenes[name] = new_sc
        self._scene_combo['values'] = list(self._scenes.keys())
        self._scene_var.set(name)
        self.current_scene = new_sc
        self.scene_canvas.load_scene(new_sc)
        self.refresh_entity_list()

    def scene_settings(self):
        d = tk.Toplevel(self); d.title('Scene Settings'); d.configure(bg=DARK2); d.grab_set()
        sc = self.current_scene
        fields = [('Scene Name', sc.name, str),
                  ('Gravity X', sc.physics.gravity.x, float),
                  ('Gravity Y', sc.physics.gravity.y, float)]
        vars_ = []
        for lbl,val,typ in fields:
            f = tk.Frame(d,bg=DARK2); f.pack(fill='x',padx=12,pady=4)
            tk.Label(f,text=lbl,bg=DARK2,fg=TEXT,font=('Consolas',10),width=14).pack(side='left')
            v = tk.StringVar(value=str(val))
            tk.Entry(f,textvariable=v,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',10)).pack(side='left',fill='x',expand=True)
            vars_.append((v,typ,lbl))
        # BG Color
        f = tk.Frame(d,bg=DARK2); f.pack(fill='x',padx=12,pady=4)
        tk.Label(f,text='BG Color',bg=DARK2,fg=TEXT,font=('Consolas',10),width=14).pack(side='left')
        bg_hex = '#{:02x}{:02x}{:02x}'.format(*sc.bg_color)
        bg_v = tk.StringVar(value=bg_hex)
        tk.Entry(f,textvariable=bg_v,bg=DARK3,fg=TEXT,relief='flat',font=('Consolas',10),width=8).pack(side='left')
        def pick_bg():
            r = colorchooser.askcolor(color=bg_v.get(),title='BG Color')
            if r and r[1]: bg_v.set(r[1])
        tk.Button(f,text='Pick',bg=PANEL,fg=TEXT2,relief='flat',command=pick_bg).pack(side='left',padx=4)
        pev = tk.BooleanVar(value=sc.physics.enabled)
        tk.Checkbutton(d,text='Physics Enabled',variable=pev,bg=DARK2,fg=TEXT,
                       selectcolor=DARK3).pack(padx=12,anchor='w',pady=4)
        def apply():
            try:
                sc.name = vars_[0][0].get()
                sc.physics.gravity.x = float(vars_[1][0].get())
                sc.physics.gravity.y = float(vars_[2][0].get())
                h = bg_v.get().lstrip('#')
                sc.bg_color = tuple(int(h[i:i+2],16) for i in (0,2,4))
                sc.physics.enabled = pev.get()
            except Exception as ex: messagebox.showerror('Error',str(ex))
            d.destroy()
        tk.Button(d,text='Apply',bg=ACCENT,fg='#000',relief='flat',command=apply).pack(padx=12,pady=8)

    # ── Project ──
    def new_project(self):
        self._scenes = {'Main': Scene('Main')}
        self.current_scene = self._scenes['Main']
        self._setup_default_scene()
        self._scene_combo['values'] = ['Main']
        self._scene_var.set('Main')
        self.scene_canvas.load_scene(self.current_scene)
        self.refresh_entity_list()
        self._project_path = None
        self._status_var.set('New project created')

    def open_project(self):
        path = filedialog.askopenfilename(
            filetypes=[('GDL Project','*.gdlproj *.json'),('All','*.*')])
        if not path: return
        try:
            with open(path,'r',encoding='utf-8') as f:
                data = json.load(f)
            self._load_project_data(data)
            self._project_path = path
            self._status_var.set(f'Opened: {os.path.basename(path)}')
        except Exception as ex:
            messagebox.showerror('Error',f'Cannot open project:\n{ex}')

    def save_project(self):
        if self._project_path:
            self._do_save(self._project_path)
        else:
            self.save_project_as()

    def save_project_as(self):
        path = filedialog.asksaveasfilename(
            defaultextension='.gdlproj',
            filetypes=[('GDL Project','*.gdlproj'),('JSON','*.json'),('All','*.*')])
        if path:
            self._do_save(path)
            self._project_path = path

    def _do_save(self, path):
        data = {
            'version': '1.0',
            'scenes': {name: sc.to_dict() for name,sc in self._scenes.items()},
            'gdl_code': self.code_editor.get_content(),
            'active_scene': self.current_scene.name,
        }
        with open(path,'w',encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        self._status_var.set(f'Saved: {os.path.basename(path)}')

    def _load_project_data(self, data):
        self._scenes = {}
        for name, sc_data in data.get('scenes',{}).items():
            sc = Scene(name)
            sc.bg_color = tuple(sc_data.get('bg_color',[20,20,30]))
            phys = sc_data.get('physics',{})
            sc.physics.gravity = Vec2(phys.get('gravity_x',0), phys.get('gravity_y',980))
            sc.physics.enabled = phys.get('enabled', True)
            for ed in sc_data.get('entities',[]):
                e = Entity(ed.get('name','Entity'))
                e.tag    = ed.get('tag','')
                e.layer  = ed.get('layer',0)
                e.active = ed.get('active',True)
                comps = ed.get('components',{})
                if 'Transform' in comps:
                    t = comps['Transform']
                    e.transform.position = Vec2(t.get('x',0),t.get('y',0))
                    e.transform.rotation = t.get('rot',0)
                    e.transform.scale    = Vec2(t.get('sx',1),t.get('sy',1))
                if 'SpriteRenderer' in comps:
                    t = comps['SpriteRenderer']
                    sr = SpriteRenderer(t.get('texture',''),
                                        tuple(t.get('color',[150,150,200])),
                                        t.get('w',32),t.get('h',32))
                    sr.layer = t.get('layer',0)
                    e.add(sr)
                if 'Rigidbody' in comps:
                    t = comps['Rigidbody']; rb = Rigidbody()
                    rb.mass=t.get('mass',1); rb.gravity_scale=t.get('gravity_scale',1)
                    rb.drag=t.get('drag',0.02); rb.use_gravity=t.get('use_gravity',True)
                    rb.bounce=t.get('bounce',0); rb.friction=t.get('friction',0.8)
                    rb.is_kinematic=t.get('is_kinematic',False); rb.is_static=t.get('is_static',False)
                    e.add(rb)
                if 'Collider' in comps:
                    t = comps['Collider']
                    e.add(Collider(t.get('kind','box'),t.get('w',32),t.get('h',32),t.get('radius',16)))
                if 'Animator' in comps:
                    t = comps['Animator']; anim = Animator()
                    for aname,ad in t.get('animations',{}).items():
                        anim.add_animation(aname, Animation(ad['frames'],ad.get('fps',12),ad.get('loop',True)))
                    if t.get('current'): anim.play(t['current'])
                    e.add(anim)
                if 'Script' in comps:
                    e.add(Script(comps['Script'].get('path','')))
                sc.entities.append(e)
                e.scene = sc
            self._scenes[name] = sc
        active = data.get('active_scene','Main')
        self.current_scene = self._scenes.get(active, next(iter(self._scenes.values())))
        self._scene_combo['values'] = list(self._scenes.keys())
        self._scene_var.set(self.current_scene.name)
        self.scene_canvas.load_scene(self.current_scene)
        self.refresh_entity_list()
        if 'gdl_code' in data:
            self.code_editor.set_content(data['gdl_code'])

    def import_assets(self):
        paths = filedialog.askopenfilenames(
            title='Import Assets',
            filetypes=[('Images','*.png *.jpg *.bmp *.gif'),
                       ('Audio','*.wav *.ogg *.mp3'),
                       ('All','*.*')])
        if not paths: return
        assets_dir = 'assets'
        os.makedirs(assets_dir, exist_ok=True)
        for p in paths:
            import shutil
            dest = os.path.join(assets_dir, os.path.basename(p))
            shutil.copy2(p, dest)
        self._status_var.set(f'Imported {len(paths)} assets → assets/')
        messagebox.showinfo('Import Complete',
                            f'Imported {len(paths)} file(s) to ./assets/\n\nYou can now use their names in SpriteRenderer texture fields.')

    def open_script(self, path):
        if path and os.path.exists(path):
            with open(path,'r') as f:
                self.code_editor.set_content(f.read())
        self.notebook.select(1)

    # ── Run / Build ──
    def run_game(self):
        from engine.renderer import GameRuntime
        code = self.code_editor.get_content()
        # Parse GDL
        try:
            compile_gdl(code)
        except Exception as ex:
            messagebox.showerror('GDL Error', str(ex)); return

        sc = copy.deepcopy(self.current_scene)
        sc._flush_pending()
        self._status_var.set('Running game...')

        def run_in_thread():
            try:
                rt = GameRuntime(sc, title=f'GDL Game — {sc.name}')
                rt.run()
            except Exception as ex:
                print(f'[Runtime Error] {ex}')
        t = threading.Thread(target=run_in_thread, daemon=True)
        t.start()

    def build_python(self):
        path = filedialog.asksaveasfilename(
            defaultextension='.py',
            filetypes=[('Python','*.py'),('All','*.*')],
            initialfile='gdl_game')
        if not path: return
        sc   = self.current_scene
        code = self.code_editor.get_content()
        py_code = self._generate_python(sc, code)
        with open(path,'w',encoding='utf-8') as f: f.write(py_code)
        self._status_var.set(f'Python script: {os.path.basename(path)}')
        messagebox.showinfo('Build Complete',
            f'Python script saved to:\n{path}\n\n'
            f'Run: python {os.path.basename(path)}\n'
            f'EXE: pyinstaller --onefile --windowed {os.path.basename(path)}')

    def build_exe_guide(self):
        d = tk.Toplevel(self); d.title('Build EXE'); d.configure(bg=DARK2); d.grab_set()
        d.geometry('500x380')
        tk.Label(d,text='⚙ Build Executable',bg=DARK2,fg=ACCENT2,
                 font=('Consolas',14,'bold')).pack(pady=(16,8))
        steps = [
            '# 1. Встановити Python 3.10+\nhttps://python.org/downloads',
            '# 2. Встановити залежності\npip install pygame pyinstaller Pillow',
            '# 3. Зберегти проект → Build → Build Python Script',
            '# 4. Скомпілювати\npyinstaller --onefile --windowed gdl_game.py',
            '# 5. Знайти EXE в папці dist/',
        ]
        for s in steps:
            tk.Label(d,text=s,bg=DARK3,fg='#8be9fd',font=('Consolas',10),
                     justify='left',anchor='w',padx=12,pady=4).pack(fill='x',padx=16,pady=2)
        def do_build():
            d.destroy(); self.build_python()
        tk.Button(d,text='Generate Python Script Now',bg=ACCENT,fg='#000',
                  relief='flat',padx=16,pady=6,font=('Consolas',11,'bold'),
                  command=do_build).pack(pady=12)

    def _generate_python(self, scene: Scene, gdl_code: str) -> str:
        entities_json = json.dumps([e.to_dict() for e in scene.entities], indent=2, default=str)
        return f'''#!/usr/bin/env python3
"""
GDL Studio — Auto-generated Python game
Scene: {scene.name}
Generated by GDL Studio v1.0
"""
import pygame, sys, os, math, json

pygame.init()
if pygame.mixer:
    pygame.mixer.pre_init(44100,-16,2,512); pygame.mixer.init()

SCREEN_W, SCREEN_H = 800, 600
FPS = 60
BG_COLOR = {tuple(scene.bg_color)}

screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
pygame.display.set_caption("GDL Game — {scene.name}")
clock  = pygame.time.Clock()

# ── Entity data (from GDL Studio) ──
ENTITIES_DATA = {entities_json!r}

class Vec2:
    def __init__(self,x=0,y=0): self.x=float(x); self.y=float(y)
    def __add__(self,o): return Vec2(self.x+o.x,self.y+o.y)
    def __sub__(self,o): return Vec2(self.x-o.x,self.y-o.y)
    def __mul__(self,s): return Vec2(self.x*s,self.y*s)
    def length(self): return math.hypot(self.x,self.y)
    def normalized(self):
        l=self.length(); return Vec2(self.x/l,self.y/l) if l>0.001 else Vec2()

class Entity:
    def __init__(self,data):
        self.name   = data.get('name','Entity')
        self.tag    = data.get('tag','')
        self.active = data.get('active',True)
        c = data.get('components',{{}})
        t = c.get('Transform',{{}})
        self.pos    = Vec2(t.get('x',0),t.get('y',0))
        sr = c.get('SpriteRenderer',{{}})
        self.color  = tuple(sr.get('color',[150,150,200]))
        self.width  = sr.get('w',32)
        self.height = sr.get('h',32)
        rb = c.get('Rigidbody',None)
        self.has_physics = rb is not None
        self.vel    = Vec2()
        self.on_ground = False
        self.mass   = (rb or {{}}).get('mass',1.0)
        self.gravity_scale = (rb or {{}}).get('gravity_scale',1.0)
        self.bounce = (rb or {{}}).get('bounce',0.0)
        col = c.get('Collider',None)
        self.solid  = col is not None

GX, GY = {scene.physics.gravity.x}, {scene.physics.gravity.y}

entities = [Entity(d) for d in ENTITIES_DATA]
player   = next((e for e in entities if e.tag=='player'), None)
cam_x,cam_y = 0.0, 0.0
font = pygame.font.SysFont('consolas,monospace', 16)
font_big = pygame.font.SysFont('consolas,monospace', 28, bold=True)

def world_to_screen(wx,wy):
    return int(wx-cam_x), int(wy-cam_y)

running = True
while running:
    dt = min(clock.tick(FPS)/1000.0, 0.05)
    for event in pygame.event.get():
        if event.type == pygame.QUIT: running=False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: running=False

    keys = pygame.key.get_pressed()
    # Player movement
    if player:
        spd = 200
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: player.vel.x = -spd
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]: player.vel.x =  spd
        else: player.vel.x *= 0.8
        if (keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]) and player.on_ground:
            player.vel.y = -500
        # Physics
        player.vel.y += GY * player.gravity_scale * dt
        player.vel.y = min(player.vel.y, 800)
        player.pos.x += player.vel.x * dt
        player.pos.y += player.vel.y * dt
        player.on_ground = False
        # Ground clamp (simple)
        if player.pos.y > SCREEN_H - 60:
            player.pos.y = SCREEN_H - 60
            player.vel.y = -player.vel.y * player.bounce if player.bounce > 0 else 0
            player.on_ground = True
        # Camera follow
        cam_x = player.pos.x - SCREEN_W//2
        cam_y = player.pos.y - SCREEN_H//2

    # Render
    screen.fill(BG_COLOR)
    for e in entities:
        if not e.active: continue
        sx,sy = world_to_screen(e.pos.x, e.pos.y)
        if sx+e.width<0 or sx>SCREEN_W or sy+e.height<0 or sy>SCREEN_H: continue
        pygame.draw.rect(screen, e.color, (sx-e.width//2, sy-e.height//2, e.width, e.height))
        if e is player:
            # Draw simple player sprite
            pygame.draw.circle(screen,(255,255,255),(sx,sy-e.height//4),6)
    # HUD
    if player:
        hud = font.render(f"GDL Studio Game | Arrows/WASD: move | Space: jump | ESC: quit",True,(150,150,180))
        screen.blit(hud,(10,10))
    pygame.display.flip()

pygame.quit()
sys.exit()
'''

    def toggle_debug(self):
        if hasattr(self,'scene_canvas'):
            r = getattr(self,'_renderer_debug', False)
            self._renderer_debug = not r
            self._status_var.set(f'Debug: {"ON" if not r else "OFF"}')

    def toggle_lighting(self):
        self._status_var.set('Lighting toggle (available in game runtime)')

    def _on_close(self):
        if messagebox.askyesno('Exit','Exit GDL Studio?'):
            self.destroy()

def main():
    app = GDLStudio()
    app.mainloop()

if __name__ == '__main__':
    main()
