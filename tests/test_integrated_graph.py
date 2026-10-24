"""Independent numerical examples for a segment-driven integrated annual graph."""
import copy
import unittest

from research_platform.construction import calculate_integrated, validate_integrated


def financial_example():
    """A complete synthetic accounting case, never a company-data substitute."""
    rows = []

    def driver(key, value, unit="ratio"):
        rows.append(dict(id=key, label=key, section="controls", unit=unit, kind="assumption",
                         historical={}, inputs={"2026": value, "2027": value},
                         note="Explicit synthetic temporary assumption"))

    def line(key, historical, expression, unit="CHFm", **extra):
        rows.append(dict(id=key, label=key, section="statements", unit=unit, kind="calculated",
                         historical={"2025": historical}, expression=expression, **extra))

    for key, value in (("north_price", .1), ("north_activity", .1), ("north_unit_cost", .05),
                       ("other_growth", 0), ("inventory_ratio", .2), ("receivables_ratio", .1),
                       ("payables_ratio", .1), ("depreciation_rate", .1), ("tax_rate", .2),
                       ("interest_rate", .05)):
        driver(key, value)
    for key, value in (("corporate_cost", 10), ("other_cost", 35), ("capex", 15),
                       ("borrowing", 5), ("repayment", 2), ("dividends", 10)):
        driver(key, value, "CHFm")
    line("north_sales", 100, 'lag("north_sales",1)*(1+north_price)*(1+north_activity)')
    line("other_sales", 50, 'lag("other_sales",1)*(1+other_growth)')
    line("sales", 150, "north_sales+other_sales", historical_expression="north_sales+other_sales")
    line("north_cost", 60, 'lag("north_cost",1)*(1+north_activity)*(1+north_unit_cost)')
    line("ebitda", None, "sales-north_cost-other_cost-corporate_cost")
    line("depreciation", None, 'lag("ppe",1)*depreciation_rate')
    line("ebit", None, "ebitda-depreciation")
    line("interest", None, 'lag("debt",1)*interest_rate')
    line("pretax", None, "ebit-interest")
    line("tax", None, "pretax*tax_rate")
    line("profit", None, "pretax-tax")
    line("inventory", 30, "sales*inventory_ratio", nonnegative=True)
    line("receivables", 20, "sales*receivables_ratio", nonnegative=True)
    line("payables", 15, "sales*payables_ratio", nonnegative=True)
    line("working_capital_cash", None,
         '-(inventory-lag("inventory",1))-(receivables-lag("receivables",1))+(payables-lag("payables",1))')
    line("cfo", None, "profit+depreciation+working_capital_cash")
    line("cash_change", None, "cfo-capex+borrowing-repayment-dividends")
    line("cash", 20, 'lag("cash",1)+cash_change')
    line("ppe", 100, 'lag("ppe",1)+capex-depreciation', nonnegative=True)
    line("debt", 60, 'lag("debt",1)+borrowing-repayment', nonnegative=True)
    line("equity", 95, 'lag("equity",1)+profit-dividends')
    line("assets", 170, "cash+inventory+receivables+ppe", nonnegative=True)
    line("liabilities_equity", 170, "payables+debt+equity")
    return dict(company="SYNTHETIC integration fixture", currency="CHF", historical_years=[2025],
        forecast_years=[2026, 2027], sections=[dict(id="controls", label="Controls"),
        dict(id="statements", label="Financial statements")], rows=rows,
        identities=[dict(id="balance_sheet", label="Assets equal liabilities and equity",
            expression="assets-liabilities_equity", periods=["2025", "2026", "2027"], tolerance=.000001, independent=False),
            dict(id="segment_sales", label="Segment consolidation", expression="sales-north_sales-other_sales",
                 periods=["2025", "2026", "2027"], tolerance=.000001, independent=False)])


