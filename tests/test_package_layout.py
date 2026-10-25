"""Stage boundaries and historical handoffs; all company data here is synthetic."""
import ast
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT=Path(__file__).resolve().parents[1]


def historical_fixture():
    """March year-end, yen reporting, half-year statements and a reorganisation."""
    from company_initiation.historic_construction.periods import build_periods
    periods={(p['fiscal_year'],p['kind']):p for p in build_periods([2023,2024,2025,2026],{'fiscal_year_end':'03-31'})}
    observations=[]
    def fact(row,year,kind,value,entity='group',basis='consolidated',status='reported'):
        period=periods[year,kind]
        observations.append(dict(id=f'{row}_{year}_{kind}',row_id=row,label=row,entity_id=entity,
            model_entity_id=entity,period_id=period['id'],fiscal_year=year,kind=kind,
            start=period['start'],end=period['end'],value=value,metric_type='flow',unit='JPYm',currency='JPY',
            definition='Synthetic disclosed revenue',definition_id='sales',scope=entity,basis=basis,
            compatibility_key=basis,restatement='original',status=status,
            source_refs=[dict(source_id='synthetic_statements',unit_id='table:revenue',token_index=len(observations))]))
    fact('sales',2023,'FY',120)
    fact('sales',2024,'H1',60)
    fact('sales',2024,'FY',140)
    fact('sales',2025,'H1',100)
    fact('legacy_sales',2023,'FY',120,'legacy','legacy_combined')
    fact('industrial_sales',2024,'FY',80,'industrial','current_split')
    fact('services_sales',2024,'FY',60,'services','current_split')
    fact('sales',2026,'FY',999,status='forecast')
    return dict(company='SYNTHETIC March Industrial Services',currency='JPY',history_years=[2023,2024],
        fiscal_calendar={'fiscal_year_end':'03-31'},historical={},schedule_controls={},corporate={},
        segments=[dict(id='industrial',label='Industrial equipment'),dict(id='services',label='Maintenance services')],
        forecast_basis='current_split',observations=observations,
        model_configuration=dict(as_of='2024-10-25',actual_through='2024-09-30',full_statement_frequency='half_year'),
        entity_versions=[dict(id='legacy',model_entity_id='industrial',current_basis_compatible=False,
                              bases=['legacy_combined'],period_ids=['2023-FY']),
                         dict(id='industrial',model_entity_id='industrial',current_basis_compatible=True,
                              bases=['current_split'],period_ids=['2024-FY']),
                         dict(id='services',model_entity_id='services',current_basis_compatible=True,
                              bases=['current_split'],period_ids=['2024-FY'])],
        reporting_bridges=[dict(id='synthetic_split',period_id='2024-FY',predecessors=['legacy'],
                               successors=['industrial','services'],status='synthetic_fixture')])


class PackageBoundaryTests(unittest.TestCase):
    def test_history_and_shared_imports_do_not_load_forecast_or_dcf(self):
        script="""
import importlib, json, pkgutil, sys
import company_initiation.historic_construction as history
for item in pkgutil.walk_packages(history.__path__, history.__name__+'.'):
    importlib.import_module(item.name)
print(json.dumps(sorted(name for name in sys.modules if name.startswith((
    'company_initiation.forecast_construction', 'company_initiation.dcf_construction')))))
"""
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src'))
        process=subprocess.run([sys.executable,'-c',script],cwd=ROOT,env=env,
                               capture_output=True,text=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout),[])

    def test_historical_functions_have_no_deferred_downstream_imports(self):
        # Import-only checks cannot detect a forbidden import inside a function.
        roots=[ROOT/'src/company_initiation/historic_construction']
        files=list(roots[0].glob('*.py'))+list((ROOT/'src/company_initiation').glob('shared_*.py'))
        violations=[]
        for path in files:
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                imports=[node.module or ''] if isinstance(node,ast.ImportFrom) else [a.name for a in node.names] if isinstance(node,ast.Import) else []
                for name in imports:
                    if any(stage in name.split('.') for stage in ('forecast_construction','dcf_construction')):
                        violations.append(f'{path.name}:{node.lineno}: {name}')
        self.assertEqual(violations,[])

    def test_shared_fx_modules_live_in_their_own_package(self):
        for name in ('fx','fx_store','ibkr'):
            module=importlib.import_module('shared_FX.'+name)
            self.assertEqual(Path(module.__file__).resolve().parent,ROOT/'src/shared_FX')


