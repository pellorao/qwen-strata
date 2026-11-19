"""Import for its effect: loopback test servers stop in milliseconds instead of waiting out the 0.5 s poll of
`serve_forever` (`shutdown()` blocks until the loop wakes).  Only the default poll interval changes."""
import socketserver

socketserver.BaseServer.serve_forever.__defaults__ = (0.005,)
