"""Fiscal calendars and compatible historical observation derivations."""
from __future__ import annotations

import calendar
import copy
from datetime import date, datetime, timedelta
import hashlib
import json
import math

from ..shared_runtime import check

_ORDER=('Q1','Q2','Q3','Q4','H1','H2','FY','9M')
_COMPONENTS={'H1':('Q1','Q2'),'H2':('Q3','Q4'),'FY':('Q1','Q2','Q3','Q4'),'9M':('Q1','Q2','Q3')}

def _date(value):
    return value.date() if isinstance(value,datetime) else value if isinstance(value,date) else date.fromisoformat(str(value))


def _months(day,count):
    month=day.year*12+day.month-1+count;year,month=divmod(month,12)
    return date(year,month+1,min(day.day,calendar.monthrange(year,month+1)[1]))


def build_periods(years,fiscal_calendar=None):
    """Return Q1,Q2,Q3,Q4,H1,H2,FY and hidden 9M for each fiscal year.

    Explicit periods accept id or period_id. Four explicit quarters can define
    a retail calendar; their aggregate dates are then calculated without assuming
    three-month quarters. Otherwise use fiscal_start_month/day or fiscal_year_end
    (alias annual_end, MM-DD), with the fiscal label based on the ending year.
    """
    config=dict(fiscal_calendar or {});years=sorted(set(int(y) for y in years))
    explicit={}
    for raw in config.get('periods',[]):
        item=copy.deepcopy(raw);item['id']=item.get('id',item.get('period_id'))
        if not item['id'] or item['kind'] not in _ORDER:
            raise ValueError('Explicit fiscal periods need id/period_id and a supported kind')
        key=(int(item['fiscal_year']),item['kind'])
        if key in explicit:raise ValueError('Duplicate fiscal year/period kind')
        explicit[key]=item
    result=[]
    for year in years:
        quarters={k:copy.deepcopy(explicit[(year,k)]) for k in ('Q1','Q2','Q3','Q4') if (year,k) in explicit}
        if quarters and len(quarters)!=4:
            raise ValueError('An explicit fiscal calendar must supply all four quarter boundaries')
        if not quarters:
            month=config.get('fiscal_start_month');day=int(config.get('fiscal_start_day',1))
            explicit_end=None
            if month is None:
                ending=config.get('fiscal_year_end',config.get('annual_end','12-31'))
                if isinstance(ending,dict):ending=ending.get(str(year),ending.get(year))
                ending=str(ending)
                end_year=year+1 if config.get('label_by_start') and ending!='12-31' else year
                end=_date(ending if len(ending)==10 else f'{end_year}-{ending}')
                explicit_end=end
                start=date(end.year-1,end.month,min(end.day,calendar.monthrange(end.year-1,end.month)[1]))+timedelta(days=1)
            else:
                month=int(month)
                start_year=year if config.get('label_by_start') or (month,day)==(1,1) else year-1
                start=date(start_year,month,day)
            for q in range(4):
                quarters[f'Q{q+1}']=dict(id=f'{year}-Q{q+1}',fiscal_year=year,kind=f'Q{q+1}',
                    start=_months(start,3*q).isoformat(),end=(explicit_end if q==3 and explicit_end is not None else _months(start,3*(q+1))-timedelta(days=1)).isoformat())
        ordered=[quarters[k] for k in ('Q1','Q2','Q3','Q4')]
        for index,item in enumerate(ordered):
            if _date(item['start'])>_date(item['end']):raise ValueError('Fiscal period has reversed dates')
            if index and _date(item['start'])!=_date(ordered[index-1]['end'])+timedelta(days=1):
                raise ValueError('Fiscal quarters must be contiguous and non-overlapping')
        all_periods=dict(quarters)
        for kind,parts in _COMPONENTS.items():
            item=copy.deepcopy(explicit.get((year,kind),dict(id=f'{year}-{kind}',fiscal_year=year,kind=kind)))
            begin,finish=quarters[parts[0]]['start'],quarters[parts[-1]]['end']
            if ('start' in item and _date(item['start'])!=_date(begin)) or ('end' in item and _date(item['end'])!=_date(finish)):
                raise ValueError('Aggregate fiscal dates disagree with component quarters')
            item.update(start=begin,end=finish,components=[quarters[p]['id'] for p in parts]);all_periods[kind]=item
        for kind in _ORDER:
            item=all_periods[kind];item['start']=_date(item['start']).isoformat();item['end']=_date(item['end']).isoformat()
            item['duration_days']=(_date(item['end'])-_date(item['start'])).days+1
            item.setdefault('components',[]);item.setdefault('display',kind);item.setdefault('hidden',kind=='9M')
            item.setdefault('status','actual' if config.get('actual_through') and item['end']<=str(config['actual_through']) else 'unspecified')
            result.append(item)
    if len({p['id'] for p in result})!=len(result):raise ValueError('Duplicate fiscal period IDs')
    return result


