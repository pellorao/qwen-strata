"""One opt-in summary failure for a local integration test; no production use."""
import io,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from responses_bridge import Handler
class FaultHandler(Handler):
    def do_POST(self):
        size=int(self.headers.get('Content-Length',0));raw=self.rfile.read(size)
        req=json.loads(raw);text=json.dumps(req.get('input',[]),ensure_ascii=False).lower()
        is_compact=any(v in text for v in ('create a compact continuation summary','context checkpoint'))
        if is_compact and self.server.fail_summary:
            self.server.failure_requests.append(req)
            return self.send_json(getattr(self.server,'failure_status',503),{'error':{'message':'Injected summary failure for recovery validation'}})
        original=self.rfile;self.rfile=io.BytesIO(raw)
        try:return super().do_POST()
        finally:self.rfile=original
