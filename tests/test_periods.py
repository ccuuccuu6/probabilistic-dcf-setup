"""Independent fiscal-calendar and linked-period financial examples."""
import copy
import unittest

from research_platform.periods import (build_periods,cell_dependencies,cell_formula_excel,
    calculate_periodic,validate_periodic,derive_observations,iter_identity_cells)


def observation(kind,value,**changes):
    period=next(p for p in build_periods([2024]) if p['kind']==kind)
    item=dict(id='original_'+kind,row_id='sales',metric='sales',entity_id='north',metric_type='flow',
        period_id=period['id'],fiscal_year=2024,kind=kind,start=period['start'],end=period['end'],
        definition='External sales',currency='GBP',unit='GBPm',basis='published_2024',scope='north_original',
        restatement='original',status='reported',value=value,source_refs=[dict(source_id='synthetic',cell=kind,raw=value)])
    item.update(changes);return item


def financial_spec():
    periods=build_periods([2025,2026])
    for p in periods:p['status']='actual' if p['fiscal_year']==2025 else 'forecast'
    def raw(value,status='actual',editable=False):return dict(value=value,status=status,editable=editable)
    def formula(expr,bindings=None):return dict(expression=expr,bindings=bindings or {},status='forecast')
    def bind(pid,row='sales'):return dict(row_id=row,period_id=pid)
    rows=[dict(id='price',kind='assumption',unit='ratio',cells={'2026-Q1':raw(.1,'forecast',True),'2026-Q2':raw(.2,'forecast',True)}),
          dict(id='cost_ratio',kind='assumption',unit='ratio',cells={'2026-Q1':raw(.6,'forecast',True),'2026-Q2':raw(.6,'forecast',True)}),
          dict(id='sales',kind='calculated',unit='GBPm',cells={'2025-Q1':raw(100),'2025-Q2':raw(200),
              '2026-Q1':formula('prior*(1+price)',{'prior':bind('2025-Q1')}),
              '2026-Q2':formula('prior*(1+price)',{'prior':bind('2025-Q2')}),
              '2026-H1':formula('q1+q2',{'q1':bind('2026-Q1'),'q2':bind('2026-Q2')})}),
          dict(id='cost',kind='calculated',unit='GBPm',cells={'2026-Q1':formula('-sales*cost_ratio'),'2026-Q2':formula('-sales*cost_ratio'),
              '2026-H1':formula('q1+q2',{'q1':bind('2026-Q1','cost'),'q2':bind('2026-Q2','cost')})}),
          dict(id='profit',kind='calculated',unit='GBPm',cells={p:formula('sales+cost') for p in ('2026-Q1','2026-Q2','2026-H1')}),
          dict(id='cash',kind='calculated',unit='GBPm',nonnegative=True,cells={'2025-FY':raw(100),
              '2026-Q1':formula('lag("cash",1)+profit',{'lag:cash:1':bind('2025-FY','cash')}),
              '2026-Q2':formula('lag("cash",1)+profit',{'lag:cash:1':bind('2026-Q1','cash')}),
              '2026-H1':formula('closing',{'closing':bind('2026-Q2','cash')})})]
    return dict(periods=periods,rows=rows,identities=[dict(id='income',label='Profit equals sales less costs',
        expression='profit-sales-cost',periods=['2026-Q1','2026-Q2','2026-H1'],tolerance=1e-8,independent=False)])


