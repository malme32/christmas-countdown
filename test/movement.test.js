import test from 'node:test';
import assert from 'node:assert/strict';

import { DIR, PLAYER_SPEED, UNIT } from '../src/core/constants.js';
import { createMaze } from '../src/core/maze.js';
import {
  advance,
  canTurn,
  isCentered,
  overlaps,
  sameTile,
  tileOf,
  wrapEntity,
} from '../src/core/movement.js';

const maze = createMaze();

function entityAt(x, y, dir = DIR.NONE, speed = PLAYER_SPEED) {
  return { x: x * UNIT, y: y * UNIT, dir, speed };
}

test('isCentered is true only on tile centres', () => {
  assert.equal(isCentered(entityAt(13, 23)), true);
  const off = entityAt(13, 23);
  off.x += PLAYER_SPEED;
  assert.equal(isCentered(off), false);
});

test('advance moves one step along an open corridor', () => {
  const entity = entityAt(13, 23, DIR.RIGHT);
  assert.equal(advance(entity, maze), true);
  assert.equal(entity.x, 13 * UNIT + PLAYER_SPEED);
  assert.equal(entity.y, 23 * UNIT);
});

test('advance refuses to enter a wall', () => {
  const entity = entityAt(13, 23, DIR.UP);
  assert.equal(advance(entity, maze), false);
  assert.deepEqual(tileOf(entity), { x: 13, y: 23 });
});

test('advance refuses the ghost door unless allowed', () => {
  const blocked = entityAt(13, 11, DIR.DOWN);
  assert.equal(advance(blocked, maze), false);
  const allowed = entityAt(13, 11, DIR.DOWN);
  assert.equal(advance(allowed, maze, { allowDoor: true }), true);
  assert.equal(allowed.y, 11 * UNIT + PLAYER_SPEED);
});

test('horizontal movement wraps through the tunnel', () => {
  const entity = entityAt(0, 14, DIR.LEFT);
  assert.equal(advance(entity, maze), true);
  assert.ok(entity.x > (maze.cols - 1) * UNIT);
});

test('wrapping normalises out-of-range x', () => {
  const span = maze.cols * UNIT;
  const left = { x: -1, y: 0 };
  const right = { x: span, y: 0 };
  wrapEntity(left, maze);
  wrapEntity(right, maze);
  assert.equal(left.x, span - 1);
  assert.equal(right.x, 0);
});

test('canTurn reports walkability of the next tile', () => {
  const entity = entityAt(13, 23, DIR.NONE);
  assert.equal(canTurn(entity, maze, DIR.LEFT), true);
  assert.equal(canTurn(entity, maze, DIR.UP), false);
  assert.equal(canTurn(entity, maze, DIR.NONE), false);
});

test('sameTile and overlaps compare positions', () => {
  const a = entityAt(13, 23);
  const b = entityAt(13, 23, DIR.RIGHT);
  const c = entityAt(14, 23);
  assert.equal(sameTile(a, b), true);
  assert.equal(sameTile(a, c), false);
  assert.equal(overlaps(a, b), true);
  assert.equal(overlaps(a, c), false);
});
