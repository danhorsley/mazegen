import pygame
import random
import sys
import math

# ================== SETTINGS ==================
CELL_SIZE = 20
MAZE_WIDTH = 30
MAZE_HEIGHT = 22

PATH_COLOR = (30, 40, 60)
WALL_STONE = (90, 90, 110)
WALL_WOOD  = (160, 100, 60)
PIPE_COLOR = (60, 80, 130)
FIRE_COLORS = [(255, 80, 0), (255, 120, 0), (255, 170, 0), (255, 255, 80)]
WATER_COLORS = [(200, 220, 255), (180, 210, 255), (160, 200, 255),
                (140, 190, 255), (120, 180, 255)]
REGROW_TINT = (180, 120, 80)
PLAYER_COLOR = (0, 255, 100)
PLAYER_DEAD_COLOR = (255, 0, 0)
PLAYER_DROWN_COLOR = (80, 80, 200)
GOAL_COLOR = (255, 215, 0)
BG_COLOR = (20, 20, 30)
HUD_BG = (15, 15, 25)

SAFE_RADIUS = 2

DROWN_THRESHOLD = 4
BREATH_MAX = 10
BREATH_RECOVER_RATE = 2

LIGHTNING_MIN_FRAMES = 300
LIGHTNING_MAX_FRAMES = 750
WATER_FLOW_INTERVAL = 3

# Game modes
MODE_TACTICAL = 'tactical'
MODE_CHAOS = 'chaos'

TACTICAL_LIGHTNING_MIN = 20
TACTICAL_LIGHTNING_MAX = 40

# ================== TUNING (editor-adjustable) ==================
tuning_keys = [
    'fire_spread', 'fire_spread_i',
    'decay_dry', 'decay_damp', 'decay_wet',
    'wood_burn', 'wood_burn_i',
    'seep_base',
    'flow_with', 'flow_perp', 'flow_against',
    'regrow_time',
    'regrow_chance',
]
tuning = {
    'fire_spread':   {'val': 0.10, 'min': 0.0, 'max': 0.50, 'step': 0.01, 'fmt': '.2f', 'label': 'Spread Base'},
    'fire_spread_i': {'val': 0.06, 'min': 0.0, 'max': 0.20, 'step': 0.01, 'fmt': '.2f', 'label': 'Spread /Int'},
    'decay_dry':     {'val': 0.08, 'min': 0.0, 'max': 0.50, 'step': 0.01, 'fmt': '.2f', 'label': 'Decay Dry'},
    'decay_damp':    {'val': 0.25, 'min': 0.0, 'max': 0.80, 'step': 0.01, 'fmt': '.2f', 'label': 'Decay Damp'},
    'decay_wet':     {'val': 0.40, 'min': 0.0, 'max': 1.00, 'step': 0.02, 'fmt': '.2f', 'label': 'Decay Wet'},
    'wood_burn':     {'val': 0.15, 'min': 0.0, 'max': 0.60, 'step': 0.01, 'fmt': '.2f', 'label': 'Wood Burn'},
    'wood_burn_i':   {'val': 0.10, 'min': 0.0, 'max': 0.30, 'step': 0.01, 'fmt': '.2f', 'label': 'WBurn /Int'},
    'seep_base':     {'val': 0.15, 'min': 0.0, 'max': 0.50, 'step': 0.01, 'fmt': '.2f', 'label': 'Seep Rate'},
    'flow_with':     {'val': 0.12, 'min': 0.0, 'max': 0.30, 'step': 0.01, 'fmt': '.2f', 'label': 'Flow With'},
    'flow_perp':     {'val': 0.04, 'min': 0.0, 'max': 0.20, 'step': 0.01, 'fmt': '.2f', 'label': 'Flow Perp'},
    'flow_against':  {'val': 0.01, 'min': 0.0, 'max': 0.10, 'step': 0.005,'fmt': '.3f', 'label': 'Flow Against'},
    'regrow_time':   {'val': 150,  'min': 30,  'max': 500,  'step': 10,   'fmt': '.0f', 'label': 'Regrow Cool'},
    'regrow_chance': {'val': 0.08, 'min': 0.01,'max': 0.50, 'step': 0.01, 'fmt': '.2f', 'label': 'Regrow Spread'},
}
def tv(k): return tuning[k]['val']

# ================== ITEM DEFINITIONS ==================
ITEM_MACHETE  = 'machete'
ITEM_TORCH    = 'torch'
ITEM_CLOAK    = 'cloak'
ITEM_AQUALUNG = 'aqualung'
ITEM_BUCKET   = 'bucket'
ITEM_COMPASS  = 'compass'

ITEM_DEFS = {
    ITEM_MACHETE:  {'uses': 5,  'passive': False, 'color': (200, 200, 210), 'name': 'Machete',    'key': 'm'},
    ITEM_TORCH:    {'uses': 3,  'passive': False, 'color': (255, 180, 50),  'name': 'Torch',      'key': 't'},
    ITEM_CLOAK:    {'uses': 5,  'passive': True,  'color': (255, 100, 50),  'name': 'Fire Cloak', 'key': None},
    ITEM_AQUALUNG: {'uses': 15, 'passive': True,  'color': (60, 180, 255),  'name': 'Aqualung',   'key': None},
    ITEM_BUCKET:   {'uses': 3,  'passive': False, 'color': (100, 200, 255), 'name': 'Bucket',     'key': 'b'},
    ITEM_COMPASS:  {'uses': 1,  'passive': False, 'color': (255, 255, 100), 'name': 'Compass',    'key': 'c'},
}

