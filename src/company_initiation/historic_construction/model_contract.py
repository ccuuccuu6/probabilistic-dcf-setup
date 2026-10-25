"""Historical financial roles and sourced company structure.

The catalogue contains identifiers and presentation metadata, never a company
mapping or forecast equation. Later stages consume this contract; historical
research does not import or inspect their implementation.
"""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import json
import math

_HISTORICAL_ROLE_CONTRACT = {'version': 'historical_roles_v1',
 'group_roles': ['amortization',
                 'associate_dividends',
                 'associate_investing_cf',
                 'associate_profit',
                 'associates',
                 'balance_check',
                 'business_acquisitions_cf',
                 'business_disposals_cf',
                 'buyback_shares',
                 'buybacks',
                 'capex_intangibles',
                 'capex_ppe',
                 'cash',
                 'cash_change',
                 'cash_fx',
                 'cash_interest',
                 'cash_interest_income',
                 'cf_associates',
                 'cf_finance_timing',
                 'cf_net_profit',
                 'cf_tax_timing',
                 'cf_to_bs_cash',
                 'cff',
                 'cfi',
                 'cfo',
                 'cfo_fx_noncash',
                 'cfo_portfolio_noncash',
                 'closing_cash',
                 'cogs',
                 'current_assets',
                 'current_liabilities',
                 'current_tax_expense',
                 'current_tax_liabilities',
                 'da',
                 'debt_borrow',
                 'debt_interest',
                 'debt_interest_expense',
                 'debt_repay',
                 'deferred_tax_assets',
                 'deferred_tax_expense',
                 'deferred_tax_liabilities',
                 'disposal_result_cf',
                 'distribution',
                 'dividends_nci',
                 'dividends_parent',
                 'eps_basic',
                 'eps_diluted',
                 'exceptional_associate_distribution',
                 'financial_expense',
                 'financial_income',
                 'forecast_basis_note',
                 'goodwill',
                 'gross_profit',
                 'held_for_sale_cash',
                 'impairment',
                 'intangibles',
                 'inventories',
                 'is_utop',
                 'lease_asset_additions',
                 'lease_interest',
                 'lease_interest_expense',
                 'lease_liabilities',
                 'lease_principal',
                 'liabilities_equity',
                 'long_debt',
                 'marketing_admin',
                 'nci_acquisition_cf',
                 'nci_equity',
                 'nci_profit',
                 'net_debt',
                 'net_operating_working_capital',
                 'net_other_operating',
                 'net_other_trading',
                 'noncurrent_assets',
                 'noncurrent_liabilities',
                 'nonlease_debt',
                 'opening_cash',
                 'operating_profit',
                 'other_current_assets',
                 'other_current_liabilities',
                 'other_current_liabilities_ex_tax',
                 'other_investing_combined_cf',
                 'other_noncash_ex_sbc',
                 'other_noncurrent_assets',
                 'other_noncurrent_assets_ex_tax',
                 'other_noncurrent_liabilities',
                 'other_noncurrent_liabilities_ex_tax',
                 'other_operating_assets_liabilities_cf',
                 'other_operating_expense',
                 'other_operating_income',
                 'other_revenue',
                 'other_trading_expense',
                 'other_trading_income',
                 'owned_ppe',
                 'owned_ppe_depreciation',
                 'paid_tax',
                 'parent_equity',
                 'parent_profit',
                 'ppe',
                 'pretax',
                 'receivables',
                 'research',
                 'reserves',
                 'retained_earnings',
                 'right_of_use_assets',
                 'rou_additions',
                 'rou_depreciation',
                 'sales',
                 'sbc',
                 'share_capital',
                 'shares_basic',
                 'shares_diluted',
                 'shares_end_outstanding',
                 'short_debt',
                 'short_debt_cash',
                 'short_investments',
                 'tax_expense',
                 'total_assets',
                 'total_debt',
                 'total_equity',
                 'total_liabilities',
                 'total_profit',
                 'total_revenue',
                 'trade_payables',
                 'trading_profit',
                 'treasury_investments_cf',
                 'treasury_stock',
                 'utop',
                 'wc_accruals_cf',
                 'wc_cash',
                 'wc_inventory_cf',
                 'wc_payables_cf',
                 'wc_prepayments_cf',
                 'wc_receivables_cf'],
 'corporate_roles': ['corporate_cash_cost', 'corporate_da', 'corporate_utop'],
 'anchor_roles': ['amortization',
                  'associate_dividends',
                  'associate_profit',
                  'associates',
                  'capex_intangibles',
                  'capex_ppe',
                  'cash',
                  'cash_interest_income',
                  'cogs',
                  'da',
                  'debt_interest_expense',
                  'deferred_tax_expense',
                  'distribution',
                  'dividends_nci',
                  'dividends_parent',
                  'exceptional_associate_distribution',
                  'financial_expense',
                  'financial_income',
                  'held_for_sale_cash',
                  'intangibles',
                  'inventories',
                  'lease_asset_additions',
                  'lease_interest_expense',
                  'lease_liabilities',
                  'long_debt',
                  'marketing_admin',
                  'nci_profit',
                  'other_revenue',
                  'owned_ppe',
                  'owned_ppe_depreciation',
                  'paid_tax',
                  'parent_equity',
                  'parent_profit',
                  'pretax',
                  'receivables',
                  'research',
                  'right_of_use_assets',
                  'rou_additions',
                  'rou_depreciation',
                  'sales',
                  'sbc',
                  'shares_basic',
                  'short_debt',
                  'short_investments',
                  'tax_expense',
                  'total_profit',
                  'total_revenue',
                  'trade_payables',
                  'utop'],
 'segment_role_suffixes': ['_cash_cost',
                           '_da',
                           '_ebitda',
                           '_fx_effect',
                           '_growth',
                           '_margin',
                           '_organic',
                           '_pricing_effect',
                           '_rig_effect',
                           '_sales',
                           '_utop'],
 'role_sections': {'amortization': ['assets'],
                   'associate_dividends': ['cashflow'],
                   'associate_investing_cf': ['cashflow'],
                   'associate_profit': ['income'],
                   'associates': ['balance'],
                   'balance_check': ['balance'],
                   'business_acquisitions_cf': ['cashflow'],
                   'business_disposals_cf': ['cashflow'],
                   'buyback_shares': ['financing'],
                   'buybacks': ['cashflow'],
                   'capex_intangibles': ['cashflow'],
                   'capex_ppe': ['cashflow'],
                   'cash': ['balance', 'cashflow'],
                   'cash_change': ['cashflow'],
                   'cash_fx': ['cashflow'],
                   'cash_interest': ['financing'],
                   'cash_interest_income': ['financing'],
                   'cf_associates': ['cashflow'],
                   'cf_finance_timing': ['cashflow'],
                   'cf_net_profit': ['cashflow'],
                   'cf_tax_timing': ['cashflow'],
                   'cf_to_bs_cash': ['cashflow'],
                   'cff': ['cashflow'],
                   'cfi': ['cashflow'],
                   'cfo': ['cashflow'],
                   'cfo_fx_noncash': ['cashflow'],
                   'cfo_portfolio_noncash': ['cashflow'],
                   'closing_cash': ['cashflow'],
                   'cogs': ['income'],
                   'corporate_cash_cost': ['corporate'],
                   'corporate_da': ['corporate'],
                   'corporate_utop': ['corporate'],
                   'current_assets': ['balance'],
                   'current_liabilities': ['balance'],
                   'current_tax_expense': ['working_capital'],
                   'current_tax_liabilities': ['balance'],
                   'da': ['cashflow'],
                   'debt_borrow': ['cashflow'],
                   'debt_interest': ['financing'],
                   'debt_repay': ['cashflow'],
                   'deferred_tax_assets': ['balance'],
                   'deferred_tax_expense': ['working_capital'],
                   'deferred_tax_liabilities': ['balance'],
                   'disposal_result_cf': ['cashflow'],
                   'distribution': ['income'],
                   'dividends_nci': ['cashflow'],
                   'dividends_parent': ['cashflow'],
                   'eps_basic': ['income'],
                   'eps_diluted': ['income'],
                   'financial_expense': ['income'],
                   'financial_income': ['income'],
                   'forecast_basis_note': ['shared'],
                   'goodwill': ['balance'],
                   'gross_profit': ['income'],
                   'held_for_sale_cash': ['cashflow'],
                   'impairment': ['cashflow'],
                   'intangibles': ['balance'],
                   'inventories': ['balance'],
                   'is_utop': ['income'],
                   'lease_interest': ['financing'],
                   'lease_interest_expense': ['financing'],
                   'lease_liabilities': ['financing'],
                   'lease_principal': ['cashflow'],
                   'liabilities_equity': ['balance'],
                   'long_debt': ['balance'],
                   'marketing_admin': ['income'],
                   'nci_acquisition_cf': ['cashflow'],
                   'nci_equity': ['balance'],
                   'nci_profit': ['income'],
                   'net_debt': ['financing'],
                   'net_operating_working_capital': ['working_capital'],
                   'net_other_operating': ['income'],
                   'net_other_trading': ['income'],
                   'noncurrent_assets': ['balance'],
                   'noncurrent_liabilities': ['balance'],
                   'nonlease_debt': ['financing'],
                   'opening_cash': ['cashflow'],
                   'operating_profit': ['income'],
                   'other_current_assets': ['balance'],
                   'other_current_liabilities': ['balance'],
                   'other_current_liabilities_ex_tax': ['balance'],
                   'other_investing_combined_cf': ['cashflow'],
                   'other_noncash_ex_sbc': ['cashflow'],
                   'other_noncurrent_assets': ['balance'],
                   'other_noncurrent_assets_ex_tax': ['balance'],
                   'other_noncurrent_liabilities': ['balance'],
                   'other_noncurrent_liabilities_ex_tax': ['balance'],
                   'other_operating_assets_liabilities_cf': ['cashflow'],
                   'other_revenue': ['income'],
                   'owned_ppe': ['assets'],
                   'owned_ppe_depreciation': ['assets'],
                   'paid_tax': ['working_capital'],
                   'parent_equity': ['balance'],
                   'parent_profit': ['income'],
                   'ppe': ['balance'],
                   'pretax': ['income'],
                   'receivables': ['balance'],
                   'research': ['income'],
                   'reserves': ['balance'],
                   'retained_earnings': ['balance'],
                   'right_of_use_assets': ['assets'],
                   'rou_depreciation': ['assets'],
                   'sales': ['corporate'],
                   'sbc': ['cashflow'],
                   'share_capital': ['balance'],
                   'shares_basic': ['income'],
                   'shares_diluted': ['income'],
                   'shares_end_outstanding': ['income'],
                   'short_debt': ['balance'],
                   'short_debt_cash': ['cashflow'],
                   'short_investments': ['balance'],
                   'tax_expense': ['income'],
                   'total_assets': ['balance'],
                   'total_debt': ['financing'],
                   'total_equity': ['balance'],
                   'total_liabilities': ['balance'],
                   'total_profit': ['cashflow', 'income'],
                   'total_revenue': ['income'],
                   'trade_payables': ['balance'],
                   'trading_profit': ['income'],
                   'treasury_investments_cf': ['cashflow'],
                   'treasury_stock': ['balance'],
                   'utop': ['corporate'],
                   'wc_accruals_cf': ['cashflow'],
                   'wc_cash': ['cashflow'],
                   'wc_inventory_cf': ['cashflow'],
                   'wc_payables_cf': ['cashflow'],
                   'wc_prepayments_cf': ['cashflow'],
                   'wc_receivables_cf': ['cashflow']},
 'interpretation': 'Canonical identifiers only; preserve company definitions, missing evidence and separately '
                   'identified historical entities.'}

