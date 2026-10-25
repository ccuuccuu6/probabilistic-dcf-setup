"""Dated, deterministic FCFF valuation of the saved operating model.

This module owns valuation assumptions and arithmetic, not company forecasting.
Money and share scales are explicit. No provider, spreadsheet or company adapter
is imported here. Generic defaults are deliberately labelled unresearched.
"""
from __future__ import annotations

import copy
import ast
from datetime import date, timedelta
import hashlib
import json
import math
import statistics


VERSION = 'valuation-v1'
VALUATION_RESEARCH_VERSION = 'valuation_research_v4'
# These expressions also generate the Excel audit projection. Names are the
# output component keys (plus explicit assumptions), never worksheet addresses.
VALUATION_EQUATIONS = {
    'cost_of_equity': 'risk_free_rate + beta * equity_risk_premium',
    'pre_tax_cost_of_debt': 'risk_free_rate + debt_spread',
    'wacc': 'cost_of_equity * (1 - debt_weight) + pre_tax_cost_of_debt * (1 - tax_rate) * debt_weight + wacc_shift',
    'normalized_operating_profit': 'operating_profit + noncash_portfolio_reversal',
    'cash_lease_cost': 'lease_principal - lease_interest',
    'operating_profit_after_cash_leases': 'normalized_operating_profit + rou_depreciation_reversal + cash_lease_cost',
    'unlevered_tax': '-operating_profit_after_cash_leases * tax_rate',
    'nopat': 'operating_profit_after_cash_leases + unlevered_tax',
    'eligible_da': 'owned_depreciation + amortization',
    'full_period_fcff': 'nopat + eligible_da + capex_ppe + capex_intangibles + operating_working_capital_cash + other_cash_adjustments',
    'remaining_fcff': 'full_period_fcff * remaining_fraction + scope_timing_adjustment',
    'discount_factor': '(1 + wacc) ** (-discount_years)',
    'present_value': 'remaining_fcff * discount_factor',
    'reinvestment_rate': 'growth / roic',
    'next_year_revenue': 'base_revenue * (1 + growth)',
    'terminal_nopat': 'next_year_revenue * operating_margin * (1 - tax_rate)',
    'reinvestment': 'nopat * reinvestment_rate',
    'terminal_fcff': 'nopat - reinvestment',
    'terminal_value': 'fcff * (1 + wacc) ** 0.5 / (wacc - growth)',
    'terminal_present_value': 'value / (1 + wacc) ** discount_years',
    'enterprise_value': 'operating_cashflow_present_value + terminal_present_value',
    'equity_value': 'enterprise_value + future_portfolio_events + cash + cash_like + restricted_cash + nonlease_debt + associates + nci + noncommon_equity + pension_claim + deferred_consideration + other_claims + other_assets',
    'valuation_date_shares': 'basic_shares + dilution_shares',
    'fair_value_per_share': 'equity_value * money_scale / (valuation_date_shares * share_scale)',
    'event_present_value': '(net_cash + event_cash_tax + retained_interest_value - incremental_nci_claim + existing_interest_transfer + nonlease_debt_transfer) * discount_factor',
}


def valuation_equation(name, values):
    """Evaluate the shared arithmetic representation without eval or code calls."""
    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Name):
            return _number(values[node.id], node.id)
        if isinstance(node, ast.Constant):
            return _number(node.value, name)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return evaluate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add): return left+right
            if isinstance(node.op, ast.Sub): return left-right
            if isinstance(node.op, ast.Mult): return left*right
            if isinstance(node.op, ast.Div): return left/right
            return left**right
        raise ValueError('Unsupported valuation arithmetic')
    return evaluate(ast.parse(VALUATION_EQUATIONS[name], mode='eval'))
METHODOLOGY_REFERENCES = [
    {'url': 'https://www.ifrs.org/issued-standards/list-of-standards/ias-33-earnings-per-share.html/',
     'purpose': 'Ordinary-share earnings attribution is separate from cash distributions on noncommon equity instruments.'},
    {'url': 'https://www.ifrs.org/issued-standards/list-of-standards/ifrs-16-leases/',
     'purpose': 'Separate right-of-use depreciation, lease interest and principal; operating-lease valuation treatment is an explicit analytical recast.'},
    {'url': 'https://pages.stern.nyu.edu/~adamodar/pdfiles/uValue/uValuebook.pdf',
     'purpose': 'FCFF, enterprise-to-equity reconciliation and terminal reinvestment equal to growth divided by return on capital.'},
    {'url': 'https://pages.stern.nyu.edu/~adamodar/New_Home_Page/project/prques.htm',
     'purpose': 'Market or explicit target capital weights, separate non-operating holdings and minority claims.'},
]
DEFAULT_ROLES = dict(revenue='sales', operating_profit='operating_profit',
    owned_depreciation='owned_ppe_depreciation', rou_depreciation='rou_depreciation',
    amortization='amortization', lease_principal='lease_principal', lease_interest='lease_interest',
    capex_ppe='capex_ppe', capex_intangibles='capex_intangibles', working_capital_cash='wc_cash',
    portfolio_noncash='cfo_portfolio_noncash', cash_change='cash_change', cash='cash',
    cash_like='short_investments', debt='nonlease_debt', shares='shares_end_outstanding',
    associates='associates', nci='nci_equity', tax_rate='effective_tax_rate')
_FCFF_REQUIRED = ('revenue', 'operating_profit', 'owned_depreciation', 'rou_depreciation',
    'amortization', 'lease_principal', 'lease_interest', 'capex_ppe', 'capex_intangibles',
    'working_capital_cash')
_BOUNDS = dict(risk_free_rate=(-.05, .5), equity_risk_premium=(0, .5), beta=(0, 5),
    debt_spread=(0, .5), debt_weight=(0, 1), tax_rate=(0, 1), terminal_growth=(-.1, .2),
    terminal_roic=(.000001, 1), terminal_margin=(-1, 1), transition_years=(0, 30),
    dilution_shares=(0, None), other_claims=(0, None), other_assets=(0, None),
    restricted_cash=(0, None), pension_claim=(0, None), deferred_consideration=(0, None))
_MONEY_ASSUMPTIONS = {'other_claims', 'other_assets', 'restricted_cash', 'pension_claim', 'deferred_consideration'}
REQUIRED_CLAIM_ASSUMPTIONS = frozenset(_MONEY_ASSUMPTIONS | {'dilution_shares'})


def valuation_claim_errors(assumptions, information_cutoff):
    """Required bridge claims need measured or supported provisional inputs.

    This checks the dated evidence contract, not whether a source semantically
    proves a claim. Research retains that review and its exact original context.
    A cited classification or immateriality estimate may legitimately be zero.
    """
    errors = {}
    assumptions = assumptions if isinstance(assumptions, dict) else {}
    for key in sorted(REQUIRED_CLAIM_ASSUMPTIONS):
        item = assumptions.get(key)
        reason = None
        if not isinstance(item, dict):
            reason = 'missing required claim entry'
        elif item.get('status') not in ('reported', 'derived_reported', 'estimated', 'proxy') or item.get('value') is None:
            reason = 'unresolved claim: ' + str(item.get('method') or 'no supported value')
        else:
            try:
                value = _number(item.get('value'), key)
                if value < 0:
                    raise ValueError('claim magnitude must be nonnegative')
                if not item.get('as_of') or _date(item['as_of']) > _date(information_cutoff):
                    raise ValueError('measurement/assumption date must be at or before ' + information_cutoff)
                if not isinstance(item.get('method'), str) or not item['method'].strip():
                    raise ValueError('nonempty economic method is required')
                refs = item.get('source_refs')
                if not isinstance(refs, list) or not refs or any(not isinstance(ref, dict) or not ref.get('source_id') or not ref.get('unit_id') for ref in refs):
                    raise ValueError('exact original source_id/unit_id citations are required')
            except (ValueError, TypeError, KeyError) as exc:
                reason = str(exc)
        if reason:
            errors[key] = (key + ': ' + reason + '. Supply a dated cited amount, a supported estimated/proxy value, '
                'or an affirmative cited absence/classification/immateriality assessment. Missing disclosure is not zero; '
                'if support remains unavailable, research must remain incomplete.')
    return errors


def _assumption_dimension(key, currency, money_scale, share_scale):
    if key in _MONEY_ASSUMPTIONS:return currency, money_scale
    if key == 'dilution_shares':return 'shares', share_scale
    return ('years' if key == 'transition_years' else 'multiple' if key == 'beta' else 'ratio'), 1


