"""
cave.py — Side-On Cave Game (Phase 3: Fuse & Boom)

A side-scrolling cave exploration game with physics-based movement.
  - Gravity, jumping, vine climbing, swimming, ledge clamber
  - Cellular automata cave + rolling descent path (zigzag down)
  - Fire only through player agency (torch)
  - Water depth 0-3: trace → ankle → waist → deep
  - Rising flood: water creeps up from the bottom over time
  - VINE FUSE: fire races along dry vine chains (~1 tile/0.5s)
  - EXPLODING MUSHROOMS: fire triggers charge → 3x3 blast
  - GLOWCAPS: bioluminescent fungi that glow when wet

Run: python3 cave.py
"""

import pygame
import random
import sys
import math
import json
import os
import time
from collections import deque

# =============================================================================
# CONSTANTS
# =============================================================================

CELL_SIZE = 20
CAVE_WIDTH = 40           # cells wide
CAVE_HEIGHT = 30          # cells tall
CAVE_PX_W = CAVE_WIDTH * CELL_SIZE    # 800
CAVE_PX_H = CAVE_HEIGHT * CELL_SIZE   # 600
SIDEBAR_W = 220
HUD_HEIGHT = 36
WINDOW_W = CAVE_PX_W + SIDEBAR_W      # 1020
WINDOW_H = CAVE_PX_H + HUD_HEIGHT     # 636

FPS = 60
SIM_INTERVAL = 4          # fire/water sim every N frames (~15 tps)

# Cell types
CELL_AIR      = 0
CELL_STONE    = 1
CELL_WOOD     = 2
CELL_SPRING   = 3
CELL_VINE     = 4
CELL_MUSHROOM = 5
CELL_GLOWCAP  = 6

SOLID_CELLS    = {CELL_STONE, CELL_WOOD, CELL_SPRING}
BURNABLE_CELLS = {CELL_WOOD, CELL_VINE}

# Mushroom explosion
MUSHROOM_CHARGE_FRAMES = 60    # 1 second at 60fps
MUSHROOM_BLAST_RADIUS  = 1     # 3x3 area (radius 1 from center)
BLASTABLE_CELLS = {CELL_WOOD, CELL_VINE, CELL_MUSHROOM, CELL_GLOWCAP}

# Player bounding box (smaller than cell for smooth movement)
PLAYER_W = 14
PLAYER_H = 18

# Water depth levels (0-3):
#   0 = dry
#   1 = ankle  — slightly slower movement
#   2 = waist  — very slow, drowning risk starts
#   3 = deep   — swim only, fast drowning
WATER_MAX = 3
DROWN_THRESHOLD = 2       # water level at which drowning begins (waist)
BREATH_MAX_DEFAULT = 240   # frames (4s at 60fps)
BREATH_MAX = 240           # mutable — can be upgraded by shop
BREATH_RECOVER = 4         # per frame when above water
FALL_DAMAGE_VY = 7.0       # landing velocity threshold for lethal fall (~3.5 cells)

# Colors — dark cave palette
AIR_COLOR        = (25, 30, 45)
STONE_COLOR      = (85, 85, 105)
WOOD_COLOR       = (140, 90, 50)
SPRING_COLOR     = (50, 70, 120)
VINE_COLOR       = (50, 130, 45)
MUSHROOM_CAP     = (190, 150, 210)
MUSHROOM_STEM    = (160, 140, 120)
MUSHROOM_CHARGE_COLOR = (255, 100, 60)   # pulsing orange when about to explode
GLOWCAP_DIM      = (60, 80, 70)          # unlit glowcap (dim green-grey)
GLOWCAP_LIT      = (100, 255, 180)       # wet glowcap (bright cyan-green)
GLOWCAP_GLOW     = (50, 140, 100)        # glow halo color
SKY_TINT         = (35, 42, 65)

FIRE_COLORS = [
    (200, 60, 0),       # intensity 1 — embers
    (230, 100, 0),      # intensity 2
    (255, 160, 20),     # intensity 3
    (255, 230, 80),     # intensity 4 — raging
]

# Water colors per depth level (1-3).  Rendered as partial cell fill from bottom.
WATER_COLORS = [
    (130, 170, 230),    # depth 1 — ankle (light blue, transparent feel)
    (90, 140, 210),     # depth 2 — waist (medium blue)
    (50, 100, 185),     # depth 3 — deep  (rich blue)
]

PLAYER_COLOR       = (0, 230, 100)
PLAYER_DEAD_COLOR  = (220, 30, 30)
PLAYER_DROWN_COLOR = (70, 70, 190)
PLAYER_FELL_COLOR  = (200, 120, 50)
EXIT_COLOR         = (255, 210, 50)
GOLD_COLOR         = (255, 215, 50)
BG_COLOR           = (15, 15, 25)
HUD_BG             = (12, 12, 22)
SIDEBAR_BG         = (18, 18, 28)
FLOOD_WARN_COLOR   = (40, 50, 90)    # subtle tint on rows near flood line

# =============================================================================
# TUNING SYSTEM
# =============================================================================

tuning_keys = [
    'gravity', 'jump_force', 'move_speed', 'terminal_vel',
    'friction', 'climb_speed', 'swim_speed', 'swim_gravity',
    'fire_spread', 'fire_decay', 'vine_fuse',
    'water_seep', 'water_flow_rate',
    'flood_interval', 'flood_amount',
    'vine_regrow', 'fall_damage_vy',
]

tuning = {
    'gravity':        {'val': 0.50,  'min': 0.1,  'max': 1.5,  'step': 0.05, 'fmt': '.2f', 'label': 'Gravity'},
    'jump_force':     {'val': 7.0,   'min': 3.0,  'max': 12.0, 'step': 0.5,  'fmt': '.1f', 'label': 'Jump Force'},
    'move_speed':     {'val': 3.0,   'min': 1.0,  'max': 6.0,  'step': 0.25, 'fmt': '.2f', 'label': 'Move Speed'},
    'terminal_vel':   {'val': 10.0,  'min': 4.0,  'max': 20.0, 'step': 0.5,  'fmt': '.1f', 'label': 'Terminal Vel'},
    'friction':       {'val': 0.80,  'min': 0.3,  'max': 1.0,  'step': 0.05, 'fmt': '.2f', 'label': 'Friction'},
    'climb_speed':    {'val': 2.0,   'min': 0.5,  'max': 4.0,  'step': 0.25, 'fmt': '.2f', 'label': 'Climb Speed'},
    'swim_speed':     {'val': 1.5,   'min': 0.5,  'max': 3.0,  'step': 0.25, 'fmt': '.2f', 'label': 'Swim Speed'},
    'swim_gravity':   {'val': 0.10,  'min': 0.0,  'max': 0.5,  'step': 0.02, 'fmt': '.2f', 'label': 'Swim Grav'},
    'fire_spread':    {'val': 0.04,  'min': 0.0,  'max': 0.20, 'step': 0.01, 'fmt': '.2f', 'label': 'Fire Spread'},
    'fire_decay':     {'val': 0.15,  'min': 0.01, 'max': 0.50, 'step': 0.01, 'fmt': '.2f', 'label': 'Fire Decay'},
    'vine_fuse':      {'val': 0.15,  'min': 0.0,  'max': 0.40, 'step': 0.01, 'fmt': '.2f', 'label': 'Vine Fuse'},
    'water_seep':     {'val': 0.12,  'min': 0.0,  'max': 0.40, 'step': 0.01, 'fmt': '.2f', 'label': 'Water Seep'},
    'water_flow_rate':{'val': 0.25,  'min': 0.05, 'max': 0.60, 'step': 0.01, 'fmt': '.2f', 'label': 'Water Flow'},
    'flood_interval': {'val': 45,    'min': 15,   'max': 120,  'step': 5,    'fmt': '.0f', 'label': 'Flood Intv'},
    'flood_amount':   {'val': 1,     'min': 1,    'max': 3,    'step': 1,    'fmt': '.0f', 'label': 'Flood Amt'},
    'vine_regrow':    {'val': 0.03,  'min': 0.0,  'max': 0.15, 'step': 0.01, 'fmt': '.2f', 'label': 'Vine Regrow'},
    'fall_damage_vy': {'val': 7.0,   'min': 4.0,  'max': 15.0, 'step': 0.5,  'fmt': '.1f', 'label': 'Fall Dmg VY'},
}

def tv(k):
    """Tuning value accessor."""
    return tuning[k]['val']

# =============================================================================
# ITEMS
# =============================================================================

ITEM_TORCH   = 'torch'
ITEM_MACHETE = 'machete'
ITEM_SEED    = 'seed'
ITEM_PICKAXE = 'pickaxe'
ITEM_GOLD    = 'gold'
ITEM_MACGUFFINIUM = 'macguffinium'
MACGUFFINIUM_COLOR = (200, 50, 255)

# Vine seed growth
SEED_GROW_HEIGHT = 5      # max cells a planted seed will grow upward
SEED_GROW_RATE   = 1      # cells per sim tick (1 = one cell per tick ≈ 0.27s)

# Vine ignition delay — torch on vine starts a countdown, not instant fire
VINE_IGNITE_DELAY = 300   # frames (5 seconds at 60fps)

ITEM_DEFS = {
    ITEM_TORCH:   {'uses': 5, 'color': (255, 180, 50),  'name': 'Torch',   'key': 't'},
    ITEM_MACHETE: {'uses': 5, 'color': (200, 200, 210), 'name': 'Machete', 'key': 'm'},
    ITEM_SEED:    {'uses': 3, 'color': (100, 220, 80),   'name': 'Seed',    'key': 'v'},
    ITEM_PICKAXE: {'uses': 3, 'color': (140, 160, 200), 'name': 'Pickaxe', 'key': 'x'},
}
ITEM_ORDER = [ITEM_TORCH, ITEM_MACHETE, ITEM_SEED, ITEM_PICKAXE]

# Shop system
SHOP_ZONE = (1, 1, 5, 3)   # entry area doubles as shop (x_min, y_min, x_max, y_max)
SHOP_ITEMS = [
    {'label': 'Torch +3',    'cost': 2, 'item': ITEM_TORCH,   'amount': 3},
    {'label': 'Machete +3',  'cost': 2, 'item': ITEM_MACHETE, 'amount': 3},
    {'label': 'Pickaxe +2',  'cost': 3, 'item': ITEM_PICKAXE, 'amount': 2},
    {'label': 'Seed +2',     'cost': 3, 'item': ITEM_SEED,    'amount': 2},
    {'label': 'Breath +120', 'cost': 4, 'item': 'breath',     'amount': 120},
]

# =============================================================================
# PYGAME INIT
# =============================================================================

pygame.init()
screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
pygame.display.set_caption("Living Cave — Phase 3: Fuse & Boom")
clock = pygame.time.Clock()

font_hud  = pygame.font.SysFont("menlo", 13, bold=True)
font_msg  = pygame.font.SysFont("menlo", 20, bold=True)
font_big  = pygame.font.SysFont("menlo", 28, bold=True)
font_tiny = pygame.font.SysFont("menlo", 10)
font_ed   = pygame.font.SysFont("menlo", 11)

# =============================================================================
# GAME STATE
# =============================================================================

# Grids — parallel 2D arrays [y][x]
cave    = [[CELL_STONE] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]
fire    = [[0] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]
water   = [[0] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]
pickups = [[None] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]

# Player — pixel-based position
player_x  = 0.0
player_y  = 0.0
player_vx = 0.0
player_vy = 0.0
player_on_ground = False
player_on_vine   = False
player_in_water  = False
player_water_depth = 0       # current depth at player center (0-3)
player_alive = True
player_drowned = False
player_fell = False
breath = BREATH_MAX
won = False

# Inventory & items
inventory = {}
aim_mode = None

# Gold & shop
gold_count = 0
shop_open = False

# Round-trip / Macguffinium
game_phase = 1              # 1=descent, 2=ascent
has_macguffinium = False
macguffinium_gx = 0
macguffinium_gy = 0

# Exit location (grid coords)
exit_gx = CAVE_WIDTH - 4
exit_gy = CAVE_HEIGHT - 5

# Flood state — the rising water threat
flood_line = CAVE_HEIGHT    # row index: water rises from bottom. starts at bottom edge (off screen)
flood_timer = 0             # sim ticks since last flood rise

# Mushroom charges — list of [x, y, frames_remaining]
# When fire touches a mushroom, it starts charging. At 0, it explodes.
mushroom_charges = []

# Growing vines — list of [x, y_tip, remaining_growth]
# When a vine seed is planted, vines grow upward from the plant point.
# y_tip tracks the current top of the growing vine column.
growing_vines = []

# Vine ignition fuses — list of [x, y, frames_remaining]
# When torch hits a vine, it smoulders for 5 seconds before catching fire.
vine_ignitions = []

# Seed — for reproducible cave generation
current_seed = 0

# Archetype system — each cave picks a personality that changes gen params
current_archetype = None       # name of active archetype (str)
forced_archetype = None        # if set, next gen uses this instead of random

CAVE_DEFAULTS = {
    # Noise & cellular automata
    'fill_base':        0.48,
    'fill_depth_scale': 0.10,
    'ca_iterations':    5,
    'ca_threshold':     5,
    # Descent path
    'path_radius':      2,
    'ledge_interval':   6,
    # Stone → wood conversion
    'wood_chance':      0.25,
    # Springs
    'springs_min':      4,
    'springs_max':      7,
    'spring_top_frac':  0.33,
    # Vines
    'vine_density':     0.10,
    'vine_depth_decay': 0.7,
    # Mushrooms
    'mushroom_density': 0.05,
    'mushroom_top_frac':0.40,
    # Glowcaps
    'glowcap_density':  0.03,
    'glowcap_top_frac': 0.50,
    # Plunge pools
    'pools_min':        2,
    'pools_max':        4,
    # Pickups
    'extra_pickups_min': 2,
    'extra_pickups_max': 4,
    # Flood tuning overrides (None = use sidebar tuning value)
    'flood_interval_override': None,
    'flood_amount_override':   None,
    # Post-CA special geometry pass (None, 'shaft', or 'pillared')
    'post_ca_pass':     None,
}

