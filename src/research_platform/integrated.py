"""Reusable segment and three-statement construction from sourced company data.

Company names, source bindings, segment identities and reported values belong to
the frozen input specification. This module owns a disclosed temporary modelling
policy, its equations and acceptance workflow; it never patches workbook cells.
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4

from .ai import OpenAIProvider, AIError
from .budget import BudgetLedger, ledger_path, company_key
from .construction import (RunJournal, write_json, digest, check, calculate_integrated,
    validate_integrated, recalculate_workbook, _object, _array, TEXT, _enum)
from .evidence import inventory_local_sources
from .initiation import _initiation_lock
from .model_excel import export_integrated


def asset_scope_context(data):
    """Validate disclosed asset scope without assuming a company's presentation.

    Each relation names a reported amount, its declared scope and separate owned
    and leased roles. References and interpretation are company research data.
    """
    roles=dict(data.get('historical',{}),**data.get('schedule_controls',{}))
    result=[]
    for relation in data.get('asset_scope',[]):
        scope=relation['reported_scope']
        if scope not in ('owned_only','owned_and_rou'):raise ValueError('Unsupported asset inclusion scope')
        if not relation.get('source_refs'):raise ValueError('Asset inclusion scope requires cited evidence')
        reported,owned,rou=(relation[k] for k in ('reported_role','owned_role','rou_role'))
        if scope=='owned_only' and relation.get('owned_expression') not in (None,reported):
            raise ValueError('Duplicate subtraction risk: reported amount already excludes ROU')
        if scope=='owned_and_rou' and relation.get('owned_expression') not in (None,reported+' - '+rou):
            raise ValueError('Owned asset mapping disagrees with combined reported scope')
        identities=[]
        for year,value in roles[reported]['values'].items():
            a=roles[owned]['values'].get(year);b=roles[rou]['values'].get(year)
            if value is None or a is None or b is None:continue
            expected=a if scope=='owned_only' else a+b
            if not math.isclose(value,expected,abs_tol=relation.get('tolerance',1e-6),rel_tol=0):
                raise ValueError('Asset scope reconciliation fails for '+year)
            identities.append(dict(period=year,reported=value,owned_excluding_rou=a,right_of_use=b,expected=expected))
        result.append(dict(relation,reconciliations=identities))
    return result


def historical_eligibility_inputs(data):
    """Keep excluded observations out of legacy annual/segment anchor paths.

    Old saved inputs can contain the same number in both an excluded observation
    and an unclassified annual dictionary. An eligible matching observation is
    required to disambiguate that anchor; absence is not permission to calibrate.
    The caller's evidence is retained unchanged, including excluded variants.
    """
    excluded_statuses={'unverified','conflict','excluded','vendor_unverified','primary_conflict'}
    def excluded(o):
        return (o.get('eligible') is False or o.get('restatement') in ('unknown','vendor_normalized')
                or o.get('status') in excluded_statuses)
    if not any(excluded(o) for o in data.get('observations',[])):return data
    result=copy.deepcopy(data);annual={}
    for observation in result.get('observations',[]):
        if excluded(observation):observation['eligible']=False
        if observation.get('kind')=='FY' or observation['period_id'].endswith('-FY'):
            annual.setdefault((observation['row_id'],str(observation.get('fiscal_year',observation['period_id'].split('-')[0]))),[]).append(observation)
    def validate(role,year,value,basis=None,observation_id=None):
        choices=annual.get((role,str(year)),[])
        if value is None or not any(not o.get('eligible',True) for o in choices):return
        matching=[o for o in choices if o.get('eligible',True) and o.get('value') is not None
                  and math.isclose(o['value'],value,rel_tol=0,abs_tol=1e-8)
                  and (basis is None or basis in (o.get('basis'),o.get('compatibility_key')))
                  and (observation_id is None or o['id']==observation_id)]
        if not matching:
            raise ValueError('Historical anchor '+role+':'+str(year)+' has excluded observation evidence without an eligible matching binding; preserve excluded facts for audit and supply eligible primary support')
    for source in (result.get('historical',{}),result.get('schedule_controls',{})):
        for role,history in source.items():
            for year,value in history.get('values',{}).items():
                basis=history.get('basis');basis=basis.get(str(year)) if isinstance(basis,dict) else basis
                validate(role,year,value,basis,history.get('observation_ids',{}).get(str(year)))
    for entity in result.get('segments',[])+[dict(result.get('corporate',{}),id='corporate')]:
        for year in result.get('history_years',[]):
            for metric in ('sales','utop','da','pricing','rig','organic'):
                key=('og' if metric=='organic' else metric)+str(year)
                if key in entity:validate(entity['id']+'_'+metric,year,entity[key])
    return result


def operating_expense_functions(data):
    """Declared additional operating functions extend the default taxonomy."""
    import re
    result=[dict(id=role,label=label) for role,label in (
        ('cogs','Cost of goods sold'),('distribution','Distribution costs'),
        ('marketing_admin','Marketing and administration'),('research','Research and development'))]
    seen={item['id'] for item in result}
    for item in data.get('model_configuration',{}).get('operating_expense_functions',[]):
        role=item.get('id','')
        if not re.fullmatch(r'[a-z][a-z0-9_]*',role) or role in seen:
            raise ValueError('Additional operating function needs a unique financial role: '+role)
        if not item.get('source_refs') or not item.get('definition') or not item.get('label'):
            raise ValueError('Additional operating function requires its label, definition and primary citations: '+role)
        # Do not let an expense declaration overwrite an unrelated statement row.
        if role in integrated_role_contract()['group_roles']:
            raise ValueError('Additional operating function collides with an existing statement role: '+role)
        seen.add(role);result.append(copy.deepcopy(item))
    return result


def cash_scope_policy(data):
    """CF cash equals balance-sheet cash plus the signed disclosed components."""
    import re
    policy=data.get('model_configuration',{}).get('cash_scope')
    if policy is None:return None
    if not policy.get('method') or not policy.get('source_refs'):
        raise ValueError('Cash scope requires a cited definition and method')
    ids=set();roles=set()
    for item in policy.get('components',[]):
        role=item.get('role','');identifier=item.get('id','')
        if not re.fullmatch(r'[a-z][a-z0-9_]*',role) or not re.fullmatch(r'[a-z][a-z0-9_]*',identifier) or role in roles or identifier in ids:
            raise ValueError('Cash-scope component identities must be unique financial roles')
        if role in ('cash','closing_cash','opening_cash','cash_change','short_debt','long_debt','nonlease_debt','total_debt'):
            raise ValueError('Cash-scope component cannot be an aggregate cash or debt role')
        if role!='held_for_sale_cash' and role in integrated_role_contract()['group_roles']:
            raise ValueError('Cash-scope component must use a distinct subaccount rather than overwrite an existing statement role')
        if type(item.get('coefficient')) not in (int,float) or item['coefficient'] not in (-1,1):
            raise ValueError('Cash-scope coefficient must be +1 or -1')
        if type(item.get('included_in_debt')) is not bool or (item['included_in_debt'] and item['coefficient']!=-1):
            raise ValueError('A cash-scope debt component must be explicitly included in debt and deducted from CF cash')
        if not item.get('source_refs') or not item.get('definition'):
            raise ValueError('Cash-scope components require original citations and definitions')
        ids.add(identifier);roles.add(role)
    return copy.deepcopy(policy)


def cashflow_presentation_policy(data):
    """Cited extra cash movements, with separate equity and asset counterparts."""
    import re
    policy=data.get('model_configuration',{}).get('cashflow_presentation')
    if policy is None:return None
    if not policy.get('method') or not policy.get('source_refs'):
        raise ValueError('Cash-flow presentation requires its method and source references')
    seen=set();noncommon=False;distribution=False
    for item in policy.get('components',[]):
        role=item.get('role','');kind=item.get('classification');forecast=item.get('forecast_policy')
        if not re.fullmatch(r'[a-z][a-z0-9_]*',role) or role in seen:
            raise ValueError('Cash-flow component requires a unique financial role: '+role)
        seen.add(role)
        if not all(item.get(k) for k in ('label','definition','source_refs')):
            raise ValueError('Cash-flow component requires cited label and definition: '+role)
        if item.get('cashflow_section') not in ('cfi','cff'):
            raise ValueError('Cash-flow component must identify cfi or cff: '+role)
        if kind=='ordinary_equity_issuance':
            if role!='issuance_cash' or item['cashflow_section']!='cff' or forecast!='existing_issuance_controls' or item.get('equity_role')!='share_capital' or item.get('asset_role') is not None:
                raise ValueError('Ordinary issuance must use issuance_cash and existing share issuance controls')
        elif kind in ('noncommon_equity_issuance','noncommon_equity_distribution'):
            noncommon=True;distribution|=kind=='noncommon_equity_distribution'
            if item['cashflow_section']!='cff' or item.get('equity_role') not in ('reserves','retained_earnings') or item.get('asset_role') is not None:
                raise ValueError('Noncommon equity cash requires a separately cited equity counterpart, never debt: '+role)
            if forecast not in ('no_new_transaction','hold_latest_annual'):
                raise ValueError('Noncommon equity requires an explicit temporary transaction policy: '+role)
        elif kind=='investment_movement':
            if item.get('asset_role')!='short_investments' or item.get('equity_role') is not None or forecast not in ('no_new_transaction','hold_latest_annual'):
                raise ValueError('Investment cash requires the opposite short-investment asset movement: '+role)
        else:raise ValueError('Unsupported cash-flow component classification: '+str(kind))
        if role not in ('issuance_cash','treasury_investments_cf') and role in integrated_role_contract()['group_roles']:
            raise ValueError('Additional cash-flow component cannot overwrite an existing statement role: '+role)
    claim=policy.get('noncommon_equity_claim_role')
    if noncommon and (not isinstance(claim,str) or not re.fullmatch(r'[a-z][a-z0-9_]*',claim) or claim in seen or claim in integrated_role_contract()['group_roles']):
        raise ValueError('Noncommon equity requires a distinct sourced memorandum equity claim role')
    if not noncommon and claim is not None:raise ValueError('Noncommon equity claim requires corresponding classified cash components')
    if distribution:
        eps=data.get('model_configuration',{}).get('financial_contracts',{}).get('adjusted_earnings',{}).get('basic_earnings_adjustment')
        if (not eps or not eps.get('source_refs') or not eps.get('method')
                or eps.get('annual_amount') is None and not eps.get('amounts_by_period')):
            raise ValueError('Noncommon distributions require a separate cited after-tax EPS attribution policy; paid cash cannot substitute for the EPS accrual')
    return copy.deepcopy(policy)


def functional_structure_inputs(data):
    """Supply internal empty taxonomy buckets without inventing reported facts."""
    structure=data.get('model_configuration',{}).get('functional_expense_structure',{})
    allocations=data.get('model_configuration',{}).get('historical_allocations',[])
    policies=data.get('model_configuration',{}).get('structural_account_policies',[])
    cash_scope=cash_scope_policy(data)
    if not structure and not allocations and not policies and cash_scope is None and not data.get('model_configuration',{}).get('cashflow_presentation'):return data
    result=copy.deepcopy(data);allowed={item['id'] for item in operating_expense_functions(data)}
    for role,policy in structure.items():
        included=policy.get('included_in',[])
        if role not in allowed or policy.get('treatment')!='included_in_other_functions' or not included or set(included)-allowed or role in included:
            raise ValueError('Unsupported or overlapping functional expense structure: '+role)
        if not policy.get('source_refs'):raise ValueError('Functional expense classification requires source evidence: '+role)
        existing=[v for source in (data.get('historical',{}),data.get('schedule_controls',{})) for v in source.get(role,{}).get('values',{}).values()]
        existing += [o.get('value') for o in data.get('observations',[]) if o['row_id']==role and o.get('eligible',True)]
        if any(v is not None and v!=0 for v in existing):raise ValueError('A combined expense classification conflicts with a standalone amount: '+role)
        result['historical'][role]=dict(values={str(y):0 for y in data['history_years']},sources={},basis=data['forecast_basis'],
            data_role='structural_parameter',calibration_eligible=False,
            note='No separately reported amount. Costs are included in '+', '.join(included)+'; the internal empty bucket is a classification identity, not a reported zero.')
        result.get('schedule_controls',{}).pop(role,None)
    seen=set()
    policy_by_role={p.get('role'):p for p in policies}
    for policy in policies:
        role=policy.get('role');included=policy.get('included_in',[]);treatment=policy.get('treatment')
        domains={'other_revenue':{'sales'},'net_other_trading':{'net_other_operating'},
                 'net_other_operating':{'net_other_trading'},'exceptional_associate_distribution':set()}
        valid=(role in domains and role not in seen and policy.get('source_refs') and policy.get('definition'))
        if treatment=='included_in_role':valid=valid and bool(included) and set(included)<=domains.get(role,set())
        elif treatment=='inactive_stage':valid=valid and role in ('net_other_trading','net_other_operating','exceptional_associate_distribution') and not included
        else:valid=False
        if not valid:raise ValueError('Unsupported or uncited structural account policy: '+str(role))
        if any(role in policy_by_role.get(target,{}).get('included_in',[]) for target in included):
            raise ValueError('Structural account inclusion cannot be circular')
        seen.add(role)
        if any(target not in result['historical'] for target in included):raise ValueError('Structural account containing role is missing: '+str(included))
        existing=[v for source in (data.get('historical',{}),data.get('schedule_controls',{})) for v in source.get(role,{}).get('values',{}).values()]
        existing += [o.get('value') for o in data.get('observations',[]) if o['row_id']==role and o.get('eligible',True)]
        if any(v is not None and v!=0 for v in existing):raise ValueError('Structural account policy conflicts with a nonzero observation: '+role)
        result['historical'][role]=dict(values={str(y):0 for y in data['history_years']},sources={},basis=data['forecast_basis'],
            data_role='structural_parameter',calibration_eligible=False,classification_source_refs=copy.deepcopy(policy['source_refs']),
            note='Internal classification identity, not a reported zero. '+policy['definition'])
        result.get('schedule_controls',{}).pop(role,None)
    if cash_scope is not None and 'held_for_sale_cash' not in result['historical'] and not any(i['role']=='held_for_sale_cash' for i in cash_scope['components']):
        result['historical']['held_for_sale_cash']=dict(values={str(y):0 for y in data['history_years']},sources={},basis=data['forecast_basis'],
            data_role='structural_parameter',calibration_eligible=False,classification_source_refs=cash_scope['source_refs'],
            note='Inactive held-for-sale cash bridge; the cited company cash-scope components replace the default bridge.')
    allocated=set()
    for item in allocations:
        role=item['row_id'];year=item['year'];amount=item['amount'];key=(role,year)
        if key in allocated:raise ValueError('Duplicate historical allocation: '+str(key))
        allocated.add(key)
        if year not in data['history_years'] or item.get('status')!='estimated' or not item.get('source_refs') or not item.get('method') or not isinstance(amount,(int,float)) or isinstance(amount,bool) or not math.isfinite(amount):
            raise ValueError('Historical allocations require a historical year, finite amount, estimated status, source evidence and method')
        if any(o['row_id']==role and o['period_id']==str(year)+'-FY' and o.get('value') is not None and o.get('eligible',True) for o in data.get('observations',[])):
            raise ValueError('Historical allocation cannot overwrite a source observation: '+role)
        entity=next((s for s in result['segments'] if role==s['id']+'_da'),None)
        if role=='corporate_da':entity=result['corporate']
        if entity is not None:
            entity['da'+str(year)]=amount
            entity.setdefault('source_refs',{})['da'+str(year)]=copy.deepcopy(item['source_refs'][0])
        elif role in result['historical']:
            source=result['historical'][role];source.setdefault('values',{})[str(year)]=amount
            source.setdefault('sources',{})[str(year)]=[]
        else:raise ValueError('Unsupported historical allocation role: '+role)
    return result


def integrated_role_contract(scaffold_source=None):
    """Read canonical historical roles from the scaffold without executing it.

    Literal loop bindings are resolved, but company entities and financial values
    are never evaluated. This catalogue describes identifiers, not evidence that
    a company reports every role or that two accounting definitions are equal.
    """
    import ast
    import inspect
    import textwrap
    source=scaffold_source if scaffold_source is not None else inspect.getsource(build_integrated_spec)
    tree=ast.parse(textwrap.dedent(source));roles=set();anchors=set();segment_suffixes=set();role_sections={}
    class Roles(ast.NodeVisitor):
        def __init__(self):self.bindings={}
        def strings(self,node):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):return {node.value}
            if isinstance(node,ast.Name):
                value=self.bindings.get(node.id)
                return {value} if isinstance(value,str) else set()
            if isinstance(node,ast.IfExp):return self.strings(node.body)|self.strings(node.orelse)
            if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):
                return {left+right for left in self.strings(node.left) for right in self.strings(node.right)}
            return set()
        def visit_FunctionDef(self,node):
            if node.name=='build_integrated_spec':
                for statement in node.body:self.visit(statement)
        def visit_For(self,node):
            old=self.bindings.copy()
            def bind(target,value):
                if isinstance(target,ast.Name):self.bindings[target.id]=value
                elif isinstance(target,(ast.Tuple,ast.List)):
                    values=value if isinstance(value,(tuple,list)) else [None]*len(target.elts)
                    for item,part in zip(target.elts,values):bind(item,part)
            try:values=ast.literal_eval(node.iter)
            except (ValueError,TypeError):values=[None]
            if not isinstance(values,(list,tuple,set)):values=[None]
            for value in values:
                self.bindings=old.copy();bind(node.target,value)
                for statement in node.body:self.visit(statement)
            self.bindings=old
            for statement in node.orelse:self.visit(statement)
        def visit_Call(self,node):
            name=node.func.id if isinstance(node.func,ast.Name) else None
            positions={'row':(0,),'val':(0,),'ratio':(1,2),'composed':(0,1)}.get(name,())
            for index in positions:
                if len(node.args)>index:
                    found=self.strings(node.args[index]);roles.update(found)
                    if name in ('val','ratio'):anchors.update(found)
            if name=='row':
                row_roles=self.strings(node.args[0]) if node.args else set()
                for keyword in node.keywords:
                    if keyword.arg=='role':
                        found=self.strings(keyword.value);roles.update(found);row_roles.update(found)
                if len(node.args)>2:
                    for role in row_roles:role_sections.setdefault(role,set()).update(self.strings(node.args[2]))
                # Segment identifiers come from supplied entities. Retain their
                # suffix contract separately from static group identifiers.
                if node.args and isinstance(node.args[0],ast.BinOp) and isinstance(node.args[0].left,ast.Name) and node.args[0].left.id not in self.bindings:
                    segment_suffixes.update(value for value in self.strings(node.args[0].right) if value.startswith('_'))
            if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='historical' and node.func.attr=='get' and node.args:
                roles.update(self.strings(node.args[0]))
            self.generic_visit(node)
        def visit_Subscript(self,node):
            if isinstance(node.value,ast.Name) and node.value.id=='historical':roles.update(self.strings(node.slice))
            self.generic_visit(node)
    Roles().visit(tree)
    # The configurable function loop is not an AST literal loop. Preserve the
    # canonical baseline expense roles in the research contract explicitly.
    if scaffold_source is None:
        standard={item['id'] for item in operating_expense_functions({})}
        roles.update(standard);anchors.update(standard)
        for role in standard:role_sections.setdefault(role,set()).add('income')
        source+='\n'+inspect.getsource(operating_expense_functions)
    # Corporate identifiers are explicit scaffold rows, not group aliases.
    corporate={role for role in roles if role.startswith('corporate_')}
    return dict(version='scaffold_roles_v1',source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        group_roles=sorted(roles-corporate),corporate_roles=sorted(corporate),
        anchor_roles=sorted(anchors),segment_role_suffixes=sorted(segment_suffixes),
        role_sections={role:sorted(sections) for role,sections in sorted(role_sections.items()) if sections},
        interpretation='Canonical identifiers only; preserve company definitions, missing evidence and separately identified historical entities.')


def build_integrated_spec(data, forecast_years=5):
    """Build the annual role scaffold used by the causal period compiler.

    Historical statement signs are preserved. Forecast operating costs are shown
    negative; segment pre-D&A costs are positive magnitudes. Opening-asset/debt timing
    avoids circularity and makes capex/financing effects explicit in following years.
    This compatibility scaffold is not a construction/export entry point: the
    period compiler replaces its legacy economics with financial contracts before
    calculation, review and export, including for annual-only companies.
    """
    data=functional_structure_inputs(historical_eligibility_inputs(data))
    functions=operating_expense_functions(data)
    cash_scope=cash_scope_policy(data)
    cashflow_policy=cashflow_presentation_policy(data)
    extra_cash_components=(cashflow_policy or {}).get('components',[])
    historical = copy.deepcopy(data['historical'])
    for key, supplement in data.get('schedule_controls', {}).items():
        if key not in historical:
            historical[key]=copy.deepcopy(supplement)
            continue
        target=historical[key]
        for year,value in supplement.get('values',{}).items():
            old=target.get('values',{}).get(year)
            if old is not None and value is not None and old != value:
                raise ValueError(f'Conflicting historical/schedule anchors {key}:{year}: {old} vs {value}')
        for field in ('values','sources','basis'):
            if isinstance(supplement.get(field),dict):
                if not isinstance(target.get(field),dict):
                    original=target.get(field)
                    target[field]={year:original for year in target.get('values',{})} if field=='basis' else {}
                for year,item in supplement[field].items():
                    if supplement.get('values',{}).get(year) is None and target.get('values',{}).get(year) is not None:
                        continue
                    target[field][year]=copy.deepcopy(item)
    past = list(data['history_years']); base = max(past); b = str(base)
    if base-1 not in past or forecast_years < 1:
        raise ValueError('Construction requires the latest two annual periods and at least one forecast year')
    future = list(range(base + 1, base + 1 + forecast_years))
    split_tax=all(k in historical for k in ('current_tax_expense','deferred_tax_expense','deferred_tax_assets','deferred_tax_liabilities'))
    spec = dict(company=data['company'], currency=data['currency'], historical_years=past,
        forecast_years=future, sections=[], rows=[], identities=[], sources=list(data['sources'].values()) if isinstance(data['sources'],dict) else data['sources'],
        gaps=[], historical_segments=data.get('historical_segments', []), interims=data.get('interims', []),
        reporting_changes=data.get('reporting_changes', []),
        forecast_basis=data['forecast_basis'], policies={
          'growth':'Disclosed additive pricing plus real internal growth; RIG can include mix, not physical volume.',
          'operating_costs':'Prior segment operating costs before D&A grow with RIG, cost inflation and translation. These costs include noncash compensation; the CFO schedule adds that component back. No independent group revenue forecast.',
          'depreciation':'Owned assets, ROU and intangibles depreciate/amortise from opening balances. Allocate total D&A using last disclosed segment shares.',
          'financing':'Opening debt determines interest; explicit borrowing and repayment inputs. The unchanged-debt baseline assumes continued funding/rollover and omits offsetting gross refinancing flows; it does not prove contractual maturities can be funded. No automatic balancing debt plug. Negative cash fails acceptance.',
          'acquisitions':'No new acquisitions/disposals in the temporary baseline; no invented purchase-price allocation.',
          'tax':'Effective P&L tax, current/deferred P&L split and cash-payment ratio are separate. Cash settlement is initialized from paid tax / current P&L tax where that split is disclosed. Current charge less cash payments changes current tax liabilities; deferred P&L charge changes deferred liabilities. Deferred/current tax assets and tax OCI/FX held flat in the temporary baseline.',
          'equity':'Retained earnings, treasury shares, reserves and NCI roll through profit, distributions, buybacks and equity-settled compensation.',
          'fx':'Segment sales/cost translation assumptions are zero initially; balance-sheet FX and cash FX zero. This is not a quantified currency-exposure model.'})
    if cashflow_policy:spec['cashflow_presentation_contract']=copy.deepcopy(cashflow_policy)
    if data.get('associate_scope'):spec['policies']['associates']=data['associate_scope']
    def val(role, year=base):
        value = historical.get(role, {}).get('values', {}).get(str(year))
        if not isinstance(value, (int, float)):
            raise ValueError(f'Missing required sourced anchor {role}:{year}')
        return value
    def section(key, label): spec['sections'].append(dict(id=key,label=label))
    def row(key, label, sec, expr=None, *, role=None, unit='money', hist=None,
            note='', subtotal=False, nonnegative=False, historical_expression=None):
        source=historical.get(role or key,{})
        r=dict(id=key,label=label,section=sec,unit=unit,kind='calculated' if expr else 'reported',
            historical=copy.deepcopy(source.get('values',{}) if hist is None else hist),
            source_refs=copy.deepcopy(source.get('sources',{})),basis=source.get('basis',data['forecast_basis']),
            note=note,style='subtotal' if subtotal else 'normal',nonnegative=nonnegative)
        if expr is not None:r['expression']=expr
        if historical_expression:r['historical_expression']=historical_expression
        if source.get('data_role')=='structural_parameter':
            r.update(data_role='structural_parameter',calibration_eligible=False,kind='calculated',note=source['note'])
        spec['rows'].append(r);return r
    def assumption(key,label,sec,value,unit='ratio',note='', refs=None):
        r=row(key,label,sec,unit=unit,hist={b:value},note='TEMPORARY: '+note)
        r.update(kind='assumption',inputs={str(y):value for y in future},
            initialization=note,relationship='temporary modelling assumption',source_refs={b:refs or []})
        return key
    def identity(key,label,expr,periods=None,tolerance=1e-6,independent=False):
        spec['identities'].append(dict(id=key,label=label,expression=expr,
            periods=periods or [str(y) for y in future],tolerance=tolerance,independent=independent))
    def quotient(num,den,label):
        if den == 0:
            if num == 0:return 0.0
            raise ValueError(f'Cannot initialise {label}: nonzero numerator with zero reported denominator')
        return num/den
    def ratio(key,num,den):return quotient(val(num),val(den),key)
    def composed(left,right,net=None):
        if net and net in historical and (left not in historical or right not in historical):
            return copy.deepcopy(historical[net].get('values',{}))
        if left not in historical or right not in historical:
            raise ValueError('Supply the reported net account '+str(net)+' or both gross components '+left+' and '+right)
        return {str(y):(historical[left]['values'].get(str(y))+historical[right]['values'].get(str(y)))
            if historical[left]['values'].get(str(y)) is not None and historical[right]['values'].get(str(y)) is not None else None for y in past}
    def lag(key):return f'lag("{key}", 1)'
    def total(keys):return ' + '.join(keys) or '0'

    section('shared','Shared conventions and temporary baseline')
    assumption('cash_fx_assumption','Cash translation / other FX movements','shared',0,'money',
               'Zero future cash FX; no inferred purchasing-currency exposure.')
    row('forecast_basis_note','Forecast segments follow the published restated basis','shared',
        unit='ratio',hist={},note=str(data['forecast_basis']))['optional']=True
    segments=[]
    da_total=val('da')
    for seg in data['segments']:
        key=seg['id'];sec='segment_'+key;segments.append(key)
        section(sec,seg['label']+' — operating build')
        revenue_model=data.get('model_configuration',{}).get('revenue_models',{}).get(key,{})
        aggregate_organic=revenue_model.get('method')=='aggregate_organic'
        values={name:seg[f'{name}{base}'] for name in ('sales','utop','da')}
        values.update({name:seg.get(f'{name}{base}',0) if aggregate_organic else seg[f'{name}{base}'] for name in ('pricing','rig')})
        refs=seg.get('source_refs',{})
        price=assumption(key+'_pricing','Pricing contribution',sec,values['pricing'],note=
            'Hold last completed annual pricing contribution. Additive with RIG; not a latest-quarter policy or validated forecast.',refs=[refs.get(f'pricing{base}',{})])
        activity=assumption(key+'_rig','Real internal growth (volume and mix)',sec,values['rig'],note=
            'Hold last completed annual RIG, including product mix. This is an activity proxy, not observed physical volume.',refs=[refs.get(f'rig{base}',{})])
        fx=assumption(key+'_fx','FX translation contribution',sec,0,note='Neutral temporary translation; not a measured exposure.')
        inflation=assumption(key+'_cost_inflation','Operating-cost inflation before D&A',sec,values['pricing'],note=
            'Temporary proxy initialized to last pricing contribution, NOT reported unit-cost inflation. Costs also scale with RIG. Includes operating costs other than D&A.')
        share=assumption(key+'_da_share','Share of group D&A allocation',sec,quotient(values['da'],da_total,'segment D&A allocation'),note=
            'Fixed allocation based on last disclosed segment D&A. Changes in capex affect next-year depreciation.',refs=[refs.get(f'da{base}',{})])
        r=row(key+'_sales','Sales',sec,f'{lag(key+"_sales")} * (1 + {price} + {activity} + {fx})',hist={b:values['sales']},subtotal=True)
        r['source_refs']={b:[refs[f'sales{base}']]}
        row(key+'_organic','Organic growth',sec,f'{price} + {activity}',unit='ratio',hist={b:seg.get(f'og{base}')},
            note='Historical published rounded OG can differ by 0.1 percentage point from rounded pricing + RIG.')['source_refs']={b:[refs.get(f'og{base}',{})]}
        row(key+'_growth','Modelled sales growth (no transactions)',sec,f'{price} + {activity} + {fx}',unit='ratio',hist={},
            note='No acquisition contribution in the baseline; requires a purchase-accounting specification before activation.')
        row(key+'_pricing_effect','Pricing contribution to sales',sec,f'{lag(key+"_sales")} * {price}',hist={})
        row(key+'_rig_effect','RIG contribution to sales',sec,f'{lag(key+"_sales")} * {activity}',hist={})
        row(key+'_fx_effect','FX contribution to sales',sec,f'{lag(key+"_sales")} * {fx}',hist={})
        cost=values['sales']-values['utop']-values['da']
        row(key+'_cash_cost','Operating costs before D&A (positive)',sec,f'{lag(key+"_cash_cost")} * (1 + {activity} + {fx}) * (1 + {inflation})',
            hist={b:cost},note='Derived sales less underlying trading profit less disclosed D&A; cost categories not separately disclosed.',nonnegative=True)
        row(key+'_ebitda','Underlying profit before D&A',sec,key+'_sales - '+key+'_cash_cost',hist={b:values['utop']+values['da']},subtotal=True)
        row(key+'_da','Allocated depreciation and amortisation',sec,'da * '+share,hist={b:values['da']})
        row(key+'_utop','Underlying trading operating profit',sec,key+'_ebitda - '+key+'_da',hist={b:values['utop']},subtotal=True)['source_refs']={b:[refs[f'utop{base}']]}
        row(key+'_margin','Underlying trading margin',sec,key+'_utop / '+key+'_sales',unit='ratio',hist={b:values['utop']/values['sales']})
        identity(key+'_sales_bridge',seg['label']+' sales bridge',key+'_sales - ('+lag(key+'_sales')+' + '+key+'_pricing_effect + '+key+'_rig_effect + '+key+'_fx_effect)')
        if aggregate_organic:
            organic=seg.get(f'og{base}')
            if organic is None:raise ValueError('Aggregate organic mode requires a cited organic growth anchor: '+key)
            selected={r['id']:r for r in spec['rows']}
            for suffix in ('pricing','rig'):
                selected[key+'_'+suffix].update(kind='calculated',expression='0',historical={},inputs={},support_matrix=True,
                    note='Decomposition not disclosed; inactive calculation placeholder, not a reported zero or writable forecast.')
            selected[key+'_organic'].update(kind='assumption',inputs={str(y):organic for y in future},
                initialization='Hold last annual disclosed aggregate organic growth; provisional forecast.',
                note=revenue_model.get('definition','Aggregate organic growth; no inferred price-volume decomposition.'))
            selected[key+'_organic'].pop('expression',None)
            selected[key+'_growth']['expression']=key+'_organic + '+key+'_fx'
            selected[key+'_sales']['expression']=lag(key+'_sales')+' * (1 + '+key+'_organic + '+key+'_fx)'
            selected[key+'_pricing_effect'].update(label='Organic growth contribution to sales',expression=lag(key+'_sales')+' * '+key+'_organic')
            selected[key+'_rig_effect'].update(expression='0',support_matrix=True)

    section('corporate','Corporate and group consolidation')
    corp=data['corporate'];corp_utop=corp[f'utop{base}'];corp_da=corp[f'da{base}']
    assumption('corporate_cost_growth','Corporate operating-cost growth before D&A','corporate',0,note='Hold corporate operating costs before D&A nominally flat; explicit temporary convention.')
    assumption('corporate_da_share','Corporate share of D&A','corporate',quotient(corp_da,da_total,'corporate D&A allocation'),note='Last disclosed allocation share.')
    row('corporate_cash_cost','Corporate operating costs before D&A','corporate',lag('corporate_cash_cost')+' * (1 + corporate_cost_growth)',hist={b:-corp_utop-corp_da})
    row('corporate_da','Corporate depreciation and amortisation','corporate','da * corporate_da_share',hist={b:corp_da})
    row('corporate_utop','Corporate / unallocated underlying profit','corporate','-corporate_cash_cost - corporate_da',hist={b:corp_utop},subtotal=True)
    row('sales','Group sales from operating segments','corporate',total([k+'_sales' for k in segments]),subtotal=True,nonnegative=True)
    row('utop','Group underlying trading operating profit','corporate',total([k+'_utop' for k in segments])+ ' + corporate_utop',subtotal=True)
    identity('segment_sales','Segment sales to group sales','sales - ('+total([k+'_sales' for k in segments])+')',[b]+[str(y) for y in future],1e-6,True)
    identity('segment_profit','Segment profit plus corporate to group UTOP','utop - ('+total([k+'_utop' for k in segments])+ ' + corporate_utop)',[b]+[str(y) for y in future],1e-6,True)
    identity('da_allocation','D&A allocation shares sum to one',total([k+'_da_share' for k in segments])+' + corporate_da_share - 1')

    section('income','Group income statement')
    assumption('other_revenue_ratio','Other revenue / sales','income',ratio('x','other_revenue','sales'),note='Hold latest disclosed ratio; other revenue is separate from sales.')
    row('other_revenue','Other revenue','income','sales * other_revenue_ratio')
    row('total_revenue','Total revenue including other revenue','income','sales + other_revenue',subtotal=True)
    core_cost=val('total_revenue')-val('utop')
    for function in functions:
        role,label=function['id'],function['label']
        assumption(role+'_allocation',label+' allocation','income',-val(role)/core_cost,note=
            'Forecast allocation of group underlying costs using last reported functional expense shares; not a separately observed segment cost mix.')
        row(role,label,'income','-(total_revenue - utop) * '+role+'_allocation')
    row('gross_profit','Gross profit (sales less COGS)','income','sales + cogs',subtotal=True)
    row('is_utop','Underlying trading profit — statement view','income','total_revenue + '+total([item['id'] for item in functions]),hist=historical['utop']['values'],subtotal=True)
    assumption('net_other_trading_assumption','Net other trading income / (expense)','income',0,'money',
        'No future restructuring or impairment costs in temporary baseline. Explicitly provisional, not a claim that recurring costs disappear.')
    row('net_other_trading','Net other trading income / (expense)','income','net_other_trading_assumption',hist=composed('other_trading_income','other_trading_expense','net_other_trading'))
    row('trading_profit','Trading operating profit','income','utop + net_other_trading',subtotal=True)
    assumption('net_other_operating_assumption','Other operating income / (expense)','income',0,'money',
        'No future disposals or other nontrading items. Activation requires an evidenced asset/cash counterpart.')
    row('net_other_operating','Net other operating income / (expense)','income','net_other_operating_assumption',hist=composed('other_operating_income','other_operating_expense','net_other_operating'))
    row('operating_profit','Operating profit','income','trading_profit + net_other_operating',subtotal=True)
    row('financial_income','Financial income','income','cash_interest + other_financial_income')
    row('financial_expense','Financial expense','income','-debt_interest - lease_interest - other_financial_cost')
    row('pretax','Profit before tax and associates','income','operating_profit + financial_income + financial_expense',subtotal=True)
    assumption('effective_tax_rate','Effective income tax rate','income',-val('tax_expense')/val('pretax'),note='Latest reported P&L tax expense / profit before tax, separate from cash payments.')
    row('tax_expense','Income tax expense','income','-pretax * effective_tax_rate')
    row('associate_profit','Share of results of associates','income',lag('associates')+' * associate_earnings_yield')
    row('total_profit','Profit for the year — Group including NCI','income','pretax + tax_expense + associate_profit',subtotal=True)
    assumption('nci_profit_share','Non-controlling share of group profit','income',val('nci_profit')/val('total_profit'),note='Hold latest attribution ratio; not parent profit.')
    row('nci_profit','Profit attributable to non-controlling interests','income','total_profit * nci_profit_share')
    row('parent_profit','Profit attributable to shareholders','income','total_profit - nci_profit',subtotal=True)
    if 'shares_end_outstanding' in historical:
        row('shares_end_outstanding','Closing shares outstanding (millions)','income',lag('shares_end_outstanding')+' - buyback_shares',unit='shares_m',nonnegative=True)
    opening_shares='shares_end_outstanding' if 'shares_end_outstanding' in historical else 'shares_basic'
    row('shares_basic','Weighted-average basic shares (millions)','income',lag(opening_shares)+' - buyback_shares',unit='shares_m',nonnegative=True,
        note='Buybacks assumed at start of year for EPS. No new issuance in baseline.')
    row('eps_basic','Basic earnings per share','income','parent_profit / shares_basic',unit='money/shares_m')
    # Declare these roles before period source binding; a reported EPS remains
    # a fact even when its independent diluted denominator is undisclosed.
    row('shares_diluted','Diluted weighted-average shares','income','shares_basic',unit='shares_m',nonnegative=True)
    row('eps_diluted','Diluted earnings per share','income','parent_profit / shares_diluted',unit='money/shares_m')
    identity('cost_allocation','Functional cost shares sum to one',total([item['id']+'_allocation' for item in functions])+' - 1')
    identity('is_utop','Statement UTOP to segment UTOP','is_utop - utop')
    identity('profit_attribution','Total profit equals parent plus NCI','total_profit - parent_profit - nci_profit',[str(y) for y in past+future],1.5,True)
    identity('income_statement','Income statement profit bridge','total_profit - (operating_profit + financial_income + financial_expense + tax_expense + associate_profit)',[str(y) for y in past+future],3,True)

    section('cashflow','Cash flow statement')
    row('cf_net_profit','Profit for the year','cashflow','total_profit',role='total_profit')
    row('da','Depreciation and amortisation','cashflow','owned_ppe_depreciation + rou_depreciation + amortization')
    assumption('sbc_ratio','Equity-settled compensation / sales','cashflow',val('sbc')/val('sales'),note='Latest noncash share-compensation cash-flow addback. Forecast equity credit equals expense; no new withholding/settlement transactions.')
    row('sbc','Share-based compensation addback','cashflow','sales * sbc_ratio')
    row('cf_associates','Remove noncash associate earnings','cashflow','-associate_profit',hist={str(y):-v for y,v in historical['associate_profit']['values'].items()})
    row('associate_dividends','Cash distributions and interest from associates','cashflow','associate_profit * associate_distribution_ratio')
    row('cf_tax_timing','Tax expense less cash tax payments','cashflow','-tax_expense + paid_tax',hist={},historical_expression='-tax_expense + paid_tax')
    operating_adjustments=[]
    for key,label in [('impairment','Impairment addback'),('disposal_result_cf','Net disposal result adjustment'),
            ('other_noncash_ex_sbc','Other noncash adjustments excluding share compensation'),
            ('other_operating_assets_liabilities_cf','Other operating asset and liability movements'),
            ('cf_finance_timing','Financial P&L to treasury cash settlement bridge')]:
        if key in historical:
            row(key,label,'cashflow','0 * sales',note='Historical original cash-flow bridge. Zero future noncash/settlement difference under the disclosed baseline; not an omitted historical cash movement.')
            operating_adjustments.append(key)
    row('wc_inventory_cf','Change in inventories — cash effect','cashflow',lag('inventories')+' - inventories')
    row('wc_receivables_cf','Change in receivables — cash effect','cashflow',lag('receivables')+' - receivables')
    row('wc_payables_cf','Change in trade payables — cash effect','cashflow','trade_payables - '+lag('trade_payables'))
    wc_extra=[]
    for key,label in [('wc_prepayments_cf','Change in prepayments — cash effect'),('wc_accruals_cf','Change in accruals — cash effect')]:
        if key in historical:
            row(key,label,'cashflow','0 * sales',note='Disclosed historical movement; corresponding forecast balances held flat.')
            wc_extra.append(key)
    row('wc_cash','Operating working-capital cash effect','cashflow','wc_inventory_cf + wc_receivables_cf + wc_payables_cf'+(' + '+total(wc_extra) if wc_extra else ''),subtotal=True,
        note='Historical disclosed WC includes prepayments/accruals and FX/scope effects. Forecast other operating balances held flat; do not infer historic CF from closing BS differences.')
    for rid,label in [('cfo_portfolio_noncash','Modelled noncash portfolio gain / loss reversal'),
                      ('cfo_fx_noncash','Modelled noncash monetary FX reversal')]:
        row(rid,label,'cashflow','0 * sales',hist={},note='Incremental modelled noncash reversal; disclosed historical adjustments remain in their original cash-flow rows.')
    cfo_historical='cf_net_profit + da + sbc + cf_associates + associate_dividends + cf_tax_timing + wc_cash'+(' + '+total(operating_adjustments) if operating_adjustments else '')
    cfo_equation=cfo_historical+' + cfo_portfolio_noncash + cfo_fx_noncash'
    row('cfo','Net cash from operating activities','cashflow',cfo_equation,subtotal=True)
    row('capex_ppe','Cash capital expenditure — owned PPE','cashflow','-sales * capex_ppe_ratio')
    row('capex_intangibles','Cash investment in intangible assets','cashflow','-sales * capex_intangible_ratio')
    for item in extra_cash_components:
        role=item['role']
        expr='0 * sales'
        if item['forecast_policy']!='existing_issuance_controls':
            control=role+'_annual_policy'
            hold=item['forecast_policy']=='hold_latest_annual'
            assumption(control,item['label']+' — annual cash policy','financing',val(role) if hold else 0,'money',
                ('Hold latest sourced annual cash amount' if hold else 'Explicit no-new-transaction scenario, not a reported zero')+
                ', allocated by fiscal duration. Paid cash is distinct from any EPS accrual.',
                refs=historical.get(role,{}).get('sources',{}).get(b,[]) if hold else item['source_refs'])
            expr=control
        row(role,item['label'],'cashflow',expr,note=item['definition']+' '+item['forecast_policy'])
    investing_adjustments=[]
    for key,label in [('business_acquisitions_cf','Acquisition of businesses'),('business_disposals_cf','Disposal of businesses'),
            ('associate_investing_cf','Investments / divestments in associates'),('treasury_investments_cf','Treasury investments'),
            ('other_investing_combined_cf','Other investing including long-term investments')]:
        if key in historical:
            configured=next((i for i in extra_cash_components if i['role']==key),None)
            if not configured:row(key,label,'cashflow','0 * sales',note='Historical cash transaction retained; no new transaction in the temporary forecast. Activation needs a supported asset/equity counterpart.')
            if not configured or configured['cashflow_section']=='cfi':investing_adjustments.append(key)
    investing_adjustments += [i['role'] for i in extra_cash_components if i['cashflow_section']=='cfi' and i['role'] not in investing_adjustments]
    cfi_equation='capex_ppe + capex_intangibles'+(' + '+total(investing_adjustments) if investing_adjustments else '')
    row('cfi','Net cash used in investing activities','cashflow',cfi_equation,subtotal=True,
        note='No new acquisitions, disposals or treasury-investment movements in the baseline; existing balances retained.')
    row('dividends_parent','Dividends to shareholders','cashflow','-parent_profit * dividend_payout')
    row('dividends_nci','Dividends to non-controlling interests','cashflow','-nci_profit * nci_dividend_payout')
    row('buybacks','Treasury share purchases','cashflow','-buyback_cash')
    row('debt_borrow','New non-lease borrowings','cashflow','borrowing_input')
    row('debt_repay','Non-lease repayments','cashflow','-repayment_input',note='Forecast row excludes lease principal, shown separately. Historical company aggregate includes leases.')
    row('lease_principal','Lease principal payments','cashflow','-lease_principal_input',hist={},note='Temporary forecast policy, not an inferred historical split of total lease cash outflows.')
    financing_adjustments=[]
    for key,label in [('nci_acquisition_cf','Acquisition / disposal of non-controlling interests'),('short_debt_cash','Historical current-debt cash movements')]:
        if key in historical:
            row(key,label,'cashflow','0 * sales',note='Original financing movement retained. Future new debt is in the explicit borrowing/repayment controls; no new NCI acquisition.')
            financing_adjustments.append(key)
    financing_adjustments += [i['role'] for i in extra_cash_components if i['cashflow_section']=='cff']
    cff_historical='dividends_parent + dividends_nci + buybacks + debt_borrow + debt_repay'+(' + '+total(financing_adjustments) if financing_adjustments else '')
    row('cff','Net cash used in financing activities','cashflow',cff_historical+' + lease_principal',subtotal=True)
    if len(operating_adjustments)==5:
        identity('cfo_components','Historical operating cash subtotal from disclosed adjustments','cfo - ('+cfo_historical+')',[str(y) for y in past],1.5,True)
    if len(investing_adjustments)==5 or any(i['cashflow_section']=='cfi' for i in extra_cash_components):
        identity('cfi_components','Historical investing cash subtotal from visible movements','cfi - ('+cfi_equation+')',[str(y) for y in past],1.5,True)
    if len(financing_adjustments)==2 or any(i['cashflow_section']=='cff' for i in extra_cash_components):
        identity('cff_components','Historical financing cash subtotal from visible movements','cff - ('+cff_historical+')',[str(y) for y in past],1.5,True)
    if len(wc_extra)==2:
        covered=[str(y) for y in past if all(historical.get(k,{}).get('values',{}).get(str(y)) is not None
            for k in ('wc_cash','wc_inventory_cf','wc_receivables_cf','wc_payables_cf','wc_prepayments_cf','wc_accruals_cf'))]
        identity('wc_components','Reported working capital movement detail','wc_cash - wc_inventory_cf - wc_receivables_cf - wc_payables_cf - wc_prepayments_cf - wc_accruals_cf',covered,1.5,True)
    row('cash_fx','Currency effects on cash','cashflow','cash_fx_assumption')
    row('cash_change','Net change in cash including FX','cashflow','cfo + cfi + cff + cash_fx',subtotal=True,
        note='Historical reported cash_change may exclude FX; opening/closing controls below use the company cash statement.')
    row('opening_cash','Opening cash — cash-flow scope' if cash_scope is not None else 'Opening cash including held-for-sale scope','cashflow',lag('closing_cash'))
    row('closing_cash','Closing cash — cash-flow scope','cashflow','opening_cash + cash_change',subtotal=True,nonnegative=not cash_scope or not any(i['included_in_debt'] for i in cash_scope['components']))
    row('held_for_sale_cash','Cash within assets held for sale','cashflow','held_for_sale_cash_input',note='Explicit CF-to-BS scope bridge.')
    cash_bridge='closing_cash - held_for_sale_cash'
    if cash_scope is not None:
        cash_bridge='closing_cash'
        for component in cash_scope['components']:
            role=component['role']
            if role!='held_for_sale_cash':
                control=row(role,component['definition'],'cashflow',note='Hold the last sourced closing balance; separately declared cash scope, not operating cash flow.',nonnegative=True)
                control.update(kind='assumption',metric_type='stock',inputs={str(y):val(role) for y in future},
                    initialization='Hold latest sourced closing cash-scope component; changes occur at period end unless a dated model specifies otherwise.')
            cash_bridge+=(' - ' if component['coefficient']==1 else ' + ')+role
        spec['cash_scope_contract']=copy.deepcopy(cash_scope)
    row('cf_to_bs_cash','Closing balance-sheet cash','cashflow',cash_bridge,role='cash',subtotal=True)
    identity('cash_roll','Cash flow opening-to-closing reconciliation','closing_cash - opening_cash - cfo - cfi - cff - cash_fx',[str(y) for y in past+future],2.5,True)
    identity('cash_scope','Cash flow to balance-sheet cash scope',cash_bridge+' - cash',[b]+[str(y) for y in future],1.5,True)

    section('balance','Balance sheet')
    row('cash','Cash and cash equivalents','balance','cf_to_bs_cash',nonnegative=True)
    row('short_investments','Short-term investments','balance',lag('short_investments'),nonnegative=True)
    investment_roles=[i['role'] for i in extra_cash_components if i['classification']=='investment_movement']
    if investment_roles:spec['rows'][-1]['expression']+=' - ('+total(investment_roles)+')'
    row('inventories','Inventories','balance','-cogs * inventory_ratio',nonnegative=True)
    row('receivables','Trade and other receivables','balance','sales * receivables_ratio',nonnegative=True)
    row('other_current_assets','Other current assets','balance',lag('other_current_assets'),nonnegative=True)
    row('current_assets','Total current assets','balance','cash + short_investments + inventories + receivables + other_current_assets',subtotal=True)
    row('ppe','Property, plant and equipment including ROU','balance','owned_ppe + right_of_use_assets',nonnegative=True)
    row('goodwill','Goodwill','balance',lag('goodwill'),nonnegative=True)
    row('intangibles','Intangible assets','balance',lag('intangibles')+' - capex_intangibles - amortization',nonnegative=True)
    row('associates','Investments in associates and joint ventures','balance',lag('associates')+' + associate_profit - associate_dividends',nonnegative=True,
        note=data.get('associate_scope','Cash-return and earnings scope must match the reported carrying-value scope.'))
    if split_tax:
        row('deferred_tax_assets','Deferred tax assets','balance',lag('deferred_tax_assets'),nonnegative=True)
        row('other_noncurrent_assets_ex_tax','Other non-current assets excluding deferred tax','balance',lag('other_noncurrent_assets_ex_tax'),hist={str(y):historical['other_noncurrent_assets']['values'][str(y)]-historical['deferred_tax_assets']['values'][str(y)] for y in past})
    row('other_noncurrent_assets','Other non-current assets','balance','other_noncurrent_assets_ex_tax + deferred_tax_assets' if split_tax else lag('other_noncurrent_assets'),nonnegative=True)
    row('noncurrent_assets','Total non-current assets','balance','ppe + goodwill + intangibles + associates + other_noncurrent_assets',subtotal=True)
    row('total_assets','TOTAL ASSETS','balance','current_assets + noncurrent_assets',subtotal=True)
    row('short_debt','Current financial debt, including leases','balance','total_debt * current_debt_share',nonnegative=True)
    row('trade_payables','Trade and other payables','balance','-cogs * payables_ratio',nonnegative=True)
    row('current_tax_liabilities','Current income tax liabilities','balance',lag('current_tax_liabilities')+(' - current_tax_expense + paid_tax' if split_tax else ' - tax_expense + paid_tax'),nonnegative=True,
        note='Current P&L tax charge less cash payments; current tax assets held flat. Tax reclassifications/FX require a separate scenario specification.')
    row('other_current_liabilities_ex_tax','Other current liabilities excluding income tax','balance',lag('other_current_liabilities_ex_tax'),
        hist={str(y):historical['other_current_liabilities']['values'][str(y)]-historical['current_tax_liabilities']['values'][str(y)] for y in past})
    row('other_current_liabilities','Other current liabilities including tax','balance','other_current_liabilities_ex_tax + current_tax_liabilities')
    row('current_liabilities','Total current liabilities','balance','short_debt + trade_payables + other_current_liabilities',subtotal=True)
    row('long_debt','Non-current financial debt, including leases','balance','total_debt - short_debt',nonnegative=True)
    if split_tax:
        row('deferred_tax_liabilities','Deferred tax liabilities','balance',lag('deferred_tax_liabilities')+' - deferred_tax_expense',nonnegative=True,
            note='Temporary net P&L deferred-tax movement allocated to liabilities with deferred tax assets held flat. No forecast OCI, FX, acquisition or jurisdictional netting changes.')
        row('other_noncurrent_liabilities_ex_tax','Other non-current liabilities excluding deferred tax','balance',lag('other_noncurrent_liabilities_ex_tax'),hist={str(y):historical['other_noncurrent_liabilities']['values'][str(y)]-historical['deferred_tax_liabilities']['values'][str(y)] for y in past})
    row('other_noncurrent_liabilities','Other non-current liabilities','balance','other_noncurrent_liabilities_ex_tax + deferred_tax_liabilities' if split_tax else lag('other_noncurrent_liabilities'))
    row('noncurrent_liabilities','Total non-current liabilities','balance','long_debt + other_noncurrent_liabilities',subtotal=True)
    row('total_liabilities','Total liabilities','balance','current_liabilities + noncurrent_liabilities',subtotal=True)
    row('share_capital','Share capital','balance',lag('share_capital'))
    row('treasury_stock','Treasury shares','balance',lag('treasury_stock')+' + buybacks')
    row('reserves','Translation and other reserves','balance',lag('reserves')+' + sbc + cash_fx',
        note='No forecast OCI other than the explicitly modelled cash FX; equity-settled share compensation increases reserves. Not a full currency translation model.')
    row('retained_earnings','Retained earnings','balance',lag('retained_earnings')+' + parent_profit + dividends_parent')
    for equity_role in ('reserves','retained_earnings'):
        cash_roles=[i['role'] for i in extra_cash_components if i.get('equity_role')==equity_role]
        if cash_roles:next(r for r in spec['rows'] if r['id']==equity_role)['expression']+=' + '+total(cash_roles)
    if cashflow_policy and cashflow_policy.get('noncommon_equity_claim_role'):
        claim=cashflow_policy['noncommon_equity_claim_role'];val(claim)
        movements=[i['role'] for i in extra_cash_components if i['classification']=='noncommon_equity_issuance']
        claim_row=row(claim,'Noncommon equity — carrying claim already included in parent equity','balance',
            lag(claim)+(' + '+total(movements) if movements else ''),nonnegative=True,
            note='Memorandum senior claim on common equity; included in the declared reserves/retained balance, never added again to total equity or debt. Carrying value is a provisional valuation proxy.')
        claim_row.update(metric_type='stock',support_matrix=True)
        spec['cashflow_presentation_contract']=copy.deepcopy(cashflow_policy)
    row('parent_equity','Equity attributable to shareholders','balance','share_capital + treasury_stock + reserves + retained_earnings',subtotal=True)
    row('nci_equity','Non-controlling interests','balance',lag('nci_equity')+' + nci_profit + dividends_nci')
    row('total_equity','Total equity','balance','parent_equity + nci_equity',subtotal=True)
    row('liabilities_equity','TOTAL LIABILITIES AND EQUITY','balance','total_liabilities + total_equity',subtotal=True)
    row('balance_check','LIVE BALANCE-SHEET CHECK','balance','total_assets - liabilities_equity',hist={},historical_expression='total_assets - liabilities_equity',subtotal=True)['check_tolerance']=1e-6
    identity('balance_sheet','Assets equal liabilities and equity','total_assets - liabilities_equity',[str(y) for y in past+future],1.5,True)
    identity('equity_parent','Parent equity component reconciliation','parent_equity - share_capital - treasury_stock - reserves - retained_earnings',[str(y) for y in past+future],2.5,True)

    section('working_capital','Working capital and tax schedules')
    if split_tax:
        assumption('deferred_tax_share','Deferred P&L tax / total P&L tax','working_capital',ratio('deferred tax share','deferred_tax_expense','tax_expense'),note='Last deferred charge specifically recorded in profit and loss, not the note total before OCI/equity reclassifications. Temporary stable P&L mix.')
        row('deferred_tax_expense','Deferred tax charged to profit and loss','working_capital','tax_expense * deferred_tax_share')
        row('current_tax_expense','Current tax charged to profit and loss','working_capital','tax_expense - deferred_tax_expense')
        identity('tax_expense_split','Current plus deferred P&L tax equals total tax','tax_expense - current_tax_expense - deferred_tax_expense',[b]+[str(y) for y in future],1e-6,True)
    assumption('inventory_ratio','Inventory / annual cost of goods sold','working_capital',val('inventories')/-val('cogs'),note='Latest closing inventory relative to annual reported COGS; cash effect linked to balance movement.')
    assumption('receivables_ratio','Receivables / annual sales','working_capital',val('receivables')/val('sales'),note='Latest reported balance divided by annual sales.')
    assumption('payables_ratio','Payables / annual cost of goods sold','working_capital',val('trade_payables')/-val('cogs'),note='Latest reported balance divided by annual COGS; includes other trade payables.')
    cash_tax_base='current_tax_expense' if split_tax else 'tax_expense'
    assumption('cash_tax_ratio','Cash tax paid / '+('current ' if split_tax else '')+'P&L tax expense','working_capital',val('paid_tax')/val(cash_tax_base),note=
        'Latest cash payments relative to '+('current ' if split_tax else 'total ')+'P&L tax expense. The same payment reduces CFO and current tax liabilities; deferred P&L tax is excluded from the cash-payment basis when disclosed.')
    row('paid_tax','Cash income taxes paid','working_capital',cash_tax_base+' * cash_tax_ratio')
    row('net_operating_working_capital','Inventory + receivables − payables','working_capital','inventories + receivables - trade_payables',hist={},historical_expression='inventories + receivables - trade_payables',subtotal=True)

    section('assets','Capital expenditure, depreciation and asset schedules')
    assumption('capex_ppe_ratio','Cash PPE capex / sales','assets',-val('capex_ppe')/val('sales'),note='Latest cash capex ratio. No future accrual/cash difference in baseline; historical difference retained in source notes.')
    assumption('capex_intangible_ratio','Intangible investment / sales','assets',-val('capex_intangibles')/val('sales'),note='Latest cash investment ratio.')
    assumption('owned_depreciation_rate','Owned PPE depreciation / opening assets','assets',val('owned_ppe_depreciation')/val('owned_ppe',base-1),note='Last disclosed depreciation on opening owned PPE; no same-year depreciation on new capex.')
    assumption('rou_depreciation_rate','ROU depreciation / opening ROU assets','assets',quotient(val('rou_depreciation'),val('right_of_use_assets',base-1),'ROU depreciation rate'),note='Last disclosed depreciation on opening ROU assets; zero only if both disclosed anchors are zero.')
    assumption('amortization_rate','Amortisation / opening intangibles','assets',quotient(val('amortization'),val('intangibles',base-1),'amortisation rate'),note='Last disclosed amortisation on opening net intangible assets; zero only if both disclosed anchors are zero.')
    assumption('lease_asset_additions','New right-of-use assets','assets',val('rou_additions'),'money','Hold latest ROU additions; equal new lease liability under temporary policy. Historical asset/liability additions differ and are not rewritten.')
    row('owned_ppe_depreciation','Depreciation — owned PPE','assets',lag('owned_ppe')+' * owned_depreciation_rate')
    row('rou_depreciation','Depreciation — right-of-use assets','assets',lag('right_of_use_assets')+' * rou_depreciation_rate')
    row('amortization','Amortisation — intangibles','assets',lag('intangibles')+' * amortization_rate')
    row('owned_ppe','Closing owned PPE','assets',lag('owned_ppe')+' - capex_ppe - owned_ppe_depreciation',nonnegative=True)
    row('right_of_use_assets','Closing right-of-use assets','assets',lag('right_of_use_assets')+' + lease_asset_additions - rou_depreciation',nonnegative=True)
    identity('ppe_roll','Owned PPE roll-forward','owned_ppe - ('+lag('owned_ppe')+' - capex_ppe - owned_ppe_depreciation)')
    identity('intangible_roll','Intangible assets roll-forward','intangibles - ('+lag('intangibles')+' - capex_intangibles - amortization)')

    section('financing','Debt, leases, interest and distributions')
    debt=val('short_debt')+val('long_debt');lease=val('lease_liabilities')
    assumption('borrowing_input','New non-lease borrowing','financing',0,'money','Zero new borrowing baseline. Explicit draws flow to debt and cash; interest begins next year.')
    assumption('repayment_input','Non-lease debt repayment','financing',0,'money','Zero net repayment baseline assumes continued funding/rollover, omitting offsetting gross refinancing flows. Not a contractual-maturity liquidity assessment; no minimum-cash debt sweep.')
    assumption('lease_principal_input','Lease principal repayment policy','financing',val('lease_asset_additions') if 'lease_asset_additions' in historical else val('rou_additions'),'money',
        'Temporary replacement-lease policy: principal payments equal new ROU additions, maintaining lease debt. Not presented as disclosed historic lease principal.')
    assumption('current_debt_share','Current share of total financial debt','financing',quotient(val('short_debt'),debt,'current debt share'),note='Hold latest current/noncurrent mix, including leases; a debt-free company starts with zero current share.')
    debt_interest=val('debt_interest_expense')-val('lease_interest_expense')
    assumption('borrowing_rate','Interest on opening non-lease debt','financing',quotient(debt_interest,debt-lease,'borrowing rate'),note='Last interest on financial debt excluding lease interest, divided by closing non-lease debt. Temporary blended funding rate; a debt-free company must set a supported rate before new financing.')
    assumption('lease_rate','Interest on opening lease liabilities','financing',quotient(val('lease_interest_expense'),lease,'lease rate'),note='Last lease interest / closing lease liability; zero only if both disclosed anchors are zero.')
    assumption('cash_yield','Yield on opening cash and short investments','financing',val('cash_interest_income')/(val('cash')+val('short_investments')),note='Cash financial interest / last cash and short investments; excludes pension income.')
    assumption('other_financial_income','Other financial income (including pensions)','financing',val('financial_income')-val('cash_interest_income'),'money',
        'Hold latest noncash/pension financial income; cash settlement is assumed equal in temporary forecast and pension balances stay fixed.')
    assumption('other_financial_cost','Other financial costs (including pensions)','financing',-val('financial_expense')-val('debt_interest_expense'),'money',
        'Hold latest non-debt financial cost; temporary cash settlement convention with fixed pension balances.')
    row('lease_liabilities','Closing lease liabilities','financing',lag('lease_liabilities')+' + lease_asset_additions + lease_principal',nonnegative=True)
    row('nonlease_debt','Closing non-lease debt','financing',lag('nonlease_debt')+' + debt_borrow + debt_repay',hist={str(y):historical['short_debt']['values'][str(y)]+historical['long_debt']['values'][str(y)]-historical['lease_liabilities']['values'][str(y)] for y in (base-1,base)},nonnegative=True)
    row('total_debt','Total financial debt including leases','financing','nonlease_debt + lease_liabilities',hist={str(y):historical['short_debt']['values'][str(y)]+historical['long_debt']['values'][str(y)] for y in past},subtotal=True)
    row('debt_interest','Interest on non-lease borrowing','financing',lag('nonlease_debt')+' * borrowing_rate',hist={b:debt_interest})
    row('lease_interest','Interest on lease liabilities','financing',lag('lease_liabilities')+' * lease_rate',role='lease_interest_expense')
    row('cash_interest','Interest on cash and short investments','financing','('+lag('cash')+' + '+lag('short_investments')+') * cash_yield',role='cash_interest_income')
    assumption('associate_earnings_yield','Associate net-income run rate / latest carrying value','financing',quotient(val('associate_profit'),val('associates'),'associate earnings yield'),note='Temporary run-rate convention: last reported NET associate income divided by last CLOSING carrying value, then applied to each forecast opening balance. This is not a measured historical opening-balance yield or clean recurring earnings. With no future disposals/impairments, forecast income is assumed to accrue to the investment carrying value.')
    normalized_dividend=val('associate_dividends')-val('exceptional_associate_distribution')
    assumption('associate_distribution_ratio','Normalised associate cash payout ratio','financing',quotient(normalized_dividend,val('associate_profit'),'associate distribution ratio'),note='Latest associate distributions excluding the separately disclosed exceptional distribution.')
    assumption('dividend_payout','Dividend payout / parent profit','financing',-val('dividends_parent')/val('parent_profit'),note='Latest paid dividends / owner profit; declared and paid in the same forecast period.')
    assumption('nci_dividend_payout','NCI dividend payout / NCI profit','financing',quotient(-val('dividends_nci'),val('nci_profit'),'NCI dividend payout'),note='Latest cash distributions / NCI profit; inactive only when both disclosed amounts are zero.')
    assumption('buyback_cash','Cash allocated to share buybacks','financing',0,'money','No new buybacks in baseline; adjustable cash use with treasury-equity and share-count links.')
    assumption('buyback_price','Inactive buyback price placeholder','financing',val('parent_equity')/val('shares_basic'),'money/shares_m',
        'Initialised to book equity per share solely as an inactive arithmetic placeholder, NOT a market quote or execution estimate. Replace before enabling a buyback scenario.')
    row('buyback_shares','Shares repurchased (millions)','financing','buyback_cash / buyback_price',unit='shares_m',hist={})
    assumption('held_for_sale_cash_input','Cash held for sale — baseline before event transfers','financing',val('held_for_sale_cash'),'money','Hold disclosed held-for-sale cash scope; no invented disposal transaction.')
    row('net_debt','Net debt before derivatives','financing','total_debt - cash - short_investments',hist={},historical_expression='total_debt - cash - short_investments',subtotal=True,
        note='Transparent debt minus cash/short investments, not the company APM including derivatives.')
    identity('debt_roll','Debt and lease liability roll-forward','total_debt - ('+lag('total_debt')+' + debt_borrow + debt_repay + lease_asset_additions + lease_principal)')
    retained_extra=[i['role'] for i in extra_cash_components if i.get('equity_role')=='retained_earnings']
    identity('retained_roll','Retained earnings roll-forward','retained_earnings - ('+lag('retained_earnings')+' + parent_profit + dividends_parent'+(' + '+total(retained_extra) if retained_extra else '')+')')
    # Derived historical rows execute visibly rather than pretending to be
    # separately reported observations. Original components remain source pulls.
    by_id={r['id']:r for r in spec['rows']}
    for key,source_key in [('corporate_utop','utop'),('corporate_da','da')]:
        ref=corp.get('source_refs',{}).get(source_key+b)
        if ref:by_id[key]['source_refs']={b:[copy.deepcopy(ref)]}
    for seg in data['segments']:
        ref=seg.get('source_refs',{}).get('da'+b)
        if ref:by_id[seg['id']+'_da']['source_refs']={b:[copy.deepcopy(ref)]}
    derived={'total_revenue':'sales + other_revenue','gross_profit':'sales + cogs',
        'corporate_cash_cost':'-corporate_utop - corporate_da','is_utop':'utop',
        'cf_associates':'-associate_profit','other_current_liabilities_ex_tax':'other_current_liabilities - current_tax_liabilities',
        'total_debt':'short_debt + long_debt','nonlease_debt':'total_debt - lease_liabilities'}
    if split_tax:
        derived.update(other_noncurrent_assets_ex_tax='other_noncurrent_assets - deferred_tax_assets',
            other_noncurrent_liabilities_ex_tax='other_noncurrent_liabilities - deferred_tax_liabilities')
    for key in segments:
        derived.update({key+'_cash_cost':f'{key}_sales - {key}_utop - {key}_da',
            key+'_ebitda':f'{key}_utop + {key}_da',key+'_margin':f'{key}_utop / {key}_sales'})
    from .construction import dependencies,expression_tree
    def historical_references(expr):
        import ast
        def linear(node,weight=1):
            if isinstance(node,ast.Expression):return linear(node.body,weight)
            if isinstance(node,ast.Name):return {node.id:weight}
            if isinstance(node,ast.UnaryOp):return linear(node.operand,-weight if isinstance(node.op,ast.USub) else weight)
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub)):
                left=linear(node.left,weight);right=linear(node.right,-weight if isinstance(node.op,ast.Sub) else weight)
                if left is None or right is None:return None
                for key,value in right.items():left[key]=left.get(key,0)+value
                return left
            return None
        tree=expression_tree(expr);weights=linear(tree);refs={};bases={}
        for dep in dict.fromkeys(dep for dep,_ in dependencies(tree)):
            for year,items in by_id[dep]['source_refs'].items():
                for item in items:
                    ref=copy.deepcopy(item)
                    ref['expression_input']=dep;ref['derivation_expression']=expr
                    if weights is not None:
                        ref['contribution_weight']=ref.get('contribution_weight',1)*weights[dep]
                    else:
                        ref['reference_use']='Input to a non-additive expression; evaluate the declared expression, not a sum of cited values'
                    refs.setdefault(year,[]).append(ref)
            basis=by_id[dep]['basis']
            if isinstance(basis,dict):bases.update(copy.deepcopy(basis))
        return refs,bases
    for key,expr in derived.items():
        r=by_id[key];r['historical_reference']=r['historical'];r['historical']={};r['historical_expression']=expr
        r['historical_expression_periods']=[p for p,v in r['historical_reference'].items() if v is not None]
        refs,bases=historical_references(expr)
        r['source_refs']=refs
        if bases:r['basis']=bases
    for key,parts in [('net_other_trading',('other_trading_income','other_trading_expense')),
                      ('net_other_operating',('other_operating_income','other_operating_expense'))]:
        if key in historical and any(part not in historical for part in parts):
            by_id[key]['note']+=' Historical directly reported net presentation retained without inventing gross components.'
            continue
        r=by_id[key];r['source_refs']={str(y):sum([copy.deepcopy(historical[p]['sources'].get(str(y),[])) for p in parts],[]) for y in past}
        r['basis']=copy.deepcopy(historical[parts[0]].get('basis',{}))
        r['note']+=' Historical calculated sum of '+ ' and '.join(parts)+'.'
    initialization_sources={
        'other_revenue_ratio':('other_revenue','sales'),'effective_tax_rate':('tax_expense','pretax'),
        'nci_profit_share':('nci_profit','total_profit'),'sbc_ratio':('sbc','sales'),
        'inventory_ratio':('inventories','cogs'),'receivables_ratio':('receivables','sales'),
        'payables_ratio':('trade_payables','cogs'),'cash_tax_ratio':('paid_tax',cash_tax_base),
        'capex_ppe_ratio':('capex_ppe','sales'),'capex_intangible_ratio':('capex_intangibles','sales'),
        'owned_depreciation_rate':('owned_ppe_depreciation','owned_ppe'),
        'rou_depreciation_rate':('rou_depreciation','right_of_use_assets'),
        'amortization_rate':('amortization','intangibles'),
        'lease_asset_additions':('rou_additions',),'lease_principal_input':('rou_additions',),
        'current_debt_share':('short_debt','long_debt'),
        'borrowing_rate':('debt_interest_expense','lease_interest_expense','short_debt','long_debt','lease_liabilities'),
        'lease_rate':('lease_interest_expense','lease_liabilities'),
        'cash_yield':('cash_interest_income','cash','short_investments'),
        'other_financial_income':('financial_income','cash_interest_income'),
        'other_financial_cost':('financial_expense','debt_interest_expense'),
        'associate_earnings_yield':('associate_profit','associates'),
        'associate_distribution_ratio':('associate_dividends','exceptional_associate_distribution','associate_profit'),
        'dividend_payout':('dividends_parent','parent_profit'),'nci_dividend_payout':('dividends_nci','nci_profit'),
        'buyback_price':('parent_equity','shares_basic'),'held_for_sale_cash_input':('held_for_sale_cash',)}
    if split_tax:initialization_sources['deferred_tax_share']=('deferred_tax_expense','tax_expense')
    initialization_expressions={
        'other_revenue_ratio':'other_revenue / sales',
        'effective_tax_rate':'-tax_expense / pretax',
        'nci_profit_share':'nci_profit / total_profit','sbc_ratio':'sbc / sales',
        'inventory_ratio':'inventories / -cogs','receivables_ratio':'receivables / sales',
        'payables_ratio':'trade_payables / -cogs','cash_tax_ratio':'paid_tax / '+cash_tax_base,
        'capex_ppe_ratio':'-capex_ppe / sales','capex_intangible_ratio':'-capex_intangibles / sales',
        'owned_depreciation_rate':'owned_ppe_depreciation / lag("owned_ppe", 1)',
        'rou_depreciation_rate':'rou_depreciation / lag("right_of_use_assets", 1)',
        'amortization_rate':'amortization / lag("intangibles", 1)',
        'current_debt_share':'short_debt / (short_debt + long_debt)',
        'borrowing_rate':'(debt_interest_expense - lease_interest_expense) / (short_debt + long_debt - lease_liabilities)',
        'lease_rate':'lease_interest_expense / lease_liabilities',
        'cash_yield':'cash_interest_income / (cash + short_investments)',
        'other_financial_income':'financial_income - cash_interest_income',
        'other_financial_cost':'-financial_expense - debt_interest_expense',
        'associate_earnings_yield':'associate_profit / associates',
        'associate_distribution_ratio':'(associate_dividends - exceptional_associate_distribution) / associate_profit',
        'dividend_payout':'-dividends_parent / parent_profit',
        'nci_dividend_payout':'-dividends_nci / nci_profit',
        'buyback_price':'parent_equity / shares_basic',
        'deferred_tax_share':'deferred_tax_expense / tax_expense'}
    for key in (item['id'] for item in functions):
        initialization_sources[key+'_allocation']=(key,'total_revenue','utop')
        initialization_expressions[key+'_allocation']=f'-{key} / (total_revenue - utop)'
    for key,parts in initialization_sources.items():
        if key not in by_id:continue
        refs=[]
        for part in parts:
            source_year=str(base-1) if key in ('owned_depreciation_rate','rou_depreciation_rate','amortization_rate') and part==parts[-1] else b
            refs.extend(copy.deepcopy(historical[part].get('sources',{}).get(source_year,[])))
        by_id[key]['source_refs']={b:refs}
        by_id[key]['initialization_components']=list(parts)
        expression=initialization_expressions.get(key)
        if expression:
            by_id[key]['initialization_expression']=expression
            by_id[key]['initialization_period']=b
            by_id[key]['note']+=f' Initialization at {base}: {expression}; lag denotes the previous annual balance. Disclosed inactive 0/0 ratios initialize to zero.'
    for seg in data['segments']:
        by_id[seg['id']+'_cost_inflation']['source_refs']=copy.deepcopy(by_id[seg['id']+'_pricing']['source_refs'])
    by_id['corporate_da_share']['source_refs']={b:copy.deepcopy(by_id['corporate_da']['source_refs'].get(b,[])+historical['da'].get('sources',{}).get(b,[]))}
    for r in spec['rows']:
        if r['kind']=='assumption':
            for refs in r['source_refs'].values():
                for ref in refs:ref['reference_use']='Observed initialization ingredient; apply the stated initialization rule, not an additive sum of citations'
        if r.get('historical_expression') and not any(r['source_refs'].values()):
            r['source_refs'],bases=historical_references(r['historical_expression'])
            if bases:r['basis']=bases
    spec['gaps']=[
        'Temporary baseline, not a calibrated forecast. No probabilities, DCF or trading logic.',
        'Prior years in current-basis segment blocks are non-comparable; original segment versions remain in Historical Segments.',
        'Cost inflation is a temporary proxy, with no invented commodity elasticity, purchasing exposure or pass-through coefficient.',
        'Opening asset/debt convention delays capex depreciation and new borrowing interest to the next year.',
        'No future acquisition/disposal, restructuring, impairment or balance-sheet FX in the baseline; these require explicit economic counterparts before activation.',
        'Historical cash capex and accrual additions differ; future baseline explicitly assumes equality.',
        'Lease principal is not separately recoverable from the inspected historic aggregate; forecast uses an explicit replacement-lease policy.',
        'Historical original-year statements can differ from subsequent restatements; no synthetic decade on current segment geography.',
        'Forecast checks balance by construction; independent historical source checks are reported separately.'
    ]
    # Historical publication precision must never loosen forecast arithmetic gates.
    expanded=[]
    for item in spec['identities']:
        hp=[p for p in item['periods'] if int(p) in past]
        fp=[p for p in item['periods'] if int(p) in future]
        if hp:expanded.append(dict(item,id=item['id']+'_history',periods=hp))
        if fp:expanded.append(dict(item,periods=fp,tolerance=1e-6,independent=False))
    spec['identities']=expanded
    money=data['currency']+'m'
    for r in spec['rows']:
        r['unit']=r['unit'].replace('money',money)
        if r['unit']==money+'/shares_m':r['display_unit']=data['currency']+'/share'
    for item in data.get('model_configuration',{}).get('historical_allocations',[]):
        r=by_id[item['row_id']];year=str(item['year'])
        r.setdefault('estimated_historical',{})[year]=copy.deepcopy(item)
        r['source_refs'][year]=[]
        r['calibration_eligible']=False
    return spec


def financial_cost_pools(data):
    """Return a small, non-overlapping expense taxonomy from company inputs.

    The fallback is the existing reported financial-role taxonomy, not a product,
    geography or currency mapping. Baseline allocation is explicitly an estimate.
    """
    configured=data.get('financial_contracts',data.get('model_configuration',{}).get('financial_contracts',{})).get('cost_pools')
    if configured:
        pools=copy.deepcopy(configured)
    else:
        pools=[dict(id=role,label=label,destination=role,baseline_role=role,
                    activity_driver='rig' if role in ('cogs','distribution') else 'independent',
                    elasticity=1.0 if role in ('cogs','distribution') else 0.0,
                    unit_cost_change=0.0,spending_change=0.0,
                    behaviour='activity_proxy' if role in ('cogs','distribution') else 'spending_budget',
                    status='provisional',source_refs=[],
                    limitations=['RIG includes mix. The temporary activity elasticity is an explicit scenario, not measured physical volume.']
                        if role in ('cogs','distribution') else ['Independent nominal spending budget; no sales-ratio forecast.'])
               for role,label in ((item['id'],{'cogs':'Production and procurement','distribution':'Distribution',
                    'marketing_admin':'Marketing and administration','research':'Research and development'}.get(item['id'],item['label']))
                    for item in operating_expense_functions(data))]
    ids=[p['id'] for p in pools]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate financial cost pool')
    allowed={item['id'] for item in operating_expense_functions(data)}
    if any(p.get('destination') not in allowed for p in pools):
        raise ValueError('Cost pool must name a supported, non-overlapping statement expense destination')
    absent=data.get('model_configuration',{}).get('functional_expense_structure',{})
    for role in allowed-{p['destination'] for p in pools}:
        if absent.get(role,{}).get('treatment')=='included_in_other_functions':
            pools.append(dict(id=role,label=role.replace('_',' ').capitalize()+' (included in other functions)',destination=role,baseline_role=role,
                baseline_amount=0,activity_driver='independent',method='budget_delta',source_refs=copy.deepcopy(absent[role].get('source_refs',[])),structural_empty=True))
    if {p['destination'] for p in pools}!=allowed:
        raise ValueError('Cost pools must cover every reported functional expense destination')
    if len({p['id'] for p in pools})!=len(pools):raise ValueError('Structural expense bucket conflicts with a configured pool ID')
    for pool in pools:
        method=pool.setdefault('method','activity_cost' if pool.get('activity_driver')=='rig' else 'budget_delta')
        if method not in ('activity_cost','budget_delta','budget_growth','absolute_budget'):
            raise ValueError('Unsupported cost method '+str(method))
        pool.setdefault('effective_activity_sensitivity',pool.get('elasticity',0)*pool.get('variable_share',1))
        pool.setdefault('input_cost_includes_transaction_fx',False)
        if method!='activity_cost' and pool.get('unit_cost_change',0):
            raise ValueError('Budget costs cannot also apply unit-cost inflation')
        if method!='budget_growth' and pool.get('spending_change',0):
            raise ValueError('Spending growth requires the budget_growth method')
        if method!='budget_delta' and pool.get('budget_change',0):
            raise ValueError('An incremental budget cannot overlap the selected cost method')
    return pools


def scope_period_inclusion(event,start,end,year_days=365):
    """Annual contribution included after the control date, with explicit seasonality."""
    from datetime import date, timedelta
    import calendar
    first=max(date.fromisoformat(start),date.fromisoformat(event['effective_date']));last=date.fromisoformat(end)
    if first>last:return 0.0
    weights=event.get('calendar_month_weights')
    if weights:
        if len(weights)!=12 or any(v<0 for v in weights) or abs(sum(weights)-1)>1e-8:raise ValueError('Event monthly seasonality requires twelve nonnegative weights summing to one')
        total=0.0;day=first
        while day<=last:
            total+=weights[day.month-1]/calendar.monthrange(day.year,day.month)[1];day+=timedelta(days=1)
        return total
    return (last-first).days/year_days+1/year_days


def estimate_scope_events(events):
    """Compile cited operating and closing estimates into common event mechanics.

    Inputs are company research, not inferred balancing amounts. Disposal gain and
    acquisition goodwill are the accounting consequences of independently supplied
    consideration and asset estimates. Every estimation ingredient remains saved.
    """
    result=copy.deepcopy(events)
    for event in result:
        estimate=event.get('estimation')
        if not estimate:continue
        if not event.get('source_refs') or not estimate.get('method'):raise ValueError('Event estimates require cited evidence and a method')
        direction=1 if event.get('type')=='acquisition' else -1
        revenue=estimate.get('annual_revenue')
        if revenue is None and estimate.get('revenue_anchor') is not None:revenue=estimate['revenue_anchor']*estimate['revenue_share']
        profit=estimate.get('annual_operating_profit')
        if profit is None and revenue is not None and estimate.get('operating_margin') is not None:profit=revenue*estimate['operating_margin']
        da=estimate.get('annual_da')
        if da is None and revenue is not None and estimate.get('da_intensity') is not None:da=revenue*estimate['da_intensity']
        if revenue is not None:event['annual_revenue']=direction*revenue
        if da is not None:event['annual_da']=direction*da
        if None not in (revenue,profit,da) and estimate.get('cost_weights'):
            weights=estimate['cost_weights']
            if abs(sum(weights.values())-1)>1e-8:raise ValueError('Event cost allocation weights must sum to one')
            event['annual_cash_costs']={k:direction*(revenue-profit-da)*w for k,w in weights.items()}
        closing=estimate.get('closing')
        if not closing:continue
        assets=closing.get('assets',{});liabilities=closing.get('liabilities',{})
        if set(assets)&set(liabilities):raise ValueError('Event asset and liability roles overlap')
        cash=closing.get('cash_transferred',0);consideration=closing.get('consideration',0)
        net_assets=sum(assets.values())+(0 if closing.get('cash_transferred_in_asset_roles') else cash)-sum(liabilities.values())
        expected=closing.get('net_assets_check')
        if expected is not None and abs(expected-net_assets)>closing.get('rounding_tolerance',1e-6):raise ValueError('Estimated closing accounts disagree with cited net asset total')
        event['balance_movements']={k:direction*v for k,v in {**assets,**liabilities}.items()}
        if direction<0:
            retained=closing.get('retained_investment',0);recycling=closing.get('cta_recycling',0)
            event['cash_flows']={'business_disposals_cf':consideration-cash}
            event['gain_loss']=consideration+retained-net_assets-recycling
            event['oci_reclassification']=recycling
            if retained:event['balance_movements']['associates']=event['balance_movements'].get('associates',0)+retained
        else:
            prior_value=closing.get('previous_interest_fair_value',0);prior_book=closing.get('previous_interest_carrying_value',0)
            event['cash_flows']={'business_acquisitions_cf':cash-consideration}
            event['gain_loss']=prior_value-prior_book
            event['balance_movements']['associates']=event['balance_movements'].get('associates',0)-prior_book
            event['balance_movements']['goodwill']=event['balance_movements'].get('goodwill',0)+consideration+prior_value-net_assets
        event['accounting_enabled']=True
        event['estimated_closing_net_assets']=net_assets
        event['accounting_status']='estimated_closing_accounts_not_reported'
        event['tax_rate']=closing.get('gain_tax_rate',0)
        event['nci_share']=closing.get('gain_nci_share',0)
        event['held_for_sale_cash_removed']=closing.get('held_for_sale_cash',0)
        event['estimation_outputs']=dict(annual_revenue=revenue,annual_operating_profit=profit,annual_da=da,
            net_assets=net_assets,gain_loss=event['gain_loss'],method=estimate['method'],classification='estimated_baseline')
    return result


def apply_financial_contracts(spec, data):
    """Install causal forecast contracts without editing historical observations.

    Functional cash expense pools are authoritative. Their source-based starting
    allocations are estimates; pricing never changes their independent budgets.
    This runs after the FX adapter and uses stable period/date bindings, including
    direct annual forecasts after the detailed horizon.
    """
    if not spec.get('periods'):return spec
    from datetime import date, timedelta
    from .construction import dependencies, expression_tree
    data=functional_structure_inputs(historical_eligibility_inputs(data))
    cfg=copy.deepcopy(data.get('financial_contracts',data.get('model_configuration',{}).get('financial_contracts',{})))
    rows={r['id']:r for r in spec['rows']};periods=spec['periods'];pm={p['id']:p for p in periods}
    py={(p['fiscal_year'],p['kind']):p['id'] for p in periods}
    base=max(data['history_years']);base_pid=py[base,'FY'];money=data['currency']+'m'
    history={**data['historical'],**data.get('schedule_controls',{})}
    forecast_years=set(spec['forecast_years'])
    frequency=spec.get('frequency_policy',{}).get('statements') or spec.get('model_configuration',{}).get('statement_forecast_frequency',
        'half_year' if spec.get('model_configuration',{}).get('full_statement_frequency')=='half_year' else
        spec.get('model_configuration',{}).get('forecast_frequency','quarterly'))
    regular=('H1','H2') if frequency=='half_year' else ('Q1','Q2','Q3','Q4')
    def actual(cell):return cell.get('status') in ('actual','reported','derived_actual')
    def present(rid,pid):
        c=rows.get(rid,{}).get('cells',{}).get(pid,{})
        return c.get('value') is not None or bool(c.get('expression'))
    def forecast(rid,pid):return present(rid,pid) and not actual(rows[rid]['cells'][pid])
    def leaves(year):
        kinds=regular if any((year,k) in py for k in regular) else ('FY',)
        return [pm[py[year,k]] for k in kinds if (year,k) in py]
    financial=[p for y in sorted(forecast_years) for p in leaves(y) if forecast('utop',p['id'])]
    def planned_pool_period(pid):
        """A declared forecast aggregate can be bound before its cells exist."""
        if pid not in pm:return False
        p=pm[pid]
        return any(q['fiscal_year']==p['fiscal_year'] and q['start']>=p['start'] and q['end']<=p['end'] for q in financial)
    def frac(p):return p['duration_days']/pm[py[p['fiscal_year'],'FY']]['duration_days']
    def hv(role, default=None):return history.get(role,{}).get('values',{}).get(str(base),default)
    def missing():return dict(value=None,status='not_applicable',editable=False)
    def make(rid,label,section='working_capital',unit=None,kind='calculated',metric_type='flow',note='',support=False):
        if rid in rows:return rows[rid]
        r=dict(id=rid,label=label,section=section,unit=unit or money,kind=kind,metric_type=metric_type,
               note=note,basis=data['forecast_basis'],historical={},source_refs={},cells={p['id']:missing() for p in periods})
        if support:r['assumption_support']=True;r['support_matrix']=True
        rows[rid]=r;spec['rows'].append(r);return r
    def f(rid,pid,expr,bindings=None,reason='',status='forecast',editable=False,required=True):
        rows[rid]['cells'][pid]=dict(expression=expr,bindings=bindings or {},status=status,reason=reason,
                                      editable=editable,required=required)
    def a(rid,p,value,note='',required=True):
        rows[rid]['cells'][p['id']]=dict(value=value,status='forecast',editable=True,required=required,reason=note)
    def summed(rid,pid,targets,reason='Sum of disjoint financial amounts'):
        if not targets:return
        f(rid,pid,' + '.join('x'+str(i) for i in range(len(targets))),
          {'x'+str(i):dict(row_id=r,period_id=q) for i,(r,q) in enumerate(targets)},reason)
    def aggregate(rid,year,metric='flow'):
        for p in periods:
            if p['fiscal_year']!=year or actual(rows[rid]['cells'].get(p['id'],{})):continue
            members=[q for q in leaves(year) if q['id']!=p['id'] and q['start']>=p['start'] and q['end']<=p['end']]
            if len(members)>1 and members[0]['start']==p['start'] and members[-1]['end']==p['end']:
                if metric=='flow':summed(rid,p['id'],[(rid,q['id']) for q in members])
                else:
                    expr='('+' + '.join(f'x{i} * w{i}' for i,q in enumerate(members))+') / whole'
                    bindings={f'x{i}':dict(row_id=rid,period_id=q['id']) for i,q in enumerate(members)}
                    bindings.update({f'w{i}':dict(row_id='period_year_fraction',period_id=q['id']) for i,q in enumerate(members)})
                    bindings['whole']=dict(row_id='period_year_fraction',period_id=p['id'])
                    f(rid,p['id'],expr,bindings)
    contracts=[]
    def contract(rid,entity,pool,role,outputs,currency='reporting_currency',timing='period',definition=None):
        c=dict(id=rid,definition=definition or rows[rid]['label'],units=rows[rid]['unit'],
               financial_basis=data['forecast_basis'],frequency=frequency,forecast_horizon=sorted(forecast_years),
               entity_id=entity,cost_pool=pool,currency_basis=currency,timing=timing,
               parameter_role=role,expected_downstream_outputs=outputs)
        rows[rid]['driver_contract']=copy.deepcopy(c)
        existing=next((i for i,item in enumerate(contracts) if item['id']==rid),None)
        if existing is None:contracts.append(c)
        else:contracts[existing]=c
    def cost_expression(rid,pool,base,scope_factor='1'):
        cash_base='('+base+' - '+rid+'_sbc_seed * '+scope_factor+')'
        method=pool['method']
        if method=='activity_cost':return cash_base+f' * (1 + {rid}_activity_change * {rid}_effective_activity_sensitivity) * (1 + {rid}_unit_cost_change)'
        if method=='budget_growth':return cash_base+f' * (1 + {rid}_spending_change)'
        if method=='absolute_budget':return rid+'_budget_amount * '+scope_factor
        return cash_base+' + '+rid+'_budget_change * '+scope_factor
    # These rows contain incremental forecast reversals, not replacements for
    # already reported historical noncash components. Historical zero therefore
    # means no additional modelled adjustment and is not calibration evidence.
    for rid in ('cfo_portfolio_noncash','cfo_fx_noncash'):
        for p in periods:
            if actual(rows['cfo']['cells'].get(p['id'],{})):
                rows[rid]['cells'][p['id']]=dict(value=0,status='derived_actual',data_role='structural_absence',
                    calibration_eligible=False,editable=False,required=False,reason='No incremental forecast adjustment to reported historical CFO.')
        for p in financial:f(rid,p['id'],'0 * sales')
    pools=financial_cost_pools(data)
    source_tolerance=cfg.get('source_rounding_tolerance',1e-6)
    if not isinstance(source_tolerance,(int,float)) or isinstance(source_tolerance,bool) or not math.isfinite(source_tolerance) or source_tolerance<0:
        raise ValueError('Source rounding tolerance must be finite and nonnegative')
    destinations=[item['id'] for item in operating_expense_functions(data)]
    total_expenses=sum(-hv(role) for role in destinations)
    total_da=hv('da');cash_total=total_expenses-total_da
    if cash_total<=0:raise ValueError('Positive sourced cash operating expense base is required')
    # Pool amounts and D&A shares must reconcile to each reported expense exactly.
    by_dest={d:[p for p in pools if p['destination']==d] for d in destinations}
    for destination,items in by_dest.items():
        reported=-hv(destination)
        for pool in items:
            if pool.get('baseline_amount') is None and pool.get('baseline_share') is not None:
                pool['baseline_amount']=reported*pool['baseline_share']
        specified=sum(float(p.get('baseline_amount',0)) for p in items)
        unspecified=[p for p in items if p.get('baseline_amount') is None]
        if len(unspecified)>1:raise ValueError('Split expense pools need explicit non-overlapping baseline amounts: '+destination)
        if unspecified:unspecified[0]['baseline_amount']=reported-specified
        if not math.isclose(sum(p['baseline_amount'] for p in items),reported,abs_tol=1e-6):
            raise ValueError('Cost-pool baselines do not reconcile to reported '+destination)
        for pool in items:
            if pool['baseline_amount']<0:raise ValueError('Negative cost-pool baseline')
            pool['da_share']=pool.get('da_share',pool['baseline_amount']/total_expenses)
            pool['cash_baseline']=pool['baseline_amount']-total_da*pool['da_share']
            if pool['cash_baseline']<0:raise ValueError('D&A allocation exceeds cost-pool baseline')
    if not math.isclose(sum(p['da_share'] for p in pools),1,abs_tol=1e-9):raise ValueError('Functional D&A allocations must sum to one')
    entities=[(s['id'],s['label'],s[f'sales{base}']-s[f'utop{base}']-s[f'da{base}']) for s in data['segments']]
    corporate_base=-data['corporate'][f'utop{base}']-data['corporate'][f'da{base}']+hv('other_revenue',0)
    entities.append(('corporate','Corporate',corporate_base))
    if not math.isclose(sum(x[2] for x in entities),cash_total,abs_tol=source_tolerance,rel_tol=0):
        raise ValueError('Functional expense base and segment cash costs do not reconcile')
    # Tiny source publication rounding is explicit in the baseline allocation.
    entity_denominator=sum(x[2] for x in entities)
    corporate_weights=cfg.get('corporate_cost_weights')
    if corporate_weights is None:
        preferred=next((p for p in pools if p['id']=='administration'),next(p for p in pools if p['destination']=='marketing_admin'))
        corporate_weights={preferred['id']:1.0}
    if set(corporate_weights)-{p['id'] for p in pools} or not math.isclose(sum(corporate_weights.values()),1,abs_tol=1e-9):
        raise ValueError('Corporate cost weights must name configured pools and sum to one')
    baseline_matrix={}
    for pool in pools:
        corp=corporate_base*corporate_weights.get(pool['id'],0)
        remainder=pool['cash_baseline']-corp
        if remainder < -1e-6:raise ValueError('Corporate allocation exceeds the available '+pool['id']+' expense; provide supported corporate_cost_weights')
        for entity,_,entity_base in entities:
            amount=corp if entity=='corporate' else remainder*entity_base/(entity_denominator-corporate_base)
            baseline_matrix[entity,pool['id']]=pool.get('baseline_amounts',{}).get(entity,amount)
    for entity,_,entity_base in entities:
        if not math.isclose(sum(baseline_matrix[entity,p['id']] for p in pools),entity_base,abs_tol=source_tolerance,rel_tol=0):raise ValueError('Entity cost allocation does not reconcile: '+entity)
    for pool in pools:
        if not math.isclose(sum(baseline_matrix[e,pool['id']] for e,_,_ in entities),pool['cash_baseline'],abs_tol=source_tolerance,rel_tol=0):raise ValueError('Functional cost allocation does not reconcile: '+pool['id'])
    sbc_cfg=cfg.get('sbc',{});sbc_base=hv('sbc',0)
    sbc_weights={(x['entity_id'],x['pool_id']):x['weight'] for x in sbc_cfg.get('allocations',[])}
    if not sbc_weights:
        candidates={k:v for k,v in baseline_matrix.items() if next(p['destination'] for p in pools if p['id']==k[1])=='marketing_admin'}
        total=sum(candidates.values())
        sbc_weights={k:v/total for k,v in candidates.items()} if total else {}
    if sbc_base and (not math.isclose(sum(sbc_weights.values()),1,abs_tol=1e-9) or set(sbc_weights)-set(baseline_matrix)):
        raise ValueError('SBC allocation must identify cost pools and reconcile to one')
    for key,weight in sbc_weights.items():
        if weight<0 or sbc_base*weight>baseline_matrix[key]+1e-8:raise ValueError('Embedded SBC allocation exceeds its operating expense baseline')
    make('sbc_annual_budget','Annual equity-settled compensation expense budget','financing',kind='assumption',metric_type='stock',
         note='Reporting-currency expense already embedded in operating costs; separately identified once for expense, noncash addback and equity.')
    for year in forecast_years:a('sbc_annual_budget',pm[py[year,'FY']],sbc_cfg.get('annual_amount',sbc_base),'Previous full-year expense held nominally constant unless an explicit budget is supplied.')
    pool_rows={};new_flows=[]
    for pool in pools:
        for suffix,value,label in [('cash_share',pool['cash_baseline']/cash_total,'Historical cash-expense allocation'),
                                    ('da_share',pool['da_share'],'Functional D&A allocation')]:
            rid='pool_'+pool['id']+'_'+suffix
            make(rid,pool['label']+' — '+label,'working_capital','ratio','assumption','ratio',
                 note='Baseline allocation only; source-reconciled estimate, not an independent economic driver.',support=True)
            rows[rid]['cells'][base_pid]=dict(value=value,status='estimated',editable=False,required=False)
            for p in financial:f(rid,p['id'],'anchor',{'anchor':dict(row_id=rid,period_id=base_pid)},editable=False)
    for entity,label,entity_base in entities:
        section='corporate' if entity=='corporate' else 'segment_'+entity
        revenue_model=spec.get('revenue_models',spec.get('model_configuration',{}).get('revenue_models',{})).get(entity,{})
        revenue_mode=revenue_model.get('method',revenue_model.get('mode')) if isinstance(revenue_model,dict) else revenue_model
        targets=[]
        for pool in pools:
            rid=entity+'_pool_'+pool['id'];targets.append(rid);pool_rows[entity,pool['id']]=rid
            baseline=baseline_matrix[entity,pool['id']]
            note='Estimated baseline allocation of reported functional cash expense; not a reported segment-by-function expense. '+str(pool.get('behaviour','independent cost pool'))
            make(rid,label+' — '+pool['label']+' expense before D&A',section,note=note+' Includes separately identified equity-settled compensation, removed from the cash-cost driver base.')['nonnegative']=True
            make(rid+'_seed','Comparable cash expense base',section,kind='calculated',note=note,support=True)
            make(rid+'_activity_base','Operating expense base excluding disposed scope',section,note=note,support=True)
            make(rid+'_pre_fx','Expense before transaction/translation FX',section,note=note,support=True)
            make(rid+'_transaction_amount','Transaction FX expense effect',section,note='Functional-currency margin effect, applied once.',support=True)
            make(rid+'_translation_amount','Translation FX expense effect',section,note='Consolidation effect after transaction FX, applied once.',support=True)
            new_flows.extend((rid,rid+'_pre_fx',rid+'_transaction_amount',rid+'_translation_amount'))
            rows[rid]['cells'][base_pid]=dict(value=baseline,status='estimated',editable=False,required=False,
                reason=note,data_role='estimated_historical_baseline',calibration_eligible=False,
                source_refs=copy.deepcopy(pool.get('source_refs') or history[pool.get('baseline_role',pool['destination'])].get('sources',{}).get(str(base),[])))
            rows[rid].update(historical_allocation=True,calibration_eligible=False,allocation_method='Corporate-specific allocation, then remaining functional expenses proportional to segment expense bases; estimated, not reported segment functions.')
            weight=sbc_weights.get((entity,pool['id']),0)
            make(rid+'_sbc_expense','Embedded equity-settled compensation expense',section,support=True)
            make(rid+'_sbc_seed','Comparable embedded compensation to remove from cash base',section,support=True)
            rows[rid+'_sbc_expense']['cells'][base_pid]=dict(value=sbc_base*weight,status='estimated',editable=False,required=False,data_role='estimated_historical_baseline',calibration_eligible=False)
            controls=[('activity_change','Activity proxy change',0,'ratio'),
                      ('effective_activity_sensitivity','Effective activity sensitivity',pool['effective_activity_sensitivity'],'ratio'),
                      ('elasticity','Legacy activity elasticity diagnostic',pool['effective_activity_sensitivity'],'ratio'),('variable_share','Legacy combined-sensitivity identity',1,'ratio'),
                      ('unit_cost_change','Unit input-cost change',pool.get('unit_cost_change',0),'ratio'),
                      ('spending_change','Independent spending change',pool.get('spending_change',0),'ratio'),
                      ('budget_change','Incremental cash spending budget',pool.get('budget_change',0),money),
                      ('budget_amount','Absolute cash spending budget',pool.get('budget_amount',baseline-sbc_base*weight),money)]
            active_controls={'activity_cost':{'effective_activity_sensitivity','unit_cost_change'},'budget_delta':{'budget_change'},
                             'budget_growth':{'spending_change'},'absolute_budget':{'budget_amount'}}[pool['method']]
            linked_activity=pool.get('activity_driver')=='rig' and entity!='corporate' and revenue_mode!='aggregate_organic'
            if pool['method']=='activity_cost' and not linked_activity:active_controls=active_controls|{'activity_change'}
            if baseline==0:active_controls=set()
            for suffix,title,value,unit in controls:
                active=suffix in active_controls
                cr=make(rid+'_'+suffix,pool['label']+' — '+title,section,unit,'assumption' if active else 'calculated','ratio' if unit=='ratio' else 'flow',
                        note='Selected '+pool['method']+' method; no overlapping growth/budget controls. Input-cost inflation '+('includes' if pool['input_cost_includes_transaction_fx'] else 'excludes')+' transaction FX.',support=not active or suffix=='effective_activity_sensitivity')
                if active:contract(cr['id'],entity,pool['id'],'structural_parameter' if suffix=='effective_activity_sensitivity' else 'forecast_assumption',[rid,entity+'_utop','utop','operating_profit','cfo'])
            for side in ('translation_fx','transaction_fx'):
                if rid+'_'+side not in rows:
                    make(rid+'_'+side,pool['label']+' — '+side.replace('_',' '),section,'ratio','assumption','ratio',
                        note='Explicit zero scenario: cost-pool currency exposure is unresolved, not inferred from revenue.',support=True)
                    for p in financial:a(rid+'_'+side,p,0,'Unmodelled exposure; zero scenario, not evidence of no exposure.')
            if pool['input_cost_includes_transaction_fx']:
                transaction=rows[rid+'_transaction_fx'];transaction['kind']='calculated'
                transaction['note']='Transaction FX is already included in the unit-cost forecast; a separate transaction effect is disabled.'
                for p in financial:transaction['cells'][p['id']]=dict(value=0,status='forecast',editable=False,required=False,reason=transaction['note'])
            # Source-linked interim baseline allocations stay estimates and never
            # manufacture unsupported quarterly statements or alter source rows.
            for p in periods:
                if p['id']==base_pid or p['kind'] not in (*regular,'FY') or p['fiscal_year']<base:continue
                cash_row=entity+'_cash_cost'
                if present(cash_row,p['id']) and actual(rows[cash_row]['cells'][p['id']]):
                    ratio=rid+'_baseline_weight';make(ratio,'Estimated entity functional-cost allocation','working_capital','ratio',metric_type='ratio',support=True)
                    rows[ratio]['cells'][base_pid]=dict(value=baseline/entity_base if entity_base else 0,status='estimated',editable=False,required=False,calibration_eligible=False)
                    if entity=='corporate':
                        f(rid,p['id'],'(base + other) * weight',{'base':dict(row_id=cash_row,period_id=p['id']),
                           'other':dict(row_id='other_revenue',period_id=p['id']),'weight':dict(row_id=ratio,period_id=base_pid)},note,status='estimated',required=False)
                    else:f(rid,p['id'],'base * weight',{'base':dict(row_id=cash_row,period_id=p['id']),
                        'weight':dict(row_id=ratio,period_id=base_pid)},note,status='estimated',required=False)
                    rows[rid]['cells'][p['id']].update(data_role='estimated_historical_baseline',calibration_eligible=False)
                    if present('sbc',p['id']):
                        rows[rid+'_sbc_expense']['cells'][p['id']]=dict(value=None,status='estimated',editable=False,required=False)
                        # An allocation is an estimate even when its source total is reported.
                        sbc_weight=rid+'_sbc_weight';make(sbc_weight,'Estimated embedded compensation weight',section,'ratio',metric_type='ratio',support=True)
                        rows[sbc_weight]['cells'][base_pid]=dict(value=weight,status='estimated',editable=False,required=False)
                        f(rid+'_sbc_expense',p['id'],'sbc * allocation',{'allocation':dict(row_id=sbc_weight,period_id=base_pid)},status='estimated',required=False)
            for p in financial:
                pid=p['id'];prior=py.get((p['fiscal_year']-1,p['kind']))
                if prior and (present(rid,prior) or planned_pool_period(prior)):
                    f(rid+'_seed',pid,'prior',{'prior':dict(row_id=rid,period_id=prior)},'Comparable prior-year functional cash expense, including the previously modelled FY at an annual-frequency transition')
                else:
                    priorfy=py.get((p['fiscal_year']-1,'FY'),base_pid)
                    if not present(rid,priorfy) and not planned_pool_period(priorfy):priorfy=base_pid
                    f(rid+'_seed',pid,'base * period_year_fraction',{'base':dict(row_id=rid,period_id=priorfy)},'Explicit fiscal-duration allocation of annual functional expense')
                seed=rows[rid+'_seed']['cells'][pid];source=seed['bindings'].get('prior',seed['bindings'].get('base'))
                f(rid+'_sbc_seed',pid,'anchor'+(' * period_year_fraction' if 'base' in seed['bindings'] else ''),{'anchor':dict(row_id=rid+'_sbc_expense',period_id=source['period_id'])})
                sbc_weight=rid+'_sbc_weight';make(sbc_weight,'Estimated embedded compensation weight',section,'ratio',metric_type='ratio',support=True)
                rows[sbc_weight]['cells'][base_pid]=dict(value=weight,status='estimated',editable=False,required=False)
                f(rid+'_sbc_expense',pid,'budget * period_year_fraction * allocation * '+entity+'_scope_active_fraction',{
                    'budget':dict(row_id='sbc_annual_budget',period_id=py[p['fiscal_year'],'FY']),
                    'allocation':dict(row_id=sbc_weight,period_id=base_pid)})
                for suffix,title,value,unit in controls:
                    if suffix in active_controls:a(rid+'_'+suffix,p,value*frac(p) if unit==money else value)
                    else:rows[rid+'_'+suffix]['cells'][pid]=dict(value=value*frac(p) if unit==money else value,status='forecast',editable=False,required=False)
                if pool['method']=='activity_cost' and linked_activity:
                    f(rid+'_activity_change',pid,entity+'_rig',reason='Derived RIG activity/mix proxy; use an independent activity source only through explicit method configuration.')
                f(rid+'_pre_fx',pid,cost_expression(rid,pool,rid+'_seed'))
                f(rid+'_activity_base',pid,rid+'_seed')
                f(rid+'_transaction_amount',pid,f'{rid}_pre_fx * '+('0' if pool['input_cost_includes_transaction_fx'] else rid+'_transaction_fx'))
                f(rid+'_translation_amount',pid,f'({rid}_pre_fx + {rid}_transaction_amount) * {rid}_translation_fx')
                f(rid,pid,f'{rid}_pre_fx + {rid}_transaction_amount + {rid}_translation_amount + {rid}_sbc_expense')
            for year in forecast_years:
                for out in (rid,rid+'_pre_fx',rid+'_transaction_amount',rid+'_translation_amount',rid+'_sbc_expense'):aggregate(out,year)
        target=entity+'_cash_cost'
        if entity=='corporate':
            target='corporate_gross_cash_cost';make(target,'Corporate cash expense before other revenue','corporate')
            for p in periods:
                if actual(rows['corporate_cash_cost']['cells'].get(p['id'],{})) and present('other_revenue',p['id']):
                    f(target,p['id'],'corporate_cash_cost + other_revenue',status='derived_actual',
                      reason='Source-linked gross corporate expense equals reported net corporate expense plus separately reported other revenue.')
        for p in financial:summed(target,p['id'],[(rid,p['id']) for rid in targets])
        for year in forecast_years:aggregate(target,year)
        if entity=='corporate':
            for p in financial:f('corporate_cash_cost',p['id'],'corporate_gross_cash_cost - other_revenue',reason='Other revenue reconciles the gross expense taxonomy to corporate net costs.')
            for year in forecast_years:aggregate('corporate_cash_cost',year)
        legacy=rows.get(entity+'_cost_inflation')
        if legacy:
            legacy.update(kind='calculated',support_matrix=True,note='Diagnostic only: economic costs use independent pool controls. No pricing-linked fallback.',inputs={})
            for pid,cell in legacy['cells'].items():
                if not actual(cell):legacy['cells'][pid]=missing()
    for p in financial:summed('sbc',p['id'],[(pool_rows[e,pool['id']]+'_sbc_expense',p['id']) for e,_,_ in entities for pool in pools])
    for year in forecast_years:aggregate('sbc',year)
    rows['sbc_ratio']['kind']='calculated';rows['sbc_ratio']['note']='Diagnostic embedded compensation / sales; the independent expense budget drives compensation.'
    for p in financial:f('sbc_ratio',p['id'],'sbc / sales')
    for destination,items in by_dest.items():
        for p in financial:
            pid=p['id'];amounts=[pool_rows[e,pool['id']] for e,_,_ in entities for pool in items]
            expr='-('+' + '.join(amounts)+' + da * ('+' + '.join('pool_'+pool['id']+'_da_share' for pool in items)+'))'
            f(destination,pid,expr,reason='Authoritative functional cash pools plus explicit D&A allocation; not a residual of profit.')
        for year in forecast_years:aggregate(destination,year)
        legacy=rows.get(destination+'_allocation')
        if legacy:
            legacy.update(kind='calculated',note='Historical baseline/presentation allocation, not an economic profit driver.',inputs={})
            for p in financial:f(legacy['id'],p['id'],f'-{destination} / (total_revenue - utop)',reason='Diagnostic functional cost share; cannot change aggregate profit.')
            contract(legacy['id'],'group',None,'presentation_parameter',[])
    # Scope contributions are separate regional changes in the comparable base.
    # The event contributes only its change versus the same prior-year dates.
    # Once included in both periods, it is organic baseline rather than repeated M&A.
    event_audit=[]
    def event_overlap(event,p):
        return scope_period_inclusion(event,p['start'],p['end'],pm[py[p['fiscal_year'],'FY']]['duration_days'])
    def previous_overlap(event,p):
        prior=py.get((p['fiscal_year']-1,p['kind']))
        if prior:return event_overlap(event,pm[prior])
        def previous_day(s):
            d=date.fromisoformat(s)
            try:return d.replace(year=d.year-1)
            except ValueError:return d.replace(year=d.year-1,day=28)
        start=previous_day(p['start']);end=previous_day(p['end']);effective=date.fromisoformat(event['effective_date'])
        priorfy=pm.get(py.get((p['fiscal_year']-1,'FY')),{})
        denominator=priorfy.get('duration_days',365)
        return scope_period_inclusion(event,start.isoformat(),end.isoformat(),denominator)
    events=estimate_scope_events(cfg.get('scope_events',[]))
    # A complete business exit is a fraction of the running comparable base,
    # not a frozen old revenue number that leaves a fictitious residual business.
    for entity,label,_ in entities:
        full=[e for e in events if e.get('entity_id')==entity and e.get('enabled',True) and e.get('entity_scope_fraction') is not None]
        for suffix,labelpart in [('scope_active_fraction','remaining operating scope'),('scope_comparable_fraction','comparable prior operating scope'),('scope_activity_factor','remaining/comparable scope factor')]:
            make(entity+'_'+suffix,label+' — '+labelpart,'corporate' if entity=='corporate' else 'segment_'+entity,'ratio',
                 'calculated' if suffix=='scope_activity_factor' else 'assumption','ratio',support=True)
        for p in periods:
            current=previous=1.0
            for event in full:
                proportion=event['entity_scope_fraction']
                if not 0<=proportion<=1:raise ValueError('Entity scope fraction must lie between zero and one')
                whole=scope_period_inclusion(dict(event,effective_date=p['start']),p['start'],p['end'],pm[py[p['fiscal_year'],'FY']]['duration_days'])
                current*=1-proportion*event_overlap(event,p)/whole
                prior=py.get((p['fiscal_year']-1,p['kind']))
                if prior:
                    previous_period=pm[prior]
                    prior_fraction=scope_period_inclusion(dict(event,effective_date=previous_period['start']),previous_period['start'],previous_period['end'],pm[py[previous_period['fiscal_year'],'FY']]['duration_days'])
                else:prior_fraction=whole
                previous*=1-proportion*previous_overlap(event,p)/prior_fraction
            for suffix,value in [('scope_active_fraction',current),('scope_comparable_fraction',previous)]:
                rows[entity+'_'+suffix]['cells'][p['id']]=dict(value=value,status='estimate',editable=False,required=False,
                    reason='Effective-dated entity scope; partial-period exposure follows calendar days, not a claimed reported seasonal split.')
            f(entity+'_scope_activity_factor',p['id'],f'if_zero({entity}_scope_comparable_fraction, 0, {entity}_scope_active_fraction / {entity}_scope_comparable_fraction)',required=False)
    depreciation_roles={'owned_ppe_depreciation':'owned_ppe','rou_depreciation':'right_of_use_assets','amortization':'intangibles'}
    make('group_scope_da','Scope-related depreciation/amortisation adjustment','assets',support=True)
    for entity,label,_ in entities:
        if entity=='corporate':continue
        rid=entity+'_scope_da';make(rid,label+' scope depreciation/amortisation','segment_'+entity,support=True)
        direct=entity+'_direct_scope_da';make(direct,label+' partial-business scope D&A allocation','assets',support=True)
        selected=[e for e in events if e.get('entity_id')==entity and e.get('enabled',True)]
        for event in selected:
            if event.get('da_already_in_baseline'):continue
            allocations=event.get('annual_da_by_role',{})
            if set(allocations)-set(depreciation_roles):raise ValueError('Unsupported scope depreciation asset class')
            if event.get('annual_da') and not allocations:raise ValueError('Scope D&A requires explicit class allocation or documented already-in-baseline treatment')
            if allocations and event.get('annual_da') is not None and not math.isclose(sum(allocations.values()),event['annual_da'],abs_tol=1e-6):
                raise ValueError('Scope depreciation class allocations disagree with annual D&A effect')
        for p in financial:
            components=[];direct_components=[]
            for role,asset in depreciation_roles.items():
                control=entity+'_scope_'+role;make(control,label+' scope '+rows[role]['label'],'assets',support=True)
                event_components=[]
                for event in selected:
                    if event.get('da_already_in_baseline'):continue
                    # With a complete closing asset bridge, future opening assets
                    # already exclude the disposal. Only within-period timing is
                    # additional. Otherwise this is an explicit provisional run
                    # rate until the unmodelled derecognition is supplied.
                    amount=0 if event.get('accounting_enabled') and (event.get('accounting_date') or event['effective_date'])<p['start'] else event.get('annual_da_by_role',{}).get(role,0)*event_overlap(event,p)
                    event_control='scope_'+event['id']+'_'+role
                    make(event_control,event['id']+' — '+rows[role]['label'],'assets',kind='assumption',support=True)
                    a(event_control,p,amount,'Explicit event D&A by asset class, already weighted for event dates; missing deconsolidation remains separately qualified.')
                    event_components.append((event_control,p['id']))
                    if event.get('entity_scope_fraction') is None:direct_components.append((event_control,p['id']))
                if event_components:summed(control,p['id'],event_components)
                else:rows[control]['cells'][p['id']]=dict(value=0,status='forecast',editable=False,required=True)
                c=rows[role]['cells'][p['id']];c['expression']='('+c['expression']+') + '+control
                components.append((control,p['id']))
            summed(rid,p['id'],components)
            if direct_components:summed(direct,p['id'],direct_components)
            else:rows[direct]['cells'][p['id']]=dict(value=0,status='forecast',editable=False,required=True)
        for year in forecast_years:aggregate(rid,year)
    for p in financial:
        summed('group_scope_da',p['id'],[(e+'_scope_da',p['id']) for e,_,_ in entities if e!='corporate'])
        for entity,label,_ in entities:
            if entity=='corporate':f('corporate_da',p['id'],'(da - group_scope_da) * corporate_da_share')
            else:f(entity+'_da',p['id'],f'(da - group_scope_da) * {entity}_da_share + {entity}_scope_da')
    for year in forecast_years:aggregate('group_scope_da',year)
    make('active_da_allocation_total','Remaining-business D&A allocation total','assets','ratio',metric_type='ratio',support=True)
    make('allocated_scope_da','Scope D&A attributable to remaining operating businesses','assets',support=True)
    make('remaining_da_per_allocation_weight','Remaining D&A per allocation weight','assets',support=True)
    for entity,label,_ in entities:
        rid=entity+'_da_active_fraction'
        make(rid,label+' — depreciating allocation exposure','assets','ratio',metric_type='ratio',support=True)
        stops=[e['depreciation_stop_date'] for e in events if e.get('entity_id')==entity and e.get('enabled',True)
               and e.get('entity_scope_fraction')==1 and e.get('depreciation_stop_date')]
        for p in financial:
            exposure=1.0
            if stops:
                stop=date.fromisoformat(min(stops));start=date.fromisoformat(p['start']);end=date.fromisoformat(p['end'])
                exposure=max(0,min((stop-start).days,(end-start).days+1))/p['duration_days']
            active=rows[entity+'_scope_active_fraction']['cells'][p['id']]['value']
            rows[rid]['cells'][p['id']]=dict(value=min(active,exposure),status='estimate',editable=False,required=True,
                reason='Estimated allocation exposure: full-entity held-for-sale depreciation stops on its supplied date; no extra group D&A deduction. Partial-business events do not stop the entire entity.')
    for p in financial:
        terms=[e+'_da_share * '+e+'_da_active_fraction' for e,_,_ in entities]
        f('active_da_allocation_total',p['id'],' + '.join(terms))
        f('allocated_scope_da',p['id'],' + '.join(e+'_direct_scope_da' for e,_,_ in entities if e!='corporate'))
        f('remaining_da_per_allocation_weight',p['id'],'if_zero(active_da_allocation_total, 0, (da - allocated_scope_da) / active_da_allocation_total)',
          reason='Shared guarded allocation rate; a zero recipient weight with remaining group D&A fails the allocation completeness check.')
        for entity,label,_ in entities:
            adjustment='' if entity=='corporate' else ' + '+entity+'_direct_scope_da'
            f(entity+'_da',p['id'],f'remaining_da_per_allocation_weight * {entity}_da_share * {entity}_da_active_fraction'+adjustment,
                reason='Estimated proportional allocation of unchanged group D&A among remaining depreciating businesses; full-entity held-for-sale cessation uses the supplied date and preserves reported history.')
    for entity,label,_ in entities:
        if entity=='corporate':continue
        selected=[e for e in events if e.get('entity_id')==entity]
        scope=entity+'_scope_effect';make(scope,'Modelled incremental scope contribution to sales','segment_'+entity)
        growth=entity+'_scope_growth';make(growth,'Scope contribution to reported sales growth','segment_'+entity,'ratio',metric_type='ratio')
        rows[entity+'_growth']['label']='Modelled sales growth'
        rows[entity+'_growth']['note']='Organic pricing/activity, effective-dated operating scope and separately applied translation FX.'
        sales_periods=[p for p in periods if p['fiscal_year'] in forecast_years and forecast(entity+'_sales',p['id']) and
            p['kind'] in (('Q1','Q2','Q3','Q4') if any((p['fiscal_year'],k) in py for k in ('Q1','Q2','Q3','Q4')) and
                spec.get('model_configuration',{}).get('primary_sales_frequency',frequency)=='quarterly' else regular if any((p['fiscal_year'],k) in py for k in regular) else ('FY',))]
        for p in periods:
            if p['fiscal_year']<base:continue
            if actual(rows[entity+'_sales']['cells'].get(p['id'],{})):
                rows[scope]['cells'][p['id']]=missing();continue
            rows[scope]['cells'][p['id']]=dict(value=0,status='forecast',editable=False,required=False,
                reason='No incremental configured scope contribution; known excluded/unresolved events remain in the event audit.')
        for p in sales_periods:
            ids=[];negative=[];positive=[]
            for event in selected:
                if not event.get('enabled',True):continue
                if event.get('entity_scope_fraction') is not None:continue
                eventid=entity+'_scope_'+event['id'];make(eventid,event.get('label',event['id'])+' revenue step','segment_'+entity,kind='assumption',
                    note='Effective-dated annual run-rate change less comparable prior-year contribution; no repeated acquisition addition.',support=True)
                annual=event.get('annual_revenue')
                if annual is None:continue
                delta=annual*(event_overlap(event,p)-previous_overlap(event,p));a(eventid,p,delta,event.get('status','provisional scope scenario'))
                ids.append(eventid)
                (negative if annual<0 else positive).append(eventid)
                contract(eventid,entity,None,'economic_input',[entity+'_sales','sales'],timing=event['effective_date'],definition=event.get('label',event['id']))
            full_step=f'{entity}_sales_seed * ({entity}_scope_activity_factor - 1)'
            f(scope,p['id'],full_step+(' + '+' + '.join(ids) if ids else ''))
            f(growth,p['id'],f'if_zero({entity}_sales_seed, 0, {scope} / {entity}_sales_seed)')
            organic=entity+'_organic_comparable_sales';make(organic,'Organic comparable sales excluding disposed scope','segment_'+entity,support=True)
            f(organic,p['id'],f'{entity}_sales_seed * {entity}_scope_activity_factor'+(' + '+' + '.join(negative) if negative else ''),
                reason='Disposed comparable sales do not receive organic pricing or activity growth; acquisitions enter scope before joining the comparable organic base.')
            constant=f'{organic} * (1 + {entity}_organic)'+(' + '+' + '.join(positive) if positive else '')
            constant_row=entity+'_constant_currency_sales';make(constant_row,'Sales including scope before translation','segment_'+entity,support=True)
            f(constant_row,p['id'],constant)
            translation=entity+'_revenue_fx_adjusted'
            cell=rows[entity+'_sales']['cells'][p['id']]
            if translation in rows and present(translation,p['id']):
                rows[entity+'_fx']['kind']='calculated'
                f(entity+'_sales',p['id'],f'{constant_row} * (1 + {translation})')
                f(entity+'_fx_effect',p['id'],f'{constant_row} * {translation}')
                f(entity+'_fx',p['id'],f'if_zero({entity}_sales_seed, 0, {entity}_fx_effect / {entity}_sales_seed)')
            else:
                f(entity+'_sales',p['id'],constant_row+f' + {entity}_sales_seed * {entity}_fx')
            aggregate_organic=spec.get('model_configuration',{}).get('revenue_models',{}).get(entity,{}).get('method')=='aggregate_organic'
            for suffix,driver in [('pricing_effect','organic' if aggregate_organic else 'pricing'),('rig_effect','rig')]:f(entity+'_'+suffix,p['id'],organic+' * '+entity+'_'+driver)
            if entity+'_growth' in rows:f(entity+'_growth',p['id'],f'if_zero({entity}_sales_seed, 0, {entity}_sales / {entity}_sales_seed - 1)')
            for identity in spec.get('identities',[]):
                if identity.get('id','').startswith(entity+'_sales_bridge_') and p['id'] in identity.get('periods',[]):
                    identity['expression']+=' - '+scope
        # Scope cost steps enter the appropriate functional pool before FX.
        for p in financial:
            for pool in pools:
                rid=pool_rows[entity,pool['id']];sid=rid+'_scope_change'
                make(sid,pool['label']+' operating scope change','segment_'+entity,kind='assumption',note='Signed cash cost change from configured scope events; not revenue-growth allocation.',support=True)
                amount=0
                for event in selected:
                    if event.get('enabled',True) and event.get('entity_scope_fraction') is None:amount+=event.get('annual_cash_costs',{}).get(pool['id'],0)*(event_overlap(event,p)-previous_overlap(event,p))
                a(sid,p,amount)
                before=f'{rid}_seed * {entity}_scope_activity_factor'+(' + '+sid if amount<0 else '')
                f(rid+'_activity_base',p['id'],before)
                expr=cost_expression(rid,pool,rid+'_activity_base',entity+'_scope_activity_factor')
                if amount>=0:expr+=' + '+sid
                f(rid+'_pre_fx',p['id'],expr,reason='Disposed costs leave the activity/unit-cost baseline; acquisition cost enters scope once. Full exits remove the current expense base rather than an old fixed amount.')
            f(entity+'_margin',p['id'],f'if_zero({entity}_sales, 0, {entity}_utop / {entity}_sales)',reason='Inactive fully closed entity displays zero margin; no active profit forecast remains.')
        for year in forecast_years:
            # Scope follows sales frequency, which can differ from financial flows.
            for p in [q for q in periods if q['fiscal_year']==year]:
                members=[q for q in sales_periods if q['fiscal_year']==year and q['id']!=p['id'] and q['start']>=p['start'] and q['end']<=p['end']]
                if members and p['kind'] in ('H1','H2','FY','9M'):summed(scope,p['id'],[(scope,q['id']) for q in members])
        for p in periods:
            if p['fiscal_year'] in forecast_years and forecast(entity+'_margin',p['id']):
                f(entity+'_margin',p['id'],f'if_zero({entity}_sales, 0, {entity}_utop / {entity}_sales)',reason='Inactive fully closed entity: zero display, no meaningful margin estimate.')
            if p['fiscal_year'] in forecast_years and present(scope,p['id']):
                prior=py.get((p['fiscal_year']-1,p['kind']))
                if prior and present(entity+'_sales',prior):
                    f(growth,p['id'],'if_zero(base, 0, scope / base)',{'base':dict(row_id=entity+'_sales',period_id=prior),
                      'scope':dict(row_id=scope,period_id=p['id'])},reason='Sum monetary scope effects first, then divide by corresponding prior-period sales.')
            season=rows.get(entity+'_sales_seasonality',{}).get('cells',{}).get(p['id'],{})
            if season.get('expression')=='part / whole' and not actual(season):
                season['expression']='if_zero(whole, period_year_fraction, part / whole)'
                season['reason']='Comparable sales seasonality; calendar duration is inactive fallback after a full business exit.'
    for event in events:
        unresolved=not event.get('accounting_enabled',False)
        event_audit.append(dict(event,material_unresolved=unresolved,limitation='Operating scope is separately modelled where enabled; acquisition/disposal closing balance and gain/cash breakdown remains unresolved. Missing transferred working-capital balances can affect the projected operating cash flow, not just disposal proceeds.' if unresolved else 'Explicit event cash and balance counterparts supplied.'))
    spec['scope_event_audit']=event_audit
    investing_note='Capital expenditure and explicitly configured investing cash flows. Unprovided acquisition/disposal closing flows remain unmodelled in the scope-event audit.'
    rows['cfi']['note']=investing_note
    for p in financial:
        if not actual(rows['cfi']['cells'][p['id']]):rows['cfi']['cells'][p['id']]['reason']=investing_note
    # Complete acquisition/disposal accounting is activated only from explicit
    # cash, balance and gain inputs. An unknown consideration/asset split cannot
    # be recovered by making a reserve or cash plug.
    asset_roles={'inventories','receivables','owned_ppe','right_of_use_assets','intangibles','goodwill',
                 'associates','short_investments','other_current_assets','other_noncurrent_assets_ex_tax','deferred_tax_assets'}
    liability_roles={'trade_payables','nonlease_debt','lease_liabilities','current_tax_liabilities',
                     'other_current_liabilities_ex_tax','other_noncurrent_liabilities_ex_tax','deferred_tax_liabilities'}
    for event in events:
        if not event.get('enabled',True) or not event.get('accounting_enabled',False):continue
        if not event.get('source_refs'):raise ValueError('Active scope accounting requires source evidence or an explicit cited scenario')
        accounting_date=event.get('accounting_date') or event['effective_date']
        for p in financial:
            if not p['start']<=accounting_date<=p['end']:continue
            pid=p['id'];closing=py[p['fiscal_year'],'FY'] if p['kind']=='H2' else pid
            for role,amount in event.get('cash_flows',{}).items():
                if role not in rows or rows[role].get('section')!='cashflow':raise ValueError('Unsupported scope cash-flow destination '+role)
                driver='scope_'+event['id']+'_'+role;make(driver,event['id']+' — '+rows[role]['label'],'cashflow',kind='assumption',support=True)
                a(driver,p,amount)
                c=rows[role]['cells'][pid]
                if actual(c):raise ValueError('Scope accounting cannot overwrite a reported transaction')
                c['expression']='('+c.get('expression','0')+') + '+driver
            for role,amount in event.get('balance_movements',{}).items():
                if role not in asset_roles|liability_roles or role not in rows:raise ValueError('Unsupported scope balance destination '+role)
                driver='scope_'+event['id']+'_'+role;make(driver,event['id']+' — '+rows[role]['label']+' movement','working_capital',kind='assumption',support=True)
                a(driver,p,amount);c=rows[role]['cells'][closing]
                if actual(c):raise ValueError('Scope accounting cannot overwrite a reported closing balance')
                cf={'inventories':'wc_inventory_cf','receivables':'wc_receivables_cf','trade_payables':'wc_payables_cf'}.get(role)
                if cf:
                    # These closing stocks are already post-scope targets from
                    # the remaining revenue/cost base. Add the transfer only to
                    # their cash bridge, not to the closing target a second time.
                    c=rows[cf]['cells'][pid];c['expression']='('+c['expression']+') '+('-' if role=='trade_payables' else '+')+' '+driver
                    c.setdefault('bindings',{})[driver]=dict(row_id=driver,period_id=pid)
                else:
                    c['expression']='('+c['expression']+') + '+driver;c.setdefault('bindings',{})[driver]=dict(row_id=driver,period_id=pid)
                prefix={'owned_ppe':'ppe_roll_','intangibles':'intangible_roll_','nonlease_debt':'debt_roll_','lease_liabilities':'debt_roll_'}.get(role)
                if prefix:
                    for identity in spec.get('identities',[]):
                        if identity.get('id','').startswith(prefix) and pid in identity.get('periods',[]):identity['expression']+=' - '+driver
            gain=event.get('gain_loss',0);rid='scope_'+event['id']+'_gain_loss'
            make(rid,event['id']+' — disposal/acquisition P&L','income',kind='assumption',support=True);a(rid,p,gain)
            # Attach to the calculated adjustment, not its recurring policy input.
            c=rows['net_other_operating']['cells'][pid];c['expression']='('+c['expression']+') + '+rid
            c=rows['cfo_portfolio_noncash']['cells'][pid];c['expression']='('+c['expression']+') - '+rid
            if 'tax_rate' in event:
                # Reverse the ordinary operating tax/NCI policy on this event,
                # then apply separately specified event treatment exactly once.
                tax=event['tax_rate'];nci=event.get('nci_share',0)
                taxid='scope_'+event['id']+'_tax_rate';nciid='scope_'+event['id']+'_nci_share'
                make(taxid,'Event-specific tax-rate estimate','income','ratio','assumption','ratio',support=True);a(taxid,p,tax)
                make(nciid,'Event-specific NCI attribution estimate','income','ratio','assumption','ratio',support=True);a(nciid,p,nci)
                c=rows['tax_expense']['cells'][pid]
                c['expression']='('+c['expression']+') + '+rid+f' * (effective_tax_rate - {taxid})'
                c=rows['nci_profit']['cells'][pid]
                c['expression']='('+c['expression']+') + '+rid+f' * (1 - {taxid}) * ({nciid} - nci_profit_share)'
            transfer=event.get('oci_reclassification',0)
            if transfer:
                rid='scope_'+event['id']+'_oci_reclassification';make(rid,event['id']+' — separately sourced OCI reclassification','working_capital',kind='assumption',support=True)
                a(rid,p,transfer);c=rows['reserves']['cells'][closing]
                c['expression']='('+c['expression']+') + '+rid;c.setdefault('bindings',{})[rid]=dict(row_id=rid,period_id=pid)
        removed=event.get('held_for_sale_cash_removed',0)
        if removed:
            rid='scope_'+event['id']+'_held_for_sale_cash';make(rid,'Estimated cash removed from held-for-sale scope','cashflow',kind='assumption',metric_type='stock',support=True)
            for y in forecast_years:a(rid,pm[py[y,'FY']],removed)
            for p in periods:
                if p['end']<accounting_date or not forecast('held_for_sale_cash',p['id']):continue
                c=rows['held_for_sale_cash']['cells'][p['id']]
                if c.get('expression'):
                    c['expression']='('+c['expression']+') - '+rid
                    c.setdefault('bindings',{})[rid]=dict(row_id=rid,period_id=py[p['fiscal_year'],'FY'])
        retained=event.get('retained_operation')
        if retained:
            inv='scope_'+event['id']+'_retained_investment';earn=inv+'_earnings';dist=inv+'_distributions'
            make(inv,'Retained investment carrying amount','assets',metric_type='stock',support=True)
            make(earn,'Retained operation after-tax earnings','income',support=True);make(dist,'Retained operation cash distributions','cashflow',support=True)
            historical_cutoff=data.get('model_configuration',{}).get('actual_through',pm[base_pid]['end'])
            for p in periods:
                for rid,creation_date in ((inv,accounting_date),(earn,event['effective_date']),(dist,event['effective_date'])):
                    if p['end']>=creation_date:continue
                    rows[rid]['cells'][p['id']]=dict(value=0,status='derived_actual' if p['end']<=historical_cutoff else 'forecast',
                        data_role='structural_absence',calibration_eligible=False,editable=False,required=False,
                        reason='Structural absence before the configured accounting creation or operating inclusion date; this zero is not a reported historical observation or calibration evidence.')
            previous=None
            if financial and accounting_date<financial[0]['start']:
                opening=retained.get('opening_carrying_value')
                if opening is None or not retained.get('opening_source_refs'):
                    raise ValueError('Existing retained operation requires a cited opening carrying estimate; otherwise generic yield and incremental earnings would double count')
                candidates=[p for p in periods if p['end']<financial[0]['start'] and p['kind'] in ('FY','H1','Q1','Q2','Q3','Q4')]
                previous=max(candidates,key=lambda p:p['end'])['id']
                rows[inv]['cells'][previous]=dict(value=opening,status='estimated',data_role='estimated_historical_baseline',calibration_eligible=False,
                    editable=False,required=False,source_refs=retained['opening_source_refs'],reason='Explicit opening retained investment; exclude generic yield before adding separately modelled earnings.')
            for p in financial:
                pid=p['id'];closing=py[p['fiscal_year'],'FY'] if p['kind']=='H2' else pid
                inclusion=event_overlap(event,p)
                earnings=retained['annual_profit_after_tax']*retained['ownership']*inclusion
                payout=earnings*retained['distribution_share']
                a(earn,p,earnings);rows[earn]['kind']='assumption';a(dist,p,payout);rows[dist]['kind']='assumption'
                opening=0 if previous is None else previous
                # Remove the generic investment-yield return on this separate
                # carrying amount before adding the independently estimated JV.
                correction=earn
                bindings={}
                if previous:
                    correction+=' - retained_opening * associate_earnings_yield * period_year_fraction'
                    bindings['retained_opening']=dict(row_id=inv,period_id=previous)
                c=rows['associate_profit']['cells'][pid];c['expression']='('+c['expression']+') + '+correction;c.setdefault('bindings',{}).update(bindings)
                c=rows['associate_dividends']['cells'][pid]
                c['expression']='('+c['expression']+') - '+earn+' * associate_distribution_ratio + '+dist
                start_value=event.get('estimation',{}).get('closing',{}).get('retained_investment',0) if p['start']<=accounting_date<=p['end'] else 0
                capital=inv+'_initial_value';make(capital,'Estimated retained investment at loss of control','assets',kind='assumption',support=True);a(capital,p,start_value)
                expr=capital+' + '+earn+' - '+dist
                binds={r:dict(row_id=r,period_id=pid) for r in (earn,dist,capital)}
                if previous:expr+=' + opening';binds['opening']=dict(row_id=inv,period_id=previous)
                f(inv,closing,expr,binds);previous=closing
            for y in forecast_years:aggregate(earn,y);aggregate(dist,y)
    # Regional cost FX summaries sum money before deriving annual percentages.
    for entity,label,_ in entities:
        if entity=='corporate':continue
        amount=entity+'_cost_fx_amount';base_row=entity+'_cost_fx_base'
        rows[entity+'_cost_fx']['kind']='calculated'
        make(amount,'Translation FX — functional cost monetary effect','segment_'+entity)
        make(base_row,'Pre-translation functional cost base','segment_'+entity,note='Includes transaction FX once; annual factor uses this economic base.',support=True)
        for p in financial:
            summed(amount,p['id'],[(pool_rows[entity,pool['id']]+'_translation_amount',p['id']) for pool in pools])
            expr=' + '.join(pool_rows[entity,pool['id']]+'_pre_fx + '+pool_rows[entity,pool['id']]+'_transaction_amount' for pool in pools)
            f(base_row,p['id'],expr)
        for year in forecast_years:aggregate(amount,year);aggregate(base_row,year)
        for p in periods:
            if p['fiscal_year'] in forecast_years and present(amount,p['id']):
                f(entity+'_cost_fx',p['id'],f'if_zero({base_row}, 0, {amount} / {base_row})',reason='Financial translation impact divided by the summed underlying cost base, not a duration-average of percentages. Zero for an inactive closed business.')
                for suffix in ('_cost_fx_adjusted','_cost_fx_raw'):
                    if entity+suffix in rows:f(entity+suffix,p['id'],entity+'_cost_fx')
    make('group_cost_fx_amount','Group cost translation — monetary impact','corporate')
    for p in financial:summed('group_cost_fx_amount',p['id'],[(pool_rows[e,pool['id']]+'_translation_amount',p['id']) for e,_,_ in entities for pool in pools])
    for year in forecast_years:aggregate('group_cost_fx_amount',year)
    # Operating working-capital targets use constant-translation activity/cost
    # bases. Closing-rate translation and acquired/disposed balances are separate
    # movements below, not operating cash flows generated by a currency change.
    make('operating_cogs_base','COGS before modelled translation for operating working capital','working_capital',support=True)
    make('operating_sales_base','Sales before modelled translation for operating working capital','working_capital',support=True)
    for rid,label in [('closing_scope_sales_correction','Period-equivalent revenue adjustment to closing operating scope'),
                      ('closing_scope_cost_correction','Period-equivalent COGS expense adjustment to closing operating scope'),
                      ('closing_operating_sales_base','Period-equivalent sales run rate for closing working capital'),
                      ('closing_operating_cogs_base','Period-equivalent COGS run rate for closing working capital')]:
        make(rid,label,'working_capital',support=True,note='Closing working capital uses remaining operating scope at the balance date, separately from time-weighted income-statement flows. Estimated run rate, not a reported flow.')
    for event in events:
        exclusion=event.get('operating_wc_excluded_from')
        if not exclusion or not event.get('enabled',True):continue
        date.fromisoformat(exclusion)
        accounting=event.get('accounting_date') or event['effective_date']
        if exclusion>accounting:raise ValueError('Operating working-capital exclusion cannot follow the accounting disposal date')
        if financial and exclusion>=financial[0]['start']:
            raise ValueError('Forecast held-for-sale reclassification requires a separate supported transfer bridge; operating_wc_excluded_from currently describes an already reported reclassification')
        if set(event.get('balance_movements',{})) & {'inventories','receivables','trade_payables'}:
            raise ValueError('Already reclassified held-for-sale working capital cannot be removed again from operating balances at disposal')
    if any(e.get('operating_wc_excluded_from') for e in events):
        policy=f'Working-capital turnover holds fiscal {base} ratios as provisional assumptions on remaining operating scope. Held-for-sale exclusions use cited dates and estimated business run rates; these are not observed post-reclassification turnover ratios.'
        spec['policies']['working_capital']=policy
        for rid in ('inventory_ratio','receivables_ratio','payables_ratio'):rows[rid]['note']=policy
    for p in financial:
        pid=p['id'];fxcost=[pool_rows[e,pool['id']]+'_translation_amount' for e,_,_ in entities for pool in pools if pool['destination']=='cogs']
        f('operating_cogs_base',pid,'cogs + '+' + '.join(fxcost),reason='Remove the modelled consolidation FX expense; transaction FX remains a functional-currency input cost.')
        rev_bindings={};revterms=[];entity_fx={}
        for entity,_,_ in entities:
            if entity=='corporate':continue
            # Revenue may be quarterly while the WC financial flow is half-year.
            candidates=[q for q in periods if q['start']>=p['start'] and q['end']<=p['end'] and q['kind'].startswith('Q')]
            if not candidates:candidates=[p]
            for q in candidates:
                role=entity+'_fx_effect';cell=rows[role]['cells'].get(q['id'],{})
                if rows[entity+'_sales']['cells'].get(q['id'],{}).get('status') not in ('forecast','estimate'):continue
                if cell.get('status') not in ('forecast','estimate') or not present(role,q['id']):continue
                token='fx'+str(len(revterms));revterms.append(token);rev_bindings[token]=dict(row_id=role,period_id=q['id'])
                entity_fx.setdefault(entity,[]).append((role,q['id']))
        f('operating_sales_base',pid,'sales'+(' - ('+' + '.join(revterms)+')' if revterms else ''),rev_bindings,
          'Remove known modelled translation only. Undisclosed historical FX is not reconstructed; mixed-period working-capital targets remain provisional.')
        revenue_corrections=[];cost_corrections=[]
        for entity,label,_ in entities:
            selected=[e for e in events if e.get('enabled',True) and e.get('entity_id')==entity and
                (p['start']<=(e.get('accounting_date') or e['effective_date'])<=p['end'] or
                 e.get('operating_wc_excluded_from') and e['operating_wc_excluded_from']<=p['end'])]
            full=[e for e in selected if e.get('entity_scope_fraction') is not None]
            if full:
                end=1.0
                for event in events:
                    closing_date=event.get('operating_wc_excluded_from') or event.get('accounting_date') or event['effective_date']
                    if event.get('enabled',True) and event.get('entity_id')==entity and event.get('entity_scope_fraction') is not None and closing_date<=p['end']:end*=1-event['entity_scope_fraction']
                active=entity+'_closing_scope_active_fraction';factor=entity+'_closing_scope_correction_factor'
                make(active,label+' closing operating scope','working_capital','ratio',metric_type='ratio',support=True)
                make(factor,label+' closing versus included operating scope','working_capital','ratio',metric_type='ratio',support=True)
                rows[active]['cells'][pid]=dict(value=end,status='estimate',editable=False,required=True,reason='Remaining entity fraction at the closing date; dated company scope configuration.')
                f(factor,pid,f'if_zero({entity}_scope_active_fraction, 0, {active} / {entity}_scope_active_fraction - 1)')
                if entity!='corporate':
                    rid=entity+'_closing_scope_sales_correction';make(rid,label+' closing revenue scope correction','working_capital',support=True)
                    bindings={f'fx{i}':dict(row_id=r,period_id=q) for i,(r,q) in enumerate(entity_fx.get(entity,[]))}
                    untranslated=entity+'_sales'+(' - ('+' + '.join(bindings)+')' if bindings else '')
                    f(rid,pid,'('+untranslated+') * '+factor,bindings);revenue_corrections.append(rid)
                rid=entity+'_closing_scope_cost_correction';make(rid,label+' closing expense scope correction','working_capital',support=True)
                terms=[pool_rows[entity,pool['id']]+'_'+suffix for pool in by_dest['cogs'] for suffix in ('pre_fx','transaction_amount','sbc_expense')]
                da_share=' + '.join('pool_'+pool['id']+'_da_share' for pool in by_dest['cogs'])
                f(rid,pid,'('+' + '.join(terms)+' + '+entity+'_da * ('+da_share+')) * '+factor);cost_corrections.append(rid)
            for event in selected:
                if event.get('entity_scope_fraction') is not None:continue
                # The income statement includes the business for only part of
                # this period. Closing balances require the full post-event run
                # rate; transferred balances remain separate in the cash bridge.
                weight=0 if event['effective_date']<=p['start'] else frac(p)-event_overlap(event,p)
                if entity!='corporate':
                    rid='scope_'+event['id']+'_closing_revenue_correction';make(rid,'Estimated closing revenue scope adjustment','working_capital',support=True)
                    control=rid+'_run_rate';make(control,'Period-equivalent extra event revenue exposure','working_capital',support=True)
                    rows[control]['cells'][pid]=dict(value=event.get('annual_revenue',0)*weight,status='estimate',editable=False,required=True,
                        reason='Configured event annual run rate times closing-versus-included date exposure; rebuild from the event scenario when its estimate changes.',source_refs=copy.deepcopy(event.get('source_refs',[])))
                    expression=control+(' * (1 + '+entity+'_organic)' if event.get('annual_revenue',0)<0 else '')
                    f(rid,pid,expression);revenue_corrections.append(rid)
                for pool in by_dest['cogs']:
                    rid='scope_'+event['id']+'_'+pool['id']+'_closing_cost_correction';make(rid,'Estimated closing COGS scope adjustment','working_capital',support=True)
                    control=rid+'_run_rate';make(control,'Period-equivalent extra event cash-cost exposure','working_capital',support=True)
                    amount=event.get('annual_cash_costs',{}).get(pool['id'],0)
                    rows[control]['cells'][pid]=dict(value=amount*weight,status='estimate',editable=False,required=True,
                        reason='Configured signed event cash-cost run rate times closing-versus-included date exposure.',source_refs=copy.deepcopy(event.get('source_refs',[])))
                    expr=control;poolid=pool_rows[entity,pool['id']]
                    if amount<0:
                        if pool['method']=='activity_cost':expr+=f' * (1 + {poolid}_activity_change * {poolid}_effective_activity_sensitivity) * (1 + {poolid}_unit_cost_change)'
                        elif pool['method']=='budget_growth':expr+=' * (1 + '+poolid+'_spending_change)'
                    if not pool['input_cost_includes_transaction_fx']:expr+=' * (1 + '+poolid+'_transaction_fx)'
                    da=0 if event.get('da_already_in_baseline') else event.get('annual_da',0)
                    dacontrol=rid+'_da_run_rate';make(dacontrol,'Period-equivalent extra event D&A exposure','working_capital',support=True)
                    rows[dacontrol]['cells'][pid]=dict(value=da*weight,status='estimate',editable=False,required=True,
                        reason='Configured event D&A run rate times closing-versus-included date exposure; allocated to the expense destination explicitly.')
                    f(rid,pid,expr+' + '+dacontrol+' * pool_'+pool['id']+'_da_share');cost_corrections.append(rid)
        for rid,terms in [('closing_scope_sales_correction',revenue_corrections),('closing_scope_cost_correction',cost_corrections)]:
            f(rid,pid,' + '.join(terms) if terms else '0 * sales')
        f('closing_operating_sales_base',pid,'operating_sales_base + closing_scope_sales_correction')
        f('closing_operating_cogs_base',pid,'operating_cogs_base - closing_scope_cost_correction')
        closing=py[p['fiscal_year'],'FY'] if p['kind']=='H2' else pid
        for role,dep,target in [('inventories','cogs','closing_operating_cogs_base'),('trade_payables','cogs','closing_operating_cogs_base'),('receivables','sales','closing_operating_sales_base')]:
            cell=rows[role]['cells'][closing]
            if cell.get('expression') and not actual(cell):cell.setdefault('bindings',{})[dep]=dict(row_id=target,period_id=pid)
    for year in forecast_years:
        aggregate('operating_cogs_base',year);aggregate('operating_sales_base',year)
    # Normalisation retains recurring expenditure and isolates exceptional fade.
    normalization=cfg.get('normalisation',cfg.get('normalization',{}))
    for role,assumption,parts in [('net_other_trading','net_other_trading_assumption',('other_trading_income','other_trading_expense')),
                                  ('net_other_operating','net_other_operating_assumption',('other_operating_income','other_operating_expense'))]:
        policy=normalization.get(role,{})
        amount=policy.get('annual_amount',hv(role,sum(hv(x,0) for x in parts)) if any(x not in history for x in parts) else sum(hv(x,0) for x in parts))
        for p in financial:a(assumption,p,amount*frac(p),policy.get('reason','Explicit recurring run-rate scenario from latest net adjustment; exceptional classification remains unresolved.'))
        contract(assumption,'group',None,'economic_input',['operating_profit','parent_profit','cfo'],timing='annual policy allocated by fiscal duration')
    for rid,label in [('underlying_operating_profit_change','Underlying operating profit change'),
                      ('normalisation_profit_change','Profit change from trading/operating adjustments'),
                      ('statutory_operating_profit_change','Statutory operating profit change')]:
        make(rid,label,'income',note='Separate operating performance from the assumed change/disappearance of exceptional or recurring adjustments.')
    for p in periods:
        pid=p['id'];prior=py.get((p['fiscal_year']-1,p['kind']))
        if not prior or not all(present(r,q) for r in ('utop','net_other_trading','net_other_operating','operating_profit') for q in (pid,prior)):continue
        status='derived_actual' if actual(rows['operating_profit']['cells'][pid]) else 'forecast'
        f('underlying_operating_profit_change',pid,'utop - prior',{'prior':dict(row_id='utop',period_id=prior)},status=status,required=False)
        f('normalisation_profit_change',pid,'net_other_trading + net_other_operating - prior_trading - prior_operating',{
            'prior_trading':dict(row_id='net_other_trading',period_id=prior),'prior_operating':dict(row_id='net_other_operating',period_id=prior)},status=status,required=False)
        f('statutory_operating_profit_change',pid,'operating_profit - prior',{'prior':dict(row_id='operating_profit',period_id=prior)},status=status,required=False)
        spec['identities'].append(dict(id='normalisation_bridge_'+pid,label='Operating performance plus adjustment changes equals statutory profit change',periods=[pid],
            expression='statutory_operating_profit_change - underlying_operating_profit_change - normalisation_profit_change',tolerance=2.5 if status=='derived_actual' else 1e-6,independent=False))
    # Dividend policy is a fixed annual pool, separate from its payment schedule.
    dividend_cfg=cfg.get('dividends',{})
    for side,role in [('parent','dividends_parent'),('nci','dividends_nci')]:
        rid=role+'_annual_pool';make(rid,'Annual '+side+' dividend pool','financing',kind='assumption',metric_type='stock',
                                   note='Declared/supported annual amount; independent of half-year earnings annualisation.')
        policy=dividend_cfg.get(side,{})
        for year in forecast_years:
            fy=py[year,'FY'];amount=policy.get('amounts',{}).get(str(year),policy.get('annual_amount',-hv(role,0)))
            a(rid,pm[fy],amount,policy.get('reason','Latest paid annual dividend held nominally constant; explicit provisional annual pool.'))
        for p in financial:
            fy=py[p['fiscal_year'],'FY'];season=role+'_seasonality'
            if season not in rows:make(season,'Dividend payment fraction','financing','ratio','assumption','ratio')
            if p['kind']=='FY':a(season,p,1,'Direct annual payment of the annual dividend pool')
            elif p['kind'] in policy.get('payment_weights',{}):a(season,p,policy['payment_weights'][p['kind']],'Explicit company dividend payment schedule')
            elif not present(season,p['id']):a(season,p,frac(p),'Explicit fiscal-duration payment schedule')
            f(role,p['id'],'-pool * payment',{'pool':dict(row_id=rid,period_id=fy),'payment':dict(row_id=season,period_id=p['id'])},'Annual cash dividend pool multiplied by payment timing; not current half-year EPS.')
        for year in forecast_years:aggregate(role,year)
        contract(rid,'group',None,'economic_input',[role,'closing_cash','retained_earnings'],timing='annual amount, separately scheduled payments')
        if side=='parent' and 'dividend_payout' in rows:
            rows['dividend_payout']['kind']='calculated';rows['dividend_payout']['note']='Diagnostic payout ratio; annual dividend pool and payment timing are authoritative.'
            for p in financial:f('dividend_payout',p['id'],'-dividends_parent / parent_profit')
        if side=='nci' and 'nci_dividend_payout' in rows:
            rows['nci_dividend_payout']['kind']='calculated';rows['nci_dividend_payout']['note']='Diagnostic payout ratio; the annual NCI pool is authoritative.'
            for p in financial:f('nci_dividend_payout',p['id'],'if_zero(nci_profit, 0, -dividends_nci / nci_profit)',
                reason='Inactive zero-profit diagnostic is zero; the explicit annual NCI dividend pool remains authoritative.')
        payout='dividend_payout' if side=='parent' else 'nci_dividend_payout'
        if payout in rows:
            expression='-dividends_parent / parent_profit' if side=='parent' else 'if_zero(nci_profit, 0, -dividends_nci / nci_profit)'
            for year in forecast_years:
                fy=py[year,'FY']
                if not actual(rows[payout]['cells'].get(fy,{})):
                    f(payout,fy,expression,reason='Annual cash dividends divided by the corresponding annual profit; never a duration-weighted average of interim payout ratios.')
    finance=cfg.get('financing',{})
    rows['buyback_price'].pop('initialization_expression',None);rows['buyback_price'].pop('initialization_components',None)
    rows['buyback_price'].pop('initialization_period',None);rows['buyback_price']['source_refs']={};rows['buyback_price']['historical']={}
    for pid,c in rows['buyback_price']['cells'].items():
        if actual(c):rows['buyback_price']['cells'][pid]=missing()
        else:c['required']=False
    make('repurchase_elapsed_fraction','Repurchase timing: fraction of period elapsed','financing','ratio','assumption','ratio',
         note='0=start, 0.5=midpoint, 1=end. Closing shares and time-weighted EPS shares are distinct.')
    make('issuance_shares','New shares issued (millions)','financing','shares_m','assumption','flow')
    make('issuance_elapsed_fraction','Issuance timing: fraction of period elapsed','financing','ratio','assumption','ratio')
    make('issuance_price','Share issuance execution price','financing',money+'/shares_m','assumption','ratio',
         note='Explicit reporting-currency issue price. A missing price is permitted only for inactive issuance.')
    make('issuance_cash','Cash proceeds from issued shares','cashflow')
    if 'shares_end_outstanding' not in rows:
        make('shares_end_outstanding','Closing shares outstanding (millions)','income','shares_m','calculated','stock',
             note='Opening closing-share estimate uses reported weighted shares only where the company lacks a separate closing count.')
        rows['shares_end_outstanding']['cells'][base_pid]=dict(copy.deepcopy(rows['shares_basic']['cells'][base_pid]),
            status='estimated',reason='Unresolved closing count: explicitly labelled weighted-average opening proxy, not an actual closing-share disclosure.')
        spec['gaps'].append('Closing shares lack a distinct source at the base date; the weighted-average opening proxy remains an unresolved financing input.')
    for item in finance.get('historical_closing_shares',[]):
        pid=item['period_id'];amount=item['value']
        if pid not in pm or pm[pid]['end']>spec['model_configuration'].get('actual_through',pm[base_pid]['end']) or not item.get('source_refs') or not isinstance(amount,(int,float)) or isinstance(amount,bool) or not math.isfinite(amount) or amount<=0:
            raise ValueError('Historical closing shares require an actual date, positive count and source evidence')
        disclosed=[o for o in data.get('observations',[]) if o['row_id']=='shares_end_outstanding' and o['period_id']==pid and o.get('status') in ('actual','reported','derived_actual')]
        if any(not math.isclose(o['value'],amount,abs_tol=1e-8,rel_tol=0) for o in disclosed):raise ValueError('Historical closing shares conflict with a preserved source observation')
        cell=rows['shares_end_outstanding']['cells'].get(pid,{})
        if actual(cell) and present('shares_end_outstanding',pid):
            if cell.get('value') is None or not math.isclose(cell['value'],amount,abs_tol=1e-8,rel_tol=0):raise ValueError('Historical closing shares conflict with a preserved source observation')
            continue
        rows['shares_end_outstanding']['cells'][pid]=dict(value=amount,status='reported',editable=False,required=False,
            source_refs=copy.deepcopy(item['source_refs']),data_role='reported_fact',reason='Separately disclosed closing shares outstanding, distinct from weighted-average EPS shares.')
    if actual(rows['shares_end_outstanding']['cells'].get(base_pid,{})):
        spec['gaps']=[g for g in spec['gaps'] if not g.startswith('Closing shares lack a distinct source at the base date')]
    for p in financial:
        pid=p['id'];a('buyback_price',p,finance.get('repurchase_price'),
            'Explicit execution price in reporting currency per share. Missing is permitted only while buyback cash is zero.',required=False)
        a('repurchase_elapsed_fraction',p,finance.get('repurchase_elapsed_fraction',0.5))
        a('issuance_shares',p,finance.get('issuance_shares',0)*frac(p));a('issuance_elapsed_fraction',p,finance.get('issuance_elapsed_fraction',0.5))
        a('issuance_price',p,finance.get('issuance_price'),required=False)
        f('issuance_cash',pid,'if_zero(issuance_shares, 0, issuance_shares * issuance_price)')
        cf=rows['cff']['cells'][pid]
        if ('issuance_cash',0) not in dependencies(expression_tree(cf['expression'])):
            cf['expression']='('+cf['expression']+') + issuance_cash'
        rows['buyback_price']['label']='Repurchase execution price';rows['buyback_price']['note']='No book-value fallback. Inactive missing price is allowed; positive buyback requires a positive execution price.'
        f('buyback_shares',pid,'if_zero(buyback_cash, 0, buyback_cash / buyback_price)')
        old=rows['shares_basic']['cells'][pid];opening=next((v for k,v in old.get('bindings',{}).items() if k.startswith('lag:')),None)
        if opening is None:
            prior=[q for q in periods if q['end']<p['start'] and q['kind'] in ('FY','H1','Q1','Q2','Q3','Q4') and present('shares_end_outstanding',q['id'])]
            prior=max(prior,key=lambda q:(q['end'],q['kind']=='FY')) if prior else pm[base_pid]
            opening=dict(row_id='shares_end_outstanding',period_id=prior['id'])
        else:
            candidate=dict(opening,row_id='shares_end_outstanding')
            aliases=[q for q in periods if q['end']==pm[candidate['period_id']]['end'] and present('shares_end_outstanding',q['id'])]
            if aliases:
                chosen=max(aliases,key=lambda q:(actual(rows['shares_end_outstanding']['cells'][q['id']]),q['kind']=='FY'))
                candidate['period_id']=chosen['id']
            weighted_aliases=[q for q in periods if q['end']==pm[candidate['period_id']]['end'] and
                actual(rows['shares_basic']['cells'].get(q['id'],{})) and present('shares_basic',q['id'])]
            if not present('shares_end_outstanding',candidate['period_id']) and weighted_aliases:
                proxy=max(weighted_aliases,key=lambda q:(q['kind']=='FY',q['kind']=='H1',q['duration_days']))
                f('shares_end_outstanding',candidate['period_id'],'weighted_proxy',{'weighted_proxy':dict(row_id='shares_basic',period_id=proxy['id'])},
                    reason='Unresolved closing share count at this date. Reported weighted-average shares are an explicit provisional proxy; earlier disclosed closing shares do not establish subsequent treasury or employee-plan movements.',status='estimated_historical',required=False)
                rows['shares_end_outstanding']['cells'][candidate['period_id']].update(data_role='estimated_historical_baseline',calibration_eligible=False)
                spec['gaps'].append('Closing shares at '+candidate['period_id']+' use a weighted-average proxy because intervening share movements and the closing count are undisclosed; an earlier reported closing count is preserved separately.')
            if present('shares_end_outstanding',candidate['period_id']):opening=candidate
        f('shares_basic',pid,'opening - buyback_shares * (1 - repurchase_elapsed_fraction) + issuance_shares * (1 - issuance_elapsed_fraction)',{'opening':opening})
        close_pid=py[p['fiscal_year'],'FY'] if p['kind']=='H2' else pid
        capital=rows['share_capital']['cells'][close_pid];capital['expression']='('+capital['expression']+') + issued_cash'
        capital.setdefault('bindings',{})['issued_cash']=dict(row_id='issuance_cash',period_id=pid)
        f('shares_end_outstanding',close_pid,'opening - bought + issued',{'opening':opening,'bought':dict(row_id='buyback_shares',period_id=pid),'issued':dict(row_id='issuance_shares',period_id=pid)})
    for year in forecast_years:
        aggregate('shares_basic',year,'weighted_average');aggregate('buyback_shares',year)
    # Financing is an explicit dated manual schedule, with within-period
    # borrowing/repayment interest; no cash floor or automatic debt plug.
    schedule=finance.get('schedule',{})
    rows['borrowing_input']['note']='Manual discretionary borrowing; separate refinancing and maturity inputs. Interest reflects the supplied within-period transaction timing.'
    rows['repayment_input']['note']='Manual discretionary repayment, separate from contractual maturities; cash, debt and time-weighted interest share one input.'
    rows['debt_interest']['note']='Opening non-lease debt plus within-period time-weighted borrowing and repayment, multiplied by the annual funding rate and fiscal duration.'
    valid_periods={p['id'] for p in financial}
    if set(schedule)-valid_periods:raise ValueError('Financing schedule must use authoritative financial periods: '+', '.join(sorted(set(schedule)-valid_periods)))
    for rid,label in [('maturity_input','Contractual non-lease debt maturities'),('refinancing_input','Refinancing borrowings'),
                      ('issuance_nominal_cash','Legal nominal capital issued'),('issuance_premium_cash','Share premium issued')]:
        make(rid,label,'financing',kind='assumption' if rid.endswith('_input') else 'calculated')
    for rid,label in [('borrowing_elapsed_fraction','Borrowing date: fraction of period elapsed'),('repayment_elapsed_fraction','Repayment date: fraction of period elapsed')]:
        make(rid,label,'financing','ratio','assumption','ratio')
    nominal=finance.get('issuance_nominal_price')
    if nominal is not None:make('issuance_nominal_price','Legal nominal value per issued share','financing',money+'/shares_m','assumption','ratio')
    else:
        rows['share_capital']['label']='Share capital / combined paid-in capital'
        rows['share_capital']['note']='Reported history retains its legal definition. Forecast issuance is combined paid-in capital until nominal value and premium are separately specified.'
    for p in financial:
        pid=p['id'];item=schedule.get(pid,{})
        for rid,key in [('borrowing_input','borrowing'),('repayment_input','repayment'),('maturity_input','maturities'),('refinancing_input','refinancing')]:
            current=rows[rid]['cells'][pid].get('value',0) if rid in ('borrowing_input','repayment_input') else 0
            a(rid,p,item.get(key,current),'Explicit period financing cash flow; missing schedule means the documented hold/zero policy, not verified absence of contractual maturities.')
        for rid in ('borrowing_elapsed_fraction','repayment_elapsed_fraction'):a(rid,p,item.get(rid,finance.get(rid,.5)))
        f('debt_borrow',pid,'borrowing_input + refinancing_input')
        f('debt_repay',pid,'-repayment_input - maturity_input')
        old=rows['debt_interest']['cells'][pid];opening=next(b for k,b in old['bindings'].items() if k.startswith('lag:'))
        f('debt_interest',pid,'(opening + debt_borrow * (1 - borrowing_elapsed_fraction) + debt_repay * (1 - repayment_elapsed_fraction)) * borrowing_rate * period_year_fraction',{'opening':opening},
          'Interest on opening debt plus time-weighted scheduled borrowing and repayment; manual financing, no automatic cash balancing.')
        if nominal is not None:
            a('issuance_nominal_price',p,nominal)
            f('issuance_nominal_cash',pid,'issuance_shares * issuance_nominal_price')
            f('issuance_premium_cash',pid,'issuance_cash - issuance_nominal_cash')
        else:
            f('issuance_nominal_cash',pid,'issuance_cash',reason='Combined paid-in capital because no nominal-value contract was supplied; not represented as legal nominal capital.')
            rows['issuance_premium_cash']['cells'][pid]=dict(value=0,status='forecast',editable=False)
        closing=py[p['fiscal_year'],'FY'] if p['kind']=='H2' else pid
        rows['share_capital']['cells'][closing]['bindings']['issued_cash']=dict(row_id='issuance_nominal_cash',period_id=pid)
        reserve=rows['reserves']['cells'][closing]
        reserve['expression']='('+reserve['expression']+') + issuance_premium'
        reserve.setdefault('bindings',{})['issuance_premium']=dict(row_id='issuance_premium_cash',period_id=pid)
    for year in forecast_years:
        for rid in ('debt_borrow','debt_repay','debt_interest','issuance_nominal_cash','issuance_premium_cash'):aggregate(rid,year)
    spec['policies']['financing']='Manual maturities, refinancing, discretionary borrowing/repayment and capital distributions. Interest includes the remaining period after each scheduled cash flow. Absent maturities are unresolved hold-policy inputs, not evidence of no maturity.'
    # Company-defined adjusted earnings bridge, including separate tax,
    # non-controlling and after-tax associate effects rather than UTOP/EPS.
    earnings=cfg.get('adjusted_earnings',{})
    basic_adjustment=earnings.get('basic_earnings_adjustment')
    eps_parent='parent_profit';adjusted_numerator='adjusted_parent_profit'
    if basic_adjustment is not None:
        if not basic_adjustment.get('source_refs') or not basic_adjustment.get('method'):
            raise ValueError('An EPS numerator adjustment requires company evidence and an explicit method')
        amounts=basic_adjustment.get('amounts_by_period',{})
        if set(amounts)-valid_periods:raise ValueError('EPS numerator adjustment must use authoritative financial periods')
        make('basic_earnings_adjustment','After-tax basic EPS numerator adjustment','income',kind='assumption',
             note=basic_adjustment['method']+' EPS attribution only; no duplicate cash flow or P&L expense.')
        make('basic_eps_numerator','Earnings attributable to ordinary shares','income')
        eps_parent='basic_eps_numerator';adjusted_numerator='(adjusted_parent_profit + basic_earnings_adjustment)'
        for p in financial:
            a('basic_earnings_adjustment',p,amounts.get(p['id'],basic_adjustment.get('annual_amount',0)*frac(p)))
            f('basic_eps_numerator',p['id'],'parent_profit + basic_earnings_adjustment')
            f('eps_basic',p['id'],'basic_eps_numerator / shares_basic')
        for year in forecast_years:
            aggregate('basic_earnings_adjustment',year);aggregate('basic_eps_numerator',year)
            f('eps_basic',py[year,'FY'],'basic_eps_numerator / shares_basic')
        for pid,item in basic_adjustment.get('historical',{}).items():
            if pid not in pm or not actual(rows['parent_profit']['cells'].get(pid,{})) or not item.get('source_refs'):
                raise ValueError('Historical EPS attribution needs an actual earnings period and cited adjustment')
            rows['basic_earnings_adjustment']['cells'][pid]=dict(value=item['amount'],status='reported',editable=False,required=False,
                source_refs=copy.deepcopy(item['source_refs']),data_role='reported_fact')
            f('basic_eps_numerator',pid,'parent_profit + basic_earnings_adjustment',status='derived_actual',required=False)
            existing=rows['eps_basic']['cells'].get(pid,{})
            if existing.get('status') not in ('actual','reported'):
                f('eps_basic',pid,'basic_eps_numerator / shares_basic',status='derived_actual',required=False)
    dilution=earnings.get('dilution',cfg.get('dilution',{}))
    make('incremental_diluted_shares','Incremental dilutive weighted shares','financing','shares_m','assumption','weighted_average',
         note=dilution.get('method','Explicit incremental-share scenario; no unreported dilution is asserted as fact.'))
    make('diluted_earnings_adjustment','After-tax diluted earnings adjustment','income',kind='assumption')
    make('shares_diluted','Diluted weighted-average shares','income','shares_m',metric_type='weighted_average')
    make('eps_diluted','Statutory diluted EPS','income',money+'/shares_m',metric_type='ratio')
    control_numerator=dilution.get('control_numerator_row',eps_parent)
    if control_numerator not in rows:raise ValueError('Unknown continuing-operations dilution control numerator: '+control_numerator)
    for rid,label,unit in [('dilution_control_basic_eps','Continuing-operations EPS before potential shares',money+'/shares_m'),
        ('dilution_control_candidate_eps','Continuing-operations EPS with potential shares',money+'/shares_m'),
        ('dilution_control_spread','Decrease in continuing-operations EPS from potential shares',money+'/shares_m'),
        ('eligible_diluted_shares','Potential weighted shares passing anti-dilution test','shares_m'),
        ('eligible_diluted_earnings_adjustment','Diluted earnings adjustment passing anti-dilution test',money)]:
        make(rid,label,'income',unit,metric_type='weighted_average' if rid=='eligible_diluted_shares' else 'ratio' if 'eps' in rid or rid.endswith('spread') else 'flow',support=True)
    def forecast_dilution(pid):
        f('dilution_control_basic_eps',pid,control_numerator+' / shares_basic')
        f('dilution_control_candidate_eps',pid,'('+control_numerator+' + diluted_earnings_adjustment) / (shares_basic + incremental_diluted_shares)')
        f('dilution_control_spread',pid,'dilution_control_basic_eps - dilution_control_candidate_eps')
        f('eligible_diluted_shares',pid,'if_positive(dilution_control_spread, incremental_diluted_shares, 0)')
        f('eligible_diluted_earnings_adjustment',pid,'if_positive(dilution_control_spread, diluted_earnings_adjustment, 0)')
        f('shares_diluted',pid,'shares_basic + eligible_diluted_shares')
        f('eps_diluted',pid,f'({eps_parent} + eligible_diluted_earnings_adjustment) / shares_diluted')
    for p in financial:
        a('incremental_diluted_shares',p,dilution.get('incremental_shares',max(0,(hv('shares_diluted') or hv('shares_basic'))-hv('shares_basic'))))
        a('diluted_earnings_adjustment',p,dilution.get('earnings_adjustment',0)*frac(p))
        forecast_dilution(p['id'])
    for year in forecast_years:
        # IAS33 eligibility is tested independently for the annual earnings
        # control number, not averaged from shares eligible in each half.
        aggregate('incremental_diluted_shares',year,'weighted_average');aggregate('diluted_earnings_adjustment',year)
        forecast_dilution(py[year,'FY'])
    historical_dilution=copy.deepcopy(dilution.get('historical',{}))
    for p in periods:
        pid=p['id'];eps=rows['eps_diluted']['cells'].get(pid,{})
        if pid in historical_dilution or eps.get('status') not in ('actual','reported') or present('shares_diluted',pid):continue
        if dilution.get('historical_missing_denominator_policy','carry_latest_cited_increment')!='carry_latest_cited_increment':continue
        previous=[(q,item) for q,item in historical_dilution.items() if q in pm and pm[q]['end']<p['start'] and item.get('source_refs') and item.get('status','reported') in ('actual','reported')]
        if previous:
            anchor,item=max(previous,key=lambda pair:pm[pair[0]]['end'])
            historical_dilution[pid]=dict(incremental_shares=item['incremental_shares'],earnings_adjustment=item['earnings_adjustment']*p['duration_days']/pm[anchor]['duration_days'],
                status='estimated',source_refs=copy.deepcopy(item['source_refs']),reason='Undisclosed diluted denominator: carry the latest cited potential-share increment from '+anchor+'. Independent estimate, never reverse-engineered from rounded EPS.')
    for pid,item in historical_dilution.items():
        if pid not in pm or not actual(rows['shares_basic']['cells'].get(pid,{})):raise ValueError('Historical dilution requires an actual basic-share period')
        if not item.get('source_refs'):raise ValueError('Historical dilution requires cited evidence, including for an estimated allocation')
        status=item.get('status','reported')
        if status not in ('actual','reported','estimated','estimate','estimated_historical'):raise ValueError('Unsupported historical dilution status')
        estimated=status not in ('actual','reported');status='estimated_historical' if estimated else 'reported'
        for rid,key in [('incremental_diluted_shares','incremental_shares'),('diluted_earnings_adjustment','earnings_adjustment')]:
            if key not in item:raise ValueError('Historical dilution must disclose both shares and earnings adjustment')
            rows[rid]['cells'][pid]=dict(value=item[key],status=status,editable=False,required=False,source_refs=copy.deepcopy(item['source_refs']),
                data_role='estimated_historical_baseline' if estimated else 'reported_fact',calibration_eligible=not estimated,reason=item.get('reason','Cited historical dilution bridge'))
        for rid,source in [('eligible_diluted_shares','incremental_diluted_shares'),('eligible_diluted_earnings_adjustment','diluted_earnings_adjustment')]:
            f(rid,pid,source,status='estimated_historical' if estimated else 'derived_actual',required=False)
            rows[rid]['cells'][pid].update(data_role='estimated_historical_baseline' if estimated else 'derived_fact',calibration_eligible=not estimated)
        from .construction import formula_value
        def historical_number(rid,target,seen=None):
            seen=set() if seen is None else set(seen)
            if (rid,target) in seen:return None
            seen.add((rid,target));cell=rows[rid]['cells'].get(target,{})
            if cell.get('value') is not None:return cell['value']
            if not cell.get('expression'):return None
            def resolve(symbol,lag):
                binding=cell.get('bindings',{}).get(f'lag:{symbol}:{lag}' if lag else symbol,dict(row_id=symbol,period_id=target))
                return historical_number(binding['row_id'],binding['period_id'],seen)
            return formula_value(expression_tree(cell['expression']),resolve)
        for rid,expression,tolerance in [('shares_diluted','shares_basic + incremental_diluted_shares',item.get('share_rounding_tolerance',1e-6)),
                                        ('eps_diluted',f'({eps_parent} + diluted_earnings_adjustment) / shares_diluted',item.get('eps_rounding_tolerance',.005))]:
            reported=[o for o in data.get('observations',[]) if o['row_id']==rid and o['period_id']==pid and o.get('status') in ('actual','reported') and o.get('eligible',True)]
            existing=rows[rid]['cells'].get(pid,{})
            if reported:
                chosen=reported[0]
                if any(not math.isclose(o['value'],chosen['value'],abs_tol=tolerance,rel_tol=0) for o in reported):raise ValueError('Conflicting preserved historical dilution observations: '+rid)
                existing=dict(value=chosen['value'],status='reported',editable=False,required=False,source_refs=copy.deepcopy(chosen.get('source_refs',[])),observation_id=chosen['id'],data_role='reported_fact')
            elif pm[pid]['kind']=='FY':
                source=history.get(rid,{})
                amount=source.get('values',{}).get(str(pm[pid]['fiscal_year']));refs=source.get('sources',{}).get(str(pm[pid]['fiscal_year']),[])
                if amount is not None and refs:existing=dict(value=amount,status='reported',editable=False,required=False,source_refs=copy.deepcopy(refs),data_role='reported_fact')
            expected=formula_value(expression_tree(expression),lambda symbol,lag:historical_number(symbol,pid))
            if actual(existing) and (existing.get('value') is not None or existing.get('expression')):
                observed=existing.get('value') if existing.get('value') is not None else historical_number(rid,pid)
                if expected is None or observed is None or not math.isclose(observed,expected,abs_tol=tolerance,rel_tol=0):raise ValueError('Historical dilution conflicts with a preserved reported '+rid)
                rows[rid]['cells'][pid]=existing
            else:
                f(rid,pid,expression,status='estimated_historical' if estimated else 'derived_actual',required=False)
                rows[rid]['cells'][pid].update(data_role='estimated_historical_baseline' if estimated else 'derived_fact',calibration_eligible=not estimated)
    spec['dilution_contract']=dict(control_numerator_row=control_numerator,
        historical_missing_denominator_policy=dilution.get('historical_missing_denominator_policy','carry_latest_cited_increment'),
        method='Single supported potential-share class or explicitly equivalent share-plan pool; include only when continuing-operations EPS falls. Apply independently to interim and annual periods.',
        limitations=['Different convertible/option classes require a separately sequenced instrument model; an aggregate mixed-instrument pool is not a claim of full IAS33 instrument modelling.',
            'When no separate continuing-operations control numerator is supplied, the ordinary-share earnings numerator is the explicit proxy.'])
    if earnings:
        bridges={k:[] for k in ('pretax','tax','associate','nci')}
        for adjustment in earnings.get('adjustments',[]):
            key='adjustment_'+adjustment['id'];basis=adjustment.get('basis','after_tax_associate' if adjustment.get('associate_after_tax') else 'pretax')
            if basis not in ('pretax','after_tax_associate','tax_only','nci_only'):raise ValueError('Unsupported adjusted-earnings adjustment basis')
            sign=adjustment.get('sign',1)
            if sign not in (-1,1):raise ValueError('Earnings adjustment sign must be -1 or 1')
            make(key,adjustment.get('label',adjustment['id']),'income',kind='calculated' if adjustment.get('source_row') else 'assumption',support=True)
            for p in financial:
                if adjustment.get('source_row'):
                    if adjustment['source_row'] not in rows:raise ValueError('Unknown earnings bridge source '+adjustment['source_row'])
                    f(key,p['id'],('-' if sign<0 else '')+adjustment['source_row'])
                else:a(key,p,sign*adjustment.get('annual_amount',0)*frac(p),'Explicit company-defined normalization estimate, not a reported adjustment.')
            category={'pretax':'pretax','after_tax_associate':'associate','tax_only':'tax','nci_only':'nci'}[basis]
            bridges[category].append(key)
            if basis in ('pretax','after_tax_associate'):
                for suffix in ('tax_rate','nci_share'):
                    make(key+'_'+suffix,adjustment.get('label',adjustment['id'])+' '+suffix.replace('_',' '),'income','ratio','assumption','ratio',support=True)
                    for p in financial:a(key+'_'+suffix,p,0 if basis=='after_tax_associate' and suffix=='tax_rate' else adjustment.get(suffix,0))
                make(key+'_tax','Adjustment tax effect','income',support=True);make(key+'_nci','Adjustment attributable to NCI','income',support=True)
                for p in financial:
                    f(key+'_tax',p['id'],f'-{key} * {key}_tax_rate')
                    f(key+'_nci',p['id'],f'({key} + {key}_tax) * {key}_nci_share')
                bridges['tax'].append(key+'_tax');bridges['nci'].append(key+'_nci')
        for category,source in [('pretax','pretax'),('tax','tax_expense'),('associate','associate_profit'),('nci','nci_profit')]:
            rid='adjusted_'+category;make(rid,earnings.get('label','Adjusted')+' '+category,'income')
            for p in financial:f(rid,p['id'],source+(' + '+' + '.join(bridges[category]) if bridges[category] else ''))
            for year in forecast_years:aggregate(rid,year)
        for rid,label,expr,unit in [('adjusted_total_profit','Adjusted total profit','adjusted_pretax + adjusted_tax + adjusted_associate',money),
             ('adjusted_parent_profit','Adjusted profit attributable to owners','adjusted_total_profit - adjusted_nci',money),
             ('adjusted_eps_basic','Adjusted basic EPS',adjusted_numerator+' / shares_basic',money+'/shares_m'),
             ('adjusted_eps_diluted','Adjusted diluted EPS','('+adjusted_numerator+' + eligible_diluted_earnings_adjustment) / shares_diluted',money+'/shares_m')]:
            make(rid,label,'income',unit,metric_type='ratio' if 'eps' in rid else 'flow')
            for p in financial:f(rid,p['id'],expr)
            for year in forecast_years:
                if 'eps' in rid:f(rid,py[year,'FY'],expr)
                else:aggregate(rid,year)
        historical_bridges={}
        for item in earnings.get('historical_adjustments',[]):
            pid=item['period_id'];basis=item['basis'];rid='historical_adjustment_'+item['id']
            if pid not in pm or not actual(rows['parent_profit']['cells'].get(pid,{})):raise ValueError('Historical earnings bridge requires an actual statutory earnings period')
            category={'pretax':'pretax','after_tax_associate':'associate','tax_only':'tax','nci_only':'nci'}.get(basis)
            if category is None:raise ValueError('Unsupported historical adjustment basis')
            if not item.get('source_refs'):raise ValueError('Historical adjustment requires explicit source provenance')
            make(rid,item.get('label',item['id']),'income',support=True)
            rows[rid]['cells'][pid]=dict(value=item['amount'],status=item.get('status','reported'),editable=False,required=False,
                source_refs=copy.deepcopy(item['source_refs']),data_role='reported_fact' if item.get('status','reported')=='reported' else 'estimated_historical_baseline')
            historical_bridges.setdefault(pid,{k:[] for k in ('pretax','tax','associate','nci')})[category].append(rid)
        for pid,bridge in historical_bridges.items():
            estimate=any(rows[r]['cells'][pid]['status']!='reported' for items in bridge.values() for r in items)
            status='estimated' if estimate else 'derived_actual'
            for category,source in [('pretax','pretax'),('tax','tax_expense'),('associate','associate_profit'),('nci','nci_profit')]:
                f('adjusted_'+category,pid,source+(' + '+' + '.join(bridge[category]) if bridge[category] else ''),status=status,required=False,
                  reason='Company-defined historical adjustment bridge from cited period-specific amounts; absence of a category means this supplied bridge has no adjustment in that category.')
            for rid,expr in [('adjusted_total_profit','adjusted_pretax + adjusted_tax + adjusted_associate'),
                ('adjusted_parent_profit','adjusted_total_profit - adjusted_nci'),('adjusted_eps_basic',adjusted_numerator+' / shares_basic')]:
                f(rid,pid,expr,status=status,required=False)
            if present('shares_diluted',pid):f('adjusted_eps_diluted',pid,'('+adjusted_numerator+' + eligible_diluted_earnings_adjustment) / shares_diluted',status=status,required=False)
        spec['adjusted_earnings_contract']=copy.deepcopy(earnings)
    # Writable policy and calculated effective ratio are distinct business IDs.
    ratio_contracts=[('effective_tax_rate','Tax-rate policy','-tax_expense / pretax'),
                     ('nci_profit_share','NCI attribution policy','if_zero(total_profit, 0, nci_profit / total_profit)'),
                     ('current_debt_share','Current-debt classification policy','if_zero(total_debt, 0, short_debt / total_debt)')]
    for rid,label,expression in ratio_contracts:
        policy=rid+'_policy';r=copy.deepcopy(rows[rid]);r.update(id=policy,label=label,kind='assumption')
        for cell in r['cells'].values():
            if actual(cell):continue
            for binding in cell.get('bindings',{}).values():
                if binding.get('row_id')==rid:binding['row_id']=policy
        if rid=='current_debt_share':
            r['note']='Closing-date debt classification policy. Annual classification uses the final financial-period policy, never an average of interim classifications.'
            for year in forecast_years:
                candidates=leaves(year);last=max(candidates,key=lambda p:p['end']);fy=py[year,'FY']
                if last['id']!=fy and not actual(r['cells'].get(fy,{})):
                    r['cells'][fy]=dict(expression='closing_policy',bindings={'closing_policy':dict(row_id=policy,period_id=last['id'])},
                        status='forecast',editable=False,required=True,reason=r['note'])
        rows[policy]=r;spec['rows'].append(r);rows[rid]['kind']='calculated';rows[rid]['note']='Calculated effective ratio from matching financial amounts; the separate policy input determines the forecast.'
        spec.setdefault('input_migrations',{})[rid]=policy
        for target in spec['rows']:
            if target['id'] in (rid,policy):continue
            for pid,cell in target['cells'].items():
                if actual(cell) or not cell.get('expression'):continue
                if (rid,0) in dependencies(expression_tree(cell['expression'])):
                    cell.setdefault('bindings',{})[rid]=dict(row_id=policy,period_id=pid)
        for p in periods:
            if p['fiscal_year'] not in forecast_years or actual(rows[rid]['cells'].get(p['id'],{})):continue
            if rid=='current_debt_share' and not present('short_debt',p['id']):continue
            if p in financial or p['kind']=='FY':f(rid,p['id'],expression)
    # FX accounting inputs are distinct. Asset/liability translation drives OCI;
    # cash-flow FX never masquerades as a translation-reserve plug.
    fx_policy=cfg.get('balance_sheet_fx',{})
    bs_roles=('inventories','receivables','trade_payables','owned_ppe','right_of_use_assets','intangibles','goodwill','nonlease_debt','lease_liabilities')
    for role in bs_roles:
        rid=role+'_translation_movement';make(rid,rows[role]['label']+' — FX translation movement','working_capital',kind='assumption',
            note='Separate closing-rate exposure scenario. Zero means unmodelled exposure, not complete FX accounting.',support=True)
        for p in financial:a(rid,p,fx_policy.get('annual_movements',{}).get(role,0)*frac(p))
    make('cash_translation_oci','OCI attributable to translated cash exposure','working_capital',kind='assumption',
        note='Independent attribution based on foreign cash exposure; not automatically equal to the cash-flow FX line.',support=True)
    make('oci_translation','OCI translation of explicit net-asset exposures','working_capital',note='Sum of declared asset less liability currency movements, independently of cash-flow FX.')
    reserves_note=('Opening reserves plus equity-settled compensation, issuance premium and explicitly modelled net-asset OCI translation or event reclassifications. '
                   'Cash-flow FX and financing remeasurement remain separate; undisclosed translation exposures are unmodelled.')
    rows['reserves']['note']=reserves_note
    make('financing_fx_remeasurement','Financing FX remeasurement charge / (gain)','financing',kind='assumption',
        note='Separate financing P&L effect, with the corresponding noncash debt movement.')
    for p in financial:
        pid=p['id'];a('cash_translation_oci',p,fx_policy.get('annual_cash_translation_oci',0)*frac(p))
        a('financing_fx_remeasurement',p,fx_policy.get('annual_financing_remeasurement',0)*frac(p))
        f('oci_translation',pid,'cash_translation_oci + inventories_translation_movement + receivables_translation_movement + owned_ppe_translation_movement + right_of_use_assets_translation_movement + intangibles_translation_movement + goodwill_translation_movement - trade_payables_translation_movement - nonlease_debt_translation_movement - lease_liabilities_translation_movement')
        for role in bs_roles:
            closing=py[p['fiscal_year'],'FY'] if p['kind']=='H2' else pid
            cell=rows[role]['cells'].get(closing)
            if cell and cell.get('expression') and not actual(cell):
                cell['expression']='('+cell['expression']+') + translation'
                cell.setdefault('bindings',{})['translation']=dict(row_id=role+'_translation_movement',period_id=pid)
        for cf,role,sign in [('wc_inventory_cf','inventories',1),('wc_receivables_cf','receivables',1),('wc_payables_cf','trade_payables',-1)]:
            cell=rows[cf]['cells'][pid];cell['expression']='('+cell['expression']+') '+('+' if sign==1 else '-')+' translation'
            cell.setdefault('bindings',{})['translation']=dict(row_id=role+'_translation_movement',period_id=pid)
        closing=py[p['fiscal_year'],'FY'] if p['kind']=='H2' else pid
        cell=rows['reserves']['cells'][closing]
        if cell.get('expression') and not actual(cell):
            cell['expression']=cell['expression'].replace('cash_fx','oci_translation')
            cell['reason']=reserves_note
            cell.setdefault('bindings',{}).pop('cash_fx',None)
            cell['bindings']['oci_translation']=dict(row_id='oci_translation',period_id=pid)
        # A debt remeasurement is noncash P&L, not new borrowing.
        fc=rows['financial_expense']['cells'][pid];fc['expression']='('+fc['expression']+') - financing_fx_remeasurement'
        debt=rows['nonlease_debt']['cells'][closing];debt['expression']='('+debt['expression']+') + remeasurement';debt['bindings']['remeasurement']=dict(row_id='financing_fx_remeasurement',period_id=pid)
        cfo=rows['cfo_fx_noncash']['cells'][pid];cfo['expression']='('+cfo['expression']+') + financing_fx_remeasurement'
    for year in forecast_years:
        aggregate('oci_translation',year)
        aggregate('cfo_portfolio_noncash',year);aggregate('cfo_fx_noncash',year)
        for role in bs_roles:aggregate(role+'_translation_movement',year)
    component_ids=['cf_net_profit','da','sbc','cf_associates','associate_dividends','cf_tax_timing','wc_cash']
    component_ids += [rid for rid in ('impairment','disposal_result_cf','other_noncash_ex_sbc',
        'other_operating_assets_liabilities_cf','cf_finance_timing') if rid in rows]
    component_ids += ['cfo_portfolio_noncash','cfo_fx_noncash']
    spec['cashflow_component_contract']=dict(cfo_components=component_ids,
        method='CFO equals the sum of named visible signed components; working-capital detail is counted through its subtotal once.')
    for p in financial:
        spec['identities'].append(dict(id='cfo_visible_components_'+p['id'],label='Visible cash-flow components reconcile to CFO',
            expression='cfo - ('+' + '.join(component_ids)+')',periods=[p['id']],tolerance=1e-6,independent=False))
    # Existing roll-forward checks gain the explicit noncash movements rather
    # than loosening their tolerances or forcing a balancing cash/reserve value.
    for identity in spec.get('identities',[]):
        name=identity.get('id','');pid=(identity.get('periods') or [None])[0]
        if not pid or pid not in pm or pm[pid]['fiscal_year'] not in forecast_years:continue
        if name.startswith('ppe_roll_'):identity['expression']+=' - owned_ppe_translation_movement'
        elif name.startswith('intangible_roll_'):identity['expression']+=' - intangibles_translation_movement'
        elif name.startswith('debt_roll_'):identity['expression']+=' - nonlease_debt_translation_movement - lease_liabilities_translation_movement - financing_fx_remeasurement'
    spec['financial_contracts']=dict(version=2,cost_pools=pools,drivers=contracts,
        authoritative_profit_build='Independent cash cost methods plus explicit embedded SBC and allocated D&A feed segment profit and the same group expense totals.',
        limitations=['Segment-by-function cash-cost baselines are source-reconciled allocations, not disclosed facts.',
                     'Foreign balance-sheet exposures remain incomplete unless explicit closing-rate movements are supplied; cash-flow FX and OCI are independent.'])
    # Full-year attribution is not available merely because its forecast portion
    # is modelled. In a mixed actual/forecast year, historical expense FX, OCI and
    # repurchase counts require their own disclosures. Preserve their absence,
    # while keeping every future-only financial/driver requirement strict.
    attribution_rows={'buyback_shares','group_cost_fx_amount','group_scope_da','operating_cogs_base','operating_sales_base','oci_translation',
                      'debt_interest','issuance_nominal_cash','issuance_premium_cash','diluted_earnings_adjustment','shares_diluted','eps_diluted',
                      'basic_earnings_adjustment','basic_eps_numerator','eps_basic'}
    attribution_rows.update(r for r in rows if r.startswith('adjusted_'))
    attribution_rows.update(r for r in rows if r.startswith(('dilution_control_','eligible_diluted_')))
    attribution_rows.add('incremental_diluted_shares')
    attribution_rows.update(role+'_translation_movement' for role in bs_roles)
    for entity,_,_ in entities:
        if entity!='corporate':attribution_rows.update(entity+suffix for suffix in ('_scope_da','_cost_fx','_cost_fx_amount','_cost_fx_base','_cost_fx_adjusted','_cost_fx_raw'))
        for pool in pools:attribution_rows.update(pool_rows[entity,pool['id']]+suffix for suffix in ('_pre_fx','_transaction_amount','_translation_amount'))
    absent_summaries={};financial_pids={p['id'] for p in financial}
    for _ in range(3):
        for rid in sorted(attribution_rows & rows.keys()):
            for pid,cell in rows[rid]['cells'].items():
                if pid in financial_pids or pm[pid]['fiscal_year'] not in forecast_years or not cell.get('expression'):continue
                gaps=[]
                for dep,n in dependencies(expression_tree(cell['expression'])):
                    binding=cell.get('bindings',{}).get(f'lag:{dep}:{n}' if n else dep,dict(row_id=dep,period_id=pid))
                    key=(binding['row_id'],binding['period_id'])
                    if key in absent_summaries:gaps.extend(absent_summaries[key])
                    elif actual(rows['utop']['cells'].get(binding['period_id'],{})) and not present(*key):gaps.append(dict(row_id=key[0],period_id=key[1]))
                if gaps:
                    unique=list({(g['row_id'],g['period_id']):g for g in gaps}.values())
                    absent_summaries[rid,pid]=unique;cell['required']=False
                    cell['reason']='Full-period attribution unavailable: historical companion observations were not disclosed. Forecast components remain calculated; no zero, current FX or invented execution price replaces historical evidence.'
                    cell['unavailable_historical_components']=unique
    spec['financial_contracts']['unavailable_historical_summaries']=[dict(row_id=r,period_id=p,missing_components=gaps) for (r,p),gaps in sorted(absent_summaries.items())]
    registered={c['id'] for c in contracts}
    dependents={};parsed_dependencies={}
    for target in spec['rows']:
        for cell in target['cells'].values():
            expr=cell.get('expression')
            if not expr:continue
            if expr not in parsed_dependencies:parsed_dependencies[expr]=dependencies(expression_tree(expr))
            for dep,lag in parsed_dependencies[expr]:
                binding=cell.get('bindings',{}).get(f'lag:{dep}:{lag}' if lag else dep,{})
                dependents.setdefault(binding.get('row_id',dep),set()).add(target['id'])
    obsolete=['corporate_cost_growth']+[e+suffix for e,_,_ in entities if e!='corporate' for suffix in ('_cash_cost_seed','_cash_cost_seasonality')]
    for rid in obsolete:
        if rid not in rows:continue
        rows[rid].update(kind='calculated',support_matrix=True,note='Legacy aggregate-cost diagnostic; independent functional pool controls are authoritative.')
        for pid,c in rows[rid]['cells'].items():
            if not actual(c):rows[rid]['cells'][pid]=missing()
    for r in spec['rows']:
        if r['kind'] not in ('assumption','driver') or r['id'] in registered:continue
        if not any(c.get('editable') and c.get('status') in ('forecast','estimate') for c in r['cells'].values()):continue
        if r.get('driver_contract'):
            contracts.append(copy.deepcopy(r['driver_contract']));continue
        outputs=sorted(dependents.get(r['id'],()))
        entity=next((e for e,_,_ in entities if r['id'].startswith(e+'_')),'group')
        role='allocation' if r['id'].endswith(('_share','_weight','_seasonality','_allocation')) or '_weight_' in r['id'] else 'economic_input'
        contract(r['id'],entity,None,role,outputs,timing=r.get('note','Explicit financial-period input'))
    for r in spec['rows']:
        if r['kind'] not in ('assumption','driver'):continue
        for pid,cell in r['cells'].items():
            if actual(cell) or not cell.get('editable'):continue
            anchors=sorted({b['period_id'] for b in cell.get('bindings',{}).values() if b.get('period_id') in pm and pm[b['period_id']]['fiscal_year']<=base})
            if not anchors:continue
            cell['initialization_anchor_periods']=anchors
            reason=cell.get('reason','')
            for phrase in ('Latest','latest','Last disclosed','last disclosed','Last reported','last reported'):
                reason=reason.replace(phrase,'Base full-year')
            cell['reason']=reason+' Initialization uses '+', '.join(anchors)+'; later interim disclosures are not automatically substituted.'
    spec['policies']['operating_costs']='One selected method per pool: effective activity sensitivity and unit costs, or an independent budget. Embedded SBC is removed from comparable cash bases and added once; pricing does not determine costs.'
    spec['policies']['dividends']='Explicit annual cash-dividend pool and independent payment schedule; no half-year earnings annualisation.'
    spec['policies']['equity']='Weighted share timing and separate cash-flow FX, debt remeasurement and net-asset OCI translation.'
    for role,policy in data.get('model_configuration',{}).get('functional_expense_structure',{}).items():
        row=rows[role];note=data['historical'][role]['note']
        row.update(data_role='structural_parameter',calibration_eligible=False,note=note,label=row['label']+' (included in other functions)')
        for p in periods:
            cell=row['cells'].get(p['id'],{})
            if cell.get('status')=='not_applicable':continue
            if p['fiscal_year']<=base or actual(rows['utop']['cells'].get(p['id'],{})):
                row['cells'][p['id']]=dict(value=0,status='estimated',editable=False,required=False,reason=note,
                    data_role='structural_parameter',calibration_eligible=False,classification_source_refs=copy.deepcopy(policy['source_refs']))
            else:cell.update(data_role='structural_parameter',calibration_eligible=False)
    spec['functional_expense_structure']=copy.deepcopy(data.get('model_configuration',{}).get('functional_expense_structure',{}))
    for policy in data.get('model_configuration',{}).get('structural_account_policies',[]):
        role=policy['role']
        targets=[role]+({'other_revenue':['other_revenue_ratio'],
            'net_other_trading':['net_other_trading_assumption'],
            'net_other_operating':['net_other_operating_assumption']}.get(role,[]))
        for target in targets:
            if target not in rows:continue
            row=rows[target];row.update(kind='calculated',data_role='structural_parameter',calibration_eligible=False)
            for pid,cell in row['cells'].items():
                if cell.get('status')=='not_applicable':continue
                row['cells'][pid]=dict(value=0,status='estimated' if pm[pid]['end']<=spec['model_configuration'].get('actual_through',pm[base_pid]['end']) else 'forecast',
                    editable=False,required=False,data_role='structural_parameter',calibration_eligible=False,
                    reason=data['historical'][role]['note'],classification_source_refs=copy.deepcopy(policy['source_refs']))
    spec['structural_account_policies']=copy.deepcopy(data.get('model_configuration',{}).get('structural_account_policies',[]))
    spec['gaps']=[g for g in spec.get('gaps',[]) if 'Cost inflation is a temporary proxy' not in g]
    spec['gaps']=[g.replace('Opening asset/debt convention delays capex depreciation and new borrowing interest to the next year.',
                 'Opening-asset depreciation delays new-capex depreciation; financing interest instead uses explicit within-period borrowing/repayment timing.') for g in spec['gaps']]
    spec['gaps']+=spec['financial_contracts']['limitations']
    return spec


def apply_cash_scope_contract(spec, data):
    """Preserve reported net cash while financing and valuation use gross debt.

    A separately controlled overdraft changes gross cash and debt together. It
    does not create another financing inflow in an already net cash statement.
    The default scenario holds that closing stock; edits occur at period end.
    """
    policy=cash_scope_policy(data)
    if policy is None:return spec
    periods=spec['periods'];pm={p['id']:p for p in periods};rows={r['id']:r for r in spec['rows']}
    py={(p['fiscal_year'],p['kind']):p['id'] for p in periods}
    frequency=spec['frequency_policy']['statements'];kinds=('H1','H2') if frequency=='half_year' else ('Q1','Q2','Q3','Q4')
    base_pid=py[max(data['history_years']),'FY'];money=spec['currency']+'m'
    debt_roles=[item['role'] for item in policy['components'] if item['included_in_debt']]
    def present(role,pid):
        cell=rows[role]['cells'].get(pid,{})
        return cell.get('value') is not None or bool(cell.get('expression'))
    def stock_period(p):return py[p['fiscal_year'],'FY'] if frequency=='half_year' and p['kind']=='H2' else p['id']
    def original(role,pid):return rows[role]['cells'].get(pid,{}).get('status') in ('actual','reported','derived_actual')
    def add(role,label,metric):
        row=dict(id=role,label=label,section='cashflow',unit=money,kind='calculated',metric_type=metric,
            note=policy['method'],cells={p['id']:dict(value=None,status='not_applicable',editable=False,required=False) for p in periods})
        rows[role]=row;spec['rows'].append(row);return row
    def formula(role,pid,expression,bindings,status='forecast'):
        rows[role]['cells'][pid]=dict(expression=expression,bindings=bindings,status=status,editable=False,
            reason='Cited cash-scope bridge. Netted debt is included once in gross cash and gross debt.',source_refs=copy.deepcopy(policy['source_refs']))
    add('cash_scope_netted_debt','Debt deducted within reported cash-flow cash','stock')
    add('cash_scope_debt_change','Change in debt netted within cash-flow cash','flow')
    add('valuation_cash','Gross cash in the valuation bridge','stock')
    add('valuation_cash_change','Change in gross valuation cash','flow')
    if not any(item['role']=='held_for_sale_cash' for item in policy['components']):
        # Replacing the cash-flow bridge does not replace independently reported
        # held-for-sale assets. Only the normalizer's absent internal bucket is
        # a structural zero; a disclosed HFS balance remains a historical fact.
        hfs=data.get('historical',{}).get('held_for_sale_cash',{})
        internal_hfs=(hfs.get('data_role')=='structural_parameter' and not hfs.get('sources')
            and not any(o.get('row_id')=='held_for_sale_cash' and o.get('eligible',True)
                        and o.get('value') is not None for o in data.get('observations',[])))
        control=rows['held_for_sale_cash_input']
        control.update(kind='calculated',support_matrix=True)
        for cell in control['cells'].values():
            cell['editable']=False
            if cell.get('status')!='not_applicable':
                cell['reason']='Hold the separately disclosed HFS cash balance; it is excluded from the configured cash-flow cash bridge.'
        for role in ('held_for_sale_cash','held_for_sale_cash_input') if internal_hfs else ():
            rows[role].update(kind='calculated',data_role='structural_parameter',calibration_eligible=False,support_matrix=True)
            for pid,cell in rows[role]['cells'].items():
                if cell.get('status')=='not_applicable':continue
                rows[role]['cells'][pid]=dict(value=0,status='forecast' if pm[pid]['fiscal_year'] in spec['forecast_years'] else 'estimated',
                    data_role='structural_parameter',calibration_eligible=False,editable=False,required=False,
                    reason='Inactive internal HFS cash bucket; the cited cash-scope policy replaces this bridge.',classification_source_refs=copy.deepcopy(policy['source_refs']))
    for p in periods:
        pid=p['id']
        if not present('closing_cash',pid):continue
        if all(present(role,pid) for role in debt_roles):
            expression=' + '.join(debt_roles) or '0 * closing_cash'
            formula('cash_scope_netted_debt',pid,expression,{r:dict(row_id=r,period_id=pid) for r in debt_roles} |
                ({} if debt_roles else {'closing_cash':dict(row_id='closing_cash',period_id=pid)}),
                'derived_actual' if original('closing_cash',pid) and all(original(r,pid) for r in debt_roles) else 'forecast')
            formula('valuation_cash',pid,'closing_cash + netted_debt',{
                'closing_cash':dict(row_id='closing_cash',period_id=pid),'netted_debt':dict(row_id='cash_scope_netted_debt',period_id=pid)},
                rows['cash_scope_netted_debt']['cells'][pid]['status'])
    leaves=[p for p in periods if p.get('annual_only') or p['kind'] in kinds]
    for p in leaves:
        pid=p['id'];closing=stock_period(p)
        if not present('cash_change',pid) or not present('cash_scope_netted_debt',closing):continue
        prior=[q for q in periods if q['end']<p['start'] and present('cash_scope_netted_debt',q['id'])]
        if not prior:
            if not debt_roles:
                formula('cash_scope_debt_change',pid,'0 * cash_change',{'cash_change':dict(row_id='cash_change',period_id=pid)},'derived_actual' if original('cash_change',pid) else 'forecast')
            else:continue
        else:
            previous=max(prior,key=lambda q:(q['end'],q['kind']=='FY'))['id']
            formula('cash_scope_debt_change',pid,'closing - opening',{
                'closing':dict(row_id='cash_scope_netted_debt',period_id=closing),
                'opening':dict(row_id='cash_scope_netted_debt',period_id=previous)},
                'derived_actual' if original('cash_change',pid) else 'forecast')
        formula('valuation_cash_change',pid,'cash_change + debt_change',{
            'cash_change':dict(row_id='cash_change',period_id=pid),'debt_change':dict(row_id='cash_scope_debt_change',period_id=pid)},
            'derived_actual' if original('cash_change',pid) else 'forecast')
        if not debt_roles or original('cash_change',pid):continue
        debt=rows['nonlease_debt']['cells'][closing]
        if debt.get('expression'):
            debt['expression']='('+debt['expression']+') + scope_debt_change'
            debt.setdefault('bindings',{})['scope_debt_change']=dict(row_id='cash_scope_debt_change',period_id=pid)
        # The sourced short-debt balance already includes the disclosed overdraft.
        # Allocate only the remaining debt using its historical maturity share.
        formula('current_debt_share',pid,'if_zero(total - netted, 0, (short - netted) / (total - netted))',{
            'total':dict(row_id='total_debt',period_id=base_pid),'short':dict(row_id='short_debt',period_id=base_pid),
            'netted':dict(row_id='cash_scope_netted_debt',period_id=base_pid)})
        rows['current_debt_share']['cells'][pid]['editable']=True
        formula('short_debt',closing,'(total - netted) * share + netted',{
            'total':dict(row_id='total_debt',period_id=closing),'netted':dict(row_id='cash_scope_netted_debt',period_id=closing),
            'share':dict(row_id='current_debt_share',period_id=pid)})
        for identity in spec['identities']:
            if identity['id'].startswith('debt_roll_') and pid in identity.get('periods',[]):
                identity['expression']+=' - cash_scope_debt_change'
                identity.setdefault('bindings',{})['cash_scope_debt_change']=dict(row_id='cash_scope_debt_change',period_id=pid)
    # Additive summaries include actual and forecast financial periods; stock
    # rows above always use the closing snapshot rather than sum balances.
    for p in periods:
        parts=[q for q in leaves if q['id']!=p['id'] and q['start']>=p['start'] and q['end']<=p['end']]
        for role in ('cash_scope_debt_change','valuation_cash_change'):
            if present(role,p['id']) or len(parts)<2 or not all(present(role,q['id']) for q in parts):continue
            if parts[0]['start']!=p['start'] or parts[-1]['end']!=p['end']:continue
            formula(role,p['id'],' + '.join('x'+str(i) for i in range(len(parts))),
                {'x'+str(i):dict(row_id=role,period_id=q['id']) for i,q in enumerate(parts)},
                'derived_actual' if all(original(role,q['id']) for q in parts) else 'forecast')
    spec['cash_scope_contract']=dict(policy,valuation_cash_role='valuation_cash',valuation_cash_change_role='valuation_cash_change',
        debt_policy='Netted debt is already within sourced total debt. Its closing change affects gross cash and debt once, outside the net CF financing subtotal.',
        availability_policy='Cash-flow scope does not establish cash accessibility. Review each cited component and treat restricted or unavailable cash as a separate valuation claim.',
        forecast_timing='Component changes occur at period end; next-period opening debt bears interest. Borrowing controls describe other borrowing.')
    return spec


def validate_financial_contracts(spec, values):
    """Check activation and economic contracts independently of graph equality."""
    if not spec.get('financial_contracts'):return []
    checks=[];rows={r['id']:r for r in spec['rows']}
    def value(r,p):return values.get(r,{}).get(p)
    for item in spec.get('cash_scope_contract',{}).get('components',[]):
        if not item.get('included_in_debt'):continue
        for p in spec['periods']:
            pid=p['id'];amount=value(item['role'],pid);short=value('short_debt',pid);debt=value('nonlease_debt',pid)
            if None not in (amount,short,debt):
                checks.append(check('cash_scope',item['role']+':'+pid,'PASS' if 0<=amount<=min(short,debt)+1e-6 else 'FAIL',
                    'Netted cash-scope borrowing must be a nonnegative component of current non-lease debt.'))
    for p in spec['periods']:
        pid=p['id'];cash=value('buyback_cash',pid);price=value('buyback_price',pid)
        if cash is not None and rows['buyback_cash']['cells'][pid].get('status')=='forecast':
            ok=cash>=0 and (cash==0 or price is not None and price>0)
            checks.append(check('financial_contract','repurchase_price:'+pid,'PASS' if ok else 'FAIL',
                'Zero repurchase cash permits missing price; active repurchases require a strictly positive currency-per-share execution price.'))
        for rid in ('repurchase_elapsed_fraction','issuance_elapsed_fraction','borrowing_elapsed_fraction','repayment_elapsed_fraction'):
            v=value(rid,pid)
            if v is not None:checks.append(check('financial_contract',rid+':'+pid,'PASS' if 0<=v<=1 else 'FAIL','Share transaction timing must fall within the period.'))
        issued=value('issuance_shares',pid);issue_price=value('issuance_price',pid)
        if issued is not None:
            checks.append(check('financial_contract','issuance_price:'+pid,'PASS' if issued>=0 and (issued==0 or issue_price is not None and issue_price>0) else 'FAIL',
                'Active share issuance requires a positive reporting-currency execution price and explicit timing.'))
            nominal=value('issuance_nominal_price',pid)
            if nominal is not None and issued>0:checks.append(check('financial_contract','issuance_nominal:'+pid,
                'PASS' if nominal>=0 and issue_price is not None and nominal<=issue_price else 'FAIL','Legal nominal capital cannot exceed total issuance proceeds.'))
        for rid in ('borrowing_input','repayment_input','maturity_input','refinancing_input','sbc_annual_budget','incremental_diluted_shares'):
            amount=value(rid,pid)
            if amount is not None:checks.append(check('financial_contract',rid+':'+pid,'PASS' if amount>=0 else 'FAIL','Amount must be nonnegative under the stated cash/sign convention.'))
        basic=value('eps_basic',pid);diluted=value('eps_diluted',pid)
        if basic is not None and diluted is not None and rows.get('eps_diluted',{}).get('cells',{}).get(pid,{}).get('status')=='forecast':
            spread=value('dilution_control_spread',pid);eligible=value('eligible_diluted_shares',pid)
            valid=spread is not None and eligible is not None and (eligible==0 or spread>0)
            checks.append(check('financial_contract','dilution:'+pid,'PASS' if valid else 'FAIL','Potential shares must reduce continuing-operations EPS; total/adjusted earnings may have a different sign.'))
        for r in spec['rows']:
            if r['id'].endswith('_variable_share'):
                v=value(r['id'],pid)
                if v is not None:checks.append(check('financial_contract',r['id']+':'+pid,'PASS' if 0<=v<=1 else 'FAIL','Variable expense share must be between zero and one.'))
            if r['id'].endswith('_effective_activity_sensitivity'):
                v=value(r['id'],pid)
                if v is not None:checks.append(check('financial_contract',r['id']+':'+pid,'PASS' if v>=0 else 'FAIL','Effective activity sensitivity must be nonnegative; it is one structural estimate, not duplicated elasticity and variable share.'))
        cashfx=value('cash_fx',pid);cashoci=value('cash_translation_oci',pid)
        allocation=value('active_da_allocation_total',pid);group_da=value('da',pid)
        if allocation is not None and group_da is not None:
            missing_allocation=abs(allocation)<1e-12 and abs(group_da)>1e-8
            checks.append(check('financial_contract','depreciation_allocation:'+pid,'FAIL' if missing_allocation else 'PASS',
                'Nonzero group D&A requires a supported remaining-business allocation; a zero allocation denominator leaves the model incomplete rather than inventing a recipient.'))
        if not spec.get('fx_accounting_contract') and cashfx is not None and cashoci is not None and abs(cashfx-cashoci)>1e-8:
            checks.append(check('financial_contract','cash_fx_attribution:'+pid,'FAIL',
                'Cash-flow currency movement and independently specified translated cash exposure differ; supply the missing exposure/reconciliation rather than using an equity plug.',cashfx-cashoci,1e-8))
    for contract in spec['financial_contracts'].get('drivers',[]):
        required=('definition','units','financial_basis','frequency','forecast_horizon','entity_id','currency_basis','timing','parameter_role','expected_downstream_outputs')
        good=all(k in contract for k in required)
        checks.append(check('financial_contract','driver:'+contract['id'],'PASS' if good else 'FAIL','Economic input, allocation and presentation roles carry explicit definition, timing and downstream contracts.'))
    for event in spec.get('scope_event_audit',[]):
        if event.get('material_unresolved'):
            checks.append(check('financial_contract','scope:'+event['id'],'WARNING',event.get('limitation','Material scope accounting inputs remain unresolved.')))
    unavailable=spec.get('financial_contracts',{}).get('unavailable_historical_summaries',[])
    if unavailable:
        checks.append(check('financial_contract','historical_attribution_coverage','WARNING',
            f'{len(unavailable)} mixed-period attribution summaries remain unavailable because their historical FX/OCI/share-count components are undisclosed. Future component calculations and statement totals remain required.'))
    from .fx import validate_fx_contracts
    checks.extend(validate_fx_contracts(spec,values))
    return checks


def segment_research_context(data, entity_id, periods=None):
    """Retrieve numerical predecessor history without creating consolidation rows.

    The same function can feed a financial reviewer or a later driver-research
    task. Roles distinguish usable consolidation facts from comparables/context;
    a bridge total is not an invented allocation to each successor.
    """
    versions=data.get('entity_versions',[])
    if isinstance(versions,dict):versions=list(versions.values())
    selected={v['id'] for v in versions if v['id']==entity_id or v.get('model_entity_id')==entity_id}
    if not selected:raise ValueError('Unknown company entity '+str(entity_id))
    connected=set(selected);bridges=[]
    for _ in range(len(versions)+1):
        changed=False
        for bridge in data.get('reporting_bridges',[]):
            def ids(side):
                return {x['entity_id'] if isinstance(x,dict) else x for x in bridge.get(side,[])}
            successors=ids('successors');predecessors=ids('predecessors')
            if successors & connected:
                if bridge not in bridges:bridges.append(bridge)
                new=predecessors-connected
                if new:connected.update(new);changed=True
        if not changed:break
    current=data.get('model_configuration',{}).get('current_reporting_basis')
    facts=[]
    for o in data.get('observations',[]):
        if o.get('entity_id') not in connected or periods is not None and o.get('period_id') not in periods:continue
        role='context_only'
        if o.get('eligible',True) and o.get('entity_id') in selected:
            if current and o.get('basis')==current:role='direct_consolidation'
            elif o.get('current_basis_compatible') or o.get('usage_role')=='like_for_like':role='like_for_like'
        facts.append(dict(o,research_use=role))
    return dict(entity=entity_id,entity_versions=[v for v in versions if v['id'] in connected],
        numerical_history=facts,reporting_bridges=bridges,
        rules='Only the selected period/basis view consolidates. Predecessors and bridge totals are context unless an exact published comparable or allocation is explicitly supported.')


def build_periodic_spec(data, forecast_years=5, fx_source=None):
    """Compile the same company roles into an explicit, acyclic period graph.

    Disclosures select entity versions and observation bases. This compiler never
    assigns a company to a geography, currency, calendar or source cell. Economic
    template overrides, opening allocation policies and calendars are input data.
    """
    from .periods import build_periods, derive_observations, calculate_periodic
    from .construction import expression_tree, dependencies
    from datetime import date
    from collections import Counter, defaultdict
    data=functional_structure_inputs(historical_eligibility_inputs(data))
    annual=build_integrated_spec(data,forecast_years)
    config=data.get('model_configuration',{})
    if not data.get('fiscal_calendar'):
        raise ValueError('A period model requires a sourced company fiscal calendar')
    frequency=config.get('statement_forecast_frequency',
        'half_year' if config.get('full_statement_frequency')=='half_year' else config.get('forecast_frequency','quarterly'))
    sales_frequency=config.get('primary_sales_frequency',config.get('forecast_frequency',frequency))
    mixed_frequency=frequency=='half_year' and sales_frequency=='quarterly'
    if frequency not in ('quarterly','half_year','annual'):
        raise ValueError('Supported forecast frequencies are quarterly, half_year and annual')
    leaf_kinds=('Q1','Q2','Q3','Q4') if frequency=='quarterly' else ('H1','H2') if frequency=='half_year' else ('FY',)
    years=annual['historical_years']+annual['forecast_years']
    periods=build_periods(years,data['fiscal_calendar'])
    as_of=config.get('as_of',config.get('actual_through'))
    current=next((p['fiscal_year'] for p in periods if p['kind']=='FY' and as_of and p['start']<=as_of<=p['end']),annual['forecast_years'][0])
    detail_years=config.get('detailed_forecast_years',2)
    if type(detail_years) is not int or detail_years<0:raise ValueError('Detailed forecast years must be a nonnegative integer')
    detail_through=current+detail_years-1
    annual_only={y for y in annual['forecast_years'] if y>detail_through or frequency=='annual'}
    periods=[p for p in periods if p['fiscal_year'] not in annual_only or p['kind']=='FY']
    for p in periods:
        if p['fiscal_year'] in annual_only:p.update(annual_only=True,components=[])
    pmap={p['id']:p for p in periods}
    for p in periods:
        p['status']='actual' if p['fiscal_year'] in annual['historical_years'] else 'forecast'
    by_year={(p['fiscal_year'],p['kind']):p['id'] for p in periods}
    base=max(annual['historical_years']); base_pid=by_year[base,'FY']
    actual_through=config.get('actual_through',pmap[base_pid]['end'])
    for p in periods:
        p['status']='actual' if p['end']<=actual_through else 'mixed' if p['start']<=actual_through else 'forecast'
    spec=copy.deepcopy(annual)
    spec.update(periods=periods,model_configuration=copy.deepcopy(config),
        forecast_horizon=dict(as_of=as_of,current_fiscal_year=current,detailed_forecast_years=detail_years,detailed_through=detail_through,annual_only_years=sorted(annual_only)),
        expanded_fiscal_years=[y for y in years if current-1<=y<=detail_through],
        entity_versions=copy.deepcopy(data.get('entity_versions',[])),
        reporting_bridges=copy.deepcopy(data.get('reporting_bridges',[])),
        identities=[],forecast_periods=[],observation_selection=[],derivation_checks=[],
        forecast_basis_note=data['forecast_basis'])
    spec['rows']=[r for r in spec['rows'] if r['id']!='forecast_basis_note']
    rows={r['id']:r for r in spec['rows']}
    segment_ids=[s['id'] for s in data['segments']]
    segment_prefixes=tuple(k+'_' for k in segment_ids)
    revenue_roles={'sales'} | {key+'_'+suffix for key in segment_ids for suffix in
        ('sales','pricing','rig','fx','organic','growth','pricing_effect','rig_effect','fx_effect','sales_seed','sales_seasonality')}
    revenue_roles.update(config.get('quarterly_disclosed_rows',[]))
    def is_revenue(r):return r['id'] in revenue_roles
    def row_leaves(r,p=None):
        if p and p.get('annual_only'):return ('FY',)
        return ('Q1','Q2','Q3','Q4') if mixed_frequency and is_revenue(r) else leaf_kinds
    def statement_leaf(p):return p.get('annual_only') or p['kind'] in leaf_kinds
    def applicable(r,p):
        if p['end']<=actual_through and config.get('full_statement_frequency',frequency)=='quarterly' and p['kind']!='H2':return True
        if frequency=='half_year' and p['kind'].startswith('Q') and not (mixed_frequency and is_revenue(r)):return False
        if frequency=='half_year' and p['kind']=='9M' and not is_revenue(r):return False
        if frequency=='half_year' and p['kind']=='H2' and r['metric_type']=='stock':return False
        return True
    # Type is a financial-role contract, not inferred by subtracting numbers.
    stocks={r['id'] for r in spec['rows'] if r['section']=='balance'} | {
        'owned_ppe','right_of_use_assets','lease_liabilities','nonlease_debt','total_debt',
        'net_debt','net_operating_working_capital','shares_end_outstanding',
        'closing_cash','cf_to_bs_cash','held_for_sale_cash','held_for_sale_cash_input'}
    stocks.update(r['id'] for r in spec['rows'] if r.get('metric_type')=='stock')
    # A balance-sheet residual is a closing-date control, never an additive flow.
    weighted={'shares_basic','shares_diluted'}
    ratios={r['id'] for r in spec['rows'] if r['unit']=='ratio' or '/shares_m' in r['unit']} | {'eps_basic'}
    overrides=config.get('row_overrides',{})
    for r in spec['rows']:
        r.update(copy.deepcopy(overrides.get(r['id'],{})))
        for suffix,label in config.get('driver_labels',{}).items():
            if r['section'].startswith('segment_') and r['id'].endswith('_'+suffix):r['label']=label
        r['metric_type']=r.get('metric_type',
            'stock' if r['id'] in stocks else 'weighted_average' if r['id'] in weighted else
            'ratio' if r['id'] in ratios else 'flow')
        r['cells']={}
    def missing(status='not_disclosed',reason=None):
        if reason is None:
            reason='No applicable input or control for this period' if status=='not_applicable' else 'No compatible disclosure for this metric and period'
        return dict(value=None,status=status,reason=reason,editable=False)
    def formula(expr,bindings=None,status='derived_actual',reason='',**extra):
        return dict(expression=expr,bindings=bindings or {},status=status,reason=reason,editable=False) | extra
    def bind(expr,pid,lag_pid=None):
        result={}
        for rid,n in dependencies(expression_tree(expr)):
            result[(f'lag:{rid}:{n}' if n else rid)]={
                'row_id':rid,'period_id':lag_pid if n else pid}
        return result
    def add_row(rid,label,section,unit='ratio',kind='calculated',metric_type='ratio',note=''):
        if rid in rows:return rows[rid]
        r=dict(id=rid,label=label,section=section,unit=unit,kind=kind,metric_type=metric_type,
            cells={},historical={},source_refs={},basis=data['forecast_basis'],note=note)
        spec['rows'].append(r);rows[rid]=r;return r
    # Calibration ingredients absent from the main annual presentation remain
    # explicit sourced support rows, rather than undocumented numeric constants.
    source_roles={**data['historical'],**data.get('schedule_controls',{})}
    ingredients=set()
    for r in list(spec['rows']):
        if r.get('initialization_expression'):
            ingredients.update(dep for dep,n in dependencies(expression_tree(r['initialization_expression'])))
    for allocation in data.get('schedule_anchor_policy',{}).get('assumptions',[]):
        ingredients.update(x['row_id'] for x in allocation.get('bindings',{}).values())
    for observation in data.get('observations',[]):
        if observation.get('expression') and observation.get('model_selection_eligible',True):
            ingredients.update(x['row_id'] for x in observation.get('bindings',{}).values())
    for rid in sorted(ingredients-set(rows)):
        source=source_roles.get(rid)
        examples=[o for o in data.get('observations',[]) if o['row_id']==rid]
        if source:
            unit=examples[0]['unit'] if examples else data['currency']+'m'
            metric_type=examples[0]['metric_type'] if examples else source.get('metric_type','flow')
            r=add_row(rid,rid.replace('_',' ').capitalize(),'working_capital',unit,'reported',metric_type,
                      'Reported calibration ingredient; not a second forecast schedule.')
            r.update(historical=copy.deepcopy(source.get('values',{})),source_refs=copy.deepcopy(source.get('sources',{})),basis=source.get('basis'),supporting_input=True)
        else:
            if examples:
                o=examples[0]
                add_row(rid,o.get('label',rid.replace('_',' ').capitalize()),'working_capital',o['unit'],'reported',o['metric_type'],
                        'Reported ingredient for an explicit forecast-opening allocation; original disclosure remains separate from the proxy.')['supporting_input']=True
    observations=copy.deepcopy(data.get('observations',[]))
    existing={(o['row_id'],o['period_id']) for o in observations if o.get('model_selection_eligible',True)}
    # Annual source roles remain useful when a normalized interim archive omits
    # ancillary schedule disclosures. Never copy a temporary initializer as fact.
    for r in spec['rows']:
        if r['kind']=='assumption':continue
        for year,value in r.get('historical',{}).items():
            if (int(year),'FY') not in by_year or value is None:continue
            pid=by_year[int(year),'FY']
            if (r['id'],pid) in existing:continue
            refs=r.get('source_refs',{}).get(str(year),[])
            if not refs:continue
            p=pmap[pid];basis=r.get('basis')
            if isinstance(basis,dict):basis=basis.get(str(year))
            is_segment=r['section'].startswith('segment_') or r['section']=='corporate' and r['id'].startswith('corporate_')
            intended=data.get('active_basis_by_period',{}).get(pid,{})
            if is_segment and int(year)==base and isinstance(intended,dict):basis=intended.get('segments',basis)
            if not basis and isinstance(intended,dict):basis=intended.get('group')
            if not basis:basis='annual_source_only_'+str(year)
            observations.append(dict(id='annual_'+r['id']+'_'+str(year),row_id=r['id'],metric=r['id'],
                entity_id='group',model_entity_id='group',period_id=pid,fiscal_year=int(year),
                kind='FY',start=p['start'],end=p['end'],metric_type=r['metric_type'],value=value,
                currency=data['currency'],unit=r['unit'],basis=basis,
                compatibility_key=(intended.get('segments' if is_segment else 'group',basis) if isinstance(intended,dict) else basis),scope='consolidated_group',
                definition=r['label'],definition_id=r['id'],restatement='original',status='actual',source_refs=refs,
                current_basis_compatible=is_segment and int(year)==base))
    derived=derive_observations(observations,periods)
    observations=derived['observations'];spec['observations']=observations
    spec['derivation_checks']=derived['checks']
    candidates=defaultdict(list)
    for o in observations:
        if o['row_id'] in rows and o['period_id'] in pmap:
            candidates[o['row_id'],o['period_id']].append(o)
    active=data.get('active_basis_by_period',{})
    def select(r,pid):
        choices=candidates.get((r['id'],pid),[])
        choices=[o for o in choices if o.get('status') not in ('unverified','conflict','excluded','vendor_unverified','primary_conflict')
                 and o.get('eligible',True) and o.get('model_selection_eligible',True)]
        if not choices:return None
        is_segment=r['section'].startswith('segment_') or r['section']=='corporate' and r['id'].startswith('corporate_')
        intended=active.get(pid,{})
        target=intended.get('segments' if is_segment else 'group') if isinstance(intended,dict) else intended
        if is_segment:
            target=config.get('current_reporting_basis',active.get(base_pid,{}).get('segments',target))
        matching=[o for o in choices if target in (o.get('basis'),o.get('compatibility_key'))] if target else []
        if matching:choices=matching
        elif is_segment:
            # Only an explicitly declared unchanged identity may bridge vintages.
            choices=[o for o in choices if o.get('current_basis_compatible') or o.get('usage_role')=='like_for_like']
            if not choices:return None
        elif target:
            return None
        actuals=[o for o in choices if o.get('status') in ('actual','reported','derived_actual')]
        if actuals:choices=actuals
        direct=[o for o in choices if o.get('status') in ('actual','reported')]
        if direct:choices=direct
        choices.sort(key=lambda o:(o.get('status')=='derived_actual',o.get('restatement')!='restated',o['id']))
        chosen=choices[0]
        disagreements=[o for o in choices if not math.isclose(o['value'],chosen['value'],rel_tol=1e-9,abs_tol=1e-6)]
        if disagreements:
            raise ValueError(f'Ambiguous observation selection {r["id"]}:{pid}; supply an exact preferred_observation_ids mapping')
        return chosen
    preferred=config.get('preferred_observation_ids',{})
    obs_by_id={o['id']:o for o in observations}
    def validate_observation(r,p,o):
        unit=o.get('unit')
        if unit==data['currency']+'_per_share':unit=data['currency']+'m/shares_m'
        if unit!=r['unit']:
            raise ValueError('Observation unit disagrees with model row: '+o['id']+' '+str(unit)+' versus '+r['unit'])
        if o.get('start')!=p['start'] or o.get('end')!=p['end']:
            raise ValueError('Observation dates disagree with fiscal period: '+o['id'])
        expected='stock' if r['id']=='opening_cash' else r['metric_type']
        aliases={'balance':'stock','additive_flow':'flow'}
        actual=aliases.get(o.get('metric_type'),o.get('metric_type'))
        if actual!=expected:
            raise ValueError('Observation metric type disagrees with model row '+r['id']+': '+o['id']+' '+str(actual)+' versus '+expected)
        if unit==data['currency']+'m' and o.get('currency')!=data['currency']:
            raise ValueError('Observation reporting currency disagrees with model row: '+o['id'])
    for r in spec['rows']:
        for p in periods:
            pid=p['id'];preferred_id=preferred.get(r['id']+':'+pid)
            if not applicable(r,p):
                r['cells'][pid]=missing('not_applicable','Company disclosure/model policy excludes this metric at this frequency')
                continue
            chosen=select(r,pid) if preferred_id is None else obs_by_id.get(preferred_id)
            if preferred_id is not None:
                if chosen is None or chosen.get('row_id')!=r['id'] or chosen.get('period_id')!=pid:
                    raise ValueError('Preferred observation must match the exact row and fiscal period: '+str(preferred_id))
                if (not chosen.get('eligible',True) or not chosen.get('model_selection_eligible',True)
                        or chosen.get('status') not in ('actual','reported','derived_actual','estimate','forecast')):
                    raise ValueError('Preferred observation is ineligible: '+str(preferred_id))
                if chosen.get('start')!=p['start'] or chosen.get('end')!=p['end'] or chosen.get('unit')!=r['unit']:
                    raise ValueError('Preferred observation dates or units disagree: '+str(preferred_id))
                is_segment=r['section'].startswith('segment_') or r['section']=='corporate' and r['id'].startswith('corporate_')
                intended=active.get(pid,{})
                target=config.get('current_reporting_basis',active.get(base_pid,{}).get('segments')) if is_segment else intended.get('group') if isinstance(intended,dict) else intended
                if target not in (chosen.get('basis'),chosen.get('compatibility_key')) and not (is_segment and chosen.get('current_basis_compatible')):
                    raise ValueError('Preferred observation is not on the selected reporting basis: '+str(preferred_id))
            if chosen:
                validate_observation(r,p,chosen)
                status=chosen.get('status','actual')
                if status=='reported':status='actual'
                if status not in ('actual','derived_actual','estimate','forecast'):
                    raise ValueError('Unsupported model observation status '+status)
                c=dict(value=chosen['value'],status=status,editable=False,source_refs=chosen.get('source_refs',[]),
                    observation_id=chosen['id'],basis=chosen.get('basis'),reason=chosen.get('reason','Reported original or published restatement'))
                if chosen.get('expression') and chosen.get('bindings'):
                    # Only expose graph derivations whose exact input observations
                    # are the selected model cells. Otherwise retain the sourced
                    # observation in its own basis, with provenance in Sources.
                    c['derivation']=dict(expression=chosen['expression'],bindings=chosen['bindings'],
                                         input_observation_ids=chosen.get('input_observation_ids',[]))
                r['cells'][pid]=c
                spec['observation_selection'].append(dict(row_id=r['id'],period_id=pid,observation_id=chosen['id']))
            else:
                is_segment=r['section'].startswith('segment_')
                status='not_comparable' if is_segment and p['fiscal_year']<base else 'not_disclosed'
                if r['kind']=='assumption' and not r.get('initialization_expression') and not is_segment:status='not_applicable'
                reason={'not_comparable':'No supported current-basis mapping; see Historical Segments and Reporting Bridges',
                    'not_applicable':'Forecast-only control has no reported historical equivalent',
                    'not_disclosed':'Not disclosed for this period'}
                r['cells'][pid]=missing(status,reason.get(status,'Unresolved source or calculation error'))
    for r in spec['rows']:
        for year,item in r.get('estimated_historical',{}).items():
            pid=by_year[int(year),'FY']
            r['cells'][pid]=dict(value=item['amount'],status='estimated_historical',editable=False,required=False,
                data_role='estimated_historical_baseline',calibration_eligible=False,reason=item['method'],
                allocation_source_refs=copy.deepcopy(item['source_refs']))
    spec['historical_allocations']=copy.deepcopy(config.get('historical_allocations',[]))
    before=Counter(c['status'] for r in spec['rows'] for c in r['cells'].values())
    # Promote exact period arithmetic to live formulas when its source cells match.
    for r in spec['rows']:
        for pid,c in r['cells'].items():
            deriv=c.get('derivation')
            if not deriv:continue
            inputs=[obs_by_id[i] for i in deriv['input_observation_ids']]
            def selected_equivalent(o):
                selected_id=rows.get(o['row_id'],{}).get('cells',{}).get(o['period_id'],{}).get('observation_id')
                if selected_id==o['id']:return True
                selected=obs_by_id.get(selected_id,{})
                fields=('currency','unit','scope','compatibility_key')
                return (selected.get('value')==o.get('value') and o.get('compatibility_key') is not None
                    and all(selected.get(k)==o.get(k) for k in fields)
                    and selected.get('definition_id',selected.get('definition'))==o.get('definition_id',o.get('definition')))
            if all(selected_equivalent(o) for o in inputs):
                c.pop('value',None);c.update(expression=deriv['expression'],bindings=deriv['bindings'])
    # Declarative historical equations are evaluated only when all components are
    # present on a compatible selected view. Do not use forecast policy equations.
    history_equations={r['id']:r['historical_expression'] for r in spec['rows'] if r.get('historical_expression')}
    history_equations.update(total_revenue='sales + other_revenue',gross_profit='sales + cogs',
        is_utop='utop',cf_net_profit='total_profit',net_other_trading='other_trading_income + other_trading_expense',
        net_other_operating='other_operating_income + other_operating_expense',
        other_current_assets='current_assets - cash - short_investments - inventories - receivables',
        other_noncurrent_assets='noncurrent_assets - ppe - goodwill - intangibles - associates',
        other_current_liabilities='current_liabilities - short_debt - trade_payables',
        other_noncurrent_liabilities='noncurrent_liabilities - long_debt',
        reserves='parent_equity - share_capital - treasury_stock - retained_earnings',
        held_for_sale_cash='closing_cash - cash',
        total_debt='short_debt + long_debt',
        corporate_cash_cost='-corporate_utop - corporate_da',eps_basic='parent_profit / shares_basic')
    cash_scope=cash_scope_policy(data)
    if cash_scope is not None:
        history_equations.pop('held_for_sale_cash',None)
        for target in cash_scope['components']:
            expression='closing_cash - cash'+''.join(
                (' - ' if item['coefficient']==1 else ' + ')+item['role'] for item in cash_scope['components'] if item['role']!=target['role'])
            history_equations[target['role']]=expression if target['coefficient']==1 else '-('+expression+')'
    # Supporting source roles are named economic concepts, never fixed source cells.
    for role in {dep for expr in history_equations.values() for dep,n in dependencies(expression_tree(expr)) if not n}:
        if role not in rows:
            source_matches=[o for o in observations if o['row_id']==role]
            if not source_matches:continue
            r=add_row(role,source_matches[0].get('label',role.replace('_',' ')),'working_capital',source_matches[0]['unit'],metric_type=source_matches[0]['metric_type'])
            for p in periods:
                candidates[role,p['id']]=[o for o in source_matches if o['period_id']==p['id']]
                o=select(r,p['id'])
                if o:
                    validate_observation(r,p,o)
                    r['cells'][p['id']]=dict(value=o['value'],status=o['status'],editable=False,source_refs=o.get('source_refs',[]),observation_id=o['id'])
                else:r['cells'][p['id']]=missing()
    for key in segment_ids:
        history_equations.update({key+'_cash_cost':f'{key}_sales - {key}_utop - {key}_da',
            key+'_ebitda':f'{key}_utop + {key}_da',key+'_margin':f'{key}_utop / {key}_sales'})
    # Closing-date aliases use stocks only. Profit and cash flows are never aliased.
    def available(rid,pid):
        c=rows.get(rid,{}).get('cells',{}).get(pid,{})
        return c.get('value') is not None or bool(c.get('expression'))
    def known_number(rid,pid,seen=None):
        from .construction import formula_value
        seen=set() if seen is None else set(seen)
        if (rid,pid) in seen:return None
        seen.add((rid,pid));c=rows.get(rid,{}).get('cells',{}).get(pid,{})
        if c.get('value') is not None:return c['value']
        if not c.get('expression'):return None
        def resolve(symbol,n):
            bnd=c.get('bindings',{}).get(f'lag:{symbol}:{n}' if n else symbol)
            if bnd:return known_number(bnd['row_id'],bnd['period_id'],seen)
            target=by_year.get((pmap[pid]['fiscal_year']-n,'FY')) if n else pid
            return known_number(symbol,target,seen) if target else None
        return formula_value(expression_tree(c['expression']),resolve)
    def inactive_ratio(expr,bindings,pid):
        import ast
        from .construction import formula_value
        tree=expression_tree(expr)
        if not isinstance(tree,ast.BinOp) or not isinstance(tree.op,ast.Div):return False
        def resolve(symbol,n):
            target=bindings.get(f'lag:{symbol}:{n}' if n else symbol,dict(row_id=symbol,period_id=pid))
            return known_number(target['row_id'],target['period_id'])
        return formula_value(tree.left,resolve)==0 and formula_value(tree.right,resolve)==0
    def historical_pass():
        changed=False
        for p in periods:
            pid=p['id']
            for rid,expr in history_equations.items():
                if rid not in rows:continue
                current=rows[rid]['cells'][pid]
                if not applicable(rows[rid],p):continue
                if available(rid,pid) and not (current.get('observation_id','').startswith('annual_') and rows[rid].get('historical_expression')):continue
                deps=dependencies(expression_tree(expr))
                if all(not n and available(dep,pid) for dep,n in deps):
                    if inactive_ratio(expr,{},pid):
                        rows[rid]['cells'][pid]=missing('not_applicable','Undefined historical 0/0 ratio; no observed ratio is asserted')
                        continue
                    estimated=any(rows[dep]['cells'][pid].get('status') in ('estimate','estimated','estimated_historical','forecast') for dep,n in deps)
                    status='estimated_historical' if estimated and p['end']<=actual_through else 'estimate' if estimated else 'derived_actual'
                    rows[rid]['cells'][pid]=formula(expr,status=status,reason='Calculated from selected components; any allocation estimate remains an estimate.')
                    if estimated:rows[rid]['cells'][pid].update(data_role='estimated_historical_baseline',calibration_eligible=False)
                    changed=True
            for r in spec['rows']:
                if r['metric_type']!='stock' or not applicable(r,p) or available(r['id'],pid):continue
                matching=[q['id'] for q in periods if q['id']!=pid and q['end']==p['end'] and available(r['id'],q['id'])]
                if matching:
                    source_status=r['cells'][matching[0]].get('status')
                    r['cells'][pid]=formula('closing',{'closing':dict(row_id=r['id'],period_id=matching[0])},
                        status='estimate' if source_status in ('estimate','forecast') else 'derived_actual',reason='Same closing date; stock alias, never a subtraction')
                    changed=True
        return changed
    for _ in range(len(rows)):
        if not historical_pass():break
    for p in periods:
        if not applicable(rows['opening_cash'],p) or p['end']>actual_through or available('opening_cash',p['id']):continue
        prior=[q for q in periods if date.fromisoformat(q['end']).toordinal()+1==date.fromisoformat(p['start']).toordinal()
               and available('closing_cash',q['id'])]
        if prior:
            q=max(prior,key=lambda q:q['duration_days'])
            rows['opening_cash']['cells'][p['id']]=formula('opening',{'opening':dict(row_id='closing_cash',period_id=q['id'])},
                reason='Opening cash equals the immediately preceding reported closing cash on the same cash-flow scope; source scope bridges remain separate.')
    # Explicit company-reviewed provisional allocations live in Assumptions. The
    # historical source row stays N/D; only forecast opening balances use proxies.
    proxy_lookup={}
    policy=data.get('schedule_anchor_policy',{})
    allocations=policy.get('assumptions',[]) if isinstance(policy,dict) else policy
    for item in allocations:
        pid=item.get('period_id',policy.get('period_id'));rid=item['row_id']
        aid='opening_proxy_'+rid
        ar=add_row(aid,'Opening allocation: '+rows[rid]['label'],'shared',rows[rid]['unit'],'assumption',rows[rid]['metric_type'],item['reason'])
        ar['cells']={p['id']:missing('not_applicable') for p in periods}
        c=copy.deepcopy(item);c.pop('row_id',None);c.pop('period_id',None)
        c.update(status='estimate',editable=True)
        ar['cells'][pid]=c;proxy_lookup[rid,pid]=aid
        for q in periods:
            if q['end']==pmap[pid]['end']:proxy_lookup[rid,q['id']]=aid
    for (rid,pid),aid in list(proxy_lookup.items()):
        if rid!='lease_liabilities' or not available('total_debt',pid):continue
        nid='opening_proxy_nonlease_debt'
        if nid not in rows:
            ar=add_row(nid,'Opening allocation: non-lease debt','shared',data['currency']+'m','assumption','stock',
                'Reported total financial debt less the explicitly provisional lease allocation; no extra debt is invented.')
            ar['cells']={p['id']:missing('not_applicable') for p in periods}
        anchor=next(k for k,c in rows[aid]['cells'].items() if c.get('expression') or c.get('value') is not None)
        rows[nid]['cells'][pid]=formula('total - leases',{'total':dict(row_id='total_debt',period_id=pid),
            'leases':dict(row_id=aid,period_id=anchor)},'estimate',rows[nid]['note'],editable=True)
        proxy_lookup['nonlease_debt',pid]=nid
    # Recompute historical diagnostics. Ratio assumptions are observed ratios only
    # when their ingredients exist; temporary policies never become history.
    for r in list(spec['rows']):
        expr=r.get('initialization_expression')
        if r['kind']!='assumption' or not expr:continue
        for p in periods:
            pid=p['id']
            if not applicable(r,p) or p['end']>actual_through or available(r['id'],pid):continue
            depmap={};okay=True
            for dep,n in dependencies(expression_tree(expr)):
                dp=by_year.get((p['fiscal_year']-n,'FY')) if n else pid
                if dp is None or not available(dep,dp):okay=False;break
                depmap[f'lag:{dep}:{n}' if n else dep]=dict(row_id=dep,period_id=dp)
            if okay:
                inactive=inactive_ratio(expr,depmap,pid)
                display_expr=expr
                reason='Historical ratio calculated from observed components; no assumption backfill'
                if r['id'] in ('inventory_ratio','receivables_ratio','payables_ratio'):
                    display_expr='('+expr+') * period_year_fraction'
                    depmap['period_year_fraction']=dict(row_id='period_year_fraction',period_id=pid)
                    reason+='; period flows annualized using explicit fiscal duration to match the annual denominator convention'
                r['cells'][pid]=missing('not_applicable','Undefined historical 0/0 ratio; forecast zero is a separate inactive policy') if inactive else formula(display_expr,depmap,reason=reason)
    # Every projection is built from chronological leaf periods; aggregates later
    # refer to these leaves or a disclosed actual block, never an independent year.
    leaves=sorted([p for p in periods if (p.get('annual_only') or p['kind'] in (('Q1','Q2','Q3','Q4','H1','H2') if mixed_frequency else leaf_kinds)) and p['fiscal_year']>base],key=lambda p:p['start'])
    future_leaves=[p for p in leaves if p['end']>actual_through]
    def available_or_planned(rid,pid):
        """Bind a forecast aggregate independently of construction order.

        FY totals are assembled after the underlying periods. Their temporary
        lack of a cell during this pass must not reset the next year's operating
        base to the last historical year. Undisclosed completed periods still
        require the explicitly labelled annual-seasonality fallback.
        """
        if available(rid,pid):return True
        if pid not in pmap:return False
        p=pmap[pid]
        return any(q['fiscal_year']==p['fiscal_year'] and q['start']>=p['start'] and q['end']<=p['end']
                   and q['kind'] in row_leaves(rows[rid],q) for q in future_leaves)
    spec['forecast_periods']=[p['id'] for p in future_leaves]
    yearfrac=add_row('period_year_fraction','Period duration / fiscal year','shared',kind='assumption',note='Explicit time fraction for annual rates; not applied to year-on-year pricing or activity growth.')
    for p in periods:
        fy=pmap[by_year[p['fiscal_year'],'FY']]
        yearfrac['cells'][p['id']]=dict(value=p['duration_days']/fy['duration_days'],status='actual',editable=False,
                                      data_role='structural_parameter',calibration_eligible=False)
    # Weighted shares are time averages, not additive flows. An H2 average can be
    # reconstructed from compatible full-year and H1 share-days; EPS then uses H2
    # parent earnings / H2 weighted shares. Published EPS is never subtracted.
    for p in periods:
        if p['kind']!='H2' or p['end']>actual_through or available('shares_basic',p['id']):continue
        fy=by_year[p['fiscal_year'],'FY'];h1=by_year[p['fiscal_year'],'H1']
        if not available('shares_basic',fy) or not available('shares_basic',h1):continue
        fyobs=obs_by_id.get(rows['shares_basic']['cells'][fy].get('observation_id'),{})
        h1obs=obs_by_id.get(rows['shares_basic']['cells'][h1].get('observation_id'),{})
        if not fyobs.get('compatibility_key') or fyobs.get('compatibility_key')!=h1obs.get('compatibility_key'):continue
        rows['shares_basic']['cells'][p['id']]=formula('(fy * fy_time - h1 * h1_time) / h2_time',{
            'fy':dict(row_id='shares_basic',period_id=fy),'h1':dict(row_id='shares_basic',period_id=h1),
            'fy_time':dict(row_id='period_year_fraction',period_id=fy),
            'h1_time':dict(row_id='period_year_fraction',period_id=h1),
            'h2_time':dict(row_id='period_year_fraction',period_id=p['id'])},
            reason='Exact time-weighted share-day reconstruction from compatible FY and H1 averages; subject to publication rounding.')
    for _ in range(len(rows)):
        if not historical_pass():break
    # Opening shares default to a labelled weighted-average proxy only when a
    # company specification explicitly authorizes it through schedule_anchor_policy.
    def opening_target(rid,prev):
        proxy=proxy_lookup.get((rid,prev))
        if proxy:
            anchor=next(k for k,c in rows[proxy]['cells'].items() if c.get('expression') or c.get('value') is not None)
            return dict(row_id=proxy,period_id=anchor)
        return dict(row_id=rid,period_id=prev)
    def default_cell(r,p):
        rid=r['id'];pid=p['id'];y=p['fiscal_year']
        prev_candidates=[q for q in periods if q['end']<p['start'] and q['kind'] in (*leaf_kinds,'FY','H1','H2')]
        prev=max(prev_candidates,key=lambda q:q['end'])['id']
        # Select the latest same-date alias with actual stock disclosure if needed.
        same_end=[q['id'] for q in periods if q['end']==pmap[prev]['end']]
        for alias in same_end:
            if available('cash',alias):prev=alias;break
        expr=r.get('expression')
        if not expr:return missing('not_applicable','Supporting reported control; no forecast policy applies')
        bindings={}
        for dep,n in dependencies(expression_tree(expr)):
            if n:
                bindings[f'lag:{dep}:{n}']=opening_target(dep,prev)
            else:bindings[dep]=dict(row_id=dep,period_id=pid)
        c=formula(expr,bindings,'forecast',r.get('note',''))
        return c
    # Period-specific seed assumptions preserve undisclosed quarter costs as an
    # explicit forecast proxy. No synthetic quarter is inserted into history.
    for seg in data['segments']:
        key=seg['id']
        cost_fx=add_row(key+'_cost_fx',seg['label']+' cost FX contribution','segment_'+key,kind='assumption',
            note='Neutral manual cost translation contribution; revenue FX does not establish purchasing-currency exposure.')
        cost_fx['cells']={p['id']:missing('not_applicable') for p in periods}
        for metric in ('sales','cash_cost'):
            sid=key+'_'+metric+'_seasonality'
            sr=add_row(sid,seg['label']+' '+('sales' if metric=='sales' else 'cost')+' seasonality','segment_'+key,
                kind='assumption',note='Editable period weight. Calibrated to published same-basis sales where available; cost allocation is a temporary proxy, not historical quarter profit.')
            sr['cells']={p['id']:missing('not_applicable') for p in periods}
            seed=add_row(key+'_'+metric+'_seed','Prior-year '+metric.replace('_',' ')+' for forecast','segment_'+key,
                data['currency']+'m','assumption','flow',note='Direct comparable prior-period value where disclosed; otherwise explicit annual-base seasonality estimate.')
            seed['cells']={p['id']:missing('not_applicable') for p in periods}
    for role in ('dividends_parent','dividends_nci'):
        sr=add_row(role+'_seasonality',rows[role]['label']+' — payment seasonality','financing',kind='assumption',
            note='Editable temporary payment timing calibrated from last completed FY and H1/H2 paid distributions. Quarter allocation within a disclosed half-year uses its duration; no quarter payment is claimed as a reported fact.')
        sr['cells']={p['id']:missing('not_applicable') for p in periods}
    # Forecast scalar controls are editable only at the underlying frequency.
    # Formula controls calibrate against historical cells on Assumptions, with no
    # dependency on the result in the forecast period that they determine.
    annual_rows={r['id']:r for r in annual['rows']}
    for p in future_leaves:
        pid=p['id'];year=p['fiscal_year'];prior=by_year.get((year-1,p['kind']))
        disclosed={r['id']:copy.deepcopy(r['cells'][pid]) for r in spec['rows']
            if r['cells'].get(pid,{}).get('status') in ('actual','reported','derived_actual')
            and available(r['id'],pid)}
        for r in list(spec['rows']):
            rid=r['id']
            if rid not in annual_rows or p['kind'] not in row_leaves(r,p):continue
            ar=annual_rows[rid] | copy.deepcopy(overrides.get(rid,{}))
            if ar['kind']=='assumption':
                expr=ar.get('initialization_expression')
                if expr:
                    bindings=bind(expr,base_pid,by_year.get((base-1,'FY')))
                    if inactive_ratio(expr,bindings,base_pid):
                        c=dict(value=0,status='forecast',editable=True,reason='Explicit inactive policy: both disclosed calibration numerator and denominator are zero; no historical 0/0 ratio is claimed.')
                    else:
                        c=formula(expr,bindings,'forecast',ar.get('initialization',''));c['editable']=True
                else:
                    c=dict(value=ar['inputs'][str(year)],status='forecast',editable=True,reason=ar.get('initialization',''))
                    held_growth_ids={s['id']+'_'+suffix for s in data['segments'] for suffix in ('pricing','rig','organic')}
                    if rid in held_growth_ids and rid not in overrides and available(rid,base_pid):
                        c['initialization_anchor_periods']=[base_pid]
                # Monetary flow policies are annual amounts allocated explicitly
                # by period duration. Stock assumptions and prices are not divided.
                if ar['unit']==data['currency']+'m' and rid not in stocks:
                    if c.get('expression'):c['expression']='('+expr+') * period_year_fraction';c['bindings']['period_year_fraction']=dict(row_id='period_year_fraction',period_id=pid)
                    else:c['value']*=yearfrac['cells'][pid]['value']
                    c['reason']+=' Annual amount allocated by explicit period duration.'
                r['cells'][pid]=c
            else:r['cells'][pid]=default_cell(r,p)
        # Economic template overrides are data, not company branches in code.
        for seg in data['segments']:
            key=seg['id']
            if statement_leaf(p):rows[key+'_cost_fx']['cells'][pid]=dict(value=0,status='forecast',editable=True,
                reason='Neutral manual contribution; no measured purchasing exposure is claimed.')
            for metric in ('sales','cash_cost'):
                if p['kind'] not in row_leaves(rows[key+'_'+metric],p):continue
                season=rows[key+'_'+metric+'_seasonality'];seed=rows[key+'_'+metric+'_seed']
                denominator=base_pid
                prior_base=by_year.get((year-1,'FY'))
                if prior and available_or_planned(key+'_sales',prior) and available_or_planned(key+'_sales',prior_base):
                    season['cells'][pid]=formula('if_zero(whole, 0, part / whole)',{'part':dict(row_id=key+'_sales',period_id=prior),
                        'whole':dict(row_id=key+'_sales',period_id=prior_base)},'forecast','Observed prior-period sales weight; cost use is an explicit proxy')
                else:
                    season['cells'][pid]=dict(value=yearfrac['cells'][pid]['value'],status='forecast',
                        reason='TEMPORARY calendar-day seasonality; no published comparable quarter allocation')
                season['cells'][pid]['editable']=True
                target=key+'_'+metric
                if prior and available_or_planned(target,prior):
                    seed['cells'][pid]=formula('observed',{'observed':dict(row_id=target,period_id=prior)},'forecast','Comparable previous-year period')
                else:
                    if not available_or_planned(target,prior_base):prior_base=base_pid
                    seed['cells'][pid]=formula('annual * seasonality',{
                        'annual':dict(row_id=target,period_id=prior_base),
                        'seasonality':dict(row_id=season['id'],period_id=pid)},'forecast','Explicit allocation proxy; undisclosed historical period remains N/D')
                seed['cells'][pid]['editable']=True
            if p['kind'] in row_leaves(rows[key+'_sales'],p):rows[key+'_sales']['cells'][pid]=formula(f'{key}_sales_seed * (1 + {key}_organic + {key}_fx)',status='forecast',reason='Company-defined organic growth applied to the same prior-year period; no division by four')
            if statement_leaf(p):rows[key+'_cash_cost']['cells'][pid]=formula(f'{key}_cash_cost_seed * (1 + {key}_rig + {key}_cost_fx) * (1 + {key}_cost_inflation)',status='forecast')
            for suffix,driver in (('pricing_effect','pricing'),('rig_effect','rig'),('fx_effect','fx')):
                if p['kind'] not in row_leaves(rows[key+'_sales'],p):continue
                if driver=='pricing' and config.get('revenue_models',{}).get(key,{}).get('method')=='aggregate_organic':driver='organic'
                rows[key+'_'+suffix]['cells'][pid]=formula(f'{key}_sales_seed * {key}_{driver}',status='forecast')
        if statement_leaf(p):
            for role,payout,profit in (('dividends_parent','dividend_payout','parent_profit'),('dividends_nci','nci_dividend_payout','nci_profit')):
                half='H1' if p['kind'] in ('Q1','Q2','H1') else 'H2'
                hp=by_year.get((base,half));sr=rows[role+'_seasonality']
                if p.get('annual_only'):
                    sr['cells'][pid]=dict(value=1,status='forecast',editable=True,reason='Annual-only dividend payment schedule covers the full fiscal year.')
                elif hp and available(role,hp) and known_number(role,base_pid) not in (None,0):
                    sr['cells'][pid]=formula('half_paid / annual_paid * part_duration / half_duration',{
                        'half_paid':dict(row_id=role,period_id=hp),'annual_paid':dict(row_id=role,period_id=base_pid),
                        'part_duration':dict(row_id='period_year_fraction',period_id=pid),
                        'half_duration':dict(row_id='period_year_fraction',period_id=by_year[year,half])},
                        'forecast','Temporary payment schedule from disclosed prior-year half-year cash distributions; within-half timing allocated by duration.',editable=True)
                else:
                    sr['cells'][pid]=dict(value=yearfrac['cells'][pid]['value'],status='forecast',editable=True,
                        reason='TEMPORARY even payment timing by period duration; no usable nonzero historical distribution schedule.')
                rows[role]['cells'][pid]=formula(f'-{profit} * {payout} * {role}_seasonality / period_year_fraction',status='forecast',
                    reason='Annualized current-period earnings times annual payout policy and explicit payment-seasonality weight. Current-year reported distributions are preserved.')
            # Annual rates apply to opening balances for the actual leaf duration.
            for rid in ('owned_ppe_depreciation','rou_depreciation','amortization','debt_interest','lease_interest','cash_interest','associate_profit'):
                c=rows[rid]['cells'][pid];c['expression']='('+c['expression']+') * period_year_fraction'
                c['bindings']['period_year_fraction']=dict(row_id='period_year_fraction',period_id=pid)
            for rid in ('inventories','receivables','trade_payables'):
                c=rows[rid]['cells'][pid];c['expression']='('+c['expression']+') / period_year_fraction'
                c['bindings']['period_year_fraction']=dict(row_id='period_year_fraction',period_id=pid)
                c['reason']='Temporary working-capital convention: annualize current-period sales/COGS using actual fiscal duration, then apply the observed annual balance ratio.'
            # Corporate cash cost is an annual operating policy, not quarter-on-quarter
            # compounding of an annual growth rate.
            rows['corporate_cash_cost']['cells'][pid]=formula('annual * period_year_fraction * (1 + corporate_cost_growth)',
                {'annual':dict(row_id='corporate_cash_cost',period_id=by_year[year-1,'FY'])},'forecast')
            # Preserve cash-flow opening/closing scope independently of BS cash.
            for rid in ('held_for_sale_cash_input',):
                c=rows[rid]['cells'][pid]
                prev_actual=[q for q in periods if q['end']<=actual_through and available('held_for_sale_cash',q['id'])]
                if prev_actual:
                    q=max(prev_actual,key=lambda q:q['end'])
                    rows[rid]['cells'][pid]=formula('anchor',{'anchor':dict(row_id='held_for_sale_cash',period_id=q['id'])},'forecast','Hold most recent disclosed CF/BS cash scope bridge',editable=True)
        p['status']='forecast'
        # Disclosure coverage belongs to individual concepts, not a global date.
        # Retain reported sales/drivers while leaving unreported profits estimated.
        for rid,cell in disclosed.items():rows[rid]['cells'][pid]=cell
    # Half-year closing stocks are calculated at the FY end date. H2 contains
    # flows; its balance-sheet display and graph contain no duplicate snapshots.
    # Redirect dependencies before any numerical evaluation of the graph.
    if frequency=='half_year':
        for r in spec['rows']:
            if r['metric_type']=='stock':
                for year in annual['forecast_years']:
                    if year in annual_only:continue
                    h2=by_year[year,'H2'];fy=by_year[year,'FY']
                    if available(r['id'],h2):r['cells'][fy]=r['cells'][h2]
                    r['cells'][h2]=missing('not_applicable','Closing snapshot is shown at FY; H2 is a flow period')
        for r in spec['rows']:
            for pid,cell in r['cells'].items():
                if not cell.get('expression'):continue
                for dep,n in dependencies(expression_tree(cell['expression'])):
                    symbol=f'lag:{dep}:{n}' if n else dep
                    binding=cell.setdefault('bindings',{}).get(symbol,dict(row_id=dep,period_id=pid))
                    target=rows.get(binding['row_id']);period=pmap.get(binding['period_id'])
                    if target and target['metric_type']=='stock' and period and period['kind']=='H2':
                        cell['bindings'][symbol]=dict(row_id=target['id'],period_id=by_year[period['fiscal_year'],'FY'])
    spec['frequency_policy']=dict(statements=frequency,sales=sales_frequency,detailed_through=detail_through,annual_only_years=sorted(annual_only),
        stock_periods=['H1','FY'] if frequency=='half_year' else ['Q1','Q2','Q3','Q4','H1','FY'],
        note='Unsupported periods are inapplicable in the compiled graph, not hidden forecast calculations.')
    # Actual blocks win. Aggregation uses the largest disclosed compatible block
    # first, so H1 actual profit plus Q3/Q4 forecast never invents Q1/Q2 profit.
    def cover(r,p):
        if not applicable(r,p):return []
        candidates=[]
        for q in periods:
            if q['fiscal_year']!=p['fiscal_year'] or q['id']==p['id']:continue
            if p['start']<=q['start'] and q['end']<=p['end'] and available(r['id'],q['id']):candidates.append(q)
        current=date.fromisoformat(p['start']);end=date.fromisoformat(p['end']);chosen=[]
        from datetime import timedelta
        while current<=end:
            opts=[q for q in candidates if q['start']==current.isoformat()]
            if not opts:return []
            q=max(opts,key=lambda q:q['end']);chosen.append(q['id']);current=date.fromisoformat(q['end'])+timedelta(days=1)
        return chosen
    # Summary ratio definitions exclude published growth decompositions. Those
    # are weighted by prior-period sales, not differences of cumulative rates.
    ratio_equations={r['id']:r['expression'] for r in spec['rows'] if r['metric_type']=='ratio' and r.get('expression') and r['kind']!='assumption'}
    sales_growth_rows={key+suffix for key in segment_ids for suffix in ('_pricing','_rig','_fx','_organic','_growth')}
    for _ in range(8):
        changed=False
        for p in periods:
            pid=p['id']
            if p['end']<=actual_through:continue
            for r in spec['rows']:
                rid=r['id']
                if not applicable(r,p) or p['kind'] in row_leaves(r,p):continue
                if available(rid,pid):continue
                if r['metric_type']=='stock':
                    opts=[q for q in periods if q['end']==p['end'] and q['id']!=pid and available(rid,q['id'])]
                    if opts:r['cells'][pid]=formula('closing',{'closing':dict(row_id=rid,period_id=opts[0]['id'])},'forecast','Closing stock, not sum of balances');changed=True
                    continue
                if rid=='opening_cash':
                    parts=cover(r,p)
                    if parts:
                        r['cells'][pid]=formula('opening',{'opening':dict(row_id=rid,period_id=parts[0])},'forecast','Opening balance of first component period');changed=True
                    continue
                expr=ratio_equations.get(rid)
                if expr and all(not n and available(dep,pid) for dep,n in dependencies(expression_tree(expr))):
                    r['cells'][pid]=formula(expr,status='forecast',reason='Recomputed from period components');changed=True;continue
                parts=cover(r,p)
                if not parts:continue
                bindings={f'x{i}':dict(row_id=rid,period_id=part) for i,part in enumerate(parts)}
                if r['metric_type']=='flow' or rid.endswith('_seasonality'):
                    expr=' + '.join(bindings)
                elif r['metric_type']=='weighted_average':
                    for i,part in enumerate(parts):bindings[f'w{i}']=dict(row_id='period_year_fraction',period_id=part)
                    bindings['duration']=dict(row_id='period_year_fraction',period_id=pid)
                    expr='('+' + '.join(f'x{i} * w{i}' for i in range(len(parts)))+') / duration'
                elif rid in sales_growth_rows:
                    key=next((k for k in segment_ids if rid.startswith(k+'_')),None)
                    if not key:continue
                    prior_parts=[by_year.get((pmap[part]['fiscal_year']-1,pmap[part]['kind'])) for part in parts]
                    if not all(q and available(key+'_sales',q) for q in prior_parts):continue
                    for i,q in enumerate(prior_parts):bindings[f'w{i}']=dict(row_id=key+'_sales',period_id=q)
                    # Keep the lazy zero guard on short references. Expanding
                    # weighted arithmetic inside it duplicates missing/error
                    # checks enough to exceed Excel's formula length limit.
                    numerator=add_row(rid+'_weighted_amount',r['label']+' weighted monetary contribution',r['section'],
                        unit=rows[key+'_sales']['unit'],metric_type='flow')
                    denominator=add_row(rid+'_comparable_revenue',r['label']+' comparable revenue denominator',r['section'],
                        unit=rows[key+'_sales']['unit'],metric_type='flow')
                    for support in (numerator,denominator):
                        support['layout']='assumption_support';support['assumption_support']=True
                    numerator['cells'][pid]=formula(' + '.join(f'x{i} * w{i}' for i in range(len(parts))),bindings,'forecast',
                        'Growth contribution weighted by compatible prior-period revenue; read-only aggregation support.')
                    denominator['cells'][pid]=formula(' + '.join(f'w{i}' for i in range(len(parts))),bindings,'forecast',
                        'Comparable prior-period revenue; zero for a fully exited business.')
                    bindings={'amount':dict(row_id=numerator['id'],period_id=pid),
                              'base':dict(row_id=denominator['id'],period_id=pid)}
                    expr='if_zero(base, 0, amount / base)'
                else:
                    # Driver summaries are duration-weighted displays, never a
                    # second set of editable assumptions or annual forecast inputs.
                    for i,part in enumerate(parts):bindings[f'w{i}']=dict(row_id='period_year_fraction',period_id=part)
                    bindings['duration']=dict(row_id='period_year_fraction',period_id=pid)
                    expr='('+' + '.join(f'x{i} * w{i}' for i in range(len(parts)))+') / duration'
                r['cells'][pid]=formula(expr,bindings,'forecast','Aggregation of actual blocks and/or forecast periods');changed=True
        if not changed:break
    # Identity checks run at the calculation frequency; annual/half-year totals
    # have additional live aggregate checks. A by-construction balance is labelled.
    valid_ids=set(rows)
    for item in annual['identities']:
        if item['id'].endswith('_history'):continue
        expr=item['expression']
        if any(dep not in valid_ids for dep,n in dependencies(expression_tree(expr))):continue
        for p in future_leaves:
            pid=p['id'];bindings={}
            required_rows=[rows[dep] for dep,n in dependencies(expression_tree(expr))]
            if any(not applicable(r,p) for r in required_rows):
                if p['kind']!='H2' or any(not applicable(r,p) and r['metric_type']!='stock' for r in required_rows):continue
            for dep,n in dependencies(expression_tree(expr)):
                if n:
                    cell_pid=by_year[p['fiscal_year'],'FY'] if frequency=='half_year' and p['kind']=='H2' and rows[dep]['metric_type']=='stock' else pid
                    c=rows[dep]['cells'][cell_pid]
                    target=c.get('bindings',{}).get(f'lag:{dep}:{n}')
                    if target is None:
                        prior=[q for q in periods if q['end']<p['start'] and available(dep,q['id'])]
                        target=opening_target(dep,max(prior,key=lambda q:q['end'])['id']) if prior else None
                    bindings[f'lag:{dep}:{n}']=target
            if frequency=='half_year' and p['kind']=='H2':
                for dep,n in dependencies(expression_tree(expr)):
                    if not n and rows[dep]['metric_type']=='stock':bindings[dep]=dict(row_id=dep,period_id=by_year[p['fiscal_year'],'FY'])
            if item['id'].endswith('_sales_bridge'):
                key=item['id'][:-13]
                if p['kind'] not in row_leaves(rows[key+'_sales'],p):continue
                if rows[key+'_sales']['cells'][pid].get('status') in ('actual','reported','derived_actual'):continue
                bindings[f'lag:{key}_sales:1']=dict(row_id=key+'_sales_seed',period_id=pid)
            spec['identities'].append(dict(item,id=item['id']+'_'+pid,periods=[pid],bindings=bindings,tolerance=1e-6,independent=False))
    for item in annual['identities']:
        if not item['id'].endswith('_history'):continue
        deps=dependencies(expression_tree(item['expression']))
        if any(n for dep,n in deps):continue
        for p in periods:
            if p['end']>actual_through:continue
            if all(available(dep,p['id']) for dep,n in deps):
                spec['identities'].append(dict(item,id=item['id']+'_'+p['id'],periods=[p['id']],
                    independent=all(rows[dep]['cells'][p['id']].get('status')=='actual' and not rows[dep]['cells'][p['id']].get('expression') for dep,n in deps),
                    scope='Independent reported components where present; derived periods are arithmetic controls of those observations.'))
    # Editable company-configured formula cells override template policies without
    # requiring a source-code branch. They remain subject to the same graph gates.
    for rid,period_cells in config.get('cell_overrides',{}).items():
        if rid not in rows:raise ValueError('Unknown company policy row '+rid)
        for pid,cell in period_cells.items():
            if pid not in pmap:raise ValueError('Unknown company policy period '+pid)
            rows[rid]['cells'][pid]=copy.deepcopy(cell)
    if fx_source is not None and fx_source.get('schema')=='shared_fx_snapshot_v1':
        from .fx import attach_company_fx
        attach_company_fx(spec,data,fx_source)
        rows={r['id']:r for r in spec['rows']}
    elif fx_source is not None:
        from .fx import fx_for_period
        spec['sections'].insert(0,dict(id='fx',label='Foreign exchange rates and translation interfaces'))
        spec['fx_observations']=[];spec['fx_source']=copy.deepcopy(fx_source['source']);spec['fx_metadata']=copy.deepcopy(fx_source['metadata'])
        currency_list=config.get('fx_currencies',list(config.get('fx_exposure_weights',{})))
        fxrows=[]
        for currency in currency_list:
            if currency==data['currency']:continue
            rid='fx_average_'+currency.lower()
            r=add_row(rid,data['currency']+' per '+currency+' — period average','fx','exchange_rate',metric_type='ratio',note='Source status is retained; rates alone do not establish company exposure.')
            r['assumption_support']=True
            fxrows.append(r)
            for p in periods:
                result=fx_for_period(fx_source,data['currency'],currency,p['start'],p['end'])
                spec['fx_observations'].append(dict(result,row_id=rid,period_id=p['id']))
                r['cells'][p['id']]=dict(value=result.get('value'),status=result['status'] if result['status']!='missing' else 'not_disclosed',
                    reason='; '.join(result.get('qualifications',[])),source_refs=result.get('provenance',[]),editable=False)
            average=add_row('fx_assumed_average_'+currency.lower(),data['currency']+' per '+currency+' — future average input',
                'fx','exchange_rate','assumption','ratio',note='Reserved future rate input. Source estimates initialize covered periods only; no future rate is invented and no company exposure is inferred.')
            closing=add_row('fx_assumed_closing_'+currency.lower(),data['currency']+' per '+currency+' — closing-rate input',
                'fx','exchange_rate','assumption','ratio',note='Separate closing rate, intentionally missing. An average rate is never a closing-rate proxy.')
            for p in periods:
                pid=p['id'];future=p['end']>actual_through
                average['cells'][pid]=missing('not_applicable')
                closing['cells'][pid]=missing('not_applicable')
                if future:
                    source=r['cells'][pid]
                    average['cells'][pid]=formula('source_estimate',{'source_estimate':dict(row_id=rid,period_id=pid)},'estimate',
                        'Source-labelled estimate, available for an explicit future exposure mapping.',editable=True,required=False) if source.get('value') is not None else dict(value=None,status='not_disclosed',editable=True,required=False,reason='No supplied future average rate; enter a supported assumption before enabling currency translation.')
                    closing['cells'][pid]=dict(value=None,status='not_disclosed',editable=True,required=False,reason='No supplied closing rate; separate supported input required for balance translation.')
            fxrows.extend((average,closing))
        spec['rows']=fxrows+[r for r in spec['rows'] if r not in fxrows]
        spec['fx_interfaces']=dict(reporting_currency=data['currency'],rates='fx_average_<currency>',
            revenue_translation='segment *_fx contributions',cost_translation='segment *_cost_fx contributions',
            future_average_inputs='fx_assumed_average_<currency>',closing_rate_inputs='fx_assumed_closing_<currency>',
            balance_translation='Requires separate closing-rate inputs and evidenced asset/liability currency exposure',
            cash_translation='cash_fx_assumption',exposure_weights={},closing_rates={},
            warning='No quantified exposure inferred from geography; reported-currency historical amounts are not translated again.')
    apply_financial_contracts(spec,data)
    spec['revenue_models']=copy.deepcopy(config.get('revenue_models',{}))
    if fx_source is not None:
        from .fx import apply_fx_accounting_contracts
        apply_fx_accounting_contracts(spec,data,fx_source)
    apply_cash_scope_contract(spec,data)
    rows={r['id']:r for r in spec['rows']}
    # Headers summarize mixed disclosure coverage; detailed status remains per cell.
    for p in periods:
        states={r['cells'].get(p['id'],{}).get('status') for r in spec['rows']
                if r['kind']!='assumption' and r['section']!='fx' and available(r['id'],p['id'])}
        observed=bool(states & {'actual','reported','derived_actual'})
        projected=bool(states & {'forecast','estimate'})
        if observed and projected:p['status']='mixed'
        elif observed:p['status']='actual'
        elif projected:p['status']='forecast'
    spec['missing_value_audit']=dict(before=dict(before),after=dict(Counter(c['status'] for r in spec['rows'] for c in r['cells'].values())),
        reasons=dict(Counter(c.get('reason','') for r in spec['rows'] for c in r['cells'].values() if c['status'] in ('not_comparable','not_disclosed','error'))),
        method='Before = selected primary observations before live derivations and forecast construction. N/C denotes only unsupported comparability; N/D denotes undisclosed metrics.')
    spec['policies'].update(periods='Flows aggregate; stocks use closing dates; shares use duration weights; ratios recompute. Published historical quarter growth is read directly.',
        annual_rates='Annual interest/depreciation/yields use period_year_fraction; year-on-year growth contributions do not.',
        seasonality='Editable prior-period revenue weights; temporary disclosed calendar-day or revenue-weighted cost allocation where quarter cost history is not reported.',
        assumptions='Backend inputs are authoritative. Excel Assumptions and Model boxes project the same controls; edits to Excel do not modify saved backend inputs.')
    spec['gaps']=[g for g in spec['gaps'] if 'next year' not in g and 'Prior years in current-basis' not in g]
    spec['gaps']+=list(config.get('limitations',[]))
    scope_change=data.get('schedule_anchor_policy',{}).get('scope_change',{})
    if scope_change.get('text'):
        spec['gaps'].append('Reported subsequent scope context; compare the dated scope-event calculations and unresolved closing-accounting disclosures: '+scope_change['text'])
    from .periods import assumption_contract
    # Published rounded contributions may differ from reported organic growth.
    # Preserve all facts and expose the difference rather than rewriting a source.
    for segment in data['segments']:
        entity=segment['id']
        if config.get('revenue_models',{}).get(entity,{}).get('method')=='aggregate_organic':continue
        rr=dict(id=entity+'_reported_growth_rounding',label='Reported organic growth less rounded pricing and RIG',
            section='segment_'+entity,unit='ratio',kind='calculated',metric_type='ratio',cells={},
            note='Published rounding reconciliation; forecast organic growth remains the exact sum of assumed contributions.')
        for p in periods:
            cells=[rows[entity+'_'+k]['cells'].get(p['id'],{}) for k in ('organic','pricing','rig')]
            if all(c.get('value') is not None or c.get('expression') for c in cells):
                rr['cells'][p['id']]=formula(f'{entity}_organic - {entity}_pricing - {entity}_rig',status='derived_actual' if all(c.get('status') in ('actual','reported','derived_actual') for c in cells) else 'forecast')
            else:rr['cells'][p['id']]=missing()
        spec['rows'].append(rr)
    spec['input_contract']=assumption_contract(spec)
    return spec


def periodic_sensitivities(spec, values):
    """Independent amount/timing expectations at each financial item's cadence."""
    from .periods import calculate_periodic,validate_periodic
    segment=next(r['id'][:-8] for r in spec['rows'] if r['id'].endswith('_pricing'))
    rows={r['id']:r for r in spec['rows']};pmap={p['id']:p for p in spec['periods']}
    by_kind={(p['fiscal_year'],p['kind']):p['id'] for p in spec['periods']}
    half=spec.get('frequency_policy',{}).get('statements')=='half_year'
    cases=[];checks=[]
    def stock(pid):return by_kind[pmap[pid]['fiscal_year'],'FY'] if half and pmap[pid]['kind']=='H2' else pid
    def eligible(driver):
        return sorted([pid for pid,c in rows[driver]['cells'].items() if c.get('editable') and c.get('status') in ('forecast','estimate') and values[driver].get(pid) is not None],key=lambda pid:pmap[pid]['start'])
    def case(name,driver,pid,bump,deltas):
        item=dict(id=name,driver=driver,period_id=pid,bump=bump,expected_deltas=[dict(row=rid,period_id=target,delta=delta) for rid,target,delta in deltas])
        cases.append(item);changed=calculate_periodic(spec,{driver:{pid:values[driver][pid]+bump}})
        for expected in item['expected_deltas']:
            rid=expected['row'];target=expected['period_id'];delta=expected['delta']
            if changed[rid][target] is None or values[rid][target] is None:
                checks.append(check('period_sensitivity',name+':'+rid+':'+target,'MISSING','Required sensitivity output is unavailable'));continue
            actual=changed[rid][target]-values[rid][target]
            checks.append(check('period_sensitivity',name+':'+rid+':'+target,
                'PASS' if math.isclose(actual,delta,abs_tol=1e-6,rel_tol=1e-8) else 'FAIL',f'Independent expected change {delta:g}; observed {actual:g}',actual-delta,1e-6))
        failures=[c for c in validate_periodic(spec,changed) if c['status']=='FAIL']
        funding=[c for c in failures if c['area']=='period_values' and c['name'].split(':')[0] in ('cash','closing_cash') and c.get('detail')=='Negative value for a nonnegative financial balance']
        failures=[c for c in failures if c not in funding]
        if funding:
            checks.append(check('period_sensitivity',name+':funding','WARNING','Stress scenario requires additional financing; no cash floor or automatic borrowing applied. '+json.dumps(funding)))
        checks.append(check('period_sensitivity',name+':integrity','FAIL' if failures else 'PASS','Financial identities remain valid' if not failures else json.dumps(failures[:5])))
    aggregate_organic=spec.get('revenue_models',{}).get(segment,{}).get('method')=='aggregate_organic'
    primary_cases=[('organic' if aggregate_organic else 'pricing',segment+('_organic' if aggregate_organic else '_pricing')),('inventory','inventory_ratio'),('capex','capex_ppe_ratio'),('borrowing','borrowing_input')]
    if not spec.get('financial_contracts'):primary_cases.insert(1,('cost',segment+'_cost_inflation'))
    for name,driver in primary_cases:
        periods=eligible(driver)
        if not periods:
            checks.append(check('period_sensitivity',name,'MISSING','No active input at the supported cadence'));continue
        pid=periods[0];second=periods[1] if len(periods)>1 else None;fraction=values['period_year_fraction'][pid]
        if name in ('pricing','organic'):
            fx_factor=values.get(segment+'_revenue_fx_adjusted',{}).get(pid,0) or 0
            convention=spec.get('fx_interfaces',{}).get('exposures',{}).get(segment,{}).get('revenue_bridge')
            amount=values.get(segment+'_organic_comparable_sales',values[segment+'_sales_seed'])[pid]*.01*(1+fx_factor if convention=='translation_of_constant_currency' else 1)
            case(name,driver,pid,.01,[('sales',pid,amount)])
        elif name=='cost':
            activity=values[segment+'_rig'][pid];fx=values[segment+'_cost_fx'][pid]
            amount=values[segment+'_cash_cost_seed'][pid]*((1+activity)*(1+fx) if spec.get('fx_interfaces',{}).get('exposures') else 1+activity+fx)*.01
            case(name,driver,pid,.01,[('utop',pid,-amount)])
        elif name=='inventory':
            amount=-values.get('closing_operating_cogs_base',values.get('operating_cogs_base',values['cogs']))[pid]/fraction*.01
            case(name,driver,pid,.01,[('inventories',stock(pid),amount),('cfo',pid,-amount)])
        elif name=='capex':
            amount=values['sales'][pid]*.01;effects=[('owned_ppe',stock(pid),amount),('cfi',pid,-amount),('da',pid,0)]
            if second:effects.append(('da',second,amount*values['owned_depreciation_rate'][second]*values['period_year_fraction'][second]))
            case(name,driver,pid,.01,effects)
        else:
            interest=100*(1-values.get('borrowing_elapsed_fraction',{}).get(pid,1))*values['borrowing_rate'][pid]*fraction
            tax=values.get('effective_tax_rate_policy',values['effective_tax_rate'])[pid];cash_tax=values['cash_tax_ratio'][pid];current_share=1-values.get('deferred_tax_share',{}).get(pid,0)
            effects=[('total_debt',stock(pid),100),('closing_cash',stock(pid),100-interest*(1-tax*cash_tax*current_share)),('debt_interest',pid,interest)]
            if second:effects.append(('debt_interest',second,100*values['borrowing_rate'][second]*values['period_year_fraction'][second]))
            case(name,driver,pid,100,effects)
    if spec.get('fx_interfaces',{}).get('exposures'):
        for side in (('revenue',) if spec.get('financial_contracts') else ('revenue','cost')):
            driver=segment+'_'+side+'_fx_multiplier'
            periods=eligible(driver)
            if not periods:continue
            pid=periods[0];raw=values[segment+'_'+side+'_fx_raw'][pid]
            if raw is None:continue
            if side=='revenue':
                convention=spec['fx_interfaces']['exposures'][segment]['revenue_bridge']
                constant_growth=1+values[segment+'_pricing'][pid]+values[segment+'_rig'][pid]
                constant_base=values.get(segment+'_constant_currency_sales',{}).get(pid)
                if constant_base is None:constant_base=values[segment+'_sales_seed'][pid]*(constant_growth if convention=='translation_of_constant_currency' else 1)
                amount=constant_base*raw*.1
                case('fx_revenue_multiplier',driver,pid,.1,[('sales',pid,amount)])
            else:
                amount=values[segment+'_cash_cost_seed'][pid]*(1+values[segment+'_rig'][pid])*(1+values[segment+'_cost_inflation'][pid])*raw*.1
                case('fx_cost_multiplier',driver,pid,.1,[('utop',pid,-amount)])
    if spec.get('financial_contracts'):
        pools=spec['financial_contracts']['cost_pools']
        marketing=next((p for p in pools if p['id']=='marketing'),next(p for p in pools if p['destination']=='marketing_admin'))
        production=next(p for p in pools if p['destination']=='cogs')
        marketing_suffix={'budget_growth':'spending_change','absolute_budget':'budget_amount'}.get(marketing.get('method'),'budget_change')
        for name,pool,suffix,bump in [('marketing_budget',marketing,marketing_suffix,.01 if marketing_suffix=='spending_change' else 100),('production_unit_cost',production,'unit_cost_change',.01)]:
            rid=segment+'_pool_'+pool['id'];driver=rid+'_'+suffix;targets=eligible(driver)
            if not targets:continue
            pid=targets[0];fx=(1+(0 if pool.get('input_cost_includes_transaction_fx') else values[rid+'_transaction_fx'][pid]))*(1+values[rid+'_translation_fx'][pid])
            scope=values[segment+'_scope_activity_factor'][pid]
            base=values[rid+'_activity_base'][pid]-values[rid+'_sbc_seed'][pid]*scope
            amount=bump*fx*scope if suffix in ('budget_change','budget_amount') else base*bump*fx*(1 if suffix=='spending_change' else 1+values[rid+'_activity_change'][pid]*values[rid+'_effective_activity_sensitivity'][pid])
            tax=values.get('effective_tax_rate_policy',values['effective_tax_rate'])[pid];current_share=1-values.get('deferred_tax_share',{}).get(pid,0)
            cash_tax=values['cash_tax_ratio'][pid];cash=-amount*(1-tax*current_share*cash_tax)
            if pool['destination']=='cogs':
                closing_expense=amount/(1+values[rid+'_translation_fx'][pid])
                closing_expense*=1+(values.get(segment+'_closing_scope_correction_factor',{}).get(pid) or 0)
                if suffix=='unit_cost_change':
                    for event in spec.get('scope_event_audit',[]):
                        if event.get('entity_id')!=segment or event.get('entity_scope_fraction') is not None:continue
                        control='scope_'+event['id']+'_'+pool['id']+'_closing_cost_correction_run_rate'
                        extra=values.get(control,{}).get(pid)
                        if extra is not None and extra<0:
                            closing_expense+=extra*(1+values[rid+'_activity_change'][pid]*values[rid+'_effective_activity_sensitivity'][pid])*bump*(1+(0 if pool.get('input_cost_includes_transaction_fx') else values[rid+'_transaction_fx'][pid]))
                cash+=closing_expense/values['period_year_fraction'][pid]*(values['payables_ratio'][pid]-values['inventory_ratio'][pid])
            case(name,driver,pid,bump,[('operating_profit',pid,-amount),('cfo',pid,cash)])
        fx_candidates=[(r['id'],r['id'][:-len('_translation_multiplier')]) for r in spec['rows'] if r['id'].endswith('_translation_multiplier')]
        for driver,rid in fx_candidates:
            targets=[p for p in eligible(driver) if values[rid+'_translation_fx'].get(p) is not None and values[driver][p]!=0]
            if not targets:continue
            pid=targets[0];raw=values[rid+'_translation_fx'][pid]/values[driver][pid]
            base=values[rid+'_pre_fx'][pid]+values[rid+'_transaction_amount'][pid]
            if base is None or abs(raw)<1e-12:continue
            case('fx_cost_pool_multiplier',driver,pid,.1,[('utop',pid,-base*raw*.1)])
            break
        # Pricing-only behaviour is independently checked against unchanged cost
        # pools, not inferred merely from Python/Excel formula agreement.
        price_periods=eligible(segment+'_pricing')
        if price_periods:
            pid=price_periods[0];changed=calculate_periodic(spec,{segment+'_pricing':{pid:values[segment+'_pricing'][pid]+.01}})
            for pool in (marketing,production):
                rid=segment+'_pool_'+pool['id']
                comparable=[p for p in pmap if pmap[p]['start']<=pmap[pid]['start'] and pmap[p]['end']>=pmap[pid]['end'] and values[rid].get(p) is not None]
                if comparable:
                    target=min(comparable,key=lambda p:pmap[p]['duration_days']);difference=changed[rid][target]-values[rid][target]
                    checks.append(check('period_sensitivity','pricing_independent_'+pool['id'],'PASS' if abs(difference)<1e-8 else 'FAIL',
                        'A selling-price change does not mechanically change the independent production/marketing cash expense.',difference,1e-8))
    return cases,checks


