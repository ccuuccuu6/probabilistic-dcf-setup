"""Independent numerical examples for a segment-driven integrated annual graph."""
import copy
import unittest

from company_initiation.forecast_construction.construction import calculate_integrated, validate_integrated


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


class CompanyPresentationContractTests(unittest.TestCase):
    """Synthetic source presentations exercise shared cash and expense policies."""
    def data(self):
        from tests.test_periodic_model import different_period_company
        return different_period_company()

    def cash_data(self):
        data=self.data();refs=[dict(source_id='synthetic_cash_note',unit_id='cash_scope')]
        data['model_configuration']['cash_scope']=dict(method='Reported CF cash includes HFS cash and nets overdrafts already within current debt.',source_refs=refs,
            components=[dict(id='hfs',role='held_for_sale_cash',coefficient=1,included_in_debt=False,definition='Cash in held-for-sale assets',source_refs=refs),
                        dict(id='overdraft',role='bank_overdrafts',coefficient=-1,included_in_debt=True,definition='Current bank overdrafts',source_refs=refs)])
        data['historical']['bank_overdrafts']=dict(values={'2024':4.,'2025':4.},sources={'2024':refs,'2025':refs},basis='synthetic_group_basis')
        for role in ('opening_cash','closing_cash'):
            for year in data['historical'][role]['values']:data['historical'][role]['values'][year]-=4
        extra=[]
        for observation in data['observations']:
            if observation['row_id'] in ('opening_cash','closing_cash'):
                observation['value']-=4;observation['source_refs'][0]['raw']-=4
            if observation['row_id']=='held_for_sale_cash':
                item=copy.deepcopy(observation)
                item.update(id=item['id']+'_overdraft',row_id='bank_overdrafts',metric='bank_overdrafts',definition_id='bank_overdrafts',definition='Current bank overdrafts',value=4.,source_refs=refs)
                extra.append(item)
        data['observations'].extend(extra)
        return data

    def test_overdraft_scope_preserves_net_cf_and_counts_gross_cash_and_debt_once(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
        data=self.cash_data();before=copy.deepcopy(data);spec=build_periodic_spec(data,2);values=calculate_periodic(spec)
        self.assertEqual(data,before)
        self.assertEqual(values['cash']['2025-FY'],29.5)
        self.assertEqual(values['closing_cash']['2025-FY'],27.5)
        self.assertEqual(values['valuation_cash']['2025-FY'],31.5)
        changed=calculate_periodic(spec,{'bank_overdrafts':{'2026-H1':7.,'2026-FY':7.}})
        for rid in ('cash','nonlease_debt','total_debt','short_debt','valuation_cash'):
            self.assertAlmostEqual(changed[rid]['2026-H1']-values[rid]['2026-H1'],3.,msg=rid)
        for rid in ('cfo','cff','cash_change','closing_cash','long_debt','debt_interest'):
            self.assertAlmostEqual(changed[rid]['2026-H1'],values[rid]['2026-H1'],msg=rid)
        self.assertAlmostEqual(changed['cash_scope_debt_change']['2026-FY'],3.)
        self.assertAlmostEqual(changed['valuation_cash_change']['2026-H1']-values['valuation_cash_change']['2026-H1'],3.)
        self.assertFalse([c for c in validate_periodic(spec,changed) if c['status'] in ('FAIL','MISSING')])

    def test_additional_cited_recurring_function_has_its_own_budget_and_profit_effect(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
        data=self.data();refs=[dict(source_id='synthetic_function_note',unit_id='expense_functions')]
        role='other_recurring_costs'
        data['model_configuration']['operating_expense_functions']=[dict(id=role,label='Other recurring operating costs',definition='Separately reported recurring costs within segment operating profit',source_refs=refs)]
        data['historical'][role]=dict(values={'2024':-5.,'2025':-5.},sources={'2024':refs,'2025':refs},basis='synthetic_group_basis')
        for year in data['historical']['marketing_admin']['values']:data['historical']['marketing_admin']['values'][year]+=5.
        extra=[]
        for observation in data['observations']:
            if observation['row_id']!='marketing_admin':continue
            ratio=observation['value']/-35.;observation['value']+=5*ratio;observation['source_refs'][0]['raw']=observation['value']
            item=copy.deepcopy(observation);item.update(id=item['id']+'_other',row_id=role,metric=role,definition_id=role,definition='Other recurring operating costs',value=-5*ratio,source_refs=refs);extra.append(item)
        data['observations'].extend(extra)
        spec=build_periodic_spec(data,2);values=calculate_periodic(spec)
        self.assertAlmostEqual(values[role]['2025-FY'],-5.)
        self.assertAlmostEqual(values['is_utop']['2026-FY'],values['utop']['2026-FY'])
        changed=calculate_periodic(spec,{'north_pool_'+role+'_budget_change':{'2026-H1':10.}})
        self.assertAlmostEqual(changed['operating_profit']['2026-H1']-values['operating_profit']['2026-H1'],-10.)
        self.assertAlmostEqual(changed[role]['2026-H1']-values[role]['2026-H1'],-10.)
        self.assertAlmostEqual(changed['cfo']['2026-H1']-values['cfo']['2026-H1'],-10*(1-.2*(5/5.4)))
        self.assertFalse([c for c in validate_periodic(spec,changed) if c['status'] in ('FAIL','MISSING')])

    def test_explicit_cash_scope_without_hfs_does_not_require_an_invented_hfs_fact(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
        data=self.cash_data();data['model_configuration']['cash_scope']['components']=data['model_configuration']['cash_scope']['components'][1:]
        data['historical'].pop('held_for_sale_cash')
        data['observations']=[o for o in data['observations'] if o['row_id']!='held_for_sale_cash']
        for role in ('opening_cash','closing_cash'):
            for year in data['historical'][role]['values']:data['historical'][role]['values'][year]-=2
        for o in data['observations']:
            if o['row_id'] in ('opening_cash','closing_cash'):o['value']-=2;o['source_refs'][0]['raw']-=2
        spec=build_periodic_spec(data,1);values=calculate_periodic(spec);rows={r['id']:r for r in spec['rows']}
        self.assertEqual(values['closing_cash']['2025-FY'],25.5)
        self.assertEqual(values['valuation_cash']['2025-FY'],29.5)
        self.assertEqual(rows['held_for_sale_cash']['cells']['2025-FY']['data_role'],'structural_parameter')
        self.assertFalse(rows['held_for_sale_cash_input']['cells']['2026-H1']['editable'])
        self.assertFalse([c for c in validate_periodic(spec,values) if c['status'] in ('FAIL','MISSING')])

    def test_replacement_cash_scope_preserves_separately_disclosed_hfs_cash(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
        data=self.cash_data()
        data['model_configuration']['cash_scope']['components']=data['model_configuration']['cash_scope']['components'][1:]
        data['model_configuration']['cash_scope']['method']='CF cash nets current overdrafts and excludes the separately disclosed HFS cash.'
        for role in ('opening_cash','closing_cash'):
            for year in data['historical'][role]['values']:data['historical'][role]['values'][year]-=2
        for observation in data['observations']:
            if observation['row_id'] in ('opening_cash','closing_cash'):
                observation['value']-=2;observation['source_refs'][0]['raw']-=2
        before=copy.deepcopy(data)
        expected=next(o for o in data['observations'] if o['row_id']=='held_for_sale_cash' and o['period_id']=='2025-FY')
        spec=build_periodic_spec(data,1);values=calculate_periodic(spec);rows={r['id']:r for r in spec['rows']}
        self.assertEqual(data,before)
        self.assertEqual(values['held_for_sale_cash']['2025-FY'],2.)
        actual=rows['held_for_sale_cash']['cells']['2025-FY']
        self.assertEqual(actual['status'],'actual')
        self.assertEqual(actual['source_refs'],expected['source_refs'])
        self.assertNotEqual(actual.get('data_role'),'structural_parameter')
        self.assertEqual(values['held_for_sale_cash_input']['2026-H1'],2.)
        self.assertFalse(rows['held_for_sale_cash_input']['cells']['2026-H1']['editable'])
        self.assertEqual(values['closing_cash']['2025-FY'],25.5)
        self.assertEqual(values['valuation_cash']['2025-FY'],29.5)
        self.assertFalse([c for c in validate_periodic(spec,values) if c['status'] in ('FAIL','MISSING')])

    def test_direct_nonzero_net_amount_retains_sign_and_forecast_initialization(self):
        from tests.test_integrated_model import second_company
        from company_initiation.forecast_construction.integrated import build_integrated_spec
        data=second_company();refs=[dict(source_id='synthetic_net_statement')]
        data['historical'].pop('other_operating_income');data['historical'].pop('other_operating_expense')
        data['historical']['net_other_operating']=dict(values={'2024':-2.,'2025':-3.},sources={'2024':refs,'2025':refs},basis='synthetic_net_presentation')
        # This isolates the source presentation; other financial fixture facts
        # are not changed or represented as a reconciled new historical model.
        spec=build_integrated_spec(data,1);row=next(r for r in spec['rows'] if r['id']=='net_other_operating')
        self.assertEqual(row['historical'],{'2024':-2.,'2025':-3.})
        self.assertEqual(row['source_refs']['2025'],refs)
        self.assertNotIn('other_operating_income',{r['id'] for r in spec['rows']})

    def test_direct_net_and_cited_inactive_presentation_do_not_invent_gross_facts(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic, assumption_contract
        data=self.data();refs=[dict(source_id='synthetic_presentation_note',unit_id='net_accounts')]
        for role in ('other_trading_income','other_trading_expense','other_operating_income','other_operating_expense','other_revenue'):
            data['historical'].pop(role,None)
        data['observations']=[o for o in data['observations'] if o['row_id'] not in ('other_trading_income','other_trading_expense','other_operating_income','other_operating_expense','other_revenue')]
        data['historical']['net_other_operating']=dict(values={'2024':0.,'2025':0.},sources={'2024':refs,'2025':refs},basis='synthetic_group_basis')
        data['model_configuration']['structural_account_policies']=[
            dict(role='other_revenue',treatment='included_in_role',included_in=['sales'],definition='The reported sales line contains all operating revenue.',source_refs=refs),
            dict(role='net_other_trading',treatment='inactive_stage',included_in=[],definition='The company presents one adjustment stage, in net_other_operating.',source_refs=refs)]
        original=copy.deepcopy(data);spec=build_periodic_spec(data,1);values=calculate_periodic(spec);rows={r['id']:r for r in spec['rows']}
        self.assertEqual(data,original)
        self.assertNotIn('other_operating_income',rows)
        self.assertEqual(values['net_other_operating']['2025-FY'],0.)
        self.assertEqual(values['other_revenue']['2026-H1'],0.)
        contract=assumption_contract(spec)
        self.assertEqual(contract['classifications']['other_revenue_ratio']['2026-H1'],'structural_parameter')
        self.assertFalse(rows['other_revenue']['cells']['2025-FY']['calibration_eligible'])
        self.assertFalse([c for c in validate_periodic(spec,values) if c['status'] in ('FAIL','MISSING')])

    def test_unproven_or_contradictory_presentation_policies_are_rejected(self):
        from company_initiation.forecast_construction.integrated import functional_structure_inputs, operating_expense_functions, cash_scope_policy
        data=self.cash_data();data['model_configuration']['cash_scope']['components'][1]['coefficient']=1
        with self.assertRaisesRegex(ValueError,'deducted'):cash_scope_policy(data)
        data=self.data();data['model_configuration']['operating_expense_functions']=[dict(id='cash',label='Not an expense',definition='Invalid',source_refs=['fixture'])]
        with self.assertRaisesRegex(ValueError,'collides'):operating_expense_functions(data)
        data=self.data();data['historical']['other_revenue']['values']['2025']=1.
        data['model_configuration']['structural_account_policies']=[dict(role='other_revenue',treatment='included_in_role',included_in=['sales'],definition='All revenue in sales',source_refs=['fixture'])]
        with self.assertRaisesRegex(ValueError,'nonzero'):functional_structure_inputs(data)

    def presentation_data(self):
        data=self.data();refs=[dict(source_id='synthetic_capital_note',unit_id='capital_and_cash')]
        def component(role,kind,equity=None,asset=None,policy='no_new_transaction'):
            return dict(role=role,label=role.replace('_',' '),cashflow_section='cff',classification=kind,
                equity_role=equity,asset_role=asset,forecast_policy=policy,
                definition='Synthetic signed source cash movement with a separate stock counterpart.',source_refs=refs)
        data['model_configuration']['cashflow_presentation']=dict(method='Explicit synthetic financing statement',source_refs=refs,
            noncommon_equity_claim_role='preferred_equity_claim',components=[
                component('issuance_cash','ordinary_equity_issuance','share_capital',policy='existing_issuance_controls'),
                component('preferred_issuance_cash','noncommon_equity_issuance','retained_earnings'),
                component('preferred_distribution_cash','noncommon_equity_distribution','retained_earnings',policy='hold_latest_annual'),
                component('investment_cash','investment_movement',asset='short_investments')])
        data['model_configuration']['financial_contracts']=dict(adjusted_earnings=dict(basic_earnings_adjustment=dict(
            annual_amount=-3.,amounts_by_period={},historical={},source_refs=refs,
            method='Synthetic after-tax accrued preference return; independently specified from cash paid.')))
        additions=dict(issuance_cash=3.,preferred_issuance_cash=10.,preferred_distribution_cash=-2.,investment_cash=1.,preferred_equity_claim=10.)
        for role,amount in additions.items():
            data['historical'][role]=dict(values={str(y):amount for y in data['history_years']},
                sources={str(y):refs for y in data['history_years']},basis='synthetic_group_basis')
        delta=dict(cff=12.,cash_change=12.,closing_cash=12.,cash=12.,short_investments=-1.,
            current_assets=11.,total_assets=11.,share_capital=3.,retained_earnings=8.,parent_equity=11.,
            total_equity=11.,liabilities_equity=11.)
        for role,amount in delta.items():
            for year in data['historical'][role]['values']:
                data['historical'][role]['values'][year]+=amount
        weights=dict(Q1=.15,Q2=.4,H1=.4,Q3=.6,**{'9M':.6},Q4=1.,H2=1.,FY=1.)
        extra=[]
        for observation in data['observations']:
            if observation['row_id'] in delta:
                observation['value']+=delta[observation['row_id']]*weights[observation['kind']]
                observation['source_refs'][0]['raw']=observation['value']
            for role,amount in additions.items():
                template='held_for_sale_cash' if role=='preferred_equity_claim' else 'dividends_parent'
                if observation['row_id']!=template:continue
                item=copy.deepcopy(observation)
                item.update(id=role+'_'+observation['period_id'],row_id=role,metric=role,definition_id=role,
                    definition='Synthetic '+role,source_refs=refs,
                    value=amount if role=='preferred_equity_claim' else amount*weights[observation['kind']])
                extra.append(item)
        data['observations'].extend(extra)
        return data

    def test_cash_components_keep_equity_debt_investments_and_eps_distinct(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
        data=self.presentation_data();before=copy.deepcopy(data)
        spec=build_periodic_spec(data,1);values=calculate_periodic(spec);pid='2026-H1'
        self.assertEqual(data,before)
        self.assertEqual(values['cff']['2025-FY'],.5)
        self.assertEqual(values['issuance_cash']['2025-FY'],3.)
        self.assertEqual(values['preferred_equity_claim']['2025-FY'],10.)
        fraction=184/365
        self.assertAlmostEqual(values['preferred_distribution_cash'][pid],-2*fraction)
        self.assertAlmostEqual(values['basic_eps_numerator'][pid],values['parent_profit'][pid]-3*fraction)
        cases=[({'preferred_issuance_cash_annual_policy':{pid:7.}},
                dict(cff=7.,cash=7.,retained_earnings=7.,preferred_equity_claim=7.,total_debt=0.,parent_profit=0.,eps_basic=0.)),
               ({'investment_cash_annual_policy':{pid:-4.}},
                dict(cff=-4.,cfi=0.,cash=-4.,short_investments=4.,total_assets=0.,total_equity=0.,total_debt=0.)),
               ({'preferred_distribution_cash_annual_policy':{pid:-5.}},
                dict(cff=-5+2*fraction,cash=-5+2*fraction,retained_earnings=-5+2*fraction,
                     preferred_equity_claim=0.,parent_profit=0.,eps_basic=0.)),
               ({'issuance_shares':{pid:.5},'issuance_price':{pid:20.}},
                dict(cff=10.,cash=10.,share_capital=10.,preferred_equity_claim=0.,total_debt=0.))]
        for overrides,expected in cases:
            with self.subTest(overrides=overrides):
                changed=calculate_periodic(spec,overrides)
                for role,amount in expected.items():self.assertAlmostEqual(changed[role][pid]-values[role][pid],amount,msg=role)
                failures=[c for c in validate_periodic(spec,changed) if c['status'] in ('FAIL','MISSING')]
                self.assertFalse(failures,failures[:5])
        changed=calculate_periodic(spec,{'basic_earnings_adjustment':{pid:-4.}})
        self.assertAlmostEqual(changed['eps_basic'][pid],(values['parent_profit'][pid]-4)/values['shares_basic'][pid])
        for role in ('cash','retained_earnings','cff','parent_profit'):
            self.assertEqual(changed[role][pid],values[role][pid])

    def test_noncommon_distribution_cannot_reuse_cash_as_implicit_eps_adjustment(self):
        from company_initiation.forecast_construction.integrated import cashflow_presentation_policy
        data=self.presentation_data();data['model_configuration']['financial_contracts'].clear()
        with self.assertRaisesRegex(ValueError,'separate cited after-tax EPS'):
            cashflow_presentation_policy(data)


class CausalContractTests(unittest.TestCase):
    """Independent economic checks on a different fiscal calendar/company."""
    @classmethod
    def setUpClass(cls):
        from tests.test_periodic_model import different_period_company
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        cls.data=different_period_company();cls.spec=build_periodic_spec(cls.data,5)
        cls.values=calculate_periodic(cls.spec)

    def run_case(self,overrides):
        from company_initiation.forecast_construction.periods import calculate_periodic
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

    def test_budget_method_rejects_redundant_controls_and_marks_allocated_history(self):
        rows={r['id']:r for r in self.spec['rows']};pid='2026-H1'
        for suffix in ('activity_change','elasticity','variable_share','effective_activity_sensitivity','unit_cost_change','spending_change'):
            with self.assertRaisesRegex(ValueError,'Only authoritative editable'):
                self.run_case({'north_pool_marketing_admin_'+suffix:{pid:.1}})
        self.assertTrue(rows['north_pool_marketing_admin_budget_change']['cells'][pid]['editable'])
        for entity in ('north','specialty','corporate'):
            row=rows[entity+'_pool_cogs'];cell=row['cells']['2025-FY']
            self.assertEqual(cell['data_role'],'estimated_historical_baseline')
            self.assertFalse(cell['calibration_eligible']);self.assertFalse(row['calibration_eligible'])
        self.assertEqual(self.values['corporate_pool_cogs']['2025-FY'],0)
        self.assertAlmostEqual(sum(self.values[e+'_pool_cogs']['2025-FY'] for e in ('north','specialty','corporate')),84)

    def test_sbc_expense_addback_and_equity_do_not_manufacture_cash(self):
        controls={'effective_tax_rate_policy':{'2026-H1':0,'2026-H2':0}}
        baseline=self.run_case(controls)
        changed=self.run_case(dict(controls,sbc_annual_budget={'2026-FY':11.5}))
        for pid in ('2026-H1','2026-H2'):
            amount=10*self.values['period_year_fraction'][pid]
            self.assertAlmostEqual(changed['sbc'][pid]-baseline['sbc'][pid],amount)
            self.assertAlmostEqual(changed['operating_profit'][pid]-baseline['operating_profit'][pid],-amount)
            self.assertAlmostEqual(changed['cfo'][pid],baseline['cfo'][pid])
        self.assertAlmostEqual(changed['reserves']['2026-FY']-baseline['reserves']['2026-FY'],10)
        self.assertAlmostEqual(changed['total_equity']['2026-FY'],baseline['total_equity']['2026-FY'])

    def test_manual_financing_interest_includes_within_annual_period_timing(self):
        pid='2029-FY';v=self.values
        changed=self.run_case({'borrowing_input':{pid:100},'borrowing_elapsed_fraction':{pid:.25}})
        self.assertAlmostEqual(changed['debt_interest'][pid]-v['debt_interest'][pid],75*v['borrowing_rate'][pid])
        self.assertAlmostEqual(changed['nonlease_debt'][pid]-v['nonlease_debt'][pid],100)
        repaid=self.run_case({'repayment_input':{pid:20},'repayment_elapsed_fraction':{pid:.75}})
        self.assertAlmostEqual(repaid['debt_interest'][pid]-v['debt_interest'][pid],-5*v['borrowing_rate'][pid])

    def test_issuance_splits_legal_nominal_capital_and_premium(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);data['model_configuration']['financial_contracts']={'financing':{'issuance_nominal_price':1}}
        s=build_periodic_spec(data,1);base=calculate_periodic(s);pid='2026-H1'
        changed=calculate_periodic(s,{'issuance_shares':{pid:2},'issuance_price':{pid:10}})
        for rid,amount in [('share_capital',2),('reserves',18),('closing_cash',20),('total_equity',20)]:
            self.assertAlmostEqual(changed[rid][pid]-base[rid][pid],amount)
        self.assertAlmostEqual(changed['balance_check'][pid],0)

    def test_adjusted_eps_bridge_separates_tax_nci_and_after_tax_associates(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'adjusted_earnings':{'label':'Company adjusted','adjustments':[
            {'id':'operating','annual_amount':20,'tax_rate':.25,'nci_share':.1,'basis':'pretax'},
            {'id':'associate','annual_amount':4,'nci_share':.25,'basis':'after_tax_associate'}],
            'dilution':{'incremental_shares':1,'earnings_adjustment':2,'method':'Explicit synthetic convertible-share scenario'}}}
        v=calculate_periodic(build_periodic_spec(data,1));pid='2026-FY'
        self.assertAlmostEqual(v['adjusted_pretax'][pid]-v['pretax'][pid],20)
        self.assertAlmostEqual(v['adjusted_tax'][pid]-v['tax_expense'][pid],-5)
        self.assertAlmostEqual(v['adjusted_associate'][pid]-v['associate_profit'][pid],4)
        self.assertAlmostEqual(v['adjusted_nci'][pid]-v['nci_profit'][pid],2.5)
        self.assertAlmostEqual(v['adjusted_parent_profit'][pid]-v['parent_profit'][pid],16.5)
        self.assertAlmostEqual(v['adjusted_eps_basic'][pid]-v['eps_basic'][pid],1.65)
        self.assertAlmostEqual(v['adjusted_eps_diluted'][pid],(v['adjusted_parent_profit'][pid]+2)/11)

    def test_visible_cashflow_components_expose_noncash_portfolio_reversal(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['historical']['business_disposals_cf']=dict(values={'2024':0,'2025':0},sources={'2024':[],'2025':[]})
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='gain',entity_id='north',type='disposal',
            effective_date='2025-07-01',enabled=True,accounting_enabled=True,annual_revenue=0,annual_cash_costs={},
            gain_loss=30,balance_movements={'other_current_assets':-10},cash_flows={'business_disposals_cf':40},source_refs=[{'source_id':'synthetic_sale'}])]}
        s=build_periodic_spec(data,1);v=calculate_periodic(s);pid='2026-H1'
        self.assertAlmostEqual(v['operating_profit'][pid]-self.values['operating_profit'][pid],30)
        self.assertAlmostEqual(v['cfo_portfolio_noncash'][pid],-30)
        self.assertAlmostEqual(v['cfo'][pid]-self.values['cfo'][pid],-30*.2*5/5.4)
        for period in ('2026-H1','2026-H2','2026-FY'):
            self.assertAlmostEqual(v['cfo'][period],sum(v[r][period] for r in s['cashflow_component_contract']['cfo_components']))
        rowids=[r['id'] for r in s['rows']]
        self.assertLess(rowids.index('cfo_portfolio_noncash'),rowids.index('cfo'))

    def test_dilution_excludes_potential_shares_in_loss_and_tests_annual_independently(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);data['model_configuration']['financial_contracts']={'dilution':{'incremental_shares':2,'earnings_adjustment':0}}
        s=build_periodic_spec(data,1);positive=calculate_periodic(s)
        self.assertAlmostEqual(positive['shares_diluted']['2026-H1'],12)
        anti=calculate_periodic(s,{'diluted_earnings_adjustment':{'2026-H1':100}})
        self.assertGreater(anti['parent_profit']['2026-H1'],0)
        self.assertEqual(anti['shares_diluted']['2026-H1'],10)
        self.assertEqual(anti['eligible_diluted_earnings_adjustment']['2026-H1'],0)
        self.assertEqual(anti['eps_diluted']['2026-H1'],anti['eps_basic']['2026-H1'])
        loss=calculate_periodic(s,{'north_pool_marketing_admin_budget_change':{'2026-H1':100}})
        self.assertLess(loss['parent_profit']['2026-H1'],0)
        self.assertEqual(loss['shares_diluted']['2026-H1'],10)
        self.assertEqual(loss['eps_diluted']['2026-H1'],loss['eps_basic']['2026-H1'])
        self.assertLess(loss['parent_profit']['2026-FY'],0)
        self.assertEqual(loss['shares_diluted']['2026-FY'],10)
        self.assertEqual(loss['shares_diluted']['2026-H2'],12)
        # Annual shares cannot average the eligible10and12interim counts.
        self.assertNotEqual(loss['shares_diluted']['2026-FY'],(10*184+12*181)/365)

    def test_reported_interim_diluted_eps_is_retained_with_separate_estimated_denominator(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);data['model_configuration']['actual_through']='2025-12-31'
        for original in list(data['observations']):
            if original['period_id']!='2025-H1':continue
            item=dict(copy.deepcopy(original),id='next_'+original['id'],period_id='2026-H1',fiscal_year=2026,start='2025-07-01',end='2025-12-31')
            data['observations'].append(item)
            if item['row_id']=='eps_basic':data['observations'].append(dict(copy.deepcopy(item),id='reported_diluted_h1',row_id='eps_diluted',metric='eps_diluted',definition_id='eps_diluted',value=.73))
        data['model_configuration']['financial_contracts']={'dilution':{'incremental_shares':2,'historical':{'2025-FY':dict(incremental_shares=2,earnings_adjustment=0,source_refs=[{'source_id':'synthetic_prior_share_note'}])}}}
        s=build_periodic_spec(data,1);v=calculate_periodic(s);rows={r['id']:r for r in s['rows']}
        self.assertEqual(v['eps_diluted']['2026-H1'],.73)
        self.assertEqual(rows['eps_diluted']['cells']['2026-H1']['observation_id'],'reported_diluted_h1')
        self.assertEqual(v['shares_diluted']['2026-H1'],12)
        self.assertNotAlmostEqual(v['parent_profit']['2026-H1']/.73,12)
        self.assertFalse(rows['shares_diluted']['cells']['2026-H1']['calibration_eligible'])
        self.assertEqual(v['shares_diluted']['2026-FY'],12)
        self.assertAlmostEqual(v['eps_diluted']['2026-FY'],v['parent_profit']['2026-FY']/12)

    def test_historical_adjusted_bridge_uses_its_own_cited_period_amounts(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);refs=[{'source_id':'synthetic_company_apm','unit_id':'note:earnings'}]
        data['model_configuration']['financial_contracts']={'adjusted_earnings':{'adjustments':[],
            'historical_adjustments':[{'id':basis,'period_id':'2025-FY','basis':basis,'amount':amount,'source_refs':refs}
                for basis,amount in [('pretax',8),('tax_only',-2),('after_tax_associate',3),('nci_only',1)]],
            'dilution':{'historical':{'2025-FY':{'incremental_shares':2,'earnings_adjustment':0,'source_refs':refs}}}}}
        original=copy.deepcopy(data['observations']);s=build_periodic_spec(data,1);v=calculate_periodic(s)
        self.assertEqual(data['observations'],original)
        self.assertAlmostEqual(v['adjusted_parent_profit']['2025-FY'],30)
        self.assertAlmostEqual(v['adjusted_eps_basic']['2025-FY'],3)
        self.assertAlmostEqual(v['adjusted_eps_diluted']['2025-FY'],2.5)
        self.assertAlmostEqual(v['adjusted_parent_profit']['2026-FY'],v['parent_profit']['2026-FY'])

    def test_unit_cost_including_currency_effect_disables_second_transaction_control(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec, financial_cost_pools
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);pools=financial_cost_pools(data)
        pools[0]['input_cost_includes_transaction_fx']=True
        data['model_configuration']['financial_contracts']={'cost_pools':pools}
        s=build_periodic_spec(data,1);v=calculate_periodic(s);pid='2026-H1'
        self.assertEqual(v['north_pool_cogs_transaction_amount'][pid],0)
        with self.assertRaisesRegex(ValueError,'Only authoritative editable'):
            calculate_periodic(s,{'north_pool_cogs_transaction_fx':{pid:.1}})

    def test_historical_dilution_preserves_reported_counts_and_estimated_status(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);refs=[{'source_id':'synthetic_dilution_note'}]
        item={'incremental_shares':2,'earnings_adjustment':0,'status':'estimated','source_refs':refs}
        data['model_configuration']['financial_contracts']={'adjusted_earnings':{'dilution':{'historical':{'2025-FY':item}}}}
        s=build_periodic_spec(data,1);rows={r['id']:r for r in s['rows']}
        for rid in ('incremental_diluted_shares','shares_diluted','eps_diluted'):
            cell=rows[rid]['cells']['2025-FY']
            self.assertEqual(cell['data_role'],'estimated_historical_baseline')
            self.assertFalse(cell['calibration_eligible'])
        for rid,template,value in [('shares_diluted','shares_basic',12),('eps_diluted','eps_basic',1.83)]:
            original=next(o for o in data['observations'] if o['row_id']==template and o['period_id']=='2025-FY')
            observation=dict(copy.deepcopy(original),id='reported_'+rid,row_id=rid,metric=rid,definition_id=rid,value=value)
            data['observations'].append(observation)
        s=build_periodic_spec(data,1);v=calculate_periodic(s);rows={r['id']:r for r in s['rows']}
        self.assertEqual(v['shares_diluted']['2025-FY'],12)
        self.assertEqual(v['eps_diluted']['2025-FY'],1.83)
        self.assertEqual(rows['eps_diluted']['cells']['2025-FY']['observation_id'],'reported_eps_diluted')
        item['incremental_shares']=3
        with self.assertRaisesRegex(ValueError,'conflicts with a preserved reported shares_diluted'):build_periodic_spec(data,1)
        item['incremental_shares']=2;item['source_refs']=[]
        with self.assertRaisesRegex(ValueError,'requires cited evidence'):build_periodic_spec(data,1)

    def test_source_rounding_tolerance_is_explicit_and_validated(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        data=copy.deepcopy(self.data)
        for amount in (-1,float('nan'),float('inf'),True):
            data['model_configuration']['financial_contracts']={'source_rounding_tolerance':amount}
            with self.assertRaisesRegex(ValueError,'finite and nonnegative'):build_periodic_spec(data,1)
        data['segments'][0]['utop2025']+=.1
        data['model_configuration']['financial_contracts']={}
        with self.assertRaisesRegex(ValueError,'expense base and segment cash costs'):build_periodic_spec(data,1)
        data['model_configuration']['financial_contracts']={'source_rounding_tolerance':.1}
        build_periodic_spec(data,1)

    def test_absent_function_is_structural_classification_not_reported_zero(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec, financial_cost_pools
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
        data=copy.deepcopy(self.data)
        for year,value in data['historical'].pop('distribution')['values'].items():data['historical']['cogs']['values'][year]+=value
        distribution={o['period_id']:o['value'] for o in data['observations'] if o['row_id']=='distribution'}
        for observation in data['observations']:
            if observation['row_id']=='cogs':observation['value']+=distribution[observation['period_id']]
        data['observations']=[o for o in data['observations'] if o['row_id']!='distribution']
        data['model_configuration']['functional_expense_structure']={'distribution':dict(treatment='included_in_other_functions',included_in=['cogs'],source_refs=[{'source_id':'synthetic_classification_note'}])}
        data['model_configuration']['financial_contracts']={'cost_pools':[p for p in financial_cost_pools(self.data) if p['destination']!='distribution']}
        original=copy.deepcopy(data);s=build_periodic_spec(data,1);v=calculate_periodic(s);rows={r['id']:r for r in s['rows']}
        self.assertEqual(data,original)
        self.assertEqual(v['distribution']['2025-FY'],0)
        self.assertEqual(rows['distribution']['cells']['2025-FY']['data_role'],'structural_parameter')
        self.assertFalse(rows['distribution']['calibration_eligible'])
        self.assertNotIn(rows['distribution']['cells']['2025-FY']['status'],('actual','reported','derived_actual'))
        self.assertAlmostEqual(v['cogs']['2025-FY'],-110)
        self.assertAlmostEqual(v['utop']['2026-FY'],v['is_utop']['2026-FY'])
        self.assertFalse([c for c in validate_periodic(s,v) if c['status'] in ('FAIL','MISSING')])
        conflicting=copy.deepcopy(original);conflicting['historical']['distribution']={'values':{'2025':-1}}
        with self.assertRaisesRegex(ValueError,'conflicts with a standalone'):build_periodic_spec(conflicting,1)

    def test_aggregate_organic_does_not_invent_a_physical_volume_driver(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec, periodic_sensitivities
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['revenue_models']={s['id']:{'method':'aggregate_organic'} for s in data['segments']}
        for segment in data['segments']:
            segment['og2025']=segment.pop('pricing2025')+segment.pop('rig2025')
        data['observations']=[o for o in data['observations'] if not o['row_id'].endswith(('_pricing','_rig'))]
        s=build_periodic_spec(data,1);v=calculate_periodic(s);rows={r['id']:r for r in s['rows']};pid='2026-H1'
        self.assertTrue(rows['north_pool_cogs_activity_change']['cells'][pid]['editable'])
        self.assertEqual(v['north_pool_cogs_activity_change'][pid],0)
        changed=calculate_periodic(s,{'north_organic':{pid:v['north_organic'][pid]+.01}})
        self.assertAlmostEqual(changed['north_pool_cogs'][pid],v['north_pool_cogs'][pid])
        self.assertAlmostEqual(changed['north_sales'][pid]-v['north_sales'][pid],.4)
        cases,checks=periodic_sensitivities(s,v)
        self.assertEqual(cases[0]['driver'],'north_organic')
        self.assertFalse([c for c in checks if c['status'] in ('FAIL','MISSING')])

    def test_effective_ratios_use_annual_amounts_and_year_end_debt(self):
        from company_initiation.forecast_construction.periods import calculate_periodic
        s=copy.deepcopy(self.spec);rows={r['id']:r for r in s['rows']}
        for rid,amounts in [('pretax',(10,90)),('tax_expense',(-4,-9)),('total_profit',(10,90)),('nci_profit',(3,2))]:
            for half,amount in zip(('H1','H2'),amounts):rows[rid]['cells']['2026-'+half]=dict(value=amount,status='forecast',editable=False)
        for pid,short in [('2026-H1',3),('2026-FY',2)]:
            rows['short_debt']['cells'][pid]=dict(value=short,status='forecast',editable=False)
            rows['total_debt']['cells'][pid]=dict(value=10,status='forecast',editable=False)
        v=calculate_periodic(s)
        self.assertAlmostEqual(v['effective_tax_rate']['2026-FY'],.13)
        self.assertAlmostEqual(v['nci_profit_share']['2026-FY'],.05)
        self.assertAlmostEqual(v['current_debt_share']['2026-FY'],.2)
        for rid in ('effective_tax_rate','nci_profit_share','current_debt_share'):
            self.assertFalse(rows[rid]['cells']['2026-FY']['editable'])
            self.assertTrue(rows[rid+'_policy']['cells']['2026-H1']['editable'])

    def test_estimated_segment_da_is_separate_from_combined_reported_measure(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec, functional_structure_inputs
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);refs=[{'source_id':'synthetic_combined_depreciation_and_provisions'}]
        data['observations']=[o for o in data['observations'] if o['row_id']!='north_da']
        data['model_configuration']['historical_allocations']=[dict(row_id='north_da',year=2025,amount=5,
            method='Reported pure group depreciation allocated using reported segment combined depreciation and provision weights.',source_refs=refs,status='estimated')]
        data['segments'][0].pop('da2025');original=copy.deepcopy(data)
        normalized=functional_structure_inputs(data);self.assertEqual(normalized['segments'][0]['da2025'],5)
        s=build_periodic_spec(data,1);v=calculate_periodic(s);rows={r['id']:r for r in s['rows']}
        self.assertEqual(data,original)
        self.assertEqual(v['north_da']['2025-FY'],5)
        self.assertEqual(rows['north_da']['cells']['2025-FY']['status'],'estimated_historical')
        self.assertFalse(rows['north_da']['cells']['2025-FY']['calibration_eligible'])
        self.assertFalse([o for o in s['observations'] if o['row_id']=='north_da'])
        self.assertEqual(rows['north_cash_cost']['cells']['2025-FY']['status'],'estimated_historical')
        self.assertAlmostEqual(v['is_utop']['2026-FY'],v['utop']['2026-FY'])

    def test_annual_current_debt_uses_closing_policy_not_average_interim_policy(self):
        changed=self.run_case({'current_debt_share_policy':{'2026-H1':.3,'2026-H2':.1}})
        self.assertAlmostEqual(changed['current_debt_share_policy']['2026-FY'],.1)
        self.assertAlmostEqual(changed['current_debt_share']['2026-FY'],.1)
        self.assertAlmostEqual(changed['short_debt']['2026-FY']/changed['total_debt']['2026-FY'],.1)

    def test_sourced_closing_shares_replace_proxy_without_rewriting_weighted_shares(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);refs=[{'source_id':'synthetic_closing_shares'}]
        data['model_configuration']['financial_contracts']={'financing':{'historical_closing_shares':[dict(period_id='2025-FY',value=9,source_refs=refs)]}}
        s=build_periodic_spec(data,1);v=calculate_periodic(s);rows={r['id']:r for r in s['rows']}
        self.assertEqual(v['shares_basic']['2025-FY'],10)
        self.assertEqual(v['shares_end_outstanding']['2025-FY'],9)
        self.assertEqual(v['shares_basic']['2026-H1'],9)
        self.assertEqual(rows['shares_end_outstanding']['cells']['2025-FY']['data_role'],'reported_fact')
        observation=copy.deepcopy(next(o for o in data['observations'] if o['row_id']=='shares_basic' and o['period_id']=='2025-FY'))
        observation.update(id='independent_closing_count',row_id='shares_end_outstanding',value=8,metric_type='stock')
        data['observations'].append(observation)
        with self.assertRaisesRegex(ValueError,'conflict with a preserved'):build_periodic_spec(data,1)

    def test_hybrid_coupon_changes_eps_attribution_without_expensing_it_twice(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);data['model_configuration']['forecast_frequency']='annual'
        baseline=calculate_periodic(build_periodic_spec(data,1));refs=[{'source_id':'synthetic_hybrid_terms'}]
        data['model_configuration']['financial_contracts']={'adjusted_earnings':{'adjustments':[],
            'basic_earnings_adjustment':{'annual_amount':-2,'amounts_by_period':{'2026-FY':-3},'source_refs':refs,
                'method':'After-tax coupon attributable to hybrid capital, excluded from ordinary-share earnings.'},
            'dilution':{'incremental_shares':2,'earnings_adjustment':0}}}
        s=build_periodic_spec(data,1);v=calculate_periodic(s);pid='2026-FY'
        self.assertAlmostEqual(v['eps_basic'][pid]-baseline['eps_basic'][pid],-.3)
        self.assertAlmostEqual(v['eps_diluted'][pid],(v['parent_profit'][pid]-3)/12)
        self.assertAlmostEqual(v['adjusted_eps_basic'][pid],v['eps_basic'][pid])
        self.assertAlmostEqual(v['adjusted_eps_diluted'][pid],v['eps_diluted'][pid])
        for rid in ('parent_profit','operating_profit','cfo','cff','closing_cash'):
            self.assertAlmostEqual(v[rid][pid],baseline[rid][pid])

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
        from company_initiation.forecast_construction.integrated import validate_financial_contracts
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
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
        from company_initiation.forecast_construction.integrated import validate_financial_contracts
        pid='2026-H1';v=self.values
        changed=self.run_case({'cash_fx_assumption':{pid:7}})
        self.assertAlmostEqual(changed['reserves'][pid],v['reserves'][pid])
        self.assertAlmostEqual(changed['closing_cash'][pid]-v['closing_cash'][pid],7)
        self.assertTrue(any(c['status']=='FAIL' and c['name']=='cash_fx_attribution:'+pid for c in validate_financial_contracts(self.spec,changed)))

    def test_scope_effect_annualises_once_in_correct_region(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
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
        from company_initiation.forecast_construction.periods import validate_periodic
        self.assertEqual([p['kind'] for p in self.spec['periods'] if p['fiscal_year']==2029],['FY'])
        failures=[c for c in validate_periodic(self.spec,self.values) if c['status'] in ('FAIL','MISSING')]
        self.assertEqual(failures,[])
        self.assertIsNotNone(self.values['north_pool_cogs']['2029-FY'])
        self.assertAlmostEqual(self.values['balance_check']['2029-FY'],0)

    def test_explicit_scope_cash_and_assets_reconcile_without_reserve_plug(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
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

    def test_full_exit_with_month_weights_has_no_residual_sales_or_costs(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='monthly_full_exit',entity_id='north',
            type='disposal',effective_date='2026-01-01',enabled=True,accounting_enabled=False,entity_scope_fraction=1,
            calendar_month_weights=[1/12]*12,annual_revenue=-100,annual_cash_costs={},
            source_refs=[{'source_id':'synthetic_monthly_scope'}])]}
        v=calculate_periodic(build_periodic_spec(data,5))
        # Six equal monthly weights are half a year despite the half-year's
        # 181/365 calendar fraction. A complete exit has exactly no remaining
        # business in that half or later direct annual forecasts.
        for pid in ('2026-H2','2027-H1','2027-H2','2029-FY'):
            self.assertAlmostEqual(v['north_scope_active_fraction'][pid],0)
            self.assertAlmostEqual(v['north_sales'][pid],0)
            self.assertAlmostEqual(v['north_cash_cost'][pid],0)
            self.assertAlmostEqual(v['north_utop'][pid],0)

    def test_midyear_full_disposal_uses_closing_scope_for_receivables(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);data['model_configuration']['forecast_frequency']='annual'
        data['historical']['business_disposals_cf']=dict(values={'2024':0,'2025':0},sources={'2024':[],'2025':[]})
        transferred=100*25/180
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='midyear_sale',entity_id='north',
            type='disposal',effective_date='2026-01-01',enabled=True,accounting_enabled=True,entity_scope_fraction=1,
            annual_revenue=-100,annual_cash_costs={},balance_movements={'receivables':-transferred},
            cash_flows={'business_disposals_cf':transferred},gain_loss=0,source_refs=[{'source_id':'synthetic_scope'}])]}
        s=build_periodic_spec(data,1)
        v=calculate_periodic(s,{e+'_'+driver:{'2026-FY':0} for e in ('north','specialty') for driver in ('pricing','rig')})
        # Revenue includes the sold business for184days, while its entire
        # receivable balance transfers at the closing date. Only specialty's
        # 80annual revenue supports the closing working-capital target.
        self.assertAlmostEqual(v['north_sales']['2026-FY'],100*184/365)
        self.assertAlmostEqual(v['receivables']['2026-FY'],80*25/180)
        self.assertAlmostEqual(v['wc_receivables_cf']['2026-FY'],0)
        self.assertAlmostEqual(v['business_disposals_cf']['2026-FY'],transferred)
        self.assertAlmostEqual(v['balance_check']['2026-FY'],0)

    def test_partial_midperiod_scope_uses_full_exit_run_rate_for_working_capital(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='partial_scope',entity_id='north',
            type='disposal',effective_date='2026-04-01',enabled=True,accounting_enabled=False,
            annual_revenue=-50,annual_cash_costs={'cogs':-20},annual_da=-4,
            annual_da_by_role={'owned_ppe_depreciation':-4},source_refs=[{'source_id':'synthetic_partial_scope'}])]}
        changes={e+'_'+driver:{'2026-H1':0,'2026-H2':0} for e in ('north','specialty') for driver in ('pricing','rig')}
        baseline=calculate_periodic(self.spec,changes);s=build_periodic_spec(data,1);v=calculate_periodic(s,changes);pid='2026-H2'
        fraction=v['period_year_fraction'][pid];da_share=v['pool_cogs_da_share'][pid]
        self.assertAlmostEqual(v['sales'][pid]-baseline['sales'][pid],-50*91/365)
        self.assertAlmostEqual((v['closing_operating_sales_base'][pid]-baseline['closing_operating_sales_base'][pid])/fraction,-50)
        self.assertAlmostEqual((v['closing_operating_cogs_base'][pid]-baseline['closing_operating_cogs_base'][pid])/fraction,20+4*da_share)
        self.assertAlmostEqual(v['receivables']['2026-FY']-baseline['receivables']['2026-FY'],-50*25/180)
        self.assertAlmostEqual(v['inventories']['2026-FY']-baseline['inventories']['2026-FY'],-(20+4*da_share)*v['inventory_ratio'][pid])

    def test_no_remaining_da_recipient_is_explicitly_incomplete(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
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

    def test_previously_reclassified_working_capital_is_not_removed_again_at_sale(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data);data['model_configuration']['actual_through']='2025-12-31'
        transferred=100*25/180
        for original in list(data['observations']):
            if original['period_id']!='2025-H1':continue
            item=dict(copy.deepcopy(original),id='next_'+original['id'],period_id='2026-H1',fiscal_year=2026,start='2025-07-01',end='2025-12-31')
            if item['row_id']=='receivables':item['value']-=transferred
            if item['row_id']=='other_current_assets':item['value']+=transferred
            data['observations'].append(item)
        data['historical']['business_disposals_cf']=dict(values={'2024':0,'2025':0},sources={'2024':[],'2025':[]})
        event=dict(id='held_business',entity_id='north',type='disposal',effective_date='2026-07-01',accounting_date='2026-06-30',
            operating_wc_excluded_from='2025-12-31',enabled=True,accounting_enabled=True,entity_scope_fraction=1,
            annual_revenue=-100,annual_cash_costs={},balance_movements={'other_current_assets':-transferred},
            cash_flows={'business_disposals_cf':transferred},gain_loss=0,source_refs=[{'source_id':'synthetic_hfs_note'}])
        data['model_configuration']['financial_contracts']={'scope_events':[event]}
        controls={e+'_'+driver:{'2026-H2':0} for e in ('north','specialty') for driver in ('pricing','rig')}
        s=build_periodic_spec(data,2);v=calculate_periodic(s,controls)
        # The sold business remains in H2 revenue until June30, but its working
        # capital has already moved to held-for-sale assets in reported H1.
        self.assertAlmostEqual(v['north_sales']['2026-H2'],60)
        self.assertAlmostEqual(v['closing_operating_sales_base']['2026-H2'],48)
        self.assertAlmostEqual(v['receivables']['2026-FY'],48/(181/365)*25/180)
        event['accounting_date']='2027-06-30';event['effective_date']='2027-07-01'
        later=calculate_periodic(build_periodic_spec(data,2),controls)
        self.assertAlmostEqual(v['receivables']['2026-FY'],later['receivables']['2026-FY'])
        self.assertAlmostEqual(v['wc_receivables_cf']['2026-H2'],later['wc_receivables_cf']['2026-H2'])
        event['balance_movements']={'receivables':-transferred}
        with self.assertRaisesRegex(ValueError,'cannot be removed again'):build_periodic_spec(data,1)

    def test_depreciation_uses_assets_removed_on_the_accounting_close_date(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['historical']['business_disposals_cf']=dict(values={'2024':0,'2025':0},sources={'2024':[],'2025':[]})
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='year_end_assets',entity_id='north',
            type='disposal',effective_date='2026-01-01',accounting_date='2025-12-31',enabled=True,accounting_enabled=True,
            annual_revenue=0,annual_cash_costs={},annual_da=-2,annual_da_by_role={'owned_ppe_depreciation':-2},
            balance_movements={'owned_ppe':-20},cash_flows={'business_disposals_cf':20},gain_loss=0,
            source_refs=[{'source_id':'synthetic_closing_assets'}])]}
        v=calculate_periodic(build_periodic_spec(data,1));base=self.values
        self.assertAlmostEqual(v['owned_ppe']['2026-H1']-base['owned_ppe']['2026-H1'],-20)
        # H2 opening assets already exclude20; their10% annual depreciation
        # rate removes2*181/365 once. A second scope-D&A removal would double it.
        self.assertAlmostEqual(v['owned_ppe_depreciation']['2026-H2']-base['owned_ppe_depreciation']['2026-H2'],-2*181/365)
        self.assertAlmostEqual(v['group_scope_da']['2026-H2'],0)

    def test_future_retained_investment_seeds_are_not_historical_evidence(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
        data=copy.deepcopy(self.data)
        data['historical']['business_disposals_cf']=dict(values={'2024':0,'2025':0},sources={'2024':[],'2025':[]})
        data['model_configuration']['financial_contracts']={'scope_events':[dict(id='retained',entity_id='north',
            type='disposal',effective_date='2027-01-01',accounting_date='2026-12-31',enabled=True,
            source_refs=[{'source_id':'synthetic_jv'}],estimation=dict(method='Explicit synthetic retained interest',
                annual_revenue=0,annual_operating_profit=0,annual_da=0,closing=dict(consideration=10,retained_investment=20,
                assets={'other_current_assets':10},liabilities={})),retained_operation=dict(ownership=.5,
                annual_profit_after_tax=4,distribution_share=.5))]}
        s=build_periodic_spec(data,2);v=calculate_periodic(s);rows={r['id']:r for r in s['rows']}
        for suffix in ('','_earnings','_distributions'):
            row=rows['scope_retained_retained_investment'+suffix]
            historical=row['cells']['2025-FY'];future=row['cells']['2026-Q1']
            self.assertEqual(historical['status'],'derived_actual')
            self.assertEqual(future['status'],'forecast')
            for cell in (historical,future):
                self.assertEqual(cell['data_role'],'structural_absence')
                self.assertFalse(cell['calibration_eligible'])
        self.assertIsNone(v['scope_retained_retained_investment']['2027-Q2'])
        self.assertAlmostEqual(v['scope_retained_retained_investment']['2027-H1'],20)
        self.assertAlmostEqual(v['scope_retained_retained_investment_earnings']['2027-H1'],0)
        self.assertAlmostEqual(v['scope_retained_retained_investment_earnings']['2027-H2'],2*181/365)

    def test_da_allocation_conditional_fits_excel_formula_limit(self):
        from company_initiation.forecast_construction.periods import cell_formula_excel
        rows={r['id']:r for r in self.spec['rows']}
        positions={rid:i+100000 for i,rid in enumerate(rows)}
        targets=[(rid,'2026-H1') for rid in ('remaining_da_per_allocation_weight','north_da','specialty_da','corporate_da')]
        targets.append(('north_pricing','2026-FY'))
        for rid,pid in targets:
            formula=cell_formula_excel(rows[rid]['cells'][pid],pid,
                lambda row,period:"'Assumptions'!ZZZ"+str(positions[row]))
            self.assertLessEqual(len(formula),8192)

    def test_mixed_actual_year_does_not_invent_historical_fx_attribution(self):
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
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
        from company_initiation.forecast_construction.periods import calculate_periodic
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic
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
        from company_initiation.forecast_construction.periods import calculate_periodic
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
        from company_initiation.forecast_construction.integrated import build_periodic_spec
        from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
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
