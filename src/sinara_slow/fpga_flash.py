"""YAML/API flash maintenance using flashrom, independent of module configure.

A serprog STM service exposes the dedicated configuration SPI; external
flashrom programmers use the same backup/patch/verify pipeline.
"""
import copy
import fcntl
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
from importlib.resources import files
import jsonschema
import yaml
from .config import StrictLoader
from .errors import ControlError, ValidationError


def load_flash(path, kind):
    if kind not in ('flash-job', 'flash-connection'):
        raise ValidationError('unknown flash document kind')
    try:
        with open(path) as stream:
            document = yaml.load(stream, Loader=StrictLoader)
        validate_flash(document, kind)
        if kind == 'flash-job':
            document['image'] = str((Path(path).resolve().parent / document['image']).resolve())
        return document
    except (OSError, yaml.YAMLError, RecursionError) as error:
        raise ValidationError(str(error)) from error


def validate_flash(document, kind):
    schema = json.loads(files('sinara_slow').joinpath(f'schemas/{kind}-v1.schema.json').read_text())
    try:
        jsonschema.Draft202012Validator(schema).validate(document)
    except jsonschema.ValidationError as error:
        raise ValidationError(error.message) from error
    if kind == 'flash-connection':
        if not math.isfinite(document['timeout_s']):
            raise ValidationError('timeout must be finite')
        for region in document.get('protected_regions', []):
            if region['offset'] + region['length'] > document['capacity_bytes']:
                raise ValidationError('protected region outside flash')