def prior_missing_value_audit(previous, spec):
    """Compare prior N/C displays with the same annual cells in the new model."""
    from collections import Counter
    from openpyxl import load_workbook
    if not previous or not previous.get('_reuse_verified'):
        return dict(status='unavailable',reason='No verified previous workbook supplied')
    directory=Path(previous['directory'])
    if not (directory/'workbook_validation.json').is_file() or not (directory/'model.xlsx').is_file():
        return dict(status='unavailable',reason='Previous run stopped before workbook export; source and call progress remain reusable')
    inspection=json.loads((directory/'workbook_validation.json').read_text(encoding='utf-8'))
    columns=inspection.get('year_columns')
    if not columns:return dict(status='unavailable',reason='Previous workbook has no comparable annual-column map')
    rows={r['id']:r for r in spec['rows']};after=Counter();reasons=Counter();before=0
    with (directory/'model.xlsx').open('rb') as stream:
        book=load_workbook(stream,read_only=True,data_only=True);sheet=book['Model']
        # Read the modest annual sheet once; random access in read-only mode would
        # repeatedly parse its XML for every old cell.
        matrix=list(sheet.values)
        from openpyxl.utils.cell import column_index_from_string
        for rid,index in inspection.get('model_rows',{}).items():
            for year,col in columns.items():
                if matrix[index-1][column_index_from_string(col)-1]!='N/C':continue
                before+=1
                cell=rows.get(rid,{}).get('cells',{}).get(year+'-FY',{})
                status=cell.get('status','not_applicable');after[status]+=1
                if status in ('not_comparable','not_disclosed','not_applicable','error'):
                    reasons[status+': '+cell.get('reason','Removed nonnumeric or inapplicable row')]+=1
        book.close()
    return dict(status='compared',previous_workbook=str(directory/'model.xlsx'),
        previous_sha256=hashlib.sha256((directory/'model.xlsx').read_bytes()).hexdigest(),
        before_nc=before,after_statuses_for_same_cells=dict(after),remaining_nc=after['not_comparable'],
        causes=dict(reasons),scope='Same row IDs and FY periods only; new quarterly and half-year cells are excluded from this before/after comparison.')


