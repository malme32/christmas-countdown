import test from 'node:test';
import assert from 'node:assert/strict';

import { COLS, ROWS } from '../src/core/constants.js';
import { createMaze, MAZE_ROWS, reachableTiles, tileKey } from '../src/core/maze.js';

test('maze has the expected 28x31 geometry', () => {
  const maze = createMaze();
  assert.equal(maze.cols, COLS);
  assert.equal(maze.height, ROWS);
  assert.equal(MAZE_ROWS.length, ROWS);
  for (const row of MAZE_ROWS) {
    assert.equal(row.length, COLS);
  }
});

test('maze rejects malformed layouts', () => {
  assert.throws(() => createMaze(MAZE_ROWS.slice(1)), /31 rows/);
  const tooNarrow = MAZE_ROWS.map((row) => `${row.slice(0, 27)}`);
  assert.throws(() => createMaze(tooNarrow), /28x31/);
});

test('maze exposes player start, four ghost starts and pellets', () => {
  const maze = createMaze();
  assert.deepEqual(maze.playerStart, { x: 13, y: 23 });
  assert.equal(maze.ghostStarts.filter(Boolean).length, 4);
  assert.equal(maze.powerPellets.size, 4);
  assert.ok(maze.pellets.size > 200);
  assert.equal(maze.pelletCount, maze.pellets.size + maze.powerPellets.size);
});

test('every pellet is reachable from the player start', () => {
  const maze = createMaze();
  const reachable = reachableTiles(maze, maze.playerStart);
  for (const key of maze.pellets) {
    assert.ok(reachable.has(key), `pellet ${key} is unreachable`);
  }
  for (const key of maze.powerPellets) {
    assert.ok(reachable.has(key), `power pellet ${key} is unreachable`);
  }
});

test('walls and the ghost door block movement by default', () => {
  const maze = createMaze();
  assert.equal(maze.isWall(0, 0), true);
  assert.equal(maze.isWalkable(0, 0), false);
  assert.equal(maze.isWalkable(13, 12), false);
  assert.equal(maze.isWalkable(13, 12, { allowDoor: true }), true);
});

test('horizontal wrapping joins the tunnel edges', () => {
  const maze = createMaze();
  assert.equal(maze.wrapX(-1), COLS - 1);
  assert.equal(maze.wrapX(COLS), 0);
  assert.equal(maze.isWalkable(-1, 14), true);
  assert.equal(maze.isWalkable(COLS, 14), true);
});

test('tileKey is stable', () => {
  assert.equal(tileKey(13, 23), '13,23');
});
