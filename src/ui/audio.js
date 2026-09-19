export const CUES = {
  start: { type: 'square', frequency: 260, endFrequency: 520, duration: 0.2, gain: 0.2 },
  chomp: { type: 'square', frequency: 180, endFrequency: 140, duration: 0.05, gain: 0.12 },
  power: { type: 'sawtooth', frequency: 120, endFrequency: 480, duration: 0.35, gain: 0.2 },
  eatGhost: { type: 'square', frequency: 640, endFrequency: 1200, duration: 0.25, gain: 0.22 },
  ghostRevive: { type: 'triangle', frequency: 320, endFrequency: 640, duration: 0.12, gain: 0.12 },
  death: { type: 'sawtooth', frequency: 400, endFrequency: 60, duration: 0.7, gain: 0.25 },
  extraLife: { type: 'triangle', frequency: 880, endFrequency: 1320, duration: 0.3, gain: 0.2 },
  levelComplete: { type: 'triangle', frequency: 660, endFrequency: 990, duration: 0.4, gain: 0.2 },
  gameOver: { type: 'sawtooth', frequency: 300, endFrequency: 80, duration: 0.8, gain: 0.25 },
  win: { type: 'triangle', frequency: 520, endFrequency: 1560, duration: 0.6, gain: 0.22 },
};

/**
 * Pure mapping from a game event to a synthesisable cue. No audio APIs are
 * touched here so the function can be unit tested in Node.
 */
export function cueFor(event) {
  const cue = CUES[event];
  if (!cue) throw new Error(`unknown audio event: ${event}`);
  return { name: event, ...cue };
}

function resolveAudioContext(AudioContextClass) {
  if (AudioContextClass) return AudioContextClass;
  return globalThis.AudioContext || globalThis.webkitAudioContext || null;
}

/**
 * Lazily creates an AudioContext and plays the cue for a game event.
 * Safe to construct in environments without Web Audio (all play calls no-op).
 */
export function createAudio({ AudioContextClass, muted = false } = {}) {
  const Context = resolveAudioContext(AudioContextClass);
  let context = null;
  let isMuted = muted;

  const ensureContext = () => {
    if (!Context) return null;
    if (!context) context = new Context();
    return context;
  };

  return {
    get muted() {
      return isMuted;
    },
    setMuted(next) {
      isMuted = Boolean(next);
    },
    toggleMuted() {
      isMuted = !isMuted;
      return isMuted;
    },
    resume() {
      const ctx = ensureContext();
      if (ctx && ctx.state === 'suspended' && typeof ctx.resume === 'function') {
        ctx.resume();
      }
      return ctx;
    },
    play(event) {
      const cue = cueFor(event);
      if (isMuted) return false;
      const ctx = ensureContext();
      if (!ctx) return false;
      const now = ctx.currentTime;
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.type = cue.type;
      oscillator.frequency.setValueAtTime(cue.frequency, now);
      if (cue.endFrequency) {
        oscillator.frequency.linearRampToValueAtTime(cue.endFrequency, now + cue.duration);
      }
      gain.gain.setValueAtTime(cue.gain, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + cue.duration);
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.start(now);
      oscillator.stop(now + cue.duration);
      return true;
    },
  };
}