def financial_sensitivities(spec, values):
    """Known directional/amount checks on the actual constructed company graph."""
    first=str(spec['forecast_years'][0]);second=str(spec['forecast_years'][1]) if len(spec['forecast_years'])>1 else None;base=str(max(spec['historical_years']))
    rows={r['id']:r for r in spec['rows']};segment=next(r['id'][:-8] for r in spec['rows'] if r['id'].endswith('_pricing'))
    results=[]
    def run(name,driver,delta,target,year,expected,more=None):
        old=rows[driver]['inputs'][first]
        changed=calculate_integrated(spec,{driver:{first:old+delta}})
        observed=changed[target][year]-values[target][year]
        ok=math.isclose(observed,expected,rel_tol=1e-8,abs_tol=1e-6)
        results.append(check('sensitivity',name,'PASS' if ok else 'FAIL',
            f'{driver} + {delta:g}; {target}:{year} change {observed:g}, independently expected {expected:g}',observed-expected,1e-6))
        if more:more(changed)
        return changed
    delta_sales=values[segment+'_sales'][base]*.01
    changed=run('segment_pricing',segment+'_pricing',.01,'sales',first,delta_sales)
    results.append(check('sensitivity','pricing_unrelated_segment_cost','PASS' if changed[segment+'_cash_cost'][first]==values[segment+'_cash_cost'][first] else 'FAIL','Pricing does not silently change segment cash operating-cost assumptions'))
    inflation=rows[segment+'_cost_inflation']['inputs'][first]
    expected_cost=values[segment+'_cash_cost'][first]/(1+inflation)*.01
    cost_case=run('segment_cost',segment+'_cost_inflation',.01,'utop',first,-expected_cost)
    def input_value(key):return rows[key]['inputs'][first]
    current_tax_share=1-input_value('deferred_tax_share') if 'deferred_tax_share' in rows else 1
    cash_delta=-expected_cost*(1-input_value('effective_tax_rate')*current_tax_share*input_value('cash_tax_ratio'))
    cash_delta+=expected_cost*input_value('cogs_allocation')*(input_value('payables_ratio')-input_value('inventory_ratio'))
    results.append(check('sensitivity','operating_cost_cash','PASS' if math.isclose(cost_case['cfo'][first]-values['cfo'][first],cash_delta,abs_tol=1e-6) else 'FAIL',
        'Independent cost/tax/working-capital calculation: CFO change '+str(cash_delta)))
    changed=run('inventory_balance','inventory_ratio',.01,'inventories',first,-values['cogs'][first]*.01)
    expected_cash=values['cogs'][first]*.01
    results.append(check('sensitivity','inventory_cash','PASS' if math.isclose(changed['cfo'][first]-values['cfo'][first],expected_cash,abs_tol=1e-6) else 'FAIL','Inventory increase reduces CFO by the same independently calculated balance change'))
    capex=values['sales'][first]*.01
    changed=run('capex_asset','capex_ppe_ratio',.01,'owned_ppe',first,capex)
    results.append(check('sensitivity','capex_cash','PASS' if math.isclose(changed['cfi'][first]-values['cfi'][first],-capex,abs_tol=1e-6) else 'FAIL','Cash capex reduces investing cash flow by the independently calculated additional investment'))
    if second:
        expected_dep=capex*rows['owned_depreciation_rate']['inputs'][second]
        results.append(check('sensitivity','capex_depreciation_lag','PASS' if math.isclose(changed['da'][second]-values['da'][second],expected_dep,abs_tol=1e-6) else 'FAIL',f'Additional capex {capex:g} increases following-year D&A by {expected_dep:g}'))
    changed=run('borrowing_debt','borrowing_input',100,'total_debt',first,100)
    expectations=[('closing_cash',first,100),('debt_interest',first,0)]
    if second:expectations.append(('debt_interest',second,100*rows['borrowing_rate']['inputs'][second]))
    for target,year,expected in expectations:
        diff=changed[target][year]-values[target][year]
        results.append(check('sensitivity','borrowing_'+target+year,'PASS' if math.isclose(diff,expected,abs_tol=1e-6) else 'FAIL',f'Expected {expected:g}; observed {diff:g}',diff-expected,1e-6))
    return results


