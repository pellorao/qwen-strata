import hashlib,json,re,unittest
from pathlib import Path

SUITE=Path(__file__).resolve().parents[1]/'benchmarks/reviewer-suite-v1'
BRIEFS={'code-spec-v5-brief.md':('code-spec-reviewer','32bafcb591cd3629f0456963f227ced2ff0b332a956c0efe7b72567c5e4471c6'),
        'code-standards-v5.1-brief.md':('code-standards-reviewer','3950875c7c223af3beee58265c1fb9eb3ff48cf21cbd4b94ffa43a124a0d0b66'),
        'spec-readiness-v4.3-brief.md':('spec-readiness-reviewer','74252e0aa4e50d231efaefdfa24a27e1b4d97936e747425787d30bace996a344')}

def text(name):return (SUITE/name).read_text(encoding='utf-8')
def section(source,heading):
    lines=source.splitlines(keepends=True);start=lines.index(heading)
    level=len(heading)-len(heading.lstrip('#'))
    end=next((i for i in range(start+1,len(lines)) if re.match(r'#{1,%d} '%level,lines[i])),len(lines))
    return ''.join(lines[start+1:end]).strip()+'\n'

class AdjudicationBriefTests(unittest.TestCase):
    """Mechanical consistency of the draft blind-adjudication briefs with the frozen Commit Audit brief and answer keys."""
    def setUp(self):
        self.frozen=text('commit-audit-v3-brief.md')
        self.arw=re.search(r'^## 决定语义[^\n]*\n\n(.*?)^本工程补充（评分 r8\.1',self.frozen,re.S|re.M).group(1)
    def test_arw_adjudication_text_is_verbatim(self):
        self.assertTrue(self.arw.startswith('## Adjudication\n\n'))
        for name in BRIEFS:
            self.assertIn(self.arw,text(name),name)
    def test_output_contract_matches_frozen_brief(self):
        # Same contract as the frozen brief: one blind Opus adjudicator (user 2026-10-19, no dual adjudication).
        output=self.frozen[self.frozen.index('## 输出'):]
        for name in BRIEFS:
            brief=text(name);self.assertEqual(brief[brief.index('## 输出'):],output,name)
    def test_only_caller_placeholders(self):
        for name in BRIEFS:
            self.assertEqual(set(re.findall(r'<(?:[A-Z]+|名|裁决者)>',text(name))),{'<ADJ>','<名>'},name)
    def test_cited_answer_key_is_registered(self):
        registry=json.loads(text('judgment/registry.json'))
        for name,(reviewer,digest) in BRIEFS.items():
            self.assertIn(digest,text(name),name);self.assertIn(digest,registry[reviewer],name)
    def test_spec_readiness_quotes_frozen_adjudication_section(self):
        body=section(text('spec-readiness-v4.md'),'### 裁决 brief（新用例）\n')
        brief=text('spec-readiness-v4.3-brief.md')
        self.assertIn(body,brief);self.assertIn(hashlib.sha256(body.encode()).hexdigest(),brief)
        self.assertEqual(json.loads(text('judgment/spec-readiness-v4.2.json'))['expectedSha256'],BRIEFS['spec-readiness-v4.3-brief.md'][1])
    def test_briefs_are_frozen(self):
        # Frozen 2026-10-19 before any benchmark output (plan §9 stage 0); any edit is a new brief version.
        frozen={'code-spec-v5-brief.md':'5f1381c4565193b0f7260c522fc1dfdab4c79a84554e7a25b9e03fb3607167ad',
                'code-standards-v5.1-brief.md':'dffb827fdc7483eafb4105aec3725f32b0e9d7afb5640affd8d2ebdc42cafe97',
                'spec-readiness-v4.3-brief.md':'eaa1df470c69261b7f86aa5b4ad2b50487620e6505857f9e59e79246a40c5e4a',
                'commit-audit-v3-brief.md':'9c36e60b8090e24e693a53581e86056950cacfb00faf607b566ad5d2334fc221'}
        for name,digest in frozen.items():
            self.assertTrue(text(name).split('\n')[2].startswith('冻结件（'),name)
            self.assertEqual(hashlib.sha256(text(name).encode()).hexdigest(),digest,name)
    def test_adjudication_view_redacts_the_request_and_skips_preparation_files(self):
        import tempfile
        from tools.reviewer.adjudication_view import copy_view,redacted_request
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root'
            for name in ['.tmp/x','.prepared','AGENTS.md','docs/agents/r.md','docs/adr/a.md','src/AGENTS.md','.gitignore']:
                (root/name).parent.mkdir(parents=True,exist_ok=True);(root/name).write_text('x')
            import subprocess
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            subprocess.run(['git','-c','user.email=t@t','-c','user.name=t','commit','-q','--allow-empty','-m','b'],cwd=root,check=True)
            copy_view(root,Path(tmp)/'view')
            kept=sorted(str(p.relative_to(Path(tmp)/'view')) for p in (Path(tmp)/'view').rglob('*') if p.is_file())
            self.assertEqual(kept,['.gitignore','docs/adr/a.md','src/AGENTS.md'])
            request=Path(tmp)/'r.json';request.write_text(json.dumps({'draftPath':'/run/x/draft.jsonl','inputs':[]}))
            out=redacted_request(request);self.assertNotIn('/run/x',out);self.assertEqual(json.loads(out)['draftPath'],'<redacted>')

if __name__=='__main__':unittest.main()
