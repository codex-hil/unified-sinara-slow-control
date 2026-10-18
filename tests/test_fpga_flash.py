"""Host safeguards with a command fixture. Physical flash is never accessed."""
import copy,fcntl,hashlib,json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from sinara_slow.fpga_flash import FPGAFlash,load_flash
from sinara_slow.flash_cli import make_handler
from sinara_slow.errors import ControlError

class CommandFixture(FPGAFlash):
    def __init__(self,profile):
        super().__init__(profile);self.memory=b'\xaa'*profile['capacity_bytes'];self.calls=[];self.fail=None
    def _run(self,args,directory,label):
        self.calls.append(label)
        if label==self.fail:raise ControlError('TRANSPORT','reply lost')
        if args[0]=='-r':Path(args[1]).write_bytes(self.memory)
        elif args[0]=='-w':self.memory=Path(args[1]).read_bytes()

class FlashTests(unittest.TestCase):
    def setUp(self):
        temp_root=Path(__file__).resolve().parents[1]/'work/tmp'
        temp_root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=temp_root);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        image=b'\x12\x34'*300;(self.root/'image.bin').write_bytes(image)
        self.job={'schema_version':1,'operation':'fpga_flash','format':'raw','image':str(self.root/'image.bin'),
                  'sha256':hashlib.sha256(image).hexdigest(),'fpga_part':'xc7a100t','offset':0}
        self.profile={'schema_version':1,'controller':'kasli','board_revision':'v1.1','board_id':'FIXTURE','fpga_part':'xc7a100t',
                      'capacity_bytes':1048576,'chip':'fixture','tool':'/fixture/flashrom',
                      'programmer':{'kind':'serprog-tcp','host':'127.0.0.1','port':12345},
                      'resource_lock':str(self.root/'board.lock'),'timeout_s':2,'reviewed':True,'use':'simulation'}
    def test_plan_no_tool_or_hardware(self):
        s=CommandFixture(self.profile);self.assertFalse(s.plan(self.job)['executed']);self.assertEqual(s.calls,[])
    def test_preserve_outside_image_and_backup(self):
        s=CommandFixture(self.profile);before=s.memory;r=s.program(self.job,artifacts=self.root/'runs')
        self.assertEqual((Path(r['artifacts'])/'backup.bin').read_bytes(),before)
        self.assertEqual(s.memory[:600],(self.root/'image.bin').read_bytes());self.assertEqual(s.memory[600:],before[600:])
        self.assertEqual(s.calls,['backup','write_verify','readback']);self.assertTrue(r['verified_readback'])
    def test_hash_part_bounds_protected_and_review(self):
        cases=[dict(self.job,sha256='0'*64),dict(self.job,fpga_part='wrong'),dict(self.job,offset=1),dict(self.job,offset=1048576)]
        for job in cases:
            s=CommandFixture(self.profile)
            with self.assertRaises(ControlError):s.program(job,artifacts=self.root/'runs')
            self.assertEqual(s.calls,[])
        for profile in [dict(self.profile,reviewed=False),dict(self.profile,protected_regions=[{'offset':0,'length':4096}])]:
            s=CommandFixture(profile)
            with self.assertRaises(ControlError):s.program(self.job,artifacts=self.root/'runs')
            self.assertEqual(s.calls,[])
    def test_busy_lock_no_commands(self):
        with open(self.profile['resource_lock'],'a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            s=CommandFixture(self.profile)
            with self.assertRaises(ControlError) as error:s.program(self.job,artifacts=self.root/'runs')
            self.assertEqual(error.exception.code,'BUSY');self.assertEqual(s.calls,[])
    def test_write_failure_uncertain_and_backup_retained(self):
        s=CommandFixture(self.profile);s.fail='write_verify'
        with self.assertRaises(ControlError) as error:s.program(self.job,artifacts=self.root/'runs')
        self.assertTrue(error.exception.uncertain);self.assertEqual(s.calls,['backup','write_verify'])
        report=json.loads(next((self.root/'runs').glob('*/report.json')).read_text())
        self.assertTrue(report['outcome_uncertain']);self.assertTrue(next((self.root/'runs').glob('*/backup.bin')).exists())
    def test_no_space_before_board_access(self):
        s=CommandFixture(self.profile)
        with patch('sinara_slow.fpga_flash.shutil.disk_usage') as space:
            space.return_value.free=0
            with self.assertRaises(ControlError):s.program(self.job,artifacts=self.root/'runs')
        self.assertEqual(s.calls,[])
    def test_duplicate_yaml_keys(self):
        path=self.root/'bad.yaml';path.write_text('schema_version: 1\nschema_version: 1\n')
        with self.assertRaises(ControlError):load_flash(path,'flash-job')
    def test_http_auth_and_registered_job(self):
        s=CommandFixture(self.profile);token='x'*32
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(s,self.job,self.root/'runs',token))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_address[1]}/v1/fpga/flash/program'
            for data,headers,expected in [(b'{}',{},401),(b'{"image":"other"}',{'Authorization':'Bearer '+token},400)]:
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers),timeout=2)
                self.assertEqual(error.exception.code,expected)
            self.assertEqual(s.calls,[])
        finally:server.shutdown();server.server_close();thread.join(2)

    def test_jtag_serial_dump_verify_and_wrong_id(self):
        profile=dict(self.profile,use='hardware',programmer={
            'kind':'openfpgaloader-jtag','cable':'fixture','serial':'ONLY-THIS-DEVICE',
            'chain_index':0,'frequency_hz':1000000,'jedec_id':'ef4018'})
        service=FPGAFlash(profile)
        with patch('sinara_slow.fpga_flash.subprocess.run') as runner:
            runner.return_value.returncode=0;runner.return_value.stdout=b'JEDEC ID: 0xef4018\n'
            service._run(['-r','backup.bin'],self.root,'backup')
            command=runner.call_args.args[0]
            self.assertIn('--dump-flash',command);self.assertIn('--skip-reset',command)
            self.assertEqual(command[command.index('--usb-serial-num')+1],'ONLY-THIS-DEVICE')
            service._run(['-w','desired.bin'],self.root,'write_verify')
            self.assertIn('--verify',runner.call_args.args[0])
            runner.return_value.stdout=b'JEDEC ID: 0xef4017\n'
            with self.assertRaises(ControlError):service._run(['-r','backup.bin'],self.root,'backup')

    def test_final_journal_disk_failure_preserves_error_semantics(self):
        original=Path.write_text
        for fail_write in (False,True):
            service=CommandFixture(self.profile)
            if fail_write:service.fail='write_verify'
            report_writes=0
            def write(path,*args,**kwargs):
                nonlocal report_writes
                if path.name=='report.json':
                    report_writes+=1
                    if report_writes>=2:raise OSError('fixture: disk full')
                return original(path,*args,**kwargs)
            with patch.object(Path,'write_text',write):
                with self.assertRaises(ControlError) as error:
                    service.program(self.job,artifacts=self.root/'runs')
            self.assertEqual(error.exception.code,'TRANSPORT' if fail_write else 'RESOURCE')
            self.assertTrue(error.exception.uncertain)