class FiscalCalendarTests(unittest.TestCase):
    def test_calendar_leap_year_display_order_and_noncalendar_labels(self):
        periods=build_periods([2024]);lookup={p['kind']:p for p in periods}
        self.assertEqual([p['kind'] for p in periods],['Q1','Q2','Q3','Q4','H1','H2','FY','9M'])
        self.assertEqual(lookup['Q1']['duration_days'],91);self.assertEqual(lookup['FY']['duration_days'],366)
        self.assertEqual(lookup['H1']['components'],['2024-Q1','2024-Q2']);self.assertTrue(lookup['9M']['hidden'])
        october=build_periods([2024],{'fiscal_start_month':10})
        self.assertEqual(october[0]['start'],'2023-10-01');self.assertEqual(october[6]['end'],'2024-09-30')
        labelled=build_periods([2024],{'fiscal_year_end':'09-30','label_by_start':True})
        self.assertEqual(labelled[0]['start'],'2024-10-01');self.assertEqual(labelled[6]['end'],'2025-09-30')

    def test_explicit_retail_quarters_support_period_id_alias_and_reject_overlap(self):
        boundaries=[('2024-02-04','2024-05-04'),('2024-05-05','2024-08-03'),('2024-08-04','2024-11-02'),('2024-11-03','2025-02-01')]
        explicit=[dict(period_id=f'retail-{q}',fiscal_year=2025,kind=f'Q{q}',start=s,end=e) for q,(s,e) in enumerate(boundaries,1)]
        periods=build_periods([2025],{'periods':explicit})
        self.assertEqual(periods[6]['duration_days'],364);self.assertEqual(next(p for p in periods if p['kind']=='H1')['end'],'2024-08-03')
        explicit[1]['start']='2024-05-04'
        with self.assertRaisesRegex(ValueError,'contiguous'):build_periods([2025],{'periods':explicit})

    def test_fixed_february_end_remains_exact_across_leap_year(self):
        periods=build_periods([2024,2025],{'fiscal_year_end':'02-28'})
        annual={p['fiscal_year']:p for p in periods if p['kind']=='FY'}
        self.assertEqual(annual[2024]['end'],'2024-02-28')
        self.assertEqual(annual[2024]['duration_days'],365)
        self.assertEqual(annual[2025]['start'],'2024-02-29')
        self.assertEqual(annual[2025]['end'],'2025-02-28')
        self.assertEqual(annual[2025]['duration_days'],366)


