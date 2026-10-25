"""Independent small-company arithmetic for the deterministic valuation backend."""
import copy
from datetime import date
import unittest

from company_initiation.dcf_construction.valuation import DEFAULT_ROLES, VERSION, VALUATION_EQUATIONS, apply_valuation_payload, generate_valuation_inputs, valuation_equation, valuation_input_contract, value_company


def fixture(valuation_date='2024-12-31', currency='GBP'):
    periods = [dict(id='2024-FY', kind='FY', start='2024-01-01', end='2024-12-31', fiscal_year=2024, status='actual'),
               dict(id='2025-FY', kind='FY', start='2025-01-01', end='2025-12-31', fiscal_year=2025, status='forecast')]
    roles = dict(revenue=1000., operating_profit=100., owned_depreciation=10., rou_depreciation=5.,
        amortization=2., lease_principal=-6., lease_interest=1., capex_ppe=-15., capex_intangibles=-3.,
        working_capital_cash=-4., portfolio_noncash=0., cash_change=12., cash=20., cash_like=5.,
        debt=30., shares=10., associates=7., nci=2., tax_rate=.25)
    rows = []; values = {}
    for role, value in roles.items():
        rid = DEFAULT_ROLES[role]
        rows.append(dict(id=rid, unit='shares_m' if role == 'shares' else 'ratio' if role == 'tax_rate' else currency+'m',
            cells={p['id']: dict(value=value, status=p['status']) for p in periods}))
        values[rid] = {p['id']: value for p in periods}
    values['cash']['2025-FY'] = 32.
    spec = dict(company='Synthetic diversified fixture', currency=currency, rows=rows, periods=periods,
                scope_event_audit=[])
    inputs = generate_valuation_inputs(spec, values, valuation_date=valuation_date)
    for name, value in dict(risk_free_rate=.04, equity_risk_premium=.06, beta=1., debt_weight=0.,
                            tax_rate=.25, terminal_growth=.02, terminal_roic=.1, terminal_margin=.1,
                            transition_years=0).items():
        inputs['assumptions'][name]['value'] = value
    return spec, values, inputs


