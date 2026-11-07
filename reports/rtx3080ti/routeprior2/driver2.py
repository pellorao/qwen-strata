"""Windows-side driver: ROUTE_PRIOR A/B on a temporary native service (127.0.0.1 only). Run with the installation venv python."""
import json, os, re, secrets, subprocess, sys, threading, time, urllib.request, urllib.error
from pathlib import Path

INST = Path(r'C:\Users\pello\AppData\Local\Programs\qwen-3.8-flash-next')
RT = INST / 'runtime/Strata'
MODE = sys.argv[1]  # 'rep' or 'speed'
OUT = Path(r'C:\Users\pello\AppData\Local\Temp\routeprior2') / MODE
PORT = 8199
SCHEDULE = {'rep': [('C', 1), ('R', 1), ('R', 2), ('C', 2)], 'speed': [('C', 1), ('R', 1), ('R', 2), ('C', 2), ('C', 3), ('R', 3)]}[MODE]  # (arm, round); C control, R route-prior 1.5
ARM_ENV = {'C': {}, 'R': {'STRATA_ROUTE_PRIOR': '1.5'}}
DEC_TOKENS = 700
PROG = OUT / 'progress.log'
sys.path.insert(0, str(INST / 'src'))
import model_process  # noqa: E402
import psutil  # noqa: E402


def log(msg):
    OUT.mkdir(parents=True, exist_ok=True)
    with PROG.open('a', encoding='utf-8') as f:
        f.write(time.strftime('%H:%M:%S ') + msg + '\n')


def docs(names, limit=None):
    text = ''
    for n in names:
        text += f'=== {n} ===\n' + (RT / 'docs' / n).read_text(encoding='utf-8', errors='replace') + '\n\n'
    return text[:limit] if limit else text


M_DOC = ['release-notes-0.2.2.md', 'OLDER_GPUS.md', 'DOCKER.md']
L_DOC = ['DETAILS.md', 'BATCHING.md', 'AMD_HIP.md', 'TERMINAL.md', 'DEVELOPER_INTEGRATION_HANDOFF.md']
S_DOC = {1: ['DETAILS.md', 'TROUBLESHOOTING.md'], 2: ['BATCHING.md', 'AMD_HIP.md', 'TERMINAL.md', 'INTEL.md'],
         3: ['DEVELOPER_INTEGRATION_HANDOFF.md', 'A770_SPEED_SPEC.md', 'INTEL.md', 'BENCHMARK_PROTOCOL.md']}
SESSION_BYTES = 190000

STORY = ['Write a long, vivid short story (at least 1500 words) about a lighthouse keeper who finds a message in a bottle. Keep writing; do not summarize.',
         'Write a long, detailed fantasy story (at least 1500 words) about a cartographer mapping a city that rearranges itself every night. Keep writing; do not summarize.']
CODE = ['Write a complete Python module implementing an LRU cache with per-entry TTL, thread safety, type hints, docstrings, and a full unittest suite. Output only code.',
        'Write a complete Python module implementing a tokenizer, recursive-descent parser and evaluator for arithmetic expressions with variables and functions, with type hints, docstrings and a unittest suite. Output only code.']
DOC_CODE = 'Based on the material above, write a complete Python program that reads Markdown files like it, extracts every table into CSV files, and includes a full unittest suite. Output only code.'

NOTOOL = '\n\n(Answer directly in this reply as plain text. There are no tools, files or working directory; do not call any tool.)'
SESS_OFF = ['Write a detailed technical summary of the document above, section by section.',
            'Now list 15 questions a new user would ask about it and answer each in detail.',
            'Rewrite all troubleshooting-style advice from the document as a checklist, explaining the reason for each item.',
            'Write a long FAQ in Chinese covering the most important configuration options.',
            'Draft a critical design review: list the main risks and weaknesses of this system, each with a paragraph of analysis.',
            'Expand each risk you listed with concrete mitigation steps and example commands.',
            'Write an executive briefing of about 800 words for a non-technical manager.',
            'Produce a detailed test plan covering the features discussed in this conversation.']
