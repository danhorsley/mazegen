import pygame
import random
import sys
import math

# ================== SETTINGS ==================
CELL_SIZE = 16
MAZE_WIDTH = 50
MAZE_HEIGHT = 38

PATH_COLOR = (30, 40, 60)
WALL_STONE = (90, 90, 110)
WALL_WOOD  = (160, 100, 60)
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

SAFE_RADIUS = 3

DROWN_THRESHOLD = 4
BREATH_MAX = 10
BREATH_RECOVER_RATE = 2

LIGHTNING_MIN_FRAMES = 300
LIGHTNING_MAX_FRAMES = 750
LEAK_MIN_FRAMES = 90
LEAK_MAX_FRAMES = 270
WATER_FLOW_INTERVAL = 3

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

# Items shown in HUD order
ITEM_ORDER = [ITEM_MACHETE, ITEM_TORCH, ITEM_CLOAK, ITEM_AQUALUNG, ITEM_BUCKET, ITEM_COMPASS]

# Unlock schedule: (wins_needed, item_type)
UNLOCK_SCHEDULE = [
    (0, ITEM_TORCH),
    (1, ITEM_MACHETE),
    (2, ITEM_CLOAK),
    (3, ITEM_AQUALUNG),
    (4, ITEM_BUCKET),
    (5, ITEM_COMPASS),
]

# Player starts each run with a torch so they can never be softlocked
STARTING_INVENTORY = {ITEM_TORCH: 1}

# ================== INIT ==================
pygame.init()
MAZE_PX_W = MAZE_WIDTH * CELL_SIZE
MAZE_PX_H = MAZE_HEIGHT * CELL_SIZE
HUD_HEIGHT = 36
screen = pygame.display.set_mode((MAZE_PX_W, MAZE_PX_H + HUD_HEIGHT))
pygame.display.set_caption("Living Maze — Navigate the Chaos")
clock = pygame.time.Clock()
pygame.key.set_repeat(150, 80)

font_hud = pygame.font.SysFont(None, 20)
font_msg = pygame.font.SysFont(None, 36)
font_big = pygame.font.SysFont(None, 48)
font_tiny = pygame.font.SysFont(None, 14)

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
inventory = {}      # item_type -> uses_remaining
aim_mode = None     # None or item_type (for directional items)
compass_timer = 0

# Meta-progression (persists across runs within session)
total_wins = 0
just_unlocked = None
unlock_timer = 0

lightning_timer = random.randint(LIGHTNING_MIN_FRAMES, LIGHTNING_MAX_FRAMES)
leak_timer = random.randint(LEAK_MIN_FRAMES, LEAK_MAX_FRAMES)

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

# ================== MAZE GENERATION ==================
def place_pickups():
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            pickups[y][x] = None

    available = get_unlocked_items()
    for item_type in available:
        count = random.randint(2, 4)
        for _ in range(count):
            for _attempt in range(200):
                x = random.randint(1, MAZE_WIDTH - 2)
                y = random.randint(1, MAZE_HEIGHT - 2)
                if maze[y][x] != 0 or pickups[y][x] is not None:
                    continue
                if in_safe_zone(x, y):
                    continue

                # Thematic placement
                if item_type == ITEM_CLOAK:
                    # Near fire or wood (likely to catch fire)
                    near_danger = any(
                        0 <= x+dx < MAZE_WIDTH and 0 <= y+dy < MAZE_HEIGHT
                        and (fire[y+dy][x+dx] > 0 or maze[y+dy][x+dx] == 2)
                        for dx, dy in directions
                    )
                    if not near_danger:
                        continue
                elif item_type == ITEM_AQUALUNG:
                    if water[y][x] < 2 and random.random() > 0.3:
                        continue

                pickups[y][x] = item_type
                break