REVIEW_SCHEMA=_object(findings=_array(_object(severity=_enum(('error','warning')),area=TEXT,detail=TEXT,
    source_references=_array(TEXT))),summary=TEXT)


def freeze_model_sources(data, archive, source_folder, *, previous=None, outputs=None):
    """Freeze originals, retaining verified historical files removed from the live archive.

    A changed live original is never replaced by an old copy. Missing originals
    may use an identical source from a verified parent; this is evidence reuse,
    not a company-specific input migration.
    """
    from .evidence import _local_file
    frozen=[];reused=[]
    prior_sources={s['id']:s for s in (previous or {}).get('sources',[])}
    descriptors=data['sources'].values() if isinstance(data['sources'],dict) else data['sources']
    for source in descriptors:
        try:
            raw=_local_file(archive,source['local_path']).read_bytes()
        except FileNotFoundError:
            prior=prior_sources.get(source['id'])
            if not previous or not previous.get('_reuse_verified') or not outputs or not prior or prior.get('sha256')!=source.get('sha256'):
                raise ValueError('Original is absent and no identical verified parent source is available: '+source['local_path'])
            prior_path=Path(prior['path']).resolve()
            raw=_local_file(Path(outputs).resolve(),str(prior_path.relative_to(Path(outputs).resolve()))).read_bytes()
            reused.append(dict(source_id=source['id'],local_path=source['local_path'],
                parent_path=str(prior_path),sha256=source['sha256'],reason='Original absent from current archive; verified frozen original retained'))
        if hashlib.sha256(raw).hexdigest()!=source['sha256']:
            raise ValueError('Source changed before freezing: '+source['local_path'])
        target=source_folder/(source['id']+Path(source['local_path']).suffix)
        target.write_bytes(raw)
        frozen.append(dict(source,path=str(target)))
    return frozen,reused


