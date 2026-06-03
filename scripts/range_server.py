#!/usr/bin/env python3
"""Tiny HTTP server with Range request support (needed for PMTiles)."""
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class RangeHTTPRequestHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        if not os.path.isfile(path):
            self.send_error(404, "File not found")
            return None
        ctype = self.guess_type(path)
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(404, "File not found")
            return None
        fs = os.fstat(f.fileno())
        size = fs.st_size
        rng = self.headers.get('Range')
        if rng and rng.startswith('bytes='):
            try:
                spec = rng[6:]
                start_s, _, end_s = spec.partition('-')
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else size - 1
                if start > end or end >= size:
                    self.send_error(416, "Requested Range Not Satisfiable")
                    f.close()
                    return None
                length = end - start + 1
                f.seek(start)
                self.send_response(206)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(length))
                self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
                # CORS for local dev
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                # Read only requested bytes
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
                f.close()
                return None
            except ValueError:
                pass
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(size))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Last-Modified', self.date_time_string(fs.st_mtime))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        return f

    def log_message(self, format, *args):
        pass  # quiet


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3001
    addr = ('0.0.0.0', port)
    print(f"Range-aware HTTP server on http://localhost:{port}", flush=True)
    HTTPServer(addr, RangeHTTPRequestHandler).serve_forever()
