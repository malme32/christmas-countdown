import { UNIT } from './constants.js';

export function isCentered(entity) {
  return entity.x % UNIT === 0 && entity.y % UNIT === 0;
}

export function tileOf(entity) {
  return { x: entity.x / UNIT, y: entity.y / UNIT };
}

export function pixelOf(entity) {
  return { x: entity.x / UNIT, y: entity.y / UNIT };
}

export function wrapEntity(entity, maze) {
  const span = maze.cols * UNIT;
  if (entity.x < 0) entity.x += span;
  else if (entity.x >= span) entity.x -= span;
}

/** Move one fixed tick in the entity's current direction, stopping at walls. */
export function advance(entity, maze, { allowDoor = false } = {}) {
  if (!entity.dir || (entity.dir.x === 0 && entity.dir.y === 0)) return false;
  if (isCentered(entity)) {
    const tile = tileOf(entity);
    if (!maze.isWalkable(tile.x + entity.dir.x, tile.y + entity.dir.y, { allowDoor })) {
      return false;
    }
  }
  entity.x += entity.dir.x * entity.speed;
  entity.y += entity.dir.y * entity.speed;
  wrapEntity(entity, maze);
  return true;
}

export function canTurn(entity, maze, dir, allowDoor = false) {
  if (!dir || (dir.x === 0 && dir.y === 0)) return false;
  const tile = tileOf(entity);
  return maze.isWalkable(tile.x + dir.x, tile.y + dir.y, { allowDoor });
}

export function sameTile(a, b) {
  return Math.round(a.x / UNIT) === Math.round(b.x / UNIT)
    && Math.round(a.y / UNIT) === Math.round(b.y / UNIT);
}

export function overlaps(a, b) {
  return Math.abs(a.x - b.x) < UNIT * 0.5 && Math.abs(a.y - b.y) < UNIT * 0.5;
}