_HISTORICAL_ROW_METADATA = [('corporate_cash_cost', 'Corporate operating costs before D&A', 'money', 'flow', 'corporate'),
 ('corporate_da', 'Corporate depreciation and amortisation', 'money', 'flow', 'corporate'),
 ('corporate_utop', 'Corporate / unallocated underlying profit', 'money', 'flow', 'corporate'),
 ('sales', 'Group sales from operating segments', 'money', 'flow', 'corporate'),
 ('utop', 'Group underlying trading operating profit', 'money', 'flow', 'corporate'),
 ('other_revenue', 'Other revenue', 'money', 'flow', 'income'),
 ('total_revenue', 'Total revenue including other revenue', 'money', 'flow', 'income'),
 ('cogs', 'Cost of goods sold', 'money', 'flow', 'income'),
 ('distribution', 'Distribution costs', 'money', 'flow', 'income'),
 ('marketing_admin', 'Marketing and administration', 'money', 'flow', 'income'),
 ('research', 'Research and development', 'money', 'flow', 'income'),
 ('gross_profit', 'Gross profit (sales less COGS)', 'money', 'flow', 'income'),
 ('is_utop', 'Underlying trading profit â€” statement view', 'money', 'flow', 'income'),
 ('net_other_trading', 'Net other trading income / (expense)', 'money', 'flow', 'income'),
 ('trading_profit', 'Trading operating profit', 'money', 'flow', 'income'),
 ('net_other_operating', 'Net other operating income / (expense)', 'money', 'flow', 'income'),
 ('operating_profit', 'Operating profit', 'money', 'flow', 'income'),
 ('financial_income', 'Financial income', 'money', 'flow', 'income'),
 ('financial_expense', 'Financial expense', 'money', 'flow', 'income'),
 ('pretax', 'Profit before tax and associates', 'money', 'flow', 'income'),
 ('tax_expense', 'Income tax expense', 'money', 'flow', 'income'),
 ('associate_profit', 'Share of results of associates', 'money', 'flow', 'income'),
 ('total_profit', 'Profit for the year â€” Group including NCI', 'money', 'flow', 'income'),
 ('nci_profit', 'Profit attributable to non-controlling interests', 'money', 'flow', 'income'),
 ('parent_profit', 'Profit attributable to shareholders', 'money', 'flow', 'income'),
 ('shares_basic', 'Weighted-average basic shares (millions)', 'shares_m', 'weighted_average', 'income'),
 ('eps_basic', 'Basic earnings per share', 'money/shares_m', 'ratio', 'income'),
 ('shares_diluted', 'Diluted weighted-average shares', 'shares_m', 'weighted_average', 'income'),
 ('eps_diluted', 'Diluted earnings per share', 'money/shares_m', 'ratio', 'income'),
 ('cf_net_profit', 'Profit for the year', 'money', 'flow', 'cashflow'),
 ('da', 'Depreciation and amortisation', 'money', 'flow', 'cashflow'),
 ('sbc', 'Share-based compensation addback', 'money', 'flow', 'cashflow'),
 ('cf_associates', 'Remove noncash associate earnings', 'money', 'flow', 'cashflow'),
 ('associate_dividends', 'Cash distributions and interest from associates', 'money', 'flow', 'cashflow'),
 ('cf_tax_timing', 'Tax expense less cash tax payments', 'money', 'flow', 'cashflow'),
 ('wc_inventory_cf', 'Change in inventories â€” cash effect', 'money', 'flow', 'cashflow'),
 ('wc_receivables_cf', 'Change in receivables â€” cash effect', 'money', 'flow', 'cashflow'),
 ('wc_payables_cf', 'Change in trade payables â€” cash effect', 'money', 'flow', 'cashflow'),
 ('wc_cash', 'Operating working-capital cash effect', 'money', 'flow', 'cashflow'),
 ('cfo_portfolio_noncash', 'Modelled noncash portfolio gain / loss reversal', 'money', 'flow', 'cashflow'),
 ('cfo_fx_noncash', 'Modelled noncash monetary FX reversal', 'money', 'flow', 'cashflow'),
 ('cfo', 'Net cash from operating activities', 'money', 'flow', 'cashflow'),
 ('capex_ppe', 'Cash capital expenditure â€” owned PPE', 'money', 'flow', 'cashflow'),
 ('capex_intangibles', 'Cash investment in intangible assets', 'money', 'flow', 'cashflow'),
 ('cfi', 'Net cash used in investing activities', 'money', 'flow', 'cashflow'),
 ('dividends_parent', 'Dividends to shareholders', 'money', 'flow', 'cashflow'),
 ('dividends_nci', 'Dividends to non-controlling interests', 'money', 'flow', 'cashflow'),
 ('buybacks', 'Treasury share purchases', 'money', 'flow', 'cashflow'),
 ('debt_borrow', 'New non-lease borrowings', 'money', 'flow', 'cashflow'),
 ('debt_repay', 'Non-lease repayments', 'money', 'flow', 'cashflow'),
 ('lease_principal', 'Lease principal payments', 'money', 'flow', 'cashflow'),
 ('cff', 'Net cash used in financing activities', 'money', 'flow', 'cashflow'),
 ('cash_fx', 'Currency effects on cash', 'money', 'flow', 'cashflow'),
 ('cash_change', 'Net change in cash including FX', 'money', 'flow', 'cashflow'),
 ('opening_cash', 'Opening cash including held-for-sale scope', 'money', 'flow', 'cashflow'),
 ('closing_cash', 'Closing cash â€” cash-flow scope', 'money', 'stock', 'cashflow'),
 ('held_for_sale_cash', 'Cash within assets held for sale', 'money', 'stock', 'cashflow'),
 ('cf_to_bs_cash', 'Closing balance-sheet cash', 'money', 'stock', 'cashflow'),
 ('cash', 'Cash and cash equivalents', 'money', 'stock', 'balance'),
 ('short_investments', 'Short-term investments', 'money', 'stock', 'balance'),
 ('inventories', 'Inventories', 'money', 'stock', 'balance'),
 ('receivables', 'Trade and other receivables', 'money', 'stock', 'balance'),
 ('other_current_assets', 'Other current assets', 'money', 'stock', 'balance'),
 ('current_assets', 'Total current assets', 'money', 'stock', 'balance'),
 ('ppe', 'Property, plant and equipment including ROU', 'money', 'stock', 'balance'),
 ('goodwill', 'Goodwill', 'money', 'stock', 'balance'),
 ('intangibles', 'Intangible assets', 'money', 'stock', 'balance'),
 ('associates', 'Investments in associates and joint ventures', 'money', 'stock', 'balance'),
 ('other_noncurrent_assets', 'Other non-current assets', 'money', 'stock', 'balance'),
 ('noncurrent_assets', 'Total non-current assets', 'money', 'stock', 'balance'),
 ('total_assets', 'TOTAL ASSETS', 'money', 'stock', 'balance'),
 ('short_debt', 'Current financial debt, including leases', 'money', 'stock', 'balance'),
 ('trade_payables', 'Trade and other payables', 'money', 'stock', 'balance'),
 ('current_tax_liabilities', 'Current income tax liabilities', 'money', 'stock', 'balance'),
 ('other_current_liabilities_ex_tax', 'Other current liabilities excluding income tax', 'money', 'stock', 'balance'),
 ('other_current_liabilities', 'Other current liabilities including tax', 'money', 'stock', 'balance'),
 ('current_liabilities', 'Total current liabilities', 'money', 'stock', 'balance'),
 ('long_debt', 'Non-current financial debt, including leases', 'money', 'stock', 'balance'),
 ('other_noncurrent_liabilities', 'Other non-current liabilities', 'money', 'stock', 'balance'),
 ('noncurrent_liabilities', 'Total non-current liabilities', 'money', 'stock', 'balance'),
 ('total_liabilities', 'Total liabilities', 'money', 'stock', 'balance'),
 ('share_capital', 'Share capital / combined paid-in capital', 'money', 'stock', 'balance'),
 ('treasury_stock', 'Treasury shares', 'money', 'stock', 'balance'),
 ('reserves', 'Translation and other reserves', 'money', 'stock', 'balance'),
 ('retained_earnings', 'Retained earnings', 'money', 'stock', 'balance'),
 ('parent_equity', 'Equity attributable to shareholders', 'money', 'stock', 'balance'),
 ('nci_equity', 'Non-controlling interests', 'money', 'stock', 'balance'),
 ('total_equity', 'Total equity', 'money', 'stock', 'balance'),
 ('liabilities_equity', 'TOTAL LIABILITIES AND EQUITY', 'money', 'stock', 'balance'),
 ('balance_check', 'LIVE BALANCE-SHEET CHECK', 'money', 'stock', 'balance'),
 ('paid_tax', 'Cash income taxes paid', 'money', 'flow', 'working_capital'),
 ('net_operating_working_capital', 'Inventory + receivables âˆ’ payables', 'money', 'stock', 'working_capital'),
 ('lease_asset_additions', 'New right-of-use assets', 'money', 'flow', 'assets'),
 ('owned_ppe_depreciation', 'Depreciation â€” owned PPE', 'money', 'flow', 'assets'),
 ('rou_depreciation', 'Depreciation â€” right-of-use assets', 'money', 'flow', 'assets'),
 ('amortization', 'Amortisation â€” intangibles', 'money', 'flow', 'assets'),
 ('owned_ppe', 'Closing owned PPE', 'money', 'stock', 'assets'),
 ('right_of_use_assets', 'Closing right-of-use assets', 'money', 'stock', 'assets'),
 ('lease_liabilities', 'Closing lease liabilities', 'money', 'stock', 'financing'),
 ('nonlease_debt', 'Closing non-lease debt', 'money', 'stock', 'financing'),
 ('total_debt', 'Total financial debt including leases', 'money', 'stock', 'financing'),
 ('debt_interest', 'Interest on non-lease borrowing', 'money', 'flow', 'financing'),
 ('lease_interest', 'Interest on lease liabilities', 'money', 'flow', 'financing'),
 ('cash_interest', 'Interest on cash and short investments', 'money', 'flow', 'financing'),
 ('buyback_shares', 'Shares repurchased (millions)', 'shares_m', 'flow', 'financing'),
 ('net_debt', 'Net debt before derivatives', 'money', 'stock', 'financing'),
 ('cash_interest_income', 'Cash interest income', 'money', 'flow', 'working_capital'),
 ('debt_interest_expense', 'Debt interest expense', 'money', 'flow', 'working_capital'),
 ('exceptional_associate_distribution', 'Exceptional associate distribution', 'money', 'flow', 'working_capital'),
 ('lease_interest_expense', 'Lease interest expense', 'money', 'flow', 'working_capital'),
 ('other_trading_expense', 'Other Trading Expense', 'money', 'flow', 'working_capital'),
 ('other_operating_expense', 'Other Operating Expense', 'money', 'flow', 'working_capital'),
 ('other_operating_income', 'Other Operating Income', 'money', 'flow', 'working_capital'),
 ('other_trading_income', 'Other Trading Income', 'money', 'flow', 'working_capital'),
 ('shares_end_outstanding', 'Closing shares outstanding (millions)', 'shares_m', 'stock', 'income')]