class HistoricalHandoffTests(unittest.TestCase):
    def test_history_stops_at_latest_report_and_preserves_reorganisation(self):
        from company_initiation.historic_construction.model_contract import historical_model
        data=historical_fixture();before=copy.deepcopy(data)
        result=historical_model(data)
        self.assertEqual(data,before)
        self.assertEqual(result['currency'],'JPY')
        self.assertEqual(result['latest_reporting_date'],'2024-09-30')
        self.assertEqual(result['entity_versions'],data['entity_versions'])
        self.assertEqual(result['reporting_bridges'],data['reporting_bridges'])
        self.assertTrue(all(period['end']<='2024-09-30' for period in result['periods']))
        self.assertTrue(all(period['status']!='forecast' for period in result['periods']))
        rows={row['id']:row for row in result['rows']}
        self.assertEqual(rows['sales']['cells']['2024-H2']['value'],80)
        self.assertEqual(rows['sales']['cells']['2025-H1']['value'],100)
        self.assertEqual(rows['legacy_sales']['cells']['2023-FY']['value'],120)
        self.assertEqual(rows['industrial_sales']['cells']['2024-FY']['value'],80)
        self.assertEqual(rows['services_sales']['cells']['2024-FY']['value'],60)
        self.assertFalse(any(row.get('kind')=='assumption' for row in result['rows']))
        self.assertFalse(any(cell.get('status')=='forecast' for row in result['rows'] for cell in row['cells'].values()))
        self.assertNotIn('2026-FY',rows['sales']['cells'])
        self.assertTrue(all(o.get('status')!='forecast' for o in result['observations']))

    def test_source_update_catalogue_adds_only_closed_unreported_periods(self):
        from company_initiation.historic_construction.model_contract import historical_model
        data=historical_fixture();data['model_configuration']['as_of']='2025-01-15'
        model=historical_model(data)
        catalogue=historical_model(data,include_unreported_periods=True)
        self.assertEqual(max(p['end'] for p in model['periods']),'2024-09-30')
        self.assertEqual(max(p['end'] for p in catalogue['periods']),'2024-12-31')
        self.assertTrue(all(p['end']<='2025-01-15' for p in catalogue['periods']))
        self.assertTrue(all(p['status']=='not_disclosed' for p in catalogue['periods'] if p['end']>'2024-09-30'))
        self.assertTrue(all('2025-Q3' not in row['cells'] for row in catalogue['rows']))

    def test_legacy_segment_and_corporate_facts_keep_citations_without_overriding_observations(self):
        from company_initiation.historic_construction.model_contract import historical_model
        data=historical_fixture()
        citation=dict(source_id='synthetic_segment_note',unit_id='table:segments',token_index=3)
        data['segments'][0].update(sales2024=999,utop2024=15,da2024=8,pricing2024=.02,
            source_refs={key:dict(citation) for key in ('sales2024','utop2024','da2024','pricing2024')})
        # A normalized allocation carries evidence about its method, not an
        # independent report of the allocated amount.
        data['model_configuration']['historical_allocations']=[dict(row_id='industrial_da',year=2024,
            amount=8,status='estimated',method='Synthetic allocation',source_refs=[dict(citation)])]
        data['corporate']=dict(utop2024=-3,da2024=1,source_refs={'utop2024':dict(citation)})
        result=historical_model(data);rows={row['id']:row for row in result['rows']}
        self.assertEqual(rows['industrial_sales']['cells']['2024-FY']['value'],80)
        self.assertEqual(rows['industrial_utop']['cells']['2024-FY']['value'],15)
        self.assertEqual(rows['industrial_utop']['cells']['2024-FY']['source_refs'],[citation])
        self.assertEqual(rows['corporate_utop']['cells']['2024-FY']['value'],-3)
        self.assertEqual(rows['industrial_pricing']['cells']['2024-FY']['value'],.02)
        self.assertEqual(rows['industrial_pricing']['unit'],'ratio')
        self.assertEqual(rows['industrial_utop']['unit'],'JPYm')
        self.assertNotIn('2024-FY',rows['industrial_da']['cells'])
        self.assertNotIn('2024-FY',rows['corporate_da']['cells'])


if __name__=='__main__':
    unittest.main()
