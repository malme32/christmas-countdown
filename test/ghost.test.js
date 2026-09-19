import test from 'node:test';
import assert from 'node:assert/strict';

import { DIR, TICK_HZ, UNIT } from '../src/core/constants.js';
import { createMaze } from '../src/core/maze.js';
import { isCentered, tileOf } from '../src/core/movement.js';
import { createPlayer } from '../src/core/player.js';
import {
  EXIT_TILE,
  HOUSE_TILE,
  chooseDirection,
  createGhosts,
  ghostTarget,
  updateGhost,
} from '../src/core/ghost.js';

const maze = createMaze();

function context(overrides = {}) {
  const ghosts = createGhosts(maze);
  return {
    maze,
    tick: 0,
    mode: 'chase',
    player: createPlayer(maze.playerStart),
    ghosts,
    houseTile: HOUSE_TILE,
    exitTile: EXIT_TILE,
    rng: () => 0,
    events: [],
    ...overrides,
  };
}

test('createGhosts builds four distinct ghosts inside the house', () => {
  const ghosts = createGhosts(maze);
  assert.equal(ghosts.length, 4);
  assert.deepEqual(ghosts.map((g) => g.name), ['blinky', 'pinky', 'inky', 'clyde']);
  for (const ghost of ghosts) {
    assert.equal(ghost.inHouse, true);
    assert.deepEqual(tileOf(ghost), maze.ghostStarts[ghost.index]);
  }
});

test('scatter targets each ghost corner', () => {
  const ghosts = createGhosts(maze);
  const ctx = context({ ghosts, mode: 'scatter' });
  assert.deepEqual(ghostTarget(ghosts[0], ctx), { x: 25, y: 0 });
  assert.deepEqual(ghostTarget(ghosts[3], ctx), { x: 0, y: 30 });
});

test('chase targets follow the classic algorithms', () => {
  const ghosts = createGhosts(maze);
  const player = createPlayer(maze.playerStart);
  player.dir = DIR.RIGHT;
  const ctx = context({ ghosts, player, mode: 'chase' });
  assert.deepEqual(ghostTarget(ghosts[0], ctx), { x: 13, y: 23 });
  assert.deepEqual(ghostTarget(ghosts[1], ctx), { x: 17, y: 23 });
  const blinky = tileOf(ghosts[0]);
  assert.deepEqual(ghostTarget(ghosts[2], ctx), {
    x: 2 * (13 + 2) - blinky.x,
    y: 2 * (23) - blinky.y,
  });
});

test('clyde switches between chase and scatter by distance', () => {
  const ghosts = createGhosts(maze);
  const player = createPlayer(maze.playerStart);
  const ctx = context({ ghosts, player, mode: 'chase' });
  ghosts[3].x = 13 * UNIT;
  ghosts[3].y = 23 * UNIT;
  assert.deepEqual(ghostTarget(ghosts[3], ctx), ghosts[3].scatter);
  ghosts[3].x = 3 * UNIT;
  ghosts[3].y = 2 * UNIT;
  assert.deepEqual(ghostTarget(ghosts[3], ctx), { x: 13, y: 23 });
});

test('chooseDirection never reverses unless allowed and picks the shortest path', () => {
  const junction = { x: 6, y: 23 };
  assert.equal(chooseDirection(maze, junction, DIR.RIGHT, { x: 6, y: 20 }), DIR.UP);
  assert.equal(
    chooseDirection(maze, junction, DIR.UP, { x: 6, y: 24 }, { allowReverse: true }),
    DIR.DOWN,
  );
});

test('chooseDirection with random uses the injected rng', () => {
  const tile = { x: 13, y: 23 };
  const first = chooseDirection(maze, tile, DIR.NONE, null, { random: true, rng: () => 0 });
  const last = chooseDirection(maze, tile, DIR.NONE, null, { random: true, rng: () => 0.999 });
  assert.equal(first, DIR.LEFT);
  assert.equal(last, DIR.RIGHT);
});

test('ghosts leave the house after their release tick', () => {
  const ghosts = createGhosts(maze);
  const ctx = context({ ghosts, tick: 0, rng: () => 0 });
  const blinky = ghosts[0];
  for (let i = 0; i < TICK_HZ * 4; i += 1) {
    ctx.tick = i;
    updateGhost(blinky, ctx);
  }
  assert.equal(blinky.inHouse, false);
  assert.equal(blinky.exiting, false);
  assert.notDeepEqual(tileOf(blinky), maze.ghostStarts[0]);
});

test('an eaten ghost returns home and revives', () => {
  const ghosts = createGhosts(maze);
  const ctx = context({ ghosts, tick: 0, rng: () => 0 });
  const ghost = ghosts[0];
  ghost.inHouse = false;
  ghost.exiting = false;
  ghost.eaten = true;
  ghost.x = 13 * UNIT;
  ghost.y = 11 * UNIT;
  ghost.dir = DIR.DOWN;
  for (let i = 0; i < TICK_HZ * 4 && ghost.eaten; i += 1) {
    updateGhost(ghost, ctx);
  }
  assert.equal(ghost.eaten, false);
  assert.equal(ghost.exiting, true);
  for (let i = 0; i < TICK_HZ * 6 && ghost.exiting; i += 1) {
    updateGhost(ghost, ctx);
  }
  assert.equal(ghost.exiting, false);
  assert.equal(ghost.inHouse, false);
  assert.ok(ctx.events.includes('ghostRevive'));
});