ITEM_ORDER = [ITEM_MACHETE, ITEM_TORCH, ITEM_CLOAK, ITEM_AQUALUNG, ITEM_BUCKET, ITEM_COMPASS]

UNLOCK_SCHEDULE = [
    (0, ITEM_TORCH),
    (1, ITEM_MACHETE),
    (2, ITEM_CLOAK),
    (3, ITEM_AQUALUNG),
    (4, ITEM_BUCKET),
    (5, ITEM_COMPASS),
]

STARTING_INVENTORY = {ITEM_TORCH: 1}

# ================== INIT ==================
pygame.init()
MAZE_PX_W = MAZE_WIDTH * CELL_SIZE
MAZE_PX_H = MAZE_HEIGHT * CELL_SIZE
HUD_HEIGHT = 36
SIDEBAR_W = 220
screen = pygame.display.set_mode((MAZE_PX_W + SIDEBAR_W, MAZE_PX_H + HUD_HEIGHT))
pygame.display.set_caption("Living Maze — Navigate the Chaos")
clock = pygame.time.Clock()
pygame.key.set_repeat(150, 80)

font_hud = pygame.font.SysFont(None, 20)
font_msg = pygame.font.SysFont(None, 36)
font_big = pygame.font.SysFont(None, 48)
font_tiny = pygame.font.SysFont(None, 14)
font_ed = pygame.font.SysFont("monospace", 14)

# ================== STATE ==================
maze   = [[0]*MAZE_WIDTH for _ in range(MAZE_HEIGHT)]
fire   = [[0]*MAZE_WIDTH for _ in range(MAZE_HEIGHT)]
water  = [[0]*MAZE_WIDTH for _ in range(MAZE_HEIGHT)]
regrow = [[0]*MAZE_WIDTH for _ in range(MAZE_HEIGHT)]
pickups = [[None]*MAZE_WIDTH for _ in range(MAZE_HEIGHT)]

player_x, player_y = 0, 0
player_alive = True
player_drowned = False
won = False
breath = BREATH_MAX
inventory = {}
aim_mode = None
compass_timer = 0
compass_path = []

# Floor system
current_floor = 1
floor_msg_timer = 0

# Water system
flow_direction = (0, 1)
pipe_cells = []

# Game mode
game_mode = MODE_TACTICAL
move_count = 0

# Meta-progression
total_wins = 0
just_unlocked = None
unlock_timer = 0

lightning_timer = 0

# Editor sidebar
editor_sel = 0

directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

# ================== HELPERS ==================
def get_unlocked_items():
    return [item for wins_needed, item in UNLOCK_SCHEDULE if total_wins >= wins_needed]

def in_safe_zone(x, y):
    if x <= SAFE_RADIUS and y <= SAFE_RADIUS:
        return True
    if x >= MAZE_WIDTH - 1 - SAFE_RADIUS and y >= MAZE_HEIGHT - 1 - SAFE_RADIUS:
        return True
    return False

PLAYER_EXCLUSION = 3

def near_player(x, y):
    return abs(x - player_x) <= PLAYER_EXCLUSION and abs(y - player_y) <= PLAYER_EXCLUSION

def find_path(sx, sy, gx, gy):
    """BFS shortest path through open cells."""
    from collections import deque
    visited = {(sx, sy): None}
    queue = deque([(sx, sy)])
    while queue:
        x, y = queue.popleft()
        if x == gx and y == gy:
            path = []
            pos = (gx, gy)
            while pos != (sx, sy):
                path.append(pos)
                pos = visited[pos]
            path.reverse()
            return path
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT and (nx, ny) not in visited:
                if maze[ny][nx] == 0:
                    visited[(nx, ny)] = (x, y)
                    queue.append((nx, ny))
    return []

def get_floor_params(floor):
    return {
        'num_fires': min(2 + floor - 1, 8),
        'wood_ratio': min(0.75 + (floor - 1) * 0.02, 0.90),
        'lightning_scale': max(0.4, 1.0 - (floor - 1) * 0.06),
        'seep_rate': min(0.35, tv('seep_base') + (floor - 1) * 0.02),
        'num_branches': 1 + (floor - 1) // 2,
    }

