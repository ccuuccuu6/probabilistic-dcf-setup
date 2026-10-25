"""Independent fiscal-calendar and linked-period financial examples."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
    def test_derived_period_retains_all_source_vintages_and_latest_publication(self):
        first=observation('Q1',100,published_at='2024-04-20',source_vintage=[dict(source_id='q1',published_at='2024-04-20',publication_status='source_verified')])
        half=observation('H1',250,published_at='2024-08-15',source_vintage=[dict(source_id='h1',published_at='2024-08-15',publication_status='source_verified')])
        quarter=next(o for o in derive_observations([first,half],build_periods([2024]))['derived'] if o['kind']=='Q2')
        self.assertEqual(quarter['published_at'],'2024-08-15')
        self.assertEqual({v['source_id'] for v in quarter['source_vintage']},{'q1','h1'})
        half.pop('published_at');half['source_vintage'][0].update(published_at=None,publication_status='unknown')
        quarter=next(o for o in derive_observations([first,half],build_periods([2024]))['derived'] if o['kind']=='Q2')
        self.assertNotIn('published_at',quarter)
        self.assertEqual(len(quarter['source_vintage']),2)

    def test_scope_carryover_uses_current_and_comparable_inclusion(self):
        from research_platform.integrated import scope_period_inclusion
        event=dict(effective_date='2026-10-01',calendar_month_weights=[1/12]*12)
        excluded=[scope_period_inclusion(event,f'{y}-01-01',f'{y}-12-31') for y in (2025,2026,2027,2028)]
        reductions=[100*(b-a) for a,b in zip(excluded,excluded[1:])]
        for actual,expected in zip(reductions,[25,75,0]):self.assertAlmostEqual(actual,expected)
        self.assertAlmostEqual(100*(1-excluded[1]),75)
        self.assertAlmostEqual(100*(1-excluded[2]),0)
        event['calendar_month_weights']=[.05]*6+[.1]*4+[.15]*2
        self.assertAlmostEqual(scope_period_inclusion(event,'2026-01-01','2026-12-31'),.4)

    def test_estimated_event_accounting_uses_independent_closing_inputs(self):
        from research_platform.integrated import estimate_scope_events
        event=dict(id='sale',type='disposal',source_refs=[{'source_id':'fixture'}],estimation=dict(method='Explicit fixture estimates',
            annual_revenue=100,operating_margin=.2,annual_da=5,cost_weights={'production':.8,'marketing':.2},
            closing=dict(consideration=400,cash_transferred=20,assets={'owned_ppe':300},liabilities={'trade_payables':80},retained_investment=60,cta_recycling=15,net_assets_check=240)))
        result=estimate_scope_events([event])[0]
        self.assertEqual(result['annual_cash_costs'],{'production':-60,'marketing':-15})
        self.assertEqual(result['cash_flows']['business_disposals_cf'],380)
        self.assertEqual(result['gain_loss'],205);self.assertEqual(result['oci_reclassification'],15)
        self.assertEqual(result['balance_movements'],{'owned_ppe':-300,'trade_payables':-80,'associates':60})
        self.assertNotIn('gain_loss',event)
        event['estimation']['closing']['net_assets_check']=241
        with self.assertRaisesRegex(ValueError,'net asset'):estimate_scope_events([event])

    def test_typed_scenario_evaluates_multiple_drivers_without_changing_history_or_formulas(self):
        from research_platform.periods import assumption_contract,apply_assumption_payload,model_logic_digest
        spec=financial_spec();spec.update(company='Typed fixture',currency='GBP')
        contract=assumption_contract(spec);before=model_logic_digest(spec)
        fields={(f['driver_id'],f['period_id']):f for f in contract['fields']}
        inputs=[]
        for rid,value in [('price',.3),('cost_ratio',.5)]:
            field=fields[rid,'2026-Q1']
            inputs.append({**{k:field[k] for k in ('driver_id','period_id','unit','currency','frequency','value_type')},'value':value})
        payload=dict(schema='financial_assumptions_v1',company=spec['company'],scenario_id='test',as_of='2026-01-01',model_digest=before,inputs=inputs)
        apply_assumption_payload(spec,payload);result=calculate_periodic(spec)
        self.assertEqual(result['sales']['2026-Q1'],130);self.assertEqual(result['profit']['2026-Q1'],65)
        self.assertEqual(result['sales']['2025-Q1'],100);self.assertEqual(model_logic_digest(spec),before)
        for change in ({'driver_id':'profit'},{'period_id':'2025-Q1'},{'unit':'EURm'},{'frequency':'FY'},{'value':float('nan')}):
            invalid=copy.deepcopy(payload);invalid['inputs'][0].update(change)
            with self.assertRaises(ValueError):apply_assumption_payload(spec,invalid)
        self.assertEqual(calculate_periodic(spec)['profit']['2026-Q1'],65)

    def test_typed_refresh_preserves_overrides_and_rejects_stale_targets(self):
        from research_platform.periods import assumption_contract,apply_assumption_payload
        spec=financial_spec();spec.update(company='Typed fixture',currency='GBP');contract=assumption_contract(spec)
        field=contract['fields'][0];item={k:field[k] for k in ('driver_id','period_id','unit','currency','frequency','value_type')};item['value']=.3
        payload=dict(schema='financial_assumptions_v1',company=spec['company'],scenario_id='keep',as_of='2026-01-01',model_digest=contract['model_digest'],inputs=[item])
        apply_assumption_payload(spec,payload)
        fresh=financial_spec();fresh.update(company=spec['company'],currency='GBP');fresh['rows'][0]['cells']['2026-Q1']['value']=.9
        apply_assumption_payload(fresh,payload,allow_model_refresh=True)
        self.assertEqual(calculate_periodic(fresh)['sales']['2026-Q1'],130)
        fresh['rows'][0]['cells']['2026-Q1']['editable']=False
        with self.assertRaises(ValueError):apply_assumption_payload(fresh,payload,allow_model_refresh=True)

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


class TypedAssumptionContractTests(unittest.TestCase):
    def setUp(self):
        self.spec=financial_spec()
        self.spec.update(company='SYNTHETIC typed input fixture',currency='GBP',model_configuration={'as_of':'2026-01-01'})

    def payload(self,spec,changes,**extra):
        from research_platform.periods import assumption_contract
        contract=assumption_contract(spec)
        fields={(f['driver_id'],f['period_id']):f for f in contract['fields']}
        inputs=[]
        for rid,pid,value in changes:
            item={k:fields[rid,pid][k] for k in ('driver_id','period_id','unit','currency','frequency','value_type')}
            inputs.append(dict(item,value=value))
        return dict(schema='financial_assumptions_v1',company=spec['company'],scenario_id='independent-test',
                    as_of='2026-01-02',model_digest=contract['model_digest'],inputs=inputs,**extra)

    def test_contract_shape_includes_support_controls_and_excludes_every_historical_baseline_marker(self):
        from research_platform.periods import assumption_contract,apply_assumption_payload
        self.spec['driver_registry']=[dict(driver_id='price',entity_id='north',cost_pool='production',
            parameter_role='forecast_assumption',value_type='growth_rate',currency_basis='Functional-currency price')]
        self.spec['rows'][0].update(label='Price growth',source_refs=[{'source_id':'synthetic-disclosure'}])
        self.spec['rows'][0]['cells']['2026-Q1'].update(expression='prior',bindings={'prior':{'row_id':'price','period_id':'2025-Q1'}},reason='Carry the prior disclosed input')
        self.spec['rows'][0]['cells']['2026-Q1'].pop('value')
        self.spec['rows'][0]['cells']['2025-Q1']=dict(value=.1,status='actual',editable=True)
        self.spec['rows'].append(dict(id='functional_translation_weight',kind='assumption',unit='ratio',assumption_support=True,
            cells={'2026-Q1':dict(value=.4,status='forecast',editable=True)}))
        markers=[{'status':'estimated_historical'},{'data_role':'estimated_historical_baseline'},
                 {'classification':'estimated_historical_baseline'},{'calibration_eligible':False}]
        for n,marker in enumerate(markers):
            self.spec['rows'].append(dict(id=f'baseline_{n}',kind='assumption',unit='ratio',
                cells={'2026-Q1':dict({'value':.2,'status':'estimated','editable':True},**marker)}))
        self.spec['rows'][4]['cells']['2026-Q1']['editable']=True  # A calculated output cannot become an input.
        contract=assumption_contract(self.spec)
        fields={(f['driver_id'],f['period_id']):f for f in contract['fields']}
        required={'driver_id','period_id','classification','meaning','company','entity','cost_pool','frequency',
            'period_start','period_end','unit','currency','sign','value_type','basis','historical_anchor','anchor_date',
            'dependencies','constraints','default','default_expression','evidence','method','provisional','override_precedence'}
        self.assertEqual(contract['schema'],'financial_input_contract_v1')
        self.assertEqual(contract['as_of'],'2026-01-01')
        self.assertEqual(set(fields['price','2026-Q1']),required)
        price=fields['price','2026-Q1']
        self.assertEqual((price['entity'],price['cost_pool'],price['value_type']),('north','production','growth_rate'))
        self.assertEqual((price['period_start'],price['period_end']),('2026-01-01','2026-03-31'))
        self.assertEqual(price['historical_anchor'],[{'driver_id':'price','period_id':'2025-Q1'}])
        self.assertEqual(price['anchor_date'],'2025-03-31')
        self.assertEqual(price['evidence'],[{'source_id':'synthetic-disclosure'}])
        self.assertIsNone(price['currency'])
        self.assertEqual(fields['functional_translation_weight','2026-Q1']['constraints'],{'minimum':0,'maximum':1})
        self.assertNotIn(('price','2025-Q1'),fields)
        self.assertNotIn(('profit','2026-Q1'),fields)
        for n in range(len(markers)):
            self.assertNotIn((f'baseline_{n}','2026-Q1'),fields)
            self.assertEqual(contract['classifications'][f'baseline_{n}']['2026-Q1'],'estimated_historical_baseline')
        apply_assumption_payload(self.spec,self.payload(self.spec,[('functional_translation_weight','2026-Q1',.7)]))
        self.assertEqual(calculate_periodic(self.spec)['functional_translation_weight']['2026-Q1'],.7)
        for invalid in (-.01,1.01):
            with self.assertRaisesRegex(ValueError,'violates'):
                apply_assumption_payload(self.spec,self.payload(self.spec,[('functional_translation_weight','2026-Q1',invalid)]))
        self.assertEqual(calculate_periodic(self.spec)['functional_translation_weight']['2026-Q1'],.7)

    def test_payload_rejects_invalid_types_dates_metadata_and_duplicates_atomically(self):
        from research_platform.periods import apply_assumption_payload
        original=self.payload(self.spec,[('price','2026-Q1',.3),('cost_ratio','2026-Q1',.5)])
        apply_assumption_payload(self.spec,original)
        baseline=copy.deepcopy(self.spec)
        cases=[]
        for attr,value in [('unit','EURm'),('currency','EUR'),('frequency','FY'),('value_type','incremental_amount'),
                           ('value',True),('value',None),('value','0.3'),('value',float('inf')),('value',float('nan')),
                           ('driver_id','profit'),('period_id','2025-Q1')]:
            bad=copy.deepcopy(original);bad['inputs'][0][attr]=value;cases.append((attr+repr(value),bad))
        for attr,value in [('as_of','2026-02-30'),('as_of','2025-12-31'),('as_of',''),('company','Other fixture'),
                           ('schema','wrong'),('scenario_id',''),('model_digest','different-model')]:
            bad=copy.deepcopy(original);bad[attr]=value;cases.append((attr+repr(value),bad))
        bad=copy.deepcopy(original);bad['inputs'].append(copy.deepcopy(bad['inputs'][0]));cases.append(('duplicate',bad))
        for label,payload in cases:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):apply_assumption_payload(self.spec,payload)
                self.assertEqual(self.spec,baseline)
        self.assertEqual(calculate_periodic(self.spec)['profit']['2026-Q1'],65)

    def test_native_money_exposure_and_event_ratio_metadata_preserve_economic_types(self):
        from research_platform.periods import assumption_contract,apply_assumption_payload
        definitions=[('foreign_cash_weight','ratio','exposure_assumption',.3),
                     ('foreign_cash_movement','USDm','exposure_assumption',20),
                     ('foreign_share_price','EURm/shares_m','economic_input',5),
                     ('scope_disposal_tax_rate','ratio','economic_input',.2),
                     ('scope_disposal_nci_share','ratio','allocation',.1),
                     ('scope_disposal_proceeds','GBPm','economic_input',100)]
        self.spec['driver_registry']=[]
        for rid,unit,role,value in definitions:
            self.spec['rows'].append(dict(id=rid,kind='assumption',unit=unit,
                cells={'2026-Q1':dict(value=value,status='forecast',editable=True)}))
            self.spec['driver_registry'].append(dict(driver_id=rid,parameter_role=role))
        fields={f['driver_id']:f for f in assumption_contract(self.spec)['fields']}
        self.assertEqual(fields['foreign_cash_weight']['classification'],'structural_parameter')
        self.assertEqual(fields['foreign_cash_movement']['classification'],'forecast_assumption')
        self.assertEqual(fields['foreign_cash_movement']['currency'],'USD')
        self.assertEqual(fields['foreign_share_price']['currency'],'EUR')
        self.assertEqual(fields['scope_disposal_proceeds']['currency'],'GBP')
        self.assertEqual(fields['scope_disposal_proceeds']['value_type'],'incremental_amount')
        for rid in ('scope_disposal_tax_rate','scope_disposal_nci_share'):
            self.assertEqual(fields[rid]['value_type'],'level')
            self.assertIsNone(fields[rid]['currency'])
            self.assertEqual(fields[rid]['constraints'],{'minimum':0,'maximum':1})
            with self.assertRaisesRegex(ValueError,'violates'):
                apply_assumption_payload(self.spec,self.payload(self.spec,[(rid,'2026-Q1',1.01)]))
        payload=self.payload(self.spec,[('foreign_cash_movement','2026-Q1',25)])
        payload['inputs'][0]['currency']='GBP'
        with self.assertRaisesRegex(ValueError,'currency'):apply_assumption_payload(self.spec,payload)

    def test_literal_default_uses_only_explicit_anchor_and_keeps_row_method_when_cell_reason_empty(self):
        from research_platform.periods import assumption_contract
        row=self.spec['rows'][0]
        row['note']='Hold the explicitly selected historical price contribution.'
        row['cells']['2025-Q1']=dict(value=.1,status='actual',editable=False)
        row['cells']['2026-Q1'].update(reason='',initialization_anchor_periods=['2025-Q1'])
        row['cells']['2026-Q2'].update(reason='')
        fields={(f['driver_id'],f['period_id']):f for f in assumption_contract(self.spec)['fields']}
        self.assertEqual(fields['price','2026-Q1']['historical_anchor'],[{'driver_id':'price','period_id':'2025-Q1'}])
        self.assertEqual(fields['price','2026-Q1']['anchor_date'],'2025-03-31')
        self.assertEqual(fields['price','2026-Q1']['method'],row['note'])
        # An equal historical value and generic prose do not create an evidence relationship.
        self.assertEqual(fields['price','2026-Q2']['historical_anchor'],[])

    def test_structural_absence_is_read_only_structure_in_both_historical_and_future_periods(self):
        from research_platform.periods import assumption_contract,apply_assumption_payload
        for role in ('structural_absence','structural_parameter'):
            self.spec['rows'].append(dict(id=role,kind='assumption',unit='GBPm',cells={
                '2025-Q1':dict(value=0,status='derived_actual',data_role=role,calibration_eligible=False,editable=True),
                '2026-Q1':dict(value=0,status='forecast',data_role=role,calibration_eligible=False,editable=True),
                '2026-Q2':dict(value=0,status='forecast',data_role=role,editable=True)}))
        contract=assumption_contract(self.spec)
        keys={(f['driver_id'],f['period_id']) for f in contract['fields']}
        for role in ('structural_absence','structural_parameter'):
            for pid in ('2025-Q1','2026-Q1','2026-Q2'):
                self.assertEqual(contract['classifications'][role][pid],'structural_parameter')
                self.assertNotIn((role,pid),keys)
            payload=self.payload(self.spec,[('price','2026-Q1',.2)])
            payload['inputs'][0].update(driver_id=role,unit='GBPm',currency='GBP',value=10)
            with self.assertRaisesRegex(ValueError,'not an authoritative writable'):
                apply_assumption_payload(self.spec,payload)

    def test_adjacent_inputs_allowed_and_overlapping_frequency_inputs_rejected_including_saved_values(self):
        from research_platform.periods import apply_assumption_payload
        self.spec['rows'][0]['cells']['2026-H1']=dict(value=.1,status='forecast',editable=True)
        adjacent=self.payload(self.spec,[('price','2026-Q1',.3),('price','2026-Q2',.4)])
        apply_assumption_payload(self.spec,adjacent)
        self.assertEqual(calculate_periodic(self.spec)['sales']['2026-H1'],410)
        baseline=copy.deepcopy(self.spec)
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            apply_assumption_payload(self.spec,self.payload(self.spec,[('price','2026-H1',.5)]))
        self.assertEqual(self.spec,baseline)
        # Replacing the complete scenario explicitly makes a half-year control non-overlapping.
        apply_assumption_payload(self.spec,self.payload(self.spec,[('price','2026-H1',.5)],replace_existing=True))
        self.assertEqual(self.spec['assumption_overrides'],{'price':{'2026-H1':.5}})

    def test_partial_payload_preserves_prior_values_and_explicit_replacement_resets_them(self):
        from research_platform.periods import apply_assumption_payload,model_logic_digest
        digest=model_logic_digest(self.spec)
        apply_assumption_payload(self.spec,self.payload(self.spec,[('price','2026-Q1',.3)]))
        apply_assumption_payload(self.spec,self.payload(self.spec,[('cost_ratio','2026-Q1',.5)]))
        self.assertEqual(calculate_periodic(self.spec)['profit']['2026-Q1'],65)
        self.assertEqual(len(self.spec['assumption_payload']['inputs']),2)
        apply_assumption_payload(self.spec,self.payload(self.spec,[('cost_ratio','2026-Q1',.5)],replace_existing=True))
        self.assertAlmostEqual(calculate_periodic(self.spec)['profit']['2026-Q1'],55)
        self.assertEqual(model_logic_digest(self.spec),digest)
        self.assertEqual(self.spec['rows'][0]['cells']['2026-Q1']['value'],.1)

    def test_saved_backend_evaluation_versions_artifacts_preserves_fx_and_never_calls_ai_or_excel(self):
        from research_platform.periods import evaluate_saved_model,model_logic_digest
        from research_platform.integrated import verified_integrated_record
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);parent=root/'outputs'/'parent';parent.mkdir(parents=True)
            (parent/'model_specification.json').write_text(json.dumps(self.spec),encoding='utf-8')
            (parent/'calls.jsonl').write_text('',encoding='utf-8')
            (parent/'company_model_inputs.json').write_text('{"company":"synthetic"}',encoding='utf-8')
            fx_bytes=b'{"schema":"synthetic-immutable-fx","rate":1.25}\n'
            (parent/'fx_snapshot.json').write_bytes(fx_bytes)
            hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.iterdir()}
            (parent/'record.json').write_text(json.dumps(dict(directory=str(parent),calls=[],sources=[],artifacts=hashes)),encoding='utf-8')
            payload_path=root/'scenario.json'
            payload_path.write_text(json.dumps(self.payload(self.spec,[('price','2026-Q1',.3),('cost_ratio','2026-Q1',.5)])),encoding='utf-8')
            with patch('research_platform.ai.OpenAIProvider',side_effect=AssertionError('Backend evaluation must not create an AI provider')), \
                 patch('research_platform.model_excel.export_integrated',side_effect=AssertionError('Backend evaluation must not export Excel')):
                result=evaluate_saved_model(root,'parent',payload_path)
                replay=evaluate_saved_model(root,result)
            self.assertNotEqual(result,replay)
            for directory in (result,replay):
                saved=json.loads((directory/'model_specification.json').read_text(encoding='utf-8'))
                values=json.loads((directory/'forecast.json').read_text(encoding='utf-8'))
                evaluation=json.loads((directory/'evaluation.json').read_text(encoding='utf-8'))
                self.assertEqual(values['sales']['2026-Q1'],130)
                self.assertEqual(values['profit']['2026-Q1'],65)
                self.assertEqual(saved['rows'],self.spec['rows'])
                self.assertEqual(model_logic_digest(saved),model_logic_digest(self.spec))
                self.assertEqual((directory/'fx_snapshot.json').read_bytes(),fx_bytes)
                self.assertEqual((evaluation['ai_calls'],evaluation['excel_used']),(0,False))
                self.assertEqual(evaluation['status'],'scenario_evaluated_provisional')
                self.assertFalse((directory/'model.xlsx').exists())
                self.assertTrue(verified_integrated_record(directory,root/'outputs')['_reuse_verified'])
            for name,digest in hashes.items():self.assertEqual(hashlib.sha256((parent/name).read_bytes()).hexdigest(),digest)

    def test_export_projects_saved_overrides_without_mutating_default_formulas_or_history(self):
        from openpyxl import load_workbook
        from research_platform.model_excel import export_integrated
        from research_platform.periods import apply_assumption_payload,model_logic_digest
        from tests.test_model_excel import periodic_example
        spec,_=periodic_example()
        # A sourced default expression remains in the backend while the scenario is an authoritative value.
        growth=next(row for row in spec['rows'] if row['id']=='growth')
        growth['cells']['2026-Q1']=dict(expression='prior/annual',bindings={
            'prior':dict(row_id='sales',period_id='2025-Q1'),'annual':dict(row_id='sales',period_id='2025-FY')},status='forecast',editable=True)
        apply_assumption_payload(spec,self.payload(spec,[('growth','2026-Q1',.3)]))
        before=copy.deepcopy(spec);digest=model_logic_digest(spec);values=calculate_periodic(spec)
        self.assertEqual(values['sales']['2026-Q1'],13)
        self.assertEqual(values['sales']['2026-FY'],103)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'scenario.xlsx';audit=export_integrated(path,spec,values,[])
            with path.open('rb') as stream:
                workbook=load_workbook(stream)
                control=audit['assumption_cells']['growth']['2026-Q1']['cell']
                output=audit['period_columns']['2026-Q1']+str(audit['model_rows']['sales'])
                annual=audit['period_columns']['2026-FY']+str(audit['model_rows']['sales'])
                self.assertEqual(workbook['Assumptions'][control].value,.3)
                self.assertIn("'Assumptions'!"+control,workbook['Model'][output].value)
                self.assertEqual(audit['expected_assumption_cells'][control],.3)
                self.assertEqual(audit['expected_model_cells'][output],13)
                self.assertEqual(audit['expected_model_cells'][annual],103)
                self.assertTrue(workbook['Model'][annual].value.startswith('='))
                workbook.close()
        self.assertEqual(spec,before)
        self.assertEqual(model_logic_digest(spec),digest)
        self.assertEqual(growth['cells']['2026-Q1']['expression'],'prior/annual')


class BoundPeriodGraphTests(unittest.TestCase):
    def test_positive_condition_is_lazy_and_preserves_missing_values(self):
        period=build_periods([2026])[-2];pid=period['id']
        spec=dict(periods=[period],identities=[],rows=[
            dict(id='profit',kind='assumption',unit='GBPm',cells={pid:dict(value=-10,editable=True,status='forecast')}),
            dict(id='increment',kind='assumption',unit='shares_m',cells={pid:dict(value=None,editable=True,status='forecast',required=False)}),
            dict(id='eligible',kind='calculated',unit='shares_m',cells={pid:dict(expression='if_positive(profit, increment, 0)',status='forecast')})])
        self.assertEqual(calculate_periodic(spec)['eligible'][pid],0)
        self.assertEqual(calculate_periodic(spec,{'profit':{pid:0}})['eligible'][pid],0)
        self.assertIsNone(calculate_periodic(spec,{'profit':{pid:10}})['eligible'][pid])
        self.assertEqual(calculate_periodic(spec,{'profit':{pid:10},'increment':{pid:2}})['eligible'][pid],2)
        formula=cell_formula_excel(spec['rows'][2]['cells'][pid],pid,lambda rid,p:rid+'_cell')
        self.assertIn('>0,',formula)
        self.assertNotIn('IFERROR',formula)

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


class SavedValuationScenarioTests(unittest.TestCase):
    def test_invalid_valuation_payload_is_rejected_instead_of_becoming_an_accepted_snapshot(self):
        from tests.test_valuation import fixture
        from research_platform.workflow import valuation_snapshot
        spec,values,inputs=fixture()
        payload=dict(version=inputs['version'],valuation_date=inputs['valuation_date'],
            source_model_digest=inputs['source_model_digest'],changes=[dict(id='equity_value',value=100.,
                unit='GBP',scale=1000000,as_of='2024-12-31',status='provisional',method='Forbidden calculated-output edit')])
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'payload.json';path.write_text(json.dumps(payload),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Valuation scenario rejected: Read-only'):
                valuation_snapshot(spec,values,{},previous_inputs=inputs,inputs_file=path)

    def test_operating_and_valuation_payloads_revalue_without_ai_or_excel(self):
        from tests.test_valuation import fixture
        from research_platform.periods import assumption_contract, evaluate_saved_model, model_logic_digest
        from research_platform.valuation import value_company
        spec, _, inputs = fixture()
        for key in ('other_claims','other_assets','restricted_cash','pension_claim','deferred_consideration','dilution_shares'):
            inputs['assumptions'][key].update(status='researched',
                source_refs=[dict(source_id='synthetic_scenario_absence_note',unit_id=key)],
                method='Synthetic original explicitly establishes no such claim or adjustment in this positive-path fixture.')
        spec['identities'] = []
        spec['rows'].append(dict(id='incremental_profit', kind='assumption', unit='GBPm',
            cells={'2025-FY':dict(value=0., status='forecast', editable=True)}))
        profit = next(r for r in spec['rows'] if r['id']=='operating_profit')
        profit['cells']['2025-FY'] = dict(expression='100+incremental_profit', status='forecast')
        # A financial amount constant is a source anchor, represented as a row.
        spec['rows'].append(dict(id='profit_anchor', kind='historical', unit='GBPm',
            cells={'2025-FY':dict(value=100., status='estimated_historical')}))
        profit['cells']['2025-FY']['expression']='profit_anchor+incremental_profit'
        baseline = value_company(spec, calculate_periodic(spec), inputs)
        contract = assumption_contract(spec)
        field = next(f for f in contract['fields'] if f['driver_id']=='incremental_profit')
        change = {k:field[k] for k in ('driver_id','period_id','unit','currency','frequency','value_type')}
        payload = dict(schema='financial_assumptions_v1',company=spec['company'],scenario_id='test-dcf',
            as_of='2024-12-31',model_digest=model_logic_digest(spec),inputs=[dict(change,value=20.)])
        valuation_payload = dict(version=inputs['version'],valuation_date=inputs['valuation_date'],
            source_model_digest=inputs['source_model_digest'],company=spec['company'],
            changes=[dict(id='assumptions.risk_free_rate',value=.05,unit='ratio',scale=1,
                as_of='2024-12-31',status='provisional',method='Independent higher discount-rate scenario')])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);parent=root/'outputs'/'parent';parent.mkdir(parents=True)
            for name,content in [('model_specification.json',spec),('valuation_inputs.json',inputs),
                                 ('company_model_inputs.json',{'company':spec['company']})]:
                (parent/name).write_text(json.dumps(content),encoding='utf-8')
            (parent/'calls.jsonl').write_text('',encoding='utf-8')
            hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.iterdir()}
            (parent/'record.json').write_text(json.dumps(dict(directory=str(parent),calls=[],sources=[],artifacts=hashes)),encoding='utf-8')
            scenario=root/'scenario.json';scenario.write_text(json.dumps(payload),encoding='utf-8')
            valuation_file=root/'valuation_scenario.json';valuation_file.write_text(json.dumps(valuation_payload),encoding='utf-8')
            with patch('research_platform.ai.OpenAIProvider',side_effect=AssertionError('No AI during evaluation')), \
                 patch('research_platform.model_excel.export_integrated',side_effect=AssertionError('No Excel during evaluation')):
                revised=evaluate_saved_model(root,parent,scenario)
                discounted=evaluate_saved_model(root,revised,valuation_payload_file=valuation_file)
            revised_value=json.loads((revised/'valuation.json').read_text(encoding='utf-8'))
            discounted_value=json.loads((discounted/'valuation.json').read_text(encoding='utf-8'))
            # Operating profit +20 creates +15 post-tax FCFF; no terminal control changed.
            expected_delta=15/1.1**(183/365)
            self.assertAlmostEqual(revised_value['enterprise_value']-baseline['enterprise_value'],expected_delta)
            self.assertLess(discounted_value['enterprise_value'],revised_value['enterprise_value'])
            self.assertEqual(discounted_value['ai_calls'],0)
            for directory in (revised,discounted):
                saved=json.loads((directory/'model_specification.json').read_text(encoding='utf-8'))
                self.assertEqual(model_logic_digest(saved),model_logic_digest(spec))
                self.assertEqual(saved['rows'],spec['rows'])
                self.assertFalse((directory/'model.xlsx').exists())
                result=json.loads((directory/'evaluation.json').read_text(encoding='utf-8'))
                self.assertEqual(result['status'],'scenario_evaluated_provisional')
            for name,digest in hashes.items():
                self.assertEqual(hashlib.sha256((parent/name).read_bytes()).hexdigest(),digest)
