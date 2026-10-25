"""Exercise the reusable financial compiler on a second, synthetic company.

No Nestle archive, private credentials or generated company workbook is used.
The disclosed balances and independently calculated expected values live here.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_platform.ai import AIError, OpenAIProvider, response_usage
from research_platform.budget import BudgetLedger
from research_platform.construction import RunJournal, calculate_integrated, validate_integrated, digest
from research_platform.integrated import (build_integrated_spec, financial_sensitivities,
    integrated_runtime_fingerprint,integrated_source_cache_key,verified_integrated_record,
    compatible_integrated_result,cached_integrated_source_checks,select_integrated_previous)
from research_platform.evidence import parse_number


def weighted_reference_value(reference):
    """Independent arithmetic over source metadata, not the model expression AST."""
    weight=parse_number(reference.get('contribution_weight',1))
    if 'source_refs' in reference and 'source_id' not in reference:
        return sum(weighted_reference_value(child) for child in reference['source_refs'])*weight
    raw=reference['raw'] if 'raw' in reference else reference['original_value']
    return (parse_number(raw,reference.get('number_format','dot_decimal'))
            *parse_number(reference.get('multiplier',1))*weight)


def second_company():
    """Two operating businesses with explicit original financial-statement signs."""
    base = dict(sales=180., other_revenue=0., total_revenue=180., utop=30., cogs=-90.,
        distribution=-20., marketing_admin=-35., research=-5., other_trading_income=0.,
        other_trading_expense=0., other_operating_income=0., other_operating_expense=0.,
        trading_profit=30., operating_profit=30., financial_income=1., financial_expense=-4.,
        pretax=27., tax_expense=-5.4, associate_profit=1.4, total_profit=23., nci_profit=1.,
        parent_profit=22., shares_basic=10., eps_basic=2.2, da=10., sbc=1.5,
        associate_dividends=1., paid_tax=-5., wc_inventory_cf=-2., wc_receivables_cf=-1.,
        wc_payables_cf=1., wc_cash=-2., cfo=30., capex_ppe=-10., capex_intangibles=-3.,
        cfi=-13., dividends_parent=-11., dividends_nci=-.5, buybacks=0., debt_borrow=0.,
        debt_repay=0., cff=-11.5, cash_fx=0., cash_change=5.5, opening_cash=26.,
        closing_cash=31.5, held_for_sale_cash=2., cash=29.5, short_investments=5.,
        inventories=30., receivables=25., other_current_assets=10., current_assets=99.5,
        ppe=75., goodwill=20., intangibles=21., associates=15., other_noncurrent_assets=10.,
        noncurrent_assets=141., total_assets=240.5, short_debt=20., long_debt=50.,
        trade_payables=20., current_tax_liabilities=4., other_current_liabilities=10.,
        current_liabilities=50., other_noncurrent_liabilities=15., noncurrent_liabilities=65.,
        total_liabilities=115., share_capital=10., treasury_stock=-2., reserves=8.,
        retained_earnings=104.5, parent_equity=120.5, nci_equity=5., total_equity=125.5,
        liabilities_equity=240.5, owned_ppe=64., right_of_use_assets=11.,
        owned_ppe_depreciation=6., rou_depreciation=2., amortization=2., rou_additions=3.,
        lease_liabilities=12., debt_interest_expense=3.5, lease_interest_expense=.5,
        cash_interest_income=.8, exceptional_associate_distribution=0.)
    prior = dict(base, cash=24., inventories=28., receivables=24., current_assets=91.,
        ppe=70., owned_ppe=60., right_of_use_assets=10., intangibles=20., associates=14.,
        noncurrent_assets=134., total_assets=225., long_debt=48., trade_payables=19.,
        current_tax_liabilities=3., other_current_liabilities=9., current_liabilities=48.,
        noncurrent_liabilities=63., total_liabilities=111., reserves=7., retained_earnings=95.,
        parent_equity=110., nci_equity=4., total_equity=114., liabilities_equity=225.,
        lease_liabilities=11., opening_cash=25., closing_cash=26., cfo=26., cff=-12., cash_change=1.)
    historical = {}
    for index, (key, value) in enumerate(base.items(), 1):
        historical[key] = dict(values={"2024": prior[key], "2025": value},
            sources={str(year): [dict(source_id="synthetic_primary_statements", unit_id="table:statements",
                        number_index=index, original_value=prior[key] if year == 2024 else value,
                        unit="CHFm", period=str(year))] for year in (2024, 2025)},
            basis="SYNTHETIC original reporting basis")
    segments = []
    for key, label, sales, profit, da, pricing, rig in (
            ("north", "Northern distribution", 100., 20., 5., .02, .01),
            ("specialty", "Specialty services", 80., 12., 3., .03, .02)):
        segments.append(dict(id=key, label=label, sales2025=sales, utop2025=profit, da2025=da,
            pricing2025=pricing, rig2025=rig, og2025=pricing+rig,
            source_refs={f"{metric}2025": dict(source_id="synthetic_primary_segment_note",
                unit_id="table:"+key, number_index=index, original_value=value)
                for index, (metric, value) in enumerate((("sales", sales), ("utop", profit),
                    ("da", da), ("pricing", pricing), ("rig", rig)), 1)}))
    return dict(company="SYNTHETIC Alpine Distribution plc", currency="CHF", history_years=[2024, 2025],
        historical=historical, forecast_basis="SYNTHETIC two mutually exclusive business segments",
        segments=segments, corporate=dict(utop2025=-2., da2025=2.), sources=[
            dict(id="synthetic_primary_statements", category="financial_reports", name="SYNTHETIC statements"),
            dict(id="synthetic_primary_segment_note", category="financial_reports", name="SYNTHETIC segment note")])


class IntegratedCompilerTests(unittest.TestCase):
    def setUp(self):
        self.data = second_company()
        self.spec = build_integrated_spec(self.data, 2)
        self.values = calculate_integrated(self.spec)

    def test_different_two_segment_layout_preserves_primary_history_and_signs(self):
        section_ids = [s["id"] for s in self.spec["sections"]]
        self.assertIn("segment_north", section_ids)
        self.assertIn("segment_specialty", section_ids)
        self.assertEqual(len([s for s in section_ids if s.startswith("segment_")]), 2)
        for key, expected in (("cogs", -90.), ("tax_expense", -5.4), ("financial_expense", -4.),
                              ("parent_profit", 22.), ("total_profit", 23.), ("cash", 29.5),
                              ("closing_cash", 31.5), ("total_assets", 240.5)):
            self.assertEqual(self.values[key]["2025"], expected)
            source_row = next(r for r in self.spec["rows"] if r["id"] == key)
            self.assertEqual(source_row["source_refs"]["2025"][0]["source_id"], "synthetic_primary_statements")
        self.assertEqual(self.values["north_sales"]["2025"], 100.)
        self.assertEqual(self.values["specialty_sales"]["2025"], 80.)
        self.assertEqual(self.data["historical"]["cash"]["values"]["2025"], 29.5)

    def test_independently_calculated_forecast_and_integrated_balances(self):
        expected = dict(north_sales=103., specialty_sales=84., sales=187., north_cash_cost=77.265,
            specialty_cash_cost=68.289, da=10.7, utop=30.746, cogs=-93.7524,
            operating_profit=30.746, financial_income=1., financial_expense=-4., pretax=27.746,
            tax_expense=-5.5492, total_profit=23.5968, inventories=31.2508,
            receivables=25.97222222222222, trade_payables=20.833866666666665,
            cfo=34.477029629629626, closing_cash=37.67307407407407, cash=35.67307407407407,
            total_debt=70., owned_ppe=67.9888888888889, right_of_use_assets=11.8,
            intangibles=22.016666666666666, total_assets=255.10165185185184)
        for key, amount in expected.items():
            with self.subTest(metric=key):
                self.assertAlmostEqual(self.values[key]["2026"], amount)
        checks = validate_integrated(self.spec, self.values)
        self.assertFalse([c for c in checks if c["status"] in ("FAIL", "MISSING")])
        self.assertAlmostEqual(self.values["total_assets"]["2026"], self.values["liabilities_equity"]["2026"])

    def test_initialization_expressions_reproduce_signed_source_ratios_and_asset_timing(self):
        from research_platform.construction import expression_tree, formula_value
        found=[]
        for row in self.spec['rows']:
            if 'initialization_expression' not in row:
                continue
            with self.subTest(driver=row['id']):
                period=int(row['initialization_period'])
                result=formula_value(expression_tree(row['initialization_expression']),
                    lambda role,lag:self.data['historical'][role]['values'][str(period-lag)])
                self.assertAlmostEqual(result,row['historical'][str(period)])
                found.append(row['id'])
        self.assertIn('effective_tax_rate',found)
        self.assertIn('cogs_allocation',found)
        self.assertIn('owned_depreciation_rate',found)

    def test_current_tax_settlement_excludes_deferred_charge_and_preserves_cash_bridge(self):
        for key,amount in {'current_tax_expense':-4.4,'deferred_tax_expense':-1.,
                           'deferred_tax_assets':2.,'deferred_tax_liabilities':3.}.items():
            self.data['historical'][key]=copy.deepcopy(self.data['historical']['tax_expense'])
            self.data['historical'][key]['values']={str(y):amount for y in (2024,2025)}
        spec=build_integrated_spec(self.data,2)
        rows={r['id']:r for r in spec['rows']};values=calculate_integrated(spec)
        self.assertAlmostEqual(rows['cash_tax_ratio']['inputs']['2026'],5/4.4)
        self.assertAlmostEqual(values['paid_tax']['2026'],self.values['paid_tax']['2026'])
        changed=calculate_integrated(spec,{'deferred_tax_share':{'2026':1/5.4+.01}})
        deferred_liability_change=-values['tax_expense']['2026']*.01
        expected_cash=deferred_liability_change*5/4.4
        self.assertAlmostEqual(changed['total_profit']['2026'],values['total_profit']['2026'])
        for key in ('paid_tax','cfo','cash','total_liabilities'):
            self.assertAlmostEqual(changed[key]['2026']-values[key]['2026'],expected_cash)
        self.assertAlmostEqual(changed['deferred_tax_liabilities']['2026']-values['deferred_tax_liabilities']['2026'],deferred_liability_change)
        self.assertAlmostEqual(changed['current_tax_liabilities']['2026']-values['current_tax_liabilities']['2026'],expected_cash-deferred_liability_change)
        self.assertFalse([c for c in validate_integrated(spec,changed) if c['status'] in ('FAIL','MISSING')])
        self.assertFalse([c for c in financial_sensitivities(spec,values) if c['status']=='FAIL'])

    def test_price_and_operating_cost_controls_reach_group_profit_and_cash(self):
        priced = calculate_integrated(self.spec, {"north_pricing": {2026: .03}})
        self.assertAlmostEqual(priced["sales"]["2026"] - self.values["sales"]["2026"], 1.)
        self.assertAlmostEqual(priced["total_profit"]["2026"] - self.values["total_profit"]["2026"], .8)
        self.assertAlmostEqual(priced["closing_cash"]["2026"] - self.values["closing_cash"]["2026"], .212037037037037)
        self.assertEqual(priced["specialty_sales"], self.values["specialty_sales"])
        costed = calculate_integrated(self.spec, {"north_cost_inflation": {2026: .03}})
        self.assertAlmostEqual(costed["utop"]["2026"] - self.values["utop"]["2026"], -.7575)
        self.assertAlmostEqual(costed["total_profit"]["2026"] - self.values["total_profit"]["2026"], -.606)
        self.assertAlmostEqual(costed["closing_cash"]["2026"] - self.values["closing_cash"]["2026"], -.36472222222222)

    def test_working_capital_capex_and_financing_have_expected_amounts_and_timing(self):
        rows = {r["id"]:r for r in self.spec["rows"]}
        inv = calculate_integrated(self.spec, {"inventory_ratio": {2026: rows["inventory_ratio"]["inputs"]["2026"]+.01}})
        self.assertAlmostEqual(inv["inventories"]["2026"] - self.values["inventories"]["2026"], .937524)
        self.assertAlmostEqual(inv["cfo"]["2026"] - self.values["cfo"]["2026"], -.937524)
        capex = calculate_integrated(self.spec, {"capex_ppe_ratio": {2026: rows["capex_ppe_ratio"]["inputs"]["2026"]+.01}})
        self.assertAlmostEqual(capex["owned_ppe"]["2026"] - self.values["owned_ppe"]["2026"], 1.87)
        self.assertAlmostEqual(capex["closing_cash"]["2026"] - self.values["closing_cash"]["2026"], -1.87)
        self.assertEqual(capex["da"]["2026"], self.values["da"]["2026"])
        self.assertAlmostEqual(capex["da"]["2027"] - self.values["da"]["2027"], .187)
        funded = calculate_integrated(self.spec, {"borrowing_input": {2026: 10.}})
        self.assertAlmostEqual(funded["total_debt"]["2026"] - self.values["total_debt"]["2026"], 10.)
        self.assertAlmostEqual(funded["closing_cash"]["2026"] - self.values["closing_cash"]["2026"], 10.)
        self.assertEqual(funded["debt_interest"]["2026"], self.values["debt_interest"]["2026"])
        self.assertAlmostEqual(funded["debt_interest"]["2027"] - self.values["debt_interest"]["2027"], 30./58.)
        for altered in (inv, capex, funded):
            self.assertFalse([c for c in validate_integrated(self.spec, altered) if c["status"] == "FAIL"])
        self.assertFalse([c for c in financial_sensitivities(self.spec, self.values) if c["status"] != "PASS"])

    def test_source_segment_discrepancy_is_not_erased_by_consolidation(self):
        data = copy.deepcopy(self.data)
        data["segments"][0]["sales2025"] += 7
        spec = build_integrated_spec(data, 2)
        checks = validate_integrated(spec, calculate_integrated(spec))
        reconciliation = next(c for c in checks if c["name"].startswith("segment_sales") and c["name"].endswith(":2025"))
        self.assertEqual(reconciliation["status"], "FAIL")
        self.assertEqual(reconciliation["difference"], -7.)


class IntegratedHistoryRegressionTests(unittest.TestCase):
    def test_schedule_merge_preserves_early_history_and_period_provenance(self):
        data=second_company()
        data['schedule_controls']={'sbc':dict(values={'2025':1.5},
            sources={'2025':[dict(source_id='synthetic_schedule',unit_id='table:equity',number_index=1)]},
            basis={'2025':'SYNTHETIC supplementary detail'})}
        spec=build_integrated_spec(data,2)
        row=next(r for r in spec['rows'] if r['id']=='sbc')
        self.assertEqual(row['historical'],{'2024':1.5,'2025':1.5})
        self.assertEqual(row['source_refs']['2024'][0]['source_id'],'synthetic_primary_statements')
        self.assertEqual(row['source_refs']['2025'][0]['source_id'],'synthetic_schedule')
        self.assertEqual(row['basis']['2024'],'SYNTHETIC original reporting basis')
        self.assertEqual(row['basis']['2025'],'SYNTHETIC supplementary detail')

    def test_null_supplement_cannot_erase_a_known_original_value(self):
        data=second_company()
        data['schedule_controls']={'sbc':dict(values={'2025':None},sources={})}
        spec=build_integrated_spec(data,2)
        row=next(r for r in spec['rows'] if r['id']=='sbc')
        self.assertEqual(row['historical']['2025'],1.5)

    def test_contradictory_schedule_anchor_fails_instead_of_overwriting_history(self):
        data=second_company()
        data['schedule_controls']={'sbc':dict(values={'2025':1.6},sources={})}
        with self.assertRaisesRegex(ValueError,'Conflicting historical/schedule anchors sbc:2025'):
            build_integrated_spec(data,2)

    @staticmethod
    def with_cash_components():
        data=second_company()
        groups={'impairment':(0.,0.),'disposal_result_cf':(0.,0.),'other_noncash_ex_sbc':(0.,0.),
            'other_operating_assets_liabilities_cf':(-6.5,-2.5),'cf_finance_timing':(0.,0.),
            'business_acquisitions_cf':(0.,0.),'business_disposals_cf':(0.,0.),
            'associate_investing_cf':(0.,0.),'treasury_investments_cf':(0.,0.),'other_investing_combined_cf':(0.,0.),
            'nci_acquisition_cf':(0.,0.),'short_debt_cash':(-.5,0.),
            'wc_prepayments_cf':(0.,0.),'wc_accruals_cf':(0.,0.)}
        for key,(earlier,later) in groups.items():
            data['historical'][key]=dict(values={'2024':earlier,'2025':later},sources={},basis='SYNTHETIC CF note')
        return data

    def test_all_year_cash_components_detect_hidden_errors_that_net_cash_does_not(self):
        cases=[('other_operating_assets_liabilities_cf','cfo_components'),
               ('business_acquisitions_cf','cfi_components'),('nci_acquisition_cf','cff_components'),
               ('wc_prepayments_cf','wc_components')]
        for component,control in cases:
            with self.subTest(component=component):
                data=self.with_cash_components()
                base=build_integrated_spec(data,2)
                self.assertFalse([c for c in validate_integrated(base,calculate_integrated(base))
                                  if c['status'] in ('FAIL','MISSING')])
                data['historical'][component]['values']['2024']+=4
                spec=build_integrated_spec(data,2)
                checks=validate_integrated(spec,calculate_integrated(spec))
                self.assertTrue(any(c['name'].startswith(control) and c['name'].endswith(':2024')
                                    and c['status']=='FAIL' for c in checks))
                self.assertTrue(any(c['name'].startswith('cash_roll') and c['name'].endswith(':2024')
                                    and c['status']=='PASS' for c in checks))

    def test_zero_nci_and_lease_ratios_require_two_real_zero_anchors(self):
        data=second_company()
        for key in ('nci_profit','dividends_nci','lease_liabilities','lease_interest_expense',
                    'rou_depreciation','right_of_use_assets','rou_additions'):
            data['historical'][key]['values']={'2024':0.,'2025':0.}
        spec=build_integrated_spec(data,2)
        rows={r['id']:r for r in spec['rows']}
        for key in ('nci_profit_share','nci_dividend_payout','lease_rate','rou_depreciation_rate'):
            self.assertEqual(rows[key]['inputs']['2026'],0.)
        values=calculate_integrated(spec)
        for key in ('nci_profit','dividends_nci','lease_liabilities','lease_interest','rou_depreciation'):
            self.assertEqual(values[key]['2026'],0.)
        for numerator,denominator in (('dividends_nci','nci_profit'),('lease_interest_expense','lease_liabilities'),
                                      ('rou_depreciation','right_of_use_assets')):
            bad=second_company()
            bad['historical'][denominator]['values']={'2024':0.,'2025':0.}
            with self.subTest(numerator=numerator),self.assertRaisesRegex(ValueError,'nonzero numerator with zero reported denominator'):
                build_integrated_spec(bad,2)

    def test_currency_and_forecast_precision_follow_company_specification(self):
        data=second_company();data['currency']='GBP'
        spec=build_integrated_spec(data,1)
        rows={r['id']:r for r in spec['rows']}
        self.assertEqual(rows['sales']['unit'],'GBPm')
        self.assertEqual(rows['eps_basic']['unit'],'GBPm/shares_m')
        self.assertEqual(rows['eps_basic']['display_unit'],'GBP/share')
        self.assertFalse([c for c in financial_sensitivities(spec,calculate_integrated(spec)) if c['status']=='FAIL'])
        for item in spec['identities']:
            if any(int(y) in spec['forecast_years'] for y in item['periods']):
                self.assertLessEqual(item['tolerance'],1e-6)


class HistoricalReferenceWeightsTests(unittest.TestCase):
    def setUp(self):
        self.data=second_company()

    def test_associate_reversal_and_tax_timing_have_signed_source_contributions(self):
        spec=build_integrated_spec(self.data,2)
        rows={r['id']:r for r in spec['rows']};values=calculate_integrated(spec)
        for year in ('2024','2025'):
            associates=rows['cf_associates']['source_refs'][year]
            self.assertEqual([r['contribution_weight'] for r in associates],[-1])
            self.assertEqual(associates[0]['expression_input'],'associate_profit')
            self.assertAlmostEqual(sum(map(weighted_reference_value,associates)),values['cf_associates'][year])
            tax=rows['cf_tax_timing']['source_refs'][year]
            self.assertEqual({r['expression_input']:r['contribution_weight'] for r in tax},
                             {'tax_expense':-1,'paid_tax':1})
            self.assertAlmostEqual(sum(map(weighted_reference_value,tax)),.4)
            self.assertAlmostEqual(sum(map(weighted_reference_value,tax)),values['cf_tax_timing'][year])
        # Derivation annotation must not mutate source originals.
        self.assertNotIn('contribution_weight',self.data['historical']['associate_profit']['sources']['2025'][0])

    def test_repeated_linear_dependency_is_counted_once_with_its_combined_weight(self):
        # Use an algebraically equivalent expansion to exercise a repeated AST
        # dependency through the actual compiler's private provenance helper.
        from research_platform.construction import expression_tree as original_tree
        def expanded(expression):
            return original_tree('sales + sales - sales + other_revenue'
                if expression=='sales + other_revenue' else expression)
        with patch('research_platform.construction.expression_tree',side_effect=expanded):
            spec=build_integrated_spec(self.data,2)
            values=calculate_integrated(spec)
        row=next(r for r in spec['rows'] if r['id']=='total_revenue')
        for year in ('2024','2025'):
            refs=row['source_refs'][year]
            sales_refs=[r for r in refs if r['expression_input']=='sales']
            self.assertEqual(len(sales_refs),1)
            self.assertEqual(sales_refs[0]['contribution_weight'],1)
            self.assertEqual(sum(map(weighted_reference_value,refs)),180.)
            self.assertEqual(sum(map(weighted_reference_value,refs)),values['total_revenue'][year])

    def test_residual_liability_subtraction_preserves_nested_original_weights(self):
        original=self.data['historical']['other_current_liabilities']['sources']['2025'][0]
        nested=dict(source_refs=[dict(original,original_value=15.,contribution_weight=1),
                                 dict(original,original_value=5.,contribution_weight=-1)],contribution_weight=1)
        self.data['historical']['other_current_liabilities']['sources']['2025']=[nested]
        spec=build_integrated_spec(self.data,2)
        rows={r['id']:r for r in spec['rows']};values=calculate_integrated(spec)
        refs=rows['other_current_liabilities_ex_tax']['source_refs']['2025']
        self.assertEqual(refs[0]['contribution_weight'],1)
        self.assertEqual(refs[0]['source_refs'][1]['contribution_weight'],-1)
        self.assertEqual(refs[1]['contribution_weight'],-1)
        self.assertEqual(sum(map(weighted_reference_value,refs)),6.)
        self.assertEqual(sum(map(weighted_reference_value,refs)),values['other_current_liabilities_ex_tax']['2025'])
        self.assertEqual(nested['contribution_weight'],1)

    def test_ratios_are_marked_nonadditive_and_cannot_masquerade_as_a_source_sum(self):
        spec=build_integrated_spec(self.data,2)
        rows={r['id']:r for r in spec['rows']};values=calculate_integrated(spec)
        refs=rows['north_margin']['source_refs']['2025']
        self.assertTrue(refs)
        self.assertTrue(all('non-additive expression' in r['reference_use'] for r in refs))
        self.assertTrue(all(r['derivation_expression']=='north_utop / north_sales' for r in refs))
        self.assertAlmostEqual(values['north_margin']['2025'],.2)
        self.assertNotAlmostEqual(sum(map(weighted_reference_value,refs)),values['north_margin']['2025'])

    def test_all_supported_linear_derived_source_sums_match_independent_values(self):
        # Give the synthetic corporate note explicit originals as well.
        self.data['corporate']['source_refs']={key:dict(source_id='synthetic_corporate',
            unit_id='table:corporate',original_value=value) for key,value in [('utop2025',-2.),('da2025',2.)]}
        spec=build_integrated_spec(self.data,2);values=calculate_integrated(spec)
        checked=[]
        for row in spec['rows']:
            if not row.get('historical_expression'):continue
            for year,refs in row['source_refs'].items():
                if not refs or values[row['id']].get(year) is None or any('reference_use' in r for r in refs):continue
                with self.subTest(row=row['id'],year=year):
                    actual=sum(map(weighted_reference_value,refs))
                    self.assertAlmostEqual(actual,values[row['id']][year])
                    checked.append((row['id'],year))
        self.assertGreaterEqual(len(checked),20)
        self.assertIn(('nonlease_debt','2025'),checked)
        self.assertIn(('north_cash_cost','2025'),checked)
        self.assertIn(('corporate_cash_cost','2025'),checked)


class IntegratedReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.outputs=Path(self.temp.name)/'outputs';self.run=self.outputs/'construct_synthetic'
        self.run.mkdir(parents=True)
        self.runtime=integrated_runtime_fingerprint()
        self.data=second_company();self.inventory={'manifest_sha256':'synthetic-archive-hash'}
        self.key=integrated_source_cache_key(self.data,self.inventory,self.runtime)
        self.config=dict(company=self.data['company'],sources='synthetic-source-location',
            manifest=self.inventory['manifest_sha256'],provider={'provider':'scripted_fixture_no_network'},
            mode='integrated_v1',input_hash=digest(self.data),forecast_years=2,
            runtime=self.runtime,source_cache_key=self.key)
        artifacts={}
        for name,value in [('source_validation.json',[{'area':'source','name':'fixture','status':'PASS'}]),
            ('model_specification.json',{'company':'SYNTHETIC'}),('forecast.json',{'fixture':1}),
            ('validation.json',{'status':'complete_provisional','checks':[{'status':'PASS'}]}),
            ('workbook_validation.json',{'recalculation':{'status':'passed','engine':'scripted test fixture'}})]:
            payload=json.dumps(value).encode();(self.run/name).write_bytes(payload)
            artifacts[name]=hashlib.sha256(payload).hexdigest()
        workbook=b'SYNTHETIC workbook integrity bytes; not a financial demonstration'
        (self.run/'model.xlsx').write_bytes(workbook)
        artifacts['model.xlsx']=hashlib.sha256(workbook).hexdigest()
        original=self.run/'synthetic_original.txt';original.write_bytes(b'SYNTHETIC original')
        request=dict(stage='integrated_review',model='gpt-6-luna',effort='medium',instructions='fixture',payload={},schema={},attempt=0)
        call=dict(call_id='synthetic-saved-call',signature=digest(request),model='gpt-6-luna',request=request,result={'ok':True})
        self.record=dict(directory=str(self.run),status='complete_provisional',configuration=self.config,
            calls=[call],pending_call=None,artifacts=artifacts,
            sources=[dict(id='synthetic',path=str(original),sha256=hashlib.sha256(original.read_bytes()).hexdigest())])
        self.save()

    def save(self):
        (self.run/'record.json').write_text(json.dumps(self.record),encoding='utf-8')
        (self.run/'calls.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in self.record['calls']),encoding='utf-8')

    def changed_descendant(self,extra_calls=()):
        child=self.outputs/'construct_changed_descendant';child.mkdir()
        for file in self.run.iterdir():
            if file.is_file():(child/file.name).write_bytes(file.read_bytes())
        record=copy.deepcopy(self.record);record.update(directory=str(child),parent_run=str(self.run))
        record['calls'].extend(copy.deepcopy(extra_calls))
        (child/'record.json').write_text(json.dumps(record),encoding='utf-8')
        (child/'calls.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in record['calls']),encoding='utf-8')
        (child/'model.xlsx').write_bytes(b'SYNTHETIC workbook changed after accepted export; preserve it')
        later=self.run.stat().st_mtime+10;os.utime(child,(later,later))
        return record

    def test_default_continuation_still_blocks_changed_latest_workbook(self):
        child=self.changed_descendant();path=Path(child['directory'])
        before={p.name:p.read_bytes() for p in path.iterdir() if p.is_file()}
        with self.assertRaisesRegex(ValueError,'artifact content changed: model.xlsx'):
            select_integrated_previous([self.record,child],self.outputs,self.data['company'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in path.iterdir() if p.is_file()})

    def test_explicit_ancestor_reuses_only_verified_work_and_carries_all_descendant_charges_once(self):
        provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE',max_output_tokens=500)
        self.config.update(provider=provider.metadata(),limits=dict(usd=20.,calls=20,repairs=0,retries=0,generated_tokens=10000))
        schema=dict(type='object',properties={'ok':{'type':'boolean'}},required=['ok'],additionalProperties=False)
        original=self.record['calls'][0];original['request']['schema']=schema;original['signature']=digest(original['request'])
        response=dict(model='gpt-6-luna',status='completed',usage=dict(input_tokens=100,output_tokens=20,total_tokens=120))
        original['usage']=response_usage(response,'gpt-6-luna');original['response']=response;self.save()
        later=copy.deepcopy(original);later['call_id']='descendant-paid-call';later['request']['payload']={'batch':'later'};later['signature']=digest(later['request'])
        unknown=copy.deepcopy(original);unknown['call_id']='descendant-timeout';unknown['request']['payload']={'batch':'unknown'};unknown['signature']=digest(unknown['request'])
        unknown.pop('result');unknown['response']=None;unknown['usage']=response_usage(None,'gpt-6-luna');unknown['error']='Synthetic transport timeout'
        unknown['allowance']=provider.estimate_request_cost(role='reviewer',instructions='fixture',payload=dict(unknown['request']['payload'],stage='integrated_review'),schema=schema)
        child=self.changed_descendant([later,unknown]);prior=[self.record,child]
        original_bytes={str(p):p.read_bytes() for run in (self.run,Path(child['directory'])) for p in run.iterdir() if p.is_file()}
        ledger=BudgetLedger(self.outputs/'synthetic_budget.json',self.data['company'],20.)
        for record in prior:ledger.import_record(record)
        before=ledger.summary();self.assertEqual(before['total_requests'],3);self.assertEqual(before['settled_requests'],2)
        self.assertAlmostEqual(before['known_cost_usd'],2*original['usage']['estimated_cost_usd'])
        self.assertGreater(before['unresolved_reservations_usd'],0)
        selected,recovery=select_integrated_previous(prior,self.outputs,self.data['company'],self.run.name)
        self.assertEqual(selected['directory'],str(self.run));self.assertEqual(len(selected['calls']),1)
        self.assertEqual(recovery['excluded_runs'][0]['directory'],child['directory'])
        self.assertIn('model.xlsx',recovery['newest_verification_error'])
        self.assertEqual(recovery['excluded_runs'][0]['calls_sha256'],hashlib.sha256((Path(child['directory'])/'calls.jsonl').read_bytes()).hexdigest())
        continuation=self.outputs/'construct_recovery';continuation.mkdir()
        journal=RunJournal(continuation,provider,self.config,previous=selected,ledger=ledger)
        with patch('research_platform.ai.urlopen') as network,patch.object(provider,'complete',side_effect=AssertionError('No dispatch on exact reuse')):
            self.assertEqual(journal.ask('integrated_review','fixture',{},schema),{'ok':True});network.assert_not_called()
        for record in [journal.state,child,self.record]:ledger.import_record(record)
        self.assertEqual(ledger.summary(),before)
        self.assertEqual(original_bytes,{name:Path(name).read_bytes() for name in original_bytes})

    def test_explicit_resume_rejects_sibling_and_damaged_selected_ancestor(self):
        child=self.changed_descendant();sibling=copy.deepcopy(self.record)
        sibling_path=self.outputs/'construct_sibling';sibling_path.mkdir();sibling['directory']=str(sibling_path)
        earlier=self.run.stat().st_mtime-10;os.utime(sibling_path,(earlier,earlier))
        prior=[self.record,sibling,child]
        with self.assertRaisesRegex(ValueError,'ancestor'):
            select_integrated_previous(prior,self.outputs,self.data['company'],sibling_path)
        with self.assertRaisesRegex(ValueError,'artifact content changed'):
            select_integrated_previous(prior,self.outputs,self.data['company'],child['directory'])
        (self.run/'model.xlsx').write_bytes(b'Also changed')
        with self.assertRaisesRegex(ValueError,'artifact content changed'):
            select_integrated_previous(prior,self.outputs,self.data['company'],self.run)

    def test_exact_accepted_result_and_source_checks_can_reuse_without_provider(self):
        with patch('research_platform.ai.urlopen') as network,patch.object(OpenAIProvider,'from_env',side_effect=AssertionError('No credentials for reuse')):
            verified=verified_integrated_record(self.run,self.outputs)
            self.assertTrue(compatible_integrated_result(verified,self.config,self.runtime,self.key))
            checks=cached_integrated_source_checks(verified,self.key)
            checks[0]['status']='FAIL'
            self.assertEqual(cached_integrated_source_checks(verified,self.key)[0]['status'],'PASS')
            network.assert_not_called()

    def test_default_provider_pricing_survives_saved_configuration_roundtrip_for_reuse(self):
        provider=OpenAIProvider(api_key='',stage_models={'integrated_schedules':'gpt-6.1-sol'},
            stage_efforts={'integrated_schedules':'medium'},max_output_tokens=12000,timeout=240)
        metadata=provider.metadata()
        self.assertEqual(metadata,json.loads(json.dumps(metadata)))
        self.config['provider']=metadata;self.save()
        with patch('research_platform.ai.urlopen') as network:
            verified=verified_integrated_record(self.run,self.outputs)
            self.assertTrue(compatible_integrated_result(verified,self.config,self.runtime,self.key))
            network.assert_not_called()
        metadata['pricing']['rates']['gpt-6-luna'][0]=999
        self.assertNotEqual(provider.metadata()['pricing']['rates']['gpt-6-luna'][0],999)

    def test_source_cache_invalidates_on_data_sources_parser_or_evidence_code(self):
        variants=[]
        changed=copy.deepcopy(self.data);changed['historical']['sales']['values']['2025']+=1
        variants.append(integrated_source_cache_key(changed,self.inventory,self.runtime))
        variants.append(integrated_source_cache_key(self.data,{'manifest_sha256':'changed'},self.runtime))
        changed=copy.deepcopy(self.runtime);changed['parsers']['pypdf']='different'
        variants.append(integrated_source_cache_key(self.data,self.inventory,changed))
        changed=copy.deepcopy(self.runtime);changed['code']['evidence.py']='different'
        variants.append(integrated_source_cache_key(self.data,self.inventory,changed))
        self.assertTrue(all(key!=self.key for key in variants))
        verified=verified_integrated_record(self.run,self.outputs)
        self.assertIsNone(cached_integrated_source_checks(verified,variants[0]))

    def test_call_journal_and_request_identity_damage_reject_reuse(self):
        (self.run/'calls.jsonl').write_text('',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'differs from record'):
            verified_integrated_record(self.run,self.outputs)
        self.record['calls'][0]['request']['instructions']='changed after paid result'
        self.save()
        with self.assertRaisesRegex(ValueError,'signature is invalid'):
            verified_integrated_record(self.run,self.outputs)

    def test_modified_workbook_and_frozen_source_reject_reuse(self):
        (self.run/'model.xlsx').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'artifact content changed'):
            verified_integrated_record(self.run,self.outputs)
        self.record['artifacts']['model.xlsx']=hashlib.sha256(b'changed').hexdigest();self.save()
        (self.run/'synthetic_original.txt').write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError,'Frozen source bytes changed'):
            verified_integrated_record(self.run,self.outputs)

    def test_changed_runtime_configuration_or_pending_call_never_returns_accepted_result(self):
        verified=verified_integrated_record(self.run,self.outputs)
        for field,value in [('input_hash','changed'),('forecast_years',5),('manifest','changed'),('provider',{}),
                ('valuation',dict(enabled=True,date='2026-10-25',inputs_sha256='changed'))]:
            changed=copy.deepcopy(self.config);changed[field]=value
            self.assertFalse(compatible_integrated_result(verified,changed,self.runtime,self.key))
        runtime=copy.deepcopy(self.runtime);runtime['code']['integrated.py']='changed'
        self.assertFalse(compatible_integrated_result(verified,self.config,runtime,self.key))
        verified['pending_call']={'call_id':'still-unknown'}
        self.assertFalse(compatible_integrated_result(verified,self.config,self.runtime,self.key))


class ConstructionScopeLockTests(unittest.TestCase):
    def test_independent_companies_can_run_but_same_company_cannot_branch(self):
        from research_platform.budget import company_key
        from research_platform.initiation import _initiation_lock
        with tempfile.TemporaryDirectory() as temp:
            outputs=Path(temp)/'outputs'
            first=company_key('Synthetic Alpha plc');second=company_key('Synthetic Beta plc')
            with _initiation_lock(outputs,scope=first):
                with self.assertRaisesRegex(AIError,'this company is active'):
                    with _initiation_lock(outputs,scope=company_key('SYNTHETIC ALPHA PLC')):pass
                with _initiation_lock(outputs,scope=second):
                    with self.assertRaisesRegex(AIError,'this company is active'):
                        with _initiation_lock(outputs,scope=second):pass
            with _initiation_lock(outputs,scope=first):pass
            self.assertTrue((outputs/('.construction_'+first+'.lock')).exists())

    def test_invalid_scope_rejected_and_error_releases_real_os_lock(self):
        from research_platform.budget import company_key
        from research_platform.initiation import _initiation_lock
        with tempfile.TemporaryDirectory() as temp:
            outputs=Path(temp)/'outputs';scope=company_key('Synthetic Alpha plc')
            with self.assertRaisesRegex(ValueError,'hexadecimal company key'):
                with _initiation_lock(outputs,scope='../outside'):pass
            with self.assertRaisesRegex(RuntimeError,'synthetic failure'):
                with _initiation_lock(outputs,scope=scope):raise RuntimeError('synthetic failure')
            with _initiation_lock(outputs,scope=scope):pass


class JournalReservationContinuationTests(unittest.TestCase):
    def test_unknown_reserved_call_can_continue_and_settle_only_once_without_network(self):
        provider = OpenAIProvider(api_key="SYNTHETIC-TEST-KEY", max_output_tokens=500)
        company = "SYNTHETIC Continuation Company"
        config = dict(company=company, provider=provider.metadata(),
            limits=dict(usd=20., calls=8, repairs=0, retries=0, generated_tokens=5000))
        schema = dict(type="object", properties={"ok": {"type":"boolean"}}, required=["ok"], additionalProperties=False)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);first=root/"first";first.mkdir();second=root/"second";second.mkdir()
            ledger=BudgetLedger(root/"budget.json",company,20.)
            journal=RunJournal(first,provider,config,ledger=ledger)
            with patch("research_platform.ai.urlopen") as network, patch.object(provider,"complete",side_effect=AIError("Synthetic timeout")):
                with self.assertRaisesRegex(AIError,"Synthetic timeout"):
                    journal.ask("integrated_review","fixture",{"batch":"first"},schema)
                network.assert_not_called()
            old_reservation=ledger.summary()["unresolved_reservations_usd"]
            self.assertGreater(old_reservation,0)
            old=json.loads((first/"record.json").read_text())
            ledger.import_record(old)
            resumed=RunJournal(second,provider,config,previous=old,ledger=ledger)
            def complete(**kwargs):
                # The reservation and pending request must already be durable.
                state=json.loads((second/"record.json").read_text())
                self.assertIsNotNone(state["pending_call"])
                self.assertEqual(ledger.summary()["total_requests"],2)
                provider.last_response=dict(model="gpt-6-luna",status="completed",id="resp_synthetic",
                    usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[])
                return {"ok":True}
            with patch("research_platform.ai.urlopen") as network,patch.object(provider,"complete",side_effect=complete) as call:
                self.assertEqual(resumed.ask("integrated_review","fixture",{"batch":"second"},schema),{"ok":True})
                self.assertEqual(resumed.ask("integrated_review","fixture",{"batch":"second"},schema),{"ok":True})
                self.assertEqual(call.call_count,1)
                network.assert_not_called()
            ledger.import_record(resumed.state)
            ledger.import_record(old)
            final=ledger.summary()
            self.assertEqual(final["unresolved_reservations_usd"],old_reservation)
            self.assertEqual(final["settled_requests"],1)
            self.assertEqual(final["total_requests"],2)
            self.assertEqual(final["known_cost_usd"],response_usage(provider.last_response,"gpt-6-luna")["estimated_cost_usd"])


class IntegratedEscalationTests(unittest.TestCase):
    @staticmethod
    def evidence():
        return dict(failure="Repeated schedule scope error",input_fixes=["Include the opening note and dependencies"],
            reason="Narrow adjudication after a documented cheaper attempt",
            luna_trials=[dict(run="synthetic_prior_run",model="gpt-6-luna",effort="medium",
                              result="Misclassified an explicitly separate asset balance")])

    def test_one_documented_medium_luna_trial_allows_only_the_named_stage(self):
        provider=OpenAIProvider(api_key="SYNTHETIC-TEST-KEY",max_output_tokens=500,
            stage_models={"integrated_schedules":"gpt-6.1-sol","integrated_structure":"gpt-6.1-sol"},
            stage_efforts={"integrated_schedules":"medium"})
        config=dict(limits=dict(usd=20.,calls=5,repairs=0,retries=0,generated_tokens=5000),
                    escalations={"integrated_schedules":self.evidence()})
        schema=dict(type="object",properties={"ok":{"type":"boolean"}},required=["ok"],additionalProperties=False)
        with tempfile.TemporaryDirectory() as temp:
            journal=RunJournal(Path(temp),provider,config)
            def complete(**kwargs):
                provider.last_response=dict(model="gpt-6.1-sol",usage=dict(input_tokens=10,output_tokens=5,total_tokens=15),output=[])
                return {"ok":True}
            with patch("research_platform.ai.urlopen") as network,patch.object(provider,"complete",side_effect=complete) as call:
                self.assertEqual(journal.ask("integrated_schedules","synthetic review",{},schema),{"ok":True})
                with self.assertRaisesRegex(AIError,"Non-Luna"):
                    journal.ask("integrated_structure","synthetic review",{},schema)
                self.assertEqual(call.call_count,1)
                network.assert_not_called()
            self.assertEqual(journal.entries[0]["model"],"gpt-6.1-sol")
            self.assertEqual(journal.entries[0]["reasoning_effort"],"medium")
            self.assertEqual(journal.entries[0]["escalation_reason"],self.evidence()["reason"])

    def test_missing_or_malformed_escalation_evidence_blocks_before_dispatch(self):
        invalid=[]
        for field in ("failure","input_fixes","reason","luna_trials"):
            item=self.evidence();item.pop(field);invalid.append(item)
        for trial in ({"effort":"medium","run":"prior"},
                      {"effort":"medium","result":"failure"},
                      {"effort":"medium","run":"prior","result":"failure","model":"gpt-6.1-sol"},
                      "not a trial"):
            item=self.evidence();item["luna_trials"]=[trial];invalid.append(item)
        invalid.extend([None,[]])
        provider=OpenAIProvider(api_key="SYNTHETIC-TEST-KEY",max_output_tokens=500,
                                stage_models={"integrated_schedules":"gpt-6.1-sol"})
        for evidence in invalid:
            with self.subTest(evidence=evidence),tempfile.TemporaryDirectory() as temp:
                config=dict(limits=dict(usd=20.,calls=5,repairs=0,retries=0,generated_tokens=5000),
                            escalations={"integrated_schedules":evidence})
                journal=RunJournal(Path(temp),provider,config)
                with patch.object(provider,"complete") as call,patch.object(provider,"estimate_request_cost") as allowance:
                    with self.assertRaisesRegex(AIError,"Non-Luna"):
                        journal.ask("integrated_schedules","synthetic review",{},dict(type="object"))
                    call.assert_not_called();allowance.assert_not_called()

    def test_integrated_route_persists_evidence_without_changing_model_settings(self):
        from research_platform.integrated import construct_integrated
        class ReachedJournal(Exception):pass
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/"sources";archive.mkdir()
            inputs=root/"inputs.json";inputs.write_text(json.dumps({'fiscal_calendar':{'fiscal_year_end':'06-30'}}),encoding="utf-8")
            evidence=root/"escalation.json";expected={"integrated_schedules":self.evidence()}
            evidence.write_text(json.dumps(expected),encoding="utf-8")
            provider=OpenAIProvider(api_key="SYNTHETIC-TEST-KEY",
                stage_models={"integrated_schedules":"gpt-6.1-sol"},stage_efforts={"integrated_schedules":"medium"})
            with patch("research_platform.integrated.inventory_local_sources",return_value={"manifest_sha256":"synthetic"}), \
                    patch("research_platform.integrated.RunJournal",side_effect=ReachedJournal) as journal, \
                    patch("research_platform.ai.urlopen") as network:
                with self.assertRaises(ReachedJournal):
                    construct_integrated(root,"Synthetic Escalation Company",archive,inputs,
                                         provider=provider,escalation_file=evidence)
                configuration=journal.call_args.args[2]
                self.assertEqual(configuration["escalations"],expected)
                self.assertEqual(configuration["provider"]["stage_models"],{"integrated_schedules":"gpt-6.1-sol"})
                self.assertEqual(configuration["provider"]["stage_reasoning_efforts"]["integrated_schedules"],"medium")
                network.assert_not_called()

    def test_cli_passes_escalation_file_to_integrated_route(self):
        from research_platform.__main__ import main
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            argv=["research_platform","construct","Synthetic Company","--sources",str(root),
                  "--model-inputs","synthetic-inputs.json","--escalation-evidence","synthetic-escalation.json"]
            with patch("sys.argv",argv),patch("research_platform.__main__.find_project_root",return_value=root), \
                    patch("research_platform.workflow.ensure_company_history_research",return_value=Path('synthetic-inputs.json')), \
                    patch("research_platform.workflow.ensure_valuation_research",return_value=Path('synthetic-inputs.json')), \
                    patch("research_platform.integrated.construct_integrated",return_value=root) as construct, \
                    patch("research_platform.project.read_json",return_value=dict(status="complete_provisional",usage={},issues=[])), \
                    patch("research_platform.ai.format_usage",return_value="synthetic"), \
                    patch("research_platform.ai.format_stage_usage",return_value="synthetic"),patch("builtins.print"):
                self.assertEqual(main(),0)
                self.assertEqual(construct.call_args.kwargs["escalation_file"],"synthetic-escalation.json")


class AutomaticReviewTests(unittest.TestCase):
    def run_review(self, answers, *, repair=None, limit=20, payload=None, calls=8):
        from research_platform.integrated import REVIEW_SCHEMA
        provider=OpenAIProvider(api_key='SYNTHETIC-TEST-KEY',max_output_tokens=500)
        routes=[]
        def complete(**kwargs):
            model,_=provider.route(kwargs['role'],kwargs['payload']['stage'])
            routes.append(model)
            provider.last_response=dict(model=model,usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[])
            return answers[len(routes)-1]
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        journal=RunJournal(Path(temp.name),provider,dict(limits=dict(usd=limit,calls=calls,repairs=1,retries=0,generated_tokens=10000)))
        self.last_review_journal=journal;self.last_review_routes=routes
        with patch.object(provider,'complete',side_effect=complete),patch('research_platform.ai.urlopen') as network:
            result=journal.review_stage('integrated_schedules','Evidence-based fixture review',payload or {},REVIEW_SCHEMA,repair_context=repair)
            network.assert_not_called()
        return result,routes,journal,provider

    @staticmethod
    def answer(error=False,cited=True):
        return dict(findings=[dict(severity='error',area='scope',detail='Synthetic contradictory scope interpretation',source_references=['synthetic_note:page:1'] if cited else [])] if error else [],summary='Synthetic fixture')

    def test_pass_uses_only_luna(self):
        _,routes,journal,provider=self.run_review([self.answer()])
        self.assertEqual(routes,['gpt-6-luna']);self.assertNotIn('integrated_schedules',provider.stage_models)
        self.assertFalse((journal.directory/'integrated_schedules_escalation.json').exists())

    def test_context_repair_precedes_any_escalation(self):
        def repair(payload,failures):return dict(payload,missing_note='Synthetic original scope note')
        _,routes,journal,_=self.run_review([self.answer(True,False),self.answer()],repair=repair)
        self.assertEqual(routes,['gpt-6-luna','gpt-6-luna'])
        self.assertEqual(journal.entries[1]['request']['payload']['missing_note'],'Synthetic original scope note')

    def test_last_acquisition_gets_exactly_one_cheap_completion_review(self):
        original=dict(source_id='original',unit_id='page:1',text='Verbatim supplied statement.',numbers=[])
        added=dict(source_id='note',unit_id='page:2',text='Verbatim omitted primary note 100.',numbers=[dict(index=0,raw='100')])
        repairs=[]
        def repair(payload,failures):
            repairs.append(copy.deepcopy(payload))
            return dict(payload,evidence=payload['evidence']+[added]) if len(repairs)==2 else payload
        _,routes,journal,_=self.run_review([self.answer(True,False),self.answer(True,False),self.answer()],repair=repair,payload=dict(evidence=[original]))
        self.assertEqual(routes,['gpt-6-luna']*3);self.assertEqual(len(repairs),2)
        self.assertEqual(journal.entries[2]['request']['payload']['evidence'],[original,added])
        self.assertEqual([entry['request']['attempt'] for entry in journal.entries],[0,1,2])
        routing=json.loads((journal.directory/'integrated_schedules_routing.json').read_text())
        self.assertTrue(routing['history'][-1]['terminal_evidence_review_pending'])
        self.assertEqual(routing['status'],'passed')

    def test_terminal_evidence_completion_cannot_acquire_again_or_waive_missing_support(self):
        repairs=[]
        def repair(payload,failures):
            repairs.append(None)
            return dict(payload,evidence=payload.get('evidence',[])+[dict(source_id='original',unit_id='page:'+str(len(repairs)),text='Complete new primary note.',numbers=[])])
        with self.assertRaisesRegex(ValueError,'premium model cannot repair'):
            self.run_review([self.answer(True,False)]*3,repair=repair)
        self.assertEqual(self.last_review_routes,['gpt-6-luna']*3)
        self.assertEqual(len(repairs),2)
        self.assertNotIn('integrated_schedules',self.last_review_journal.configuration.get('escalations',{}))

    def test_feedback_only_reordering_encoding_or_removal_cannot_extend_review(self):
        units=[dict(source_id='original',unit_id='page:1',text='Source statement 100.',numbers=[dict(index=0,raw='100')]),
            dict(source_id='original',unit_id='page:2',text='Source notes.',numbers=[])]
        for change in ('feedback','ordering','encoding','removal'):
            attempts=[]
            def repair(payload,failures):
                attempts.append(None);result=copy.deepcopy(payload)
                result['review_challenge']='Changed feedback '+str(len(attempts))
                if change=='ordering':result['evidence'].reverse()
                elif change=='encoding':result['evidence'][0]['numbers']=dict(encoding='token_columns_v1',columns=['index','raw'],rows=[[0,'100']])
                elif change=='removal':result['evidence']=result['evidence'][:1]
                return result
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'premium model cannot repair'):
                self.run_review([self.answer(True,False)]*2,repair=repair,payload=dict(evidence=units))
            self.assertEqual(self.last_review_routes,['gpt-6-luna']*2)
            self.assertEqual(len(attempts),2)

    def test_financial_escalation_retains_acquired_originals_and_unique_attempts(self):
        note=dict(source_id='original',unit_id='page:2',text='Primary reconciliation note.',numbers=[])
        repairs=[]
        def repair(payload,failures):
            repairs.append(None)
            return dict(payload,evidence=[note]) if len(repairs)==2 else payload
        _,routes,journal,_=self.run_review([self.answer(True,False),self.answer(True,False),self.answer(True),self.answer()],repair=repair)
        self.assertEqual(routes,['gpt-6-luna']*3+['gpt-6.1-sol'])
        self.assertEqual(len(repairs),2)
        self.assertEqual([entry['request']['attempt'] for entry in journal.entries],[0,1,2,3])
        self.assertEqual(journal.entries[-1]['request']['payload']['evidence'],[note])

    def test_completion_dispatch_still_obeys_budget_and_call_limits(self):
        repairs=[]
        def repair(payload,failures):
            repairs.append(None)
            if len(repairs)==2:
                self.last_review_journal.configuration['limits']['usd']=0
                return dict(payload,evidence=[dict(source_id='original',unit_id='page:2',text='New original.',numbers=[])])
            return payload
        with self.assertRaisesRegex(AIError,'remaining cumulative budget'):
            self.run_review([self.answer(True,False)]*2,repair=repair)
        self.assertEqual(self.last_review_routes,['gpt-6-luna']*2)
        repairs.clear()
        def bounded_repair(payload,failures):
            repairs.append(None)
            return dict(payload,evidence=[dict(source_id='original',unit_id='page:2',text='New original.',numbers=[])]) if len(repairs)==2 else payload
        with self.assertRaisesRegex(AIError,'Call/generated-token limit reached'):
            self.run_review([self.answer(True,False)]*2,repair=bounded_repair,calls=2)
        self.assertEqual(self.last_review_routes,['gpt-6-luna']*2)

    def test_cited_persistent_financial_disagreement_generates_evidence(self):
        _,routes,journal,provider=self.run_review([self.answer(True),self.answer(True),self.answer()])
        self.assertEqual(routes,['gpt-6-luna','gpt-6-luna','gpt-6.1-sol'])
        evidence=json.loads((journal.directory/'integrated_schedules_escalation.json').read_text())
        self.assertEqual(len(evidence['luna_trials']),2)
        self.assertNotIn('integrated_schedules',provider.stage_models)

    def test_budget_prevents_unaffordable_dispatch(self):
        with self.assertRaisesRegex(AIError,'remaining cumulative budget'):
            self.run_review([self.answer()],limit=0)

    def test_missing_uncited_evidence_does_not_trigger_premium(self):
        with self.assertRaisesRegex(ValueError,'premium model cannot repair'):
            self.run_review([self.answer(True,False),self.answer(True,False)])

    def test_missing_graph_dependency_is_context_failure_even_with_citation(self):
        payload=dict(complete_forecast_graph=[dict(id='assets',expression='omitted_owned_ppe + omitted_rou')])
        with self.assertRaisesRegex(ValueError,'premium model cannot repair'):
            self.run_review([self.answer(True),self.answer(True)],payload=payload)

    def test_owned_only_and_combined_asset_scope_follow_evidence(self):
        from research_platform.integrated import asset_scope_context
        data=dict(historical={k:dict(values={'2031':v}) for k,v in [('owned',80),('rou',20),('reported',100)]},
            asset_scope=[dict(reported_role='reported',owned_role='owned',rou_role='rou',reported_scope='owned_and_rou',owned_expression='reported - rou',source_refs=[{'source_id':'synthetic_note'}])])
        self.assertEqual(asset_scope_context(data)[0]['reconciliations'][0]['expected'],100)
        data['asset_scope'][0].update(reported_scope='owned_only',owned_expression='reported')
        data['historical']['reported']['values']['2031']=80
        self.assertEqual(asset_scope_context(data)[0]['reconciliations'][0]['expected'],80)
        data['asset_scope'][0]['owned_expression']='reported - rou'
        with self.assertRaisesRegex(ValueError,'Duplicate subtraction'):asset_scope_context(data)


if __name__ == "__main__":
    unittest.main()


class FrozenOriginalReuseTests(unittest.TestCase):
    def test_absent_original_reuses_exact_verified_parent_and_changed_live_file_rejects(self):
        from research_platform.integrated import freeze_model_sources
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'archive';archive.mkdir()
            outputs=root/'outputs';old=outputs/'old'/'sources';old.mkdir(parents=True)
            target=outputs/'new'/'sources';target.mkdir(parents=True)
            raw=b'Immutable original evidence';saved=old/'s.txt';saved.write_bytes(raw)
            source=dict(id='s',local_path='withdrawn.txt',sha256=hashlib.sha256(raw).hexdigest(),format='txt')
            data=dict(sources={'s':source});parent=dict(_reuse_verified=True,sources=[dict(source,path=str(saved))])
            frozen,audit=freeze_model_sources(data,archive,target,previous=parent,outputs=outputs)
            self.assertEqual(Path(frozen[0]['path']).read_bytes(),raw)
            self.assertEqual(audit[0]['source_id'],'s')
            self.assertEqual(data['sources']['s']['local_path'],'withdrawn.txt')
            (archive/'withdrawn.txt').write_bytes(b'changed original')
            with self.assertRaisesRegex(ValueError,'changed before freezing'):
                freeze_model_sources(data,archive,target,previous=parent,outputs=outputs)
            (archive/'withdrawn.txt').unlink()
            for wrong in (None,dict(parent,_reuse_verified=False),dict(parent,sources=[])):
                with self.assertRaisesRegex(ValueError,'no identical verified'):
                    freeze_model_sources(data,archive,target,previous=wrong,outputs=outputs)
            saved.write_bytes(b'changed frozen original')
            with self.assertRaisesRegex(ValueError,'changed before freezing'):
                freeze_model_sources(data,archive,target,previous=parent,outputs=outputs)