class ValuationTests(unittest.TestCase):
    def test_missing_last_forecast_component_cannot_shorten_declared_horizon(self):
        spec,values,inputs=fixture()
        spec['forecast_years']=[2025,2026]
        period=dict(id='2026-FY',kind='FY',fiscal_year=2026,start='2026-01-01',end='2026-12-31',status='forecast')
        spec['periods'].append(period)
        for row in spec['rows']:
            amount=values[row['id']]['2025-FY'];values[row['id']]['2026-FY']=amount
            row['cells']['2026-FY']=dict(value=amount,status='forecast')
        values['operating_profit']['2026-FY']=200.
        before=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual(before['terminal']['date'],'2026-12-31')
        self.assertEqual(before['detailed_cashflows'][-1]['full_period_fcff'],138.5)
        spec['forecast_years']=[2025]
        with self.assertRaisesRegex(ValueError,'do not end at the declared final forecast FY boundary'):
            value_company(spec,values,inputs,include_sensitivities=False)
        spec['forecast_years']=[2024]
        with self.assertRaisesRegex(ValueError,'horizon ends on or before valuation date'):
            value_company(spec,values,inputs,include_sensitivities=False)
        spec['forecast_years']=[2025,2026]
        values['amortization']['2026-FY']=None
        with self.assertRaisesRegex(ValueError,'Forecast FCFF coverage is incomplete from 2026-01-01 through 2026-12-31'):
            value_company(spec,values,inputs,include_sensitivities=False)
        from company_initiation.dcf_construction.workflow import valuation_snapshot
        public=valuation_snapshot(spec,values,{},valuation_date=inputs['valuation_date'],previous_inputs=inputs)
        self.assertEqual(public['result']['status'],'incomplete')
        self.assertEqual(public['checks'][0]['status'],'MISSING')
        # Missing every amount still cannot erase the declared financial year.
        for row in values.values():row.pop('2026-FY',None)
        with self.assertRaisesRegex(ValueError,'Forecast FCFF coverage is incomplete'):
            value_company(spec,values,inputs,include_sensitivities=False)
        spec['periods'].pop()
        with self.assertRaisesRegex(ValueError,'final forecast year has no explicit FY'):
            value_company(spec,values,inputs,include_sensitivities=False)

    def test_missing_elapsed_cash_coverage_is_not_a_zero_movement(self):
        spec,values,inputs=fixture('2025-06-30')
        complete=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertAlmostEqual(complete['opening_bridge']['cash']['value'],20+12*181/365)
        values['cash_change']['2025-FY']=None
        with self.assertRaisesRegex(ValueError,'Elapsed cash bridge coverage is incomplete from 2025-01-01 through 2025-06-30'):
            value_company(spec,values,inputs,include_sensitivities=False)

    def test_missing_future_cash_change_needs_no_bridge_at_snapshot_date(self):
        spec,values,inputs=fixture('2024-12-31')
        values['cash_change']['2025-FY']=None
        result=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual(result['opening_bridge']['cash']['value'],20.)
        self.assertEqual(result['opening_bridge']['cash']['movements'],[])

    def test_newer_reported_cash_snapshot_excludes_earlier_missing_movements(self):
        spec,values,_=fixture('2025-06-30')
        period=dict(id='2025-H1',kind='H1',fiscal_year=2025,start='2025-01-01',end='2025-06-30',status='actual')
        spec['periods'].append(period)
        spec['rows'].append(dict(id='closing_cash',unit='GBPm',cells={'2025-H1':dict(value=31.,status='reported',source_refs=[dict(source_id='fixture',unit_id='page:1')])}))
        values['closing_cash']={'2025-H1':31.};values['cash_change']['2025-FY']=None
        inputs=generate_valuation_inputs(spec,values,valuation_date='2025-06-30')
        result=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual(inputs['balance_bridge']['snapshots']['cash']['date'],'2025-06-30')
        self.assertEqual(result['opening_bridge']['cash']['value'],31.)

    def test_missing_stock_endpoint_cannot_silently_hold_debt_shares_or_investments(self):
        for role,rid in [('debt','nonlease_debt'),('shares','shares_end_outstanding'),('cash_like','short_investments')]:
            spec,values,inputs=fixture('2025-09-30')
            spec['periods'].append(dict(id='2025-H1',kind='H1',fiscal_year=2025,start='2025-01-01',end='2025-06-30',status='forecast'))
            values[rid]['2025-H1']=values[rid]['2024-FY']+1
            values[rid]['2025-FY']=None
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'Opening '+role+' bridge has no model stock endpoint'):
                value_company(spec,values,inputs,include_sensitivities=False)
            # A genuinely valuation-date closing snapshot needs no future movement.
            inputs['balance_bridge']['snapshots'][role].update(date='2025-09-30')
            value_company(spec,values,inputs,include_sensitivities=False)

    def test_half_year_policy_cannot_hide_missing_h2_behind_annual_aggregate(self):
        spec,values,inputs=fixture('2025-09-30')
        spec['frequency_policy']=dict(statements='half_year',sales='quarterly',annual_only_years=[])
        for slot,start,end,status in [('H1','2025-01-01','2025-06-30','actual'),('H2','2025-07-01','2025-12-31','forecast')]:
            pid='2025-'+slot;spec['periods'].append(dict(id=pid,kind=slot,fiscal_year=2025,start=start,end=end,status=status))
            for row in spec['rows']:
                amount=values[row['id']]['2025-FY']
                if row['id'] not in ('effective_tax_rate','cash','short_investments','nonlease_debt','shares_end_outstanding','associates','nci_equity'):amount/=2
                values[row['id']][pid]=amount;row['cells'][pid]=dict(value=amount,status=status)
        inputs['balance_bridge']['snapshots']['cash'].update(value=26.,date='2025-06-30')
        result=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual([c['period_id'] for c in result['detailed_cashflows']],['2025-H2'])
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'],29.)
        values['cash_change']['2025-H2']=None
        with self.assertRaisesRegex(ValueError,'Elapsed cash bridge coverage is incomplete'):
            value_company(spec,values,inputs,include_sensitivities=False)
        values['cash_change']['2025-H2']=6.;values['amortization']['2025-H2']=None
        with self.assertRaisesRegex(ValueError,'Forecast FCFF coverage is incomplete'):
            value_company(spec,values,inputs,include_sensitivities=False)
        # The same explicit model may deliberately switch later years to FY-only.
        spec['frequency_policy']['annual_only_years']=[2025]
        result=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual([c['period_id'] for c in result['detailed_cashflows']],['2025-FY'])

    def test_quarterly_policy_retains_reported_h1_then_forecast_quarters(self):
        spec,values,inputs=fixture('2025-09-30')
        spec['frequency_policy']=dict(statements='quarterly',sales='quarterly',annual_only_years=[])
        for slot,start,end,status,fraction in [('H1','2025-01-01','2025-06-30','actual',.5),('Q3','2025-07-01','2025-09-30','forecast',.25),('Q4','2025-10-01','2025-12-31','forecast',.25)]:
            pid='2025-'+slot;spec['periods'].append(dict(id=pid,kind=slot,fiscal_year=2025,start=start,end=end,status=status))
            for row in spec['rows']:
                amount=values[row['id']]['2025-FY']
                if row['id'] not in ('effective_tax_rate','cash','short_investments','nonlease_debt','shares_end_outstanding','associates','nci_equity'):amount*=fraction
                values[row['id']][pid]=amount;row['cells'][pid]=dict(value=amount,status=status)
        result=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual([c['period_id'] for c in result['detailed_cashflows']],['2025-Q4'])
        self.assertEqual(result['detailed_cashflows'][0]['full_period_fcff'],15.875)
        self.assertAlmostEqual(result['terminal']['base_revenue'],1000.)

    def test_noncommon_equity_claim_and_elapsed_issuance_are_counted_once(self):
        spec,values,base_inputs=fixture('2025-06-30')
        baseline=value_company(spec,values,base_inputs,include_sensitivities=False)
        refs=[dict(source_id='synthetic_preference_equity_note',unit_id='capital')]
        spec['rows'].append(dict(id='preference_claim',unit='GBPm',metric_type='stock',cells={
            '2024-FY':dict(value=12.,status='reported',source_refs=refs,reason='Sourced preference-equity carrying claim'),
            '2025-FY':dict(value=22.,status='forecast')}))
        values['preference_claim']={'2024-FY':12.,'2025-FY':22.}
        # Issuance increases cash and the senior equity claim by the same amount.
        values['cash_change']['2025-FY']=22.;values['cash']['2025-FY']=42.
        spec['cashflow_presentation_contract']=dict(noncommon_equity_claim_role='preference_claim')
        inputs=generate_valuation_inputs(spec,values,valuation_date='2025-06-30')
        inputs['assumptions']=copy.deepcopy(base_inputs['assumptions'])
        result=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertAlmostEqual(result['enterprise_value'],baseline['enterprise_value'])
        self.assertAlmostEqual(result['equity_value'],baseline['equity_value']-12.)
        self.assertAlmostEqual(result['opening_bridge']['noncommon_equity']['value'],12+10*181/365)
        self.assertEqual(result['equity_bridge']['nonlease_debt'],baseline['equity_bridge']['nonlease_debt'])
        self.assertEqual(result['opening_bridge']['noncommon_equity']['opening']['source_refs'],refs)
        self.assertEqual(result['opening_bridge']['noncommon_equity']['opening']['date'],'2024-12-31')
        self.assertEqual(result['detailed_cashflows'],baseline['detailed_cashflows'])
        inputs['balance_bridge']['dated_movements']=[dict(role=role,date='2025-04-01',amount=10.,
            included_in_model=True,source_refs=refs,event_id='preference_issue') for role in ('cash','noncommon_equity')]
        dated=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertAlmostEqual(dated['opening_bridge']['cash']['value'],20+12*181/365+10)
        self.assertEqual(dated['opening_bridge']['noncommon_equity']['value'],22.)
        self.assertAlmostEqual(dated['equity_value'],baseline['equity_value']-12.)
        inputs['balance_bridge']['dated_movements'].pop(0)
        with self.assertRaisesRegex(ValueError,'matching dated cash'):
            value_company(spec,values,inputs,include_sensitivities=False)
        missing=copy.deepcopy(inputs);missing['balance_bridge']['snapshots'].pop('noncommon_equity')
        with self.assertRaisesRegex(ValueError,'Declared noncommon equity claim is missing'):
            value_company(spec,values,missing,include_sensitivities=False)
        spec['rows'][-1]['unit']='USDm'
        with self.assertRaisesRegex(ValueError,'reporting currency'):
            generate_valuation_inputs(spec,values,valuation_date='2025-06-30')

    def test_unknown_zero_claims_block_valuation_until_supported(self):
        spec,values,inputs=fixture()
        result=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual(result['status'],'incomplete')
        self.assertTrue(any(d['code']=='unresolved_other_claims' and d['severity']=='error' for d in result['diagnostics']))
        # Numeric diagnostic results are retained but are not accepted valuation.
        conditional=result['fair_value_per_share']
        for key in ('other_claims','other_assets','restricted_cash','pension_claim','deferred_consideration','dilution_shares'):
            inputs['assumptions'][key].update(status='researched',source_refs=[dict(source_id='synthetic_absence_note')],
                method='Synthetic original explicitly states absence of this claim or adjustment.')
        supported=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertNotEqual(supported['status'],'incomplete')
        self.assertEqual(supported['fair_value_per_share'],conditional)
        inputs['balance_bridge']['snapshots']['associates'].update(value=None,status='missing')
        missing=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual(missing['status'],'incomplete')
        self.assertTrue(any(d['code']=='missing_associates' and d['severity']=='error' for d in missing['diagnostics']))
        snapshot=inputs['balance_bridge']['snapshots']['associates']
        for status in ('unresolved_zero_scenario','reported'):
            with self.subTest(snapshot_status=status):
                snapshot.update(value=0.,status=status,source_refs=[],method='Unknown investment balance, not evidence of absence.')
                missing=value_company(spec,values,inputs,include_sensitivities=False)
                self.assertEqual(missing['status'],'incomplete')
                self.assertTrue(any(d['code']=='unresolved_opening_associates' and d['severity']=='error' for d in missing['diagnostics']))
        snapshot.update(value=0.,status='reported',source_refs=[dict(source_id='synthetic_absence_note',unit_id='associates')],
            method='Synthetic original explicitly reports no associate investment at the opening date.')
        supported=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertNotEqual(supported['status'],'incomplete')

    def test_elapsed_investment_purchase_preserves_cash_plus_investment_value(self):
        spec,values,inputs=fixture('2025-06-30')
        baseline=value_company(spec,values,inputs,include_sensitivities=False)
        # A4 cash purchase creates a4 investment; it does not destroy equity.
        values['cash_change']['2025-FY']-=4.
        values['cash']['2025-FY']-=4.
        values['short_investments']['2025-FY']+=4.
        revised=generate_valuation_inputs(spec,values,valuation_date='2025-06-30')
        revised['assumptions']=copy.deepcopy(inputs['assumptions'])
        result=value_company(spec,values,revised,include_sensitivities=False)
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'],20+8*181/365)
        self.assertAlmostEqual(result['opening_bridge']['cash_like']['value'],5+4*181/365)
        self.assertAlmostEqual(result['equity_value'],baseline['equity_value'])
        self.assertEqual(result['detailed_cashflows'],baseline['detailed_cashflows'])
        refs=[dict(source_id='synthetic_investment_transaction',unit_id='purchase')]
        revised['balance_bridge']['dated_movements']=[dict(role=role,date='2025-04-01',amount=amount,
            included_in_model=True,source_refs=refs,event_id='investment_purchase') for role,amount in (('cash',-4.),('cash_like',4.))]
        dated=value_company(spec,values,revised,include_sensitivities=False)
        self.assertAlmostEqual(dated['opening_bridge']['cash']['value'],20+12*181/365-4)
        self.assertEqual(dated['opening_bridge']['cash_like']['value'],9.)
        self.assertAlmostEqual(dated['equity_value'],baseline['equity_value'])

    def test_cash_scope_gross_up_prevents_overdraft_double_subtraction_in_date_stub(self):
        spec,values,_=fixture('2025-06-30')
        # Reported CF cash nets a10 overdraft: opening net10, movement8.
        # Gross cash20, movement12; the4 difference is new overdraft borrowing.
        # Full debt30 already includes the opening overdraft, and closes34.
        for rid,opening,closing,metric in [('closing_cash',10.,18.,'stock'),
                ('valuation_cash',20.,32.,'stock'),('valuation_cash_change',12.,12.,'flow')]:
            spec['rows'].append(dict(id=rid,unit='GBPm',metric_type=metric,cells={
                '2024-FY':dict(value=opening,status='derived_actual'),
                '2025-FY':dict(value=closing,status='forecast')}))
            values[rid]={'2024-FY':opening,'2025-FY':closing}
        values['cash_change']['2025-FY']=8.;values['nonlease_debt']['2025-FY']=34.
        spec['cash_scope_contract']=dict(valuation_cash_role='valuation_cash',valuation_cash_change_role='valuation_cash_change')
        inputs=generate_valuation_inputs(spec,values,valuation_date='2025-06-30')
        result=value_company(spec,values,inputs,include_sensitivities=False)
        self.assertEqual(inputs['row_roles']['cash'],'valuation_cash')
        self.assertEqual(inputs['row_roles']['cash_change'],'valuation_cash_change')
        self.assertIn('does not establish cash accessibility',inputs['cash_scope'])
        self.assertIn('restricted or unavailable cash',inputs['cash_scope'])
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'],20+12*181/365)
        self.assertAlmostEqual(result['opening_bridge']['debt']['value'],30+4*181/365)
        self.assertAlmostEqual(result['opening_bridge']['cash']['value']-result['opening_bridge']['debt']['value'],-10+8*181/365)

    def test_known_fcff_lease_tax_and_terminal_value(self):
        spec, values, inputs = fixture()
        result = value_company(spec, values, inputs, include_sensitivities=False)
        c = result['detailed_cashflows'][0]
        # EBIT100 + ROU5 - principal6 - interest1 =98. Tax24.5.
        # FCFF98-24.5+ownedDA10+amort2-capex18-WC4 =63.5.
        self.assertEqual(c['operating_profit_after_cash_leases'], 98.)
        self.assertEqual(c['unlevered_tax'], -24.5)
        self.assertEqual(c['eligible_da'], 12.)
        self.assertEqual(c['full_period_fcff'], 63.5)
        self.assertEqual(c['sbc_addback'], 0.)
        self.assertAlmostEqual(result['terminal']['reinvestment'], 15.3)
        self.assertAlmostEqual(result['terminal']['fcff'], 61.2)
        self.assertAlmostEqual(result['terminal']['value'], 765.*1.1**.5)
        expected = 63.5/1.1**(183/365)+765/1.1**.5
        self.assertAlmostEqual(result['enterprise_value'], expected)
        self.assertAlmostEqual(result['fair_value_per_share'], expected/10)

    def test_stub_cash_bridge_excludes_elapsed_cash_from_dcf(self):
        spec, values, inputs = fixture('2025-06-30')
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'], 20+12*181/365)
        c = result['detailed_cashflows'][0]
        self.assertAlmostEqual(c['remaining_fcff'], 63.5*184/365)
        self.assertAlmostEqual(c['present_value'], 63.5*184/365/1.1**(92.5/365))
        self.assertNotEqual(result['opening_bridge']['cash']['value'], values['cash']['2025-FY'])

    def test_dated_distribution_replaces_proration_in_opening_cash(self):
        spec, values, inputs = fixture('2025-06-30')
        values['cash_change']['2025-FY'] = -88.  # +12 operations, -100 dividend.
        inputs['balance_bridge']['dated_movements'] = [dict(role='cash', date='2025-02-01', amount=-100., included_in_model=True, status='reported', source_refs=['fixture'])]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'], 20+12*181/365-100)

    def test_future_event_cash_gain_and_retained_interest_counted_once(self):
        spec, values, inputs = fixture('2025-06-30')
        values['operating_profit']['2025-FY'] = 120.
        values['cfo_portfolio_noncash']['2025-FY'] = -20.
        values['cash_change']['2025-FY'] = 112.
        event = dict(id='sale', date='2025-12-31', gain_loss=20., net_cash=dict(value=100.),
                     cash_tax=dict(value=0.), retained_interest_value=dict(value=30.),
                     model_net_cash=100., model_cash_tax=0., balance_movements={'associates':30.})
        inputs['events'] = [event]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['detailed_cashflows'][0]['full_period_fcff'], 63.5)
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'], 20+12*181/365)
        self.assertEqual(result['equity_bridge']['associates'], 7.)
        self.assertAlmostEqual(result['equity_bridge']['future_portfolio_events'], 130/1.1**(184/365))
        alternative = copy.deepcopy(inputs); alternative['events'][0]['net_cash']['value'] = 80.
        alt = value_company(spec, values, alternative, include_sensitivities=False)
        self.assertEqual(alt['opening_bridge']['cash']['value'], result['opening_bridge']['cash']['value'])
        self.assertAlmostEqual(alt['equity_value']-result['equity_value'], -20/1.1**(184/365))

    def test_prevaluation_event_enters_opening_cash_not_future_value(self):
        spec, values, inputs = fixture('2025-06-30')
        values['cash_change']['2025-FY'] = 112.
        inputs['events'] = [dict(id='sale', date='2025-03-31', net_cash=dict(value=100.),
            cash_tax=dict(value=0.), model_net_cash=100., model_cash_tax=0.,
            retained_interest_value=dict(value=30.), balance_movements={'associates':30.})]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'], 120+12*181/365)
        self.assertEqual(result['equity_bridge']['associates'], 37.)
        self.assertEqual(result['portfolio_events'], [])

    def test_explicit_transition_margin_and_reinvestment_converge(self):
        spec, values, inputs = fixture()
        inputs['assumptions']['transition_years']['value'] = 2
        inputs['assumptions']['terminal_margin']['value'] = .08
        result = value_company(spec, values, inputs, include_sensitivities=False)
        first, last = result['transition_cashflows']
        self.assertAlmostEqual(first['operating_margin'], .089)
        self.assertAlmostEqual(last['operating_margin'], .08)
        self.assertAlmostEqual(last['reinvestment_rate'], .2)
        self.assertEqual(last['end'], '2027-12-31')
        self.assertAlmostEqual(last['full_period_fcff'], last['nopat']*.8)

    def test_growth_sensitivity_recalculates_reinvestment_using_same_function(self):
        spec, values, inputs = fixture()
        result = value_company(spec, values, inputs)
        point = next(p for p in result['sensitivities']['wacc_growth'] if abs(p['wacc']-.1)<1e-9 and abs(p['growth']-.025)<1e-9)
        self.assertAlmostEqual(point['terminal_reinvestment'], 1000*1.025*.1*.75*.025/.1)
        changed = copy.deepcopy(inputs); changed['assumptions']['terminal_growth']['value'] = .025
        again = value_company(spec, values, changed, include_sensitivities=False)
        self.assertEqual(point['fair_value_per_share'], again['fair_value_per_share'])

    def test_profit_driver_flows_into_fcff_and_fair_value_without_second_model(self):
        spec, values, inputs = fixture()
        baseline = value_company(spec, values, inputs, include_sensitivities=False)
        values['operating_profit']['2025-FY'] += 20.
        changed = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(changed['detailed_cashflows'][0]['full_period_fcff']-baseline['detailed_cashflows'][0]['full_period_fcff'], 15.)
        self.assertAlmostEqual(changed['equity_value']-baseline['equity_value'], 15/1.1**(183/365))
        self.assertNotEqual(changed['evaluated_model_digest'], baseline['evaluated_model_digest'])

    def test_market_pence_money_millions_and_share_millions(self):
        spec, values, inputs = fixture()
        inputs['market'].update(price=dict(value=1000., as_of='2024-12-30', status='observed', method='Synthetic quote'), price_unit_scale=.01)
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['market_comparison']['price_in_reporting_currency'], 10.)
        self.assertEqual(result['market_comparison']['market_cap'], 100.)
        self.assertAlmostEqual(result['market_comparison']['upside'], result['fair_value_per_share']/10-1)
        # Store actual share count instead of millions: economic value is identical.
        converted = copy.deepcopy(inputs); converted['share_scale'] = 1.; converted['balance_bridge']['snapshots']['shares']['value'] *= 1e6
        values['shares_end_outstanding'] = {k:v*1e6 for k,v in values['shares_end_outstanding'].items()}
        next(r for r in spec['rows'] if r['id']=='shares_end_outstanding')['unit'] = 'shares'
        again = value_company(spec, values, converted, include_sensitivities=False)
        self.assertEqual(result['fair_value_per_share'], again['fair_value_per_share'])

    def test_no_lease_debt_or_rou_addback_and_sbc_retained(self):
        spec, values, inputs = fixture()
        baseline = value_company(spec, values, inputs, include_sensitivities=False)
        values['lease_liabilities'] = {'2024-FY': 500., '2025-FY': 900.}
        values['sbc'] = {'2024-FY': 10., '2025-FY': 20.}
        changed = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(changed['equity_value'], baseline['equity_value'])
        self.assertNotIn('lease_debt', changed['equity_bridge'])
        inputs['profit_basis'] = 'adjusted_ebit_ex_amortization'
        with self.assertRaisesRegex(ValueError, 'amortisation bridge'):
            value_company(spec, values, inputs)

    def test_rejects_invalid_terminal_policy_dates_currency_and_missing_component(self):
        for name, value in [('terminal_growth', .1), ('terminal_roic', .01)]:
            spec, values, inputs = fixture(); inputs['assumptions'][name]['value'] = value
            with self.assertRaises(ValueError): value_company(spec, values, inputs)
        spec, values, inputs = fixture(); inputs['market']['currency'] = 'EUR'; inputs['market']['price']['value'] = 10.
        with self.assertRaisesRegex(ValueError, 'currency'): value_company(spec, values, inputs)
        spec, values, inputs = fixture(); values['lease_interest']['2025-FY'] = None
        with self.assertRaisesRegex(ValueError, 'Forecast FCFF coverage is incomplete'): value_company(spec, values, inputs)
        spec, values, inputs = fixture(); inputs['information_cutoff'] = '2025-01-01'
        with self.assertRaisesRegex(ValueError, 'cutoff'): value_company(spec, values, inputs)

    def test_contract_rejects_history_output_structure_and_undated_edits(self):
        spec, values, inputs = fixture()
        contract = valuation_input_contract(spec, inputs)
        self.assertFalse(next(f for f in contract['fields'] if f['id']=='balance_bridge.snapshots.cash')['writable'])
        before = copy.deepcopy(inputs)
        payload = dict(version=VERSION, valuation_date=inputs['valuation_date'], source_model_digest=inputs['source_model_digest'],
                       changes=[dict(id='assumptions.beta', value=.8, unit='multiple', scale=1, as_of='2024-12-31', status='scenario', method='Independent beta sensitivity')])
        altered = apply_valuation_payload(inputs, payload)
        self.assertEqual(inputs, before)
        self.assertEqual(altered['assumptions']['beta']['value'], .8)
        payload['changes'][0]['unit'] = 'EUR'
        with self.assertRaisesRegex(ValueError, 'unit/scale'): apply_valuation_payload(inputs, payload)
        payload['changes'][0].update(unit='multiple', scale=100)
        with self.assertRaisesRegex(ValueError, 'unit/scale'): apply_valuation_payload(inputs, payload)
        payload['changes'][0]['scale'] = 1
        for field in ('fair_value_per_share', 'row_roles', 'balance_bridge.snapshots.cash', 'valuation_date'):
            payload['changes'][0]['id'] = field
            with self.assertRaisesRegex(ValueError, 'Read-only'): apply_valuation_payload(inputs, payload)
        payload['changes'][0].update(id='assumptions.beta', as_of='2025-01-01')
        with self.assertRaisesRegex(ValueError, 'cutoff'): apply_valuation_payload(inputs, payload)

    def test_application_config_and_noncalendar_currency_fixture(self):
        spec, values, _ = fixture(currency='EUR')
        spec['periods'][0].update(start='2023-07-01', end='2024-06-30')
        spec['periods'][1].update(start='2024-07-01', end='2025-06-30')
        config = dict(model_configuration=dict(valuation=dict(assumptions={'terminal_growth':dict(value=.015, as_of='2024-06-30', status='researched', method='Fixture only', source_refs=['synthetic'])})))
        inputs = generate_valuation_inputs(spec, values, config, valuation_date='2024-06-30')
        self.assertEqual(inputs['assumptions']['terminal_growth']['value'], .015)
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['currency'], 'EUR')
        self.assertEqual(result['transition_cashflows'][-1]['end'], '2030-06-30')
        self.assertTrue(result['provenance']['methodology_references'])

    def test_researched_millions_convert_to_thousands_and_individual_shares(self):
        spec,values,baseline=fixture()
        researched=copy.deepcopy(baseline['assumptions'])
        researched['pension_claim'].update(value=3.,unit='reporting_currency_millions',scale=1e6,currency='GBP')
        researched['dilution_shares'].update(value=2.,unit='shares_millions',scale=1e6,currency='GBP')
        config=dict(model_configuration=dict(valuation=dict(assumptions=researched)))
        million=generate_valuation_inputs(spec,values,config,valuation_date='2024-12-31')
        expected=value_company(spec,values,million,include_sensitivities=False)
        smaller=copy.deepcopy(spec);scaled=copy.deepcopy(values)
        for row in smaller['rows']:
            multiplier=1000 if row['unit']=='GBPm' else 1e6 if row['unit']=='shares_m' else 1
            if row['unit']=='GBPm':row['unit']='GBPk'
            elif row['unit']=='shares_m':row['unit']='shares'
            for pid,cell in row['cells'].items():
                cell['value']*=multiplier;scaled[row['id']][pid]*=multiplier
        inputs=generate_valuation_inputs(smaller,scaled,config,valuation_date='2024-12-31')
        self.assertEqual(inputs['assumptions']['pension_claim']['value'],3000)
        self.assertEqual(inputs['assumptions']['dilution_shares']['value'],2e6)
        self.assertEqual(inputs['assumptions']['pension_claim']['source_measurement']['value'],3)
        contract={f['id']:f for f in valuation_input_contract(smaller,inputs)['fields']}
        self.assertEqual((contract['assumptions.pension_claim']['unit'],contract['assumptions.pension_claim']['scale']),('GBP',1000))
        self.assertEqual((contract['assumptions.dilution_shares']['unit'],contract['assumptions.dilution_shares']['scale']),('shares',1))
        actual=value_company(smaller,scaled,inputs,include_sensitivities=False)
        self.assertAlmostEqual(actual['fair_value_per_share'],expected['fair_value_per_share'])
        self.assertAlmostEqual(actual['equity_value'],expected['equity_value']*1000)

    def test_typed_research_rejects_currency_dimension_and_scale_mismatch(self):
        spec,values,base=fixture()
        entry=dict(base['assumptions']['pension_claim'],value=3.,unit='reporting_currency_millions',scale=1e6,currency='GBP')
        for changes,message in [(dict(currency='EUR'),'currency'),(dict(unit='shares_millions'),'incompatible'),(dict(scale=1000),'scale disagrees'),(dict(scale=None),'positive explicit scale')]:
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,message):
                generate_valuation_inputs(spec,values,dict(valuation=dict(assumptions={'pension_claim':dict(entry,**changes)})),valuation_date='2024-12-31')
        tax=dict(base['assumptions']['tax_rate'],value=25.,unit='ratio',scale=.01,currency='GBP')
        with self.assertRaisesRegex(ValueError,'scale 1'):
            generate_valuation_inputs(spec,values,dict(valuation=dict(assumptions={'tax_rate':tax})),valuation_date='2024-12-31')

    def test_statement_cfo_bridge_explains_finance_associates_sbc_and_tax(self):
        spec, values, inputs = fixture()
        items = dict(cf_net_profit=60., da=17., sbc=4., cf_associates=-3.,
                     associate_dividends=2., cf_tax_timing=-1., wc_cash=-4., cf_finance_timing=2.)
        for key, value in items.items(): values[key] = {'2025-FY':value}
        values['cfo'] = {'2025-FY':77.}
        spec['cashflow_component_contract'] = dict(cfo_components=list(items))
        result = value_company(spec, values, inputs, include_sensitivities=False)
        bridge = result['statement_cf_reconciliation'][0]
        self.assertEqual(bridge['statement_cash_after_capex'], 59.)
        self.assertEqual(sum(bridge['adjustments'].values()), 4.5)
        self.assertEqual(bridge['reconstructed_fcff'], 63.5)
        self.assertEqual(bridge['residual'], 0.)
        values['cfo']['2025-FY'] += 3.
        broken = value_company(spec, values, inputs, include_sensitivities=False)['statement_cf_reconciliation'][0]
        self.assertEqual(broken['status'], 'unresolved')
        self.assertEqual(broken['residual'], -3.)

    def test_stock_bridge_traverses_endpoints_and_respects_dated_financing(self):
        spec, values, inputs = fixture('2025-09-30')
        spec['periods'].append(dict(id='2025-H1', kind='H1', start='2025-01-01', end='2025-06-30', fiscal_year=2025, status='forecast'))
        values['nonlease_debt'].update({'2025-H1':40., '2025-FY':50.})
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['opening_bridge']['debt']['value'], 45.)
        # Debt issue occurs at year end: it must not be interpolated into September.
        inputs['balance_bridge']['dated_movements'] = [dict(role='debt', date='2025-12-31', amount=10., included_in_model=True)]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['opening_bridge']['debt']['value'], 40.)

    def test_newer_explicit_opening_seed_remains_labelled_estimate(self):
        spec, values, _ = fixture('2025-09-30')
        spec['periods'].append(dict(id='2025-H1', kind='H1', start='2025-01-01', end='2025-06-30', fiscal_year=2025, status='actual'))
        rid = 'opening_proxy_nonlease_debt'
        spec['rows'].append(dict(id=rid, unit='GBPm', cells={'2025-H1':dict(value=40., status='estimated_historical', reason='Explicit synthetic closing-debt allocation', calibration_eligible=False)}))
        values[rid] = {'2025-H1':40.}; values['nonlease_debt']['2025-FY'] = 50.
        inputs = generate_valuation_inputs(spec, values, valuation_date='2025-09-30')
        self.assertEqual(inputs['balance_bridge']['snapshots']['debt']['row_id'], rid)
        self.assertEqual(inputs['balance_bridge']['snapshots']['debt']['status'], 'estimated_historical')
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['opening_bridge']['debt']['value'], 45.)

    def test_hfs_cash_stays_in_cashflow_scope_until_transferred(self):
        spec, values, _ = fixture('2025-06-30')
        spec['rows'].append(dict(id='closing_cash', unit='GBPm', cells={'2024-FY':dict(value=25., status='actual'), '2025-FY':dict(value=132., status='forecast')}))
        values['closing_cash'] = {'2024-FY':25., '2025-FY':132.}
        values['cash_change']['2025-FY'] = 107.  # ordinary12 + consideration100 - HFS cash5
        spec['scope_event_audit'] = [dict(id='sale', effective_date='2025-12-31', cash_flows={'business_disposals_cf':95.}, gain_loss=0., balance_movements={}, held_for_sale_cash_removed=5.)]
        inputs = generate_valuation_inputs(spec, values, valuation_date='2025-06-30')
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(inputs['row_roles']['cash'], 'closing_cash')
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'], 25+12*181/365)
        self.assertEqual(result['portfolio_events'][0]['net_cash'], 95.)

    def test_scope_stub_reallocates_known_economics_without_doublecount_elapsed_cash(self):
        spec, values, inputs = fixture('2025-09-30')
        values['cash_change']['2025-FY'] = 63.5
        inputs['events'] = [dict(id='exit', date='2025-06-30', effective_date='2025-07-01',
            annual_revenue=-100., annual_cash_costs={'production':-60.},
            annual_da_by_role={'owned_ppe_depreciation':-5., 'amortization':-1.},
            net_cash=dict(value=0.), cash_tax=dict(value=0.), model_net_cash=0., model_cash_tax=0., balance_movements={})]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        c = result['detailed_cashflows'][0]
        expected_adjustment = -31.5*(92/365-(184/365)*(92/365))
        self.assertAlmostEqual(c['scope_timing_adjustment'], expected_adjustment)
        self.assertAlmostEqual(c['remaining_fcff'], 63.5*92/365+expected_adjustment)
        elapsed = result['opening_bridge']['cash']['value']-20.
        self.assertAlmostEqual(elapsed+c['remaining_fcff'], 63.5)

    def test_future_acquisition_removes_existing_stake_and_assumed_debt_once(self):
        spec, values, inputs = fixture()
        inputs['events'] = [dict(id='buy', date='2025-12-31', effective_date='2025-12-31',
            net_cash=dict(value=-80.), cash_tax=dict(value=0.), balance_movements={'associates':-7., 'nonlease_debt':20., 'nci_equity':3.})]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['equity_bridge']['associates'], 7.)
        self.assertAlmostEqual(result['equity_bridge']['future_portfolio_events'], -110/1.1)
        inputs['events'][0]['date'] = '2026-12-31'; inputs['events'][0]['effective_date'] = '2026-12-31'
        inputs['assumptions']['transition_years']['value'] = 3
        with self.assertRaisesRegex(ValueError, 'detailed operating horizon'):
            value_company(spec, values, inputs)

    def test_taxable_event_uses_cash_tax_policy_not_marginal_charge(self):
        spec, values, _ = fixture()
        values['cash_tax_ratio'] = {'2025-FY':.5}; values['deferred_tax_share'] = {'2025-FY':.2}
        spec['scope_event_audit'] = [dict(id='sale', effective_date='2025-12-31', gain_loss=20., tax_rate=.25,
            cash_flows={'business_disposals_cf':100.}, balance_movements={})]
        inputs = generate_valuation_inputs(spec, values, valuation_date='2024-12-31')
        self.assertEqual(inputs['events'][0]['cash_tax']['value'], -2.)
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['portfolio_events'][0]['event_cash_tax'], -2.)

    def test_no_backdated_information_or_inconsistent_share_scale(self):
        spec, values, inputs = fixture()
        spec['sources'] = [dict(id='later_filing', published_at='2025-01-15')]
        with self.assertRaisesRegex(ValueError, 'historical vintage'):
            value_company(spec, values, inputs)
        spec['sources'] = []
        inputs['share_scale'] = 1.
        with self.assertRaisesRegex(ValueError, 'Share scale'):
            value_company(spec, values, inputs)

    def test_explicit_information_cutoff_does_not_move_valuation_timing_or_research_dates(self):
        spec, values, _ = fixture('2025-06-30')
        spec['sources'] = [dict(id='synthetic_annual', published_at='2025-03-01')]
        config = dict(valuation=dict(assumptions={'beta':dict(value=.9, as_of='2025-03-01',
            status='provisional_assumption', method='Synthetic dated estimate', source_refs=['synthetic_annual'])}))
        inputs = generate_valuation_inputs(spec, values, config, valuation_date='2025-06-30',
                                          information_cutoff='2025-03-31')
        self.assertEqual(inputs['assumptions']['risk_free_rate']['as_of'], '2025-03-31')
        self.assertEqual(inputs['assumptions']['beta']['as_of'], '2025-03-01')
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['information_cutoff'], '2025-03-31')
        self.assertEqual(result['valuation_date'], '2025-06-30')
        self.assertAlmostEqual(result['opening_bridge']['cash']['value'], 20+12*181/365)
        config['valuation']['assumptions']['beta']['as_of'] = '2025-04-01'
        late = generate_valuation_inputs(spec, values, config, valuation_date='2025-06-30',
                                        information_cutoff='2025-03-31')
        self.assertEqual(late['assumptions']['beta']['as_of'], '2025-04-01')
        with self.assertRaisesRegex(ValueError, 'beta is after information cutoff'):
            value_company(spec, values, late)

    def test_supported_full_period_used_when_partial_quarters_cannot_tile(self):
        spec, values, inputs = fixture()
        spec['periods'].append(dict(id='2025-Q1', kind='Q1', start='2025-01-01', end='2025-03-31', fiscal_year=2025, status='forecast'))
        for role in ('revenue','operating_profit','owned_depreciation','rou_depreciation','amortization','lease_principal','lease_interest','capex_ppe','capex_intangibles','working_capital_cash'):
            rid = DEFAULT_ROLES[role]; values[rid]['2025-Q1'] = values[rid]['2025-FY']/4
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual([p['period_id'] for p in result['detailed_cashflows']], ['2025-FY'])

    def test_shared_expressions_drive_arithmetic_and_reject_calls(self):
        self.assertAlmostEqual(valuation_equation('terminal_value', dict(fcff=61.2,wacc=.1,growth=.02)), 765*1.1**.5)
        original = VALUATION_EQUATIONS.get('test')
        try:
            VALUATION_EQUATIONS['test'] = 'abs(value)'
            with self.assertRaisesRegex(ValueError, 'Unsupported'): valuation_equation('test', dict(value=-1.))
        finally:
            if original is None: del VALUATION_EQUATIONS['test']
            else: VALUATION_EQUATIONS['test'] = original