CAVE_ARCHETYPES = {
    'Caverns': {
        # Big open chambers. Spacious exploration.
        'fill_base':        0.40,
        'fill_depth_scale': 0.05,
        'ca_iterations':    4,
        'path_radius':      3,
        'ledge_interval':   8,
        'wood_chance':      0.20,
        'pools_min':        3,
        'pools_max':        5,
    },
    'Warrens': {
        # Tight, claustrophobic tunnels. Machete is king.
        'fill_base':        0.56,
        'fill_depth_scale': 0.12,
        'ca_iterations':    6,
        'path_radius':      1,
        'ledge_interval':   4,
        'wood_chance':      0.30,
        'vine_density':     0.14,
        'springs_min':      2,
        'springs_max':      4,
        'pools_min':        1,
        'pools_max':        2,
        'extra_pickups_min': 3,
        'extra_pickups_max': 5,
    },
    'Flooded Grotto': {
        # Water is the dominant threat. Swim or drown.
        'fill_base':        0.46,
        'springs_min':      8,
        'springs_max':      12,
        'spring_top_frac':  0.25,
        'vine_density':     0.05,
        'vine_depth_decay': 0.9,
        'glowcap_density':  0.06,
        'glowcap_top_frac': 0.35,
        'pools_min':        4,
        'pools_max':        6,
        'flood_interval_override': 30,
        'flood_amount_override':   2,
    },
    'Overgrown': {
        # Vine-choked tinderbox. Fire chain reactions are spectacular.
        'fill_base':        0.46,
        'fill_depth_scale': 0.08,
        'wood_chance':      0.35,
        'vine_density':     0.25,
        'vine_depth_decay': 0.3,
        'mushroom_density': 0.08,
        'mushroom_top_frac':0.30,
        'springs_min':      3,
        'springs_max':      5,
        'extra_pickups_min': 3,
        'extra_pickups_max': 5,
    },
    'The Shaft': {
        # Vertical emphasis. Deep drops, vine seeds critical.
        'fill_base':        0.50,
        'fill_depth_scale': 0.06,
        'path_radius':      1,
        'ledge_interval':   10,
        'vine_density':     0.07,
        'springs_min':      5,
        'springs_max':      8,
        'spring_top_frac':  0.20,
        'pools_min':        1,
        'pools_max':        2,
        'post_ca_pass':     'shaft',
    },
    'Pillared Hall': {
        # Open hall with stone pillars. Architectural feel.
        'fill_base':        0.38,
        'fill_depth_scale': 0.05,
        'ca_iterations':    3,
        'path_radius':      3,
        'wood_chance':      0.15,
        'vine_density':     0.06,
        'mushroom_density': 0.04,
        'glowcap_density':  0.04,
        'post_ca_pass':     'pillared',
    },
}

ARCHETYPE_NAMES = list(CAVE_ARCHETYPES.keys())


def get_gen_params(archetype_name):
    """Merge archetype overrides onto defaults."""
    params = dict(CAVE_DEFAULTS)
    if archetype_name and archetype_name in CAVE_ARCHETYPES:
        params.update(CAVE_ARCHETYPES[archetype_name])
    return params


# Editor / tuning state
editor_sel = 0
edit_mode = False           # E toggles edit mode (pauses sim, enables mouse painting)
edit_brush = 0              # index into EDIT_PALETTE (starts on Air)
edit_layer = 'cell'         # 'cell' for terrain, 'pickup' for items, 'exit' for exit marker

# Cell palette for editor (in order, cycled with scroll wheel or number keys)
EDIT_PALETTE = [
    (CELL_AIR,      'Air',      AIR_COLOR),
    (CELL_STONE,    'Stone',    STONE_COLOR),
    (CELL_WOOD,     'Wood',     WOOD_COLOR),
    (CELL_SPRING,   'Spring',   SPRING_COLOR),
    (CELL_VINE,     'Vine',     VINE_COLOR),
    (CELL_MUSHROOM, 'Mushroom', MUSHROOM_CAP),
    (CELL_GLOWCAP,  'Glowcap',  GLOWCAP_DIM),
]
EDIT_LAYERS = ['cell', 'pickup', 'exit']
edit_layer_idx = 0

# Save directory
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'caves')

# Frame counter + sim tick counter
frame = 0
sim_ticks = 0

# =============================================================================
# HELPERS
# =============================================================================

def is_solid(gx, gy):
    """Check if grid cell blocks movement. Out of bounds = solid."""
    if gx < 0 or gx >= CAVE_WIDTH or gy < 0 or gy >= CAVE_HEIGHT:
        return True
    return cave[gy][gx] in SOLID_CELLS

def grid_at(px, py):
    """Convert pixel position to grid coords."""
    return int(px) // CELL_SIZE, int(py) // CELL_SIZE

