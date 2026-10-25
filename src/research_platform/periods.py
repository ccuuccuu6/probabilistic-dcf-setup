"""Fiscal calendars, compatible period derivations and one bound financial graph."""
from __future__ import annotations

import ast
import calendar
import copy
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import re

from .construction import (check, dependencies, dimension, expression_tree,
                           formula_excel, unit_dimension)


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


def _binding(cell,pid,symbol,lag):
    key=f'lag:{symbol}:{lag}' if lag else symbol
    binding=cell.get('bindings',{}).get(key)
    if binding is None:
        if lag:raise ValueError(f'Explicit period binding required for {key}')
        return symbol,pid
    if not isinstance(binding,dict) or not binding.get('row_id') or not binding.get('period_id'):
        raise ValueError(f'Invalid period binding for {key}')
    return binding['row_id'],binding['period_id']


def cell_dependencies(cell,pid):
    if not cell.get('expression'):return []
    tree=expression_tree(cell['expression']);result=[]
    for symbol,lag in dict.fromkeys(dependencies(tree)):
        row,period=_binding(cell,pid,symbol,lag)
        result.append(dict(symbol=symbol,lag=lag,row_id=row,period_id=period))
    return result


def cell_formula_excel(cell,pid,resolve):
    """Return an Excel formula including '=', using the same restricted AST."""
    if not cell.get('expression'):raise ValueError('Cell has no expression')
    tree=expression_tree(cell['expression'])
    if any(isinstance(n,ast.Call) and n.func.id in ('if_zero','if_positive') for n in ast.walk(tree)):
        # A dormant financing control may legitimately be missing. Guard only
        # the selected branch, so Excel and Python share lazy missing semantics.
        def guarded(node):
            if isinstance(node,ast.Call) and node.func.id in ('if_zero','if_positive'):
                test=guarded(node.args[0]);a=guarded(node.args[1]);b=guarded(node.args[2])
                comparison='=0' if node.func.id=='if_zero' else '>0'
                return f'IF(ISNUMBER({test}),IF({test}{comparison},{a},{b}),IF(ISERROR({test}),{test},""))'
            if isinstance(node,ast.BinOp):
                left,right=guarded(node.left),guarded(node.right)
                op={ast.Add:'+',ast.Sub:'-',ast.Mult:'*',ast.Div:'/'}[type(node.op)]
                expr=f'({left}{op}{right})'
                return f'IF(AND(ISNUMBER({left}),ISNUMBER({right})),{expr},IF(OR(ISERROR({left}),ISERROR({right})),{expr},""))'
            if isinstance(node,ast.UnaryOp):
                value=guarded(node.operand);sign='-' if isinstance(node.op,ast.USub) else '+'
                return f'IF(ISNUMBER({value}),{sign}({value}),IF(ISERROR({value}),{value},""))'
            if isinstance(node,ast.Constant):return str(node.value)
            ref=formula_excel(node,lambda symbol,lag:resolve(*_binding(cell,pid,symbol,lag)))
            return f'IF(ISNUMBER({ref}),{ref},IF(ISERROR({ref}),{ref},""))'
        result='='+guarded(tree)
        if len(result)>8192:raise ValueError('Conditional financial expression exceeds Excel limits')
        return result
    expression=formula_excel(tree,lambda symbol,lag:resolve(*_binding(cell,pid,symbol,lag)))
    refs=list(dict.fromkeys(resolve(dep['row_id'],dep['period_id']) for dep in cell_dependencies(cell,pid)))
    if not refs:return '='+expression
    # Excel coerces empty references to zero. Match Python's missing propagation,
    # while preserving actual Excel errors rather than masking them with IFERROR.
    numbers=','.join('ISNUMBER('+ref+')' for ref in refs)
    errors=','.join('ISERROR('+ref+')' for ref in refs)
    formula='=IF(OR('+errors+'),'+expression+',IF(AND('+numbers+'),'+expression+',""))'
    if len(formula)>8000:
        # Large currency baskets can exceed Excel's 8,192-character limit when
        # the arithmetic is repeated in both guard branches. COUNT checks all
        # numeric dependencies; SUM propagates an input error without treating
        # absent inputs as zeros in the actual financial calculation.
        arguments=','.join(refs)
        formula=f'=IF(COUNT({arguments})={len(refs)},{expression},IF(ISERROR(SUM({arguments})),SUM({arguments}),""))'
    if len(formula)>8192 or len(refs)>255:
        raise ValueError('Financial expression exceeds Excel limits; split it into named intermediate calculations')
    return formula


