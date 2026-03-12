import pygame
import random
import sys

# ================== SETTINGS ==================
CELL_SIZE = 16          # pixels per cell (increase to 30–40 for bigger/slower view)
MAZE_WIDTH = 50         # cells — keep even-ish for clean carving
MAZE_HEIGHT = 38

PATH_COLOR = (30, 40, 60)          # dry path
WALL_STONE = (90, 90, 110)         # permanent
WALL_WOOD  = (160, 100, 60)        # healthy wood
FIRE_COLORS = [(255, 80, 0), (255, 120, 0), (255, 170, 0), (255, 255, 80)]
WATER_COLORS = [(200, 220, 255), (180, 210, 255), (160, 200, 255),
                (140, 190, 255), (120, 180, 255)]  # wet levels 1–5
REGROW_TINT = (180, 120, 80)       # lighter during regrowth

BG_COLOR = (20, 20, 30)

# Event timers (in frames at 15 FPS → seconds = value / 15)
LIGHTNING_MIN_FRAMES = 150   # ~10 sec min
LIGHTNING_MAX_FRAMES = 450   # ~30 sec max
LEAK_MIN_FRAMES = 225        # ~15 sec
LEAK_MAX_FRAMES = 600        # ~40 sec

lightning_timer = random.randint(LIGHTNING_MIN_FRAMES, LIGHTNING_MAX_FRAMES)
leak_timer = random.randint(LEAK_MIN_FRAMES, LEAK_MAX_FRAMES)

pygame.init()
WIDTH = MAZE_WIDTH * CELL_SIZE
HEIGHT = MAZE_HEIGHT * CELL_SIZE
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Living Maze Proto — Fire, Water, Regrowing Wood")
clock = pygame.time.Clock()

# Grids
maze  = [[0 for _ in range(MAZE_WIDTH)] for _ in range(MAZE_HEIGHT)]   # 0=path, 1=stone, 2=wood
fire  = [[0 for _ in range(MAZE_WIDTH)] for _ in range(MAZE_HEIGHT)]   # 0=none, 1–4 intensity
water = [[0 for _ in range(MAZE_WIDTH)] for _ in range(MAZE_HEIGHT)]   # 0=dry, 1–5 moisture
regrow = [[0 for _ in range(MAZE_WIDTH)] for _ in range(MAZE_HEIGHT)]  # countdown to regrow wood

directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

# ================== MAZE GENERATION ==================
def generate_maze():
    # Reset everything
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            maze[y][x] = 1   # stone
            fire[y][x] = 0
            water[y][x] = 0
            regrow[y][x] = 0

    # Iterative backtracker (no recursion limit issues)
    stack = []
    start_x, start_y = 0, 0
    maze[start_y][start_x] = 0
    stack.append((start_x, start_y))

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
            maze[y + dy][x + dx] = 0          # carve passage
            maze[ny][nx] = 0
            stack.append((nx, ny))
        else:
            stack.pop()

    # Ensure start & end are open
    maze[0][0] = 0
    maze[MAZE_HEIGHT-1][MAZE_WIDTH-1] = 0

    # Randomly convert some walls to burnable wood (~35%)
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if maze[y][x] == 1 and random.random() < 0.35:
                maze[y][x] = 2

    # Default water on most path cells (mostly medium moisture)
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if maze[y][x] == 0:
                water[y][x] = random.choices([0,1,2,3,4,5], weights=[5,10,20,40,20,5])[0]

    # Start 3–5 fires
    for _ in range(random.randint(3, 5)):
        while True:
            fx = random.randint(2, MAZE_WIDTH-3)
            fy = random.randint(2, MAZE_HEIGHT-3)
            if maze[fy][fx] == 0:
                fire[fy][fx] = 1
                break