def generate_maze():
    global player_x, player_y, player_alive, player_drowned, won, breath
    global inventory, aim_mode, compass_timer
    global lightning_timer, leak_timer

    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            maze[y][x] = 1
            fire[y][x] = 0
            water[y][x] = 0
            regrow[y][x] = 0
            pickups[y][x] = None

    # Iterative backtracker
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

    # ~75% wood, safe zones + border stay stone
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if maze[y][x] == 1:
                if x == 0 or x == MAZE_WIDTH - 1 or y == 0 or y == MAZE_HEIGHT - 1:
                    continue
                if in_safe_zone(x, y):
                    continue
                if random.random() < 0.75:
                    maze[y][x] = 2

    # Guarantee open approach into start and exit through the safe zone.
    # Carve a path from just outside each safe zone to the corner cell.
    # Start (0,0): carve along row 0 from x=SAFE_RADIUS+1 inward
    for x in range(SAFE_RADIUS + 1, -1, -1):
        if maze[0][x] == 0:
            # Found an open cell, carve from here to (0,0)
            for cx in range(x, -1, -1):
                maze[0][cx] = 0
            break
    else:
        # Fallback: carve column 0 from y=SAFE_RADIUS+1 inward
        for cy in range(SAFE_RADIUS + 1, -1, -1):
            maze[cy][0] = 0

    # Exit (MAZE_WIDTH-1, MAZE_HEIGHT-1): carve inward
    ey, ex = MAZE_HEIGHT - 1, MAZE_WIDTH - 1
    for x in range(ex - SAFE_RADIUS - 1, ex + 1):
        if maze[ey][x] == 0:
            for cx in range(x, ex + 1):
                maze[ey][cx] = 0
            break
    else:
        for cy in range(ey - SAFE_RADIUS - 1, ey + 1):
            maze[cy][ex] = 0

    # Water on paths
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if maze[y][x] == 0:
                water[y][x] = random.choices([0,1,2,3,4,5], weights=[5,10,20,40,20,5])[0]

    # Dry safe zones
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if in_safe_zone(x, y):
                water[y][x] = 0

    # Start 2-3 small fires away from safe zones
    for _ in range(random.randint(2, 3)):
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
    inventory = {k: v for k, v in STARTING_INVENTORY.items()}
    aim_mode = None
    compass_timer = 0
    lightning_timer = random.randint(LIGHTNING_MIN_FRAMES, LIGHTNING_MAX_FRAMES)
    leak_timer = random.randint(LEAK_MIN_FRAMES, LEAK_MAX_FRAMES)

# ================== SIMULATION ==================
def count_fire_cells():
    return sum(1 for y in range(MAZE_HEIGHT) for x in range(MAZE_WIDTH) if fire[y][x] > 0)

def update_fire():
    new_fire = [row[:] for row in fire]
    fire_count = count_fire_cells()
    total_open = sum(1 for y in range(MAZE_HEIGHT) for x in range(MAZE_WIDTH) if maze[y][x] != 1)
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

            base_spread = 0.06 + intensity * 0.04
            spread_chance = base_spread * global_dampen

            if maze[y][x] == 2 and intensity >= 2:
                if random.random() < 0.40:
                    maze[y][x] = 0
                    regrow[y][x] = 150

            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
                    if maze[ny][nx] != 1:
                        if water[ny][nx] >= 3:
                            continue
                        if water[ny][nx] >= 1 and random.random() > 0.12:
                            continue
                        if random.random() < spread_chance:
                            spread_intensity = max(1, intensity - 1)
                            new_fire[ny][nx] = max(new_fire[ny][nx], spread_intensity)

            decay_chance = 0.22 + intensity * 0.08
            if maze[y][x] == 0 and random.random() < decay_chance:
                new_fire[y][x] = max(0, intensity - 1)

    return new_fire

def update_water():
    new_water = [row[:] for row in water]
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if water[y][x] > 0:
                if random.random() < 0.008:
                    new_water[y][x] -= 1
            if fire[y][x] > 0 and water[y][x] > 0:
                if random.random() < 0.3:
                    new_water[y][x] = max(0, water[y][x] - 1)
    return new_water

def flow_water():
    new_water = [row[:] for row in water]
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if water[y][x] >= 3 and maze[y][x] == 0:
                for dx, dy in directions:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
                        if maze[ny][nx] == 0 and water[ny][nx] < water[y][x] - 1:
                            if random.random() < 0.06:
                                new_water[ny][nx] = min(5, new_water[ny][nx] + 1)
    return new_water

