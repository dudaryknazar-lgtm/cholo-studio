# GDL Studio — Game Design Language

Повноцінний рушій та IDE для розробки 2D ігор на Python.

## Встановлення

```bash
pip install pygame Pillow
python main.py
```

На Linux додатково може знадобитись:
```bash
sudo apt install python3-tk python3-pygame
```

## Структура проекту

```
gdl_studio/
├── main.py               ← точка входу
├── engine/
│   ├── core.py           ← ECS, фізика, компоненти
│   ├── renderer.py       ← Pygame рендерер + ігровий runtime
│   └── gdl_lang.py       ← GDL мова: лексер, парсер, інтерпретатор
├── editor/
│   └── studio.py         ← повний GUI редактор (tkinter)
└── assets/               ← твої текстури, звуки, шрифти
```

## Що вміє рушій

### Entity-Component System (ECS)
- `Transform`     — позиція, поворот, масштаб
- `SpriteRenderer`— текстура, колір, розмір, alpha, flip, шар
- `Animator`      — покадрова анімація (список текстур + FPS)
- `Rigidbody`     — фізика: маса, гравітація, drag, bounce, friction
- `Collider`      — box/circle/trigger коллайдери з callback'ами
- `Camera`        — zoom, follow, shake, bounds, lerp
- `Light`         — point/directional/ambient освітлення
- `ParticleEmitter`— частинки з burst та continuous режимами
- `AudioSource`   — звук з volume, pitch, spatial
- `Script`        — .gdl скрипти для логіки
- `TilemapRenderer`— тайлмапа з малюванням у редакторі
- `DialogSystem`  — діалоги в стилі Undertale (typewriter)
- `BattleSystem`  — покрокові бої з bullet patterns

### Фізика
- Гравітація (налаштовується X/Y)
- Кілька ітерацій на кадр (точніше)
- Box-box та circle-circle коллізії
- Impulse / force / kinematic тіла
- Bounce, friction, linear drag
- Freeze axes

### Анімація
- Назвіть текстури: hero_walk_0.png, hero_walk_1.png...
- Додайте Animation: frames=['hero_walk_0','hero_walk_1'], fps=12
- Animator автоматично перемикає кадри
- on_end callback, loop/no-loop

### GDL Мова

```gdl
scene Main {
    bg_color = #1a1a2e
    gravity  = vec2(0, 980)

    on start {
        show_text("Привіт, світ!")
        camera_shake(5)
    }

    on update {
        if key_pressed("escape") { load_scene("Menu") }
    }
}

character Hero {
    hp = 20; atk = 10; speed = 150
    sprite = "hero_idle"

    on update {
        let dx = 0
        if key_held("left")  { dx = -speed }
        if key_held("right") { dx =  speed  }
    }
}

battle Boss {
    hp = 200; atk = 15; mercy_req = 5
    attacks = [
        bullet { pattern="wave"; speed=120; count=5 }
    ]
}
```

### Tween система
```python
tweens.add(entity.transform.position, 'x', 0, 500, duration=2.0, ease='ease_out')
tweens.add(sprite, 'alpha', 255, 0, duration=1.0, ease='linear')
```

### Збірка EXE
1. Build → Build Python Script → зберегти `game.py`
2. `pyinstaller --onefile --windowed game.py`
3. Готово: `dist/game.exe`

## Можливі типи ігор

- Платформери (Mario, Hollow Knight)
- RPG з діалогами та боями (Undertale, Zelda)
- Top-down шутери та dungeon crawler'и
- Puzzle ігри
- Visual novel
- Аркадні ігри
