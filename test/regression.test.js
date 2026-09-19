import test from 'node:test';
import assert from 'node:assert/strict';

import {
  COLS,
  DIR,
  EYES_SPEED,
  FRIGHTENED_SPEED,
  GHOST_SPEED,
  PLAYER_SPEED,
  ROWS,
  UNIT,
} from '../src/core/constants.js';
import { createMaze } from '../src/core/maze.js';
import {
  applyGhostSpeed,
  createGame,
  restart,
  setDirection,
  update,
} from '../src/core/game.js';
import { isCentered, tileOf } from '../src/core/movement.js';

const maze = createMaze();

function playingGame(options = {}) {
  const game = createGame({ maze, ...options });
  game.status = 'playing';
  game.statusTicks = 0;
  return game;
}

function seededRng(seed) {
  let state = seed;
  return () => {
    state = (state * 1103515245 + 12345) & 0x7fffffff;
    return state / 0x7fffffff;
  };
}

test('every movement speed is an exact divisor of UNIT', () => {
  for (const speed of [PLAYER_SPEED, GHOST_SPEED, FRIGHTENED_SPEED, EYES_SPEED]) {
    assert.equal(UNIT % speed, 0, `speed ${speed} does not divide ${UNIT}`);
  }
});

test('ghost speed changes are deferred until the next tile centre', () => {
  const game = playingGame();
  const ghost = game.ghosts[0];
  ghost.inHouse = false;
  ghost.exiting = false;
  ghost.dir = DIR.UP;
  ghost.x = 1 * UNIT;
  ghost.y = 6 * UNIT;
  ghost.speed = GHOST_SPEED;

  for (let i = 0; i < 3; i += 1) update(game);
  assert.equal(isCentered(ghost), false);

  game.frightenedTicks = 3 * 60;
  applyGhostSpeed(game, ghost);
  assert.equal(ghost.speed, GHOST_SPEED);
  assert.equal(ghost.pendingSpeed, FRIGHTENED_SPEED);

  let applied = false;
  let appliedAtCentre = false;
  for (let i = 0; i < 80 && !applied; i += 1) {
    const centredBeforeUpdate = isCentered(ghost);
    update(game);
    if (ghost.speed === FRIGHTENED_SPEED) {
      applied = true;
      appliedAtCentre = centredBeforeUpdate;
    }
  }
  assert.equal(applied, true);
  assert.equal(appliedAtCentre, true);
  assert.equal(ghost.pendingSpeed, null);
});

test('a ghost eaten mid-tile re-centres instead of being stranded off-grid', () => {
  const game = playingGame();
  const ghost = game.ghosts[0];
  ghost.inHouse = false;
  ghost.exiting = false;
  ghost.dir = DIR.UP;
  ghost.x = 1 * UNIT;
  ghost.y = 6 * UNIT;
  ghost.speed = GHOST_SPEED;

  for (let i = 0; i < 3; i += 1) update(game);
  assert.equal(isCentered(ghost), false);

  ghost.eaten = true;
  let recentred = false;
  for (let i = 0; i < 40 && !recentred; i += 1) {
    update(game);
    recentred = isCentered(ghost);
  }
  assert.equal(recentred, true);
  assert.ok(ghost.y >= 0);
});

test('an eaten ghost reaches the house and revives from every walkable tile', () => {
  let checked = 0;
  for (let y = 0; y < ROWS; y += 1) {
    for (let x = 0; x < COLS; x += 1) {
      if (!maze.isWalkable(x, y)) continue;
      checked += 1;

      const game = playingGame();
      const ghost = game.ghosts[0];
      game.ghosts = [ghost];
      ghost.inHouse = false;
      ghost.exiting = false;
      ghost.eaten = true;
      ghost.x = x * UNIT;
      ghost.y = y * UNIT;
      ghost.dir = DIR.UP;

      let revived = false;
      for (let i = 0; i < 600 && !revived; i += 1) {
        update(game);
        revived = !ghost.eaten;
      }
      assert.ok(revived, `eaten ghost from (${x},${y}) never revived`);
      assert.ok(game.events.includes('ghostRevive'), `no ghostRevive event from (${x},${y})`);
    }
  }
  assert.ok(checked > 300, `expected many walkable tiles, checked ${checked}`);
});

test('a mid-tile frightened transition cannot push a ghost through a wall', () => {
  const game = playingGame();
  const ghost = game.ghosts[0];
  ghost.inHouse = false;
  ghost.exiting = false;
  ghost.dir = DIR.UP;
  ghost.x = 1 * UNIT;
  ghost.y = 6 * UNIT;
  ghost.speed = GHOST_SPEED;

  for (let i = 0; i < 3; i += 1) update(game);
  game.frightenedTicks = 3 * 60;

  let minY = ghost.y;
  for (let i = 0; i < 600; i += 1) {
    update(game);
    minY = Math.min(minY, ghost.y);
  }
  assert.ok(minY >= 0, `ghost escaped the maze to y=${minY}`);
  assert.ok(ghost.y >= 0 && ghost.y <= (ROWS - 1) * UNIT);
});

test('seeded random play keeps entities on the grid and inside the maze', () => {
  const rng = seededRng(28);
  const game = playingGame({ rng });
  const directions = [DIR.UP, DIR.DOWN, DIR.LEFT, DIR.RIGHT, DIR.NONE];
  const offGrid = game.ghosts.map(() => 0);

  for (let i = 0; i < 30000; i += 1) {
    if (i % 5 === 0) setDirection(game, directions[Math.floor(rng() * directions.length)]);
    update(game);
    if (game.status === 'won' || game.status === 'gameOver') restart(game);

    const playerTile = tileOf(game.player);
    assert.ok(
      playerTile.x >= 0 && playerTile.x < COLS && playerTile.y >= 0 && playerTile.y < ROWS,
      `player left the maze at ${playerTile.x},${playerTile.y}`,
    );

    for (let g = 0; g < game.ghosts.length; g += 1) {
      const ghost = game.ghosts[g];
      const tile = tileOf(ghost);
      assert.ok(
        tile.x >= 0 && tile.x < COLS && tile.y >= 0 && tile.y < ROWS,
        `ghost ${ghost.name} left the maze at ${tile.x},${tile.y}`,
      );
      if (game.status !== 'playing') {
        offGrid[g] = 0;
      } else {
        offGrid[g] = isCentered(ghost) ? 0 : offGrid[g] + 1;
        assert.ok(
          offGrid[g] <= 40,
          `ghost ${ghost.name} stayed off-grid for ${offGrid[g]} ticks`,
        );
      }
    }
  }
});