def _evaluate(tree,resolve):
    """Missing propagates; numeric errors remain exceptions, never implicit zero."""
    if isinstance(tree,ast.Name):return resolve(tree.id,0)
    if isinstance(tree,ast.Call):
        if tree.func.id in ('if_zero','if_positive'):
            test=_evaluate(tree.args[0],resolve)
            return None if test is None else _evaluate(tree.args[1 if (test==0 if tree.func.id=='if_zero' else test>0) else 2],resolve)
        return resolve(tree.args[0].value,tree.args[1].value)
    if isinstance(tree,ast.Constant):return tree.value
    if isinstance(tree,ast.UnaryOp):
        value=_evaluate(tree.operand,resolve)
        return None if value is None else -value if isinstance(tree.op,ast.USub) else value
    left,right=_evaluate(tree.left,resolve),_evaluate(tree.right,resolve)
    if left is None or right is None:return None
    if isinstance(tree.op,ast.Add):return left+right
    if isinstance(tree.op,ast.Sub):return left-right
    if isinstance(tree.op,ast.Mult):return left*right
    if right==0:raise ValueError('Division by zero')
    return left/right


def _cell_dimension(cell,pid,rows):
    tree=expression_tree(cell['expression']);units={}
    class BoundNames(ast.NodeTransformer):
        def visit_Name(self,node):
            key=f'bound_{len(units)}';row,_=_binding(cell,pid,node.id,0);units[key]=rows[row]['unit']
            return ast.copy_location(ast.Name(id=key,ctx=ast.Load()),node)
        def visit_Call(self,node):
            if node.func.id in ('if_zero','if_positive'):
                node.args=[self.visit(argument) for argument in node.args]
                return node
            key=f'bound_{len(units)}';row,_=_binding(cell,pid,node.args[0].value,node.args[1].value);units[key]=rows[row]['unit']
            return ast.copy_location(ast.Name(id=key,ctx=ast.Load()),node)
    return dimension(BoundNames().visit(tree),units)


def _plan(spec):
    rows={r['id']:r for r in spec['rows']};periods={p['id']:p for p in spec['periods']}
    if len(rows)!=len(spec['rows']) or len(periods)!=len(spec['periods']):raise ValueError('Duplicate row or period IDs')
    graph={};cells={}
    for row in rows.values():
        unit_dimension(row['unit'])
        for pid,cell in row.get('cells',{}).items():
            if pid not in periods:raise ValueError(f'Unknown period {pid}')
            if not isinstance(cell,dict):raise ValueError('Period cells must be descriptors')
            key=(row['id'],pid);cells[key]=cell;graph[key]=[]
            if cell.get('expression'):
                if cell.get('value') is not None:raise ValueError(f'Cell has both source value and expression: {key}')
                for dep in cell_dependencies(cell,pid):
                    target=(dep['row_id'],dep['period_id'])
                    if target[0] not in rows or target[1] not in periods:
                        raise ValueError(f'Unknown formula target {target}')
                    if target[1] not in rows[target[0]].get('cells',{}):
                        raise ValueError(f'Formula target has no declared cell {target}; use an explicit missing descriptor')
                    graph[key].append(target)
                if _cell_dimension(cell,pid,rows)!=unit_dimension(row['unit']):
                    raise ValueError(f'Formula result has incompatible units: {key}')
            elif cell.get('value') is not None and (type(cell['value']) not in (int,float) or not math.isfinite(cell['value'])):
                raise ValueError(f'Non-finite or nonnumeric source value: {key}')
    state={};order=[]
    def visit(key):
        if state.get(key)==1:raise ValueError(f'Circular period dependency at {key}')
        if state.get(key)==2:return
        state[key]=1
        for target in graph[key]:visit(target)
        state[key]=2;order.append(key)
    for key in graph:visit(key)
    for key,cell in cells.items():
        if rows[key[0]].get('kind') not in ('assumption','driver') or not cell.get('expression'):continue
        for target in graph[key]:
            target_row=rows[target[0]];target_cell=cells[target]
            forecast=target_cell.get('status',periods[target[1]].get('status')) in ('forecast','estimate','estimated')
            current_or_future=periods[target[1]]['end']>=periods[key[1]]['start']
            if forecast and current_or_future and target_row.get('kind') not in ('assumption','driver') and not target_row.get('assumption_support'):
                raise ValueError(f'Forecast financial result cannot initialise an assumption: {key} depends on {target}')
    return rows,periods,cells,order


