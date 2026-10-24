"""Freshness and partial disclosures are tested with explicit synthetic sources."""
import copy
from collections import Counter
import hashlib
from pathlib import Path
import tempfile
import unittest
import json
from unittest.mock import patch

from research_platform.workflow import freshness_checks
from research_platform.integrated import build_periodic_spec, periodic_sensitivities
from research_platform.periods import calculate_periodic
from tests.test_periodic_model import different_period_company


class FreshResearchEntryTests(unittest.TestCase):
    def test_missing_scope_accounting_is_distinct_from_arithmetic_status(self):
        from research_platform.workflow import model_financial_completeness
        data=different_period_company()
        data['model_configuration']['financial_contracts']={'scope_events':[dict(
            id='synthetic_pending_acquisition',entity_id='north',enabled=False,
            accounting_enabled=False,effective_date='2026-07-01',
            limitations=['SYNTHETIC disclosed transaction with missing consideration and opening balance allocation'])]}
        spec=build_periodic_spec(data,2)
        self.assertTrue(spec['scope_event_audit'][0]['material_unresolved'])
        self.assertEqual(model_financial_completeness(spec),'incomplete_scope_accounting')
        self.assertEqual(model_financial_completeness({'scope_event_audit':[]}),'provisional')

    def test_new_archive_generates_spec_without_prior_model_or_reference(self):
        self._fresh_archive(False)

    def test_new_company_consumes_shared_database_and_refreshes_without_ai(self):
        self._fresh_archive(True)

    def _fresh_archive(self,with_fx):
        from tests.test_periodic_model import _write_synthetic_originals
        from research_platform.evidence import inventory_local_sources
        from research_platform.ai import OpenAIProvider
        from research_platform.__main__ import main
        data=different_period_company()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'company';archive.mkdir()
            (root/'pyproject.toml').write_text('[tool.research-platform]\ncheap-review-repairs = 1\n',encoding='utf-8')
            if with_fx:
                from research_platform.fx_store import FXStore
                from research_platform.fx import publication_dates
                from tests.test_shared_fx import quote
                database=root/'shared.sqlite'
                with FXStore(database) as store:
                    quotes=[]
                    for day in publication_dates('2023-01-01','2026-10-23'):
                        quotes.extend([quote(day,.8),quote(day,150,currency='JPY')])
                    store.import_quotes(quotes,{'fixture':'Different GBP June-year-end company shared FX'})
                with (root/'pyproject.toml').open('a',encoding='utf-8') as settings:settings.write('fx-database = "shared.sqlite"\n')
            _write_synthetic_originals(data,archive)
            inventory=inventory_local_sources(archive)
            sources=inventory['sources'];by_old={Path(s['local_path']).stem:s['id'] for s in sources}
            provider=OpenAIProvider(api_key='SYNTHETIC-TEST-KEY')
            review_payloads={}
            def answer(**kwargs):
                payload=kwargs['payload'];stage=payload['stage']
                if stage.startswith('integrated_'):review_payloads[stage]=copy.deepcopy(payload)
                provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=10,output_tokens=5,total_tokens=15),output=[])
                if stage in ('company_identity_sources','company_year_sources'):
                    return dict(source_ids=[] if payload.get('years')==[2026] else list(by_old.values()),reasons=['Synthetic originals'],gaps=[])
                if stage=='company_reporting_scope':
                    self.assertIn('annual, half_year or quarterly',kwargs['instructions'])
                    self.assertIn('retain full_statement_frequency separately',kwargs['instructions'])
                    return dict(currency='GBP',fiscal_year_end='06-30',latest_completed_year=2025,forecast_frequency='half_year',full_statement_frequency='quarterly',reporting_basis='current_components_basis',segments=[dict(id=s['id'],label=s['label']) for s in data['segments']],corporate_label='Corporate',official_indexes=['https://synthetic.invalid/releases'],source_references=[],gaps=[])
                if stage in ('company_year_mapping','company_year_blind'):
                    facts=[]
                    for o in data['observations']:
                        if o['fiscal_year']!=payload['year']:continue
                        terms=[]
                        for ref in o['source_refs']:
                            terms.append(dict(reference=dict(source_id=by_old[ref['source_id']],unit_id=ref['sheet']+'!R'+ref['cell'][1:],number_index=0,number_format='dot_decimal'),multiplier=ref['multiplier'],weight=ref.get('contribution_weight',1)))
                        facts.append(dict(row_id=o['row_id'],label=o['label'],period_id=o['period_id'],unit=o['unit'],metric_type=o['metric_type'],entity_id=o['entity_id'],basis=o['basis'],definition_id=o['definition_id'],scope=o['scope'],terms=terms,rounding_increment=0))
                    return dict(observations=facts,reporting_changes=['Synthetic predecessor has a different scope; retain its original basis.'],gaps=[])
                if stage=='company_accounting_structure':
                    ref=dict(source_id=next(iter(by_old.values())),unit_id='SYNTHETIC disclosures!R3')
                    versions=[dict(v,source_refs=[ref]) for v in data['entity_versions']]
                    bridge=copy.deepcopy(data['reporting_bridges'][0]);bridge['source_refs']=[ref]
                    bridge.pop('residual');bridge.pop('status')
                    bridge['predecessors']=[dict(row_id='legacy_north_sales',entity_id='old_north',period_id='2025-FY')]
                    bridge['successors']=[dict(row_id=key+'_sales',entity_id='new_'+key,period_id='2025-FY') for key in ('north','specialty')]
                    bridge['relationships']=[dict(predecessor='old_north',successor='new_'+key,fact=dict(row_id=key+'_sales',entity_id='new_'+key,period_id='2025-FY')) for key in ('north','specialty')]
                    exposures=[]
                    if with_fx:
                        for segment in data['segments']:
                            basket=dict(weights=[dict(currency='JPY',weight=.7,rate_currency='JPY',proxy_reason='',exposure_status='reported',effective_date='2025-07-01',source_refs=[ref],allocation='Synthetic disclosed',evidence_basis='functional_currency_disclosure',scenario_neutral=False,label='JPY'),dict(currency='GBP',weight=.3,rate_currency='GBP',proxy_reason='',exposure_status='reported',effective_date='2025-07-01',source_refs=[ref],allocation='Synthetic disclosed',evidence_basis='functional_currency_disclosure',scenario_neutral=False,label='GBP')],method='Synthetic disclosed currency weights',limitations='Synthetic fixture only',status='provisional',source_refs=[ref],effective_date='2025-07-01',proxy_materiality_threshold=.05)
                            exposures.append(dict(entity_id=segment['id'],revenue_bridge='translation_of_constant_currency',revenue=copy.deepcopy(basket),cost=copy.deepcopy(basket)))
                    pools=[dict(id=role,label=role,destination=role,baseline_role=role,baseline_amount=None,
                        baseline_share=1,variable_share=.5 if role=='cogs' else 0,
                        activity_driver='rig' if role=='cogs' else 'independent',elasticity=1 if role=='cogs' else 0,
                        unit_cost_change=0,spending_change=0,behaviour='Synthetic independent spending contract',
                        currency_basis='functional_currency',lag_months=0,source_refs=[ref],effective_date='2025-07-01',
                        definition='SYNTHETIC source amount, no sales-ratio forecast',status='synthetic_fixture')
                        for role in ('cogs','distribution','marketing_admin','research')]
                    neutral_basket=dict(weights=[dict(currency='GBP',weight=1,rate_currency='GBP',proxy_reason='',
                        exposure_status='unresolved',effective_date='2025-07-01',source_refs=[ref],allocation='Synthetic neutral scenario',
                        evidence_basis='unmeasured',scenario_neutral=True,label='Unallocated neutral scenario')],method='Synthetic unmeasured cost exposure',
                        limitations='Scenario only',status='unresolved',effective_date='2025-07-01',source_refs=[ref],proxy_materiality_threshold=.05)
                    for pool in pools:pool['fx']=dict(translation=copy.deepcopy(neutral_basket),
                        transaction=dict(components=[],method='Synthetic unmodelled transaction exposure',source_refs=[ref],status='unmodelled'))
                    contracts=dict(cost_pools=pools,scope_events=[],
                        normalisation={key:dict(annual_amount=0,reason='Synthetic no-adjustment policy',source_refs=[ref]) for key in ('net_other_trading','net_other_operating')},
                        dividends={side:dict(annual_amount=-data['historical'][role]['values']['2025'],
                            payment_weights=[dict(period_kind='Q4',weight=1)],reason='Synthetic annual cash pool paid at fiscal close',source_refs=[ref])
                            for side,role in [('parent','dividends_parent'),('nci','dividends_nci')]},
                        financing=dict(repurchase_price=None,repurchase_elapsed_fraction=.5,reason='Zero buybacks need no invented price',source_refs=[ref]),
                        limitations=['Synthetic contracts exercise entry point; not real-company economic validation'])
                    return dict(asset_scope=[dict(reported_role='ppe',owned_role='owned_ppe',rou_role='right_of_use_assets',reported_scope='owned_and_rou',owned_expression='ppe - right_of_use_assets',definition='Synthetic combined PPE includes ROU',source_refs=[ref])],entity_versions=versions,reporting_bridges=[bridge],fx_exposures=exposures,financial_contracts=contracts,gaps=[])
                if with_fx and stage=='integrated_schedules':
                    return dict(findings=[dict(severity='warning',area='synthetic_source_limitation',
                        detail='Synthetic source review warning retained across deterministic FX refreshes.',
                        source_references=[])],summary='Synthetic provider fixture; not a real-company review')
                return dict(findings=[],summary='Synthetic provider fixture; not a real-company review')
            with patch.object(provider,'complete',side_effect=answer) as calls,patch('research_platform.ai.urlopen') as network,patch('research_platform.workflow.discover_releases',return_value=(data['source_freshness'],[])):
                with patch('research_platform.ai.OpenAIProvider.from_env',return_value=provider),patch('research_platform.__main__.find_project_root',return_value=root), \
                        patch('sys.argv',['research_platform','construct',data['company'],'--sources',str(archive),'--as-of','2026-10-23','--history-years','2','--forecast-years','2']), \
                        patch('research_platform.integrated.recalculate_workbook',return_value={'status':'passed'}), \
                        patch('research_platform.model_excel.verify_excel_sensitivities',return_value={'status':'passed'}),patch('builtins.print') as printed:
                    result=main()
                    self.assertEqual(result,0,str(printed.call_args_list[-3:]))
                inputs=next((root/'outputs').glob('construct_research_*/company_model_inputs.json'))
                generated=json.loads(inputs.read_text(encoding='utf-8'))
                self.assertEqual(generated['currency'],'GBP')
                self.assertEqual(generated['fiscal_calendar']['fiscal_year_end'],'06-30')
                self.assertEqual(len(generated['segments']),2)
                self.assertEqual(generated['historical']['sales']['values']['2025'],180)
                self.assertEqual(generated['reporting_bridges'][0]['residual'],0)
                self.assertEqual(generated['entity_versions'][0]['scope'],'both_current_businesses')
                self.assertEqual(generated['asset_scope'][0]['reported_scope'],'owned_and_rou')
                self.assertEqual(generated['model_configuration']['financial_contracts']['cost_pools'][0]['variable_share'],.5)
                self.assertIsNone(generated['model_configuration']['financial_contracts']['financing']['repurchase_price'])
                self.assertEqual(generated['model_configuration']['financial_contracts']['dividends']['parent']['payment_weights'],{'Q4':1})
                run=next((root/'outputs').glob('construct_integrated_*'))
                self.assertEqual(set(review_payloads),{'integrated_segments','integrated_income_review',
                    'integrated_cashflow_review','integrated_balance_review','integrated_schedules'})
                reviewed_income={r['id']:r for r in review_payloads['integrated_income_review']['rows']}
                for role in ('cogs','marketing_admin'):
                    cells=reviewed_income[role]['period_cells']
                    self.assertTrue(cells)
                    expressions=' '.join(c.get('expression','') for c in cells.values())
                    self.assertIn('_pool_'+role,expressions)
                    self.assertNotIn('total_revenue - utop',expressions)
                    self.assertNotIn(role+'_allocation',expressions)
                    self.assertTrue(all('result' in c for c in cells.values()))
                reviewed_segments={r['id']:r for r in review_payloads['integrated_segments']['rows']}
                spending=reviewed_segments['north_pool_marketing_admin_spending_change']
                self.assertEqual(spending['driver_contract']['parameter_role'],'economic_input')
                self.assertIn('operating_profit',spending['driver_contract']['expected_downstream_outputs'])
                for payload in review_payloads.values():
                    self.assertTrue(payload['forecast_horizon'])
                    self.assertTrue(any(r['period_cells'] for r in payload['complete_forecast_graph']))
                self.assertGreater(calls.call_count,5)
                self.assertTrue((run/'model.xlsx').is_file())
                self.assertEqual(json.loads((run/'record.json').read_text(encoding='utf-8'))['status'],'complete_provisional')
                for filename in ('record.json','model_specification.json','validation.json'):
                    self.assertEqual(json.loads((run/filename).read_text(encoding='utf-8'))['financial_completeness'],'provisional')
                from research_platform.workflow import offline_export
                before=calls.call_count
                with patch('research_platform.ai.OpenAIProvider.from_env',side_effect=AssertionError('Offline export must not load an AI provider')), \
                        patch('research_platform.construction.recalculate_workbook',return_value={'status':'passed'}), \
                        patch('research_platform.model_excel.verify_excel_sensitivities',return_value={'status':'passed'}):
                    exported=offline_export(root,run,**dict(fx_database=database,fx_as_of='2026-10-23T23:59:59+00:00') if with_fx else {})
                prior_checks=json.loads((run/'validation.json').read_text(encoding='utf-8'))['checks']
                exported_checks=json.loads((exported/'validation.json').read_text(encoding='utf-8'))['checks']
                exported_record=json.loads((exported/'record.json').read_text(encoding='utf-8'))
                self.assertEqual(exported_record['financial_completeness'],'provisional')
                exported_specification=json.loads((exported/'model_specification.json').read_text(encoding='utf-8'))
                self.assertEqual(exported_specification['financial_completeness'],'provisional')
                self.assertEqual(exported_record['summary']['rows'],len(exported_specification['rows']))
                self.assertEqual(exported_record['summary']['assumptions'],sum(r['kind']=='assumption' for r in exported_specification['rows']))
                self.assertEqual(exported_record['summary']['segments'],len(generated['segments']))
                self.assertEqual(exported_record['summary']['historical_years'],generated['history_years'])
                self.assertEqual(exported_record['summary']['forecast_years'],exported_specification['forecast_years'])
                self.assertLessEqual({(c.get('area'),c.get('name')) for c in prior_checks},
                                     {(c.get('area'),c.get('name')) for c in exported_checks})
                self.assertEqual(calls.call_count,before)
                operation=json.loads((exported/'record.json').read_text(encoding='utf-8'))['operation']
                self.assertEqual(operation['budget_before'],operation['budget_after'])
                self.assertFalse(operation['model_configuration_changed'])
                self.assertFalse(operation['changed_model_configuration_fields'])
                self.assertFalse(operation['calculation_policy_changed'])
                self.assertEqual(operation['ai_calls'],0)
                if with_fx:
                    self.assertTrue((exported/'fx_snapshot.json').is_file())
                    exported_spec=json.loads((exported/'model_specification.json').read_text(encoding='utf-8'))
                    rate_change=next(row for row in exported_spec['rows'] if row['id']=='fx_yoy_jpy')
                    self.assertEqual(rate_change['cells']['2026-Q1']['status'],'derived_actual')
                    audit=json.loads((exported/'fx_refresh_audit.json').read_text(encoding='utf-8'))
                    self.assertTrue(audit['company_historical_values_unchanged'])
                    proof=json.loads((exported/'workbook_validation.json').read_text(encoding='utf-8'))
                    bad=[c for c in exported_checks if c['status'] in ('FAIL','MISSING')]
                    self.assertEqual(json.loads((exported/'record.json').read_text(encoding='utf-8'))['status'],'complete_provisional',str(dict(checks=bad,layout=proof.get('layout'))))
                    with patch('research_platform.ai.OpenAIProvider.from_env',side_effect=AssertionError('Repeated refresh must not load an AI provider')), \
                            patch('research_platform.construction.recalculate_workbook',return_value={'status':'passed'}), \
                            patch('research_platform.model_excel.verify_excel_sensitivities',return_value={'status':'passed'}):
                        repeated=offline_export(root,exported,fx_database=database,fx_as_of='2026-10-23T23:59:59+00:00')
                    repeated_checks=json.loads((repeated/'validation.json').read_text(encoding='utf-8'))['checks']
                    repeated_record=json.loads((repeated/'record.json').read_text(encoding='utf-8'))
                    def check_counts(items):
                        return Counter((c.get('area'),c.get('name'),c.get('status'),c.get('detail')) for c in items)
                    self.assertEqual(check_counts(prior_checks),check_counts(exported_checks))
                    self.assertEqual(check_counts(exported_checks),check_counts(repeated_checks))
                    for area in ('transaction_fx','fx_contract','AI_review','source_integrity','source_data'):
                        self.assertTrue(any(c['area']==area for c in repeated_checks),area)
                    self.assertEqual(exported_record['summary']['checks'],repeated_record['summary']['checks'])
                    self.assertEqual(repeated_record['operation']['ai_calls'],0)
                    self.assertEqual(repeated_record['operation']['budget_before'],repeated_record['operation']['budget_after'])
                    self.assertEqual(calls.call_count,before)
                network.assert_not_called()