def derive_observations(observations,periods):
    """Preserve originals and add only date- and basis-compatible flow/stock facts.

    Returns observations (all canonical copies), derived (new entries), checks.
    'reported' normalises to 'actual' with source_status retaining the original.
    Equal explicit compatibility_key authorises different basis/restatement labels;
    it never overrides differences in metric definition, currency, units or scope.
    """
    calendar_by_id={p.get('id',p.get('period_id')):p for p in periods}
    by_year={}
    for pid,p in calendar_by_id.items():by_year.setdefault(int(p['fiscal_year']),{})[p['kind']]=dict(p,id=pid)
    originals=copy.deepcopy(observations);derived=[];checks=[];groups={};identities=set()
    for index,item in enumerate(originals):
        item.setdefault('id',f'original_{index}');item.setdefault('source_status',item.get('status','reported'))
        if not isinstance(item['id'],str) or not item['id'] or item['id'] in identities:
            raise ValueError('Observation identities must be unique nonempty strings')
        identities.add(item['id'])
        if item.get('status') in (None,'reported'):item['status']='actual'
        elif item['status']=='derived':item['status']='derived_actual'
        elif item['status']=='estimated':item['status']='estimate'
        item.setdefault('source_refs',copy.deepcopy(item.get('sources',[])))
        if 'value' not in item:item['value']=item.get('raw_value',item.get('raw'))
        # Original exclusions remain effective through every derived generation.
        # A status rewrite must never turn unverified or rejected evidence into
        # a reported fact; estimates may derive only other estimates.
        # Retained alternative versions are evidence, not active period inputs.
        if (not item.get('eligible',True) or not item.get('model_selection_eligible',True)
                or item['status'] not in ('actual','derived_actual','estimate','estimated','forecast')):
            continue
        pid=item.get('period_id');period=calendar_by_id.get(pid)
        if not period:
            checks.append(check('period_derivation',item['id'],'MISSING','Observation period is absent from the fiscal calendar'));continue
        metric_type=item.get('metric_type',item.get('time_basis'))
        if metric_type not in ('flow','additive_flow','stock','balance'):continue
        if any(token in str(item.get('metric',item.get('row_id',''))).lower() for token in ('eps','per_share','margin','growth','pricing','ratio')):continue
        if item.get('value') is None:continue
        if type(item['value']) not in (int,float) or not math.isfinite(item['value']):
            checks.append(check('period_derivation',item['id'],'FAIL','Nonnumeric observation'));continue
        stock=metric_type in ('stock','balance')
        dates_match=_date(item.get('end',period['end']))==_date(period['end']) and (stock or _date(item.get('start',period['start']))==_date(period['start']))
        stock_timing='closing'
        if stock and item.get('measurement_date'):
            measurement=_date(item['measurement_date'])
            if measurement==_date(period['start'])-timedelta(days=1):stock_timing='opening'
            elif measurement!=_date(period['end']):
                checks.append(check('period_derivation',item['id'],'WARNING','Stock has a separate measurement date; retain original without period aliases'));continue
        if not stock and item.get('duration_days') is not None:
            dates_match=dates_match and item['duration_days']==(_date(period['end'])-_date(period['start'])).days+1
        if not dates_match:
            checks.append(check('period_derivation',item['id'],'FAIL','Observation dates do not match the fiscal period'));continue
        fields=('definition','currency','unit','scope')
        nonmonetary=item.get('unit') in ('ratio','shares','shares_m','units','days')
        definition=item.get('definition_id',item.get('definition'))
        if not definition or any(item.get(field) in (None,'') for field in fields if field!='definition' and (field!='currency' or not nonmonetary)):
            checks.append(check('period_derivation',item['id'],'MISSING','Definition, currency, unit and scope are required for derivation'));continue
        compatible=('explicit',item['compatibility_key']) if item.get('compatibility_key') else ('basis',item.get('basis'),item.get('restatement'))
        if not item.get('compatibility_key') and (not item.get('basis') or not item.get('restatement')):
            checks.append(check('period_derivation',item['id'],'MISSING','Explicit basis/restatement compatibility is required'));continue
        key=(item.get('row_id',item.get('metric')),item.get('entity_id',item.get('model_entity_id')),int(period['fiscal_year']),stock,stock_timing,
             *(json.dumps(definition if field=='definition' else item.get(field),sort_keys=True) for field in fields),json.dumps(item.get('scale')),json.dumps(compatible,sort_keys=True))
        groups.setdefault(key,{}).setdefault(period['kind'],[]).append(item)
    recipes=[('Q2',('H1','Q1'),(1,-1)),('Q3',('9M','H1'),(1,-1)),('Q4',('FY','9M'),(1,-1)),
             ('H2',('FY','H1'),(1,-1)),('H1',('Q1','Q2'),(1,1)),('H2',('Q3','Q4'),(1,1)),
             ('9M',('Q1','Q2','Q3'),(1,1,1)),('FY',('Q1','Q2','Q3','Q4'),(1,1,1,1)),('FY',('H1','H2'),(1,1))]
    for group,variants in groups.items():
        year,stock=group[2],group[3];calendar=by_year[year];known={};logged=set()
        for kind,items in variants.items():
            if any(not math.isclose(i['value'],items[0]['value'],rel_tol=1e-10,abs_tol=1e-8) for i in items[1:]):
                checks.append(check('period_derivation',items[0]['row_id']+':'+calendar[kind]['id'],'FAIL','Conflicting originals on an asserted compatible basis'));continue
            known[kind]=items[0]
        def add(kind,inputs,signs):
            target=calendar[kind];base=inputs[0]
            expression='+'.join(('' if sign==1 else '-')+f's{i}' for i,sign in enumerate(signs)).replace('+-','-')
            bindings={f's{i}':dict(row_id=o.get('row_id',o.get('metric')),period_id=o['period_id'],observation_id=o['id']) for i,o in enumerate(inputs)}
            value=sum(o['value']*sign for o,sign in zip(inputs,signs));item=copy.deepcopy(base)
            identity=json.dumps([target['id'],[o['id'] for o in inputs],signs],sort_keys=True)
            refs=[]
            for original,weight in zip(inputs,signs):
                for ref in original.get('source_refs',[]):
                    ref=copy.deepcopy(ref);ref['contribution_weight']=ref.get('contribution_weight',1)*weight;refs.append(ref)
            item.update(id='derived_'+hashlib.sha256(identity.encode()).hexdigest()[:20],period_id=target['id'],kind=kind,
                start=target['start'],end=target['end'],duration_days=(_date(target['end'])-_date(target['start'])).days+1,
                value=value,status='estimate' if any(o['status'] in ('estimate','estimated','forecast') for o in inputs) else 'derived_actual',
                source_status='derived',expression=expression,bindings=bindings,source_refs=refs,
                input_observation_ids=[o['id'] for o in inputs],derivation='closing-date alias' if stock else 'compatible additive flow',is_derived=True)
            # A derived quarter cannot become available before the latest
            # contributing disclosure; retain every source's publication status.
            vintages=[];classification_refs=[]
            for original in inputs:
                for vintage in original.get('source_vintage',[]):
                    if vintage not in vintages:vintages.append(copy.deepcopy(vintage))
                for reference in original.get('classification_source_refs',[]):
                    if reference not in classification_refs:classification_refs.append(copy.deepcopy(reference))
            if vintages:item['source_vintage']=vintages
            if classification_refs:item['classification_source_refs']=classification_refs
            if all(original.get('published_at') for original in inputs):
                item['published_at']=max(original['published_at'] for original in inputs)
            else:item.pop('published_at',None)
            if stock:item['measurement_date']=target['end'] if group[4]=='closing' else (_date(target['start'])-timedelta(days=1)).isoformat()
            known[kind]=item;derived.append(item)
        if stock:
            for target in _ORDER:
                if target not in calendar or target in known:continue
                boundary='end' if group[4]=='closing' else 'start'
                same=next((o for k,o in known.items() if calendar[k][boundary]==calendar[target][boundary]),None)
                if same:add(target,[same],[1])
            continue
        for _ in range(8):
            added=False
            for target,parts,signs in recipes:
                if target not in calendar or any(p not in known for p in parts):continue
                boundaries={}
                for p,sign in [(calendar[k],s) for k,s in zip(parts,signs)]+[(calendar[target],-1)]:
                    begin,finish=_date(p['start']).toordinal(),_date(p['end']).toordinal()+1
                    boundaries[begin]=boundaries.get(begin,0)+sign;boundaries[finish]=boundaries.get(finish,0)-sign
                if any(boundaries.values()):
                    if (target,parts) not in logged:
                        checks.append(check('period_derivation',calendar[target]['id']+':'+','.join(parts),'FAIL','Input fiscal intervals do not algebraically equal the target interval'))
                        logged.add((target,parts))
                    continue
                inputs=[known[p] for p in parts];value=sum(o['value']*sign for o,sign in zip(inputs,signs))
                if target not in known:add(target,inputs,signs);added=True
                elif (target,parts) not in logged:
                    delta=known[target]['value']-value
                    increments=[o.get('rounding_increment',0) for o in [known[target]]+inputs]
                    if any(type(x) not in (int,float) or not math.isfinite(x) or x<0 for x in increments):
                        raise ValueError('Publication rounding increments must be finite and nonnegative')
                    tolerance=max(1e-6,sum(increments)/2)
                    checks.append(check('period_derivation',known[target]['row_id']+':'+calendar[target]['id']+':'+','.join(parts),
                        'PASS' if abs(delta)<=tolerance else 'FAIL','Compatible additive periods reconcile within declared publication rounding',delta,tolerance));logged.add((target,parts))
            if not added:break
    return dict(observations=originals+derived,derived=derived,checks=checks)