def calculate_periodic(spec,overrides=None):
    """Evaluate declared cells; override only authoritative editable inputs."""
    rows,periods,cells,order=_plan(spec);changes={}
    merged=copy.deepcopy(spec.get('assumption_overrides',{}))
    for key,value in (overrides or {}).items():
        if isinstance(value,dict):merged.setdefault(key,{}).update(value)
        else:merged[key]=value
    for key,value in merged.items():
        if isinstance(key,tuple) and len(key)==2:changes[key]=value
        elif isinstance(value,dict):changes.update({(key,pid):v for pid,v in value.items()})
        else:raise ValueError('Overrides require (row_id,period_id) keys or nested row/period mappings')
    for key,value in changes.items():
        if key not in cells or not cells[key].get('editable') or rows[key[0]].get('kind') not in ('assumption','driver'):
            raise ValueError(f'Only authoritative editable inputs can be overridden: {key}')
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
            raise ValueError('Override must be a finite number or explicit missing value')
    values={row:{pid:None for pid in periods} for row in rows}
    for key in order:
        row,pid=key;cell=cells[key]
        try:
            value=changes[key] if key in changes else _evaluate(expression_tree(cell['expression']),
                lambda symbol,lag:values[_binding(cell,pid,symbol,lag)[0]][_binding(cell,pid,symbol,lag)[1]]) if cell.get('expression') else cell.get('value')
        except (ValueError,TypeError,OverflowError) as exc:raise ValueError(f'Calculation error at {row}:{pid}: {exc}') from exc
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
            raise ValueError(f'Non-finite calculation at {row}:{pid}')
        values[row][pid]=value
    return values