def update_regrowth():
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if regrow[y][x] > 0:
                regrow[y][x] -= 1
                if regrow[y][x] <= 0:
                    if maze[y][x] == 0 and fire[y][x] == 0:
                        if (x, y) != (player_x, player_y) and pickups[y][x] is None:
                            maze[y][x] = 2

def try_lightning():
    global lightning_timer
    lightning_timer -= 1
    if lightning_timer <= 0:
        count = random.randint(1, 2)
        for _ in range(count):
            for _attempt in range(100):
                x = random.randint(1, MAZE_WIDTH - 2)
                y = random.randint(1, MAZE_HEIGHT - 2)
                if maze[y][x] != 1 and water[y][x] <= 1:
                    fire[y][x] = random.randint(1, 3)
                    break
        lightning_timer = random.randint(LIGHTNING_MIN_FRAMES, LIGHTNING_MAX_FRAMES)

def try_leak():
    global leak_timer
    leak_timer -= 1
    if leak_timer <= 0:
        count = random.randint(3, 6)
        for _ in range(count):
            for _attempt in range(100):
                x = random.randint(1, MAZE_WIDTH - 2)
                y = random.randint(1, MAZE_HEIGHT - 2)
                if maze[y][x] == 0:
                    water[y][x] = min(5, water[y][x] + random.randint(3, 5))
                    for dx, dy in directions:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
                            if maze[ny][nx] == 0:
                                water[ny][nx] = min(5, water[ny][nx] + random.randint(1, 3))
                    break
        leak_timer = random.randint(LEAK_MIN_FRAMES, LEAK_MAX_FRAMES)

# ================== PLAYER & ITEMS ==================
def check_fire_damage():
    """Fire on player's cell: cloak absorbs or player dies."""
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

            # Pick up items first (cloak pickup saves you from fire on same cell)
            if pickups[ny][nx] is not None:
                item = pickups[ny][nx]
                if item in inventory:
                    inventory[item] += ITEM_DEFS[item]['uses']
                else:
                    inventory[item] = ITEM_DEFS[item]['uses']
                pickups[ny][nx] = None

            # Fire damage (cloak absorbs)
            check_fire_damage()
            if not player_alive:
                return

            # Breath mechanic (aqualung absorbs)
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

def use_directional_item(item_type, dx, dy):
    """Use machete/torch/bucket in the given direction."""
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
            regrow[ty][tx] = 150
            used = True

    elif item_type == ITEM_BUCKET:
        if maze[ty][tx] != 1:
            water[ty][tx] = 5
            fire[ty][tx] = 0
            used = True

    if used:
        inventory[item_type] -= 1
        if inventory[item_type] <= 0:
            del inventory[item_type]

def use_compass():
    global compass_timer
    if ITEM_COMPASS not in inventory or inventory[ITEM_COMPASS] <= 0:
        return
    compass_timer = 45  # 3 sec at 15 FPS
    inventory[ITEM_COMPASS] -= 1
    if inventory[ITEM_COMPASS] <= 0:
        del inventory[ITEM_COMPASS]

def handle_win():
    global total_wins, just_unlocked, unlock_timer
    total_wins += 1
    for wins_needed, item_type in UNLOCK_SCHEDULE:
        if wins_needed == total_wins:
            just_unlocked = item_type
            unlock_timer = 90  # 6 sec
            break