# ================== PIPE GENERATION ==================
def generate_pipes():
    global flow_direction, pipe_cells

    flow_direction = random.choice(directions)
    fdx, fdy = flow_direction
    pipe_cells = []
    pipe_set = set()
    params = get_floor_params(current_floor)

    if fdy > 0:
        sx, sy = random.randint(MAZE_WIDTH // 4, 3 * MAZE_WIDTH // 4), 1
    elif fdy < 0:
        sx, sy = random.randint(MAZE_WIDTH // 4, 3 * MAZE_WIDTH // 4), MAZE_HEIGHT - 2
    elif fdx > 0:
        sx, sy = 1, random.randint(MAZE_HEIGHT // 4, 3 * MAZE_HEIGHT // 4)
    else:
        sx, sy = MAZE_WIDTH - 2, random.randint(MAZE_HEIGHT // 4, 3 * MAZE_HEIGHT // 4)

    def find_wall_near(tx, ty):
        for r in range(6):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    nx, ny = tx + dx, ty + dy
                    if 1 <= nx < MAZE_WIDTH - 1 and 1 <= ny < MAZE_HEIGHT - 1:
                        if maze[ny][nx] in (1, 2) and not in_safe_zone(nx, ny):
                            return nx, ny
        return None, None

    def worm_walk(start_x, start_y, max_steps, bias_dx, bias_dy):
        x, y = start_x, start_y
        for _ in range(max_steps):
            if not (1 <= x < MAZE_WIDTH - 1 and 1 <= y < MAZE_HEIGHT - 1):
                break
            if in_safe_zone(x, y):
                break
            if maze[y][x] in (1, 2) and (x, y) not in pipe_set:
                pipe_set.add((x, y))
            candidates = []
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if not (1 <= nx < MAZE_WIDTH - 1 and 1 <= ny < MAZE_HEIGHT - 1):
                    continue
                if in_safe_zone(nx, ny):
                    continue
                if maze[ny][nx] not in (1, 2):
                    continue
                if (nx, ny) in pipe_set:
                    continue
                if (dx, dy) == (bias_dx, bias_dy):
                    candidates.extend([(nx, ny)] * 6)
                elif (dx, dy) == (-bias_dx, -bias_dy):
                    candidates.extend([(nx, ny)] * 1)
                else:
                    candidates.extend([(nx, ny)] * 3)
            if not candidates:
                break
            x, y = random.choice(candidates)

    sx, sy = find_wall_near(sx, sy)
    if sx is not None:
        trunk_length = max(MAZE_WIDTH, MAZE_HEIGHT) + 5
        worm_walk(sx, sy, trunk_length, fdx, fdy)

    num_branches = params['num_branches']
    for _ in range(num_branches):
        if not pipe_set:
            break
        bx, by = random.choice(list(pipe_set))
        if fdx == 0:
            bdx, bdy = random.choice([-1, 1]), 0
        else:
            bdx, bdy = 0, random.choice([-1, 1])
        bsx, bsy = bx + bdx, by + bdy
        if 1 <= bsx < MAZE_WIDTH - 1 and 1 <= bsy < MAZE_HEIGHT - 1:
            worm_walk(bsx, bsy, random.randint(3, 8), bdx, bdy)

    pipe_cells = list(pipe_set)
    for x, y in pipe_cells:
        maze[y][x] = 3

# ================== MAZE GENERATION ==================
def place_pickups():
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            pickups[y][x] = None
    available = get_unlocked_items()
    if not available:
        return
    total = random.randint(2, 3)
    for _ in range(total):
        item_type = random.choice(available)
        for _attempt in range(200):
            x = random.randint(1, MAZE_WIDTH - 2)
            y = random.randint(1, MAZE_HEIGHT - 2)
            if maze[y][x] != 0 or pickups[y][x] is not None:
                continue
            if in_safe_zone(x, y):
                continue
            pickups[y][x] = item_type
            break

def generate_maze(keep_inventory=False):
    global player_x, player_y, player_alive, player_drowned, won, breath
    global inventory, aim_mode, compass_timer

    params = get_floor_params(current_floor)

    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            maze[y][x] = 1
            fire[y][x] = 0
            water[y][x] = 0
            regrow[y][x] = 0
            pickups[y][x] = None

    stack = [(0, 0)]
    maze[0][0] = 0
    while stack:
        x, y = stack[-1]
        neighbors = []
        random.shuffle(directions)
        for dx, dy in directions:
            nx, ny = x + dx * 2, y + dy * 2
            if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT and maze[ny][nx] == 1:
                neighbors.append((nx, ny, dx, dy))
        if neighbors:
            nx, ny, dx, dy = neighbors[0]
            maze[y + dy][x + dx] = 0
            maze[ny][nx] = 0
            stack.append((nx, ny))
        else:
            stack.pop()

    maze[0][0] = 0
    maze[MAZE_HEIGHT - 1][MAZE_WIDTH - 1] = 0

    wood_ratio = params['wood_ratio']
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if maze[y][x] == 1:
                if x == 0 or x == MAZE_WIDTH - 1 or y == 0 or y == MAZE_HEIGHT - 1:
                    continue
                if in_safe_zone(x, y):
                    continue
                if random.random() < wood_ratio:
                    maze[y][x] = 2

    generate_pipes()

    for y in range(2):
        for x in range(2):
            maze[y][x] = 0
    for y in range(MAZE_HEIGHT - 2, MAZE_HEIGHT):
        for x in range(MAZE_WIDTH - 2, MAZE_WIDTH):
            maze[y][x] = 0

    for px, py in pipe_cells:
        for dx, dy in directions:
            nx, ny = px + dx, py + dy
            if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT and maze[ny][nx] == 0:
                water[ny][nx] = max(water[ny][nx], random.randint(2, 4))
                for dx2, dy2 in directions:
                    nnx, nny = nx + dx2, ny + dy2
                    if 0 <= nnx < MAZE_WIDTH and 0 <= nny < MAZE_HEIGHT:
                        if maze[nny][nnx] == 0 and water[nny][nnx] == 0:
                            water[nny][nnx] = random.randint(0, 2)

    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if in_safe_zone(x, y):
                water[y][x] = 0

    num_fires = params['num_fires']
    for _ in range(num_fires):
        for _attempt in range(100):
            fx = random.randint(SAFE_RADIUS + 1, MAZE_WIDTH - SAFE_RADIUS - 2)
            fy = random.randint(SAFE_RADIUS + 1, MAZE_HEIGHT - SAFE_RADIUS - 2)
            if maze[fy][fx] == 0 and water[fy][fx] <= 1:
                fire[fy][fx] = 1
                break

    place_pickups()

    player_x, player_y = 0, 0
    player_alive = True
    player_drowned = False
    won = False
    breath = BREATH_MAX
    if not keep_inventory:
        inventory.clear()
        for k, v in STARTING_INVENTORY.items():
            inventory[k] = v
    aim_mode = None
    compass_timer = 0
    reset_lightning_timer()

# ================== SIMULATION ==================
def count_fire_cells():
    return sum(1 for y in range(MAZE_HEIGHT) for x in range(MAZE_WIDTH) if fire[y][x] > 0)

def update_fire():
    new_fire = [row[:] for row in fire]
    fire_count = count_fire_cells()
    total_open = sum(1 for y in range(MAZE_HEIGHT) for x in range(MAZE_WIDTH) if maze[y][x] == 0)
    fire_ratio = fire_count / max(1, total_open)
    global_dampen = max(0.05, 1.0 - fire_ratio * 3.0)

    for y in range(1, MAZE_HEIGHT - 1):
        for x in range(1, MAZE_WIDTH - 1):
            if fire[y][x] == 0:
                continue
            intensity = fire[y][x]

            if water[y][x] > 0:
                new_fire[y][x] = max(0, intensity - water[y][x])
                continue

            base_spread = tv('fire_spread') + intensity * tv('fire_spread_i')
            spread_chance = base_spread * global_dampen

            # Wood burns — scales with intensity, no threshold
            if maze[y][x] == 2:
                burn_chance = tv('wood_burn') + intensity * tv('wood_burn_i')
                if random.random() < burn_chance:
                    maze[y][x] = 0
                    regrow[y][x] = int(tv('regrow_time'))

            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
                    if maze[ny][nx] in (0, 2):
                        # Fire on open path (embers) can only ignite wood, not more open air
                        if maze[y][x] == 0 and maze[ny][nx] == 0:
                            continue
                        if water[ny][nx] >= 3:
                            continue
                        if water[ny][nx] >= 1 and random.random() > 0.12:
                            continue
                        if random.random() < spread_chance:
                            spread_intensity = max(1, intensity - 1)
                            new_fire[ny][nx] = max(new_fire[ny][nx], spread_intensity)

            # Decay tied to nearby moisture
            nearby_water = 0
            for ddx, ddy in directions:
                wx, wy = x + ddx, y + ddy
                if 0 <= wx < MAZE_WIDTH and 0 <= wy < MAZE_HEIGHT:
                    nearby_water = max(nearby_water, water[wy][wx])

            if nearby_water >= 2:
                base_decay = tv('decay_wet')
            elif nearby_water >= 1:
                base_decay = tv('decay_damp')
            else:
                base_decay = tv('decay_dry')
            decay_chance = base_decay * (1.0 + intensity * 0.3)

            if maze[y][x] == 0 and random.random() < decay_chance:
                new_fire[y][x] = max(0, intensity - random.randint(1, 2))

    return new_fire

def update_water():
    new_water = [row[:] for row in water]
    fdx, fdy = flow_direction
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if water[y][x] > 0:
                if random.random() < 0.008:
                    new_water[y][x] -= 1
                if fire[y][x] > 0:
                    if random.random() < 0.3:
                        new_water[y][x] = max(0, water[y][x] - 1)
                is_drain = False
                if fdy > 0 and y >= MAZE_HEIGHT - 2:
                    is_drain = True
                elif fdy < 0 and y <= 1:
                    is_drain = True
                elif fdx > 0 and x >= MAZE_WIDTH - 2:
                    is_drain = True
                elif fdx < 0 and x <= 1:
                    is_drain = True
                if is_drain and random.random() < 0.15:
                    new_water[y][x] = max(0, new_water[y][x] - 1)
    return new_water

def flow_water():
    new_water = [row[:] for row in water]
    fdx, fdy = flow_direction
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if water[y][x] >= 2 and maze[y][x] == 0:
                for dx, dy in directions:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
                        if maze[ny][nx] == 0 and water[ny][nx] < water[y][x] - 1:
                            if (dx, dy) == (fdx, fdy):
                                chance = tv('flow_with')
                            elif (dx, dy) == (-fdx, -fdy):
                                chance = tv('flow_against')
                            else:
                                chance = tv('flow_perp')
                            if random.random() < chance:
                                new_water[ny][nx] = min(5, new_water[ny][nx] + 1)
    return new_water

def seep_from_pipes():
    params = get_floor_params(current_floor)
    rate = params['seep_rate']
    for px, py in pipe_cells:
        for dx, dy in directions:
            nx, ny = px + dx, py + dy
            if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
                if maze[ny][nx] == 0 and water[ny][nx] < 4:
                    if random.random() < rate:
                        water[ny][nx] = min(5, water[ny][nx] + 1)

def update_regrowth():
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if regrow[y][x] > 0:
                # Cooldown phase — count down, then become fertile (-1)
                regrow[y][x] -= 1
                if regrow[y][x] == 0:
                    regrow[y][x] = -1  # now fertile
            elif regrow[y][x] == -1:
                # Fertile phase — can regrow if adjacent to existing wood
                if maze[y][x] != 0 or fire[y][x] > 0:
                    regrow[y][x] = 0  # no longer eligible
                    continue
                # Safety buffer: don't regrow on or adjacent to player
                dx = abs(x - player_x)
                dy = abs(y - player_y)
                if dx <= 1 and dy <= 1:
                    continue
                # Check for adjacent wood to grow from
                has_neighbor_wood = False
                for ddx, ddy in directions:
                    nx, ny = x + ddx, y + ddy
                    if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
                        if maze[ny][nx] == 2:
                            has_neighbor_wood = True
                            break
                if has_neighbor_wood and random.random() < tv('regrow_chance'):
                    if pickups[y][x] is None:
                        maze[y][x] = 2
                        regrow[y][x] = 0

def reset_lightning_timer():
    global lightning_timer
    params = get_floor_params(current_floor)
    scale = params['lightning_scale']
    if game_mode == MODE_TACTICAL:
        lightning_timer = random.randint(
            max(5, int(TACTICAL_LIGHTNING_MIN * scale)),
            max(8, int(TACTICAL_LIGHTNING_MAX * scale)))
    else:
        lightning_timer = random.randint(
            max(30, int(LIGHTNING_MIN_FRAMES * scale)),
            max(60, int(LIGHTNING_MAX_FRAMES * scale)))

def try_lightning():
    global lightning_timer
    lightning_timer -= 1
    if lightning_timer <= 0:
        count = random.randint(1, 2)
        for _ in range(count):
            for _attempt in range(100):
                x = random.randint(1, MAZE_WIDTH - 2)
                y = random.randint(1, MAZE_HEIGHT - 2)
                if maze[y][x] == 0 and water[y][x] <= 1 and not near_player(x, y):
                    fire[y][x] = random.randint(2, 4)
                    break
        reset_lightning_timer()

# ================== PLAYER & ITEMS ==================
def check_fire_damage():
    global player_alive
    if not player_alive or won:
        return
    if fire[player_y][player_x] > 0:
        if ITEM_CLOAK in inventory and inventory[ITEM_CLOAK] > 0:
            inventory[ITEM_CLOAK] -= 1
            if inventory[ITEM_CLOAK] <= 0:
                del inventory[ITEM_CLOAK]
            fire[player_y][player_x] = 0
        else:
            player_alive = False

def move_player(dx, dy):
    global player_x, player_y, player_alive, player_drowned, breath
    if not player_alive or won:
        return
    nx, ny = player_x + dx, player_y + dy
    if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
        if maze[ny][nx] == 0:
            player_x, player_y = nx, ny
            if pickups[ny][nx] is not None:
                item = pickups[ny][nx]
                if item in inventory:
                    inventory[item] += ITEM_DEFS[item]['uses']
                else:
                    inventory[item] = ITEM_DEFS[item]['uses']
                pickups[ny][nx] = None
            check_fire_damage()
            if not player_alive:
                return
            if water[ny][nx] >= DROWN_THRESHOLD:
                if ITEM_AQUALUNG in inventory and inventory[ITEM_AQUALUNG] > 0:
                    inventory[ITEM_AQUALUNG] -= 1
                    if inventory[ITEM_AQUALUNG] <= 0:
                        del inventory[ITEM_AQUALUNG]
                else:
                    breath -= 1
                    if breath <= 0:
                        breath = 0
                        player_alive = False
                        player_drowned = True
            else:
                breath = min(BREATH_MAX, breath + BREATH_RECOVER_RATE)
            on_player_action()

def use_directional_item(item_type, dx, dy):
    global aim_mode
    aim_mode = None
    if item_type not in inventory or inventory[item_type] <= 0:
        return
    tx, ty = player_x + dx, player_y + dy
    if not (0 <= tx < MAZE_WIDTH and 0 <= ty < MAZE_HEIGHT):
        return
    used = False
    if item_type == ITEM_MACHETE:
        if maze[ty][tx] == 2:
            maze[ty][tx] = 0
            used = True
    elif item_type == ITEM_TORCH:
        if maze[ty][tx] == 2:
            maze[ty][tx] = 0
            fire[ty][tx] = 3
            regrow[ty][tx] = int(tv('regrow_time'))
            used = True
    elif item_type == ITEM_BUCKET:
        if maze[ty][tx] == 0:
            water[ty][tx] = 5
            fire[ty][tx] = 0
            used = True
    if used:
        inventory[item_type] -= 1
        if inventory[item_type] <= 0:
            del inventory[item_type]
        on_player_action()

def use_compass():
    global compass_timer, compass_path
    if ITEM_COMPASS not in inventory or inventory[ITEM_COMPASS] <= 0:
        return
    compass_path = find_path(player_x, player_y, MAZE_WIDTH - 1, MAZE_HEIGHT - 1)
    compass_timer = 45
    inventory[ITEM_COMPASS] -= 1
    if inventory[ITEM_COMPASS] <= 0:
        del inventory[ITEM_COMPASS]

def sim_tick():
    global frame
    try_lightning()
    seep_from_pipes()
    fire[:] = update_fire()
    water[:] = update_water()
    frame += 1
    if frame % WATER_FLOW_INTERVAL == 0:
        water[:] = flow_water()
    update_regrowth()
    check_fire_damage()

def on_player_action():
    global move_count
    if game_mode == MODE_TACTICAL and player_alive and not won:
        move_count += 1
        sim_tick()

def advance_floor():
    global current_floor, floor_msg_timer, total_wins, just_unlocked, unlock_timer
    total_wins += 1
    current_floor += 1
    floor_msg_timer = 45
    for wins_needed, item_type in UNLOCK_SCHEDULE:
        if wins_needed == total_wins:
            just_unlocked = item_type
            unlock_timer = 90
            break
    generate_maze(keep_inventory=True)

# ================== DRAWING ==================
def draw_maze():
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            rect = (x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            if maze[y][x] == 1:
                pygame.draw.rect(screen, WALL_STONE, rect)
            elif maze[y][x] == 3:
                pygame.draw.rect(screen, PIPE_COLOR, rect)
            elif maze[y][x] == 2:
                col = REGROW_TINT if regrow[y][x] > 0 else WALL_WOOD
                max_heat = 0.0
                for dx, dy in directions:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT and fire[ny][nx] > 0:
                        max_heat = max(max_heat, fire[ny][nx] / 4.0)
                    nx2, ny2 = x + dx * 2, y + dy * 2
                    if 0 <= nx2 < MAZE_WIDTH and 0 <= ny2 < MAZE_HEIGHT and fire[ny2][nx2] > 0:
                        max_heat = max(max_heat, fire[ny2][nx2] / 8.0)
                if max_heat > 0:
                    h = min(1.0, max_heat)
                    col = (
                        min(255, int(col[0] + (255 - col[0]) * h)),
                        max(40, int(col[1] - col[1] * h * 0.6)),
                        max(20, int(col[2] - col[2] * h * 0.5)),
                    )
                pygame.draw.rect(screen, col, rect)
            elif fire[y][x] > 0:
                pygame.draw.rect(screen, FIRE_COLORS[min(fire[y][x]-1, 3)], rect)
            else:
                if water[y][x] > 0:
                    col = WATER_COLORS[min(water[y][x]-1, 4)]
                elif regrow[y][x] == -1:
                    # Fertile ground — subtle green tint shows wood creeping in
                    col = (35, 45, 30)
                elif regrow[y][x] > 0:
                    # Cooling down — subtle warm tint (recently burned)
                    col = (40, 32, 28)
                else:
                    col = PATH_COLOR
                pygame.draw.rect(screen, col, rect)

def draw_grid():
    for xi in range(0, MAZE_PX_W + 1, CELL_SIZE):
        pygame.draw.line(screen, (40, 40, 50), (xi, 0), (xi, MAZE_PX_H), 1)
    for yi in range(0, MAZE_PX_H + 1, CELL_SIZE):
        pygame.draw.line(screen, (40, 40, 50), (0, yi), (MAZE_PX_W, yi), 1)

def draw_pickups():
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if pickups[y][x] is not None:
                item_def = ITEM_DEFS[pickups[y][x]]
                cx = x * CELL_SIZE + CELL_SIZE // 2
                cy = y * CELL_SIZE + CELL_SIZE // 2
                size = CELL_SIZE // 3
                pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
                pygame.draw.polygon(screen, item_def['color'], pts)
                pygame.draw.polygon(screen, (255, 255, 255), pts, 1)

def draw_goal():
    gx = (MAZE_WIDTH - 1) * CELL_SIZE + 2
    gy = (MAZE_HEIGHT - 1) * CELL_SIZE + 2
    pygame.draw.rect(screen, GOAL_COLOR, (gx, gy, CELL_SIZE - 4, CELL_SIZE - 4))

def draw_player():
    px_c = player_x * CELL_SIZE + CELL_SIZE // 2
    py_c = player_y * CELL_SIZE + CELL_SIZE // 2
    if not player_alive:
        color = PLAYER_DROWN_COLOR if player_drowned else PLAYER_DEAD_COLOR
    else:
        color = PLAYER_COLOR
    pygame.draw.circle(screen, color, (px_c, py_c), CELL_SIZE // 2 - 1)

def draw_compass():
    if compass_timer > 0 and compass_path:
        pulse = abs(math.sin(compass_timer * 0.2)) * 0.5 + 0.5
        show_count = min(10, len(compass_path))
        for i in range(show_count):
            cx, cy = compass_path[i]
            fade = 1.0 - (i / show_count) * 0.6
            r = int(255 * pulse * fade)
            g = int(255 * pulse * fade)
            b = int(100 * pulse * fade)
            px = cx * CELL_SIZE + CELL_SIZE // 2
            py = cy * CELL_SIZE + CELL_SIZE // 2
            pygame.draw.circle(screen, (r, g, b), (px, py), CELL_SIZE // 4)

def draw_aim_indicator():
    if aim_mode and player_alive:
        for dx, dy in directions:
            tx = player_x + dx
            ty = player_y + dy
            if 0 <= tx < MAZE_WIDTH and 0 <= ty < MAZE_HEIGHT:
                valid = False
                if aim_mode == ITEM_MACHETE and maze[ty][tx] == 2:
                    valid = True
                elif aim_mode == ITEM_TORCH and maze[ty][tx] == 2:
                    valid = True
                elif aim_mode == ITEM_BUCKET and maze[ty][tx] == 0:
                    valid = True
                if valid:
                    rect = (tx * CELL_SIZE, ty * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                    col = ITEM_DEFS[aim_mode]['color']
                    pygame.draw.rect(screen, col, rect, 2)

def draw_breath_bar():
    if player_alive and not won and breath < BREATH_MAX:
        px_c = player_x * CELL_SIZE + CELL_SIZE // 2
        py_c = player_y * CELL_SIZE + CELL_SIZE // 2
        bar_w, bar_h = 80, 8
        bar_x = max(0, min(px_c - bar_w // 2, MAZE_PX_W - bar_w))
        bar_y = max(0, py_c - CELL_SIZE // 2 - 12)
        pygame.draw.rect(screen, (40, 40, 60), (bar_x, bar_y, bar_w, bar_h))
        fill = breath / BREATH_MAX
        r = int(255 * (1 - fill))
        g = int(180 * fill)
        b = int(255 * fill)
        pygame.draw.rect(screen, (r, g, b), (bar_x, bar_y, int(bar_w * fill), bar_h))
        pygame.draw.rect(screen, (200, 200, 200), (bar_x, bar_y, bar_w, bar_h), 1)

def draw_hud():
    hud_y = MAZE_PX_H
    pygame.draw.rect(screen, HUD_BG, (0, hud_y, MAZE_PX_W, HUD_HEIGHT))
    pygame.draw.line(screen, (60, 60, 80), (0, hud_y), (MAZE_PX_W, hud_y), 1)

    floor_col = (255, 220, 100) if floor_msg_timer > 0 else (180, 180, 200)
    floor_text = font_hud.render(f"F{current_floor}", True, floor_col)
    screen.blit(floor_text, (6, hud_y + 10))
    x_off = 6 + floor_text.get_width() + 8

    unlocked = get_unlocked_items()
    for item_type in ITEM_ORDER:
        if item_type not in unlocked:
            continue
        item_def = ITEM_DEFS[item_type]
        has = item_type in inventory
        col = item_def['color'] if has else (50, 50, 60)
        pygame.draw.rect(screen, col, (x_off, hud_y + 10, 14, 14))
        if has:
            pygame.draw.rect(screen, (255, 255, 255), (x_off, hud_y + 10, 14, 14), 1)
        x_off += 18
        if has:
            ct = font_hud.render(str(inventory[item_type]), True, (255, 255, 255))
            screen.blit(ct, (x_off, hud_y + 10))
            x_off += ct.get_width() + 2
        if item_def['key']:
            kt = font_tiny.render(f"[{item_def['key'].upper()}]", True, (120, 120, 140))
            screen.blit(kt, (x_off, hud_y + 13))
            x_off += kt.get_width() + 4
        x_off += 6

    # Lightning countdown
    params = get_floor_params(current_floor)
    if game_mode == MODE_TACTICAL:
        lt_max = max(8, int(TACTICAL_LIGHTNING_MAX * params['lightning_scale']))
    else:
        lt_max = max(60, int(LIGHTNING_MAX_FRAMES * params['lightning_scale']))
    lt_ratio = max(0.0, 1.0 - lightning_timer / max(1, lt_max))
    bar_w, bar_h = 40, 6
    lt_r = int(255 * lt_ratio)
    lt_g = int(255 * (1 - lt_ratio * 0.5))
    lt_col = (lt_r, lt_g, 50)
    bolt_text = font_tiny.render("ZAP", True, (200, 200, 100) if lt_ratio < 0.8 else (255, 255, 80))
    screen.blit(bolt_text, (x_off, hud_y + 12))
    bx = x_off + bolt_text.get_width() + 3
    pygame.draw.rect(screen, (40, 40, 50), (bx, hud_y + 14, bar_w, bar_h))
    pygame.draw.rect(screen, lt_col, (bx, hud_y + 14, int(bar_w * lt_ratio), bar_h))

    if aim_mode:
        aim_text = font_hud.render(f"AIM: {ITEM_DEFS[aim_mode]['name']}", True, (255, 255, 100))
        screen.blit(aim_text, (MAZE_PX_W - aim_text.get_width() - 80, hud_y + 10))

    mode_label = "TACTICAL" if game_mode == MODE_TACTICAL else "CHAOS"
    mode_col = (100, 200, 255) if game_mode == MODE_TACTICAL else (255, 130, 60)
    mode_text = font_hud.render(f"{mode_label}", True, mode_col)
    tab_hint = font_tiny.render("[TAB]", True, (120, 120, 140))
    rx = MAZE_PX_W - 8
    rx -= mode_text.get_width()
    screen.blit(mode_text, (rx, hud_y + 10))
    rx -= tab_hint.get_width() + 2
    screen.blit(tab_hint, (rx, hud_y + 13))

def draw_sidebar():
    sx = MAZE_PX_W  # sidebar left edge
    # Background
    pygame.draw.rect(screen, (20, 20, 28), (sx, 0, SIDEBAR_W, MAZE_PX_H + HUD_HEIGHT))
    pygame.draw.line(screen, (60, 60, 80), (sx, 0), (sx, MAZE_PX_H + HUD_HEIGHT), 1)

    # Title
    title = font_ed.render("TUNING  [/] -/=", True, (255, 200, 100))
    screen.blit(title, (sx + 8, 8))

    row_h = 18
    for i, key in enumerate(tuning_keys):
        t = tuning[key]
        y = 30 + i * row_h
        selected = (i == editor_sel)
        col = (255, 255, 100) if selected else (180, 180, 200)
        marker = "\u25b6" if selected else " "
        fmt = t['fmt']
        val_str = f"{t['val']:{fmt}}"
        text = font_ed.render(f"{marker}{t['label']:.<14s}{val_str}", True, col)
        screen.blit(text, (sx + 8, y))
        # Bar showing position in range
        ratio = (t['val'] - t['min']) / max(0.001, t['max'] - t['min'])
        bar_w = SIDEBAR_W - 24
        bar_y = y + 14
        pygame.draw.rect(screen, (40, 40, 60), (sx + 8, bar_y, bar_w, 3))
        pygame.draw.rect(screen, col, (sx + 8, bar_y, int(bar_w * ratio), 3))

def draw_messages():
    if not player_alive:
        if player_drowned:
            msg = f"DROWNED on Floor {current_floor}! R to restart"
            col = (80, 130, 255)
        else:
            msg = f"BURNED on Floor {current_floor}! R to restart"
            col = (255, 80, 80)
        text = font_msg.render(msg, True, col)
        screen.blit(text, (MAZE_PX_W // 2 - text.get_width() // 2, 10))

    if floor_msg_timer > 0:
        alpha = min(1.0, floor_msg_timer / 15.0)
        col = (int(255 * alpha), int(220 * alpha), int(100 * alpha))
        text = font_big.render(f"FLOOR {current_floor}", True, col)
        screen.blit(text, (MAZE_PX_W // 2 - text.get_width() // 2, MAZE_PX_H // 2 - 24))

    if unlock_timer > 0 and just_unlocked:
        name = ITEM_DEFS[just_unlocked]['name']
        col = ITEM_DEFS[just_unlocked]['color']
        text = font_msg.render(f"UNLOCKED: {name}!", True, col)
        screen.blit(text, (MAZE_PX_W // 2 - text.get_width() // 2, 50))

# ================== MAIN LOOP ==================
generate_maze()
running = True
paused = False
frame = 0

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            # Sidebar tuning controls (always active)
            if event.key == pygame.K_LEFTBRACKET:
                editor_sel = (editor_sel - 1) % len(tuning_keys)
            elif event.key == pygame.K_RIGHTBRACKET:
                editor_sel = (editor_sel + 1) % len(tuning_keys)
            elif event.key == pygame.K_MINUS:
                k = tuning_keys[editor_sel]
                t = tuning[k]
                t['val'] = max(t['min'], round(t['val'] - t['step'], 4))
            elif event.key == pygame.K_EQUALS:
                k = tuning_keys[editor_sel]
                t = tuning[k]
                t['val'] = min(t['max'], round(t['val'] + t['step'], 4))
            # Game controls
            elif event.key == pygame.K_ESCAPE:
                aim_mode = None
            elif event.key == pygame.K_SPACE:
                paused = not paused
            elif event.key == pygame.K_TAB:
                game_mode = MODE_CHAOS if game_mode == MODE_TACTICAL else MODE_TACTICAL
                reset_lightning_timer()
            elif event.key == pygame.K_r:
                if not player_alive:
                    current_floor = 1
                    generate_maze()
            elif event.key == pygame.K_m and ITEM_MACHETE in inventory:
                aim_mode = ITEM_MACHETE if aim_mode != ITEM_MACHETE else None
            elif event.key == pygame.K_t and ITEM_TORCH in inventory:
                aim_mode = ITEM_TORCH if aim_mode != ITEM_TORCH else None
            elif event.key == pygame.K_b and ITEM_BUCKET in inventory:
                aim_mode = ITEM_BUCKET if aim_mode != ITEM_BUCKET else None
            elif event.key == pygame.K_c and ITEM_COMPASS in inventory:
                use_compass()
            elif event.key in (pygame.K_UP, pygame.K_w):
                if aim_mode:
                    use_directional_item(aim_mode, 0, -1)
                else:
                    move_player(0, -1)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                if aim_mode:
                    use_directional_item(aim_mode, 0, 1)
                else:
                    move_player(0, 1)
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                if aim_mode:
                    use_directional_item(aim_mode, -1, 0)
                else:
                    move_player(-1, 0)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                if aim_mode:
                    use_directional_item(aim_mode, 1, 0)
                else:
                    move_player(1, 0)

    if not paused:
        if game_mode == MODE_CHAOS:
            sim_tick()

        if player_alive and not won and player_x == MAZE_WIDTH - 1 and player_y == MAZE_HEIGHT - 1:
            advance_floor()

        if compass_timer > 0:
            compass_timer -= 1
        if unlock_timer > 0:
            unlock_timer -= 1
        if floor_msg_timer > 0:
            floor_msg_timer -= 1

    screen.fill(BG_COLOR)
    draw_maze()
    draw_grid()
    draw_pickups()
    draw_goal()
    draw_compass()
    draw_aim_indicator()
    draw_player()
    draw_breath_bar()
    draw_hud()
    draw_messages()
    draw_sidebar()

    pygame.display.flip()
    clock.tick(15)

pygame.quit()
sys.exit()
