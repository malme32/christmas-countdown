import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEATH_TICKS,
  DIR,
  GHOST_SCORE,
  LEVEL_COMPLETE_TICKS,
  MAX_LEVELS,
  PELLET_SCORE,
  POWER_PELLET_SCORE,
  POWER_TICKS,
  READY_TICKS,
  START_LIVES,
} from '../src/core/constants.js';
import { createMaze } from '../src/core/maze.js';
import {
  createGame,
  drainEvents,
  pelletsRemaining,
  restart,
  setDirection,
  update,
} from '../src/core/game.js';

const maze = createMaze();

function playingGame(options = {}) {
  const game = createGame({ maze, ...options });
  game.status = 'playing';
  game.statusTicks = 0;
  return game;
}

function overlapPlayer(game, ghost) {
  ghost.inHouse = false;
  ghost.exiting = false;
  ghost.eaten = false;
  ghost.x = game.player.x;
  ghost.y = game.player.y;
  ghost.dir = DIR.NONE;
}

test('a new game starts ready with full pellets and lives', () => {
  const game = createGame({ maze });
  assert.equal(game.status, 'ready');
  assert.equal(game.lives, START_LIVES);
  assert.equal(game.level, 1);
  assert.equal(game.score, 0);
  assert.equal(pelletsRemaining(game), maze.pelletCount);
});

test('nothing moves during the ready countdown', () => {
  const game = createGame({ maze });
  const start = { x: game.player.x, y: game.player.y };
  setDirection(game, DIR.LEFT);
  update(game);
  assert.deepEqual({ x: game.player.x, y: game.player.y }, start);
});

test('the game becomes playable when the countdown elapses', () => {
  const game = createGame({ maze });
  for (let i = 0; i < READY_TICKS; i += 1) update(game);
  assert.equal(game.status, 'playing');
  assert.ok(drainEvents(game).includes('start'));
});

test('eating a pellet scores ten points and removes it', () => {
  const game = playingGame();
  game.pellets.add('13,23');
  update(game);
  assert.equal(game.score, PELLET_SCORE);
  assert.equal(game.pellets.has('13,23'), false);
  assert.ok(drainEvents(game).includes('chomp'));
});

test('eating a power pellet starts the frightened timer', () => {
  const game = playingGame();
  game.powerPellets.add('13,23');
  update(game);
  assert.equal(game.score, POWER_PELLET_SCORE);
  assert.ok(game.frightenedTicks > 0 && game.frightenedTicks <= POWER_TICKS);
  assert.ok(drainEvents(game).includes('power'));
});

test('eating a frightened ghost awards points and sends it home', () => {
  const game = playingGame();
  game.powerPellets.add('13,23');
  update(game);
  const ghost = game.ghosts[0];
  overlapPlayer(game, ghost);
  drainEvents(game);
  update(game);
  assert.equal(ghost.eaten, true);
  assert.ok(game.score >= POWER_PELLET_SCORE + GHOST_SCORE);
  assert.ok(drainEvents(game).includes('eatGhost'));
});

test('touching a normal ghost costs a life and resets positions', () => {
  const game = playingGame();
  overlapPlayer(game, game.ghosts[0]);
  update(game);
  assert.equal(game.status, 'dying');
  assert.ok(drainEvents(game).includes('death'));
  for (let i = 0; i < DEATH_TICKS; i += 1) update(game);
  assert.equal(game.lives, START_LIVES - 1);
  assert.equal(game.status, 'ready');
});

test('losing the last life ends the game', () => {
  const game = playingGame();
  game.lives = 1;
  overlapPlayer(game, game.ghosts[0]);
  update(game);
  for (let i = 0; i < DEATH_TICKS; i += 1) update(game);
  assert.equal(game.status, 'gameOver');
  assert.ok(drainEvents(game).includes('gameOver'));
  const frozen = { ...game.player };
  update(game);
  assert.deepEqual({ x: game.player.x, y: game.player.y }, { x: frozen.x, y: frozen.y });
});

test('clearing the board advances to the next level', () => {
  const game = playingGame();
  game.pellets = new Set();
  game.powerPellets = new Set();
  update(game);
  assert.equal(game.status, 'levelComplete');
  assert.ok(drainEvents(game).includes('levelComplete'));
  for (let i = 0; i < LEVEL_COMPLETE_TICKS; i += 1) update(game);
  assert.equal(game.level, 2);
  assert.equal(game.status, 'ready');
  assert.equal(pelletsRemaining(game), maze.pelletCount);
});

test('clearing the final level wins the game', () => {
  const game = playingGame();
  game.level = MAX_LEVELS;
  game.pellets = new Set();
  game.powerPellets = new Set();
  update(game);
  for (let i = 0; i < LEVEL_COMPLETE_TICKS; i += 1) update(game);
  assert.equal(game.status, 'won');
  assert.ok(drainEvents(game).includes('win'));
});

test('the level counter does not run past MAX_LEVELS on a win', () => {
  const game = playingGame();
  game.level = MAX_LEVELS;
  game.pellets = new Set();
  game.powerPellets = new Set();
  update(game);
  for (let i = 0; i < LEVEL_COMPLETE_TICKS; i += 1) update(game);
  assert.equal(game.status, 'won');
  assert.equal(game.level, MAX_LEVELS);
});

test('restart returns the game to its initial state', () => {
  const game = playingGame();
  game.score = 1234;
  game.lives = 1;
  game.level = 3;
  game.pellets = new Set();
  game.powerPellets = new Set();
  restart(game);
  assert.equal(game.score, 0);
  assert.equal(game.lives, START_LIVES);
  assert.equal(game.level, 1);
  assert.equal(game.status, 'ready');
  assert.equal(pelletsRemaining(game), maze.pelletCount);
});

test('the fixed-timestep simulation is deterministic for a given rng', () => {
  const run = () => {
    const game = playingGame({ rng: () => 0.5 });
    setDirection(game, DIR.LEFT);
    for (let i = 0; i < 600; i += 1) update(game);
    return game;
  };
  const first = run();
  const second = run();
  assert.equal(first.score, second.score);
  assert.deepEqual(first.player, second.player);
  assert.deepEqual(first.ghosts.map((g) => g.x), second.ghosts.map((g) => g.x));
  assert.deepEqual(first.ghosts.map((g) => g.y), second.ghosts.map((g) => g.y));
});