def construct_integrated(root, company, archive, inputs_file, *, reference_workbook=None,
        budget_usd=20, forecast_years=5, recalculate=True, progress=None, provider=None, escalation_file=None,
        fx_file=None, fx_database=None, resume=None, as_of=None, historical_vintage=False,
        include_valuation=False, valuation_date=None, valuation_inputs=None):
    """Resume a sourced company specification and construct its complete model.

    Inputs are generated company research data, not a user-filled forecast. Source
    values are re-read and checked. The code works for any specification satisfying
    the financial-role contract; incompatible economics fail review explicitly.
    """
    root=Path(root).resolve();outputs=root/'outputs';archive=Path(archive).resolve()
    data=json.loads(Path(inputs_file).read_text(encoding='utf-8'))
    data.setdefault('model_configuration',{})['as_of']=as_of or data.get('model_configuration',{}).get('as_of') or datetime.now(timezone.utc).date().isoformat()
    data['model_configuration']['historical_vintage']=bool(historical_vintage)
    valuation_configuration=dict(enabled=bool(include_valuation),
        date=(valuation_date or data['model_configuration']['as_of']) if include_valuation else None,
        inputs_sha256=hashlib.sha256(Path(valuation_inputs).read_bytes()).hexdigest() if include_valuation and valuation_inputs else None)
    if not data.get('fiscal_calendar'):
        raise ValueError('Construction requires the company fiscal calendar; annual reporters use statement_forecast_frequency=annual through the same period engine')
    periodic=True
    fx_identity=None
    fx_snapshot=None
    if fx_database:
        from .fx_store import FXStore
        if not Path(fx_database).is_file():raise ValueError('Shared FX database missing; run fx-import first')
        with FXStore(fx_database) as store:
            fx_snapshot=store.snapshot(data['model_configuration'].get('fx_as_of',data['model_configuration']['as_of']),store.latest_policy())
        fx_identity=fx_snapshot['source']
    elif fx_file:
        fx_file=Path(fx_file).resolve()
        fx_identity=dict(path=str(fx_file),sha256=hashlib.sha256(fx_file.read_bytes()).hexdigest())
    escalations=json.loads(Path(escalation_file).read_text(encoding='utf-8')) if escalation_file else {}
    if not isinstance(escalations,dict):
        raise ValueError('Escalation evidence must be a JSON object keyed by stage')
    inventory=inventory_local_sources(archive)
    provider=provider or OpenAIProvider.from_env(root/'.env');provider.max_output_tokens=12000
    # Compact financial reviews can still use several thousand reasoning tokens.
    # This bounds transport waiting without adding hidden retries or free calls.
    provider.timeout=max(getattr(provider,'timeout',120),240)
    defaults={}
    if (root/'pyproject.toml').is_file():
        import tomllib
        defaults=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8')).get('tool',{}).get('research-platform',{})
    with _initiation_lock(outputs,scope=company_key(company)):
        ledger=BudgetLedger(ledger_path(outputs,company),company,budget_usd)
        prior=[]
        for file in outputs.glob('construct_*/record.json'):
            saved=json.loads(file.read_text(encoding='utf-8'))
            if company_key(saved.get('configuration',{}).get('company','unknown'))==company_key(company):
                ledger.import_record(saved);prior.append(saved)
        previous,continuation_recovery=select_integrated_previous(prior,outputs,company,resume)
        runtime=integrated_runtime_fingerprint()
        cache_key=integrated_source_cache_key(data,inventory,runtime)
        configuration=dict(company=company,sources=str(archive),manifest=inventory['manifest_sha256'],
            provider=provider.metadata(),mode='integrated_periodic_v2' if periodic else 'integrated_v1',input_hash=digest(dict(data=data,fx=fx_identity)) if fx_identity else digest(data),forecast_years=forecast_years,
            runtime=runtime,source_cache_key=cache_key,valuation=valuation_configuration,
            limits=dict(usd=budget_usd,calls=None,repairs=2,retries=0,generated_tokens=None),escalations=escalations,
            review_policy=dict(cheap_repairs=data['model_configuration'].get('cheap_review_repairs',defaults.get('cheap-review-repairs',1))))
        if previous and continuation_recovery is None and compatible_integrated_result(previous,configuration,runtime,cache_key):
            if progress:progress('Returning verified accepted model; no AI calls or source reparsing. Cumulative budget: '+json.dumps(ledger.summary()))
            return Path(previous['directory'])
        provider.validate_configuration()
        recovery=ledger.recover(provider)
        directory=outputs/f'construct_integrated_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid4().hex[:8]}'
        directory.mkdir()
        journal=RunJournal(directory,provider,configuration,progress,previous,ledger)
        if continuation_recovery:
            journal.artifact('continuation_recovery.json',continuation_recovery)
            if progress:progress('Explicit continuation from verified ancestor '+previous['directory']+'; excluded newer artifacts remain preserved and all charges remain in the cumulative ledger.')
        journal.artifact('inventory.json',inventory);journal.artifact('company_model_inputs.json',data)
        journal.artifact('reservation_recovery.json',recovery)
        source_folder=directory/'sources';source_folder.mkdir()
        frozen,reused_originals=freeze_model_sources(data,archive,source_folder,previous=previous,outputs=outputs)
        journal.state['sources']=frozen
        journal.artifact('source_freeze_audit.json',dict(reused_missing_originals=reused_originals,
            policy='Current archive originals must match their hashes. Only absent originals may reuse verified parent bytes.'))
        verification_data=dict(data,sources={s['id']:dict(s,local_path=Path(s['path']).name) for s in frozen})
        if fx_snapshot:
            journal.artifact('fx_snapshot.json',fx_snapshot)
            configuration['fx_database']=str(Path(fx_database).resolve())
            configuration['fx_snapshot_id']=fx_identity['snapshot_id']
        elif fx_file:
            target=source_folder/('shared_fx'+fx_file.suffix);target.write_bytes(fx_file.read_bytes())
            if hashlib.sha256(target.read_bytes()).hexdigest()!=fx_identity['sha256']:
                raise ValueError('Shared FX original changed while freezing')
            frozen.append(dict(id='shared_fx',path=str(target),sha256=fx_identity['sha256'],local_path=str(fx_file),
                category='shared_factor',format=fx_file.suffix.lstrip('.')))
            journal.artifact('fx_original.json',fx_identity)
        if reference_workbook:
            ref=Path(reference_workbook).resolve()
            journal.artifact('reference_workbook.json',dict(path=str(ref),sha256=hashlib.sha256(ref.read_bytes()).hexdigest(),
                use='Architecture and presentation only; no reference-company numbers or assumptions enter the company model',
                architecture=['Shared assumptions','Operating segment blocks','Corporate consolidation','Group income statement',
                    'Cash flow','Balance sheet','Working capital','Asset and financing schedules'],
                conventions='Dark headers; pink historical pulls; inline yellow assumption boxes; hidden IDs; live formulas and checks'))
        journal.artifact('code_snapshot.json',{name:Path(__file__).with_name(name).read_text(encoding='utf-8') for name in runtime['code']})
        if progress:progress('Cumulative budget: '+json.dumps(ledger.summary()))
        try:
            from .evidence import verify_model_input_sources
            source_checks=cached_integrated_source_checks(previous,cache_key) if previous else None
            if source_checks is None:source_checks=verify_model_input_sources(verification_data,source_folder)
            elif progress:progress('Reused verified source checks for identical inputs, originals and parser code.')
            from .workflow import freshness_checks, model_financial_completeness
            source_checks+=freshness_checks(verification_data,source_folder,historical_vintage=historical_vintage)
            journal.artifact('source_validation.json',source_checks)
            if any(c['status']=='FAIL' for c in source_checks):
                raise ValueError('Source validation has discrepancies; inspect source_validation.json before model acceptance')
            from .periods import calculate_periodic,validate_periodic
            from .fx import load_fx_source
            fx=fx_snapshot or (load_fx_source(source_folder/('shared_fx'+fx_file.suffix),
                adapter=data.get('model_configuration',{}).get('fx_adapter')) if fx_file else None)
            if fx:journal.artifact('fx_import.json',fx)
            spec=build_periodic_spec(data,forecast_years,fx)
            spec['financial_completeness']=model_financial_completeness(spec)
            journal.state['financial_completeness']=spec['financial_completeness']
            # The supplied verified company query is the display identity; keep
            # the original research label unchanged in its frozen evidence file.
            spec['company']=company
            spec['sources']=frozen
            values=calculate_periodic(spec)
            cases,behaviour=periodic_sensitivities(spec,values)
            spec['sensitivity_cases']=cases
            checks=source_checks+validate_periodic(spec,values)+behaviour
            journal.artifact('model_specification.json',spec);journal.artifact('forecast.json',values)
            journal.artifact('drivers.json',[r for r in spec['rows'] if r['kind']=='assumption'])
            review_periods=[p['id'] for p in spec['periods'] if p['fiscal_year'] in spec['forecast_years'][:2] and p['kind']=='FY']
            review_periods += [p['id'] for p in spec['periods'] if p.get('annual_only')][:1]
            def review_cells(row):
                active=[p for p,c in row['cells'].items() if c.get('status') in ('forecast','estimate') and (c.get('expression') or c.get('value') is not None)]
                chosen=list(dict.fromkeys(active[:1]+review_periods))
                return {p:dict(row['cells'][p],result=values[row['id']].get(p)) for p in chosen if p in row['cells'] and row['cells'][p].get('status')!='not_applicable'}
            # Coherent compact review batches contain actual observations, not just labels.
            # Whole originals remain local and retrieval expands by explicit source/page.
            def repair_review_context(context,failures):
                from .evidence import _units
                requested=' '.join(str(f.get('evidence',[])) for f in failures)
                existing={(e.get('source_id'),e.get('unit_id')) for e in context.get('evidence',[])}
                for source in frozen:
                    if source['id'] not in requested or source.get('category')=='shared_factor':continue
                    # Expand the cited original in full; do not guess its answer
                    # from a model verdict or silently drop parser failures.
                    for unit in _units(Path(source['path']).read_bytes(),source['format']):
                        key=(source['id'],unit['unit_id'])
                        if key not in existing:
                            context.setdefault('evidence',[]).append(dict(unit,source_id=source['id']))
                            existing.add(key)
                return context
            for stage,sections,evidence_key in [('integrated_segments',{'corporate'}|{r['section'] for r in spec['rows'] if r['section'].startswith('segment_')},'integrated_segments'),
                                   ('integrated_income_review',{'income'},'integrated_statements'),
                                   ('integrated_cashflow_review',{'cashflow'},'integrated_statements'),
                                   ('integrated_balance_review',{'balance'},'integrated_statements'),
                                   ('integrated_schedules',{'working_capital','assets','financing'},'integrated_schedules')]:
                compact=[{k:v for k,v in r.items() if k in ('id','label','unit','note','driver_contract')}
                         | {'source_refs':{str(y):r.get('source_refs',{}).get(str(y)) for y in data['history_years'][-2:]},
                            'basis':{str(y):r['basis'].get(str(y)) for y in data['history_years'][-2:]} if isinstance(r.get('basis'),dict) else r.get('basis','shared_market_or_parameter_basis')}
                         | {'history':{str(y):values[r['id']].get(next(p['id'] for p in spec['periods'] if p['fiscal_year']==y and p['kind']=='FY')) for y in data['history_years'][-2:]},
                            'historical_expression':r.get('historical_expression'),
                            'period_cells':review_cells(r)}
                    for r in spec['rows'] if r['section'] in sections]
                review=journal.review_stage(stage,
                    'Review this real company integrated temporary model. Use the actual cited historical observations and supplied company evidence. '
                    'Find MATERIAL arithmetic, accounting scope, source mapping, double counting or dependency errors. '
                    'Explicit temporary assumptions and disclosed simplifications are warnings, not invented reported facts. '
                    'Do not demand a predictive forecast or perfect asset-specific lease data. Do not approve merely because statements balance. '
                    'Name exact problematic IDs and an economically correct repair. Relevant source sections can be retrieved locally for follow-up. '
                    'Review only the target rows; dependency context is provided to establish their actual inputs, not to request a full-company review in every task. '
                    'Review the actual bound period cells and driver contracts, including the direct annual transition. '
                    'Functional cash spending/activity/unit-cost pools determine segment and group profits. Marketing and COGS must not be driven by selling-price or sales-ratio defaults. Baseline segment-by-function allocations are estimates, not economic spending drivers. '
                    'Check regional scope annualisation, organic denominators, separate transaction/translation FX, independent cash/OCI effects, weighted shares and dividend payment timing. Explicit unresolved closing-accounting inputs prevent a claim of complete portfolio integration. '
                    'In source references, multiplier normalizes the original units/sign; contribution_weight applies the arithmetic contribution. Non-additive expression and assumption references are labelled operands/initialization ingredients, not additive mappings. '
                    'Asset_scope defines evidence-backed inclusion relationships: owned PPE excludes ROU only when the cited disclosure establishes that scope. Never subtract ROU again from an already owned-only amount. Check combined amounts against owned plus ROU, and treat ambiguous classifications as unresolved evidence questions. Findings are proposals; do not alter source mappings. '
                    'Return only structured findings. The user authorized targeted evidence contexts, not entire report repetition.',
                    dict(company=company,basis=data['forecast_basis'],policies=spec['policies'],rows=compact,
                        asset_scope=asset_scope_context(data) if stage=='integrated_schedules' else [],
                        forecast_horizon=spec.get('forecast_horizon'),frequency_policy=spec.get('frequency_policy'),
                        scope_events=spec.get('scope_event_audit',[]),
                        research_limitations=data.get('model_configuration',{}).get('limitations',[]),
                        complete_forecast_graph=[dict(id=r['id'],unit=r['unit'],kind=r['kind'],period_cells=review_cells(r)) for r in spec['rows']],
                        source_controls=data.get('independent_controls',[]),evidence=[dict(e,unit_id=e.get('unit_id','sheet:'+e.get('sheet',''))) for e in data.get('review_evidence',{}).get(evidence_key,[])]),REVIEW_SCHEMA,repair_context=repair_review_context)
                for finding in review['findings']:
                    checks.append(check('AI_review',stage,'FAIL' if finding['severity']=='error' else 'WARNING',finding['detail']))
            if periodic:
                spec['missing_value_audit']['previous_workbook_comparison']=prior_missing_value_audit(previous,spec)
                periodic_checks=validate_periodic(spec,values)
                journal.artifact('period_validation.json',dict(checks=periodic_checks+behaviour,
                    observation_selection=spec['observation_selection'],derivations=spec['derivation_checks'],
                    missing_value_audit=spec['missing_value_audit'],
                    review_scope='AI reviews target this final causal period graph; deterministic checks independently test its stated financial contracts.'))
                journal.artifact('model_specification.json',spec);journal.artifact('forecast.json',values)
                journal.artifact('drivers.json',[r for r in spec['rows'] if r['kind']=='assumption'])
            valuation=None
            if include_valuation:
                from .workflow import valuation_snapshot
                valuation=valuation_snapshot(spec,values,data,valuation_date=valuation_configuration['date'],inputs_file=valuation_inputs)
                for name,value in valuation['artifacts'].items():journal.artifact(name,value)
                checks.extend(valuation['checks'])
            status='complete_provisional' if not any(c['status'] in ('FAIL','MISSING') for c in checks) else 'incomplete_model'
            journal.artifact('validation.json',dict(status=status,financial_completeness=spec['financial_completeness'],checks=checks,gaps=spec['gaps']))
            inspection=export_integrated(directory/'model.xlsx',spec,values,checks,**({'valuation':valuation['result']} if valuation else {}))
            if recalculate:
                inspection['recalculation']=recalculate_workbook(directory/'model.xlsx',inspection)
                if inspection['recalculation'].get('status')=='passed':
                    from .model_excel import verify_excel_sensitivities
                    inspection['sensitivities']=verify_excel_sensitivities(directory/'model.xlsx',spec,inspection,output_directory=directory)
            from .model_excel import validate_workbook_layout
            inspection['layout']=validate_workbook_layout(directory/'model.xlsx',inspection)
            journal.artifact('workbook_validation.json',inspection)
            if inspection.get('recalculation',{}).get('status')!='passed' or inspection.get('sensitivities',{}).get('status')!='passed' or inspection['layout']['status']!='passed':status='incomplete_model'
            journal.state['artifacts']['model.xlsx']=hashlib.sha256((directory/'model.xlsx').read_bytes()).hexdigest()
            if (directory/'model.audit.json').exists():
                journal.state['artifacts']['model.audit.json']=hashlib.sha256((directory/'model.audit.json').read_bytes()).hexdigest()
            if (directory/'excel_sensitivity_validation.json').exists():
                journal.state['artifacts']['excel_sensitivity_validation.json']=hashlib.sha256((directory/'excel_sensitivity_validation.json').read_bytes()).hexdigest()
            journal.artifact('validation.json',dict(status=status,financial_completeness=spec['financial_completeness'],checks=checks,gaps=spec['gaps']))
            journal.state.update(status=status,financial_completeness=spec['financial_completeness'],summary=dict(rows=len(spec['rows']),segments=len(data['segments']),
                assumptions=sum(r['kind']=='assumption' for r in spec['rows']),historical_years=data['history_years'],
                forecast_years=spec['forecast_years'],checks={s:sum(c['status']==s for c in checks) for s in ('PASS','FAIL','MISSING','WARNING')}))
        except Exception as exc:
            journal.state['status']='incomplete';journal.state['issues'].append(str(exc));journal.save();raise
        journal.save()
        return directory