class EventValuationChecks(unittest.TestCase):
    def supported_fixture(self, day='2024-12-31'):
        spec, values, inputs = fixture(day)
        for key in ('other_claims', 'other_assets', 'restricted_cash', 'pension_claim', 'deferred_consideration', 'dilution_shares'):
            inputs['assumptions'][key].update(status='reported', source_refs=[dict(source_id='synthetic_absence_note')],
                method='Synthetic original explicitly reports absence of this claim or adjustment.')
        return spec, values, inputs

    def amount(self, value):
        return dict(value=value, as_of='2024-12-31', status='reported',
            source_refs=[dict(source_id='synthetic_transaction_note')],
            method='Synthetic original states this signed cash amount and its payment at closing.', unit='GBP', scale=1e6)

    def test_unknown_future_cash_and_date_block_public_valuation_boundary(self):
        from company_initiation.dcf_construction.workflow import valuation_snapshot
        spec, values, inputs = self.supported_fixture()
        baseline = value_company(spec, values, inputs, include_sensitivities=False)
        event = dict(id='purchase', date='2025-06-30', net_cash=self.amount(None), cash_tax=self.amount(0.),
                     material_unresolved=False)  # A flag cannot supply the missing amount.
        inputs['events'] = [event]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['equity_value'], baseline['equity_value'])
        self.assertTrue(any(d['code'] == 'unresolved_event_net_cash:purchase' and d['severity'] == 'error' for d in result['diagnostics']))
        public = valuation_snapshot(spec, values, {}, valuation_date=inputs['valuation_date'], previous_inputs=inputs)
        self.assertTrue(any(c['name'] == 'unresolved_event_net_cash:purchase' and c['status'] == 'FAIL' for c in public['checks']))
        event.update(date=None, net_cash=self.amount(-100.))
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(result['status'], 'incomplete')
        self.assertTrue(any(d['code'] == 'unresolved_event_date:purchase' for d in result['diagnostics']))

    def test_missing_elapsed_cash_or_tax_does_not_become_accepted_zero(self):
        spec, values, inputs = self.supported_fixture('2025-06-30')
        # The annual cash forecast includes a100 disposal and5 cash tax.
        values['cash_change']['2025-FY'] = 107.
        event = dict(id='sale', date='2025-03-31', net_cash=self.amount(100.), cash_tax=self.amount(-5.),
                     model_net_cash=100., model_cash_tax=-5.)
        inputs['events'] = [event]
        complete = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertNotEqual(complete['status'], 'incomplete')
        self.assertAlmostEqual(complete['opening_bridge']['cash']['value'], 115+12*181/365)
        for field in ('net_cash', 'cash_tax'):
            changed = copy.deepcopy(inputs)
            changed['events'][0][field]['value'] = None
            result = value_company(spec, values, changed, include_sensitivities=False)
            self.assertEqual(result['status'], 'incomplete')
            self.assertTrue(any(d['code'] == 'unresolved_event_' + field + ':sale' and d['severity'] == 'error'
                                for d in result['diagnostics']))
        # Future tax uncertainty preserves known consideration as conditional
        # arithmetic, with the same blocking error as the elapsed cash bridge.
        event['date'] = '2025-12-31'
        event['cash_tax']['value'] = None
        future = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertEqual(future['status'], 'incomplete')
        self.assertAlmostEqual(future['equity_bridge']['future_portfolio_events'], 100/1.1**(184/365))

    def test_completed_event_exemption_requires_all_affected_supported_opening_stocks(self):
        spec, values, inputs = self.supported_fixture('2025-06-30')
        for role in ('cash', 'debt', 'associates'):
            inputs['balance_bridge']['snapshots'][role].update(status='reported',
                source_refs=[dict(source_id='synthetic_post_disposal_balance_sheet')],
                method='Reported closing stock after the completed disposal.')
        baseline = value_company(spec, values, inputs, include_sensitivities=False)
        inputs['events'] = [dict(id='historical_sale', date='2024-11-30', net_cash=self.amount(None),
            cash_tax=self.amount(None), balance_movements={'nonlease_debt':-2., 'associates':3.})]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertNotEqual(result['status'], 'incomplete')
        self.assertEqual(result['equity_value'], baseline['equity_value'])
        self.assertEqual(result['portfolio_events'], [])
        self.assertTrue(any(d['code'] == 'event_in_opening_balances:historical_sale' for d in result['diagnostics']))
        for role in ('cash', 'debt', 'associates'):
            for defect in ('older', 'uncited'):
                with self.subTest(role=role, defect=defect):
                    changed = copy.deepcopy(inputs)
                    snapshot = changed['balance_bridge']['snapshots'][role]
                    snapshot.update(date='2024-10-31') if defect == 'older' else snapshot.update(source_refs=[])
                    result = value_company(spec, values, changed, include_sensitivities=False)
                    self.assertEqual(result['status'], 'incomplete')

    def test_evidenced_cashless_reorganisation_allowed_but_unsupported_zero_blocks(self):
        spec, values, inputs = self.supported_fixture()
        baseline = value_company(spec, values, inputs, include_sensitivities=False)
        zero = self.amount(0.)
        zero['method'] = 'Cited internal reorganisation: no consideration, equity issuance, cash tax or standalone value.'
        inputs['events'] = [dict(id='internal_reorganisation', date='2025-06-30', net_cash=copy.deepcopy(zero),
                                cash_tax=copy.deepcopy(zero), balance_movements={})]
        result = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertNotEqual(result['status'], 'incomplete')
        self.assertEqual(result['equity_value'], baseline['equity_value'])
        self.assertEqual(result['detailed_cashflows'], baseline['detailed_cashflows'])
        self.assertEqual(result['portfolio_events'][0]['present_value'], 0.)
        for update in (dict(source_refs=[]), dict(method=''), dict(status='unresolved_zero_scenario')):
            changed = copy.deepcopy(inputs)
            changed['events'][0]['net_cash'].update(update)
            self.assertEqual(value_company(spec, values, changed, include_sensitivities=False)['status'], 'incomplete')
        inputs['events'][0].update(enabled=False, date=None, net_cash=self.amount(None))
        inactive = value_company(spec, values, inputs, include_sensitivities=False)
        self.assertNotEqual(inactive['status'], 'incomplete')
        self.assertEqual(inactive['equity_value'], baseline['equity_value'])
        self.assertEqual(inactive['portfolio_events'], [])

    def test_event_money_preserves_typed_units_finite_values_and_cutoff(self):
        spec, values, inputs = self.supported_fixture()
        inputs['events'] = [dict(id='purchase', date='2025-06-30', net_cash=self.amount(-100.), cash_tax=self.amount(0.))]
        for change, message in [(dict(value=float('nan')), 'finite number'), (dict(value=True), 'finite number'),
                                (dict(unit='USD'), 'unit/scale'), (dict(currency='USD'), 'unit/scale'), (dict(scale=1.), 'unit/scale'),
                                (dict(as_of='2025-01-01'), 'information cutoff')]:
            with self.subTest(change=change):
                revised = copy.deepcopy(inputs)
                revised['events'][0]['net_cash'].update(change)
                with self.assertRaisesRegex(ValueError, message):
                    value_company(spec, values, revised, include_sensitivities=False)