def _configured_assumption(key, entry, currency, money_scale, share_scale):
    """Convert explicitly typed research units into this saved model's units.

    Legacy untyped caller entries remain in model units. New research retains its
    original measurement and conversion; a typed wrong currency is never guessed.
    """
    result=copy.deepcopy(entry)
    expected_unit,expected_scale=_assumption_dimension(key,currency,money_scale,share_scale)
    if 'unit' not in result and 'scale' not in result and 'currency' not in result:return result
    unit=result.get('unit');scale=result.get('scale')
    if result.get('currency',currency)!=currency:
        raise ValueError(f'{key} research currency {result.get("currency")!r} differs from model currency {currency}; an explicit currency conversion is required')
    aliases={'reporting_currency_millions':(currency,1e6),'shares_millions':('shares',1e6)}
    canonical,declared_scale=aliases.get(unit,(unit,scale))
    if canonical!=expected_unit:
        raise ValueError(f'{key} research unit {unit!r} is incompatible with {expected_unit!r}')
    if scale is None or _number(scale,key+' research scale')<=0:
        raise ValueError(f'{key} typed research needs a positive explicit scale')
    if unit in aliases and scale!=declared_scale:
        raise ValueError(f'{key} research scale disagrees with declared {unit}')
    if expected_unit in ('ratio','multiple','years') and scale!=1:
        raise ValueError(f'{key} requires decimal/unitless scale 1, not {scale}')
    original=dict(value=_number(result.get('value'),key),unit=unit,scale=scale,currency=currency)
    result.update(value=original['value']*scale/expected_scale,unit=expected_unit,scale=expected_scale,currency=currency,
        source_measurement=original,unit_conversion=dict(multiplier=scale/expected_scale,
            method='Original researched value times source scale divided by saved model scale; no currency conversion.'))
    return result


def _date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be a finite number')
    return float(value)


def _entry(value, day, method, status='provisional_assumption', source_refs=None, **extra):
    return dict(value=value, as_of=str(day), status=status, source_refs=source_refs or [], method=method, **extra)


def _value(values, roles, role, pid):
    rid = roles.get(role)
    return values.get(rid, {}).get(pid) if rid else None


def _rows(spec):
    return {r['id']: r for r in spec['rows']}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _periods(spec, values, roles, required):
    """Select available financial leaves, never overlapping FY/interim totals."""
    frequency = spec.get('frequency_policy', {}).get('statements')
    leaves = {'annual': {'FY'}, 'half_year': {'H1', 'H2'},
              'quarterly': {'Q1', 'Q2', 'Q3', 'Q4'}}.get(frequency)
    annual_years = set(spec.get('frequency_policy', {}).get('annual_only_years', []))
    annual_years.update(spec.get('forecast_horizon', {}).get('annual_only_years', []))
    def applicable(period):
        if period.get('kind') == '9M':
            return False
        # Preserve disclosed larger actual blocks (for example H1 followed by
        # forecast Q3/Q4), but never replace a missing forecast statement leaf
        # with its FY aggregate. Sales cadence does not define financial cadence.
        if leaves and period.get('status') in ('forecast', 'mixed'):
            expected = {'FY'} if period.get('annual_only') or period.get('fiscal_year') in annual_years else leaves
            return period.get('kind') in expected
        return True
    candidates = [p for p in spec['periods'] if applicable(p)
                  and all(_value(values, roles, k, p['id']) is not None for k in required)]
    def tile(start, end, available):
        if start > end:
            return []
        choices = sorted((q for q in available if q['start'] == start and q['end'] <= end), key=lambda q:q['end'])
        for q in choices:
            rest = tile((_date(q['end'])+timedelta(days=1)).isoformat(), end, available)
            if rest is not None:
                return [q]+rest
        return None
    roots = [p for p in candidates if not any(q['id'] != p['id'] and q['start'] <= p['start']
             and q['end'] >= p['end'] and (q['start'], q['end']) != (p['start'], p['end']) for q in candidates)]
    result = []
    for p in roots:
        available = [q for q in candidates if q['start'] >= p['start'] and q['end'] <= p['end']]
        result.extend(tile(p['start'], p['end'], available) or [p])
    result.sort(key=lambda p: (p['start'], p['end']))
    for left, right in zip(result, result[1:]):
        if left['end'] >= right['start']:
            raise ValueError('Available financial periods overlap; provide a compatible period structure')
    return result


def _forecast_endpoint(spec, day):
    """Read the intended horizon from model metadata, not surviving amounts."""
    annual = [p for p in spec['periods'] if p.get('kind') == 'FY']
    declared = spec.get('forecast_years')
    if declared:
        final_year = max(declared)
        annual = [p for p in annual if p.get('fiscal_year') == final_year]
        if not annual:
            raise ValueError('Declared final forecast year has no explicit FY period boundary')
    else:
        annual = [p for p in annual if p['end'] > day]
    if not annual:
        raise ValueError('No explicit future FY endpoint in the saved model')
    endpoint = max(p['end'] for p in annual)
    if endpoint <= day:
        raise ValueError('Declared forecast horizon ends on or before valuation date; extend the operating model explicitly')
    return endpoint


def _require_period_coverage(periods, start, end, label):
    """Require coverage after an opening/date boundary; no zero-filled gaps."""
    cursor = _date(start) + timedelta(days=1)
    finish = _date(end)
    if cursor > finish:
        return
    for period in sorted(periods, key=lambda p: (p['start'], p['end'])):
        first, last = _date(period['start']), _date(period['end'])
        if last < cursor or first > finish:
            continue
        if first > cursor:
            break
        cursor = last + timedelta(days=1)
        if cursor > finish:
            return
    raise ValueError(label + ' coverage is incomplete from ' + cursor.isoformat() +
                     ' through ' + finish.isoformat() + '; required model periods/components cannot be omitted or replaced by zero')


def _source_snapshot(spec, values, roles, role, day):
    row_map = _rows(spec)
    row = row_map.get(roles.get(role), {})
    seed = row_map.get('opening_proxy_' + str(roles.get(role)), {})
    candidates = []
    for candidate_row in (row, seed):
        if not candidate_row:
            continue
        for p in spec['periods']:
            cell = candidate_row.get('cells', {}).get(p['id'], {})
            value = values.get(candidate_row['id'], {}).get(p['id'])
            if value is not None and p['end'] <= str(day) and cell.get('status', p.get('status')) not in ('forecast', 'mixed'):
                candidates.append((p, cell, value, candidate_row))
    if not candidates:
        return dict(value=None, date=None, status='missing', row_id=roles.get(role), source_refs=[],
                    method='No compatible dated opening stock in saved model; supply a researched input.')
    p, cell, value, selected_row = max(candidates, key=lambda x: (x[0]['end'], x[3]['id'] == row.get('id'), x[0]['kind'] == 'FY'))
    return dict(value=value, date=p['end'], period_id=p['id'], row_id=selected_row.get('id'),
                status=cell.get('status', 'model_derived'), source_refs=copy.deepcopy(cell.get('source_refs', [])),
                method=cell.get('reason') or cell.get('method') or selected_row.get('note') or 'Saved model closing stock; preserve its original actual/estimated status.',
                data_role=cell.get('data_role'), calibration_eligible=cell.get('calibration_eligible'))


def _event_date(event):
    return event.get('accounting_date') or event.get('effective_date')


def _information_dates(spec):
    result = []
    for source in spec.get('sources', []):
        value = source.get('published_at') or source.get('publication_date')
        if value:
            try:
                result.append(_date(str(value)[:10]).isoformat())
            except ValueError:
                pass
    value = spec.get('fx_metadata', {}).get('as_of')
    if value:
        try:
            result.append(_date(str(value)[:10]).isoformat())
        except ValueError:
            pass
    return result