def model_logic_digest(spec):
    """Identity of the financial graph and immutable history, excluding scenarios."""
    return hashlib.sha256(json.dumps(dict(company=spec['company'],periods=spec['periods'],
        rows=spec['rows'],identities=spec.get('identities',[])),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def assumption_contract(spec):
    """Project stable business inputs from the compiled graph, never Excel cells.

    Classification belongs to each period cell: a reported historical observation
    and a provisional forecast may occupy the same business row.
    """
    registry={r.get('driver_id',r.get('id')):r for r in spec.get('driver_registry',spec.get('financial_contracts',{}).get('drivers',[]))}
    periods={p['id']:p for p in spec['periods']};fields=[];classes={}
    for row in spec['rows']:
        rid=row['id'];meta=registry.get(rid,{})
        for pid,cell in row.get('cells',{}).items():
            period=periods[pid];status=cell.get('status','');expr=cell.get('expression')
            historical=status in ('actual','reported','derived_actual','estimated_historical')
            structural=cell.get('data_role',row.get('data_role')) in ('structural_absence','structural_parameter')
            reference=(rid.endswith('_seed') or row.get('classification')=='estimated_historical_baseline'
                or cell.get('data_role',cell.get('classification'))=='estimated_historical_baseline'
                or cell.get('calibration_eligible') is False or structural)
            writable=bool(cell.get('editable') and row.get('kind') in ('assumption','driver') and not historical and not reference)
            if structural:classification='structural_parameter'
            elif status=='estimated_historical' or cell.get('data_role',cell.get('classification'))=='estimated_historical_baseline' or cell.get('calibration_eligible') is False:classification='estimated_historical_baseline'
            elif status in ('actual','reported'):classification='reported_fact' if not expr else 'derived_history'
            elif status=='derived_actual':classification='derived_history'
            elif writable:
                role=meta.get('parameter_role',meta.get('role',meta.get('classification','')))
                classification=role if role in ('structural_parameter','policy_control','forecast_assumption') else 'forecast_assumption'
                if role=='allocation' or role=='exposure_assumption' and row.get('unit')=='ratio' or any(s in rid for s in ('sensitivity','allocation','_weight')):classification='structural_parameter'
                elif any(s in rid for s in ('policy','payout','buyback','borrowing','repayment','seasonality')):classification='policy_control'
            else:classification='calculated_result' if expr or row.get('kind')=='calculated' else 'structural_parameter'
            classes.setdefault(rid,{})[pid]=classification
            if not writable:continue
            unit=row.get('unit','ratio');is_ratio=unit=='ratio'
            convention=meta.get('value_type') or ('percentage_point_contribution' if rid.endswith(('_pricing','_rig','_fx')) else
                'growth_rate' if is_ratio and any(s in rid for s in ('growth','change','organic','inflation')) else
                'incremental_amount' if not is_ratio and any(s in rid for s in ('budget_change','scope_')) else 'level')
            deps=[dict(driver_id=d['row_id'],period_id=d['period_id']) for d in cell_dependencies(cell,pid)] if expr else []
            anchors=[x for x in deps if periods[x['period_id']]['end']<period['start']]
            for anchor_pid in cell.get('initialization_anchor_periods',row.get('initialization_anchor_periods',[])):
                source=row.get('cells',{}).get(anchor_pid,{})
                if (anchor_pid in periods and periods[anchor_pid]['end']<period['start']
                        and (source.get('value') is not None or source.get('expression'))
                        and not any(x['period_id']==anchor_pid for x in anchors)):
                    anchors.append(dict(driver_id=rid,period_id=anchor_pid))
            constraints=copy.deepcopy(row.get('constraints',{}))
            if row.get('nonnegative'):constraints.setdefault('minimum',0)
            if convention=='growth_rate':constraints.setdefault('minimum',-1)
            if any(s in rid for s in ('effective_activity_sensitivity','_weight','hedge_ratio')):constraints.setdefault('minimum',0)
            if '_weight' in rid or 'hedge_ratio' in rid:constraints.setdefault('maximum',1)
            if rid.startswith('scope_') and rid.endswith(('_tax_rate','_nci_share')):
                constraints.setdefault('minimum',0);constraints.setdefault('maximum',1)
            # Money can be denominated in a native currency rather than the
            # company reporting currency. Shares and dimensionless ratios have
            # no monetary denomination; generic money units use explicit data.
            monetary_unit=re.fullmatch(r'([A-Z]{3})m(?:/shares_m)?',unit)
            currency=meta.get('currency',row.get('currency'))
            if currency is None:
                currency=monetary_unit.group(1) if monetary_unit else spec.get('currency') if unit in ('money','money/shares_m') else None
            fields.append(dict(driver_id=rid,period_id=pid,classification=classification,meaning=row.get('label',rid),
                company=spec['company'],entity=meta.get('entity_id',row.get('section')),cost_pool=meta.get('cost_pool'),
                frequency=period['kind'],period_start=period['start'],period_end=period['end'],unit=unit,
                currency=currency,
                sign='nonnegative' if constraints.get('minimum')==0 else 'signed; follow economic meaning',value_type=convention,
                basis=meta.get('currency_basis',row.get('basis','See stated economic method')),
                historical_anchor=anchors,anchor_date=max((periods[x['period_id']]['end'] for x in anchors),default=None),
                dependencies=deps,constraints=constraints,default=cell.get('value'),default_expression=expr,
                evidence=cell.get('source_refs',row.get('source_refs',{})),method=cell.get('reason') or row.get('note') or row.get('initialization',''),
                provisional=True,override_precedence='Validated scenario > saved model default; summary periods are derived'))
    return dict(schema='financial_input_contract_v1',model_digest=model_logic_digest(spec),company=spec['company'],
        as_of=spec.get('model_configuration',{}).get('as_of'),fields=fields,classifications=classes,
        authority='Saved backend model and validated scenario payload; Excel is an export',
        history_calibration='Use reported_fact and compatible derived_history only; estimated baselines are not independent observations')


def apply_assumption_payload(spec,payload,*,allow_model_refresh=False):
    """Validate a dated scenario atomically; preserve all observations/formulas."""
    if payload.get('schema')!='financial_assumptions_v1':raise ValueError('Expected financial_assumptions_v1 payload')
    if not payload.get('scenario_id'):raise ValueError('Scenario requires a stable scenario_id')
    as_of=payload.get('as_of');date.fromisoformat(as_of or '')
    model_as_of=spec.get('model_configuration',{}).get('as_of')
    if model_as_of and as_of<model_as_of:raise ValueError('Scenario information date precedes saved model information date')
    contract=assumption_contract(spec)
    if not allow_model_refresh and payload.get('model_digest')!=contract['model_digest']:raise ValueError('Scenario model_digest does not match saved financial graph')
    if payload.get('company')!=spec['company']:raise ValueError('Scenario company does not match saved model')
    lookup={(x['driver_id'],x['period_id']):x for x in contract['fields']};seen=set();changes={};inputs=[];intervals={}
    supplied_inputs=payload.get('inputs',[])
    requested_keys=[(x.get('driver_id'),x.get('period_id')) for x in supplied_inputs]
    if len(requested_keys)!=len(set(requested_keys)):raise ValueError('Duplicate scenario input')
    retained={ (x['driver_id'],x['period_id']):copy.deepcopy(x) for x in spec.get('assumption_payload',{}).get('inputs',[]) }
    if payload.get('replace_existing',False):retained={}
    retained.update({(x.get('driver_id'),x.get('period_id')):x for x in supplied_inputs})
    for supplied in retained.values():
        item=copy.deepcopy(supplied);rid=item.get('driver_id');pid=item.get('period_id')
        if allow_model_refresh:rid=spec.get('input_migrations',{}).get(rid,rid);item['driver_id']=rid
        key=(rid,pid)
        if key in seen:raise ValueError('Duplicate scenario input '+str(key))
        seen.add(key);field=lookup.get(key)
        if field is None:raise ValueError('Input is not an authoritative writable business field: '+str(key))
        for attr in ('unit','currency','frequency','value_type'):
            if item.get(attr)!=field[attr]:raise ValueError('Input '+attr+' does not match contract: '+str(key))
        value=item.get('value')
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Scenario values must be finite numbers')
        for bound,op in (('minimum',lambda a,b:a<b),('maximum',lambda a,b:a>b)):
            if bound in field['constraints'] and op(value,field['constraints'][bound]):raise ValueError('Input violates '+bound+': '+str(key))
        for start,end in intervals.setdefault(rid,[]):
            if max(start,field['period_start'])<=min(end,field['period_end']):raise ValueError('Overlapping authoritative input periods: '+rid)
        intervals[rid].append((field['period_start'],field['period_end']))
        changes.setdefault(rid,{})[pid]=value;inputs.append(item)
    spec['assumption_overrides']=changes
    spec['assumption_payload']=dict(payload,model_digest=contract['model_digest'],inputs=inputs)
    spec['input_contract']=contract
    return spec


def evaluate_saved_model(root,run,payload_file=None,*,valuation_payload_file=None):
    """Version a backend scenario, without importing Excel, credentials or an AI client."""
    from pathlib import Path
    import shutil
    from uuid import uuid4
    from .integrated import verified_integrated_record
    from .construction import write_json
    root=Path(root).resolve();parent=Path(run)
    if not parent.is_absolute():parent=root/'outputs'/parent
    record=verified_integrated_record(parent,root/'outputs')
    spec=json.loads((parent/'model_specification.json').read_text(encoding='utf-8'))
    before=model_logic_digest(spec)
    if payload_file:apply_assumption_payload(spec,json.loads(Path(payload_file).read_text(encoding='utf-8')))
    spec['input_contract']=assumption_contract(spec)
    values=calculate_periodic(spec);checks=validate_periodic(spec,values)
    if model_logic_digest(spec)!=before:raise ValueError('Scenario evaluation changed model logic/history')
    directory=root/'outputs'/('evaluate_'+datetime.now().strftime('%Y%m%dT%H%M%S')+'_'+uuid4().hex[:8]);directory.mkdir()
    # The small evidence/configuration journals are preserved so this scenario can
    # itself be refreshed. Originals remain at their verified immutable locations.
    for name in ('company_model_inputs.json','calls.jsonl','code_snapshot.json','fx_snapshot.json'):
        if (parent/name).is_file():shutil.copyfile(parent/name,directory/name)
    write_json(directory/'model_specification.json',spec);write_json(directory/'forecast.json',values)
    write_json(directory/'input_contract.json',spec['input_contract'])
    if spec.get('assumption_payload'):write_json(directory/'assumptions.json',spec['assumption_payload'])
    if (parent/'valuation_inputs.json').is_file() or valuation_payload_file:
        from .workflow import valuation_snapshot
        prior_valuation=json.loads((parent/'valuation_inputs.json').read_text(encoding='utf-8')) if (parent/'valuation_inputs.json').is_file() else None
        data=json.loads((parent/'company_model_inputs.json').read_text(encoding='utf-8'))
        valuation=valuation_snapshot(spec,values,data,previous_inputs=prior_valuation,inputs_file=valuation_payload_file)
        checks+=valuation['checks']
        for name,content in valuation['artifacts'].items():write_json(directory/name,content)
    status='scenario_evaluated_provisional' if not any(c['status'] in ('FAIL','MISSING') for c in checks) else 'incomplete_model'
    write_json(directory/'validation.json',dict(status=status,checks=checks))
    write_json(directory/'evaluation.json',dict(parent_run=str(parent),ai_calls=0,excel_used=False,
        model_digest=before,history_and_formulas_unchanged=True,scenario_id=spec.get('assumption_payload',{}).get('scenario_id'),
        status=status,source_acceptance='Preserved parent evidence; no renewed source review'))
    record.pop('_reuse_verified',None)
    record.update(directory=str(directory),parent_run=str(parent),status=status,
        operation=dict(kind='backend_scenario',ai_calls=0,excel_used=False),
        artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()})
    write_json(directory/'record.json',record)
    return directory


def iter_identity_cells(spec):
    """Yield (identity, period_id, cell) for Python and live Excel checks."""
    periods={p['id']:p for p in spec['periods']}
    for identity in spec.get('identities',[]):
        if identity.get('cells'):
            selected=identity['cells'].items()
        else:
            chosen=identity.get('periods') or [p['id'] for p in spec['periods'] if p.get('status')=='forecast']
            selected=((pid,dict(expression=identity['expression'],bindings=identity.get('bindings',{}))) for pid in chosen)
        for pid,cell in selected:
            if pid not in periods:raise ValueError(f'Unknown identity period {pid}')
            yield identity,pid,cell


def validate_periodic(spec,values):
    results=copy.deepcopy(spec.get('derivation_checks',[]))+copy.deepcopy(spec.get('fx_validation',[]))
    try:rows,periods,cells,_=_plan(spec)
    except (ValueError,KeyError) as exc:return results+[check('period_graph','structure','FAIL',str(exc))]
    results.append(check('period_graph','structure','PASS','Acyclic bound graph and compatible units; historical calibration remains separate from forecast results'))
    for (row,pid),cell in cells.items():
        value=values.get(row,{}).get(pid);name=f'{row}:{pid}'
        status=cell.get('status',periods[pid].get('status'))
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
            results.append(check('period_values',name,'FAIL','Non-finite or nonnumeric result'));continue
        required=cell.get('required',rows[row].get('required',not rows[row].get('optional',False) and status=='forecast'))
        if value is None and required:results.append(check('period_values',name,'MISSING',cell.get('reason','Required forecast value is missing')))
        if value is not None and rows[row].get('nonnegative') and value < -1e-9:
            results.append(check('period_values',name,'FAIL','Negative value for a nonnegative financial balance',value,0))
        if cell.get('expression') and not (cell.get('editable') and rows[row].get('kind') in ('assumption','driver')):
            try:
                expected=_evaluate(expression_tree(cell['expression']),lambda symbol,lag:values[_binding(cell,pid,symbol,lag)[0]][_binding(cell,pid,symbol,lag)[1]])
                if expected is None and value is not None or expected is not None and value is None:
                    results.append(check('period_formula',name,'FAIL','Saved result does not preserve missing dependencies'))
                elif expected is not None and not math.isclose(expected,value,rel_tol=1e-10,abs_tol=1e-8):
                    results.append(check('period_formula',name,'FAIL','Saved value disagrees with its formula',value-expected,1e-8))
            except (ValueError,KeyError,TypeError,OverflowError) as exc:results.append(check('period_formula',name,'FAIL',str(exc)))
    try:
        for identity,pid,cell in iter_identity_cells(spec):
            name=identity.get('id',identity.get('label','identity'))+':'+pid
            tolerance=identity.get('tolerance',1e-6)
            if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or tolerance<0:
                raise ValueError('Identity tolerance must be finite and nonnegative')
            try:
                for dep in cell_dependencies(cell,pid):
                    if dep['row_id'] not in rows or dep['period_id'] not in periods:raise ValueError('Unknown identity target')
                _cell_dimension(cell,pid,rows)
                difference=_evaluate(expression_tree(cell['expression']),lambda symbol,lag:values[_binding(cell,pid,symbol,lag)[0]][_binding(cell,pid,symbol,lag)[1]])
                results.append(check('period_identity',name,'MISSING' if difference is None else 'PASS' if abs(difference)<=tolerance else 'FAIL',
                    identity.get('label',name)+(' [independent control]' if identity.get('independent') else ' [accounting identity]'),difference,tolerance))
            except (ValueError,KeyError,TypeError) as exc:results.append(check('period_identity',name,'FAIL',str(exc)))
    except (ValueError,KeyError) as exc:results.append(check('period_identity','definition','FAIL',str(exc)))
    if spec.get('financial_contracts'):
        from .integrated import validate_financial_contracts
        results.extend(validate_financial_contracts(spec,values))
    return results


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