class FPGAFlash:
    def __init__(self, connection):
        validate_flash(connection, 'flash-connection')
        self.connection = copy.deepcopy(connection)

    def _programmer(self):
        p = self.connection['programmer']
        if p['kind'] == 'serprog-serial':
            return f"serprog:dev={p['device']}:{p['baud']}"
        if p['kind'] == 'serprog-tcp':
            return f"serprog:ip={p['host']}:{p['port']}"
        if p['kind'] == 'openfpgaloader-jtag':
            return f"openFPGALoader:{p['cable']}:{p['serial']}"
        return p['driver'] + (':' + p['parameters'] if p.get('parameters') else '')

    def _image(self, job):
        validate_flash(job, 'flash-job')
        p = self.connection
        if job['fpga_part'] != p['fpga_part']:
            raise ValidationError('image/profile FPGA part mismatch')
        try:
            image = Path(job['image']).read_bytes()
        except OSError as error:
            raise ValidationError(str(error)) from error
        if not image or hashlib.sha256(image).hexdigest() != job['sha256']:
            raise ValidationError('image missing, empty or SHA-256 mismatch')
        if image.startswith(b'\x7fELF') or Path(job['image']).suffix.lower() in ('.elf', '.svf', '.mcs', '.jed'):
            raise ValidationError('requires raw flash bytes, not MCU ELF or a programming script/container')
        start, end = job['offset'], job['offset'] + len(image)
        if start % 4096 or end > p['capacity_bytes']:
            raise ValidationError('image offset must be sector aligned and fit the flash')
        for region in p.get('protected_regions', []):
            if start < region['offset'] + region['length'] and end > region['offset']:
                raise ValidationError('image overlaps a protected region')
        if job.get('reconfigure', False) and p['programmer']['kind'] in ('external', 'openfpgaloader-jtag'):
            raise ValidationError('automatic boot requires STM serprog BOOT extension')
        if job.get('reconfigure', False) and p['controller'] != 'stm_sys_board':
            raise ValidationError('BOOT extension is currently STM-only')
        return image

    def plan(self, job):
        job = copy.deepcopy(job)
        image = self._image(job)
        return {'operation': 'fpga_flash', 'controller': self.connection['controller'],
                'board_id': self.connection['board_id'], 'board_revision': self.connection['board_revision'],
                'fpga_part': job['fpga_part'], 'format': job['format'],
                'profile_reviewed': self.connection['reviewed'], 'programmer': self._programmer(),
                'image_sha256': hashlib.sha256(image).hexdigest(), 'image_bytes': len(image),
                'offset': job['offset'], 'capacity_bytes': self.connection['capacity_bytes'],
                'steps': ['full_backup', 'patch_backup', 'flashrom_write_and_verify', 'independent_full_readback'] +
                         (['explicit_boot'] if job.get('reconfigure') else []),
                'executed': False, 'hardware_validated': False}

    def _run(self, arguments, directory, label):
        p = self.connection
        driver = p['programmer']
        if driver['kind'] == 'openfpgaloader-jtag':
            command = [p['tool'], '--cable', driver['cable'], '--usb-serial-num', driver['serial'],
                       '--index-chain', str(driver['chain_index']), '--freq', str(driver['frequency_hz']),
                       '--offset', '0', '--file-type', 'bin', '--skip-reset']
            if arguments[0] == '-r':
                command += ['--dump-flash', '--file-size', str(p['capacity_bytes']), arguments[1]]
            else:
                command += ['--write-flash', '--verify', arguments[1]]
        else:
            command = [p['tool'], '-p', self._programmer(), '-c', p['chip'], *arguments]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=p['timeout_s'], check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ControlError('TRANSPORT', f'{label}: {error}', uncertain=label != 'backup') from error
        (directory / f'{label}.log').write_bytes(result.stdout)
        if driver['kind'] == 'openfpgaloader-jtag' and label == 'backup':
            ids = re.findall(rb'JEDEC ID:\s*0x([0-9a-fA-F]{6})', result.stdout)
            if not ids or any(value.decode().lower() != driver['jedec_id'] for value in ids):
                raise ControlError('IDENTITY_MISMATCH', 'JTAG flash JEDEC ID missing or differs; no write issued')
        if result.returncode:
            raise ControlError('HARDWARE', f'{label}: flashrom exit {result.returncode}', uncertain=label != 'backup')

    def _boot(self):
        p = self.connection['programmer']
        if p['kind'] == 'serprog-tcp':
            with socket.create_connection((p['host'], p['port']), timeout=10) as channel:
                channel.settimeout(10); channel.sendall(b'\x80BOOT'); reply = channel.recv(1)
        else:
            import serial
            with serial.Serial(p['device'], p['baud'], timeout=10, write_timeout=3) as channel:
                channel.write(b'\x80BOOT'); channel.flush(); reply = channel.read(1)
        if reply != b'\x06':
            raise ControlError('HARDWARE', 'FPGA reconfiguration failed or was not acknowledged', uncertain=True)

    def program(self, job, *, artifacts):
        job = copy.deepcopy(job)
        # Read and hash once. The staged image, not the source pathname, is used.
        image = self._image(job)
        p = self.connection
        if not p['reviewed']:
            raise ControlError('INVALID_CONFIG', 'physical connection/profile must be reviewed before execution')
        if p['use'] == 'simulation' and (p['programmer']['kind'] != 'serprog-tcp' or
                                        p['programmer']['host'] != '127.0.0.1'):
            raise ControlError('INVALID_CONFIG', 'simulation requires an explicit local serprog fixture')
        artifacts = Path(artifacts); artifacts.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(artifacts).free < p['capacity_bytes'] * 4 + 10*1024*1024:
            raise ControlError('RESOURCE', 'insufficient space for backup/staging/readback before hardware access')
        with open(p['resource_lock'], 'a+b') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ControlError('BUSY', 'board is owned by another operation') from error
            directory = Path(tempfile.mkdtemp(prefix='fpga-flash-', dir=artifacts))
            report = {'state': 'started', 'simulated': p['use'] == 'simulation',
                      'hardware_validated': False, 'board_id': p['board_id'],
                      'image_sha256': hashlib.sha256(image).hexdigest(), 'artifacts': str(directory)}
            modifying = False
            pending_error = None
            try:
                backup = directory/'backup.bin'
                self._run(['-r', str(backup.resolve())], directory, 'backup')
                before = backup.read_bytes()
                if len(before) != p['capacity_bytes']:
                    raise ControlError('IDENTITY_MISMATCH', 'flash capacity/read length mismatch')
                report['backup_sha256'] = hashlib.sha256(before).hexdigest()
                staged = bytearray(before)
                staged[job['offset']:job['offset']+len(image)] = image
                desired = directory/'desired.bin'; desired.write_bytes(staged)
                # Persist backup/desired before the first flash modification.
                for path in (backup, desired):
                    with path.open('rb') as stream: os.fsync(stream.fileno())
                fd = os.open(directory, os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
                report['state'] = 'backup_saved'
                (directory/'report.json').write_text(json.dumps(report, indent=2)+'\n')
                modifying = True
                self._run(['-w', str(desired.resolve())], directory, 'write_verify')
                readback = directory/'readback.bin'
                self._run(['-r', str(readback.resolve())], directory, 'readback')
                if readback.read_bytes() != staged:
                    raise ControlError('READBACK_MISMATCH', 'full flash readback differs', uncertain=True)
                report.update(state='verified', flash_sha256=hashlib.sha256(staged).hexdigest(),
                              verified_readback=True, reconfigured=False)
                if job.get('reconfigure', False):
                    try: self._boot()
                    except (OSError, ControlError) as error:
                        raise ControlError('HARDWARE', str(error), uncertain=True) from error
                    report['reconfigured'] = True
            except Exception as error:
                pending_error = error
                if modifying and report.get('verified_readback') is not True and isinstance(error, ControlError):
                    error.uncertain = True
                report.update(state='failed', error=str(error),
                              outcome_uncertain=getattr(error, 'uncertain', modifying))
                if isinstance(error, ControlError):
                    raise
                raise ControlError('HARDWARE', str(error), uncertain=modifying) from error
            finally:
                try:
                    (directory/'report.json').write_text(json.dumps(report, indent=2)+'\n')
                except OSError as error:
                    if pending_error is None:
                        raise ControlError('RESOURCE', f'cannot save report in {directory}: {error}',
                                           uncertain=modifying) from error
            return report