def generate_valuation_inputs(spec, values, company_inputs=None, *, valuation_date,
                              information_cutoff=None, market_inputs=None):
    """Generate reviewable inputs from this company's saved model, without calls.

    Company inputs may contain ``valuation`` with role overrides and researched
    assumptions. Numeric overrides must retain the same dated entry shape.
    No generated company-specific Python configuration is required.
    """
    day = _date(valuation_date).isoformat()
    cutoff = _date(information_cutoff or day).isoformat()
    company_inputs = company_inputs or {}
    config = copy.deepcopy(company_inputs.get('valuation', company_inputs.get('model_configuration', {}).get('valuation', {})))
    roles = dict(DEFAULT_ROLES, **config.get('row_roles', {}))
    currency = spec.get('currency')
    row_map = _rows(spec)
    # Match the cash-flow change's consolidation scope. A cash-flow closing
    # stock can include cash held for sale which the face balance sheet omits.
    if 'cash' not in config.get('row_roles', {}) and 'closing_cash' in row_map:
        roles['cash'] = 'closing_cash'
    scope=spec.get('cash_scope_contract',{})
    if scope.get('valuation_cash_role'):
        for key,field in [('cash','valuation_cash_role'),('cash_change','valuation_cash_change_role')]:
            if key not in config.get('row_roles',{}):roles[key]=scope[field]
    equity_claim=spec.get('cashflow_presentation_contract',{}).get('noncommon_equity_claim_role')
    if equity_claim:
        if config.get('row_roles',{}).get('noncommon_equity',equity_claim)!=equity_claim:
            raise ValueError('Noncommon equity must use the model declared claim role; do not reclassify it as debt or another claim')
        roles['noncommon_equity']=equity_claim
    revenue_unit = row_map.get(roles['revenue'], {}).get('unit', '')
    share_unit = row_map.get(roles['shares'], {}).get('unit', '')
    scales = {'': 1., 'm': 1e6, 'bn': 1e9, 'k': 1e3}
    suffix = revenue_unit[len(currency):] if currency and revenue_unit.startswith(currency) else None
    if suffix not in scales:
        raise ValueError(f'Cannot infer reporting-money scale from {revenue_unit!r}; supply a supported saved row unit')
    if equity_claim and row_map.get(equity_claim,{}).get('unit')!=revenue_unit:
        raise ValueError('Noncommon equity claim must use the reporting currency and money scale')
    share_scales = {'shares': 1., 'shares_m': 1e6, 'shares_k': 1e3, 'shares_bn': 1e9}
    if share_unit not in share_scales:
        raise ValueError(f'Cannot infer outstanding-share scale from {share_unit!r}')
    snapshots = {role: _source_snapshot(spec, values, roles, role, day)
                 for role in ('cash', 'cash_like', 'debt', 'shares', 'associates', 'nci')+ (('noncommon_equity',) if equity_claim else ())}
    tax_values = [(p['end'], _value(values, roles, 'tax_rate', p['id'])) for p in spec['periods']]
    tax_values = [(d, v) for d, v in tax_values if v is not None]
    tax = sorted(tax_values)[-1][1] if tax_values else .25
    margins = []
    for p in spec['periods']:
        if p.get('kind') != 'FY' or p['end'] > day:
            continue
        rev = _value(values, roles, 'revenue', p['id'])
        op = _value(values, roles, 'operating_profit', p['id'])
        if rev and op is not None:
            # Prefer a completely specified lease recast; otherwise preserve the
            # reported margin and disclose that it is only a terminal proxy.
            rou = _value(values, roles, 'rou_depreciation', p['id'])
            principal = _value(values, roles, 'lease_principal', p['id'])
            interest = _value(values, roles, 'lease_interest', p['id'])
            if all(x is not None for x in (rou, principal, interest)):
                op += rou + principal - interest
            margins.append((p['end'], op / rev))
    terminal_margin = statistics.median(v for _, v in sorted(margins)[-3:]) if margins else .1
    method = 'Unresearched generic starting assumption, not an observed market input; replace through the typed research interface.'
    defaults = dict(risk_free_rate=.03, equity_risk_premium=.05, beta=1., debt_spread=.015,
                    debt_weight=.2, tax_rate=tax, terminal_growth=.02, terminal_roic=.1,
                    terminal_margin=terminal_margin, transition_years=5, dilution_shares=0.,
                    other_claims=0., other_assets=0., restricted_cash=0., pension_claim=0.,
                    deferred_consideration=0.)
    # Scenario defaults belong to the selected information set. Discounting and
    # elapsed-cash timing still use the independently specified valuation date.
    # Explicit researched entries below retain their own original dates.
    assumptions = {k: _entry(v, cutoff, method) for k, v in defaults.items()}
    assumptions['tax_rate'].update(method='Saved effective-tax policy used as provisional unlevered tax rate; financing and exceptional tax differences need review.', status='model_policy_proxy')
    assumptions['terminal_margin'].update(method='Median of up to three available historical annual operating margins, cash-lease recast where disclosed. Provisional normalisation, not a permanent forecast-margin hold.', status='historical_normalisation_proxy')
    for key in REQUIRED_CLAIM_ASSUMPTIONS:
        assumptions[key].update(status='unresolved_zero_scenario', method='Unmeasured claim/adjustment: zero is an explicit provisional scenario, not a finding of absence. Requires company evidence review.')
    for key, value in config.get('assumptions', {}).items():
        if key not in assumptions:
            raise ValueError(f'Unknown valuation assumption {key}')
        assumptions[key] = _configured_assumption(key,value,currency,scales[suffix],share_scales[share_unit])
    events = []
    for raw in spec.get('scope_event_audit', []):
        if raw.get('enabled') is False:
            continue
        event = copy.deepcopy(raw)
        event['date'] = _event_date(raw)
        flows = raw.get('cash_flows', {})
        event['net_cash'] = _entry(sum(flows.values()) if flows else None, cutoff,
            'Modelled net acquisition/disposal cash, including cash transferred. Applied once at the accounting/closing date.',
            raw.get('accounting_status', 'provisional_event'), raw.get('source_refs', []))
        gain_tax = -(raw.get('gain_loss') or 0.)*raw.get('tax_rate', 0.)
        tax_cash = 0. if gain_tax == 0 else None
        if gain_tax:
            tax_periods = [p for p in spec['periods'] if event['date'] and p['start'] <= event['date'] <= p['end']
                           and values.get('cash_tax_ratio', {}).get(p['id']) is not None]
            if tax_periods:
                tax_pid = min(tax_periods, key=lambda p: (_date(p['end'])-_date(p['start'])).days)['id']
                current_share = 1-values.get('deferred_tax_share', {}).get(tax_pid, 0.)
                tax_cash = gain_tax*current_share*values['cash_tax_ratio'][tax_pid]
        event['cash_tax'] = copy.deepcopy(raw['cash_tax']) if isinstance(raw.get('cash_tax'), dict) else _entry(
            raw.get('cash_tax', tax_cash), cutoff,
            'Gain tax uses the model current/deferred split and cash-tax payment ratio, not marginal tax alone. Closing-date payment is a provisional timing convention unless explicitly researched.',
            raw.get('accounting_status', 'provisional_event'), raw.get('source_refs', []))
        event['model_net_cash'] = event['net_cash']['value']
        event['model_cash_tax'] = event['cash_tax']['value']
        retained = raw.get('balance_movements', {}).get('associates', 0)
        if raw.get('retained_operation') and retained > 0:
            event['retained_interest_value'] = _entry(retained, cutoff,
                'Initial recognised retained-interest value is a provisional economic-value proxy at creation; already an ownership-adjusted amount.',
                'carrying_value_proxy', raw.get('source_refs', []))
        events.append(event)
    result = dict(version=VERSION, company=spec.get('company'), valuation_date=day,
        information_cutoff=cutoff, currency=currency, money_scale=scales[suffix],
        share_scale=share_scales[share_unit], lease_policy='operating',
        profit_basis='statutory_operating_profit', sbc_policy='retain_expense_no_addback',
        discount_convention='mid_period_ACT_365', row_roles=roles, assumptions=assumptions,
        cash_scope=('Gross cash from the cited cash-scope bridge: add back borrowing netted in reported CF cash while retaining that borrowing once in the full debt claim. Elapsed cash uses the matching gross cash-change row. Cash-flow scope does not establish cash accessibility; each cited nondebt component requires review, and restricted or unavailable cash remains a separate valuation claim.'
            if scope.get('valuation_cash_role') else 'Cash-flow closing-stock scope, including separately held-for-sale cash where the model reconciles it; restricted/unavailable cash is a separate claim.'),
        balance_bridge=dict(snapshots=snapshots, dated_movements=[],
            method='Saved opening stocks plus estimated elapsed model movements; portfolio events occur on explicit dates.'),
        events=events, adjustments=[],
        market=dict(price=_entry(None, cutoff, 'No dated market quote supplied.', 'missing'),
                    currency=currency, price_unit_scale=1.),
        sensitivity=dict(wacc_shifts=[-.01, 0., .01], growth_shifts=[-.005, 0., .005],
                         event_cash_multipliers=[.8, 1., 1.2]),
        methodology_references=copy.deepcopy(METHODOLOGY_REFERENCES),
        source_model_digest=_digest(dict(spec=spec, values=values)))
    result['model_information_date'] = max(_information_dates(spec), default=None)
    result['research_limitations'] = copy.deepcopy(config.get('limitations', config.get('research', {}).get('limitations', [])))
    for key in ('balance_bridge', 'events', 'market', 'adjustments', 'profit_basis', 'sensitivity'):
        if key in config:
            result[key] = config[key]
    if market_inputs:
        result['market'].update(copy.deepcopy(market_inputs))
    return result


def valuation_input_contract(spec, inputs):
    """Stable field paths, data types and economic units for non-LLM callers."""
    fields = []
    for key, item in inputs['assumptions'].items():
        unit,scale=_assumption_dimension(key,inputs['currency'],inputs['money_scale'],inputs['share_scale'])
        field=copy.deepcopy(item)
        field.update(id='assumptions.' + key,writable=True,value_type='integer' if key=='transition_years' else 'number',
            unit=unit,scale=scale,bounds=list(_BOUNDS[key]))
        fields.append(field)
    market_field=copy.deepcopy(inputs['market']['price'])
    market_field.update(id='market.price',writable=True,value_type='number',unit=inputs['market']['currency'],
        scale=inputs['market'].get('price_unit_scale',1),bounds=[0,None])
    fields.append(market_field)
    for key in ('valuation_date', 'information_cutoff', 'currency', 'money_scale', 'share_scale',
                'lease_policy', 'profit_basis', 'sbc_policy', 'discount_convention', 'cash_scope', 'row_roles', 'source_model_digest', 'model_information_date'):
        fields.append(dict(id=key, writable=False, value=copy.deepcopy(inputs.get(key)),
                           value_type='structural', reason='New dated valuation setup or model research required.'))
    for role, item in inputs['balance_bridge']['snapshots'].items():
        fields.append(dict(id='balance_bridge.snapshots.' + role, writable=False,
                           value_type='dated_evidence', value=copy.deepcopy(item)))
    return dict(version=VERSION, company=spec.get('company'), valuation_date=inputs['valuation_date'],
                model_digest=inputs.get('source_model_digest'), fields=fields)


