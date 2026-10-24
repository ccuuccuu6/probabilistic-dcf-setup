"""Read-only local TWS/Gateway FX adapter. No order/account APIs are exposed.

The optional ib_async dependency implements the TWS socket protocol. Financial
calculation and Excel exports never import it. The narrow client boundary can be
tested with recorded/synthetic callbacks without a broker session.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import time

from .fx import _cross_quotes, publication_dates
from .fx_store import utc_now


class BrokerError(RuntimeError):pass


def validate_spot(quote,as_of=None,max_age=900):
    now=as_of or datetime.now(timezone.utc)
    bid,ask=quote.get('bid'),quote.get('ask')
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in (bid,ask)) or bid>ask:
        raise BrokerError('Invalid bid/ask: prices must be positive, finite and ordered')
    stamp=datetime.fromisoformat(quote['timestamp'].replace('Z','+00:00'))
    if stamp.tzinfo is None:raise BrokerError('Spot timestamp requires timezone')
    age=(now-stamp).total_seconds()
    # Weekend frozen observations are allowed only if their actual timestamp is
    # recent relative to Friday close. They are never labelled live/new ticks.
    closed=now.weekday()==5 or (now.weekday()==6 and now.hour<21) or (now.weekday()==4 and now.hour>=21)
    ceiling=72*3600 if closed and quote.get('market_data_type')=='frozen' else max_age
    if age<0 or age>ceiling:raise BrokerError('Stale or future-dated spot')
    if quote.get('market_data_type') not in ('live','frozen'):raise BrokerError('Delayed or unknown data is not an eligible spot')
    return dict(quote,value=(bid+ask)/2,market_closed=closed,age_seconds=age)


def overlap_check(existing,new,base,quote,threshold=.05):
    """Compare daily directions first; fixing/close differences remain explicit.

    A tolerance is a quarantine threshold, never an instruction to rescale or
    fit one provider to another. At least three overlapping dates are required.
    """
    days=sorted({q['day'] for q in new});comparisons=[];old_by_day={}
    for q in existing:
        if q['status']=='actual':old_by_day.setdefault(q['day'],[]).append(q)
    for q in new:
        before,path=_cross_quotes(old_by_day.get(q['day'],[]),q['quote'],q['base'])
        if before is None:continue
        comparisons.append(dict(day=q['day'],old=before,new=q['value'],relative_difference=q['value']/before-1,
            old_ids=[v['id'] for v in path],old_definitions=sorted({v['definition'] for v in path}),
            new_definition=q['definition'],comparison='Same session date; fixing and daily close are different sampling times'))
    material=[c for c in comparisons if abs(c['relative_difference'])>threshold]
    changes=[abs(new[i]['value']/new[i-1]['value']-1) for i in range(1,len(new)) if new[i]['day']>new[i-1]['day']]
    return dict(base=base,quote=quote,comparisons=comparisons,threshold=threshold,
        status='quarantined' if material or any(x>threshold*2 for x in changes) else 'insufficient_overlap' if len(comparisons)<3 else 'passed',
        reason='No rescaling. Reference fixings and MIDPOINT closes differ in sampling time; unexplained material discontinuities require investigation.',
        comparable_intraday_times=False)


class TWSClient:
    """Read-only facade using ib_async's TWS protocol implementation.

    Connect the socket client directly: no positions, executions or account
    synchronization is requested. Broker Read-Only API remains the server guard.
    """
    def __init__(self,host='127.0.0.1',port=7497,client_id=71,timeout=20,session_timezone='UTC'):
        if host not in ('127.0.0.1','localhost','::1'):raise ValueError('Only a local broker is supported')
        try:
            from ib_async import IB, Forex
        except ImportError as exc:
            raise BrokerError('Install the optional broker dependency: python -m pip install -e ".[ibkr]"') from exc
        self._ib=IB();self.Forex=Forex;self.timeout=timeout;self.session_timezone=session_timezone
        self.errors=[]
        self._ib.RequestTimeout=timeout
        self._ib.RaiseRequestErrors=True
        def forbidden(*args,**kwargs):raise BrokerError('Order actions are disabled in the research adapter')
        for method in ('placeOrder','cancelOrder','reqGlobalCancel'):
            setattr(self._ib.client,method,forbidden)
        try:self._ib.client.connect(host,int(port),int(client_id),timeout)
        except Exception as exc:
            self.close();raise BrokerError('TWS handshake failed: '+str(exc)) from exc
        self.handshake=dict(connected=self._ib.client.isReady(),server_version=self._ib.client.serverVersion(),
            host=host,port=int(port),client_id=int(client_id),read_operations_only=True)

    def close(self):self._ib.disconnect()

    def resolve(self,base,quote):
        errors=[]
        for left,right in ((base,quote),(quote,base)):
            try:
                contracts=self._ib.qualifyContracts(self.Forex(left+right,exchange='IDEALPRO'))
                if len(contracts)!=1:raise BrokerError('No unique CASH contract')
                c=contracts[0]
                if c.secType!='CASH' or c.symbol!=left or c.currency!=right:raise BrokerError('Contract mismatch')
                return dict(base=left,quote=right,contract=c,con_id=c.conId)
            except Exception as exc:errors.append(str(exc))
        raise BrokerError('Unavailable '+base+'/'+quote+': '+ '; '.join(errors))

    def history(self,resolved,start,end):
        finish=(_date(end)+timedelta(days=1)).strftime('%Y%m%d')+' 00:00:00 UTC'
        try:
            bars=self._ib.reqHistoricalData(resolved['contract'],finish,f'{(_date(end)-_date(start)).days+1} D',
                '1 day','MIDPOINT',False,formatDate=1,keepUpToDate=False,timeout=self.timeout)
            return [dict(day=b.date.isoformat(),value=float(b.close)) for b in bars if start<=b.date.isoformat()<=end]
        except Exception as exc:raise BrokerError('Historical data: '+str(exc)) from exc

    def spot(self,resolved):
        c=resolved['contract'];self._ib.reqMarketDataType(1)
        ticker=self._ib.reqTickByTickData(c,'BidAsk',0,False)
        deadline=time.monotonic()+self.timeout
        try:
            while time.monotonic()<deadline:
                self._ib.sleep(.1)
                if ticker.tickByTicks:
                    tick=ticker.tickByTicks[-1]
                    return validate_spot(dict(bid=float(tick.bidPrice),ask=float(tick.askPrice),
                        timestamp=tick.time.isoformat(),market_data_type='live'))
        finally:self._ib.cancelTickByTickData(c,'BidAsk')
        # Weekend: historical ticks have a provider timestamp, unlike a frozen
        # watchlist quote whose receipt time says nothing about observation age.
        try:
            ticks=self._ib.reqHistoricalTicks(c,'',datetime.now(timezone.utc),100,'BID_ASK',False,True)
            rejected=[]
            for tick in reversed(ticks):
                try:
                    return validate_spot(dict(bid=float(tick.priceBid),ask=float(tick.priceAsk),timestamp=tick.time.isoformat(),
                        market_data_type='frozen' if datetime.now(timezone.utc).weekday() in (5,6) else 'live'))
                except BrokerError as exc:rejected.append(str(exc))
            if rejected:raise BrokerError('No valid recent bid/ask among returned ticks: '+rejected[0])
        except Exception as exc:raise BrokerError('Timestamped bid/ask unavailable: '+str(exc)) from exc
        raise BrokerError('No timestamped bid/ask quote; LAST is not a Forex fallback')


def _date(value):return date.fromisoformat(str(value))


def update_fx(store,client,pairs,*,as_of=None,overlap_days=7,max_recent_days=90,retries=1,pacing_seconds=11,diagnostic=False,progress=None,cross_currencies=('USD','EUR')):
    """Incremental per-pair update; preserves successful pairs on partial failure."""
    now=as_of or datetime.now(timezone.utc);end=(now.date()-timedelta(days=1)).isoformat()
    if overlap_days<0 or max_recent_days<1 or retries<0:raise ValueError('Invalid incremental request bounds')
    existing=store.quotes();results=[];cutovers=[];resolved_pairs=set()
    queue=list(dict.fromkeys(pairs));resolved_cache={};routes=[]
    def log(message):
        if progress:progress(message)
    for requested in queue:
        base,quote=requested.split('/')
        log('IBKR '+requested+': resolving contract')
        try:
            resolved=resolved_cache.get(requested) or client.resolve(base,quote)
        except BrokerError as exc:
            # Request supported legs, preserving native orientation; calculator
            # derives cross rates later. No synthetic quote is labelled native.
            route=None
            if requested in pairs:
                for intermediate in cross_currencies:
                    if intermediate in (base,quote):continue
                    legs=[base+'/'+intermediate,intermediate+'/'+quote]
                    try:
                        resolved_legs=[client.resolve(*leg.split('/')) for leg in legs]
                    except BrokerError:continue
                    for leg,contract in zip(legs,resolved_legs):
                        resolved_cache[leg]=contract
                        if leg not in queue:queue.append(leg)
                    route=dict(pair=requested,status='pending_cross',legs=legs,
                        definition='Derived daily cross and spot from native broker legs; no synthetic native quote stored')
                    routes.append(route);break
            results.append(route or dict(pair=requested,status='unavailable_contract',error=str(exc)))
            continue
        base,quote=resolved['base'],resolved['quote']
        if (base,quote) in resolved_pairs:continue
        resolved_pairs.add((base,quote))
        same=[q for q in existing if q['status']=='actual' and {q['base'],q['quote']}=={base,quote}]
        latest=max((q['day'] for q in same),default=None)
        # Cross-compatible reference history also bounds bootstrap downloads.
        if latest is None:
            for day in sorted({q['day'] for q in existing},reverse=True):
                value,path=_cross_quotes([q for q in existing if q['day']==day],quote,base)
                if value is not None:latest=day;break
        floor=now.date()-timedelta(days=max_recent_days)
        start=max(floor,_date(latest)-timedelta(days=overlap_days) if latest else now.date()-timedelta(days=overlap_days))
        result=dict(pair=requested,resolved_pair=base+'/'+quote,contract_id=resolved.get('con_id'),start=start.isoformat(),end=end)
        bars=[]
        for attempt in range(retries+1):
            try:
                log('IBKR '+requested+': daily MIDPOINT closes '+start.isoformat()+' through '+end)
                bars=client.history(resolved,start.isoformat(),end);break
            except BrokerError as exc:
                result['history_error']=str(exc)
                if attempt<retries:time.sleep(min(30,max(16,pacing_seconds)))
        quotes=[]
        for bar in sorted(bars,key=lambda b:b['day']):
            if not start.isoformat()<=bar['day']<=end:continue
            quotes.append(dict(provider='IBKR',base=base,quote=quote,day=bar['day'],source_date=bar['day'],value=bar['value'],
                definition='MIDPOINT_daily_close',status='actual',timezone=client.session_timezone,
                observation_time='session close; day label in configured TWS login timezone',native=True,
                retrieved_at=utc_now(),provenance=dict(contract_id=resolved.get('con_id'),what_to_show='MIDPOINT',bar_size='1 day',use_rth=False)))
        comparison=overlap_check(existing,quotes,base,quote)
        result['overlap']=comparison
        if comparison['status']=='quarantined':
            for q in quotes:q['quality']='quarantined_transition'
        if quotes and not diagnostic:
            result['history_import']=store.import_quotes(quotes,dict(provider='IBKR',pair=base+'/'+quote,start=start.isoformat(),end=end,content=[(q['day'],q['value']) for q in quotes]))
            if comparison['status']=='passed':
                # Extend only beyond the existing history, never silently replace
                # the overlap or adopt a new provider before its comparison gate.
                cutovers.append(dict(base=base,quote=quote,provider='IBKR',
                    **{'from':(_date(latest)+timedelta(days=1)).isoformat() if latest else start.isoformat()},
                    overlap_evidence=comparison,reason='Incremental extension after preserved reference history; fixing/close convention change documented'))
        try:
            spot=client.spot(resolved)
            if spot.get('timestamp') and spot.get('value') is not None:
                spot=validate_spot(spot,now)
                result['spot']=spot
                if not diagnostic:
                    q=dict(provider='IBKR',base=base,quote=quote,day=spot['timestamp'][:10],source_date=spot['timestamp'][:10],
                        definition='bid_ask_midpoint',status='actual',timezone='UTC',native=True,retrieved_at=utc_now(),**spot)
                    result['spot_import']=store.import_quotes([q],dict(provider='IBKR',pair=base+'/'+quote,spot_timestamp=spot['timestamp']))
        except BrokerError as exc:result['spot_error']=str(exc)
        result['status']='passed' if bars and comparison['status']=='passed' and result.get('spot',{}).get('value') is not None else 'partial'
        results.append(result)
        if pacing_seconds:time.sleep(pacing_seconds)
    for route in routes:
        legs=[next((r for r in results if r['pair']==leg),None) for leg in route['legs']]
        route['status']='derived_cross' if all(r and r['status']=='passed' for r in legs) else 'partial'
    succeeded=bool(results) and all(r['status'] in ('passed','derived_cross') for r in results)
    report=dict(as_of=now.isoformat(),operation='diagnostic' if diagnostic else 'incremental_update',ai_calls=0,
        pairs=results,cutovers=cutovers,status='passed' if succeeded else 'partial',exit_code=0 if succeeded else 2)
    store.record_update(report)
    return report
