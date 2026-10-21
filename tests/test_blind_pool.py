import json
import tempfile
import unittest
from pathlib import Path

from tools.reviewer import blind_pool

UUID = '42b4f896-1071-4617-bcba-e1110a1fc457'


def association(n, expectation, record='openai/code-spec-v5/sol-high-a1'):
    cid = f'code-spec-reviewer:default-{UUID}-instance-1:scope-1:problem-{n}:CODE-SPEC-FINDINGS:finding-{n}'
    return {'stable_id': f'code-spec-reviewer:default:scope-1:problem-{n}:CODE-SPEC-FINDINGS:finding-{n}', 'record': record,
            'candidateId': cid, 'instanceId': f'default-{UUID}-instance-1', 'kind': 'association',
            'check': 'CODE-SPEC-FINDINGS', 'allowedDecisions': ['matched', 'not-matched'], 'expectation': expectation,
            'finding': f'- finding {n}', 'result': 'gap', 'evidence': [{'filePath': 'src/a.mjs', 'line': n}],
            'referenceTerms': ['hidden'], 'problemCaseIndex': n}


def finding(n, record='anthropic/code-spec-v5/opus-low-a1', line=1):
    cid = f'code-spec-reviewer:default-{UUID}-instance-1:scope-1:unassociated:CODE-SPEC-FINDINGS:finding-{n}'
    return {'stable_id': f'code-spec-reviewer:default:scope-1:unassociated:CODE-SPEC-FINDINGS:finding-{n}', 'record': record,
            'candidateId': cid, 'instanceId': f'default-{UUID}-instance-1', 'kind': 'finding', 'check': 'CODE-SPEC-FINDINGS',
            'allowedDecisions': ['unsupported', 'supported', 'problem-1'], 'expectation': None, 'finding': f'- extra {n}',
            'result': 'gap', 'evidence': [{'filePath': 'src/a.mjs', 'line': line}],
            'problemOptions': [{'decision': 'problem-1', 'expectation': 'E1'}], 'cleanTargets': [], 'scope': 'x'}


def control(cid, kind, family, expected, expectation='E1'):
    item = {'kind': kind, 'check': 'CODE-SPEC-FINDINGS', 'expectation': expectation if kind == 'association' else None,
            'finding': f'- control {cid}', 'result': 'gap', 'evidence': [{'filePath': 'src/b.mjs', 'line': 9}],
            'allowedDecisions': ['matched', 'not-matched'] if kind == 'association' else ['unsupported', 'supported']}
    if kind == 'finding':
        item.update(problemOptions=[], cleanTargets=[])
    return {'id': cid, 'family': family, 'model': None, 'expected': expected, 'item': item}


class BlindPoolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.adj, self.keys, self.root, self.registry = t / 'ADJ', t / 'keys', t / 'score', t / 'anchors'
        anchors = [control(f'a{i:02d}', 'association', ('openai', 'anthropic', 'strata')[i % 3], 'matched') for i in range(12)]
        synthetic = [dict(control('s01', 'finding', 'strata', 'unsupported'), type='registered-decoy'),
                     dict(control('s02', 'association', 'openai', 'not-matched', 'E2'), type='mismatch')]
        blind_pool.save(self.registry / 'code-spec-v5.json', {'scenario': 'code-spec-v5', 'anchors': anchors,
                                                              'synthetic': synthetic})
        self.candidates = t / 'c.json'
        blind_pool.save(self.candidates, [association(1, 'E1'), association(2, 'E2'), finding(7, line=1), finding(8, line=3)])

    def tearDown(self):
        self.tmp.cleanup()

    def built(self, **kw):
        return blind_pool.build('code-spec-v5', 'p', self.adj, self.keys, [self.candidates], self.registry, **kw)

    def answer(self, pool_name, wrong=(), real=None):
        key = json.loads((self.keys / f'key-{pool_name}.json').read_text())
        decisions = []
        for pid, meta in key['items'].items():
            if meta['source'] == 'instance':
                decision = (real or {}).get(meta['stable_id'].rsplit(':', 1)[1],
                                            'matched' if meta['kind'] == 'association' else 'unsupported')
            else:
                decision = meta['expected']
                if meta['control'] in wrong:
                    decision = 'not-matched' if decision == 'matched' else 'supported'
            decisions.append({'id': pid, 'decision': decision, 'reason': '可能如此' if decision == 'unsupported' else '一致'})
        path = self.adj / pool_name / f'decisions-{pool_name}.json'
        blind_pool.save(path, {'adjudicator': 'blind Opus high', 'decisions': decisions})
        return self.keys / f'key-{pool_name}.json', path

    def test_pool_follows_the_brief_and_hides_sources(self):
        [info] = self.built()
        self.assertEqual((info['items'], info['real'], info['controls']), (18, 4, 14))
        pool = json.loads((self.adj / 'p' / 'pool-p.json').read_text())
        text = json.dumps(pool)
        for hidden in (UUID, 'sol-high', 'opus-low', 'referenceTerms', 'stable_id', 'problemCaseIndex'):
            self.assertNotIn(hidden, text)
        for item in pool:
            self.assertEqual(list(item)[:4], ['id', 'group', 'kind', 'check'])
            self.assertEqual('problemOptions' in item, item['kind'] == 'finding')
        groups = {i['group'] for i in pool if i['expectation'] == 'E1'}
        self.assertEqual(len(groups), 1)
        self.assertFalse((self.adj / 'key-p.json').exists())

    def test_prompt_is_the_frozen_brief_plus_the_fairness_note(self):
        self.built()
        key = self.keys / 'key-p.json'
        with self.assertRaises(ValueError):
            blind_pool.prompt(key)  # view not staged yet
        (self.adj / 'p' / 'view').mkdir()
        (self.adj / 'p' / 'change.diff').write_text('')
        info = blind_pool.prompt(key)
        text = Path(info['prompt_path']).read_text()
        brief = blind_pool.brief_path('code-spec-v5').read_text()
        body = brief.replace('<ADJ>', str((self.adj / 'p').resolve())).replace('<名>', 'p').rstrip('\n')
        self.assertEqual(text, f'{body}\n\n{blind_pool.FAIRNESS_NOTE}\n')
        self.assertNotIn('<ADJ>', text)
        self.assertIn('来源', blind_pool.FAIRNESS_NOTE)
        self.assertEqual(json.loads(key.read_text())['prompt_sha256'], blind_pool.sha256_file(info['prompt_path']))
        relative = Path(blind_pool.prompt(key, adj_as='adj')['prompt_path']).read_text()
        self.assertEqual(relative, f"{brief.replace('<ADJ>', 'adj').replace('<名>', 'p').rstrip(chr(10))}\n\n{blind_pool.FAIRNESS_NOTE}\n")
        self.assertEqual(json.loads(key.read_text())['adj_as'], 'adj')
        (self.adj / 'p' / 'pool-other.json').write_text('[]')
        with self.assertRaises(ValueError):
            blind_pool.prompt(key)  # another pool in <ADJ>

    def test_each_pool_has_its_own_adj(self):
        infos = self.built(limit=17)
        self.assertGreater(len(infos), 1)
        for info in infos:
            self.assertEqual(sorted(p.name for p in Path(info['adj']).iterdir()), [f"pool-{info['pool']}.json"])

    def test_pools_split_by_whole_groups(self):
        infos = self.built(limit=17)
        self.assertEqual(sum(i['real'] for i in infos), 4)
        self.assertTrue(all(i['items'] <= 17 for i in infos))

    def test_split_writes_stores_and_review_lists(self):
        self.built()
        key, decisions = self.answer('p', real={'finding-8': 'supported'})
        verdict, review, _ = blind_pool.split(key, decisions, self.root)
        self.assertTrue(verdict['passed'])
        self.assertEqual(verdict['anchor_agreement_by_family']['openai']['rate'], 1.0)
        self.assertEqual(verdict['written'], 4)
        store = json.loads((self.root / 'openai/code-spec-v5/sol-high-a1/decisions.json').read_text())
        self.assertEqual(store['decisions']['code-spec-reviewer:default:scope-1:problem-1:CODE-SPEC-FINDINGS:finding-1']
                         ['decision'], 'matched')
        self.assertEqual([r['stable_id'].rsplit(':', 1)[1] for r in review['supported']], ['finding-8'])
        [disputed] = review['disputed_unsupported']
        self.assertIn('hedged reason', disputed['why'])

    def test_failed_controls_write_nothing(self):
        self.built()
        key, decisions = self.answer('p', wrong=('a00', 'a01'))
        verdict, _, _ = blind_pool.split(key, decisions, self.root)
        self.assertFalse(verdict['passed'])
        self.assertEqual(verdict['written'], 0)
        self.assertFalse(self.root.exists())
        key, decisions = self.answer('p', wrong=('s01',))
        self.assertFalse(blind_pool.split(key, decisions, self.root)[0]['passed'])

    def test_split_rejects_a_changed_id_set_or_decision(self):
        self.built()
        key, decisions = self.answer('p')
        value = json.loads(decisions.read_text())
        value['decisions'][0]['decision'] = 'problem-99'
        blind_pool.save(decisions, value)
        with self.assertRaises(ValueError):
            blind_pool.split(key, decisions, self.root)
        value['decisions'] = value['decisions'][1:]
        blind_pool.save(decisions, value)
        with self.assertRaises(ValueError):
            blind_pool.split(key, decisions, self.root)

    def test_decided_candidates_are_skipped_and_overrides_keep_history(self):
        self.built()
        key, decisions = self.answer('p')
        blind_pool.split(key, decisions, self.root)
        [info] = blind_pool.build('code-spec-v5', 'q', self.adj, self.keys, [self.candidates], self.registry,
                                  root=self.root)
        self.assertEqual((info['real'], info['already_decided_skipped']), (0, 4))
        sid = 'code-spec-reviewer:default:scope-1:unassociated:CODE-SPEC-FINDINGS:finding-7'
        blind_pool.override('anthropic/code-spec-v5/opus-low-a1', sid, 'supported', 'node 复现成立', root=self.root)
        store = json.loads((self.root / 'anthropic/code-spec-v5/opus-low-a1/decisions.json').read_text())
        self.assertEqual(store['decisions'][sid]['decision'], 'supported')
        self.assertEqual(store['history'][-1]['replaced']['decision'], 'unsupported')
        with self.assertRaises(ValueError):
            blind_pool.override('anthropic/code-spec-v5/opus-low-a1', sid, 'matched', 'x', root=self.root)

    def test_an_override_must_be_one_of_the_candidates_allowed_decisions(self):
        self.built()
        key, decisions = self.answer('p')
        blind_pool.split(key, decisions, self.root)
        record, sid = 'anthropic/code-spec-v5/opus-low-a1', 'code-spec-reviewer:default:scope-1:unassociated:CODE-SPEC-FINDINGS:finding-7'
        path = self.root / record / 'decisions.json'
        store = json.loads(path.read_text())
        self.assertEqual(store['decisions'][sid]['allowedDecisions'], ['unsupported', 'supported', 'problem-1'])
        # Well-formed but not offered for this candidate (the false-positive:clean-1 case of 10-22).
        for bad in ('false-positive:clean-1', 'problem-2'):
            with self.assertRaisesRegex(ValueError, 'not in allowedDecisions'):
                blind_pool.override(record, sid, bad, 'x', root=self.root)
        # A store written before allowedDecisions were kept: from the live candidate with the same fingerprint, or refused.
        del store['decisions'][sid]['allowedDecisions']
        blind_pool.save(path, store)
        with self.assertRaisesRegex(ValueError, 'allowedDecisions unknown'):
            blind_pool.override(record, sid, 'problem-1', 'x', root=self.root)
        other = finding(7, line=2)  # same stable id, other content: another fingerprint
        blind_pool.save(self.root / record / 'pending.json', [other])
        with self.assertRaisesRegex(ValueError, 'allowedDecisions unknown'):
            blind_pool.override(record, sid, 'problem-1', 'x', root=self.root)
        blind_pool.save(self.root / record / 'candidates.json', [finding(7)])
        new = blind_pool.override(record, sid, 'problem-1', 'node 复现成立', root=self.root)
        self.assertEqual((new['decision'], new['allowedDecisions']), ('problem-1', ['unsupported', 'supported', 'problem-1']))
        with self.assertRaisesRegex(ValueError, 'not in allowedDecisions'):
            blind_pool.override(record, sid, 'false-positive:clean-1', 'x', root=self.root)

    def test_stores_carry_fingerprints_and_a_changed_candidate_is_pooled_again(self):
        self.built()
        key, decisions = self.answer('p')
        blind_pool.split(key, decisions, self.root)
        store = json.loads((self.root / 'openai/code-spec-v5/sol-high-a1/decisions.json').read_text())
        entry = store['decisions'][association(1, 'E1')['stable_id']]
        self.assertEqual(entry['fingerprint'], blind_pool.fingerprint(association(1, 'E1'), 'code-spec-v5'))
        changed = association(1, 'E1')
        changed['evidence'] = [{'filePath': 'src/a.mjs', 'line': 99}]
        blind_pool.save(self.candidates, [changed, association(2, 'E2'), finding(7, line=1), finding(8, line=3)])
        [info] = blind_pool.build('code-spec-v5', 'q', self.adj, self.keys, [self.candidates], self.registry,
                                  root=self.root)
        self.assertEqual((info['real'], info['already_decided_skipped']), (1, 3))

    def test_stored_reads_the_store_each_time(self):
        self.assertEqual(blind_pool.stored(self.root, 'openai/code-spec-v5/sol-high-a1'), {})
        blind_pool.save(blind_pool.store_path(self.root, 'openai/code-spec-v5/sol-high-a1'),
                        {'decisions': {'x': {'decision': 'matched', 'fingerprint': 'f'}}, 'history': []})
        self.assertEqual(blind_pool.stored(self.root, 'openai/code-spec-v5/sol-high-a1'), {'x': 'f'})

    def test_every_pool_holds_a_not_matched_control(self):
        registry = json.loads((self.registry / 'code-spec-v5.json').read_text())
        registry['synthetic'] = [s for s in registry['synthetic'] if s['expected'] != 'not-matched']
        blind_pool.save(self.registry / 'code-spec-v5.json', registry)
        with self.assertRaises(ValueError):
            self.built()
        registry['anchors'].append(control('a99', 'association', 'strata', 'not-matched'))
        blind_pool.save(self.registry / 'code-spec-v5.json', registry)
        for seed in range(5):
            self.built(seed=seed, anchor_count=3)
            key = json.loads((self.keys / 'key-p.json').read_text())
            self.assertIn('not-matched', [m['expected'] for m in key['items'].values() if m['source'] != 'instance'])

    def test_the_key_directory_must_not_be_under_adj(self):
        with self.assertRaises(ValueError):
            blind_pool.build('code-spec-v5', 'p', self.adj, self.adj / 'keys', [self.candidates], self.registry)

    def test_anchors_are_association_decisions_with_their_fields(self):
        item = {k: v for k, v in association(3, 'E3').items() if k in blind_pool.FIELDS and k not in ('kind', 'allowedDecisions')}
        with self.assertRaises(ValueError):
            blind_pool.anchor_add('code-spec-v5', item, 'not-matched', 'anthropic', 'x', registry=self.registry)  # no model
        origin = {'record': 'anthropic/code-spec-v5/opus-low-a1', 'stable_id': 's1'}
        anchor = blind_pool.anchor_add('code-spec-v5', item, 'not-matched', 'anthropic', 'Main executable check',
                                       origin=origin, registry=self.registry, model='opus')
        self.assertEqual((anchor['model'], anchor['origin']), ('opus', origin))
        self.assertEqual(anchor['item']['allowedDecisions'], ['matched', 'not-matched'])
        self.assertEqual(anchor['item']['kind'], 'association')
        with self.assertRaises(ValueError):
            blind_pool.anchor_add('code-spec-v5', finding(9), 'matched', 'openai', 'x', registry=self.registry, model='m')

    def test_an_anchor_of_a_pooled_instance_is_refused(self):
        registry = json.loads((self.registry / 'code-spec-v5.json').read_text())
        registry['anchors'][0]['origin'] = {'record': 'openai/code-spec-v5/sol-high-a1',
                                            'stable_id': association(1, 'E1')['stable_id']}
        blind_pool.save(self.registry / 'code-spec-v5.json', registry)
        with self.assertRaises(ValueError):
            self.built()