def apply_valuation_payload(inputs, payload):
    """Apply strict dated scalar assumption edits; never mutate the saved model."""
    if payload.get('version') != VERSION or payload.get('valuation_date') != inputs['valuation_date']:
        raise ValueError('Valuation payload version/date does not match the saved valuation')
    if payload.get('source_model_digest') != inputs.get('source_model_digest'):
        raise ValueError('Valuation payload model digest does not match')
    if payload.get('company', inputs.get('company')) != inputs.get('company'):
        raise ValueError('Valuation payload company does not match')
    fields = {f['id']:f for f in valuation_input_contract({'company':inputs.get('company')}, inputs)['fields']}
    result = copy.deepcopy(inputs)
    changes = payload.get('changes')
    if not isinstance(changes, list):
        raise ValueError('Valuation changes must be a list')
    seen = set()
    for change in changes:
        key = change.get('id', '')
        if key in seen:
            raise ValueError('Duplicate valuation override')
        seen.add(key)
        if key.startswith('assumptions.') and key.split('.')[1] in _BOUNDS:
            name = key.split('.')[1]
            if key != 'assumptions.' + name:
                raise ValueError('Invalid valuation input path')
            target = result['assumptions']; field = name
        elif key == 'market.price':
            target = result['market']; field = 'price'
        else:
            raise ValueError(f'Read-only or unknown valuation field {key}')
        if change.get('unit') != fields[key]['unit'] or change.get('scale') != fields[key]['scale']:
            raise ValueError('Valuation edit unit/scale must match the typed contract exactly')
        if not change.get('method') or not change.get('as_of') or not change.get('status'):
            raise ValueError('Valuation edits require as_of, status and method')
        if _date(change['as_of']) > _date(inputs['information_cutoff']):
            raise ValueError('Valuation input is after information cutoff')
        _number(change.get('value'), key)
        target[field] = {k: copy.deepcopy(change[k]) for k in ('value', 'as_of', 'status', 'method')}
        target[field]['source_refs'] = copy.deepcopy(change.get('source_refs', []))
    _assumptions(result)
    return result


def _assumptions(inputs):
    result = {}
    for key, (lo, hi) in _BOUNDS.items():
        item = inputs['assumptions'][key]
        value = _number(item.get('value'), key)
        unit,scale=_assumption_dimension(key,inputs['currency'],inputs['money_scale'],inputs['share_scale'])
        if 'unit' in item and (item['unit']!=unit or item.get('scale')!=scale or item.get('currency',inputs['currency'])!=inputs['currency']):
            raise ValueError(f'{key} unit/scale/currency differs from the saved valuation contract')
        if not item.get('method') or not item.get('status') or not item.get('as_of'):
            raise ValueError(f'{key} needs dated provenance and method')
        if _date(item['as_of']) > _date(inputs['information_cutoff']):
            raise ValueError(f'{key} is after information cutoff')
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            raise ValueError(f'{key} is outside allowed range')
        if key == 'transition_years' and value != int(value):
            raise ValueError('transition_years must be an integer')
        result[key] = value
    return result


def _diag(items, code, message, severity='warning'):
    items.append(dict(code=code, severity=severity, message=message))


def _event_amount(event, key):
    item = event.get(key)
    return item.get('value') if isinstance(item, dict) else item


def _active_events(inputs):
    return [event for event in inputs.get('events', []) if event.get('enabled', True)]


def _validate_event_inputs(inputs, diagnostics):
    """Unknown transaction cash cannot establish an accepted common-equity value.

    A completed event needs no reconstructed consideration when supported later
    opening stocks already contain all its relevant valuation counterparts.
    """
    day = _date(inputs['valuation_date'])
    snapshots = inputs['balance_bridge']['snapshots']
    for event in _active_events(inputs):
        label = str(event.get('id', 'unnamed'))
        if not event.get('date'):
            _diag(diagnostics, 'unresolved_event_date:' + label,
                  'Event ' + label + ' has no dated closing/accounting boundary; its elapsed and future cash effects remain unresolved.', 'error')
            continue
        eventday = _date(event['date'])
        relevant = {'cash'}
        movements = event.get('balance_movements', {})
        for role in snapshots:
            if inputs['row_roles'].get(role) in movements:
                relevant.add(role)
        if event.get('retained_operation') or event.get('retained_interest_value') is not None:
            relevant.add('associates')
        # An unresolved accounting footprint cannot establish which stocks are
        # unaffected. Require the complete opening bridge in that case.
        if event.get('material_unresolved'):
            relevant.update(snapshots)
        captured = eventday <= day
        for role in relevant:
            snap = snapshots.get(role, {})
            captured = captured and (snap.get('value') is not None and bool(snap.get('date'))
                and eventday <= _date(snap['date']) <= day
                and snap.get('status') in ('actual', 'derived_actual', 'reported', 'observed')
                and bool(snap.get('source_refs')) and bool(snap.get('method')))
            if snap.get('value') is not None:
                _number(snap['value'], 'opening ' + role)
        if captured:
            _diag(diagnostics, 'event_in_opening_balances:' + label,
                  'Completed event ' + label + ' is already included in supported later opening ' + ', '.join(sorted(relevant)) + ' stocks; its consideration is not added again.')
            continue
        for key in ('net_cash', 'cash_tax'):
            item = event.get(key)
            metadata = item if isinstance(item, dict) else event
            amount = _event_amount(event, key)
            if amount is not None:
                _number(amount, 'Event ' + label + ' ' + key)
            if (any(key in metadata for key in ('unit', 'scale')) and
                    (metadata.get('unit') != inputs['currency'] or metadata.get('scale') != inputs['money_scale'])) or metadata.get('currency', inputs['currency']) != inputs['currency']:
                raise ValueError('Event ' + label + ' ' + key + ' unit/scale differs from the valuation contract')
            if metadata.get('as_of') and _date(metadata['as_of']) > _date(inputs['information_cutoff']):
                raise ValueError('Event ' + label + ' ' + key + ' is after information cutoff')
            unsupported_zero = amount == 0 and (not metadata.get('source_refs') or not metadata.get('method'))
            if amount is None or metadata.get('status') in ('missing', 'unresolved_zero_scenario') or unsupported_zero:
                _diag(diagnostics, 'unresolved_event_' + key + ':' + label,
                      'Event ' + label + ' requires quantified, supported ' + key + ' for its elapsed or future valuation effect. Missing amounts and unsupported zeros leave conditional arithmetic incomplete.', 'error')


def _date_fraction(period, day):
    start, end = _date(period['start']), _date(period['end'])
    return max(0., min(1., ((_date(day) - start).days + 1) / ((end - start).days + 1)))