def integrated_runtime_fingerprint():
    """Exact local code/parser identity for reuse, without reading credentials."""
    from importlib.metadata import version, PackageNotFoundError
    import platform
    names=('__main__.py','project.py','integrated.py','construction.py','model_excel.py','periods.py','fx.py','fx_store.py','ibkr.py','budget.py','ai.py','evidence.py','initiation.py','workflow.py','valuation.py')
    code={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names}
    parsers={}
    for name in ('openpyxl','pypdf','xlrd'):
        try:parsers[name]=version(name)
        except PackageNotFoundError:parsers[name]='not-installed'
    return dict(version=1,code=code,parsers=parsers,python=platform.python_version())


def integrated_source_cache_key(data, inventory, runtime=None):
    """Source checks reuse only exact data, source bytes and parser implementations."""
    runtime=runtime or integrated_runtime_fingerprint()
    manifest=inventory.get('manifest_sha256')
    if not isinstance(manifest,str) or not manifest:
        raise ValueError('Source validation cache requires a hashed archive inventory')
    return digest(dict(version=1,input_hash=digest(data),manifest=manifest,
        evidence_code=runtime['code']['evidence.py'],parsers=runtime['parsers'],python=runtime['python']))


def select_integrated_previous(prior, outputs, company, resume=None):
    """Verify the newest run, or an explicitly requested recorded ancestor.

    The caller imports every same-company record into its cumulative ledger
    before selecting reusable work. An explicit ancestor never erases charges
    or edits the excluded run's changed workbook, record or request transcript.
    """
    outputs=Path(outputs).resolve()
    newest=max(prior,key=lambda r:Path(r['directory']).stat().st_mtime_ns) if prior else None
    if resume is None:
        return (verified_integrated_record(newest['directory'],outputs),None) if newest else (None,None)
    requested=Path(resume)
    if not requested.is_absolute() and not requested.exists():requested=outputs/requested
    requested=requested.resolve()
    records={Path(r['directory']).resolve():r for r in prior}
    if requested not in records or company_key(records[requested].get('configuration',{}).get('company','unknown'))!=company_key(company):
        raise ValueError('Explicit resume must select a recorded construction for the same company')
    excluded=[];cursor=Path(newest['directory']).resolve();seen=set()
    while cursor!=requested:
        if cursor in seen or cursor not in records:
            raise ValueError('Explicit resume must name a recorded ancestor of the newest construction')
        seen.add(cursor);item=records[cursor]
        def saved_hash(name):
            file=cursor/name
            return hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
        excluded.append(dict(directory=str(cursor),record_sha256=saved_hash('record.json'),
            calls_sha256=saved_hash('calls.jsonl'),reuse='No artifacts or responses reused from this excluded run'))
        parent=item.get('parent_run')
        if not parent:raise ValueError('Explicit resume must name a recorded ancestor of the newest construction')
        cursor=Path(parent).resolve()
    selected=verified_integrated_record(requested,outputs)
    latest_error=None
    if excluded:
        try:verified_integrated_record(newest['directory'],outputs)
        except (ValueError,OSError) as exc:latest_error=str(exc)
    recovery=dict(mode='explicit_verified_ancestor',requested_run=str(requested),
        selected_run=selected['directory'],newest_run=newest['directory'],
        newest_verification_error=latest_error,excluded_runs=excluded,
        budget_policy='All same-company records, including excluded runs, were imported once into the existing cumulative ledger before selecting reusable work.')
    return selected,recovery


