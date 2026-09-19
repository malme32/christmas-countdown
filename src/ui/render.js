import { DIR, FLASH_TICKS, UNIT } from '../core/constants.js';
import { tileOf } from '../core/movement.js';

const WALL_COLOR = '#1f2fff';
const WALL_INNER = '#0a0a4a';
const PELLET_COLOR = '#ffd9b3';
const POWER_COLOR = '#ffe600';
const PLAYER_COLOR = '#ffe600';
const FRIGHTENED_COLOR = '#2121de';
const FRIGHTENED_FLASH = '#ffffff';

function center(entity, tileSize) {
  return {
    x: (entity.x / UNIT) * tileSize + tileSize / 2,
    y: (entity.y / UNIT) * tileSize + tileSize / 2,
  };
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function drawWalls(ctx, maze, tileSize) {
  for (let y = 0; y < maze.height; y += 1) {
    for (let x = 0; x < maze.cols; x += 1) {
      if (!maze.isWall(x, y)) continue;
      roundRect(ctx, x * tileSize + 0.5, y * tileSize + 0.5, tileSize - 1, tileSize - 1, 3);
      ctx.fillStyle = WALL_COLOR;
      ctx.fill();
      roundRect(ctx, x * tileSize + 3, y * tileSize + 3, tileSize - 6, tileSize - 6, 2);
      ctx.fillStyle = WALL_INNER;
      ctx.fill();
    }
  }
}

function drawPellets(ctx, game, tileSize) {
  ctx.fillStyle = PELLET_COLOR;
  for (const key of game.pellets) {
    const [x, y] = key.split(',').map(Number);
    ctx.beginPath();
    ctx.arc(x * tileSize + tileSize / 2, y * tileSize + tileSize / 2, tileSize * 0.09, 0, Math.PI * 2);
    ctx.fill();
  }
  const blink = Math.floor(game.tick / 12) % 2 === 0;
  ctx.fillStyle = POWER_COLOR;
  for (const key of game.powerPellets) {
    const [x, y] = key.split(',').map(Number);
    const radius = tileSize * (blink ? 0.24 : 0.19);
    ctx.beginPath();
    ctx.arc(x * tileSize + tileSize / 2, y * tileSize + tileSize / 2, radius, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawPlayer(ctx, player, tileSize) {
  const { x, y } = center(player, tileSize);
  const radius = tileSize * 0.42;
  const mouth = (player.mouth % 4) / 4;
  const base = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }[player.dir.name] ?? 0;
  const spread = 0.05 + mouth * 0.35;
  ctx.fillStyle = PLAYER_COLOR;
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.arc(x, y, radius, base + spread, base - spread + Math.PI * 2);
  ctx.closePath();
  ctx.fill();
}

function drawGhostBody(ctx, ctxColor, x, y, tileSize) {
  const radius = tileSize * 0.4;
  ctx.fillStyle = ctxColor;
  ctx.beginPath();
  ctx.arc(x, y - radius * 0.1, radius, Math.PI, 0);
  ctx.lineTo(x + radius, y + radius);
  const waves = 3;
  const step = (radius * 2) / waves;
  for (let i = 0; i < waves; i += 1) {
    const bx = x + radius - step * (i + 0.5);
    ctx.lineTo(bx, y + radius * 0.6);
    ctx.lineTo(bx - step / 2, y + radius);
  }
  ctx.closePath();
  ctx.fill();
  return { radius };
}

function drawEyes(ctx, x, y, tileSize, direction) {
  const eye = tileSize * 0.13;
  const pupil = eye * 0.55;
  const dx = direction.x * eye * 0.5;
  const dy = direction.y * eye * 0.5;
  for (const side of [-1, 1]) {
    const ex = x + side * tileSize * 0.15;
    const ey = y - tileSize * 0.05;
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(ex, ey, eye, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#1515b5';
    ctx.beginPath();
    ctx.arc(ex + dx, ey + dy, pupil, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawGhost(ctx, ghost, game, tileSize) {
  const { x, y } = center(ghost, tileSize);
  if (ghost.eaten) {
    drawEyes(ctx, x, y, tileSize, ghost.dir);
    return;
  }
  if (game.frightenedTicks > 0) {
    const flashing = game.frightenedTicks < FLASH_TICKS && Math.floor(game.tick / 8) % 2 === 0;
    drawGhostBody(ctx, flashing ? FRIGHTENED_FLASH : FRIGHTENED_COLOR, x, y, tileSize);
    ctx.fillStyle = flashing ? '#ff2b2b' : '#ffffff';
    for (const side of [-1, 1]) {
      ctx.beginPath();
      ctx.arc(x + side * tileSize * 0.15, y - tileSize * 0.05, tileSize * 0.06, 0, Math.PI * 2);
      ctx.fill();
    }
    return;
  }
  drawGhostBody(ctx, ghost.color, x, y, tileSize);
  drawEyes(ctx, x, y, tileSize, ghost.dir);
}

export function draw(ctx, game, { tileSize = 24 } = {}) {
  const width = game.maze.cols * tileSize;
  const height = game.maze.height * tileSize;
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, width, height);
  drawWalls(ctx, game.maze, tileSize);
  drawPellets(ctx, game, tileSize);
  drawPlayer(ctx, game.player, tileSize);
  for (const ghost of game.ghosts) {
    drawGhost(ctx, ghost, game, tileSize);
  }
}