def _opening_bridge(spec, values, inputs, diagnostics):
    roles = inputs['row_roles']; day = inputs['valuation_date']
    periods = _periods(spec, values, roles, ('cash_change',))
    result = {}
    events = _active_events(inputs)
    movements = inputs['balance_bridge'].get('dated_movements', [])
    for movement in movements:
        if movement.get('role')!='noncommon_equity':continue
        matches=[m for m in movements if m.get('role')=='cash' and m.get('date')==movement.get('date')
            and m.get('amount')==movement.get('amount') and m.get('included_in_model',True)==movement.get('included_in_model',True)
            and (not movement.get('event_id') or m.get('event_id')==movement['event_id'])]
        if len(matches)!=1:
            raise ValueError('Dated noncommon equity issuance/redemption needs exactly one matching dated cash movement; distributions are separate from principal')
    tax_rate = _assumptions(inputs)['tax_rate']
    for role, snap in inputs['balance_bridge']['snapshots'].items():
        if snap.get('value') is None:
            if role in ('cash', 'debt', 'shares','noncommon_equity'):
                raise ValueError(f'Missing dated opening {role}; supply research, not a terminal stock')
            _diag(diagnostics, 'missing_' + role, f'No measured {role}; conditional zero arithmetic cannot establish an accepted valuation.', 'error')
            result[role] = dict(value=0., opening=None, movements=[], status='unresolved_zero_scenario')
            continue
        opening = _number(snap['value'], 'opening ' + role)
        if (snap.get('status') in ('unresolved_zero_scenario','missing')
                or opening==0 and (not snap.get('source_refs') or not snap.get('method'))):
            _diag(diagnostics,'unresolved_opening_'+role,
                'Opening '+role+' is unresolved or an unsupported zero. Supply cited absence, immateriality or a supported estimate; conditional arithmetic does not establish an accepted valuation.','error')
        if role=='noncommon_equity' and (opening<0 or not snap.get('source_refs') or not snap.get('method')):
            raise ValueError('Noncommon equity opening claim requires a nonnegative amount, dated source evidence and a carrying-value method')
        snapdate = snap.get('date')
        if not snapdate or snapdate > day:
            raise ValueError(f'Opening {role} is after valuation date or undated')
        detail = []; total = opening
        if role == 'cash':
            _require_period_coverage(periods, snapdate, day, 'Elapsed cash bridge')
            for p in periods:
                if p['end'] <= snapdate or p['start'] > day:
                    continue
                fraction = _date_fraction(p, day) - _date_fraction(p, snapdate)
                eventcash = sum((e.get('model_net_cash', _event_amount(e, 'net_cash')) or 0.) + (e.get('model_cash_tax', _event_amount(e, 'cash_tax')) or 0.)
                    for e in events if e.get('date') and p['start'] <= e['date'] <= p['end'])
                # User-supplied dated movements replace the same portion of the
                # period's total change, rather than adding it a second time.
                scheduled = sum(_number(m['amount'], 'dated cash movement') for m in movements
                                if m['role'] == role and p['start'] <= m['date'] <= p['end']
                                and m.get('included_in_model', True))
                amount = (_value(values, roles, role='cash_change', pid=p['id']) - eventcash - scheduled) * fraction
                after = _scope_stub(inputs, p, day, tax_rate, 1-_date_fraction(p, day))
                before = _scope_stub(inputs, p, snapdate, tax_rate, 1-_date_fraction(p, snapdate))
                scope_timing = sum(x['amount'] for x in before)-sum(x['amount'] for x in after)
                amount += scope_timing
                total += amount
                detail.append(dict(kind='estimated_elapsed_model_cash', period_id=p['id'],
                    fraction=fraction, amount=amount, excluded_dated_events=eventcash, scope_timing_adjustment=scope_timing,
                    method='Uniform accrual of remaining period cash movement; event, distribution and financing dates replace proration when supplied.'))
            for event in events:
                if event.get('date') and snapdate < event['date'] <= day:
                    amount = (_event_amount(event, 'net_cash') or 0.) + (_event_amount(event, 'cash_tax') or 0.)
                    total += amount
                    detail.append(dict(kind='dated_event', event_id=event['id'], date=event['date'], amount=amount))
        elif role in ('debt', 'shares','noncommon_equity','cash_like'):
            endpoints = [p for p in spec['periods'] if p['end'] > snapdate and
                         _value(values, roles, role, p['id']) is not None]
            if day > snapdate and not any(p['end'] >= day for p in endpoints):
                raise ValueError('Opening ' + role + ' bridge has no model stock endpoint reaching valuation date ' +
                                 day + '; a missing elapsed movement cannot be assumed unchanged')
            if endpoints and day > snapdate:
                previous_date, previous_value = snapdate, opening
                for endpoint in sorted(endpoints, key=lambda p:p['end']):
                    if endpoint['end'] <= previous_date or previous_date >= day:
                        continue
                    fraction = min(1., (_date(day)-_date(previous_date)).days / (_date(endpoint['end'])-_date(previous_date)).days)
                    endpoint_value = _value(values, roles, role, endpoint['id'])
                    delta = endpoint_value-previous_value
                    scheduled = sum(_number(m['amount'], 'dated stock movement') for m in movements
                                    if m['role'] == role and previous_date < m['date'] <= endpoint['end'] and m.get('included_in_model', True))
                    dated_scope = [(e, e.get('balance_movements', {}).get('nonlease_debt', 0.)) for e in events
                                   if role == 'debt' and e.get('date') and previous_date < e['date'] <= endpoint['end']]
                    amount = (delta-scheduled-sum(v for _, v in dated_scope))*fraction
                    total += amount
                    detail.append(dict(kind='estimated_model_stock_interpolation', period_id=endpoint['id'],
                                       start=previous_date, fraction=fraction, amount=amount))
                    for event, amount in dated_scope:
                        if event['date'] <= day:
                            total += amount
                            detail.append(dict(kind='dated_scope_debt', event_id=event['id'], date=event['date'], amount=amount))
                    previous_date, previous_value = endpoint['end'], endpoint_value
                _diag(diagnostics, 'estimated_' + role + '_bridge', f'{role} between reported snapshots is interpolated from the saved model; dated transaction evidence can replace it.')
        elif role in ('associates', 'nci'):
            for event in events:
                if event.get('date') and snapdate < event['date'] <= day:
                    amount = event.get('balance_movements', {}).get('associates' if role == 'associates' else 'nci_equity', 0.)
                    total += amount
                    if amount:
                        detail.append(dict(kind='dated_nonoperating_interest_movement', event_id=event['id'], date=event['date'], amount=amount))
        for m in movements:
            if m['role'] == role and snapdate < m['date'] <= day:
                amount = _number(m['amount'], 'dated movement')
                total += amount; detail.append(dict(kind='dated_researched_movement', **copy.deepcopy(m)))
        result[role] = dict(value=total, opening=copy.deepcopy(snap), movements=detail,
                            status='estimated_at_valuation_date' if detail else snap.get('status'))
        if snap.get('status') not in ('actual', 'derived_actual', 'reported', 'observed'):
            _diag(diagnostics, 'estimated_opening_' + role, f"Opening {role} is a labelled {snap.get('status')} model seed, not a separately reported closing balance. {snap.get('method', '')}")
    if result['shares']['value'] <= 0:
        raise ValueError('Valuation-date outstanding shares must be positive')
    _diag(diagnostics, 'elapsed_cash_estimate', 'Opening cash includes estimated cash earned/spent before valuation date; only remaining operating cash flows enter DCF. Unspecified distribution/financing timing is provisional.')
    _diag(diagnostics, 'cash_scope', inputs.get('cash_scope', 'Opening cash must match the saved cash-change consolidation scope.'))
    for role in ('associates', 'nci'):
        _diag(diagnostics, role + '_carrying_proxy', f'Opening {role} uses carrying value as an explicitly provisional economic-value proxy; earnings are excluded from FCFF / consolidated operating cash flows include minority operations respectively.')
    if 'noncommon_equity' in result:
        _diag(diagnostics,'noncommon_equity_carrying_proxy','Noncommon equity is a separate senior claim on common shareholders, using its sourced dated carrying amount as a provisional economic-value proxy. It is not debt, not an operating expense, and must be excluded from other_claims to avoid double counting.')
    return result


def _components(spec, values, inputs, p, assumptions):
    roles = inputs['row_roles']; pid = p['id']
    v = {key: _number(_value(values, roles, key, pid), key + ' ' + pid) for key in _FCFF_REQUIRED}
    if v['lease_principal'] > 0 or v['lease_interest'] < 0 or v['owned_depreciation'] < 0 or v['rou_depreciation'] < 0 or v['amortization'] < 0:
        raise ValueError('Lease principal must be signed outflow; depreciation and lease interest positive expenses')
    if v['capex_ppe'] > 0 or v['capex_intangibles'] > 0:
        raise ValueError('Capex roles must be signed cash outflows')
    reversal = _value(values, roles, 'portfolio_noncash', pid)
    if reversal is None:
        reversal = -sum(e.get('gain_loss') or 0. for e in _active_events(inputs)
                        if e.get('date') and p['start'] <= e['date'] <= p['end'])
    normal_op = valuation_equation('normalized_operating_profit', dict(operating_profit=v['operating_profit'], noncash_portfolio_reversal=reversal))
    lease_cost = valuation_equation('cash_lease_cost', v)
    after_lease = valuation_equation('operating_profit_after_cash_leases', dict(normalized_operating_profit=normal_op,
        rou_depreciation_reversal=v['rou_depreciation'], cash_lease_cost=lease_cost))
    adjustments = 0.
    for item in inputs.get('adjustments', []):
        if item.get('period_id') == pid:
            if not item.get('method') or not item.get('source_refs'):
                raise ValueError('Operating cash adjustments require a method and evidence')
            if item.get('includes_sbc'):
                raise ValueError('SBC addback is incompatible with retain-expense policy')
            adjustments += _number(item['amount'], 'cash adjustment')
    tax = valuation_equation('unlevered_tax', dict(operating_profit_after_cash_leases=after_lease, tax_rate=assumptions['tax_rate']))
    nopat = valuation_equation('nopat', dict(operating_profit_after_cash_leases=after_lease, unlevered_tax=tax))
    eligible_da = valuation_equation('eligible_da', v)
    fcff = valuation_equation('full_period_fcff', dict(nopat=nopat, eligible_da=eligible_da,
        capex_ppe=v['capex_ppe'], capex_intangibles=v['capex_intangibles'],
        operating_working_capital_cash=v['working_capital_cash'], other_cash_adjustments=adjustments))
    return dict(period_id=pid, start=p['start'], end=p['end'], revenue=v['revenue'],
        operating_profit=v['operating_profit'], noncash_portfolio_reversal=reversal,
        normalized_operating_profit=normal_op, rou_depreciation_reversal=v['rou_depreciation'],
        lease_principal=v['lease_principal'], lease_interest=v['lease_interest'], tax_rate=assumptions['tax_rate'],
        cash_lease_cost=lease_cost, operating_profit_after_cash_leases=after_lease,
        unlevered_tax=tax, nopat=nopat, eligible_da=eligible_da,
        owned_depreciation=v['owned_depreciation'], amortization=v['amortization'],
        capex_ppe=v['capex_ppe'], capex_intangibles=v['capex_intangibles'],
        operating_working_capital_cash=v['working_capital_cash'], other_cash_adjustments=adjustments,
        sbc_addback=0., full_period_fcff=fcff,
        economic_reinvestment=-(v['capex_ppe']+v['capex_intangibles']+v['working_capital_cash'])-eligible_da-adjustments)


