import {
  DIR,
  DIRECTIONS,
  GHOST_SPEED,
  TICK_HZ,
  UNIT,
  opposite,
} from './constants.js';
import { advance, isCentered, tileOf } from './movement.js';

export const GHOST_DEFS = [
  { name: 'blinky', color: '#ff2b2b', scatter: { x: 25, y: 0 } },
  { name: 'pinky', color: '#ff9ee8', scatter: { x: 2, y: 0 } },
  { name: 'inky', color: '#38d9ff', scatter: { x: 27, y: 30 } },
  { name: 'clyde', color: '#ffb852', scatter: { x: 0, y: 30 } },
];

export const HOUSE_TILE = { x: 13, y: 14 };
export const EXIT_TILE = { x: 13, y: 11 };
export const RELEASE_TICKS = [0, 1 * TICK_HZ, 3 * TICK_HZ, 6 * TICK_HZ];

export function createGhosts(maze, { level = 1 } = {}) {
  return GHOST_DEFS.map((def, index) => ({
    index,
    name: def.name,
    color: def.color,
    scatter: def.scatter,
    x: maze.ghostStarts[index].x * UNIT,
    y: maze.ghostStarts[index].y * UNIT,
    dir: index === 1 ? DIR.DOWN : DIR.UP,
    speed: GHOST_SPEED,
    pendingSpeed: null,
    inHouse: true,
    exiting: false,
    eaten: false,
    releaseTick: RELEASE_TICKS[index] + (level - 1) * TICK_HZ,
  }));
}

export function ghostTarget(ghost, ctx) {
  if (ghost.eaten) return ctx.houseTile;
  if (ghost.exiting) return ctx.exitTile;
  if (ctx.mode === 'scatter') return ghost.scatter;

  const playerTile = tileOf(ctx.player);
  const dir = ctx.player.dir;

  if (ghost.index === 0) return playerTile;
  if (ghost.index === 1) {
    return { x: playerTile.x + dir.x * 4, y: playerTile.y + dir.y * 4 };
  }
  if (ghost.index === 2) {
    const ahead = { x: playerTile.x + dir.x * 2, y: playerTile.y + dir.y * 2 };
    const blinky = tileOf(ctx.ghosts[0]);
    return { x: ahead.x * 2 - blinky.x, y: ahead.y * 2 - blinky.y };
  }

  const here = tileOf(ghost);
  const distance = (playerTile.x - here.x) ** 2 + (playerTile.y - here.y) ** 2;
  return distance > 64 ? playerTile : ghost.scatter;
}

export function chooseDirection(maze, tile, currentDir, target, options = {}) {
  const {
    allowDoor = false,
    allowReverse = false,
    random = false,
    rng = Math.random,
  } = options;
  const back = opposite(currentDir);
  const walkable = (d) => maze.isWalkable(tile.x + d.x, tile.y + d.y, { allowDoor });

  let candidates = DIRECTIONS.filter((d) => (allowReverse || d !== back) && walkable(d));
  if (candidates.length === 0) {
    candidates = DIRECTIONS.filter((d) => d === back && walkable(d));
  }
  if (candidates.length === 0) return DIR.NONE;

  if (random) {
    return candidates[Math.floor(rng() * candidates.length)];
  }

  let best = candidates[0];
  let bestDistance = Infinity;
  for (const d of candidates) {
    const dx = tile.x + d.x - target.x;
    const dy = tile.y + d.y - target.y;
    const distance = dx * dx + dy * dy;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = d;
    }
  }
  return best;
}

export function updateGhost(ghost, ctx) {
  const { maze } = ctx;

  if (ghost.eaten) {
    if (isCentered(ghost)) {
      const tile = tileOf(ghost);
      if (tile.x === ctx.houseTile.x && tile.y === ctx.houseTile.y) {
        ghost.eaten = false;
        ghost.exiting = true;
        ghost.speed = GHOST_SPEED;
        ctx.events.push('ghostRevive');
      } else {
        ghost.dir = chooseDirection(maze, tile, ghost.dir, ctx.houseTile, {
          allowDoor: true,
          allowReverse: true,
        });
      }
    }
    advance(ghost, maze, { allowDoor: true });
    return;
  }

  if (ghost.inHouse && !ghost.exiting) {
    if (ctx.tick < ghost.releaseTick) return;
    ghost.exiting = true;
  }

  if (ghost.exiting) {
    if (isCentered(ghost) && tileOf(ghost).y <= ctx.exitTile.y) {
      ghost.exiting = false;
      ghost.inHouse = false;
    }
  }

  if (ghost.exiting) {
    if (isCentered(ghost)) {
      ghost.dir = chooseDirection(maze, tileOf(ghost), ghost.dir, ctx.exitTile, {
        allowDoor: true,
        allowReverse: true,
      });
    }
    advance(ghost, maze, { allowDoor: true });
    return;
  }

  const target = ghostTarget(ghost, ctx);
  if (isCentered(ghost)) {
    ghost.dir = chooseDirection(maze, tileOf(ghost), ghost.dir, target, {
      random: ctx.mode === 'frightened',
      rng: ctx.rng,
    });
  }
  advance(ghost, maze, { allowDoor: false });
}
