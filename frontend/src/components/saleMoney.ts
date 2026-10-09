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
export function paymentSchedule(amount: bigint, count: number, firstDueDate: string): { date: string; amount: bigint }[] {
  if (!Number.isInteger(count) || count < 1 || count > 12 || !/^\d{4}-\d{2}-\d{2}$/.test(firstDueDate)) return []
  const [year, month, day] = firstDueDate.split('-').map(Number)
  const result = []
  for (let index = 0; index < count; index++) {
    const first = new Date(year, month - 1 + index, 1)
    const lastDay = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
    const due = `${first.getFullYear()}-${String(first.getMonth()+1).padStart(2,'0')}-${String(Math.min(day,lastDay)).padStart(2,'0')}`
    result.push({ date: due, amount: amount / BigInt(count) + (BigInt(index) < amount % BigInt(count) ? 1n : 0n) })
  }
  return result
}
export function failure(error: unknown): string { return error instanceof Error ? error.message : 'Não foi possível concluir a operação.' }