def _cashflow_reconciliation(spec, values, component):
    """Explain the difference from statement CFO without changing either total."""
    pid = component['period_id']; cfo = values.get('cfo', {}).get(pid)
    if cfo is None:
        return dict(period_id=pid, status='unavailable', reason='No saved statement CFO for comparison')
    expected = spec.get('cashflow_component_contract', {}).get('cfo_components') or [
        'cf_net_profit', 'da', 'sbc', 'cf_associates', 'associate_dividends', 'cf_tax_timing', 'wc_cash',
        'impairment', 'disposal_result_cf', 'other_noncash_ex_sbc', 'other_operating_assets_liabilities_cf',
        'cf_finance_timing', 'cfo_portfolio_noncash', 'cfo_fx_noncash']
    available = {rid: values.get(rid, {}).get(pid) for rid in expected if values.get(rid, {}).get(pid) is not None}
    essential = ('cf_net_profit', 'da', 'sbc', 'cf_associates', 'associate_dividends', 'cf_tax_timing', 'wc_cash')
    missing = [rid for rid in essential if rid not in available]
    if missing:
        return dict(period_id=pid, status='incomplete', statement_cfo=cfo,
                    missing_components=missing, reason='No fabricated decomposition of the saved CFO total')
    known = set(essential)
    bridge = dict(replace_net_profit_with_unlevered_operating_profit=component['nopat']-available['cf_net_profit'],
        exclude_rou_from_da_addback=component['eligible_da']-available['da'],
        retain_sbc_economic_cost=-available['sbc'],
        remove_associate_cash_and_accounting_adjustments=-available['cf_associates']-available['associate_dividends'],
        replace_reported_tax_timing=-available['cf_tax_timing'],
        operating_working_capital_basis=component['operating_working_capital_cash']-available['wc_cash'],
        remove_other_statement_adjustments=-sum(v for k, v in available.items() if k not in known),
        explicit_dcf_cash_adjustments=component['other_cash_adjustments'])
    cash_after_capex = cfo+component['capex_ppe']+component['capex_intangibles']
    reconstructed = cash_after_capex+sum(bridge.values())
    residual = component['full_period_fcff']-reconstructed
    return dict(period_id=pid, status='reconciled' if abs(residual)<1e-6 else 'unresolved',
        statement_cfo=cfo, statement_cash_after_capex=cash_after_capex,
        cfo_components=available, cfo_component_residual=cfo-sum(available.values()),
        adjustments=bridge, reconstructed_fcff=reconstructed, model_fcff=component['full_period_fcff'],
        residual=residual, method='Replace the statement net-profit/tax/finance/associate bridge with unlevered operating economics; retain SBC cost and cash leases. Residuals remain visible, never balancing adjustments.')


def _present(component, valuation_date, wacc, remaining_fraction=1.):
    start = max(_date(component['start']), _date(valuation_date) + timedelta(days=1))
    end = _date(component['end'])
    years = ((start - _date(valuation_date)).days + (end - _date(valuation_date)).days) / 2 / 365.
    factor = valuation_equation('discount_factor', dict(wacc=wacc, discount_years=years))
    remaining = valuation_equation('remaining_fcff', dict(full_period_fcff=component['full_period_fcff'], remaining_fraction=remaining_fraction,
                                                        scope_timing_adjustment=component.get('scope_timing_adjustment', 0.)))
    component.update(remaining_fraction=remaining_fraction, remaining_fcff=remaining,
        discount_years=years, discount_factor=factor,
        present_value=valuation_equation('present_value', dict(remaining_fcff=remaining, discount_factor=factor)))
    return component


def _scope_stub(inputs, period, day, tax_rate, fraction):
    """Reallocate known event operating contributions inside a financial stub.

    Uses the operating engine's disclosed/scenario seasonality and annual cash
    economics; does not invent an event's cash-lease/capex/WC split.
    """
    if fraction == 1:
        return []
    from .integrated import scope_period_inclusion
    details = []
    for event in _active_events(inputs):
        effective = event.get('effective_date')
        if not effective or not period['start'] < effective <= period['end']:
            continue
        revenue = event.get('annual_revenue')
        costs = event.get('annual_cash_costs')
        if revenue is None or not costs:
            details.append(dict(event_id=event['id'], amount=0., status='unresolved',
                                method='Within-period scope event lacks annual cash economics; remaining stub includes an unresolved uniform timing approximation.'))
            continue
        eligible_da = sum(event.get('annual_da_by_role', {}).get(k, 0.) for k in ('owned_ppe_depreciation', 'amortization'))
        annual_known_cash = (revenue-sum(costs.values()))*(1-tax_rate)+eligible_da*tax_rate
        year_days = 366 if _date(period['end']).year % 4 == 0 and (_date(period['end']).year % 100 != 0 or _date(period['end']).year % 400 == 0) else 365
        full = scope_period_inclusion(event, period['start'], period['end'], year_days)
        remaining = scope_period_inclusion(event, (_date(day)+timedelta(days=1)).isoformat(), period['end'], year_days)
        amount = annual_known_cash*(remaining-full*fraction)
        details.append(dict(event_id=event['id'], amount=amount, annual_known_cash_contribution=annual_known_cash,
            full_period_inclusion=full, remaining_inclusion=remaining, effective_date=effective,
            status='estimated_event_timing', method='Reallocate existing event revenue/cash-cost/eligible-DA contributions using the operating engine seasonality. Event-specific lease cash, capex, WC and organic/FX interaction remain uniform where unprovided.'))
    return details


def _future_year(start, offset):
    day = _date(start)
    try:
        return day.replace(year=day.year+offset)
    except ValueError:
        return day.replace(year=day.year+offset, day=28)