SESS_ON = ['Find inconsistencies, ambiguities or likely mistakes in the document above and explain each one carefully.',
           'Pick the three most serious problems you found and propose precise text patches for them.',
           'Write a Python script that checks the document for the kinds of problems you found, and explain how it works.',
           'Now review your own script for bugs and give a corrected version.',
           'Summarize everything we did in this conversation as a work log, with decisions and open questions.']


def make_quality(rnd):
    import random
    r = random.Random(1000 + rnd)
    a, b, c = r.randint(12, 40), r.randint(3, 9), r.randint(100, 400)
    math = [
        (f'A warehouse ships boxes in two truck types. Type A carries {a} boxes, type B carries {a + b}. A run uses 7 trucks of type A and {b} trucks of type B, and {c} boxes are already loaded elsewhere. How many boxes are shipped in total? Think carefully, then give the final integer after "ANSWER:".', str(7 * a + b * (a + b) + c)),
        (f'Alice is {a} years old now. In {b + 3} years Bob will be twice as old as Alice was {b} years ago. How old is Bob now? Give the final integer after "ANSWER:".', str(2 * (a - b) - (b + 3))),
        (f'How many integers n with 1 <= n <= {c * 5} are divisible by {b} or by {b + 2} (or both)? Give the final integer after "ANSWER:".', str(sum(1 for n in range(1, c * 5 + 1) if n % b == 0 or n % (b + 2) == 0))),
        (f'What is the remainder when {a}^{c} is divided by {b + 4}? Give the final integer after "ANSWER:".', str(pow(a, c, b + 4))),
    ]
    return math


CODE_TASKS = {  # per round: (prompt, test code appended after the model's code; must print OK)
    1: [('Write a Python function `merge_intervals(items)` that takes a list of [start, end] pairs and returns the merged, sorted list of [start, end] lists (touching intervals merge). Reply with one python code block only.',
         "assert merge_intervals([[1,3],[2,6],[8,10],[15,18]])==[[1,6],[8,10],[15,18]]\nassert merge_intervals([[1,4],[4,5]])==[[1,5]]\nassert merge_intervals([])==[]\nassert merge_intervals([[5,6],[1,2]])==[[1,2],[5,6]]\nprint('OK')"),
        ('Write a Python function `roman_to_int(s)` converting a Roman numeral (I,V,X,L,C,D,M with subtractive forms) to an int. Reply with one python code block only.',
         "assert roman_to_int('MCMXCIV')==1994\nassert roman_to_int('LVIII')==58\nassert roman_to_int('IV')==4\nassert roman_to_int('MMMCMXCIX')==3999\nprint('OK')")],
    2: [('Write a Python function `longest_common_prefix(strs)` returning the longest common prefix of a list of strings ("" if none). Reply with one python code block only.',
         "assert longest_common_prefix(['flower','flow','flight'])=='fl'\nassert longest_common_prefix(['dog','car'])==''\nassert longest_common_prefix([])==''\nassert longest_common_prefix(['a'])=='a'\nprint('OK')"),
        ('Write a Python function `balanced(s)` returning True if the brackets ()[]{} in string s are balanced and properly nested, ignoring other characters. Reply with one python code block only.',
         "assert balanced('([]{})')\nassert not balanced('([)]')\nassert balanced('a(b)c')\nassert not balanced('((')\nassert balanced('')\nprint('OK')")],
    3: [('Write a Python function `rotate(matrix)` that rotates a square matrix (list of lists) 90 degrees clockwise and returns a new matrix. Reply with one python code block only.',
         "assert rotate([[1,2],[3,4]])==[[3,1],[4,2]]\nassert rotate([[1]])==[[1]]\nassert rotate([[1,2,3],[4,5,6],[7,8,9]])==[[7,4,1],[8,5,2],[9,6,3]]\nprint('OK')"),
        ('Write a Python function `word_freq(text)` returning a dict of lowercase word counts, where words are maximal runs of ASCII letters. Reply with one python code block only.',
         "assert word_freq('The cat, the DOG; the end.')=={'the':3,'cat':1,'dog':1,'end':1}\nassert word_freq('')=={}\nassert word_freq('a1b')=={'a':1,'b':1}\nprint('OK')")],
}
FREE = ['请用中文写一篇约 600 字的短文，主题是“深夜的图书馆”，要求有具体细节和一个转折。',
        '请用中文解释什么是投机解码（speculative decoding），并举一个生活中的类比，约 500 字。',
        '请用中文写一封约 500 字的邮件，向同事说明为何本周的发布要推迟两天，语气诚恳、条理清楚。']

