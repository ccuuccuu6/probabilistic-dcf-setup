"""Freshness and partial disclosures are tested with explicit synthetic sources."""
import copy
from collections import Counter
import hashlib
from pathlib import Path
import tempfile
import unittest
import json
from unittest.mock import patch, Mock

from company_initiation.historic_construction.workflow import freshness_checks
from company_initiation.dcf_construction.valuation import VALUATION_RESEARCH_VERSION
from company_initiation.forecast_construction.integrated import build_periodic_spec, periodic_sensitivities
from company_initiation.forecast_construction.periods import calculate_periodic
from tests.test_periodic_model import different_period_company


class DiscoveryCheckpointTests(unittest.TestCase):
    def prepare(self, root, *, unknown=False):
        from datetime import datetime,timezone
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.historic_construction.workflow import discover_releases
        archive=root/'archive';(archive/'financial_reports').mkdir(parents=True)
        (archive/'financial_reports'/'seed.pdf').write_bytes(b'%PDF synthetic unchanged initial original')
        outputs=root/'outputs';first=outputs/'construct_research_first';first.mkdir(parents=True)
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/2025.pdf'
        html=b'<p>1 March 2026</p><a href="/2025.pdf">2025 Annual Report</a>'
        provider=OpenAIProvider(api_key='SYNTHETIC-NO-NETWORK');provider.max_output_tokens=32000
        config=dict(company='SYNTHETIC checkpoint',sources=str(archive.resolve()),as_of='2026-10-25',provider=provider.metadata(),
            limits=dict(usd=2,repairs=1,retries=0))
        journal=RunJournal(first,provider,config);journal.artifact('inventory.json',inventory_local_sources(archive))
        def complete(**kwargs):
            provider.last_response=dict(status='completed',usage=dict(input_tokens=100,output_tokens=100,total_tokens=200))
            payload=kwargs['payload'];link=next(item for item in payload['catalog'] if item['url']==pdf)
            return dict(releases=[dict(link_id=link['link_id'],published_at=None if unknown else '2026-03-01',
                title='2025 Annual Report',publication_evidence='' if unknown else '1 March 2026',publication_date_id=None,
                requires_observations=True,coverage_kind='historical_original' if unknown else 'dated_release',
                reporting_year=2025,reporting_period_evidence='2025 Annual Report')],event_page_ids=[],gaps=[dict(
                detail='Annual statement coverage must be established from primary originals',fiscal_year=2025,period_kind='FY',period_end='2025-12-31',
                expected_publication_date=None,expected_publication_date_id=None,
                evidence=[dict(page_id=payload['inspected_pages'][0]['page_id'],quotation='2025 Annual Report')])])
        class ObservedEarlier(datetime):
            @classmethod
            def now(cls,tz=None):return cls(2026,10,24,12,tzinfo=timezone.utc)
        with patch.object(provider,'complete',side_effect=complete),patch('company_initiation.historic_construction.workflow.datetime',ObservedEarlier), \
                patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF synthetic selected original',pdf,'application/pdf')):
            fresh,sources=discover_releases(journal,archive,[index],'2026-10-25',latest_completed_year=2025,
                historical_years=[2025],fiscal_calendar={'fiscal_year_end':'12-31'})
        record=json.loads((first/'record.json').read_text(encoding='utf-8'))
        return archive,outputs,record,provider,config,index,fresh,sources

    def restore(self, archive, record, index, **changes):
        from company_initiation.historic_construction.workflow import restore_discovery_checkpoint
        from company_initiation.historic_construction.evidence import inventory_local_sources
        kwargs=dict(company='SYNTHETIC checkpoint',historical_years=[2025],latest_completed_year=2025,fiscal_calendar={'fiscal_year_end':'12-31'})
        kwargs.update(changes)
        return restore_discovery_checkpoint(record,[record],archive,inventory_local_sources(archive),[index],
            kwargs.pop('as_of','2026-10-25'),**kwargs)

    def replay(self, archive, outputs, records, provider, config, index, name):
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.historic_construction.workflow import restore_discovery_checkpoint, discover_releases
        parent=records[-1];checkpoint=restore_discovery_checkpoint(parent,records,archive,inventory_local_sources(archive),
            [index],'2026-10-25',company=config['company'],historical_years=[2025],latest_completed_year=2025,
            fiscal_calendar={'fiscal_year_end':'12-31'})
        directory=outputs/name;directory.mkdir();journal=RunJournal(directory,provider,config,previous=parent)
        journal.state['parent_run']=parent['directory'];journal.artifact('inventory.json',inventory_local_sources(archive))
        with patch('company_initiation.historic_construction.evidence.download',side_effect=AssertionError('No transitive network fallback')), \
                patch.object(provider,'complete',side_effect=AssertionError('No transitive AI fallback')):
            fresh,sources=discover_releases(journal,archive,[index],'2026-10-25',latest_completed_year=2025,
                historical_years=[2025],fiscal_calendar={'fiscal_year_end':'12-31'},checkpoint=checkpoint)
        return json.loads((directory/'record.json').read_text(encoding='utf-8')),checkpoint,fresh,sources

    def test_repeated_continuation_follows_exact_proof_while_retaining_latest_state(self):
        from company_initiation.historic_construction.workflow import _validate_discovery_coverage
        with tempfile.TemporaryDirectory() as temporary:
            archive,outputs,first,provider,config,index,prior,_=self.prepare(Path(temporary),unknown=True)
            before={p:p.read_bytes() for p in archive.rglob('*.pdf')};records=[first]
            for generation in range(2,5):
                current,checkpoint,fresh,sources=self.replay(archive,outputs,records,provider,config,index,
                    'construct_research_'+str(generation))
                self.assertEqual(checkpoint['run'],records[-1]['directory'])
                self.assertEqual(len(checkpoint['navigation_provenance']),generation-2)
                self.assertEqual([c['call_id'] for c in checkpoint['calls']],[c['call_id'] for c in first['calls']])
                self.assertEqual(sources[0]['observed_available_at'],'2026-10-24')
                self.assertEqual(fresh['coverage_obligations'],prior['coverage_obligations'])
                self.assertEqual(current['usage'],first['usage'])
                self.assertFalse(any(name.startswith('official_release_') for name in current['artifacts']))
                with self.assertRaisesRegex(ValueError,'never reached primary coverage'):_validate_discovery_coverage(fresh,[])
                records.append(current)
            self.assertEqual({p:p.read_bytes() for p in before},before)

    def test_continuation_proof_rejects_tampering_forged_calls_and_nonancestor_targets(self):
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.historic_construction.workflow import restore_discovery_checkpoint
        for change in ('bytes','target_hash','calls','target','cycle','scope'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temporary:
                archive,outputs,first,provider,config,index,_,_=self.prepare(Path(temporary))
                second,_,_,_=self.replay(archive,outputs,[first],provider,config,index,'construct_research_second')
                path=Path(second['directory'])/'official_discovery_continuation.json';proof=json.loads(path.read_text())
                if change=='bytes':path.write_bytes(b'changed artifact')
                else:
                    if change=='target_hash':proof['artifact_sha256']='wrong'
                    elif change=='calls':proof['replayed_calls']=['invented-call']
                    elif change=='target':proof['run']=str(outputs/'unrelated_run')
                    elif change=='cycle':second['parent_run']=second['directory'];proof['run']=second['directory']
                    else:proof['checked_as_of']='2026-10-26'
                    path.write_text(json.dumps(proof),encoding='utf-8');second['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
                    (path.parent/'record.json').write_text(json.dumps(second),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'changed|Changed|ancestor|Cyclic|exact verified|incompatible'):
                    restore_discovery_checkpoint(second,[first,second],archive,inventory_local_sources(archive),[index],
                        '2026-10-25',company=config['company'],historical_years=[2025],latest_completed_year=2025,
                        fiscal_calendar={'fiscal_year_end':'12-31'})

    def test_completed_replay_uses_no_network_or_ai_and_preserves_unknown_observation_date_and_obligations(self):
        from datetime import datetime,timezone
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.workflow import discover_releases, _validate_discovery_coverage
        with tempfile.TemporaryDirectory() as temporary:
            archive,outputs,record,provider,config,index,prior,prior_sources=self.prepare(Path(temporary),unknown=True)
            checkpoint=self.restore(archive,record,index)
            second=outputs/'construct_research_second';second.mkdir();journal=RunJournal(second,provider,config,previous=record)
            class ReplayedLater(datetime):
                @classmethod
                def now(cls,tz=None):return cls(2026,10,27,12,tzinfo=timezone.utc)
            before={p:p.read_bytes() for p in archive.rglob('*.pdf')}
            with patch('company_initiation.historic_construction.evidence.download',side_effect=AssertionError('No network replay')), \
                    patch.object(provider,'complete',side_effect=AssertionError('No AI selection replay')), \
                    patch('company_initiation.historic_construction.workflow.datetime',ReplayedLater):
                fresh,sources=discover_releases(journal,archive,[index],'2026-10-25',latest_completed_year=2025,
                    historical_years=[2025],fiscal_calendar={'fiscal_year_end':'12-31'},checkpoint=checkpoint)
            self.assertEqual(fresh['status'],'discovered_pending_numeric_validation')
            self.assertEqual(sources[0]['observed_available_at'],'2026-10-24')
            self.assertEqual(len(fresh['coverage_obligations']),1)
            self.assertEqual(fresh['coverage_obligations'][0]['status'],'pending_primary_coverage')
            with self.assertRaisesRegex(ValueError,'never reached primary coverage'):_validate_discovery_coverage(fresh,[])
            self.assertEqual({p:p.read_bytes() for p in before},before)
            self.assertEqual(journal.state['usage'],record['usage'])
            receipt=json.loads((second/'official_discovery_continuation.json').read_text())
            self.assertEqual(receipt['mode'],'completed_discovery')
            self.assertTrue(all(value.startswith('2026-10-24') for value in receipt['original_retrieval_times']))
            self.assertEqual(prior['discovery_contract_fingerprint'],fresh['discovery_contract_fingerprint'])

    def test_scope_changes_are_not_reusable_and_source_metadata_or_bytes_changes_fail_explicitly(self):
        from company_initiation.historic_construction.evidence import inventory_local_sources
        with tempfile.TemporaryDirectory() as temporary:
            archive,outputs,record,provider,config,index,_,_=self.prepare(Path(temporary))
            for changes in (dict(as_of='2026-10-26'),dict(company='Different Company'),dict(historical_years=[2024,2025]),
                            dict(fiscal_calendar={'fiscal_year_end':'06-30'}),dict(latest_completed_year=2024)):
                self.assertIsNone(self.restore(archive,record,index,**changes))
            metadata=archive/'sources.csv';metadata.write_text('filename,title\nfinancial_reports/seed.pdf,Changed user title\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'User source metadata changed'):self.restore(archive,record,index)
            metadata.unlink()
            source=archive/'financial_reports'/'seed.pdf';source.write_bytes(b'%PDF changed original')
            with self.assertRaisesRegex(ValueError,'Original archive changed'):self.restore(archive,record,index)

    def test_tampered_html_or_download_and_unrelated_new_original_cannot_silently_restart_discovery(self):
        for change in ('html','download','new'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temporary:
                archive,outputs,record,provider,config,index,_,sources=self.prepare(Path(temporary))
                if change=='html':next((outputs/'construct_research_first').glob('official_index_*.html')).write_bytes(b'<p>tampered original</p>')
                elif change=='download':(archive/sources[0]['local_path']).write_bytes(b'%PDF changed downloaded original')
                else:(archive/'financial_reports'/'new.pdf').write_bytes(b'%PDF new unrelated source')
                with self.assertRaisesRegex(ValueError,'changed|outside|Changed'):
                    self.restore(archive,record,index)

    def test_legacy_replay_revalidates_dates_and_selector_settings_instead_of_trusting_hashes(self):
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.workflow import discover_releases
        for change in ('date','prompt','provider','contract'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temporary:
                archive,outputs,record,provider,config,index,_,_=self.prepare(Path(temporary));checkpoint=self.restore(archive,record,index)
                checkpoint['freshness'].pop('discovery_contract_fingerprint')
                if change=='date':checkpoint['calls'][0]['result']['releases'][0]['published_at']='2026-03-02'
                elif change=='prompt':checkpoint['calls'][0]['request']['instructions']='Different selector semantics'
                elif change=='provider':checkpoint['provider']['max_output_tokens']=16000
                else:checkpoint['freshness']['discovery_contract_fingerprint']='changed'
                second=outputs/'construct_research_second';second.mkdir();journal=RunJournal(second,provider,config,previous=record)
                with patch('company_initiation.historic_construction.evidence.download',side_effect=AssertionError('No network fallback')), \
                        patch.object(provider,'complete',side_effect=AssertionError('No paid fallback')), \
                        self.assertRaisesRegex(ValueError,'publication|incompatible|contract changed'):
                    discover_releases(journal,archive,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025],
                        fiscal_calendar={'fiscal_year_end':'12-31'},checkpoint=checkpoint)

    def test_newer_navigation_failure_uses_prior_navigation_complete_checkpoint_without_erasing_new_claims(self):
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.workflow import restore_discovery_checkpoint, discover_releases
        from company_initiation.historic_construction.evidence import inventory_local_sources
        with tempfile.TemporaryDirectory() as temporary:
            archive,outputs,record,provider,config,index,_,_=self.prepare(Path(temporary))
            failed=outputs/'construct_research_failed';failed.mkdir();later=RunJournal(failed,provider,config,previous=record)
            later.state['parent_run']=record['directory'];later.artifact('source_freshness_partial.json',dict(
                checked_as_of='2026-10-25',status='incomplete_discovery',navigation_complete=False,error='context_length_exceeded'))
            parent=json.loads((failed/'record.json').read_text());checkpoint=restore_discovery_checkpoint(parent,[record,parent],archive,
                inventory_local_sources(archive),[index],'2026-10-25',company=config['company'],historical_years=[2025],
                latest_completed_year=2025,fiscal_calendar={'fiscal_year_end':'12-31'})
            self.assertEqual(checkpoint['run'],record['directory'])
            restored=dict(obligations=[dict(detail='Unscoped required release remains unresolved',fiscal_year=None,period_kind='unknown',
                period_end=None,evidence=[],period_scope_verified=False)],audit=[])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=AssertionError('No network fallback')), \
                    patch.object(provider,'complete',side_effect=AssertionError('No paid fallback')), \
                    self.assertRaisesRegex(ValueError,'Unscoped|unscoped|scope'):
                discover_releases(later,archive,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025],
                    fiscal_calendar={'fiscal_year_end':'12-31'},restored_coverage=restored,checkpoint=checkpoint)

    def test_legacy_navigation_complete_partial_resumes_download_phase_without_accepting_history(self):
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.workflow import discover_releases
        with tempfile.TemporaryDirectory() as temporary:
            archive,outputs,record,provider,config,index,prior,sources=self.prepare(Path(temporary))
            directory=Path(record['directory']);downloads=json.loads((directory/'official_downloaded_originals.json').read_text())
            partial=dict(prior,status='incomplete_discovery',selected_releases=[item['selection'] for item in downloads],
                downloaded_releases=[],error_type='AIError',error='Synthetic cooperative source checkpoint before publication processing')
            partial.pop('navigation_complete');partial.pop('discovery_contract_fingerprint');partial.pop('releases')
            path=directory/'source_freshness_partial.json';path.write_text(json.dumps(partial),encoding='utf-8')
            record['artifacts'].pop('source_freshness.json');record['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
            (directory/'record.json').write_text(json.dumps(record),encoding='utf-8')
            checkpoint=self.restore(archive,record,index)
            self.assertEqual(checkpoint['mode'],'resume_after_navigation')
            second=outputs/'construct_research_second';second.mkdir();journal=RunJournal(second,provider,config,previous=record)
            with patch('company_initiation.historic_construction.evidence.download',side_effect=AssertionError('Saved downloads must be reused')), \
                    patch.object(provider,'complete',side_effect=AssertionError('Completed navigation must be reused')):
                fresh,reused=discover_releases(journal,archive,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025],
                    fiscal_calendar={'fiscal_year_end':'12-31'},checkpoint=checkpoint)
            self.assertEqual([item['sha256'] for item in reused],[item['sha256'] for item in sources])
            self.assertEqual(fresh['status'],'discovered_pending_numeric_validation')
            self.assertEqual(fresh['coverage_obligations'][0]['status'],'pending_primary_coverage')


class NumericEntryRepairTests(unittest.TestCase):
    def fixture(self,root,*,repairs=2):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        from company_initiation.historic_construction.workflow import _financial_mapping_schema, _materialize_financial_observations
        data,answer,_,_,catalog,units=HistoricalVersionRevisionTests().fixture()
        units.append(dict(source_id='old',unit_id='page:2',text='Supplementary original 2020 cash-flow statement: 100.0.',
            numbers=[dict(raw='100.0',index=0)]))
        expected={key:copy.deepcopy(answer[key]) for key in ('observations','gaps','reporting_changes')}
        initial=copy.deepcopy(expected)
        for entry in initial['observations'][:2]:entry['terms'][0]['reference']['number_index']=1
        store=SourceStore(Path('.'));store.sources=list(catalog.values())
        for unit in units:store._units.setdefault(unit['source_id'],{})[unit['unit_id']]=unit
        roles=integrated_role_contract();context=dict(company='SYNTHETIC',periods=data['periods'],evidence=units,
            engine_contract=dict(roles=roles),required_disclosure_coverage=[])
        provider=OpenAIProvider(api_key='SYNTHETIC-NO-NETWORK')
        journal=RunJournal(root,provider,dict(limits=dict(usd=10,repairs=repairs,retries=0,calls=30,generated_tokens=1000000)))
        def validate(response,period_ids):
            _materialize_financial_observations(response,store=store,catalog=catalog,periods=context['periods'],currency='EUR',
                roles=roles,segments=[],evidence=units,requested_period_ids=period_ids,primary_only=True)
            return response
        return journal,context,_financial_mapping_schema(['2020-FY']),initial,expected,validate

    def response(self,payload,expected):
        patches=[]
        for target in payload['repair']['targets']:
            observation=copy.deepcopy(payload['prior_answer']['observations'][target['entry_index']])
            observation['terms']=copy.deepcopy(expected['observations'][target['entry_index']]['terms'])
            patches.append(dict(entry_id=target['entry_id'],entry_index=target['entry_index'],entry_digest=target['entry_digest'],observation=observation))
        return dict(patches=patches,additions=[],gap_additions=[],reporting_change_additions=[])

    def complete(self,journal):
        journal.provider.last_response=dict(status='completed',usage=dict(input_tokens=1000,output_tokens=100,total_tokens=1100))

    def test_exact_failed_entry_patches_freeze_valid_versions_and_resume_without_calls(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        from company_initiation.shared_runtime import RunJournal, digest
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);first=root/'first';first.mkdir();second=root/'second';second.mkdir()
            journal,context,schema,initial,expected,validate=self.fixture(first);requests=[]
            def complete(**kwargs):
                requests.append(copy.deepcopy(kwargs));self.complete(journal);payload=kwargs['payload']
                if 'repair' not in payload:return copy.deepcopy(initial)
                self.assertEqual(payload['prior_answer'],initial);self.assertEqual(payload['evidence'],context['evidence'])
                targets=payload['repair']['targets'];self.assertEqual([t['entry_index'] for t in targets],[0,1])
                self.assertNotEqual(targets[0]['entry_id'],targets[1]['entry_id'])
                self.assertEqual(targets[0]['entry_digest'],digest(initial['observations'][0]))
                self.assertEqual(targets[1]['allowed_fields'],['terms'])
                return self.response(payload,expected)
            with patch.object(journal.provider,'complete',side_effect=complete):
                answer=_period_bounded_mapping_stage(journal,'company_year_mapping','Unchanged original prompt',context,schema,validate)
            self.assertEqual(answer,expected);self.assertEqual(answer['observations'][2:],initial['observations'][2:])
            self.assertEqual(requests[0]['payload'],dict(context,stage='company_year_mapping',validation_errors=[]))
            self.assertEqual(requests[0]['schema'],schema);self.assertEqual(len(requests),2)
            saved=json.loads((first/'record.json').read_text());resumed=RunJournal(second,journal.provider,journal.configuration,previous=saved)
            with patch.object(journal.provider,'complete',side_effect=AssertionError('Cached initial answer and exact patch must be reused')):
                self.assertEqual(_period_bounded_mapping_stage(resumed,'company_year_mapping','Unchanged original prompt',context,schema,validate),expected)
            self.assertEqual(resumed.state['usage'],saved['usage'])

    def test_patch_contract_rejects_frozen_mutation_erasure_or_unscoped_addition(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        for case in ('digest','valid_entry','basis','erase','omit','addition'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temporary:
                journal,context,schema,initial,expected,validate=self.fixture(Path(temporary));calls=[]
                def complete(**kwargs):
                    calls.append(kwargs);self.complete(journal);payload=kwargs['payload']
                    if 'repair' not in payload:return copy.deepcopy(initial)
                    response=self.response(payload,expected)
                    if case=='digest':response['patches'][0]['entry_digest']='changed'
                    elif case=='valid_entry':response['patches'][0]['entry_id']='frozen_valid_entry'
                    elif case=='basis':response['patches'][0]['observation']['basis']='invented restatement'
                    elif case=='erase':response['patches'][0]['observation']['terms']=[]
                    elif case=='omit':response['patches'].pop()
                    else:response['additions'].append(copy.deepcopy(expected['observations'][0]))
                    return response
                with patch.object(journal.provider,'complete',side_effect=complete),self.assertRaises(ValueError):
                    _period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,validate)
                self.assertEqual(journal.entries[0]['result'],initial);self.assertEqual(len(calls),2)

    def test_blind_repair_uses_only_its_own_prior_answer_and_stops_on_no_progress(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema,initial,expected,validate=self.fixture(Path(temporary));requests=[]
            context['concepts']=[{key:entry[key] for key in ('row_id','period_id','unit')} for entry in expected['observations']]
            def complete(**kwargs):
                requests.append(kwargs);self.complete(journal);payload=kwargs['payload']
                self.assertFalse({'candidates','independent','disputes','review_challenge'}&set(payload))
                if 'repair' not in payload:return copy.deepcopy(initial)
                self.assertEqual(payload['prior_answer'],initial)
                response=self.response(payload,initial);response['gap_additions']=['New prose is not numeric progress']
                return response
            with patch.object(journal.provider,'complete',side_effect=complete),self.assertRaisesRegex(ValueError,'no progress'):
                _period_bounded_mapping_stage(journal,'company_year_blind','Independent originals only',context,schema,validate)
            self.assertEqual(len(requests),2)

    def test_second_bounded_patch_freezes_the_entry_fixed_in_the_first_patch(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema,initial,expected,validate=self.fixture(Path(temporary));repairs=[]
            def complete(**kwargs):
                self.complete(journal);payload=kwargs['payload']
                if 'repair' not in payload:return copy.deepcopy(initial)
                repairs.append(copy.deepcopy(payload));response=self.response(payload,expected)
                if len(repairs)==1:response['patches'][1]['observation']=copy.deepcopy(initial['observations'][1])
                else:
                    self.assertEqual([t['entry_index'] for t in payload['repair']['targets']],[1])
                    self.assertEqual(payload['prior_answer']['observations'][0],expected['observations'][0])
                return response
            with patch.object(journal.provider,'complete',side_effect=complete):
                result=_period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,validate)
            self.assertEqual(result,expected);self.assertEqual(len(repairs),2)

    def test_missing_coverage_addition_preserves_existing_entries_and_must_match_scope(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage, _validate_disclosure_coverage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema,_,expected,validate=self.fixture(Path(temporary));initial=copy.deepcopy(expected)
            period=dict(context['periods'][0],id='2020-H1',kind='H1',end='2020-06-30');context['periods'].append(period)
            schema['properties']['observations']['items']['properties']['period_id']['enum'].append('2020-H1')
            requirements=[dict(period_id='2020-H1',family='cash_flow')]
            context['required_disclosure_coverage']=requirements
            def covered(answer,period_ids):
                validate(answer,period_ids)
                facts=[dict(entry,value=1) for entry in answer['observations']]
                _validate_disclosure_coverage(facts,[r for r in requirements if r['period_id'] in period_ids],{})
                return answer
            def complete(**kwargs):
                self.complete(journal);payload=kwargs['payload']
                if 'repair' not in payload:return copy.deepcopy(initial)
                self.assertEqual(payload['repair']['targets'],[]);self.assertEqual(payload['repair']['allowed_additions'],requirements)
                addition=dict(copy.deepcopy(expected['observations'][0]),period_id='2020-H1')
                return dict(patches=[],additions=[addition],gap_additions=[],reporting_change_additions=[])
            with patch.object(journal.provider,'complete',side_effect=complete):
                result=_period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,covered)
            self.assertEqual(result['observations'][:-1],initial['observations']);self.assertEqual(result['observations'][-1]['period_id'],'2020-H1')

    def test_output_cap_splits_patch_targets_without_regenerating_prior_answer(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema,initial,expected,validate=self.fixture(Path(temporary));requests=[]
            context['periods'].append(dict(context['periods'][0],id='2020-H1',kind='H1',end='2020-06-30'))
            schema['properties']['observations']['items']['properties']['period_id']['enum'].append('2020-H1')
            for answer in (initial,expected):answer['observations'][1]['period_id']='2020-H1'
            def complete(**kwargs):
                requests.append(copy.deepcopy(kwargs));payload=kwargs['payload']
                if 'repair' not in payload:self.complete(journal);return copy.deepcopy(initial)
                self.assertEqual(payload['prior_answer'],initial);self.assertEqual(payload['evidence'],context['evidence'])
                if len(payload['repair']['targets'])>1:MappingOutputLimitRecoveryTests().cap(journal.provider)
                self.complete(journal);return self.response(payload,expected)
            with patch.object(journal.provider,'complete',side_effect=complete):
                answer=_period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,validate)
            self.assertEqual(answer,expected);self.assertEqual(len(requests),4)
            self.assertEqual(sum(bool(entry.get('error')) for entry in journal.entries),1)
            audits=[json.loads(p.read_text()) for p in Path(temporary).glob('*entry_repair_decomposition*.json')]
            self.assertEqual(len(audits),1);self.assertFalse(audits[0]['partial_response_used']);self.assertEqual(audits[0]['status'],'complete')

    def test_primary_unit_coverage_can_patch_one_matching_binding_without_changing_value(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage, _validate_disclosure_coverage
        for change_amount in (False,True):
            with self.subTest(change_amount=change_amount),tempfile.TemporaryDirectory() as temporary:
                journal,context,schema,_,initial,validate=self.fixture(Path(temporary))
                requirement=dict(period_id='2020-FY',family='cash_flow',obligation_id='retained_primary',
                    required_reporting_basis='reported',source_refs=[dict(source_id='old',unit_id='page:2')])
                context['required_disclosure_coverage']=[requirement]
                def covered(answer,period_ids):
                    validate(answer,period_ids)
                    facts=[dict(entry,value=1,source_refs=[term['reference'] for term in entry['terms']]) for entry in answer['observations']]
                    _validate_disclosure_coverage(facts,[requirement],{});return answer
                def complete(**kwargs):
                    self.complete(journal);payload=kwargs['payload']
                    if 'repair' not in payload:return copy.deepcopy(initial)
                    targets=payload['repair']['targets'];self.assertEqual(len(targets),2);self.assertFalse(any(t['required'] for t in targets))
                    target=targets[0];entry=copy.deepcopy(initial['observations'][0])
                    if change_amount:entry['terms']=copy.deepcopy(initial['observations'][1]['terms'])
                    else:entry['terms'][0]['reference']['unit_id']='page:2'
                    return dict(patches=[dict(entry_id=target['entry_id'],entry_index=target['entry_index'],entry_digest=target['entry_digest'],observation=entry)],
                        additions=[],gap_additions=[],reporting_change_additions=[])
                with patch.object(journal.provider,'complete',side_effect=complete):
                    if change_amount:
                        with self.assertRaisesRegex(ValueError,'cannot change an already validated numeric amount'):
                            _period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,covered)
                    else:
                        result=_period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,covered)
                        self.assertEqual(len(result['observations']),len(initial['observations']))
                        self.assertEqual(result['observations'][1:],initial['observations'][1:])
                        self.assertEqual(result['observations'][0]['terms'][0]['source_raw'],'100.0')

    def test_legacy_full_regeneration_repair_is_not_reused_as_an_entry_patch(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        from company_initiation.shared_runtime import RunJournal
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);first=root/'first';first.mkdir();second=root/'second';second.mkdir()
            journal,context,schema,initial,expected,validate=self.fixture(first)
            def old_complete(**kwargs):
                self.complete(journal);return copy.deepcopy(initial if not kwargs['payload']['validation_errors'] else expected)
            with patch.object(journal.provider,'complete',side_effect=old_complete):
                journal.ask('company_year_mapping','Original',dict(context,validation_errors=[]),schema,0)
                journal.ask('company_year_mapping','Original',dict(context,validation_errors=['Legacy full-answer regeneration']),schema,1)
            saved=json.loads((first/'record.json').read_text());resumed=RunJournal(second,journal.provider,journal.configuration,previous=saved);requests=[]
            def new_complete(**kwargs):
                requests.append(kwargs);self.complete(resumed);self.assertIn('repair',kwargs['payload'])
                return self.response(kwargs['payload'],expected)
            with patch.object(resumed.provider,'complete',side_effect=new_complete):
                result=_period_bounded_mapping_stage(resumed,'company_year_mapping','Original',context,schema,validate)
            self.assertEqual(result,expected);self.assertEqual(len(requests),1);self.assertEqual(len(resumed.entries),3)
            self.assertEqual(resumed.entries[:2],saved['calls'])

    def test_unscoped_validator_error_never_triggers_full_answer_regeneration(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema,_,expected,_=self.fixture(Path(temporary));requests=[]
            def complete(**kwargs):requests.append(kwargs);self.complete(journal);return copy.deepcopy(expected)
            def validate(answer,period_ids):raise ValueError('Unscoped semantic identity disagreement')
            with patch.object(journal.provider,'complete',side_effect=complete),self.assertRaisesRegex(ValueError,'full-answer regeneration is disabled'):
                _period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,validate)
            self.assertEqual(len(requests),1);self.assertEqual(requests[0]['payload'],dict(context,stage='company_year_mapping',validation_errors=[]))

    def test_missing_requested_concept_or_version_is_added_without_regenerating_valid_entries(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage, _validate_reconstruction_revision
        for mode in ('blind_concept','candidate_version','wrong_version'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temporary:
                journal,context,schema,_,expected,validate=self.fixture(Path(temporary));initial=copy.deepcopy(expected)
                missing=initial['observations'].pop(-1 if mode=='blind_concept' else 1)
                context['concepts']=[{key:entry[key] for key in ('row_id','period_id','unit')} for entry in expected['observations']]
                if mode!='blind_concept':context['candidates']=copy.deepcopy(expected['observations'])
                disputed={(entry['row_id'],entry['period_id']) for entry in expected['observations']}
                def complete_scope(answer,period_ids):
                    validate(answer,period_ids)
                    _validate_reconstruction_revision(answer['observations'],disputed,None if mode=='blind_concept' else expected['observations'])
                    return answer
                def complete(**kwargs):
                    self.complete(journal);payload=kwargs['payload']
                    if 'repair' not in payload:return copy.deepcopy(initial)
                    self.assertEqual(payload['prior_answer'],initial);self.assertEqual(payload['repair']['targets'],[])
                    allowed=payload['repair']['allowed_additions'];self.assertEqual(len(allowed),1)
                    if mode=='blind_concept':
                        self.assertNotIn('candidates',payload);self.assertNotIn('required_identity',allowed[0])
                        self.assertEqual(allowed[0],dict(row_id=missing['row_id'],period_id=missing['period_id']))
                    else:self.assertEqual(allowed[0]['required_identity']['restatement'],'restated')
                    addition=copy.deepcopy(missing)
                    if mode=='wrong_version':addition.update(restatement='original',restatement_vintage=None)
                    return dict(patches=[],additions=[addition],gap_additions=[],reporting_change_additions=[])
                with patch.object(journal.provider,'complete',side_effect=complete):
                    if mode=='wrong_version':
                        with self.assertRaisesRegex(ValueError,'outside the explicitly missing coverage scope'):
                            _period_bounded_mapping_stage(journal,'company_year_mapping_revision','Original',context,schema,complete_scope)
                    else:
                        result=_period_bounded_mapping_stage(journal,'company_year_blind_reextraction' if mode=='blind_concept' else 'company_year_mapping_revision','Original',context,schema,complete_scope)
                        self.assertEqual(result['observations'][:-1],initial['observations']);self.assertEqual(result['observations'][-1],missing)
                        self.assertEqual(len(journal.entries),2)


class MappingOutputLimitRecoveryTests(unittest.TestCase):
    def setup_case(self, root, *, count=4):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.initiation import _object, _array, TEXT
        ids=['2025-'+kind for kind in ('Q1','H1','9M','FY')][:count]
        periods=[dict(id=pid,fiscal_year=2025) for pid in ids]
        evidence=[dict(source_id='primary',unit_id='page:1',text='COMPLETE original with all periods and restatements',
            numbers=[dict(index=0,raw='100',value=100)]),
            dict(source_id='primary',unit_id='page:2',text='COMPLETE surrounding accounting note',numbers=[])]
        context=dict(company='SYNTHETIC',year=2025,task='operating performance',periods=periods,evidence=evidence,
            required_disclosure_coverage=[dict(period_id=pid,family='sales') for pid in ids])
        observation=_object(row_id=TEXT,period_id=TEXT,value={'type':'number'},basis=TEXT,metric_type=TEXT,unit=TEXT)
        observation['properties']['period_id']={'type':'string','enum':ids}
        schema=_object(observations=_array(observation),gaps=_array(TEXT),reporting_changes=_array(TEXT))
        provider=OpenAIProvider(api_key='SYNTHETIC-NO-NETWORK')
        journal=RunJournal(root,provider,dict(limits=dict(usd=10,repairs=0,retries=2,calls=30,generated_tokens=1000000)))
        return journal,context,schema

    def cap(self, provider):
        from company_initiation.shared_ai import AIError
        # Same provider shape as the real failure, including unusable partial JSON.
        provider.last_response=dict(status='incomplete',incomplete_details=dict(reason='max_output_tokens'),
            usage=dict(input_tokens=1000,output_tokens=provider.max_output_tokens,total_tokens=1000+provider.max_output_tokens),
            output=[dict(type='message',content=[dict(type='output_text',text='{"observations":[{"row_id":"sales","value":987654321,')])])
        raise AIError('AI response was incomplete or failed; it cannot be accepted.')

    def answer(self, provider, payload):
        provider.last_response=dict(status='completed',usage=dict(input_tokens=1000,output_tokens=100,total_tokens=1100))
        facts=[dict(row_id='sales',period_id=period['id'],value=100,basis='original',metric_type='flow',unit='EURm') for period in payload['periods']]
        # Multiple source versions must remain separate through the merge.
        if any(item['period_id']=='2025-FY' for item in facts):
            facts.append(dict(row_id='sales',period_id='2025-FY',value=101,basis='restated',metric_type='flow',unit='EURm'))
        return dict(observations=facts,gaps=[],reporting_changes=['Preserve original and restated definitions'])

    def validate(self, answer, period_ids):
        from company_initiation.historic_construction.workflow import _validate_disclosure_coverage
        _validate_disclosure_coverage(answer['observations'],
            [dict(period_id=pid,family='sales') for pid in period_ids],{})
        return answer

    def test_capped_year_splits_periods_preserves_complete_evidence_versions_and_exact_resume(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        from company_initiation.shared_runtime import RunJournal
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);first=root/'first';first.mkdir();second=root/'second';second.mkdir()
            journal,context,schema=self.setup_case(first);requests=[]
            def complete(**kwargs):
                requests.append(copy.deepcopy(kwargs))
                if len(kwargs['payload']['periods'])>2:self.cap(journal.provider)
                return self.answer(journal.provider,kwargs['payload'])
            with patch.object(journal.provider,'complete',side_effect=complete):
                answer=_period_bounded_mapping_stage(journal,'company_year_mapping','Original prompt',context,schema,self.validate)
            self.assertEqual(len(requests),3)
            self.assertEqual({item['period_id'] for item in answer['observations']},{p['id'] for p in context['periods']})
            self.assertEqual(len([item for item in answer['observations'] if item['period_id']=='2025-FY']),2)
            self.assertNotIn(987654321,[item['value'] for item in answer['observations']])
            for request in requests:self.assertEqual(request['payload']['evidence'],context['evidence'])
            self.assertNotIn('period_decomposition',requests[0]['payload'])
            self.assertEqual(requests[0]['schema'],schema)
            audits=[json.loads(p.read_text()) for p in first.glob('*_period_decomposition_*.json')]
            self.assertEqual(len(audits),1);self.assertEqual(audits[0]['status'],'complete')
            self.assertFalse(audits[0]['partial_response_used']);self.assertEqual(len(journal.entries),3)
            saved=json.loads((first/'record.json').read_text());usage=copy.deepcopy(saved['usage'])
            resumed=RunJournal(second,journal.provider,journal.configuration,previous=saved)
            with patch.object(journal.provider,'complete',side_effect=AssertionError('Exact cached cohorts must be free')):
                replay=_period_bounded_mapping_stage(resumed,'company_year_mapping','Original prompt',context,schema,self.validate)
            self.assertEqual(replay,answer);self.assertEqual(resumed.state['usage'],usage)

    def test_normal_success_retains_exact_request_and_does_not_decompose(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema=self.setup_case(Path(temporary));requests=[]
            def complete(**kwargs):
                requests.append(kwargs);return self.answer(journal.provider,kwargs['payload'])
            with patch.object(journal.provider,'complete',side_effect=complete):
                _period_bounded_mapping_stage(journal,'company_year_mapping','Unchanged',context,schema,self.validate)
            self.assertEqual(len(requests),1)
            self.assertEqual(requests[0]['payload'],dict(context,stage='company_year_mapping',validation_errors=[]))
            self.assertEqual(requests[0]['schema'],schema)
            self.assertFalse(list(Path(temporary).glob('*_period_decomposition_*.json')))

    def test_blind_and_reblind_cohorts_only_receive_originals_and_requested_concepts(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema=self.setup_case(Path(temporary));requests=[]
            context['concepts']=[dict(row_id='sales',label='Sales',period_id=p['id'],unit='GBPm') for p in context['periods']]
            def complete(**kwargs):
                requests.append(copy.deepcopy(kwargs))
                if len(kwargs['payload']['periods'])>2:self.cap(journal.provider)
                return self.answer(journal.provider,kwargs['payload'])
            with patch.object(journal.provider,'complete',side_effect=complete):
                for stage in ('company_year_blind','company_year_blind_reextraction'):
                    _period_bounded_mapping_stage(journal,stage,'Independent reconstruction',context,schema,self.validate)
            self.assertEqual(len(requests),6)
            for request in requests:
                payload=request['payload'];ids={p['id'] for p in payload['periods']}
                self.assertEqual(payload['evidence'],context['evidence'])
                self.assertEqual({c['period_id'] for c in payload['concepts']},ids)
                self.assertTrue(all(set(c)=={'row_id','label','period_id','unit'} for c in payload['concepts']))
                for forbidden in ('candidates','independent','disputes','validation_verdict','failed_response'):
                    self.assertNotIn(forbidden,payload)
                self.assertTrue(all(set(item)=={'period_id','family'} for item in payload['required_disclosure_coverage']))

    def test_missing_required_period_or_out_of_cohort_fact_still_blocks(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        for failure in ('missing','extra'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temporary:
                journal,context,schema=self.setup_case(Path(temporary));requests=[]
                def complete(**kwargs):
                    requests.append(kwargs)
                    if len(kwargs['payload']['periods'])>2:self.cap(journal.provider)
                    answer=self.answer(journal.provider,kwargs['payload'])
                    if failure=='missing':answer['observations']=answer['observations'][:1]
                    else:answer['observations'][0]['period_id']='2025-FY'
                    return answer
                with patch.object(journal.provider,'complete',side_effect=complete):
                    with self.assertRaisesRegex(ValueError,'coverage|outside|unsupported value'):
                        _period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,self.validate)
                self.assertLessEqual(len(requests),4)
                self.assertFalse(list(Path(temporary).glob('*_period_merged_*.json')))

    def test_single_period_failure_stops_finite_decomposition_with_saved_charge(self):
        from company_initiation.shared_ai import AIError
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema=self.setup_case(Path(temporary));calls=[]
            def complete(**kwargs):
                calls.append(kwargs);self.cap(journal.provider)
            with patch.object(journal.provider,'complete',side_effect=complete):
                with self.assertRaisesRegex(AIError,'single-period mapping remains too large'):
                    _period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,self.validate)
            self.assertEqual([len(c['payload']['periods']) for c in calls],[4,2,1])
            self.assertEqual(len(journal.entries),3);self.assertIsNone(journal.state['pending_call'])
            self.assertTrue(journal.state['usage']['cost_is_complete'])

    def test_revision_cohorts_project_disputes_and_preserve_every_original_reporting_version(self):
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage, _validate_reconstruction_revision
        for drop_version in (False,True):
            with self.subTest(drop_version=drop_version),tempfile.TemporaryDirectory() as temporary:
                journal,context,schema=self.setup_case(Path(temporary));requests=[]
                disputed={('sales','2025-Q1'),('sales','2025-FY')}
                all_facts=self.answer(journal.provider,context)['observations']
                current=[item for item in all_facts if (item['row_id'],item['period_id']) in disputed]
                context.update(concepts=[dict(row_id=row,period_id=period,label='Sales',unit='GBPm') for row,period in sorted(disputed)],
                    candidates=copy.deepcopy(current),independent=copy.deepcopy(current),
                    disputes=[dict(row_id=row,period_id=period,status='unresolved') for row,period in sorted(disputed)])
                def complete(**kwargs):
                    requests.append(copy.deepcopy(kwargs));payload=kwargs['payload']
                    if len(payload['periods'])>1:self.cap(journal.provider)
                    answer=self.answer(journal.provider,payload)
                    if drop_version:answer['observations']=[item for item in answer['observations'] if item['basis']!='restated']
                    return answer
                def validate(answer,period_ids):
                    _validate_reconstruction_revision(answer['observations'],
                        {pair for pair in disputed if pair[1] in period_ids},
                        [item for item in current if item['period_id'] in period_ids])
                    return answer
                with patch.object(journal.provider,'complete',side_effect=complete):
                    if drop_version:
                        with self.assertRaisesRegex(ValueError,'retain every candidate reporting version'):
                            _period_bounded_mapping_stage(journal,'company_year_mapping_revision','Revision',context,schema,validate)
                    else:
                        answer=_period_bounded_mapping_stage(journal,'company_year_mapping_revision','Revision',context,schema,validate)
                        self.assertCountEqual(answer['observations'],current)
                for request in requests[1:]:
                    payload=request['payload'];allowed={p['id'] for p in payload['periods']}
                    self.assertEqual(payload['evidence'],context['evidence'])
                    for field in ('concepts','candidates','independent','disputes'):
                        self.assertTrue(all(item['period_id'] in allowed for item in payload[field]))

    def test_unproved_output_cap_message_cannot_trigger_decomposition(self):
        from company_initiation.shared_ai import AIError
        from company_initiation.historic_construction.workflow import _period_bounded_mapping_stage
        with tempfile.TemporaryDirectory() as temporary:
            journal,context,schema=self.setup_case(Path(temporary))
            with patch.object(journal,'stage',side_effect=AIError('max_output_tokens unverified caller text')) as stage:
                with self.assertRaisesRegex(AIError,'unverified'):
                    _period_bounded_mapping_stage(journal,'company_year_mapping','Original',context,schema,self.validate)
                self.assertEqual(stage.call_count,1)
            self.assertFalse(list(Path(temporary).glob('*_period_decomposition_*.json')))


class DiscoveryObligationProjectionTests(unittest.TestCase):
    def obligations(self,repeats=1):
        claim=dict(detail='Exact cumulative sales require primary support',fiscal_year=2025,period_kind='9M',
            period_end='2025-09-30',as_of='2026-10-25',period_scope_verified=True,
            evidence=[dict(page_id='page_original',page_url='https://synthetic.invalid/results',sha256='original-hash',quotation='2025 nine-month sales')])
        return [dict(id='discovery_nine_months',status='pending_primary_coverage',fiscal_year=2025,period_kind='9M',
            period_end='2025-09-30',first_navigation_round=1,last_navigation_round=repeats,
            restored_from=dict(run='top_level_run_'+str(repeats),artifact='retained_gap_audit.json'),
            claims=[dict(copy.deepcopy(claim),restored_from=dict(run='run_'+str(i),answer={'sha256':'audit_'+str(i)},
                originals=[dict(run='run_'+str(i),sha256='original-hash')])) for i in range(repeats)])]

    def test_repeated_origins_project_identically_without_losing_scope_or_exact_evidence(self):
        from company_initiation.historic_construction.workflow import _discovery_obligations_for_research
        earlier=self.obligations(31);later=self.obligations(46);before=copy.deepcopy(later)
        a=_discovery_obligations_for_research(earlier);b=_discovery_obligations_for_research(later)
        self.assertEqual(a,b);self.assertEqual(_discovery_obligations_for_research(b),b)
        self.assertEqual(len(b[0]['claims']),1);self.assertEqual(b[0]['id'],later[0]['id'])
        self.assertEqual(b[0]['claims'][0]['evidence'],later[0]['claims'][0]['evidence'])
        self.assertEqual(b[0]['claims'][0]['period_end'],'2025-09-30');self.assertEqual(b[0]['claims'][0]['as_of'],'2026-10-25')
        self.assertEqual(later,before);self.assertEqual(len(later[0]['claims']),46)

    def test_distinct_conflicting_quotation_hash_or_period_remains_in_request(self):
        from company_initiation.historic_construction.workflow import _discovery_obligations_for_research
        for field,value in (('quotation','2025 third-quarter sales'),('sha256','changed-original-hash'),('period_end','2025-06-30')):
            with self.subTest(field=field):
                obligations=self.obligations(3);conflict=copy.deepcopy(obligations[0]['claims'][0])
                if field=='period_end':conflict[field]=value
                else:conflict['evidence'][0][field]=value
                obligations[0]['claims'].append(conflict)
                projected=_discovery_obligations_for_research(obligations)
                self.assertEqual(len(projected[0]['claims']),2)
                self.assertNotEqual(projected,_discovery_obligations_for_research(self.obligations(3)))

    def test_year_selection_payload_stays_exactly_compatible_across_audit_only_continuations(self):
        from types import SimpleNamespace
        from company_initiation.historic_construction.workflow import _company_year_sources
        requests=[];catalog={'annual':dict(id='annual',category='financial_reports',sha256='same-original')}
        def stage(name,prompt,payload,schema,validate):
            requests.append(copy.deepcopy(dict(name=name,prompt=prompt,payload=payload,schema=schema)))
            with self.assertRaisesRegex(ValueError,'require selected primary'):validate(dict(source_ids=[],reason='Missing separate release'))
            return validate(dict(source_ids=['annual'],reason='Later primary reproduces exact interim facts'))
        for count in (31,46):_company_year_sources(SimpleNamespace(stage=stage),'Synthetic',2025,'2026-10-25',catalog,discovery_obligations=self.obligations(count))
        self.assertEqual(requests[0],requests[1])

    def test_coverage_requests_and_limitations_are_stable_but_saved_audit_remains_complete(self):
        from types import SimpleNamespace
        from company_initiation.historic_construction.workflow import _year_disclosure_coverage, _disclosure_coverage_for_research, _task_disclosure_coverage
        _,answer,units=DisclosureCoverageTests().retained_fixture();units[0]['text']+=' full table context'*11000
        requests=[];inventories=[];limit_sets=[];raw_obligations=[]
        for count in (31,46):
            captured=[];saved={};limitations=[];obligations=self.obligations(count);raw_obligations.append(copy.deepcopy(obligations))
            def stage(name,prompt,payload,schema,validate):
                captured.append(copy.deepcopy(dict(name=name,prompt=prompt,payload=payload,schema=schema)))
                if name=='company_source_sections':
                    self.assertLess(len(payload['purpose']),1000)
                    self.assertEqual(len(payload['discovery_obligations'][0]['claims']),1)
                    return validate(dict(sections=[dict(source_id='annual',first_unit='page:2',last_unit='page:2',reason='Complete original table')],
                        gaps=['The primary note does not quantify the separate cost driver.']))
                self.assertEqual(payload['evidence'],units)
                return validate(copy.deepcopy(answer))
            journal=SimpleNamespace(stage=stage,artifact=lambda name,value:saved.update({name:copy.deepcopy(value)}))
            result=_year_disclosure_coverage(journal,'Synthetic',2025,[dict(id='2025-9M')],units,['annual'],
                limitations=limitations,discovery_obligations=obligations)
            requests.append(captured);inventories.append(result);limit_sets.append(limitations)
            self.assertEqual(result['discovery_obligations'],obligations)
            self.assertEqual(saved['disclosure_coverage_2025.json']['discovery_obligations'],obligations)
            self.assertEqual(obligations,raw_obligations[-1]);self.assertLess(len(json.dumps(limitations)),1200)
        self.assertEqual(requests[0],requests[1]);self.assertEqual(limit_sets[0],limit_sets[1])
        self.assertEqual(_disclosure_coverage_for_research([inventories[0]]),_disclosure_coverage_for_research([inventories[1]]))
        self.assertEqual(_task_disclosure_coverage(inventories[0],['sales']),_task_disclosure_coverage(inventories[1],['sales']))
        self.assertEqual(len(inventories[1]['discovery_obligations'][0]['claims']),46)


class DiscoveryMetadataReuseTests(unittest.TestCase):
    def fixture(self, root, *, date_phrase='15 March 2017'):
        outputs=root/'outputs';outputs.mkdir();run=outputs/'construct_research_fixture';run.mkdir()
        source=dict(id='official_original',sha256='a'*64,local_path='financial_reports/opaque.pdf',
            category='financial_reports',format='pdf',title='Synthetic annual report 2016',
            url='https://example.test/reports/2016.pdf',published_at='2017-03-15',publication_evidence=date_phrase)
        path=run/'discovered_sources.json';path.write_text(json.dumps([source]),encoding='utf-8')
        record=dict(directory=str(run),calls=[],sources=[],artifacts={path.name:hashlib.sha256(path.read_bytes()).hexdigest()})
        (run/'record.json').write_text(json.dumps(record),encoding='utf-8');(run/'calls.jsonl').write_text('',encoding='utf-8')
        current=dict(source,id='local_current',local_path='financial_reports/renamed.pdf',title='renamed',
            url='local:///financial_reports/renamed.pdf',published_at=None,supplied_metadata={})
        current.pop('publication_evidence')
        return outputs,record,dict(sources=[current]),path

    def test_exact_bytes_restore_provenance_without_replacing_current_identity_or_supplied_metadata(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,path=self.fixture(Path(temporary));before=copy.deepcopy(inventory);raw=path.read_bytes()
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs);source=catalog['local_current']
            self.assertEqual(source['title'],'Synthetic annual report 2016')
            self.assertEqual(source['published_at'],'2017-03-15')
            self.assertEqual(source['local_path'],'financial_reports/renamed.pdf')
            self.assertEqual(source['sha256'],'a'*64)
            self.assertEqual(source['discovery_provenance']['original_source_id'],'official_original')
            self.assertEqual(audit['ai_calls'],0);self.assertEqual(inventory,before);self.assertEqual(path.read_bytes(),raw)
            inventory['sources'][0].update(title='User title',published_at='2017-03-16',url='https://example.test/user.pdf',
                supplied_metadata=dict(title='User title',publication_date='2017-03-16',url='https://example.test/user.pdf'))
            catalog,_=restore_discovered_metadata(inventory,[record],outputs);source=catalog['local_current']
            self.assertEqual(source['title'],'User title');self.assertEqual(source['published_at'],'2017-03-16')
            self.assertEqual(source['url'],'https://example.test/user.pdf');self.assertNotIn('publication_evidence',source)

    def test_changed_bytes_do_not_inherit_metadata_and_changed_artifact_blocks_reuse(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,path=self.fixture(Path(temporary));inventory['sources'][0]['sha256']='b'*64
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs)
            self.assertEqual(catalog['local_current']['title'],'renamed');self.assertEqual(audit['recovered'],[])
            path.write_text('[]',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'metadata content changed'):
                restore_discovered_metadata(inventory,[record],outputs)

    def test_unknown_or_mismatched_publication_date_never_becomes_verified_availability(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,_=self.fixture(Path(temporary),date_phrase='15 March 2018')
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs);source=catalog['local_current']
            self.assertIsNone(source['published_at']);self.assertFalse(source['point_in_time_eligible'])
            self.assertFalse(source['freshness_eligible']);self.assertEqual(len(audit['conflicts']),1)


    def test_structured_date_provenance_survives_restore_and_rejects_mismatch(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,path=self.fixture(Path(temporary),date_phrase=None)
            source=json.loads(path.read_text(encoding='utf-8'))[0]
            source.update(publication_availability='verified_structured_html',publication_date_id='date_1',
                publication_date_refs=[dict(date_id='date_1',date='2017-03-15',sha256='b'*64,
                    page_url='https://example.test/results',container_id='card_1',attribute='data-startdate',raw_value='1489536000000')])
            def save():
                path.write_text(json.dumps([source]),encoding='utf-8')
                record['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
                (path.parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
            save()
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs)
            self.assertEqual(catalog['local_current']['published_at'],'2017-03-15')
            self.assertEqual(catalog['local_current']['publication_date_refs'],source['publication_date_refs'])
            self.assertEqual(catalog['local_current']['publication_availability'],'verified_structured_html')
            self.assertEqual(audit['conflicts'],[])
            source['publication_date_refs'][0]['date']='2017-03-16';save()
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs)
            self.assertIsNone(catalog['local_current']['published_at'])
            self.assertEqual(len(audit['conflicts']),1)


    def test_original_dateline_resolves_prior_metadata_conflict_for_identical_bytes(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,path=self.fixture(Path(temporary))
            source=json.loads(path.read_text(encoding='utf-8'))[0]
            earlier=dict(source,id='earlier_metadata',published_at='2017-03-09',publication_evidence='9 March 2017')
            claims=[{key:item[key] for key in ('published_at','publication_evidence')} for item in (earlier,source)]
            source.update(publication_availability='verified_original_dateline',publication_claims=claims,
                observed_urls=[source['url'],'https://example.test/alias/identical-original.pdf'],
                point_in_time_eligible=True,freshness_eligible=True,
                publication_date_refs=[dict(source_id=source['id'],unit_id='page:1',sha256=source['sha256'],
                    date='2017-03-15',quotation='15 March 2017',method='Exact synthetic original dateline')])
            def save():
                path.write_text(json.dumps([earlier,source]),encoding='utf-8')
                record['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
                (path.parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
            save()
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs)
            restored=catalog['local_current']
            self.assertEqual(restored['published_at'],'2017-03-15')
            self.assertEqual(restored['publication_availability'],'verified_original_dateline')
            self.assertEqual(restored['publication_claims'],claims)
            self.assertEqual(restored['observed_urls'],source['observed_urls'])
            self.assertEqual(restored['publication_date_refs'],source['publication_date_refs'])
            self.assertTrue(restored['point_in_time_eligible']);self.assertEqual(audit['conflicts'],[])
            source['publication_date_refs'][0]['sha256']='b'*64;save()
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs)
            self.assertIsNone(catalog['local_current']['published_at'])
            self.assertFalse(catalog['local_current']['freshness_eligible'])
            self.assertEqual(len(audit['conflicts']),1)

    def interrupted_metadata_fixture(self,root,*,resolved=True):
        outputs,record,inventory,path=self.fixture(root)
        source=json.loads(path.read_text(encoding='utf-8'))[0]
        claims=[dict(url=source['url'],published_at='2017-03-15',publication_evidence='15 March 2017')]
        if resolved:claims.insert(0,dict(url=source['url'],published_at='2017-03-09',publication_evidence='9 March 2017'))
        source.update(publication_claims=claims,observed_urls=[source['url']],point_in_time_eligible=True,freshness_eligible=True)
        if resolved:
            source.update(publication_availability='verified_original_dateline',publication_date_refs=[dict(
                source_id=source['id'],unit_id='page:1',sha256=source['sha256'],date=source['published_at'],
                quotation=source['publication_evidence'],method='Exact original issuer dateline')])
        path.write_text(json.dumps([source]),encoding='utf-8');record['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        (path.parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
        selection=copy.deepcopy(source)
        if resolved:selection.update(published_at=None,publication_evidence='',publication_date_refs=[],
            publication_availability='conflicting_official_claims',point_in_time_eligible=False,freshness_eligible=False)
        def interrupted(name,selected):
            run=outputs/name;run.mkdir()
            descriptor=dict(url=source['url'],final_url=source['url'],sha256=selected.get('sha256',source['sha256']),
                source_id=source['id'],local_path=source['local_path'],selection=selected)
            saved=dict(directory=str(run),calls=[],sources=[],configuration={'as_of':'2026-10-25'},artifacts={})
            for filename,value in {'official_downloaded_originals.json':[descriptor],
                    'source_freshness_partial.json':dict(status='incomplete_discovery',releases=[],deferred_releases=[]),
                    'discovered_sources.json':[]}.items():
                target=run/filename;target.write_text(json.dumps(value),encoding='utf-8')
                saved['artifacts'][filename]=hashlib.sha256(target.read_bytes()).hexdigest()
            (run/'record.json').write_text(json.dumps(saved),encoding='utf-8');(run/'calls.jsonl').write_text('',encoding='utf-8')
            return saved
        return outputs,record,inventory,path,source,selection,interrupted

    def test_interrupted_replays_retain_completed_metadata_and_identical_request_provenance(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        for resolved in (True,False):
            with self.subTest(original_dateline=resolved),tempfile.TemporaryDirectory() as temporary:
                outputs,record,inventory,path,source,selection,interrupted=self.interrupted_metadata_fixture(Path(temporary),resolved=resolved)
                before=copy.deepcopy(inventory);original_bytes=path.read_bytes()
                baseline,_=restore_discovered_metadata(inventory,[record],outputs)
                records=[record,interrupted('interrupted_once',selection),interrupted('interrupted_twice',selection)]
                catalog,audit=restore_discovered_metadata(inventory,records,outputs)
                self.assertEqual(catalog,baseline,'Interrupted raw replay must not change the paid selection context or its source provenance')
                self.assertEqual(catalog['local_current']['published_at'],'2017-03-15')
                self.assertEqual(catalog['local_current']['publication_claims'],source['publication_claims'])
                self.assertEqual(audit['retained_completed_metadata'][0]['replayed_selections'],2)
                self.assertEqual(audit['conflicts'],[]);self.assertEqual(audit['ai_calls'],0)
                self.assertEqual(inventory,before);self.assertEqual(path.read_bytes(),original_bytes)

    def test_interrupted_replay_new_claim_date_or_bytes_cannot_reuse_an_older_resolution(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        for change in ('new_claim','new_date','new_quote','new_period_reference','changed_bytes'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temporary:
                outputs,record,inventory,path,source,selection,interrupted=self.interrupted_metadata_fixture(Path(temporary))
                if change=='new_claim':selection['publication_claims'].append(dict(url=source['url'],published_at='2017-03-20',publication_evidence='20 March 2017'))
                elif change=='new_date':selection.update(published_at='2017-03-20',publication_evidence='20 March 2017')
                elif change=='new_quote':selection.update(published_at='2017-03-15',publication_evidence='Issuer announcement: 15 March 2017')
                elif change=='new_period_reference':selection['reporting_period_refs']=[dict(page_url=source['url'],sha256='c'*64,quotation='Half year 2016')]
                else:
                    selection['sha256']='b'*64;inventory['sources'][0]['sha256']='b'*64
                later=interrupted('interrupted_changed',selection)
                catalog,audit=restore_discovered_metadata(inventory,[record,later],outputs);restored=catalog['local_current']
                self.assertEqual(audit['retained_completed_metadata'],[])
                self.assertIsNone(restored['published_at']);self.assertNotIn('discovery_publication_date',restored)
                self.assertFalse(restored['point_in_time_eligible']);self.assertNotEqual(restored['publication_availability'],'verified_original_dateline')
                if change=='new_date':self.assertIn('2017-03-20',[item.get('published_at') for item in restored['publication_claims']])

    def test_unresolved_publication_claims_keep_contradictory_status_without_a_date(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,path=self.fixture(Path(temporary))
            source=json.loads(path.read_text(encoding='utf-8'))[0]
            claims=[dict(published_at='2017-03-09',publication_evidence='9 March 2017'),
                    dict(published_at='2017-03-15',publication_evidence='15 March 2017')]
            source.update(published_at=None,publication_evidence='',publication_availability='contradictory',
                publication_claims=claims,point_in_time_eligible=False,freshness_eligible=False)
            path.write_text(json.dumps([source]),encoding='utf-8')
            record['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
            (path.parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs)
            restored=catalog['local_current']
            self.assertIsNone(restored['published_at'])
            self.assertEqual(restored['publication_availability'],'contradictory')
            self.assertEqual(restored['publication_claims'],claims)
            self.assertFalse(restored['point_in_time_eligible']);self.assertFalse(restored['freshness_eligible'])

    def deferred_fixture(self,root,*,resolved=True,partial=False,no_file=False):
        outputs,record,inventory,path=self.fixture(root)
        source=json.loads(path.read_text(encoding='utf-8'))[0];sha=source['sha256'];url=source['url']
        dates=('2026-10-28','2026-10-30')
        claims=[dict(url=url,published_at=value,publication_evidence=quote,publication_availability='verified_linking_page',
            publication_date_refs=[dict(page_url='https://example.test/results',sha256='pagehash',date=value,quotation=quote)])
            for value,quote in zip(dates,('28 October 2026','30 October 2026'))]
        selection=dict(source,published_at=dates[0],publication_evidence=claims[0]['publication_evidence'],publication_availability='verified_linking_page',
            publication_claims=claims,point_in_time_eligible=False,freshness_eligible=False)
        descriptor=dict(url=url,final_url=url,sha256=sha,source_id=source['id'],local_path=source['local_path'],selection=selection)
        deferred=dict(selection,source_id=source['id'],status='after_cutoff',observed_urls=[url],
            published_at=dates[1] if resolved else None,publication_evidence=claims[1]['publication_evidence'] if resolved else '',
            publication_availability='verified_original_dateline' if resolved else 'conflicting_official_claims')
        if resolved:deferred['publication_date_refs']=[dict(source_id=source['id'],unit_id='page:1',sha256=sha,
            date=dates[1],quotation=claims[1]['publication_evidence'],method='Exact original dateline')]
        if no_file:deferred.pop('sha256',None);deferred.pop('source_id',None)
        values={'discovered_sources.json':[],'official_downloaded_originals.json':[] if no_file else [descriptor],
            'source_freshness_partial.json' if partial else 'source_freshness.json':dict(checked_as_of='2026-10-25',deferred_releases=[deferred])}
        record['configuration']={'as_of':'2026-10-25'}
        for name,value in values.items():
            target=path.parent/name;target.write_text(json.dumps(value),encoding='utf-8')
            record['artifacts'][name]=hashlib.sha256(target.read_bytes()).hexdigest()
        (path.parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
        return outputs,record,inventory,path,values

    def test_resolved_future_continuation_keeps_hash_bound_date_and_filters_before_selection(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata, research_catalogue_as_of
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,path,_=self.deferred_fixture(Path(temporary));before=copy.deepcopy(inventory)
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs);source=catalog['local_current']
            self.assertEqual(source['published_at'],'2026-10-30','Final dateline must win over pre-resolution selected date')
            self.assertEqual(source['publication_availability'],'verified_original_dateline')
            self.assertEqual(source['discovery_provenance']['artifact'],'source_freshness.json')
            self.assertIn('official_downloaded_originals.json',source['discovery_provenance']['supporting_artifact_hashes'])
            selected,scope=research_catalogue_as_of(catalog,'2026-10-25')
            self.assertEqual(selected,{});self.assertEqual(scope['excluded'][0]['source']['published_at'],'2026-10-30')
            self.assertEqual(scope['full_inventory_source_ids'],['local_current']);self.assertEqual(inventory,before)
            self.assertEqual(set(research_catalogue_as_of(catalog,'2026-10-30')[0]),{'local_current'})
            inventory['sources'][0].update(published_at='2026-10-24',supplied_metadata={'publication_date':'2026-10-24'})
            catalog,_=restore_discovered_metadata(inventory,[record],outputs)
            self.assertEqual(catalog['local_current']['published_at'],'2026-10-24','User annotation remains unchanged')
            self.assertEqual(catalog['local_current']['discovery_publication_date'],'2026-10-30')
            self.assertEqual(research_catalogue_as_of(catalog,'2026-10-25')[0],{},'User annotation cannot erase verified future source evidence')

    def test_future_conflicts_restore_conservative_policy_without_inventing_publication_date(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata, research_catalogue_as_of
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,path,values=self.deferred_fixture(Path(temporary),resolved=False,partial=True)
            catalog,_=restore_discovered_metadata(inventory,[record],outputs);source=catalog['local_current']
            self.assertIsNone(source['published_at']);self.assertEqual(source['publication_availability'],'contradictory')
            self.assertEqual(source['deferred_until'],'2026-10-30');self.assertIn('not a verified publication date',source['deferred_until_basis'])
            self.assertFalse(source['point_in_time_eligible']);self.assertFalse(source['freshness_eligible'])
            self.assertEqual(research_catalogue_as_of(catalog,'2026-10-29')[0],{})
            self.assertIn('local_current',research_catalogue_as_of(catalog,'2026-10-30')[0])
            # A later authoritative original dateline overrides the earlier
            # future-only policy instead of carrying a stale deferral forward.
            resolved=copy.deepcopy(source);resolved.update(id='resolved',published_at='2026-10-24',publication_evidence='24 October 2026',
                publication_availability='verified_original_dateline',publication_date_refs=[dict(source_id='resolved',unit_id='page:1',
                    sha256=source['sha256'],date='2026-10-24',quotation='24 October 2026',method='Original dateline')])
            resolved.pop('deferred_until');resolved.pop('deferred_until_basis')
            path.write_text(json.dumps([resolved]),encoding='utf-8');record['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
            (path.parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
            catalog,_=restore_discovered_metadata(inventory,[record],outputs)
            self.assertNotIn('deferred_until',catalog['local_current']);self.assertEqual(catalog['local_current']['published_at'],'2026-10-24')
            self.assertIn('local_current',research_catalogue_as_of(catalog,'2026-10-25')[0])

    def test_deferred_continuation_rejects_changed_bytes_and_tampered_artifacts_and_ignores_missing_files(self):
        from company_initiation.historic_construction.workflow import restore_discovered_metadata
        for tampered in ('official_downloaded_originals.json','source_freshness.json'):
            with self.subTest(tampered=tampered),tempfile.TemporaryDirectory() as temporary:
                outputs,record,inventory,path,_=self.deferred_fixture(Path(temporary))
                inventory['sources'][0]['sha256']='b'*64
                catalog,audit=restore_discovered_metadata(inventory,[record],outputs)
                self.assertEqual(audit['recovered'],[]);self.assertNotIn('discovery_publication_date',catalog['local_current'])
                (path.parent/tampered).write_text('[]',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'metadata content changed'):restore_discovered_metadata(inventory,[record],outputs)
        with tempfile.TemporaryDirectory() as temporary:
            outputs,record,inventory,_,_=self.deferred_fixture(Path(temporary),no_file=True)
            catalog,audit=restore_discovered_metadata(inventory,[record],outputs)
            self.assertEqual(audit['recovered'],[]);self.assertNotIn('deferred_until',catalog['local_current'])

    def test_research_filters_restored_future_sources_before_first_selection_and_keeps_inventory(self):
        from types import SimpleNamespace
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.historic_construction.workflow import research_company_inputs
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'outputs').mkdir();archive=root/'company';reports=archive/'financial_reports';reports.mkdir(parents=True)
            (reports/'past.txt').write_text('Synthetic original annual sales 12.',encoding='utf-8')
            (reports/'future.txt').write_text('Synthetic future interim sales 13.',encoding='utf-8')
            inventory=inventory_local_sources(archive);catalog={source['id']:copy.deepcopy(source) for source in inventory['sources']}
            future=next(sid for sid,source in catalog.items() if source['local_path'].endswith('future.txt'))
            catalog[future].update(discovery_publication_date='2026-10-30',published_at='2026-10-24',
                supplied_metadata={'publication_date':'2026-10-24'})
            captured=[]
            class Journal:
                def __init__(self,directory,*args):self.directory=directory;self.state={'issues':[],'artifacts':{}};self.saved={};captured.append(self)
                def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
                def save(self):pass
                def stage(self,name,prompt,payload,schema,*args):
                    self.selection=(name,copy.deepcopy(payload))
                    raise ValueError('Synthetic stop before provider dispatch')
            provider=SimpleNamespace(timeout=300,metadata=lambda:{})
            with patch('company_initiation.shared_runtime.RunJournal',Journal),patch('company_initiation.historic_construction.workflow._capture_research_engine_contract',return_value={}), \
                 patch('company_initiation.historic_construction.workflow.restore_discovered_metadata',return_value=(catalog,dict(recovered=[],conflicts=[]))), \
                 self.assertRaisesRegex(ValueError,'Synthetic stop before provider'):
                research_company_inputs(root,'Synthetic catalogue fixture',archive,as_of='2026-10-25',provider=provider)
            journal=captured[0];self.assertEqual(journal.selection[0],'company_identity_sources')
            self.assertNotIn(future,{item['id'] for item in journal.selection[1]['catalog']})
            self.assertIn(future,{item['id'] for item in journal.saved['inventory.json']['sources']})
            audit=journal.saved['discovery_metadata_reuse.json']['selection_eligibility']
            self.assertEqual(audit['excluded'][0]['source_id'],future)
            self.assertEqual(audit['excluded'][0]['source']['discovery_publication_date'],'2026-10-30')
            self.assertTrue((reports/'future.txt').is_file());self.assertEqual(catalog[future]['published_at'],'2026-10-24')


class ReconstructionComparisonTests(unittest.TestCase):
    def fact(self,identifier,value,raw,**changes):
        result=dict(id=identifier,row_id='sales',period_id='2025-FY',value=value,unit='EURm',currency='EUR',
            metric_type='flow',entity_id='group',basis='reported',definition_id='sales',scope='consolidated',
            source_refs=[dict(raw=raw,number_format='dot_decimal',multiplier=1,contribution_weight=1)])
        result.update(changes);return result

    def test_source_precision_handles_scaled_signed_compositions_and_primary_rounding(self):
        from company_initiation.historic_construction.workflow import _source_rounding_bound, _reconstruction_comparison
        refs=[dict(raw='1.234,5',number_format='comma_decimal',multiplier=.001,contribution_weight=1),
              dict(raw='12.3%',number_format='dot_decimal',multiplier=1,contribution_weight=-2)]
        self.assertAlmostEqual(_source_rounding_bound(refs),.00005+.001)
        left=self.fact('vendor',123.456,'123.456');right=self.fact('original',123.5,'123.5')
        self.assertEqual(_reconstruction_comparison([left],[right])[0]['status'],'matched')
        right['value']=123.6
        self.assertEqual(_reconstruction_comparison([left],[right])[0]['status'],'unresolved')

    def test_numeric_agreement_does_not_merge_basis_entity_scope_or_rounded_zero(self):
        from company_initiation.historic_construction.workflow import _reconstruction_comparison
        left=self.fact('mapped',100,'100.0')
        for field,value in [('basis','restated'),('entity_id','different_division'),('scope','continuing_only'),('definition_id','adjusted_sales'),('restatement','restated'),('restatement_vintage','2026-revision')]:
            right=self.fact('blind',100,'100.0',**{field:value})
            with self.subTest(field=field):
                comparison=_reconstruction_comparison([left],[right])[0]
                self.assertEqual(comparison['status'],'semantic_review')
                self.assertIn(field,comparison['comparisons'][0]['metadata_differences'])
        self.assertEqual(_reconstruction_comparison([self.fact('zero',0,'0.0')],[self.fact('small',.01,'0.01')])[0]['status'],'semantic_review')
        self.assertEqual(_reconstruction_comparison([self.fact('dash',0,'-')],[self.fact('zero',0,'0')])[0]['status'],'semantic_review')

    def test_missing_primary_and_incompatible_units_cannot_be_rounded_away(self):
        from company_initiation.historic_construction.workflow import _reconstruction_comparison
        left=self.fact('mapped',100,'100')
        self.assertEqual(_reconstruction_comparison([left],[])[0]['status'],'unresolved')
        self.assertEqual(_reconstruction_comparison([left],[self.fact('blind',100,'100',unit='EURbn')])[0]['status'],'unresolved')
        # Adjacent integer disclosures differ by a whole published unit.
        self.assertEqual(_reconstruction_comparison([left],[self.fact('blind',101,'101')])[0]['status'],'unresolved')

    def test_reporting_versions_keep_separate_compatibility_and_source_vintage(self):
        from company_initiation.historic_construction.workflow import _observation_classification
        ref=dict(source_id='original',unit_id='page:1')
        entry=dict(basis='group_reporting',entity_id='group',restatement='original',restatement_vintage=None,
            classification_basis='Synthetic original table heading and period definition.',classification_source_refs=[ref])
        catalog={'original':dict(sha256='frozen-source',category='financial_reports',published_at='2026-03-10',publication_evidence='Published10March2026')}
        original=_observation_classification(entry,[ref],catalog,{('original','page:1')})
        restated=_observation_classification(dict(entry,restatement='restated',restatement_vintage='2027-policy-revision'),[ref],catalog,{('original','page:1')})
        self.assertNotEqual(original['compatibility_key'],restated['compatibility_key'])
        self.assertEqual(original['published_at'],'2026-03-10')
        self.assertEqual(original['source_vintage'][0]['sha256'],'frozen-source')
        with self.assertRaisesRegex(ValueError,'restatement vintage'):
            _observation_classification(dict(entry,restatement='restated'),[ref],catalog,{('original','page:1')})
        for kind in ('unknown','vendor_normalized'):
            self.assertFalse(_observation_classification(dict(entry,restatement=kind),[ref],catalog,{('original','page:1')})['eligible'])
        unknown=_observation_classification(entry,[ref],{'original':dict(category='visible_alpha')},{('original','page:1')})
        self.assertNotIn('published_at',unknown)
        self.assertEqual(unknown['source_vintage'][0]['publication_status'],'unknown')

    def test_structured_publication_vintage_requires_matching_cited_date_metadata(self):
        from company_initiation.historic_construction.workflow import _observation_classification
        ref=dict(source_id='original',unit_id='page:1')
        entry=dict(basis='reported',entity_id='group',restatement='original',restatement_vintage=None,
            classification_basis='Original supplied financial table.',classification_source_refs=[ref])
        date_ref=dict(date_id='date_original',date='2026-03-10',sha256='saved-html-hash',page_url='https://synthetic.invalid/results',
            container_id='original_release_card',attribute='datetime',raw_value='2026-03-10',native_unit='calendar_date',native_timezone=None)
        source=dict(category='financial_reports',published_at='2026-03-10',publication_evidence='',
            publication_availability='verified_structured_html',publication_date_id='date_original',publication_date_refs=[date_ref])
        classified=_observation_classification(entry,[ref],{'original':source},{('original','page:1')})
        self.assertEqual(classified['published_at'],'2026-03-10')
        self.assertEqual(classified['source_vintage'][0]['publication_status'],'source_verified')
        self.assertEqual(classified['source_vintage'][0]['publication_date_refs'],[date_ref])
        for changes in [dict(publication_date_refs=[]),dict(publication_date_id='another_card'),dict(published_at='2026-03-11')]:
            with self.subTest(changes=changes):
                unverified=_observation_classification(entry,[ref],{'original':dict(source,**changes)},{('original','page:1')})
                self.assertNotIn('published_at',unverified)
                self.assertEqual(unverified['source_vintage'][0]['publication_status'],'metadata_unverified')

    def test_ineligible_history_stays_audit_only_and_cannot_override_active_basis(self):
        from company_initiation.historic_construction.workflow import _bind_mapped_history
        eligible=self.fact('reported',100,'100',kind='FY',fiscal_year=2025,restatement='original',eligible=True)
        excluded=[self.fact(kind,900,'900',kind='FY',fiscal_year=2025,basis=kind,restatement=kind,eligible=False)
                  for kind in ('unknown','vendor_normalized')]
        data=dict(historical={},observations=[eligible]+excluded,model_configuration={})
        _bind_mapped_history(data,data['observations'])
        self.assertEqual(data['historical']['sales']['values'],{'2025':100})
        self.assertEqual(data['historical']['sales']['observation_ids'],{'2025':'reported'})
        self.assertEqual(data['active_basis_by_period'],{'2025-FY':{'group':'reported'}})
        self.assertEqual(len(data['observations']),3)
        self.assertEqual(len(data['model_configuration']['limitations']),2)
        empty=dict(historical={},observations=excluded,model_configuration={})
        _bind_mapped_history(empty,excluded)
        self.assertEqual(empty['historical'],{})
        self.assertNotIn('active_basis_by_period',empty)

    def test_legacy_annual_and_segment_anchors_cannot_bypass_excluded_observations(self):
        from company_initiation.forecast_construction.integrated import historical_eligibility_inputs
        for role in ('sales','north_sales'):
            for kind in ('unknown','vendor_normalized'):
                with self.subTest(role=role,kind=kind):
                    data=different_period_company()
                    candidates=[o for o in data['observations'] if o['row_id']==role and o['period_id']=='2025-FY']
                    for observation in candidates:observation['restatement']=kind
                    original=copy.deepcopy(data)
                    with self.assertRaisesRegex(ValueError,'excluded observation evidence'):
                        build_periodic_spec(data,1)
                    self.assertEqual(data,original)
                    # An independently eligible matching original permits the
                    # real anchor while retaining the other version for audit.
                    primary=copy.deepcopy(candidates[-1]);primary.update(id='eligible_'+role,restatement='original',eligible=True)
                    data['observations'].append(primary)
                    validated=historical_eligibility_inputs(data)
                    self.assertFalse(next(o for o in validated['observations'] if o['id']==candidates[-1]['id'])['eligible'])
                    self.assertTrue(next(o for o in validated['observations'] if o['id']==primary['id'])['eligible'])

    def test_combined_history_gate_keeps_missing_primary_evidence_out_of_financial_escalation(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        unit=dict(source_id='synthetic',unit_id='page:1',text='Original interim reporting cadence and segment definitions.',numbers=[])
        data=dict(company='Synthetic',history_years=[2024,2025],model_configuration={},observations=[],sources={'synthetic':dict(id='synthetic')},
            reporting_changes=[],entity_versions=[],reporting_bridges=[])
        class Journal:
            def __init__(self):self.artifacts={}
            def artifact(self,name,value):self.artifacts[name]=copy.deepcopy(value)
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                self.stage=stage;self.context=payload
                checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Synthetic cited definition.',
                    source_refs=[dict(source_id='synthetic',unit_id='page:1')]) for topic in payload['required_topics']]
                checks[0].update(status=self.status,issue_type=self.issue,detail='Required reported H1 statement original absent.')
                self.failures=assess(dict(checks=checks,summary='Missing primary fixture'))
                if self.failures:raise ValueError('Required reported H1 statement original absent')
                return dict(checks=checks,summary='Unsupported completion')
        for status in ('error','warning','pass'):
            for issue in ('missing_primary_evidence','context_omission'):
                journal=Journal();journal.status=status;journal.issue=issue
                with self.subTest(status=status,issue=issue),self.assertRaisesRegex(ValueError,'H1 statement'):
                    _combined_history_challenge(journal,data,[unit])
                self.assertEqual(journal.stage,'company_combined_history')
                self.assertEqual(journal.failures[0]['kind'],'output_contract' if issue=='context_omission' else issue)
                self.assertIn('combined_history_context.json',journal.artifacts)
                self.assertNotIn('combined_history_review',data)

    def test_combined_history_gate_fingerprint_invalidates_changed_history_but_not_forecast_scenarios(self):
        from company_initiation.historic_construction.workflow import ensure_combined_history_review, combined_history_review_current, combined_history_fingerprint
        unit=dict(source_id='synthetic',unit_id='page:1',text='Synthetic original reporting definitions.',numbers=[])
        data=dict(company='Synthetic',history_years=[2024,2025],model_configuration={},observations=[],
            sources={'synthetic':dict(id='synthetic',sha256='originalhash',category='financial_reports')},
            reporting_changes=[],entity_versions=[],reporting_bridges=[])
        class Journal:
            def __init__(self):self.calls=0;self.artifacts={}
            def artifact(self,name,value):self.artifacts[name]=copy.deepcopy(value)
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                self.calls+=1
                answer=dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited synthetic check.',
                    source_refs=[dict(source_id='synthetic',unit_id='page:1')]) for topic in payload['required_topics']],summary='Synthetic complete history')
                self_test.assertEqual(assess(answer),[])
                return answer
        self_test=self;journal=Journal()
        first=ensure_combined_history_review(journal,data,[unit])
        self.assertTrue(combined_history_review_current(data));self.assertEqual(first['status'],'passed')
        ensure_combined_history_review(journal,data,[]);self.assertEqual(journal.calls,1)
        original_fingerprint=combined_history_fingerprint(data)
        data['model_configuration']['financial_contracts']={'cost_pools':[dict(id='research',spending_change=.1)]}
        data['sources']['synthetic']['path']='relocated/original.pdf'
        self.assertEqual(combined_history_fingerprint(data),original_fingerprint)
        optional_empty=copy.deepcopy(data);optional_empty['sources']['synthetic'].update(publication_date_id=None,publication_date_refs=None)
        self.assertEqual(combined_history_fingerprint(optional_empty),original_fingerprint)
        changes=[lambda d:d['sources']['synthetic'].update(sha256='changed-source'),
                 lambda d:d['sources']['synthetic'].update(publication_date_id='new_date',publication_date_refs=[dict(date='2026-03-10',sha256='html-original')]),
                 lambda d:d['sources']['synthetic'].update(publication_claims=[dict(published_at='2026-03-11',publication_availability='contradictory')]),
                 lambda d:d['sources']['synthetic'].update(publication_availability='unknown',observed_available_at='2026-10-25',point_in_time_eligible=False),
                 lambda d:d['observations'].append(dict(id='new_reported_actual',period_id='2026-H1')),
                 lambda d:d.update(missing_concepts=[dict(row_id='cfo',period_id='2025-H1',reason='Missing primary support')]),
                 lambda d:d.update(disclosure_coverage=[dict(year=2025,sources=[dict(source_id='synthetic',period_ids=['2025-H1'])])]),
                 lambda d:d['model_configuration'].update(cash_scope={'policy':'cited overdraft bridge'}),
                 lambda d:d['model_configuration'].update(operating_expense_functions=[{'id':'other_recurring'}]),
                 lambda d:d['model_configuration'].update(structural_account_policies=[{'role':'other_current_assets','treatment':'included_in'}]),
                 lambda d:d['model_configuration'].update(cashflow_presentation={'cffi_components':[{'row_id':'hybrid_issuance','sign':1}]}),
                 lambda d:d['reporting_changes'].append(dict(description='Dated segment reorganisation')),
                 lambda d:d['model_configuration'].update(actual_through='2026-06-30')]
        for mutate in changes:
            changed=copy.deepcopy(data);mutate(changed)
            self.assertFalse(combined_history_review_current(changed))
            with self.assertRaisesRegex(ValueError,'cannot be grandfathered'):ensure_combined_history_review(journal,changed,[])
        data['reporting_changes'].append(dict(description='Sourced reporting reorganisation'))
        ensure_combined_history_review(journal,data,[unit]);self.assertEqual(journal.calls,2)
        self.assertTrue(combined_history_review_current(data))
        data['combined_history_review']['checks'][0]['status']='error'
        self.assertFalse(combined_history_review_current(data))
        data['combined_history_review']['checks'][0].update(status='warning',issue_type='missing_primary_evidence')
        self.assertFalse(combined_history_review_current(data))
        data['combined_history_review']['checks'][0]['issue_type']='context_omission'
        self.assertFalse(combined_history_review_current(data))

    def test_history_source_parse_failure_names_original_and_page_without_paid_call(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject,NumberObject
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.historic_construction.workflow import ensure_company_history_research
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'archive';reports=archive/'financial_reports';reports.mkdir(parents=True)
            writer=PdfWriter();page=writer.add_blank_page(600,800);page[NameObject('/Contents')]=NumberObject(42)
            writer.write(reports/'malformed_original.pdf')
            source=inventory_local_sources(archive)['sources'][0]
            data=dict(company='SYNTHETIC malformed history',history_years=[2025],sources={source['id']:source},
                model_configuration={'as_of':'2026-10-25'},observations=[],reporting_changes=[],entity_versions=[],reporting_bridges=[])
            inputs=root/'inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
            provider=OpenAIProvider(api_key='SYNTHETIC-NOT-A-CREDENTIAL')
            with patch.object(provider,'complete',side_effect=AssertionError('No paid call before readable evidence')) as calls, \
                 self.assertRaisesRegex(ValueError,'malformed_original.pdf.*PDF page 1'):
                ensure_company_history_research(root,data['company'],archive,inputs,provider=provider)
            self.assertEqual(calls.call_count,0)
            record=json.loads(next((root/'outputs').glob('construct_history_review_*/record.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['status'],'incomplete');self.assertEqual(record['calls'],[])
            self.assertIn(source['id'],record['issues'][-1])

    def test_history_matrix_round_trip_keeps_versions_periods_values_and_source_identities(self):
        from company_initiation.historic_construction.workflow import _history_review_matrix
        observations=[]
        for index,(kind,vintage,value) in enumerate([('original',None,100),('restated','2027-policy',100),('unknown',None,None)]):
            observations.append(self.fact('observation_'+str(index),value,'100',restatement=kind,restatement_vintage=vintage,
                start='2025-01-01',end='2025-12-31',fiscal_year=2025,kind='FY',eligible=kind!='unknown',status='reported',
                source_refs=[dict(source_id='original_'+str(index),unit_id='page:1')],
                source_vintage=[dict(source_id='original_'+str(index),published_at=None,publication_status='unknown')]))
        encoded=_history_review_matrix(observations);decoded={}
        for series in encoded['series']:
            metadata={field:encoded['dictionaries'][field][series['metadata'][i]] for i,field in enumerate(encoded['metadata_fields'])}
            for identifier,period_index,value in series['points']:
                decoded[identifier]=dict(metadata,**encoded['periods'][period_index],id=identifier,value=value)
        self.assertEqual(encoded['observation_count'],3)
        for index,observation in enumerate(observations):
            actual=decoded[observation['id']]
            for field in encoded['metadata_fields']:
                self.assertEqual(actual[field],['original_'+str(index)] if field=='source_ids' else observation.get(field))
            for field in ('id','period_id','start','end','fiscal_year','kind','value'):self.assertEqual(actual[field],observation.get(field))

    def test_history_context_compaction_preserves_every_token_and_bridge_reference(self):
        from company_initiation.historic_construction.workflow import _history_compact_evidence, _history_compact_bridges
        units=[dict(source_id='original',unit_id='page:1',text='Complete table 100 and 20 with surrounding notes.',
            numbers=[dict(index=0,raw='100',start=15,end=18),dict(index=1,raw='20',start=23,end=25)],warnings=['Original parser note']),
            dict(source_id='original',unit_id='page:2',text='Additional complete original.',numbers=[],warnings=[])]
        encoded=_history_compact_evidence(units);decoded=copy.deepcopy(encoded)
        for unit in decoded:
            if isinstance(unit['numbers'],dict):unit['numbers']=[dict(zip(unit['numbers']['columns'],row)) for row in unit['numbers']['rows']]
        self.assertEqual(decoded,units);self.assertEqual(_history_compact_evidence(encoded),encoded)
        ref=dict(source_id='original',unit_id='page:1',raw='100',number_index=0)
        bridges=[dict(id='change',period_id='2020-FY',effective_date='2024-01-01',
            before=dict(value=100,source_refs=[ref]),after=dict(value=120,source_refs=[ref]),change_source_ref=ref)]
        packed=_history_compact_bridges(bridges)
        def restore(value):
            if isinstance(value,list):return [restore(item) for item in value]
            if not isinstance(value,dict):return value
            if set(value)=={'$source_reference'}:return packed['source_references'][value['$source_reference']]
            return {key:restore(item) for key,item in value.items()}
        self.assertEqual(len(packed['source_references']),1);self.assertEqual(restore(packed['records']),bridges)

    def test_history_cohorts_cover_all_interims_long_bridges_and_bounded_synthesis(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, _HISTORY_GATE_TOPICS
        years=list(range(2020,2025));units=[];observations=[];coverage=[]
        for year in years:
            sid='original_'+str(year)
            units.extend(dict(source_id=sid,unit_id='page:'+str(page),text='Complete original '+str(year)+' page '+str(page),numbers=[],warnings=[]) for page in range(1,4))
            coverage.append(dict(year=year,source_ids=[sid]))
            for kind in ('FY','H1'):
                observations.append(self.fact(str(year)+kind,year,str(year),period_id=str(year)+'-'+kind,fiscal_year=year,kind=kind,
                    source_refs=[dict(source_id=sid,unit_id='page:1')]))
        data=dict(company='SYNTHETIC changing reporting',history_years=years[:-1],model_configuration={},observations=observations,
            sources={'original_'+str(y):dict(id='original_'+str(y)) for y in years},entity_versions=[],reporting_changes=[],
            disclosure_coverage=[dict(year=y,sources=[]) for y in years],
            missing_concepts=[dict(row_id='synthetic_optional',period_id=str(y)+'-H1',reason='Explicit unavailable synthetic note') for y in years],
            reporting_bridges=[dict(id='long_restatement',period_id='2020-FY',effective_date='2024-01-01',
                change_source_ref=dict(source_id='original_2024',unit_id='page:2'))])
        owner=self
        class Journal:
            def __init__(self):self.artifacts={};self.calls=[]
            def artifact(self,name,value):self.artifacts[name]=copy.deepcopy(value)
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                self.calls.append((stage,copy.deepcopy(payload)))
                if stage=='company_combined_history_synthesis':raise ValueError('AI provider returned HTTP 400 (context_length_exceeded); synthetic test')
                evidence=payload['evidence'][0];refs=[dict(source_id=evidence['source_id'],unit_id=evidence['unit_id'])]
                checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited synthetic cross-year check.',source_refs=refs) for topic in payload['required_topics']]
                if '_cohort_' in stage:
                    owner.assertNotIn('all_requested_years',payload)
                    owner.assertEqual(payload['review_scope']['required_fiscal_years'],payload['requested_years'])
                    owner.assertEqual(payload['combined_run_years_for_navigation_only'],years)
                    owner.assertEqual({item['year'] for item in payload['disclosure_coverage']},set(payload['requested_years']))
                    owner.assertEqual({int(item['period_id'][:4]) for item in payload['missing_concepts']},set(payload['requested_years']))
                    owner.assertIn('SOLE fiscal-observation coverage obligation',prompt)
                    owner.assertIn('Other-year entity_versions',payload['cohort_role'])
                    wrong=copy.deepcopy(checks);wrong[0]['period_ids']=['2030-FY']
                    failures=assess(dict(checks=wrong,summary='Incorrect out-of-cohort obligation'))
                    owner.assertEqual(failures[0]['kind'],'output_contract')
                    owner.assertIn('outside this review requested_years',failures[0]['check'])
                if stage=='company_combined_history_cohort_1':checks[0]['status']='warning'
                answer=dict(checks=checks,summary='Synthetic evidence challenge');owner.assertEqual(assess(answer),[]);return answer
        journal=Journal();review=_combined_history_challenge(journal,data,units,coverage=coverage)
        cohort_calls=[(stage,payload) for stage,payload in journal.calls if '_cohort_' in stage]
        self.assertEqual(len(cohort_calls),5)
        self.assertIn([2020,2024],[payload['requested_years'] for _,payload in cohort_calls])
        ids={point[0] for _,payload in cohort_calls for series in payload['historical_matrix']['series'] for point in series['points']}
        self.assertEqual(ids,{o['id'] for o in observations})
        for _,payload in cohort_calls:self.assertEqual(set(payload['required_topics']),set(_HISTORY_GATE_TOPICS))
        self.assertEqual(len(review['checks']),6);self.assertEqual(review['checks'][0]['status'],'warning')
        self.assertEqual(len([stage for stage,_ in journal.calls if '_synthesis_' in stage]),6)
        self.assertIn('combined_history_synthesis_context_failure.json',journal.artifacts)
        synthesis=next(payload for stage,payload in journal.calls if stage=='company_combined_history_synthesis')
        # A cited middle page retains its complete originally selected section.
        self.assertTrue({('original_2024','page:'+str(i)) for i in range(1,4)}<={(u['source_id'],u['unit_id']) for u in synthesis['evidence']})
        self.assertEqual(review['status'],'passed');self.assertEqual(len(review['cohort_reviews']),5)

    def test_history_repair_combines_new_originals_with_omitted_existing_cited_sections(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        originals=[dict(source_id='annual',unit_id='page:'+str(page),text=('Complete original annual table '+str(page)+' '+('x'*180001 if page==1 else 'surrounding original note')),numbers=[])
            for page in (1,2,3)]
        additional=[dict(source_id='restatement',unit_id='page:'+str(page),text='Complete later-published comparative and notes '+str(page),numbers=[]) for page in (1,2)]
        data=dict(company='SYNTHETIC context repair',history_years=[2020,2021],model_configuration={},observations=[],
            sources={'annual':dict(id='annual')},reporting_changes=[],reporting_bridges=[],entity_versions=[])
        owner=self;loader_calls=[]
        def loader(failures):loader_calls.append(copy.deepcopy(failures));return copy.deepcopy(additional)
        class Journal:
            def __init__(self):self.artifacts={};self.repairs=[]
            def artifact(self,name,value):self.artifacts[name]=copy.deepcopy(value)
            def stage(self,name,prompt,payload,schema,validate):
                def section(sid,first,last):return dict(source_id=sid,first_unit='page:'+str(first),last_unit='page:'+str(last),reason='Complete financial section and associated original notes')
                if 'context repair for affected fiscal years' not in payload['purpose']:
                    return validate(dict(sections=[section('annual',1,1)],gaps=[]))
                self.repairs.append(copy.deepcopy(payload))
                owner.assertEqual({unit['source_id'] for unit in payload['navigation']},{'annual','restatement'})
                owner.assertEqual(payload['required_source_ids'],['annual','restatement'])
                owner.assertEqual(payload['required_unit_refs'],[dict(source_id='annual',unit_id='page:2')])
                with owner.assertRaisesRegex(ValueError,'Previously cited original units remain omitted'):
                    validate(dict(sections=[section('annual',1,1),section('restatement',1,2)],gaps=[]))
                return validate(dict(sections=[section('annual',1,3),section('restatement',1,2)],gaps=[]))
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                refs=[dict(source_id='annual',unit_id='page:1')]
                checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=['2020-FY'],detail='Synthetic primary check.',source_refs=refs)
                    for topic in payload['required_topics']]
                missing=copy.deepcopy(checks);missing[0].update(status='warning',issue_type='context_omission',source_refs=[dict(source_id='annual',unit_id='page:2')])
                repaired=repair_context(copy.deepcopy(payload),assess(dict(checks=missing,summary='Existing primary page omitted')))
                owner.assertEqual({(u['source_id'],u['unit_id']) for u in repaired['evidence']},
                    {('annual','page:'+str(page)) for page in (1,2,3)}|{('restatement','page:'+str(page)) for page in (1,2)})
                checks[0]['source_refs']=[dict(source_id='annual',unit_id='page:2')]
                answer=dict(checks=checks,summary='All existing and new original context retained')
                owner.assertEqual(assess(answer),[]);return answer
        journal=Journal();before=copy.deepcopy(data['observations'])
        result=_combined_history_challenge(journal,data,originals,source_loader=loader)
        self.assertEqual(result['status'],'passed');self.assertEqual(len(journal.repairs),1)
        self.assertEqual(loader_calls[0][0]['review_scope']['required_fiscal_years'],[2020,2021])
        self.assertEqual(data['observations'],before)

    def test_failed_history_cohort_cannot_be_hidden_by_final_synthesis(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        unit=dict(source_id='original',unit_id='page:1',text='Complete supplied original.',numbers=[])
        data=dict(company='SYNTHETIC incomplete cohorts',history_years=[2020,2021,2022],model_configuration={},observations=[],
            sources={'original':dict(id='original')},reporting_changes=[],reporting_bridges=[],entity_versions=[])
        class Journal:
            def __init__(self):self.calls=[]
            def artifact(self,name,value):pass
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                self.calls.append(stage)
                checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Synthetic source check.',source_refs=[dict(source_id='original',unit_id='page:1')]) for t in payload['required_topics']]
                checks[0].update(status='warning',issue_type='missing_primary_evidence',detail='Required interim original absent.')
                return dict(checks=checks,summary='Must remain blocked')
        journal=Journal()
        with self.assertRaisesRegex(ValueError,'Required interim original absent'):_combined_history_challenge(journal,data,[unit])
        self.assertEqual(journal.calls,['company_combined_history_cohort_1']);self.assertNotIn('combined_history_review',data)

    def test_history_source_selection_precedes_parsing_and_expands_only_on_demand(self):
        from company_initiation.historic_construction.workflow import prepare_history_review_context
        from company_initiation.historic_construction.evidence import _units
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);sources=[]
            for i in range(4):
                path=folder/('original_'+str(i)+'.txt');path.write_text('Original reporting definition '+str(i),encoding='utf-8')
                sources.append(dict(id='source_'+str(i),path=str(path),local_path=path.name,format='txt',category='financial_reports',sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            data=dict(company='SYNTHETIC history selection',history_years=[2024,2025],observations=[],model_configuration={},sources={s['id']:s for s in sources})
            class Journal:
                progress=None
                def __init__(self,path):self.directory=path;path.mkdir();self.artifacts={};self.values={};self.stages=[]
                def artifact(self,name,value):
                    self.values[name]=copy.deepcopy(value);target=self.directory/name;target.write_text(json.dumps(value),encoding='utf-8')
                    self.artifacts[name]=hashlib.sha256(target.read_bytes()).hexdigest()
                def stage(self,name,prompt,payload,schema,validate):
                    self.stages.append(name)
                    self_test.assertEqual(schema['properties']['source_ids']['items']['enum'],['source_'+str(i) for i in range(4)])
                    self_test.assertEqual(schema['properties']['coverage']['items']['properties']['source_ids']['items']['enum'],['source_'+str(i) for i in range(4)])
                    if name=='company_history_sources':
                        self_test.assertEqual(parser.call_count,0)
                        answer=dict(source_ids=['source_0','source_1','source_0'],reasons=['Distinct original years'],coverage=[dict(year=year,source_ids=['source_'+str(i)]*2,period_kinds=['FY','H1'],method='Synthetic complete original') for i,year in enumerate((2024,2025))],gaps=[])
                        if getattr(self,'coverage_extra',False):answer['coverage'][1]['source_ids'].append('source_2')
                        if getattr(self,'unknown',False):answer['source_ids'].append('invented_source')
                        before=copy.deepcopy(answer);result=validate(answer)
                        self_test.assertEqual(answer,before)
                        self_test.assertEqual(result['source_ids'],['source_0','source_1']+(['source_2'] if getattr(self,'coverage_extra',False) else []))
                        self_test.assertEqual(result['coverage'][0]['source_ids'],['source_0'])
                        return result
                    self_test.assertEqual(name,'company_history_source_expansion')
                    return validate(dict(source_ids=['source_2'],reasons=['Missing restatement note'],coverage=[],gaps=[]))
            self_test=self;journal=Journal(folder/'first')
            with patch('company_initiation.historic_construction.evidence._units',wraps=_units) as parser:
                context=prepare_history_review_context(journal,data,sources)
                self.assertEqual(parser.call_count,2)
                self.assertEqual({u['source_id'] for u in context['original_units']},{'source_0','source_1'})
                extra=context['source_loader']([dict(kind='missing_primary_evidence',check='Restatement note absent')])
                self.assertEqual({u['source_id'] for u in extra},{'source_2'});self.assertEqual(parser.call_count,3)
                self.assertEqual(context['source_loader']([dict(kind='context_omission',check='Recheck existing note')]),extra)
                self.assertEqual(parser.call_count,3)
            self.assertEqual(journal.values['history_source_selection.json']['omitted_source_ids'],['source_2','source_3'])
            previous=dict(_reuse_verified=True,directory=str(journal.directory),artifacts=journal.artifacts)
            resumed=Journal(folder/'second')
            with patch('company_initiation.historic_construction.evidence._units',side_effect=AssertionError('Verified parsed originals should be reused')) as parser:
                again=prepare_history_review_context(resumed,data,sources,previous=previous)
            self.assertEqual(again['original_units'],context['original_units'])
            self.assertTrue(all(item['status']=='reused_verified_parsed_original' for item in resumed.values['history_original_index.json']['sources'].values()))
            invalid=Journal(folder/'invalid');invalid.unknown=True
            with patch('company_initiation.historic_construction.evidence._units',side_effect=AssertionError('Unknown source IDs must fail before parsing')) as parser:
                with self.assertRaisesRegex(ValueError,'unknown primary source IDs: invented_source'):
                    prepare_history_review_context(invalid,data,sources)
                parser.assert_not_called()
            coverage_request=Journal(folder/'coverage_request');coverage_request.coverage_extra=True
            with patch('company_initiation.historic_construction.evidence._units',wraps=_units) as parser:
                included=prepare_history_review_context(coverage_request,data,sources)
            self.assertEqual({u['source_id'] for u in included['original_units']},{'source_0','source_1','source_2'})
            self.assertEqual(parser.call_count,3)
            self.assertEqual(coverage_request.values['history_source_selection.json']['omitted_source_ids'],['source_3'])

    def test_history_expansion_returns_requested_parsed_original_without_losing_other_sections(self):
        from company_initiation.historic_construction.workflow import prepare_history_review_context, _combined_history_challenge
        from company_initiation.historic_construction.evidence import _units
        outer=self
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);sources=[]
            for index in range(4):
                path=folder/('source_'+str(index)+'.txt');path.write_text('Complete synthetic original '+str(index)+' with financial notes and amount 100.',encoding='utf-8')
                sources.append(dict(id='source_'+str(index),path=str(path),local_path=path.name,format='txt',category='financial_reports',sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            data=dict(company='SYNTHETIC cached source expansion',history_years=[2020,2021],observations=[],model_configuration={},
                sources={source['id']:source for source in sources},reporting_changes=[],reporting_bridges=[],entity_versions=[])
            class Journal:
                progress=None
                def __init__(self):self.saved={};self.repairs=[]
                def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
                def stage(self,name,prompt,payload,schema,validate):
                    if name=='company_history_sources':
                        return validate(dict(source_ids=['source_0','source_1','source_2'],reasons=['Complete synthetic originals'],gaps=[],
                            coverage=[dict(year=year,source_ids=['source_0','source_1','source_2'],period_kinds=['FY'],method='Synthetic source coverage') for year in (2020,2021)]))
                    outer.assertEqual(name,'company_history_source_expansion')
                    return validate(dict(source_ids=['source_1'],reasons=['Already parsed original omitted from cohort sections'],coverage=[],gaps=[]))
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    outer.assertEqual({unit['source_id'] for unit in payload['evidence']},{'source_0','source_2'})
                    cited=next(unit for unit in payload['evidence'] if unit['source_id']=='source_0')
                    checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Synthetic cited review',
                        source_refs=[dict(source_id=cited['source_id'],unit_id=cited['unit_id'])]) for topic in payload['required_topics']]
                    failed=copy.deepcopy(checks);failed[0].update(status='warning',issue_type='context_omission',detail='Requested already-indexed supporting original is absent from these selected sections.')
                    omitted=self.saved['history_original_index.json']['sources']['source_1']['units'][0]
                    failed[0]['source_refs'].append(dict(source_id='source_1',unit_id=omitted['unit_id']))
                    repaired=repair_context(copy.deepcopy(payload),assess(dict(checks=failed,summary='Context repair needed')))
                    self.repairs.append(copy.deepcopy(repaired))
                    outer.assertEqual({unit['source_id'] for unit in repaired['evidence']},{'source_0','source_1','source_2'})
                    outer.assertEqual(next(unit for unit in repaired['evidence'] if unit['source_id']=='source_2'),
                        next(unit for unit in payload['evidence'] if unit['source_id']=='source_2'))
                    replacement=next(unit for unit in repaired['evidence'] if unit['source_id']=='source_1')
                    checks[0]['source_refs']=[dict(source_id='source_1',unit_id=replacement['unit_id'])]
                    result=dict(checks=checks,summary='Cited complete repaired context');outer.assertEqual(assess(result),[]);return result
            journal=Journal();selection_calls=[]
            def sections(journal,documents,purpose,**kwargs):
                selection_calls.append(copy.deepcopy(documents))
                if len(selection_calls)==1:return [unit for unit in documents if unit['source_id']!='source_1']
                outer.assertEqual(set(kwargs['required_source_ids']),{'source_0','source_1'})
                outer.assertEqual({unit['source_id'] for unit in documents},{'source_0','source_1'})
                return documents
            with patch('company_initiation.historic_construction.evidence._units',wraps=_units) as parser,patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=sections):
                prepared=prepare_history_review_context(journal,data,sources)
                original_units=copy.deepcopy(prepared['original_units'])
                self.assertEqual(parser.call_count,3)
                result=_combined_history_challenge(journal,data,**prepared)
                self.assertEqual(result['status'],'passed');self.assertEqual(parser.call_count,3)
                self.assertEqual(prepared['original_units'],original_units)
                repeated=prepared['source_loader']([dict(kind='context_omission',check='Same original requested again')])
                self.assertEqual(repeated,[unit for unit in original_units if unit['source_id']=='source_1'])
                self.assertEqual(parser.call_count,3)
                self.assertEqual(len({call.args[0] for call in parser.call_args_list}),3)
            self.assertEqual(len(selection_calls),2);self.assertEqual(len(journal.repairs),1)

    def test_sheet_navigation_selects_every_row_without_repeating_row_previews(self):
        from company_initiation.historic_construction.workflow import construction_evidence
        documents=[dict(source_id='original',unit_id='Statement!R'+str(i),text='Full row '+str(i)+' '+('x'*1000),numbers=[dict(index=0,raw=str(i))]) for i in range(1,301)]
        class Journal:
            def stage(self,name,prompt,payload,schema,validate):
                self.payload=payload
                return validate(dict(sections=[dict(source_id='original',first_unit='Statement!R1',last_unit='Statement!R300',reason='Complete statement worksheet')],gaps=[]))
        journal=Journal();selected=construction_evidence(journal,documents,'Complete statement')
        self.assertEqual(len(journal.payload['navigation']),1)
        self.assertEqual(journal.payload['navigation'][0]['last_unit_id'],'Statement!R300')
        self.assertEqual(selected,documents)

    def test_section_source_mismatch_and_sparse_boundaries_have_exact_repair_feedback(self):
        from company_initiation.historic_construction.workflow import construction_evidence
        worksheet=[dict(source_id='actual_workbook',unit_id='Operating segments!R'+str(i),text='Complete original row '+str(i)+' '+'x'*1000,numbers=[]) for i in range(4,304)]
        pdf=[dict(source_id='annual_pdf',unit_id='page:'+str(i),text='Original financial report '+str(i),numbers=[]) for i in range(1,3)]
        owner=self
        class Journal:
            def stage(self,name,prompt,payload,schema,validate):
                def selection(sid,first,last):return dict(sections=[dict(source_id=sid,first_unit=first,last_unit=last,reason='Complete reported segment table')],gaps=[])
                for sid,first,last,expected in [
                    ('annual_pdf','Operating segments!R4','Operating segments!R303','Sources containing BOTH requested endpoints: [{"source_id": "actual_workbook"'),
                    ('actual_workbook','Operating segments!R1','Operating segments!R303','"first_unit": "Operating segments!R4"'),
                    ('invented_source','Operating segments!R4','Operating segments!R303','Supplied source IDs:'),
                    ('actual_workbook','Operating segments!R303','Operating segments!R4','Section range is reversed for actual_workbook')]:
                    with owner.subTest(source=sid,first=first):
                        with owner.assertRaises(ValueError) as caught:validate(selection(sid,first,last))
                        owner.assertIn(expected,str(caught.exception))
                return validate(selection('actual_workbook','Operating segments!R4','Operating segments!R303'))
        self.assertEqual(construction_evidence(Journal(),pdf+worksheet,'Complete segment evidence'),worksheet)


class PositiveDisclosureContinuationTests(unittest.TestCase):
    def test_two_continuations_merge_one_obligation_with_all_families_claims_and_origins(self):
        from company_initiation.historic_construction.workflow import _merge_coverage_obligations, _discovery_obligations_for_research
        original=dict(id='prior_coverage_one',kind='prior_primary_coverage',fiscal_year=2025,period_kind='H1',period_end='2025-06-30',
            source_sha256='same-original',required_families=['sales','cash_flow'],claims=[dict(definition='Original H1 statements',unit_ids=['page:2'])],restored_from=[dict(run='first')])
        first=_merge_coverage_obligations([original],[dict(original,restored_from=[dict(run='second')])])
        second=_merge_coverage_obligations(first,[dict(original,restored_from=[dict(run='third')])])
        self.assertEqual(len(second),1);self.assertEqual(len(second[0]['restored_from']),3)
        self.assertEqual(_discovery_obligations_for_research(first),_discovery_obligations_for_research(second))
        changed=dict(original,required_families=['income_statement'],claims=[dict(definition='Restated H1 perimeter',unit_ids=['page:3'])])
        third=_merge_coverage_obligations(second,[changed])
        self.assertEqual(set(third[0]['required_families']),{'sales','cash_flow','income_statement'})
        self.assertEqual(len(third[0]['claims']),2)
        self.assertNotEqual(_discovery_obligations_for_research(second),_discovery_obligations_for_research(third))

    def fixture(self,root):
        archive=root/'archive';archive.mkdir();outputs=root/'outputs';outputs.mkdir()
        catalog={};old_sources=[]
        for sid in ('annual','half','nine'):
            path=archive/(sid+'.pdf');path.write_bytes(('complete original '+sid).encode())
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            source=dict(id=sid,local_path=path.name,sha256=sha,category='financial_reports',reporting_year=2025)
            old_sources.append(source);catalog['current_'+sid]=dict(source,id='current_'+sid)
        def record(name,entries,parent=None):
            directory=outputs/name;directory.mkdir();path=directory/'disclosure_coverage_2025.json'
            path.write_text(json.dumps(dict(sources=[dict(source_id=sid,disclosures=[dict(period_id='2025-'+kind,
                families=families,definition='Original '+kind+' tables',source_refs=[dict(source_id=sid,unit_id='page:2')])])
                for sid,kind,families in entries],gaps=[])),encoding='utf-8')
            return dict(directory=str(directory),configuration=dict(company='Synthetic',sources=str(archive),as_of='2026-10-25'),
                sources=copy.deepcopy(old_sources),artifacts={path.name:hashlib.sha256(path.read_bytes()).hexdigest()},
                parent_run=str(parent['directory']) if parent else None,_reuse_verified=True)
        old=record('construct_old',[('half','H1',['sales','income_statement','balance_sheet','cash_flow']),('nine','9M',['sales'])])
        latest=record('construct_latest',[('annual','FY',['sales','income_statement'])],old)
        return archive,catalog,[old,latest],latest

    def test_resume_retains_positive_half_and_nine_month_claims_but_needs_revalidation(self):
        from company_initiation.historic_construction.workflow import restore_positive_disclosure_coverage, _year_primary_candidates
        with tempfile.TemporaryDirectory() as folder:
            archive,catalog,records,parent=self.fixture(Path(folder))
            result=restore_positive_disclosure_coverage(parent,records,archive,catalog,'2026-10-25',[2025],{'fiscal_year_end':'12-31'})
            by_kind={item['period_kind']:item for item in result['obligations']}
            self.assertEqual(set(by_kind),{'FY','H1','9M'})
            self.assertEqual(by_kind['H1']['required_families'],['balance_sheet','cash_flow','income_statement','sales'])
            self.assertEqual(by_kind['9M']['required_families'],['sales'])
            self.assertEqual(by_kind['H1']['source_id'],'current_half')
            self.assertEqual(by_kind['H1']['status'],'pending_primary_revalidation')
            self.assertIn('allegation only',by_kind['H1']['claims'][0]['interpretation'])
            selected,_=_year_primary_candidates(catalog,2025,['current_annual'],result['obligations'])
            self.assertEqual(set(selected),set(catalog))
            self.assertNotIn('value',json.dumps(result))

    def test_changed_original_and_tampered_coverage_cannot_inherit_positive_claims(self):
        from company_initiation.historic_construction.workflow import restore_positive_disclosure_coverage
        with tempfile.TemporaryDirectory() as folder:
            archive,catalog,records,parent=self.fixture(Path(folder));args=(parent,records,archive,catalog,'2026-10-25',[2025],{'fiscal_year_end':'12-31'})
            original=(archive/'half.pdf').read_bytes();(archive/'half.pdf').write_bytes(b'changed financial source')
            with self.assertRaisesRegex(ValueError,'original hash changed'):restore_positive_disclosure_coverage(*args)
            catalog['current_half']['sha256']=hashlib.sha256((archive/'half.pdf').read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'changed bytes'):restore_positive_disclosure_coverage(*args)
            (archive/'half.pdf').write_bytes(original);catalog['current_half']['sha256']=hashlib.sha256(original).hexdigest()
            (Path(records[0]['directory'])/'disclosure_coverage_2025.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'artifact hash changed'):restore_positive_disclosure_coverage(*args)

    def test_first_selection_inspects_relevant_hints_and_deduplicates_bytes_without_loading_other_years(self):
        from company_initiation.historic_construction.workflow import _company_year_sources
        from types import SimpleNamespace
        catalog={sid:dict(id=sid,category='financial_reports',sha256=sid,reporting_year=year,title=title)
            for sid,year,title in [('annual',2025,'Annual'),('half',2025,'Interim'),('nine',2025,'Nine-month sales'),
                                 ('false_hint',2025,'Incorrect supplied title'),('other_year',2023,'Annual') ]}
        catalog['half_alias']=dict(catalog['half'],id='half_alias')
        catalog['opaque']=dict(id='opaque',category='financial_reports',sha256='opaque',local_path='official_ab2023cd.pdf')
        saved={};journal=SimpleNamespace(stage=lambda name,prompt,payload,schema,validate:validate(dict(source_ids=['annual'],reasons=['Annual sufficient'],gaps=[])),
            artifact=lambda name,value:saved.update({name:value}))
        result=_company_year_sources(journal,'Synthetic',2025,'2026-10-25',catalog)
        self.assertEqual(set(result['source_ids']),{'annual','half','nine','false_hint','opaque'})
        self.assertEqual(set(saved['year_source_accounting_2025.json']['selected_source_ids']),{'annual'})
        self.assertTrue(all(item['status']=='requires_original_inspection_or_cited_exclusion' for item in result['primary_candidate_accounting']))

    def test_false_metadata_hint_requires_cited_exclusion_and_cannot_create_fake_interim(self):
        from company_initiation.historic_construction.workflow import _year_disclosure_coverage
        from types import SimpleNamespace
        units=[dict(source_id=sid,unit_id='page:1',text=text,numbers=[]) for sid,text in
            [('annual','Year ended 2025 financial statements'),('false','Year ended 2023 financial statements; no 2025 comparative')]]
        ref=lambda sid:[dict(source_id=sid,unit_id='page:1')]
        answer=dict(sources=[dict(source_id='annual',disclosures=[dict(period_id='2025-FY',families=['sales'],definition='2025 annual sales',source_refs=ref('annual'))],no_applicable_disclosure_reason='',source_refs=ref('annual')),
            dict(source_id='false',disclosures=[],no_applicable_disclosure_reason='Original is 2023 and has no requested-year comparative; supplied title was false',source_refs=ref('false'))],gaps=[])
        def stage(name,prompt,payload,schema,validate):
            missing=copy.deepcopy(answer);missing['sources'].pop()
            with self.assertRaisesRegex(ValueError,'omitted selected primary'):validate(missing)
            uncited=copy.deepcopy(answer);uncited['sources'][1]['source_refs']=[]
            with self.assertRaisesRegex(ValueError,'own selected primary'):validate(uncited)
            return validate(answer)
        result=_year_disclosure_coverage(SimpleNamespace(stage=stage,artifact=lambda *args:None),'Synthetic',2025,
            [dict(id='2025-FY'),dict(id='2025-H1')],units,['annual','false'])
        self.assertEqual(result['sources'][1]['disclosures'],[])

    def test_positive_statement_families_cannot_be_downgraded_to_sales_only(self):
        from company_initiation.historic_construction.workflow import _year_disclosure_coverage
        from types import SimpleNamespace
        ref=[dict(source_id='half',unit_id='page:1')]
        obligation=dict(id='prior',fiscal_year=2025,period_kind='H1',required_families=['sales','cash_flow'],claims=[])
        answer=dict(sources=[dict(source_id='half',disclosures=[dict(period_id='2025-H1',families=['sales'],definition='Half-year sales',source_refs=ref)],
            no_applicable_disclosure_reason='',source_refs=ref)],gaps=[],discovery_dispositions=[dict(obligation_id='prior',outcome='supported_primary',period_id='2025-H1',families=['sales'],reporting_basis='Original',reason='H1 supplied',source_refs=ref)])
        journal=SimpleNamespace(stage=lambda name,prompt,payload,schema,validate:validate(answer),artifact=lambda *args:None)
        with self.assertRaisesRegex(ValueError,'positive coverage families cannot disappear'):
            _year_disclosure_coverage(journal,'Synthetic',2025,[dict(id='2025-H1')],
                [dict(source_id='half',unit_id='page:1',text='H1 financial statements',numbers=[])],['half'],discovery_obligations=[obligation])


class DisclosureBasisAdjudicationTests(unittest.TestCase):
    def fixture(self):
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        fact=dict(id='sales-original',row_id='sales',period_id='2025-FY',metric_type='flow',unit='EURm',value=100,
            eligible=True,basis='Original annual net sales',restatement='original',entity_id='group',
            source_refs=[dict(source_id='primary',unit_id='page:51')])
        requirement=dict(obligation_id='retained_fy',period_id='2025-FY',family='sales',
            required_reporting_basis='Consolidated annual statements including cash flow and balances',
            source_refs=[dict(source_id='primary',unit_id='page:53')])
        units=[dict(source_id='primary',unit_id=page,text=text,numbers=[]) for page,text in
            [('page:51','Consolidated original net sales year ended 2025: 100'),
             ('page:53','Annual 2025 consolidated statements; original perimeter, no restatement'),
             ('page:54','Unrelated 2024 financing table')]]
        return fact,requirement,units,integrated_role_contract()

    def test_cited_compatible_prose_and_different_numeric_page_bind_exact_fact_and_scope(self):
        from company_initiation.historic_construction.workflow import _adjudicate_disclosure_bases, _validate_disclosure_coverage
        from types import SimpleNamespace
        fact,requirement,units,roles=self.fixture();before=copy.deepcopy((fact,requirement,units));requests=[]
        def stage(name,prompt,payload,schema,validate):
            self.assertEqual(name,'company_disclosure_basis_review');requests.append(copy.deepcopy(payload))
            self.assertEqual(payload['evidence'],units)
            decision=dict(coverage_id=payload['coverage'][0]['coverage_id'],fact_id=payload['facts'][0]['fact_id'],compatible=True,
                period_analysis='Both are year-ended 2025 flows',entity_and_perimeter_analysis='Same consolidated group',
                definition_and_restatement_analysis='Original annual net sales; no restatement or mixed scope',
                source_refs=[dict(source_id='primary',unit_id=unit,quotation=quote,purpose=purpose) for unit,quote,purpose in
                    [('page:51',units[0]['text'],'fact_table'),('page:53',units[1]['text'],'coverage_scope'),('page:53','original perimeter, no restatement','basis_context')]])
            for changes in ({'fact_id':'invented'},{'definition_and_restatement_analysis':''}):
                with self.assertRaises(ValueError):validate(dict(decisions=[dict(decision,**changes)]))
            adjacent=copy.deepcopy(decision);adjacent['source_refs'][0].update(unit_id='page:54',quotation=units[2]['text'])
            with self.assertRaisesRegex(ValueError,'adjacent unrelated'):validate(dict(decisions=[adjacent]))
            bad=copy.deepcopy(decision);bad['source_refs'][0]['quotation']='Invented revenue quotation'
            with self.assertRaisesRegex(ValueError,'exact quotations'):validate(dict(decisions=[bad]))
            return validate(dict(decisions=[decision]))
        journal=SimpleNamespace(stage=stage,artifact=lambda *args:None)
        with self.assertRaises(ValueError):_validate_disclosure_coverage([fact],[requirement],roles)
        _validate_disclosure_coverage([fact],[requirement],roles,basis_pending=True)
        proof=_adjudicate_disclosure_bases(journal,'Synthetic',2025,'sales',[fact],[requirement],roles,units,{'primary':'original-sha'})
        self.assertEqual(_validate_disclosure_coverage([fact],[requirement],roles,basis_adjudications=proof),[fact])
        for changed in ({'basis':'Restated different perimeter'},{'source_refs':[dict(source_id='primary',unit_id='page:54')]},
                        {'period_id':'2025-H1'}):
            with self.assertRaises(ValueError):_validate_disclosure_coverage([dict(fact,**changed)],[requirement],roles,basis_adjudications=proof)
        changed_requirement=dict(requirement,required_reporting_basis='A different restated perimeter')
        with self.assertRaises(ValueError):_validate_disclosure_coverage([fact],[changed_requirement],roles,basis_adjudications=proof)
        _adjudicate_disclosure_bases(journal,'Synthetic',2025,'sales',[fact],[requirement],roles,units,{'primary':'changed-sha'})
        self.assertNotEqual(requests[0],requests[1]);self.assertEqual((fact,requirement,units),before)

    def test_cited_incompatible_basis_is_saved_then_blocks_without_stage_retry(self):
        from company_initiation.historic_construction.workflow import _adjudicate_disclosure_bases
        from types import SimpleNamespace
        fact,requirement,units,roles=self.fixture();saved={};attempts=[]
        def stage(name,prompt,payload,schema,validate):
            response=dict(decisions=[dict(coverage_id=payload['coverage'][0]['coverage_id'],fact_id=payload['facts'][0]['fact_id'],compatible=False,
                period_analysis='Period matches',entity_and_perimeter_analysis='Perimeter compatibility is not established',
                definition_and_restatement_analysis='Source definitions do not establish equivalence',
                source_refs=[dict(source_id='primary',unit_id=page,quotation=quote,purpose=purpose) for page,quote,purpose in
                    [('page:51',units[0]['text'],'fact_table'),('page:53',units[1]['text'],'coverage_scope'),('page:53','original perimeter, no restatement','basis_context')]])])
            for attempt in range(3):
                attempts.append(attempt)
                try:return validate(copy.deepcopy(response))
                except ValueError:
                    if attempt==2:raise
        journal=SimpleNamespace(stage=stage,artifact=lambda name,value:saved.update({name:copy.deepcopy(value)}))
        with self.assertRaisesRegex(ValueError,'negative decisions preserved'):
            _adjudicate_disclosure_bases(journal,'Synthetic',2025,'sales',[fact],[requirement],roles,units,{'primary':'original-sha'})
        self.assertEqual(attempts,[0]);self.assertFalse(next(iter(saved.values()))[0]['decision']['compatible'])

    def test_cited_negative_reconstruction_equivalence_is_saved_without_regenerating_disagreement(self):
        from company_initiation.historic_construction.workflow import _validate_reconstruction_equivalence, _save_reconstruction_equivalence
        from types import SimpleNamespace
        _,_,units,_=self.fixture();attempts=[];saved={}
        semantic=[dict(candidate_id='candidate',comparisons=[dict(independent_id='independent',numeric_compatible=True)])]
        answer=dict(decisions=[dict(candidate_id='candidate',independent_id='independent',equivalent=False,
            method='Equal rounded numbers do not establish equal perimeter',source_refs=[dict(source_id='primary',unit_id='page:53')])])
        def stage():
            for attempt in range(3):
                attempts.append(attempt)
                try:return _validate_reconstruction_equivalence(copy.deepcopy(answer),semantic,['primary'],units)
                except ValueError:
                    if attempt==2:raise
        journal=SimpleNamespace(artifact=lambda name,value:saved.update({name:copy.deepcopy(value)}))
        with self.assertRaisesRegex(ValueError,'negative reconstruction equivalence preserved'):
            _save_reconstruction_equivalence(journal,'equivalence.json',stage())
        self.assertEqual(attempts,[0]);self.assertEqual(saved['equivalence.json'],answer)
        bad=copy.deepcopy(answer);bad['decisions'][0]['source_refs'][0]['unit_id']='page:999'
        with self.assertRaisesRegex(ValueError,'primary original evidence'):_validate_reconstruction_equivalence(bad,semantic,['primary'],units)


class DisclosureCoverageTests(unittest.TestCase):
    def retained_fixture(self):
        ref=dict(source_id='annual',unit_id='page:2')
        obligation=dict(id='discovery_nine_months',fiscal_year=2025,period_kind='9M',period_end='2025-09-30',
            status='pending_primary_coverage',claims=[dict(detail='Separate nine-month release missing',evidence=[dict(page_url='https://synthetic.invalid/results',sha256='original-index-hash',quotation='2025 nine-month sales')])])
        inventory=dict(sources=[dict(source_id='annual',disclosures=[dict(period_id='2025-9M',families=['sales'],
            definition='Annual original reproduces cumulative nine-month sales on the original perimeter',source_refs=[ref])],
            no_applicable_disclosure_reason='',source_refs=[ref])],gaps=[],discovery_dispositions=[dict(obligation_id=obligation['id'],
                outcome='supported_primary',period_id='2025-9M',families=['sales'],reporting_basis='original_perimeter',
                reason='Exact cumulative sales and original perimeter are reproduced in the later annual original.',source_refs=[ref])])
        units=[dict(source_id='annual',unit_id='page:2',text='2025 nine-month cumulative sales; original perimeter; 90',numbers=[])]
        return obligation,inventory,units

    def retained_inventory(self,answer):
        from company_initiation.historic_construction.workflow import _year_disclosure_coverage
        from types import SimpleNamespace
        obligation,_,units=self.retained_fixture();saved={}
        journal=SimpleNamespace(artifact=lambda name,value:saved.update({name:copy.deepcopy(value)}))
        def stage(name,prompt,payload,schema,validate):
            self.assertEqual(payload['discovery_obligations'],[obligation])
            self.assertIn('discovery_dispositions',schema['required'])
            self.assertNotIn('observations',payload)
            return validate(copy.deepcopy(answer))
        journal.stage=stage
        result=_year_disclosure_coverage(journal,'Synthetic',2025,[dict(id='2025-'+kind) for kind in ('FY','9M','Q3')],
            units,['annual'],discovery_obligations=[obligation])
        self.assertEqual(saved['disclosure_coverage_2025.json'],result)
        return result

    def test_later_primary_report_resolves_exact_nine_month_sales_without_inventing_statements(self):
        from company_initiation.historic_construction.workflow import _task_disclosure_coverage, _validate_disclosure_coverage, _validate_discovery_coverage
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        obligation,answer,_=self.retained_fixture();inventory=self.retained_inventory(answer)
        self.assertEqual(inventory['discovery_obligations'],[obligation])
        self.assertEqual(_task_disclosure_coverage(inventory,['cash_flow','balance_sheet','income_statement']),[])
        requirements=_task_disclosure_coverage(inventory,['sales']);roles=integrated_role_contract()
        fact=dict(row_id='sales',period_id='2025-9M',metric_type='flow',unit='EURm',value=90,eligible=True,
            basis='original_perimeter',source_refs=[dict(source_id='annual',unit_id='page:2')])
        self.assertEqual(_validate_disclosure_coverage([fact],requirements,roles),[fact])
        for changed in ({'period_id':'2025-FY'},{'period_id':'2025-Q3'},{'basis':'restated_perimeter'},
                        {'source_refs':[dict(source_id='vendor',unit_id='sheet:1')]}):
            with self.subTest(changed=changed),self.assertRaisesRegex(ValueError,'omitted directly reported disclosure coverage'):
                _validate_disclosure_coverage([dict(fact,**changed)],requirements,roles)
        resolved=_validate_discovery_coverage({'coverage_obligations':[obligation]},[dict(year=2025,**inventory)])
        self.assertEqual(resolved[0]['period_id'],'2025-9M')

    def test_every_retained_gap_needs_one_cited_nonmissing_disposition(self):
        _,answer,_=self.retained_fixture()
        variants=[]
        for disposition in ([],answer['discovery_dispositions']*2):
            variants.append(dict(answer,discovery_dispositions=disposition))
        for changes in ({'outcome':'unresolved'},{'source_refs':[]},{'period_id':'2025-FY'},
                        {'families':['cash_flow']},{'reporting_basis':''}):
            variants.append(dict(answer,discovery_dispositions=[dict(answer['discovery_dispositions'][0],**changes)]))
        for bad in variants:
            with self.subTest(bad=bad['discovery_dispositions']),self.assertRaises(ValueError):self.retained_inventory(bad)

    def test_cited_inapplicable_gap_correction_does_not_claim_numeric_coverage(self):
        _,answer,_=self.retained_fixture()
        answer['discovery_dispositions'][0].update(outcome='not_applicable',period_id=None,families=[],reporting_basis='',
            reason='The cited original establishes that the navigation description referred to a different issuer; the initial coverage claim was erroneous.')
        result=self.retained_inventory(answer)
        self.assertEqual(result['discovery_dispositions'][0]['outcome'],'not_applicable')
        answer['discovery_dispositions'][0]['families']=['sales']
        with self.assertRaisesRegex(ValueError,'must not claim numeric coverage'):self.retained_inventory(answer)

    def test_blind_period_obligations_exclude_cited_disposition_and_basis_conclusions(self):
        from company_initiation.historic_construction.workflow import _task_disclosure_coverage, _blind_disclosure_requirements
        _,answer,_=self.retained_fixture();requirements=_task_disclosure_coverage(answer,['sales'])
        blind=_blind_disclosure_requirements(requirements)
        self.assertEqual(blind,[dict(period_id='2025-9M',family='sales')])
        self.assertTrue(any('required_reporting_basis' in item for item in requirements))
        self.assertNotIn('source_refs',blind[0]);self.assertNotIn('outcome',blind[0]);self.assertNotIn('definition',blind[0])

    def test_unassigned_retained_gap_cannot_disappear_before_combined_history(self):
        from company_initiation.historic_construction.workflow import _validate_discovery_coverage
        obligation,answer,_=self.retained_fixture()
        with self.assertRaisesRegex(ValueError,'never reached primary coverage adjudication'):
            _validate_discovery_coverage({'coverage_obligations':[obligation]},[])
        bad=copy.deepcopy(answer);bad['discovery_dispositions'][0]['outcome']='unresolved'
        with self.assertRaisesRegex(ValueError,'Unresolved required discovery coverage'):
            _validate_discovery_coverage({'coverage_obligations':[obligation]},[dict(year=2025,**bad)])

    def fixture(self):
        sources=[];units=[]
        for sid,pid,families in [('annual','2025-FY',['sales','income_statement','balance_sheet','cash_flow']),
                                 ('half','2025-H1',['sales','income_statement','balance_sheet','cash_flow']),
                                 ('quarter','2025-Q1',['sales'])]:
            ref=dict(source_id=sid,unit_id='page:1')
            sources.append(dict(source_id=sid,disclosures=[dict(period_id=pid,families=families,
                definition='Synthetic original '+pid+' '+', '.join(families),source_refs=[ref])],
                no_applicable_disclosure_reason='',source_refs=[ref]))
            units.append(dict(source_id=sid,unit_id='page:1',text='Synthetic '+pid+' full financial table',numbers=[]))
        return dict(sources=sources,gaps=[]),units

    def test_required_section_sources_cannot_silently_drop_half_year(self):
        from company_initiation.historic_construction.workflow import construction_evidence
        inventory,units=self.fixture();units[0]['text']+='x'*180001;owner=self
        class Journal:
            def stage(self,name,prompt,payload,schema,validate):
                owner.assertEqual(payload['required_source_ids'],['annual','half','quarter'])
                sections=[dict(source_id=sid,first_unit='page:1',last_unit='page:1',reason='Complete original table') for sid in ('annual','quarter')]
                with owner.assertRaisesRegex(ValueError,'disclosure omitted from section selection: half'):
                    validate(dict(sections=sections,gaps=[]))
                sections.append(dict(source_id='half',first_unit='page:1',last_unit='page:1',reason='Complete H1 table'))
                return validate(dict(sections=sections,gaps=[]))
        self.assertEqual(construction_evidence(Journal(),units,'Original cadence',required_source_ids=['annual','half','quarter']),units)

    def test_evidence_first_inventory_requires_each_source_and_its_original_citations(self):
        from company_initiation.historic_construction.workflow import _year_disclosure_coverage
        inventory,units=self.fixture();owner=self
        class Journal:
            def artifact(self,name,value):self.saved=(name,value)
            def stage(self,name,prompt,payload,schema,validate):
                owner.assertEqual(name,'company_year_coverage')
                for key in ('candidates','concepts','observations','values','verdicts'):owner.assertNotIn(key,payload)
                omitted=copy.deepcopy(inventory);omitted['sources'].pop(1)
                with owner.assertRaisesRegex(ValueError,'omitted selected primary sources: half'):validate(omitted)
                wrong=copy.deepcopy(inventory);wrong['sources'][1]['disclosures'][0]['source_refs'][0]['source_id']='annual'
                with owner.assertRaisesRegex(ValueError,'own selected primary source: half'):validate(wrong)
                return validate(copy.deepcopy(inventory))
        journal=Journal();answer=_year_disclosure_coverage(journal,'Synthetic',2025,
            [dict(id='2025-'+p) for p in ('FY','H1','Q1')],units,['annual','half','quarter'])
        self.assertEqual(answer,inventory);self.assertEqual(journal.saved[0],'disclosure_coverage_2025.json')

    def test_reported_half_year_is_required_but_sales_only_quarter_does_not_create_statements(self):
        from company_initiation.historic_construction.workflow import _task_disclosure_coverage, _validate_disclosure_coverage
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        inventory,_=self.fixture();roles=integrated_role_contract()
        requirements=_task_disclosure_coverage(inventory,['sales','income_statement','balance_sheet','cash_flow'])
        facts=[]
        for period in ('2025-FY','2025-H1'):
            for row,kind in [('sales','flow'),('parent_profit','flow'),('total_assets','stock'),('cfo','flow')]:
                facts.append(dict(row_id=row,period_id=period,metric_type=kind,unit='EURm',value=100,eligible=True))
        facts.append(dict(row_id='sales',period_id='2025-Q1',metric_type='flow',unit='EURm',value=20,eligible=True))
        self.assertIs(_validate_disclosure_coverage(facts,requirements,roles),facts)
        annual_only=[fact for fact in facts if fact['period_id']!='2025-H1']
        with self.assertRaisesRegex(ValueError,'2025-H1'):_validate_disclosure_coverage(annual_only,requirements,roles)
        cash_requirements=_task_disclosure_coverage(inventory,['cash_flow'])
        self.assertEqual({item['source_id'] for item in cash_requirements},{'annual','half'})
        self.assertNotIn('2025-Q1',{item['period_id'] for item in cash_requirements})

    def test_missing_or_ineligible_fact_cannot_satisfy_source_coverage(self):
        from company_initiation.historic_construction.workflow import _validate_disclosure_coverage
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        requirement=[dict(period_id='2025-H1',family='sales',source_id='half')]
        for value,eligible in [(None,True),(40,False)]:
            with self.subTest(value=value,eligible=eligible),self.assertRaisesRegex(ValueError,'2025-H1'):
                _validate_disclosure_coverage([dict(row_id='sales',period_id='2025-H1',metric_type='flow',value=value,eligible=eligible)],requirement,integrated_role_contract())


class OfficialUrlRecoveryTests(unittest.TestCase):
    def test_unselected_original_page_supplies_cited_recovery_index(self):
        from company_initiation.historic_construction.workflow import construction_evidence, official_url_catalog, recover_official_indexes
        url='https://synthetic.invalid/financial-results'
        units=[dict(source_id='original',unit_id='page:'+str(i),text='Financial statement\n'+'x'*65000,numbers=[])
            for i in range(1,5)]
        units[-1]['text']='Company contacts: official investor publications '+url+'\n'+units[-1]['text']
        class Journal:
            def __init__(self):self.saved={};self.calls=[]
            def artifact(self,name,value):self.saved[name]=value
            def stage(self,name,prompt,payload,schema,validator):
                self.calls.append(name)
                if name=='company_source_sections':
                    return validator(dict(sections=[dict(source_id='original',first_unit='page:1',last_unit='page:2',reason='Statements')],gaps=[]))
                self.payload=payload
                return validator(dict(indexes=[dict(url=url,source_refs=[dict(source_id='original',unit_id='page:4')],reason='Company investor publications contact')],gaps=[]))
        journal=Journal();catalog=official_url_catalog(units,[])
        selected=construction_evidence(journal,units,'Financial statements')
        self.assertFalse(any(url in unit['text'] for unit in selected))
        self.assertEqual(recover_official_indexes(journal,'SYNTHETIC issuer','2026-10-25',{'official_indexes':[]},catalog),[url])
        self.assertEqual(journal.calls,['company_source_sections','company_official_index_recovery'])
        observed=next(item for item in catalog['entries'] if item['url']==url)
        self.assertEqual(observed['evidence'][0]['source_ref']['unit_id'],'page:4')
        self.assertEqual(journal.payload['whole_original_url_catalog']['text_units'],4)
        self.assertEqual(journal.saved['official_index_recovery.json']['status'],'recovered')

    def test_annotation_only_url_and_document_origin_preserve_provenance(self):
        from pypdf import PdfWriter
        from pypdf.annotations import Link
        from company_initiation.historic_construction.workflow import official_url_catalog, recover_official_indexes
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'original.pdf';writer=PdfWriter();writer.add_blank_page(width=400,height=400)
            writer.add_annotation(page_number=0,annotation=Link(rect=(10,10,100,50),url='https://synthetic.invalid/publications'))
            with path.open('wb') as target:writer.write(target)
            source=dict(id='original',format='pdf',path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                url='https://synthetic.invalid/archive/annual.pdf',title='SYNTHETIC company annual report')
            catalog=official_url_catalog([dict(source_id='original',unit_id='page:1',text='',numbers=[])],[source])
        self.assertEqual(catalog['pdf_uri_annotations'],1);self.assertEqual(catalog['limitations'],[])
        observed={item['url']:item for item in catalog['entries']}
        self.assertEqual(observed['https://synthetic.invalid/']['derivation'],'origin_of_observed_url')
        annotation=observed['https://synthetic.invalid/publications']['evidence'][0]
        self.assertEqual(annotation['kind'],'pdf_uri_annotation')
        self.assertEqual(annotation['source_ref'],dict(source_id='original',unit_id='page:1',annotation_index=0))
        class Journal:
            def artifact(self,name,value):self.result=value
            def stage(self,*args):raise AssertionError('Observed scope index needs no additional AI stage')
        journal=Journal()
        self.assertEqual(recover_official_indexes(journal,'SYNTHETIC issuer','2026-10-25',
            {'official_indexes':['https://synthetic.invalid/publications']},catalog),['https://synthetic.invalid/publications'])

    def test_recovery_rejects_guessed_paths_and_wrong_original_citations(self):
        from company_initiation.historic_construction.workflow import official_url_catalog, recover_official_indexes
        catalog=official_url_catalog([dict(source_id='original',unit_id='page:9',text='Official company https://synthetic.invalid/',numbers=[])],[])
        class Journal:
            def artifact(self,*args):pass
            def stage(self,name,prompt,payload,schema,validator):return validator(self.answer)
        for url,unit,error in [('https://synthetic.invalid/investors','page:9','exactly match'),('https://synthetic.invalid/','page:1','exact original')]:
            journal=Journal();journal.answer=dict(indexes=[dict(url=url,source_refs=[dict(source_id='original',unit_id=unit)],reason='Synthetic')],gaps=[])
            with self.subTest(url=url,unit=unit),self.assertRaisesRegex(ValueError,error):
                recover_official_indexes(journal,'SYNTHETIC issuer','2026-10-25',{'official_indexes':[]},catalog)

    def test_no_candidates_retains_recovery_gap_without_paid_retry(self):
        from company_initiation.historic_construction.workflow import official_url_catalog, recover_official_indexes
        class Journal:
            def artifact(self,name,value):self.result=value
            def stage(self,*args):raise AssertionError('No evidence cannot justify a research request')
        journal=Journal();catalog=official_url_catalog([dict(source_id='original',unit_id='page:1',text='No website supplied',numbers=[])],[])
        self.assertEqual(recover_official_indexes(journal,'SYNTHETIC issuer','2026-10-25',
            {'official_indexes':['https://synthetic.invalid/guessed']},catalog),[])
        self.assertEqual(journal.result['status'],'no_observed_candidates')
        self.assertEqual(journal.result['rejected_unobserved_urls'],['https://synthetic.invalid/guessed'])

    def test_direct_pdf_index_gets_recovery_and_cannot_be_reselected(self):
        from company_initiation.historic_construction.workflow import official_url_catalog, recover_official_indexes
        pdf='https://synthetic.invalid/original.pdf';origin='https://synthetic.invalid/'
        catalog=official_url_catalog([], [dict(id='original',url=pdf,title='Synthetic original')])
        class Journal:
            def artifact(self,*args):pass
            def stage(self,name,prompt,payload,schema,validator):
                self.stage_name=name
                with self_test.assertRaisesRegex(ValueError,'not a navigation index'):
                    validator(dict(indexes=[dict(url=pdf,source_refs=[dict(source_id='original',unit_id='source_metadata:url')],reason='Original')],gaps=[]))
                return validator(dict(indexes=[dict(url=origin,source_refs=[dict(source_id='original',unit_id='source_metadata:url')],reason='Observed official origin; follow actual links')],gaps=[]))
        self_test=self;journal=Journal()
        self.assertEqual(recover_official_indexes(journal,'SYNTHETIC issuer','2026-10-25',{'official_indexes':[pdf]},catalog),[origin])
        self.assertEqual(journal.stage_name,'company_official_index_recovery')


class FreshResearchEntryTests(unittest.TestCase):
    _valuation_absence_fields=('other_claims','other_assets','restricted_cash','pension_claim','deferred_consideration','dilution_shares')

    def _write_valuation_absence_notes(self,data,archive):
        from openpyxl import load_workbook
        source=data['sources']['synthetic_primary_statements'];path=archive/source['local_path']
        book=load_workbook(path);sheet=book.active
        for field in self._valuation_absence_fields:
            unit='million additional shares' if field=='dilution_shares' else 'GBP millions'
            sheet.append(['SYNTHETIC valuation absence '+field+': explicitly no such claim or adjustment at 2025-06-30; '+unit,0.])
        book.save(path);book.close()
        source['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()

    def _valuation_absence_answer(self,payload):
        entries=[]
        for field in self._valuation_absence_fields:
            matches=[unit for unit in payload['evidence'] if 'SYNTHETIC valuation absence '+field+':' in unit['text']]
            self.assertEqual(len(matches),1,'The mocked research must cite its exact synthetic absence note')
            unit=matches[0];token=next(token for token in unit['numbers'] if token.get('locator','').startswith('B'))
            self.assertEqual(float(token['raw']),0.)
            ref=dict(source_id=unit['source_id'],unit_id=unit['unit_id'])
            entries.append(dict(field=field,calculation='sum',
                terms=[dict(reference=dict(ref,number_index=token['index'],number_format='dot_decimal'),multiplier=1.,weight=1.)],
                denominator_terms=[],estimated_value=None,as_of='2025-06-30',status='reported',
                method='Synthetic original explicitly establishes absence of '+field+'; Python reads its stated zero, rather than inferring absence from missing disclosure.',
                source_refs=[ref],unit='shares_millions' if field=='dilution_shares' else 'reporting_currency_millions',
                currency='GBP',price_unit_scale=1.,date_evidence=''))
        return dict(entries=entries,conventions=[],gaps=['Synthetic fixture has no researched market parameters.'])

    def test_synthetic_valuation_absence_notes_pass_research_and_backend_preflight(self):
        from types import SimpleNamespace
        from tests.test_periodic_model import _write_synthetic_originals
        from tests.test_valuation import fixture
        from company_initiation.forecast_construction.construction import validate_shape
        from company_initiation.historic_construction.evidence import SourceStore, inventory_local_sources
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        from company_initiation.dcf_construction.valuation import generate_valuation_inputs, value_company
        data=different_period_company()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'company';archive.mkdir()
            _write_synthetic_originals(data,archive);self._write_valuation_absence_notes(data,archive)
            store=SourceStore(root/'parsed')
            for source in inventory_local_sources(archive)['sources']:store.add_local(source,root=archive)
            documents=store.read_documents([dict(source_id=source['id'],unit_id=next(iter(store._units[source['id']]))) for source in store.sources])
            stages=[]
            def stage(name,prompt,payload,schema,validator):
                stages.append(name);answer=self._valuation_absence_answer(payload)
                validate_shape(answer,schema)
                return validator(answer)
            journal=SimpleNamespace(state={},stage=stage,artifact=lambda name,value:None)
            config=research_valuation_configuration(journal,data,documents,store)
            self.assertEqual(stages,['company_valuation_research','company_valuation_review'])
            self.assertEqual(set(config['assumptions']),set(self._valuation_absence_fields))
            for entry in config['assumptions'].values():
                self.assertEqual(entry['value'],0.);self.assertEqual(entry['status'],'reported')
                self.assertEqual(entry['source_refs'][0]['raw'],0.)
            spec,values,_=fixture('2025-06-30')
            inputs=generate_valuation_inputs(spec,values,dict(model_configuration={'valuation':config}),valuation_date='2025-06-30')
            result=value_company(spec,values,inputs,include_sensitivities=False)
            self.assertEqual(result['status'],'provisional',result['diagnostics'])
            self.assertEqual(inputs['assumptions']['risk_free_rate']['status'],'provisional_assumption')
            self.assertIsNone(inputs['market']['price']['value'])
            self.assertEqual(inputs['market']['price']['status'],'missing')

    def test_scope_section_selection_requests_evidence_for_every_required_driver_category(self):
        from company_initiation.historic_construction.workflow import research_company_inputs
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.historic_construction.evidence import inventory_local_sources
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'company';reports=archive/'financial_reports';reports.mkdir(parents=True)
            original='SYNTHETIC annual reporting and driver evidence. Fiscal year ends 31 December.'
            (reports/'annual.txt').write_text(original,encoding='utf-8')
            source=inventory_local_sources(archive)['sources'][0]
            provider=OpenAIProvider(api_key='SYNTHETIC-TEST-KEY');captured={}
            def select(**kwargs):
                self.assertEqual(kwargs['payload']['stage'],'company_identity_sources')
                provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=10,output_tokens=5,total_tokens=15),output=[])
                return dict(source_ids=[source['id']],reasons=['Synthetic complete original'],gaps=[])
            def capture(journal,documents,purpose,**kwargs):
                captured.update(documents=documents,purpose=purpose)
                raise ValueError('Synthetic stop after scope retrieval context')
            with patch.object(provider,'complete',side_effect=select) as calls,patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=capture), \
                 self.assertRaisesRegex(ValueError,'Synthetic stop after scope retrieval context'):
                research_company_inputs(root,'SYNTHETIC driver evidence',archive,as_of='2026-10-25',years=[2025],provider=provider)
            self.assertEqual(calls.call_count,1)
            purpose=captured['purpose'].lower()
            for category in ('material revenue','causal operating costs','working capital','capex','depreciation','financing','tax','portfolio events','acquisitions','disposals','reporting reorganisations'):
                with self.subTest(category=category):self.assertIn(category,purpose)
            self.assertIn('timing/lag',purpose);self.assertIn('associated notes',purpose)
            self.assertIn(original,captured['documents'][0]['text'])

    def test_saved_research_journal_preserves_unicode_original_line_separators(self):
        from company_initiation.shared_runtime import digest
        from company_initiation.forecast_construction.integrated import verified_integrated_record
        with tempfile.TemporaryDirectory() as temp:
            outputs=Path(temp);run=outputs/'construct_research_fixture';run.mkdir()
            request=dict(model='gpt-6-luna',evidence='Original paragraph\u2028and next page\u0085still one JSON record')
            calls=[dict(call_id='fixture_call',model='gpt-6-luna',request=request,signature=digest(request),result={})]
            record=dict(directory=str(run),calls=calls,sources=[],artifacts={})
            (run/'record.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
            (run/'calls.jsonl').write_text(json.dumps(calls[0],ensure_ascii=False)+'\n',encoding='utf-8')
            self.assertEqual(verified_integrated_record(run,outputs)['calls'],calls)

    def test_large_original_retrieval_keeps_complete_selected_units_and_numeric_ids(self):
        from company_initiation.historic_construction.workflow import construction_evidence
        units=[dict(source_id='synthetic_original',unit_id='page:'+str(i),
            text=('Complete synthetic section '+str(i)+'\n')+'x'*65000,
            numbers=[dict(index=17,raw='123.4')]) for i in range(1,5)]
        class Journal:
            def stage(self,stage,prompt,payload,schema,validator):
                self.payload=payload
                return validator(dict(sections=[dict(source_id='synthetic_original',first_unit='page:2',last_unit='page:3',reason='Complete statements and definitions')],gaps=['Synthetic financing note unavailable']))
        data=different_period_company();data['model_configuration']['limitations']=[]
        journal=Journal();selected=construction_evidence(journal,units,'Synthetic cash-flow task',limitations=data['model_configuration']['limitations'])
        self.assertEqual(selected,units[1:3])
        self.assertEqual(selected[0]['numbers'][0]['index'],17)
        self.assertEqual(len(journal.payload['navigation']),4)
        self.assertNotIn('numbers',journal.payload['navigation'][0])
        limitation='Source retrieval for Synthetic cash-flow task: Synthetic financing note unavailable'
        self.assertEqual(data['model_configuration']['limitations'],[limitation])
        self.assertIn(limitation,build_periodic_spec(data,2)['gaps'])

    def test_company_driver_definitions_require_resolvable_original_citations(self):
        from company_initiation.historic_construction.workflow import _validate_driver_references
        ref=dict(source_id='original',unit_id='page:1')
        scope=dict(driver_map=[dict(id='activity',source_refs=[ref])],
            revenue_models=[dict(entity_id='north',source_refs=[ref])])
        units={'original':{'page:1':{}}}
        _validate_driver_references(scope,units)
        for category in ('driver_map','revenue_models'):
            missing=copy.deepcopy(scope);missing[category][0]['source_refs']=[]
            with self.subTest(category=category),self.assertRaisesRegex(ValueError,'requires original citations'):
                _validate_driver_references(missing,units)
        with self.assertRaisesRegex(ValueError,'unresolved original citation'):
            _validate_driver_references(scope,{'original':{'page:2':{}}})

    def test_research_anchor_binding_supports_organic_and_estimated_segment_da(self):
        from company_initiation.historic_construction.workflow import _bind_research_anchors
        data=different_period_company();base=str(data['history_years'][-1])
        for observation in data['observations']:
            if observation['kind']!='FY':continue
            role=data['historical'].setdefault(observation['row_id'],dict(values={},sources={},basis={}))
            year=str(observation['fiscal_year'])
            role['values'][year]=observation['value'];role['sources'][year]=observation['source_refs']
            if isinstance(role['basis'],dict):role['basis'][year]=observation['basis']
        models={segment['id']:dict(method='aggregate_organic') for segment in data['segments']}
        data['model_configuration']['revenue_models']=models
        allocations=[]
        for entity,entity_id in [(s,s['id']) for s in data['segments']]+[(data['corporate'],'corporate')]:
            role=entity_id+'_da';reported=data['historical'].pop(role)
            allocations.append(dict(row_id=role,year=int(base),amount=entity['da'+base],status='estimated',
                method='SYNTHETIC pure D&A allocation from distinct reported combined measures',source_refs=reported['sources'][base]))
            for field in list(entity):
                if field.endswith(base):entity.pop(field)
            data['observations']=[o for o in data['observations'] if o['row_id']!=role]
            if entity_id!='corporate':
                data['historical'][entity_id+'_organic']=dict(values={base:.03},sources={base:reported['sources'][base]},basis=data['forecast_basis'])
                for metric in ('pricing','rig'):
                    data['historical'].pop(entity_id+'_'+metric,None)
                    data['observations']=[o for o in data['observations'] if o['row_id']!=entity_id+'_'+metric]
        data['model_configuration']['historical_allocations']=allocations
        _bind_research_anchors(data,models)
        for segment in data['segments']:
            self.assertEqual(segment['og'+base],.03)
            self.assertNotIn('organic'+base,segment)
            self.assertNotIn('da'+base,segment)
            self.assertNotIn(segment['id']+'_da',data['historical'])
        self.assertNotIn('da'+base,data['corporate'])
        spec=build_periodic_spec(data,2)
        rows={r['id']:r for r in spec['rows']}
        for allocation in allocations:
            self.assertEqual(rows[allocation['row_id']]['cells'][base+'-FY']['status'],'estimated_historical')
        self.assertIn('north_organic',rows)

    def test_missing_scope_accounting_is_distinct_from_arithmetic_status(self):
        from company_initiation.forecast_construction.workflow import model_financial_completeness
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
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.__main__ import main
        data=different_period_company()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive=root/'company';archive.mkdir()
            (root/'pyproject.toml').write_text('[tool.research-platform]\ncheap-review-repairs = 1\n',encoding='utf-8')
            if with_fx:
                from shared_FX.fx_store import FXStore
                from shared_FX.fx import publication_dates
                from tests.test_shared_fx import quote
                database=root/'shared.sqlite'
                with FXStore(database) as store:
                    quotes=[]
                    for day in publication_dates('2023-01-01','2026-10-23'):
                        quotes.extend([quote(day,.8),quote(day,150,currency='JPY')])
                    store.import_quotes(quotes,{'fixture':'Different GBP June-year-end company shared FX'})
                with (root/'pyproject.toml').open('a',encoding='utf-8') as settings:settings.write('fx-database = "shared.sqlite"\n')
            _write_synthetic_originals(data,archive)
            self._write_valuation_absence_notes(data,archive)
            inventory=inventory_local_sources(archive)
            sources=inventory['sources'];by_old={Path(s['local_path']).stem:s['id'] for s in sources}
            provider=OpenAIProvider(api_key='SYNTHETIC-TEST-KEY')
            review_payloads={}
            def answer(**kwargs):
                payload=kwargs['payload'];stage=payload['stage']
                if stage.startswith('integrated_'):review_payloads[stage]=copy.deepcopy(payload)
                provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=10,output_tokens=5,total_tokens=15),output=[])
                if stage in ('company_identity_sources','company_year_sources'):
                    if stage=='company_identity_sources':
                        captured=list((root/'outputs').glob('construct_research_*/engine_contract.json'))
                        self.assertEqual(len(captured),1,'Engine contract must exist before the first research request')
                        self.assertIn('sales',json.loads(captured[0].read_text(encoding='utf-8'))['roles']['group_roles'])
                    return dict(source_ids=[] if payload.get('years')==[2026] else list(by_old.values()),reasons=['Synthetic originals'],gaps=[])
                if stage=='company_source_sections':
                    selected={}
                    for unit in payload['navigation']:
                        selected.setdefault(unit['source_id'],[]).extend([unit['unit_id'],unit.get('last_unit_id',unit['unit_id'])])
                    return dict(sections=[dict(source_id=sid,first_unit=ids[0],last_unit=ids[-1],reason='Complete synthetic financial evidence') for sid,ids in selected.items()],gaps=[])
                if stage=='company_year_coverage':
                    for key in ('candidates','concepts','observations','values'):self.assertNotIn(key,payload)
                    entries=[]
                    for old,sid in by_old.items():
                        by_period={}
                        for observation in data['observations']:
                            if observation['fiscal_year']!=payload['year']:continue
                            refs=[ref for ref in observation['source_refs'] if ref['source_id']==old]
                            if not refs:continue
                            row=observation['row_id'];family={'sales':'sales','parent_profit':'income_statement','total_assets':'balance_sheet','cfo':'cash_flow'}.get(row)
                            if not family:continue
                            ref=refs[0];pid=observation['period_id']
                            entry=by_period.setdefault(pid,dict(period_id=pid,families=[],definition='SYNTHETIC directly reported '+pid,source_refs=[]))
                            if family not in entry['families']:entry['families'].append(family)
                            entry['source_refs'].append(dict(source_id=sid,unit_id=ref['sheet']+'!R'+ref['cell'][1:]))
                        original=next(unit for unit in payload['evidence'] if unit['source_id']==sid)
                        entries.append(dict(source_id=sid,disclosures=list(by_period.values()),no_applicable_disclosure_reason='' if by_period else 'SYNTHETIC source has no table for the requested year.',source_refs=[dict(source_id=sid,unit_id=original['unit_id'])]))
                    return dict(sources=entries,gaps=[])
                if stage=='company_valuation_sources':
                    return dict(source_ids=list(by_old.values()),reasons=['Synthetic latest valuation notes'],gaps=[])
                if stage in ('company_valuation_research','company_valuation_review'):
                    return self._valuation_absence_answer(payload)
                if stage=='company_reporting_scope':
                    self.assertIn('annual, half_year or quarterly',kwargs['instructions'])
                    self.assertIn('retain full_statement_frequency separately',kwargs['instructions'])
                    self.assertIn('one primary consolidation hierarchy',kwargs['instructions'])
                    ref=dict(source_id=next(iter(by_old.values())),unit_id='SYNTHETIC disclosures!R3')
                    return dict(currency='GBP',fiscal_year_end='06-30',latest_completed_year=2025,forecast_frequency='half_year',full_statement_frequency='quarterly',reporting_basis='current_components_basis',segments=[dict(id=s['id'],label=s['label']) for s in data['segments']],corporate_label='Corporate',
                        primary_hierarchy='SYNTHETIC operating components',supplementary_dimensions=['SYNTHETIC customer geography'],
                        revenue_models=[dict(entity_id=s['id'],method='additive_contributions',definition='SYNTHETIC disclosed pricing and activity contributions',source_refs=[ref]) for s in data['segments']],
                        driver_map=[dict(id='synthetic_activity',category='revenue',entity_id='north',economic_meaning='SYNTHETIC activity contribution',
                            affected_lines=['north_sales','north_pool_cogs'],mechanism='Activity affects sales and the variable cost pool',frequency='half_year',lag='same_period',
                            evidence_and_feasibility='SYNTHETIC source disclosures; temporary future input',materiality='Material sales and cost driver',status='synthetic_fixture',source_refs=[ref])],
                        official_indexes=['https://synthetic.invalid/releases'],source_references=[],gaps=['SYNTHETIC optional input-cost detail remains undisclosed'])
                if stage in ('company_year_mapping','company_year_blind','company_year_mapping_revision','company_year_blind_reextraction'):
                    self.assertIn('sales',payload['engine_contract']['roles']['group_roles'])
                    self.assertEqual(payload['engine_contract']['current_segment_ids'],[s['id'] for s in data['segments']])
                    self.assertIn('never group_sales/group_cogs/group_da',kwargs['instructions'])
                    self.assertIn('Map ordinary equity issuance proceeds to issuance_cash',kwargs['instructions'])
                    self.assertIn('never relabel equity funding as debt',kwargs['instructions'])
                    allowed=kwargs['schema']['properties']['observations']['items']['properties']['period_id']['enum']
                    self.assertTrue(all(period.startswith(str(payload['year'])+'-') for period in allowed))
                    facts=[]
                    for o in data['observations']:
                        if o['fiscal_year']!=payload['year']:continue
                        if payload.get('concepts') and (o['row_id'],o['period_id']) not in {(c['row_id'],c['period_id']) for c in payload['concepts']}:continue
                        terms=[]
                        for ref in o['source_refs']:
                            terms.append(dict(reference=dict(source_id=by_old[ref['source_id']],unit_id=ref['sheet']+'!R'+ref['cell'][1:],number_index=0,number_format='dot_decimal'),source_raw=str(ref['raw']),multiplier=ref['multiplier'],weight=ref.get('contribution_weight',1)))
                        facts.append(dict(row_id=o['row_id'],label=o['label'],period_id=o['period_id'],unit=o['unit'],metric_type=o['metric_type'],entity_id=o['entity_id'],basis=o['basis'],definition_id=o['definition_id'],scope=o['scope'],terms=terms,rounding_increment=0,
                            restatement='original',restatement_vintage=None,classification_basis='Synthetic original financial table and period heading.',
                            classification_source_refs=[{k:terms[0]['reference'][k] for k in ('source_id','unit_id')}]))
                    if stage=='company_year_blind' and not with_fx:
                        facts[-1]['basis']+=' alternate description'
                        facts[0]['terms'][0]['weight']*=-1
                    if stage=='company_year_mapping_revision':
                        self.assertTrue(list((root/'outputs').glob('construct_research_*/blind_initial_*_0.json')))
                        self.assertIn('independent',payload)
                    if stage=='company_year_blind_reextraction':
                        for field in ('candidates','independent','disputes','review_challenge'):
                            self.assertNotIn(field,payload)
                        self.assertTrue(all(set(c)=={'row_id','label','period_id','unit'} for c in payload['concepts']))
                    return dict(observations=facts,reporting_changes=['Synthetic predecessor has a different scope; retain its original basis.'],gaps=[])
                if stage=='company_reconstruction_equivalence':
                    self.assertTrue(list((root/'outputs').glob('construct_research_*/blind_*_0.json')))
                    ref=payload['evidence'][0]
                    return dict(decisions=[dict(candidate_id=item['candidate_id'],independent_id=next(c['independent_id'] for c in item['comparisons'] if c['numeric_compatible']),
                        equivalent=True,method='Synthetic primary definition establishes identical perimeter despite alternate basis description.',
                        source_refs=[dict(source_id=ref['source_id'],unit_id=ref['unit_id'])]) for item in payload['disputes']])
                if stage.startswith('company_combined_history'):
                    ref=payload['evidence'][0]
                    return dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],
                        detail='SYNTHETIC original cadence and explicitly separated predecessor/current identities checked.',
                        source_refs=[dict(source_id=ref['source_id'],unit_id=ref['unit_id'])]) for topic in payload['required_topics']],
                        summary='Synthetic combined-history fixture; no real-company validation.')
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
                        method='activity_cost' if role=='cogs' else 'budget_delta',effective_activity_sensitivity=.5 if role=='cogs' else 0,input_cost_includes_transaction_fx=False,
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
                    contracts=dict(source_rounding_tolerance=0,cost_pools=pools,scope_events=[],
                        normalisation={key:dict(annual_amount=0,reason='Synthetic no-adjustment policy',source_refs=[ref]) for key in ('net_other_trading','net_other_operating')},
                        dividends={side:dict(annual_amount=-data['historical'][role]['values']['2025'],
                            payment_weights=[dict(period_kind='Q4',weight=1)],reason='Synthetic annual cash pool paid at fiscal close',source_refs=[ref])
                            for side,role in [('parent','dividends_parent'),('nci','dividends_nci')]},
                        sbc=dict(annual_amount=None,allocations=[],source_refs=[ref]),
                        adjusted_earnings=dict(label='SYNTHETIC no company adjustment bridge',adjustments=[],basic_earnings_adjustment=None,dilution=dict(incremental_shares=0,earnings_adjustment=0,method='Synthetic no dilution',source_refs=[ref])),
                        financing=dict(repurchase_price=None,repurchase_elapsed_fraction=.5,issuance_nominal_price=None,historical_closing_shares=[],schedule=[],reason='Zero buybacks need no invented price',source_refs=[ref]),
                        fx_accounting=dict(exposures=[],policy='Synthetic undisclosed foreign balance exposures remain incomplete'),
                        limitations=['Synthetic contracts exercise entry point; not real-company economic validation'])
                    self.assertIn('cash_scope',kwargs['schema']['properties'])
                    self.assertIn('operating_expense_functions',kwargs['schema']['properties'])
                    self.assertIn('cashflow_presentation',kwargs['schema']['properties'])
                    self.assertIn('Paid hybrid coupons, accrued coupons net of tax',kwargs['instructions'])
                    return dict(structural_account_policies=[],cashflow_presentation=None,cash_scope=None,operating_expense_functions=[],functional_expense_structure=[],historical_allocations=[],asset_scope=[dict(reported_role='ppe',owned_role='owned_ppe',rou_role='right_of_use_assets',reported_scope='owned_and_rou',owned_expression='ppe - right_of_use_assets',definition='Synthetic combined PPE includes ROU',source_refs=[ref])],entity_versions=versions,reporting_bridges=[bridge],fx_exposures=exposures,financial_contracts=contracts,gaps=[])
                if with_fx and stage=='integrated_schedules':
                    return dict(findings=[dict(severity='warning',area='synthetic_source_limitation',
                        detail='Synthetic source review warning retained across deterministic FX refreshes.',
                        source_references=[])],summary='Synthetic provider fixture; not a real-company review')
                return dict(findings=[],summary='Synthetic provider fixture; not a real-company review')
            with patch.object(provider,'complete',side_effect=answer) as calls,patch('company_initiation.shared_ai.urlopen') as network,patch('company_initiation.historic_construction.workflow.discover_releases',return_value=(data['source_freshness'],[])):
                with patch('company_initiation.shared_ai.OpenAIProvider.from_env',return_value=provider),patch('company_initiation.__main__.find_project_root',return_value=root), \
                        patch('sys.argv',['company_initiation','construct',data['company'],'--sources',str(archive),'--as-of','2026-10-23','--history-years','2','--forecast-years','2']), \
                        patch('company_initiation.forecast_construction.integrated.recalculate_workbook',return_value={'status':'passed'}), \
                        patch('company_initiation.forecast_construction.model_excel.verify_excel_sensitivities',return_value={'status':'passed'}),patch('builtins.print') as printed:
                    result=main()
                    self.assertEqual(result,0,str(printed.call_args_list[-3:]))
                inputs=next((root/'outputs').glob('construct_research_*/company_model_inputs.json'))
                generated=json.loads(inputs.read_text(encoding='utf-8'))
                self.assertEqual(generated['currency'],'GBP')
                self.assertNotIn('valuation',generated['model_configuration'])
                self.assertFalse((inputs.parent/'valuation_research.json').exists())
                historical=json.loads((inputs.parent/'historical_model.json').read_text(encoding='utf-8'))
                self.assertNotIn('forecast_years',historical)
                self.assertLessEqual(max(period['end'] for period in historical['periods']),historical['latest_reporting_date'])
                self.assertFalse(any(cell.get('status')=='forecast' for row in historical['rows'] for cell in row.get('cells',{}).values()))
                self.assertEqual(generated['fiscal_calendar']['fiscal_year_end'],'06-30')
                self.assertEqual(len(generated['segments']),2)
                self.assertEqual(generated['consolidation_hierarchy']['primary'],'SYNTHETIC operating components')
                self.assertEqual(generated['driver_map'][0]['id'],'synthetic_activity')
                self.assertTrue((inputs.parent/'company_driver_map.json').is_file())
                self.assertEqual(generated['historical']['sales']['values']['2025'],180)
                self.assertEqual(generated['reporting_bridges'][0]['residual'],0)
                self.assertEqual(generated['entity_versions'][0]['scope'],'both_current_businesses')
                self.assertEqual(generated['asset_scope'][0]['reported_scope'],'owned_and_rou')
                self.assertEqual(generated['model_configuration']['financial_contracts']['cost_pools'][0]['variable_share'],.5)
                self.assertIsNone(generated['model_configuration']['financial_contracts']['financing']['repurchase_price'])
                self.assertEqual(generated['model_configuration']['financial_contracts']['dividends']['parent']['payment_weights'],{'Q4':1})
                run=next((root/'outputs').glob('construct_integrated_*'))
                valued_inputs=json.loads((run/'company_model_inputs.json').read_text(encoding='utf-8'))
                self.assertEqual(valued_inputs['model_configuration']['valuation']['research']['schema'],VALUATION_RESEARCH_VERSION)
                self.assertTrue((run/'valuation_research.json').is_file())
                recorded_stages=[call['stage'] for call in json.loads((run/'record.json').read_text(encoding='utf-8'))['calls']]
                self.assertLess(recorded_stages.index('integrated_schedules'),recorded_stages.index('company_valuation_sources'))
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
                spending=reviewed_segments['north_pool_marketing_admin_budget_change']
                self.assertEqual(spending['driver_contract']['parameter_role'],'forecast_assumption')
                self.assertIn('operating_profit',spending['driver_contract']['expected_downstream_outputs'])
                for payload in review_payloads.values():
                    self.assertIn('SYNTHETIC optional input-cost detail remains undisclosed',payload['research_limitations'])
                    self.assertTrue(payload['forecast_horizon'])
                    self.assertTrue(any(r['period_cells'] for r in payload['complete_forecast_graph']))
                self.assertGreater(calls.call_count,5)
                self.assertTrue((run/'model.xlsx').is_file())
                self.assertEqual(json.loads((run/'record.json').read_text(encoding='utf-8'))['status'],'complete_provisional')
                for filename in ('record.json','model_specification.json','validation.json'):
                    self.assertEqual(json.loads((run/filename).read_text(encoding='utf-8'))['financial_completeness'],'provisional')
                from company_initiation.forecast_construction.workflow import offline_export
                before=calls.call_count
                with patch('company_initiation.shared_ai.OpenAIProvider.from_env',side_effect=AssertionError('Offline export must not load an AI provider')), \
                        patch('company_initiation.forecast_construction.construction.recalculate_workbook',return_value={'status':'passed'}), \
                        patch('company_initiation.forecast_construction.model_excel.verify_excel_sensitivities',return_value={'status':'passed'}):
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
                    with patch('company_initiation.shared_ai.OpenAIProvider.from_env',side_effect=AssertionError('Repeated refresh must not load an AI provider')), \
                            patch('company_initiation.forecast_construction.construction.recalculate_workbook',return_value={'status':'passed'}), \
                            patch('company_initiation.forecast_construction.model_excel.verify_excel_sensitivities',return_value={'status':'passed'}):
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
    def test_historical_contradictory_date_exception_never_certifies_current_or_vintage_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);original=root/'original.pdf';original.write_bytes(b'%PDF preserved original')
            source=dict(id='original',local_path=original.name,sha256=hashlib.sha256(original.read_bytes()).hexdigest(),published_at=None)
            release=dict(id='release',source_id='original',published_at=None,coverage_kind='historical_original',reporting_year=2025,
                reporting_period_refs=[dict(page_url='https://synthetic.invalid/results',sha256='original-page-hash',quote='2025 annual original')],
                publication_availability='contradictory',point_in_time_eligible=False,freshness_eligible=False,observed_available_at='2026-10-25',
                publication_claims=[dict(published_at='2026-03-01'),dict(published_at='2026-03-02')])
            data=dict(history_years=[2025],sources={'original':source},observations=[dict(source_refs=[dict(source_id='original')])],
                model_configuration={'as_of':'2026-10-25'},source_freshness=dict(checked_as_of='2026-10-25',official_indexes=['https://synthetic.invalid/results'],releases=[release]))
            checked=freshness_checks(data,root)
            self.assertFalse(any(item['status']=='FAIL' for item in checked))
            self.assertTrue(any(item['status']=='WARNING' and 'contradictory' in item['detail'] for item in checked))
            self.assertFalse(any(item['area']=='freshness' and item['name']=='release:release' for item in checked))
            self.assertTrue(any(item['status']=='FAIL' for item in freshness_checks(data,root,historical_vintage=True)))
            self.assertTrue(any(item['status']=='FAIL' for item in freshness_checks(data,root,as_of='2026-10-24')))
            for change in ({'reporting_year':2026},{'coverage_kind':'dated_release'},{'reporting_period_refs':[]},
                           {'point_in_time_eligible':True},{'freshness_eligible':True},{'observed_available_at':None}):
                with self.subTest(change=change):
                    revised=copy.deepcopy(data);revised['source_freshness']['releases'][0].update(change)
                    self.assertTrue(any(item['status']=='FAIL' for item in freshness_checks(revised,root)))

    def test_disclosure_update_resolves_relocated_archive_and_rejects_changed_live_bytes(self):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.historic_construction.workflow import update_company_inputs
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'local_store'/'synthetic';reports=archive/'financial_reports';reports.mkdir(parents=True)
            original=reports/'original.txt';original.write_text('Synthetic original annual revenue 30.',encoding='utf-8')
            inventory=inventory_local_sources(archive);source=inventory['sources'][0]
            parent=root/'outputs'/'construct_original';frozen=parent/'sources';frozen.mkdir(parents=True)
            frozen_file=frozen/(source['id']+'.txt');frozen_file.write_bytes(original.read_bytes())
            data=dict(company='SYNTHETIC update',currency='GBP',fiscal_calendar={'fiscal_year_end':'12-31'},history_years=[2025],sources={source['id']:source},observations=[],
                model_configuration={'as_of':'2026-10-23'},source_freshness={'official_indexes':['https://synthetic.invalid/results']})
            inputs=parent/'company_model_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
            (parent/'calls.jsonl').write_text('',encoding='utf-8')
            record=dict(directory=str(parent),configuration=dict(company=data['company'],sources=str(archive),
                manifest=inventory['manifest_sha256'],limits=dict(usd=20,calls=None,repairs=2,retries=0,generated_tokens=None)),
                sources=[dict(source,path=str(frozen_file))],calls=[],status='research_complete',
                artifacts={inputs.name:hashlib.sha256(inputs.read_bytes()).hexdigest()})
            (parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
            parent_bytes=(parent/'record.json').read_bytes()
            relocated=root/'data_store'/'company_data'/'synthetic';relocated.parent.mkdir(parents=True)
            archive.rename(relocated);archive=relocated;original=archive/'financial_reports'/'original.txt'
            original.unlink()
            freshness=dict(checked_as_of='2026-10-25',official_indexes=['https://synthetic.invalid/results'],
                releases=[dict(id='original_release',source_id=source['id'],published_at='2026-01-01',requires_observations=False)])
            provider=OpenAIProvider(api_key='SYNTHETIC-NOT-A-CREDENTIAL')
            with patch('company_initiation.historic_construction.workflow.discover_releases',return_value=(freshness,[])) as discovery, \
                 patch.object(provider,'complete',side_effect=AssertionError('No AI in relocation regression')), \
                 patch('company_initiation.historic_construction.workflow.combined_history_review_current',return_value=False), \
                 patch('company_initiation.historic_construction.workflow.ensure_combined_history_review') as review:
                result=update_company_inputs(root,parent,as_of='2026-10-25',provider=provider)
                self.assertEqual(discovery.call_args.args[1],relocated.resolve())
                review.assert_called_once()
                self.assertIn('Synthetic original annual revenue 30.',review.call_args.kwargs['original_units'][0]['text'])
                saved=json.loads((result.parent/'record.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['status'],'research_complete');self.assertEqual(saved['calls'],[])
                self.assertEqual(saved['configuration']['sources'],str(relocated.resolve()))
                self.assertEqual((parent/'record.json').read_bytes(),parent_bytes)
                audit=json.loads((result.parent/'source_freeze_audit.json').read_text(encoding='utf-8'))
                self.assertEqual(audit['reused_missing_originals'][0]['source_id'],source['id'])
                checks=json.loads((result.parent/'freshness_validation.json').read_text(encoding='utf-8'))
                self.assertTrue(all(item['status']=='PASS' for item in checks))
                original.write_text('Changed live original 31.',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'Source changed before freezing'):
                    update_company_inputs(root,parent,as_of='2026-10-25',provider=provider)

    def test_official_discovery_reads_event_and_checks_date_quote_and_url(self):
        from types import SimpleNamespace
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';event=index+'/event';pdf=index+'/release.pdf'
        index_html=b'<p>Results calendar</p><a href="/results/event">2031 nine months</a>'
        event_html=b'<p>22 October 2031</p><a href="/results/release.pdf">Original release</a>'
        release=dict(url=pdf,published_at='2031-10-22',title='SYNTHETIC nine months',publication_evidence='22 October 2031',requires_observations=True)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);saved={};answers=[dict(releases=[],event_pages=[event],gaps=[]),dict(releases=[release],event_pages=[],gaps=[])]
            def stage(*args):
                from company_initiation.shared_ai import _input_messages
                messages=_input_messages(args[2])
                self.assertGreater(len(messages),1)
                if args[0]=='official_release_documents':
                    self.assertTrue(any('22 October 2031' in unit['text'] for unit in args[2]['evidence']))
                return answers.pop(0)
            journal=SimpleNamespace(directory=root,state={'artifacts':{}},stage=stage,artifact=lambda name,data:saved.update({name:data}))
            def fetch(url):return {index:(index_html,index,'text/html'),event:(event_html,event,'text/html'),pdf:(b'%PDF SYNTHETIC fixture',pdf,'application/pdf')}[url]
            with patch('company_initiation.historic_construction.evidence.download',side_effect=fetch) as calls:
                fresh,sources=discover_releases(journal,root,['http://synthetic.invalid/results'],'2031-10-23',latest_completed_year=2030)
            self.assertEqual(calls.call_count,3);self.assertEqual(fresh['releases'][0]['published_at'],'2031-10-22')
            self.assertTrue((root/sources[0]['local_path']).is_file())
            self.assertEqual(fresh['official_indexes'][0]['requested_url'],'http://synthetic.invalid/results')
            answers.extend([dict(releases=[],event_pages=[event],gaps=[]),dict(releases=[dict(release,publication_evidence='invented date quote')],event_pages=[],gaps=[])])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=fetch),self.assertRaisesRegex(ValueError,'quotation'):
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


class SavedScenarioArtifactTests(unittest.TestCase):
    def test_plain_export_then_input_refresh_retains_snapshot_and_typed_scenario_artifacts(self):
        from company_initiation.forecast_construction.workflow import offline_export
        from company_initiation.forecast_construction.periods import assumption_contract, apply_assumption_payload, model_logic_digest
        from company_initiation.forecast_construction.integrated import verified_integrated_record
        from tests.test_periods import financial_spec
        spec=financial_spec();spec.update(company='SYNTHETIC saved scenario',currency='GBP',forecast_years=[2026],
            historical_years=[2025],model_configuration={'as_of':'2026-01-01'},gaps=[],policies={})
        default_spec=copy.deepcopy(spec);contract=assumption_contract(spec)
        field=next(f for f in contract['fields'] if f['driver_id']=='price' and f['period_id']=='2026-Q1')
        item={key:field[key] for key in ('driver_id','period_id','unit','currency','frequency','value_type')};item['value']=.3
        payload=dict(schema='financial_assumptions_v1',company=spec['company'],scenario_id='retained-scenario',
            as_of='2026-01-02',model_digest=contract['model_digest'],inputs=[item])
        apply_assumption_payload(spec,payload)
        snapshot=dict(schema='shared_fx_snapshot_v1',source={'snapshot_id':'synthetic-pinned'},metadata={'daily_end':'2026-01-01'},policy={},findings=[])
        snapshot_bytes=(json.dumps(snapshot,indent=1)+'\n').encode()
        data=dict(company=spec['company'],currency='GBP',sources={},history_years=[2025],
            fiscal_calendar={'fiscal_year_end':'12-31'},model_configuration={'as_of':'2026-01-01'})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);parent=root/'outputs'/'parent';parent.mkdir(parents=True)
            for name,value in [('company_model_inputs.json',data),('model_specification.json',spec),
                               ('forecast.json',calculate_periodic(spec)),('validation.json',{'checks':[]})]:
                (parent/name).write_text(json.dumps(value),encoding='utf-8')
            (parent/'calls.jsonl').write_text('',encoding='utf-8');(parent/'fx_snapshot.json').write_bytes(snapshot_bytes)
            record=dict(directory=str(parent),calls=[],sources=[],configuration=dict(company=spec['company'],sources=str(root),limits={'usd':20}),
                        artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.iterdir()})
            (parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
            revised=copy.deepcopy(data);revised['model_configuration']['scenario_note']='Independent metadata revision'
            inputs=root/'revised_inputs.json';inputs.write_text(json.dumps(revised),encoding='utf-8')
            # This test isolates saved-artifact lineage and actual Python scenario
            # arithmetic. Renderer/desktop checks have their separate test suite.
            def fake_export(path,*args,**kwargs):path.write_bytes(b'synthetic renderer placeholder');return {}
            with patch('company_initiation.shared_ai.OpenAIProvider.from_env',side_effect=AssertionError('No AI during saved export')), \
                 patch('company_initiation.forecast_construction.model_excel.export_integrated',side_effect=fake_export), \
                 patch('company_initiation.forecast_construction.model_excel.validate_workbook_layout',return_value={'status':'passed'}), \
                 patch('company_initiation.forecast_construction.construction.recalculate_workbook',side_effect=AssertionError('No desktop Excel in artifact test')), \
                 patch('company_initiation.forecast_construction.integrated.periodic_sensitivities',return_value=([],[])), \
                 patch('company_initiation.shared_artifacts.integrated_runtime_fingerprint',return_value={'code':[]}), \
                 patch('company_initiation.historic_construction.evidence.source_selection_audit',return_value={}), \
                 patch('company_initiation.forecast_construction.integrated.build_periodic_spec',side_effect=lambda *args:copy.deepcopy(default_spec)) as compile_model:
                exported=offline_export(root,parent,recalculate=False)
                compile_model.assert_not_called()
                refreshed=offline_export(root,exported,inputs_file=inputs,recalculate=False)
                self.assertEqual(compile_model.call_count,1)
                self.assertEqual(compile_model.call_args.args[2],snapshot)
            for directory in (exported,refreshed):
                self.assertEqual((directory/'fx_snapshot.json').read_bytes(),snapshot_bytes)
                saved=json.loads((directory/'model_specification.json').read_text(encoding='utf-8'))
                self.assertEqual(json.loads((directory/'input_contract.json').read_text(encoding='utf-8')),saved['input_contract'])
                self.assertEqual(json.loads((directory/'assumptions.json').read_text(encoding='utf-8')),saved['assumption_payload'])
                self.assertEqual(saved['assumption_overrides'],{'price':{'2026-Q1':.3}})
                self.assertEqual(model_logic_digest(saved),model_logic_digest(default_spec))
                self.assertEqual(json.loads((directory/'forecast.json').read_text(encoding='utf-8'))['sales']['2026-Q1'],130)
                checked=verified_integrated_record(directory,root/'outputs')
                self.assertTrue({'fx_snapshot.json','input_contract.json','assumptions.json'}<=checked['artifacts'].keys())
                self.assertEqual(checked['operation']['ai_calls'],0)
            self.assertEqual((parent/'fx_snapshot.json').read_bytes(),snapshot_bytes)


class DiscoveryObligationReuseTests(unittest.TestCase):
    def test_modern_unscoped_claim_still_blocks_after_continuation(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations, discover_releases
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,previous,write=self.fixture(root)
            metadata=json.loads((Path(previous['directory'])/'source_freshness_partial.json').read_text())
            metadata['coverage_obligations']=[dict(id='unscoped',claims=[dict(detail='Original scope remains unknown',
                fiscal_year=None,period_kind='unknown',evidence=[])])]
            write('source_freshness_partial.json',metadata)
            restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2016],{'fiscal_year_end':'12-31'})
            self.assertEqual(len(restored['obligations']),1);self.assertFalse(restored['obligations'][0]['period_scope_verified'])
            harness=OfficialDiscoveryNavigationTests();journal=harness.journal(root,[harness.answer()]);url='https://synthetic.invalid/current'
            with patch('company_initiation.historic_construction.evidence.download',return_value=(b'<p>Current index</p>',url,'text/html')),self.assertRaisesRegex(ValueError,'Original scope remains unknown'):
                discover_releases(journal,archive,[url],'2026-10-25',historical_years=[2016],latest_completed_year=2025,
                    fiscal_calendar={'fiscal_year_end':'12-31'},restored_coverage=restored)

    def test_modern_unverified_claims_survive_continuation_without_becoming_verified(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        for quote in ('','FY Results','Invented quotation'):
            with self.subTest(quote=quote),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive,previous,write=self.fixture(root)
                html=b'<p>FY Results</p>';sha=hashlib.sha256(html).hexdigest()
                write('official_index_'+sha[:16]+'.html',html)
                metadata=json.loads((Path(previous['directory'])/'source_freshness_partial.json').read_text())
                metadata['retrieval_attempts'][0]['sha256']=sha
                url=metadata['retrieval_attempts'][0]['final_url'];pid='page_'+hashlib.sha256(url.encode()).hexdigest()[:16]
                claim=dict(detail='Original annual PDF catalogue was empty',fiscal_year=2016,period_kind='FY',period_end='2016-12-31',
                    expected_publication_date=None,period_scope_verified=False,evidence=[dict(page_id=pid,quotation=quote)] if quote else [])
                metadata['coverage_obligations']=[dict(id='retained',claims=[claim])];write('source_freshness_partial.json',metadata)
                if quote=='Invented quotation':
                    with self.assertRaisesRegex(ValueError,'exact hash-verified'):
                        restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2016],{'fiscal_year_end':'12-31'})
                else:
                    restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2016],{'fiscal_year_end':'12-31'})
                    self.assertEqual(len(restored['obligations']),1)
                    self.assertFalse(restored['obligations'][0]['period_scope_verified'])
                    self.assertEqual(restored['audit'][0]['status'],'retained_unverified_scope')
                    self.assertEqual(restored['obligations'][0]['restored_from']['answer']['artifact'],'source_freshness_partial.json')

    def fixture(self,root):
        archive=root/'archive';archive.mkdir();directory=root/'outputs'/'parent';directory.mkdir(parents=True)
        url='https://synthetic.invalid/history';html=b'<html><p>2016 Q1 and nine-month sales. 2017 Q1 and nine-month sales. 2018 Q1 and nine-month sales. 2019 Q1 and nine-month sales.</p></html>'
        sha=hashlib.sha256(html).hexdigest();pid='page_'+hashlib.sha256(url.encode()).hexdigest()[:16]
        record=dict(directory=str(directory),_reuse_verified=True,configuration=dict(company='Synthetic',sources=str(archive)),artifacts={})
        def write(name,value):
            payload=value if isinstance(value,bytes) else json.dumps(value).encode()
            (directory/name).write_bytes(payload);record['artifacts'][name]=hashlib.sha256(payload).hexdigest()
        write('official_index_'+sha[:16]+'.html',html)
        write('source_freshness_partial.json',dict(checked_as_of='2026-10-25',requested_historical_years=list(range(2016,2026)),
            retrieval_attempts=[dict(kind='index',status='downloaded',final_url=url,sha256=sha)]))
        gaps=[dict(detail='Separate '+str(year)+' '+kind+' release missing',fiscal_year=year,period_kind=kind,
            period_end=str(year)+('-03-31' if kind=='Q1' else '-09-30'),expected_publication_date=None,
            evidence=[dict(page_id=pid,quotation=str(year)+' Q1 and nine-month sales.')]) for year in range(2016,2020) for kind in ('Q1','9M')]
        write('official_release_documents_first_attempt_0.json',dict(releases=[],gaps=gaps))
        write('official_release_documents_later_attempt_0.json',dict(releases=[],gaps=[]))
        return archive,record,write

    def test_legacy_eight_period_gaps_restore_with_exact_artifact_and_html_provenance(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations, discover_releases, _validate_discovery_coverage
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,previous,write=self.fixture(root)
            restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',list(range(2016,2026)),{'fiscal_year_end':'12-31'})
            self.assertEqual(len(restored['obligations']),8)
            self.assertEqual({(item['fiscal_year'],item['period_kind']) for item in restored['obligations']},
                {(year,kind) for year in range(2016,2020) for kind in ('Q1','9M')})
            first=restored['obligations'][0]
            self.assertEqual(first['restored_from']['answer']['artifact'],'official_release_documents_first_attempt_0.json')
            self.assertEqual(first['restored_from']['originals'][0]['sha256'],first['evidence'][0]['sha256'])
            harness=OfficialDiscoveryNavigationTests();index='https://synthetic.invalid/current';journal=harness.journal(root,[harness.answer()])
            with patch('company_initiation.historic_construction.evidence.download',return_value=(b'<p>Current financial navigation</p>',index,'text/html')):
                result,_=discover_releases(journal,archive,[index],'2026-10-25',historical_years=list(range(2016,2026)),
                    latest_completed_year=2025,fiscal_calendar={'fiscal_year_end':'12-31'},restored_coverage=restored)
            self.assertEqual(len(journal.contexts[0]['retained_coverage_obligations']),8)
            self.assertEqual(len(result['coverage_obligations']),8)
            with self.assertRaisesRegex(ValueError,'never reached primary coverage adjudication'):_validate_discovery_coverage(result,[])

    def test_restoration_checks_hashes_exact_quotation_scope_and_calendar(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        for failure in ('hash','quotation','calendar'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive,previous,write=self.fixture(root)
                name='official_release_documents_first_attempt_0.json';path=Path(previous['directory'])/name
                if failure=='hash':path.write_text('{}',encoding='utf-8')
                if failure=='quotation':
                    answer=json.loads(path.read_text());answer['gaps'][0]['evidence'][0]['quotation']='Invented original quotation';write(name,answer)
                with self.assertRaisesRegex(ValueError,'hash changed|exact hash-verified|fiscal boundary'):
                    restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2016,2017,2018,2019],
                        {'fiscal_year_end':'06-30' if failure=='calendar' else '12-31'})

    def test_current_requested_scope_filters_old_claims_without_deleting_their_audit(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,previous,write=self.fixture(root)
            restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2019,2020],{'fiscal_year_end':'12-31'})
            self.assertEqual(len(restored['obligations']),2)
            self.assertEqual(len(restored['audit']),6)
            self.assertTrue(all(item['status']=='outside_requested_periods' for item in restored['audit']))
            different=root/'different_archive';different.mkdir()
            self.assertEqual(restore_discovery_obligations(previous,[previous],different,'2026-10-25',[2019],{'fiscal_year_end':'12-31'})['obligations'],[])
            previous['_reuse_verified']=False
            with self.assertRaisesRegex(ValueError,'verified selected parent'):
                restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2019],{'fiscal_year_end':'12-31'})

    def test_saved_dispositions_do_not_waive_current_primary_review(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,previous,write=self.fixture(root)
            restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2019],{'fiscal_year_end':'12-31'})
            metadata=json.loads((Path(previous['directory'])/'source_freshness_partial.json').read_text())
            metadata.update(coverage_obligations=[dict(id='prior_gap',claims=restored['obligations'])],
                coverage_dispositions=[dict(outcome='supported_primary',reason='Prior dated review')])
            write('source_freshness.json',metadata)
            repeated=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2019],{'fiscal_year_end':'12-31'})
            self.assertEqual(len(repeated['obligations']),2)
            self.assertTrue(all(item['status']=='pending_primary_coverage' for item in repeated['obligations']))

    def test_earlier_requested_cutoff_defers_later_announced_current_period_publication(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,previous,write=self.fixture(root)
            name='official_release_documents_first_attempt_0.json'
            answer=json.loads((Path(previous['directory'])/name).read_text())
            quote='2026 third quarter sales publication scheduled 23 October 2026'
            html=('<p>'+quote+'</p>').encode();sha=hashlib.sha256(html).hexdigest()
            write('official_index_'+sha[:16]+'.html',html)
            metadata=json.loads((Path(previous['directory'])/'source_freshness_partial.json').read_text())
            metadata['retrieval_attempts'][0]['sha256']=sha;write('source_freshness_partial.json',metadata)
            answer['gaps']=[dict(answer['gaps'][0],fiscal_year=2026,period_kind='Q3',period_end='2026-09-30',
                expected_publication_date='2026-10-23',evidence=[dict(answer['gaps'][0]['evidence'][0],quotation=quote)])]
            write(name,answer)
            restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-20',list(range(2016,2026)),{'fiscal_year_end':'12-31'})
            self.assertEqual(restored['obligations'],[])
            self.assertEqual(restored['audit'][0]['status'],'future_at_requested_or_recorded_cutoff')

    def test_legacy_generic_fy_quote_is_audited_without_inventing_its_year(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,previous,write=self.fixture(root)
            html=b'<p>FY Results</p>';sha=hashlib.sha256(html).hexdigest()
            write('official_index_'+sha[:16]+'.html',html)
            metadata=json.loads((Path(previous['directory'])/'source_freshness_partial.json').read_text())
            metadata['retrieval_attempts'][0]['sha256']=sha;write('source_freshness_partial.json',metadata)
            name='official_release_documents_first_attempt_0.json';answer=json.loads((Path(previous['directory'])/name).read_text())
            answer['gaps']=[dict(answer['gaps'][0],period_kind='FY',period_end='2016-12-31',
                evidence=[dict(answer['gaps'][0]['evidence'][0],quotation='FY Results')])]
            write(name,answer)
            restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2016],{'fiscal_year_end':'12-31'})
            self.assertEqual(restored['obligations'],[])
            self.assertEqual(restored['audit'][0]['status'],'unsupported_legacy_assertion')
            self.assertEqual(restored['audit'][0]['claimed_fiscal_year'],2016)
            self.assertEqual(restored['audit'][0]['evidence'][0]['quotation'],'FY Results')

    def test_unverified_future_publication_cannot_erase_a_cited_completed_period(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,previous,write=self.fixture(root)
            quote='2026 third quarter sales';html=('<p>'+quote+'</p>').encode();sha=hashlib.sha256(html).hexdigest()
            write('official_index_'+sha[:16]+'.html',html)
            metadata=json.loads((Path(previous['directory'])/'source_freshness_partial.json').read_text())
            metadata['retrieval_attempts'][0]['sha256']=sha;write('source_freshness_partial.json',metadata)
            name='official_release_documents_first_attempt_0.json';answer=json.loads((Path(previous['directory'])/name).read_text())
            answer['gaps']=[dict(answer['gaps'][0],fiscal_year=2026,period_kind='Q3',period_end='2026-09-30',
                expected_publication_date='2026-10-28',evidence=[dict(answer['gaps'][0]['evidence'][0],quotation=quote)])]
            write(name,answer)
            restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',list(range(2016,2026)),{'fiscal_year_end':'12-31'})
            self.assertEqual(len(restored['obligations']),1)
            self.assertEqual(restored['obligations'][0]['period_kind'],'Q3')
            self.assertEqual(restored['audit'][0]['status'],'unsupported_expected_publication_claim')

    def test_missing_legacy_year_list_cannot_waive_current_required_annual_history(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive,previous,write=self.fixture(root)
            metadata=json.loads((Path(previous['directory'])/'source_freshness_partial.json').read_text())
            metadata.pop('requested_historical_years');write('source_freshness_partial.json',metadata)
            name='official_release_documents_first_attempt_0.json';answer=json.loads((Path(previous['directory'])/name).read_text())
            answer['gaps']=[dict(answer['gaps'][0],period_kind='FY',period_end='2016-12-31',expected_publication_date='2027-03-01')]
            write(name,answer)
            restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',[2016],{'fiscal_year_end':'12-31'})
            self.assertEqual(len(restored['obligations']),1)
            self.assertEqual(restored['obligations'][0]['period_kind'],'FY')

    def test_legacy_missing_date_id_uses_only_unique_quoted_event_not_wrong_supplied_id(self):
        from company_initiation.historic_construction.workflow import restore_discovery_obligations
        for identifier in (None,'date_wrong'):
            with self.subTest(identifier=identifier),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);archive,previous,write=self.fixture(root)
                quote='The company will publish its Q326 sales on October 28 at 7:30 AM CET.'
                html=('<article><h2>Q3 2026 sales</h2><p>'+quote+'</p><time datetime="2026-10-28T06:30:00Z">Event</time></article>').encode()
                sha=hashlib.sha256(html).hexdigest();write('official_index_'+sha[:16]+'.html',html)
                metadata=json.loads((Path(previous['directory'])/'source_freshness_partial.json').read_text())
                metadata['retrieval_attempts'][0]['sha256']=sha;write('source_freshness_partial.json',metadata)
                name='official_release_documents_first_attempt_0.json';answer=json.loads((Path(previous['directory'])/name).read_text())
                ref=answer['gaps'][0]['evidence'][0]
                gap=dict(answer['gaps'][0],fiscal_year=2026,period_kind='Q3',period_end='2026-09-30',expected_publication_date='2026-10-28',
                    evidence=[dict(ref,quotation=quote),dict(ref,quotation='Q3 2026 sales')])
                if identifier:gap['expected_publication_date_id']=identifier
                answer['gaps']=[gap];write(name,answer)
                restored=restore_discovery_obligations(previous,[previous],archive,'2026-10-25',list(range(2016,2026)),{'fiscal_year_end':'12-31'})
                if identifier:
                    self.assertEqual(len(restored['obligations']),1)
                    self.assertEqual(restored['audit'][0]['status'],'unsupported_expected_publication_claim')
                else:
                    self.assertEqual(restored['obligations'],[])
                    proof=restored['audit'][0]['expected_publication_date_refs'][0]
                    self.assertEqual(proof['sha256'],sha);self.assertEqual(proof['date'],'2026-10-28')
                    self.assertEqual(proof['raw_value'],'2026-10-28T06:30:00Z')


class CompanyYearSourceSelectionTests(unittest.TestCase):
    def test_exact_ids_are_constrained_and_bounded_repair_preserves_distinct_sources(self):
        from types import SimpleNamespace
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.workflow import _company_year_sources
        sha='d23fac0a1216fa7197aa78b1'+'a'*40
        catalog={key:dict(id=key,title='Synthetic FY original',sha256=sha,local_path='reports/original.pdf')
            for key in ('local_current','official_d23fac0a1216fa7197aa78b1')}
        bad=dict(source_ids=['local_d23fac0a1216fa7197aa78b1'],reasons=[],gaps=[])
        good=dict(source_ids=['local_current','official_d23fac0a1216fa7197aa78b1','local_current'],reasons=[],gaps=[])
        for answers,success in (([bad,good],True),([bad,bad],False)):
            with self.subTest(success=success):
                raw=copy.deepcopy(answers);calls=[];artifacts={}
                journal=SimpleNamespace(configuration={'limits':{'repairs':2}},state={},save=lambda:None)
                journal.artifact=lambda name,value:artifacts.update({name:copy.deepcopy(value)})
                def ask(stage,prompt,payload,schema,attempt):
                    calls.append(copy.deepcopy(payload))
                    self.assertEqual(set(schema['properties']['source_ids']['items']['enum']),set(catalog))
                    return copy.deepcopy(answers[len(calls)-1])
                journal.ask=ask
                journal.stage=lambda *args:RunJournal.stage(journal,*args)
                if success:
                    selected=_company_year_sources(journal,'Synthetic company',2025,'2026-10-25',catalog)
                    self.assertEqual(selected['source_ids'],list(catalog))
                else:
                    with self.assertRaisesRegex(ValueError,'no progress'):_company_year_sources(journal,'Synthetic company',2025,'2026-10-25',catalog)
                self.assertEqual(len(calls),2);self.assertEqual(answers,raw)
                self.assertIn('official_d23fac0a1216fa7197aa78b1',calls[1]['validation_errors'][0])
                self.assertIn('not interchangeable',calls[1]['validation_errors'][0])
                self.assertTrue(any(value['source_ids']==bad['source_ids'] for value in artifacts.values()))


class OfficialDiscoveryNavigationTests(unittest.TestCase):
    """Synthetic official pages test the real navigation and evidence boundaries."""
    def test_selected_original_labels_correct_retained_scope_without_resolving_financial_coverage(self):
        from company_initiation.historic_construction.workflow import discover_releases, _validate_discovery_coverage
        for labels,quote in (({'FY':'2016 Registration Document'},'FY Results'),
                             ({'FY':'Document de référence 2016','H1':'Rapport financier semestriel 2016'},'')):
            with self.subTest(labels=labels),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);index='https://synthetic.invalid/results';detail='https://synthetic.invalid/archive'
                html=('<p>1 March 2017</p>'+''.join('<a href="/'+kind+'.pdf">'+label+'</a>' for kind,label in labels.items())).encode()
                pages={index:(('<p>'+quote+'</p><a href="/archive">Archive</a>').encode(),index,'text/html'),detail:(html,detail,'text/html')}
                for kind in labels:pages['https://synthetic.invalid/'+kind+'.pdf']=(('%PDF synthetic '+kind).encode(),'https://synthetic.invalid/'+kind+'.pdf','application/pdf')
                def first(context,schema):
                    return self.answer(pages=[detail],gaps=[dict(detail='Original '+kind+' not selected; PDF catalogue is empty',
                        fiscal_year=2016,period_kind=kind,period_end='2016-'+('12-31' if kind=='FY' else '06-30'),expected_publication_date=None,
                        evidence=[dict(page_id=context['inspected_pages'][0]['page_id'],quotation=quote)] if quote else []) for kind in labels])
                second=self.answer(releases=[self.release('https://synthetic.invalid/'+kind+'.pdf',2017) for kind in labels])
                journal=self.journal(root,[first,second])
                with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]):
                    result,_=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2016],fiscal_calendar={'fiscal_year_end':'12-31'})
                self.assertEqual(journal.errors,[])
                self.assertEqual(len(result['coverage_obligations']),len(labels))
                for obligation in result['coverage_obligations']:
                    self.assertEqual(obligation['status'],'pending_primary_coverage')
                    self.assertEqual(len(obligation['claims']),2)
                    self.assertFalse(obligation['claims'][0]['period_scope_verified'])
                    correction=obligation['claims'][1]
                    self.assertTrue(correction['period_scope_verified'])
                    self.assertEqual(correction['evidence'][0]['quotation'],labels[obligation['period_kind']])
                    self.assertEqual(correction['evidence'][0]['sha256'],hashlib.sha256(html).hexdigest())
                    self.assertIn('no financial coverage adjudication',correction['scope_correction']['method'])
                with self.assertRaisesRegex(ValueError,'never reached primary coverage adjudication'):_validate_discovery_coverage(result,[])

    def test_current_cited_scope_correction_participates_in_bounded_validation_immediately(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';detail='https://synthetic.invalid/archive'
        pages={index:(b'<a href="/archive">Archive</a>',index,'text/html'),detail:(b'<p>2016 H1 financial results</p>',detail,'text/html')}
        gap=dict(detail='Half-year original not yet identified',fiscal_year=2016,period_kind='H1',period_end='2016-06-30',expected_publication_date=None,evidence=[])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def corrected(context,schema):
                return self.answer(gaps=[dict(gap,evidence=[dict(page_id=context['inspected_pages'][-1]['page_id'],quotation='2016 H1 financial results')])])
            journal=self.journal(root,[self.answer(pages=[detail],gaps=[gap]),[self.answer(),corrected]])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]):
                result,_=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2016],fiscal_calendar={'fiscal_year_end':'12-31'})
            self.assertEqual(len(journal.errors),1)
            self.assertIn('Retained scope 2016 H1',journal.errors[0]);self.assertIn('restate this same fiscal_year/period_kind',journal.errors[0])
            claims=result['coverage_obligations'][0]['claims']
            self.assertFalse(claims[0]['period_scope_verified']);self.assertTrue(claims[1]['period_scope_verified'])

    def test_wrong_year_or_kind_selected_original_cannot_correct_retained_scope(self):
        from company_initiation.historic_construction.workflow import discover_releases
        for kind,label in (('FY','2015 Registration Document - 1 March 2016'),('H1','Annual results 2016'),
                           ('H1','Second half-year financial report 2016'),('9M','Q3 2016 sales')):
            with self.subTest(kind=kind,label=label),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);index='https://synthetic.invalid/results';detail='https://synthetic.invalid/archive';pdf='https://synthetic.invalid/original.pdf'
                pages={index:(b'<a href="/archive">Archive</a>',index,'text/html'),
                    detail:(('<p>1 March 2017</p><a href="/original.pdf">'+label+'</a>').encode(),detail,'text/html')}
                gap=dict(detail='Unverified period scope',fiscal_year=2016,period_kind=kind,period_end='2016-'+{'FY':'12-31','H1':'06-30','9M':'09-30'}[kind],expected_publication_date=None,evidence=[])
                journal=self.journal(root,[self.answer(pages=[detail],gaps=[gap]),self.answer(releases=[self.release(pdf,2017)])])
                with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]),self.assertRaisesRegex(ValueError,'Retained scope 2016 '+kind):
                    discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2016],fiscal_calendar={'fiscal_year_end':'12-31'})

    def test_cited_wrong_period_correction_cannot_change_a_cumulative_obligation(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';detail='https://synthetic.invalid/archive'
        pages={index:(b'<a href="/archive">Archive</a>',index,'text/html'),detail:(b'<p>2016 Q3 sales</p>',detail,'text/html')}
        gap=dict(detail='Nine-month source missing',fiscal_year=2016,period_kind='9M',period_end='2016-09-30',expected_publication_date=None,evidence=[])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def wrong(context,schema):
                return self.answer(gaps=[dict(gap,evidence=[dict(page_id=context['inspected_pages'][-1]['page_id'],quotation='2016 Q3 sales')])])
            journal=self.journal(root,[self.answer(pages=[detail],gaps=[gap]),wrong])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]),self.assertRaisesRegex(ValueError,'different fiscal scope'):
                discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2016],fiscal_calendar={'fiscal_year_end':'12-31'})

    def test_prior_period_gaps_survive_empty_later_answer_and_require_primary_adjudication(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';detail='https://synthetic.invalid/archive';pdf='https://synthetic.invalid/annual.pdf'
        pages={index:(b'<p>2025 nine-month sales</p><p>1 March 2026</p><a href="/annual.pdf">Annual original</a><a href="/archive">Archive</a>',index,'text/html'),
            detail:(b'<p>Previously published annual originals and archive information</p>',detail,'text/html'),
            pdf:(b'%PDF synthetic unchanged primary',pdf,'application/pdf')}
        for terminal,failed in ((False,False),(True,False),(False,True)):
            with self.subTest(terminal=terminal,failed=failed),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                def first(context,schema):
                    return self.answer(releases=[self.release(pdf,2026)],pages=[] if terminal else [detail],gaps=[dict(
                        detail='Separate 2025 nine-month sales release not found',fiscal_year=2025,period_kind='9M',period_end='2025-09-30',
                        expected_publication_date=None,expected_publication_date_id=None,
                        evidence=[dict(page_id=context['inspected_pages'][0]['page_id'],quotation='2025 nine-month sales')])])
                def last(context,schema):
                    self.assertEqual(len(context['retained_coverage_obligations']),1)
                    return self.answer()
                journal=self.journal(root,[first] if terminal else [first,last])
                def download(url):
                    if failed and url==detail:raise OSError('Synthetic access failure')
                    return pages[url]
                with patch('company_initiation.historic_construction.evidence.download',side_effect=download):
                    if failed:
                        with self.assertRaisesRegex(OSError,'Synthetic access failure'):
                            discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025],fiscal_calendar={'fiscal_year_end':'12-31'})
                        result=journal.saved['source_freshness_partial.json']
                    else:
                        result,_=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025],fiscal_calendar={'fiscal_year_end':'12-31'})
                obligation=result['coverage_obligations'][0]
                self.assertEqual(obligation['fiscal_year'],2025);self.assertEqual(obligation['period_kind'],'9M')
                self.assertEqual(obligation['status'],'pending_primary_coverage')
                self.assertEqual(obligation['first_navigation_round'],1)
                self.assertEqual(obligation['claims'][0]['evidence'][0]['page_url'],index)
                self.assertEqual(obligation['claims'][0]['evidence'][0]['sha256'],hashlib.sha256(pages[index][0]).hexdigest())
                self.assertNotIn('coverage_dispositions',result)

    def test_unscoped_prior_gap_cannot_be_cleared_by_empty_later_answer(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';detail='https://synthetic.invalid/archive'
        pages={index:(b'<a href="/archive">Archive</a>',index,'text/html'),detail:(b'<p>Archive details</p>',detail,'text/html')}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(pages=[detail],gaps=['Unscoped original coverage missing']),self.answer()])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]),self.assertRaisesRegex(ValueError,'Unscoped original coverage missing'):
                discover_releases(journal,root,[index],'2026-10-25')
            self.assertEqual(len(journal.saved['source_freshness_partial.json']['coverage_obligations']),1)

    def journal(self, root, answers):
        from types import SimpleNamespace
        journal=SimpleNamespace(directory=root,state={'artifacts':{}},saved={},contexts=[],schemas=[],errors=[])
        def artifact(name,data):journal.saved[name]=copy.deepcopy(data)
        def stage(name,prompt,context,schema,validator):
            self.assertTrue(callable(validator))
            journal.contexts.append(copy.deepcopy(context))
            journal.schemas.append(copy.deepcopy(schema))
            choices=answers.pop(0)
            if not isinstance(choices,list):choices=[choices]
            for answer in choices:
                try:return validator(answer(context,schema) if callable(answer) else answer)
                except ValueError as exc:
                    journal.errors.append(str(exc))
                    if answer is choices[-1]:raise
            self.fail('No discovery answer supplied')
        journal.artifact=artifact;journal.stage=stage
        return journal

    @staticmethod
    def answer(*,releases=(),pages=(),gaps=()):
        return dict(releases=list(releases),event_pages=list(pages),gaps=list(gaps))

    @staticmethod
    def release(url,year):
        return dict(url=url,published_at=str(year)+'-03-01',title='Synthetic annual '+str(year-1),
                    publication_evidence='1 March '+str(year),requires_observations=True,
                    coverage_kind='dated_release',reporting_year=year-1,reporting_period_evidence='')

    def test_competing_website_dates_resolve_from_preserved_original_without_losing_claims(self):
        from io import BytesIO
        from pypdf import PdfWriter
        from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject
        from company_initiation.historic_construction.workflow import discover_releases
        writer=PdfWriter();page=writer.add_blank_page(600,800)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 60 740 Td (Issued 27 July 2017 - Half-year results 2017) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream);buffer=BytesIO();writer.write(buffer);original=buffer.getvalue()
        index='https://synthetic.invalid/results';detail='https://synthetic.invalid/detail';pdf='https://synthetic.invalid/report.pdf'
        pages={index:(b'<a href="/report.pdf">Half-year results 2017 - 9 July 2017</a><a href="/detail">Detail</a>',index,'text/html'),
            detail:(b'<h1>Press release 27 July 2017</h1><a href="/report.pdf">Half-year results 2017 - 9 July 2017</a>',detail,'text/html'),
            pdf:(original,pdf,'application/pdf')}
        first=dict(self.release(pdf,2017),published_at='2017-07-09',publication_evidence='9 July 2017',reporting_year=2017,reporting_period_evidence='Half-year results 2017')
        second=dict(first,published_at='2017-07-27',publication_evidence='27 July 2017')
        for resolved,current in ((True,False),(False,False),(False,True)):
            with self.subTest(resolved=resolved,current=current),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                def resolve(context,schema):
                    self.assertEqual({claim['published_at'] for claim in context['competing_claims']},{'2017-07-09','2017-07-27'})
                    self.assertIn('Issued 27 July 2017',context['evidence'][0]['text'])
                    path=root/'financial_reports'/('official_'+hashlib.sha256(original).hexdigest()[:24]+'.pdf')
                    self.assertEqual(path.read_bytes(),original,'Original must be durable before the paid resolution stage')
                    return dict(published_at='2017-07-27' if resolved else None,unit_id='page:1' if resolved else None,
                        quotation='Issued 27 July 2017' if resolved else '',reason='Explicit original issuer dateline' if resolved else 'No unambiguous publication dateline established')
                journal=self.journal(root,[self.answer(releases=[first],pages=[detail]),self.answer(releases=[second]),resolve])
                with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]) as downloads:
                    if current:
                        with self.assertRaisesRegex(ValueError,'current or uncited historical'):
                            discover_releases(journal,root,[index],'2017-10-25',latest_completed_year=2016,historical_years=[2016])
                        self.assertNotIn('source_freshness.json',journal.saved);continue
                    fresh,sources=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2017])
                self.assertEqual(downloads.call_count,3);self.assertEqual(len(sources),1)
                source=sources[0];self.assertEqual(len(source['publication_claims']),2)
                self.assertEqual(source['published_at'],'2017-07-27' if resolved else None)
                self.assertEqual(source['publication_availability'],'verified_original_dateline' if resolved else 'contradictory')
                self.assertEqual(source['point_in_time_eligible'],resolved);self.assertEqual(source['freshness_eligible'],resolved)
                if resolved:
                    ref=source['publication_date_refs'][0]
                    self.assertEqual(ref['sha256'],hashlib.sha256(original).hexdigest());self.assertEqual(ref['unit_id'],'page:1')
                else:self.assertTrue(any('contradictory' in text for text in fresh['limitations']))

    def test_conflict_dateline_repair_rejects_wrong_unit_and_conflicting_date_quote(self):
        from company_initiation.historic_construction.workflow import discover_releases
        from company_initiation.historic_construction.evidence import _units as real_units
        index='https://synthetic.invalid/results';detail='https://synthetic.invalid/detail';pdf='https://synthetic.invalid/report.pdf'
        pages={index:(b'<p>1 March 2026</p><a href="/report.pdf">2025 report</a><a href="/detail">Details</a>',index,'text/html'),
            detail:(b'<p>2 March 2026</p><a href="/report.pdf">2025 report</a>',detail,'text/html'),pdf:(b'%PDF preserved',pdf,'application/pdf')}
        release=self.release(pdf,2026)
        good=dict(published_at='2026-03-02',unit_id='page:1',quotation='Published 2 March 2026',reason='Publication dateline')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(releases=[release],pages=[detail]),
                self.answer(releases=[dict(release,published_at='2026-03-02',publication_evidence='2 March 2026')]),
                [dict(good,unit_id='page:9'),dict(good,published_at='2026-03-01'),good]])
            def units(payload,kind):
                return [dict(unit_id='page:1',text='Published 2 March 2026',numbers=[])] if kind=='pdf' else real_units(payload,kind)
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]),patch('company_initiation.historic_construction.evidence._units',side_effect=units):
                fresh,_=discover_releases(journal,root,[index],'2026-10-25')
            self.assertEqual(len(journal.errors),2);self.assertIn('exact selected original unit',journal.errors[0])
            self.assertIn('does not establish',journal.errors[1]);self.assertEqual(fresh['releases'][0]['published_at'],'2026-03-02')

    def test_identical_pdf_aliases_merge_claims_by_hash_and_resolve_once(self):
        from company_initiation.historic_construction.workflow import discover_releases
        from company_initiation.historic_construction.evidence import _units as real_units
        index='https://synthetic.invalid/results';first='https://synthetic.invalid/first.pdf';second='https://synthetic.invalid/second.pdf'
        original=b'%PDF exact same original bytes'
        for resolved,current_alias in ((True,False),(False,False),(False,True)):
            with self.subTest(resolved=resolved,current_alias=current_alias),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);second_year=2026 if current_alias else 2025
                html=('<p>1 March 2026; 2 March 2026</p><a href="/first.pdf">2025 annual original</a><a href="/second.pdf">'+str(second_year)+' annual original</a>').encode()
                one=dict(self.release(first,2026),reporting_period_evidence='2025 annual original')
                two=dict(self.release(second,2026),published_at='2026-03-02',publication_evidence='2 March 2026',
                    reporting_year=second_year,reporting_period_evidence=str(second_year)+' annual original')
                def resolve(context,schema):
                    self.assertEqual(set(context['observed_urls']),{first,second})
                    self.assertEqual({claim['url'] for claim in context['competing_claims']},{first,second})
                    self.assertEqual(len(journal.saved['official_downloaded_originals.json']),2)
                    self.assertEqual(len(list((root/'financial_reports').glob('*.pdf'))),1)
                    return dict(published_at='2026-03-02' if resolved else None,unit_id='page:1' if resolved else None,
                        quotation='Published 2 March 2026' if resolved else '',reason='Original publication dateline' if resolved else 'Original dateline ambiguous')
                journal=self.journal(root,[self.answer(releases=[one,two]),resolve])
                def units(payload,kind):
                    return [dict(unit_id='page:1',text='Published 2 March 2026',numbers=[])] if kind=='pdf' else real_units(payload,kind)
                with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (original,url,'application/pdf')) as fetches,patch('company_initiation.historic_construction.evidence._units',side_effect=units):
                    if current_alias:
                        with self.assertRaisesRegex(ValueError,'current or uncited historical'):
                            discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025])
                        self.assertNotIn('source_freshness.json',journal.saved)
                        continue
                    fresh,sources=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025])
                self.assertEqual(fetches.call_count,3);self.assertEqual(len(journal.contexts),2,'One resolution stage for one byte-identical original')
                self.assertEqual(len(sources),1);self.assertEqual(len(fresh['releases']),2)
                self.assertEqual(set(sources[0]['observed_urls']),{first,second});self.assertEqual(len(sources[0]['publication_claims']),2)
                self.assertTrue(all(item['published_at']==('2026-03-02' if resolved else None) for item in fresh['releases']))
                self.assertTrue(all(item['publication_availability']==('verified_original_dateline' if resolved else 'contradictory') for item in fresh['releases']))
                self.assertEqual((root/sources[0]['local_path']).read_bytes(),original)
                self.assertEqual({item['url'] for item in fresh['releases']},{first,second})

    def test_later_unknown_selection_cannot_erase_recorded_publication_conflict(self):
        from company_initiation.historic_construction.workflow import discover_releases
        from company_initiation.historic_construction.evidence import _units as real_units
        base='https://synthetic.invalid';index=base+'/results';detail=base+'/details';archive=base+'/archive';pdf=base+'/report.pdf'
        pages={index:(b'<p>1 March 2026</p><a href="/report.pdf">2025 annual original</a><a href="/details">Details</a>',index,'text/html'),
            detail:(b'<p>2 March 2026</p><a href="/report.pdf">2025 annual original</a><a href="/archive">Archive</a>',detail,'text/html'),
            archive:(b'<a href="/report.pdf">2025 annual original</a>',archive,'text/html'),pdf:(b'%PDF preserved',pdf,'application/pdf')}
        release=dict(self.release(pdf,2026),reporting_period_evidence='2025 annual original')
        unknown=dict(release,published_at=None,publication_evidence='',coverage_kind='historical_original')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def resolve(context,schema):
                self.assertEqual({claim['published_at'] for claim in context['competing_claims']},{'2026-03-01','2026-03-02'})
                return dict(published_at='2026-03-02',unit_id='page:1',quotation='Published 2 March 2026',reason='Original issuer dateline')
            journal=self.journal(root,[self.answer(releases=[release],pages=[detail]),
                self.answer(releases=[dict(release,published_at='2026-03-02',publication_evidence='2 March 2026')],pages=[archive]),
                self.answer(releases=[unknown]),resolve])
            def units(payload,kind):
                return [dict(unit_id='page:1',text='Published 2 March 2026',numbers=[])] if kind=='pdf' else real_units(payload,kind)
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]),patch('company_initiation.historic_construction.evidence._units',side_effect=units):
                fresh,sources=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025])
            self.assertEqual(len(journal.contexts),4);self.assertEqual(sources[0]['publication_availability'],'verified_original_dateline')
            self.assertEqual(len(sources[0]['publication_claims']),2);self.assertEqual(fresh['releases'][0]['published_at'],'2026-03-02')

    def test_identical_originals_on_opposite_cutoff_sides_resolve_before_emission(self):
        from company_initiation.historic_construction.workflow import discover_releases
        from company_initiation.historic_construction.evidence import _units as real_units
        index='https://synthetic.invalid/results';past='https://synthetic.invalid/past.pdf';future='https://synthetic.invalid/future.pdf'
        html=b'<p>24 October 2026; 28 October 2026</p><a href="/past.pdf">2026 interim</a><a href="/future.pdf">2026 interim</a>'
        before=dict(self.release(past,2026),published_at='2026-10-24',publication_evidence='24 October 2026',reporting_year=2026)
        after=dict(before,url=future,published_at='2026-10-28',publication_evidence='28 October 2026')
        for resolved in ('2026-10-24','2026-10-28'):
            with self.subTest(resolved=resolved),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);quote='Issued '+('24' if resolved.endswith('24') else '28')+' October 2026'
                def resolve(context,schema):
                    self.assertEqual({claim['published_at'] for claim in context['competing_claims']},{'2026-10-24','2026-10-28'})
                    return dict(published_at=resolved,unit_id='page:1',quotation=quote,reason='Original issue dateline')
                journal=self.journal(root,[self.answer(releases=[before,after]),resolve])
                def units(payload,kind):return [dict(unit_id='page:1',text=quote,numbers=[])] if kind=='pdf' else real_units(payload,kind)
                with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF same bytes',url,'application/pdf')) as fetched,patch('company_initiation.historic_construction.evidence._units',side_effect=units):
                    fresh,sources=discover_releases(journal,root,[index],'2026-10-25')
                self.assertEqual(fetched.call_count,3);self.assertEqual(len(journal.contexts),2)
                if resolved.endswith('24'):
                    self.assertEqual(len(sources),1);self.assertEqual(len(fresh['releases']),2)
                    self.assertTrue(all(item['published_at']==resolved for item in fresh['releases']))
                else:
                    self.assertEqual(sources,[]);self.assertEqual(fresh['releases'],[])
                    self.assertEqual(fresh['deferred_releases'][0]['published_at'],resolved)
                    self.assertEqual(set(fresh['deferred_releases'][0]['observed_urls']),{past,future})

    def test_same_url_future_first_then_past_claim_is_not_lost_at_cutoff(self):
        from company_initiation.historic_construction.workflow import discover_releases
        from company_initiation.historic_construction.evidence import _units as real_units
        index='https://synthetic.invalid/results';detail='https://synthetic.invalid/details';pdf='https://synthetic.invalid/report.pdf'
        pages={index:(b'<p>28 October 2026</p><a href="/report.pdf">2026 interim</a><a href="/details">Details</a>',index,'text/html'),
            detail:(b'<p>24 October 2026</p><a href="/report.pdf">2026 interim</a>',detail,'text/html'),pdf:(b'%PDF preserved',pdf,'application/pdf')}
        future=dict(self.release(pdf,2026),published_at='2026-10-28',publication_evidence='28 October 2026',reporting_year=2026)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def resolve(context,schema):
                self.assertEqual({claim['published_at'] for claim in context['competing_claims']},{'2026-10-24','2026-10-28'})
                return dict(published_at='2026-10-28',unit_id='page:1',quotation='Issued 28 October 2026',reason='Original issuer dateline')
            journal=self.journal(root,[self.answer(releases=[future],pages=[detail]),
                self.answer(releases=[dict(future,published_at='2026-10-24',publication_evidence='24 October 2026')]),resolve])
            def units(payload,kind):return [dict(unit_id='page:1',text='Issued 28 October 2026',numbers=[])] if kind=='pdf' else real_units(payload,kind)
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]),patch('company_initiation.historic_construction.evidence._units',side_effect=units):
                fresh,sources=discover_releases(journal,root,[index],'2026-10-25')
            self.assertEqual(journal.contexts[1]['selected_releases'][0]['published_at'],'2026-10-28')
            self.assertEqual(sources,[]);self.assertEqual(fresh['releases'],[]);self.assertEqual(len(journal.contexts),3)

    def test_future_only_originals_and_unavailable_optional_aliases_remain_deferred(self):
        from urllib.error import HTTPError
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';past='https://synthetic.invalid/past.pdf';future='https://synthetic.invalid/future.pdf'
        html=b'<p>1 March 2026; 28 October 2026; 1 November 2026</p><a href="/past.pdf">2025 annual</a><a href="/future.pdf">2026 interim</a>'
        pending=dict(self.release(future,2026),published_at='2026-10-28',publication_evidence='28 October 2026',reporting_year=2026)
        for mode in ('future_only','conflicting_future_only','optional_404','optional_placeholder','optional_future_conflict'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);releases=[pending]
                if mode in ('conflicting_future_only','optional_future_conflict'):releases.append(dict(pending,published_at='2026-11-01',publication_evidence='1 November 2026'))
                if mode.startswith('optional'):releases.insert(0,self.release(past,2026))
                journal=self.journal(root,[self.answer(releases=releases)])
                def fetch(url):
                    if url==index:return html,index,'text/html'
                    if url==past:return b'%PDF available original',past,'application/pdf'
                    if mode=='optional_placeholder':return b'<p>Coming soon</p>',future,'text/html'
                    if mode=='optional_future_conflict':return b'%PDF different future original',future,'application/pdf'
                    raise HTTPError(url,404,'Not published yet',{},None)
                with patch('company_initiation.historic_construction.evidence.download',side_effect=fetch) as downloads:
                    fresh,sources=discover_releases(journal,root,[index],'2026-10-25')
                self.assertEqual(len(journal.contexts),1,'Future-only date conflict must not trigger paid review')
                self.assertEqual(len(sources),1 if mode.startswith('optional') else 0)
                self.assertEqual(downloads.call_count,3 if mode.startswith('optional') else 1)
                self.assertTrue(fresh['deferred_releases']);self.assertTrue(any('deferred beyond' in item for item in fresh['limitations']))
                if mode in ('optional_404','optional_placeholder'):
                    audit=fresh['deferred_releases'][0]['retrieval']
                    self.assertEqual(audit['status'],'deferred_after_cutoff');self.assertTrue(audit['error'])
                    if mode=='optional_placeholder':self.assertEqual(audit['sha256'],hashlib.sha256(b'<p>Coming soon</p>').hexdigest())

    def test_link_ids_resolve_long_original_urls_and_reject_unknown_or_wrong_kind_ids(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';archive='https://synthetic.invalid/financial/archive'
        pdf='https://synthetic.invalid/content/2018/Annual%20Report/2018_document?download=1&language=en'
        pages={index:(b'<a href="/financial/archive">Annual archive</a>',index,'text/html'),
            archive:('<p>1 March 2019</p><a type="application/pdf" href="'+pdf.replace('&','&amp;')+'">2018 Registration Document</a>').encode(),
            pdf:(b'%PDF exact long observed URL',pdf,'application/pdf')}
        pages[archive]=(pages[archive],archive,'text/html')
        def navigation(context,schema):
            self.assertNotIn('event_pages',schema['properties'])
            item=context['navigation_catalogue'][0]
            self.assertEqual(schema['properties']['event_page_ids']['items']['enum'],[item['link_id']])
            return dict(releases=[],event_page_ids=[item['link_id']],gaps=[])
        def original(context,schema):
            item=next(item for item in context['catalog'] if item['url']==pdf)
            properties=schema['properties']['releases']['items']['properties']
            self.assertNotIn('url',properties);self.assertEqual(properties['link_id']['enum'],[item['link_id']])
            release=self.release(pdf,2019);release.pop('url');release['link_id']=item['link_id']
            return dict(releases=[release],event_page_ids=[],gaps=[])
        def wrong_kind(context,schema):
            release=self.release(pdf,2019);release.pop('url')
            release['link_id']=context['navigation_catalogue'][0]['link_id']
            return dict(releases=[release],event_page_ids=['nav_unknown'],gaps=[])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[[wrong_kind,navigation],original])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:pages[url]) as calls:
                fresh,sources=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2018])
            self.assertEqual(calls.call_count,3);self.assertEqual(len(journal.errors),1)
            self.assertIn('Unknown original PDF link_id',journal.errors[0]);self.assertIn('Unknown navigation link_id',journal.errors[0])
            self.assertEqual(fresh['releases'][0]['url'],pdf);self.assertEqual(sources[0]['url'],pdf)
            self.assertEqual((root/sources[0]['local_path']).read_bytes(),pages[pdf][0])

    def test_structured_future_period_gap_uses_company_calendar_and_is_retained(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/annual.pdf'
        for ending,cutoff,finish in [('12-31','2026-10-25','2026-12-31'),('06-30','2026-03-15','2026-06-30')]:
            with self.subTest(ending=ending),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                def answer(context,schema):
                    gap=dict(detail='FY2026 original not yet published',fiscal_year=2026,period_kind='FY',period_end=finish,
                        expected_publication_date=None,evidence=[dict(page_id=context['inspected_pages'][0]['page_id'],quotation='2026 annual results calendar')])
                    return self.answer(releases=[self.release(pdf,2026)],gaps=[gap])
                journal=self.journal(root,[answer]);html=b'<p>1 March 2026. 2026 annual results calendar</p><a href="/annual.pdf">2025 annual original</a>'
                with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF original',pdf,'application/pdf')):
                    fresh,_=discover_releases(journal,root,[index],cutoff,latest_completed_year=2025,historical_years=[2025],fiscal_calendar={'fiscal_year_end':ending})
                self.assertFalse(journal.errors);gap=fresh['deferred_periods'][0]
                self.assertEqual(gap['classification'],'future_financial_period');self.assertEqual(gap['period_end'],finish)
                self.assertFalse(gap['blocking']);self.assertEqual(gap['evidence'][0]['page_url'],index)
                self.assertIn('not evidence of a published original',fresh['limitations'][0])

    def test_exact_inspected_page_id_is_audited_navigation_noop_but_pdf_id_is_not(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/annual.pdf'
        def answer(context,schema):
            release=self.release(pdf,2026);release.pop('url');release['link_id']=context['catalog'][0]['link_id']
            return dict(releases=[release],event_page_ids=[context['inspected_pages'][0]['page_id']],gaps=[])
        def wrong_kind(context,schema):
            result=answer(context,schema);result['event_page_ids']=[context['catalog'][0]['link_id']]
            return result
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[[wrong_kind,answer]])
            html=b'<p>1 March 2026</p><a href="/annual.pdf">Annual original</a>'
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF original',pdf,'application/pdf')) as calls:
                fresh,_=discover_releases(journal,root,[index],'2026-10-25')
            self.assertEqual(len(journal.errors),1);self.assertIn('Unknown navigation link_id',journal.errors[0])
            self.assertEqual(calls.call_count,2);self.assertEqual(fresh['releases'][0]['url'],pdf)
            ignored=journal.saved['official_navigation_audit.json']['ignored_already_visited']
            self.assertTrue(all(item['canonical_url']==index for item in ignored))
            self.assertTrue(any(item.get('requested_page_id')==journal.contexts[0]['inspected_pages'][0]['page_id'] for item in ignored))

    def test_structured_html_dates_preserve_native_timezone_and_reject_conflicting_fields(self):
        from datetime import datetime,timedelta,timezone
        from company_initiation.historic_construction.evidence import official_html_link_metadata
        moment=datetime(2026,3,2,0,30,tzinfo=timezone(timedelta(hours=1)));stamp=int(moment.timestamp()*1000)
        raw='java.util.GregorianCalendar[time='+str(stamp)+',zone=sun.util.calendar.ZoneInfo[id="GMT+01:00"],YEAR=2026,MONTH=2,DAY_OF_MONTH=2,HOUR_OF_DAY=0,MINUTE=30,SECOND=0,ZONE_OFFSET=3600000,DST_OFFSET=0]'
        def document(calendar):
            return ('<article title="FY 2025 results" tagYear="2025" startDate="'+calendar.replace('"','&quot;')+'"><div data-startdate="'+str(stamp)+'"><h3>FY results</h3><date-format startdate="'+str(stamp)+'"></date-format><a href="/report.pdf">Press release</a></div></article>'
                '<article title="Unrelated release"><time datetime="2026-04-01"></time><a href="/other.pdf">Other release</a></article>').encode()
        result=official_html_link_metadata(document(raw),'https://synthetic.invalid/results')
        link=next(item for item in result['link_context'] if item['url'].endswith('/report.pdf'))
        dates={item['date_id']:item for item in result['structured_dates']}
        self.assertEqual({dates[i]['date'] for i in link['structured_date_ids']},{'2026-03-02'})
        self.assertEqual({dates[i]['native_timezone'] for i in link['structured_date_ids']},{'GMT+01:00'})
        native=next(item for item in dates.values() if item['representation']=='java_gregorian_calendar')
        self.assertEqual(native['raw_value'],raw);self.assertEqual(native['native_unit'],'epoch_milliseconds')
        self.assertEqual(native['sha256'],hashlib.sha256(document(raw)).hexdigest())
        bad=official_html_link_metadata(document(raw.replace('DAY_OF_MONTH=2','DAY_OF_MONTH=3')),'https://synthetic.invalid/results')
        self.assertTrue(bad['rejected_date_attributes'])
        self.assertFalse(next(item for item in bad['link_context'] if item['url'].endswith('/report.pdf')).get('structured_date_ids'))

    def test_discovery_cache_context_ignores_retrieval_clock_but_preserves_hash_and_failure(self):
        from datetime import datetime,timezone
        from company_initiation.historic_construction.workflow import discover_releases
        from company_initiation.shared_runtime import digest
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/report.pdf';blocked='https://synthetic.invalid/blocked'
        html=b'<p>1 March 2026</p><a href="/report.pdf">2025 original report</a>'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'archive';archive.mkdir();journals=[]
            for number in range(4):
                output=root/str(number);output.mkdir();journal=self.journal(output,[self.answer(releases=[self.release(pdf,2026)])]);journals.append(journal)
                content=html+(b'<p>Changed original disclosure metadata</p>' if number==2 else b'')
                def fetch(url):
                    if url==blocked:raise OSError('Synthetic access denied')
                    return (content,index,'text/html') if url==index else (b'%PDF original',pdf,'application/pdf')
                with patch('company_initiation.historic_construction.workflow.datetime') as clock,patch('company_initiation.historic_construction.evidence.download',side_effect=fetch):
                    clock.now.return_value=datetime(2026,10,25,number,tzinfo=timezone.utc)
                    if number==3:
                        with self.assertRaisesRegex(ValueError,'access failed'):discover_releases(journal,archive,[index,blocked],'2026-10-25')
                    else:discover_releases(journal,archive,[index],'2026-10-25')
            first,second,changed,failed=journals
            self.assertEqual(first.contexts,second.contexts)
            self.assertEqual(digest(first.contexts[0]),digest(second.contexts[0]))
            self.assertNotEqual(first.saved['official_retrieval.json']['attempts'][0]['attempted_at'],second.saved['official_retrieval.json']['attempts'][0]['attempted_at'])
            self.assertTrue(all('attempted_at' not in item for item in first.contexts[0]['retrieval_attempts']))
            self.assertNotEqual(first.contexts[0]['retrieval_attempts'][0]['sha256'],changed.contexts[0]['retrieval_attempts'][0]['sha256'])
            self.assertNotEqual(digest(first.contexts[0]),digest(changed.contexts[0]))
            self.assertTrue(any(item['status']=='failed' for item in failed.contexts[0]['retrieval_attempts']))
            self.assertNotEqual(digest(first.contexts[0]),digest(failed.contexts[0]))

    def test_large_observed_catalogue_constrains_ids_and_repairs_dates_without_repeating_catalogue(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';anchor='Rapport financier semestriel au 30 juin 2026 31 juillet 2026'
        html=(''.join('<a href="/original_'+str(n)+'.pdf">'+anchor+' document '+str(n)+'</a>' for n in range(160))).encode()
        def result(context,schema,mode):
            entry=context['catalog'][110]
            self.assertEqual(set(schema['properties']['releases']['items']['properties']['link_id']['enum']),{item['link_id'] for item in context['catalog']})
            release=self.release(entry['url'],2026);release.pop('url')
            release.update(link_id=entry['link_id'],published_at='2026-07-31',publication_evidence='31 juillet 2026')
            if mode=='bad_id':release['link_id']=entry['link_id'][:-1]+'?'
            if mode=='both_dates':release['publication_evidence']=anchor
            return dict(releases=[release],event_page_ids=[],gaps=[])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[[
                lambda c,s:result(c,s,'bad_id'),lambda c,s:result(c,s,'both_dates'),lambda c,s:result(c,s,'valid')]])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF original',url,'application/pdf')):
                fresh,_=discover_releases(journal,root,[index],'2026-10-25')
            self.assertEqual(len(journal.errors),2)
            self.assertIn('nearby IDs',journal.errors[0]);self.assertLess(len(journal.errors[0]),2500)
            self.assertNotIn('original_0.pdf',journal.errors[0])
            self.assertIn('publication-date substring',journal.errors[1])
            self.assertEqual(fresh['releases'][0]['publication_evidence'],'31 juillet 2026')
            self.assertEqual(len(journal.contexts[0]['catalog']),160)

    def test_discovery_uses_only_linked_structured_dates_and_same_calendar_event(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/report.pdf'
        html=b'<article title="Q1 2026 results" tagYear="2026"><time datetime="2026-04-22"></time><h3>First quarter results</h3><a href="/report.pdf">Press release</a></article><article title="Q3 2026 sales" startDate="java.util.GregorianCalendar[time=1793169000000,zone=sun.util.calendar.ZoneInfo[id=&quot;GMT&quot;],YEAR=2026,MONTH=9,DAY_OF_MONTH=28,HOUR_OF_DAY=6,MINUTE=30,SECOND=0,ZONE_OFFSET=0,DST_OFFSET=0]"><h3>Q3 2026 sales</h3><p>We will publish Q326 sales on October 28 at 7:30 AM CET.</p></article>'
        def answer(context,schema):
            release_id=context['catalog'][0]['link_id']
            current=next(item for item in context['date_catalogue'] if item['date']=='2026-04-22')
            future=next(item for item in context['date_catalogue'] if item['date']=='2026-10-28')
            release=self.release(pdf,2026);release.pop('url');release.update(link_id=release_id,published_at=None,
                publication_evidence='',publication_date_id=current['date_id'],reporting_year=2026)
            gap=dict(detail='Quarterly sales publication announced after cutoff',fiscal_year=2026,period_kind='Q3',period_end='2026-09-30',
                expected_publication_date='2026-10-28',expected_publication_date_id=future['date_id'],
                evidence=[dict(page_id=context['inspected_pages'][0]['page_id'],quotation='We will publish Q326 sales on October 28 at 7:30 AM CET.')])
            return dict(releases=[release],event_page_ids=[],gaps=[gap])
        def unrelated(context,schema):
            value=answer(context,schema);value['releases'][0].update(published_at='2026-04-22',publication_date_id=value['gaps'][0]['expected_publication_date_id'])
            return value
        def wrong_date(context,schema):
            value=answer(context,schema);value['releases'][0]['published_at']='2026-04-21'
            return value
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[[unrelated,wrong_date,answer]])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF current original',pdf,'application/pdf')) as calls:
                fresh,sources=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025],fiscal_calendar={'fiscal_year_end':'12-31'})
            self.assertEqual(calls.call_count,2);self.assertIn('invalid structured publication date',journal.errors[0])
            self.assertEqual(len(journal.errors),2);self.assertEqual(sources[0]['published_at'],'2026-04-22')
            self.assertEqual(sources[0]['publication_availability'],'verified_structured_html')
            ref=sources[0]['publication_date_refs'][0]
            self.assertEqual(ref['date'],'2026-04-22');self.assertEqual(ref['raw_value'],'2026-04-22')
            self.assertEqual(ref['sha256'],hashlib.sha256(html).hexdigest())
            self.assertEqual(fresh['deferred_periods'][0]['classification'],'announced_future_publication')
            self.assertEqual(fresh['deferred_periods'][0]['expected_publication_date_refs'][0]['native_timezone'],'GMT')

    def test_unknown_historical_period_can_use_exact_linked_card_year_metadata(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/report.pdf'
        html=b'<article title="Quarterly results" tagYear="2025"><h3>Strong quarterly results</h3><a href="/report.pdf">Press release</a></article><article title="Other 2024 results"><h3>Unrelated 2024 statement</h3></article>'
        release=dict(self.release(pdf,2026),published_at=None,publication_evidence='',coverage_kind='historical_original',
            reporting_year=2025,reporting_period_evidence='Strong quarterly results')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[[self.answer(releases=[dict(release,reporting_period_evidence='Unrelated 2024 statement')]),self.answer(releases=[release])]])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF historic original',pdf,'application/pdf')):
                fresh,sources=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025])
            self.assertEqual(len(journal.errors),1);self.assertFalse(sources[0]['point_in_time_eligible'])
            self.assertEqual(sources[0]['reporting_period_refs'][0]['explicit_year_attributes'],{'tagyear':'2025'})

    def test_gap_future_dates_cannot_waive_missing_history_or_completed_current_period(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results'
        cases=[dict(fiscal_year=2025,period_kind='FY',period_end='2025-12-31',expected_publication_date='2027-03-01',quotation='2025 annual results expected 1 March 2027'),
            dict(fiscal_year=2026,period_kind='Q3',period_end='2026-09-30',expected_publication_date=None,quotation='2026 third quarter results'),
            dict(fiscal_year=2026,period_kind='Q3',period_end='2026-12-31',expected_publication_date=None,quotation='2026 third quarter results'),
            dict(fiscal_year=None,period_kind='unknown',period_end='2025-12-31',expected_publication_date='2027-03-01',quotation='2025 annual results expected 1 March 2027'),
            dict(fiscal_year=2026,period_kind='FY',period_end='2026-12-31',expected_publication_date=None,quotation='Unseen2026 annual results')]
        html=b'<p>2025 annual results expected 1 March 2027. 2026 third quarter results. 2026 annual results.</p>'
        for example in cases:
            with self.subTest(example=example),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                def answer(context,schema):
                    gap={k:v for k,v in example.items() if k!='quotation'}
                    gap.update(detail='Required financial original unavailable',evidence=[dict(page_id=context['inspected_pages'][0]['page_id'],quotation=example['quotation'])])
                    return self.answer(gaps=[gap])
                journal=self.journal(root,[answer])
                with patch('company_initiation.historic_construction.evidence.download',return_value=(html,index,'text/html')) as calls:
                    if example in cases[:2]:
                        result,_=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025],fiscal_calendar={'fiscal_year_end':'12-31'})
                        self.assertEqual(result['deferred_periods'],[])
                        self.assertEqual(result['coverage_obligations'][0]['status'],'pending_primary_coverage')
                    else:
                        with self.assertRaises(ValueError):
                            discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025],fiscal_calendar={'fiscal_year_end':'12-31'})
                        self.assertNotIn('source_freshness.json',journal.saved)
                self.assertEqual(calls.call_count,1)

    def test_future_gap_without_calendar_requires_exact_period_end_date_evidence(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results'
        for quote,valid in [('2026 annual results',False),('Fiscal period ends 31 December 2026',True)]:
            with self.subTest(quote=quote),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                def answer(context,schema):
                    return self.answer(gaps=[dict(detail='Annual original not due',fiscal_year=2026,period_kind='FY',period_end='2026-12-31',
                        expected_publication_date=None,evidence=[dict(page_id=context['inspected_pages'][0]['page_id'],quotation=quote)])])
                journal=self.journal(root,[answer]);html=b'<p>2026 annual results. Fiscal period ends 31 December 2026.</p>'
                with patch('company_initiation.historic_construction.evidence.download',return_value=(html,index,'text/html')):
                    if valid:
                        fresh,_=discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025])
                        self.assertEqual(fresh['deferred_periods'][0]['period_boundary_basis'],'Explicit calendar date quoted from inspected official page')
                    else:
                        with self.assertRaisesRegex(ValueError,'discovery incomplete'):
                            discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025])

    def test_unknown_historical_publication_retains_original_without_freshness_or_vintage_claim(self):
        from datetime import date,timedelta
        from company_initiation.historic_construction.workflow import discover_releases, freshness_checks
        index='https://synthetic.invalid/reports';pdf='https://synthetic.invalid/report.pdf';as_of=date.today().isoformat()
        release=dict(url=pdf,published_at=None,title='Synthetic2025 annual report',publication_evidence='',requires_observations=True,
            coverage_kind='historical_original',reporting_year=2025,reporting_period_evidence='2025 Universal Registration Document')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(releases=[release])])
            html=b'<a href="/report.pdf">2025 Universal Registration Document</a>'
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF synthetic',pdf,'application/pdf')):
                fresh,sources=discover_releases(journal,root,[index],as_of,latest_completed_year=2025,historical_years=[2025])
            source=sources[0];saved=fresh['releases'][0]
            self.assertIsNone(source['published_at']);self.assertEqual(source['publication_availability'],'unknown')
            self.assertFalse(source['point_in_time_eligible']);self.assertFalse(source['freshness_eligible'])
            self.assertEqual(source['reporting_period_refs'][0]['quote'],release['reporting_period_evidence'])
            self.assertEqual(source['reporting_period_refs'][0]['page_url'],index)
            self.assertTrue(fresh['limitations']);self.assertTrue((root/source['local_path']).is_file())
            data=dict(history_years=[2025],model_configuration={'as_of':as_of},source_freshness=fresh,
                sources={source['id']:source},observations=[dict(source_refs=[dict(source_id=source['id'])])])
            checks=freshness_checks(data,root)
            self.assertFalse(any(c['status']=='FAIL' for c in checks))
            self.assertTrue(any(c['area']=='source_availability' and c['status']=='WARNING' for c in checks))
            self.assertFalse(any(c['area']=='freshness' and c['name']=='release:'+saved['id'] for c in checks))
            self.assertTrue(any(c['status']=='FAIL' for c in freshness_checks(data,root,historical_vintage=True)))
            earlier=(date.fromisoformat(as_of)-timedelta(days=1)).isoformat()
            self.assertTrue(any(c['status']=='FAIL' for c in freshness_checks(data,root,as_of=earlier)))
            source['publication_date']=(date.fromisoformat(as_of)+timedelta(days=1)).isoformat()
            self.assertTrue(any(c['name']=='future_source:'+source['id'] and c['status']=='FAIL' for c in freshness_checks(data,root)))

    def test_unknown_publication_exception_rejects_current_year_and_unlinked_period_quote(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/reports';pdf='https://synthetic.invalid/report.pdf'
        base=dict(url=pdf,published_at=None,title='Synthetic original',publication_evidence='',requires_observations=True,
            coverage_kind='historical_original',reporting_year=2025,reporting_period_evidence='2025 annual report')
        examples=[(dict(base,reporting_year=2026,reporting_period_evidence='2026 current release'),'requested completed'),
                  (dict(base,reporting_period_evidence='Unrelated2025 period quote'),'exact year-bearing'),
                  (dict(base,coverage_kind='dated_release'),'requested completed')]
        for release,message in examples:
            with self.subTest(message=message),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);journal=self.journal(root,[self.answer(releases=[release])])
                html=b'<a href="/report.pdf">2025 annual report</a><p>Unrelated2025 period quote</p>'
                with patch('company_initiation.historic_construction.evidence.download',return_value=(html,index,'text/html')) as calls,self.assertRaisesRegex(ValueError,message):
                    discover_releases(journal,root,[index],'2026-10-25',latest_completed_year=2025,historical_years=[2025])
                self.assertEqual(calls.call_count,1)

    def test_known_publication_quote_must_match_declared_calendar_date(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/annual.pdf'
        release=dict(self.release(pdf,2026),published_at='2025-03-01')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(releases=[release])])
            html=b'<p>1 March 2026</p><a href="/annual.pdf">Annual original</a>'
            with patch('company_initiation.historic_construction.evidence.download',return_value=(html,index,'text/html')),self.assertRaisesRegex(ValueError,'does not establish declared'):
                discover_releases(journal,root,[index],'2026-10-25')

    def test_four_observed_rounds_retain_annuals_and_current_release_context(self):
        from company_initiation.historic_construction.workflow import discover_releases
        base='https://synthetic.invalid';pages=[base+'/results',base+'/archive',base+'/archive/years',base+'/archive/2020']
        historic=base+'/annual.pdf';current=base+'/interim.pdf'
        downloads={pages[0]:(b'<a href="http://synthetic.invalid/archive#top">Archive</a>',pages[0],'text/html'),
                   pages[1]:(b'<a href="/archive/years">All years</a>',pages[1],'text/html'),
                   pages[2]:(b'<a href="/archive/2020">2020</a>',pages[2],'text/html'),
                   pages[3]:(b'<p>1 March 2021</p><a href="/annual.pdf">Annual 2020</a><p>1 March 2026</p><a href="/interim.pdf">Interim</a>',pages[3],'text/html'),
                   historic:(b'%PDF synthetic annual',historic,'application/pdf'),current:(b'%PDF synthetic interim',current,'application/pdf')}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            # Navigation work is not an unscoped financial-coverage assertion.
            answers=[self.answer(pages=[page]) for page in pages[1:]]
            answers.append(self.answer(releases=[self.release(historic,2021),self.release(current,2026)]))
            journal=self.journal(root,answers)
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:downloads[url]) as calls:
                result,sources=discover_releases(journal,root,['http://synthetic.invalid/results'],'2026-10-25',
                                                 latest_completed_year=2025,historical_years=range(2016,2026))
            self.assertEqual(calls.call_count,6)
            self.assertEqual(result['navigation_rounds'],4)
            self.assertEqual(result['requested_historical_years'],list(range(2016,2026)))
            self.assertEqual(result['status'],'discovered_pending_numeric_validation')
            self.assertEqual(len(sources),2)
            self.assertTrue(all(context['historical_years']==list(range(2016,2026)) for context in journal.contexts))
            self.assertTrue(all(context['latest_completed_year']==2025 for context in journal.contexts))
            self.assertTrue(all(source['url'] in (historic,current) for source in sources))
            self.assertEqual(journal.saved['official_retrieval.json']['attempts'][0]['requested_url'],'http://synthetic.invalid/results')

    def test_invalid_link_and_unrelated_date_quote_are_repaired_inside_stage(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';unrelated=index+'/other';pdf=index+'/annual.pdf'
        release=self.release(pdf,2026)
        downloads={index:(b'<p>1 March 2026</p><a href="/results/annual.pdf">Annual</a>',index,'text/html'),
                   unrelated:(b'<p>1 March 2025</p>',unrelated,'text/html'),pdf:(b'%PDF synthetic',pdf,'application/pdf')}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            journal=self.journal(root,[[self.answer(pages=[index+'/guessed']),
                                       self.answer(releases=[dict(release,published_at='2025-03-01',publication_evidence='1 March 2025')]),
                                       self.answer(releases=[release])]])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:downloads[url]) as calls:
                result,_=discover_releases(journal,root,[index,unrelated],'2026-10-25')
            self.assertEqual(len(journal.errors),2)
            self.assertIn('absent',journal.errors[0]);self.assertIn('page linking',journal.errors[1])
            self.assertEqual(calls.call_count,3)
            self.assertEqual(result['releases'][0]['published_at'],'2026-03-01')

    def test_navigation_url_date_and_quote_failures_are_reported_in_one_repair(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/annual.pdf';bad='https://synthetic.invalid/guessed.pdf'
        release=self.release(pdf,2026)
        downloads={index:(b'<p>1 March 2026</p><a href="/results">Again</a><a href="/annual.pdf">Annual original</a>',index,'text/html'),
                   pdf:(b'%PDF synthetic',pdf,'application/pdf')}
        wrong=self.answer(pages=[index],releases=[dict(release,published_at='March 2026',publication_evidence='Date inferred from filename'),
            dict(release,url=bad,publication_evidence='Unseen date phrase')])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[[wrong,self.answer(releases=[release])]])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:downloads[url]) as calls:
                result,_=discover_releases(journal,root,[index],'2026-10-25')
            self.assertEqual(len(journal.errors),1)
            error=journal.errors[0]
            for phrase in (bad,'invalid published_at','March 2026','Date inferred from filename','Unseen date phrase'):
                self.assertIn(phrase,error)
            self.assertNotIn('already visited',error)
            self.assertEqual(journal.saved['official_navigation_audit.json']['ignored_already_visited'][0]['canonical_url'],index)
            self.assertEqual(calls.call_count,2)
            self.assertEqual(result['releases'][0]['url'],pdf)

    def test_blocked_index_survives_other_access_and_prevents_complete_coverage(self):
        from company_initiation.historic_construction.workflow import discover_releases
        blocked='https://synthetic.invalid/blocked';index='https://synthetic.invalid/results'
        def fetch(url):
            if url==blocked:raise OSError('HTTP 403 original index access denied')
            return b'<p>Official results index</p>',index,'text/html'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer()])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=fetch),self.assertRaisesRegex(ValueError,'access failed'):
                discover_releases(journal,root,[blocked,index],'2026-10-25',historical_years=[2025])
            partial=journal.saved['source_freshness_partial.json']
            self.assertEqual(partial['status'],'incomplete_discovery')
            self.assertEqual(partial['requested_historical_years'],[2025])
            self.assertEqual(partial['retrieval_attempts'][0]['status'],'failed')
            self.assertIn('403',partial['retrieval_attempts'][0]['error'])
            self.assertNotIn('source_freshness.json',journal.saved)

    def test_observed_navigation_progresses_beyond_four_rounds_and_retains_visited_audit(self):
        from company_initiation.historic_construction.workflow import discover_releases
        base='https://synthetic.invalid';pages=[base+'/'+str(i) for i in range(7)];pdf=base+'/annual.pdf'
        def fetch(url):
            if url==pdf:return b'%PDF original',pdf,'application/pdf'
            i=pages.index(url)
            text=('<p>1 March 2026</p><a href="'+pdf+'">2025 annual original</a>') if i==len(pages)-1 else ('<a href="'+pages[i]+'">Again</a><a href="'+pages[i+1]+'">Next</a>')
            return text.encode(),url,'text/html'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            answers=[self.answer(pages=[pages[0]+'#section',pages[1]])]
            answers.extend(self.answer(pages=[page]) for page in pages[2:])
            answers.append(self.answer(releases=[self.release(pdf,2026)]))
            journal=self.journal(root,answers)
            with patch('company_initiation.historic_construction.evidence.download',side_effect=fetch) as calls:
                fresh,_=discover_releases(journal,root,[pages[0]],'2026-10-25')
            self.assertFalse(journal.errors);self.assertEqual(fresh['navigation_rounds'],7)
            self.assertEqual(journal.saved['official_navigation_audit.json']['ignored_already_visited'][0]['canonical_url'],pages[0])
            self.assertEqual(calls.call_count,8)

    def test_new_navigation_url_with_same_original_and_links_stops_without_another_call(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/index';again='https://synthetic.invalid/again'
        html=b'<a href="https://synthetic.invalid/again">Next archive page</a>'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(pages=[again])])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,url,'text/html')) as calls,self.assertRaisesRegex(ValueError,'no evidence progress'):
                discover_releases(journal,root,[index],'2026-10-25')
            self.assertEqual(calls.call_count,2);self.assertEqual(len(journal.contexts),1)
            self.assertEqual(journal.saved['source_freshness_partial.json']['status'],'incomplete_discovery')

    def test_pdf_catalogue_and_complete_text_avoid_numeric_navigation_arrays_and_repeat_calls(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/annual.pdf'
        html=b'<p>1 March 2026. Complete narrative revenue 123.</p><a href="/results#2025">2025</a><a href="/annual.pdf">Annual original 1 March 2026</a><a href="/annual.pdf">Annual original 1 March 2026</a>'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(pages=[index+'#2025'],releases=[self.release(pdf,2026)])])
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:(html,index,'text/html') if url==index else (b'%PDF synthetic',pdf,'application/pdf')) as calls:
                result,_=discover_releases(journal,root,[index],'2026-10-25')
            context=journal.contexts[0]
            self.assertEqual(len(context['catalog']),1)
            self.assertEqual(context['catalog'][0]['url'],pdf)
            self.assertEqual(context['catalog'][0]['linking_evidence'][0]['exact_anchor_text'],'Annual original 1 March 2026')
            self.assertTrue(all('numbers' not in unit for unit in context['evidence']))
            self.assertIn('Complete narrative revenue 123.',' '.join(unit['text'] for unit in context['evidence']))
            self.assertEqual(next(root.glob('official_index_*.html')).read_bytes(),html)
            self.assertFalse(journal.errors);self.assertEqual(len(journal.contexts),1);self.assertEqual(calls.call_count,2)
            self.assertEqual(result['releases'][0]['url'],pdf)

    def test_terminal_gap_reports_exact_observed_pdf_candidate_evidence(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/annual.pdf'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(gaps=['Annual original URL unavailable'])])
            html=b'<p>1 March 2026</p><a href="/annual.pdf">Annual original 2025</a>'
            with patch('company_initiation.historic_construction.evidence.download',return_value=(html,index,'text/html')),self.assertRaisesRegex(ValueError,'Exact observed PDF links remain unselected'):
                discover_releases(journal,root,[index],'2026-10-25')
            self.assertIn(pdf,journal.errors[0]);self.assertIn('Annual original 2025',journal.errors[0])

    def test_only_repeated_pages_are_incomplete_without_a_paid_repair(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(pages=[index+'#2025'])])
            with patch('company_initiation.historic_construction.evidence.download',return_value=(b'<a href="/results#2025">2025</a>',index,'text/html')) as calls, \
                 self.assertRaisesRegex(ValueError,'repeated inspected pages were ignored'):
                discover_releases(journal,root,[index],'2026-10-25')
            self.assertFalse(journal.errors);self.assertEqual(len(journal.contexts),1);self.assertEqual(calls.call_count,1)
            self.assertEqual(journal.saved['source_freshness_partial.json']['status'],'incomplete_discovery')

    def test_pdf_index_format_failure_is_retained(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/report.pdf'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[])
            with patch('company_initiation.historic_construction.evidence.download',return_value=(b'%PDF synthetic',index,'application/pdf')),self.assertRaisesRegex(ValueError,'No evidenced'):
                discover_releases(journal,root,[index],'2026-10-25')
            attempt=journal.saved['source_freshness_partial.json']['retrieval_attempts'][0]
            self.assertEqual(attempt['status'],'failed');self.assertIn('navigation page is a PDF',attempt['error'])

    def test_missing_quarter_repair_uses_observed_anchor_context_then_pdf(self):
        from company_initiation.historic_construction.workflow import discover_releases
        home='https://synthetic.invalid';index=home+'/results';event=home+'/first-quarter';pdf=home+'/quarter.pdf'
        downloads={home:(b'<a href="/results" title="All financial results" hreflang="en"><span>Results archive</span></a>',home,'text/html'),
                   index:(b'<a href="/first-quarter">First quarter</a>',index,'text/html'),
                   event:(b'<p>1 March 2026</p><a type="application/pdf" href="/quarter.pdf">Original sales release</a>',event,'text/html'),
                   pdf:(b'%PDF synthetic',pdf,'application/pdf')}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            answers=[[self.answer(gaps=['Q1 not on supplied homepage']),self.answer(pages=[index])],
                     [self.answer(releases=[self.release(event,2026)],pages=[event]),self.answer(pages=[event])],
                     self.answer(releases=[self.release(pdf,2026)])]
            journal=self.journal(root,answers)
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:downloads[url]):
                result,_=discover_releases(journal,root,[home],'2026-10-25',historical_years=[2025])
            self.assertEqual(result['releases'][0]['url'],pdf)
            self.assertIn(index,journal.errors[0]);self.assertIn('Results archive',journal.errors[0]);self.assertIn('All financial results',journal.errors[0])
            self.assertIn('not an original PDF',journal.errors[1])
            link=journal.contexts[0]['official_pages'][0]['link_context'][0]
            self.assertEqual(link,dict(url=index,label='Results archive',title='All financial results',language='en'))

    def test_repeated_invalid_url_gets_actionable_feedback_and_stops_without_dispatch(self):
        from types import MethodType,SimpleNamespace
        from company_initiation.historic_construction.workflow import discover_releases
        from company_initiation.shared_runtime import RunJournal
        from unittest.mock import Mock
        index='https://synthetic.invalid/results';good=index+'/press/first-quarter-2026';bad=index+'/guessed/first-quarter-2026'
        with tempfile.TemporaryDirectory() as temporary:
            journal=SimpleNamespace(directory=Path(temporary),state={'artifacts':{}},configuration={'limits':{'repairs':2}},saved={})
            journal.ask=Mock(return_value=self.answer(pages=[bad]));journal.save=lambda:None
            journal.artifact=lambda name,data:journal.saved.update({name:copy.deepcopy(data)})
            journal.stage=MethodType(RunJournal.stage,journal)
            page=b'<a href="/results/press/first-quarter-2026">First-quarter 2026 results</a>'
            with patch('company_initiation.historic_construction.evidence.download',return_value=(page,index,'text/html')) as downloads, \
                 self.assertRaisesRegex(ValueError,'no progress'):
                discover_releases(journal,Path(temporary),[index],'2026-10-25')
            self.assertEqual(journal.ask.call_count,2);self.assertEqual(downloads.call_count,1)
            feedback=journal.ask.call_args_list[1].args[2]['validation_errors'][0]
            self.assertIn(bad,feedback);self.assertIn(good,feedback);self.assertIn('First-quarter 2026 results',feedback)
            self.assertIn('not automatic substitutes',feedback)

    def test_safe_url_equivalents_and_outer_quote_marks_preserve_exact_date_evidence(self):
        from company_initiation.historic_construction.workflow import discover_releases
        index='https://synthetic.invalid/results';pdf='https://synthetic.invalid/report.pdf'
        release=self.release('http://SYNTHETIC.invalid/report.pdf#download',2026)
        release['publication_evidence']='\u201c1 March 2026\u201d'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);journal=self.journal(root,[self.answer(releases=[release])])
            values={index:(b'<p>1 March 2026</p><a href="/report.pdf">Original annual</a>',index,'text/html'),pdf:(b'%PDF synthetic',pdf,'application/pdf')}
            with patch('company_initiation.historic_construction.evidence.download',side_effect=lambda url:values[url]):
                result,_=discover_releases(journal,root,[index],'2026-10-25')
            self.assertEqual(result['releases'][0]['url'],pdf)
            self.assertEqual(result['releases'][0]['publication_evidence'],'1 March 2026')


class ValuationResearchTests(unittest.TestCase):
    def test_public_saved_construct_enriches_once_without_remapping_or_resetting_budget(self):
        from company_initiation.__main__ import main
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_budget import BudgetLedger, ledger_path
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.forecast_construction.integrated import verified_integrated_record
        from company_initiation.dcf_construction.workflow import ensure_valuation_research
        from company_initiation.historic_construction.workflow import ensure_company_history_research
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'company';reports=archive/'financial_reports';reports.mkdir(parents=True)
            (reports/'original.txt').write_text('Synthetic restricted cash 30 as of 31 December 2025. '
                'Synthetic complete claim notes explicitly establish no other_claims, other_assets, pension_claim, '
                'deferred_consideration or additional dilution_shares: each is 0 at 31 December 2025.',encoding='utf-8')
            (root/'pyproject.toml').write_text('[tool.research-platform]\n',encoding='utf-8')
            inventory=inventory_local_sources(archive);source=inventory['sources'][0]
            outputs=root/'outputs';parent=outputs/'construct_fixture';parent.mkdir(parents=True)
            data=dict(company='SYNTHETIC saved valuation',currency='GBP',history_years=[2025],sources={source['id']:source},
                      model_configuration={'as_of':'2026-10-25'},observations=[],reporting_changes=[],entity_versions=[],reporting_bridges=[])
            inputs=parent/'company_model_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8');original=inputs.read_bytes()
            (parent/'calls.jsonl').write_text('',encoding='utf-8')
            record=dict(directory=str(parent),configuration=dict(company=data['company'],sources=str(archive),manifest=inventory['manifest_sha256'],limits={'usd':20}),
                        calls=[],sources=[],artifacts={inputs.name:hashlib.sha256(original).hexdigest()},status='research_complete')
            (parent/'record.json').write_text(json.dumps(record),encoding='utf-8')
            (archive/'valuation_research_context.json').write_text('{"purpose":"Ancillary fixture context, not original evidence"}',encoding='utf-8')
            provider=OpenAIProvider(api_key='SYNTHETIC-NOT-A-CREDENTIAL')
            stages=[]
            def answer(**kwargs):
                payload=kwargs['payload'];stage=payload['stage'];stages.append(stage)
                provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=10,output_tokens=5,total_tokens=15),output=[])
                if stage=='company_valuation_sources':return dict(source_ids=[source['id']],reasons=['Synthetic original note'],gaps=[])
                unit=payload['evidence'][0]
                if stage=='company_combined_history':return dict(checks=[dict(topic=topic,status='pass',issue_type='none',
                    period_ids=['2025-FY'],detail='Synthetic provider checks orchestration only.',
                    source_refs=[dict(source_id=source['id'],unit_id=unit['unit_id'])]) for topic in payload['required_topics']],summary='Synthetic historical gate')
                index=next(i for i,n in enumerate(unit['numbers']) if n['raw']=='30')
                item=self.entry('restricted_cash',0)
                ref=dict(source_id=source['id'],unit_id=unit['unit_id'])
                item['source_refs']=[ref];item['terms'][0]['reference']=dict(ref,number_index=index,number_format='dot_decimal')
                from company_initiation.dcf_construction.valuation import REQUIRED_CLAIM_ASSUMPTIONS
                zero_index=next(i for i,n in enumerate(unit['numbers']) if n['raw']=='0')
                claims=[item]
                for field in sorted(REQUIRED_CLAIM_ASSUMPTIONS-{'restricted_cash'}):
                    absence=self.entry(field,unit='shares_millions' if field=='dilution_shares' else 'reporting_currency_millions',
                        method='Synthetic complete original claim notes explicitly establish no '+field+'.')
                    absence['source_refs']=[ref]
                    absence['terms']=[dict(reference=dict(ref,number_index=zero_index,number_format='dot_decimal'),multiplier=1,weight=1)]
                    claims.append(absence)
                return dict(entries=claims,conventions=[],gaps=[])
            compiled=[]
            def compile_model(root_arg,company,archive_arg,path,**kwargs):
                from company_initiation.shared_runtime import RunJournal
                from company_initiation.dcf_construction.workflow import construct_valuation
                initial=json.loads(Path(path).read_text(encoding='utf-8'))
                self.assertNotIn('valuation',initial['model_configuration'])
                self.assertEqual(stages,['company_combined_history'])
                self.assertIs(kwargs['valuation_stage'],construct_valuation)
                result=outputs/'compiled_fixture';result.mkdir()
                previous=verified_integrated_record(Path(path).parent,outputs)
                ledger=BudgetLedger(ledger_path(outputs,company),company,20)
                ledger.import_record(previous)
                journal=RunJournal(result,provider,copy.deepcopy(previous['configuration']),previous=previous,ledger=ledger)
                journal.state['sources']=copy.deepcopy(previous.get('sources',[]))
                journal.artifact('inventory.json',json.loads((Path(path).parent/'inventory.json').read_text(encoding='utf-8')))
                with patch('company_initiation.dcf_construction.workflow.valuation_snapshot',
                        return_value=dict(result={'valuation_date':'2026-10-25'},artifacts={},checks=[])) as calculate_dcf:
                    valuation=kwargs['valuation_stage'](journal,{'company':company},{},initial,archive_arg)
                calculate_dcf.assert_called_once()
                enriched=valuation['company_inputs']
                self.assertEqual(enriched['observations'],initial['observations'])
                journal.artifact('company_model_inputs.json',enriched)
                journal.state['status']='complete_provisional';journal.save()
                compiled.append((result/'company_model_inputs.json',enriched,kwargs,Path(path)))
                return result
            arguments=['company_initiation','construct',data['company'],'--sources',str(archive),'--as-of','2026-10-25','--resume',str(parent)]
            with patch('company_initiation.__main__.find_project_root',return_value=root),patch('sys.argv',arguments), \
                 patch('company_initiation.shared_ai.OpenAIProvider.from_env',return_value=provider),patch.object(provider,'complete',side_effect=answer), \
                 patch('company_initiation.historic_construction.workflow.research_company_inputs',side_effect=AssertionError('No historical remapping')), \
                 patch('company_initiation.historic_construction.workflow.update_company_inputs',side_effect=AssertionError('No disclosure update for unchanged archive/date')), \
                 patch('company_initiation.forecast_construction.integrated.construct_integrated',side_effect=compile_model),patch('builtins.print') as printed:
                self.assertEqual(main(),0,str(printed.call_args_list[-3:]))
            self.assertEqual(stages,['company_combined_history','company_valuation_sources','company_valuation_research','company_valuation_review'])
            enriched,saved,kwargs,historical_inputs=compiled[0]
            self.assertEqual(saved['model_configuration']['valuation']['assumptions']['restricted_cash']['value'],30)
            self.assertTrue(kwargs['include_valuation']);self.assertEqual(kwargs['resume'],str(historical_inputs.parent))
            self.assertEqual(inputs.read_bytes(),original)
            verified=verified_integrated_record(enriched.parent,outputs)
            saved_inventory=json.loads((enriched.parent/'inventory.json').read_text(encoding='utf-8'))
            self.assertEqual(saved_inventory['ancillary'][0]['status'],'excluded_source_input')
            ledger=BudgetLedger(ledger_path(outputs,data['company']),data['company'],20)
            before=ledger.summary();self.assertEqual(before['total_requests'],4)
            self.assertGreater(before['known_cost_usd'],0)
            with patch('company_initiation.shared_ai.OpenAIProvider.from_env',side_effect=AssertionError('Completed research must not load provider')):
                self.assertEqual(ensure_valuation_research(root,data['company'],archive,enriched),enriched)
                self.assertEqual(ensure_company_history_research(root,data['company'],archive,enriched),enriched)
            self.assertEqual(ledger.summary(),before)
            self.assertEqual(len(verified['calls']),4)

    def fixture(self, answers, *, complete_claims=True):
        from types import SimpleNamespace
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.dcf_construction.valuation import REQUIRED_CLAIM_ASSUMPTIONS
        answers=[copy.deepcopy(answer) for answer in answers]
        absent=REQUIRED_CLAIM_ASSUMPTIONS-{item['field'] for answer in answers for item in answer['entries']} if complete_claims else set()
        for answer in answers:
            answer['entries'].extend(self.entry(field,4,unit='shares_millions' if field=='dilution_shares' else 'reporting_currency_millions',
                method='Synthetic complete claim note explicitly establishes no '+field+' at the stated date.') for field in sorted(absent))
        source=dict(id='synthetic_note',category='financial_reports',published_at='2026-03-01')
        document=dict(source_id=source['id'],unit_id='page:1',
            text='Synthetic notes: restricted cash 30; employee liabilities 100; assets 20. Ordinary share price 42 at 31 December 2025. '
                +'Synthetic complete claim note: '+', '.join(sorted(absent))+' are each explicitly absent, value 0, at 31 December 2025.',
            numbers=[dict(raw=str(value)) for value in (30,100,20,42,0)])
        store=object.__new__(SourceStore);store.sources=[source];store._units={source['id']:{document['unit_id']:document}}
        journal=SimpleNamespace(saved={},stages=[],prompts=[],state={})
        def stage(name,prompt,context,schema,validator):
            journal.stages.append((name,copy.deepcopy(context)))
            journal.prompts.append((name,prompt))
            return validator(copy.deepcopy(answers.pop(0)))
        journal.stage=stage;journal.artifact=lambda name,data:journal.saved.update({name:copy.deepcopy(data)})
        data=dict(company='SYNTHETIC VALUATION',currency='GBP',sources={source['id']:source},model_configuration={'as_of':'2026-10-25'})
        return journal,data,[document],store

    @staticmethod
    def entry(field,index=None,**changes):
        ref=dict(source_id='synthetic_note',unit_id='page:1')
        terms=[] if index is None else [dict(reference=dict(ref,number_index=index,number_format='dot_decimal'),multiplier=1.,weight=1.)]
        value=dict(field=field,calculation='sum',terms=terms,denominator_terms=[],estimated_value=None,as_of='2025-12-31',status='reported',
            method='Synthetic original source binding.',source_refs=[ref],unit='reporting_currency_millions',
            currency='GBP',price_unit_scale=1.,date_evidence='')
        value.update(changes);return value

    def test_source_values_proxy_and_stale_price_keep_provenance_and_missing_defaults(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        from company_initiation.dcf_construction.valuation import generate_valuation_inputs
        from tests.test_valuation import fixture
        pension=self.entry('pension_claim',1,status='proxy',method='Coarse employee-benefit liabilities less assets; not pure pension disclosure.')
        pension['terms'].append(dict(reference=dict(source_id='synthetic_note',unit_id='page:1',number_index=2,number_format='dot_decimal'),multiplier=-1.,weight=1.))
        price=self.entry('market_price',3,unit='currency_per_share',date_evidence='31 December 2025')
        unresolved=self.entry('risk_free_rate',status='unresolved',as_of=None,source_refs=[],method='No compatible dated market rate in supplied notes.',unit='ratio')
        answer=dict(entries=[self.entry('restricted_cash',0),pension,price,unresolved],conventions=[],gaps=[])
        journal,data,documents,store=self.fixture([answer,answer]);before=copy.deepcopy(data)
        config=research_valuation_configuration(journal,data,documents,store)
        self.assertEqual(data,before)
        self.assertEqual(config['assumptions']['restricted_cash']['value'],30)
        self.assertEqual(config['assumptions']['pension_claim']['value'],80)
        self.assertEqual(config['assumptions']['pension_claim']['status'],'proxy')
        self.assertEqual(len(config['assumptions']['pension_claim']['source_refs']),2)
        self.assertNotIn('risk_free_rate',config['assumptions'])
        self.assertTrue(any('risk_free_rate' in text and 'No compatible dated market rate' in text for text in config['research']['limitations']))
        self.assertIn('A numeric zero needs affirmative source-backed justification',journal.prompts[0][1])
        self.assertIn('Unresolved material valuation inputs make the valuation incomplete',journal.prompts[0][1])
        self.assertIn('Challenge every zero claim/adjustment',journal.prompts[1][1])
        self.assertNotIn('risk_free_rate',config['assumptions'])
        self.assertEqual(config['market']['price']['as_of'],'2025-12-31')
        self.assertTrue(config['market']['price']['stale_as_of_valuation'])
        self.assertEqual([item[0] for item in journal.stages],['company_valuation_research','company_valuation_review'])
        self.assertIn('candidate',journal.stages[1][1])
        self.assertIn('valuation_research.json',journal.saved)
        spec,values,_=fixture()
        actual=generate_valuation_inputs(spec,values,dict(model_configuration={'valuation':config}),valuation_date='2026-10-25')
        self.assertEqual(actual['assumptions']['restricted_cash']['value'],30)
        self.assertEqual(actual['assumptions']['risk_free_rate']['status'],'provisional_assumption')

    def test_invalid_reported_number_reference_date_and_units_fail_inside_stage(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        examples=[(self.entry('restricted_cash',estimated_value=30),'exact numeric'),
                  (self.entry('restricted_cash',0,source_refs=[]),'citations'),
                  (self.entry('restricted_cash',0,as_of='2027-01-01'),'information cutoff'),
                  (self.entry('restricted_cash',0,unit='ratio'),'Incorrect valuation unit'),
                  (self.entry('market_price',3,unit='currency_per_share',date_evidence='25 October 2026'),'quote measurement date'),
                  (self.entry('market_price',3,unit='currency_per_share',date_evidence='31 December 2025',as_of='2026-10-25'),'single explicit date'),
                  (self.entry('pension_claim',estimated_value=0,status='unresolved'),'must not fabricate')]
        for entry,message in examples:
            with self.subTest(message=message):
                answer=dict(entries=[entry],conventions=[],gaps=[])
                journal,data,documents,store=self.fixture([answer])
                with self.assertRaisesRegex(ValueError,message):research_valuation_configuration(journal,data,documents,store)
                self.assertEqual(len(journal.stages),1)
                self.assertNotIn('valuation_configuration.json',journal.saved)

    def test_review_can_remove_unsupported_claim_without_fabricated_zero(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        initial=dict(entries=[self.entry('pension_claim',1)],conventions=[],gaps=[])
        reviewed=dict(entries=[self.entry('pension_claim',status='unresolved',as_of=None,source_refs=[],
            method='Gross employee liabilities are not a supported net pension valuation claim.')],conventions=[],gaps=['Pure pension scope unresolved.'])
        journal,data,documents,store=self.fixture([initial,reviewed])
        data['model_configuration']['valuation']=dict(assumptions={'pension_claim':dict(value=0,as_of='2025-12-31',status='estimated',
            method='Prior provisional zero',source_refs=[dict(source_id='synthetic_note',unit_id='page:1')])})
        before=copy.deepcopy(data)
        with self.assertRaisesRegex(ValueError,'pension_claim: unresolved claim'):
            research_valuation_configuration(journal,data,documents,store)
        self.assertEqual(journal.saved['valuation_research_initial.json']['resolved_entries'][0]['value'],100)
        self.assertNotIn('valuation_configuration.json',journal.saved)
        self.assertNotIn('valuation_research.json',journal.saved)
        self.assertEqual(data,before)

    def test_missing_and_unresolved_required_claims_share_bounded_repair_feedback(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        from company_initiation.dcf_construction.valuation import REQUIRED_CLAIM_ASSUMPTIONS
        incomplete=dict(entries=[self.entry('pension_claim',status='unresolved',as_of=None,source_refs=[],
            method='Pure pension scope is not quantified in the available employee note.')],conventions=[],gaps=[])
        journal,data,documents,store=self.fixture([incomplete],complete_claims=False)
        with self.assertRaises(ValueError) as raised:research_valuation_configuration(journal,data,documents,store)
        for field in REQUIRED_CLAIM_ASSUMPTIONS:self.assertIn(field+':',str(raised.exception))
        self.assertIn('Pure pension scope',str(raised.exception))
        self.assertEqual(journal.saved,{})
        # Exercise a bounded stage repair using the exact same validator. The
        # source is an explicit synthetic absence schedule, not a fabricated
        # real-company zero or a relaxed completion gate.
        empty=dict(entries=[],conventions=[],gaps=[])
        journal,data,documents,store=self.fixture([empty,empty]);normal_stage=journal.stage;feedback=[]
        def repair_stage(name,prompt,payload,schema,validator):
            if name=='company_valuation_research':
                try:validator(copy.deepcopy(incomplete))
                except ValueError as exc:feedback.append(str(exc))
                else:self.fail('Incomplete claims must reach bounded repair')
            return normal_stage(name,prompt,payload,schema,validator)
        journal.stage=repair_stage
        config=research_valuation_configuration(journal,data,documents,store)
        self.assertEqual(len(feedback),1)
        self.assertEqual(set(config['assumptions']),set(REQUIRED_CLAIM_ASSUMPTIONS))
        self.assertEqual(config['research']['status'],'completed_provisional')

    def test_documented_zero_estimate_is_valid_but_incomplete_or_stale_cache_is_not(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration, _valuation_research_current, ensure_valuation_research
        from company_initiation.dcf_construction.valuation import REQUIRED_CLAIM_ASSUMPTIONS
        estimate=self.entry('other_assets',status='estimated',estimated_value=0,
            method='Synthetic complete note classifies the employee assets as operating; zero additional non-operating value is a cited classification estimate, not a missing-data fill.')
        answer=dict(entries=[estimate],conventions=[],gaps=[])
        journal,data,documents,store=self.fixture([answer,answer])
        config=research_valuation_configuration(journal,data,documents,store)
        kwargs=dict(company=data['company'],currency=data['currency'],information_cutoff=data['model_configuration']['as_of'])
        self.assertTrue(_valuation_research_current(config,**kwargs))
        self.assertEqual(config['assumptions']['other_assets']['status'],'estimated')
        self.assertNotIn('risk_free_rate',config['assumptions'])
        invalid=[]
        missing=copy.deepcopy(config);del missing['assumptions']['pension_claim'];invalid.append(missing)
        unknown=copy.deepcopy(config);unknown['research']['entries'][0].update(value=None,status='unresolved');invalid.append(unknown)
        stale=copy.deepcopy(config);stale['assumptions']['other_assets']['value']=12;invalid.append(stale)
        uncited=copy.deepcopy(config);uncited['assumptions']['other_assets']['source_refs']=[];invalid.append(uncited)
        future=copy.deepcopy(config);future['assumptions']['other_assets']['as_of']='2027-01-01';invalid.append(future)
        old=copy.deepcopy(config);old['research']['schema']='valuation_research_v3';invalid.append(old)
        for field,value in [('status','provisional_assumption'),('unit','ratio'),('currency','EUR')]:
            changed=copy.deepcopy(config);changed['research']['entries'][0][field]=value
            changed['assumptions']['other_assets'][field]=value;invalid.append(changed)
        for candidate in invalid:
            with self.subTest(candidate=candidate):self.assertFalse(_valuation_research_current(candidate,**kwargs))
        # The public enrichment boundary must not return a claimed-completed
        # cache with unresolved reviewed entries and an old projected zero.
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'company';archive.mkdir();inputs=root/'company_inputs.json'
            data['model_configuration']['valuation']=unknown
            inputs.write_text(json.dumps(data),encoding='utf-8');before=inputs.read_bytes()
            with patch('company_initiation.shared_ai.OpenAIProvider.from_env',side_effect=RuntimeError('Fresh bounded research required')):
                with self.assertRaisesRegex(RuntimeError,'Fresh bounded research required'):
                    ensure_valuation_research(root,data['company'],archive,inputs)
            self.assertEqual(inputs.read_bytes(),before)
        self.assertEqual(set(config['assumptions']),set(REQUIRED_CLAIM_ASSUMPTIONS))

    def test_all_entry_errors_identify_reconstructed_values_bounds_and_conflicts(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        bad=dict(entries=[self.entry('tax_rate',1,unit='ratio'),
            self.entry('pension_claim',1,status='proxy',estimated_value=80),
            self.entry('restricted_cash',0,as_of='2027-01-01'),
            self.entry('deferred_consideration',0)],
            conventions=[dict(topic='cash_scope',statement='',status='reported',source_refs=[])],gaps=[])
        bad['entries'][-1]['terms'][0]['multiplier']=-1.
        journal,data,documents,store=self.fixture([bad]);before=copy.deepcopy(data)
        with self.assertRaises(ValueError) as raised:research_valuation_configuration(journal,data,documents,store)
        message=str(raised.exception)
        self.assertIn('5 entries/conventions',message)
        for field in ('tax_rate','pension_claim','restricted_cash','deferred_consideration'):self.assertIn('"field": "'+field+'"',message)
        self.assertIn('"resolved_value": 100.0',message)
        self.assertIn('"resolved_value": -30.0',message)
        self.assertIn('minimum=0, maximum=None',message)
        self.assertIn('"estimated_value": 80',message)
        self.assertIn('minimum=0, maximum=1',message)
        self.assertIn('division requires calculation=ratio',message)
        self.assertIn('estimated_value=null',message)
        self.assertIn('2027-01-01',message);self.assertIn('2026-10-25',message)
        self.assertIn("topic='cash_scope'",message)
        self.assertEqual(data,before);self.assertEqual(journal.saved,{})
        self.assertEqual(len(journal.stages),1)
        requirements=journal.stages[0][1]['field_requirements']['tax_rate']
        self.assertEqual(requirements['unit'],'ratio');self.assertEqual(tuple(requirements['inclusive_bounds']),(0.,1.))

    def test_matching_estimate_does_not_silently_override_reconstruction(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        for estimate in (100,80):
            entry=self.entry('pension_claim',1,status='proxy',estimated_value=estimate)
            journal,data,documents,store=self.fixture([dict(entries=[entry],conventions=[],gaps=[])])
            with self.subTest(estimate=estimate),self.assertRaisesRegex(ValueError,'cannot combine source reconstruction'):
                research_valuation_configuration(journal,data,documents,store)
            self.assertNotIn('valuation_configuration.json',journal.saved)

    def test_explicit_source_ratio_uses_python_division_and_keeps_both_operands(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        rate=self.entry('tax_rate',2,calculation='ratio',unit='ratio',status='derived_reported',
            denominator_terms=self.entry('cash',1)['terms'],method='Synthetic compatible tax20 over pretax100; Python divides the exact sources.')
        answer=dict(entries=[rate,self.entry('pension_claim',0)],conventions=[],gaps=[])
        journal,data,documents,store=self.fixture([answer,answer])
        config=research_valuation_configuration(journal,data,documents,store)
        rate=config['assumptions']['tax_rate']
        self.assertEqual(rate['value'],.2)
        self.assertEqual(rate['arithmetic_provenance']['numerator_value'],20)
        self.assertEqual(rate['arithmetic_provenance']['denominator_value'],100)
        self.assertEqual({r['operand'] for r in rate['source_refs']},{'numerator','denominator'})
        self.assertEqual(rate['unit'],'ratio');self.assertEqual(rate['scale'],1)
        claim=config['assumptions']['pension_claim']
        self.assertEqual((claim['value'],claim['unit'],claim['scale'],claim['currency']),(30,'reporting_currency_millions',1e6,'GBP'))
        self.assertEqual(config['research']['schema'],VALUATION_RESEARCH_VERSION)
        self.assertEqual(journal.stages[0][1]['source_metadata'][0]['published_at'],'2026-03-01')

    def test_source_ratio_rejects_zero_denominator_and_hidden_reciprocal_weights(self):
        from company_initiation.dcf_construction.workflow import research_valuation_configuration
        ratio=self.entry('tax_rate',2,calculation='ratio',unit='ratio',status='proxy',denominator_terms=self.entry('cash',1)['terms'])
        zero=copy.deepcopy(ratio);zero['denominator_terms'].append(copy.deepcopy(zero['denominator_terms'][0]));zero['denominator_terms'][-1]['weight']=-1
        reciprocal=self.entry('tax_rate',2,unit='ratio',status='proxy');reciprocal['terms'][0]['weight']=1/101
        coefficient=copy.deepcopy(reciprocal);coefficient['terms'][0].update(weight=1,multiplier=1/101)
        inconsistent=copy.deepcopy(ratio);inconsistent['calculation']='sum'
        missing=copy.deepcopy(ratio);missing['denominator_terms']=[]
        for entry,message in [(zero,'denominator resolves to zero'),(reciprocal,'calculated reciprocal'),(coefficient,'invented coefficient'),(inconsistent,'sum requires empty'),(missing,'requires nonempty')]:
            journal,data,documents,store=self.fixture([dict(entries=[entry],conventions=[],gaps=[])])
            with self.subTest(message=message),self.assertRaisesRegex(ValueError,message):
                research_valuation_configuration(journal,data,documents,store)
            self.assertNotIn('valuation_configuration.json',journal.saved)


class HistoricalVersionRevisionTests(unittest.TestCase):
    @staticmethod
    def scope_answer(payload,targets):
        return dict(targets=copy.deepcopy(targets),primary_evidence_absent=False,gaps=[],
            finding_dispositions=[dict(finding_id=item['id'],action='reconstruct',
                target_indexes=list(range(len(targets))),observation_ids=[],detail='Reconstruct the cited missing version.',
                source_refs=[dict(source_id='new',unit_id='page:1')]) for item in payload['scoped_findings']])

    def test_scope_requires_every_cited_finding_without_duplicate_basis_targets(self):
        from company_initiation.historic_construction.workflow import _history_scope_findings, _validate_history_revision_scope
        data,_,facts,targets,catalog,units=self.fixture()
        saved=copy.deepcopy(facts[1]);saved['basis']='alternate_published_label';data['observations'].append(saved)
        findings=_history_scope_findings([dict(kind='missing_model_version',check='An invented basis name was alleged absent.',period_ids=['2020-FY']),
            dict(kind='missing_model_version',check='Required source vintage is missing.',period_ids=['2020-FY'])])
        answer=self.scope_answer(dict(scoped_findings=findings),targets)
        answer['finding_dispositions'][0].update(action='already_preserved',target_indexes=[],observation_ids=[saved['id']],
            detail='The published version exists under its preserved label; no new duplicate fact is needed.')
        supplied={(u['source_id'],u['unit_id']) for u in units}
        def validate(value):return _validate_history_revision_scope(value,findings,data['observations'],supplied,catalog,{2020})
        self.assertEqual(validate(answer),answer)
        cases=[('omitted',lambda a:a['finding_dispositions'].pop(),'omitted mandatory'),
            ('duplicate',lambda a:a['finding_dispositions'].append(copy.deepcopy(a['finding_dispositions'][0])),'exactly once'),
            ('index',lambda a:a['finding_dispositions'][1].update(target_indexes=[4]),'invalid or duplicate target'),
            ('citation',lambda a:a['finding_dispositions'][0].update(source_refs=[dict(source_id='new',unit_id='page:99')]),'exact supplied primary'),
            ('observation',lambda a:a['finding_dispositions'][0].update(observation_ids=['unknown']),'eligible saved observations'),
            ('model_gap',lambda a:a.update(gaps=['A source-present model binding is missing.']),'exclusively for absent required PRIMARY'),
            ('primary_gap',lambda a:a.update(primary_evidence_absent=True,gaps=['The required original is unavailable.']),'unresolved primary support')]
        for name,mutate,message in cases:
            changed=copy.deepcopy(answer);mutate(changed)
            with self.subTest(case=name),self.assertRaisesRegex(ValueError,message):validate(changed)
        original=copy.deepcopy(data);self.assertEqual(data,original)

    def test_exact_existing_source_binding_cannot_be_duplicated_under_invented_basis(self):
        from company_initiation.historic_construction.workflow import _merge_historical_version_revision
        data,answer,facts,targets,catalog,units=self.fixture()
        existing=copy.deepcopy(facts[1]);data['observations'].append(existing);before=copy.deepcopy(data)
        facts[1]=dict(facts[1],id='invented_duplicate',basis='invented_basis_name')
        with self.assertRaisesRegex(ValueError,'same financial concept, amount and exact primary token'):
            _merge_historical_version_revision(data,answer,facts,targets=targets,catalog=catalog,evidence=units,revision=1)
        self.assertEqual(data,before)

    def test_proposal_only_preserves_allegations_and_stops_unchanged_scope_after_full_reassessment(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, combined_history_review_current, combined_history_fingerprint
        data,_,facts,_,catalog,units=self.fixture();before=copy.deepcopy(data);outer=self
        # This intentionally wrong proposal claims the original amount is the
        # missing published revision. Only a complete subsequent review decides.
        class Journal:
            configuration={'limits':{'repairs':2}}
            def __init__(self):self.reviews=0;self.scopes=0;self.saved={}
            def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
            def stage(self,stage,prompt,payload,schema,validate):
                outer.assertEqual(stage,'company_history_revision_scope');self.scopes+=1
                answer=dict(targets=[],primary_evidence_absent=False,gaps=[],finding_dispositions=[dict(
                    finding_id=item['id'],action='already_preserved',target_indexes=[],observation_ids=[facts[0]['id']],
                    detail='Changed explanatory wording '+str(self.scopes),source_refs=[dict(source_id='new',unit_id='page:1')])
                    for item in payload['scoped_findings']])
                return validate(answer)
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                self.reviews+=1
                outer.assertIn('non-accepting scope opinions',prompt)
                if self.reviews>1:
                    outer.assertEqual(data['observations'],before['observations'])
                    outer.assertTrue(payload['historical_scope_proposals'])
                    outer.assertTrue(payload['financial_review_obligations'])
                result=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Cited check',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']],summary='Full reassessment')
                next(c for c in result['checks'] if c['topic']=='restatement_versions').update(status='error',
                    issue_type='missing_model_version',period_ids=['2020-FY'],detail='The published revised CFO remains absent.')
                if payload['financial_review_obligations']:
                    result['financial_adjudications']=[dict(finding_id=o['id'],outcome='unresolved',resolution='unresolved',
                        observation_ids=[],detail='The scope proposal points to original 100, whereas the primary revised figure is 107.',
                        source_refs=[dict(source_id='new',unit_id='page:1')]) for o in payload['financial_review_obligations']]
                assess(result);return result
        journal=Journal()
        with self.assertRaisesRegex(ValueError,'scope proposals made no progress'):
            _combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
        self.assertEqual((journal.reviews,journal.scopes),(2,2))
        for key in ('observations','historical','active_basis_by_period','reporting_bridges'):self.assertEqual(data[key],before[key])
        self.assertNotIn('historical_version_revisions',data);self.assertFalse(combined_history_review_current(data))
        self.assertEqual(journal.saved['company_model_inputs.json']['historical_scope_proposals'],data['historical_scope_proposals'])
        self.assertEqual(journal.saved['history_revised_inputs_1.json']['observations'],before['observations'])
        self.assertNotEqual(combined_history_fingerprint(data),combined_history_fingerprint(before))

    def test_targeted_adjudication_correction_keeps_last_request_evidence_and_full_validation(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, combined_history_review_current
        outer=self
        for outcome in ('version_repair','pass','financial','invalid','duplicate','transport','repeated','missing_primary'):
            data,_,facts,_,catalog,units=self.fixture();base=copy.deepcopy(data['observations'][0])
            half=dict(base,id='saved_half',period_id='2020-H1',kind='H1',end='2020-06-30',value=40)
            data['observations'].append(half);before=copy.deepcopy(data)
            obligation=dict(id='covered_version',topic='segment_lineage',fiscal_years=[2020],original_finding=dict(
                kind='missing_model_version',topic='segment_lineage',period_ids=['2020-H1','2020-FY'],
                check='A retained version was alleged absent.',evidence=[dict(source_id='new',unit_id='page:1')]))
            data['historical_review_obligations']=[obligation]
            class Journal:
                configuration={'limits':{'repairs':1}}
                def __init__(self):self.entries=[];self.saved={};self.asks=[];self.completed=[]
                def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    active=copy.deepcopy(payload)
                    for attempt in range(2):
                        result=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Cited primary check',
                            source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']],summary='Untouched complete review')
                        if outcome=='version_repair':
                            result['checks'][3].update(status='error',issue_type='missing_model_version',period_ids=['2020-FY'],detail='Published alternate CFO requires reconstruction.')
                            if attempt:result['checks'][4].update(status='error',issue_type='missing_model_version',period_ids=['2020-FY'],detail='New provenance allegation retained after the last request.')
                        if outcome=='financial':result['checks'][1].update(status='error',issue_type='financial_interpretation',period_ids=['2020-FY'],detail=base['id']+' has a concrete incompatible active equation.')
                        if outcome=='missing_primary' and attempt:result['checks'][1].update(status='error',issue_type='missing_primary_evidence',period_ids=['2020-FY'],detail='Required original disclosure remains absent.')
                        if attempt==0:
                            for check in result['checks'][:2]:check['source_refs']=[dict(source_id='new',unit_id='page:99')]
                        result['financial_adjudications']=[dict(finding_id=o['id'],outcome='resolved' if o['id']=='covered_version' else 'unresolved',
                            resolution='already_preserved' if o['id']=='covered_version' else 'unresolved',
                            observation_ids=([base['id']] if attempt or outcome=='repeated' else [base['id'],half['id']]) if o['id']=='covered_version' else [],
                            detail='Narrative mentions saved_half but does not insert that ID into the array.' if o['id']=='covered_version' else 'Source-present version remains unbound.',
                            source_refs=[dict(source_id='new',unit_id='page:1')]) for o in active['financial_review_obligations']]
                        request=dict(payload=copy.deepcopy(active),schema=copy.deepcopy(schema))
                        self.entries.append(dict(stage=stage,result=copy.deepcopy(result),request=request,call_id='completed_'+str(attempt),signature='signature_'+str(attempt)))
                        self.completed.append(copy.deepcopy(result));failures=assess(result)
                        repaired=repair_context(copy.deepcopy(active),failures)
                        if repaired is not None:active=repaired
                    raise ValueError('unresolved evidence/context/contract problem')
                def ask(self,stage,prompt,payload,schema):
                    self.asks.append(copy.deepcopy(payload));outer.assertTrue(stage.endswith('_adjudication_correction'))
                    outer.assertEqual(payload['correction']['finding_ids'],['covered_version'])
                    outer.assertEqual(payload['correction']['validator_feedback'][0]['missing_period_ids'],['2020-H1'])
                    outer.assertEqual(payload['review_context'],self.entries[-1]['request']['payload'])
                    outer.assertEqual(payload['original_answer'],self.completed[-1])
                    outer.assertEqual(schema['properties']['financial_adjudications']['items']['properties']['finding_id']['enum'],['covered_version'])
                    fixed=copy.deepcopy(next(item for item in self.completed[-1]['financial_adjudications'] if item['finding_id']=='covered_version'))
                    if outcome!='invalid':fixed['observation_ids'].append(half['id'])
                    if outcome=='transport':raise ValueError('Recorded synthetic provider failure; no retry')
                    if outcome=='duplicate':return dict(financial_adjudications=[fixed,copy.deepcopy(fixed)])
                    return dict(financial_adjudications=[fixed])
            journal=Journal()
            repair=Mock(side_effect=ValueError('Independent reconstruction reached'))
            def attempt_revision(*args,**kwargs):return repair(*args,**kwargs)
            with self.subTest(outcome=outcome),patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda j,docs,*a,**k:docs),patch(
                    'company_initiation.historic_construction.workflow._repair_historical_versions',new=attempt_revision):
                if outcome=='pass':
                    _combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertTrue(combined_history_review_current(data))
                else:
                    expected=('Independent reconstruction reached' if outcome=='version_repair' else
                        'unresolved evidence/context/contract problem' if outcome in ('repeated','missing_primary') else
                        'every flagged finding exactly once' if outcome=='duplicate' else
                        'Recorded synthetic provider failure' if outcome=='transport' else 'remains incomplete')
                    with self.assertRaisesRegex(ValueError,expected):_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertNotIn('combined_history_review',data)
                self.assertEqual(len(journal.asks),0 if outcome in ('repeated','missing_primary') else 1)
                if outcome=='version_repair':
                    repair.assert_called_once();gap=repair.call_args.args[3]
                    self.assertEqual({f['kind'] for f in gap.findings},{'missing_model_version'})
                    self.assertGreater(len(gap.context['financial_review_obligations']),len(journal.asks[0]['review_context']['financial_review_obligations']))
                else:repair.assert_not_called()
            if journal.asks and outcome not in ('duplicate','transport'):
                prefix=next(name[:-len('_request.json')] for name in journal.saved if name.startswith('combined_history_all_years_adjudication_correction_') and name.endswith('_request.json'))
                merged=journal.saved[prefix+'_merged.json']
                self.assertEqual(merged['checks'],journal.completed[-1]['checks']);self.assertEqual(merged['summary'],journal.completed[-1]['summary'])
                original=next(item for item in journal.completed[-1]['financial_adjudications'] if item['finding_id']=='covered_version')
                self.assertEqual(original['observation_ids'],[base['id']])
                self.assertEqual(journal.saved[prefix+'_assessment.json']['last_completed_request']['call_id'],'completed_1')
            self.assertEqual(data['observations'],before['observations']);self.assertEqual(data['historical'],before['historical'])

    def test_targeted_adjudication_progress_gate_rejects_no_progress_and_other_contracts(self):
        from company_initiation.historic_construction.workflow import _history_adjudication_correction_plan
        ordinary=[dict(kind='output_contract',check='Unsupplied citation one'),dict(kind='output_contract',check='Unsupplied citation two')]
        target=dict(kind='output_contract',check='Missing structured period reference',error_category='adjudication_reference',finding_id='f')
        def snapshot(failures):return dict(failures=copy.deepcopy(failures),answer=dict(financial_adjudications=[dict(finding_id='f')]),context={},request_identity={})
        self.assertIsNotNone(_history_adjudication_correction_plan([snapshot(ordinary),snapshot([target])]))
        for prior,final in [([target],[target]),([ordinary[0]],[target]),(ordinary,[dict(kind='output_contract',check='Missing topic')]),
                            (ordinary,[target,dict(kind='context_omission',check='Original omitted')]),
                            (ordinary,[target,dict(kind='missing_primary_evidence',check='Required primary absent')])]:
            with self.subTest(prior=prior,final=final):self.assertIsNone(_history_adjudication_correction_plan([snapshot(prior),snapshot(final)]))
        self.assertIsNone(_history_adjudication_correction_plan([snapshot([target]),snapshot(ordinary),snapshot([target])]))

    def test_complete_version_only_answer_routes_before_whole_context_retry(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, _HistoricalVersionGap
        outer=self
        for extra in (None,'output_contract','financial_interpretation','missing_primary_evidence'):
            data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data);saved={};reviews=[]
            class Journal:
                configuration={'limits':{'repairs':1}}
                def artifact(self,name,value):saved[name]=copy.deepcopy(value)
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    reviews.append(stage)
                    response=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Complete cited check',
                        source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']],summary='Synthetic')
                    response['checks'][3].update(status='error',issue_type='missing_model_version',period_ids=['2020-FY'],detail='Published alternate CFO binding absent.')
                    if extra=='output_contract':response['checks'].pop()
                    elif extra:response['checks'][1].update(status='error',issue_type=extra,detail=facts[0]['id']+' supported separate concern.')
                    if extra is None:
                        # The real stage would dispatch its cheap reconsideration
                        # after assess returns. It must never get that far here.
                        assess(response);raise AssertionError('Unnecessary whole-context retry reached')
                    failures=assess(response)
                    outer.assertIn(extra,{f['kind'] for f in failures})
                    raise ValueError('Ordinary review path retained')
            with self.subTest(extra=extra),patch('company_initiation.historic_construction.workflow._repair_historical_versions',side_effect=ValueError('Independent repair reached')) as repair:
                with self.assertRaisesRegex(ValueError,'Independent repair reached' if extra is None else 'Ordinary review path retained'):
                    _combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()))
                self.assertEqual(len(reviews),1)
                if extra is None:
                    repair.assert_called_once();gap=repair.call_args.args[3]
                    self.assertIsInstance(gap,_HistoricalVersionGap)
                    self.assertEqual({f['kind'] for f in gap.findings},{'missing_model_version'})
                    self.assertEqual(len(gap.context['financial_review_obligations']),1)
                    route=saved['combined_history_all_years_version_repair_route.json']
                    self.assertEqual(route['status'],'independent_version_repair_required')
                    self.assertEqual(len(route['answer']['checks']),6)
                else:repair.assert_not_called()
            self.assertEqual(data['observations'],before['observations']);self.assertEqual(data['historical'],before['historical'])
            self.assertNotIn('combined_history_review',data)

    def test_shifted_missing_period_plan_requires_actual_prior_coverage_and_no_repeated_pairs(self):
        from company_initiation.historic_construction.workflow import _history_adjudication_correction_plan
        base=self.fixture()[2][0]
        observations=[dict(base,id=period,period_id=period) for period in ('2020-Q1','2020-H1','2020-FY')]
        obligation=dict(id='version',topic='segment_lineage',fiscal_years=[2020],
            original_finding=dict(kind='missing_model_version',period_ids=[o['period_id'] for o in observations]))
        def snapshot(missing,ids):
            return dict(context=dict(financial_review_obligations=[copy.deepcopy(obligation)]),request_identity={},
                answer=dict(financial_adjudications=[dict(finding_id='version',outcome='resolved',resolution='already_preserved',observation_ids=ids)]),
                failures=[dict(kind='output_contract',error_category='adjudication_reference',finding_id='version',missing_period_ids=[missing],check='Missing period')])
        first=snapshot('2020-Q1',['2020-H1','2020-FY']);last=snapshot('2020-H1',['2020-Q1','2020-FY'])
        plan=_history_adjudication_correction_plan([first,last],observations=observations)
        self.assertEqual(plan['progress_kind'],'disjoint_missing_periods_after_explicit_coverage')
        self.assertEqual(plan['required_reference_coverage'],[dict(finding_id='version',period_ids=['2020-FY','2020-H1','2020-Q1'])])
        self.assertEqual(plan['prior_missing_period_coverage'],[dict(finding_id='version',period_id='2020-Q1',observation_ids=['2020-Q1'])])
        for variant in ('unchanged','uncovered','unknown','ineligible','changed_scope','other_contract','primary','financial','reappearing','more_missing'):
            before=copy.deepcopy(first);after=copy.deepcopy(last);facts=copy.deepcopy(observations);snapshots=[before,after]
            if variant=='unchanged':after['failures'][0]['missing_period_ids']=['2020-Q1']
            elif variant=='uncovered':after['answer']['financial_adjudications'][0]['observation_ids']=['2020-FY']
            elif variant=='unknown':after['answer']['financial_adjudications'][0]['observation_ids']=['unknown','2020-FY']
            elif variant=='ineligible':facts[0]['eligible']=False
            elif variant=='changed_scope':after['context']['financial_review_obligations'][0]['original_finding']['period_ids'].remove('2020-Q1')
            elif variant=='other_contract':after['failures'].append(dict(kind='output_contract',check='Invalid source citation'))
            elif variant in ('primary','financial'):after['failures'].append(dict(kind='missing_primary_evidence' if variant=='primary' else 'financial_interpretation',check='Unresolved substantive failure'))
            elif variant=='reappearing':snapshots.insert(0,copy.deepcopy(last))
            elif variant=='more_missing':after['failures'][0]['missing_period_ids']=['2020-H1','2020-FY']
            with self.subTest(case=variant):self.assertIsNone(_history_adjudication_correction_plan(snapshots,observations=facts))

    def test_shifted_reference_correction_is_single_request_with_full_period_set_and_full_reassessment(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        outer=self
        for outcome in ('repair','partial','duplicate','transport'):
            data,_,facts,_,catalog,units=self.fixture();base=data['observations'][0]
            data['observations'] += [dict(base,id='q1',period_id='2020-Q1',kind='Q1',end='2020-03-31',value=20),
                dict(base,id='h1',period_id='2020-H1',kind='H1',end='2020-06-30',value=40)]
            data['historical_review_obligations']=[dict(id='version',topic='segment_lineage',fiscal_years=[2020],original_finding=dict(
                kind='missing_model_version',topic='segment_lineage',period_ids=['2020-Q1','2020-H1','2020-FY'],
                check='The alternate segment version was alleged absent.',evidence=[dict(source_id='new',unit_id='page:1')]))]
            before=copy.deepcopy(data)
            class Journal:
                configuration={'limits':{'repairs':1}}
                def __init__(self):self.saved={};self.entries=[];self.asks=0;self.answers=[]
                def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    active=copy.deepcopy(payload)
                    for attempt in range(2):
                        answer=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Cited primary check',
                            source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']],summary='Untouched original review')
                        answer['checks'][3].update(status='error',issue_type='missing_model_version',period_ids=['2020-FY'],detail='Published alternate CFO requires independent reconstruction.')
                        answer['financial_adjudications']=[dict(finding_id=o['id'],outcome='resolved' if o['id']=='version' else 'unresolved',
                            resolution='already_preserved' if o['id']=='version' else 'unresolved',observation_ids=([base['id'],'h1' if attempt==0 else 'q1'] if o['id']=='version' else []),
                            detail='Choose explicitly supported retained versions.' if o['id']=='version' else 'Primary-present CFO remains missing.',
                            source_refs=[dict(source_id='new',unit_id='page:1')]) for o in active['financial_review_obligations']]
                        self.entries.append(dict(stage=stage,result=copy.deepcopy(answer),request=dict(payload=copy.deepcopy(active),schema=copy.deepcopy(schema)),call_id='complete_'+str(attempt),signature='signature_'+str(attempt)))
                        self.answers.append(copy.deepcopy(answer));failures=assess(answer)
                        repaired=repair_context(active,failures)
                        if repaired is not None:active=repaired
                    raise ValueError('unresolved evidence/context/contract problem')
                def ask(self,stage,prompt,payload,schema):
                    self.asks+=1;outer.assertEqual(self.asks,1)
                    outer.assertEqual(payload['correction']['required_reference_coverage'],[dict(finding_id='version',period_ids=['2020-FY','2020-H1','2020-Q1'])])
                    outer.assertEqual(payload['review_context'],self.entries[-1]['request']['payload'])
                    outer.assertEqual(payload['original_answer'],self.answers[-1]);outer.assertIn('ENTIRE required period set',prompt)
                    result=copy.deepcopy(self.answers[-1]['financial_adjudications'][0])
                    if outcome!='partial':result['observation_ids'].append('h1')
                    if outcome=='transport':raise ValueError('Recorded targeted transport failure')
                    return dict(financial_adjudications=[result,copy.deepcopy(result)] if outcome=='duplicate' else [result])
            journal=Journal();repair=Mock(side_effect=ValueError('Independent reconstruction reached'))
            def revised(*args,**kwargs):return repair(*args,**kwargs)
            with self.subTest(outcome=outcome),patch('company_initiation.historic_construction.workflow._repair_historical_versions',new=revised):
                expected={'repair':'Independent reconstruction reached','partial':'remains incomplete','duplicate':'every flagged finding exactly once','transport':'targeted transport failure'}[outcome]
                with self.assertRaisesRegex(ValueError,expected):_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                self.assertEqual(journal.asks,1)
                if outcome=='repair':repair.assert_called_once()
                else:repair.assert_not_called()
            self.assertEqual(data['observations'],before['observations']);self.assertEqual(data['historical'],before['historical'])
            if outcome in ('repair','partial'):
                merged=next(value for name,value in journal.saved.items() if '_adjudication_correction_' in name and name.endswith('_merged.json'))
                self.assertEqual(merged['checks'],journal.answers[-1]['checks']);self.assertEqual(merged['summary'],journal.answers[-1]['summary'])

    def test_verified_output_capacity_requires_exact_request_cap_and_provider_status(self):
        from types import SimpleNamespace
        from company_initiation.historic_construction.workflow import _history_output_capacity_failure
        from company_initiation.shared_runtime import digest
        context=dict(evidence=[dict(source_id='s',unit_id='page:1',text='Complete original')],required_topics=['reporting_bases'])
        schema={'type':'object'};request=dict(stage='history',instructions='review',schema=schema,payload=context,attempt=0)
        signature=digest(request)
        entry=dict(call_id='cap_call',stage='history',request=request,signature=signature,error='Incomplete provider response',max_output_tokens=16000,
            response=dict(status='incomplete',incomplete_details={'reason':'max_output_tokens'},usage={'output_tokens':16000},output=[{'type':'message','content':[{'text':'{"checks": [INCOMPLETE'}]}]))
        error=ValueError('max_output_tokens call_id=cap_call; signature='+signature)
        def proof(item=entry,maximum=16000,message=error):
            return _history_output_capacity_failure(SimpleNamespace(entries=[item],provider=SimpleNamespace(max_output_tokens=maximum)),
                'history',message,prompt='review',schema=schema,context=context)
        self.assertEqual(proof()['call_id'],'cap_call')
        self.assertIsNone(proof(maximum=32000));self.assertIsNone(proof(message=ValueError('max_output_tokens without saved identity')))
        for field,value in [('signature','forged'),('request',dict(request,instructions='different')),('result',{'checks':[]}),
            ('response',dict(status='incomplete',incomplete_details={'reason':'other'})),('response',dict(status='completed'))]:
            changed=copy.deepcopy(entry);changed[field]=value
            with self.subTest(field=field,value=value):self.assertIsNone(proof(changed))
        changed=copy.deepcopy(entry);changed['request']['payload']['evidence'][0]['text']='Changed original';changed['signature']=digest(changed['request'])
        self.assertIsNone(proof(changed,message=ValueError('max_output_tokens call_id=cap_call; signature='+changed['signature'])))

    def test_early_version_route_runs_blind_reconstruction_and_rechecks_retained_dispositions(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, combined_history_review_current
        data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data);outer=self
        prior=dict(id='previous_false_claim',topic='segment_lineage',fiscal_years=[2020],
            original_finding=dict(kind='missing_model_version',topic='segment_lineage',period_ids=['2020-FY'],
                check='A synthetic absent segment version was alleged.',evidence=[dict(source_id='new',unit_id='page:1')]))
        data['historical_review_obligations']=[prior]
        class Journal:
            configuration={'limits':{'repairs':1}}
            def __init__(self):self.calls=[];self.reviews=0;self.saved={}
            def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
            def stage(self,stage,prompt,payload,schema,validate):
                self.calls.append(stage)
                if stage.endswith('_scope'):response=outer.scope_answer(payload,targets)
                elif stage.endswith('_mapping'):response=answer
                elif stage.endswith('_independent'):
                    outer.assertEqual(set(payload),{'revision','requested_concepts','periods','evidence'})
                    response={key:copy.deepcopy(answer[key]) for key in ('observations','reporting_changes','gaps')}
                else:raise AssertionError(stage)
                return validate(copy.deepcopy(response))
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                self.calls.append(stage);self.reviews+=1
                checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Cited check',source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']]
                if self.reviews==1:
                    next(c for c in checks if c['topic']=='restatement_versions').update(status='error',issue_type='missing_model_version',period_ids=['2020-FY'],detail='Published revised CFO is absent.')
                else:
                    outer.assertEqual(len(data['observations']),4);outer.assertEqual(data['historical'],before['historical'])
                    outer.assertEqual({o['id'] for o in payload['financial_review_obligations']}&{'previous_false_claim'},{'previous_false_claim'})
                dispositions=[dict(finding_id=o['id'],outcome='resolved',resolution='withdrawn' if o['id']=='previous_false_claim' else 'repaired',
                    observation_ids=[] if o['id']=='previous_false_claim' else [facts[1]['id']],
                    detail='False segment allegation remains withdrawn against the original.' if o['id']=='previous_false_claim' else 'The independently reconstructed restated CFO is retained.',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for o in payload['financial_review_obligations']]
                response=dict(checks=checks,summary='Synthetic',financial_adjudications=dispositions)
                failures=assess(response)
                if self.reviews==1:raise AssertionError('A second whole-context reconsideration must not occur before reconstruction')
                outer.assertEqual(failures,[]);return response
        journal=Journal();result=_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
        self.assertTrue(combined_history_review_current(data));self.assertEqual(journal.reviews,2)
        self.assertEqual(journal.calls,['company_combined_history','company_history_revision_scope','company_history_revision_mapping',
            'company_history_revision_independent','company_combined_history'])
        self.assertEqual(data['observations'][0],before['observations'][0]);self.assertEqual(data['active_basis_by_period'],before['active_basis_by_period'])
        route=journal.saved['combined_history_all_years_version_repair_route.json']
        self.assertEqual(route['answer']['financial_adjudications'][0]['resolution'],'withdrawn')
        self.assertEqual({item['finding_id'] for item in result['financial_adjudications']},{o['id'] for o in data['historical_review_obligations']})

    def test_output_capacity_decomposes_once_without_reading_partial_json_or_losing_obligations(self):
        from types import SimpleNamespace
        from company_initiation.historic_construction.workflow import _combined_history_challenge, _HISTORY_GATE_TOPICS, combined_history_review_current
        from company_initiation.shared_runtime import digest
        outer=self
        for second_failure in (False,True):
            data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data['observations'])
            finding=dict(kind='financial_interpretation',topic='reporting_bases',check=facts[0]['id']+' requires explicit review.',period_ids=['2020-FY'],evidence=[dict(source_id='new',unit_id='page:1')])
            data['historical_review_obligations']=[dict(id='existing_financial',topic='reporting_bases',fiscal_years=[2020],original_finding=finding)]
            class Journal:
                provider=SimpleNamespace(max_output_tokens=16000)
                def __init__(self):self.entries=[];self.calls=[];self.saved={};self.matrix=None;self.versions=None
                def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    self.calls.append(stage)
                    if stage=='company_combined_history' or second_failure:
                        if self.matrix is None:self.matrix=copy.deepcopy(payload['historical_matrix']);self.versions=copy.deepcopy(payload['reporting_version_inventory'])
                        request=dict(stage=stage,instructions=prompt,payload=copy.deepcopy(payload),schema=copy.deepcopy(schema),attempt=0)
                        signature=digest(request);call_id='output_cap_'+str(len(self.calls))
                        self.entries.append(dict(call_id=call_id,stage=stage,request=request,signature=signature,error='Incomplete',max_output_tokens=16000,
                            response=dict(status='incomplete',incomplete_details={'reason':'max_output_tokens'},usage={'output_tokens':16000},output=[{'type':'message','content':[{'text':'unparseable partial response'}]}])))
                        raise ValueError('max_output_tokens call_id='+call_id+'; signature='+signature)
                    outer.assertEqual(payload['historical_matrix'],self.matrix);outer.assertEqual(payload['reporting_version_inventory'],self.versions)
                    response=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Cited topic check',source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']],summary='Synthetic')
                    if payload['financial_review_obligations']:
                        response['financial_adjudications']=[dict(finding_id=o['id'],outcome='resolved',detail='No incompatible active binding; cited original view is labelled.',source_refs=[dict(source_id='new',unit_id='page:1')]) for o in payload['financial_review_obligations']]
                    outer.assertEqual(assess(response),[]);return response
            journal=Journal()
            with self.subTest(second_failure=second_failure),patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda j,docs,*a,**kw:docs):
                if second_failure:
                    with self.assertRaisesRegex(ValueError,'max_output_tokens'):_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertEqual(len(journal.calls),2);self.assertNotIn('combined_history_review',data)
                else:
                    result=_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertEqual(len(journal.calls),8);self.assertEqual(len(result['checks']),6)
                    self.assertTrue(combined_history_review_current(data))
                    self.assertEqual(len(result['financial_adjudications']),1)
                failure=journal.saved['combined_history_all_years_context_failure.json']['capacity_failure']
                self.assertEqual(failure['kind'],'max_output_tokens');self.assertEqual(failure['max_output_tokens'],16000)
            self.assertEqual(data['observations'],before)

    def test_unseen_incidental_citation_is_feedback_not_evidence_acquisition(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        data,answer,facts,targets,catalog,units=self.fixture();outer=self
        units.append(dict(source_id='new',unit_id='page:2',text='Unselected original cover.',numbers=[]))
        loader=Mock(side_effect=AssertionError('An incidental citation is not an acquisition request'))
        class Journal:
            def artifact(self,*args):pass
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                result=dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited source check',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in payload['required_topics']],summary='Synthetic')
                result['checks'][0].update(status='warning',source_refs=[dict(source_id='new',unit_id='page:2')])
                failures=assess(result);outer.assertEqual([f['kind'] for f in failures],['output_contract'])
                outer.assertIsNone(repair_context(copy.deepcopy(payload),failures))
                result['checks'][0]['source_refs']=[dict(source_id='new',unit_id='page:1')]
                outer.assertEqual(assess(result),[]);return result
        with patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda j,docs,*a,**kw:[u for u in docs if u['unit_id']=='page:1']):
            _combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()),source_loader=loader)
        loader.assert_not_called()

    def test_five_lineage_allegations_recover_with_exact_calls_sources_and_persisted_artifact(self):
        from company_initiation.historic_construction.workflow import restore_history_review_obligations, _combined_history_challenge, combined_history_review_current
        from company_initiation.shared_runtime import digest
        import hashlib
        data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data);outer=self
        with tempfile.TemporaryDirectory() as temp:
            old=Path(temp)/'old';current=Path(temp)/'current';old.mkdir();current.mkdir()
            calls=[];history=[]
            for attempt,topics in enumerate([('segment_lineage','restatement_versions'),('segment_lineage','restatement_versions','source_vintage')]):
                checks=[dict(topic=topic,status='error',issue_type='missing_model_version',period_ids=['2020-FY'],
                    detail='Published alternate version '+topic+' question '+str(attempt),source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in topics]
                request=dict(stage='company_combined_history',attempt=attempt,payload=dict(requested_years=[2020],evidence=units))
                calls.append(dict(call_id='call'+str(attempt),stage='company_combined_history',repair_count=attempt,
                    request=request,signature=digest(request),result=dict(checks=checks)))
                history.append(dict(attempt=attempt,failures=[dict(kind='missing_model_version',check=c['topic']+': '+c['detail'],
                    period_ids=c['period_ids'],evidence=c['source_refs']) for c in checks]))
            routing=old/'company_combined_history_routing.json';routing.write_text(json.dumps(dict(history=history)),encoding='utf-8')
            old_record=dict(directory=str(old),configuration={'history_input_hash':digest(data)},sources=list(catalog.values()),calls=calls,
                artifacts={routing.name:hashlib.sha256(routing.read_bytes()).hexdigest()})
            previous=dict(directory=str(current),configuration=old_record['configuration'],sources=list(catalog.values()),calls=copy.deepcopy(calls),
                artifacts={},parent_run=str(old),_reuse_verified=True)
            restored=restore_history_review_obligations(previous,[old_record],data,list(catalog.values()))
            self.assertEqual(len(restored),5);self.assertEqual(data,before)
            self.assertEqual({o['provenance']['call_id'] for o in restored},{'call0','call1'})
            # A later record need not repeat the allegation in its routing.
            saved=current/'history_review_obligations.json';saved.write_text(json.dumps(restored),encoding='utf-8')
            previous['artifacts'][saved.name]=hashlib.sha256(saved.read_bytes()).hexdigest();previous.pop('parent_run')
            recovered=restore_history_review_obligations(previous,[],data,list(catalog.values()))
            self.assertEqual({o['id'] for o in recovered},{o['id'] for o in restored})
            data['historical_review_obligations']=recovered
            class Journal:
                def artifact(self,*args):pass
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    outer.assertEqual(len(payload['financial_review_obligations']),5)
                    supplied={(u['source_id'],u['unit_id']) for u in payload['evidence']}
                    outer.assertTrue(all((r['source_id'],r['unit_id']) in supplied for o in recovered for r in o['original_finding']['evidence']))
                    response=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Source-supported check',
                        source_refs=[dict(source_id='old',unit_id='page:1')]) for t in payload['required_topics']],summary='Synthetic')
                    outer.assertTrue(any('Missing explicit adjudication' in f['check'] for f in assess(response)))
                    response['financial_adjudications']=[dict(finding_id=o['id'],outcome='resolved',resolution='withdrawn',observation_ids=[],
                        detail='This synthetic allegation requested a version not asserted by the cited original; its original premise is withdrawn.',
                        source_refs=[dict(source_id='new',unit_id='page:1')]) for o in recovered]
                    outer.assertEqual(assess(response),[]);return response
            # The initial year plan includes only the old original. Mandatory
            # restored support must still enter the complete selected context.
            with patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda j,docs,*a,**kw:docs):
                _combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()),coverage=[dict(year=2020,source_ids=['old'])])
            self.assertTrue(combined_history_review_current(data));self.assertEqual(data['observations'],before['observations'])
            altered=copy.deepcopy(previous);altered['calls'][0]['request']['payload']['evidence']=[]
            with self.assertRaisesRegex(ValueError,'not bound'):restore_history_review_obligations(altered,[],before,list(catalog.values()))
            changed=copy.deepcopy(list(catalog.values()));changed[1]['sha256']='changed'
            with self.assertRaisesRegex(ValueError,'incompatible'):restore_history_review_obligations(previous,[],before,changed)
            saved.write_text('[]',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'artifact changed'):restore_history_review_obligations(previous,[],before,list(catalog.values()))

    def test_version_disposition_requires_real_scoped_observations_and_checked_repair(self):
        from company_initiation.historic_construction.workflow import _history_version_disposition_failure
        data,answer,facts,targets,catalog,units=self.fixture()
        obligation=dict(fiscal_years=[2020],original_finding=dict(kind='missing_model_version',period_ids=['2020-FY']))
        item=dict(outcome='resolved',resolution='already_preserved',observation_ids=[facts[0]['id']])
        self.assertIsNone(_history_version_disposition_failure(item,obligation,data))
        for changed,message in [(dict(resolution=None),'explicitly'),(dict(observation_ids=['invented']),'unknown'),
            (dict(observation_ids=[]),'eligible'),(dict(resolution='repaired'),'independently checked')]:
            self.assertIn(message,_history_version_disposition_failure(dict(item,**changed),obligation,data))
        outside=copy.deepcopy(data);outside['observations'][0]['period_id']='2021-FY'
        self.assertIn('outside',_history_version_disposition_failure(item,obligation,outside))
        obligation['original_finding']['period_ids'].append('2020-H1')
        self.assertIn('every affected period',_history_version_disposition_failure(item,obligation,data))

    def test_new_version_and_financial_findings_survive_retry_without_generic_pass(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, combined_history_review_current
        data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data);outer=self
        class Journal:
            def __init__(self):self.saved={}
            def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                response=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Cited check',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']],summary='Synthetic')
                next(c for c in response['checks'] if c['topic']=='restatement_versions').update(status='error',issue_type='missing_model_version',period_ids=['2020-FY'],detail='Absent published version alleged.')
                next(c for c in response['checks'] if c['topic']=='reporting_bases').update(status='error',issue_type='financial_interpretation',period_ids=['2020-FY'],detail=facts[0]['id']+' concrete active binding alleged incompatible.')
                failures=assess(response);outer.assertEqual(len(self.saved['history_review_obligations.json']),2)
                active=repair_context(copy.deepcopy(payload),failures)
                outer.assertEqual(len(active['financial_review_obligations']),2)
                outer.assertIn('financial_adjudications',schema['required'])
                for check in response['checks']:check.update(status='pass',issue_type='none')
                outer.assertTrue(any('Missing explicit adjudication' in f['check'] for f in assess(response)))
                response['financial_adjudications']=[dict(finding_id=o['id'],outcome='resolved',resolution='withdrawn' if o['original_finding']['kind']=='missing_model_version' else 'financial_resolution',
                    observation_ids=[],detail='The cited original explicitly supports a labelled original view; the synthetic allegation is withdrawn with no binding change.',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for o in active['financial_review_obligations']]
                outer.assertEqual(assess(response),[]);return response
        _combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()))
        self.assertTrue(combined_history_review_current(data));self.assertEqual(data['observations'],before['observations'])
        self.assertEqual(data['active_basis_by_period'],before['active_basis_by_period'])

    def test_impossible_citations_get_contract_feedback_without_source_expansion(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        data,answer,facts,targets,catalog,units=self.fixture();outer=self
        loader=Mock(side_effect=AssertionError('Impossible citation must not acquire originals'))
        class Journal:
            def artifact(self,*args):pass
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                result=dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited check',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in payload['required_topics']],summary='Synthetic')
                for ref in (dict(source_id='new',unit_id='page:99'),dict(source_id='new',unit_id='catalog_entry:restatement'),
                            dict(source_id='not_in_catalog',unit_id='page:1')):
                    result['checks'][0]['source_refs']=[ref]
                    failures=assess(result)
                    outer.assertEqual(failures[0]['kind'],'output_contract')
                    outer.assertIn('available_unit_ids',failures[0]['check'])
                    outer.assertIsNone(repair_context(copy.deepcopy(payload),failures))
                result['checks'][0]['source_refs']=[dict(source_id='new',unit_id='page:1')]
                outer.assertEqual(assess(result),[]);return result
        _combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()),source_loader=loader)
        loader.assert_not_called()

    def test_known_omitted_unit_expands_but_impossible_citation_is_not_sent_to_loader(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        data,answer,facts,targets,catalog,units=self.fixture();outer=self
        extra=dict(source_id='new',unit_id='page:2',text='Complete omitted statement note.',numbers=[])
        units=units+[extra];calls=[]
        def loader(findings):
            calls.append(copy.deepcopy(findings));return []
        class Journal:
            def artifact(self,*args):pass
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                result=dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited check',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in payload['required_topics']],summary='Synthetic')
                result['checks'][0]['source_refs']=[dict(source_id='new',unit_id='page:2')]
                result['checks'][0].update(status='error',issue_type='context_omission')
                result['checks'][1]['source_refs']=[dict(source_id='new',unit_id='page:99')]
                failures=assess(result);outer.assertEqual([f['kind'] for f in failures],['context_omission','output_contract'])
                repaired=repair_context(copy.deepcopy(payload),failures)
                outer.assertEqual(len(calls),1);outer.assertEqual(len(calls[0]),1)
                outer.assertEqual(calls[0][0]['evidence'],[dict(source_id='new',unit_id='page:2')])
                outer.assertIn(extra,repaired['evidence'])
                result['checks'][1]['source_refs']=[dict(source_id='new',unit_id='page:1')]
                result['checks'][0].update(status='pass',issue_type='none')
                outer.assertEqual(assess(result),[]);return result
        def select(journal,documents,purpose,**kwargs):
            return documents if 'context repair' in purpose else [u for u in documents if u['unit_id']!='page:2']
        with patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=select):
            _combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()),source_loader=loader)

    def test_one_topic_recovery_keeps_every_record_version_and_financial_obligation(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, _HISTORY_GATE_TOPICS, combined_history_review_current
        outer=self
        for outcome in ('resolved','unresolved','context_failure'):
            data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data)
            units=[dict(source_id='new',unit_id='page:'+str(i+1),text=topic+' complete original section 107.',
                numbers=[dict(index=0,raw='107',value=107,start=0,end=3)]) for i,topic in enumerate(_HISTORY_GATE_TOPICS)]
            class Journal:
                def __init__(self):self.calls=[];self.artifacts={};self.matrix=None;self.versions=None
                def artifact(self,name,value):self.artifacts[name]=copy.deepcopy(value)
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    self.calls.append(stage)
                    response=dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited primary review',
                        source_refs=[dict(source_id='new',unit_id='page:'+str(_HISTORY_GATE_TOPICS.index(topic)+1))]) for topic in payload['required_topics']],summary='Synthetic')
                    if stage=='company_combined_history':
                        self.matrix=copy.deepcopy(payload['historical_matrix']);self.versions=copy.deepcopy(payload['reporting_version_inventory'])
                        response['checks'][1].update(status='error',issue_type='financial_interpretation',detail=facts[0]['id']+' concrete selected CFO basis concern',period_ids=['2020-FY'])
                        assess(response);raise ValueError('HTTP 400 context_length_exceeded: recorded synthetic provider failure')
                    outer.assertEqual(payload['historical_matrix'],self.matrix)
                    outer.assertEqual(payload['reporting_version_inventory'],self.versions)
                    if outcome=='context_failure':raise ValueError('context_length_exceeded: further topic cannot fit')
                    for unit in payload['evidence']:
                        numbers=unit['numbers'];decoded=[dict(zip(numbers['columns'],row)) for row in numbers['rows']]
                        outer.assertEqual(dict(unit,numbers=decoded),next(u for u in units if u['unit_id']==unit['unit_id']))
                    obligations=payload.get('financial_review_obligations',[])
                    if obligations:
                        response['financial_adjudications']=[dict(finding_id=item['id'],outcome=outcome,
                            detail='Source-supported resolution.' if outcome=='resolved' else 'Concrete selected binding still conflicts.',
                            source_refs=[dict(source_id='new',unit_id='page:2')]) for item in obligations]
                    assess(response);return response
            def select(journal,documents,purpose,**kwargs):
                if not purpose.startswith('Bounded recovery'):return documents
                topic=next(topic for topic in _HISTORY_GATE_TOPICS if 'Review ONLY '+topic+' ' in purpose)
                return [unit for unit in documents if unit['text'].startswith(topic+' ')]
            journal=Journal()
            with self.subTest(outcome=outcome),patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=select):
                if outcome=='resolved':
                    result=_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertTrue(combined_history_review_current(data));self.assertEqual(len(result['checks']),6)
                    self.assertEqual(len(journal.calls),8)
                    self.assertTrue(journal.calls[-1].endswith('_topic_synthesis'))
                    coverage=journal.artifacts['combined_history_all_years_topic_coverage.json']['topics']
                    self.assertEqual({item['topic'] for item in coverage},set(_HISTORY_GATE_TOPICS))
                    self.assertTrue(all(len(item['selected_units'])==1 and len(item['available_but_not_selected'])==5 for item in coverage))
                elif outcome=='unresolved':
                    with self.assertRaisesRegex(ValueError,'remains incomplete'):_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertEqual(len(journal.calls),3);self.assertNotIn('combined_history_review',data)
                else:
                    with self.assertRaisesRegex(ValueError,'context_length_exceeded'):_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertEqual(len(journal.calls),2);self.assertNotIn('combined_history_review',data)
            self.assertEqual(data['observations'],before['observations']);self.assertEqual(data['historical'],before['historical'])
            self.assertEqual(data['active_basis_by_period'],before['active_basis_by_period'])

    def test_topic_recovery_cannot_omit_version_gap_and_unresolved_gap_keeps_repair_route(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        outer=self
        for disposition in ('omitted','unresolved','evidence_pending'):
            data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data)
            class Journal:
                configuration={'limits':{'repairs':1}}
                def artifact(self,*args):pass
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    result=dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Source-backed check',
                        source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in payload['required_topics']],summary='Synthetic')
                    if stage=='company_combined_history':
                        next(check for check in result['checks'] if check['topic']=='restatement_versions').update(
                            status='error',issue_type='missing_model_version',detail='Published CFO version is absent from saved observations.',period_ids=['2020-FY'])
                        next(check for check in result['checks'] if check['topic']=='cross_year_bridges').update(
                            status='error',issue_type='missing_primary_evidence' if disposition=='evidence_pending' else 'financial_interpretation',
                            detail=facts[0]['id']+' requires an absent primary bridge.' if disposition=='evidence_pending' else facts[0]['id']+' is alleged to use an incompatible selected bridge.',period_ids=['2020-FY'])
                        assess(result);raise ValueError('context_length_exceeded: preserved synthetic request')
                    obligations=payload['financial_review_obligations']
                    if obligations and disposition in ('unresolved','evidence_pending'):
                        outer.assertEqual(obligations[0]['original_finding']['kind'],'missing_model_version')
                        result['financial_adjudications']=[dict(finding_id=item['id'],outcome='unresolved',detail='Version is still absent.',
                            resolution='unresolved',observation_ids=[],
                            source_refs=[dict(source_id='new',unit_id='page:1')]) for item in obligations]
                    assess(result);return result
            with self.subTest(disposition=disposition),patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda j,docs,*a,**kw:docs),patch(
                    'company_initiation.historic_construction.workflow._repair_historical_versions',side_effect=ValueError('Bounded version repair reached')) as revision:
                expected=('remains incomplete' if disposition=='omitted' else 'must be adjudicated before historical-version repair'
                    if disposition=='evidence_pending' else 'Bounded version repair reached')
                with self.assertRaisesRegex(ValueError,expected):
                    _combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()))
                if disposition in ('omitted','evidence_pending'):revision.assert_not_called()
                else:
                    revision.assert_called_once()
                    self.assertEqual(revision.call_args.args[3].findings[0]['kind'],'missing_model_version')
                    self.assertTrue(any(finding['kind']=='financial_interpretation' for finding in revision.call_args.args[3].findings))
            self.assertEqual(data['observations'],before['observations']);self.assertNotIn('combined_history_review',data)

    def test_current_topic_resolved_context_allows_remaining_version_repair(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data['observations'])
        context_finding=dict(id='saved_context_gap',topic='restatement_versions',fiscal_years=[2020],
            original_finding=dict(kind='context_omission',topic='restatement_versions',period_ids=['2020-FY'],
                check='Restatement note needed.',evidence=[dict(source_id='new',unit_id='page:1')]))
        data['historical_version_revisions']=[dict(preserved_financial_findings=[context_finding])]
        outer=self
        class Journal:
            configuration={'limits':{'repairs':1}}
            def artifact(self,*args):pass
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                result=dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited check',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in payload['required_topics']],summary='Synthetic')
                initial=stage=='company_combined_history'
                if initial:
                    next(check for check in result['checks'] if check['topic']=='restatement_versions').update(
                        status='error',issue_type='missing_model_version',period_ids=['2020-FY'],detail='Published CFO version is absent.')
                obligations=payload['financial_review_obligations']
                if obligations:
                    result['financial_adjudications']=[dict(finding_id=item['id'],
                        outcome='unresolved' if initial or item['original_finding']['kind']=='missing_model_version' else 'resolved',
                        resolution='unresolved' if initial or item['original_finding']['kind']=='missing_model_version' else 'financial_resolution',observation_ids=[],
                        detail='Version still needs binding.' if item['original_finding']['kind']=='missing_model_version' else 'Required complete original note is now supplied and reviewed.',
                        source_refs=[dict(source_id='new',unit_id='page:1')]) for item in obligations]
                failures=assess(result)
                if initial:raise ValueError('context_length_exceeded: synthetic recorded limit')
                if obligations:
                    outer.assertTrue(any(item['outcome']=='resolved' for item in result['financial_adjudications']))
                    outer.assertTrue(all(item['kind']=='missing_model_version' for item in failures))
                return result
        with patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda j,docs,*a,**kw:docs),patch(
                'company_initiation.historic_construction.workflow._repair_historical_versions',side_effect=ValueError('Bounded version repair reached')) as revision:
            with self.assertRaisesRegex(ValueError,'Bounded version repair reached'):
                _combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()))
            revision.assert_called_once()
            self.assertTrue(all(item['kind']=='missing_model_version' for item in revision.call_args.args[3].findings))
        self.assertEqual(data['observations'],before);self.assertNotIn('combined_history_review',data)

    """Synthetic primary disclosures, with independently specified restatements."""

    def fixture(self, *, signed=True):
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        from company_initiation.historic_construction.workflow import _materialize_financial_observations
        period=dict(id='2020-FY',fiscal_year=2020,kind='FY',start='2020-01-01',end='2020-12-31')
        original=dict(id='old',category='financial_reports',published_at='2021-02-15',publication_evidence='15 February 2021',sha256='oldhash')
        revised=dict(id='new',category='financial_reports',published_at='2022-02-15',publication_evidence='15 February 2022',sha256='newhash')
        units=[dict(source_id='old',unit_id='page:1',text='2020 operating cash flow 100.0; original statement.',numbers=[dict(raw='100.0',index=0)]),
            dict(source_id='new',unit_id='page:1',text='2020 restated operating cash flow 107.0. Published adjustments +10.0 and -3.0.' if signed else '2020 restated operating cash flow 110.0. No numerical reconciliation disclosed.',
                numbers=[dict(raw=raw,index=i) for i,raw in enumerate(('107.0','10.0','-3.0') if signed else ('110.0',))])]
        catalog={s['id']:s for s in (original,revised)};store=SourceStore(Path('.'));store.sources=list(catalog.values())
        for unit in units:store._units.setdefault(unit['source_id'],{})[unit['unit_id']]=unit
        def entry(source,index,role='cfo',restated=False):
            return dict(row_id=role,label='Operating cash flow' if role=='cfo' else 'Disclosed '+role,period_id='2020-FY',unit='EURm',metric_type='flow',
                entity_id='group',basis='reported',definition_id=role,scope='consolidated',
                terms=[dict(reference=dict(source_id=source,unit_id='page:1',number_index=index,number_format='dot_decimal'),
                    source_raw=store._units[source]['page:1']['numbers'][index]['raw'],multiplier=1,weight=1)],
                rounding_increment=.1,restatement='restated' if restated else 'original',restatement_vintage='2022 published revision' if restated else None,
                classification_basis='Explicit original/restated statement heading.',classification_source_refs=[dict(source_id=source,unit_id='page:1')])
        entries=[entry('old',0),entry('new',0,restated=True)]
        if signed:entries.extend([entry('new',1,'history_adjustment_policy',True),entry('new',2,'history_adjustment_scope',True)])
        answer=dict(observations=entries,reporting_changes=[],gaps=[],metadata_amendments=[],bridges=[],comparability_breaks=[])
        link=dict(before_index=0,after_index=1,definition='Published revised statement with disclosed change in policy.',source_refs=[dict(source_id='new',unit_id='page:1')])
        if signed:answer['bridges']=[dict(link,adjustment_indexes=[2,3])]
        else:answer['comparability_breaks']=[link]
        facts=_materialize_financial_observations(answer,store=store,catalog=catalog,periods=[period],currency='EUR',
            roles=integrated_role_contract(),segments=[],evidence=units,primary_only=True)
        data=dict(company='SYNTHETIC reporting revision',currency='EUR',history_years=[2020],periods=[period],segments=[],
            model_configuration={},historical={'cfo':{'2020':100}},active_basis_by_period={'2020-FY':{'group':'reported'}},
            sources={'old':original},observations=[copy.deepcopy(facts[0])],entity_versions=[],reporting_changes=[],reporting_bridges=[])
        targets=[dict(row_id='cfo',period_id='2020-FY',existing_observation_ids=[facts[0]['id']],definition='Missing published revision',
            source_refs=[dict(source_id='new',unit_id='page:1')])]
        return data,answer,facts,targets,catalog,units

    def merge(self,fixture):
        from company_initiation.historic_construction.workflow import _merge_historical_version_revision
        data,answer,facts,targets,catalog,units=fixture
        return _merge_historical_version_revision(data,answer,facts,targets=targets,catalog=catalog,evidence=units,revision=1)

    def test_signed_known_answer_preserves_original_and_active_inputs(self):
        fixture=self.fixture();before=copy.deepcopy(fixture[0]);updated,audit=self.merge(fixture)
        self.assertEqual(fixture[0],before);self.assertEqual(updated['observations'][0],before['observations'][0])
        self.assertEqual(updated['historical'],before['historical']);self.assertEqual(updated['active_basis_by_period'],before['active_basis_by_period'])
        self.assertEqual(len(updated['observations']),4)
        bridge=updated['reporting_bridges'][0]
        self.assertEqual(bridge['amounts'],dict(original=100,signed_adjustments=7,restated=107));self.assertEqual(bridge['residual'],0)
        self.assertTrue(all(o['model_selection_eligible'] is False for o in updated['observations'][1:]))
        self.assertTrue(audit['active_basis_unchanged']);self.assertTrue(audit['annual_model_inputs_unchanged'])

    def test_complete_inventory_retains_110_restated_facts_outside_original_selected_view(self):
        from company_initiation.historic_construction.workflow import _history_version_inventory
        data,answer,facts,targets,catalog,units=self.fixture();before=copy.deepcopy(data)
        restated=[]
        for entity,count in [('division_a',16),('division_b',16),('division_c',16),('division_d',16),('division_e',16),('group',16),('corporate',14)]:
            for index in range(count):
                restated.append(dict(facts[1],id=entity+'_'+str(index),entity_id=entity,basis='later_published_basis',
                    row_id=entity+'_metric_'+str(index),period_id=('2020-FY','2020-H1','2020-Q1','2020-9M')[index%4]))
        inventory=_history_version_inventory(data['observations']+restated)
        versions=[item for item in inventory if item['restatement']=='restated']
        self.assertEqual(sum(item['observation_count'] for item in versions),110)
        self.assertEqual({period for item in versions for period in item['period_ids']},{'2020-FY','2020-H1','2020-Q1','2020-9M'})
        self.assertEqual({item['entity_id']:item['observation_count'] for item in versions},
            dict(division_a=16,division_b=16,division_c=16,division_d=16,division_e=16,group=16,corporate=14))
        self.assertEqual(data,before);self.assertEqual(data['active_basis_by_period']['2020-FY']['group'],'reported')
        self.assertEqual(data['historical']['cfo']['2020'],100)

    def test_complete_repair_matrix_round_trip_preserves_all_fields_and_numeric_bindings(self):
        from company_initiation.historic_construction.workflow import _history_review_matrix
        data,answer,facts,targets,catalog,units=self.fixture()
        observations=copy.deepcopy(facts)
        observations[0]['explicitly_unknown']=None
        observations[1]['extra_provenance']={'arithmetic':['disclosed',107], 'source_refs':copy.deepcopy(observations[1]['source_refs'])}
        before=copy.deepcopy(observations)
        packed=_history_review_matrix(observations,complete_records=True);decoded={}
        for series in packed['series']:
            metadata={field:packed['dictionaries'][field][series['metadata'][i]] for i,field in enumerate(packed['metadata_fields']) if series['metadata'][i] is not None}
            for oid,period_index,value in series['points']:
                decoded[oid]=dict(metadata,**packed['periods'][period_index],id=oid,value=value)
        self.assertEqual(decoded,{item['id']:item for item in before})
        self.assertEqual(observations,before)
        self.assertIn('source_refs',packed['metadata_fields'])
        self.assertIn('explicitly_unknown',decoded[observations[0]['id']])
        self.assertNotIn('explicitly_unknown',decoded[observations[1]['id']])

    def test_synthesis_retains_disjoint_adjudication_section_and_surrounding_context(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, combined_history_review_current
        data,answer,facts,targets,catalog,units=self.fixture();data['history_years']=[2019,2020,2021]
        units=[dict(source_id='old',unit_id='page:'+str(page),text='Verbatim primary context '+str(page),numbers=[]) for page in range(1,5)]
        selected=[unit for unit in units if unit['unit_id']!='page:2']
        obligation=dict(id='financial_binding',topic='reporting_bases',fiscal_years=[2020],
            original_finding=dict(kind='financial_interpretation',period_ids=['2020-FY'],check='Concrete selected binding '+facts[0]['id']))
        data['historical_version_revisions']=[dict(preserved_financial_findings=[obligation])]
        outer=self
        class Journal:
            def __init__(self):self.calls=[]
            def artifact(self,*args):pass
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                self.calls.append(stage)
                if '_synthesis' in stage:
                    outer.assertEqual(payload['evidence'],selected)
                if stage=='company_combined_history_synthesis':
                    raise ValueError('context_length_exceeded: synthetic bounded-topic test')
                result=dict(checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited source check',
                    source_refs=[dict(source_id='old',unit_id='page:1')]) for topic in payload['required_topics']],summary='Synthetic source review')
                if payload['financial_review_obligations']:
                    result['financial_adjudications']=[dict(finding_id='financial_binding',outcome='resolved',
                        detail='Separate primary definition resolves the saved binding concern.',source_refs=[dict(source_id='old',unit_id='page:3')])]
                outer.assertEqual(assess(result),[]);return result
        journal=Journal()
        with patch('company_initiation.historic_construction.workflow.construction_evidence',return_value=selected):
            result=_combined_history_challenge(journal,data,units)
        self.assertTrue(combined_history_review_current(data))
        self.assertEqual(result['financial_adjudications'][0]['finding_id'],'financial_binding')
        self.assertEqual(len([stage for stage in journal.calls if '_synthesis_' in stage]),6)

    def test_mixed_findings_repair_only_missing_version_and_require_financial_adjudication(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, combined_history_review_current
        outer=self
        for outcome in ('resolved','unresolved','omitted'):
            data,answer,facts,targets,catalog,units=self.fixture();original=copy.deepcopy(data)
            class Journal:
                configuration={'limits':{'repairs':1}}
                def __init__(self):self.calls=[];self.artifacts={};self.reviews=0
                def artifact(self,name,value):self.artifacts[name]=copy.deepcopy(value)
                def stage(self,stage,prompt,payload,schema,validate):
                    self.calls.append(stage)
                    if stage.endswith('_scope'):
                        outer.assertEqual([item['kind'] for item in payload['findings']],['missing_model_version'])
                        response=outer.scope_answer(payload,targets)
                    elif stage.endswith('_mapping'):response=answer
                    elif stage.endswith('_independent'):response={key:copy.deepcopy(answer[key]) for key in ('observations','reporting_changes','gaps')}
                    else:raise AssertionError(stage)
                    return validate(copy.deepcopy(response))
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    self.reviews+=1
                    outer.assertIn('NOT absent from retained history',prompt)
                    checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Synthetic source check',
                        source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in payload['required_topics']]
                    response=dict(checks=checks,summary='Synthetic repeated gate')
                    if self.reviews==1:
                        next(item for item in checks if item['topic']=='reporting_bases').update(status='error',issue_type='financial_interpretation',
                            period_ids=['2020-FY'],detail='Selected cfo 2020-FY '+facts[0]['id']+' is alleged to require a comparable basis; this needs explicit adjudication.')
                        next(item for item in checks if item['topic']=='restatement_versions').update(status='error',issue_type='missing_model_version',
                            period_ids=['2020-FY'],detail='Published revised CFO is absent from retained observations.')
                    else:
                        outer.assertEqual(len(payload['financial_review_obligations']),2)
                        outer.assertEqual(data['historical'],original['historical'])
                        if outcome!='omitted':
                            response['financial_adjudications']=[dict(finding_id=item['id'],outcome='resolved' if item['original_finding']['kind']=='missing_model_version' else outcome,
                                resolution='repaired' if item['original_finding']['kind']=='missing_model_version' else 'financial_resolution',
                                observation_ids=[facts[1]['id']] if item['original_finding']['kind']=='missing_model_version' else [],
                                detail='The exact published CFO version is now retained.' if item['original_finding']['kind']=='missing_model_version' else
                                    'The original selected view is explicitly labelled and no common-basis calculation was supplied.' if outcome=='resolved' else 'A concrete incompatible calculation still requires correction.',
                                source_refs=[dict(source_id='old',unit_id='page:1'),dict(source_id='new',unit_id='page:1')]) for item in payload['financial_review_obligations']]
                    assess(response);return response
            journal=Journal()
            with self.subTest(outcome=outcome):
                if outcome=='resolved':
                    result=_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertTrue(combined_history_review_current(data));self.assertEqual(result['financial_adjudications'][0]['outcome'],'resolved')
                    data['combined_history_review']['financial_adjudications']=[]
                    self.assertFalse(combined_history_review_current(data))
                else:
                    with self.assertRaisesRegex(ValueError,'remains incomplete'):
                        _combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
                    self.assertNotIn('combined_history_review',data)
                self.assertEqual(journal.reviews,2)
                self.assertEqual(len(data['observations']),4)
                self.assertEqual(data['observations'][0],original['observations'][0])
                self.assertEqual(data['active_basis_by_period'],original['active_basis_by_period'])
                audit=journal.artifacts['history_revision_1_audit.json']
                self.assertEqual(len(audit['preserved_financial_findings']),1)
                self.assertEqual(audit['preserved_financial_findings'][0]['original_finding']['kind'],'financial_interpretation')
                self.assertEqual(journal.calls,['company_history_revision_scope','company_history_revision_mapping','company_history_revision_independent'])

    def test_blanket_different_basis_claim_is_output_contract_not_financial_proof(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        data,answer,facts,targets,catalog,units=self.fixture();outer=self
        class Journal:
            def artifact(self,*args):pass
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited synthetic check',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in payload['required_topics']]
                checks[0].update(status='error',issue_type='financial_interpretation',detail='Adjacent original bases differ; always replace them with the latest restatement.')
                response=dict(checks=checks,summary='Unsupported general claim')
                failures=assess(response);outer.assertEqual(failures[0]['kind'],'output_contract')
                outer.assertIn('exact saved observation ID',failures[0]['check'])
                return response
        with self.assertRaisesRegex(ValueError,'remains incomplete'):_combined_history_challenge(Journal(),data,units)

    def test_publication_rubric_distinguishes_limitations_without_overriding_verdicts(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge
        outer=self
        for issue in ('none','context_omission'):
            data,answer,facts,targets,catalog,units=self.fixture();data['sources']['old']['published_at']=None
            class Journal:
                def artifact(self,*args):pass
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    outer.assertIn('exact absent source/unit',prompt)
                    outer.assertIn('exact affected saved observation and concrete supplied point-in-time/calibration claim',prompt)
                    outer.assertIn('Do not infer either eligibility or exclusion from missing eligibility metadata',prompt)
                    checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited synthetic check',
                        source_refs=[dict(source_id='old',unit_id='page:1')]) for topic in payload['required_topics']]
                    next(item for item in checks if item['topic']=='source_vintage').update(status='warning',issue_type=issue,
                        detail='Original publication availability remains unknown; no point-in-time claim is made.')
                    result=dict(checks=checks,summary='Synthetic availability review')
                    failures=assess(result)
                    outer.assertEqual([item['kind'] for item in failures],[] if issue=='none' else ['output_contract'])
                    return result
            with self.subTest(issue_type=issue):
                if issue=='none':
                    result=_combined_history_challenge(Journal(),data,units)
                    self.assertEqual(next(item for item in result['checks'] if item['topic']=='source_vintage')['status'],'warning')
                else:
                    with self.assertRaisesRegex(ValueError,'remains incomplete'):_combined_history_challenge(Journal(),data,units)
                    self.assertNotIn('combined_history_review',data)

    def test_unbridged_published_versions_preserved_without_invented_delta(self):
        fixture=self.fixture(signed=False);updated,_=self.merge(fixture)
        self.assertEqual([o['value'] for o in updated['observations']],[100,110])
        link=updated['reporting_bridges'][0]
        self.assertEqual(link['status'],'unbridged_published_versions')
        for key in ('adjustments','residual','amounts','rounding_tolerance'):self.assertNotIn(key,link)
        new=updated['observations'][1]
        self.assertFalse(new['model_selection_eligible']);self.assertFalse(new['calibration_eligible']);self.assertFalse(new['cross_basis_comparable'])

    def test_restatement_bridge_rejects_balanced_endpoint_subtraction(self):
        fixture=self.fixture();facts=fixture[2]
        facts[2]['source_refs']=copy.deepcopy(facts[1]['source_refs'])+copy.deepcopy(facts[0]['source_refs'])
        facts[2]['source_refs'][1]['contribution_weight']=-1;facts[2]['value']=7
        fixture[1]['bridges'][0]['adjustment_indexes']=[2]
        fixture[1]['observations'].pop();facts.pop()
        with self.assertRaisesRegex(ValueError,'separately disclosed component tokens'):self.merge(fixture)

    def test_unreconciled_signed_adjustments_and_conflicting_old_values_reject(self):
        fixture=self.fixture();fixture[2][2]['value']=14
        with self.assertRaisesRegex(ValueError,'does not reconcile'):self.merge(fixture)
        fixture=self.fixture();fixture[0]['observations'][0]['value']=99
        with self.assertRaisesRegex(ValueError,'conflicts with a preserved reporting version'):self.merge(fixture)

    def test_blind_numeric_disagreement_and_no_progress_remain_incomplete(self):
        from company_initiation.historic_construction.workflow import _history_revision_equivalence
        data,answer,facts,targets,catalog,units=self.fixture();independent=copy.deepcopy(facts)
        independent[1]['value']=109
        class Journal:
            def artifact(self,*args):pass
            def stage(self,*args,**kwargs):raise AssertionError('Interpretation cannot override numeric mismatch')
        with self.assertRaisesRegex(ValueError,'independent numeric support'):
            _history_revision_equivalence(Journal(),facts,independent,units,revision=1)
        updated,_=self.merge((data,answer,facts,targets,catalog,units))
        with self.assertRaisesRegex(ValueError,'no supported progress'):
            self.merge((updated,answer,facts,targets,catalog,units))

    def test_semantic_revision_compaction_preserves_independent_records_and_original_units(self):
        from company_initiation.historic_construction.workflow import _history_revision_equivalence
        data,answer,facts,targets,catalog,units=self.fixture()
        candidates=[copy.deepcopy(facts[0])];independent=[dict(copy.deepcopy(facts[0]),id='blind_original',definition_id='independent_cash_definition')]
        before=copy.deepcopy((candidates,independent,units));outer=self
        class Journal:
            def artifact(self,*args):pass
            def stage(self,stage,prompt,payload,schema,validate):
                outer.assertEqual(stage,'company_history_revision_equivalence')
                outer.assertEqual(payload['candidates'],before[0]);outer.assertEqual(payload['independent'],before[1])
                restored=copy.deepcopy(payload['evidence'])
                for unit in restored:
                    if isinstance(unit['numbers'],dict):unit['numbers']=[dict(zip(unit['numbers']['columns'],row)) for row in unit['numbers']['rows']]
                outer.assertEqual(restored,before[2]);outer.assertIn('token_columns_v1',prompt)
                return validate(dict(decisions=[dict(candidate_id=candidates[0]['id'],independent_id='blind_original',equivalent=True,
                    method='Both independent names denote the same source operating cash flow.',source_refs=[dict(source_id='old',unit_id='page:1')])]))
        comparison=_history_revision_equivalence(Journal(),candidates,independent,units,revision=1)
        self.assertEqual(comparison[0]['status'],'semantic_review')
        self.assertEqual((candidates,independent,units),before)

    def test_metadata_enrichment_never_changes_eligibility_or_source_binding(self):
        fixture=self.fixture(signed=False);data,answer,facts,targets,catalog,units=fixture
        old=copy.deepcopy(facts[1]);old.update(id='preserved_restated',restatement_vintage=None,source_vintage=[],eligible=False)
        data['observations']=[old];targets[0]['existing_observation_ids']=[old['id']]
        answer.update(observations=[answer['observations'][1]],comparability_breaks=[],
            metadata_amendments=[dict(observation_id=old['id'],candidate_index=0,reason='Missing cited revision vintage',source_refs=[dict(source_id='new',unit_id='page:1')])])
        fixture=(data,answer,[facts[1]],targets,catalog,units);updated,audit=self.merge(fixture)
        self.assertEqual(updated['observations'][0]['restatement_vintage'],'2022 published revision')
        self.assertFalse(updated['observations'][0]['eligible']);self.assertEqual(updated['observations'][0]['source_refs'],old['source_refs'])
        self.assertEqual(audit['metadata_amendments'][0]['before'],old)

    def test_blind_revision_has_no_candidate_metadata_and_saved_before_comparison(self):
        from company_initiation.historic_construction.workflow import _repair_historical_versions, _HistoricalVersionGap
        from company_initiation.shared_runtime import digest
        data,answer,facts,targets,catalog,units=self.fixture()
        data.pop('periods')  # Preserved real inputs store dates on observations.
        original_data=copy.deepcopy(data);original_units=copy.deepcopy(units)
        gap=_HistoricalVersionGap(dict(requested_years=[2020],evidence=units),[dict(kind='missing_model_version',check='Missing restated CFO',evidence=[dict(source_id='new',unit_id='page:1')])])
        outer=self
        class Journal:
            def __init__(self):self.artifacts={};self.calls=[]
            def artifact(self,name,value):self.artifacts[name]=copy.deepcopy(value)
            def stage(self,stage,prompt,payload,schema,validate):
                self.calls.append(stage)
                unpacked=copy.deepcopy(payload['evidence'])
                for unit in unpacked:
                    if isinstance(unit['numbers'],dict):unit['numbers']=[dict(zip(unit['numbers']['columns'],row)) for row in unit['numbers']['rows']]
                outer.assertEqual(unpacked,original_units)
                outer.assertIn('token_columns_v1',prompt)
                raw_payload=dict(payload,evidence=original_units)
                outer.assertNotEqual(digest(dict(stage=stage,prompt=prompt,payload=payload,schema=schema)),
                    digest(dict(stage=stage,prompt=prompt,payload=raw_payload,schema=schema)))
                if stage.endswith('_scope'):
                    outer.assertNotIn('existing_observations',payload)
                    outer.assertEqual(payload['historical_matrix']['observation_count'],len(original_data['observations']))
                    outer.assertIn('source_refs',payload['historical_matrix']['metadata_fields'])
                    response=outer.scope_answer(payload,targets)
                elif stage.endswith('_mapping'):
                    outer.assertEqual(payload['existing_observations'],original_data['observations'])
                    response=answer
                elif stage.endswith('_independent'):
                    outer.assertIn('history_revision_1_candidate.json',self.artifacts)
                    outer.assertEqual(set(payload),{'revision','requested_concepts','periods','evidence'})
                    for concept in payload['requested_concepts']:
                        outer.assertEqual(set(concept),{'row_id','period_id','unit','label'})
                    response={key:copy.deepcopy(answer[key]) for key in ('observations','reporting_changes','gaps')}
                else:raise AssertionError('Unexpected semantic stage: '+stage)
                return validate(copy.deepcopy(response))
        journal=Journal();updated,audit=_repair_historical_versions(journal,data,units,gap,catalog=catalog,revision=1)
        self.assertEqual(updated['observations'][1]['value'],107)
        self.assertIn('history_revision_1_independent.json',journal.artifacts)
        self.assertIn('history_revision_1_comparison.json',journal.artifacts)
        self.assertEqual(audit['affected_years'],[2020])
        self.assertEqual(data,original_data);self.assertEqual(units,original_units)
        self.assertEqual(journal.calls,['company_history_revision_scope','company_history_revision_mapping','company_history_revision_independent'])

    def test_primary_absent_never_dispatches_version_reconstruction(self):
        from company_initiation.historic_construction.workflow import _repair_historical_versions, _HistoricalVersionGap
        data,answer,facts,targets,catalog,units=self.fixture()
        class Journal:
            def stage(self,*args,**kwargs):raise AssertionError('No repair request permitted')
        for kind in ('missing_primary_evidence','context_omission','financial_interpretation'):
            gap=_HistoricalVersionGap(dict(requested_years=[2020],evidence=units),[dict(kind=kind,evidence=[dict(source_id='new',unit_id='page:1')])])
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'cannot substitute'):
                _repair_historical_versions(Journal(),data,units,gap,catalog=catalog,revision=1)
            if kind!='financial_interpretation':
                gap.findings.append(dict(kind='missing_model_version',evidence=[dict(source_id='new',unit_id='page:1')]))
                with self.subTest(mixed_blocker=kind),self.assertRaisesRegex(ValueError,'cannot substitute'):
                    _repair_historical_versions(Journal(),data,units,gap,catalog=catalog,revision=1)

    def test_temporal_metadata_correction_preserves_tokens_value_and_original_preimage(self):
        fixture=self.fixture(signed=False);data,answer,facts,targets,catalog,units=fixture
        candidate=copy.deepcopy(facts[0]);candidate['metric_type']='stock';candidate['id']='corrected_stock_candidate'
        entry=copy.deepcopy(answer['observations'][0]);entry['metric_type']='stock'
        answer.update(observations=[entry],comparability_breaks=[],metadata_amendments=[dict(
            observation_id=facts[0]['id'],candidate_index=0,amendment_type='temporal_metric_correction',
            reason='Original closing balance-sheet column establishes a stock, not period flow.',source_refs=[dict(source_id='old',unit_id='page:1')])])
        fixture=(data,answer,[candidate],targets,catalog,units);updated,audit=self.merge(fixture)
        self.assertEqual(updated['observations'][0]['metric_type'],'stock')
        for key in ('id','value','unit','period_id','entity_id','basis','scope','source_refs','status'):
            self.assertEqual(updated['observations'][0][key],data['observations'][0][key])
        self.assertEqual(audit['metadata_amendments'][0]['before']['metric_type'],'flow')
        candidate['source_refs'][0]['number_index']=1
        with self.assertRaisesRegex(ValueError,'preserve every exact source token'):self.merge(fixture)

    def test_fingerprint_covers_delegated_gate_and_merge_implementation(self):
        import inspect
        from company_initiation.historic_construction import workflow
        data=self.fixture()[0];before=workflow.combined_history_fingerprint(data);source=inspect.getsource
        for name in ('ask','review_stage','_combined_history_challenge_once','_merge_historical_version_revision','_history_revision_equivalence',
                     '_history_citation_failure','_history_topic_contexts','_history_adjudication_reference_failure','_history_adjudication_correction_plan',
                     '_history_scope_findings','_validate_history_revision_scope'):
            def changed(helper):return source(helper)+('\n# changed protected implementation' if helper.__name__==name else '')
            with self.subTest(helper=name),patch('inspect.getsource',side_effect=changed):
                self.assertNotEqual(workflow.combined_history_fingerprint(data),before)

    def test_actual_multi_cohort_gate_runs_again_after_source_revision(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, combined_history_review_current, combined_history_fingerprint
        data,answer,facts,targets,catalog,units=self.fixture();data['history_years']=[2019,2020,2021]
        updated,audit=self.merge((data,answer,facts,targets,catalog,units));audit.update(affected_years=[2020],source_ids=['old','new'])
        class Journal:
            configuration={'limits':{'repairs':1}}
            def __init__(self):self.calls=[];self.artifacts={}
            def artifact(self,name,value):self.artifacts[name]=copy.deepcopy(value)
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                self.calls.append(stage)
                checks=[dict(topic=topic,status='pass',issue_type='none',period_ids=[],detail='Cited synthetic review',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for topic in payload['required_topics']]
                if len(self.calls)==1:checks[0].update(status='error',issue_type='missing_model_version',period_ids=['2020-FY'])
                result=dict(checks=checks,summary='Synthetic review');assess(result)
                return result
        journal=Journal();expected_fingerprint=combined_history_fingerprint(updated)
        with patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda journal,documents,*args,**kwargs:documents),patch(
                'company_initiation.historic_construction.workflow._repair_historical_versions',return_value=(updated,audit)) as repair,patch(
                'company_initiation.historic_construction.workflow.combined_history_fingerprint',return_value=expected_fingerprint):
            result=_combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()))
        self.assertTrue(combined_history_review_current(data));self.assertEqual(result['status'],'passed')
        self.assertEqual(journal.calls,['company_combined_history_cohort_1','company_combined_history_cohort_1',
            'company_combined_history_cohort_2','company_combined_history_synthesis'])
        repair.assert_called_once()
        matrix=journal.artifacts['combined_history_cohort_1_context.json']['historical_matrix']
        self.assertIn('model_selection_eligible',matrix['metadata_fields']);self.assertEqual(matrix['observation_count'],4)

    def test_revision_reruns_gate_and_bound_does_not_accept_unresolved_history(self):
        from company_initiation.historic_construction.workflow import _combined_history_challenge, _HistoricalVersionGap
        data,answer,facts,targets,catalog,units=self.fixture();updated,audit=self.merge((data,answer,facts,targets,catalog,units))
        audit.update(affected_years=[2020],source_ids=['old','new'])
        gap=_HistoricalVersionGap(dict(requested_years=[2020],evidence=units),[dict(kind='missing_model_version',evidence=[dict(source_id='new',unit_id='page:1')])])
        class Journal:
            configuration={'limits':{'repairs':1}}
            def artifact(self,*args):pass
        observed=[]
        def gate(journal,current,*args,**kwargs):
            observed.append(copy.deepcopy(current))
            if len(observed)==1:raise gap
            return {'status':'passed'}
        with patch('company_initiation.historic_construction.workflow._combined_history_challenge_once',side_effect=gate),patch('company_initiation.historic_construction.workflow._repair_historical_versions',return_value=(updated,audit)) as repair:
            result=_combined_history_challenge(Journal(),data,units,source_catalog=list(catalog.values()))
        self.assertEqual(result['status'],'passed');self.assertEqual(len(observed),2)
        self.assertEqual(len(observed[0]['observations']),1);self.assertEqual(len(observed[1]['observations']),4);repair.assert_called_once()
        with patch('company_initiation.historic_construction.workflow._combined_history_challenge_once',side_effect=gap),patch('company_initiation.historic_construction.workflow._repair_historical_versions',return_value=(copy.deepcopy(updated),audit)) as repair:
            with self.assertRaisesRegex(ValueError,'revisions exhausted'):_combined_history_challenge(Journal(),data,units)
            repair.assert_called_once()
        self.assertNotIn('combined_history_review',data)


class HistoricalVersionScopeCorrectionTests(unittest.TestCase):
    def fixture(self):
        from company_initiation.historic_construction.workflow import _history_scope_findings, _validate_history_revision_scope
        from company_initiation.forecast_construction.construction import _object, _array, TEXT
        from company_initiation.shared_runtime import digest
        data,_,facts,targets,catalog,units=HistoricalVersionRevisionTests().fixture()
        for period,oid in [('2020-Q1','saved_sales_q1'),('2020-9M','saved_sales_9m')]:
            data['observations'].append(dict(facts[0],id=oid,row_id='sales',period_id=period))
        findings=_history_scope_findings([dict(kind='missing_model_version',topic='restatement_versions',
            check='Synthetic source-present statement version question '+str(n),period_ids=['2020-FY','2020-Q1','2020-9M'] if n<2 else ['2020-FY']) for n in range(3)])
        answer=HistoricalVersionRevisionTests.scope_answer(dict(scoped_findings=findings),targets)
        citation=_object(source_id=TEXT,unit_id=TEXT)
        schema=_object(targets=_array(_object(row_id=TEXT,period_id=TEXT,existing_observation_ids=_array(TEXT),definition=TEXT,source_refs=_array(citation))),
            finding_dispositions=_array(_object(finding_id=TEXT,action=TEXT,target_indexes=_array({'type':'integer'}),observation_ids=_array(TEXT),detail=TEXT,source_refs=_array(citation))),
            primary_evidence_absent={'type':'boolean'},gaps=_array(TEXT))
        context=dict(scoped_findings=findings,evidence=units,existing_observations=data['observations'])
        def validate(value):return _validate_history_revision_scope(value,findings,data['observations'],{(u['source_id'],u['unit_id']) for u in units},catalog,{2020})
        request=dict(stage='company_history_revision_scope',instructions='Synthetic complete scope',payload=dict(context,validation_errors=['Prior exact failure']),schema=schema,attempt=2)
        call=dict(call_id='saved_whole_scope_attempt2',stage=request['stage'],signature=digest(request),request=request,result=copy.deepcopy(answer))
        return data,answer,context,schema,validate,call

    @staticmethod
    def correction(payload):
        response=dict(target_patches=[],disposition_patches=[])
        for item in payload['correction']['targets']:
            target=copy.deepcopy(payload['prior_scope_answer']['targets'][item['target_index']])
            target['existing_observation_ids']=[payload['scope_context']['existing_observations'][0]['id']]
            response['target_patches'].append(dict(target_index=item['target_index'],target_digest=item['target_digest'],target=target))
        by_id={item['finding_id']:item for item in payload['prior_scope_answer']['finding_dispositions']}
        for item in payload['correction']['dispositions']:
            disposition=copy.deepcopy(by_id[item['finding_id']]);disposition['observation_ids']=['saved_sales_q1','saved_sales_9m']
            response['disposition_patches'].append(dict(finding_id=item['finding_id'],disposition_digest=item['disposition_digest'],disposition=disposition))
        return response

    def test_exact_latest_scope_reuses_own_answer_patches_all_missing_periods_and_freezes_valid_records(self):
        from company_initiation.historic_construction.workflow import _history_scope_stage
        data,answer,context,schema,validate,call=self.fixture();before=copy.deepcopy(data);outer=self
        class Journal:
            configuration={'limits':{'repairs':2}};entries=[call]
            def __init__(self):self.saved={};self.calls=0
            def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
            def stage(self,*a,**kw):raise AssertionError('Exact latest whole-scope answer must be replayed')
            def ask(self,stage,prompt,payload,patch_schema,attempt):
                self.calls+=1;outer.assertEqual(attempt,1)
                outer.assertEqual(payload['prior_scope_answer'],answer);outer.assertEqual(payload['scope_context'],context)
                outer.assertEqual(payload['correction']['targets'],[]);outer.assertEqual(len(payload['correction']['dispositions']),2)
                for error in payload['correction']['dispositions']:
                    outer.assertEqual(error['required_period_ids'],['2020-9M','2020-FY','2020-Q1'])
                    outer.assertEqual(error['omitted_period_ids'],['2020-9M','2020-Q1'])
                return outer.correction(payload)
        journal=Journal();result=_history_scope_stage(journal,call['stage'],call['request']['instructions'],context,schema,validate)
        self.assertEqual(journal.calls,1);self.assertEqual(result['targets'],answer['targets'])
        self.assertEqual(result['finding_dispositions'][2],answer['finding_dispositions'][2])
        self.assertEqual(data,before);self.assertNotIn('combined_history_review',data)
        protocol=next(value for name,value in journal.saved.items() if name.endswith('_protocol.json'))
        self.assertEqual(protocol['baseline']['attempt'],2);self.assertEqual(len(protocol['earlier_whole_answer_calls']),1)

    def test_invalid_record_patches_do_not_erase_valid_scope_or_real_evidence_gaps(self):
        from company_initiation.historic_construction.workflow import _history_scope_stage
        from company_initiation.shared_runtime import digest
        for mode,expected in [('unaffected_disposition','no frozen'),('valid_target','no frozen'),('changed_target','frozen target'),
                ('wrong_digest','exact prior finding'),('no_progress','no progress'),('primary_gap','unresolved primary support')]:
            data,answer,context,schema,validate,call=self.fixture();before=copy.deepcopy(data);outer=self
            if mode=='changed_target':
                answer['targets'][0]['existing_observation_ids']=[];call['result']=copy.deepcopy(answer)
            class Journal:
                configuration={'limits':{'repairs':2}};entries=[call]
                def artifact(self,*a):pass
                def ask(self,stage,prompt,payload,patch_schema,attempt):
                    response=outer.correction(payload)
                    if mode=='unaffected_disposition':
                        item=answer['finding_dispositions'][2];response['disposition_patches'].append(dict(finding_id=item['finding_id'],disposition_digest=digest(item),disposition=copy.deepcopy(item)))
                    if mode=='valid_target':response['target_patches']=[dict(target_index=0,target_digest=digest(answer['targets'][0]),target=copy.deepcopy(answer['targets'][0]))]
                    if mode=='changed_target':response['target_patches'][0]['target']['period_id']='2021-FY'
                    if mode=='wrong_digest':response['disposition_patches'][0]['disposition_digest']='changed'
                    if mode=='no_progress':
                        for item in response['disposition_patches']:item['disposition']['observation_ids']=[];item['disposition']['detail']='Different prose, unchanged omissions'
                    if mode=='primary_gap':response['disposition_patches'][0]['disposition'].update(action='primary_evidence_absent',target_indexes=[],observation_ids=[])
                    return response
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,expected):
                _history_scope_stage(Journal(),call['stage'],call['request']['instructions'],context,schema,validate)
            self.assertEqual(data,before)

    def test_patch_attempt_ownership_survives_resume_and_cannot_reset_after_changed_feedback(self):
        from company_initiation.historic_construction.workflow import _history_scope_stage
        from company_initiation.shared_runtime import digest
        data,answer,context,schema,validate,call=self.fixture();outer=self
        class Journal:
            configuration={'limits':{'repairs':2}}
            def __init__(self):self.entries=[copy.deepcopy(call)];self.dispatches=0;self.reuses=0
            def artifact(self,*a):pass
            def ask(self,stage,prompt,payload,patch_schema,attempt):
                request=dict(stage=stage,instructions=prompt,payload=copy.deepcopy(payload),schema=copy.deepcopy(patch_schema),attempt=attempt)
                signature=digest(request)
                for saved in self.entries:
                    if saved['signature']==signature:self.reuses+=1;return copy.deepcopy(saved['result'])
                self.dispatches+=1;response=outer.correction(payload)
                self.entries.append(dict(call_id='patch'+str(attempt),stage=stage,signature=signature,request=request,result=copy.deepcopy(response)))
                return response
        journal=Journal();first=_history_scope_stage(journal,call['stage'],call['request']['instructions'],context,schema,validate)
        second=_history_scope_stage(journal,call['stage'],call['request']['instructions'],context,schema,validate)
        self.assertEqual(first,second);self.assertEqual((journal.dispatches,journal.reuses),(1,1))
        journal.entries[-1]['error']='Recorded provider failure'
        with self.assertRaisesRegex(ValueError,'already failed'):_history_scope_stage(journal,call['stage'],call['request']['instructions'],context,schema,validate)
        self.assertEqual(journal.dispatches,1)
        journal.entries[-1].pop('error');journal.entries[-1]['request']['payload']['correction']['dispositions'][0]['errors'].append('Changed prior request')
        with self.assertRaisesRegex(ValueError,'bounded allowance cannot restart'):_history_scope_stage(journal,call['stage'],call['request']['instructions'],context,schema,validate)

    def test_scope_source_or_prompt_drift_never_selects_an_unrelated_saved_answer(self):
        from company_initiation.historic_construction.workflow import _history_scope_stage
        for mode in ('source','prompt'):
            data,answer,context,schema,validate,call=self.fixture();changed=copy.deepcopy(context)
            prompt=call['request']['instructions']
            if mode=='source':changed['evidence'][0]['text']+=' changed original'
            else:prompt+=' changed contract'
            class Journal:
                entries=[call]
                def stage(self,*a,**kw):raise RuntimeError('Fresh compatible request required')
            with self.subTest(mode=mode),self.assertRaisesRegex(RuntimeError,'Fresh compatible'):
                _history_scope_stage(Journal(),call['stage'],prompt,changed,schema,validate)

    def test_fresh_nonpatchable_scope_stops_before_generic_whole_answer_regeneration(self):
        from company_initiation.historic_construction.workflow import _history_scope_stage
        for mode,message in [('primary','unresolved primary support'),('unknown','unknown/duplicate finding'),('unlinked','unlinked targets')]:
            data,answer,context,schema,validate,call=self.fixture()
            if mode=='primary':answer.update(primary_evidence_absent=True,gaps=['Required primary original is unavailable.'])
            if mode=='unknown':answer['finding_dispositions'][0]['finding_id']='not_a_requested_finding'
            if mode=='unlinked':
                for item in answer['finding_dispositions']:item.update(action='unsupported_allegation',target_indexes=[],observation_ids=[])
            class Journal:
                configuration={'limits':{'repairs':2}};entries=[]
                def __init__(self):self.whole_requests=0
                def stage(self,stage,prompt,payload,schema,validator):
                    for attempt in range(3):
                        self.whole_requests+=1
                        try:return validator(copy.deepcopy(answer))
                        except (ValueError,KeyError,TypeError):continue
                    raise AssertionError('Unsafe whole-answer regeneration occurred')
                def ask(self,*a,**kw):raise AssertionError('A nonpatchable primary/contract failure must not dispatch a patch')
            journal=Journal()
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,message):
                _history_scope_stage(journal,call['stage'],call['request']['instructions'],context,schema,validate)
            self.assertEqual(journal.whole_requests,1)


class HistoricalVersionRouteContinuationTests(unittest.TestCase):
    def checkpoint(self,folder,*,selection_gaps=()):
        import hashlib
        from company_initiation.shared_runtime import digest
        from company_initiation.historic_construction.workflow import _combined_history_challenge_once, _HistoricalVersionGap, _history_parser_identity
        data,answer,facts,targets,catalog,units=HistoricalVersionRevisionTests().fixture()
        data['model_configuration']['limitations']=[]
        data['historical_review_obligations']=[dict(id='prior_version_question',topic='source_vintage',fiscal_years=[2020],
            original_finding=dict(kind='missing_model_version',topic='source_vintage',check='Published alternate statement needs source vintage.',
                period_ids=['2020-FY'],evidence=[dict(source_id='new',unit_id='page:1')]))]
        before=copy.deepcopy(data)
        data['model_configuration']['limitations'].extend('Historical source selection: '+gap for gap in selection_gaps)
        if selection_gaps:data['model_configuration']['limitations'].append('Source retrieval: complete-section note retained in the original review context.')
        class Journal:
            def __init__(self):self.saved={};self.entries=[]
            def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
            def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                result=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Cited check',
                    source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']],summary='Synthetic source-present gap')
                next(c for c in result['checks'] if c['topic']=='restatement_versions').update(status='error',issue_type='missing_model_version',
                    period_ids=['2020-FY'],detail='Published alternate CFO is missing from retained observations.')
                result['financial_adjudications']=[dict(finding_id=o['id'],outcome='unresolved',resolution='unresolved',observation_ids=[],
                    detail='The cited alternate source version is not yet bound.',source_refs=[dict(source_id='new',unit_id='page:1')]) for o in payload['financial_review_obligations']]
                request=dict(stage=stage,instructions=prompt,payload=copy.deepcopy(payload),schema=copy.deepcopy(schema),attempt=0)
                self.entries.append(dict(call_id='saved_complete_review',stage=stage,request=request,signature=digest(request),result=copy.deepcopy(result)))
                return assess(result)
        journal=Journal()
        with patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda j,docs,*a,**kw:docs):
            with self.assertRaises(_HistoricalVersionGap) as caught:
                _combined_history_challenge_once(journal,data,units,source_catalog=list(catalog.values()))
        journal.artifact('history_revision_1_findings.json',dict(context=caught.exception.context,findings=caught.exception.findings))
        journal.artifact('company_model_inputs.json',before)
        journal.artifact('history_original_index.json',dict(parser_identity=_history_parser_identity(),sources={sid:dict(
            sha256=source['sha256'],units=[u for u in units if u['source_id']==sid]) for sid,source in catalog.items()}))
        if selection_gaps:journal.artifact('history_source_selection.json',dict(source_ids=list(catalog),reasons=['Synthetic selected originals'],
            coverage=[dict(year=2020,source_ids=list(catalog),period_kinds=['FY'],method='Cited original and revised statements')],gaps=list(selection_gaps)))
        folder.mkdir();artifacts={}
        for name,value in journal.saved.items():
            path=folder/name;path.write_text(json.dumps(value),encoding='utf-8');artifacts[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        record=dict(directory=str(folder),artifacts=artifacts,calls=copy.deepcopy(journal.entries),sources=list(catalog.values()),_reuse_verified=True)
        data['model_configuration']['limitations']=copy.deepcopy(before['model_configuration']['limitations'])
        return data,before,record,answer,facts,targets,catalog,units

    def test_complete_preparation_allows_only_hash_verified_source_selection_note_delta(self):
        from company_initiation.historic_construction.workflow import restore_history_version_route, prepare_history_review_context, _combined_history_challenge_once, _HistoricalVersionGap
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'old'
            data,before,record,answer,facts,targets,catalog,units=self.checkpoint(folder,selection_gaps=['Quarterly originals disclose sales only.'])
            selection=json.loads((folder/'history_source_selection.json').read_text(encoding='utf-8'))
            frozen=copy.deepcopy(list(catalog.values()))
            source_path=Path(temp)/'original.pdf';source_path.write_bytes(b'preserved synthetic bytes'*10000)
            for source in frozen:source.update(path=str(source_path),format='pdf',local_path=source['id']+'.pdf')
            resume=restore_history_version_route(record,[],data,frozen);original_context=copy.deepcopy(resume['gap']['context']);outer=self
            class Journal:
                entries=record['calls']
                def __init__(self):self.saved={};self.selections=0
                def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
                def stage(self,stage,prompt,payload,schema,validate):
                    outer.assertEqual(stage,'company_history_sources');self.selections+=1;return validate(copy.deepcopy(selection))
                def review_stage(self,*args,**kwargs):raise AssertionError('Saved complete review must be replayed without another call')
            journal=Journal()
            with patch('company_initiation.historic_construction.evidence._units',side_effect=AssertionError('Reuse exact saved parsed originals')):
                prepared=prepare_history_review_context(journal,data,frozen,previous=record)
            self.assertEqual(journal.selections,1)
            self.assertEqual(data['model_configuration']['limitations'],['Historical source selection: Quarterly originals disclose sales only.'])
            self.assertNotEqual(resume['input_digest'],resume['prepared_input_digest'])
            with patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=AssertionError('No repeated section selection')):
                with self.assertRaises(_HistoricalVersionGap):
                    _combined_history_challenge_once(journal,data,**prepared,resume_version_route=resume)
            self.assertEqual(resume['gap']['context'],original_context)
            self.assertIn('Source retrieval: complete-section note retained in the original review context.',original_context['limitations'])
            changed=copy.deepcopy(data);changed['model_configuration']['limitations'].append('An unrelated altered economic limitation')
            with self.assertRaisesRegex(ValueError,'beyond its exact saved source-selection preparation'):
                _combined_history_challenge_once(journal,changed,**prepared,resume_version_route=resume)
            (folder/'history_source_selection.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'artifact is missing or changed'):
                restore_history_version_route(record,[],before,frozen)

    def test_saved_route_replays_raw_assessment_then_exact_scope_and_full_independent_repair(self):
        from company_initiation.historic_construction.workflow import restore_history_version_route, _combined_history_challenge, combined_history_review_current
        with tempfile.TemporaryDirectory() as temp:
            data,before,record,answer,facts,targets,catalog,units=self.checkpoint(Path(temp)/'old')
            resume=restore_history_version_route(record,[],data,list(catalog.values()));outer=self
            self.assertEqual(len(resume['call']['request']['payload']['financial_review_obligations']),1)
            self.assertEqual(len(data['historical_review_obligations']),2)
            class Journal:
                configuration={'limits':{'repairs':2}}
                def __init__(self):self.entries=copy.deepcopy(record['calls']);self.stages=[];self.reviews=0;self.saved={};self.scope_patches=0
                def artifact(self,name,value):self.saved[name]=copy.deepcopy(value)
                def ask(self,stage,prompt,payload,schema,attempt):
                    self.scope_patches+=1
                    outer.assertEqual(stage,'company_history_revision_scope');outer.assertEqual(attempt,1)
                    target=payload['correction']['targets'][0]
                    outer.assertEqual(target['allowed_fields'],['existing_observation_ids'])
                    return dict(target_patches=[dict(target_index=0,target_digest=target['target_digest'],target=copy.deepcopy(targets[0]))],disposition_patches=[])
                def stage(self,stage,prompt,payload,schema,validate):
                    self.stages.append(stage)
                    if stage.endswith('_scope'):
                        outer.assertEqual(payload['revision'],1)
                        initial=HistoricalVersionRevisionTests.scope_answer(payload,targets)
                        initial['targets'][0]['existing_observation_ids']=[]
                        return validate(initial)
                    if stage.endswith('_mapping'):return validate(copy.deepcopy(answer))
                    if stage.endswith('_independent'):
                        outer.assertEqual(set(payload),{'revision','requested_concepts','periods','evidence'})
                        outer.assertIn('history_revision_1_candidate.json',self.saved)
                        return validate({key:copy.deepcopy(answer[key]) for key in ('observations','reporting_changes','gaps')})
                    raise AssertionError(stage)
                def review_stage(self,stage,prompt,payload,schema,*,assess,repair_context):
                    self.reviews+=1
                    outer.assertEqual(self.stages,['company_history_revision_scope','company_history_revision_mapping','company_history_revision_independent'])
                    outer.assertTrue(data['historical_version_revisions'])
                    result=dict(checks=[dict(topic=t,status='pass',issue_type='none',period_ids=[],detail='Full source-backed recheck after independent revision.',
                        source_refs=[dict(source_id='new',unit_id='page:1')]) for t in payload['required_topics']],summary='All topics rechecked')
                    result['financial_adjudications']=[dict(finding_id=o['id'],outcome='resolved',resolution='repaired',
                        observation_ids=[data['historical_version_revisions'][0]['added_observation_ids'][0]],detail='Independently reconstructed published version retained.',
                        source_refs=[dict(source_id='new',unit_id='page:1')]) for o in payload['financial_review_obligations']]
                    outer.assertEqual(assess(result),[]);return result
            journal=Journal()
            with patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=lambda j,docs,*a,**kw:docs) as sections:
                _combined_history_challenge(journal,data,units,source_catalog=list(catalog.values()),resume_version_route=resume)
            self.assertEqual(journal.reviews,1);self.assertEqual(sections.call_count,1);self.assertEqual(journal.scope_patches,1)
            self.assertTrue(combined_history_review_current(data))
            self.assertEqual(data['observations'][0],before['observations'][0]);self.assertEqual(data['historical'],before['historical'])
            self.assertEqual(data['active_basis_by_period'],before['active_basis_by_period'])
            self.assertEqual(len(journal.saved['history_version_route_resume.json']['retained_obligation_ids']),2)
            self.assertEqual(journal.saved['company_model_inputs.json']['observations'][1]['value'],107)

    def test_restore_rejects_source_call_or_artifact_tamper_and_consumed_routes(self):
        import hashlib
        from company_initiation.historic_construction.workflow import restore_history_version_route
        with tempfile.TemporaryDirectory() as temp:
            data,before,record,answer,facts,targets,catalog,units=self.checkpoint(Path(temp)/'old')
            changed=copy.deepcopy(list(catalog.values()));changed[1]['sha256']='changed'
            with self.assertRaisesRegex(ValueError,'source identity or vintage changed'):restore_history_version_route(record,[],data,changed)
            altered=copy.deepcopy(record);altered['calls'][0]['request']['payload']['evidence']=[]
            with self.assertRaisesRegex(ValueError,'exact inherited successful'):restore_history_version_route(altered,[],data,list(catalog.values()))
            drift=copy.deepcopy(data);drift['historical']['cfo']['2020']=101
            self.assertIsNone(restore_history_version_route(record,[],drift,list(catalog.values())))
            name='history_revised_inputs_1.json';path=Path(record['directory'])/name
            path.write_text(json.dumps(data),encoding='utf-8');record['artifacts'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIsNone(restore_history_version_route(record,[],data,list(catalog.values())))
            record['artifacts'].pop(name)
            (Path(record['directory'])/'history_revision_1_findings.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'artifact is missing or changed'):restore_history_version_route(record,[],data,list(catalog.values()))

    def test_replay_rejects_missing_new_allegation_context_or_contract_before_any_call(self):
        from types import SimpleNamespace
        from company_initiation.shared_runtime import digest
        from company_initiation.historic_construction.workflow import restore_history_version_route, _combined_history_challenge_once
        with tempfile.TemporaryDirectory() as temp:
            data,before,record,answer,facts,targets,catalog,units=self.checkpoint(Path(temp)/'old')
            resume=restore_history_version_route(record,[],data,list(catalog.values()))
            for case in ('missing_allegation','new_allegation','changed_unit','changed_inputs','changed_contract','changed_provider','changed_parser','changed_route'):
                d=copy.deepcopy(data);u=copy.deepcopy(units);r=copy.deepcopy(resume)
                if case=='missing_allegation':d['historical_review_obligations'].pop()
                if case=='new_allegation':d['historical_review_obligations'].append(dict(d['historical_review_obligations'][0],id='new_unreviewed_finding'))
                if case=='changed_unit':u[0]['text']+=' altered'
                if case=='changed_inputs':d['historical']['cfo']['2020']=101
                if case=='changed_contract':
                    r['call']['request']['instructions']+=' changed';r['call']['signature']=digest(r['call']['request'])
                journal=SimpleNamespace(entries=[r['call']],artifact=lambda *args:None,review_stage=Mock(side_effect=AssertionError('No dispatch')))
                if case=='changed_provider':journal.configuration={'provider':{'provider':'different'}}
                if case=='changed_parser':r['parser_identity']['python']='different'
                if case=='changed_route':journal.provider=SimpleNamespace(route=lambda *a:('changed-model','changed-effort'))
                with self.subTest(case=case),patch('company_initiation.historic_construction.workflow.construction_evidence',side_effect=AssertionError('No reselection')):
                    with self.assertRaisesRegex(ValueError,'checkpoint'):
                        _combined_history_challenge_once(journal,d,u,source_catalog=list(catalog.values()),resume_version_route=r)
                journal.review_stage.assert_not_called()

    def test_invalid_saved_scope_feedback_names_exact_target_without_assigning_ids(self):
        from company_initiation.historic_construction.workflow import _history_scope_findings, _validate_history_revision_scope
        data,answer,facts,targets,catalog,units=HistoricalVersionRevisionTests().fixture()
        findings=_history_scope_findings([dict(kind='missing_model_version',check='Published version',period_ids=['2020-FY'])])
        scope=HistoricalVersionRevisionTests.scope_answer(dict(scoped_findings=findings),targets);scope['targets'][0]['existing_observation_ids']=[]
        unchanged=copy.deepcopy(scope)
        with self.assertRaises(ValueError) as caught:_validate_history_revision_scope(scope,findings,data['observations'],{(u['source_id'],u['unit_id']) for u in units},catalog,{2020})
        self.assertIn('"target_index": 0',str(caught.exception));self.assertIn('"row_id": "cfo"',str(caught.exception))
        self.assertIn(facts[0]['id'],str(caught.exception));self.assertEqual(scope,unchanged)


class ExtractionContractTests(unittest.TestCase):
    """Independent examples of source binding and blind-concept boundaries."""

    def entry(self, *, raw='3 399,7', token_raw=None, multiplier=1,
              number_format='comma_decimal', metric_type='flow', unit='EURm'):
        entry=dict(row_id='professional_sales',period_id='2016-FY',
                   metric_type=metric_type,unit=unit,terms=[dict(
                       source_raw=raw,multiplier=multiplier,weight=1,
                       reference=dict(source_id='annual_original',unit_id='page:224',
                                      number_index=5,number_format=number_format))])
        return entry,[dict(index=5,raw=raw if token_raw is None else token_raw)]

    def test_explicit_percent_token_is_scaled_once_by_python(self):
        from company_initiation.historic_construction.evidence import parse_number
        from company_initiation.historic_construction.workflow import _validate_financial_extraction
        entry,tokens=self.entry(raw='4.7%',number_format='dot_decimal',metric_type='ratio',unit='ratio')
        _validate_financial_extraction(entry,tokens)
        self.assertAlmostEqual(parse_number(tokens[0]['raw'],'dot_decimal')*entry['terms'][0]['multiplier'],.047)
        for repeated_scale in (.01,100):
            changed=copy.deepcopy(entry);changed['terms'][0]['multiplier']=repeated_scale
            with self.subTest(multiplier=repeated_scale),self.assertRaises(ValueError):
                _validate_financial_extraction(changed,tokens)

    def test_comma_decimal_monetary_and_signed_percent_source_bindings(self):
        from company_initiation.historic_construction.evidence import parse_number
        from company_initiation.historic_construction.workflow import _validate_financial_extraction
        for raw,metric,unit,expected in [('1\u00a0286,1','flow','EURm',1286.1),
                                         ('-25,8','flow','EURm',-25.8),
                                         ('-0,7 %','ratio','ratio',-.007)]:
            entry,tokens=self.entry(raw=raw,metric_type=metric,unit=unit)
            with self.subTest(raw=raw):
                _validate_financial_extraction(entry,tokens)
                self.assertAlmostEqual(parse_number(tokens[0]['raw'],'comma_decimal'),expected)

    def test_claimed_table_amount_cannot_select_a_year_or_prose_number(self):
        from company_initiation.historic_construction.workflow import _validate_financial_extraction
        for selected in ('2016','60','3 410,9'):
            entry,tokens=self.entry(raw='3 399,7',token_raw=selected)
            with self.subTest(selected_token=selected),self.assertRaises(ValueError):
                _validate_financial_extraction(entry,tokens)

    def test_only_canonical_measurement_types_are_accepted(self):
        from company_initiation.historic_construction.workflow import _validate_financial_extraction
        for metric in ('flow','stock','ratio','weighted_average'):
            entry,tokens=self.entry(metric_type=metric)
            with self.subTest(valid=metric):_validate_financial_extraction(entry,tokens)
        for metric in ('profit','income_expense','organic_growth','depreciation_amortisation_provisions'):
            entry,tokens=self.entry(metric_type=metric)
            with self.subTest(invalid=metric),self.assertRaises(ValueError):
                _validate_financial_extraction(entry,tokens)

    def test_blind_contract_accepts_exact_requested_concept_without_values(self):
        from company_initiation.historic_construction.workflow import _validate_financial_extraction
        entry,tokens=self.entry()
        concepts=[dict(row_id='professional_sales',period_id='2016-FY',unit='EURm')]
        before=copy.deepcopy((entry,tokens,concepts))
        _validate_financial_extraction(entry,tokens,concepts=concepts)
        self.assertEqual((entry,tokens,concepts),before)
        self.assertNotIn('value',concepts[0]);self.assertNotIn('source_refs',concepts[0])

    def test_blind_alias_wrong_period_and_unit_change_are_rejected(self):
        from company_initiation.historic_construction.workflow import _validate_financial_extraction
        entry,tokens=self.entry()
        concepts=[dict(row_id='professional_sales',period_id='2016-FY',unit='EURm')]
        for field,value in [('row_id','PP_sales'),('period_id','2015-FY'),('unit','EUR'),('unit','ratio')]:
            changed=copy.deepcopy(entry);changed[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                _validate_financial_extraction(changed,tokens,concepts=concepts)

    def test_numeric_repair_retains_both_original_and_restated_versions(self):
        from company_initiation.historic_construction.workflow import _validate_reconstruction_revision
        original=dict(row_id='sales',period_id='2025-FY',unit='EURm',metric_type='flow',entity_id='group',
            basis='consolidated',definition_id='net_sales',scope='continuing',restatement='original',restatement_vintage=None,value=100)
        restated=dict(original,restatement='restated',restatement_vintage='2026-revision',value=90)
        disputed={('sales','2025-FY')}
        _validate_reconstruction_revision([dict(original,value=101),restated],disputed,[original,restated])
        _validate_reconstruction_revision([original,restated],disputed)
        for revised in ([original],[original,original],[original,dict(restated,restatement_vintage='different-revision')]):
            with self.subTest(revised=revised),self.assertRaisesRegex(ValueError,'retain every candidate reporting version'):
                _validate_reconstruction_revision(revised,disputed,[original,restated])
        with self.assertRaisesRegex(ValueError,'cover each disputed'):
            _validate_reconstruction_revision([],disputed)

    def test_materializer_reports_all_rows_roles_tokens_and_reference_errors_without_partial_acceptance(self):
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        from company_initiation.historic_construction.workflow import _materialize_financial_observations
        period=dict(id='2023-FY',fiscal_year=2023,kind='FY',start='2022-07-01',end='2023-06-30')
        unit=dict(source_id='original',unit_id='page:4',text='Synthetic directly reported table.',
            numbers=[dict(index=i,raw=raw) for i,raw in enumerate(('5,921','5,306','1,217','786','4.7%','100.0'))])
        catalog={'original':dict(id='original',category='financial_reports',sha256='fixture')}
        store=SourceStore(Path('.'));store.sources=list(catalog.values());store._units={'original':{'page:4':unit}}
        def term(index,raw):
            return dict(reference=dict(source_id='original',unit_id='page:4',number_index=index,number_format='dot_decimal'),
                source_raw=raw,multiplier=1,weight=1)
        def entry(role,terms):
            return dict(row_id=role,label=role,period_id='2023-FY',unit='GBPm',metric_type='flow',entity_id='group',
                basis='consolidated',definition_id=role,scope='consolidated',terms=terms,rounding_increment=.1,
                restatement='original',restatement_vintage=None,classification_basis='Original table heading.',
                classification_source_refs=[dict(source_id='original',unit_id='page:4')])
        valid=entry('sales',[term(5,'100.0')])
        alias=entry('da_group_fy_2023',[term(0,'5,306'),term(2,'786')])
        missing_unit=entry('reported_special_cost',[term(0,'5,921')]);missing_unit['terms'][0]['reference']['unit_id']='page:404'
        invalid_format=entry('reported_special_gain',[term(1,'5,306')]);invalid_format['terms'][0]['reference']['number_format']='unsupported'
        percent=entry('tax_rate',[term(4,'4.7%')]);percent.update(unit='ratio',metric_type='ratio');percent['terms'][0]['multiplier']=.01
        answer=dict(observations=[valid,alias,missing_unit,invalid_format,percent],reporting_changes=[],gaps=[])
        before=copy.deepcopy((answer,store._units));kwargs=dict(store=store,catalog=catalog,periods=[period],currency='GBP',
            roles=integrated_role_contract(),segments=[],evidence=[unit])
        valid_fact=_materialize_financial_observations(dict(answer,observations=[valid]),**kwargs)[0]
        with self.assertRaises(ValueError) as failure:_materialize_financial_observations(answer,**kwargs)
        feedback=str(failure.exception)
        for required in ('use row_id=da','5,921','5,306','1,217','786','original','page:4','number_index',
                         'page:404','unsupported','Percentage token already resolves','No partial answer is accepted'):
            self.assertIn(required,feedback)
        self.assertEqual((answer,store._units),before)
        repaired=copy.deepcopy(answer);repaired['observations'][1]['row_id']='da'
        repaired['observations'][1]['terms'][0]['reference']['number_index']=1
        repaired['observations'][1]['terms'][1]['reference']['number_index']=3
        repaired['observations'][2]['terms'][0]['reference']['unit_id']='page:4'
        repaired['observations'][3]['terms'][0]['reference']['number_format']='dot_decimal'
        repaired['observations'][4]['terms'][0]['multiplier']=1
        facts=_materialize_financial_observations(repaired,**kwargs)
        self.assertEqual(facts[0],valid_fact)
        self.assertEqual(facts[1]['value'],6092)
        self.assertAlmostEqual(facts[-1]['value'],.047)

    def test_multiple_invalid_terms_and_blind_contract_errors_are_reported_together(self):
        from company_initiation.historic_construction.workflow import _validate_financial_extraction
        entry,tokens=self.entry(raw='100',token_raw='2016',number_format='dot_decimal')
        entry['terms'].append(copy.deepcopy(entry['terms'][0]));entry['terms'][1]['source_raw']='200'
        tokens.append(dict(raw='300'))
        concepts=[dict(row_id='another_requested_role',period_id='2016-FY',unit='EURm')]
        with self.assertRaises(ValueError) as failure:_validate_financial_extraction(entry,tokens,concepts)
        feedback=str(failure.exception)
        self.assertIn('preserve exact requested row_id',feedback)
        self.assertIn("selected token is '2016'",feedback);self.assertIn("source_raw claims '100'",feedback)
        self.assertIn("selected token is '300'",feedback);self.assertIn("source_raw claims '200'",feedback)
        with self.assertRaisesRegex(ValueError,'selected original token'):
            _validate_financial_extraction(entry,[None,tokens[1]])

    def test_construction_number_format_guidance_is_explicit_and_does_not_mutate_initiation(self):
        from company_initiation.historic_construction.workflow import _financial_mapping_schema
        from company_initiation.historic_construction.initiation import NUMBER_REF
        from company_initiation.historic_construction.evidence import parse_number
        original=copy.deepcopy(NUMBER_REF)
        term=_financial_mapping_schema()['properties']['observations']['items']['properties']['terms']['items']['properties']
        reference=term['reference'];guidance=reference['properties']['number_format']['description']
        self.assertIn('dot_decimal uses a period decimal separator and comma thousands separators',guidance)
        self.assertIn('comma_decimal uses a comma decimal separator and period thousands separators',guidance)
        self.assertIn('complete source/table numeric convention',guidance)
        self.assertIn('Keep source_raw exactly as printed',guidance)
        self.assertIn('separate multiplier',guidance)
        self.assertIn('source reported unit',term['multiplier']['description'])
        self.assertEqual(parse_number('1,234.5','dot_decimal'),parse_number('1.234,5','comma_decimal'))
        self.assertEqual(NUMBER_REF,original)
        reference['properties']['number_format']['enum'].append('test_mutation')
        self.assertEqual(NUMBER_REF,original,'Construction schema must not mutate the strict initiation contract')

    def test_mapping_schema_explains_canonical_roles_without_banning_extra_company_concepts(self):
        from company_initiation.historic_construction.workflow import _financial_mapping_schema
        role=_financial_mapping_schema()['properties']['observations']['items']['properties']['row_id']
        self.assertIn('engine_contract.roles',role['description']);self.assertNotIn('enum',role)
        self.assertNotIn('pattern',role)


class FinancialRoleContractTests(unittest.TestCase):
    def test_source_catalogue_resolves_literal_loops_and_does_not_execute_code(self):
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        source='''def build_integrated_spec(data):
    raise RuntimeError("must never execute")
    def row(key, label, section):
        val("not_a_scaffold_anchor")
    for role, label in [("sourced_cost", "Cost"), ("sourced_logistics", "Logistics")]:
        row(role, label, "income")
        val(role)
    ratio("a_parameter", "sourced_tax", "sourced_earnings")
    composed("sourced_income", "sourced_expense")
    row("cash_display", "Cash", "finance", role="sourced_cash")
    row("corporate_result", "Corporate", "corporate")
    historical["sourced_opening"]
    for segment in data["segments"]:
        row(key + "_sales", "Sales", "segment")
'''
        contract=integrated_role_contract(source)
        expected={'sourced_cost','sourced_logistics','sourced_tax','sourced_earnings','sourced_income','sourced_expense','cash_display','sourced_cash','sourced_opening'}
        self.assertEqual(set(contract['group_roles']),expected)
        self.assertEqual(set(contract['anchor_roles']),{'sourced_cost','sourced_logistics','sourced_tax','sourced_earnings'})
        self.assertEqual(contract['corporate_roles'],['corporate_result'])
        self.assertEqual(contract['segment_role_suffixes'],['_sales'])
        self.assertNotEqual(contract['source_sha256'],integrated_role_contract(source+'\n# changed scaffold\n')['source_sha256'])

    def test_group_aliases_reject_without_losing_auxiliary_or_legacy_entities(self):
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        from company_initiation.historic_construction.workflow import _validate_financial_role
        contract=integrated_role_contract();segments=[dict(id='industrial'),dict(id='services')]
        for role in ('sales','cogs','da','distribution','other_trading_income','debt_interest_expense'):
            entry=dict(row_id='group_'+role,entity_id='group',period_id='2025-FY')
            original=copy.deepcopy(entry)
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'use row_id='+role):
                _validate_financial_role(entry,contract,segments)
            self.assertEqual(entry,original)
        for role,entity in [('sales','group'),('industrial_sales','industrial'),('corporate_da','corporate'),
                            ('legacy_consumer_sales','legacy_consumer'),('industrial_sales','legacy_industrial'),
                            ('group_reported_special_subtotal','group'),('industrial_dap','industrial')]:
            _validate_financial_role(dict(row_id=role,entity_id=entity,period_id='2025-FY'),contract,segments)
        for role,entity in [('sales','industrial'),('industrial_sales','services'),('corporate_da','group')]:
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'requires entity_id='):
                _validate_financial_role(dict(row_id=role,entity_id=entity,period_id='2025-FY'),contract,segments)

    def test_known_role_period_suffixes_are_rejected_without_remapping_legacy_definitions(self):
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        from company_initiation.historic_construction.workflow import _validate_financial_role
        contract=integrated_role_contract();segments=[dict(id='industrial')]
        for role,expected,entity in [('sales_group_2023-Q1','sales','group'),('sales_group_q1_2023','sales','group'),
                ('group_cogs_2023','cogs','group'),('industrial_sales_2023_Q1','industrial_sales','industrial'),
                ('corporate_da_2023','corporate_da','corporate')]:
            entry=dict(row_id=role,period_id='2023-Q1',entity_id=entity);before=copy.deepcopy(entry)
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'use row_id='+expected):
                _validate_financial_role(entry,contract,segments)
            self.assertEqual(entry,before)
        for role,entity in [('legacy_2019_industrial_sales','legacy_2019_industrial'),
                ('industrial_prior_perimeter_sales','industrial_prior_perimeter'),('group_reported_special_subtotal','group'),
                ('old-consumer_sales','old-consumer'),('Asia-Pacific_prior_scope_result','Asia-Pacific_prior_scope')]:
            _validate_financial_role(dict(row_id=role,period_id='2023-Q1',entity_id=entity),contract,segments)

    def test_missing_declarations_preserve_context_without_numeric_facts(self):
        from company_initiation.historic_construction.workflow import _partition_financial_observations, _reconstruction_comparison
        reported=dict(row_id='sales',period_id='2025-FY',terms=[dict(reference='original')])
        missing=dict(row_id='industrial_da',period_id='2025-FY',terms=[],classification_basis='No pure D&A is disclosed in the segment note.',classification_source_refs=[dict(source_id='annual',unit_id='page:8')])
        answer=dict(observations=[reported,missing],gaps=[]);original=copy.deepcopy(answer)
        populated,retained=_partition_financial_observations(answer)
        self.assertEqual(answer,original);self.assertEqual(populated,[reported]);self.assertIs(populated[0],reported)
        self.assertEqual(retained[0]['status'],'missing_numeric_support');self.assertNotIn('value',retained[0])
        self.assertEqual(retained[0]['classification_source_refs'],missing['classification_source_refs'])
        self.assertEqual(_reconstruction_comparison([dict(id='candidate',row_id='industrial_da',period_id='2025-FY',value=12)],[])[0]['status'],'unresolved')
        with self.assertRaisesRegex(ValueError,'industrial_da 2025-FY'):
            _partition_financial_observations(dict(observations=[dict(missing,classification_basis='')]))

    def test_missing_required_anchor_still_blocks_the_shared_compiler(self):
        from company_initiation.forecast_construction.integrated import build_integrated_spec
        from company_initiation.historic_construction.workflow import _partition_financial_observations
        data=different_period_company();data['historical'].pop('da')
        data['observations']=[o for o in data['observations'] if o['row_id']!='da']
        data['missing_concepts']=_partition_financial_observations(dict(observations=[dict(row_id='da',period_id='2025-FY',terms=[],classification_basis='No supported group D&A anchor.')]))[1]
        with self.assertRaisesRegex(ValueError,'Missing required sourced anchor da:2025'):
            build_integrated_spec(data)

    def test_additive_source_composition_is_derived_but_single_unit_conversion_is_reported(self):
        from company_initiation.historic_construction.evidence import parse_number
        from company_initiation.historic_construction.workflow import _financial_source_classification, _validate_financial_extraction, _bind_mapped_history
        from company_initiation.forecast_construction.periods import assumption_contract
        term=lambda raw,index,weight:dict(source_raw=raw,multiplier=1e-6,weight=weight,
            reference=dict(source_id='original',unit_id='page:5',number_index=index,number_format='dot_decimal'))
        entry=dict(row_id='sales',period_id='2025-FY',unit='GBPm',metric_type='flow',
            terms=[term('1000000',0,1),term('400000',1,-1)])
        _validate_financial_extraction(entry,[dict(raw='1000000'),dict(raw='400000')])
        amount=sum(parse_number(t['source_raw'],'dot_decimal')*t['multiplier']*t['weight'] for t in entry['terms'])
        derived=_financial_source_classification(entry)
        self.assertAlmostEqual(amount,.6);self.assertEqual(derived['status'],'derived_actual')
        self.assertEqual(derived['arithmetic_provenance']['terms'],entry['terms'])
        self.assertIsNot(derived['arithmetic_provenance']['terms'],entry['terms'])
        direct=_financial_source_classification(dict(entry,terms=entry['terms'][:1]))
        self.assertEqual(direct['status'],'reported');self.assertNotIn('arithmetic_provenance',direct)
        period=dict(id='2025-FY',kind='FY',fiscal_year=2025,start='2025-01-01',end='2025-12-31')
        observation=dict(id='derived-source',row_id='sales',period_id=period['id'],fiscal_year=2025,kind='FY',
            value=amount,entity_id='group',basis='reported_scope',source_refs=entry['terms'],**derived)
        data=dict(historical={},model_configuration={});_bind_mapped_history(data,[observation])
        self.assertEqual(data['historical']['sales']['values']['2025'],amount)
        spec=dict(company='SYNTHETIC source composition',currency='GBP',periods=[period],rows=[
            dict(id='sales',unit='GBPm',kind='reported',cells={period['id']:dict(value=amount,**derived)}),
            dict(id='direct_sales',unit='GBPm',kind='reported',cells={period['id']:dict(value=1,**direct)})])
        classifications=assumption_contract(spec)['classifications']
        self.assertEqual(classifications['sales'][period['id']],'derived_history')
        self.assertEqual(classifications['direct_sales'][period['id']],'reported_fact')


class AccountingExtensionConfigurationTests(unittest.TestCase):
    def fixture(self):
        ref=dict(source_id='primary_original',unit_id='page:17')
        unit=dict(ref,text='SYNTHETIC original cash reconciliation and recurring expense note')
        component=dict(id='netted_facility',role='settlement_overdraft',coefficient=-1,included_in_debt=True,
            definition='SYNTHETIC repayment-on-demand balance included in reported debt and netted in cash-flow cash.',source_refs=[ref])
        extra=dict(id='other_recurring_costs',label='Other recurring operating expense',
            definition='SYNTHETIC separate expense included in recurring operating profit.',source_refs=[ref])
        answer=dict(cash_scope=dict(components=[component],method='SYNTHETIC cash-flow cash is gross cash less the separately reported facility balance.',source_refs=[ref]),
            operating_expense_functions=[extra],structural_account_policies=[])
        observations=[dict(row_id='settlement_overdraft',metric_type='stock',value=12),
            dict(row_id='other_recurring_costs',metric_type='flow',value=-3)]
        return answer,observations,[unit]

    def test_cited_extensions_preserve_source_roles_without_mutating_or_inventing_facts(self):
        from company_initiation.historic_construction.workflow import _accounting_extension_configuration
        answer,observations,units=self.fixture();original=copy.deepcopy((answer,observations))
        config=_accounting_extension_configuration(answer,observations,units)
        self.assertEqual((answer,observations),original)
        self.assertEqual(config['cash_scope'],answer['cash_scope'])
        self.assertEqual(config['operating_expense_functions'],answer['operating_expense_functions'])
        self.assertNotIn('historical',config);self.assertNotIn('observations',config)
        # The absence of a mapped amount cannot be replaced by a generated zero.
        self.assertEqual(_accounting_extension_configuration(answer,[],units),config)

    def test_absent_extensions_preserve_legacy_defaults_but_cited_empty_bridge_is_explicit(self):
        from company_initiation.historic_construction.workflow import _accounting_extension_configuration
        self.assertEqual(_accounting_extension_configuration(dict(cash_scope=None,operating_expense_functions=[],structural_account_policies=[]),[],[]),{})
        answer,observations,units=self.fixture();answer['cash_scope']['components']=[]
        config=_accounting_extension_configuration(answer,observations,units)
        self.assertIn('cash_scope',config);self.assertEqual(config['cash_scope']['components'],[])

    def test_cash_scope_rejects_flow_components_fitted_coefficients_and_debt_sign_conflicts(self):
        from company_initiation.historic_construction.workflow import _accounting_extension_configuration
        for change in ({'coefficient':.5},{'coefficient':1},{'included_in_debt':'yes'},{'role':'cash'}):
            answer,observations,units=self.fixture();answer['cash_scope']['components'][0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):_accounting_extension_configuration(answer,observations,units)
        answer,observations,units=self.fixture();observations[0]['metric_type']='flow'
        with self.assertRaisesRegex(ValueError,'closing stock'):_accounting_extension_configuration(answer,observations,units)

    def test_unavailable_citations_duplicates_and_existing_role_collisions_are_rejected(self):
        from company_initiation.historic_construction.workflow import _accounting_extension_configuration
        for mode in ('uncited','outside_context','duplicate_cash','duplicate_function','canonical_role','stock_cost'):
            answer,observations,units=self.fixture()
            if mode=='uncited':answer['cash_scope']['source_refs']=[]
            elif mode=='outside_context':units=[]
            elif mode=='duplicate_cash':answer['cash_scope']['components'].append(copy.deepcopy(answer['cash_scope']['components'][0]))
            elif mode=='duplicate_function':answer['operating_expense_functions']*=2
            elif mode=='canonical_role':answer['operating_expense_functions'][0]['id']='sales'
            else:observations[1]['metric_type']='stock'
            with self.subTest(mode=mode),self.assertRaises(ValueError):_accounting_extension_configuration(answer,observations,units)

    def test_structural_presentation_policy_retains_citation_without_reported_zero(self):
        from company_initiation.historic_construction.workflow import _accounting_extension_configuration
        answer,observations,units=self.fixture()
        policy=dict(role='other_revenue',treatment='included_in_role',included_in=['sales'],
            definition='SYNTHETIC total revenue is presented within the sales line.',source_refs=[dict(source_id='primary_original',unit_id='page:17')])
        answer['structural_account_policies']=[policy]
        config=_accounting_extension_configuration(answer,observations,units)
        self.assertEqual(config['structural_account_policies'],[policy]);self.assertNotIn('value',config['structural_account_policies'][0])
        answer['structural_account_policies'].append(copy.deepcopy(policy))
        with self.assertRaisesRegex(ValueError,'Duplicate structural'):_accounting_extension_configuration(answer,observations,units)

    def test_stage_validation_uses_engine_structural_domains_without_saving_normalized_zeros(self):
        from company_initiation.historic_construction.workflow import _accounting_extension_configuration
        answer,observations,units=self.fixture();data=different_period_company()
        original=copy.deepcopy(data)
        config=_accounting_extension_configuration(answer,observations,units,company_data=data)
        self.assertEqual(data,original);self.assertNotIn('historical',config)
        policy=dict(role='cash',treatment='inactive_stage',included_in=[],definition='SYNTHETIC invalid attempt to remove an essential account',source_refs=[dict(source_id='primary_original',unit_id='page:17')])
        answer['structural_account_policies']=[policy]
        with self.assertRaisesRegex(ValueError,'Unsupported or uncited structural'):
            _accounting_extension_configuration(answer,observations,units,company_data=data)
        policy.update(role='other_revenue',treatment='included_in_role',included_in=['sales'])
        data['historical']['other_revenue']['values']['2025']=1
        with self.assertRaisesRegex(ValueError,'conflicts with a nonzero'):
            _accounting_extension_configuration(answer,observations,units,company_data=data)

    def cashflow_fixture(self):
        answer,observations,units=self.fixture();ref=dict(source_id='primary_original',unit_id='page:17')
        def component(role,classification,equity_role,asset_role,forecast_policy):
            return dict(role=role,label='SYNTHETIC '+role,cashflow_section='cff',classification=classification,
                equity_role=equity_role,asset_role=asset_role,forecast_policy=forecast_policy,
                definition='SYNTHETIC separately reported signed cash movement with the stated counterpart.',source_refs=[ref])
        answer['cashflow_presentation']=dict(components=[
            component('issuance_cash','ordinary_equity_issuance','share_capital',None,'existing_issuance_controls'),
            component('preferred_issuance','noncommon_equity_issuance','retained_earnings',None,'no_new_transaction'),
            component('preferred_distribution','noncommon_equity_distribution','retained_earnings',None,'hold_latest_annual'),
            component('treasury_investments_cf','investment_movement',None,'short_investments','no_new_transaction')],
            method='SYNTHETIC company cash-flow classification; equity claims are included in retained earnings.',source_refs=[ref],
            noncommon_equity_claim_role='preferred_equity')
        answer['financial_contracts']=dict(adjusted_earnings=dict(basic_earnings_adjustment=dict(annual_amount=-7,
            amounts_by_period=[],historical=[],method='SYNTHETIC accrued coupon net of tax, independently disclosed from paid cash.',source_refs=[ref])))
        data=different_period_company()
        for role,amount in [('issuance_cash',11),('preferred_issuance',30),('preferred_distribution',-4),('treasury_investments_cf',5),('preferred_equity',90)]:
            observations.append(dict(row_id=role,metric_type='stock' if role=='preferred_equity' else 'flow',value=amount))
            data['historical'][role]=dict(values={'2025':amount},sources={'2025':[ref]})
        return answer,observations,units,data

    def test_cashflow_policy_preserves_distinct_cash_equity_and_eps_concepts(self):
        from company_initiation.historic_construction.workflow import _accounting_extension_configuration
        answer,observations,units,data=self.cashflow_fixture();before=copy.deepcopy((answer,observations,data))
        config=_accounting_extension_configuration(answer,observations,units,company_data=data)
        self.assertEqual(config['cashflow_presentation'],answer['cashflow_presentation'])
        self.assertEqual((answer,observations,data),before)
        self.assertEqual(next(o['value'] for o in observations if o['row_id']=='preferred_distribution'),-4)
        self.assertEqual(answer['financial_contracts']['adjusted_earnings']['basic_earnings_adjustment']['annual_amount'],-7)
        self.assertNotIn('historical',config);self.assertNotIn('financial_contracts',config)
        answer['cashflow_presentation']=None
        self.assertNotIn('cashflow_presentation',_accounting_extension_configuration(answer,observations,units,company_data=data))

    def test_cashflow_policy_rejects_duplicate_roles_wrong_temporal_types_and_missing_evidence(self):
        from company_initiation.historic_construction.workflow import _accounting_extension_configuration
        for mode in ('duplicate','stock_transaction','flow_claim','uncited','uncited_eps','wrong_section','debt_counterpart'):
            answer,observations,units,data=self.cashflow_fixture();policy=answer['cashflow_presentation']
            if mode=='duplicate':policy['components'].append(copy.deepcopy(policy['components'][0]))
            elif mode=='stock_transaction':next(o for o in observations if o['row_id']=='preferred_distribution')['metric_type']='stock'
            elif mode=='flow_claim':next(o for o in observations if o['row_id']=='preferred_equity')['metric_type']='flow'
            elif mode=='uncited':policy['source_refs']=[]
            elif mode=='uncited_eps':answer['financial_contracts']['adjusted_earnings']['basic_earnings_adjustment']['source_refs']=[]
            elif mode=='wrong_section':policy['components'][1]['cashflow_section']='cfo'
            else:policy['components'][1]['equity_role']='nonlease_debt'
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                _accounting_extension_configuration(answer,observations,units,company_data=data)


class ResearchEngineContractCaptureTests(unittest.TestCase):
    def journal(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        return SimpleNamespace(assert_runtime_unchanged=Mock(),artifact=Mock())

    def test_engine_contract_is_captured_and_audited_before_research(self):
        from company_initiation.historic_construction.workflow import _capture_research_engine_contract
        journal=self.journal();roles=dict(group_roles=['sales'],source_sha256='synthetic')
        with patch('company_initiation.historic_construction.model_contract.integrated_role_contract',return_value=roles):
            contract=_capture_research_engine_contract(journal)
        self.assertEqual(journal.assert_runtime_unchanged.call_count,2)
        self.assertTrue(contract['scaffold'].startswith('def historical_model('))
        self.assertEqual(contract['roles'],roles)
        journal.artifact.assert_called_once_with('engine_contract.json',contract)

    def test_empty_or_changing_engine_contract_is_not_accepted(self):
        from company_initiation.historic_construction.workflow import _capture_research_engine_contract
        from company_initiation.shared_ai import AIError
        journal=self.journal()
        with patch('company_initiation.historic_construction.model_contract.integrated_role_contract',return_value=dict(group_roles=[])),self.assertRaisesRegex(ValueError,'cannot begin paid'):
            _capture_research_engine_contract(journal)
        journal.artifact.assert_not_called()
        journal=self.journal();journal.assert_runtime_unchanged.side_effect=[None,AIError('Source changed during capture')]
        with self.assertRaisesRegex(AIError,'Source changed'):_capture_research_engine_contract(journal)
        journal.artifact.assert_not_called()


class MonetarySalesIdentityTests(unittest.TestCase):
    def fixture(self):
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.forecast_construction.integrated import integrated_role_contract
        from company_initiation.historic_construction.workflow import _materialize_financial_observations
        source=dict(id='primary',category='financial_reports',sha256='synthetic-original')
        unit=dict(source_id='primary',unit_id='page:1',text='SYNTHETIC FY2025: sales GBP100m; currency contribution 2.5%; sales backlog GBP40m.',
            numbers=[dict(index=0,raw='100'),dict(index=1,raw='2.5%'),dict(index=2,raw='40')])
        store=SourceStore(Path('.'));store.sources=[source];store._units={'primary':{'page:1':unit}}
        periods=[dict(id='2025-FY',fiscal_year=2025,kind='FY',start='2024-07-01',end='2025-06-30')]
        roles=integrated_role_contract()
        def observation(index,role,kind,measure):
            ref=dict(source_id='primary',unit_id='page:1')
            return dict(row_id=role,label=['Revenue','Currency contribution','Sales backlog'][index],period_id='2025-FY',
                unit=measure,metric_type=kind,entity_id='group',basis='Original statutory reporting',
                definition_id=['revenue','currency_growth_contribution','closing_sales_backlog'][index],scope='group',
                terms=[dict(reference=dict(ref,number_index=index,number_format='dot_decimal'),source_raw=unit['numbers'][index]['raw'],multiplier=1,weight=1)],
                rounding_increment=0,restatement='original',restatement_vintage=None,
                classification_basis='Explicit synthetic original table labels and units.',classification_source_refs=[ref])
        answer=dict(observations=[observation(0,'sales','flow','GBPm'),observation(1,'sales','ratio','ratio')],gaps=[],reporting_changes=[])
        def materialize(value):
            return _materialize_financial_observations(value,store=store,catalog={'primary':source},periods=periods,
                currency='GBP',roles=roles,segments=[],evidence=[unit],primary_only=True)
        return answer,materialize,observation,dict(periods=periods,evidence=[unit],engine_contract=dict(roles=roles))

    def test_monetary_revenue_and_separate_source_ratio_keep_independent_values(self):
        answer,materialize,_,_=self.fixture();answer['observations'][1]['row_id']='currency_growth_contribution'
        facts=materialize(answer)
        self.assertEqual([f['value'] for f in facts],[100,.025])
        self.assertEqual([f['metric_type'] for f in facts],['flow','ratio'])
        self.assertEqual(facts[1]['source_refs'][0]['raw'],'2.5%')

    def test_ratio_and_stock_cannot_occupy_monetary_sales_identity(self):
        from company_initiation.historic_construction.workflow import _FinancialMappingValidationError
        for role,kind,measure,index in [('sales','ratio','ratio',1),('legacy_division_sales','ratio','ratio',1),
                ('sales','stock','GBPm',2),('sales','flow','ratio',1)]:
            answer,materialize,observation,_=self.fixture();entry=observation(index,role,kind,measure)
            answer['observations']=[entry];before=copy.deepcopy(answer)
            with self.subTest(role=role,kind=kind,unit=measure),self.assertRaises(_FinancialMappingValidationError) as caught:
                materialize(answer)
            self.assertEqual(caught.exception.invalid_entries[0]['allowed_fields'],['row_id'])
            self.assertEqual(answer,before)

    def test_sales_presence_requires_a_monetary_flow_not_a_growth_or_stock_fact(self):
        from company_initiation.historic_construction.workflow import _financial_fact_families, _validate_disclosure_coverage
        requirement=[dict(period_id='2025-FY',family='sales')]
        for role,kind,measure in [('sales','ratio','ratio'),('segment_sales','ratio','ratio'),('sales','stock','GBPm'),
                ('sales','flow','shares_m'),('sales','flow','ratio')]:
            fact=dict(row_id=role,period_id='2025-FY',metric_type=kind,unit=measure,value=.025)
            with self.subTest(role=role,kind=kind,unit=measure):
                self.assertNotIn('sales',_financial_fact_families(fact,{}))
                with self.assertRaisesRegex(ValueError,'coverage'):_validate_disclosure_coverage([fact],requirement,{})
        for currency in ('GBP','JPY'):
            fact=dict(row_id='legacy_segment_sales',period_id='2025-FY',metric_type='flow',unit=currency+'m',value=100)
            self.assertEqual(_validate_disclosure_coverage([fact],requirement,{}),[fact])

    def test_bounded_identity_patch_preserves_exact_numbers_and_all_other_fields(self):
        from company_initiation.historic_construction.workflow import _financial_mapping_stage, _financial_mapping_schema
        for forbidden in (False,True):
            answer,materialize,_,context=self.fixture();before=copy.deepcopy(answer);outer=self
            class Journal:
                configuration={'limits':{'repairs':1}}
                def artifact(self,*args):pass
                def stage(self,stage,prompt,payload,schema,validate):return validate(copy.deepcopy(answer))
                def ask(self,stage,prompt,payload,schema,attempt):
                    outer.assertEqual(payload['prior_answer'],before)
                    target=payload['repair']['targets'][0]
                    outer.assertEqual(target['entry_index'],1);outer.assertEqual(target['allowed_fields'],['row_id'])
                    entry=copy.deepcopy(payload['prior_answer']['observations'][1]);entry['row_id']='currency_growth_contribution'
                    if forbidden:entry['terms'][0]['weight']=2
                    return dict(patches=[dict(entry_id=target['entry_id'],entry_index=1,entry_digest=target['entry_digest'],observation=entry)],
                        additions=[],gap_additions=[],reporting_change_additions=[])
            def validate(value):materialize(value);return value
            with self.subTest(forbidden_numeric_change=forbidden):
                if forbidden:
                    with self.assertRaisesRegex(ValueError,'frozen identity/metadata'):
                        _financial_mapping_stage(Journal(),'company_year_mapping','Synthetic original',context,_financial_mapping_schema(['2025-FY']),validate)
                else:
                    revised=_financial_mapping_stage(Journal(),'company_year_mapping','Synthetic original',context,_financial_mapping_schema(['2025-FY']),validate)
                    self.assertEqual(revised['observations'][0],before['observations'][0])
                    self.assertEqual({k:v for k,v in revised['observations'][1].items() if k!='row_id'},
                        {k:v for k,v in before['observations'][1].items() if k!='row_id'})
                    self.assertEqual(materialize(revised)[1]['value'],.025)
                self.assertEqual(answer,before)


class CompanyReportedVAConstructionTests(unittest.TestCase):
    """Fresh synthetic archives exercise the same VA compiler, without providers."""

    def fixture(self, root, *, currency='USD', year_end='12-31', reorganized=False):
        from openpyxl import Workbook
        from company_initiation.historic_construction.evidence import SourceStore,inventory_local_sources
        from company_initiation.historic_construction.periods import build_periods
        archive=root/'company';folder=archive/'visible_alpha';folder.mkdir(parents=True)
        path=folder/'Company Reported.xlsx';book=Workbook();sheet=book.active;sheet.title='Reported'
        sheet['B1']='SYNTHETIC reported company; fiscal year ends '+year_end
        sheet['D3']='Company Reported'
        labels=['FY-2024','FY-2024','1HFY-2024','FY-2025','FY-2025E','FY-2026']
        series=['VA Actuals','Filings','Filings','VA Actuals','Consensus','Filings']
        for col,(label,kind) in enumerate(zip(labels,series),7):
            sheet.cell(4,col,label);sheet.cell(5,col,kind)
        sheet.cell(5,5,'Units')
        metrics=[('Group sales',[99,100,40,110,9999,8888]),('Group cash',[8,None,4,9,9999,8888])]
        metrics+=([('Legacy division sales',[99,100,40,None,None,None]),
                   ('Equipment sales',[None,None,None,70,None,None]),('Services sales',[None,None,None,40,None,None])]
                  if reorganized else [('Manufacturing sales',[99,100,40,110,9999,8888])])
        for row,(label,values) in enumerate(metrics,7):
            sheet.cell(row,4,label);sheet.cell(row,5,currency+'M');sheet.cell(row,6,'Analytics')
            for col,value in enumerate(values,7):
                if value is not None:sheet.cell(row,col,value)
        book.save(path);book.close()
        standard=Workbook();standard.active.title='Unclassified';standard.active['A1']='STANDARDIZED MUST NOT BE USED'
        standard.save(folder/'Standardised.xlsx');standard.close()
        inventory=inventory_local_sources(archive);source=next(s for s in inventory['sources'] if s.get('dataset_role')=='company_reported')
        store=SourceStore(root/'parsed');store.add_local(source,root=archive)
        periods=build_periods([2024,2025,2026],dict(fiscal_year_end=year_end))
        from company_initiation.historic_construction.workflow import VA_SOURCE_POLICY
        segments=([dict(id='equipment',label='Equipment'),dict(id='services',label='Services')] if reorganized
                  else [dict(id='manufacturing',label='Manufacturing')])
        data=dict(company='SYNTHETIC '+currency,currency=currency,history_years=[2024] if year_end=='12-31' else [2024,2025],fiscal_calendar=dict(fiscal_year_end=year_end),
            forecast_basis='reported',segments=segments,corporate={},historical={},observations=[],sources={source['id']:source},
            reporting_changes=[],reporting_bridges=[],entity_versions=[],active_basis_by_period={},
            model_configuration=dict(as_of='2025-10-01',historical_source_policy=VA_SOURCE_POLICY,limitations=[]),
            source_freshness=dict(mode='local_company_reported_va',model_as_of='2025-10-01',discovery_performed=False))
        return archive,source,store,periods,data

    def journal(self, data, *, tamper=False):
        from types import SimpleNamespace
        from company_initiation.historic_construction.initiation import validate_shape
        from company_initiation.shared_runtime import write_json
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        directory=Path(temporary.name);artifacts={};calls=[]
        def artifact(name,value):
            artifacts[name]=copy.deepcopy(value);write_json(directory/name,value)
        def stage(name,prompt,payload,schema,validator):
            calls.append(name)
            if name=='company_va_row_mapping':
                decisions=[]
                for row in payload['target_rows']:
                    label=row['label'];entity={'Legacy':'legacy','Equipment':'equipment','Services':'services','Manufacturing':'manufacturing'}.get(label.split()[0],'group')
                    role='cash' if 'cash' in label.lower() else 'sales'
                    if entity!='group':role=entity+'_'+role
                    version=dict(row_id=role,label=label,entity_id=entity,
                        statement_section='balance' if role=='cash' else 'income' if entity=='group' else 'segment',
                        financial_role=role if entity=='group' else role[len(entity)+1:],
                        entity_kind='group' if entity=='group' else 'legacy_segment' if entity=='legacy' else 'current_segment',
                        measure='money',metric_type='stock' if role=='cash' else 'flow',basis='legacy' if entity=='legacy' else 'reported',
                        definition_id=role,scope=entity,restatement='original',restatement_vintage=None,
                        classification_basis='Synthetic company-reported labelled historical data; no publication-date claim',
                        definition_status='source_defined',basis_status='period_defined',
                        period_basis='closing' if role=='cash' else 'source_period',period_kinds=[],
                        effective_from=None,effective_to='2024-05-31' if tamper else None,
                        version_refs=[row['source_ref']] if tamper else [],polarity=1)
                    decisions.append(dict(row_key=row['row_key'],action='map',versions=[version]))
                answer=dict(decisions=decisions,gaps=[])
            elif name=='company_va_core_review':
                answer=dict(checks=[dict(row_key=row['row_key'],status='pass',detail='Synthetic semantic review',
                    source_refs=[row['source_ref']]) for row in payload['target_rows']],summary='Synthetic essential review')
            elif name=='company_va_history_review':
                from company_initiation.historic_construction.workflow import _HISTORY_GATE_TOPICS
                ref={k:payload['evidence'][0][k] for k in ('source_id','unit_id')}
                answer=dict(checks=[dict(topic=topic,status='pass',detail='Synthetic review of '+topic,source_refs=[ref]) for topic in _HISTORY_GATE_TOPICS],summary='Synthetic scoped review')
            else:raise AssertionError('Unexpected PDF/online research: '+name)
            validate_shape(answer,schema);validator(answer);return answer
        journal=SimpleNamespace(stage=stage,artifact=artifact,artifacts=artifacts,calls=calls,directory=directory,
            state={'artifacts':{}},save=lambda:None,progress=None)
        def patch_stage(name,prompt,payload,schema,*,assess,patch_contract,apply_patch,checkpoint,initial_candidate=None,**kwargs):
            answer=copy.deepcopy(initial_candidate) if initial_candidate is not None else journal.stage(name,prompt,payload,schema,lambda a:a)
            report=assess(answer)
            checkpoint(answer,report)
            if report['issues']:raise ValueError('; '.join(i['detail'] for i in report['issues']))
            return answer
        journal.patch_stage=patch_stage
        return journal

    def test_prefer_filing_fallback_missing_and_reject_estimates_standardized_and_future(self):
        with tempfile.TemporaryDirectory() as temp:
            _,source,store,periods,data=self.fixture(Path(temp))
            rows=store.company_reported_rows([source['id']],periods,as_of=data['model_configuration']['as_of'])
            sales=next(row for row in rows if row['label']=='Group sales')
            actual=next(cell for cell in sales['cells'] if cell['period_id']=='2024-FY')
            self.assertEqual(actual['source_raw'],'100');self.assertEqual(actual['series'],'Filings')
            cash=next(row for row in rows if row['label']=='Group cash')
            actual=next(cell for cell in cash['cells'] if cell['period_id']=='2024-FY')
            self.assertEqual(actual['source_raw'],'8');self.assertEqual(actual['series'],'VA Actuals')
            self.assertFalse(any(cell['source_raw'] in ('9999','8888') for row in rows for cell in row['cells']))
            self.assertFalse(any('STANDARDIZED' in row['label'] for row in rows))

    def test_fresh_same_compiler_two_currencies_calendars_and_segment_reorganisation(self):
        from company_initiation.historic_construction.workflow import _va_history_inputs,_review_va_history,combined_history_review_current
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        from company_initiation.historic_construction.model_excel import write_historical_output
        for currency,end,reorg in [('USD','12-31',False),('JPY','03-31',True)]:
            with self.subTest(currency=currency),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);_,source,store,periods,data=self.fixture(root,currency=currency,year_end=end,reorganized=reorg)
                journal=self.journal(data)
                with patch('urllib.request.urlopen',side_effect=AssertionError('No network')):
                    evidence=_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,dict(roles=integrated_role_contract()))
                    _review_va_history(journal,data,evidence)
                    out=root/'export';out.mkdir();written=write_historical_output(out,data)
                self.assertTrue((out/written['workbook']).is_file())
                self.assertTrue(combined_history_review_current(data))
                self.assertFalse(data['combined_history_review']['independent_primary_verification'])
                self.assertEqual(data['historical']['sales']['values']['2024'],100.)
                self.assertTrue(all(o['source_refs'][0].get('cell') for o in data['observations']))
                self.assertTrue(all(o['source_dataset']=='company_reported' for o in data['observations']))
                half=next(o for o in data['observations'] if o['row_id']=='sales' and o['period_id']=='2024-H1')
                self.assertEqual(half['end'],'2024-06-30' if end=='12-31' else '2023-09-30')
                if reorg:
                    self.assertIn('legacy_sales',data['historical']);self.assertIn('equipment_sales',data['historical'])
                    self.assertNotIn('2024',data['historical']['equipment_sales']['values'])
                    self.assertEqual(data['historical']['services_sales']['values']['2025'],40.)

    def test_row_mapping_cannot_silently_drop_interim_or_annual_cells(self):
        from company_initiation.historic_construction.workflow import _va_history_inputs
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        with tempfile.TemporaryDirectory() as temp:
            _,source,store,periods,data=self.fixture(Path(temp))
            _va_history_inputs(self.journal(data,tamper=True),data,store,data['sources'],[source['id']],periods,dict(roles=integrated_role_contract()))
            self.assertTrue(data['model_configuration']['historical_mapping_issues'])
            self.assertTrue(data['model_configuration']['va_source_rows'])

    def test_va_mapping_starts_with_latest_actuals_and_retains_legacy_bases(self):
        from company_initiation.historic_construction.workflow import _va_history_inputs
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        with tempfile.TemporaryDirectory() as temp:
            _,source,store,periods,data=self.fixture(Path(temp),currency='JPY',year_end='03-31',reorganized=True)
            rows=store.company_reported_rows([source['id']],periods,as_of=data['model_configuration']['as_of'])
            self.assertEqual(rows[-1]['label'],'Legacy division sales')
            self.assertTrue(all(row['cells'][0]['period_id']=='2025-FY' for row in rows[:-1]))
            journal=self.journal(data);original=journal.stage;requests=[]
            def stage(name,prompt,payload,*args):
                requests.append((prompt,copy.deepcopy(payload)))
                return original(name,prompt,payload,*args)
            journal.stage=stage
            _va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,dict(roles=integrated_role_contract()))
            prompt,payload=requests[0]
            self.assertIn('work backwards',prompt)
            self.assertEqual(payload['historical_anchor']['latest_actual_period_id'],'2025-FY')
            self.assertEqual(payload['historical_anchor']['latest_annual_period_id'],'2025-FY')
            self.assertEqual(payload['historical_anchor']['current_segment_ids'],['equipment','services'])
            self.assertEqual(payload['target_rows'][0]['representation_examples'][0]['period_id'],'2025-FY')
            self.assertEqual(data['historical']['legacy_sales']['values'],{'2024':100.})
            self.assertNotIn('2024',data['historical']['equipment_sales']['values'])
            self.assertTrue(all(not row['latest_period_id'].startswith('2026') for row in payload['target_rows']))
            self.assertEqual(journal.artifacts['va_history_bindings.json']['historical_anchor'],
                             data['model_configuration']['historical_anchor'])

    def test_history_command_exports_stops_and_only_explicit_resume_reuses_inputs(self):
        import builtins
        from openpyxl import load_workbook
        from company_initiation.__main__ import main
        from company_initiation.historic_construction.workflow import _va_history_inputs,_review_va_history
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive,source,store,periods,data=self.fixture(root,currency='JPY',year_end='03-31',reorganized=True)
            journal=self.journal(data)
            evidence=_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,dict(roles=integrated_role_contract()))
            _review_va_history(journal,data,evidence)
            inputs=root/'fixture_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
            (root/'pyproject.toml').write_text('[tool.research-platform]\n',encoding='utf-8')
            original_import=builtins.__import__
            def guarded_import(name,*args,**kwargs):
                if name.startswith(('company_initiation.forecast_construction','company_initiation.dcf_construction')):
                    raise AssertionError('Historical command imported a downstream stage: '+name)
                return original_import(name,*args,**kwargs)
            argv=['company_initiation','construct-history',data['company'],'--sources',str(archive),
                  '--years','2024','2025','--as-of','2025-10-01']
            with patch('company_initiation.__main__.find_project_root',return_value=root), \
                 patch('company_initiation.historic_construction.workflow.research_company_inputs',return_value=inputs) as research, \
                 patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No network')), \
                 patch('builtins.__import__',side_effect=guarded_import),patch('builtins.print'):
                with patch('sys.argv',argv):self.assertEqual(main(),0)
                first=next((root/'outputs').glob('construct_history_*/record.json'))
                first_bytes=first.read_bytes();first_record=json.loads(first_bytes)
                with patch('sys.argv',argv+['--resume',str(first.parent)]):self.assertEqual(main(),0)
                self.assertEqual(research.call_count,1)
                self.assertEqual(first.read_bytes(),first_bytes)
                with patch('sys.argv',argv):self.assertEqual(main(),0)
                self.assertEqual(research.call_count,2)
            records=[json.loads(path.read_text(encoding='utf-8')) for path in (root/'outputs').glob('construct_history_*/record.json')]
            self.assertEqual(len(records),3)
            self.assertEqual(len({record['budget']['allowance_period_id'] for record in records}),2)
            self.assertEqual(first_record['status'],'historical_complete_provisional')
            self.assertEqual(set(first_record['stage_outputs']),{'historical'})
            for record in records:
                self.assertEqual(record['completion_scope'],'historical_only')
                self.assertEqual(record['budget']['remaining_usd'],20)
                run=Path(record['directory'])
                validation=json.loads((run/'historical_validation.json').read_text(encoding='utf-8'))
                self.assertFalse(validation['forecast_started']);self.assertFalse(validation['dcf_started'])
                self.assertEqual(validation['ai_calls_in_finalization'],0)
                self.assertFalse((run/'forecast.json').exists());self.assertFalse((run/'forecast_model.xlsx').exists())
                self.assertFalse((run/'dcf_model.xlsx').exists())
                book=load_workbook(run/'historical_model.xlsx',data_only=False)
                try:
                    self.assertNotIn('Assumptions',book.sheetnames);self.assertNotIn('Valuation',book.sheetnames)
                    labels=[str(book['Model'].cell(5,col).value) for col in range(4,book['Model'].max_column+1)]
                    self.assertTrue(labels[0].startswith('2024'))
                    self.assertFalse(any(label.startswith('2026') for label in labels))
                finally:book.close()
            self.assertEqual(len(list((root/'forecasting_engine/company_initiation/logs').glob('*.log'))),3)

    def test_latest_anchor_keeps_current_interim_separate_from_latest_completed_annual(self):
        from openpyxl import load_workbook
        from company_initiation.historic_construction.evidence import SourceStore,inventory_local_sources
        from company_initiation.historic_construction.workflow import _va_history_inputs
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive,source,_,periods,data=self.fixture(root)
            path=archive/source['local_path'];book=load_workbook(path)
            book.active['I4']='1HFY-2025';book.save(path);book.close()
            source=next(s for s in inventory_local_sources(archive)['sources'] if s.get('dataset_role')=='company_reported')
            store=SourceStore(root/'new_parse');store.add_local(source,root=archive);data['sources']={source['id']:source}
            journal=self.journal(data)
            _va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,dict(roles=integrated_role_contract()))
            anchor=data['model_configuration']['historical_anchor']
            self.assertEqual(anchor['latest_actual_period_id'],'2025-H1')
            self.assertEqual(anchor['latest_annual_period_id'],'2024-FY')
            row=journal.artifacts['va_history_bindings.json']['rows'][0]
            self.assertEqual(row['cells'][0]['period_id'],'2025-H1')
            self.assertEqual(data['historical']['sales']['values'],{'2024':100.})
            self.assertFalse(any(o['period_id'] in ('2025-FY','2026-FY') for o in data['observations']))

    def test_historical_finalization_rejects_stale_review_and_changed_originals(self):
        from company_initiation.historic_construction.workflow import _va_history_inputs,_review_va_history,complete_historical_model
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive,source,store,periods,data=self.fixture(root)
            journal=self.journal(data)
            evidence=_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,dict(roles=integrated_role_contract()))
            inputs=root/'fixture_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'review is incomplete or stale'):
                complete_historical_model(root,data['company'],archive,inputs)
            _review_va_history(journal,data,evidence)
            inputs.write_text(json.dumps(data),encoding='utf-8')
            raw=archive/source['local_path'];raw.write_bytes(raw.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'Source changed'):
                complete_historical_model(root,data['company'],archive,inputs)
            records=[json.loads(path.read_text()) for path in (root/'outputs').glob('construct_history_*/record.json')]
            self.assertEqual(len(records),2);self.assertTrue(all(record['status']=='incomplete' for record in records))

    def test_local_snapshot_warns_about_freshness_without_claiming_online_or_independent_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            archive,_,_,_,data=self.fixture(Path(temp))
            checks=freshness_checks(data,archive)
            self.assertFalse(any(c['status']=='FAIL' for c in checks))
            self.assertTrue(any(c['name']=='official_release_inventory' and c['status']=='WARNING' for c in checks))
            self.assertTrue(any(c['name']=='independent_primary_verification' and c['status']=='WARNING' for c in checks))
            changed=copy.deepcopy(data);changed['model_configuration']['as_of']='2025-10-02'
            self.assertTrue(any(c['status']=='FAIL' for c in freshness_checks(changed,archive)))

    def test_public_research_entry_uses_va_without_forecast_accounting_notes(self):
        from company_initiation.shared_ai import OpenAIProvider,DEFAULT_MODEL
        from company_initiation.shared_budget import construction_command_budget
        from company_initiation.historic_construction.workflow import research_company_inputs,VA_SOURCE_POLICY
        from company_initiation.historic_construction.evidence import inventory_local_sources
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive,_,_,_,data=self.fixture(root,currency='JPY',year_end='03-31',reorganized=True)
            unrelated=root/'outputs/construct_unrelated';unrelated.mkdir(parents=True)
            (unrelated/'record.json').write_text('Unrelated saved work must not be opened',encoding='utf-8')
            fixture_journal=self.journal(data);stages=[]
            class Provider(OpenAIProvider):
                def __init__(self):super().__init__(api_key='SYNTHETIC-OFFLINE-KEY')
                def complete(self,**kwargs):
                    payload=kwargs['payload'];stage=payload['stage'];stages.append(stage)
                    self.last_response=dict(model=DEFAULT_MODEL,usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[])
                    if stage=='company_va_scope':
                        ref=payload['va']['native_rows'][0]['source_ref']
                        result=dict(currency='JPY',fiscal_year_end='03-31',latest_completed_year=2025,
                            forecast_frequency='half_year',full_statement_frequency='half_year',reporting_basis='reported',
                            segments=data['segments'],corporate_label='Corporate',primary_hierarchy='Divisions',supplementary_dimensions=[],
                            revenue_models=[dict(entity_id=s['id'],method='aggregate_organic',definition='Synthetic disclosure',source_refs=[ref]) for s in data['segments']],
                            driver_map=[],official_indexes=[],source_references=[ref],gaps=[])
                        result['historical_reporting_context']=dict(declarations=[],entity_versions=[],hierarchies=[])
                        return {key:result[key] for key in ('currency','fiscal_year_end','full_statement_frequency','reporting_basis','segments','corporate_label','historical_reporting_context')}|dict(source_refs=[ref],questions=[],source_ids=[])
                    if stage in ('company_va_row_mapping','company_va_history_review'):
                        return fixture_journal.stage(stage,kwargs['instructions'],payload,kwargs['schema'],lambda a:a)
                    raise AssertionError('Unexpected legacy discovery/reconstruction stage: '+stage)
            with patch('company_initiation.historic_construction.workflow.discover_releases',side_effect=AssertionError('No online discovery')), \
                 patch('company_initiation.historic_construction.workflow._validate_driver_references'), \
                 patch('urllib.request.urlopen',side_effect=AssertionError('No network')), \
                 construction_command_budget(root/'outputs',data['company'],20) as budget:
                inputs=research_company_inputs(root,data['company'],archive,as_of='2025-10-01',years=[2024,2025],provider=Provider())
            runs=list((root/'outputs').glob('construct_research_*'));self.assertEqual(len(runs),1)
            run=runs[0];self.assertTrue((run/'historical_model.xlsx').is_file())
            saved=json.loads(inputs.read_text(encoding='utf-8'))
            self.assertEqual(saved['model_configuration']['historical_source_policy'],VA_SOURCE_POLICY)
            self.assertEqual(saved['historical']['sales']['values']['2024'],100.)
            self.assertFalse(saved['source_freshness']['discovery_performed'])
            self.assertNotIn('company_year_mapping',stages);self.assertNotIn('company_year_blind',stages)
            record=json.loads((run/'record.json').read_text(encoding='utf-8'))
            self.assertEqual(record['status'],'research_complete')
            self.assertNotIn('company_accounting_structure',stages)
            self.assertIsNone(record['parent_run'])
            self.assertEqual(record['configuration']['budget_session_id'],budget['allowance_period_id'])
            self.assertIn('historical',record['stage_outputs'])

    def test_local_va_update_reuses_public_source_route_without_online_discovery(self):
        from company_initiation.historic_construction.workflow import update_company_inputs
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive,_,_,_,data=self.fixture(root)
            run=root/'outputs/construct_fixture';run.mkdir(parents=True)
            (run/'company_model_inputs.json').write_text(json.dumps(data),encoding='utf-8')
            previous=dict(configuration=dict(company=data['company'],sources=str(archive),start_year=2018,limits=dict(usd=20)))
            with patch('company_initiation.shared_artifacts.verified_integrated_record',return_value=previous), \
                 patch('company_initiation.historic_construction.workflow.research_company_inputs',return_value=Path('new_inputs')) as research, \
                 patch('company_initiation.historic_construction.workflow.discover_releases',side_effect=AssertionError('No network')):
                result=update_company_inputs(root,run,as_of='2025-10-02')
            self.assertEqual(result,Path('new_inputs'));self.assertEqual(research.call_args.kwargs['start_year'],2018)
            self.assertEqual(research.call_args.kwargs['budget_usd'],20)

    def test_explicit_online_update_checks_new_releases_without_historical_backfill(self):
        from company_initiation.historic_construction.workflow import update_company_inputs
        from company_initiation.shared_ai import OpenAIProvider
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive,_,_,_,data=self.fixture(root)
            run=root/'outputs/construct_fixture';run.mkdir(parents=True)
            (run/'company_model_inputs.json').write_text(json.dumps(data),encoding='utf-8')
            previous=dict(directory=str(run),calls=[],configuration=dict(company=data['company'],sources=str(archive),
                start_year=2018,limits=dict(usd=20,repairs=2,retries=0,calls=None,generated_tokens=None)))
            with patch('company_initiation.shared_artifacts.verified_integrated_record',return_value=previous), \
                 patch('company_initiation.historic_construction.workflow.discover_releases',side_effect=ValueError('Synthetic blocked website')) as discovery, \
                 patch('urllib.request.urlopen',side_effect=AssertionError('No actual network')):
                with self.assertRaisesRegex(ValueError,'blocked website'):
                    update_company_inputs(root,run,as_of='2025-10-02',online=True,provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY'))
            self.assertEqual(discovery.call_args.kwargs['historical_years'],())

    def test_vendor_interim_stock_is_retained_but_not_presented_as_supported_quarterly_statement(self):
        from company_initiation.historic_construction.workflow import _va_history_inputs
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        with tempfile.TemporaryDirectory() as temp:
            _,source,store,periods,data=self.fixture(Path(temp))
            data['model_configuration']['full_statement_frequency']='annual'
            _va_history_inputs(self.journal(data),data,store,data['sources'],[source['id']],periods,dict(roles=integrated_role_contract()))
            cash=next(o for o in data['observations'] if o['row_id']=='cash' and o['period_id']=='2024-H1')
            sales=next(o for o in data['observations'] if o['row_id']=='sales' and o['period_id']=='2024-H1')
            self.assertFalse(cash['eligible']);self.assertTrue(sales['eligible'])

    def test_review_reads_verified_frozen_va_even_when_live_export_is_absent(self):
        from types import SimpleNamespace
        from company_initiation.shared_artifacts import freeze_model_sources
        from company_initiation.historic_construction.workflow import prepare_history_review_context
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);archive,source,_,_,data=self.fixture(root)
            run=root/'review';folder=run/'sources';folder.mkdir(parents=True)
            frozen,_=freeze_model_sources(data,archive,folder)
            (archive/source['local_path']).unlink()
            with patch('urllib.request.urlopen',side_effect=AssertionError('No network')):
                context=prepare_history_review_context(SimpleNamespace(directory=run),data,frozen)
            self.assertTrue(any(u.get('vendor_row',{}).get('section')=='company_reported' for u in context['original_units']))
            frozen_path=Path(frozen[0]['path']);frozen_path.write_bytes(frozen_path.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'source changed'):
                prepare_history_review_context(SimpleNamespace(directory=run),data,frozen)

    def test_default_cli_researches_anew_even_with_old_inputs_for_the_same_years(self):
        from company_initiation.__main__ import main,_run
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);old=root/'outputs/construct_old';old.mkdir(parents=True)
            (root/'pyproject.toml').write_text('[tool.research-platform]\n',encoding='utf-8')
            archive=root/'archive';archive.mkdir()
            saved=dict(history_years=list(range(2018,2026)),model_configuration=dict(as_of='2026-10-31'))
            (old/'company_model_inputs.json').write_text(json.dumps(saved),encoding='utf-8')
            record=dict(directory=str(old),configuration=dict(company='SYNTHETIC source priority',manifest='same'))
            (old/'record.json').write_text(json.dumps(record),encoding='utf-8')
            new=root/'outputs/construct_new';new.mkdir();inputs=new/'company_model_inputs.json';inputs.write_text('{}')
            (new/'record.json').write_text(json.dumps(dict(status='complete_provisional',usage={},issues=[])))
            inventory=dict(manifest_sha256='same',source_manifest_sha256='same',sources=[dict(category='visible_alpha',dataset_role='company_reported')])
            with patch('sys.argv',['company_initiation','construct','SYNTHETIC source priority','--sources',str(archive),'--as-of','2026-10-31']), \
                 patch('company_initiation.__main__._logged_construct',side_effect=_run), \
                 patch('company_initiation.__main__.find_project_root',return_value=root), \
                 patch('company_initiation.historic_construction.evidence.inventory_local_sources',return_value=inventory), \
                 patch('company_initiation.forecast_construction.integrated.verified_integrated_record',return_value=record), \
                 patch('company_initiation.historic_construction.workflow.research_company_inputs',return_value=inputs) as research, \
                 patch('company_initiation.historic_construction.workflow.ensure_company_history_research',return_value=inputs), \
                 patch('company_initiation.historic_construction.workflow.update_company_inputs') as update, \
                 patch('company_initiation.forecast_construction.integrated.construct_integrated',return_value=new), \
                 patch('company_initiation.shared_ai.format_usage',return_value=''), \
                 patch('company_initiation.shared_ai.format_stage_usage',return_value=''),patch('builtins.print'):
                self.assertEqual(main(),0)
            research.assert_called_once();update.assert_not_called()
            self.assertTrue(research.call_args.kwargs['fresh'])
            self.assertEqual(research.call_args.kwargs['start_year'],2018)


class VAMappingRepairTests(unittest.TestCase):
    """Typed mapping/patch regressions and local archived-response replays; no API."""
    fixture=CompanyReportedVAConstructionTests.fixture
    journal=CompanyReportedVAConstructionTests.journal

    def case(self, **kwargs):
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);archive,source,store,periods,data=self.fixture(root,**kwargs)
        rows=store.company_reported_rows([source['id']],periods,as_of=data['model_configuration']['as_of'])
        evidence=store.read_documents([dict(source_id=source['id'],unit_id=next(iter(store._units[source['id']])))],historical_years={p['fiscal_year'] for p in periods})
        return root,archive,source,store,periods,data,rows,evidence,dict(roles=integrated_role_contract())

    def candidate(self,data,rows):
        from company_initiation.historic_construction.workflow import _va_schema
        targets=[dict(row_key=r['row_key'],label=r['label'],source_ref=dict(source_id=r['source_id'],unit_id=r['unit_id'])) for r in rows]
        schema,_=_va_schema([r['row_key'] for r in rows],['money'])
        return self.journal(data).stage('company_va_row_mapping','fixture',dict(target_rows=targets),schema,lambda a:a)

    def test_units_are_source_evidenced_and_literal_percent_is_converted_once(self):
        from company_initiation.historic_construction.evidence import va_unit_options,va_cell_multiplier,excel_fraction_percent
        for name in ('EURM','EUR_m','EUR millions'):
            # Arbitrary model-unit spellings are not returned by the AI anymore;
            # source formats accept documented native conventions only.
            if name=='EURM':self.assertEqual(va_unit_options(name,'EUR')[0]['unit'],'EURm')
        self.assertEqual(va_unit_options('\u20acM','EUR')[0]['multiplier'],1)
        self.assertEqual(va_unit_options('EURAbs','EUR')[1]['unit'],'EUR_per_share')
        self.assertEqual(va_unit_options('M#','EUR')[0]['unit'],'shares_m')
        self.assertEqual(va_unit_options('USDM','EUR'),[])
        option=va_unit_options('%','EUR')[0]
        for raw,fmt,expected in [('5','0.0"%"',.01),('0.05','0.0%',1.),('5%','General',1.)]:
            self.assertEqual(va_cell_multiplier(option,dict(source_raw=raw,display_format=fmt)),expected)
        self.assertFalse(excel_fraction_percent('0.0"%"'));self.assertTrue(excel_fraction_percent('0.0%'))

    def test_missing_rows_are_patchable_but_valid_fields_are_frozen(self):
        from company_initiation.historic_construction.workflow import _va_assess,_va_schema,_va_patch_contract,_va_apply_patch
        from company_initiation.shared_runtime import digest
        _,_,_,store,periods,data,rows,evidence,contract=self.case()
        original=self.candidate(data,rows);missing=original['decisions'].pop()
        report=_va_assess(original,rows,rows,data,store,data['sources'],periods,contract,evidence)
        _,schema=_va_schema([r['row_key'] for r in rows],['money'])
        rules=_va_patch_contract(original,report,schema)
        self.assertEqual(len(report['issues']),1)
        bad=dict(changes=[dict(row_key=original['decisions'][0]['row_key'],expected_digest=digest(original['decisions'][0]),path='versions.0.entity_id',value='corporate')])
        before=copy.deepcopy(original)
        with self.assertRaisesRegex(ValueError,'frozen'):_va_apply_patch(original,bad,rules)
        self.assertEqual(original,before)
        invalid=copy.deepcopy(missing);invalid['versions'][0]['polarity']='wrong type'
        with self.assertRaises(ValueError):
            _va_apply_patch(original,dict(changes=[dict(row_key=missing['row_key'],expected_digest=None,path='$',value=invalid)]),rules)
        self.assertEqual(original,before)
        fixed=_va_apply_patch(original,dict(changes=[dict(row_key=missing['row_key'],expected_digest=None,path='$',value=missing)]),rules)
        self.assertEqual(fixed['decisions'][:len(before['decisions'])],before['decisions'])
        self.assertFalse(_va_assess(fixed,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])
        with self.assertRaisesRegex(ValueError,'digest'):
            _va_apply_patch(original,dict(changes=[dict(row_key=missing['row_key'],expected_digest='forged',path='$',value=missing)]),rules)

    def test_group_entity_repairs_cannot_touch_source_definition_or_values(self):
        from company_initiation.historic_construction.workflow import _va_assess,_va_schema,_va_patch_contract,_va_apply_patch
        from company_initiation.shared_runtime import digest
        _,_,_,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows);sales=next(d for d in candidate['decisions'] if d['versions'][0]['row_id']=='sales')
        sales['versions'][0].update(entity_id='corporate',entity_kind='corporate')
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        _,schema=_va_schema([r['row_key'] for r in rows],['money']);rules=_va_patch_contract(candidate,report,schema)
        patch=dict(changes=[dict(row_key=sales['row_key'],expected_digest=digest(sales),path='versions.0.'+field,value=value)
                            for field,value in [('entity_id','group'),('entity_kind','group')]])
        fixed=_va_apply_patch(candidate,patch,rules)
        verified=_va_assess(fixed,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertFalse(verified['issues'])
        self.assertEqual(next(f['value'] for f in verified['facts'] if f['row_id']=='sales' and f['period_id']=='2024-FY'),100)
        patch['changes'][0]['path']='versions.0.basis'
        with self.assertRaisesRegex(ValueError,'frozen'):_va_apply_patch(candidate,patch,rules)

    def test_literal_percent_cells_and_native_fraction_cells_materialize_to_same_ratio(self):
        from openpyxl import load_workbook
        from company_initiation.historic_construction.evidence import SourceStore,inventory_local_sources
        from company_initiation.historic_construction.workflow import _va_assess
        root,archive,source,_,periods,data,_,_,contract=self.case()
        path=archive/source['local_path'];book=load_workbook(path);sheet=book.active
        for row,label,value,fmt in [(12,'Literal ratio',5.,'0.0"%"'),(13,'Native fraction ratio',.05,'0.0%')]:
            sheet.cell(row,4,label);sheet.cell(row,5,'%');sheet.cell(row,6,'Analytics')
            sheet.cell(row,7,value).number_format=fmt;sheet.cell(row,8,value).number_format=fmt
        book.save(path);book.close()
        source=next(s for s in inventory_local_sources(archive)['sources'] if s.get('dataset_role')=='company_reported')
        store=SourceStore(root/'ratios');store.add_local(source,root=archive);data['sources']={source['id']:source}
        rows=[r for r in store.company_reported_rows([source['id']],periods,as_of=data['model_configuration']['as_of']) if 'ratio' in r['label']]
        evidence=store.read_documents([dict(source_id=source['id'],unit_id=next(iter(store._units[source['id']])))],historical_years={2024})
        candidate=self.candidate(data,rows)
        for i,d in enumerate(candidate['decisions']):
            d['versions'][0].update(measure='ratio',metric_type='ratio',financial_role=None,row_id='disclosed_ratio_'+str(i))
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertFalse(report['issues']);self.assertEqual(len(report['facts']),2)
        self.assertTrue(all(abs(f['value']-.05)<1e-12 for f in report['facts']))

    def test_old_saved_mapping_contract_cannot_reuse_a_review_or_start_paid_work(self):
        from company_initiation.historic_construction.workflow import ensure_company_history_research
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        inputs=root/'old_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
        with patch('company_initiation.shared_ai.OpenAIProvider.from_env',side_effect=AssertionError('No provider')):
            with self.assertRaisesRegex(ValueError,'predate the current'):
                ensure_company_history_research(root,data['company'],archive,inputs)

    def test_not_assessed_and_essential_exclusions_stay_pending(self):
        from company_initiation.historic_construction.workflow import _va_assess
        _,_,_,store,periods,data,rows,evidence,contract=self.case()
        excluded=dict(decisions=[dict(row_key=r['row_key'],action='exclude',reason_code='presentation_diagnostic',
            reason='Not assessed',duplicate_of=None,evidence_refs=[dict(source_id=r['source_id'],unit_id=r['unit_id'])]) for r in rows],gaps=[])
        report=_va_assess(excluded,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertEqual(len(report['issues']),len(rows));self.assertEqual(report['facts'],[])
        excluded['decisions'][0]['reason']='This is a presentation diagnostic.'
        self.assertTrue(_va_assess(excluded,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])

    def test_definition_intervals_require_citations_and_complete_nonoverlapping_coverage(self):
        from company_initiation.historic_construction.workflow import _va_assess
        _,_,_,store,periods,data,rows,evidence,contract=self.case(currency='JPY',year_end='03-31',reorganized=True)
        candidate=self.candidate(data,rows);item=candidate['decisions'][0];version=item['versions'][0]
        version['effective_to']='2024-03-31'
        bad=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertTrue(any('citations' in i['detail'] for i in bad['issues']))
        version['version_refs']=[dict(source_id=rows[0]['source_id'],unit_id=rows[0]['unit_id'])]
        self.assertTrue(any('cover every' in i['detail'] for i in _va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues']))
        successor=copy.deepcopy(version);successor.update(effective_from='2024-04-01',effective_to=None,basis='new reporting definition')
        item['versions'].append(successor)
        self.assertFalse(_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])
        successor['effective_from']='2024-03-01'
        self.assertTrue(_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])

    def test_real_journal_passes_candidate_and_merges_only_missing_row_patch(self):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.shared_budget import BudgetLedger,ledger_path,construction_command_budget
        from company_initiation.historic_construction.workflow import _va_history_inputs,_va_schema
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        template=self.journal(data);provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY',max_output_tokens=1000);requests=[]
        def complete(**kwargs):
            payload=kwargs['payload'];requests.append(copy.deepcopy(payload))
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=100,total_tokens=200),output=[])
            if payload['stage']=='company_va_core_review':
                return template.stage(payload['stage'],'fixture',payload,kwargs['schema'],lambda a:a)
            if payload['stage']=='company_va_row_mapping':
                result=template.stage('company_va_row_mapping','fixture',payload,kwargs['schema'],lambda a:a)
                result['decisions'].pop();return result
            previous=payload['previous_candidate'];self.assertEqual(len(previous['decisions']),2)
            self.assertEqual(payload['permitted_changes'][0]['expected_digest'],None)
            original=template.stage('company_va_row_mapping','fixture',payload['context'],
                _va_schema([r['row_key'] for r in rows],['money'])[0],lambda a:a)
            missing=next(d for d in original['decisions'] if d['row_key']==payload['permitted_changes'][0]['row_key'])
            return dict(changes=[dict(row_key=missing['row_key'],expected_digest=None,path='$',value=missing)])
        with construction_command_budget(root/'outputs',data['company'],20):
            directory=root/'outputs/construct_fixture';directory.mkdir()
            ledger=BudgetLedger(ledger_path(root/'outputs',data['company']),data['company'])
            journal=RunJournal(directory,provider,dict(company=data['company'],limits=dict(usd=20,repairs=2)),ledger=ledger)
            with patch.object(provider,'complete',side_effect=complete),patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No network')):
                _va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
            self.assertEqual(len(requests),2);self.assertEqual(ledger.summary()['total_requests'],2)
            self.assertEqual(data['historical']['sales']['values']['2024'],100.)
            self.assertTrue((directory/'va_cohort_0_validated.json').is_file())
            self.assertEqual(journal.entries[0]['result']['decisions'],requests[1]['previous_candidate']['decisions'])
            self.assertTrue(all('period_ids' not in v for d in json.loads((directory/'va_cohort_0_validated.json').read_text())['candidate']['decisions'] for v in d.get('versions',[])))

    def test_partial_export_and_explicit_resume_reuse_completed_cohort_and_budget(self):
        from company_initiation.shared_ai import OpenAIProvider,AIError
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.shared_budget import BudgetLedger,ledger_path,construction_command_budget
        from company_initiation.historic_construction.workflow import _va_history_inputs
        from openpyxl import load_workbook
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        cohorts=[rows[:1],rows[1:]]
        template=self.journal(data);provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY',max_output_tokens=1000)
        first_calls=[]
        def complete(**kwargs):
            payload=kwargs['payload'];first_calls.append(payload['cohort_index'])
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=100,total_tokens=200),output=[])
            if payload['cohort_index']==1:raise AIError('Synthetic known-usage failure after a completed cohort')
            return template.stage('company_va_row_mapping','fixture',payload,kwargs['schema'],lambda a:a)
        with construction_command_budget(root/'outputs',data['company'],20) as budget:
            first=root/'outputs/construct_first';first.mkdir();ledger=BudgetLedger(ledger_path(root/'outputs',data['company']),data['company'])
            journal=RunJournal(first,provider,dict(company=data['company'],limits=dict(usd=20,repairs=2)),ledger=ledger)
            with patch('company_initiation.historic_construction.workflow._va_cohorts',return_value=cohorts),patch.object(provider,'complete',side_effect=complete):
                with self.assertRaisesRegex(AIError,'known-usage failure'):_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
            self.assertTrue((first/'historical_model_incomplete.xlsx').is_file())
            book=load_workbook(first/'historical_model_incomplete.xlsx')
            try:self.assertTrue(book['Model']['B4'].value.startswith('INCOMPLETE:'))
            finally:book.close()
            saved=json.loads((first/'va_mapping_progress.json').read_text())
            self.assertGreater(len(saved['company_inputs']['observations']),0)
            journal.state['status']='incomplete';journal.save();previous=copy.deepcopy(journal.state);old_bytes=(first/'record.json').read_bytes()
        resumed_calls=[]
        def recovered(**kwargs):
            payload=kwargs['payload']
            if payload['stage']=='company_va_row_mapping':resumed_calls.append(payload['cohort_index'])
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=100,total_tokens=200),output=[])
            return template.stage(payload['stage'],'fixture',payload,kwargs['schema'],lambda a:a)
        with construction_command_budget(root/'outputs',data['company'],None,previous=previous) as continued:
            second=root/'outputs/construct_second';second.mkdir();ledger=BudgetLedger(ledger_path(root/'outputs',data['company']),data['company'])
            journal=RunJournal(second,provider,dict(company=data['company'],limits=dict(usd=20,repairs=2)),previous=previous,ledger=ledger)
            with patch('company_initiation.historic_construction.workflow._va_cohorts',return_value=cohorts),patch.object(provider,'complete',side_effect=recovered):
                _va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
            self.assertEqual(resumed_calls,[1]);self.assertEqual(continued['allowance_period_id'],budget['allowance_period_id'])
            self.assertEqual(ledger.summary()['total_requests'],3)
        self.assertEqual((first/'record.json').read_bytes(),old_bytes)

    def test_saved_real_response_patterns_replay_locally_without_a_company_build(self):
        """Read preserved outputs when present; this is replay, not new AI research."""
        from company_initiation.historic_construction.workflow import _va_assess
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.historic_construction.periods import build_periods
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        from company_initiation.shared_project import find_project_root
        workspace=find_project_root();folders=sorted((workspace/'outputs').glob('construct_research_20261031*'))
        examined=0
        for folder in folders:
            record=json.loads((folder/'record.json').read_text(encoding='utf-8'))
            calls=[c for c in record['calls'] if c['stage']=='company_va_row_mapping' and 'mappings' in c.get('result',{})]
            if not calls:continue
            last=calls[-1];payload=last['request']['payload'];catalogue={r['row_key']:r for r in payload['rows']}
            with tempfile.TemporaryDirectory() as temp:
                store=SourceStore(Path(temp)/'sources')
                descriptors=[source for source in record['sources'] if source.get('category')=='visible_alpha']
                for source in descriptors:store.restore(source,archive_root=workspace/'outputs')
                data=dict(company=record['configuration']['company'],currency=payload['currency'],segments=payload['company_scope']['segments'],
                    model_configuration=dict(as_of='2026-10-31'),sources={s['id']:s for s in descriptors})
                periods=build_periods(list(range(2018,2027)),payload['fiscal_calendar'])
                rows=store.company_reported_rows([s['id'] for s in descriptors],periods,as_of='2026-10-31')
                selected=[r for r in rows if r['row_key'] in catalogue]
                evidence=store.read_documents([dict(source_id=s['id'],unit_id=next(iter(store._units[s['id']]))) for s in descriptors],historical_years=set(range(2018,2027)))
                decisions=[]
                for old in last['result']['mappings']:
                    row=next(r for r in selected if r['row_key']==old['row_key'])
                    from company_initiation.historic_construction.evidence import va_unit_options
                    options=va_unit_options(row['reported_unit'],data['currency'])
                    if not options:continue
                    version={k:copy.deepcopy(old[k]) for k in ('row_id','label','entity_id','metric_type','basis','definition_id','scope','restatement','restatement_vintage','classification_basis')}
                    entity=old['entity_id'];current={s['id'] for s in data['segments']}
                    version.update(definition_status='source_defined',basis_status='period_defined',entity_kind='group' if entity=='group' else 'corporate' if entity=='corporate' else 'current_segment' if entity in current else 'legacy_segment',
                        measure=options[0]['measure'],effective_from=None,effective_to=None,version_refs=[],polarity=1)
                    decisions.append(dict(row_key=old['row_key'],action='map',versions=[version]))
                if not decisions:continue
                # Test each saved mapping independently: unit/period mechanics
                # can be corrected, while the saved bad group entity is rejected.
                for decision in decisions:
                    row=next(r for r in selected if r['row_key']==decision['row_key'])
                    report=_va_assess(dict(decisions=[decision],gaps=[]),[row],rows,data,store,data['sources'],periods,
                        dict(roles=integrated_role_contract()),evidence)
                    if decision['versions'][0]['row_id']=='sales' and decision['versions'][0]['entity_id']=='corporate':
                        self.assertTrue(report['issues'])
                    if row['label']=='M&A and others impact - Nespresso':
                        self.assertFalse(report['issues']);self.assertEqual(len(report['facts']),len(row['cells']))
                        self.assertTrue({'2024-Q2','2024-Q3'}<={f['period_id'] for f in report['facts']})
                examined+=1
        if not examined:self.skipTest('Local archived real-response journals are absent; synthetic regressions still run')
        self.assertEqual(examined,3)


class HistoricalRetestFixTests(unittest.TestCase):
    fixture=CompanyReportedVAConstructionTests.fixture
    journal=CompanyReportedVAConstructionTests.journal
    case=VAMappingRepairTests.case
    candidate=VAMappingRepairTests.candidate

    def test_scientific_numeric_roundtrips_remain_finite_and_exactly_nonzero(self):
        from company_initiation.historic_construction.evidence import parse_number
        for raw,expected in [('1e-05',.00001),('-2.607164804e-05',-.00002607164804),('1E+3',1000.),('(1e-5)',-.00001),('1e-3%',.00001)]:
            self.assertEqual(parse_number(raw),expected)
        self.assertEqual(parse_number('1,2e-3','comma_decimal'),.0012)
        for bad in ('1e309','NaN','inf','1e-5junk','1e--5',None,True):
            with self.subTest(bad=bad),self.assertRaises(ValueError):parse_number(bad)

    def test_source_selection_uses_enum_compact_catalogue_and_bounded_invalid_id_repair(self):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.workflow import _identity_source_selection
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        directory=root/'selection';directory.mkdir();provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE',max_output_tokens=1000)
        journal=RunJournal(directory,provider,dict(company=data['company'],limits=dict(usd=20,repairs=2)))
        catalogue={'real-a':dict(id='real-a',title='Company Reported',category='visible_alpha',dataset_role='company_reported',vendor_profile={'large':'x'*30000}),
                   'real-b':dict(id='real-b',title='Company disclosure',category='financial_reports')}
        requests=[]
        def complete(**kwargs):
            requests.append(copy.deepcopy(kwargs));provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[])
            return dict(source_ids=['real-a','local_202?'] if len(requests)==1 else ['real-a','real-b'],reasons=['Synthetic selection'],gaps=[])
        with patch.object(provider,'complete',side_effect=complete),patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No network')):
            answer=_identity_source_selection(journal,data['company'],'2025-10-01',catalogue,'Select originals')
        self.assertEqual(answer['source_ids'],['real-a','real-b']);self.assertEqual(len(requests),2)
        self.assertEqual(requests[0]['schema']['properties']['source_ids']['items']['enum'],['real-a','real-b'])
        self.assertNotIn('vendor_profile',requests[0]['payload']['catalog'][0])
        self.assertTrue(requests[1]['payload']['validation_errors'])
        self.assertEqual(journal.state['usage']['calls'],2)
        self.assertIn('candidate_result',journal.entries[0]);self.assertNotIn('candidate_result',journal.entries[1])

    def test_parser_failure_has_no_semantic_patch_and_numeric_preflight_is_offline(self):
        from company_initiation.historic_construction.workflow import _va_assess,_va_numeric_preflight,_va_schema,_va_patch_contract,_va_apply_patch
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.shared_ai import OpenAIProvider
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        preflight=_va_numeric_preflight(store,[source['id']]);self.assertEqual(preflight['status'],'passed');self.assertGreater(preflight['checked_cells'],0)
        candidate=self.candidate(data,rows);directory=root/'parser';directory.mkdir()
        provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE',max_output_tokens=1000)
        journal=RunJournal(directory,provider,dict(company=data['company'],limits=dict(usd=20,repairs=2)))
        schema,decision_schema=_va_schema([r['row_key'] for r in rows],['money'])
        def complete(**kwargs):
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[]);return candidate
        with patch.object(store,'resolve',side_effect=ValueError('Synthetic unsupported source notation')),patch.object(provider,'complete',side_effect=complete) as api:
            with self.assertRaisesRegex(ValueError,'deterministic validation blocker'):
                journal.patch_stage('company_va_row_mapping','Fixture',{},schema,
                    assess=lambda value:_va_assess(value,rows,rows,data,store,data['sources'],periods,contract,evidence),
                    patch_contract=lambda value,report:_va_patch_contract(value,report,decision_schema),apply_patch=_va_apply_patch)
        self.assertEqual(api.call_count,1)
        self.assertTrue(all(c['stage']=='company_va_row_mapping' for c in journal.entries))

    def test_provisional_model_populates_without_changing_calibration_or_deriving_unknown_bases(self):
        from company_initiation.historic_construction.workflow import _va_assess
        from company_initiation.historic_construction.model_contract import historical_model,historical_eligibility_inputs
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows)
        for decision in candidate['decisions']:decision['versions'][0]['restatement']='unknown'
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertFalse(report['issues']);data['observations']=report['facts']
        data['model_configuration']['historical_display_policy']='provisional_vendor_v1';before=copy.deepcopy(data)
        spec=historical_model(data);sales=next(r for r in spec['rows'] if r['id']=='sales')
        self.assertEqual(sales['cells']['2024-FY']['value'],100)
        self.assertEqual(sales['cells']['2024-FY']['status'],'provisional_vendor')
        self.assertNotIn('2024-H2',sales['cells'])
        self.assertTrue(all(not o['eligible'] and not o['calibration_eligible'] for o in report['facts']))
        self.assertTrue(all(not o['eligible'] for o in historical_eligibility_inputs(data)['observations']))
        self.assertEqual(data,before)
        unresolved=copy.deepcopy(candidate);unresolved['decisions'][0]['versions'][0]['definition_status']='unresolved'
        self.assertTrue(_va_assess(unresolved,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])
        vendor=copy.deepcopy(candidate)
        for decision in vendor['decisions']:decision['versions'][0]['restatement']='vendor_normalized'
        vendor_facts=_va_assess(vendor,rows,rows,data,store,data['sources'],periods,contract,evidence)['facts']
        self.assertTrue(all(not f['historical_display_eligible'] for f in vendor_facts))

    def test_provisional_historical_checkpoint_has_model_values_and_source_verification(self):
        from company_initiation.historic_construction.workflow import _va_assess,_review_va_history,complete_historical_model,VA_MAPPING_CONTRACT
        from company_initiation.historic_construction.evidence import verify_model_input_sources
        from openpyxl import load_workbook
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows)
        for decision in candidate['decisions']:decision['versions'][0]['restatement']='unknown'
        data['observations']=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)['facts']
        data['model_configuration'].update(historical_display_policy='provisional_vendor_v1',va_mapping_contract=VA_MAPPING_CONTRACT)
        _review_va_history(self.journal(data),data,evidence)
        before=copy.deepcopy(data);inputs=root/'prepared_synthetic.json';inputs.write_text(json.dumps(data),encoding='utf-8')
        output=complete_historical_model(root,data['company'],archive,inputs)
        record=json.loads((output/'record.json').read_text());self.assertEqual(record['status'],'historical_complete_provisional')
        self.assertTrue(any(c['name'].startswith('observation:') and c['status']=='PASS' for c in json.loads((output/'source_validation.json').read_text())))
        book=load_workbook(output/'historical_model.xlsx',data_only=False)
        try:
            self.assertIn('PROVISIONAL',book['Model']['B4'].value)
            self.assertTrue(any(isinstance(c.value,str) and c.value.startswith('=') for row in book['Model'] for c in row))
            self.assertNotIn('Valuation',book.sheetnames);self.assertNotIn('Assumptions',book.sheetnames)
        finally:book.close()
        self.assertEqual(data,before)
        corrupt=copy.deepcopy(data);corrupt['observations'][0]['value']+=1
        self.assertTrue(any(c['status']=='FAIL' for c in verify_model_input_sources(corrupt,archive)))
        self.assertTrue(all(not o['eligible'] and not o['calibration_eligible'] for o in data['observations']))

    def test_verified_duplicate_core_rows_are_excluded_only_with_retained_equivalence(self):
        from company_initiation.historic_construction.workflow import _va_assess
        from company_initiation.historic_construction.evidence import SourceStore,inventory_local_sources
        from openpyxl import load_workbook
        root,archive,source,_,periods,data,_,_,contract=self.case();path=archive/source['local_path']
        book=load_workbook(path);sheet=book.active
        for col in range(4,13):sheet.cell(12,col,sheet.cell(7,col).value)
        book.save(path);book.close()
        source=next(s for s in inventory_local_sources(archive)['sources'] if s.get('dataset_role')=='company_reported')
        store=SourceStore(root/'duplicates');store.add_local(source,root=archive);data['sources']={source['id']:source}
        rows=store.company_reported_rows([source['id']],periods,as_of=data['model_configuration']['as_of'])
        evidence=store.read_documents([dict(source_id=source['id'],unit_id=next(iter(store._units[source['id']])))],historical_years={2024})
        same=[r for r in rows if r['label']=='Group sales'];self.assertEqual(len(same),2)
        candidate=self.candidate(data,rows);target=same[1];retained=same[0]
        exclusion=dict(row_key=target['row_key'],action='exclude',reason_code='duplicate',reason='Same consolidated sales definition, entity, period basis and original values in this supplied workbook.',
            duplicate_of=retained['row_key'],evidence_refs=[dict(source_id=r['source_id'],unit_id=r['unit_id']) for r in same])
        candidate['decisions']=[exclusion if d['row_key']==target['row_key'] else d for d in candidate['decisions']]
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertFalse(report['issues']);self.assertEqual(sum(f['row_id']=='sales' and f['kind']=='FY' for f in report['facts']),1)
        target['cells'][0]['source_raw']='different value'
        self.assertTrue(_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])

    def test_export_precision_and_failed_draft_registration_are_separate(self):
        from company_initiation.historic_construction.model_excel import _export_value_equal
        self.assertTrue(_export_value_equal(.101,.10099999999999999))
        self.assertTrue(_export_value_equal(12345.67890123456,12345.678901234567))
        for actual,expected in [(0.,1e-05),(100.,100.01),('=A1','=A2'),('source_a','source_b'),(False,0),(float('nan'),float('nan'))]:
            self.assertFalse(_export_value_equal(actual,expected))
        from company_initiation.historic_construction.workflow import _va_assess,_va_incomplete_output
        from company_initiation.shared_runtime import RunJournal
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        facts=_va_assess(self.candidate(data,rows),rows,rows,data,store,data['sources'],periods,contract,evidence)['facts'];data['observations']=facts
        directory=root/'failed_export';directory.mkdir();messages=[]
        journal=RunJournal(directory,None,dict(company=data['company'],limits=dict(usd=20,repairs=2)),progress=messages.append)
        with patch('company_initiation.historic_construction.model_excel._export_value_equal',return_value=False) as comparator:
            with self.assertRaisesRegex(ValueError,'validation failed'):_va_incomplete_output(journal,data,ValueError('Synthetic mapping failure'))
            first_count=comparator.call_count
            self.assertIsNone(_va_incomplete_output(journal,data,ValueError('Second handler')))
            self.assertEqual(comparator.call_count,first_count)
        output=journal.state['stage_outputs']['historical'];self.assertEqual(output['status'],'failed')
        self.assertTrue((directory/output['workbook']).is_file())
        self.assertIn(output['workbook'],journal.state['artifacts']);self.assertIn(output['validation'],journal.state['artifacts'])
        validation=json.loads((directory/output['validation']).read_text());self.assertEqual(validation['saved_value_and_formula_readback'],'failed')
        self.assertTrue(any('failed' in m and '.xlsx' in m for m in messages))

    def test_latest_local_failed_workbooks_and_scientific_tokens_replay_offline(self):
        from company_initiation.shared_project import find_project_root
        from company_initiation.historic_construction.model_excel import write_historical_output
        from company_initiation.historic_construction.evidence import parse_number
        workspace=find_project_root();examined=0
        for folder_name in ['construct_research_20261031T144355Z_2503b344','construct_research_20261031T144321Z_58bea8c9']:
            folder=workspace/'outputs'/folder_name
            if not (folder/'va_mapping_progress.json').exists():continue
            data=json.loads((folder/'va_mapping_progress.json').read_text(encoding='utf-8'))['company_inputs']
            with tempfile.TemporaryDirectory() as temp:
                output=write_historical_output(Path(temp),data,incomplete=True)
                self.assertEqual(output['status'],'incomplete')
                report=json.loads((Path(temp)/output['validation']).read_text())
                self.assertEqual(report['saved_value_and_formula_readback'],'passed')
            examined+=1
        if not examined:self.skipTest('Local archived real-data drafts are absent; synthetic precision cases still run')
        self.assertEqual(examined,2)
        self.assertEqual(parse_number('1e-05'),.00001);self.assertEqual(parse_number('-2.607164804e-05'),-.00002607164804)


class VASemanticReliabilityTests(unittest.TestCase):
    fixture=CompanyReportedVAConstructionTests.fixture
    journal=CompanyReportedVAConstructionTests.journal
    case=VAMappingRepairTests.case
    candidate=VAMappingRepairTests.candidate

    def test_source_keys_are_canonicalized_but_wrong_typed_temporal_roles_fail(self):
        from company_initiation.historic_construction.workflow import _va_assess
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows);sales=next(d for d in candidate['decisions'] if d['versions'][0]['row_id']=='sales')
        original=copy.deepcopy(candidate);sales['versions'][0]['row_id']=sales['row_key']
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertFalse(report['issues'])
        self.assertTrue(any(f['row_id']=='sales' for f in report['facts']))
        self.assertFalse(any(f['row_id'].startswith('row_') for f in report['facts']))
        wrong=copy.deepcopy(original);next(d for d in wrong['decisions'] if d['versions'][0]['row_id']=='sales')['versions'][0]['financial_role']='cash'
        self.assertTrue(_va_assess(wrong,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])
        self.assertEqual(next(r for r in rows if r['label']=='Group sales')['cells'][-1]['source_raw'],'40')

    def test_source_period_metadata_preserves_headers_series_and_distinct_intervals(self):
        root,archive,source,store,periods,data,rows,evidence,contract=self.case(currency='JPY',year_end='03-31',reorganized=True)
        sales=next(r for r in rows if r['label']=='Group sales')
        fiscal=next(c['period_metadata'] for c in sales['cells'] if c['period_id']=='2024-FY')
        half=next(c['period_metadata'] for c in sales['cells'] if c['period_id']=='2024-H1')
        self.assertEqual(fiscal['source_period_label'],'FY-2024');self.assertEqual(fiscal['source_series'],'Filings')
        self.assertEqual((fiscal['start'],fiscal['end']),('2023-04-01','2024-03-31'))
        self.assertEqual((half['start'],half['end']),('2023-04-01','2023-09-30'))
        self.assertIn(fiscal['header_ref']['unit_id'],store._units[source['id']])
        self.assertEqual(sales['source_row_role'],'metric');self.assertIn('navigation',sales['navigation_note'])
        self.assertFalse(any('E' in c['period_metadata']['source_period_label'] for r in rows for c in r['cells']))

    def test_uncertain_interim_does_not_erase_clear_annual_facts_or_generate_arithmetic(self):
        from company_initiation.historic_construction.workflow import _va_assess,_va_coverage_gaps
        from company_initiation.historic_construction.model_contract import historical_model
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows)
        sales=next(d for d in candidate['decisions'] if d['versions'][0]['row_id']=='sales')
        physical=next(r for r in rows if r['row_key']==sales['row_key'])
        annual=copy.deepcopy(sales['versions'][0]);annual.update(period_kinds=['FY'],version_refs=[dict(source_id=source['id'],unit_id=physical['unit_id'])],restatement='unknown')
        interim=copy.deepcopy(annual);interim.update(period_kinds=['H1'],period_basis='unresolved',basis_status='unresolved',basis='Unresolved: interim measurement convention')
        sales['versions']=[annual,interim]
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertFalse(report['issues']);self.assertFalse(_va_coverage_gaps(data,report['facts'],periods))
        data['observations']=report['facts'];data['model_configuration']['historical_display_policy']='provisional_vendor_v1'
        projected=next(r for r in historical_model(data)['rows'] if r['id']=='sales')
        self.assertEqual(projected['cells']['2024-FY']['value'],100)
        self.assertNotIn('2024-H1',projected['cells']);self.assertNotIn('2024-H2',projected['cells'])

    def test_flags_cannot_resolve_a_contradictory_basis_explanation(self):
        from company_initiation.historic_construction.workflow import _va_assess,_va_patch_contract,_va_schema
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows);candidate['decisions'][0]['versions'][0]['basis']='Unresolved: original flow duration'
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertTrue(any('must agree' in i['detail'] for i in report['issues']))
        patch=_va_patch_contract(candidate,report,_va_schema([r['row_key'] for r in rows],['money'])[1])
        paths={p for item in patch['permitted_changes'] for p in item['paths']}
        self.assertIn('versions.0.basis',paths);self.assertIn('versions.0.period_basis',paths)

    def test_cited_hierarchy_applies_to_its_own_fiscal_period_without_relabelling(self):
        from company_initiation.historic_construction.workflow import _va_history_inputs,_va_validate_reporting_context,_va_coverage_gaps
        root,archive,source,store,periods,data,rows,evidence,contract=self.case(currency='JPY',year_end='03-31',reorganized=True)
        ref=dict(source_id=source['id'],unit_id=rows[0]['unit_id'])
        context=dict(declarations=[],entity_versions=[dict(entity_id='legacy',label='Legacy division',entity_kind='legacy_segment',
            effective_from=None,effective_to='2024-03-31',source_refs=[ref])],hierarchies=[
                dict(effective_from=None,effective_to='2024-03-31',entity_ids=['legacy'],source_refs=[ref]),
                dict(effective_from='2024-04-01',effective_to=None,entity_ids=['equipment','services'],source_refs=[ref])])
        units={source['id']:store._units[source['id']]};_va_validate_reporting_context(context,units,data['segments'])
        data['model_configuration'].update(va_reporting_context=context,full_statement_frequency='half_year')
        data['history_years']=[2024]
        journal=self.journal(data);_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
        self.assertFalse(_va_coverage_gaps(data,data['observations'],periods))
        self.assertEqual(data['historical']['legacy_sales']['values']['2024'],100)
        self.assertNotIn('2024',data['historical'].get('equipment_sales',{}).get('values',{}))
        self.assertNotIn('company_va_core_review',journal.calls)
        bad=copy.deepcopy(context);bad['hierarchies'][1]['effective_from']='2024-03-31'
        bad['hierarchies'][1]['entity_ids']=['legacy']
        with self.assertRaisesRegex(ValueError,'overlap'):_va_validate_reporting_context(bad,units,data['segments'])
        bad=copy.deepcopy(context);bad['entity_versions'][0]['source_refs'][0]['unit_id']='not_supplied'
        with self.assertRaisesRegex(ValueError,'original sections'):_va_validate_reporting_context(bad,units,data['segments'])

    def test_prose_only_patch_stops_before_another_paid_request(self):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.workflow import _va_assess,_va_schema,_va_patch_contract,_va_apply_patch,_va_semantic_fingerprint
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows);version=candidate['decisions'][0]['versions'][0]
        version.update(basis_status='unresolved',period_basis='unresolved',basis='Unresolved: flow convention')
        schema,decision_schema=_va_schema([r['row_key'] for r in rows],['money'])
        provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY');directory=root/'journal';directory.mkdir()
        journal=RunJournal(directory,provider,dict(limits=dict(usd=20,repairs=2)))
        def complete(**kwargs):
            payload=kwargs['payload'];change=payload['permitted_changes'][0]
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[])
            return dict(changes=[dict(row_key=change['row_key'],expected_digest=change['expected_digest'],
                path='versions.0.classification_basis',value='Different prose; fiscal convention remains unknown')])
        with patch.object(provider,'complete',side_effect=complete) as api,patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No network')):
            with self.assertRaisesRegex(ValueError,'no semantic progress'):
                journal.patch_stage('company_va_row_mapping','fixture',{},schema,initial_candidate=candidate,
                    assess=lambda a:_va_assess(a,rows,rows,data,store,data['sources'],periods,contract,evidence),
                    patch_contract=lambda a,r:_va_patch_contract(a,r,decision_schema),apply_patch=_va_apply_patch,
                    semantic_fingerprint=_va_semantic_fingerprint)
        self.assertEqual(api.call_count,1);self.assertEqual(journal.state['usage']['calls'],1)
        self.assertTrue(list(directory.glob('*semantic_stop.json')))

    def test_targeted_resolution_uses_original_context_and_retains_unknown_conclusions(self):
        from company_initiation.historic_construction.workflow import _va_resolve_evidence
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        journal=self.journal(data);original=journal.stage;seen=[]
        section=dict(source_id='synthetic_note',unit_id='note:periods',text='SYNTHETIC: reporting definition is not resolved by this note')
        target=dict(row_key=rows[0]['row_key'],source_ref=dict(source_id=source['id'],unit_id=rows[0]['unit_id']))
        report=dict(issues=[dict(row_key=target['row_key'],detail='Period convention unknown',paths=['versions.0.basis_status'],kind='financial_evidence')])
        def stage(name,prompt,payload,schema,validator):
            seen.append(payload)
            answer=dict(conclusions=[dict(row_key=target['row_key'],finding_id=payload['questions'][0]['finding_id'],status='unresolved',detail='Original note does not resolve the question',
                source_refs=[dict(source_id=section['source_id'],unit_id=section['unit_id'])])],summary='Evidence remains insufficient')
            return validator(answer)
        journal.stage=stage
        self.assertIsNone(_va_resolve_evidence(journal,data,[target],report,[],[]));self.assertFalse(seen)
        result=_va_resolve_evidence(journal,data,[target],report,[section],[])
        self.assertEqual(result['conclusions']['conclusions'][0]['status'],'unresolved')
        self.assertEqual(seen[0]['original_sections'],[section]);self.assertFalse(data['observations'])
        for index in range(3):
            changed=copy.deepcopy(report);changed['issues'][0]['detail']+=' '+str(index)
            _va_resolve_evidence(journal,data,[target],changed,[section],[])
        self.assertEqual(len(seen),3);self.assertEqual(len(journal.state['va_evidence_resolutions']),3)

    def test_single_final_review_retains_native_facts_and_reports_material_definition_error(self):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.historic_construction.workflow import _va_history_inputs,_review_va_history
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        template=self.journal(data);provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY');stages=[]
        directory=root/'journal';directory.mkdir();journal=RunJournal(directory,provider,dict(limits=dict(usd=20,repairs=2)))
        def complete(**kwargs):
            payload=kwargs['payload'];stage=payload['stage'];stages.append(stage)
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[])
            answer=template.stage(stage,'fixture',payload,kwargs['schema'],lambda a:a)
            if stage=='company_va_row_mapping':
                next(d for d in answer['decisions'] if d['versions'][0]['row_id']=='sales')['versions'][0]['definition_id']='gross_billings_including_tax'
                self.assertTrue(payload['period_catalogue'])
            elif stage=='company_va_history_review':
                answer['checks'][0].update(status='error',detail='Source Sales is not gross billings including tax')
                self.assertTrue(payload['history']);self.assertTrue(payload['mapping_plan'])
            else:self.fail('Unexpected additional review/repair: '+stage)
            return answer
        with patch.object(provider,'complete',side_effect=complete),patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No network')):
            _va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
            result=_review_va_history(journal,data,evidence)
        self.assertEqual(stages,['company_va_row_mapping','company_va_history_review'])
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(data['historical']['sales']['values']['2024'],100)
        self.assertTrue(all(o['definition_id']=='gross_billings_including_tax' for o in data['observations'] if o['row_id']=='sales'))
        self.assertTrue((directory/'combined_history_review.json').is_file())

    def test_actual_saved_failures_remain_evidence_replays_not_company_builds(self):
        from company_initiation.historic_construction.workflow import _va_coverage_gaps,_va_assess
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.historic_construction.periods import build_periods
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        from company_initiation.shared_project import find_project_root
        workspace=find_project_root();examined=0
        for name in ['construct_research_20261031T152303Z_e766b896','construct_research_20261031T152305Z_5745778e','construct_research_20261031T152310Z_163598d3']:
            run=workspace/'outputs'/name
            if not (run/'va_mapping_progress.json').is_file():continue
            record=json.loads((run/'record.json').read_text(encoding='utf-8'))
            data=json.loads((run/'va_mapping_progress.json').read_text(encoding='utf-8'))['company_inputs']
            periods=build_periods(list(range(2018,2027)),data['fiscal_calendar'])
            gaps=_va_coverage_gaps(data,data['observations'],periods)
            self.assertTrue(gaps)
            if '5745778e' in name:self.assertIn('dermatological_beauty_sales',{g['row_id'] for g in gaps})
            else:
                physical='row_7' if 'e766b896' in name else 'row_22'
                initial=next(c['result'] for c in record['calls'] if c['stage']=='company_va_row_mapping' and any(d['row_key']==physical for d in c['result']['decisions']))
                decision=copy.deepcopy(next(d for d in initial['decisions'] if d['row_key']==physical))
                for v in decision['versions']:v.update(financial_role='sales',period_basis='source_period' if v['basis_status']=='period_defined' else 'unresolved',period_kinds=[])
                with tempfile.TemporaryDirectory() as temp:
                    store=SourceStore(Path(temp));descriptor=next(s for s in record['sources'] if s.get('dataset_role')=='company_reported')
                    store.restore(descriptor,archive_root=workspace/'outputs')
                    rows=store.company_reported_rows([descriptor['id']],periods,as_of='2026-10-31');row=next(r for r in rows if r['row_key']==physical)
                    evidence=store.read_documents([dict(source_id=descriptor['id'],unit_id=row['unit_id'])],historical_years=set(range(2018,2027)))
                    assessed=_va_assess(dict(decisions=[decision],gaps=[]),[row],rows,data,store,{descriptor['id']:descriptor},periods,dict(roles=integrated_role_contract()),evidence)
                    self.assertFalse(any('Source row_key' in i['detail'] for i in assessed['issues']))
                    self.assertTrue(all(not f['row_id'].startswith('row_') for f in assessed['facts']))
            examined+=1
        if not examined:self.skipTest('Saved company inputs absent; fresh synthetic regressions still run')
        self.assertEqual(examined,3)

    def test_live_journal_routes_a_basis_gap_to_original_evidence_then_bounded_patch(self):
        from openpyxl import Workbook
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.shared_budget import construction_command_budget,BudgetLedger,ledger_path
        from company_initiation.historic_construction.evidence import inventory_local_sources
        from company_initiation.historic_construction.workflow import _va_history_inputs
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        notes=archive/'financial_reports';notes.mkdir();book=Workbook();book.active['A1']='SYNTHETIC disclosure: annual sales cover the fiscal year; H1 covers the first half.'
        book.save(notes/'Reporting notes.xlsx');book.close()
        note=next(s for s in inventory_local_sources(archive)['sources'] if s['category']=='financial_reports')
        store.add_local(note,root=archive);data['sources'][note['id']]=note
        supporting=store.read_documents([dict(source_id=note['id'],unit_id=next(iter(store._units[note['id']])))])
        template=self.journal(data);provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY');stages=[];seen=[]
        def complete(**kwargs):
            payload=kwargs['payload'];stage=payload['stage'];stages.append(stage)
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[])
            if stage in ('company_va_row_mapping','company_va_core_review'):
                answer=template.stage(stage,'fixture',payload,kwargs['schema'],lambda a:a)
                if stage=='company_va_row_mapping':
                    sales=next(d for d in answer['decisions'] if d['versions'][0]['row_id']=='sales')
                    sales['versions'][0].update(period_basis='unresolved',basis_status='unresolved',basis='Unresolved: fiscal flow duration',restatement='unknown')
                return answer
            if stage=='company_va_evidence_resolution':
                from company_initiation.historic_construction.workflow import _va_semantic_sections
                self.assertEqual(payload['original_sections'],_va_semantic_sections(supporting));self.assertTrue(payload['headers'])
                return dict(conclusions=[dict(row_key=q['row_key'],finding_id=q['finding_id'],status='supported',detail='Original disclosure and headers specify fiscal intervals',
                    source_refs=[dict(source_id=supporting[0]['source_id'],unit_id=supporting[0]['unit_id'])]) for q in payload['questions']],summary='Supported source intervals')
            self.assertEqual(stage,'company_va_row_mapping_patch');seen.append(payload)
            rule=payload['permitted_changes'][0]
            return dict(changes=[dict(row_key=rule['row_key'],expected_digest=rule['expected_digest'],path='versions.0.'+field,value=value)
                for field,value in [('basis','Reported fiscal interval specified by the original header and disclosure'),('basis_status','period_defined'),('period_basis','source_period')]])
        with construction_command_budget(root/'outputs',data['company'],20):
            directory=root/'outputs/fixture';directory.mkdir()
            ledger=BudgetLedger(ledger_path(root/'outputs',data['company']),data['company'])
            journal=RunJournal(directory,provider,dict(company=data['company'],limits=dict(usd=20,repairs=2)),ledger=ledger)
            with patch.object(provider,'complete',side_effect=complete),patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No network')):
                _va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract,supporting_evidence=supporting)
        self.assertEqual(ledger.summary()['total_requests'],3);self.assertEqual(ledger.summary()['unresolved_reservations_usd'],0)
        self.assertEqual(stages,['company_va_row_mapping','company_va_evidence_resolution','company_va_row_mapping_patch'])
        self.assertIn('additional_evidence',seen[0]);self.assertEqual(data['observations'][0]['source_refs'][0]['raw'],100)
        self.assertFalse(any(o['calibration_eligible'] for o in data['observations'] if o['row_id']=='sales'))

    def test_fresh_quarterly_and_half_year_companies_export_through_the_same_entry(self):
        from openpyxl import load_workbook
        from company_initiation.historic_construction.evidence import inventory_local_sources,SourceStore
        from company_initiation.historic_construction.workflow import _va_history_inputs,_review_va_history,complete_historical_model
        for currency,end,reorg,cadence in [('USD','12-31',False,'quarterly'),('JPY','03-31',True,'half_year')]:
            with self.subTest(currency=currency):
                root,archive,source,store,periods,data,rows,evidence,contract=self.case(currency=currency,year_end=end,reorganized=reorg)
                data['model_configuration']['full_statement_frequency']=cadence
                if cadence=='quarterly':
                    path=archive/source['local_path'];book=load_workbook(path);sheet=book.active
                    for col,kind,sales,cash in [(13,'1QFY-2024',18,3),(14,'2QFY-2024',22,4),(15,'3QFY-2024',27,6),(16,'4QFY-2024',33,8)]:
                        sheet.cell(4,col,kind);sheet.cell(5,col,'Filings');sheet.cell(7,col,sales);sheet.cell(8,col,cash);sheet.cell(9,col,sales)
                    book.save(path);book.close()
                    source=next(s for s in inventory_local_sources(archive)['sources'] if s.get('dataset_role')=='company_reported')
                    store=SourceStore(root/'quarterly');store.add_local(source,root=archive);data['sources']={source['id']:source}
                journal=self.journal(data)
                evidence=_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
                _review_va_history(journal,data,evidence)
                inputs=root/'synthetic_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
                output=complete_historical_model(root,data['company'],archive,inputs)
                self.assertTrue((output/'historical_model.xlsx').is_file())
                self.assertEqual(json.loads((output/'record.json').read_text(encoding='utf-8'))['status'],'historical_complete_provisional')
                validation=json.loads((output/'historical_workbook_validation.json').read_text())
                self.assertEqual(validation['saved_value_and_formula_readback'],'passed')
                projection=json.loads((output/'historical_model.json').read_text(encoding='utf-8'))
                sales_row=next(r for r in projection['rows'] if r['id']=='sales')
                # Same-date stock aliases do not establish quarterly flow reporting.
                quarter_ids={p for p in sales_row['cells'] if '-Q' in p}
                self.assertEqual(bool(quarter_ids),cadence=='quarterly')
                if reorg:
                    self.assertEqual(data['historical']['legacy_sales']['values']['2024'],100)
                    self.assertEqual(data['historical']['equipment_sales']['values']['2025'],70)
                else:
                    self.assertEqual(next(o['value'] for o in data['observations'] if o['row_id']=='sales' and o['period_id']=='2024-Q1'),18)

    def test_missing_essential_role_is_repaired_from_source_candidates_before_detail(self):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal,digest
        from company_initiation.historic_construction.workflow import _va_history_inputs
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        template=self.journal(data);provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY');stages=[]
        directory=root/'journal';directory.mkdir();journal=RunJournal(directory,provider,dict(limits=dict(usd=20,repairs=2)))
        def complete(**kwargs):
            payload=kwargs['payload'];stage=payload['stage'];stages.append(stage)
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=50,total_tokens=150),output=[])
            if stage in ('company_va_row_mapping','company_va_core_review'):
                answer=template.stage(stage,'fixture',payload,kwargs['schema'],lambda a:a)
                if stage=='company_va_row_mapping':
                    sales=next(d for d in answer['decisions'] if d['versions'][0]['row_id']=='sales')
                    sales['versions'][0].update(row_id='reported_turnover',financial_role=None)
                return answer
            self.assertEqual(stage,'company_va_core_coverage_patch')
            self.assertEqual(payload['context']['coverage_gaps'][0]['row_id'],'sales')
            decision=next(d for d in payload['previous_candidate']['decisions'] if d['versions'][0]['row_id']=='reported_turnover')
            fixed=copy.deepcopy(decision);fixed['versions'][0].update(row_id='sales',financial_role='sales')
            return dict(changes=[dict(row_key=decision['row_key'],expected_digest=digest(decision),path='$',value=fixed)])
        with patch.object(provider,'complete',side_effect=complete),patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No network')):
            _va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
        self.assertEqual(stages,['company_va_row_mapping'])
        self.assertEqual(next(o['value'] for o in data['observations'] if o['row_id']=='reported_turnover' and o['period_id']=='2024-FY'),100)
        self.assertFalse(data['model_configuration']['historical_coverage_gaps'])


class HistoricalRestatementPolicyTests(unittest.TestCase):
    fixture=CompanyReportedVAConstructionTests.fixture
    journal=CompanyReportedVAConstructionTests.journal
    case=VAMappingRepairTests.case
    candidate=VAMappingRepairTests.candidate

    def refresh(self,root,archive,data):
        from company_initiation.historic_construction.evidence import inventory_local_sources,SourceStore
        source=next(s for s in inventory_local_sources(archive)['sources'] if s.get('dataset_role')=='company_reported')
        store=SourceStore(root/'changed_source');store.add_local(source,root=archive);data['sources']={source['id']:source}
        return source,store

    def test_unchanged_definition_selects_revised_source_numbers_and_retains_originals(self):
        from openpyxl import load_workbook
        from company_initiation.historic_construction.workflow import _va_history_inputs,_review_va_history,complete_historical_model
        from company_initiation.historic_construction.model_contract import historical_model
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        book=load_workbook(archive/source['local_path']);sheet=book.active
        for row,label in [(12,'Group sales'),(13,'Manufacturing sales')]:
            sheet.cell(row,4,label);sheet.cell(row,5,'USDM');sheet.cell(row,6,'Analytics')
            sheet.cell(row,7,110);sheet.cell(row,8,110);sheet.cell(row,9,45)
        book.save(archive/source['local_path']);book.close();source,store=self.refresh(root,archive,data)
        journal=self.journal(data);original=journal.stage
        def stage(name,prompt,payload,schema,validator):
            answer=original(name,prompt,payload,schema,lambda a:a)
            if name=='company_va_row_mapping':
                for decision in answer['decisions']:
                    ref=next(r['source_ref'] for r in payload['target_rows'] if r['row_key']==decision['row_key'])
                    if ref['unit_id'] in ('Reported!R12','Reported!R13'):
                        decision['versions'][0].update(restatement='restated',restatement_vintage='2025-05-01')
            return validator(answer)
        journal.stage=stage
        evidence=_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
        self.assertEqual(data['historical']['sales']['values']['2024'],110)
        observations=[o for o in data['observations'] if o['row_id']=='sales' and o['period_id']=='2024-FY']
        self.assertEqual({o['value'] for o in observations},{100,110})
        self.assertFalse(next(o for o in observations if o['value']==100)['model_selection_eligible'])
        spec=historical_model(data)
        self.assertEqual(next(r for r in spec['rows'] if r['id']=='sales')['cells']['2024-FY']['value'],110)
        self.assertEqual(next(r for r in spec['rows'] if r['id']=='reporting_current_sales')['cells']['2024-FY']['value'],110)
        self.assertFalse(any(r['id'].startswith('reporting_historical_') for r in spec['rows']))
        _review_va_history(journal,data,evidence)
        inputs=root/'revised_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
        output=complete_historical_model(root,data['company'],archive,inputs)
        self.assertEqual(json.loads((output/'record.json').read_text())['status'],'historical_complete_provisional')
        self.assertEqual(len([o for o in spec['observations'] if o['row_id']=='sales' and o['period_id']=='2024-FY']),2)

    def test_redefined_regions_overlap_comparatives_and_export_separate_linked_totals(self):
        from openpyxl import load_workbook
        from company_initiation.historic_construction.workflow import _va_history_inputs,_review_va_history,complete_historical_model,_va_validate_reporting_context
        from company_initiation.historic_construction.model_contract import historical_model
        root,archive,source,store,periods,data,rows,evidence,contract=self.case(currency='JPY',year_end='03-31',reorganized=True)
        book=load_workbook(archive/source['local_path']);sheet=book.active
        sheet.cell(9,10,110)
        for row,value in [(10,60),(11,40)]:
            sheet.cell(row,7,value);sheet.cell(row,8,value)
        book.save(archive/source['local_path']);book.close();source,store=self.refresh(root,archive,data)
        ref=dict(source_id=source['id'],unit_id='Reported!R1')
        context=dict(declarations=[dict(topic='reporting_change',change_kind='redefinition',change_date='2025-04-01',
            detail='SYNTHETIC reorganisation with published prior-year comparatives on both bases',effective_from='2023-04-01',effective_to=None,source_refs=[ref])],
            entity_versions=[dict(entity_id='legacy',label='Old division',entity_kind='legacy_segment',effective_from=None,effective_to='2025-03-31',source_refs=[ref]),
                *[dict(entity_id=s['id'],label=s['label'],entity_kind='current_segment',effective_from='2023-04-01',effective_to=None,source_refs=[ref]) for s in data['segments']]],
            hierarchies=[dict(effective_from=None,effective_to='2025-03-31',entity_ids=['legacy'],source_refs=[ref]),
                dict(effective_from='2023-04-01',effective_to=None,entity_ids=['equipment','services'],source_refs=[ref])])
        _va_validate_reporting_context(context,{source['id']:store._units[source['id']]},data['segments'])
        data['model_configuration']['va_reporting_context']=context
        journal=self.journal(data);evidence=_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
        spec=historical_model(data);by_id={r['id']:r for r in spec['rows']}
        self.assertEqual(by_id['reporting_current_sales']['cells']['2024-FY']['value'],100)
        self.assertEqual(by_id['reporting_historical_1_sales']['cells']['2024-FY']['value'],100)
        self.assertEqual(by_id['reporting_current_sales']['cells']['2025-FY']['value'],110)
        self.assertEqual(by_id['reporting_historical_1_sales']['cells']['2025-FY']['value'],110)
        ids=[r['id'] for r in spec['rows']]
        self.assertLess(ids.index('services_sales'),ids.index('legacy_sales'))
        self.assertEqual(set(by_id['reporting_current_sales']['cells']['2024-FY']['model_bindings'].values()),{'equipment_sales','services_sales'})
        self.assertEqual(set(by_id['reporting_historical_1_sales']['cells']['2024-FY']['model_bindings'].values()),{'legacy_sales'})
        _review_va_history(journal,data,evidence);inputs=root/'redefined_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
        output=complete_historical_model(root,data['company'],archive,inputs)
        self.assertEqual(json.loads((output/'record.json').read_text())['status'],'historical_complete_provisional')
        workbook=load_workbook(output/'historical_model.xlsx',data_only=False);sheet=workbook['Model']
        try:
            import re
            totals=[]
            total_cells=[]
            for row in sheet:
                if '— Group sales' in str(row[1].value):
                    formulas=[c for c in row if c.data_type=='f'];self.assertTrue(formulas)
                    self.assertTrue(all('Historics' not in c.value for c in formulas))
                    totals.append(row[0].row)
                    total_cells.append(formulas[-1].coordinate)
            self.assertEqual(len(totals),2);self.assertLess(totals[0],totals[1])
            def evaluate(address):
                value=sheet[address].value
                if not isinstance(value,str):return value
                if 'Historics' in value:return workbook['Historics'][value.rsplit('!',1)[1]].value
                return sum(evaluate(ref) for ref in re.findall(r'[A-Z]+\d+',value))
            self.assertEqual(evaluate(total_cells[0]),110);self.assertEqual(evaluate(total_cells[1]),110)
            dependency=re.findall(r'[A-Z]+\d+',sheet[total_cells[0]].value)[0]
            original=sheet[dependency].value;sheet[dependency]=evaluate(dependency)+5
            self.assertEqual(evaluate(total_cells[0]),115);self.assertEqual(evaluate(total_cells[1]),110)
            sheet[dependency]=original
        finally:workbook.close()

    def test_revision_vintage_selects_latest_but_different_definitions_and_ties_remain_separate(self):
        from company_initiation.historic_construction.model_contract import select_revised_observations
        original=dict(id='original',row_id='a_sales',period_id='2024-FY',entity_id='a',definition_id='net_sales',scope='a',
            unit='USDm',metric_type='flow',restatement='original',value=100,status='reported',eligible=True,source_refs=[dict(source_id='SYNTHETIC',unit_id='original')])
        older=dict(original,id='revision_1',value=110,restatement='restated',restatement_vintage='2025-03-01')
        newer=dict(older,id='revision_2',value=120,restatement_vintage='2025-04-01')
        output=select_revised_observations([original,older,newer])
        self.assertEqual([o['id'] for o in output if o.get('model_selection_eligible',True)],['revision_2'])
        self.assertEqual(len(output),3);self.assertNotIn('superseded_by',original)
        changed=dict(newer,id='different_definition',definition_id='gross_billings')
        output=select_revised_observations([original,changed]);self.assertTrue(all(o.get('model_selection_eligible',True) for o in output))
        tied=dict(newer,id='unranked_revision',value=130)
        output=select_revised_observations([original,newer,tied]);self.assertTrue(all(o.get('model_selection_eligible',True) for o in output))
        invalid=dict(newer,id='unverified',status='unverified')
        self.assertTrue(select_revised_observations([original,invalid])[0].get('model_selection_eligible',True))

    def test_version_set_patch_preserves_unaffected_versions_and_digest_is_schema_constrained(self):
        from company_initiation.historic_construction.workflow import _va_assess,_va_patch_contract,_va_apply_patch,_va_schema
        from company_initiation.shared_runtime import digest,validate_shape
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows);decision=next(d for d in candidate['decisions'] if d['versions'][0]['row_id']=='sales')
        row=next(r for r in rows if r['row_key']==decision['row_key']);ref=dict(source_id=source['id'],unit_id=row['unit_id'])
        annual=copy.deepcopy(decision['versions'][0]);annual.update(period_kinds=['FY'],version_refs=[ref])
        half=copy.deepcopy(annual);half.update(period_kinds=['H1'],entity_id='invalid_group')
        decision['versions']=[annual,half]
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        schema,version_schema=_va_schema([r['row_key'] for r in rows],['money'])
        rule=_va_patch_contract(candidate,report,version_schema)
        self.assertIn('versions.1',next(r for r in rule['permitted_changes'] if r['row_key']==decision['row_key'])['paths'])
        replacement=copy.deepcopy(half);replacement['entity_id']='group'
        patch_data=dict(changes=[dict(row_key=decision['row_key'],expected_digest=digest(decision),path='versions.1',value=replacement)])
        validate_shape(patch_data,rule['schema']);updated=_va_apply_patch(candidate,patch_data,rule)
        self.assertFalse(_va_assess(updated,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])
        invalid=copy.deepcopy(patch_data);invalid['changes'][0]['expected_digest']='wrong'
        with self.assertRaisesRegex(ValueError,'digest'):_va_apply_patch(candidate,invalid,rule)
        invalid=copy.deepcopy(patch_data);invalid['changes'][0].update(path='versions.0',value=dict(annual,definition_id='changed_valid_definition'))
        with self.assertRaisesRegex(ValueError,'frozen'):_va_apply_patch(candidate,invalid,rule)

    def test_shared_unchanged_segment_has_linked_presentation_in_each_structure(self):
        from company_initiation.historic_construction.model_contract import _historical_reporting_blocks
        cell=lambda n:dict(value=n,status='actual',source_refs=[])
        data=dict(currency='USD',segments=[dict(id='new',label='New'),dict(id='shared',label='Shared')],observations=[],
            model_configuration=dict(va_reporting_context=dict(entity_versions=[dict(entity_id='old',label='Old',entity_kind='legacy_segment')],
                hierarchies=[dict(entity_ids=['old','shared'])])))
        rows={name:dict(id=name,label='Sales',entity_id=name[:-6],unit='USDm',metric_type='flow',cells={'2024-FY':cell(n)})
            for name,n in [('new_sales',60),('shared_sales',40),('old_sales',60)]}
        ordered,checks=_historical_reporting_blocks(data,rows,[dict(id='2024-FY')]);by_id={r['id']:r for r in ordered}
        old=by_id['reporting_historical_1_sales']['cells']['2024-FY']
        self.assertEqual(old['value'],100)
        self.assertIn('reporting_historical_1__shared_sales',old['model_bindings'].values())
        self.assertEqual(by_id['reporting_historical_1__shared_sales']['cells']['2024-FY']['model_bindings'],dict(source='shared_sales'))

    def test_saved_nestle_resolver_citations_validate_only_for_the_queried_findings(self):
        from company_initiation.historic_construction.workflow import _va_resolve_evidence
        from company_initiation.shared_project import find_project_root
        run=find_project_root()/'outputs/construct_research_20261031T161220Z_f9c12a41'
        if not (run/'record.json').exists():self.skipTest('Saved live resolver reply absent; synthetic resolver tests still run')
        record=json.loads((run/'record.json').read_text(encoding='utf-8'));call=next(c for c in record['calls'] if c['stage']=='company_va_evidence_resolution')
        payload=call['request']['payload'];data=json.loads((run/'va_mapping_progress.json').read_text(encoding='utf-8'))['company_inputs']
        journal=self.journal(data);seen=[]
        def stage(name,prompt,p,schema,validator):
            seen.append(p);old={c['row_key']:c for c in call['result']['conclusions']}
            result=dict(conclusions=[dict(copy.deepcopy(old[q['row_key']]),finding_id=q['finding_id']) for q in p['questions']],summary='Saved response representation replay; no new financial verdict')
            return validator(result)
        journal.stage=stage
        answer=_va_resolve_evidence(journal,data,payload['rows'],dict(issues=[dict(q,kind='financial_evidence') for q in payload['questions']]),payload['original_sections'],payload['headers'])
        self.assertEqual(len(answer['conclusions']['conclusions']),6);self.assertEqual(len(seen[0]['rows']),6)
        manifest={(r['source_id'],r['unit_id']) for r in seen[0]['citation_manifest']}
        self.assertTrue(all((row['source_ref']['source_id'],row['source_ref']['unit_id']) in manifest for row in seen[0]['rows']))
        self.assertNotIn('original_sections',answer)

    def test_saved_loreal_document_coverage_is_not_an_entity_start_date(self):
        from company_initiation.historic_construction.workflow import _va_validate_reporting_context
        from company_initiation.shared_project import find_project_root
        run=find_project_root()/'outputs/construct_research_20261031T161225Z_4bcf13ae'
        if not (run/'record.json').exists():self.skipTest('Saved L Oreal scope absent')
        record=json.loads((run/'record.json').read_text(encoding='utf-8'))
        call=next(c for c in record['calls'] if c['stage']=='company_reporting_scope');scope=call['result'];units={}
        for unit in call['request']['payload']['evidence']:units.setdefault(unit['source_id'],{})[unit['unit_id']]=unit
        with self.assertRaisesRegex(ValueError,'birth/death'):
            _va_validate_reporting_context(scope['historical_reporting_context'],units,scope['segments'])
        supported=copy.deepcopy(scope['historical_reporting_context'])
        for item in supported['entity_versions']+supported['hierarchies']:item.update(effective_from=None,effective_to=None)
        _va_validate_reporting_context(supported,units,scope['segments'])

    def test_saved_company_mapping_context_is_compacted_without_building_or_ai(self):
        from company_initiation.historic_construction.workflow import _va_history_inputs
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.historic_construction.periods import build_periods
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        from company_initiation.shared_project import find_project_root
        workspace=find_project_root();checked=0
        for suffix in ['161220Z_f9c12a41','161225Z_4bcf13ae','161230Z_a3298f59']:
            run=workspace/'outputs'/('construct_research_20261031T'+suffix)
            if not (run/'record.json').exists():continue
            record=json.loads((run/'record.json').read_text(encoding='utf-8'))
            original=next(c['request']['payload'] for c in record['calls'] if c['stage']=='company_va_row_mapping')
            data=json.loads((run/'va_mapping_progress.json').read_text(encoding='utf-8'))['company_inputs']
            data.update(observations=[],historical={},active_basis_by_period={})
            with tempfile.TemporaryDirectory() as temp:
                store=SourceStore(Path(temp));source=next(s for s in record['sources'] if s.get('dataset_role')=='company_reported')
                store.restore(source,archive_root=workspace/'outputs')
                catalog={s['id']:s for s in record['sources']};periods=build_periods(data['history_years']+[max(data['history_years'])+1],data['fiscal_calendar'])
                journal=self.journal(data);captured=[]
                def capture(name,prompt,payload,schema,**kwargs):
                    captured.append(payload);raise RuntimeError('Metadata capture only; no mapping call')
                journal.patch_stage=capture
                with patch('company_initiation.historic_construction.workflow._va_incomplete_output'),self.assertRaisesRegex(RuntimeError,'Metadata capture only'):
                    _va_history_inputs(journal,data,store,catalog,[source['id']],periods,dict(roles=integrated_role_contract()),supporting_evidence=original['reporting_evidence'])
                self.assertEqual(len(captured),1);new=captured[0]
                self.assertLess(len(new['period_catalogue']),len(original['period_catalogue']))
                self.assertLess(len(json.dumps(new,ensure_ascii=False)),.7*len(json.dumps(original,ensure_ascii=False)))
                self.assertTrue(all('numbers' not in unit for unit in new['reporting_evidence']))
                self.assertTrue(all(key in new['period_catalogue'] for row in new['target_rows'] for key in row['source_period_keys']))
            checked+=1
        if not checked:self.skipTest('Saved company request payloads absent')
        self.assertEqual(checked,3)


class LatestHistoricalReliabilityTests(unittest.TestCase):
    """Offline reproductions of v5 interactions; no new real-company builds."""
    fixture=CompanyReportedVAConstructionTests.fixture
    journal=CompanyReportedVAConstructionTests.journal
    case=VAMappingRepairTests.case
    candidate=VAMappingRepairTests.candidate

    def saved(self,suffix):
        from company_initiation.shared_project import find_project_root
        run=find_project_root()/'outputs'/('construct_research_20261031T'+suffix)
        if not (run/'record.json').is_file():self.skipTest('Saved latest company evidence absent')
        record=json.loads((run/'record.json').read_text(encoding='utf-8'))
        return run,record,json.loads((run/'va_mapping_progress.json').read_text(encoding='utf-8'))['company_inputs']

    def test_repeated_missing_entity_exports_from_actual_nestle_progress(self):
        from company_initiation.historic_construction.model_contract import historical_model
        from company_initiation.historic_construction.model_excel import write_historical_output
        run,record,data=self.saved('171719Z_7ec712c2')
        original=(run/'company_model_inputs_progress.json').read_bytes()
        spec=historical_model(data)
        ids=[r['id'] for r in spec['rows']];self.assertEqual(len(ids),len(set(ids)))
        missing=[r for r in spec['rows'] if 'legacy_nestle_health_science_gmb_sales' in r['id']]
        self.assertGreaterEqual(len(missing),2);self.assertTrue(all(not r['cells'] for r in missing))
        with tempfile.TemporaryDirectory() as temp:
            written=write_historical_output(Path(temp),data,incomplete=True)
            validation=json.loads((Path(temp)/written['validation']).read_text(encoding='utf-8'))
            self.assertEqual(validation['saved_value_and_formula_readback'],'passed')
            self.assertEqual(validation['saved_layout'],'passed')
        self.assertEqual((run/'company_model_inputs_progress.json').read_bytes(),original)

    def test_duplicate_targets_are_source_keys_and_canonical_ids_are_python_owned(self):
        from company_initiation.historic_construction.workflow import _va_schema,_va_assess
        from company_initiation.shared_runtime import validate_shape
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        schema,_=_va_schema([r['row_key'] for r in rows],['money'])
        candidate=self.candidate(data,rows)
        for decision in candidate['decisions']:
            decision['versions'][0]['row_id']=None
            decision['versions'][0]['entity_kind']='supplementary'
        validate_shape(candidate,schema)
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertFalse(report['issues']);self.assertEqual({f['row_id'] for f in report['facts']},{'sales','cash','manufacturing_sales'})
        self.assertTrue(all(d['versions'][0]['row_id'] is None for d in candidate['decisions']))
        duplicate=dict(row_key=rows[0]['row_key'],action='exclude',reason_code='duplicate',reason='Same source series',duplicate_of='sales',evidence_refs=[dict(source_id=rows[0]['source_id'],unit_id=rows[0]['unit_id'])])
        invalid=_va_assess(dict(decisions=[duplicate],gaps=[]),rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertTrue(any('Duplicate exclusion' in i['detail'] for i in invalid['issues']))

    def test_missing_interval_append_preserves_existing_versions_without_copying_them(self):
        from company_initiation.historic_construction.workflow import _va_assess,_va_patch_contract,_va_apply_patch,_va_schema
        from company_initiation.shared_runtime import digest,validate_shape
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows);decision=next(d for d in candidate['decisions'] if d['versions'][0]['row_id']=='sales')
        row=next(r for r in rows if r['row_key']==decision['row_key']);ref=dict(source_id=source['id'],unit_id=row['unit_id'])
        version=decision['versions'][0];version.update(period_kinds=['FY'],version_refs=[ref]);frozen=copy.deepcopy(version)
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        rules=_va_patch_contract(candidate,report,_va_schema([r['row_key'] for r in rows],['money'])[1])
        paths=rules['permitted_changes'][0]['paths'];self.assertIn('versions.append',paths);self.assertNotIn('versions.0',paths)
        half=dict(version,period_kinds=['H1'])
        proposal=dict(changes=[dict(row_key=decision['row_key'],expected_digest=digest(decision),path='versions.append',value=[half])])
        validate_shape(proposal,rules['schema']);updated=_va_apply_patch(candidate,proposal,rules)
        self.assertEqual(updated['decisions'][0]['versions'][0],frozen)
        self.assertFalse(_va_assess(updated,rows,rows,data,store,data['sources'],periods,contract,evidence)['issues'])
        self.assertEqual(candidate['decisions'][0]['versions'],[frozen])

    def test_actual_danone_note_is_not_silently_added_to_bulk_selection(self):
        from company_initiation.historic_construction.workflow import _identity_source_selection
        run,record,data=self.saved('171726Z_e9169866')
        catalog={s['id']:s for s in json.loads((run/'inventory.json').read_text(encoding='utf-8'))['sources']}
        original=next(c['result'] for c in record['calls'] if c['stage']=='company_identity_sources')
        note=next(s for s in catalog.values() if s['local_path']=='financial_reports/2026_reorganisation.pdf')
        self.assertNotIn(note['id'],original['source_ids'])
        journal=self.journal(data);journal.stage=lambda n,p,x,s,validator:validator(copy.deepcopy(original))
        selected=_identity_source_selection(journal,data['company'],'2026-10-31',catalog,'Saved selection replay')
        self.assertNotIn(note['id'],selected['source_ids'])
        self.assertEqual(selected['source_ids'],original['source_ids'])

    def test_scope_date_correction_uses_pdf_definitions_but_numbers_stay_in_va(self):
        from company_initiation.historic_construction.workflow import _va_assess,_va_resolve_evidence
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        note=dict(source_id='synthetic_note',unit_id='page:1',text='SYNTHETIC: new organisation starts 2025-01-01; 2024 comparatives are restated. Table amount 999999.')
        ref={k:note[k] for k in ('source_id','unit_id')}
        context=dict(declarations=[dict(topic='reporting_change',change_kind='redefinition',change_date='2025-01-01',
            detail='Synthetic restatement',effective_from='2024-01-01',effective_to=None,source_refs=[ref])],
            entity_versions=[dict(entity_id='manufacturing',label='Manufacturing',entity_kind='current_segment',effective_from='2025-01-01',effective_to=None,source_refs=[ref])],
            hierarchies=[dict(entity_ids=['manufacturing'],effective_from='2025-01-01',effective_to=None,source_refs=[ref])])
        data['model_configuration'].update(va_reporting_context=context,va_reporting_note_source_ids=['synthetic_note'])
        candidate=self.candidate(data,rows);report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence+[note])
        self.assertTrue(any('outside its cited' in i['detail'] for i in report['issues']))
        revised=copy.deepcopy(context)
        for item in revised['entity_versions']+revised['hierarchies']:item['effective_from']='2024-01-01'
        journal=self.journal(data)
        def resolve(name,prompt,payload,schema,validator):
            self.assertIn('do not extract restated tables',prompt)
            return validator(dict(conclusions=[dict(row_key=q['row_key'],finding_id=q['finding_id'],status='supported',detail='The note establishes comparative applicability, not input numbers',source_refs=[ref])
                for q in payload['questions']],summary='Synthetic scope correction',reporting_context=revised))
        journal.stage=resolve
        targets=[dict(row_key=r['row_key'],source_ref=dict(source_id=source['id'],unit_id=r['unit_id'])) for r in rows]
        _va_resolve_evidence(journal,data,targets,report,[note],[])
        after=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence+[note])
        self.assertFalse(after['issues'])
        self.assertTrue(all(f['source_refs'][0]['source_id']==source['id'] for f in after['facts']))
        self.assertEqual(next(f['value'] for f in after['facts'] if f['row_id']=='manufacturing_sales' and f['period_id']=='2024-FY'),100)
        self.assertNotIn(999999,{f['value'] for f in after['facts']})
        self.assertIn('va_reporting_context_revision.json',journal.artifacts)

    def test_actual_loreal_unresolved_alternate_is_audited_without_forcing_a_definition(self):
        from company_initiation.historic_construction.evidence import SourceStore
        from company_initiation.historic_construction.periods import build_periods
        from company_initiation.historic_construction.model_contract import integrated_role_contract
        from company_initiation.historic_construction.workflow import _va_assess
        run,record,data=self.saved('171721Z_591489d0')
        candidate=json.loads(next(run.glob('*_initial.json')).read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temp:
            store=SourceStore(Path(temp));source=next(s for s in record['sources'] if s.get('dataset_role')=='company_reported')
            store.restore(source,archive_root=run.parent)
            periods=build_periods(data['history_years']+[max(data['history_years'])+1],data['fiscal_calendar'])
            rows=store.company_reported_rows([source['id']],periods,as_of=data['model_configuration']['as_of'])
            keys={d['row_key'] for d in candidate['decisions']};targets=[r for r in rows if r['row_key'] in keys]
            evidence=store.read_documents([dict(source_id=source['id'],unit_id=rows[0]['unit_id'])],historical_years=set(data['history_years']))
            report=_va_assess(candidate,targets,rows,data,store,{source['id']:source},periods,dict(roles=integrated_role_contract()),evidence)
        unknown=next(q for q in report['quarantined_rows'] if q['row_key']=='row_176')
        self.assertFalse(unknown['model_selection_eligible']);self.assertTrue(unknown['cells']);self.assertTrue(unknown['supported_alternative_ids'])
        self.assertFalse(any(i['row_key']=='row_176' for i in report['issues']))
        # A replay of representation/coverage behaviour does not approve the retained profit definition.
        self.assertTrue(any('operating' in f['row_id'] for f in report['facts']))

    def test_a_genuinely_missing_essential_concept_stays_blocked(self):
        from company_initiation.historic_construction.workflow import _va_assess
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        candidate=self.candidate(data,rows)
        decision=next(d for d in candidate['decisions'] if d['versions'][0]['row_id']=='sales')
        decision['versions'][0]['definition_status']='unresolved'
        report=_va_assess(candidate,rows,rows,data,store,data['sources'],periods,contract,evidence)
        self.assertTrue(any(i.get('kind')=='financial_evidence' for i in report['issues']))
        self.assertFalse(report['quarantined_rows'])

    def test_fresh_alternate_series_is_reviewed_and_audited_through_historical_finalization(self):
        from openpyxl import load_workbook
        from company_initiation.historic_construction.evidence import SourceStore,inventory_local_sources
        from company_initiation.historic_construction.workflow import _va_history_inputs,_review_va_history,complete_historical_model
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        path=archive/source['local_path'];book=load_workbook(path);sheet=book.active
        for number,label,annual,half in [(12,'Operating income',80,35),(13,'Operating profit',83,37)]:
            sheet.cell(number,4,label);sheet.cell(number,5,'USDM');sheet.cell(number,6,'Analytics')
            sheet.cell(number,7,annual);sheet.cell(number,8,annual);sheet.cell(number,9,half)
        book.save(path);book.close()
        source=next(s for s in inventory_local_sources(archive)['sources'] if s.get('dataset_role')=='company_reported')
        store=SourceStore(root/'alternate');store.add_local(source,root=archive);data['sources']={source['id']:source}
        journal=self.journal(data);original=journal.stage;reviews=[]
        def stage(name,prompt,payload,schema,validator):
            answer=original(name,prompt,payload,schema,lambda a:a)
            if name=='company_va_row_mapping':
                labels={r['row_key']:r for r in payload['target_rows']}
                for i,decision in enumerate(answer['decisions']):
                    label=labels[decision['row_key']]['label']
                    if label=='Operating income':
                        decision['versions'][0].update(row_id=None,financial_role='operating_profit',definition_id='sourced_operating_result')
                    if label=='Operating profit':
                        answer['decisions'][i]=dict(row_key=decision['row_key'],action='pending',reason='Conflicting financial definition is unresolved',evidence_refs=[labels[decision['row_key']]['source_ref']])
            if name in ('company_va_core_review','company_va_history_review'):
                reviews.append(name);self.assertTrue(payload['quarantined_series'])
            return validator(answer)
        journal.stage=stage
        evidence=_va_history_inputs(journal,data,store,data['sources'],[source['id']],periods,contract)
        self.assertEqual(data['historical']['operating_profit']['values']['2024'],80)
        self.assertEqual(len(data['model_configuration']['va_unresolved_series']),1)
        self.assertTrue(journal.artifacts['va_unresolved_series.json'][0]['cells'])
        _review_va_history(journal,data,evidence)
        inputs=root/'reviewed_inputs.json';inputs.write_text(json.dumps(data),encoding='utf-8')
        output=complete_historical_model(root,data['company'],archive,inputs)
        self.assertEqual(json.loads((output/'record.json').read_text())['status'],'historical_complete_provisional')
        self.assertEqual(reviews,['company_va_history_review'])
        self.assertTrue((output/'va_unresolved_series.json').is_file())
        self.assertIn('va_unresolved_series.json',json.loads((output/'record.json').read_text())['artifacts'])
        validation=json.loads((output/'historical_workbook_validation.json').read_text())
        self.assertTrue(any(c['area']=='unresolved_alternate' and c['status']=='WARNING' for c in validation['checks']))

    def test_unresolved_audit_changes_invalidate_saved_financial_review(self):
        from company_initiation.historic_construction.workflow import combined_history_fingerprint
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        before=combined_history_fingerprint(data)
        data['model_configuration']['va_unresolved_series']=[dict(row_key='unresolved',status='unresolved_alternate')]
        self.assertNotEqual(before,combined_history_fingerprint(data))

    def test_pending_evidence_finding_reaches_resolver_even_without_field_paths(self):
        from company_initiation.historic_construction.workflow import _va_resolve_evidence
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        row=rows[0];target=dict(row_key=row['row_key'],source_ref=dict(source_id=source['id'],unit_id=row['unit_id']))
        note=dict(source_id='synthetic',unit_id='definition',text='SYNTHETIC: definition remains unknown')
        journal=self.journal(data);calls=[]
        def resolve(name,prompt,payload,schema,validator):
            calls.append(name)
            return validator(dict(conclusions=[dict(row_key=target['row_key'],finding_id=payload['questions'][0]['finding_id'],status='unresolved',detail='Insufficient definition evidence',source_refs=[dict(source_id='synthetic',unit_id='definition')])],summary='Unresolved'))
        journal.stage=resolve
        result=_va_resolve_evidence(journal,data,[target],dict(issues=[dict(row_key=row['row_key'],detail='Financial definition unknown',paths=['$'],kind='financial_evidence')]),[note],[])
        self.assertEqual(calls,['company_va_evidence_resolution']);self.assertEqual(result['conclusions']['conclusions'][0]['status'],'unresolved')

    def test_new_evidence_gap_after_patch_is_resolved_before_another_mapping_call(self):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.shared_runtime import RunJournal,_object,INTEGER
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);root=Path(temporary.name)
        provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY');journal=RunJournal(root,provider,dict(limits=dict(usd=20,repairs=2)))
        schema=_object(value=INTEGER);ready=False;phases=[]
        def assess(candidate):
            return dict(issues=[] if ready else [dict(row_key='row_1',detail='Financial gap' if candidate['value'] else 'Mapping gap',paths=['$'],kind='financial_evidence' if candidate['value'] else 'mapping')])
        def resolve(report):
            nonlocal ready
            phases.append(report['issues'][0]['kind'])
            if phases[-1]=='financial_evidence':ready=True
        def complete(**kwargs):
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=20,total_tokens=120),output=[])
            return dict(value=1)
        with patch.object(provider,'complete',side_effect=complete) as api:
            result=journal.patch_stage('fixture','fixture',{},schema,initial_candidate=dict(value=0),assess=assess,
                patch_contract=lambda c,r:dict(schema=schema,permitted_changes=[]),apply_patch=lambda c,p,r:p,resolve_context=resolve)
        self.assertEqual(phases,['mapping','financial_evidence']);self.assertEqual(api.call_count,1);self.assertEqual(result,dict(value=1))

    def test_reporting_date_schema_uses_full_iso_dates_with_unknown_null(self):
        import re
        from company_initiation.historic_construction.workflow import _va_date_schema,_va_validate_reporting_context
        schema=_va_date_schema();self.assertIn('null',schema['type'])
        self.assertIsNone(re.fullmatch(schema['pattern'],'2024'));self.assertIsNotNone(re.fullmatch(schema['pattern'],'2024-12-31'))
        with self.assertRaises(ValueError):
            _va_validate_reporting_context(dict(declarations=[dict(change_kind='redefinition',change_date='2024',effective_from=None,effective_to=None,source_refs=[])],entity_versions=[],hierarchies=[]),{},[])


class SimplifiedHistoricalPipelineTests(unittest.TestCase):
    fixture=CompanyReportedVAConstructionTests.fixture
    journal=CompanyReportedVAConstructionTests.journal
    case=VAMappingRepairTests.case

    def run_native(self,*,currency='USD',year_end='12-31',reorg=False,review_error=False,bulk=False):
        from company_initiation.shared_ai import OpenAIProvider
        from company_initiation.historic_construction.workflow import research_company_inputs,complete_historical_model,ensure_company_history_research
        root,archive,source,store,periods,data,rows,evidence,contract=self.case(currency=currency,year_end=year_end,reorganized=reorg)
        if bulk:
            folder=archive/'financial_reports';folder.mkdir()
            for i in range(36):(folder/f'2016_restatement_{i}.txt').write_text('Irrelevant restated amount 999999\n'*1000,encoding='utf-8')
        template=self.journal(data);provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY');calls=[];captured=[]
        def complete(**kwargs):
            payload=kwargs['payload'];stage=payload['stage'];calls.append(stage);captured.append(payload)
            provider.last_response=dict(model='gpt-6-luna',usage=dict(input_tokens=100,output_tokens=40,total_tokens=140),output=[])
            if stage=='company_va_scope':
                ref=payload['va']['native_rows'][0]['source_ref']
                context=dict(declarations=[],entity_versions=[],hierarchies=[])
                if reorg:
                    context=dict(declarations=[dict(topic='reporting_change',change_kind='redefinition',change_date='2024-04-01',detail='SYNTHETIC reported reorganisation',effective_from='2024-04-01',effective_to=None,source_refs=[ref])],
                        entity_versions=[dict(entity_id='legacy',entity_kind='legacy_segment',label='Legacy',effective_from=None,effective_to='2024-03-31',source_refs=[ref])],
                        hierarchies=[dict(entity_ids=['legacy'],effective_from=None,effective_to='2024-03-31',source_refs=[ref]),
                            dict(entity_ids=['equipment','services'],effective_from='2024-04-01',effective_to=None,source_refs=[ref])])
                return dict(currency=currency,fiscal_year_end=year_end,full_statement_frequency='half_year' if reorg else 'quarterly',
                    reporting_basis='Company reported',segments=data['segments'],corporate_label='Corporate',historical_reporting_context=context,
                    source_refs=[ref],questions=[],source_ids=[])
            if stage in ('company_va_row_mapping','company_va_history_review'):
                answer=template.stage(stage,'SYNTHETIC provider fixture',payload,kwargs['schema'],lambda a:a)
                if stage=='company_va_history_review' and review_error:answer['checks'][0].update(status='error',detail='SYNTHETIC material definition remains unresolved')
                return answer
            raise AssertionError('Historical build dispatched a removed document/forecast/early-review stage: '+stage)
        with patch.object(provider,'complete',side_effect=complete),patch('company_initiation.shared_ai.urlopen',side_effect=AssertionError('No external network')):
            inputs=research_company_inputs(root,data['company'],archive,as_of=data['model_configuration']['as_of'],years=data['history_years'],fresh=True,provider=provider)
        with patch('company_initiation.shared_ai.OpenAIProvider.from_env',side_effect=AssertionError('Historical finalization must not call AI')):
            checked=ensure_company_history_research(root,data['company'],archive,inputs,as_of=data['model_configuration']['as_of'])
            output=complete_historical_model(root,data['company'],archive,checked)
        return root,archive,inputs,output,calls,captured

    def test_full_historical_entry_two_structures_and_no_forecast_or_bulk_document_calls(self):
        from openpyxl import load_workbook
        for currency,end,reorg in [('USD','12-31',False),('JPY','03-31',True)]:
            with self.subTest(currency=currency):
                root,archive,inputs,output,calls,payloads=self.run_native(currency=currency,year_end=end,reorg=reorg,bulk=True)
                self.assertEqual(calls,['company_va_scope','company_va_row_mapping','company_va_history_review'])
                record=json.loads((output/'record.json').read_text(encoding='utf-8'));self.assertEqual(record['status'],'historical_complete_provisional')
                self.assertEqual(record['stage_outputs']['historical']['status'],'exported')
                data=json.loads(inputs.read_text(encoding='utf-8'))
                self.assertEqual(data['driver_map'],[]);self.assertNotIn('financial_contracts',data['model_configuration'])
                self.assertEqual(data['model_configuration']['forecast_preparation_status'],'pending')
                self.assertNotIn('999999',json.dumps(payloads[0]));self.assertLess(len(json.dumps(payloads[0])),50000)
                self.assertEqual(data['historical']['sales']['values']['2024'],100)
                book=load_workbook(output/'historical_model.xlsx',data_only=False)
                try:
                    self.assertIn('VA Source',book.sheetnames);self.assertGreater(book['Model'].max_column,3)
                    self.assertFalse(any('Forecast' in str(c.value) for row in book['Model'] for c in row))
                finally:book.close()

    def test_material_review_error_is_recorded_once_and_exports_incomplete_history(self):
        root,archive,inputs,output,calls,payloads=self.run_native(review_error=True)
        self.assertEqual(calls.count('company_va_history_review'),1)
        record=json.loads((output/'record.json').read_text(encoding='utf-8'));self.assertEqual(record['status'],'incomplete')
        self.assertTrue((output/'historical_model_incomplete.xlsx').is_file())
        self.assertTrue((inputs.parent/'company_model_inputs.json').is_file())

    def test_latest_loreal_populated_revenue_is_coverage_not_a_pdf_evidence_gap(self):
        from company_initiation.historic_construction.workflow import _va_coverage_gaps,_va_resolve_evidence
        from company_initiation.historic_construction.periods import build_periods
        from company_initiation.shared_project import find_project_root
        run=find_project_root()/'outputs/construct_research_20261031T175450Z_beebdd62'
        if not (run/'va_mapping_progress.json').exists():self.skipTest('Latest saved failure unavailable')
        data=json.loads((run/'va_mapping_progress.json').read_text())['company_inputs']
        periods=build_periods(data['history_years']+[max(data['history_years'])+1],data['fiscal_calendar'])
        self.assertFalse(_va_coverage_gaps(data,data['observations'],periods))
        journal=self.journal(data);journal.stage=lambda *a,**k:self.fail('A financial-role coverage issue must not launch PDF proof')
        result=_va_resolve_evidence(journal,data,[],dict(issues=[dict(row_key='row_87',kind='reporting_coverage',paths=['$'],detail='Internal binding')]),[dict(source_id='note',unit_id='page:1',text='irrelevant')],[])
        self.assertIsNone(result)

    def test_schema_limits_fail_before_a_request_or_reservation(self):
        from company_initiation.shared_runtime import RunJournal
        from company_initiation.shared_ai import OpenAIProvider,AIError
        from company_initiation.shared_project import find_project_root
        run=find_project_root()/'outputs/construct_research_20261031T175450Z_8d1bd543'
        if not (run/'record.json').exists():self.skipTest('Latest saved failure unavailable')
        original=json.loads((run/'record.json').read_text(encoding='utf-8'));schema=original['calls'][-1]['request']['schema']
        with tempfile.TemporaryDirectory() as temp:
            provider=OpenAIProvider(api_key='SYNTHETIC-OFFLINE-KEY');journal=RunJournal(Path(temp),provider,dict(limits=dict(usd=20,repairs=2)))
            with patch.object(provider,'complete',side_effect=AssertionError('Invalid schema must not dispatch')) as api:
                with self.assertRaisesRegex(AIError,'no request reserved or dispatched'):journal.ask('fixture','fixture',{},schema)
            self.assertFalse(journal.state['calls']);self.assertIsNone(journal.state['pending_call']);self.assertEqual(api.call_count,0)

    def test_targeted_local_context_reads_only_the_requested_original(self):
        from company_initiation.historic_construction.workflow import _va_local_context
        root,archive,source,store,periods,data,rows,evidence,contract=self.case()
        journal=self.journal(data);calls=[]
        original=dict(source_id='calendar',unit_id='page:1',text='SYNTHETIC fiscal calendar and complete statement attribution',numbers=[])
        catalog={'calendar':dict(id='calendar',category='financial_reports',format='pdf',title='Calendar note'),
            'unrelated':dict(id='unrelated',category='financial_reports',format='pdf',title='Unrelated old restatement'),
            'table':dict(id='table',category='financial_reports',format='xlsx',title='Restated numerical appendix')}
        def stage(name,prompt,payload,schema,validate):
            calls.append(name);self.assertEqual({s['id'] for s in payload['catalog']},{'calendar','unrelated'})
            return validate(dict(source_ids=['calendar'],reason='Resolve fiscal year end'))
        journal.stage=stage
        def documents(ids):self.assertEqual(ids,['calendar']);return [original]
        selected=_va_local_context(journal,data['company'],catalog,documents,['Fiscal year end is unclear'])
        self.assertEqual(selected,[original]);self.assertEqual(calls,['company_history_sources'])

    def test_latest_nestle_resolver_schema_is_compact_and_keeps_all_selected_sections(self):
        from company_initiation.historic_construction.workflow import _va_resolve_evidence
        from company_initiation.shared_project import find_project_root
        run=find_project_root()/'outputs/construct_research_20261031T175450Z_8d1bd543'
        if not (run/'record.json').is_file():self.skipTest('Latest saved failure unavailable')
        record=json.loads((run/'record.json').read_text(encoding='utf-8'))
        payload=record['calls'][-1]['request']['payload']
        data=json.loads((run/'company_model_inputs_progress.json').read_text(encoding='utf-8'))
        journal=self.journal(data);captured=[]
        def stage(name,prompt,context,schema,validate):
            captured.append(schema)
            self.assertEqual(len(context['original_sections']),len(payload['original_sections']))
            self.assertLess(len(json.dumps(schema)),10000)
            ref=context['citation_manifest'][0]
            return validate(dict(conclusions=[dict(row_key=q['row_key'],finding_id=q['finding_id'],status='unresolved',detail='Synthetic replay retains uncertainty',source_refs=[ref]) for q in context['questions']],summary='Offline request-contract replay'))
        journal.stage=stage
        result=_va_resolve_evidence(journal,data,payload['rows'],dict(issues=[dict(q,kind='financial_evidence') for q in payload['questions']]),payload['original_sections'],payload['headers'])
        self.assertTrue(captured);self.assertTrue(result['conclusions']['conclusions'])

    def test_incomplete_history_prevents_forecast_configuration_dispatch(self):
        from company_initiation.forecast_construction.workflow import prepare_forecast_inputs
        root,archive,inputs,output,calls,payloads=self.run_native(review_error=True)
        with patch('company_initiation.shared_ai.OpenAIProvider.from_env',side_effect=AssertionError('No forecast AI for incomplete history')):
            with self.assertRaisesRegex(ValueError,'requires completed historical construction'):
                prepare_forecast_inputs(root,json.loads(inputs.read_text(encoding='utf-8'))['company'],archive,inputs)
        self.assertTrue((output/'historical_model_incomplete.xlsx').is_file())


if __name__=='__main__':unittest.main()
