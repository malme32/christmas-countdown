import { DIR, PLAYER_SPEED, UNIT, opposite } from './constants.js';
import { advance, canTurn, isCentered } from './movement.js';

export function createPlayer(start) {
  return {
    x: start.x * UNIT,
    y: start.y * UNIT,
    dir: DIR.NONE,
    nextDir: DIR.NONE,
    speed: PLAYER_SPEED,
    mouth: 0,
  };
}

export function setPlayerDirection(player, dir) {
  player.nextDir = dir;
}

/**
 * Player movement: turns are queued and applied at tile centres, while a
 * reversal of direction takes effect immediately (classic Pacman feel).
 */
export function updatePlayer(player, maze) {
  if (isCentered(player)) {
    if (canTurn(player, maze, player.nextDir)) {
      player.dir = player.nextDir;
    }
  } else if (player.nextDir === opposite(player.dir)) {
    player.dir = player.nextDir;
  }

  const moving = advance(player, maze);
  if (moving) player.mouth = (player.mouth + 1) % 4;
  return moving;
}
