"""Forecast-model refresh and export operations, consuming saved history."""
from datetime import date, datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4
from ..shared_project import resolve_data_path

def model_financial_completeness(spec):
    """Keep material portfolio-accounting omissions separate from arithmetic.

    Passing calculations or Excel comparisons cannot complete an event's missing
    consideration, derecognition or retained-interest accounting. Other models
    remain provisional; absence of this particular gap is not economic validation.
    """
    return ('incomplete_scope_accounting' if any(event.get('material_unresolved')
        for event in spec.get('scope_event_audit',[])) else 'provisional')


def save_forecast_output(directory, spec, values, checks):
    """Save the operating model before any downstream valuation research runs."""
    from .model_excel import export_integrated, validate_workbook_layout
    from ..shared_runtime import write_json
    directory = Path(directory)
    path = directory / 'forecast_model.xlsx'
    inspection = export_integrated(path, spec, values, checks)
    inspection['layout'] = validate_workbook_layout(path, inspection)
    write_json(directory / 'forecast_workbook_validation.json', inspection)
    files = [path.name, 'forecast_workbook_validation.json']
    if path.with_suffix('.audit.json').is_file():
        files.append(path.with_suffix('.audit.json').name)
    return dict(workbook=path.name, validation='forecast_workbook_validation.json',
        files=files, status='incomplete_model' if any(c.get('status') in ('FAIL','MISSING') for c in checks)
        or inspection['layout'].get('status') != 'passed' else 'provisional',
        scope='History and operating forecasts; no valuation',
        recalculation=inspection.get('recalculation', {'status':'not_run'}))