LINE = re.compile(r'prompt (\d+) tokens = (\d+) reused \+ (\d+) read in (\d+) ms \(([\d.]+) tok/s\), (\d+) generated in (\d+) ms \(([\d.]+) tok/s\)(?:, drafts accepted (\d+) of (\d+))?')


def smi():
    try:
        o = subprocess.run(['nvidia-smi.exe', '--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=10).stdout.strip().split(',')
        return int(o[0]), int(o[1])
    except Exception:
        return None, None


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.stop, self.max_vram, self.max_ram = False, 0, 0
    def run(self):
        while not self.stop:
            u, _ = smi()
            if u: self.max_vram = max(self.max_vram, u)
            self.max_ram = max(self.max_ram, psutil.virtual_memory().percent)
            time.sleep(3)


class Server:
    def __init__(self, arm, tag):
        self.arm, self.tag = arm, tag
        self.key = secrets.token_urlsafe(32)
        self.dir = OUT / tag
        self.dir.mkdir(parents=True, exist_ok=True)
        self.logfile = self.dir / 'engine.log'
        self.proc = None

    def start(self):
        model, config, env, self.reasoning = model_process.configuration({}, PORT)
        config['log'] = str(self.logfile)
        env.update(ARM_ENV[self.arm])
        cfg = self.dir / 'active-config.json'
        cfg.write_text(json.dumps(config), encoding='utf-8')
        (self.dir / 'meta.json').write_text(json.dumps({'arm': self.arm, 'env_added': env, 'args': config['args'], 'reasoning_defaults': self.reasoning,
            'admin': bool(__import__('ctypes').windll.shell32.IsUserAnAdmin()), 'strata_env_in_parent': sorted(k for k in os.environ if k.startswith('STRATA'))}, indent=1))
        startup = subprocess.STARTUPINFO(dwFlags=subprocess.STARTF_USESHOWWINDOW, wShowWindow=0)
        sl = (self.dir / 'service.log').open('ab')
        py = Path(sys.executable).with_name('python.exe')
        self.proc = subprocess.Popen([str(py), '-B', str(INST / 'src/native_service.py'), '--engine', 'strata', '--config', str(cfg), '--host', '127.0.0.1', '--port', str(PORT)],
            cwd=RT, stdin=subprocess.DEVNULL, stdout=sl, stderr=sl, env=dict(os.environ, STRATA_API_KEY=self.key, **env), startupinfo=startup, creationflags=subprocess.CREATE_NEW_CONSOLE)
        (self.dir / 'pid.txt').write_text(str(self.proc.pid))
        t0 = time.time()
        while time.time() - t0 < 600:
            if self.proc.poll() is not None:
                raise RuntimeError('native service exited early')
            try:
                if self.req('/health', timeout=5).get('loaded'):
                    return time.time() - t0
            except Exception:
                pass
            time.sleep(2)
        raise TimeoutError('load timeout')

    def req(self, path, data=None, timeout=1800):
        h = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key}
        r = urllib.request.Request(f'http://127.0.0.1:{PORT}{path}', None if data is None else json.dumps(data).encode(), h)
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(r, timeout=timeout) as resp:
            return json.load(resp)

    def logsize(self):
        return self.logfile.stat().st_size if self.logfile.exists() else 0

    def chat(self, messages, max_tokens, think, tag):
        """One request; returns dict with reply and engine-log timing records."""
        body = {'messages': messages, 'max_tokens': max_tokens, 'stream': False}
        if think is False:
            body['chat_template_kwargs'] = {'enable_thinking': False}
        else:
            body.update(reasoning_effort=think['effort'], reasoning_budget_tokens=think['budget'])
        off = self.logsize()
        t0 = time.time()
        try:
            reply = self.req('/v1/chat/completions', body)
            err = None
        except Exception as e:
            reply, err = None, repr(e)[:300]
        wall = time.time() - t0
        recs = []
        for _ in range(20):
            time.sleep(0.75)
            with self.logfile.open('rb') as f:
                f.seek(off); txt = f.read().decode('utf-8', 'replace')
            recs = [tuple(float(x) if x else 0 for x in m.groups()) for m in LINE.finditer(txt)]
            if recs or err:
                break
        keys = ['prompt', 'reused', 'read', 'read_ms', 'read_tps', 'gen', 'gen_ms', 'gen_tps', 'acc', 'drafts']
        recs = [dict(zip(keys, r)) for r in recs]
        out = {'tag': tag, 'wall_s': round(wall, 2), 'error': err, 'records': recs}
        if reply:
            m = reply['choices'][0]['message']
            out.update(content=m.get('content') or '', reasoning=m.get('reasoning_content') or m.get('reasoning') or '',
                       finish=reply['choices'][0].get('finish_reason'), usage=reply.get('usage'))
        return out

    def stop(self):
        try:
            self.req('/unload', {}, timeout=120)
        except Exception:
            pass
        if self.proc:
            try:
                kids = psutil.Process(self.proc.pid).children(recursive=True)
            except psutil.NoSuchProcess:
                kids = []
            procs = kids + [psutil.Process(self.proc.pid)] if self.proc.poll() is None else kids
            for p in procs:
                try: p.kill()
                except psutil.NoSuchProcess: pass
            psutil.wait_procs(procs, timeout=20)


REP_PURE = [
    'Write a complete, production-quality Python implementation of a Markdown-to-HTML converter (headings, nested lists, tables, fenced code blocks, links, images, emphasis, blockquotes, horizontal rules) with a full unittest suite of at least 40 tests. Output only code.',
    'Write a complete Python command-line task manager backed by sqlite3, with argparse subcommands (add, list, done, delete, tag, search, export, import, stats), input validation, type hints, docstrings and a unittest suite of at least 30 tests. Output only code.',
    'Write a complete Python in-memory relational query engine: a lexer, recursive-descent parser for a SQL subset (SELECT, WHERE, JOIN, GROUP BY, ORDER BY, LIMIT), a query planner, an executor, type hints, docstrings and a unittest suite of at least 30 tests. Output only code.',
    'Write a complete Python library for scheduling recurring calendar events (daily, weekly, monthly, yearly, with exceptions, time zones and DST handling), an iCalendar RRULE parser, type hints, docstrings and a unittest suite of at least 30 tests. Output only code.',
]
REP_DOC = [
    ('A', ['DETAILS.md', 'TROUBLESHOOTING.md'], 'Based on the documents above, write a complete Python program that scans Markdown documents for contradictions between numeric limits, option names and default values, using a catalogue of at least 80 keyword and regex rules (each with an explanation), reports findings as JSON, and includes a unittest suite. Output only code.'),
    ('B', ['BATCHING.md', 'AMD_HIP.md', 'TERMINAL.md'], 'Based on the documents above, write a complete Python program that extracts every environment variable and command-line flag mentioned, cross-checks them against each other, builds a glossary with at least 80 entries, and includes a unittest suite. Output only code.'),
    ('C', ['DEVELOPER_INTEGRATION_HANDOFF.md', 'INTEL.md'], 'Based on the documents above, write a complete Python program that converts the documented procedures into executable checklists, validates each step description for missing preconditions using at least 60 rules, and includes a unittest suite. Output only code.'),
    ('D', ['A770_SPEED_SPEC.md', 'BENCHMARK_PROTOCOL.md', 'OLDER_GPUS.md'], 'Based on the documents above, write a complete Python program that parses the benchmark protocol tables, computes derived statistics, flags inconsistent numbers, and includes a unittest suite. Output only code.'),
]
REP_THINK = {'effort': 'high', 'budget': 8192}
REP_MAX = 24576


def rep_tasks(rnd):
    """Round 1: pure tasks 1-4 + nothing else; round 2: doc tasks 1-4 (each load runs 4 tasks; same tasks for C and R)."""
    if rnd == 1:
        return [(f'pure-{i + 1}', p) for i, p in enumerate(REP_PURE)]
    return [(f'doc-{k}', docs(names, 100000) + '\n\n' + q) for k, names, q in REP_DOC]


def run_load(arm, rnd, idx):
    tag = f'load{idx}-{arm}-r{rnd}'
    d = OUT / tag
    if (d / 'done.json').exists():
        log(f'skip {tag}'); return
    srv = Server(arm, tag)
    sam = Sampler(); sam.start()
    res = {'tag': tag, 'arm': arm, 'round': rnd}
    try:
        res['load_s'] = round(srv.start(), 1)
        res['vram_after_load_mib'], res['vram_total_mib'] = smi()
        log(f'{tag} loaded in {res["load_s"]}s vram={res["vram_after_load_mib"]}')
        srv.chat([{'role': 'user', 'content': 'Say hello.'}], 16, False, 'warm')
        out = []
        if MODE == 'rep':
            for name, prompt in rep_tasks(rnd):
                o = srv.chat([{'role': 'user', 'content': prompt}], REP_MAX, REP_THINK, name)
                out.append(o)
                (d / 'rep.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
                log(f'{tag} {name}: finish={o.get("finish")} gen={[r["gen"] for r in o["records"]]} tps={[r["gen_tps"] for r in o["records"]]} err={o["error"]}')
        else:
            salt = lambda n: f'[run {tag} {n} {secrets.token_hex(4)}]\n'
            m_text, l_text = docs(M_DOC), docs(L_DOC)
            plan = [('short-story-1', STORY[0]), ('short-code-1', CODE[0]), ('short-story-2', STORY[1]), ('short-code-2', CODE[1]),
                    ('M', salt('M') + m_text + '\n\n' + DOC_CODE)] + [(f'L{i + 1}', salt(f'L{i}') + l_text + '\n\n' + DOC_CODE) for i in range(3)]
            for name, prompt in plan:
                o = srv.chat([{'role': 'user', 'content': prompt}], DEC_TOKENS, False, name)
                o.pop('content', None); o.pop('reasoning', None)
                out.append(o); log(f'{tag} dec {name}: ' + json.dumps(o['records'][-1:] if o['records'] else o['error']))
            (d / 'decode.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
        res['vram_end_mib'] = smi()[0]
        log(f'{tag} done')
    except Exception as e:
        res['fatal'] = repr(e); log(f'{tag} FATAL {e!r}')
    finally:
        sam.stop = True
        res['max_vram_mib'], res['max_ram_pct'] = sam.max_vram, sam.max_ram
        srv.stop()
        (d / 'done.json').write_text(json.dumps(res, indent=1))
        time.sleep(5)


if __name__ == '__main__':
    log('driver start ' + MODE)
    for i, (arm, rnd) in enumerate(SCHEDULE, 1):
        run_load(arm, rnd, i)
    log('ALL DONE')
