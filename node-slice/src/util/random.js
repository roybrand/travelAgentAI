export function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function randomFloat(min, max, decimals = 1) {
  const value = Math.random() * (max - min) + min;
  return Number(value.toFixed(decimals));
}

export function pick(array) {
  return array[randomInt(0, array.length - 1)];
}

export function pickN(array, n) {
  const pool = [...array];
  const out = [];
  const count = Math.min(n, pool.length);
  for (let i = 0; i < count; i++) {
    const idx = randomInt(0, pool.length - 1);
    out.push(pool.splice(idx, 1)[0]);
  }
  return out;
}