def verified_integrated_record(run, outputs):
    """Verify saved work before reuse; this never erases or settles ledger costs.

    Legacy incompatible settings do not make charges disappear. Call this after
    importing their accounting, and use only its returned detached record for
    response/artifact reuse. Parsing originals is not repeated here.
    """
    run,outputs=Path(run).resolve(),Path(outputs).resolve()
    if run.parent!=outputs or not run.is_dir():
        raise ValueError('Saved construction must be a direct run inside project outputs')
    record=json.loads((run/'record.json').read_text(encoding='utf-8'))
    record.pop('_reuse_verified',None)
    if Path(record.get('directory','')).resolve()!=run:
        raise ValueError('Saved construction directory identity disagrees with its record')
    calls=record.get('calls')
    if not isinstance(calls,list):
        raise ValueError('Saved construction has no valid call journal')
    journal=run/'calls.jsonl'
    saved_calls=[json.loads(line) for line in journal.read_text(encoding='utf-8').split('\n') if line.strip()] if journal.exists() else []
    if saved_calls!=calls:
        raise ValueError('Saved calls.jsonl differs from record; response reuse is prohibited')
    seen=set()
    for entry in calls:
        call_id=entry.get('call_id')
        if not isinstance(call_id,str) or not call_id or call_id in seen:
            raise ValueError('Saved journal has missing or duplicate request identities')
        seen.add(call_id)
        request=entry.get('request')
        if not isinstance(request,dict) or digest(request)!=entry.get('signature'):
            raise ValueError('Saved request signature is invalid; response reuse is prohibited')
        if request.get('model')!=entry.get('model'):
            raise ValueError('Saved request model disagrees with its call identity')
    artifacts=record.get('artifacts',{})
    if not isinstance(artifacts,dict):
        raise ValueError('Saved construction artifact inventory is invalid')
    for name,expected in artifacts.items():
        path=(run/name).resolve()
        if not path.is_relative_to(run) or not path.is_file():
            raise ValueError('Saved artifact is missing or outside its run: '+str(name))
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise ValueError('Saved artifact content changed: '+str(name))
    from .construction import verify_source_bytes
    verify_source_bytes(record.get('sources',[]),outputs)
    record['_reuse_verified']=True
    return copy.deepcopy(record)


