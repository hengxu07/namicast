// Returns background color, text color, and label based on score (1–10)
export function getScoreColor(score) {
  if (score >= 9)  return { bg: '#15803d', text: '#fff', label: 'Epic' };
  if (score >= 7)  return { bg: '#16a34a', text: '#fff', label: 'Very Good' };
  if (score >= 5)  return { bg: '#ca8a04', text: '#fff', label: 'Good' };
  if (score >= 3)  return { bg: '#ea580c', text: '#fff', label: 'Fair' };
  return           { bg: '#dc2626', text: '#fff', label: 'Poor' };
}

// Smooth gradient interpolation for progress rings and bars
// Interpolates red (score 0) → yellow (score 5) → green (score 10)
export function getScoreGradient(score) {
  const ratio = Math.max(0, Math.min(10, score)) / 10;

  if (ratio < 0.5) {
    // Red to yellow
    const t = ratio * 2;
    const r = Math.round(220 + (234 - 220) * t);
    const g = Math.round(38  + (179 - 38)  * t);
    const b = Math.round(38  + (8   - 38)  * t);
    return `rgb(${r},${g},${b})`;
  } else {
    // Yellow to green
    const t = (ratio - 0.5) * 2;
    const r = Math.round(234 + (22  - 234) * t);
    const g = Math.round(179 + (197 - 179) * t);
    const b = Math.round(8   + (94  - 8)   * t);
    return `rgb(${r},${g},${b})`;
  }
}