import test from 'node:test';
import assert from 'node:assert/strict';

import { DIR, PLAYER_SPEED, TICK_HZ, UNIT } from '../src/core/constants.js';
import { createMaze } from '../src/core/maze.js';
import { tileOf } from '../src/core/movement.js';
import { createPlayer, setPlayerDirection, updatePlayer } from '../src/core/player.js';

const maze = createMaze();

test('createPlayer starts centred and stationary', () => {
  const player = createPlayer(maze.playerStart);
  assert.deepEqual(tileOf(player), { x: 13, y: 23 });
  assert.equal(player.dir, DIR.NONE);
  assert.equal(player.speed, PLAYER_SPEED);
});

test('a queued direction is applied at the first centre', () => {
  const player = createPlayer(maze.playerStart);
  setPlayerDirection(player, DIR.LEFT);
  updatePlayer(player, maze);
  assert.equal(player.dir, DIR.LEFT);
  assert.equal(player.x, 13 * UNIT - PLAYER_SPEED);
});

test('the player cannot turn into a wall', () => {
  const player = createPlayer(maze.playerStart);
  setPlayerDirection(player, DIR.UP);
  updatePlayer(player, maze);
  assert.equal(player.dir, DIR.NONE);
  assert.deepEqual(tileOf(player), { x: 13, y: 23 });
});

test('movement stops against a wall', () => {
  const player = createPlayer(maze.playerStart);
  setPlayerDirection(player, DIR.LEFT);
  for (let i = 0; i < TICK_HZ * 3; i += 1) updatePlayer(player, maze);
  assert.deepEqual(tileOf(player), { x: 6, y: 23 });
});

test('turns are buffered until a junction is reached', () => {
  const player = createPlayer(maze.playerStart);
  setPlayerDirection(player, DIR.LEFT);
  for (let i = 0; i < TICK_HZ * 3; i += 1) updatePlayer(player, maze);
  setPlayerDirection(player, DIR.UP);
  updatePlayer(player, maze);
  assert.equal(player.dir, DIR.UP);
});

test('reversing direction takes effect immediately mid-tile', () => {
  const player = createPlayer(maze.playerStart);
  setPlayerDirection(player, DIR.LEFT);
  updatePlayer(player, maze);
  const midTileX = player.x;
  setPlayerDirection(player, DIR.RIGHT);
  updatePlayer(player, maze);
  assert.equal(player.dir, DIR.RIGHT);
  assert.equal(player.x, midTileX + PLAYER_SPEED);
});