class BoundPeriodGraphTests(unittest.TestCase):
    def test_dormant_buyback_has_no_execution_price_and_condition_is_lazy(self):
        period=build_periods([2026])[-2]
        pid=period['id']
        spec=dict(periods=[period],identities=[],rows=[
            dict(id='cash',kind='assumption',unit='GBPm',cells={pid:dict(value=0,editable=True,status='forecast')}),
            dict(id='price',kind='assumption',unit='GBPm/shares_m',cells={pid:dict(value=None,editable=True,status='forecast',required=False)}),
            dict(id='shares',kind='calculated',unit='shares_m',cells={pid:dict(expression='if_zero(cash, 0, cash / price)',status='forecast')})])
        self.assertEqual(calculate_periodic(spec)['shares'][pid],0)
        self.assertIsNone(calculate_periodic(spec,{'cash':{pid:100}})['shares'][pid])
        self.assertEqual(calculate_periodic(spec,{'cash':{pid:100},'price':{pid:25}})['shares'][pid],4)
        with self.assertRaisesRegex(ValueError,'Division by zero'):
            calculate_periodic(spec,{'cash':{pid:100},'price':{pid:0}})
        excel=cell_formula_excel(spec['rows'][2]['cells'][pid],pid,lambda rid,p:rid+'_cell')
        self.assertIn('=0,0,',excel)
        self.assertNotIn('IFERROR',excel)

    def test_integrated_quarters_half_year_stock_and_assumption_changes(self):
        spec=financial_spec();values=calculate_periodic(spec)
        self.assertAlmostEqual(values['sales']['2026-H1'],350)
        self.assertAlmostEqual(values['profit']['2026-H1'],140)
        self.assertAlmostEqual(values['cash']['2026-H1'],240)
        self.assertEqual(values['cash']['2026-H1'],values['cash']['2026-Q2'])
        self.assertTrue(all(c['status']=='PASS' for c in validate_periodic(spec,values)))
        changed=calculate_periodic(spec,{'price':{'2026-Q1':.2}})
        tuple_changed=calculate_periodic(spec,{('price','2026-Q1'):.2})
        self.assertEqual(changed,tuple_changed)
        self.assertAlmostEqual(changed['sales']['2026-H1'],360)
        self.assertAlmostEqual(changed['cash']['2026-H1'],244)
        zero=calculate_periodic(spec,{('price','2026-Q1'):0})
        self.assertEqual(zero['sales']['2026-Q1'],100)
        missing=calculate_periodic(spec,{('price','2026-Q1'):None})
        self.assertIsNone(missing['cash']['2026-H1'])
        self.assertTrue(any(c['status']=='MISSING' for c in validate_periodic(spec,missing)))

    def test_excel_bindings_and_identity_cells_match_python_references(self):
        cell=financial_spec()['rows'][-1]['cells']['2026-Q2']
        self.assertEqual(cell_dependencies(cell,'2026-Q2'),[
            dict(symbol='cash',lag=1,row_id='cash',period_id='2026-Q1'),
            dict(symbol='profit',lag=0,row_id='profit',period_id='2026-Q2')])
        formula=cell_formula_excel(cell,'2026-Q2',lambda row,pid:f'{row}_{pid}')
        self.assertIn('(cash_2026-Q1+profit_2026-Q2)',formula)
        self.assertIn('ISNUMBER(cash_2026-Q1)',formula)
        self.assertIn('ISERROR(profit_2026-Q2)',formula)
        self.assertNotIn('IFERROR',formula)
        spec=financial_spec();spec['identities'][0]['cells']={'2026-H1':dict(expression='profit-sales-cost')}
        self.assertEqual([pid for _,pid,_ in iter_identity_cells(spec)],['2026-H1'])
        self.assertTrue(all(c['status']=='PASS' for c in validate_periodic(spec,calculate_periodic(spec))))

    def test_cycle_unknown_binding_unit_error_and_division_by_zero_are_visible(self):
        mutations=[('Circular',lambda s:s['rows'][0]['cells']['2026-Q1'].update(value=None,expression='sales/sales')),
                   ('Unknown',lambda s:s['rows'][2]['cells']['2026-Q1']['bindings']['prior'].update(row_id='absent')),
                   ('units',lambda s:s['rows'][2]['cells']['2026-Q1'].update(expression='price+cost_ratio')),
                   ('Division by zero',lambda s:s['rows'][2]['cells']['2026-Q1'].update(expression='prior/(price-price)'))]
        for reason,mutate in mutations:
            with self.subTest(reason=reason):
                spec=financial_spec();mutate(spec)
                with self.assertRaisesRegex(ValueError,reason):calculate_periodic(spec)
        with self.assertRaisesRegex(ValueError,'Explicit period binding'):
            cell_dependencies(dict(expression='lag("sales",1)'),'2026-Q1')

    def test_historical_and_previous_forecast_calibration_allowed_current_result_rejected(self):
        spec=financial_spec()
        seed=dict(id='seed',kind='assumption',unit='GBPm',cells={
            '2026-Q1':dict(expression='old',bindings={'old':dict(row_id='sales',period_id='2025-Q1')},status='forecast'),
            '2026-Q2':dict(expression='previous',bindings={'previous':dict(row_id='sales',period_id='2026-Q1')},status='forecast')})
        spec['rows'].append(seed)
        self.assertAlmostEqual(calculate_periodic(spec)['seed']['2026-Q2'],110)
        seed['cells']['2026-Q2']['bindings']['previous']['period_id']='2026-Q2'
        with self.assertRaisesRegex(ValueError,'cannot initialise an assumption'):calculate_periodic(spec)

    def test_nonnegative_balances_and_changed_results_do_not_pass_validation(self):
        spec=financial_spec();values=calculate_periodic(spec)
        values['cash']['2026-Q2']=-1;values['profit']['2026-H1']=200
        checks=validate_periodic(spec,values)
        self.assertTrue(any(c['area']=='period_identity' and c['status']=='FAIL' for c in checks))
        self.assertTrue(any(c['area']=='period_values' and c['status']=='FAIL' for c in checks))
        self.assertTrue(any(c['area']=='period_formula' and c['status']=='FAIL' for c in checks))
        with self.assertRaisesRegex(ValueError,'authoritative editable'):
            calculate_periodic(spec,{('sales','2026-Q1'):123})

    def test_editable_formula_assumption_can_be_overridden_without_rewriting_calibration(self):
        spec=financial_spec()
        cell=dict(expression='a/b',bindings={'a':dict(row_id='sales',period_id='2025-Q1'),
            'b':dict(row_id='sales',period_id='2025-Q2')},status='forecast',editable=True)
        spec['rows'][1]['cells']['2026-Q1']=cell
        baseline=calculate_periodic(spec)
        self.assertEqual(baseline['cost_ratio']['2026-Q1'],.5)
        changed=calculate_periodic(spec,{'cost_ratio':{'2026-Q1':.7}})
        self.assertAlmostEqual(changed['cash']['2026-H1'],229)
        self.assertTrue(all(c['status']=='PASS' for c in validate_periodic(spec,changed)))
        self.assertEqual(cell['expression'],'a/b')
        self.assertEqual(calculate_periodic(spec),baseline)


