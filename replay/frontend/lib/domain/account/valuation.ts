import type {Account, Position} from '../market/types';

export function accountValue(account: Account | null, positions: Position[], last: number | null, symbol: string) {
 let unrealized = 0;
 let known = true;
 for (const position of positions) {
  const pnl = position.symbol === symbol && last != null && Number.isFinite(last)
   ? (last - position.entry) * (position.side === 'SHORT' ? -1 : 1) * position.size * position.point_value
   : position.pnl;
  if (pnl == null || !Number.isFinite(pnl)) known = false;
  else unrealized += pnl;
 }
 return {
  hasPosition: positions.length > 0,
  unrealized: known ? unrealized : null,
  equity: account && known ? account.balance + unrealized : null,
 };
}
