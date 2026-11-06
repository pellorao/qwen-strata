"""Request reading shared by the loopback gates (safety_gate, codex_compact_gate)."""
import threading

REQUEST_LOCK = threading.Lock()  # request numbering and shared gate state under ThreadingHTTPServer


def read_request_raw(handler):
    """The request body bytes, or None after replying 411/501: a chunked or length-less body is refused, never read as empty."""
    if handler.headers.get('Transfer-Encoding'):
        handler.send_error(501, 'Transfer-Encoding is not supported')
        return None
    length = handler.headers.get('Content-Length')
    if length is None or not length.strip().isdigit():
        handler.send_error(411, 'A numeric Content-Length is required')
        return None
    return handler.rfile.read(int(length))


def read_json_request(handler, decode):
    """The decoded request body, or None after replying 411/501 (see read_request_raw) or 400 when decode raises (empty or malformed body)."""
    raw = read_request_raw(handler)
    if raw is None:
        return None
    try:
        return decode(raw)
    except Exception:
        handler.send_error(400, 'Request body could not be decoded')
        return None
