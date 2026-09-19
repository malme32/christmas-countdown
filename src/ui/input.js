import { DIR } from '../core/constants.js';

const DIRECTION_KEYS = {
  ArrowUp: DIR.UP,
  ArrowDown: DIR.DOWN,
  ArrowLeft: DIR.LEFT,
  ArrowRight: DIR.RIGHT,
  w: DIR.UP,
  W: DIR.UP,
  s: DIR.DOWN,
  S: DIR.DOWN,
  a: DIR.LEFT,
  A: DIR.LEFT,
  d: DIR.RIGHT,
  D: DIR.RIGHT,
};

/** Pure key -> direction mapping; returns null for keys that are not movement. */
export function directionForKey(key) {
  return DIRECTION_KEYS[key] || null;
}

/** Pure key -> action mapping for the non-movement controls. */
export function actionForKey(key) {
  if (key === 'Enter' || key === ' ') return 'start';
  if (key === 'p' || key === 'P') return 'pause';
  if (key === 'm' || key === 'M') return 'mute';
  return null;
}

const PREVENT_DEFAULT = new Set([
  'ArrowUp',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  ' ',
]);

export function createInput({ target = globalThis, onDirection, onAction } = {}) {
  const handleKeyDown = (event) => {
    const direction = directionForKey(event.key);
    if (direction) {
      if (PREVENT_DEFAULT.has(event.key) && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }
      if (onDirection) onDirection(direction);
      return;
    }
    const action = actionForKey(event.key);
    if (action) {
      if (PREVENT_DEFAULT.has(event.key) && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }
      if (onAction) onAction(action);
    }
  };

  target.addEventListener('keydown', handleKeyDown);
  return {
    detach() {
      target.removeEventListener('keydown', handleKeyDown);
    },
  };
}
