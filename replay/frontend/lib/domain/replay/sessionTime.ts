import type {SessionInfo} from '../market/types';
/** Une séance se termine le jour de son étiquette, mais commence la veille au soir. */
export function sessionTime(session: SessionInfo, hh: number, mm: number): number {
 const [y,mo,day]=session.date.split('-').map(Number);
 let t=Date.UTC(y,mo-1,day,hh,mm)/1000;
 if(t>=session.session_start+86400)t-=86400;
 return Math.max(session.first_ts,Math.min(t,session.last_ts-60));
}
