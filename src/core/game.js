import {
  CHASE_TICKS,
  DEATH_TICKS,
  EYES_SPEED,
  FRIGHTENED_SPEED,
  GHOST_SCORE,
  GHOST_SPEED,
  LEVEL_COMPLETE_TICKS,
  MAX_LEVELS,
  PELLET_SCORE,
  POWER_PELLET_SCORE,
  POWER_TICKS,
  READY_TICKS,
  SCATTER_TICKS,
  START_LIVES,
  opposite,
} from './constants.js';
import { tileKey } from './maze.js';
import { isCentered, overlaps, tileOf } from './movement.js';
import { createPlayer, setPlayerDirection, updatePlayer } from './player.js';
import { EXIT_TILE, HOUSE_TILE, createGhosts, updateGhost } from './ghost.js';

export function createGame({ maze, rng = Math.random } = {}) {
  if (!maze) throw new Error('createGame requires a maze');
  const game = {
    maze,
    rng,
    status: 'ready',
    statusTicks: READY_TICKS,
    tick: 0,
    score: 0,
    highScore: 0,
    lives: START_LIVES,
    level: 1,
    player: createPlayer(maze.playerStart),
    ghosts: [],
    pellets: new Set(maze.pellets),
    powerPellets: new Set(maze.powerPellets),
    frightenedTicks: 0,
    ghostEatChain: 0,
    globalMode: 'scatter',
    modeTicks: SCATTER_TICKS,
    events: [],
  };
  game.ghosts = createGhosts(maze, { level: game.level });
  return game;
}

export function setDirection(game, dir) {
  setPlayerDirection(game.player, dir);
}

export function drainEvents(game) {
  const events = game.events.slice();
  game.events.length = 0;
  return events;
}

function reverse(ghost) {
  ghost.dir = opposite(ghost.dir);
}

function resetPositions(game) {
  game.player = createPlayer(game.maze.playerStart);
  game.ghosts = createGhosts(game.maze, { level: game.level });
  game.frightenedTicks = 0;
  game.ghostEatChain = 0;
  game.globalMode = 'scatter';
  game.modeTicks = SCATTER_TICKS;
  game.status = 'ready';
  game.statusTicks = READY_TICKS;
}

function consumePellet(game) {
  const player = game.player;
  if (!isCentered(player)) return;
  const tile = tileOf(player);
  const key = tileKey(tile.x, tile.y);
  if (game.pellets.delete(key)) {
    game.score += PELLET_SCORE;
    game.events.push('chomp');
    return;
  }
  if (game.powerPellets.delete(key)) {
    game.score += POWER_PELLET_SCORE;
    game.frightenedTicks = POWER_TICKS;
    game.ghostEatChain = 0;
    game.events.push('power');
    for (const ghost of game.ghosts) {
      if (!ghost.eaten && !ghost.inHouse) reverse(ghost);
    }
  }
}

function updateModes(game) {
  if (game.frightenedTicks > 0) game.frightenedTicks -= 1;
  game.modeTicks -= 1;
  if (game.modeTicks > 0) return;
  game.globalMode = game.globalMode === 'scatter' ? 'chase' : 'scatter';
  game.modeTicks = game.globalMode === 'scatter' ? SCATTER_TICKS : CHASE_TICKS;
  if (game.frightenedTicks === 0) {
    for (const ghost of game.ghosts) {
      if (!ghost.eaten && !ghost.inHouse) reverse(ghost);
    }
  }
}

function ghostContext(game) {
  return {
    maze: game.maze,
    tick: game.tick,
    mode: game.frightenedTicks > 0 ? 'frightened' : game.globalMode,
    player: game.player,
    ghosts: game.ghosts,
    houseTile: HOUSE_TILE,
    exitTile: EXIT_TILE,
    rng: game.rng,
    events: game.events,
  };
}

function checkCollisions(game) {
  for (const ghost of game.ghosts) {
    if (ghost.inHouse || ghost.eaten) continue;
    if (!overlaps(game.player, ghost)) continue;

    if (game.frightenedTicks > 0) {
      ghost.eaten = true;
      const points = GHOST_SCORE * 2 ** game.ghostEatChain;
      game.ghostEatChain += 1;
      game.score += points;
      game.events.push('eatGhost');
      return;
    }

    game.events.push('death');
    game.status = 'dying';
    game.statusTicks = DEATH_TICKS;
    return;
  }
}

function afterDeath(game) {
  game.lives -= 1;
  if (game.lives <= 0) {
    game.status = 'gameOver';
    game.events.push('gameOver');
    return;
  }
  resetPositions(game);
}

function nextLevel(game) {
  if (game.level >= MAX_LEVELS) {
    game.status = 'won';
    game.events.push('win');
    return;
  }
  game.level += 1;
  game.pellets = new Set(game.maze.pellets);
  game.powerPellets = new Set(game.maze.powerPellets);
  resetPositions(game);
}

export function desiredGhostSpeed(game, ghost) {
  if (ghost.eaten) return EYES_SPEED;
  return game.frightenedTicks > 0 ? FRIGHTENED_SPEED : GHOST_SPEED;
}

/**
 * Speed may only change on a tile centre. Every speed is an exact divisor of
 * UNIT, so an entity starting on a centre keeps landing on centres; switching
 * speed part-way through a tile would leave it off the grid and advance()
 * (which only checks walls when centred) would let it phase through walls.
 */
export function applyGhostSpeed(game, ghost) {
  const desired = desiredGhostSpeed(game, ghost);
  if (isCentered(ghost)) {
    ghost.speed = desired;
    ghost.pendingSpeed = null;
  } else {
    ghost.pendingSpeed = desired;
  }
}

export function update(game) {
  game.tick += 1;

  if (game.status === 'ready') {
    game.statusTicks -= 1;
    if (game.statusTicks <= 0) {
      game.status = 'playing';
      game.events.push('start');
    }
    return;
  }
  if (game.status === 'dying') {
    game.statusTicks -= 1;
    if (game.statusTicks <= 0) afterDeath(game);
    return;
  }
  if (game.status === 'levelComplete') {
    game.statusTicks -= 1;
    if (game.statusTicks <= 0) nextLevel(game);
    return;
  }
  if (game.status !== 'playing') return;

  updatePlayer(game.player, game.maze);
  consumePellet(game);
  updateModes(game);

  const ctx = ghostContext(game);
  for (const ghost of game.ghosts) {
    applyGhostSpeed(game, ghost);
    updateGhost(ghost, ctx);
  }

  checkCollisions(game);

  if (game.status === 'playing' && game.pellets.size === 0 && game.powerPellets.size === 0) {
    game.status = 'levelComplete';
    game.statusTicks = LEVEL_COMPLETE_TICKS;
    game.events.push('levelComplete');
  }
}

export function restart(game) {
  game.score = 0;
  game.lives = START_LIVES;
  game.level = 1;
  game.tick = 0;
  game.pellets = new Set(game.maze.pellets);
  game.powerPellets = new Set(game.maze.powerPellets);
  resetPositions(game);
}

export function pelletsRemaining(game) {
  return game.pellets.size + game.powerPellets.size;
}