def get_overlapping_tiles(left, top, right, bottom):
    """Return list of (gx, gy) grid cells overlapped by a bounding box.
    The -0.01 epsilon prevents snagging at tile seams."""
    min_gx = max(0, int(left) // CELL_SIZE)
    max_gx = min(CAVE_WIDTH - 1, int(right - 0.01) // CELL_SIZE)
    min_gy = max(0, int(top) // CELL_SIZE)
    max_gy = min(CAVE_HEIGHT - 1, int(bottom - 0.01) // CELL_SIZE)
    tiles = []
    for gy in range(min_gy, max_gy + 1):
        for gx in range(min_gx, max_gx + 1):
            tiles.append((gx, gy))
    return tiles

def flood_fill_reachable(sx, sy):
    """BFS flood fill from (sx, sy). Returns set of reachable non-solid cells."""
    visited = set()
    q = deque([(sx, sy)])
    visited.add((sx, sy))
    while q:
        x, y = q.popleft()
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT and (nx, ny) not in visited:
                if cave[ny][nx] not in SOLID_CELLS:
                    visited.add((nx, ny))
                    q.append((nx, ny))
    return visited

# =============================================================================
# CAVE GENERATION
# =============================================================================

def generate_cave(seed=None, archetype=None):
    """Generate cave with rolling descent path, shaped by archetype.
    1. Random noise + cellular automata → organic texture
    2. Post-CA special pass (shaft/pillared if archetype requires)
    3. Carve rolling descent (zigzag: down-right, down-left, down-right)
    4. Clear entry/exit zones
    5. Ensure connectivity
    6. Convert stone → wood
    7. Place springs, vines, mushrooms, glowcaps, pools, pickups
    """
    global cave, fire, water, pickups, exit_gx, exit_gy, current_seed
    global current_archetype

    if seed is None:
        seed = int(time.time() * 1000) % 999999
    current_seed = seed
    random.seed(seed)

    # Pick archetype
    if archetype is not None:
        current_archetype = archetype
    elif forced_archetype is not None:
        current_archetype = forced_archetype
    else:
        current_archetype = random.choice(ARCHETYPE_NAMES)

    p = get_gen_params(current_archetype)

    # Reset grids
    fire[:]    = [[0] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]
    water[:]   = [[0] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]
    pickups[:] = [[None] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]

    # --- Step 1: Random noise fill ---
    for y in range(CAVE_HEIGHT):
        for x in range(CAVE_WIDTH):
            if x == 0 or x == CAVE_WIDTH - 1 or y == 0 or y == CAVE_HEIGHT - 1:
                cave[y][x] = CELL_STONE
            else:
                depth_ratio = y / CAVE_HEIGHT
                fill_chance = p['fill_base'] + depth_ratio * p['fill_depth_scale']
                cave[y][x] = CELL_STONE if random.random() < fill_chance else CELL_AIR

    # --- Step 2: Cellular automata smoothing ---
    for _ in range(p['ca_iterations']):
        new_cave = [row[:] for row in cave]
        for y in range(1, CAVE_HEIGHT - 1):
            for x in range(1, CAVE_WIDTH - 1):
                walls = 0
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        ny, nx = y + dy, x + dx
                        if nx < 0 or nx >= CAVE_WIDTH or ny < 0 or ny >= CAVE_HEIGHT:
                            walls += 1
                        elif cave[ny][nx] == CELL_STONE:
                            walls += 1
                new_cave[y][x] = CELL_STONE if walls >= p['ca_threshold'] else CELL_AIR
        cave[:] = new_cave

    # --- Step 2b: Post-CA special geometry pass ---
    if p['post_ca_pass'] == 'shaft':
        _carve_shaft_columns()
    elif p['post_ca_pass'] == 'pillared':
        _carve_pillared_hall()

    # --- Step 3: Carve rolling descent ---
    carve_rolling_descent(p)

    # --- Step 4: Clear entry and exit zones ---
    for y in range(1, 4):
        for x in range(1, 6):
            cave[y][x] = CELL_AIR
    for x in range(1, 6):
        cave[4][x] = CELL_STONE

    exit_gx = CAVE_WIDTH - 4
    exit_gy = CAVE_HEIGHT - 5
    for y in range(CAVE_HEIGHT - 5, CAVE_HEIGHT - 2):
        for x in range(CAVE_WIDTH - 6, CAVE_WIDTH - 1):
            cave[y][x] = CELL_AIR
    for x in range(CAVE_WIDTH - 6, CAVE_WIDTH - 1):
        cave[CAVE_HEIGHT - 2][x] = CELL_STONE

    # --- Step 5: Ensure connectivity ---
    ensure_connectivity(2, 2, exit_gx, exit_gy)

    # --- Step 6: Convert stone → wood ---
    for y in range(2, CAVE_HEIGHT - 2):
        for x in range(2, CAVE_WIDTH - 2):
            if cave[y][x] == CELL_STONE:
                near_entry = (x < 7 and y < 6)
                near_exit = (x > CAVE_WIDTH - 8 and y > CAVE_HEIGHT - 7)
                if near_entry or near_exit:
                    continue
                if random.random() < p['wood_chance']:
                    cave[y][x] = CELL_WOOD

    # --- Step 7: Place features ---
    place_springs(p)
    place_vines(p)
    place_mushrooms(p)
    place_glowcaps(p)
    carve_plunge_pools(p)
    place_pickups(p)

    # --- Apply archetype flood tuning overrides ---
    if p['flood_interval_override'] is not None:
        tuning['flood_interval']['val'] = p['flood_interval_override']
    if p['flood_amount_override'] is not None:
        tuning['flood_amount']['val'] = p['flood_amount_override']


def carve_rolling_descent(p):
    """Carve a wide zigzag path through the cave.
    Path width and ledge frequency controlled by archetype params."""

    w, h = CAVE_WIDTH, CAVE_HEIGHT
    waypoints = [
        (4, 3),
        (w * 2 // 3 + random.randint(-3, 3), h // 3 + random.randint(-2, 2)),
        (w // 3 + random.randint(-3, 3), h * 2 // 3 + random.randint(-2, 2)),
        (w - 5, h - 4),
    ]

    radius = p['path_radius']
    ledge_int = p['ledge_interval']
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        _carve_wide_slope(x0, y0, x1, y1, radius, ledge_int)


def _carve_wide_slope(x0, y0, x1, y1, radius=2, ledge_interval=6):
    """Carve a gently sloping path between two points.
    Radius controls width, ledge_interval controls stepping frequency."""
    dist = max(abs(x1 - x0), abs(y1 - y0))
    steps = max(dist, 10)

    for i in range(steps + 1):
        t = i / steps
        cx = x0 + (x1 - x0) * t + math.sin(t * math.pi * 2) * 1.5
        cy = y0 + (y1 - y0) * t + math.sin(t * math.pi * 3 + 1.0) * 1.0
        gx = int(cx)
        gy = int(cy)

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = gx + dx, gy + dy
                if abs(dx) == radius and abs(dy) == radius:
                    continue
                if 1 <= nx < CAVE_WIDTH - 1 and 1 <= ny < CAVE_HEIGHT - 1:
                    cave[ny][nx] = CELL_AIR

    # Ledges along path
    for i in range(steps + 1):
        t = i / steps
        cx = x0 + (x1 - x0) * t + math.sin(t * math.pi * 2) * 1.5
        cy = y0 + (y1 - y0) * t
        gx = int(cx)
        gy = int(cy)

        if i % ledge_interval == ledge_interval // 2:
            ledge_y = gy + radius
            ledge_w = random.randint(2, 4)
            ledge_start = gx - ledge_w // 2
            for lx in range(ledge_start, ledge_start + ledge_w):
                if 1 <= lx < CAVE_WIDTH - 1 and 1 <= ledge_y < CAVE_HEIGHT - 1:
                    cave[ledge_y][lx] = CELL_STONE
                    if ledge_y - 1 >= 1:
                        cave[ledge_y - 1][lx] = CELL_AIR


def _carve_shaft_columns():
    """Carve 2-3 vertical shafts for The Shaft archetype.
    Each shaft is 2-3 cells wide, running 50-80% of cave height."""
    num_shafts = random.randint(2, 3)
    for _ in range(num_shafts):
        sx = random.randint(6, CAVE_WIDTH - 7)
        shaft_w = random.randint(2, 3)
        top = random.randint(3, CAVE_HEIGHT // 4)
        bottom = random.randint(CAVE_HEIGHT * 3 // 4, CAVE_HEIGHT - 3)
        for y in range(top, bottom):
            for x in range(sx, sx + shaft_w):
                if 1 <= x < CAVE_WIDTH - 1 and 1 <= y < CAVE_HEIGHT - 1:
                    cave[y][x] = CELL_AIR


def _carve_pillared_hall():
    """Carve a large open central area, then scatter stone pillars.
    Creates an architectural feel with good visibility."""
    hall_x0 = CAVE_WIDTH // 5
    hall_x1 = CAVE_WIDTH * 4 // 5
    hall_y0 = CAVE_HEIGHT // 4
    hall_y1 = CAVE_HEIGHT * 3 // 4
    # Carve the hall
    for y in range(hall_y0, hall_y1):
        for x in range(hall_x0, hall_x1):
            if 1 <= x < CAVE_WIDTH - 1 and 1 <= y < CAVE_HEIGHT - 1:
                cave[y][x] = CELL_AIR
    # Stone floor under the hall
    for x in range(hall_x0, hall_x1):
        if 1 <= x < CAVE_WIDTH - 1 and hall_y1 < CAVE_HEIGHT:
            cave[hall_y1][x] = CELL_STONE
    # Scatter pillars (tall stone columns)
    num_pillars = random.randint(5, 8)
    for _ in range(num_pillars):
        px = random.randint(hall_x0 + 2, hall_x1 - 2)
        pillar_h = random.randint(3, hall_y1 - hall_y0 - 2)
        for py in range(hall_y1 - pillar_h, hall_y1):
            if 1 <= py < CAVE_HEIGHT - 1:
                cave[py][px] = CELL_STONE


def ensure_connectivity(sx, sy, ex, ey):
    """If exit isn't reachable from start, carve a tunnel using drunkard's walk."""
    reachable = flood_fill_reachable(sx, sy)
    if (ex, ey) in reachable:
        return

    x, y = ex, ey
    max_steps = CAVE_WIDTH * CAVE_HEIGHT
    for _ in range(max_steps):
        if (x, y) in reachable:
            break
        dx = 0 if x == sx else (-1 if x > sx else 1)
        dy = 0 if y == sy else (-1 if y > sy else 1)
        if random.random() < 0.3:
            dx = random.choice([-1, 0, 1])
        if random.random() < 0.3:
            dy = random.choice([-1, 0, 1])
        if random.random() < 0.5 and dx != 0:
            nx, ny = x + dx, y
        elif dy != 0:
            nx, ny = x, y + dy
        else:
            nx, ny = x + (dx if dx != 0 else random.choice([-1, 1])), y
        if 1 <= nx < CAVE_WIDTH - 1 and 1 <= ny < CAVE_HEIGHT - 1:
            cave[ny][nx] = CELL_AIR
            for ddx, ddy in [(0, 1), (1, 0)]:
                nnx, nny = nx + ddx, ny + ddy
                if 1 <= nnx < CAVE_WIDTH - 1 and 1 <= nny < CAVE_HEIGHT - 1:
                    if cave[nny][nnx] == CELL_STONE:
                        cave[nny][nnx] = CELL_AIR
            x, y = nx, ny


def place_springs(p):
    """Place spring cells. Count and vertical range from archetype params."""
    target = random.randint(p['springs_min'], p['springs_max'])
    placed = 0
    for _ in range(target * 100):
        x = random.randint(2, CAVE_WIDTH - 3)
        y = random.randint(int(CAVE_HEIGHT * p['spring_top_frac']), CAVE_HEIGHT - 3)
        if cave[y][x] != CELL_STONE:
            continue
        # Must have at least one adjacent non-solid cell
        has_air_near = False
        for dx, dy in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT:
                if cave[ny][nx] not in SOLID_CELLS:
                    has_air_near = True
                    break
        if has_air_near:
            cave[y][x] = CELL_SPRING
            placed += 1
            if placed >= target:
                break


def place_vines(p):
    """Place vine cells on air adjacent to stone/wood walls.
    Density and depth decay from archetype params."""
    for y in range(1, CAVE_HEIGHT - 1):
        for x in range(1, CAVE_WIDTH - 1):
            if cave[y][x] != CELL_AIR:
                continue
            has_wall = False
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = y + dy, x + dx
                if 0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT:
                    if cave[ny][nx] in {CELL_STONE, CELL_WOOD}:
                        has_wall = True
                        break
            if not has_wall:
                continue
            depth_ratio = y / CAVE_HEIGHT
            chance = p['vine_density'] * (1.0 - depth_ratio * p['vine_depth_decay'])
            if random.random() < chance:
                cave[y][x] = CELL_VINE


def place_mushrooms(p):
    """Place mushroom cells sitting on solid ground.
    Density and vertical range from archetype params."""
    for y in range(int(CAVE_HEIGHT * p['mushroom_top_frac']), CAVE_HEIGHT - 2):
        for x in range(2, CAVE_WIDTH - 2):
            if cave[y][x] != CELL_AIR:
                continue
            if y + 1 >= CAVE_HEIGHT or cave[y + 1][x] not in SOLID_CELLS:
                continue
            if random.random() < p['mushroom_density']:
                cave[y][x] = CELL_MUSHROOM


def place_glowcaps(p):
    """Place glowcap fungi — bioluminescent when wet.
    Density and vertical range from archetype params."""
    for y in range(int(CAVE_HEIGHT * p['glowcap_top_frac']), CAVE_HEIGHT - 2):
        for x in range(2, CAVE_WIDTH - 2):
            if cave[y][x] != CELL_AIR:
                continue
            if y + 1 >= CAVE_HEIGHT or cave[y + 1][x] not in SOLID_CELLS:
                continue
            if random.random() < p['glowcap_density']:
                cave[y][x] = CELL_GLOWCAP


def carve_plunge_pools(p):
    """Create natural basins that fill with water first.
    Pool count from archetype params."""
    num_pools = random.randint(p['pools_min'], p['pools_max'])
    for _ in range(num_pools):
        # Pick a random spot in the lower 60%
        px = random.randint(5, CAVE_WIDTH - 6)
        py = random.randint(CAVE_HEIGHT * 2 // 5, CAVE_HEIGHT - 5)

        # Find the floor: scan downward from py to find solid ground
        floor_y = py
        while floor_y < CAVE_HEIGHT - 2 and cave[floor_y][px] not in SOLID_CELLS:
            floor_y += 1

        if floor_y >= CAVE_HEIGHT - 2:
            continue

        # Carve a basin: widen the area just above the floor
        pool_w = random.randint(3, 6)
        pool_h = random.randint(2, 3)
        start_x = px - pool_w // 2
        start_y = floor_y - pool_h

        for y in range(start_y, floor_y):
            for x in range(start_x, start_x + pool_w):
                if 1 <= x < CAVE_WIDTH - 1 and 1 <= y < CAVE_HEIGHT - 1:
                    if cave[y][x] in {CELL_STONE, CELL_WOOD}:
                        cave[y][x] = CELL_AIR
        # Ensure the floor under the pool is solid
        for x in range(start_x, start_x + pool_w):
            if 1 <= x < CAVE_WIDTH - 1 and floor_y < CAVE_HEIGHT:
                if cave[floor_y][x] == CELL_AIR:
                    cave[floor_y][x] = CELL_STONE


def place_pickups(p):
    """Scatter item pickups. Guarantee a torch near start.
    Extra pickup count from archetype params."""
    reachable = flood_fill_reachable(2, 2)

    near_start = [(x, y) for x, y in reachable
                  if x < 10 and y < 8
                  and cave[y][x] == CELL_AIR
                  and not (x < 3 and y < 3)]
    if near_start:
        tx, ty = random.choice(near_start)
        pickups[ty][tx] = ITEM_TORCH

    candidates = [(x, y) for x, y in reachable
                  if cave[y][x] == CELL_AIR
                  and pickups[y][x] is None
                  and (x > 6 or y > 6)]
    random.shuffle(candidates)
    extra = min(random.randint(p['extra_pickups_min'], p['extra_pickups_max']), len(candidates))
    for i in range(extra):
        x, y = candidates[i]
        item = random.choice([ITEM_TORCH, ITEM_MACHETE, ITEM_SEED, ITEM_PICKAXE])
        pickups[y][x] = item

    # Gold scatter
    gold_candidates = [(x, y) for x, y in reachable
                       if cave[y][x] == CELL_AIR
                       and pickups[y][x] is None
                       and (x > 4 or y > 4)]
    random.shuffle(gold_candidates)
    gold_num = min(random.randint(8, 15), len(gold_candidates))
    for i in range(gold_num):
        x, y = gold_candidates[i]
        pickups[y][x] = ITEM_GOLD


def place_macguffinium():
    """Place the macguffinium at the deepest reachable air cell."""
    global macguffinium_gx, macguffinium_gy
    reachable = flood_fill_reachable(2, 2)
    # Find deepest (highest y) reachable air cell
    best = None
    for x, y in reachable:
        if cave[y][x] == CELL_AIR and pickups[y][x] is None:
            if best is None or y > best[1]:
                best = (x, y)
    if best:
        macguffinium_gx, macguffinium_gy = best
        pickups[best[1]][best[0]] = ITEM_MACGUFFINIUM


# =============================================================================
# INIT LEVEL
# =============================================================================

def init_level(seed=None, archetype=None):
    """Generate cave and reset player state.
    Pass a seed for reproducible generation, or None for random.
    Pass an archetype name to force a specific cave type."""
    global player_x, player_y, player_vx, player_vy
    global player_on_ground, player_on_vine, player_in_water, player_water_depth
    global player_alive, player_drowned, player_fell, breath, won
    global inventory, aim_mode, frame, sim_ticks
    global flood_line, flood_timer, mushroom_charges, growing_vines, vine_ignitions
    global gold_count, shop_open, BREATH_MAX
    global game_phase, has_macguffinium, macguffinium_gx, macguffinium_gy

    # Reset flood tuning to defaults before generation
    # (so Flooded Grotto overrides don't persist across regens)
    tuning['flood_interval']['val'] = 45
    tuning['flood_amount']['val'] = 1

    generate_cave(seed=seed, archetype=archetype)
    place_macguffinium()

    mushroom_charges = []
    growing_vines = []
    vine_ignitions = []

    # Place player in entry zone
    player_x = 2.0 * CELL_SIZE + (CELL_SIZE - PLAYER_W) / 2
    player_y = 3.0 * CELL_SIZE - PLAYER_H
    player_vx = 0.0
    player_vy = 0.0
    player_on_ground = False
    player_on_vine = False
    player_in_water = False
    player_water_depth = 0
    player_alive = True
    player_drowned = False
    player_fell = False
    BREATH_MAX = BREATH_MAX_DEFAULT
    breath = BREATH_MAX
    won = False

    gold_count = 0
    shop_open = False
    game_phase = 1
    has_macguffinium = False
    inventory = {ITEM_TORCH: 3}
    aim_mode = None
    frame = 0
    sim_ticks = 0

    # Flood starts at the very bottom — rises over time
    flood_line = CAVE_HEIGHT
    flood_timer = 0

# =============================================================================
# SIMULATION — fire, water, flood (runs at ~15 tps via SIM_INTERVAL)
# =============================================================================

def sim_tick():
    """Run one tick of fire + water + flood + vine simulation."""
    global sim_ticks
    sim_ticks += 1
    seep_from_springs()
    update_fire()
    update_water()
    update_flood()
    update_vines()
    update_growing_vines()


def update_fire():
    """Fire spread, decay, and burn.
    VINE FUSE: fire on a vine spreads to adjacent vines much faster than
    normal fire spread — controlled by vine_fuse tuning param.
    Vines also burn away slower so the fuse has time to propagate.
    MUSHROOM TRIGGER: fire adjacent to a mushroom starts its charge timer."""
    new_fire = [row[:] for row in fire]
    charging_set = {(c[0], c[1]) for c in mushroom_charges}

    for y in range(1, CAVE_HEIGHT - 1):
        for x in range(1, CAVE_WIDTH - 1):
            if fire[y][x] <= 0:
                continue
            intensity = fire[y][x]

            # Water immediately douses fire
            if water[y][x] > 0:
                new_fire[y][x] = 0
                water[y][x] = max(0, water[y][x] - 1)  # steam
                continue

            # --- Spread to neighbors ---
            source_is_vine = (cave[y][x] == CELL_VINE)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT):
                    continue

                ncell = cave[ny][nx]

                # MUSHROOM TRIGGER: fire next to mushroom starts charge
                if ncell == CELL_MUSHROOM and (nx, ny) not in charging_set:
                    mushroom_charges.append([nx, ny, MUSHROOM_CHARGE_FRAMES])
                    charging_set.add((nx, ny))
                    continue

                # Normal spread to burnable cells
                if ncell in BURNABLE_CELLS and fire[ny][nx] == 0 and water[ny][nx] == 0:
                    target_is_vine = (ncell == CELL_VINE)
                    # VINE FUSE: vine→vine spread is much faster
                    if source_is_vine and target_is_vine:
                        spread_chance = tv('vine_fuse')   # ~0.15 = ~1 tile per 0.5s
                    else:
                        spread_chance = tv('fire_spread')  # ~0.04 = normal
                    if random.random() < spread_chance:
                        new_fire[ny][nx] = max(new_fire[ny][nx], max(1, intensity - 1))

            # --- Burn the cell (convert to air) ---
            if cave[y][x] in BURNABLE_CELLS:
                # Vines burn away SLOWER so fuse has time to propagate
                burn_rate = 0.04 if cave[y][x] == CELL_VINE else 0.08
                if random.random() < burn_rate:
                    cave[y][x] = CELL_AIR

            # --- Decay ---
            if random.random() < tv('fire_decay'):
                new_fire[y][x] = max(0, new_fire[y][x] - 1)

    fire[:] = new_fire


def update_water():
    """Gravity-based water flow: down first, sideways if blocked.
    Process bottom-up so water settles in one tick.
    Water max is 3 (depth levels: ankle, waist, deep)."""
    new_water = [row[:] for row in water]

    for y in range(CAVE_HEIGHT - 2, 0, -1):
        for x in range(1, CAVE_WIDTH - 1):
            if new_water[y][x] <= 0:
                continue
            level = new_water[y][x]

            # 1. Flow DOWN
            if y + 1 < CAVE_HEIGHT and cave[y + 1][x] not in SOLID_CELLS:
                space_below = WATER_MAX - new_water[y + 1][x]
                if space_below > 0 and random.random() < tv('water_flow_rate'):
                    transfer = min(level, space_below, 1)
                    new_water[y + 1][x] += transfer
                    new_water[y][x] -= transfer
                    level = new_water[y][x]
                    if level <= 0:
                        continue

            # 2. Spread SIDEWAYS if blocked below
            below_full = (y + 1 >= CAVE_HEIGHT
                          or cave[y + 1][x] in SOLID_CELLS
                          or new_water[y + 1][x] >= WATER_MAX)
            if below_full and level > 0:
                for dx in [-1, 1]:
                    nx = x + dx
                    if 0 < nx < CAVE_WIDTH - 1 and cave[y][nx] not in SOLID_CELLS:
                        if new_water[y][nx] < level:
                            if random.random() < tv('water_flow_rate') * 0.3:
                                new_water[y][nx] = min(WATER_MAX, new_water[y][nx] + 1)
                                new_water[y][x] = max(0, new_water[y][x] - 1)
                                level = new_water[y][x]
                                if level <= 0:
                                    break

            # 3. Slow evaporation (very slow — flood should feel relentless)
            if random.random() < 0.001:
                new_water[y][x] = max(0, new_water[y][x] - 1)

    water[:] = new_water


def seep_from_springs():
    """Spring cells emit water into adjacent non-solid cells."""
    for y in range(CAVE_HEIGHT):
        for x in range(CAVE_WIDTH):
            if cave[y][x] != CELL_SPRING:
                continue
            for dx, dy in [(0, 1), (0, -1), (-1, 0), (1, 0)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT:
                    if cave[ny][nx] not in SOLID_CELLS and water[ny][nx] < WATER_MAX:
                        if random.random() < tv('water_seep'):
                            water[ny][nx] = min(WATER_MAX, water[ny][nx] + 1)


def update_flood():
    """Rising flood mechanic.
    Every flood_interval sim ticks, the flood line rises by 1 row.
    Cells at or below the flood line get water injected into them,
    simulating rising ground water.

    The flood starts slow (bottom fills first — plunge pools catch it)
    and becomes threatening as it creeps up toward the player."""
    global flood_line, flood_timer

    flood_timer += 1
    interval = int(tv('flood_interval'))
    # Flood accelerates in phase 2 (ascent)
    if game_phase == 2:
        interval = max(10, interval * 2 // 3)

    if flood_timer >= interval:
        flood_timer = 0
        amount = int(tv('flood_amount'))

        # Rise the flood line
        if flood_line > 1:
            flood_line -= 1

        # Inject water at and below the flood line
        for y in range(flood_line, CAVE_HEIGHT - 1):
            for x in range(1, CAVE_WIDTH - 1):
                if cave[y][x] not in SOLID_CELLS and water[y][x] < amount:
                    # Don't flood everything instantly — probabilistic fill
                    if random.random() < 0.3:
                        water[y][x] = min(WATER_MAX, water[y][x] + 1)

def update_vines():
    """Vine lifecycle:
    1. DROWNING — water kills submerged vines (depth >= 2). They become air.
       This is the key tension: the flood destroys your climbing routes.
    2. REGROWTH — air cells adjacent to a living vine (and adjacent to a wall)
       can sprout a new vine. Only happens ABOVE the flood line, so drowned
       vines don't magically come back underwater.
       Rate controlled by vine_regrow tuning param.

    The dynamic: flood kills vines below → vines slowly creep back from
    survivors above → player has a window to use them before flood catches up."""

    # --- Phase 1: Kill submerged vines ---
    for y in range(CAVE_HEIGHT):
        for x in range(CAVE_WIDTH):
            if cave[y][x] == CELL_VINE and water[y][x] >= 2:
                cave[y][x] = CELL_AIR   # vine drowns

    # --- Phase 2: Regrow from living neighbors ---
    if tv('vine_regrow') <= 0:
        return

    # Collect new vine positions (don't modify cave while iterating)
    new_vines = []
    for y in range(1, CAVE_HEIGHT - 1):
        for x in range(1, CAVE_WIDTH - 1):
            if cave[y][x] != CELL_AIR:
                continue
            # Must be above the flood line (no regrowing underwater)
            if y >= flood_line:
                continue
            # Must not have water on it
            if water[y][x] > 0:
                continue
            # Must not have fire on it
            if fire[y][x] > 0:
                continue
            # Must be adjacent to at least one living vine
            has_vine_neighbor = False
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = y + dy, x + dx
                if 0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT:
                    if cave[ny][nx] == CELL_VINE:
                        has_vine_neighbor = True
                        break
            if not has_vine_neighbor:
                continue
            # Must be adjacent to at least one wall (vines cling to surfaces)
            has_wall = False
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ny, nx = y + dy, x + dx
                if 0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT:
                    if cave[ny][nx] in {CELL_STONE, CELL_WOOD}:
                        has_wall = True
                        break
            if not has_wall:
                continue
            # Probability check
            if random.random() < tv('vine_regrow'):
                new_vines.append((x, y))

    # Apply new vines
    for x, y in new_vines:
        # Don't overwrite pickups
        if pickups[y][x] is not None:
            continue
        cave[y][x] = CELL_VINE


def update_growing_vines():
    """Grow planted vine seeds upward.
    Each sim tick, each active growing vine extends one cell upward (if air).
    Stops if it hits stone/wood, another vine, or runs out of growth.
    The vine grows WITHOUT needing wall adjacency — that's the whole point
    of the seed item: creating routes in open space."""
    global growing_vines
    still_growing = []
    for gv in growing_vines:
        gx, gy_tip, remaining = gv

        # Check: is the vine we planted still alive? (fire/water may have killed it)
        if cave[gy_tip][gx] != CELL_VINE:
            continue  # vine was destroyed, stop growing

        if remaining <= 0:
            continue  # done growing

        # Try to grow one cell upward
        ny = gy_tip - 1
        if ny < 1:
            continue  # hit top of cave

        target = cave[ny][gx]
        if target == CELL_AIR and fire[ny][gx] == 0 and water[ny][gx] < 2:
            cave[ny][gx] = CELL_VINE
            still_growing.append([gx, ny, remaining - 1])
        elif target == CELL_VINE:
            # Already a vine above — skip up to it and keep growing from there
            still_growing.append([gx, ny, remaining - 1])
        else:
            # Hit solid cell — stop growing
            pass

    growing_vines = still_growing


def tick_mushroom_charges():
    """Tick down mushroom charge timers (called every frame, not sim tick).
    When a charge reaches 0, the mushroom explodes.
    Returns True if any explosion happened (for screen shake etc later)."""
    global mushroom_charges
    exploded = False
    still_charging = []
    for charge in mushroom_charges:
        mx, my, timer = charge
        # If mushroom was already destroyed (by water, another explosion, etc), cancel
        if cave[my][mx] != CELL_MUSHROOM:
            continue
        timer -= 1
        if timer <= 0:
            explode_mushroom(mx, my)
            exploded = True
        else:
            still_charging.append([mx, my, timer])
    mushroom_charges = still_charging
    return exploded


def tick_vine_ignitions():
    """Tick down vine ignition fuses (called every frame).
    When a fuse reaches 0, the vine catches fire normally.
    Cancelled if the vine is destroyed (chopped, exploded) or flooded."""
    global vine_ignitions
    still_burning = []
    for fuse in vine_ignitions:
        vx, vy, timer = fuse
        # Cancel if vine is gone (chopped, exploded, burned by chain)
        if cave[vy][vx] != CELL_VINE:
            continue
        # Cancel if flooded — water douses the smoulder
        if water[vy][vx] >= 2:
            continue
        timer -= 1
        if timer <= 0:
            # Ignite! Normal fire system takes over
            fire[vy][vx] = 3
        else:
            still_burning.append([vx, vy, timer])
    vine_ignitions = still_burning


def explode_mushroom(mx, my):
    """BOOM. 3×3 blast centered on (mx, my).
    - Destroys wood, vine, mushroom, glowcap → air
    - Sets fire in the blast zone
    - Stone survives (it's rock — tough stuff)
    - Chain reactions: if blast fire touches another mushroom, it'll trigger too"""
    r = MUSHROOM_BLAST_RADIUS   # 1 = 3x3 area

    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            nx, ny = mx + dx, my + dy
            if not (1 <= nx < CAVE_WIDTH - 1 and 1 <= ny < CAVE_HEIGHT - 1):
                continue
            cell = cave[ny][nx]
            if cell in BLASTABLE_CELLS:
                cave[ny][nx] = CELL_AIR
                fire[ny][nx] = 3    # explosion fire
            elif cell == CELL_AIR:
                fire[ny][nx] = max(fire[ny][nx], 2)  # blast wave
            # Stone and springs survive — they're tough

    # The mushroom itself is already destroyed (it was in BLASTABLE_CELLS)
    # Water in blast zone gets evaporated by the heat
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            nx, ny = mx + dx, my + dy
            if 0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT:
                if water[ny][nx] > 0:
                    water[ny][nx] = max(0, water[ny][nx] - 1)


# =============================================================================
# PLAYER PHYSICS
# =============================================================================

def apply_gravity():
    """Add gravity to vertical velocity. Reduced in water, suspended on vine."""
    global player_vy
    if player_on_vine:
        return
    if player_in_water:
        player_vy += tv('swim_gravity')
    else:
        player_vy += tv('gravity')
    if player_vy > tv('terminal_vel'):
        player_vy = tv('terminal_vel')


def handle_movement_input(keys):
    """Read held keys, set velocity. Water depth affects movement speed."""
    global player_vx, player_vy, player_on_vine

    if aim_mode:
        player_vx *= tv('friction')
        if abs(player_vx) < 0.1:
            player_vx = 0
        return

    # --- Speed based on water depth ---
    base_speed = tv('move_speed')
    if player_water_depth >= 3:
        speed = tv('swim_speed')              # deep: swim speed
    elif player_water_depth == 2:
        speed = base_speed * 0.4              # waist: very slow
    elif player_water_depth == 1:
        speed = base_speed * 0.7              # ankle: slightly slow
    else:
        speed = base_speed                    # dry: full speed

    # --- Horizontal movement ---
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        player_vx = -speed
    elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        player_vx = speed
    else:
        player_vx *= tv('friction')
        if abs(player_vx) < 0.1:
            player_vx = 0

    # --- Vine climbing ---
    if player_on_vine:
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            player_vy = -tv('climb_speed')
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            player_vy = tv('climb_speed')
        else:
            player_vy = 0
        if keys[pygame.K_SPACE]:
            player_on_vine = False
            player_vy = -tv('jump_force') * 0.6
        return

    # --- Swimming (deep water) ---
    if player_water_depth >= 3:
        if keys[pygame.K_UP] or keys[pygame.K_w] or keys[pygame.K_SPACE]:
            player_vy = -tv('swim_speed')
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            player_vy = tv('swim_speed')
        return

    # --- Waist-deep water: can still jump but weaker ---
    if player_water_depth == 2:
        if player_on_ground and (keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]):
            player_vy = -tv('jump_force') * 0.5   # weak jump from waist water
        return

    # --- Normal jump ---
    if player_on_ground:
        if keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]:
            player_vy = -tv('jump_force')


def resolve_x():
    """Push player out of horizontal tile overlaps.
    LEDGE CLAMBER: if the player walks into a 1-cell-high wall and the cell
    above it is air (and the player fits), pop them up onto the ledge.
    This lets you climb out of water onto adjacent ledges naturally."""
    global player_x, player_y, player_vx, player_vy, player_on_ground
    left = player_x
    top = player_y
    right = player_x + PLAYER_W
    bottom = player_y + PLAYER_H
    for gx, gy in get_overlapping_tiles(left, top, right, bottom):
        if not is_solid(gx, gy):
            continue
        tile_left = gx * CELL_SIZE
        tile_right = tile_left + CELL_SIZE

        # --- Ledge clamber check ---
        # The wall cell we hit is (gx, gy).
        # Check: is the cell ABOVE the wall (gx, gy-1) non-solid?
        # And: is the cell above THAT (gx, gy-2) also non-solid (headroom)?
        # And: is the player's feet roughly at or below the wall's top edge?
        can_clamber = False
        if gy >= 1 and not is_solid(gx, gy - 1):
            # Check headroom (cell above the landing spot)
            has_headroom = (gy < 2) or not is_solid(gx, gy - 2)
            # Player's feet (bottom) should be within 1 cell of the wall top
            wall_top = gy * CELL_SIZE
            feet_y = player_y + PLAYER_H
            if has_headroom and feet_y >= wall_top - 2 and feet_y <= wall_top + CELL_SIZE:
                can_clamber = True

        if can_clamber:
            # Pop player up onto the ledge
            player_y = (gy - 1) * CELL_SIZE + CELL_SIZE - PLAYER_H
            player_vy = 0
            player_on_ground = True
            # Nudge horizontally onto the ledge
            if player_vx > 0:
                player_x = tile_left + 1
            elif player_vx < 0:
                player_x = tile_right - PLAYER_W - 1
        else:
            # Normal wall collision — push back
            if player_vx > 0:
                player_x = tile_left - PLAYER_W
            elif player_vx < 0:
                player_x = tile_right
            player_vx = 0
        break


def resolve_y():
    """Push player out of vertical tile overlaps. Sets on_ground. Checks fall damage."""
    global player_y, player_vy, player_on_ground, player_alive, player_fell
    pre_land_vy = player_vy
    player_on_ground = False
    left = player_x
    top = player_y
    right = player_x + PLAYER_W
    bottom = player_y + PLAYER_H
    for gx, gy in get_overlapping_tiles(left, top, right, bottom):
        if not is_solid(gx, gy):
            continue
        tile_top = gy * CELL_SIZE
        tile_bottom = tile_top + CELL_SIZE
        if player_vy >= 0:
            player_y = tile_top - PLAYER_H
            # Fall damage check — water cushion saves you
            if pre_land_vy >= tv('fall_damage_vy') and player_alive:
                land_cx = int((player_x + PLAYER_W / 2)) // CELL_SIZE
                land_cy = int((player_y + PLAYER_H / 2)) // CELL_SIZE
                land_water = 0
                if 0 <= land_cx < CAVE_WIDTH and 0 <= land_cy < CAVE_HEIGHT:
                    land_water = water[land_cy][land_cx]
                if land_water < 2:
                    player_alive = False
                    player_fell = True
            player_vy = 0
            player_on_ground = True
        elif player_vy < 0:
            player_y = tile_bottom
            player_vy = 0
        break


def move_and_collide():
    """Move player by velocity, resolve collisions on each axis separately."""
    global player_x, player_y
    player_x += player_vx
    resolve_x()
    player_y += player_vy
    resolve_y()
    player_x = max(0, min(CAVE_PX_W - PLAYER_W, player_x))
    player_y = max(0, min(CAVE_PX_H - PLAYER_H, player_y))


def check_vine_contact(keys):
    """Check if player overlaps a vine. Grab it if pressing up/down."""
    global player_on_vine, player_vy
    left = player_x
    top = player_y
    right = player_x + PLAYER_W
    bottom = player_y + PLAYER_H
    touching_vine = False
    for gx, gy in get_overlapping_tiles(left, top, right, bottom):
        if 0 <= gx < CAVE_WIDTH and 0 <= gy < CAVE_HEIGHT:
            if cave[gy][gx] == CELL_VINE:
                touching_vine = True
                break
    if not touching_vine:
        player_on_vine = False
        return
    if player_on_vine:
        return
    # Auto-grab: catch vine when falling
    if not player_on_ground and player_vy > 0:
        player_on_vine = True
        player_vy = 0
        return
    # Manual grab: press up/down while touching vine
    wants_climb = (keys[pygame.K_UP] or keys[pygame.K_w]
                   or keys[pygame.K_DOWN] or keys[pygame.K_s])
    if wants_climb and not player_on_ground:
        player_on_vine = True
        player_vy = 0


def check_water_contact():
    """Check submersion depth. Handle drowning based on depth level.
    Depth 0 = dry, 1 = ankle, 2 = waist (drowning starts), 3 = deep (fast drown)."""
    global player_in_water, player_water_depth, breath, player_alive, player_drowned
    cx = int(player_x + PLAYER_W / 2) // CELL_SIZE
    cy = int(player_y + PLAYER_H / 2) // CELL_SIZE
    wlevel = 0
    if 0 <= cx < CAVE_WIDTH and 0 <= cy < CAVE_HEIGHT:
        wlevel = water[cy][cx]

    player_water_depth = wlevel
    player_in_water = wlevel >= 2   # waist-deep or more = "in water" for physics

    if wlevel >= 3:
        # Deep: fast drowning
        breath -= 2
    elif wlevel >= DROWN_THRESHOLD:
        # Waist: slow drowning
        breath -= 1
    else:
        # Dry or ankle: recover
        breath = min(BREATH_MAX, breath + BREATH_RECOVER)

    if breath <= 0:
        player_alive = False
        player_drowned = True


def check_fire_damage():
    """Kill player if overlapping a fire cell."""
    global player_alive
    if not player_alive:
        return
    left = player_x
    top = player_y
    right = player_x + PLAYER_W
    bottom = player_y + PLAYER_H
    for gx, gy in get_overlapping_tiles(left, top, right, bottom):
        if 0 <= gx < CAVE_WIDTH and 0 <= gy < CAVE_HEIGHT:
            if fire[gy][gx] > 0:
                player_alive = False
                return


def check_exit():
    """Phase-aware win condition.
    Phase 1: no win (must find macguffinium).
    Phase 2: win when player returns to entry/shop zone."""
    global won
    if game_phase == 1:
        return  # must collect macguffinium first
    cx = int(player_x + PLAYER_W / 2) // CELL_SIZE
    cy = int(player_y + PLAYER_H / 2) // CELL_SIZE
    sz = SHOP_ZONE
    if sz[0] <= cx <= sz[2] and sz[1] <= cy <= sz[3]:
        won = True


def physics_update():
    """Per-frame physics."""
    if not player_alive or won:
        return
    keys = pygame.key.get_pressed()
    apply_gravity()
    handle_movement_input(keys)
    move_and_collide()
    check_vine_contact(keys)
    check_water_contact()
    check_fire_damage()
    check_exit()

# =============================================================================
# ITEMS
# =============================================================================

def use_directional_item(item_type, dx, dy):
    """Use torch, machete, or vine seed in direction from player's grid position."""
    global aim_mode
    if item_type not in inventory or inventory[item_type] <= 0:
        return

    cx = int(player_x + PLAYER_W / 2) // CELL_SIZE
    cy = int(player_y + PLAYER_H / 2) // CELL_SIZE
    tx, ty = cx + dx, cy + dy

    if not (0 <= tx < CAVE_WIDTH and 0 <= ty < CAVE_HEIGHT):
        return

    used = False

    if item_type == ITEM_TORCH:
        if cave[ty][tx] == CELL_VINE and fire[ty][tx] == 0:
            # Vine ignition delay — smoulder for 5 seconds before catching fire
            already_fused = any(vx == tx and vy == ty for vx, vy, _ in vine_ignitions)
            if not already_fused:
                vine_ignitions.append([tx, ty, VINE_IGNITE_DELAY])
                used = True
        elif cave[ty][tx] in BURNABLE_CELLS:
            fire[ty][tx] = 3
            used = True
        elif cave[ty][tx] == CELL_AIR and fire[ty][tx] == 0:
            fire[ty][tx] = 2
            used = True

    elif item_type == ITEM_MACHETE:
        if cave[ty][tx] in BURNABLE_CELLS:
            cave[ty][tx] = CELL_AIR
            used = True

    elif item_type == ITEM_SEED:
        # Plant a vine seed on air (or existing vine to extend upward)
        if cave[ty][tx] == CELL_AIR and fire[ty][tx] == 0 and water[ty][tx] < 2:
            cave[ty][tx] = CELL_VINE
            growing_vines.append([tx, ty, SEED_GROW_HEIGHT])
            used = True
        elif cave[ty][tx] == CELL_VINE:
            # Boost an existing vine — add growth from its position
            growing_vines.append([tx, ty, SEED_GROW_HEIGHT])
            used = True

    elif item_type == ITEM_PICKAXE:
        if cave[ty][tx] == CELL_STONE:
            cave[ty][tx] = CELL_AIR
            used = True

    if used:
        inventory[item_type] -= 1
        if inventory[item_type] <= 0:
            del inventory[item_type]
            aim_mode = None
        else:
            aim_mode = None

# =============================================================================
# DRAWING
# =============================================================================

def draw_cave():
    """Render all cave cells with fire/water overlays.
    Water is drawn as partial-height fills from cell bottom (depth = fill height).
    Rows near the flood line get a subtle warning tint."""
    for y in range(CAVE_HEIGHT):
        sy = y * CELL_SIZE
        # Flood warning tint: rows 1-3 above flood line
        near_flood = 0 < (flood_line - y) <= 3

        for x in range(CAVE_WIDTH):
            sx = x * CELL_SIZE
            rect = (sx, sy, CELL_SIZE, CELL_SIZE)
            cell = cave[y][x]

            if cell == CELL_STONE:
                col = STONE_COLOR
                if near_flood:
                    # Subtle blue tint on stone near flood
                    col = (col[0] - 10, col[1] - 5, min(255, col[2] + 15))
                pygame.draw.rect(screen, col, rect)

            elif cell == CELL_WOOD:
                col = WOOD_COLOR
                # Heat tint from adjacent fire
                max_heat = 0
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < CAVE_WIDTH and 0 <= ny < CAVE_HEIGHT:
                        if fire[ny][nx] > 0:
                            max_heat = max(max_heat, fire[ny][nx])
                if max_heat > 0:
                    h = min(1.0, max_heat / 4.0)
                    r = min(255, int(col[0] + (255 - col[0]) * h))
                    g = max(30, int(col[1] - col[1] * h * 0.6))
                    b = max(15, int(col[2] - col[2] * h * 0.5))
                    col = (r, g, b)
                pygame.draw.rect(screen, col, rect)

            elif cell == CELL_SPRING:
                pygame.draw.rect(screen, SPRING_COLOR, rect)
                # Animated drip indicator
                drip_phase = (frame // 10 + x * 3 + y * 7) % 4
                drip_y = sy + CELL_SIZE - 6 + drip_phase
                pygame.draw.rect(screen, (80, 140, 200), (sx + CELL_SIZE // 2 - 2, drip_y, 4, 3))

            elif cell == CELL_VINE:
                base = SKY_TINT if y < 3 else AIR_COLOR
                pygame.draw.rect(screen, base, rect)
                # Water overlay behind vine
                if water[y][x] > 0 and fire[y][x] == 0:
                    level = min(water[y][x], WATER_MAX)
                    fill_h = int(CELL_SIZE * level / WATER_MAX)
                    wi = min(level - 1, 2)
                    pygame.draw.rect(screen, WATER_COLORS[wi],
                                     (sx, sy + CELL_SIZE - fill_h, CELL_SIZE, fill_h))
                # Vine on fire = fuse effect (bright orange vine)
                if fire[y][x] > 0:
                    fi = min(fire[y][x] - 1, 3)
                    fuse_col = FIRE_COLORS[fi]
                    vine_x = sx + CELL_SIZE // 2
                    pygame.draw.line(screen, fuse_col,
                                     (vine_x, sy), (vine_x, sy + CELL_SIZE), 4)
                    # Sparks — small bright dots
                    spark_y = sy + (frame * 3 + x * 7) % CELL_SIZE
                    pygame.draw.rect(screen, (255, 255, 200), (vine_x - 1, spark_y, 3, 2))
                else:
                    # Check for active ignition fuse (smouldering countdown)
                    ignition_timer = 0
                    for vi in vine_ignitions:
                        if vi[0] == x and vi[1] == y:
                            ignition_timer = vi[2]
                            break
                    vine_x = sx + CELL_SIZE // 2
                    if ignition_timer > 0:
                        # Smouldering vine — pulsing amber, darkens as timer runs down
                        progress = 1.0 - (ignition_timer / VINE_IGNITE_DELAY)
                        pulse = 0.5 + 0.5 * math.sin(frame * 0.15)
                        r = int(180 + 75 * progress)
                        g = int(140 - 100 * progress)
                        b = int(30 - 20 * progress)
                        smoulder = (min(255, int(r * (0.7 + 0.3 * pulse))),
                                    max(0, int(g * (0.7 + 0.3 * pulse))),
                                    max(0, b))
                        pygame.draw.line(screen, smoulder,
                                         (vine_x, sy), (vine_x, sy + CELL_SIZE), 4)
                        # Countdown number (seconds remaining, ceiling)
                        secs = math.ceil(ignition_timer / 60)
                        # Color: white → yellow → orange → red
                        t_col = (255, max(0, 255 - int(200 * progress)),
                                 max(0, 100 - int(100 * progress)))
                        num_surf = font_hud.render(str(secs), True, t_col)
                        num_rect = num_surf.get_rect(center=(sx + CELL_SIZE // 2,
                                                             sy + CELL_SIZE // 2))
                        screen.blit(num_surf, num_rect)
                        # Tiny smoke wisps
                        if frame % 8 < 4:
                            smoke_y = sy + (frame // 4 + x * 5) % 10
                            pygame.draw.rect(screen, (120, 110, 100),
                                             (vine_x + 2, smoke_y, 2, 2))
                    else:
                        # Normal healthy vine
                        pygame.draw.line(screen, VINE_COLOR,
                                         (vine_x, sy), (vine_x, sy + CELL_SIZE), 3)
                        pygame.draw.line(screen, (40, 110, 35),
                                         (vine_x, sy + 5), (vine_x - 4, sy + 8), 2)
                        pygame.draw.line(screen, (40, 110, 35),
                                         (vine_x, sy + 14), (vine_x + 4, sy + 11), 2)

            elif cell == CELL_MUSHROOM:
                base = SKY_TINT if y < 3 else AIR_COLOR
                pygame.draw.rect(screen, base, rect)
                # Water overlay behind mushroom
                if water[y][x] > 0 and fire[y][x] == 0:
                    level = min(water[y][x], WATER_MAX)
                    fill_h = int(CELL_SIZE * level / WATER_MAX)
                    wi = min(level - 1, 2)
                    pygame.draw.rect(screen, WATER_COLORS[wi],
                                     (sx, sy + CELL_SIZE - fill_h, CELL_SIZE, fill_h))
                # Check if this mushroom is charging (about to explode)
                is_charging = False
                charge_progress = 0
                for ch in mushroom_charges:
                    if ch[0] == x and ch[1] == y:
                        is_charging = True
                        charge_progress = 1.0 - (ch[2] / MUSHROOM_CHARGE_FRAMES)
                        break
                if is_charging:
                    # Pulsing scale animation — mushroom grows and turns orange-red
                    pulse = abs(math.sin(frame * 0.3)) * charge_progress
                    scale = 1.0 + pulse * 0.5
                    cap_w = int((CELL_SIZE - 6) * scale)
                    cap_h = int(8 * scale)
                    cap_x = sx + CELL_SIZE // 2 - cap_w // 2
                    cap_y = sy + CELL_SIZE // 2 - 4 - int(pulse * 3)
                    # Color shifts from purple to orange as charge builds
                    cr = int(190 + (255 - 190) * charge_progress)
                    cg = int(150 - 80 * charge_progress)
                    cb = int(210 - 160 * charge_progress)
                    cap_col = (min(255, cr), max(0, cg), max(0, cb))
                    pygame.draw.ellipse(screen, cap_col, (cap_x, cap_y, cap_w, cap_h))
                    # Warning flash
                    if int(frame * 0.3) % 2 == 0:
                        pygame.draw.rect(screen, (255, 200, 100), rect, 2)
                else:
                    # Normal mushroom
                    stem_x = sx + CELL_SIZE // 2 - 2
                    stem_top = sy + CELL_SIZE // 2
                    pygame.draw.rect(screen, MUSHROOM_STEM,
                                     (stem_x, stem_top, 4, CELL_SIZE // 2))
                    cap_x = sx + 3
                    cap_y = sy + CELL_SIZE // 2 - 4
                    pygame.draw.ellipse(screen, MUSHROOM_CAP,
                                        (cap_x, cap_y, CELL_SIZE - 6, 8))

            elif cell == CELL_GLOWCAP:
                base = SKY_TINT if y < 3 else AIR_COLOR
                pygame.draw.rect(screen, base, rect)
                # Water overlay behind glowcap
                if water[y][x] > 0:
                    level = min(water[y][x], WATER_MAX)
                    fill_h = int(CELL_SIZE * level / WATER_MAX)
                    wi = min(level - 1, 2)
                    pygame.draw.rect(screen, WATER_COLORS[wi],
                                     (sx, sy + CELL_SIZE - fill_h, CELL_SIZE, fill_h))
                is_wet = water[y][x] > 0
                if is_wet:
                    # GLOWING — draw halo first, then bright cap
                    glow_r = CELL_SIZE + 4
                    glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                    pulse = abs(math.sin(frame * 0.03 + x * 0.5)) * 0.3 + 0.5
                    alpha = int(40 * pulse)
                    pygame.draw.circle(glow_surf, (*GLOWCAP_GLOW, alpha),
                                       (glow_r, glow_r), glow_r)
                    screen.blit(glow_surf,
                                (sx + CELL_SIZE // 2 - glow_r,
                                 sy + CELL_SIZE // 2 - glow_r))
                    # Bright cap
                    cap_col = GLOWCAP_LIT
                    stem_col = (80, 180, 120)
                else:
                    cap_col = GLOWCAP_DIM
                    stem_col = (50, 60, 50)
                # Stem
                stem_x = sx + CELL_SIZE // 2 - 2
                stem_top = sy + CELL_SIZE // 2 + 2
                pygame.draw.rect(screen, stem_col,
                                 (stem_x, stem_top, 4, CELL_SIZE // 2 - 2))
                # Cap (rounder than mushroom)
                cap_x = sx + 4
                cap_y = sy + CELL_SIZE // 2 - 3
                pygame.draw.ellipse(screen, cap_col,
                                    (cap_x, cap_y, CELL_SIZE - 8, 7))
                # Tiny bright dot on wet glowcaps (bioluminescent spot)
                if is_wet:
                    dot_x = sx + CELL_SIZE // 2 - 1
                    dot_y = cap_y + 2
                    pygame.draw.rect(screen, (200, 255, 230), (dot_x, dot_y, 3, 2))

            else:
                # Air cell
                base = SKY_TINT if y < 3 else AIR_COLOR
                # Subtle flood warning tint
                if near_flood and fire[y][x] == 0 and water[y][x] == 0:
                    base = FLOOD_WARN_COLOR
                pygame.draw.rect(screen, base, rect)

                if fire[y][x] > 0:
                    fi = min(fire[y][x] - 1, 3)
                    pygame.draw.rect(screen, FIRE_COLORS[fi], rect)
                elif water[y][x] > 0:
                    # Water fills from bottom of cell — depth determines fill height
                    level = min(water[y][x], WATER_MAX)
                    # Depth 1 = 1/3 fill, 2 = 2/3 fill, 3 = full cell
                    fill_h = int(CELL_SIZE * level / WATER_MAX)
                    water_rect = (sx, sy + CELL_SIZE - fill_h, CELL_SIZE, fill_h)
                    wi = min(level - 1, 2)
                    pygame.draw.rect(screen, WATER_COLORS[wi], water_rect)

    # Draw flood line indicator (subtle dashed line)
    if 1 < flood_line < CAVE_HEIGHT:
        fy = flood_line * CELL_SIZE
        for x in range(0, CAVE_PX_W, 8):
            if (x // 8) % 2 == 0:
                pygame.draw.line(screen, (60, 80, 140), (x, fy), (x + 4, fy), 1)

    # Shop zone border (subtle gold outline around entry area)
    sz_x1, sz_y1, sz_x2, sz_y2 = SHOP_ZONE
    shop_rect = (sz_x1 * CELL_SIZE, sz_y1 * CELL_SIZE,
                 (sz_x2 - sz_x1 + 1) * CELL_SIZE, (sz_y2 - sz_y1 + 1) * CELL_SIZE)
    pulse = abs(math.sin(frame * 0.03)) * 0.3 + 0.2
    shop_border_col = (int(255 * pulse), int(215 * pulse), int(50 * pulse))
    pygame.draw.rect(screen, shop_border_col, shop_rect, 1)


def draw_exit():
    """Phase-aware objective marker.
    Phase 1: pulsing purple marker at macguffinium location.
    Phase 2: pulsing gold border on entry/shop zone."""
    pulse = abs(math.sin(frame * 0.05)) * 0.5 + 0.5
    if game_phase == 1:
        # Purple marker at macguffinium
        mx = macguffinium_gx * CELL_SIZE + CELL_SIZE // 2
        my = macguffinium_gy * CELL_SIZE + CELL_SIZE // 2
        r = int(CELL_SIZE * 0.4 * (0.7 + 0.3 * pulse))
        col = (int(200 * pulse), int(50 * pulse), int(255 * pulse))
        pygame.draw.circle(screen, col, (mx, my), r, 2)
    else:
        # Gold border on entry zone
        sz = SHOP_ZONE
        rect = (sz[0] * CELL_SIZE, sz[1] * CELL_SIZE,
                (sz[2] - sz[0] + 1) * CELL_SIZE, (sz[3] - sz[1] + 1) * CELL_SIZE)
        border_col = (int(255 * pulse), int(215 * pulse), 0)
        pygame.draw.rect(screen, border_col, rect, 3)


def draw_shop():
    """Draw shop overlay when player is in the shop zone."""
    if not shop_open or not player_alive or won:
        return
    # Semi-transparent panel
    panel_w, panel_h = 220, 160
    panel_x = CAVE_PX_W // 2 - panel_w // 2
    panel_y = 10
    panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel_surf.fill((20, 15, 10, 200))
    screen.blit(panel_surf, (panel_x, panel_y))
    # Title
    title = font_hud.render("SHOP", True, GOLD_COLOR)
    screen.blit(title, (panel_x + panel_w // 2 - title.get_width() // 2, panel_y + 6))
    # Gold display
    gold_txt = font_hud.render(f"Gold: {gold_count}", True, GOLD_COLOR)
    screen.blit(gold_txt, (panel_x + panel_w // 2 - gold_txt.get_width() // 2, panel_y + 22))
    # Items
    for i, si in enumerate(SHOP_ITEMS):
        y = panel_y + 42 + i * 22
        can_buy = gold_count >= si['cost']
        col = (200, 200, 200) if can_buy else (80, 80, 80)
        label = f"{i + 1}) {si['label']}  [{si['cost']}g]"
        surf = font_hud.render(label, True, col)
        screen.blit(surf, (panel_x + 10, y))


def draw_pickups():
    """Draw diamond shapes for items on the ground."""
    ds = CELL_SIZE // 3
    for y in range(CAVE_HEIGHT):
        for x in range(CAVE_WIDTH):
            if pickups[y][x] is None:
                continue
            item = pickups[y][x]
            if item == ITEM_GOLD:
                # Gold: smaller yellow diamond
                gs = CELL_SIZE // 4
                cx = x * CELL_SIZE + CELL_SIZE // 2
                cy = y * CELL_SIZE + CELL_SIZE // 2
                pts = [(cx, cy - gs), (cx + gs, cy), (cx, cy + gs), (cx - gs, cy)]
                pygame.draw.polygon(screen, GOLD_COLOR, pts)
                pygame.draw.polygon(screen, (255, 255, 200), pts, 1)
                continue
            if item == ITEM_MACGUFFINIUM:
                # Large pulsing purple circle
                cx = x * CELL_SIZE + CELL_SIZE // 2
                cy = y * CELL_SIZE + CELL_SIZE // 2
                pulse = abs(math.sin(frame * 0.06)) * 0.3 + 0.7
                r = int(CELL_SIZE * 0.4 * pulse)
                pygame.draw.circle(screen, MACGUFFINIUM_COLOR, (cx, cy), r)
                pygame.draw.circle(screen, (255, 200, 255), (cx, cy), r, 2)
                continue
            color = ITEM_DEFS.get(item, {}).get('color', (255, 255, 255))
            cx = x * CELL_SIZE + CELL_SIZE // 2
            cy = y * CELL_SIZE + CELL_SIZE // 2
            points = [(cx, cy - ds), (cx + ds, cy), (cx, cy + ds), (cx - ds, cy)]
            pygame.draw.polygon(screen, color, points)
            pygame.draw.polygon(screen, (255, 255, 255), points, 1)


def draw_player():
    """Draw player. Color shifts based on water depth."""
    if not player_alive:
        color = PLAYER_DROWN_COLOR if player_drowned else (PLAYER_FELL_COLOR if player_fell else PLAYER_DEAD_COLOR)
    else:
        if player_water_depth >= 3:
            color = (0, 150, 180)    # deep water — blue-green
        elif player_water_depth >= 2:
            color = (0, 180, 160)    # waist water — teal
        elif player_water_depth >= 1:
            color = (0, 210, 130)    # ankle water — slight blue shift
        elif player_on_vine:
            color = (0, 200, 140)
        else:
            color = PLAYER_COLOR

    px = int(player_x)
    py = int(player_y)
    pygame.draw.rect(screen, color, (px, py, PLAYER_W, PLAYER_H))
    # Eye indicator
    eye_y = py + 4
    eye_x = px + PLAYER_W - 5 if player_vx >= 0 else px + 2
    pygame.draw.rect(screen, (255, 255, 255), (eye_x, eye_y, 3, 3))


def draw_aim_indicator():
    """Highlight cells the player can target with current item."""
    if aim_mode is None:
        return
    color = ITEM_DEFS.get(aim_mode, {}).get('color', (255, 255, 255))
    cx = int(player_x + PLAYER_W / 2) // CELL_SIZE
    cy = int(player_y + PLAYER_H / 2) // CELL_SIZE
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        tx, ty = cx + dx, cy + dy
        if 0 <= tx < CAVE_WIDTH and 0 <= ty < CAVE_HEIGHT:
            valid = False
            if aim_mode == ITEM_TORCH:
                valid = cave[ty][tx] in BURNABLE_CELLS or cave[ty][tx] == CELL_AIR
            elif aim_mode == ITEM_MACHETE:
                valid = cave[ty][tx] in BURNABLE_CELLS
            elif aim_mode == ITEM_SEED:
                valid = (cave[ty][tx] == CELL_AIR and fire[ty][tx] == 0
                         and water[ty][tx] < 2) or cave[ty][tx] == CELL_VINE
            elif aim_mode == ITEM_PICKAXE:
                valid = cave[ty][tx] == CELL_STONE
            if valid:
                rect = (tx * CELL_SIZE, ty * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                pygame.draw.rect(screen, color, rect, 2)


def draw_breath_bar():
    """Floating breath bar above player when drowning."""
    if not player_alive or breath >= BREATH_MAX or player_water_depth < DROWN_THRESHOLD:
        return
    bar_w = 20
    bar_h = 4
    bar_x = int(player_x) + (PLAYER_W - bar_w) // 2
    bar_y = int(player_y) - 8
    ratio = max(0, breath / BREATH_MAX)
    fill_w = int(bar_w * ratio)
    pygame.draw.rect(screen, (60, 0, 0), (bar_x, bar_y, bar_w, bar_h))
    r = int(255 * (1 - ratio))
    g = int(255 * ratio)
    pygame.draw.rect(screen, (r, g, 0), (bar_x, bar_y, fill_w, bar_h))


def draw_hud():
    """Bottom HUD bar with items, status, and flood info."""
    hud_y = CAVE_PX_H
    pygame.draw.rect(screen, HUD_BG, (0, hud_y, CAVE_PX_W, HUD_HEIGHT))

    # Items
    ix = 10
    for item_type in ITEM_ORDER:
        if item_type in inventory:
            uses = inventory[item_type]
            name = ITEM_DEFS[item_type]['name']
            color = ITEM_DEFS[item_type]['color']
            if aim_mode == item_type:
                label = f"[{name}: {uses}]"
                txt_col = color
            else:
                label = f" {name}: {uses} "
                txt_col = (150, 150, 170)
            surf = font_hud.render(label, True, txt_col)
            screen.blit(surf, (ix, hud_y + 10))
            ix += surf.get_width() + 12

    # Gold count
    if gold_count > 0:
        gold_surf = font_hud.render(f"G:{gold_count}", True, GOLD_COLOR)
        screen.blit(gold_surf, (ix, hud_y + 10))
        ix += gold_surf.get_width() + 12

    # Phase indicator
    if game_phase == 1:
        phase_surf = font_hud.render("DESCEND", True, MACGUFFINIUM_COLOR)
    else:
        phase_surf = font_hud.render("ASCEND!", True, GOLD_COLOR)
    screen.blit(phase_surf, (ix, hud_y + 10))

    # Flood level indicator
    flood_pct = max(0, 100 - int((flood_line / CAVE_HEIGHT) * 100))
    flood_col = (80, 120, 200)
    if flood_pct > 60:
        flood_col = (200, 100, 60)  # orange warning
    elif flood_pct > 40:
        flood_col = (160, 140, 80)  # yellow caution
    flood_surf = font_hud.render(f"FLOOD {flood_pct}%", True, flood_col)
    screen.blit(flood_surf, (CAVE_PX_W - flood_surf.get_width() - 120, hud_y + 10))

    # Status indicators
    status_parts = []
    if player_on_vine:
        status_parts.append(("VINE", VINE_COLOR))
    if player_water_depth >= 3:
        status_parts.append(("DEEP", (50, 100, 185)))
    elif player_water_depth >= 2:
        status_parts.append(("WAIST", (90, 140, 210)))
    elif player_water_depth >= 1:
        status_parts.append(("ANKLE", (130, 170, 230)))
    if aim_mode:
        status_parts.append(("AIM", ITEM_DEFS[aim_mode]['color']))

    sx = CAVE_PX_W - 10
    for label, col in reversed(status_parts):
        surf = font_hud.render(label, True, col)
        sx -= surf.get_width()
        screen.blit(surf, (sx, hud_y + 10))
        sx -= 10

    # Win/death
    if won:
        surf = font_hud.render("ESCAPED WITH MACGUFFINIUM!", True, MACGUFFINIUM_COLOR)
        screen.blit(surf, (CAVE_PX_W // 2 - surf.get_width() // 2, hud_y + 10))
    elif not player_alive:
        if player_drowned:
            msg, col = "DROWNED!", PLAYER_DROWN_COLOR
        elif player_fell:
            msg, col = "FELL!", PLAYER_FELL_COLOR
        else:
            msg, col = "BURNED!", PLAYER_DEAD_COLOR
        surf = font_hud.render(msg + "  [R] Restart", True, col)
        screen.blit(surf, (CAVE_PX_W // 2 - surf.get_width() // 2, hud_y + 10))


def draw_messages():
    """Large overlay messages for death/win."""
    if won:
        surf = font_big.render("ESCAPED WITH MACGUFFINIUM!", True, MACGUFFINIUM_COLOR)
        screen.blit(surf, (CAVE_PX_W // 2 - surf.get_width() // 2,
                           CAVE_PX_H // 2 - 30))
        sub = font_msg.render("The Macguffinium is yours! [R] Again", True, (180, 180, 200))
        screen.blit(sub, (CAVE_PX_W // 2 - sub.get_width() // 2,
                          CAVE_PX_H // 2 + 10))
    elif not player_alive:
        if player_drowned:
            msg, col = "DROWNED", PLAYER_DROWN_COLOR
        elif player_fell:
            msg, col = "FELL", PLAYER_FELL_COLOR
        else:
            msg, col = "BURNED", PLAYER_DEAD_COLOR
        surf = font_big.render(msg, True, col)
        screen.blit(surf, (CAVE_PX_W // 2 - surf.get_width() // 2,
                           CAVE_PX_H // 2 - 30))
        sub = font_msg.render("Press R to restart", True, (180, 180, 200))
        screen.blit(sub, (CAVE_PX_W // 2 - sub.get_width() // 2,
                          CAVE_PX_H // 2 + 10))


def draw_sidebar():
    """Right sidebar with tuning parameters."""
    sx = CAVE_PX_W
    pygame.draw.rect(screen, SIDEBAR_BG, (sx, 0, SIDEBAR_W, WINDOW_H))

    title = font_hud.render("TUNING  [/]  -/=", True, (120, 130, 160))
    screen.blit(title, (sx + 8, 8))

    py_offset = 30
    for i, key in enumerate(tuning_keys):
        t = tuning[key]
        selected = (i == editor_sel)
        row_y = py_offset + i * 18
        if selected:
            pygame.draw.rect(screen, (35, 35, 55),
                             (sx + 2, row_y - 1, SIDEBAR_W - 4, 17))
        label_col = (200, 200, 220) if selected else (100, 100, 120)
        label_surf = font_ed.render(t['label'], True, label_col)
        screen.blit(label_surf, (sx + 8, row_y))
        fmt = t['fmt']
        val_str = f"{t['val']:{fmt}}"
        val_col = (255, 220, 100) if selected else (140, 140, 160)
        val_surf = font_ed.render(val_str, True, val_col)
        screen.blit(val_surf, (sx + SIDEBAR_W - 50, row_y))
        if selected:
            range_str = f"[{t['min']:{fmt}} .. {t['max']:{fmt}}]"
            range_surf = font_tiny.render(range_str, True, (80, 80, 100))
            screen.blit(range_surf, (sx + 8, row_y + 12))
            py_offset += 14

    help_y = WINDOW_H - 120
    helps = [
        ("Arrow/WASD", "Move / Jump"),
        ("Space", "Jump"),
        ("T / M", "Torch / Machete aim"),
        ("R", "Restart (when dead)"),
        ("P", "Pause"),
        ("ESC", "Cancel aim"),
    ]
    for i, (key, desc) in enumerate(helps):
        y = help_y + i * 14
        k_surf = font_tiny.render(key, True, (130, 130, 150))
        d_surf = font_tiny.render(desc, True, (80, 80, 100))
        screen.blit(k_surf, (sx + 8, y))
        screen.blit(d_surf, (sx + 80, y))

# =============================================================================
# SAVE / LOAD
# =============================================================================

def save_cave(filename=None):
    """Save current cave state as JSON.
    Saves terrain, pickups, exit position, seed, and tuning values."""
    os.makedirs(SAVE_DIR, exist_ok=True)
    if filename is None:
        filename = f"cave_{current_seed}.json"
    filepath = os.path.join(SAVE_DIR, filename)

    # Collect pickup data
    pickup_list = []
    for y in range(CAVE_HEIGHT):
        for x in range(CAVE_WIDTH):
            if pickups[y][x] is not None:
                pickup_list.append([x, y, pickups[y][x]])

    # Collect tuning values
    tuning_snapshot = {k: t['val'] for k, t in tuning.items()}

    data = {
        'version': 1,
        'seed': current_seed,
        'archetype': current_archetype,
        'cave_width': CAVE_WIDTH,
        'cave_height': CAVE_HEIGHT,
        'cave': [row[:] for row in cave],
        'exit': [exit_gx, exit_gy],
        'pickups': pickup_list,
        'tuning': tuning_snapshot,
    }
    with open(filepath, 'w') as f:
        json.dump(data, f, separators=(',', ':'))
    return filepath


def load_cave(filepath):
    """Load cave state from JSON file.
    Restores terrain, pickups, exit, and tuning. Resets player/sim state."""
    global cave, pickups, exit_gx, exit_gy, current_seed, current_archetype
    global player_x, player_y, player_vx, player_vy
    global player_on_ground, player_on_vine, player_in_water, player_water_depth
    global player_alive, player_drowned, player_fell, breath, won
    global inventory, aim_mode, frame, sim_ticks
    global flood_line, flood_timer, mushroom_charges, growing_vines, vine_ignitions
    global gold_count, shop_open, BREATH_MAX
    global game_phase, has_macguffinium, macguffinium_gx, macguffinium_gy

    with open(filepath, 'r') as f:
        data = json.load(f)

    current_seed = data.get('seed', 0)
    current_archetype = data.get('archetype', None)

    # Restore cave grid
    for y in range(min(CAVE_HEIGHT, len(data['cave']))):
        for x in range(min(CAVE_WIDTH, len(data['cave'][y]))):
            cave[y][x] = data['cave'][y][x]

    # Restore exit
    exit_gx, exit_gy = data['exit']

    # Reset fire/water
    fire[:]  = [[0] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]
    water[:] = [[0] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]

    # Restore pickups
    pickups[:] = [[None] * CAVE_WIDTH for _ in range(CAVE_HEIGHT)]
    for px, py, item in data.get('pickups', []):
        pickups[py][px] = item

    # Restore tuning
    for k, v in data.get('tuning', {}).items():
        if k in tuning:
            tuning[k]['val'] = v

    # Reset player state
    mushroom_charges = []
    growing_vines = []
    vine_ignitions = []
    player_x = 2.0 * CELL_SIZE + (CELL_SIZE - PLAYER_W) / 2
    player_y = 3.0 * CELL_SIZE - PLAYER_H
    player_vx = 0.0
    player_vy = 0.0
    player_on_ground = False
    player_on_vine = False
    player_in_water = False
    player_water_depth = 0
    player_alive = True
    player_drowned = False
    player_fell = False
    BREATH_MAX = BREATH_MAX_DEFAULT
    breath = BREATH_MAX
    won = False
    gold_count = 0
    shop_open = False
    game_phase = 1
    has_macguffinium = False
    macguffinium_gx = 0
    macguffinium_gy = 0
    inventory = {ITEM_TORCH: 3}
    aim_mode = None
    frame = 0
    sim_ticks = 0
    flood_line = CAVE_HEIGHT
    flood_timer = 0
    return True


def load_terrain_only(filepath):
    """Load ONLY terrain from JSON, then re-randomize features.
    This lets you curate a cave skeleton and get fresh bio-content each play."""
    global current_seed, current_archetype

    with open(filepath, 'r') as f:
        data = json.load(f)

    current_seed = data.get('seed', 0)
    current_archetype = data.get('archetype', None)

    # Restore cave grid — but only stone, wood, spring, air
    for y in range(min(CAVE_HEIGHT, len(data['cave']))):
        for x in range(min(CAVE_WIDTH, len(data['cave'][y]))):
            cell = data['cave'][y][x]
            if cell in (CELL_STONE, CELL_WOOD, CELL_SPRING, CELL_AIR):
                cave[y][x] = cell
            else:
                cave[y][x] = CELL_AIR  # strip vines/mushrooms/glowcaps

    # Re-randomize biological content using archetype params
    p = get_gen_params(current_archetype)
    place_vines(p)
    place_mushrooms(p)
    place_glowcaps(p)
    place_pickups(p)


def list_saved_caves():
    """Return list of .json files in the save directory."""
    if not os.path.isdir(SAVE_DIR):
        return []
    files = [f for f in os.listdir(SAVE_DIR) if f.endswith('.json')]
    files.sort()
    return files


# =============================================================================
# EDITOR DRAWING
# =============================================================================

def draw_edit_overlay():
    """Draw editor overlay — grid lines, cursor highlight, palette."""
    if not edit_mode:
        return

    # Semi-transparent grid lines
    for x in range(0, CAVE_PX_W + 1, CELL_SIZE):
        pygame.draw.line(screen, (50, 50, 70), (x, 0), (x, CAVE_PX_H), 1)
    for y in range(0, CAVE_PX_H + 1, CELL_SIZE):
        pygame.draw.line(screen, (50, 50, 70), (0, y), (CAVE_PX_W, y), 1)

    # Mouse cursor highlight
    mx, my = pygame.mouse.get_pos()
    if 0 <= mx < CAVE_PX_W and 0 <= my < CAVE_PX_H:
        gx = mx // CELL_SIZE
        gy = my // CELL_SIZE
        rect = (gx * CELL_SIZE, gy * CELL_SIZE, CELL_SIZE, CELL_SIZE)
        if edit_layer == 'cell':
            # Show what cell type will be painted
            _, name, col = EDIT_PALETTE[edit_brush]
            pygame.draw.rect(screen, col, rect, 3)
        elif edit_layer == 'pickup':
            pygame.draw.rect(screen, (255, 180, 50), rect, 3)
        elif edit_layer == 'exit':
            pygame.draw.rect(screen, EXIT_COLOR, rect, 3)

    # "EDIT MODE" indicator
    edit_surf = font_big.render("EDIT", True, (255, 200, 100))
    screen.blit(edit_surf, (CAVE_PX_W // 2 - edit_surf.get_width() // 2, 4))


def draw_edit_sidebar():
    """Draw editor palette and controls in sidebar (replaces tuning when editing)."""
    sx = CAVE_PX_W
    pygame.draw.rect(screen, SIDEBAR_BG, (sx, 0, SIDEBAR_W, WINDOW_H))

    # Title
    title = font_hud.render("EDITOR", True, (255, 200, 100))
    screen.blit(title, (sx + 8, 8))

    # Seed + archetype display
    seed_surf = font_ed.render(f"Seed: {current_seed}", True, (160, 160, 180))
    screen.blit(seed_surf, (sx + 8, 28))
    if current_archetype:
        arch_surf = font_ed.render(f"Type: {current_archetype}", True, (100, 140, 170))
        screen.blit(arch_surf, (sx + 8, 40))

    # Layer selector
    layer_y = 48
    layer_surf = font_ed.render(f"Layer: {edit_layer.upper()}", True, (180, 180, 200))
    screen.blit(layer_surf, (sx + 8, layer_y))
    tab_hint = font_tiny.render("TAB to switch", True, (80, 80, 100))
    screen.blit(tab_hint, (sx + 8, layer_y + 14))

    # Cell palette (when in cell layer)
    if edit_layer == 'cell':
        pal_y = 80
        pal_surf = font_ed.render("Palette (1-7 or scroll):", True, (130, 130, 150))
        screen.blit(pal_surf, (sx + 8, pal_y))
        for i, (cell_type, name, color) in enumerate(EDIT_PALETTE):
            row_y = pal_y + 16 + i * 18
            selected = (i == edit_brush)
            if selected:
                pygame.draw.rect(screen, (45, 40, 55),
                                 (sx + 2, row_y - 1, SIDEBAR_W - 4, 17))
            # Color swatch
            pygame.draw.rect(screen, color, (sx + 8, row_y + 2, 12, 12))
            pygame.draw.rect(screen, (100, 100, 120), (sx + 8, row_y + 2, 12, 12), 1)
            # Name
            name_col = (220, 220, 240) if selected else (120, 120, 140)
            name_surf = font_ed.render(f"{i+1}. {name}", True, name_col)
            screen.blit(name_surf, (sx + 26, row_y))

    elif edit_layer == 'pickup':
        pal_y = 80
        pal_surf = font_ed.render("Click: toggle torch", True, (130, 130, 150))
        screen.blit(pal_surf, (sx + 8, pal_y))
        pal_surf2 = font_ed.render("Right-click: machete", True, (130, 130, 150))
        screen.blit(pal_surf2, (sx + 8, pal_y + 16))
        pal_surf3 = font_ed.render("Shift+click: remove", True, (130, 130, 150))
        screen.blit(pal_surf3, (sx + 8, pal_y + 32))

    elif edit_layer == 'exit':
        pal_y = 80
        pal_surf = font_ed.render("Click to move exit", True, (130, 130, 150))
        screen.blit(pal_surf, (sx + 8, pal_y))

    # Controls help
    help_y = WINDOW_H - 160
    helps = [
        ("E", "Exit edit mode"),
        ("1-7", "Select cell type"),
        ("Scroll", "Change brush"),
        ("L-Click", "Paint cell"),
        ("R-Click", "Erase (air)"),
        ("TAB", "Switch layer"),
        ("Ctrl+S", "Save cave"),
        ("Ctrl+L", "Load cave"),
        ("Ctrl+N", "New random"),
        ("Ctrl+R", "Regen same seed"),
        ("Ctrl+A", "Cycle archetype"),
    ]
    for i, (key, desc) in enumerate(helps):
        y = help_y + i * 14
        k_surf = font_tiny.render(key, True, (130, 130, 150))
        d_surf = font_tiny.render(desc, True, (80, 80, 100))
        screen.blit(k_surf, (sx + 8, y))
        screen.blit(d_surf, (sx + 80, y))


def handle_edit_click(mx, my, button, shift_held):
    """Handle mouse click in edit mode."""
    global edit_brush, exit_gx, exit_gy

    if mx < 0 or mx >= CAVE_PX_W or my < 0 or my >= CAVE_PX_H:
        return

    gx = mx // CELL_SIZE
    gy = my // CELL_SIZE

    if edit_layer == 'cell':
        if button == 1:  # left click — paint
            cell_type, _, _ = EDIT_PALETTE[edit_brush]
            cave[gy][gx] = cell_type
            # Clear fire/water on painted cell
            fire[gy][gx] = 0
            water[gy][gx] = 0
        elif button == 3:  # right click — erase to air
            cave[gy][gx] = CELL_AIR
            fire[gy][gx] = 0
            water[gy][gx] = 0

    elif edit_layer == 'pickup':
        if shift_held:
            pickups[gy][gx] = None
        elif button == 1:
            pickups[gy][gx] = ITEM_TORCH if pickups[gy][gx] != ITEM_TORCH else None
        elif button == 3:
            pickups[gy][gx] = ITEM_MACHETE if pickups[gy][gx] != ITEM_MACHETE else None

    elif edit_layer == 'exit':
        if button == 1:
            exit_gx = gx
            exit_gy = gy


# =============================================================================
# MAIN LOOP
# =============================================================================

init_level()
running = True
paused = False
status_message = ""       # temporary status text (e.g. "Saved!", "Loaded!")
status_timer = 0          # frames remaining for status message

# Seed input mode — for typing a seed number
seed_input_mode = False
seed_input_text = ""

while running:
    mods = pygame.key.get_mods()
    ctrl_held = mods & pygame.KMOD_CTRL or mods & pygame.KMOD_META
    shift_held = mods & pygame.KMOD_SHIFT

    # ---- EVENT HANDLING ----
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        # --- Seed input mode (typing a number) ---
        elif seed_input_mode:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    # Accept seed
                    try:
                        seed_val = int(seed_input_text) if seed_input_text else None
                        init_level(seed=seed_val)
                        status_message = f"Seed {current_seed}"
                        status_timer = 180
                    except ValueError:
                        status_message = "Invalid seed"
                        status_timer = 120
                    seed_input_mode = False
                    seed_input_text = ""
                elif event.key == pygame.K_ESCAPE:
                    seed_input_mode = False
                    seed_input_text = ""
                elif event.key == pygame.K_BACKSPACE:
                    seed_input_text = seed_input_text[:-1]
                elif event.unicode.isdigit():
                    seed_input_text += event.unicode
            continue

        # --- Mouse events (edit mode) ---
        elif event.type == pygame.MOUSEBUTTONDOWN and edit_mode:
            if event.button in (1, 3):   # left or right click
                handle_edit_click(event.pos[0], event.pos[1], event.button, shift_held)
            elif event.button == 4:      # scroll up
                edit_brush = (edit_brush - 1) % len(EDIT_PALETTE)
            elif event.button == 5:      # scroll down
                edit_brush = (edit_brush + 1) % len(EDIT_PALETTE)

        elif event.type == pygame.KEYDOWN:
            key = event.key

            # --- Toggle edit mode (E) ---
            if key == pygame.K_e and not seed_input_mode:
                edit_mode = not edit_mode
                if edit_mode:
                    paused = True
                    status_message = "Edit mode ON"
                    status_timer = 120
                else:
                    status_message = "Edit mode OFF"
                    status_timer = 120

            # --- Ctrl shortcuts (work in both modes) ---
            elif ctrl_held and key == pygame.K_s:
                fp = save_cave()
                status_message = f"Saved: {os.path.basename(fp)}"
                status_timer = 180

            elif ctrl_held and key == pygame.K_l:
                files = list_saved_caves()
                if files:
                    # Load most recent
                    fp = os.path.join(SAVE_DIR, files[-1])
                    load_cave(fp)
                    status_message = f"Loaded: {files[-1]}"
                    status_timer = 180
                else:
                    status_message = "No saved caves"
                    status_timer = 120

            elif ctrl_held and key == pygame.K_n:
                init_level()
                status_message = f"New: {current_archetype} #{current_seed}"
                status_timer = 180

            elif ctrl_held and key == pygame.K_r:
                init_level(seed=current_seed, archetype=current_archetype)
                status_message = f"Regen seed: {current_seed}"
                status_timer = 180

            elif ctrl_held and key == pygame.K_a:
                # Cycle forced archetype
                if forced_archetype is None:
                    forced_archetype = ARCHETYPE_NAMES[0]
                else:
                    idx = ARCHETYPE_NAMES.index(forced_archetype)
                    idx = (idx + 1) % (len(ARCHETYPE_NAMES) + 1)
                    forced_archetype = ARCHETYPE_NAMES[idx] if idx < len(ARCHETYPE_NAMES) else None
                if forced_archetype:
                    status_message = f"Next: {forced_archetype}"
                else:
                    status_message = "Next: Random"
                status_timer = 180

            # --- Seed input (Ctrl+G = go to seed) ---
            elif ctrl_held and key == pygame.K_g:
                seed_input_mode = True
                seed_input_text = ""
                status_message = "Type seed + Enter"
                status_timer = 600

            # --- Edit mode keys ---
            elif edit_mode:
                if key == pygame.K_TAB:
                    edit_layer_idx = (edit_layer_idx + 1) % len(EDIT_LAYERS)
                    edit_layer = EDIT_LAYERS[edit_layer_idx]
                elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
                             pygame.K_5, pygame.K_6, pygame.K_7):
                    idx = key - pygame.K_1
                    if 0 <= idx < len(EDIT_PALETTE):
                        edit_brush = idx
                        edit_layer = 'cell'
                        edit_layer_idx = 0

            # --- Normal game keys (only when NOT in edit mode) ---
            elif not edit_mode:
                # Tuning sidebar
                if key == pygame.K_LEFTBRACKET:
                    editor_sel = (editor_sel - 1) % len(tuning_keys)
                elif key == pygame.K_RIGHTBRACKET:
                    editor_sel = (editor_sel + 1) % len(tuning_keys)
                elif key == pygame.K_MINUS:
                    k = tuning_keys[editor_sel]
                    t = tuning[k]
                    t['val'] = max(t['min'], round(t['val'] - t['step'], 4))
                elif key == pygame.K_EQUALS:
                    k = tuning_keys[editor_sel]
                    t = tuning[k]
                    t['val'] = min(t['max'], round(t['val'] + t['step'], 4))

                # Shop purchases (1-5 when in shop zone)
                elif shop_open and key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                    idx = key - pygame.K_1
                    si = SHOP_ITEMS[idx]
                    if gold_count >= si['cost']:
                        gold_count -= si['cost']
                        if si['item'] == 'breath':
                            BREATH_MAX += si['amount']
                            breath = min(BREATH_MAX, breath + si['amount'])
                        elif si['item'] in inventory:
                            inventory[si['item']] += si['amount']
                        else:
                            inventory[si['item']] = si['amount']
                        status_message = f"Bought {si['label']}!"
                        status_timer = 90

                # Items
                elif key == pygame.K_t:
                    if ITEM_TORCH in inventory:
                        aim_mode = ITEM_TORCH if aim_mode != ITEM_TORCH else None
                elif key == pygame.K_m:
                    if ITEM_MACHETE in inventory:
                        aim_mode = ITEM_MACHETE if aim_mode != ITEM_MACHETE else None
                elif key == pygame.K_v:
                    if ITEM_SEED in inventory:
                        aim_mode = ITEM_SEED if aim_mode != ITEM_SEED else None
                elif key == pygame.K_x:
                    if ITEM_PICKAXE in inventory:
                        aim_mode = ITEM_PICKAXE if aim_mode != ITEM_PICKAXE else None
                elif key == pygame.K_ESCAPE:
                    aim_mode = None

                # Directional item use (in aim mode)
                elif aim_mode:
                    if key in (pygame.K_UP, pygame.K_w):
                        use_directional_item(aim_mode, 0, -1)
                    elif key in (pygame.K_DOWN, pygame.K_s):
                        use_directional_item(aim_mode, 0, 1)
                    elif key in (pygame.K_LEFT, pygame.K_a):
                        use_directional_item(aim_mode, -1, 0)
                    elif key in (pygame.K_RIGHT, pygame.K_d):
                        use_directional_item(aim_mode, 1, 0)

                # Game controls
                elif key == pygame.K_r:
                    if not player_alive or won:
                        init_level()
                elif key == pygame.K_p:
                    paused = not paused

    # ---- Continuous mouse painting (hold to drag-paint) ----
    if edit_mode and pygame.mouse.get_pressed()[0]:
        mx, my = pygame.mouse.get_pos()
        if edit_layer == 'cell' and 0 <= mx < CAVE_PX_W and 0 <= my < CAVE_PX_H:
            gx = mx // CELL_SIZE
            gy = my // CELL_SIZE
            cell_type, _, _ = EDIT_PALETTE[edit_brush]
            cave[gy][gx] = cell_type
            fire[gy][gx] = 0
            water[gy][gx] = 0
    elif edit_mode and pygame.mouse.get_pressed()[2]:
        mx, my = pygame.mouse.get_pos()
        if edit_layer == 'cell' and 0 <= mx < CAVE_PX_W and 0 <= my < CAVE_PX_H:
            gx = mx // CELL_SIZE
            gy = my // CELL_SIZE
            cave[gy][gx] = CELL_AIR
            fire[gy][gx] = 0
            water[gy][gx] = 0

    # ---- UPDATE ----
    if not paused and not edit_mode:
        physics_update()
        tick_mushroom_charges()
        tick_vine_ignitions()
        frame += 1
        if frame % SIM_INTERVAL == 0:
            sim_tick()

        # Shop zone detection
        shop_open = False
        if player_alive and not won:
            pcx = int(player_x + PLAYER_W / 2) // CELL_SIZE
            pcy = int(player_y + PLAYER_H / 2) // CELL_SIZE
            sz = SHOP_ZONE
            if sz[0] <= pcx <= sz[2] and sz[1] <= pcy <= sz[3]:
                shop_open = True

        # Pickup collection
        if player_alive and not won:
            cx = int(player_x + PLAYER_W / 2) // CELL_SIZE
            cy = int(player_y + PLAYER_H / 2) // CELL_SIZE
            if 0 <= cx < CAVE_WIDTH and 0 <= cy < CAVE_HEIGHT:
                if pickups[cy][cx] is not None:
                    item = pickups[cy][cx]
                    if item == ITEM_GOLD:
                        gold_count += 1
                    elif item == ITEM_MACGUFFINIUM:
                        has_macguffinium = True
                        game_phase = 2
                        status_message = "GET BACK TO THE TOP!"
                        status_timer = 180
                    else:
                        if item in inventory:
                            inventory[item] += ITEM_DEFS[item]['uses']
                        else:
                            inventory[item] = ITEM_DEFS[item]['uses']
                    pickups[cy][cx] = None

    # Status message countdown
    if status_timer > 0:
        status_timer -= 1

    # ---- DRAW ----
    screen.fill(BG_COLOR)
    draw_cave()
    draw_exit()
    draw_pickups()
    if not edit_mode:
        draw_aim_indicator()
        draw_player()
        draw_breath_bar()
    draw_hud()
    if not edit_mode:
        draw_shop()
        draw_messages()

    # Editor overlays
    if edit_mode:
        draw_edit_overlay()
        draw_edit_sidebar()
    else:
        draw_sidebar()

    # Seed + archetype display in HUD (always visible)
    seed_col = (80, 80, 100) if not edit_mode else (160, 160, 180)
    seed_surf = font_tiny.render(f"SEED {current_seed}", True, seed_col)
    seed_x = CAVE_PX_W - seed_surf.get_width() - 10
    screen.blit(seed_surf, (seed_x, CAVE_PX_H + 2))
    if current_archetype:
        arch_surf = font_tiny.render(f"// {current_archetype}", True, (100, 130, 160))
        screen.blit(arch_surf, (seed_x - arch_surf.get_width() - 8, CAVE_PX_H + 2))

    # Seed input overlay
    if seed_input_mode:
        input_bg = pygame.Surface((200, 40), pygame.SRCALPHA)
        input_bg.fill((0, 0, 0, 180))
        screen.blit(input_bg, (CAVE_PX_W // 2 - 100, CAVE_PX_H // 2 - 20))
        prompt = font_msg.render(f"Seed: {seed_input_text}_", True, (255, 220, 100))
        screen.blit(prompt, (CAVE_PX_W // 2 - prompt.get_width() // 2,
                             CAVE_PX_H // 2 - 12))

    # Status message
    if status_timer > 0 and status_message:
        alpha = min(255, status_timer * 4)
        msg_surf = font_msg.render(status_message, True, (255, 220, 100))
        screen.blit(msg_surf, (CAVE_PX_W // 2 - msg_surf.get_width() // 2,
                               CAVE_PX_H - 30))

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
sys.exit()
