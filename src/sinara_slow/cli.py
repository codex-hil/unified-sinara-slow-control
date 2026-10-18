import argparse
import json
from dataclasses import asdict
from .config import load, validate_pair
from .devices import compile_config
from .errors import ControlError
from .api import SlowControl
from .backends import connect, STMBackend, KasliBackend
from .simulation import GPIORegisterSimulator


def main():
    parser = argparse.ArgumentParser(description='Restricted Urukul slow-control demonstrator')
    parser.add_argument('command', choices=['validate', 'compile', 'simulate', 'configure', 'status', 'health', 'reset'])
    parser.add_argument('config')
    parser.add_argument('--connection')
    args = parser.parse_args()
    backend = None
    try:
        config = load(args.config)
        profile = load(args.connection, 'connection') if args.connection else None
        if profile:
            validate_pair(config, profile)
        if args.command == 'validate':
            result = {'valid': True, 'hardware_validated': False}
        elif args.command == 'compile':
            result = [dict(asdict(op), data=op.data.hex()) for op in compile_config(config)]
        else:
            if not profile:
                parser.error('--connection required')
            if args.command == 'simulate':
                regs = GPIORegisterSimulator(profile)
                cls = STMBackend if profile['controller'] == 'stm_sys_board' else KasliBackend
                backend = cls(regs, profile)
                backend.simulated = True
                result = SlowControl(backend, config).configure()
                result['transactions'] = [(m, cs, d.hex()) for m, cs, d in regs.transactions]
            else:
                backend = connect(profile)
                result = getattr(SlowControl(backend, config), args.command)()
        print(json.dumps(result, indent=2))
        return 0
    except ControlError as exc:
        print(json.dumps({'error': exc.code, 'message': str(exc), 'outcome_uncertain': exc.uncertain}))
        return 1
    finally:
        if backend:
            backend.close()


if __name__ == '__main__':
    raise SystemExit(main())
