import test from 'node:test';
import assert from 'node:assert/strict';

import { CUES, createAudio, cueFor } from '../src/ui/audio.js';

test('cueFor returns a synthesisable descriptor for every known event', () => {
  for (const event of Object.keys(CUES)) {
    const cue = cueFor(event);
    assert.equal(cue.name, event);
    assert.equal(typeof cue.type, 'string');
    assert.ok(cue.frequency > 0);
    assert.ok(cue.duration > 0);
    assert.ok(cue.gain > 0 && cue.gain <= 1);
  }
});

test('cueFor rejects unknown events', () => {
  assert.throws(() => cueFor('nope'), /unknown audio event/);
});

test('createAudio is inert when Web Audio is unavailable', () => {
  const audio = createAudio({ AudioContextClass: null });
  assert.equal(audio.play('chomp'), false);
  assert.equal(audio.muted, false);
  assert.equal(audio.toggleMuted(), true);
  assert.equal(audio.play('chomp'), false);
});

class FakeParam {
  constructor() {
    this.calls = [];
  }

  setValueAtTime(...args) {
    this.calls.push(['setValueAtTime', ...args]);
  }

  linearRampToValueAtTime(...args) {
    this.calls.push(['linearRampToValueAtTime', ...args]);
  }

  exponentialRampToValueAtTime(...args) {
    this.calls.push(['exponentialRampToValueAtTime', ...args]);
  }
}

class FakeContext {
  constructor() {
    this.currentTime = 0;
    this.state = 'running';
    this.destination = {};
    this.oscillators = [];
    this.gains = [];
  }

  createOscillator() {
    const oscillator = { type: '', frequency: new FakeParam(), connect() {}, start() {}, stop() {} };
    this.oscillators.push(oscillator);
    return oscillator;
  }

  createGain() {
    const gain = { gain: new FakeParam(), connect() {} };
    this.gains.push(gain);
    return gain;
  }

  resume() {
    this.resumed = true;
  }
}

test('createAudio synthesises a cue through the audio graph', () => {
  const audio = createAudio({ AudioContextClass: FakeContext, muted: false });
  assert.equal(audio.play('power'), true);
  assert.equal(audio.muted, false);
});

test('muting suppresses playback', () => {
  let created = 0;
  class CountingContext extends FakeContext {
    constructor() {
      super();
      created += 1;
    }
  }
  const audio = createAudio({ AudioContextClass: CountingContext, muted: true });
  assert.equal(audio.play('chomp'), false);
  assert.equal(created, 0);
  audio.setMuted(false);
  assert.equal(audio.play('chomp'), true);
  assert.equal(created, 1);
});