class IntegratedGraphTests(unittest.TestCase):
    def setUp(self):
        self.spec = financial_example()

    def row(self, key):
        return next(row for row in self.spec["rows"] if row["id"] == key)

    def test_independent_known_three_statement_answers_and_balances(self):
        values = calculate_integrated(self.spec)
        expected = dict(north_sales=121., sales=171., north_cost=69.3, depreciation=10.,
                        ebit=46.7, interest=3., tax=8.74, profit=34.96, inventory=34.2,
                        receivables=17.1, payables=17.1, working_capital_cash=.8,
                        cfo=45.76, cash=43.76, ppe=105., debt=63., equity=119.96, assets=200.06)
        for key, amount in expected.items():
            with self.subTest(row=key):
                self.assertAlmostEqual(values[key]["2026"], amount)
        self.assertAlmostEqual(values["ppe"]["2027"], 109.5)
        self.assertAlmostEqual(values["cash"]["2027"], 73.3528)
        self.assertFalse([c for c in validate_integrated(self.spec, values) if c["status"] in ("FAIL", "MISSING")])

    def test_price_changes_segment_group_profit_and_cash_without_changing_cost(self):
        baseline = calculate_integrated(self.spec)
        changed = calculate_integrated(self.spec, {"north_price": {2026: .11}})
        for key, expected in (("north_sales", 1.1), ("sales", 1.1), ("profit", .88), ("cash", .66)):
            self.assertAlmostEqual(changed[key]["2026"] - baseline[key]["2026"], expected)
        self.assertEqual(changed["north_cost"]["2026"], baseline["north_cost"]["2026"])
        self.assertEqual(changed["other_sales"], baseline["other_sales"])
        self.assertEqual(self.row("north_price")["inputs"]["2026"], .1)

    def test_unit_cost_changes_profit_and_cash_in_expected_amount(self):
        baseline = calculate_integrated(self.spec)
        changed = calculate_integrated(self.spec, {"north_unit_cost": {"2026": .06}})
        self.assertAlmostEqual(changed["north_cost"]["2026"] - baseline["north_cost"]["2026"], .66)
        self.assertAlmostEqual(changed["profit"]["2026"] - baseline["profit"]["2026"], -.528)
        self.assertAlmostEqual(changed["cash"]["2026"] - baseline["cash"]["2026"], -.528)
        self.assertEqual(changed["sales"], baseline["sales"])

    def test_working_capital_driver_changes_balance_and_operating_cash(self):
        baseline = calculate_integrated(self.spec)
        changed = calculate_integrated(self.spec, {"inventory_ratio": {2026: .21}})
        self.assertAlmostEqual(changed["inventory"]["2026"] - baseline["inventory"]["2026"], 1.71)
        self.assertAlmostEqual(changed["cfo"]["2026"] - baseline["cfo"]["2026"], -1.71)
        self.assertAlmostEqual(changed["cash"]["2026"] - baseline["cash"]["2026"], -1.71)
        self.assertFalse([c for c in validate_integrated(self.spec, changed) if c["status"] == "FAIL"])

    def test_capex_has_current_cash_asset_and_subsequent_depreciation_effects(self):
        baseline = calculate_integrated(self.spec)
        changed = calculate_integrated(self.spec, {"capex": {2026: 16}})
        self.assertAlmostEqual(changed["ppe"]["2026"] - baseline["ppe"]["2026"], 1.)
        self.assertAlmostEqual(changed["cash"]["2026"] - baseline["cash"]["2026"], -1.)
        self.assertEqual(changed["depreciation"]["2026"], baseline["depreciation"]["2026"])
        self.assertAlmostEqual(changed["depreciation"]["2027"] - baseline["depreciation"]["2027"], .1)
        self.assertAlmostEqual(changed["ppe"]["2027"] - baseline["ppe"]["2027"], .9)

    def test_borrowing_has_current_cash_debt_and_next_year_interest_effects(self):
        baseline = calculate_integrated(self.spec)
        changed = calculate_integrated(self.spec, {"borrowing": {2026: 6}})
        self.assertAlmostEqual(changed["debt"]["2026"] - baseline["debt"]["2026"], 1.)
        self.assertAlmostEqual(changed["cash"]["2026"] - baseline["cash"]["2026"], 1.)
        self.assertEqual(changed["interest"]["2026"], baseline["interest"]["2026"])
        self.assertAlmostEqual(changed["interest"]["2027"] - baseline["interest"]["2027"], .05)
        self.assertAlmostEqual(changed["cash"]["2027"] - baseline["cash"]["2027"], .96)

    def test_raw_history_is_not_overwritten_to_make_a_consolidation_pass(self):
        self.row("sales")["historical"]["2025"] = 151.
        values = calculate_integrated(self.spec)
        self.assertEqual(values["sales"]["2025"], 151.)
        failure = next(c for c in validate_integrated(self.spec, values) if c["name"] == "segment_sales:2025")
        self.assertEqual(failure["status"], "FAIL")
        self.assertEqual(failure["difference"], 1.)
        self.row("sales")["historical"]["2025"] = None
        self.assertEqual(calculate_integrated(self.spec)["sales"]["2025"], 150.)

    def test_missing_driver_is_not_zero_and_optional_lines_are_explicit(self):
        values = calculate_integrated(self.spec, {"north_price": {2026: None}})
        self.assertIsNone(values["sales"]["2026"])
        self.assertIsNone(values["cash"]["2026"])
        self.assertEqual(values["other_sales"]["2026"], 50.)
        self.assertTrue(any(c["status"] == "MISSING" for c in validate_integrated(self.spec, values)))
        self.spec["rows"].append(dict(id="undisclosed", label="Undisclosed", section="statements",
                                     unit="CHFm", kind="reported", historical={}, optional=True))
        checks = validate_integrated(self.spec, calculate_integrated(self.spec))
        self.assertFalse(any(c["status"] == "MISSING" and c["name"].startswith("undisclosed") for c in checks))

    def test_duplicate_unknown_unit_and_circular_errors_rejected(self):
        for mutation, message in ((lambda s: s["rows"].append(copy.deepcopy(s["rows"][0])), "Duplicate"),
            (lambda s: next(r for r in s["rows"] if r["id"] == "sales").update(expression="unknown_sales"), "unknown references"),
            (lambda s: next(r for r in s["rows"] if r["id"] == "sales").update(expression="north_price+north_sales"), "units"),
            (lambda s: next(r for r in s["rows"] if r["id"] == "sales").update(expression="sales+north_sales"), "Circular")):
            spec = copy.deepcopy(self.spec)
            mutation(spec)
            with self.subTest(error=message), self.assertRaisesRegex(ValueError, message):
                calculate_integrated(spec)

    def test_overrides_cannot_change_sources_or_make_duplicate_authoritative_inputs(self):
        for override in ({"sales": {2026: 1}}, {"north_price": {2025: .1}},
                         {"north_price": {2026: .1, "2026": .2}}, {"north_price": {2026: float("nan")}}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                calculate_integrated(self.spec, override)

    def test_tampered_values_negative_stocks_and_changed_history_fail(self):
        values = calculate_integrated(self.spec)
        values["sales"]["2026"] += 1
        values["inventory"]["2026"] = -1
        values["cash"]["2025"] = 99
        failures = [c["name"] for c in validate_integrated(self.spec, values) if c["status"] == "FAIL"]
        self.assertIn("expression:sales:2026", failures)
        self.assertIn("nonnegative:inventory:2026", failures)
        self.assertIn("preserved_observation:cash:2025", failures)

    def test_zero_denominator_is_missing_and_zero_input_remains_zero(self):
        self.row("interest")["expression"] = 'lag("debt",1)/(1-interest_rate)'
        self.row("interest_rate")["inputs"]["2026"] = 1
        self.assertIsNone(calculate_integrated(self.spec)["interest"]["2026"])
        self.row("interest")["expression"] = 'lag("debt",1)*interest_rate'
        self.row("interest_rate")["inputs"]["2026"] = 0
        self.assertEqual(calculate_integrated(self.spec)["interest"]["2026"], 0.)


class CausalContractTests(unittest.TestCase):
    """Independent economic checks on a different fiscal calendar/company."""
    @classmethod
    def setUpClass(cls):
        from tests.test_periodic_model import different_period_company
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic
        cls.data=different_period_company();cls.spec=build_periodic_spec(cls.data,5)
        cls.values=calculate_periodic(cls.spec)

    def run_case(self,overrides):
        from research_platform.periods import calculate_periodic
        return calculate_periodic(self.spec,overrides)

    def test_marketing_cash_budget_reduces_profit_and_after_tax_cash(self):
        pid='2026-H1';v=self.values
        changed=self.run_case({'north_pool_marketing_admin_budget_change':{pid:100}})
        self.assertAlmostEqual(changed['operating_profit'][pid]-v['operating_profit'][pid],-100)
        self.assertAlmostEqual(changed['cfo'][pid]-v['cfo'][pid],-100*(1-.2*(5/5.4)))
        self.assertAlmostEqual(changed['marketing_admin'][pid]-v['marketing_admin'][pid],-100)
        self.assertAlmostEqual(changed['cogs'][pid],v['cogs'][pid])

    def test_pricing_has_no_automatic_marketing_or_cogs_change(self):
        pid='2026-H1';v=self.values
        changed=self.run_case({'north_pricing':{pid:v['north_pricing'][pid]+.1}})
        self.assertAlmostEqual(changed['sales'][pid]-v['sales'][pid],4)
        for role in ('north_pool_cogs','north_pool_marketing_admin','cogs','marketing_admin'):
            self.assertAlmostEqual(changed[role][pid],v[role][pid])

    def test_unit_input_inflation_hurts_profit_without_selling_price_increase(self):
        pid='2026-H1';v=self.values;rid='north_pool_cogs'
        changed=self.run_case({rid+'_unit_cost_change':{pid:.1}})
        expected=v[rid+'_seed'][pid]*(1+v[rid+'_activity_change'][pid])*.1
        self.assertAlmostEqual(changed['operating_profit'][pid]-v['operating_profit'][pid],-expected)
        self.assertAlmostEqual(changed['sales'][pid],v['sales'][pid])

    def test_activity_elasticity_changes_variable_pool_not_fixed_budget(self):
        pid='2026-H1';v=self.values
        changed=self.run_case({'north_rig':{pid:v['north_rig'][pid]+.1}})
        expected=v['north_pool_cogs_seed'][pid]*.1
        self.assertAlmostEqual(changed['north_pool_cogs'][pid]-v['north_pool_cogs'][pid],expected)
        self.assertAlmostEqual(changed['north_pool_marketing_admin'][pid],v['north_pool_marketing_admin'][pid])

    def test_dormant_missing_buyback_price_then_timed_repurchase(self):
        from research_platform.integrated import validate_financial_contracts
        pid='2026-H1';v=self.values
        self.assertIsNone(v['buyback_price'][pid]);self.assertEqual(v['buyback_shares'][pid],0)
        bad=self.run_case({'buyback_cash':{pid:20}})
        self.assertTrue(any(c['status']=='FAIL' and c['name']=='repurchase_price:'+pid for c in validate_financial_contracts(self.spec,bad)))
        changed=self.run_case({'buyback_cash':{pid:20},'buyback_price':{pid:10},'repurchase_elapsed_fraction':{pid:.5}})
        self.assertAlmostEqual(changed['shares_end_outstanding'][pid]-v['shares_end_outstanding'][pid],-2)
        self.assertAlmostEqual(changed['shares_basic'][pid]-v['shares_basic'][pid],-1)

    def test_dividend_annual_pool_is_not_current_half_year_profit(self):
        pid='2026-H1';v=self.values
        changed=self.run_case({'north_pricing':{pid:v['north_pricing'][pid]+.2}})
        for period in ('2026-H1','2026-H2','2026-FY'):
            self.assertAlmostEqual(changed['dividends_parent'][period],v['dividends_parent'][period])
        self.assertAlmostEqual(v['dividends_parent']['2026-FY'],-11)

    def test_annual_payout_uses_annual_amounts_with_asymmetric_half_profits(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'dividends':{
            'parent':{'annual_amount':40,'payment_weights':{'H1':1,'H2':0}},
            'nci':{'annual_amount':4,'payment_weights':{'H1':1,'H2':0}}}}
        s=build_periodic_spec(data,1);rows={r['id']:r for r in s['rows']}
        # Isolate the compiled diagnostic using explicit statement-profit
        # fixture values. This is not a separate integrated-company validation.
        for rid,amounts in [('parent_profit',(40,160)),('nci_profit',(10,30))]:
            for half,amount in zip(('H1','H2'),amounts):
                rows[rid]['cells']['2026-'+half]=dict(value=amount,status='forecast',editable=False)
        v=calculate_periodic(s)
        self.assertEqual(v['parent_profit']['2026-FY'],200)
        self.assertEqual(v['nci_profit']['2026-FY'],40)
        self.assertAlmostEqual(v['dividend_payout']['2026-FY'],.2)
        self.assertAlmostEqual(v['nci_dividend_payout']['2026-FY'],.1)
        for rid in ('dividend_payout','nci_dividend_payout'):
            weighted=sum(v[rid]['2026-'+h]*v['period_year_fraction']['2026-'+h] for h in ('H1','H2'))
            self.assertNotAlmostEqual(v[rid]['2026-FY'],weighted)
            self.assertFalse(rows[rid]['cells']['2026-FY']['editable'])
            original=next(r for r in self.spec['rows'] if r['id']==rid)
            self.assertEqual(rows[rid]['cells']['2025-FY'],original['cells']['2025-FY'])

    def test_translated_working_capital_has_no_operating_cash_movement(self):
        pid='2026-H1';v=self.values
        changed=self.run_case({'inventories_translation_movement':{pid:20}})
        self.assertAlmostEqual(changed['inventories'][pid]-v['inventories'][pid],20)
        self.assertAlmostEqual(changed['cfo'][pid],v['cfo'][pid])
        self.assertAlmostEqual(changed['oci_translation'][pid]-v['oci_translation'][pid],20)
        self.assertAlmostEqual(changed['cash_fx'][pid],v['cash_fx'][pid])
        self.assertAlmostEqual(changed['balance_check'][pid],0)

    def test_cash_fx_does_not_feed_oci_reserves(self):
        from research_platform.integrated import validate_financial_contracts
        pid='2026-H1';v=self.values
        changed=self.run_case({'cash_fx_assumption':{pid:7}})
        self.assertAlmostEqual(changed['reserves'][pid],v['reserves'][pid])
        self.assertAlmostEqual(changed['closing_cash'][pid]-v['closing_cash'][pid],7)
        self.assertTrue(any(c['status']=='FAIL' and c['name']=='cash_fx_attribution:'+pid for c in validate_financial_contracts(self.spec,changed)))

    def test_scope_effect_annualises_once_in_correct_region(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='test_disposal',entity_id='north',
            type='disposal',effective_date='2026-01-01',enabled=True,accounting_enabled=False,annual_revenue=-20,
            annual_cash_costs={'cogs':-10,'distribution':-2,'marketing_admin':-3,'research':-1},source_refs=[{'source_id':'synthetic_disposal'}])]}
        v=calculate_periodic(build_periodic_spec(data,5))
        self.assertEqual(v['north_scope_effect']['2026-H1'],0)
        self.assertAlmostEqual(v['north_scope_effect']['2026-H2'],-20*181/365)
        self.assertAlmostEqual(v['north_scope_effect']['2027-H1'],-20*184/365)
        self.assertAlmostEqual(v['north_scope_effect']['2027-H2'],0)
        self.assertAlmostEqual(v['north_scope_effect']['2029-FY'],0)
        self.assertAlmostEqual(v['specialty_sales']['2026-H2'],self.values['specialty_sales']['2026-H2'])

    def test_all_annual_only_years_keep_financial_contracts_and_reconcile(self):
        from research_platform.periods import validate_periodic
        self.assertEqual([p['kind'] for p in self.spec['periods'] if p['fiscal_year']==2029],['FY'])
        failures=[c for c in validate_periodic(self.spec,self.values) if c['status'] in ('FAIL','MISSING')]
        self.assertEqual(failures,[])
        self.assertIsNotNone(self.values['north_pool_cogs']['2029-FY'])
        self.assertAlmostEqual(self.values['balance_check']['2029-FY'],0)

    def test_explicit_scope_cash_and_assets_reconcile_without_reserve_plug(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic,validate_periodic
        data=copy.deepcopy(self.data)
        # A supported disposal removes five of goodwill for six of cash and a
        # one-unit accounting gain; no operating revenue run-rate changes here.
        # Fixture does not have the optional disposal CF role, so use a sourced
        # explicit investing line, keeping the production role schema generic.
        data['historical']['business_disposals_cf']=dict(values={'2024':0,'2025':0},sources={'2024':[],'2025':[]})
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='sold_unit',entity_id='north',
            type='disposal',effective_date='2026-01-01',enabled=True,accounting_enabled=True,annual_revenue=0,
            annual_cash_costs={},cash_flows={'business_disposals_cf':6},balance_movements={'goodwill':-5},gain_loss=1,
            source_refs=[{'source_id':'synthetic_transaction_note'}])]}
        s=build_periodic_spec(data,5);v=calculate_periodic(s)
        self.assertEqual(v['business_disposals_cf']['2026-H2'],6)
        self.assertAlmostEqual(v['goodwill']['2026-FY'],15)
        self.assertAlmostEqual(v['balance_check']['2026-FY'],0)
        self.assertFalse([c for c in validate_periodic(s,v) if c['status'] in ('FAIL','MISSING')])

    def test_issued_shares_have_cash_equity_and_time_weighting(self):
        pid='2026-H1';v=self.values
        changed=self.run_case({'issuance_shares':{pid:2},'issuance_price':{pid:10},'issuance_elapsed_fraction':{pid:.75}})
        self.assertAlmostEqual(changed['shares_end_outstanding'][pid]-v['shares_end_outstanding'][pid],2)
        self.assertAlmostEqual(changed['shares_basic'][pid]-v['shares_basic'][pid],.5)
        self.assertAlmostEqual(changed['closing_cash'][pid]-v['closing_cash'][pid],20)
        self.assertAlmostEqual(changed['share_capital'][pid]-v['share_capital'][pid],20)
        self.assertAlmostEqual(changed['balance_check'][pid],0)

    def test_statement_frequency_contract_overrides_quarterly_sales_default(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic,validate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration'].update(forecast_frequency='quarterly',full_statement_frequency='half_year',primary_sales_frequency='quarterly')
        spec=build_periodic_spec(data,5);v=calculate_periodic(spec)
        self.assertIsNone(v['north_pool_cogs']['2026-Q4'])
        self.assertIsNotNone(v['north_pool_cogs']['2026-H2'])
        self.assertIsNotNone(v['north_sales']['2026-Q4'])
        self.assertFalse([c for c in validate_periodic(spec,v) if c['status'] in ('FAIL','MISSING')])

    def test_annual_cost_fx_uses_cost_money_not_equal_half_year_weights(self):
        v=self.run_case({'north_pool_cogs_translation_fx':{'2026-H1':.1,'2026-H2':.2}})
        numerator=v['north_cost_fx_amount']['2026-H1']+v['north_cost_fx_amount']['2026-H2']
        denominator=v['north_cost_fx_base']['2026-H1']+v['north_cost_fx_base']['2026-H2']
        self.assertAlmostEqual(v['north_cost_fx']['2026-FY'],numerator/denominator)
        self.assertNotAlmostEqual(v['north_cost_fx']['2026-FY'],
            (v['north_cost_fx']['2026-H1']+v['north_cost_fx']['2026-H2'])/2)
        # Translation changes the reported inventory amount only through an
        # explicit closing-rate exposure, not the operating cash target.
        self.assertAlmostEqual(v['wc_inventory_cf']['2026-H1'],self.values['wc_inventory_cf']['2026-H1'])

    def test_scope_da_reduces_only_affected_segment_and_asset_depreciation(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='depreciable_disposal',entity_id='north',
            type='disposal',effective_date='2026-01-01',enabled=True,accounting_enabled=False,annual_revenue=0,
            annual_cash_costs={},annual_da=-2,annual_da_by_role={'owned_ppe_depreciation':-2},source_refs=[{'source_id':'synthetic_scope'}])]}
        v=calculate_periodic(build_periodic_spec(data,5));expected=-2*181/365
        self.assertAlmostEqual(v['north_da']['2026-H2']-self.values['north_da']['2026-H2'],expected)
        self.assertAlmostEqual(v['specialty_da']['2026-H2'],self.values['specialty_da']['2026-H2'])
        self.assertAlmostEqual(v['owned_ppe']['2026-FY']-self.values['owned_ppe']['2026-FY'],-expected)
        self.assertAlmostEqual(v['balance_check']['2026-FY'],0)

    def test_whole_entity_disposal_has_no_negative_cost_or_residual_business(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic,validate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='whole_business',entity_id='north',
            type='disposal',effective_date='2027-01-01',enabled=True,accounting_enabled=False,entity_scope_fraction=1,
            annual_revenue=-100,annual_cash_costs={'cogs':-60,'distribution':-10,'marketing_admin':-30,'research':-5},
            annual_da=-5,da_already_in_baseline=True,source_refs=[{'source_id':'synthetic_scope'}])]}
        s=build_periodic_spec(data,5);v=calculate_periodic(s)
        for pid in ('2027-H2','2028-H1','2028-H2','2029-FY','2030-FY'):
            for role in ('north_sales','north_cash_cost','north_da','north_utop'):
                self.assertAlmostEqual(v[role][pid],0,msg=role+':'+pid)
        self.assertFalse([c for c in validate_periodic(s,v) if c['status'] in ('FAIL','MISSING')])

    def test_held_for_sale_stop_reallocates_da_before_control_is_lost(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic,validate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='held_unit',entity_id='north',
            type='disposal',effective_date='2027-01-01',enabled=True,accounting_enabled=False,entity_scope_fraction=1,
            depreciation_stop_date='2025-10-01',da_already_in_baseline=True,annual_revenue=-100,annual_cash_costs={},
            source_refs=[{'source_id':'synthetic_held_for_sale_note'}])]}
        s=build_periodic_spec(data,5);v=calculate_periodic(s)
        # July-December has184days; depreciation stops after92days. Initial
        # allocation weights are north.5, specialty.3, corporate.2, so the
        # remaining north weight is .25/.75 = one third of unchanged group D&A.
        self.assertAlmostEqual(v['north_da']['2026-H1'],v['da']['2026-H1']/3)
        self.assertAlmostEqual(v['north_da']['2026-H2'],0)
        self.assertAlmostEqual(v['north_utop']['2026-H2']-self.values['north_utop']['2026-H2'],self.values['north_da']['2026-H2'])
        for pid in ('2026-H1','2026-H2','2027-H1'):
            self.assertAlmostEqual(v['da'][pid],self.values['da'][pid])
            self.assertAlmostEqual(sum(v[r][pid] for r in ('north_da','specialty_da','corporate_da')),v['da'][pid])
        self.assertEqual(v['north_da']['2025-FY'],self.values['north_da']['2025-FY'])
        self.assertFalse([c for c in validate_periodic(s,v) if c['status'] in ('FAIL','MISSING')])

    def test_disposed_receivables_leave_cash_bridge_without_double_closing_reduction(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic,validate_periodic
        data=copy.deepcopy(self.data)
        # Selling50annual revenue with receivables of25/180 of sales transfers
        # exactly125/18 receivables. It is sold at book value for the same cash.
        transferred=125/18
        data['historical']['business_disposals_cf']=dict(values={'2024':0,'2025':0},sources={'2024':[],'2025':[]})
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='sold_receivables',entity_id='north',
            type='disposal',effective_date='2026-01-01',enabled=True,accounting_enabled=True,annual_revenue=-50,
            annual_cash_costs={},cash_flows={'business_disposals_cf':transferred},balance_movements={'receivables':-transferred},
            gain_loss=0,source_refs=[{'source_id':'synthetic_receivables_sale'}])]}
        controls={e+'_'+driver:{'2026-H1':0,'2026-H2':0} for e in ('north','specialty') for driver in ('pricing','rig')}
        baseline=calculate_periodic(self.spec,controls)
        s=build_periodic_spec(data,1);v=calculate_periodic(s,controls)
        self.assertAlmostEqual(v['receivables']['2026-FY']-baseline['receivables']['2026-FY'],-transferred)
        self.assertAlmostEqual(v['wc_receivables_cf']['2026-H2'],baseline['wc_receivables_cf']['2026-H2'])
        self.assertAlmostEqual(v['business_disposals_cf']['2026-H2'],transferred)
        self.assertAlmostEqual(v['balance_check']['2026-FY'],0)
        self.assertFalse([c for c in validate_periodic(s,v) if c['status'] in ('FAIL','MISSING')])

    def test_partial_period_full_exit_does_not_weight_scope_da_twice(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='mid_half_exit',entity_id='north',
            type='disposal',effective_date='2025-10-01',enabled=True,accounting_enabled=False,entity_scope_fraction=1,
            annual_revenue=-100,annual_cash_costs={},annual_da=-5.35,annual_da_by_role={'owned_ppe_depreciation':-5.35},
            source_refs=[{'source_id':'synthetic_timed_depreciation'}])]}
        v=calculate_periodic(build_periodic_spec(data,1))
        # Opening assets imply annual group D&A10.7; north is half the original
        # allocation and operates92of184days. Its remaining expense is1.348493,
        # not another half-weighting of the already dated1.348493 removal.
        self.assertAlmostEqual(v['group_scope_da']['2026-H1'],-5.35*92/365)
        self.assertAlmostEqual(v['da']['2026-H1'],10.7*138/365)
        self.assertAlmostEqual(v['north_da']['2026-H1'],5.35*92/365)
        self.assertAlmostEqual(v['specialty_da']['2026-H1'],10.7*.3*184/365)
        self.assertAlmostEqual(v['corporate_da']['2026-H1'],10.7*.2*184/365)

    def test_no_remaining_da_recipient_is_explicitly_incomplete(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic,validate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='exit_'+e,entity_id=e,
            type='disposal',effective_date='2027-01-01',depreciation_stop_date='2025-07-01',enabled=True,accounting_enabled=False,entity_scope_fraction=1,
            annual_revenue=0,annual_cash_costs={},source_refs=[{'source_id':'synthetic_all_operations_exit'}])
            for e in ('north','specialty','corporate')]}
        s=build_periodic_spec(data,1);v=calculate_periodic(s)
        self.assertEqual(v['active_da_allocation_total']['2026-H1'],0)
        self.assertGreater(v['da']['2026-H1'],0)
        self.assertEqual(v['north_da']['2026-H1'],0)
        self.assertTrue(any(c['name']=='depreciation_allocation:2026-H1' and c['status']=='FAIL' for c in validate_periodic(s,v)))

    def test_da_allocation_conditional_fits_excel_formula_limit(self):
        from research_platform.periods import cell_formula_excel
        rows={r['id']:r for r in self.spec['rows']}
        positions={rid:i+100000 for i,rid in enumerate(rows)}
        for rid in ('remaining_da_per_allocation_weight','north_da','specialty_da','corporate_da'):
            formula=cell_formula_excel(rows[rid]['cells']['2026-H1'],'2026-H1',
                lambda row,period:"'Assumptions'!ZZZ"+str(positions[row]))
            self.assertLessEqual(len(formula),8192)

    def test_mixed_actual_year_does_not_invent_historical_fx_attribution(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic,validate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['actual_through']='2025-12-31'
        data['historical']['shares_end_outstanding']=copy.deepcopy(data['historical']['shares_basic'])
        # Repeated synthetic financials are explicit source observations for the
        # completed first half, with no disclosed cost-FX or repurchase counts.
        additions=[]
        for original in data['observations']:
            if original['period_id']!='2025-H1':continue
            item=copy.deepcopy(original);item.update(id='next_'+item['id'],period_id='2026-H1',fiscal_year=2026,start='2025-07-01',end='2025-12-31')
            additions.append(item)
            if item['row_id']=='shares_basic':
                additions.append(dict(copy.deepcopy(item),id='closing_'+item['id'],row_id='shares_end_outstanding',metric='shares_end_outstanding',
                    metric_type='stock',definition='Explicit synthetic closing shares',definition_id='shares_end_outstanding',measurement_date='2025-12-31'))
        data['observations'].extend(additions)
        spec=build_periodic_spec(data,5);v=calculate_periodic(spec)
        rows={r['id']:r for r in spec['rows']}
        self.assertIsNone(v['north_pool_cogs_translation_amount']['2026-H1'])
        self.assertIsNone(v['north_pool_cogs_translation_amount']['2026-FY'])
        summary=rows['north_pool_cogs_translation_amount']['cells']['2026-FY']
        self.assertFalse(summary['required'])
        self.assertEqual(summary['unavailable_historical_components'],[dict(row_id='north_pool_cogs_translation_amount',period_id='2026-H1')])
        self.assertTrue(rows['north_pool_cogs_translation_amount']['cells']['2027-FY']['required'])
        self.assertTrue(rows['north_pool_cogs']['cells']['2026-H2']['required'])
        self.assertIsNotNone(v['cfo']['2026-FY'])
        missing=[c for c in validate_periodic(spec,v) if c['status']=='MISSING']
        self.assertEqual(missing,[])

    def test_presentation_allocations_are_read_only_diagnostics_not_profit_drivers(self):
        from research_platform.periods import calculate_periodic
        rows={r['id']:r for r in self.spec['rows']}
        contracts={c['id']:c for c in self.spec['financial_contracts']['drivers']}
        pid='2026-H1';before=self.values['operating_profit'][pid]
        for destination in ('cogs','distribution','marketing_admin','research'):
            rid=destination+'_allocation'
            with self.subTest(allocation=rid):
                self.assertEqual(rows[rid]['kind'],'calculated')
                self.assertFalse(rows[rid]['cells'][pid]['editable'])
                self.assertEqual(contracts[rid]['parameter_role'],'presentation_parameter')
                self.assertEqual(contracts[rid]['expected_downstream_outputs'],[])
                self.assertAlmostEqual(self.values[rid][pid],
                    -self.values[destination][pid]/(self.values['total_revenue'][pid]-self.values['utop'][pid]))
                with self.assertRaisesRegex(ValueError,'Only authoritative editable inputs'):
                    calculate_periodic(self.spec,{rid:{pid:self.values[rid][pid]+.1}})
        self.assertAlmostEqual(calculate_periodic(self.spec)['operating_profit'][pid],before)

    def test_normalisation_separates_recurring_adjustments_from_operating_performance(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'normalisation':{
            'net_other_trading':{'annual_amount':-10,'reason':'Explicit synthetic recurring restructuring budget'},
            'net_other_operating':{'annual_amount':-4,'reason':'Explicit synthetic recurring operating adjustment'}}}
        spec=build_periodic_spec(data,5);v=calculate_periodic(spec);pid='2026-H1'
        # The June fiscal calendar puts 184 of 365 days in this first half.
        expected_adjustment=-14*184/365
        self.assertAlmostEqual(v['operating_profit'][pid]-v['utop'][pid],expected_adjustment)
        self.assertAlmostEqual(v['normalisation_profit_change'][pid],expected_adjustment)
        self.assertAlmostEqual(v['underlying_operating_profit_change'][pid],self.values['underlying_operating_profit_change'][pid])
        self.assertAlmostEqual(v['statutory_operating_profit_change'][pid],
            v['underlying_operating_profit_change'][pid]+expected_adjustment)
        # Recurring expenditure persists into subsequent years rather than
        # silently vanishing in the normalised forecast.
        self.assertAlmostEqual(v['net_other_trading']['2027-FY'],-10)
        self.assertAlmostEqual(v['net_other_operating']['2027-FY'],-4)
        changed=calculate_periodic(spec,{'net_other_trading_assumption':{pid:v['net_other_trading_assumption'][pid]-5}})
        self.assertAlmostEqual(changed['utop'][pid],v['utop'][pid])
        self.assertAlmostEqual(changed['operating_profit'][pid]-v['operating_profit'][pid],-5)
        self.assertAlmostEqual(changed['normalisation_profit_change'][pid]-v['normalisation_profit_change'][pid],-5)
        self.assertAlmostEqual(changed['statutory_operating_profit_change'][pid]-v['statutory_operating_profit_change'][pid],-5)

    def test_annual_transition_carries_previous_modelled_sales_and_functional_costs(self):
        from research_platform.periods import calculate_periodic
        rows={r['id']:r for r in self.spec['rows']};v=self.values
        # This June year-end fixture retains detailed FY2028 then switches to FY
        # only. A changed spending budget in its last half must survive transition.
        changed=calculate_periodic(self.spec,{'north_pool_marketing_admin_budget_change':{'2028-H2':20}})
        self.assertEqual(rows['north_sales_seed']['cells']['2029-FY']['bindings']['observed'],
                         dict(row_id='north_sales',period_id='2028-FY'))
        self.assertEqual(rows['north_pool_cogs_seed']['cells']['2029-FY']['bindings']['prior'],
                         dict(row_id='north_pool_cogs',period_id='2028-FY'))
        self.assertAlmostEqual(v['north_sales_seed']['2029-FY'],v['north_sales']['2028-FY'])
        self.assertAlmostEqual(v['north_sales']['2029-FY'],v['north_sales']['2028-FY']*1.03)
        self.assertAlmostEqual(v['north_pool_cogs_seed']['2029-FY'],v['north_pool_cogs']['2028-FY'])
        self.assertAlmostEqual(v['north_pool_cogs']['2029-FY'],v['north_pool_cogs']['2028-FY']*1.01)
        self.assertAlmostEqual(changed['north_pool_marketing_admin']['2029-FY'],changed['north_pool_marketing_admin']['2028-FY'])
        self.assertAlmostEqual(changed['north_pool_marketing_admin']['2029-FY']-v['north_pool_marketing_admin']['2029-FY'],20)

    def test_exit_scope_at_annual_transition_uses_partial_previous_year_not_original_history(self):
        from research_platform.integrated import build_periodic_spec
        from research_platform.periods import calculate_periodic,validate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='exit_at_midyear',entity_id='north',
            type='disposal',effective_date='2028-01-01',enabled=True,accounting_enabled=False,entity_scope_fraction=1,
            annual_revenue=-100,annual_cash_costs={},annual_da=-5,da_already_in_baseline=True,
            source_refs=[{'source_id':'synthetic_scope'}])]}
        s=build_periodic_spec(data,5);v=calculate_periodic(s)
        previous=v['north_sales']['2028-H1']
        self.assertAlmostEqual(v['north_sales']['2028-H2'],0)
        self.assertAlmostEqual(v['north_sales']['2028-FY'],previous)
        self.assertAlmostEqual(v['north_sales_seed']['2029-FY'],previous)
        self.assertAlmostEqual(v['north_scope_effect']['2029-FY'],-previous)
        self.assertAlmostEqual(v['north_scope_growth']['2029-FY'],-1)
        self.assertAlmostEqual(v['north_sales']['2029-FY'],0)
        self.assertAlmostEqual(v['north_scope_effect']['2030-FY'],0)
        self.assertFalse([c for c in validate_periodic(s,v) if c['status'] in ('FAIL','MISSING')])


if __name__ == "__main__":
    unittest.main()
