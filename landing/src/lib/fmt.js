// 格式化工具：Token 大单位（M/B/K）与安全数字转换
// 所有导出的函数都做了空值/NaN 兜底，避免渲染出 "NaN" 或 "undefined"

const isNum = (n) => typeof n === 'number' && Number.isFinite(n)

/**
 * 把 token 数格式化成可读大单位：
 *   n>=1e9 -> 1.23B
 *   n>=1e6 -> 1.20M
 *   n>=1e3 -> 82.5K
 *   否则   -> 1234
 * 传入 null / NaN / undefined 一律返回 '0'
 */
export function fmtTokens(n) {
  if (!isNum(n)) return '0'
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B'
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
  return String(Math.round(n))
}

/**
 * 通用数字格式化：
 *  - 整数使用 locale（千分位）
 *  - 空值/非有限数返回 '—'
 *  - 0 显示为 '0'
 */
export function fmtInt(n) {
  if (!isNum(n)) return '—'
  return Math.round(n).toLocaleString('en-US')
}

/**
 * 保留小数位。空值返回 '—'。0 返回 '0.0'（或按需）。
 * default 参数控制空值展示。
 */
export function fmtFloat(n, digits = 1) {
  if (!isNum(n)) return '—'
  return n.toFixed(digits)
}

/**
 * 安全布尔转状态文本；空值返回显示为「—」。
 */
export function fmtPct(n, digits = 1) {
  if (!isNum(n)) return '—'
  return n.toFixed(digits) + '%'
}

/**
 * 空值兜底显示（用于纯文本字段）。
 */
export function orDash(v) {
  if (v === null || v === undefined || v === '') return '—'
  return String(v)
}
