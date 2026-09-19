export const COLS = 28;
export const ROWS = 31;

export const UNIT = 120;
export const TICK_HZ = 60;
export const TICK_MS = 1000 / TICK_HZ;

export const START_LIVES = 3;
export const MAX_LEVELS = 5;

export const PELLET_SCORE = 10;
export const POWER_PELLET_SCORE = 50;
export const GHOST_SCORE = 200;

export const POWER_TICKS = 6 * TICK_HZ;
export const FLASH_TICKS = 2 * TICK_HZ;
export const READY_TICKS = 2 * TICK_HZ;
export const DEATH_TICKS = 1.5 * TICK_HZ;
export const LEVEL_COMPLETE_TICKS = 2 * TICK_HZ;

export const SCATTER_TICKS = 7 * TICK_HZ;
export const CHASE_TICKS = 20 * TICK_HZ;

export const PLAYER_SPEED = UNIT / 8;
export const GHOST_SPEED = UNIT / 10;
export const FRIGHTENED_SPEED = UNIT / 15;
export const EYES_SPEED = UNIT / 5;

export const DIR = {
  NONE: { x: 0, y: 0, name: 'none' },
  UP: { x: 0, y: -1, name: 'up' },
  DOWN: { x: 0, y: 1, name: 'down' },
  LEFT: { x: -1, y: 0, name: 'left' },
  RIGHT: { x: 1, y: 0, name: 'right' },
};

export const DIRECTIONS = [DIR.UP, DIR.LEFT, DIR.DOWN, DIR.RIGHT];

export function opposite(dir) {
  return DIRECTIONS.find((d) => d.x === -dir.x && d.y === -dir.y) || DIR.NONE;
}
