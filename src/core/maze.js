import { COLS, ROWS } from './constants.js';

export const WALL = '#';
export const DOOR = '=';
export const PELLET = '.';
export const POWER_PELLET = 'o';
export const EMPTY = ' ';
export const PLAYER_START = 'P';
export const GHOST_STARTS = ['1', '2', '3', '4'];

export const MAZE_ROWS = [
  '############################',
  '#............##............#',
  '#.####.#####.##.#####.####.#',
  '#o####.#####.##.#####.####o#',
  '#.####.#####.##.#####.####.#',
  '#..........................#',
  '#.####.##.########.##.####.#',
  '#.####.##.########.##.####.#',
  '#......##....##....##......#',
  '######.##### ## #####.######',
  '######.##### ## #####.######',
  '######.##          ##.######',
  '######.## ###==### ##.######',
  '######.## #      # ##.######',
  '          # 1234 #          ',
  '######.## #      # ##.######',
  '######.## ######## ##.######',
  '######.##          ##.######',
  '######.## ######## ##.######',
  '######.## ######## ##.######',
  '#............##............#',
  '#.####.#####.##.#####.####.#',
  '#.####.#####.##.#####.####.#',
  '#o..##.......P .......##..o#',
  '###.##.##.########.##.##.###',
  '###.##.##.########.##.##.###',
  '#......##....##....##......#',
  '#.##########.##.##########.#',
  '#.##########.##.##########.#',
  '#..........................#',
  '############################',
];

export function tileKey(x, y) {
  return `${x},${y}`;
}

/**
 * Build a static maze description from an ASCII layout.
 * Pellets and power pellets are returned as initial sets; gameplay mutates copies.
 */
export function createMaze(rows = MAZE_ROWS) {
  if (rows.length !== ROWS) {
    throw new Error(`maze must have ${ROWS} rows, got ${rows.length}`);
  }
  const cols = rows[0].length;
  if (cols !== COLS || rows.some((row) => row.length !== cols)) {
    throw new Error(`maze must be ${COLS}x${ROWS}`);
  }

  const walls = [];
  const doors = [];
  const pellets = new Set();
  const powerPellets = new Set();
  const ghostStarts = [];
  let playerStart = null;

  for (let y = 0; y < rows.length; y += 1) {
    walls.push([]);
    doors.push([]);
    for (let x = 0; x < cols; x += 1) {
      const ch = rows[y][x];
      walls[y].push(ch === WALL);
      doors[y].push(ch === DOOR);
      if (ch === PELLET) pellets.add(tileKey(x, y));
      if (ch === POWER_PELLET) powerPellets.add(tileKey(x, y));
      if (ch === PLAYER_START) playerStart = { x, y };
      if (GHOST_STARTS.includes(ch)) {
        ghostStarts[Number(ch) - 1] = { x, y };
      }
    }
  }

  if (!playerStart) throw new Error('maze is missing a player start (P)');
  if (ghostStarts.filter(Boolean).length !== 4) {
    throw new Error('maze must define four ghost starts (1-4)');
  }

  const wrapX = (x) => ((x % cols) + cols) % cols;

  const isWall = (x, y) => {
    if (y < 0 || y >= rows.length) return true;
    return walls[y][wrapX(x)];
  };

  const isDoor = (x, y) => {
    if (y < 0 || y >= rows.length) return false;
    return doors[y][wrapX(x)];
  };

  const isWalkable = (x, y, { allowDoor = false } = {}) => {
    if (isWall(x, y)) return false;
    if (!allowDoor && isDoor(x, y)) return false;
    return true;
  };

  return {
    rows,
    cols,
    width: cols,
    height: rows.length,
    playerStart,
    ghostStarts,
    walls,
    wrapX,
    isWall,
    isDoor,
    isWalkable,
    pellets,
    powerPellets,
    pelletCount: pellets.size + powerPellets.size,
  };
}

/**
 * Flood fill of tiles reachable from a start tile, honouring walls and doors.
 * Used to assert that every pellet can actually be eaten.
 */
export function reachableTiles(maze, start) {
  const seen = new Set();
  const queue = [start];
  seen.add(tileKey(start.x, start.y));
  while (queue.length > 0) {
    const { x, y } = queue.shift();
    for (const d of [
      { x: 0, y: -1 },
      { x: 0, y: 1 },
      { x: -1, y: 0 },
      { x: 1, y: 0 },
    ]) {
      const nx = maze.wrapX(x + d.x);
      const ny = y + d.y;
      if (!maze.isWalkable(nx, ny)) continue;
      const key = tileKey(nx, ny);
      if (seen.has(key)) continue;
      seen.add(key);
      queue.push({ x: nx, y: ny });
    }
  }
  return seen;
}
