export const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
export const dateTime = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
export function signedDecimal(value: string, places = 2): bigint | null {
  const text = value.trim()
  const magnitude = decimal(text.startsWith("-") ? text.slice(1) : text, places)
  return magnitude === null ? null : text.startsWith("-") ? -magnitude : magnitude
}
export function decimal(value: string, places = 2): bigint | null {
  const normalized = value.trim().replace(',', '.')
  if (!/^\d+(\.\d+)?$/.test(normalized) || normalized.length > 24) return null
  const [whole, fraction = ''] = normalized.split('.')
  if (fraction.length > places) return null
  return BigInt(whole) * 10n ** BigInt(places) + BigInt(fraction.padEnd(places, '0'))
}
export function decimalText(value: bigint, places = 2): string {
  const scale = 10n ** BigInt(places)
  return `${value / scale}.${(value % scale).toString().padStart(places, '0')}`
}
export function brl(value: bigint): string { return money.format(Number(value) / 100) }
export function today(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`
}
export function displayDate(value: string): string { return value.split('-').reverse().join('/') }
export function paymentSchedule(amount: bigint, count: number, firstDueDate: string, unit: 'months' | 'days' = 'months', interval = 1): { date: string; amount: bigint }[] {
  if (!Number.isInteger(count) || count < 1 || count > 12 || amount < BigInt(count) || !/^\d{4}-\d{2}-\d{2}$/.test(firstDueDate) || !['months', 'days'].includes(unit) || !Number.isInteger(interval) || interval < 1 || interval > (unit === 'months' ? 12 : 365)) return []
  const [year, month, day] = firstDueDate.split('-').map(Number)
  const makeDate = (y: number, m: number, d: number) => { const value = new Date(0); value.setUTCFullYear(y, m, d); value.setUTCHours(0, 0, 0, 0); return value }
  const origin = makeDate(year, month - 1, day)
  if (year < 1 || origin.getUTCFullYear() !== year || origin.getUTCMonth() !== month - 1 || origin.getUTCDate() !== day) return []
  const result = []
  for (let index = 0; index < count; index++) {
    const first = makeDate(year, month - 1 + index * interval, 1)
    const lastDay = makeDate(first.getUTCFullYear(), first.getUTCMonth() + 1, 0).getUTCDate()
    const value = unit === 'days' ? new Date(origin.getTime() + index * interval * 86400000) : makeDate(first.getUTCFullYear(), first.getUTCMonth(), Math.min(day, lastDay))
    if (value.getUTCFullYear() > 9999) return []
    const due = `${String(value.getUTCFullYear()).padStart(4, '0')}-${String(value.getUTCMonth()+1).padStart(2,'0')}-${String(value.getUTCDate()).padStart(2,'0')}`
    result.push({ date: due, amount: amount / BigInt(count) + (BigInt(index) < amount % BigInt(count) ? 1n : 0n) })
  }
  return result
}
export function failure(error: unknown): string { return error instanceof Error ? error.message : 'Não foi possível concluir a operação.' }