# ================== SIMULATION STEPS ==================
def update_fire():
    new_fire = [row[:] for row in fire]
    for y in range(1, MAZE_HEIGHT-1):
        for x in range(1, MAZE_WIDTH-1):
            if fire[y][x] == 0:
                continue
            intensity = fire[y][x]

            # Water extinguishes
            if water[y][x] > 0:
                new_fire[y][x] = max(0, intensity - water[y][x] * 2)
                continue

            spread_chance = 0.25 + intensity * 0.15

            # Burn wood → open path + start regrow timer
            if maze[y][x] == 2 and intensity >= 2:
                if random.random() < 0.55:
                    maze[y][x] = 0
                    regrow[y][x] = 120  # ~8 sec at 15 FPS

            # Spread
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                if 0 <= nx < MAZE_WIDTH and 0 <= ny < MAZE_HEIGHT:
                    if maze[ny][nx] != 1:  # not stone
                        # Resist if very wet
                        if water[ny][nx] <= 2 or random.random() < 0.3:
                            if random.random() < spread_chance:
                                new_fire[ny][nx] = max(new_fire[ny][nx], intensity)

            # Decay on dry path
            if maze[y][x] == 0 and random.random() < 0.18:
                new_fire[y][x] = max(0, intensity - 1)

    return new_fire

def update_water():
    new_water = [row[:] for row in water]
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if water[y][x] > 0:
                # Very slow evaporation
                if random.random() < 0.015:
                    new_water[y][x] -= 1

            # Fire dries water
            if fire[y][x] > 0 and water[y][x] > 0:
                new_water[y][x] = max(0, water[y][x] - fire[y][x] // 2 - 1)

    return new_water

def update_regrowth():
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            if regrow[y][x] > 0:
                regrow[y][x] -= 1
                if regrow[y][x] <= 0:
                    # Only regrow if still open and not on fire
                    if maze[y][x] == 0 and fire[y][x] == 0:
                        maze[y][x] = 2

def try_lightning():
    global lightning_timer
    lightning_timer -= 1
    if lightning_timer <= 0:
        count = random.randint(1, 3)
        for _ in range(count):
            while True:
                x = random.randint(1, MAZE_WIDTH-2)
                y = random.randint(1, MAZE_HEIGHT-2)
                if maze[y][x] != 1:  # not stone
                    fire[y][x] = random.randint(2, 4)
                    break
        lightning_timer = random.randint(LIGHTNING_MIN_FRAMES, LIGHTNING_MAX_FRAMES)
        print("Lightning strike!")  # optional console feedback

def try_leak():
    global leak_timer
    leak_timer -= 1
    if leak_timer <= 0:
        count = random.randint(1, 3)
        for _ in range(count):
            while True:
                x = random.randint(1, MAZE_WIDTH-2)
                y = random.randint(1, MAZE_HEIGHT-2)
                if maze[y][x] == 0:  # path cells only
                    water[y][x] = min(5, water[y][x] + random.randint(2, 4))
                    break
        leak_timer = random.randint(LEAK_MIN_FRAMES, LEAK_MAX_FRAMES)
        print("Leak!")  # optional

# ================== MAIN LOOP ==================
generate_maze()

running = True
paused = False

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                paused = not paused
            elif event.key == pygame.K_r:
                generate_maze()

    if not paused:
        try_lightning()
        try_leak()
        
        fire = update_fire()
        water = update_water()
        update_regrowth()

    # Draw
    screen.fill(BG_COLOR)
    for y in range(MAZE_HEIGHT):
        for x in range(MAZE_WIDTH):
            rect = (x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)

            if maze[y][x] == 1:
                pygame.draw.rect(screen, WALL_STONE, rect)
            elif maze[y][x] == 2:
                if regrow[y][x] > 0:
                    pygame.draw.rect(screen, REGROW_TINT, rect)
                else:
                    pygame.draw.rect(screen, WALL_WOOD, rect)
            elif fire[y][x] > 0:
                col = FIRE_COLORS[min(fire[y][x]-1, 3)]
                pygame.draw.rect(screen, col, rect)
            else:
                # Path with water tint or dry
                if water[y][x] > 0:
                    col = WATER_COLORS[min(water[y][x]-1, 4)]
                else:
                    col = PATH_COLOR
                pygame.draw.rect(screen, col, rect)

    # Thin grid lines (optional — comment out if you prefer clean look)
    for xi in range(0, WIDTH + 1, CELL_SIZE):
        pygame.draw.line(screen, (40, 40, 50), (xi, 0), (xi, HEIGHT), 1)
    for yi in range(0, HEIGHT + 1, CELL_SIZE):
        pygame.draw.line(screen, (40, 40, 50), (0, yi), (WIDTH, yi), 1)

    pygame.display.flip()
    clock.tick(15)  # slow enough to watch dynamics nicely

pygame.quit()
sys.exit()