def value_company(spec, values, inputs, *, include_sensitivities=True, _wacc_shift=0., _growth_shift=0., _evaluated_digest=None):
    """Calculate FCFF, dated event claims and fair value using Python alone.

    Same-function scenarios shift discount inputs or underlying terminal growth;
    terminal reinvestment is recalculated on every call.
    """
    if inputs.get('version') != VERSION:
        raise ValueError('Unsupported valuation input version')
    evaluated_digest = _evaluated_digest or _digest(dict(spec=spec, values=values))
    day = _date(inputs['valuation_date']).isoformat()
    if _date(inputs['information_cutoff']) > _date(day):
        raise ValueError('Information cutoff cannot be later than valuation date')
    available_dates = _information_dates(spec)
    if available_dates and max(available_dates) > inputs['information_cutoff']:
        raise ValueError('Saved model sources/FX snapshot contain information after the valuation cutoff; use a compatible historical vintage')
    if inputs.get('lease_policy') != 'operating' or inputs.get('sbc_policy') != 'retain_expense_no_addback':
        raise ValueError('Supported convention: operating cash leases and SBC retained as economic expense')
    if inputs.get('profit_basis') != 'statutory_operating_profit':
        raise ValueError('Adjusted EBIT needs an explicit amortisation bridge before it can be valued; statutory operating profit is required')
    if inputs.get('currency') != spec.get('currency'):
        raise ValueError('DCF/model currency mismatch; translate the full model or provide a separate explicit currency bridge')
    declared_claim=spec.get('cashflow_presentation_contract',{}).get('noncommon_equity_claim_role')
    if declared_claim and (inputs.get('row_roles',{}).get('noncommon_equity')!=declared_claim
            or 'noncommon_equity' not in inputs.get('balance_bridge',{}).get('snapshots',{})):
        raise ValueError('Declared noncommon equity claim is missing from the common-equity valuation bridge')
    for key in ('money_scale', 'share_scale'):
        if _number(inputs.get(key), key) <= 0:
            raise ValueError(key + ' must be positive')
    row_map = _rows(spec)
    expected_money = {inputs['currency']:1., inputs['currency']+'k':1e3, inputs['currency']+'m':1e6, inputs['currency']+'bn':1e9}
    expected_shares = {'shares':1., 'shares_k':1e3, 'shares_m':1e6, 'shares_bn':1e9}
    if expected_money.get(row_map.get(inputs['row_roles']['revenue'], {}).get('unit')) != inputs['money_scale']:
        raise ValueError('Reporting-money scale disagrees with saved model units')
    if expected_shares.get(row_map.get(inputs['row_roles']['shares'], {}).get('unit')) != inputs['share_scale']:
        raise ValueError('Share scale disagrees with saved outstanding-share units')
    a = _assumptions(inputs); diagnostics = []
    _validate_event_inputs(inputs, diagnostics)
    for key,item in inputs['assumptions'].items():
        if item.get('status') in ('unresolved_zero_scenario','missing') or (key in REQUIRED_CLAIM_ASSUMPTIONS and item.get('value')==0
                and (not item.get('source_refs') or not item.get('method'))):
            _diag(diagnostics,'unresolved_'+key,'Unresolved '+key+' cannot be substituted with zero for an accepted valuation; supply cited absence, immateriality or an explicit supported estimate. Conditional arithmetic is diagnostic only.','error')
    if not available_dates:
        _diag(diagnostics, 'unverified_information_vintage', 'Saved model has no verified publication/snapshot dates; information-cutoff compatibility is unverified.')
    cost_equity = valuation_equation('cost_of_equity', a)
    cost_debt = valuation_equation('pre_tax_cost_of_debt', a)
    wacc = valuation_equation('wacc', dict(a, cost_of_equity=cost_equity, pre_tax_cost_of_debt=cost_debt, wacc_shift=_wacc_shift))
    growth = a['terminal_growth'] + _growth_shift
    if wacc <= growth or wacc <= 0:
        raise ValueError('WACC must be positive and strictly greater than terminal growth')
    if growth < 0:
        raise ValueError('Negative perpetual growth needs an explicit asset-release policy; this ROIC terminal convention requires nonnegative growth')
    reinvestment_rate = valuation_equation('reinvestment_rate', dict(growth=growth, roic=a['terminal_roic']))
    if reinvestment_rate > 1:
        raise ValueError('Terminal growth cannot exceed terminal ROIC under the supported sustainable reinvestment policy')
    roles = inputs['row_roles']
    periods = _periods(spec, values, roles, _FCFF_REQUIRED)
    future = [p for p in periods if p['end'] > day]
    expected_end = _forecast_endpoint(spec, day)
    _require_period_coverage(future, day, expected_end, 'Forecast FCFF')
    if not future or future[-1]['end'] != expected_end:
        raise ValueError('FCFF periods do not end at the declared final forecast FY boundary ' + expected_end)
    if future[0]['start'] > (_date(day)+timedelta(days=1)).isoformat():
        raise ValueError('Forecast gap after valuation date; cannot silently omit a stub')
    for left, right in zip(future, future[1:]):
        if (_date(left['end'])+timedelta(days=1)).isoformat() != right['start']:
            raise ValueError('Incomplete future financial coverage; missing FCFF components cannot be zero filled')
    detail = []
    for p in future:
        component = _components(spec, values, inputs, p, a)
        fraction = 1 - _date_fraction(p, day)
        timing = _scope_stub(inputs, p, day, a['tax_rate'], fraction)
        component['scope_timing_adjustment'] = sum(x['amount'] for x in timing)
        component['scope_timing_details'] = timing
        if timing:
            _diag(diagnostics, 'scope_stub_timing', f"{p['id']}: known event operating contributions use explicit control dates; undisclosed event lease/capex/WC seasonality remains an estimated uniform allocation.")
        detail.append(_present(component, day, wacc, fraction))
    reconciliations = [_cashflow_reconciliation(spec, values, component) for component in detail]
    for item in reconciliations:
        if item['status'] in ('incomplete', 'unresolved'):
            _diag(diagnostics, 'statement_cf_reconciliation', f"{item['period_id']}: statement-CFO to FCFF bridge is {item['status']}; see the explicit component/residual report.")
    bridge = _opening_bridge(spec, values, inputs, diagnostics)
    # Annualise the final complete fiscal year, respecting fiscal calendars.
    final_end = future[-1]['end']
    annual = [p for p in spec['periods'] if p.get('kind') == 'FY' and p['end'] == final_end]
    if not annual:
        raise ValueError('Detailed forecast must end at a complete fiscal year for the annual transition')
    last_year = annual[0]
    anchor_parts = [p for p in periods if p['start'] >= last_year['start'] and p['end'] <= final_end]
    if not anchor_parts or anchor_parts[0]['start'] != last_year['start']:
        raise ValueError('Final annual FCFF anchor is incomplete')
    anchor_components = [_components(spec, values, inputs, p, a) for p in anchor_parts]
    revenue = sum(c['revenue'] for c in anchor_components)
    nopat = sum(c['nopat'] for c in anchor_components)
    margin = sum(c['operating_profit_after_cash_leases'] for c in anchor_components) / revenue
    last_reinvestment = sum(c['economic_reinvestment'] for c in anchor_components)
    initial_reinvestment_rate = last_reinvestment / nopat if nopat > 0 else reinvestment_rate
    last_sales = _value(values, roles, 'revenue', last_year['id']) or revenue
    prior_years = [p for p in spec['periods'] if p.get('kind') == 'FY' and p['end'] < last_year['end']
                   and _value(values, roles, 'revenue', p['id'])]
    start_growth = last_sales/_value(values, roles, 'revenue', max(prior_years, key=lambda p:p['end'])['id'])-1 if prior_years else growth
    transition = []
    for index in range(1, int(a['transition_years'])+1):
        weight = index / a['transition_years']
        rate = start_growth + (growth-start_growth)*weight
        year_margin = margin + (a['terminal_margin']-margin)*weight
        reinvest_rate = initial_reinvestment_rate + (reinvestment_rate-initial_reinvestment_rate)*weight
        revenue *= 1+rate
        year_nopat = valuation_equation('terminal_nopat', dict(next_year_revenue=revenue, operating_margin=year_margin, tax_rate=a['tax_rate']))
        reinvest = valuation_equation('reinvestment', dict(nopat=year_nopat, reinvestment_rate=reinvest_rate))
        end = _future_year(final_end, index)
        start = _future_year(final_end, index-1)+timedelta(days=1)
        c = dict(period_id='transition_'+str(index), start=start.isoformat(), end=end.isoformat(),
            revenue=revenue, revenue_growth=rate, operating_margin=year_margin,
            operating_profit_after_cash_leases=revenue*year_margin, nopat=year_nopat,
            reinvestment_rate=reinvest_rate, economic_reinvestment=reinvest,
            full_period_fcff=valuation_equation('terminal_fcff', dict(nopat=year_nopat, reinvestment=reinvest)), source='valuation_transition')
        transition.append(_present(c, day, wacc))
    if not transition:
        _diag(diagnostics, 'immediate_terminal_transition', 'No transition years: terminal economics change immediately to the explicitly supplied stable margin and ROIC.')
    terminal_end = transition[-1]['end'] if transition else final_end
    terminal_revenue = valuation_equation('next_year_revenue', dict(base_revenue=revenue, growth=growth))
    terminal_nopat = valuation_equation('terminal_nopat', dict(next_year_revenue=terminal_revenue, operating_margin=a['terminal_margin'], tax_rate=a['tax_rate']))
    if terminal_nopat <= 0:
        raise ValueError('Positive sustainable terminal NOPAT required; use a separate finite-life/distress method')
    terminal_reinvestment = valuation_equation('reinvestment', dict(nopat=terminal_nopat, reinvestment_rate=reinvestment_rate))
    terminal_fcff = valuation_equation('terminal_fcff', dict(nopat=terminal_nopat, reinvestment=terminal_reinvestment))
    terminal_value = valuation_equation('terminal_value', dict(fcff=terminal_fcff, wacc=wacc, growth=growth))
    terminal_years = (_date(terminal_end)-_date(day)).days/365.
    terminal_pv = valuation_equation('terminal_present_value', dict(value=terminal_value, wacc=wacc, discount_years=terminal_years))
    event_components = []
    for event in _active_events(inputs):
        eventdate = event.get('date')
        cash = _event_amount(event, 'net_cash')
        if not eventdate or cash is None:
            continue
        if eventdate <= day:
            continue
        if eventdate > final_end or event.get('effective_date', eventdate) > final_end:
            raise ValueError('A discrete ownership event falls beyond the detailed operating horizon; extend the operating model before valuation')
        taxcash = _event_amount(event, 'cash_tax')
        if taxcash is None:
            # The event-input guard marks this arithmetic incomplete. Preserve
            # the known consideration for inspection without claiming zero tax.
            taxcash = 0.
        retained = _event_amount(event, 'retained_interest_value') or 0.
        nci = event.get('balance_movements', {}).get('nci_equity', 0.)
        interest_transfer = min(0., event.get('balance_movements', {}).get('associates', 0.))
        debt_transfer = -event.get('balance_movements', {}).get('nonlease_debt', 0.)
        years = (_date(eventdate)-_date(day)).days/365.
        factor = (1+wacc)**-years
        event_component = dict(id=event['id'], date=eventdate, net_cash=cash,
            event_cash_tax=taxcash, retained_interest_value=retained, incremental_nci_claim=nci,
            existing_interest_transfer=interest_transfer, nonlease_debt_transfer=debt_transfer,
            discount_years=years, discount_factor=factor,
            method='Net consideration once; retained ownership valued only at creation, excluded from operating FCFF.')
        event_component['present_value'] = valuation_equation('event_present_value', event_component)
        event_components.append(event_component)
        if retained:
            _diag(diagnostics, 'retained_interest_proxy', f"Event {event['id']} retained-interest value is a separate, ownership-adjusted creation-date proxy; no future subsidiary standalone value added.")
    operating_pv = sum(c['present_value'] for c in detail+transition)
    enterprise_value = valuation_equation('enterprise_value', dict(operating_cashflow_present_value=operating_pv, terminal_present_value=terminal_pv))
    event_pv = sum(e['present_value'] for e in event_components)
    equity_components = dict(enterprise_value=enterprise_value, future_portfolio_events=event_pv,
        cash=bridge['cash']['value'], cash_like=bridge.get('cash_like', {}).get('value', 0.),
        restricted_cash=-a['restricted_cash'], nonlease_debt=-bridge['debt']['value'],
        associates=bridge.get('associates', {}).get('value', 0.), nci=-bridge.get('nci', {}).get('value', 0.),
        noncommon_equity=-bridge.get('noncommon_equity',{}).get('value',0.),
        pension_claim=-a['pension_claim'], deferred_consideration=-a['deferred_consideration'],
        other_claims=-a['other_claims'], other_assets=a['other_assets'])
    equity_value = valuation_equation('equity_value', equity_components)
    shares = valuation_equation('valuation_date_shares', dict(basic_shares=bridge['shares']['value'], dilution_shares=a['dilution_shares']))
    fair_value = valuation_equation('fair_value_per_share', dict(equity_value=equity_value, money_scale=inputs['money_scale'], valuation_date_shares=shares, share_scale=inputs['share_scale']))
    market = inputs.get('market', {})
    comparison = dict(status='unavailable', fair_value_currency=inputs['currency'], fair_value_per_share=fair_value)
    quote = market.get('price', {})
    if quote.get('value') is not None:
        if market.get('currency') != inputs['currency']:
            raise ValueError('Market quote currency differs from DCF currency; explicit conversion is required')
        if not quote.get('as_of') or _date(quote['as_of']) > _date(inputs['information_cutoff']):
            raise ValueError('Market price must be dated at or before information cutoff')
        price = _number(quote['value'], 'market price')*_number(market.get('price_unit_scale', 1), 'quote unit scale')
        if price <= 0:
            raise ValueError('Market price must be positive')
        market_cap = price*shares*inputs['share_scale']/inputs['money_scale']
        comparison = dict(status='available', quote=copy.deepcopy(quote), price_in_reporting_currency=price,
            fair_value_per_share=fair_value, upside=fair_value/price-1, market_cap=market_cap,
            market_enterprise_value=market_cap-(equity_value-enterprise_value),
            fair_value_currency=inputs['currency'], fair_value_meaning='Value as of valuation_date, not a future price target')
    else:
        _diag(diagnostics, 'missing_market_quote', 'No dated market price; relative upside and current trading multiples are unavailable.')
    multiples = []
    for annual_period in [p for p in spec['periods'] if p.get('kind') == 'FY' and p['end'] >= day][:2]:
        parts = [p for p in periods if annual_period['start'] <= p['start'] and p['end'] <= annual_period['end']]
        if not parts or parts[0]['start'] != annual_period['start'] or parts[-1]['end'] != annual_period['end']:
            continue
        comps = [_components(spec, values, inputs, p, a) for p in parts]
        ebit = sum(c['operating_profit_after_cash_leases'] for c in comps)
        ebitda = ebit+sum(c['eligible_da'] for c in comps)
        multiples.append(dict(period_id=annual_period['id'], basis='After cash leases, no lease debt',
            implied_ev_ebit=enterprise_value/ebit if ebit else None,
            implied_ev_ebitda=enterprise_value/ebitda if ebitda else None,
            market_ev_ebit=comparison.get('market_enterprise_value', 0)/ebit if ebit and comparison['status']=='available' else None,
            market_ev_ebitda=comparison.get('market_enterprise_value', 0)/ebitda if ebitda and comparison['status']=='available' else None))
    _diag(diagnostics, 'valuation_policy', 'Operating cash leases: lease debt and ROU investment excluded; cash rent retained in EBIT/tax and terminal margins. SBC remains an economic expense. Recurring restructuring is retained. No financial-interest or associate earnings in FCFF.')
    provisional = [k for k, v in inputs['assumptions'].items() if v.get('status') not in ('reported', 'observed', 'researched')]
    if provisional:
        _diag(diagnostics, 'provisional_inputs', 'Unresearched or proxy assumptions: '+', '.join(provisional))
    for limitation in inputs.get('research_limitations', []):
        _diag(diagnostics, 'valuation_research_limitation', str(limitation))
    result = dict(version=VERSION, status='incomplete' if any(d['severity']=='error' for d in diagnostics) else 'provisional' if diagnostics else 'complete',
        company=spec.get('company'), valuation_date=day, information_cutoff=inputs['information_cutoff'],
        currency=inputs['currency'], money_scale=inputs['money_scale'], share_scale=inputs['share_scale'],
        source_model_digest=inputs.get('source_model_digest'), valuation_input_digest=_digest(inputs),
        evaluated_model_digest=evaluated_digest,
        wacc=dict(risk_free_rate=a['risk_free_rate'], beta=a['beta'], equity_risk_premium=a['equity_risk_premium'],
            cost_of_equity=cost_equity, debt_spread=a['debt_spread'], pre_tax_cost_of_debt=cost_debt,
            debt_weight=a['debt_weight'], tax_rate=a['tax_rate'], value=wacc,
            basis='Explicit target market capital weights; book equity is not used.'),
        detailed_cashflows=detail, statement_cf_reconciliation=reconciliations, transition_cashflows=transition,
        terminal=dict(date=terminal_end, base_revenue=revenue, next_year_revenue=terminal_revenue, growth=growth,
            operating_margin=a['terminal_margin'], roic=a['terminal_roic'], nopat=terminal_nopat,
            reinvestment_rate=reinvestment_rate, reinvestment=terminal_reinvestment, fcff=terminal_fcff,
            value=terminal_value, discount_years=terminal_years, present_value=terminal_pv,
            share_of_enterprise_value=terminal_pv/enterprise_value if enterprise_value else None),
        opening_bridge=bridge, portfolio_events=event_components, equity_bridge=equity_components,
        enterprise_value=enterprise_value, equity_value=equity_value, valuation_date_shares=shares,
        fair_value_per_share=fair_value, market_comparison=comparison, implied_multiples=multiples,
        diagnostics=diagnostics, ai_calls=0, excel_required=False,
        provenance=dict(methodology_references=copy.deepcopy(METHODOLOGY_REFERENCES),
                        assumptions=copy.deepcopy(inputs['assumptions']),
                        terminal_discount_convention='First terminal FCFF paid halfway through the following year; perpetuity value at final year-end includes (1+WACC)^0.5.'))
    if include_sensitivities:
        grid = []
        for ws in inputs.get('sensitivity', {}).get('wacc_shifts', [-.01, 0., .01]):
            for gs in inputs.get('sensitivity', {}).get('growth_shifts', [-.005, 0., .005]):
                try:
                    value = value_company(spec, values, inputs, include_sensitivities=False, _wacc_shift=ws, _growth_shift=gs, _evaluated_digest=evaluated_digest)
                    grid.append(dict(wacc=value['wacc']['value'], growth=value['terminal']['growth'],
                        terminal_reinvestment=value['terminal']['reinvestment'], fair_value_per_share=value['fair_value_per_share'], status='calculated'))
                except ValueError as exc:
                    grid.append(dict(wacc=wacc+ws, growth=growth+gs, status='invalid', reason=str(exc)))
        event_cases = []
        for event in _active_events(inputs):
            if not event.get('date') or event['date'] <= day or _event_amount(event, 'net_cash') is None:
                continue
            for multiplier in inputs.get('sensitivity', {}).get('event_cash_multipliers', [.8, 1., 1.2]):
                altered = copy.deepcopy(inputs)
                target = next(e for e in altered['events'] if e['id'] == event['id'])
                target['net_cash']['value'] *= multiplier
                scenario = value_company(spec, values, altered, include_sensitivities=False, _evaluated_digest=evaluated_digest)
                event_cases.append(dict(event_id=event['id'], net_cash_multiplier=multiplier,
                    fair_value_per_share=scenario['fair_value_per_share'], delta=scenario['fair_value_per_share']-fair_value))
        result['sensitivities'] = dict(wacc_growth=grid, event_consideration=event_cases,
            method='Every case calls value_company again; growth recomputes terminal reinvestment. Operating/FX scenarios use recalculated saved model values through the same entry point.')
    return result