def compatible_integrated_result(record, configuration, runtime, source_cache_key):
    """Whether an already verified accepted workbook can return without API work.

    The caller sets configuration.runtime and configuration.source_cache_key on
    every new run. Missing fields on older runs cause a safe cache miss.
    """
    if (not record.get('_reuse_verified') or record.get('status')!='complete_provisional'
            or record.get('pending_call')):
        return False
    old=record.get('configuration',{})
    required=('company','sources','manifest','provider','mode','input_hash','forecast_years')
    if any(key not in old or old[key]!=configuration.get(key) for key in required):
        return False
    if old.get('valuation')!=configuration.get('valuation'):
        return False
    if old.get('runtime')!=runtime or old.get('source_cache_key')!=source_cache_key:
        return False
    artifacts=record.get('artifacts',{})
    if not {'model.xlsx','model_specification.json','forecast.json','validation.json','workbook_validation.json'}<=artifacts.keys():
        return False
    directory=Path(record['directory'])
    validation=json.loads((directory/'validation.json').read_text(encoding='utf-8'))
    inspection=json.loads((directory/'workbook_validation.json').read_text(encoding='utf-8'))
    if (validation.get('status')!='complete_provisional' or
            any(item.get('status') in ('FAIL','MISSING') for item in validation.get('checks',[]))):
        return False
    return inspection.get('recalculation',{}).get('status')=='passed'


def cached_integrated_source_checks(record, source_cache_key):
    """Return verified exact cached checks or None, never an aliased mutable list."""
    if (not record.get('_reuse_verified') or
            record.get('configuration',{}).get('source_cache_key')!=source_cache_key or
            'source_validation.json' not in record.get('artifacts',{})):
        return None
    checks=json.loads((Path(record['directory'])/'source_validation.json').read_text(encoding='utf-8'))
    if not isinstance(checks,list) or any(not isinstance(item,dict) or item.get('status') not in
                                          ('PASS','FAIL','MISSING','WARNING') for item in checks):
        raise ValueError('Saved source-validation result is malformed')
    return copy.deepcopy(checks)