class ValuationStageHandoffTests(unittest.TestCase):
    def test_research_uses_existing_journal_and_preserves_upstream_model(self):
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from company_initiation.dcf_construction.workflow import construct_valuation
        spec,values,_=fixture()
        data=dict(company=spec['company'],currency='GBP',observations=[{'value':1000.}],
            model_configuration={'as_of':'2024-12-31'})
        original=copy.deepcopy((spec,values,data))
        provider=SimpleNamespace(max_output_tokens=12000,timeout=240)
        journal=SimpleNamespace(directory=Path('synthetic-run'),provider=provider,progress=None)
        events=[];configuration={'assumptions':{'risk_free_rate':{'value':.04}}}
        def research(actual_journal,actual_data,documents,store):
            self.assertIs(actual_journal,journal)
            self.assertEqual((provider.max_output_tokens,provider.timeout),(16000,300))
            events.append('valuation_research')
            return configuration
        def snapshot(actual_spec,actual_values,actual_data,**kwargs):
            self.assertIs(actual_spec,spec);self.assertIs(actual_values,values)
            self.assertEqual(actual_data['model_configuration']['valuation'],configuration)
            self.assertEqual((provider.max_output_tokens,provider.timeout),(12000,240))
            events.append('dcf')
            return dict(result={'status':'provisional'},artifacts={},checks=[])
        with patch('company_initiation.dcf_construction.workflow._valuation_research_current',return_value=False), \
                patch('company_initiation.dcf_construction.workflow._valuation_research_documents',return_value=[]), \
                patch('company_initiation.dcf_construction.workflow.research_valuation_configuration',side_effect=research), \
                patch('company_initiation.dcf_construction.workflow.valuation_snapshot',side_effect=snapshot):
            result=construct_valuation(journal,spec,values,data,Path('synthetic-archive'))
        self.assertEqual(events,['valuation_research','dcf'])
        self.assertEqual((spec,values,data),original)
        self.assertEqual(result['company_inputs']['model_configuration']['valuation'],configuration)

    def test_current_research_needs_no_provider_or_original_reparse(self):
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from company_initiation.dcf_construction.workflow import construct_valuation
        spec,values,_=fixture()
        data=dict(company=spec['company'],currency='GBP',model_configuration={'as_of':'2024-12-31'})
        journal=SimpleNamespace(progress=None)
        with patch('company_initiation.dcf_construction.workflow._valuation_research_current',return_value=True), \
                patch('company_initiation.dcf_construction.workflow._valuation_research_documents',side_effect=AssertionError('No research on reuse')), \
                patch('company_initiation.dcf_construction.workflow.valuation_snapshot',return_value=dict(result={},artifacts={},checks=[])):
            result=construct_valuation(journal,spec,values,data,Path('synthetic-archive'))
        self.assertEqual(result['company_inputs'],data)

    def test_failed_research_restores_existing_provider_limits(self):
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        from company_initiation.dcf_construction.workflow import construct_valuation
        spec,values,_=fixture()
        data=dict(company=spec['company'],currency='GBP',model_configuration={'as_of':'2024-12-31'})
        provider=SimpleNamespace(max_output_tokens=12000,timeout=240)
        journal=SimpleNamespace(directory=Path('synthetic-run'),provider=provider,progress=None)
        with patch('company_initiation.dcf_construction.workflow._valuation_research_current',return_value=False), \
                patch('company_initiation.dcf_construction.workflow._valuation_research_documents',side_effect=ValueError('Unsupported evidence')):
            with self.assertRaisesRegex(ValueError,'Unsupported evidence'):
                construct_valuation(journal,spec,values,data,Path('synthetic-archive'))
        self.assertEqual((provider.max_output_tokens,provider.timeout),(12000,240))


if __name__ == '__main__':
    unittest.main()
