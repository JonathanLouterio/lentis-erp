// Valores em centavos; taxa em centésimos de percentual. Sem ponto flutuante.
export const financedKinds = ['boleto', 'store_credit']
export function financingFee(principal: bigint, rate: bigint, kind: string): bigint {
  return financedKinds.includes(kind) && principal > 0n && rate > 0n ? (principal * rate + 5000n) / 10000n : 0n
}
export function minimumEntry(base: bigint): bigint {
  return base > 0n ? (base * 40n + 99n) / 100n : 0n
}