_SEGMENT_ROW_METADATA = [('pricing', 'Pricing contribution', 'ratio', 'ratio'),
 ('rig', 'Real internal growth (volume and mix)', 'ratio', 'ratio'),
 ('fx', 'FX translation contribution', 'ratio', 'ratio'),
 ('sales', 'Sales', 'money', 'flow'),
 ('organic', 'Organic growth', 'ratio', 'ratio'),
 ('growth', 'Modelled sales growth', 'ratio', 'ratio'),
 ('pricing_effect', 'Pricing contribution to sales', 'money', 'flow'),
 ('rig_effect', 'RIG contribution to sales', 'money', 'flow'),
 ('fx_effect', 'FX contribution to sales', 'money', 'flow'),
 ('cash_cost', 'Operating costs before D&A (positive)', 'money', 'flow'),
 ('ebitda', 'Underlying profit before D&A', 'money', 'flow'),
 ('da', 'Allocated depreciation and amortisation', 'money', 'flow'),
 ('utop', 'Underlying trading operating profit', 'money', 'flow'),
 ('margin', 'Underlying trading margin', 'ratio', 'ratio')]

def historical_model(data, *, include_unreported_periods=False):
    """Project sourced history without constructing assumptions or forecasts.

    Company inputs retain all reporting versions. This projection adds only the
    existing compatible-period derivations and exposes supported observations;
    it does not evaluate later-stage financial equations. Disclosure mapping may
    request closed but unreported periods up to the information date.
    """
    from .periods import build_periods, derive_observations

    data=functional_structure_inputs(historical_eligibility_inputs(data))
    if not data.get('fiscal_calendar'):
        raise ValueError('Historical construction requires the company fiscal calendar')
    years=sorted(set(int(year) for year in data['history_years']))
    if not years:raise ValueError('Historical construction requires historical years')
    config=data.get('model_configuration',{})
    as_of=config.get('as_of',config.get('actual_through'))
    if as_of:date.fromisoformat(as_of)
    observations=copy.deepcopy(data.get('observations',[]))
    disclosed_years={int(o.get('fiscal_year',str(o['period_id']).split('-')[0])) for o in observations}
    calendar_years=set(years)|disclosed_years
    if as_of:calendar_years.update(range(min(years),max(max(years),date.fromisoformat(as_of).year+1)+1))
    calendar=build_periods(calendar_years,data['fiscal_calendar'])
    annual={p['fiscal_year']:p for p in calendar if p['kind']=='FY'}
    reported_statuses={'reported','actual','derived','derived_actual'}
    latest=max([annual[year]['end'] for year in years]+[
        o['end'] for o in observations if o.get('end') and o.get('status','reported') in reported_statuses
        and o.get('eligible',True) and (not as_of or o['end']<=as_of)])
    through=as_of if include_unreported_periods and as_of else min(latest,as_of) if as_of else latest
    periods=[dict(p,status='actual' if p['end']<=latest else 'not_disclosed') for p in calendar if p['end']<=through]
    period_map={p['id']:p for p in periods}

    money=data['currency']+'m'
    def unit_name(unit):
        return data['currency']+'_per_share' if unit=='money_per_share' else unit.replace('money',money)
    rows={rid:dict(id=rid,label=label,unit=unit_name(unit),metric_type=metric_type,section=section,
                   kind='reported',cells={})
          for rid,label,unit,metric_type,section in _HISTORICAL_ROW_METADATA}
    contract=integrated_role_contract()
    for rid in contract['group_roles']+contract['corporate_roles']:
        if rid=='forecast_basis_note' or rid in rows:continue
        section=contract['role_sections'].get(rid,['historical'])[0]
        rows[rid]=dict(id=rid,label=rid.replace('_',' ').capitalize(),unit=money,
                      metric_type='stock' if section=='balance' else 'flow',section=section,kind='reported',cells={})
    for segment in data.get('segments',[]):
        for suffix,label,unit,metric_type in _SEGMENT_ROW_METADATA:
            rid=segment['id']+'_'+suffix
            rows[rid]=dict(id=rid,label=label,unit=unit_name(unit),metric_type=metric_type,
                          section='segment_'+segment['id'],kind='reported',cells={})
    for item in operating_expense_functions(data):
        rows.setdefault(item['id'],dict(id=item['id'],label=item['label'],unit=money,
                                       metric_type='flow',section='income',kind='reported',cells={}))
    for observation in observations:
        rid=observation['row_id']
        section=rows.get(rid,{}).get('section','historical')
        rows.setdefault(rid,dict(id=rid,label=observation.get('label',rid.replace('_',' ').capitalize()),
            unit=observation.get('unit',money),metric_type=observation.get('metric_type','flow'),
            section=section,kind='reported',cells={}))
    existing={(o['row_id'],o['period_id']) for o in observations}
    for rid,source in dict(data.get('historical',{}),**data.get('schedule_controls',{})).items():
        row=rows.setdefault(rid,dict(id=rid,label=rid.replace('_',' ').capitalize(),unit=money,
            metric_type=source.get('metric_type','flow'),section='historical',kind='reported',cells={}))
        for year,value in source.get('values',{}).items():
            period=annual.get(int(year))
            if not period or period['id'] not in period_map or (rid,period['id']) in existing or value is None:continue
            refs=copy.deepcopy(source.get('sources',{}).get(str(year),[]))
            if not refs:continue
            basis=source.get('basis')
            if isinstance(basis,dict):basis=basis.get(str(year))
            observation=dict(id='annual_'+rid+'_'+str(year),row_id=rid,metric=rid,label=row['label'],
                entity_id='group',model_entity_id='group',period_id=period['id'],fiscal_year=int(year),kind='FY',
                start=period['start'],end=period['end'],metric_type=row['metric_type'],value=value,
                unit=row['unit'],currency=data['currency'],definition=row['label'],definition_id=rid,
                basis=basis,scope='consolidated_group',restatement='original',status='actual',source_refs=refs)
            observations.append(observation)
    # Earlier saved inputs also keep cited segment/corporate annual facts beside
    # their identities. Preserve those facts without calculating a forecast or
    # promoting an allocated historical estimate into a reported observation.
    allocations={(item['row_id'],int(item['year'])) for item in config.get('historical_allocations',[])}
    entities=data.get('segments',[])+[dict(data.get('corporate',{}),id='corporate')]
    for entity in entities:
        for year in years:
            period=annual[year]
            if period['id'] not in period_map:continue
            for metric in ('sales','utop','da','pricing','rig','organic'):
                rid=entity['id']+'_'+metric
                key=('og' if metric=='organic' else metric)+str(year)
                if rid not in rows or (rid,period['id']) in existing or (rid,year) in allocations:continue
                value=entity.get(key);refs=copy.deepcopy(entity.get('source_refs',{}).get(key,[]))
                if value is None or not refs:continue
                if isinstance(refs,dict):refs=[refs]
                if not all(isinstance(ref,dict) and ref.get('source_id') for ref in refs):continue
                row=rows[rid]
                basis=entity.get('basis',data.get('forecast_basis'))
                if isinstance(basis,dict):basis=basis.get(str(year))
                intended=data.get('active_basis_by_period',{}).get(period['id'],{})
                if year==max(years) and isinstance(intended,dict):basis=intended.get('segments',basis)
                observations.append(dict(id='annual_'+rid+'_'+str(year),row_id=rid,metric=rid,label=row['label'],
                    entity_id=entity['id'],model_entity_id=entity['id'],period_id=period['id'],
                    fiscal_year=year,kind='FY',start=period['start'],end=period['end'],
                    metric_type=row['metric_type'],value=value,unit=row['unit'],
                    currency=None if row['unit'] in ('ratio','shares_m') else data['currency'],
                    definition=row['label'],definition_id=rid,basis=basis,compatibility_key=basis,
                    scope=entity['id'],restatement='original',status='actual',source_refs=refs,
                    current_basis_compatible=year==max(years)))
    # Keep unsupported facts visible in the original input artifact, never turn
    # them into historical cells or silently manufacture missing amounts.
    applicable=[o for o in observations if o['period_id'] in period_map and o.get('status','reported') in reported_statuses]
    derived=derive_observations(applicable,periods)
    candidates={}
    for observation in derived['observations']:
        if not observation.get('eligible',True) or not observation.get('model_selection_eligible',True):continue
        candidates.setdefault((observation['row_id'],observation['period_id']),[]).append(observation)
    preferred=config.get('preferred_observation_ids',{})
    for (rid,pid),choices in candidates.items():
        if rid not in rows:continue
        selected=[o for o in choices if o['id']==preferred.get(rid+':'+pid)]
        if not selected:
            active=data.get('active_basis_by_period',{}).get(pid,{})
            entity_scope='segments' if rows[rid]['section'].startswith('segment_') else 'group'
            basis=active.get(entity_scope) if isinstance(active,dict) else active
            selected=[o for o in choices if basis in (o.get('basis'),o.get('compatibility_key'))] if basis else choices
        direct=[o for o in selected if o.get('status') in ('actual','reported')]
        if direct:selected=direct
        if not selected:continue
        values={o.get('value') for o in selected}
        if len(values)>1:
            rows[rid]['cells'][pid]=dict(value=None,status='conflict',observation_ids=[o['id'] for o in selected],editable=False)
        else:
            chosen=selected[0]
            rows[rid]['cells'][pid]=dict(value=chosen.get('value'),status=chosen.get('status','actual'),
                observation_id=chosen['id'],source_refs=copy.deepcopy(chosen.get('source_refs',[])),editable=False)
    return dict(company=data['company'],currency=data['currency'],historical_years=years,
        latest_reporting_date=latest,as_of=as_of,periods=periods,rows=list(rows.values()),
        observations=derived['observations'],derivation_checks=derived['checks'],
        entity_versions=copy.deepcopy(data.get('entity_versions',[])),
        reporting_bridges=copy.deepcopy(data.get('reporting_bridges',[])))


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
    """Return the historical financial-role contract without loading later stages.

    Literal loop bindings are resolved, but company entities and financial values
    are never evaluated. This catalogue describes identifiers, not evidence that
    a company reports every role or that two accounting definitions are equal.
    """
    import ast
    import textwrap
    if scaffold_source is None:
        result=copy.deepcopy(_HISTORICAL_ROLE_CONTRACT)
        result['source_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return result
    source=scaffold_source
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
    # Corporate identifiers are explicit scaffold rows, not group aliases.
    corporate={role for role in roles if role.startswith('corporate_')}
    return dict(version='scaffold_roles_v1',source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        group_roles=sorted(roles-corporate),corporate_roles=sorted(corporate),
        anchor_roles=sorted(anchors),segment_role_suffixes=sorted(segment_suffixes),
        role_sections={role:sorted(sections) for role,sections in sorted(role_sections.items()) if sections},
        interpretation='Canonical identifiers only; preserve company definitions, missing evidence and separately identified historical entities.')


