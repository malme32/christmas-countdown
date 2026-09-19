import test from 'node:test';
import assert from 'node:assert/strict';

import { DIR } from '../src/core/constants.js';
import { actionForKey, createInput, directionForKey } from '../src/ui/input.js';

test('directionForKey maps arrow keys and WASD', () => {
  assert.equal(directionForKey('ArrowUp'), DIR.UP);
  assert.equal(directionForKey('ArrowDown'), DIR.DOWN);
  assert.equal(directionForKey('ArrowLeft'), DIR.LEFT);
  assert.equal(directionForKey('ArrowRight'), DIR.RIGHT);
  assert.equal(directionForKey('w'), DIR.UP);
  assert.equal(directionForKey('a'), DIR.LEFT);
  assert.equal(directionForKey('s'), DIR.DOWN);
  assert.equal(directionForKey('d'), DIR.RIGHT);
  assert.equal(directionForKey('W'), DIR.UP);
  assert.equal(directionForKey('q'), null);
});

test('actionForKey maps the control keys', () => {
  assert.equal(actionForKey('Enter'), 'start');
  assert.equal(actionForKey(' '), 'start');
  assert.equal(actionForKey('p'), 'pause');
  assert.equal(actionForKey('P'), 'pause');
  assert.equal(actionForKey('m'), 'mute');
  assert.equal(actionForKey('M'), 'mute');
  assert.equal(actionForKey('x'), null);
});

test('createInput forwards directions and actions, and detaches cleanly', () => {
  const handlers = {};
  const target = {
    addEventListener(type, handler) {
      handlers[type] = handler;
    },
    removeEventListener(type) {
      delete handlers[type];
    },
  };
  const directions = [];
  const actions = [];
  const input = createInput({
    target,
    onDirection: (dir) => directions.push(dir),
    onAction: (action) => actions.push(action),
  });

  handlers.keydown({ key: 'ArrowLeft', preventDefault() {} });
  handlers.keydown({ key: 'm', preventDefault() {} });
  assert.deepEqual(directions, [DIR.LEFT]);
  assert.deepEqual(actions, ['mute']);

  input.detach();
  assert.equal(handlers.keydown, undefined);
});