class ObservationDerivationTests(unittest.TestCase):
    def test_rejected_sources_cannot_reappear_as_derived_actuals(self):
        for rejection in ({'status':'excluded'},{'status':'vendor_unverified'},{'eligible':False}):
            with self.subTest(rejection=rejection):
                originals=[observation('Q1',10,**rejection),observation('H1',30)]
                result=derive_observations(originals,build_periods([2024]))
                self.assertEqual(result['observations'][:2][0]['value'],10)
                self.assertFalse(any(o['kind']=='Q2' for o in result['derived']))
        result=derive_observations([observation('Q1',10,status='estimate'),observation('H1',30)],build_periods([2024]))
        self.assertEqual(next(o for o in result['derived'] if o['kind']=='Q2')['status'],'estimate')
        result=derive_observations([observation('Q1',10,status='derived'),observation('H1',30)],build_periods([2024]))
        self.assertEqual(result['observations'][0]['source_status'],'derived')
        self.assertEqual(result['observations'][0]['status'],'derived_actual')
        self.assertEqual(next(o for o in result['derived'] if o['kind']=='Q2')['value'],20)

    def test_conflicting_reported_periods_fail_model_validation(self):
        originals=[observation('Q1',10),observation('Q2',25),observation('H1',30)]
        derived=derive_observations(originals,build_periods([2024]))
        self.assertTrue(any(c['status']=='FAIL' for c in derived['checks']))
        spec=financial_spec();spec['derivation_checks']=derived['checks']
        checks=validate_periodic(spec,calculate_periodic(spec))
        self.assertTrue(any(c['area']=='period_derivation' and c['status']=='FAIL' for c in checks))

    def test_derived_quarters_and_h2_preserve_originals_formula_and_sources(self):
        originals=[observation('Q1',10),observation('H1',30),observation('9M',60),observation('FY',100)]
        before=copy.deepcopy(originals);result=derive_observations(originals,build_periods([2024]))
        self.assertEqual(originals,before)
        derived={o['kind']:o for o in result['derived']}
        self.assertEqual({k:derived[k]['value'] for k in ('Q2','Q3','Q4','H2')},{'Q2':20,'Q3':30,'Q4':40,'H2':70})
        self.assertEqual(derived['Q2']['expression'],'s0-s1')
        self.assertEqual(derived['Q2']['bindings']['s0']['period_id'],'2024-H1')
        self.assertEqual([r['contribution_weight'] for r in derived['Q2']['source_refs']],[1,-1])
        self.assertEqual(derived['Q2']['status'],'derived_actual')
        self.assertEqual(result['observations'][0]['source_status'],'reported')
        self.assertTrue(all(c['status']=='PASS' for c in result['checks']))

    def test_explicit_compatibility_key_allows_disclosed_equivalent_basis_only(self):
        q1=observation('Q1',10);half=observation('H1',30,basis='restated',restatement='company_restated')
        self.assertFalse(derive_observations([q1,half],build_periods([2024]))['derived'])
        q1['compatibility_key']=half['compatibility_key']='verified_equivalent_scope'
        self.assertEqual(derive_observations([q1,half],build_periods([2024]))['derived'][0]['value'],20)
        for field in ('definition','currency','unit','scope'):
            changed=copy.deepcopy(half);changed[field]='different'
            self.assertFalse(derive_observations([q1,changed],build_periods([2024]))['derived'])

    def test_verified_definition_id_bridges_labels_without_guessing(self):
        q1=observation('Q1',10,definition='Sales',definition_id='external_sales')
        half=observation('H1',30,definition='External revenue',definition_id='external_sales')
        result=derive_observations([q1,half],build_periods([2024]))
        self.assertEqual(result['derived'][0]['value'],20)
        self.assertEqual(result['observations'][0]['definition'],'Sales')
        self.assertEqual(result['observations'][1]['definition'],'External revenue')
        half['definition_id']='gross_including_internal_sales'
        self.assertFalse(derive_observations([q1,half],build_periods([2024]))['derived'])

    def test_stocks_use_closing_aliases_and_rates_eps_are_never_subtracted(self):
        cash=observation('FY',50,row_id='cash',metric='cash',metric_type='stock',definition='Closing cash',measurement_date='2024-12-31')
        result=derive_observations([cash],build_periods([2024]))
        self.assertEqual({o['kind']:o['value'] for o in result['derived']},{'Q4':50,'H2':50})
        for metric,type_ in [('margin','ratio'),('eps','flow'),('pricing','flow')]:
            data=[observation('H1',.2,metric=metric,metric_type=type_),observation('FY',.3,metric=metric,metric_type=type_)]
            self.assertFalse(derive_observations(data,build_periods([2024]))['derived'])

    def test_conflicting_originals_and_wrong_duration_are_not_forced_together(self):
        data=[observation('Q1',10),observation('Q1',11,id='second_q1'),observation('H1',30)]
        result=derive_observations(data,build_periods([2024]))
        self.assertFalse(result['derived']);self.assertTrue(any(c['status']=='FAIL' for c in result['checks']))
        data=[observation('Q1',10,id='same_source_id'),observation('H1',30,id='same_source_id')]
        with self.assertRaisesRegex(ValueError,'identities'):
            derive_observations(data,build_periods([2024]))
        data=[observation('Q1',10,duration_days=90),observation('H1',30)]
        result=derive_observations(data,build_periods([2024]))
        self.assertFalse(result['derived']);self.assertTrue(any(c['status']=='FAIL' for c in result['checks']))

    def test_opening_stocks_share_opening_dates_and_shares_need_no_currency(self):
        opening=observation('FY',50,row_id='opening_cash',metric='opening_cash',metric_type='stock',
                            definition='Opening cash',measurement_date='2023-12-31')
        result=derive_observations([opening],build_periods([2024]))
        self.assertEqual({o['kind'] for o in result['derived']},{'Q1','H1','9M'})
        self.assertTrue(all(o['measurement_date']=='2023-12-31' for o in result['derived']))
        shares=observation('FY',10,row_id='shares_issued',metric='shares_issued',metric_type='stock',unit='shares_m',currency=None)
        result=derive_observations([shares],build_periods([2024]))
        self.assertEqual({o['kind'] for o in result['derived']},{'Q4','H2'})
        self.assertFalse(result['checks'])


if __name__=='__main__':unittest.main()
