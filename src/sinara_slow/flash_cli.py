"""Host-local maintenance API and YAML CLI. Never flashes during validation."""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from .fpga_flash import FPGAFlash, load_flash
from .errors import ControlError


def make_handler(service, job, artifacts, token):
    job = copy.deepcopy(job)
    if len(token) < 32:
        raise ValueError('API token must contain at least 32 characters')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # do not log credentials
        def reply(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        def authorized(self):
            expected = 'Bearer ' + token
            if not secrets.compare_digest(self.headers.get('Authorization', '').encode(), expected.encode()):
                self.reply(401, {'error':'UNAUTHORIZED'}); return False
            return True
        def do_GET(self):
            if not self.authorized(): return
            if self.path != '/v1/fpga/flash/plan': self.reply(404, {'error':'NOT_FOUND'}); return
            try: self.reply(200, service.plan(job))
            except ControlError as error: self.reply(400, {'error':error.code,'message':str(error)})
        def do_POST(self):
            if not self.authorized(): return
            if self.path != '/v1/fpga/flash/program': self.reply(404, {'error':'NOT_FOUND'}); return
            try:
                n = int(self.headers.get('Content-Length', '0'))
                if not 0 <= n <= 1024: raise ValueError('body too large')
                self.connection.settimeout(5)
                body = self.rfile.read(n)
                if n != len(body) or json.loads(body or b'{}') != {}:
                    raise ValueError('only the registered YAML job may be executed')
                self.reply(200, service.program(job, artifacts=artifacts))
            except ControlError as error:
                self.reply(409 if error.code == 'BUSY' else 400,
                           {'error':error.code,'message':str(error),'outcome_uncertain':error.uncertain})
            except (ValueError, OSError) as error: self.reply(400, {'error':'INVALID_REQUEST','message':str(error)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan','program','serve'])
    parser.add_argument('job'); parser.add_argument('--connection',required=True)
    parser.add_argument('--artifacts'); parser.add_argument('--execute',action='store_true')
    parser.add_argument('--port',type=int,default=8765); parser.add_argument('--token-file')
    args = parser.parse_args()
    try:
        service = FPGAFlash(load_flash(args.connection,'flash-connection'))
        job = load_flash(args.job,'flash-job')
        if args.command == 'plan': result = service.plan(job)
        else:
            if not args.artifacts: parser.error('--artifacts required')
            if args.command == 'program':
                if not args.execute: parser.error('--execute required for persistent programming')
                result = service.program(job,artifacts=args.artifacts)
            else:
                if not args.token_file: parser.error('--token-file required')
                token = Path(args.token_file).read_text().strip()
                server = ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(service,job,args.artifacts,token))
                try: server.serve_forever()
                finally: server.server_close()
                return 0
        print(json.dumps(result,indent=2)); return 0
    except (ControlError,OSError,ValueError) as error:
        print(json.dumps({'error':getattr(error,'code','INVALID_CONFIG'),'message':str(error),
                          'outcome_uncertain':getattr(error,'uncertain',False)}));return 1

if __name__ == '__main__': raise SystemExit(main())