# ================== DRAWING ==================
def draw_maze():
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            rect = (x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            if maze[y][x] == 1:
                pygame.draw.rect(screen, WALL_STONE, rect)
            elif maze[y][x] == 2:
                col = REGROW_TINT if regrow[y][x] > 0 else WALL_WOOD
                pygame.draw.rect(screen, col, rect)
            elif fire[y][x] > 0:
                pygame.draw.rect(screen, FIRE_COLORS[min(fire[y][x]-1, 3)], rect)
            else:
                col = WATER_COLORS[min(water[y][x]-1, 4)] if water[y][x] > 0 else PATH_COLOR
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
    if compass_timer > 0:
        px_c = player_x * CELL_SIZE + CELL_SIZE // 2
        py_c = player_y * CELL_SIZE + CELL_SIZE // 2
        gx_c = (MAZE_WIDTH - 1) * CELL_SIZE + CELL_SIZE // 2
        gy_c = (MAZE_HEIGHT - 1) * CELL_SIZE + CELL_SIZE // 2
        pulse = abs(math.sin(compass_timer * 0.2)) * 0.5 + 0.5
        col = (int(255 * pulse), int(255 * pulse), int(100 * pulse))
        pygame.draw.line(screen, col, (px_c, py_c), (gx_c, gy_c), 2)

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
                elif aim_mode == ITEM_BUCKET and maze[ty][tx] != 1:
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

    unlocked = get_unlocked_items()
    x_off = 8

    for item_type in ITEM_ORDER:
        if item_type not in unlocked:
            continue
        item_def = ITEM_DEFS[item_type]
        has = item_type in inventory

        col = item_def['color'] if has else (50, 50, 60)
        # Colored square
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

        x_off += 10

    # Aim mode indicator
    if aim_mode:
        aim_text = font_hud.render(f"AIM: {ITEM_DEFS[aim_mode]['name']}", True, (255, 255, 100))
        screen.blit(aim_text, (MAZE_PX_W - aim_text.get_width() - 80, hud_y + 10))

    # Wins
    wins_text = font_hud.render(f"Wins: {total_wins}", True, (180, 180, 200))
    screen.blit(wins_text, (MAZE_PX_W - wins_text.get_width() - 8, hud_y + 10))

def draw_messages():
    if not player_alive:
        if player_drowned:
            msg, col = "DROWNED! Press R to restart", (80, 130, 255)
        else:
            msg, col = "BURNED! Press R to restart", (255, 80, 80)
        text = font_msg.render(msg, True, col)
        screen.blit(text, (MAZE_PX_W // 2 - text.get_width() // 2, 10))
    elif won:
        text = font_big.render("YOU ESCAPED!", True, (0, 255, 100))
        screen.blit(text, (MAZE_PX_W // 2 - text.get_width() // 2, MAZE_PX_H // 2 - 24))
        hint = font_hud.render("Press R for next run", True, (180, 180, 200))
        screen.blit(hint, (MAZE_PX_W // 2 - hint.get_width() // 2, MAZE_PX_H // 2 + 20))

    # Unlock notification
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
            if event.key == pygame.K_ESCAPE:
                aim_mode = None
            elif event.key == pygame.K_SPACE:
                paused = not paused
            elif event.key == pygame.K_r:
                if won:
                    handle_win()
                generate_maze()
            # Item activation
            elif event.key == pygame.K_m and ITEM_MACHETE in inventory:
                aim_mode = ITEM_MACHETE if aim_mode != ITEM_MACHETE else None
            elif event.key == pygame.K_t and ITEM_TORCH in inventory:
                aim_mode = ITEM_TORCH if aim_mode != ITEM_TORCH else None
            elif event.key == pygame.K_b and ITEM_BUCKET in inventory:
                aim_mode = ITEM_BUCKET if aim_mode != ITEM_BUCKET else None
            elif event.key == pygame.K_c and ITEM_COMPASS in inventory:
                use_compass()
            # Direction: use item if aiming, otherwise move
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
        try_lightning()
        try_leak()
        fire[:] = update_fire()
        water[:] = update_water()
        frame += 1
        if frame % WATER_FLOW_INTERVAL == 0:
            water[:] = flow_water()
        update_regrowth()

        # Fire may have spread to player
        check_fire_damage()

        # Win check
        if player_alive and not won and player_x == MAZE_WIDTH - 1 and player_y == MAZE_HEIGHT - 1:
            won = True
            handle_win()

        if compass_timer > 0:
            compass_timer -= 1
        if unlock_timer > 0:
            unlock_timer -= 1

    # Draw
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

    pygame.display.flip()
    clock.tick(15)

pygame.quit()
sys.exit()
