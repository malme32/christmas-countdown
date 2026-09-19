import { TICK_MS } from './core/constants.js';
import { createGame, drainEvents, restart, setDirection, update } from './core/game.js';
import { createMaze } from './core/maze.js';
import { createAudio } from './ui/audio.js';
import { createInput } from './ui/input.js';
import { draw } from './ui/render.js';

const TILE_SIZE = 24;
const EXTRA_LIFE_EVERY = 10000;
const HIGH_SCORE_KEY = 'pacman.highScore';

function byId(id) {
  return document.getElementById(id);
}

function readHighScore() {
  try {
    const value = Number(globalThis.localStorage?.getItem(HIGH_SCORE_KEY));
    return Number.isFinite(value) && value > 0 ? value : 0;
  } catch {
    return 0;
  }
}

function writeHighScore(value) {
  try {
    globalThis.localStorage?.setItem(HIGH_SCORE_KEY, String(value));
  } catch {
    // Storage can be unavailable (private mode); the score still shows in-session.
  }
}

function bootstrap() {
  const maze = createMaze();
  const game = createGame({ maze });
  game.highScore = readHighScore();
  const canvas = byId('board');
  canvas.width = maze.cols * TILE_SIZE;
  canvas.height = maze.height * TILE_SIZE;
  const ctx = canvas.getContext('2d');

  const audio = createAudio();
  const scoreEl = byId('score');
  const highEl = byId('high-score');
  const livesEl = byId('lives');
  const levelEl = byId('level');
  const overlay = byId('overlay');

  let paused = false;
  let accumulator = 0;
  let lastTime = 0;
  let nextExtraLife = EXTRA_LIFE_EVERY;

  const applyAction = (action) => {
    audio.resume();
    if (action === 'mute') {
      const muted = audio.toggleMuted();
      byId('mute').textContent = muted ? 'Muted (M)' : 'Sound on (M)';
      return;
    }
    if (action === 'pause') {
      if (game.status === 'playing' || paused) paused = !paused;
      return;
    }
    if (action === 'start' && (game.status === 'gameOver' || game.status === 'won')) {
      restart(game);
      nextExtraLife = EXTRA_LIFE_EVERY;
    }
  };

  createInput({
    onDirection: (dir) => {
      audio.resume();
      setDirection(game, dir);
    },
    onAction: applyAction,
  });
  byId('mute').addEventListener('click', () => applyAction('mute'));

  const trackHighScore = () => {
    if (game.score > game.highScore) {
      game.highScore = game.score;
      writeHighScore(game.highScore);
    }
  };

  const updateHud = () => {
    scoreEl.textContent = String(game.score).padStart(6, '0');
    highEl.textContent = String(game.highScore).padStart(6, '0');
    livesEl.textContent = String(Math.max(game.lives, 0));
    levelEl.textContent = String(game.level);
  };

  const updateOverlay = () => {
    if (game.status === 'gameOver') {
      overlay.textContent = 'GAME OVER - press Enter to play again';
      overlay.hidden = false;
    } else if (game.status === 'won') {
      overlay.textContent = 'YOU WIN! - press Enter to play again';
      overlay.hidden = false;
    } else if (paused) {
      overlay.textContent = 'PAUSED - press P to resume';
      overlay.hidden = false;
    } else if (game.status === 'ready') {
      overlay.textContent = 'READY!';
      overlay.hidden = false;
    } else {
      overlay.hidden = true;
    }
  };

  const playEvents = () => {
    for (const event of drainEvents(game)) {
      if (event === 'chomp' && game.tick % 3 !== 0) continue;
      audio.play(event);
    }
    while (game.score >= nextExtraLife) {
      game.lives += 1;
      nextExtraLife += EXTRA_LIFE_EVERY;
      audio.play('extraLife');
    }
    trackHighScore();
  };

  const frame = (time) => {
    if (!lastTime) lastTime = time;
    const delta = Math.min(time - lastTime, 250);
    lastTime = time;

    if (!paused) {
      accumulator += delta;
      let steps = 0;
      while (accumulator >= TICK_MS && steps < 8) {
        update(game);
        playEvents();
        accumulator -= TICK_MS;
        steps += 1;
      }
      if (steps === 0 && accumulator > TICK_MS * 8) accumulator = 0;
    }

    draw(ctx, game, { tileSize: TILE_SIZE });
    updateHud();
    updateOverlay();
    requestAnimationFrame(frame);
  };

  updateHud();
  updateOverlay();
  requestAnimationFrame(frame);
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
}