def offline_export(root, run, *, fx_file=None, fx_database=None, snapshot_id=None, fx_as_of=None, inputs_file=None, recalculate=True, progress=None,
                   include_valuation=False,valuation_date=None,rebuild=False):
    """Re-export saved inputs, optionally refreshing only shared FX, with zero AI."""
    from ..shared_budget import BudgetLedger, ledger_path, company_key
    from ..shared_runtime import write_json, digest
    from .construction import recalculate_workbook
    from ..shared_artifacts import verified_integrated_record
    from company_initiation.forecast_construction.integrated import build_periodic_spec, periodic_sensitivities
    from ..historic_construction.initiation import _initiation_lock
    from company_initiation.forecast_construction.periods import calculate_periodic, validate_periodic
    from company_initiation.forecast_construction.model_excel import export_integrated, verify_excel_sensitivities
    from shared_FX.fx import load_fx_source
    root=Path(root).resolve();outputs=root/'outputs';prior=Path(run)
    if not prior.is_absolute():prior=outputs/prior
    previous=json.loads((prior/'record.json').read_text(encoding='utf-8'))
    previous=verified_integrated_record(prior,outputs)
    config=copy.deepcopy(previous['configuration']);company=config['company']
    config['sources']=str(resolve_data_path(root,config['sources']))
    with _initiation_lock(outputs,scope=company_key(company)):
        ledger=BudgetLedger(ledger_path(outputs,company),company,config['limits']['usd'])
        ledger.import_record(previous)
        before=ledger.summary()
        data=json.loads((prior/'company_model_inputs.json').read_text(encoding='utf-8'))
        original_data=copy.deepcopy(data)
        if inputs_file:
            revised=json.loads(Path(inputs_file).read_text(encoding='utf-8'))
            for key,value in data.items():
                if key not in ('model_configuration','sources') and revised.get(key)!=value:
                    raise ValueError('Offline exposure/policy refresh cannot revise company historical evidence: '+key)
            if any(revised.get('sources',{}).get(sid)!=source for sid,source in data['sources'].items()):
                raise ValueError('Offline configuration must preserve existing company source identities')
            data=revised
        oldspec=json.loads((prior/'model_specification.json').read_text(encoding='utf-8'))
        directory=outputs/('construct_refresh_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8])
        directory.mkdir()
        # Verified immutable originals are shared across preserved continuations.
        # Only a changed shared-factor original needs a new frozen copy.
        frozen=copy.deepcopy(previous['sources'])
        for sid,source in data['sources'].items():
            if sid in original_data['sources']:continue
            from ..historic_construction.evidence import _local_file
            raw=_local_file(Path(config['sources']),source['local_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=source['sha256']:raise ValueError('Changed new configuration evidence '+sid)
            (directory/'sources').mkdir(exist_ok=True)
            target=directory/'sources'/(sid+Path(source['local_path']).suffix);target.write_bytes(raw)
            frozen.append(dict(source,path=str(target)))
        if data['model_configuration'].pop('refresh_vendor_bindings',False):
            from ..historic_construction.evidence import migrate_vendor_bindings
            migration=migrate_vendor_bindings(data,previous['sources'],frozen)
            write_json(directory/'vendor_binding_migration.json',migration)
            if progress:progress(f'Migrated {len(migration)} unchanged vendor bindings by exact label, unit, period and value; no AI calls.')
        from ..historic_construction.model_excel import write_historical_output
        stage_outputs={'historical':write_historical_output(directory,data)}
        fx=None
        if fx_database:
            from shared_FX.fx_store import FXStore
            if not Path(fx_database).is_file():raise ValueError('Shared FX database missing; run fx-import first')
            with FXStore(fx_database) as store:
                fx=store.get_snapshot(snapshot_id) if snapshot_id else store.snapshot(
                    fx_as_of or datetime.now(timezone.utc).isoformat(),store.latest_policy())
            data['model_configuration']['fx_as_of']=fx['as_of']
            write_json(directory/'fx_snapshot.json',fx)
            spec=build_periodic_spec(data,len(oldspec['forecast_years']),fx)
            config['input_hash']=digest(dict(data=data,fx=fx['source']))
            config['fx_database']=str(Path(fx_database).resolve());config['fx_snapshot_id']=fx['source']['snapshot_id']
        elif fx_file:
            fx=load_fx_source(Path(fx_file),adapter=data.get('model_configuration',{}).get('fx_adapter'))
            fx_hash=hashlib.sha256(Path(fx_file).read_bytes()).hexdigest()
            existing=next((s for s in frozen if s['id']=='shared_fx' and s['sha256']==fx_hash),None)
            if not existing:
                (directory/'sources').mkdir()
                target=directory/'sources'/('shared_fx'+Path(fx_file).suffix)
                shutil.copyfile(fx_file,target)
                frozen=[s for s in frozen if s['id']!='shared_fx']+[dict(id='shared_fx',path=str(target),sha256=fx_hash,category='shared_factor',local_path=str(fx_file))]
            spec=build_periodic_spec(data,len(oldspec['forecast_years']),fx)
            config['input_hash']=digest(dict(data=data,fx=dict(path=str(Path(fx_file).resolve()),sha256=hashlib.sha256(Path(fx_file).read_bytes()).hexdigest())))
            config['fx_source']=str(Path(fx_file).resolve())
        elif inputs_file or rebuild:
            previous_fx=prior/'fx_snapshot.json'
            fx=json.loads(previous_fx.read_text(encoding='utf-8')) if previous_fx.is_file() else None
            spec=build_periodic_spec(data,len(oldspec['forecast_years']),fx)
        else:
            spec=copy.deepcopy(oldspec)
        # An ordinary export or company-policy refresh retains the same pinned
        # market state. A supplied replacement database/workbook owns its own
        # factor provenance and must not inherit an obsolete snapshot.
        if not fx_database and not fx_file and (prior/'fx_snapshot.json').is_file():
            shutil.copyfile(prior/'fx_snapshot.json',directory/'fx_snapshot.json')
        if oldspec.get('assumption_payload'):
            from company_initiation.forecast_construction.periods import apply_assumption_payload
            spec=apply_assumption_payload(spec,oldspec['assumption_payload'],allow_model_refresh=True)
        from company_initiation.forecast_construction.periods import assumption_contract
        spec['input_contract']=assumption_contract(spec)
        spec['financial_completeness']=model_financial_completeness(spec)
        spec['sources']=frozen
        values=calculate_periodic(spec)
        refresh_audit=None
        if fx:
            old_values=json.loads((prior/'forecast.json').read_text(encoding='utf-8'))
            changed=[]
            for row in spec['rows']:
                for pid,value in values[row['id']].items():
                    old=old_values.get(row['id'],{}).get(pid)
                    if old!=value:changed.append(dict(row_id=row['id'],period_id=pid,before=old,after=value,section=row['section']))
            refresh_audit=dict(previous_source=oldspec.get('fx_source'),new_source=fx['source'],
                previous_vintage=oldspec.get('fx_metadata',{}).get('daily_end'),new_vintage=fx['metadata'].get('daily_end'),
                changed_cells=changed,ai_calls=0,company_observations_unchanged=data.get('observations')==original_data.get('observations'),
                company_historical_values_unchanged=[(o['id'],o['value']) for o in data.get('observations',[])]==[(o['id'],o['value']) for o in original_data.get('observations',[])],
                economic_interface=spec.get('fx_interfaces',{}))
        saved_checks=json.loads((prior/'validation.json').read_text(encoding='utf-8'))['checks']
        # Retain all frozen source/annual-contract reviews. Current period, FX
        # and financial-contract checks are regenerated, including warnings;
        # retaining them would accumulate stale duplicates on each refresh.
        recomputed={'period_derivation','period_identity','period_sensitivity','period_graph','period_values','period_formula',
            'fx_exposure','transaction_fx','fx_contract',
            'financial_contracts','financial_contract','scope_bridge','cost_pool','fx_accounting','exposure_quality','driver_contract','valuation'}
        checks=[dict(c,verification_scope='Preserved prior source/annual review; see parent run') for c in saved_checks if c.get('area') not in recomputed]
        checks+=validate_periodic(spec,values)
        cases,behavior=periodic_sensitivities(spec,values);checks+=behavior;spec['sensitivity_cases']=cases
        stage_outputs['forecast']=save_forecast_output(directory,spec,values,checks)
        valuation=None
        if include_valuation or (prior/'valuation_inputs.json').is_file():
            previous_valuation=json.loads((prior/'valuation_inputs.json').read_text(encoding='utf-8')) if (prior/'valuation_inputs.json').is_file() else None
            from ..dcf_construction.workflow import valuation_snapshot
            valuation=valuation_snapshot(spec,values,data,valuation_date=valuation_date,previous_inputs=previous_valuation)
            checks+=valuation['checks']
            for name,content in valuation['artifacts'].items():write_json(directory/name,content)
            config['valuation']=dict(enabled=True,date=valuation['result']['valuation_date'])
        inspection=export_integrated(directory/'model.xlsx',spec,values,checks,valuation=valuation['result'] if valuation else None)
        if valuation:
            from ..dcf_construction.workflow import save_dcf_output
            stage_outputs['dcf']=save_dcf_output(directory,directory/'model.xlsx',inspection,checks)
        if recalculate:
            inspection['recalculation']=recalculate_workbook(directory/'model.xlsx',inspection)
            if inspection['recalculation'].get('status')=='passed':
                inspection['sensitivities']=verify_excel_sensitivities(directory/'model.xlsx',spec,inspection,output_directory=directory)
        from company_initiation.forecast_construction.model_excel import validate_workbook_layout
        inspection['layout']=validate_workbook_layout(directory/'model.xlsx',inspection)
        if valuation:
            stage_outputs['dcf']=save_dcf_output(directory,directory/'model.xlsx',inspection,checks)
        status='complete_provisional' if not any(c['status'] in ('FAIL','MISSING') for c in checks) and inspection.get('recalculation',{}).get('status')=='passed' and inspection.get('sensitivities',{}).get('status')=='passed' and inspection['layout'].get('status')=='passed' else 'incomplete_model'
        record=copy.deepcopy(previous)
        record.update(directory=str(directory),parent_run=str(prior),configuration=config,sources=frozen,status=status,
            financial_completeness=spec['financial_completeness'],artifacts={},pending_call=None,issues=[],budget=ledger.summary(),
            stage_outputs=stage_outputs)
        config['stage_workbooks']=1
        record.setdefault('summary',{}).update(rows=len(spec['rows']),segments=len(data.get('segments',[])),
            assumptions=sum(r.get('kind')=='assumption' for r in spec['rows']),
            historical_years=list(spec.get('historical_years',data.get('history_years',[]))),
            forecast_years=list(spec.get('forecast_years',[])),
            checks={state:sum(c.get('status')==state for c in checks) for state in ('PASS','FAIL','MISSING','WARNING')})
        # A new market snapshot is not itself a changed company modelling policy.
        # Keep that distinction visible even when the CLI operation remains an
        # FX refresh for compatibility with existing callers.
        market_operation_keys={'fx_as_of','refresh_vendor_bindings'}
        prior_model_config={k:v for k,v in original_data.get('model_configuration',{}).items() if k not in market_operation_keys}
        current_model_config={k:v for k,v in data.get('model_configuration',{}).items() if k not in market_operation_keys}
        changed_model_fields=sorted(k for k in prior_model_config.keys()|current_model_config.keys()
            if k not in prior_model_config or k not in current_model_config or prior_model_config[k]!=current_model_config[k])
        policy_changed=bool(changed_model_fields) or oldspec.get('policies')!=spec.get('policies')
        record['operation']=dict(kind='fx_refresh' if fx else 'reexport',ai_calls=0,
            model_configuration_changed=bool(changed_model_fields),changed_model_configuration_fields=changed_model_fields,
            calculation_policy_changed=policy_changed or rebuild,recompiled_shared_engine=bool(rebuild),
            calculation_policy='Deterministic calculation policy changed; no new AI review or acceptance.' if policy_changed else
                'Company calculation policy retained; deterministic snapshot/export operation with no AI calls.',
            budget_before=before,budget_after=ledger.summary(),source_reviews='Frozen previous source reviews; new financial contracts, FX and frequency logic are deterministically tested, with no renewed AI semantic acceptance',freshness='Preserves saved company as-of date; FX has its own explicit snapshot time; use update to discover newer company releases')
        from ..shared_artifacts import integrated_runtime_fingerprint
        record['configuration']['runtime']=integrated_runtime_fingerprint()
        from ..shared_artifacts import code_snapshot
        write_json(directory/'code_snapshot.json',code_snapshot())
        latest_reviews={}
        for call in previous.get('calls',[]):
            if call.get('stage','').startswith('integrated_') and call.get('result') and not call.get('error'):
                latest_reviews[call['stage']]={key:call.get(key) for key in ('call_id','model','reasoning_effort','result','usage')}
        write_json(directory/'review_routes.json',dict(mode='Preserved completed reviews; no AI calls during this operation',stages=latest_reviews))
        if fx:write_json(directory/'fx_import.json',{k:fx[k] for k in ('source','metadata','policy','findings') if k in fx} if fx_database else fx)
        if refresh_audit:write_json(directory/'fx_refresh_audit.json',refresh_audit)
        from ..historic_construction.evidence import source_selection_audit
        write_json(directory/'source_selection_audit.json',source_selection_audit(data,spec,frozen,values))
        for name,value in [('company_model_inputs.json',data),('model_specification.json',spec),('forecast.json',values),('validation.json',dict(status=status,financial_completeness=spec['financial_completeness'],checks=checks,gaps=spec['gaps'])),('workbook_validation.json',inspection)]:write_json(directory/name,value)
        write_json(directory/'input_contract.json',spec['input_contract'])
        if spec.get('assumption_payload'):write_json(directory/'assumptions.json',spec['assumption_payload'])
        shutil.copyfile(prior/'calls.jsonl',directory/'calls.jsonl')
        for file in directory.iterdir():
            if file.is_file():record['artifacts'][file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
        write_json(directory/'record.json',record)
        if progress:progress('Offline export: zero AI calls. '+str(directory))
        return directory



def prepare_forecast_inputs(root, company, archive, inputs_file, *, budget_usd=20, provider=None, progress=None):
    """Consume an exported historical checkpoint before researching forward policies."""
    from ..shared_ai import OpenAIProvider
    from ..shared_runtime import RunJournal,_object,_array,TEXT
    from ..shared_budget import BudgetLedger,ledger_path
    from ..shared_artifacts import verified_integrated_record
    from ..historic_construction.evidence import SourceStore,inventory_local_sources
    from ..historic_construction.workflow import (complete_historical_model,construction_evidence,_va_semantic_sections,
        _combined_history_challenge,combined_history_review_current)
    from ..historic_construction.model_contract import integrated_role_contract
    root=Path(root).resolve();archive=Path(archive).resolve();outputs=root/'outputs'
    history=complete_historical_model(root,company,archive,inputs_file,budget_usd=budget_usd,progress=progress)
    parent=verified_integrated_record(history,outputs)
    if parent['status']!='historical_complete_provisional':raise ValueError('Forecast preparation requires completed historical construction; checkpoint preserved at '+str(history))
    data=json.loads((history/'company_model_inputs.json').read_text(encoding='utf-8'))
    provider=provider or OpenAIProvider.from_env(root/'.env');provider.max_output_tokens=32000
    directory=outputs/('construct_forecast_inputs_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:8]);directory.mkdir()
    ledger=BudgetLedger(ledger_path(outputs,company),company,budget_usd);ledger.import_record(parent)
    configuration=copy.deepcopy(parent['configuration']);configuration.update(mode='forecast_input_research_v1',provider=provider.metadata())
    journal=RunJournal(directory,provider,configuration,progress,previous=parent,ledger=ledger)
    store=SourceStore(directory/'sources');catalog={s['id']:s for s in inventory_local_sources(archive)['sources']}
    for source in parent['sources']:store.restore(source,archive_root=outputs)
    def documents(ids):
        for sid in ids:
            if sid not in store._units:store.add_local(catalog[sid],root=archive)
        journal.state['sources']=store.sources;journal.save()
        return store.read_documents([dict(source_id=sid,unit_id=next(iter(store._units[sid]))) for sid in ids])
    try:
        eligible={sid:s for sid,s in catalog.items() if s.get('category')=='financial_reports' and s.get('format') in ('pdf','html','txt')}
        def validate_sources(answer):
            if set(answer['source_ids'])-eligible.keys():raise ValueError('Forecast source selection must use exact local original IDs')
            return answer
        selected=journal.stage('company_forecast_sources',
            'Select applicable company originals for forward operating drivers, cash/lease/asset accounting, portfolio events, financing and forecast policy configuration. '
            'Numerical historical observations are already constructed; do not reconstruct them or gather historical restatement appendices.',
            dict(company=company,catalog=[{k:s[k] for k in ('id','title','local_path','published_at') if k in s} for s in eligible.values()]),
            _object(source_ids=_array(TEXT)),validate_sources)
        evidence=construction_evidence(journal,documents(selected['source_ids']),
            'Forward operating-driver definitions, cash/lease/asset scope, portfolio events, financing and forecast policy configuration. Retain complete relevant sections and notes.')
        citation=_object(source_id=TEXT,unit_id=TEXT)
        schema=_object(forecast_frequency={'type':'string','enum':['annual','half_year','quarterly']},
            revenue_models=_array(_object(entity_id=TEXT,method={'type':'string','enum':['additive_contributions','aggregate_organic']},definition=TEXT,source_refs=_array(citation))),
            driver_map=_array(_object(id=TEXT,category=TEXT,entity_id=TEXT,economic_meaning=TEXT,affected_lines=_array(TEXT),
                mechanism=TEXT,frequency=TEXT,lag=TEXT,evidence_and_feasibility=TEXT,materiality=TEXT,status=TEXT,source_refs=_array(citation))))
        scope=journal.stage('company_forecast_scope',
            'Prepare forecast driver interfaces from completed historical inputs and cited originals. Preserve existing company/segment IDs and all reported history. '
            'Identify disclosed price/activity versus aggregate-organic revenue methods, causal operating costs, investment and financing policies. '
            'Do not invent a price-volume split, independent exposure or financial coefficient.',
            dict(company=company,segments=data['segments'],historical_inputs=data['historical'],evidence=_va_semantic_sections(evidence)),schema)
        if {r['entity_id'] for r in scope['revenue_models']}!={s['id'] for s in data['segments']}:raise ValueError('Forecast revenue methods must cover the historical segments')
        configure_forecast_inputs(journal,data,scope,evidence,dict(roles=integrated_role_contract()),store)
        data['sources'].update({s['id']:s for s in store.sources})
        if not combined_history_review_current(data):_combined_history_challenge(journal,data,evidence)
        if not combined_history_review_current(data):raise ValueError('Forecast accounting interpretation remains incomplete')
        journal.artifact('company_model_inputs.json',data)
        journal.state['status']='forecast_inputs_ready';journal.save()
        return directory/'company_model_inputs.json'
    except Exception as exc:
        journal.state['status']='incomplete';journal.state['issues'].append(str(exc));journal.save();raise


def configure_forecast_inputs(journal, data, scope, history_evidence, contract, store):
    """Research forward model configuration only after historical construction."""
    from ..shared_runtime import _object, _array, _enum, TEXT
    from ..historic_construction.workflow import _accounting_extension_configuration, _bind_research_anchors
    company=data['company']
    research_limitations=data['model_configuration'].setdefault('limitations',[])
    revenue_models={item['entity_id']:item for item in scope['revenue_models']}
    data['driver_map']=scope['driver_map']
    data['model_configuration'].update(revenue_models=revenue_models,forecast_frequency=scope['forecast_frequency'])
    # Interpret company accounting scope separately from numeric extraction.
    # Bridges refer to independently reconstructed facts, never AI numbers.
    citation=_object(source_id=TEXT,unit_id=TEXT)
    fact_key=_object(row_id=TEXT,entity_id=TEXT,period_id=TEXT)
    fx_weight=_object(currency=TEXT,weight={'type':'number'},rate_currency=TEXT,proxy_reason=TEXT,
        exposure_status=TEXT,effective_date=TEXT,source_refs=_array(citation),allocation=TEXT,
        evidence_basis=TEXT,scenario_neutral={'type':'boolean'},label=TEXT)
    fx_basket=_object(weights=_array(fx_weight),method=TEXT,limitations=TEXT,status=TEXT,
        effective_date=TEXT,source_refs=_array(citation),proxy_materiality_threshold={'type':'number'})
    nullable_number={'type':['number','null']}
    amount_role=_object(row_id=TEXT,amount={'type':'number'})
    event_estimation=_object(method=TEXT,annual_revenue=nullable_number,revenue_anchor=nullable_number,
        revenue_share=nullable_number,annual_operating_profit=nullable_number,operating_margin=nullable_number,
        annual_da=nullable_number,da_intensity=nullable_number,cost_weights=_array(amount_role),
        closing=_object(consideration=nullable_number,cash_transferred=nullable_number,cash_transferred_in_asset_roles={'type':'boolean'},
            assets=_array(amount_role),liabilities=_array(amount_role),retained_investment=nullable_number,
            cta_recycling=nullable_number,previous_interest_fair_value=nullable_number,
            previous_interest_carrying_value=nullable_number,net_assets_check=nullable_number,
            gain_tax_rate=nullable_number,gain_nci_share=nullable_number,held_for_sale_cash=nullable_number))
    cost_fx=_object(translation=fx_basket,transaction=_object(
        components=_array(_object(weight={'type':'number'},functional_currency=TEXT,invoice_currency=TEXT,
            lag_months={'type':'integer'},hedge_coverage={'type':'number'},hedge_rate=nullable_number,
            prior_hedge_coverage={'type':'number'},prior_hedge_rate=nullable_number,
            source_refs=_array(citation),status=TEXT)),method=TEXT,source_refs=_array(citation),status=TEXT))
    financial_contracts=_object(
        source_rounding_tolerance={'type':'number'},
        cost_pools=_array(_object(id=TEXT,label=TEXT,destination=TEXT,baseline_role=TEXT,
            baseline_amount=nullable_number,baseline_share={'type':'number'},variable_share={'type':'number'},
            method=TEXT,effective_activity_sensitivity={'type':'number'},input_cost_includes_transaction_fx={'type':'boolean'},
            activity_driver=TEXT,elasticity={'type':'number'},unit_cost_change={'type':'number'},
            spending_change={'type':'number'},behaviour=TEXT,currency_basis=TEXT,lag_months={'type':'integer'},
            source_refs=_array(citation),effective_date=TEXT,definition=TEXT,status=TEXT,fx=cost_fx)),
        scope_events=_array(_object(id=TEXT,entity_id=TEXT,type=TEXT,effective_date=TEXT,accounting_date={'type':['string','null']},
            operating_wc_excluded_from={'type':['string','null']},status=TEXT,
            enabled={'type':'boolean'},accounting_enabled={'type':'boolean'},source_refs=_array(citation),
            estimation={'anyOf':[event_estimation,{'type':'null'}]},
            annual_revenue=nullable_number,annual_cash_costs=_array(amount_role),annual_da=nullable_number,
            annual_da_by_role=_array(amount_role),da_already_in_baseline={'type':'boolean'},
            depreciation_stop_date={'type':['string','null']},
            entity_scope_fraction=nullable_number,
            amount_basis=TEXT,baseline_includes_from={'type':['string','null']},cash_flows=_array(amount_role),
            balance_movements=_array(amount_role),gain_loss=nullable_number,limitations=_array(TEXT))),
        normalisation=_object(**{key:_object(annual_amount={'type':'number'},reason=TEXT,source_refs=_array(citation))
            for key in ('net_other_trading','net_other_operating')}),
        dividends=_object(**{key:_object(annual_amount={'type':'number'},
            payment_weights=_array(_object(period_kind=TEXT,weight={'type':'number'})),reason=TEXT,source_refs=_array(citation))
            for key in ('parent','nci')}),
        sbc=_object(annual_amount=nullable_number,allocations=_array(_object(entity_id=TEXT,pool_id=TEXT,weight={'type':'number'})),source_refs=_array(citation)),
        adjusted_earnings=_object(label=TEXT,adjustments=_array(_object(id=TEXT,label=TEXT,source_row=TEXT,sign={'type':'number'},annual_amount=nullable_number,
            tax_rate={'type':'number'},nci_share={'type':'number'},associate_after_tax={'type':'boolean'},source_refs=_array(citation))),
            basic_earnings_adjustment={'anyOf':[_object(annual_amount={'type':'number'},method=TEXT,source_refs=_array(citation),
                amounts_by_period=_array(_object(period_id=TEXT,amount={'type':'number'})),
                historical=_array(_object(period_id=TEXT,amount={'type':'number'},source_refs=_array(citation)))),{'type':'null'}]},
            dilution=_object(incremental_shares={'type':'number'},earnings_adjustment={'type':'number'},method=TEXT,source_refs=_array(citation))),
        financing=_object(repurchase_price=nullable_number,repurchase_elapsed_fraction={'type':'number'},issuance_nominal_price=nullable_number,
            historical_closing_shares=_array(_object(period_id=TEXT,value={'type':'number'},source_refs=_array(citation))),
            schedule=_array(_object(period_id=TEXT,borrowing={'type':'number'},repayment={'type':'number'},maturities={'type':'number'},refinancing={'type':'number'},
                borrowing_elapsed_fraction={'type':'number'},repayment_elapsed_fraction={'type':'number'})),
            reason=TEXT,source_refs=_array(citation)),
        fx_accounting=_object(exposures=_array(_object(id=TEXT,type=TEXT,role=TEXT,currency=TEXT,functional_currency=TEXT,
            opening_share={'type':'number'},effective_from=TEXT,status=TEXT,source_refs=_array(citation),method=TEXT,
            net_movement_native_by_period=_array(_object(period_id=TEXT,amount={'type':'number'})))),policy=TEXT),limitations=_array(TEXT))
    structure_schema=_object(
        structural_account_policies=_array(_object(role=TEXT,treatment=TEXT,included_in=_array(TEXT),definition=TEXT,source_refs=_array(citation))),
        cashflow_presentation={'anyOf':[_object(components=_array(_object(role=TEXT,label=TEXT,
            cashflow_section=_enum(['cfi','cff']),classification=_enum(['ordinary_equity_issuance','noncommon_equity_issuance','noncommon_equity_distribution','investment_movement']),
            equity_role={'anyOf':[_enum(['share_capital','reserves','retained_earnings']),{'type':'null'}]},
            asset_role={'anyOf':[_enum(['short_investments']),{'type':'null'}]},
            forecast_policy=_enum(['existing_issuance_controls','no_new_transaction','hold_latest_annual']),definition=TEXT,source_refs=_array(citation))),
            method=TEXT,source_refs=_array(citation),noncommon_equity_claim_role={'type':['string','null']}),{'type':'null'}]},
        cash_scope={'anyOf':[_object(components=_array(_object(id=TEXT,role=TEXT,coefficient={'type':'number'},
            included_in_debt={'type':'boolean'},source_refs=_array(citation),definition=TEXT)),method=TEXT,source_refs=_array(citation)),{'type':'null'}]},
        operating_expense_functions=_array(_object(id=TEXT,label=TEXT,definition=TEXT,source_refs=_array(citation))),
        functional_expense_structure=_array(_object(role=TEXT,treatment=TEXT,included_in=_array(TEXT),source_refs=_array(citation))),
        historical_allocations=_array(_object(row_id=TEXT,year={'type':'integer'},amount={'type':'number'},method=TEXT,status=TEXT,source_refs=_array(citation))),
        fx_exposures=_array(_object(entity_id=TEXT,revenue_bridge=TEXT,revenue=fx_basket,cost=fx_basket)),
        financial_contracts=financial_contracts,
        asset_scope=_array(_object(reported_role=TEXT,owned_role=TEXT,rou_role=TEXT,reported_scope=TEXT,
            owned_expression=TEXT,definition=TEXT,source_refs=_array(citation))),
        entity_versions=_array(_object(id=TEXT,model_entity_id=TEXT,label=TEXT,period_ids=_array(TEXT),
            bases=_array(TEXT),scope=TEXT,current_basis_compatible={'type':'boolean'},source_refs=_array(citation))),
        reporting_bridges=_array(_object(id=TEXT,effective_date=TEXT,published_at=TEXT,period_id=TEXT,metric=TEXT,unit=TEXT,
            predecessor_basis=TEXT,successor_basis=TEXT,predecessors=_array(fact_key),successors=_array(fact_key),
            relationships=_array(_object(predecessor=TEXT,successor=TEXT,fact=fact_key)),
            limitations=_array(TEXT),source_refs=_array(citation))),gaps=_array(TEXT))
    structure_docs=history_evidence
    structure=journal.stage('company_accounting_structure',
        'Establish cited asset inclusion definitions and versioned reporting entities from the complete originals. '
        'Explain whether the reported PPE role includes ROU or is already owned-only; never subtract leases twice. '
        'Define cash_scope only from a cited cash reconciliation: cash-flow closing cash equals balance-sheet cash plus the sum of coefficient times each component stock. Coefficients are +1 or -1, never fitted ratios; each role must retain its separate mapped original amount. A supplied cash_scope fully replaces the legacy held-for-sale-only bridge, so include every applicable component once. Use included_in_debt true only for a negative component already included in reported debt, such as a bank overdraft; this prevents counting it again in financing and valuation. A cited empty components list states matching cash scopes; null means no new scope definition was established and does not assert undisclosed balances are zero. '
        'Use cashflow_presentation for separately mapped, cited ordinary/noncommon equity transactions and investment movements that require explicit statement placement. Every component keeps its signed original flow role and is counted once in cfi or cff. Ordinary equity issuance uses role issuance_cash, section cff and existing_issuance_controls; it links historical proceeds to the existing forecast issuance controls without a second transaction. Noncommon equity issuance/distributions belong in cff with their cited equity_role, never debt or statutory profit. Investment movements name asset_role short_investments and their disclosed cfi/cff section; relocation must not count them in both. Use no_new_transaction as an explicit future scenario, not a reported historical zero; hold_latest_annual is an editable policy based on the last sourced annual flow, requiring cited support for a recurring distribution. '
        'A noncommon equity component requires noncommon_equity_claim_role: a separately sourced closing claim already included in its equity account, retained as a memorandum for common-equity valuation, never added to the balance sheet twice. Paid hybrid coupons, accrued coupons net of tax used for EPS, and the outstanding senior equity claim are different concepts. Configure the EPS numerator independently in financial_contracts.adjusted_earnings.basic_earnings_adjustment; never copy paid cash into it or deduct the coupon from statutory profit. Missing amounts or unclear classification belong in gaps, not invented zeros or borrowing rows. Null cashflow_presentation retains the existing presentation. '
        'Preserve historical segment labels, scopes and bases. A numerical reorganisation bridge must reference already reconstructed observation keys; '
        'never invent numerical allocations. Use a separately reported predecessor or restatement when available. '
        'If no numerical bridge exists, retain separate incompatible entity versions and name that comparability limitation. '
        'Each scope or bridge requires original source/page references. Unresolved asset inclusion or current entity scope belongs in gaps. '
        'Build separate revenue and cost currency exposure hypotheses with cited sources and effective dates. '
        'Respect the company functional expense presentation. If a scaffold expense role is included within other reported functions, specify functional_expense_structure with treatment included_in_other_functions and the containing role IDs; do not fabricate a separately reported zero or cost split. '
        'Use structural_account_policies only for affirmative cited presentation classifications in the supported optional scaffold stages: other_revenue may be included_in_role sales; net_other_trading/net_other_operating may be included in the other active net adjustment stage or explicitly inactive_stage; exceptional_associate_distribution may be an explicitly inactive_stage. Supply the containing roles and exact definition. These create internal calibration-ineligible structural parameters, never reported zero observations. Do not apply them to unknown amounts, contradict an existing nonzero fact, infer absence merely because a note was not retrieved, or create circular inclusion. '
        'Additional recurring operating expense categories belong in operating_expense_functions with a distinct id, company label, definition and original citations. The id must equal the previously mapped historical role and its cost-pool destination; these functions extend the existing four destinations rather than replace them. Reconcile their total to the company recurring operating profit. Never relabel a recurring expense as exceptional or bury it in another function merely to fit the scaffold. '
        'Where segment/corporate pure D&A is absent but group pure D&A and segment combined DAP are disclosed, supply historical_allocations with status estimated, an explicit allocation method and citations. Preserve the reported DAP separately; allocate group pure D&A by segment DAP proportions only as a stated estimate, including corporate and reconciling exactly to group pure D&A. Never overwrite reported pure D&A. '
        'Customer-country sales are not disclosed functional/invoice currency exposures: mark those weights estimated. '
        'Do not allocate residual revenue by factory counts or copy revenue weights into every cost category. '
        'Do not assume geographically adjacent currencies move together. A different rate_currency is a currency proxy, never a cross-rate. '
        'When evidence cannot allocate a residual, preserve its full weight explicitly as exposure_status unresolved, '
        'scenario_neutral true, label Unallocated exposure - neutral scenario, using reporting currency only as the stated zero-shock scenario. '
        'This is not evidence that the residual is denominated in reporting currency; report its materiality and avoid tiny invented rows. '
        'Include reporting currency at its explicit weight (zero allowed); each basket must sum to one without renormalising available currencies. '
        'Distinguish reported, estimated, scenario and unresolved exposure_status on every component. '
        'Choose revenue_bridge as translation_of_constant_currency or additive_reported_growth_contribution according to the disclosed bridge; keep calibration at provisional 1.0. '
        'Do not fit a historical near-zero impact by division. If support is insufficient omit that basket and state the exact limitation. '
        'Define one authoritative cash operating cost build from reported expense categories, without double counting distribution or marketing. '
        'Each cost pool names its baseline_role, destination, evidence and one method: activity_cost, budget_delta, budget_growth or absolute_budget. '
        'Use one effective_activity_sensitivity for activity_cost; legacy variable_share/elasticity are initialization metadata, not two independently estimated overlapping drivers. Budget methods must not carry activity or unit-cost controls. '
        'Set input_cost_includes_transaction_fx true when input inflation already includes invoice-currency movements; do not apply the same FX shock twice. '
        'If baseline_amount is null Python uses the original historical role times baseline_share. Multiple pools sharing a role must exhaust its baseline once. '
        'COGS and marketing must not be forecast from sales ratios or backwards from predetermined profit. A rounded reported historical marketing ratio may initialise an absolute spending base only. '
        'RIG includes mix: explicitly identify its use as an activity proxy and do not make fixed costs scale automatically. '
        'Use cost functional-currency translation separately from invoice-to-functional transaction FX; same currency has no transaction effect. '
        'Resolve hedge_coverage/hedge_rate for current purchases separately from prior_hedge_coverage/prior_hedge_rate for comparable purchases; absent coverage is zero with null rate, never copy current terms to the prior period. If procurement currency, lags or hedges are undisclosed, components may be empty with status unmodelled; never invent hedge contracts. '
        'Record completed and sufficiently defined portfolio changes as regional scope_events, with effective dates, signed annual revenue/cost amounts, cashflows and balance movements. '
        'Distinguish timing scenarios from confirmed closing dates; preserve already-included actual contributions and annualisation, and never use a reorganisation as acquisition growth. '
        'Use effective_date for the first included/excluded operating day and accounting_date for the balance-sheet/cash/gain closing date; a transaction closing on June30 may first exclude operations on July1. '
        'For an already reported held-for-sale classification, operating_wc_excluded_from identifies the cited date when the business left operating inventory/receivables/payables. Keep those balances excluded while its income remains consolidated, and dispose of held-for-sale asset/liability buckets only; never remove its operating working capital twice. Forecast classifications need a separate transfer bridge. '
        'Set closing.cash_transferred_in_asset_roles true only when transferred cash is already included in a supplied aggregate asset bucket, so net assets do not count it twice. '
        'An event with incomplete closing accounting may have operating effects enabled and accounting_enabled false with precise material limitations. '
        'Where disclosures leave material event amounts unknown, provide an explicit provisional estimation method using positive annual revenue/profit/D&A magnitudes, supported revenue shares or margins and cost-pool weights. The engine applies acquisition/disposal signs. '
        'Optional closing estimates must independently specify consideration, transferred cash, each material asset/liability and retained/prior interest; derived gain or goodwill is not an invented balancing asset. Leave unestimated closing fields null and arrays empty. '
        'Assess recurring restructuring separately from exceptional adjustments; explicit normalisation annual amounts must not erase every adjustment without evidence. '
        'Separate annual dividend pools from their payment period weights and prior-year policy. Repurchase price may be null for inactive buybacks; book value per share is not an execution price. '
        'Identify SBC embedded in historical operating expenses, its noncash addback and equity treatment; do not add an expense twice. Source annual_amount where disclosed, otherwise null preserves the mapped historical anchor. '
        'For adjusted earnings use the company definition, explicitly distinguishing pretax adjustments, their tax/NCI effects and after-tax associate items; never substitute UTOP for statutory earnings. Derive a supported incremental diluted share count or disclose uncertainty. '
        'Any hybrid or preferred coupon deducted only from the EPS numerator belongs in signed basic_earnings_adjustment with cited historical periods, not a reduction of statutory parent profit. Leave this policy null if no such adjustment is disclosed. '
        'Financing schedules use actual maturities/refinancing/discretionary decisions and dated execution fractions; empty schedules mean no researched new transactions, not proof of zero obligations. Missing legal nominal issue price remains null. '
        'Preserve cited period-end outstanding ordinary shares separately from weighted-average shares in financing.historical_closing_shares, using shares in millions and subtracting treasury shares only where the source definition requires it. '
        'Research material FX accounting exposures separately from revenue/cost baskets: foreign_operation balance/cash translation versus monetary cash/debt remeasurement in the reporting functional currency. Give cited or explicitly estimated opening shares, dates and net native-currency movements; do not infer geographic sales weights as asset shares. Empty exposures mean unresolved accounting coverage, never known zero. '
        'Every non-reported policy must be clearly provisional with a reason, source references and any unresolved limitation. Evidence is not permission to fabricate a detailed cost or exposure matrix.',
        dict(company=company,scope=scope,evidence=structure_docs,observations=data['observations'],research_limitations=list(research_limitations)),structure_schema,
        lambda answer:(_accounting_extension_configuration(answer,data['observations'],structure_docs,company_data=data,role_contract=contract['roles']),answer)[1])
    data['model_configuration'].update(_accounting_extension_configuration(structure,data['observations'],structure_docs,company_data=data,role_contract=contract['roles']))
    data['model_configuration'].setdefault('limitations',[]).extend(structure['gaps'])
    def checked_refs(item):
        if not item['source_refs']:raise ValueError('Company accounting structure requires original citations')
        for ref in item['source_refs']:
            if ref['source_id'] not in store._units or ref['unit_id'] not in store._units[ref['source_id']]:
                raise ValueError('Accounting scope cites an unavailable original unit')
    for item in structure['asset_scope']+structure['entity_versions']+structure['reporting_bridges']:checked_refs(item)
    data['asset_scope']=structure['asset_scope'];data['entity_versions']=structure['entity_versions']
    for item in structure.get('functional_expense_structure',[]):checked_refs(item)
    data['model_configuration']['functional_expense_structure']={item['role']:{k:v for k,v in item.items() if k!='role'} for item in structure.get('functional_expense_structure',[])}
    for item in structure.get('historical_allocations',[]):
        checked_refs(item)
        if item['status']!='estimated':raise ValueError('Historical allocation must be explicitly estimated, never reported')
    data['model_configuration']['historical_allocations']=structure.get('historical_allocations',[])
    data['model_configuration']['fx_exposures']={item['entity_id']:{k:v for k,v in item.items() if k!='entity_id'} for item in structure.get('fx_exposures',[])}
    for exposure in data['model_configuration']['fx_exposures'].values():
        for role in ('revenue','cost'):
            checked_refs(exposure[role]);exposure[role]['multiplier']=1.0
    proposed_contracts=structure.get('financial_contracts')
    if proposed_contracts:
        contracts=copy.deepcopy(proposed_contracts)
        for pool in contracts['cost_pools']:
            checked_refs(pool)
            if pool.get('baseline_amount') is None:pool.pop('baseline_amount',None)
        for event in contracts['scope_events']:
            checked_refs(event)
            estimate=event.get('estimation')
            if estimate is None:event.pop('estimation',None)
            else:
                for key in list(estimate):
                    if estimate[key] is None:estimate.pop(key)
                estimate['cost_weights']={item['row_id']:item['amount'] for item in estimate.get('cost_weights',[])}
                closing=estimate.get('closing',{})
                for key in list(closing):
                    if closing[key] is None:closing.pop(key)
                for key in ('assets','liabilities'):
                    closing[key]={item['row_id']:item['amount'] for item in closing.get(key,[])}
                if not any(value not in ({},None) for value in closing.values()):estimate.pop('closing',None)
            for key in ('annual_cash_costs','annual_da_by_role','cash_flows','balance_movements'):
                event[key]={item['row_id']:item['amount'] for item in event[key]}
            for key in ('annual_revenue','annual_da','gain_loss','entity_scope_fraction'):
                if event.get(key) is None:event.pop(key,None)
        for policy in contracts['normalisation'].values():checked_refs(policy)
        for policy in contracts['dividends'].values():
            checked_refs(policy)
            policy['payment_weights']={item['period_kind']:item['weight'] for item in policy['payment_weights']}
        checked_refs(contracts['financing'])
        for item in contracts['financing'].get('historical_closing_shares',[]):checked_refs(item)
        contracts['financing']['schedule']={item['period_id']:{k:v for k,v in item.items() if k!='period_id'} for item in contracts['financing']['schedule']}
        checked_refs(contracts['sbc'])
        if contracts['sbc']['annual_amount'] is None:contracts['sbc'].pop('annual_amount')
        for item in contracts['adjusted_earnings']['adjustments']:
            checked_refs(item)
            if item.get('annual_amount') is None:item.pop('annual_amount')
        checked_refs(contracts['adjusted_earnings']['dilution'])
        earnings_adjustment=contracts['adjusted_earnings'].get('basic_earnings_adjustment')
        if earnings_adjustment is None:contracts['adjusted_earnings'].pop('basic_earnings_adjustment',None)
        else:
            checked_refs(earnings_adjustment)
            earnings_adjustment['amounts_by_period']={item['period_id']:item['amount'] for item in earnings_adjustment['amounts_by_period']}
            for item in earnings_adjustment['historical']:checked_refs(item)
            earnings_adjustment['historical']={item['period_id']:{k:v for k,v in item.items() if k!='period_id'} for item in earnings_adjustment['historical']}
        for exposure in contracts.get('fx_accounting',{}).get('exposures',[]):
            checked_refs(exposure)
            exposure['net_movement_native_by_period']={item['period_id']:item['amount'] for item in exposure['net_movement_native_by_period']}
        data['model_configuration']['financial_contracts']=contracts
    if not data['asset_scope']:raise ValueError('Owned PPE / ROU scope must be established before schedule construction')
    versions={v['id']:v for v in data['entity_versions']}
    for observation in data['observations']:
        version=versions.get(observation['entity_id'])
        if version:
            observation['model_entity_id']=version['model_entity_id']
            observation['current_basis_compatible']=version['current_basis_compatible']
    def fact(key):
        matches=[o for o in data['observations'] if all(o[k]==v for k,v in key.items())]
        if len(matches)!=1:raise ValueError('Reporting bridge requires an unambiguous reconstructed observation: '+str(key))
        o=matches[0]
        return dict(entity_id=o['entity_id'],value=o['value'],observation_id=o['id'])
    for proposed in structure['reporting_bridges']:
        bridge=copy.deepcopy(proposed)
        bridge['predecessors']=[fact(k) for k in proposed['predecessors']]
        bridge['successors']=[fact(k) for k in proposed['successors']]
        bridge['relationships']=[dict(predecessor=r['predecessor'],successor=r['successor'],value=fact(r['fact'])['value']) for r in proposed['relationships']]
        bridge['residual']=sum(i['value'] for i in bridge['predecessors'])-sum(i['value'] for i in bridge['successors'])
        if abs(bridge['residual'])>1e-6:raise ValueError('Reconstructed reporting bridge does not reconcile')
        bridge['status']='exact_published_split';data['reporting_bridges'].append(bridge)
    from ..historic_construction.model_contract import asset_scope_context
    asset_scope_context(data)
    _bind_research_anchors(data,revenue_models)
    data['model_configuration']['forecast_preparation_status']='complete'
    return data