class FreshnessTests(unittest.TestCase):
    def test_official_discovery_reads_event_and_checks_date_quote_and_url(self):
        from types import SimpleNamespace
        from research_platform.workflow import discover_releases
        index='https://synthetic.invalid/results';event=index+'/event';pdf=index+'/release.pdf'
        index_html=b'<p>Results calendar</p><a href="/results/event">2031 nine months</a>'
        event_html=b'<p>22 October 2031</p><a href="/results/release.pdf">Original release</a>'
        release=dict(url=pdf,published_at='2031-10-22',title='SYNTHETIC nine months',publication_evidence='22 October 2031',requires_observations=True)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);saved={};answers=[dict(releases=[],event_pages=[event],gaps=[]),dict(releases=[release],event_pages=[],gaps=[])]
            journal=SimpleNamespace(directory=root,state={'artifacts':{}},stage=lambda *a:answers.pop(0),artifact=lambda name,data:saved.update({name:data}))
            def fetch(url):return {index:(index_html,index,'text/html'),event:(event_html,event,'text/html'),pdf:(b'%PDF SYNTHETIC fixture',pdf,'application/pdf')}[url]
            with patch('research_platform.evidence.download',side_effect=fetch) as calls:
                fresh,sources=discover_releases(journal,root,['https://synthetic.invalid/results'],'2031-10-23',latest_completed_year=2030)
            self.assertEqual(calls.call_count,3);self.assertEqual(fresh['releases'][0]['published_at'],'2031-10-22')
            self.assertTrue((root/sources[0]['local_path']).is_file())
            answers.extend([dict(releases=[],event_pages=[event],gaps=[]),dict(releases=[dict(release,publication_evidence='invented date quote')],event_pages=[],gaps=[])])
            with patch('research_platform.evidence.download',side_effect=fetch),self.assertRaisesRegex(ValueError,'quotation'):
                discover_releases(journal,root,[index],'2031-10-23')

    def test_release_published_by_asof_requires_original_and_bindings(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'release.txt';source.write_text('SYNTHETIC disclosed sales 75')
            data=dict(model_configuration={'as_of':'2031-10-23'},sources={'release':dict(id='release',local_path='release.txt',sha256=hashlib.sha256(source.read_bytes()).hexdigest(),published_at='2031-10-22')},
                observations=[dict(source_refs=[{'source_id':'release'}])],source_freshness=dict(checked_as_of='2031-10-23',official_indexes=['https://synthetic.invalid/releases'],releases=[dict(id='q3',source_id='release',published_at='2031-10-22',url='https://synthetic.invalid/q3')]))
            self.assertTrue(all(c['status']=='PASS' for c in freshness_checks(data,root)))
            source.unlink()
            self.assertTrue(any(c['status']=='FAIL' for c in freshness_checks(data,root)))
            data['model_configuration']['as_of']='2031-10-21'
            self.assertTrue(any(c['status']=='FAIL' for c in freshness_checks(data,root)))
            data['sources']={};data['observations']=[]
            self.assertTrue(all(c['status']=='PASS' for c in freshness_checks(data,root)))
            data['source_freshness']['checked_as_of']='2031-10-01'
            self.assertTrue(any(c['status']=='FAIL' for c in freshness_checks(data,root)))

    def test_historical_vintage_rejects_later_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            data=dict(model_configuration={'as_of':'2031-10-21'},sources={'later':dict(id='later',published_at='2031-10-22')},source_freshness=dict(checked_as_of='2031-10-23',official_indexes=['https://synthetic.invalid'],releases=[]))
            self.assertTrue(any(c['status']=='FAIL' for c in freshness_checks(data,Path(temp),historical_vintage=True)))


class DisclosurePrecedenceTests(unittest.TestCase):
    def test_new_sales_does_not_turn_undisclosed_profit_into_actual(self):
        data=different_period_company()
        previous=next(o for o in data['observations'] if o['row_id']=='north_sales' and o['period_id']=='2025-H1')
        actual=copy.deepcopy(previous)
        actual.update(id='synthetic_new_actual',period_id='2026-H1',fiscal_year=2026,start='2025-07-01',end='2025-12-31',value=65)
        data['observations'].append(actual)
        spec=build_periodic_spec(data,2);values=calculate_periodic(spec);rows={r['id']:r for r in spec['rows']}
        self.assertEqual(values['north_sales']['2026-H1'],65)
        self.assertEqual(rows['north_sales']['cells']['2026-H1']['status'],'actual')
        self.assertEqual(rows['north_utop']['cells']['2026-H1']['status'],'forecast')
        self.assertAlmostEqual(values['north_sales']['2026-FY'],65+values['north_sales']['2026-H2'])
        self.assertEqual(next(p for p in spec['periods'] if p['id']=='2026-H1')['status'],'mixed')

    def test_sensitivity_does_not_edit_a_newly_reported_driver(self):
        data=different_period_company()
        for role,value in [('north_sales',65),('north_pricing',.025)]:
            actual=copy.deepcopy(next(o for o in data['observations'] if o['row_id']==role and o['period_id']=='2025-H1'))
            actual.update(id='new_'+role,period_id='2026-H1',fiscal_year=2026,start='2025-07-01',end='2025-12-31',value=value)
            data['observations'].append(actual)
        spec=build_periodic_spec(data,2);values=calculate_periodic(spec)
        cases,checks=periodic_sensitivities(spec,values)
        self.assertEqual(next(c for c in cases if c['id']=='pricing')['period_id'],'2026-H2')
        # Sales/pricing are disclosed for H1; its costs and financial schedules
        # remain estimates and retain their own active H1 controls.
        self.assertTrue(all(c['period_id']=='2026-H1' for c in cases if c['id']!='pricing'))
        self.assertFalse([c for c in checks if c['status'] in ('FAIL','MISSING')])
        self.assertTrue(all(c['name'].endswith(':funding') for c in checks if c['status']=='WARNING'))

    def test_no_exposures_does_not_import_all_source_currencies(self):
        data=different_period_company();data['model_configuration'].pop('fx_currencies')
        spec=build_periodic_spec(data,2,dict(source={},metadata={},daily_series={'USD':{},'EUR':{}}))
        self.assertFalse(any(r['section']=='fx' for r in spec['rows']))
        self.assertEqual(spec['fx_interfaces']['exposure_weights'],{})


if __name__=='__main__':unittest.main()