class RegistryTest(unittest.TestCase):
    def test_committed_registries_are_valid_controls(self):
        for path in sorted(blind_pool.REGISTRY.glob('*.json')):
            registry, _ = blind_pool.load_registry(path.stem)
            items = blind_pool.controls(registry)
            self.assertGreaterEqual(sum(m['source'] == 'anchor' for _, m in items), 10, path.name)
            self.assertTrue(all(i['kind'] == 'association' for i, m in items if m['source'] == 'anchor'))
            self.assertTrue(any(m['expected'] == 'not-matched' for _, m in items), path.name)
            self.assertEqual({m['family'] for _, m in items if m['source'] == 'synthetic'}, set(blind_pool.FAMILIES),
                             path.name)
            marks = [blind_pool.item_fingerprint(i) for i, _ in items]
            self.assertEqual(len(marks), len(set(marks)), path.name)
            for item, meta in items:
                # A control must look like a real candidate of the scenario: same fields in the same order.
                view = blind_pool.pool_item(item, path.stem)
                self.assertEqual(list(view), list(item), f"{path.name} {meta['control']}")
                self.assertEqual(view, item, f"{path.name} {meta['control']}")
                self.assertTrue(all(isinstance(e, dict) for e in item['evidence']), f"{path.name} {meta['control']}")


if __name__ == '__main__':
    unittest.main()
