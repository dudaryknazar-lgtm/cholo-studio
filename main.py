#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║           GDL STUDIO  —  Game Design Language IDE             ║
║           Version 1.0  |  Python 3.10+  |  pygame            ║
╠═══════════════════════════════════════════════════════════════╣
║  Features:                                                     ║
║  • Entity-Component-System (ECS) architecture                 ║
║  • Visual Scene Editor with tilemap painting                  ║
║  • Full Physics Engine (gravity, bounce, friction, drag)      ║
║  • Frame-based Sprite Animation system                        ║
║  • GDL scripting language (custom, Lua-inspired)              ║
║  • Particle System with configurable emitters                 ║
║  • Dynamic Lighting (point / directional / ambient)           ║
║  • Dialog system (Undertale-style typewriter)                 ║
║  • Turn-based Battle system with bullet patterns              ║
║  • Camera with follow, zoom, shake, bounds                    ║
║  • Tween / easing animation for UI and objects               ║
║  • Inspector panel (edit every component property)            ║
║  • GDL Code Editor with syntax highlighting                   ║
║  • Save / Load project (JSON)                                 ║
║  • Export to standalone Python + PyInstaller EXE guide        ║
║  • Multi-scene project management                             ║
╠═══════════════════════════════════════════════════════════════╣
║  Install:  pip install pygame Pillow                          ║
║  Run:      python main.py                                     ║
╚═══════════════════════════════════════════════════════════════╝
"""

import sys, os

# Make sure project root is on path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

def check_deps():
    missing = []
    try:
        import tkinter
    except ImportError:
        missing.append('tkinter (built-in, may need python3-tk package on Linux)')
    try:
        import pygame
    except ImportError:
        missing.append('pygame  →  pip install pygame')
    try:
        from PIL import Image
    except ImportError:
        pass  # optional
    if missing:
        print("╔══ Missing dependencies ══╗")
        for m in missing:
            print(f"  ✗  {m}")
        print("\nInstall with:  pip install pygame Pillow")
        if 'pygame' in str(missing):
            print("\nCannot start without pygame.")
            sys.exit(1)

def print_banner():
    print("""
╔═══════════════════════════════════════════════════════╗
║              GDL Studio  v1.0                         ║
║    Game Design Language — Full Game Engine IDE        ║
╚═══════════════════════════════════════════════════════╝
  Features:  ECS · Physics · Animations · GDL scripting
             Tilemap · Particles · Lighting · Battle system
             Camera · Tweens · Dialog · Multi-scene projects
  
  Starting editor...
""")

def main():
    print_banner()
    check_deps()
    from editor.studio import main as run_editor
    run_editor()

if __name__ == '__main__':
    main()
