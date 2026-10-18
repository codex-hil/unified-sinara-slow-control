import copy
import tempfile
import unittest
from pathlib import Path
from sinara_slow.config import load, validate, validate_pair, attenuation_code
from sinara_slow.devices import compile_config
from sinara_slow.errors import ControlError, ValidationError
from sinara_slow.backends import STMBackend, KasliBackend
from sinara_slow.api import SlowControl
from sinara_slow.simulation import GPIORegisterSimulator, GatewaySerialSimulator
from sinara_slow.transports import SerialWishbone, LiteXRegisters, FRAME

ROOT = Path(__file__).resolve().parents[1]


class Tests(unittest.TestCase):
    def setUp(self):
        self.config = load(ROOT/'examples/urukul.yaml')
        self.stm = load(ROOT/'examples/stm.simulation.yaml', 'connection')
        self.kasli = load(ROOT/'examples/kasli.simulation.yaml', 'connection')

    def test_same_yaml_same_wire_transactions(self):
        histories = []
        for cls, profile in [(STMBackend, self.stm), (KasliBackend, self.kasli)]:
            regs = GPIORegisterSimulator(profile)
            backend = cls(regs, profile)
            backend.simulated = True
            result = SlowControl(backend, self.config).configure()
            self.assertTrue(result['simulated'])
            self.assertTrue(result['verified_readback'])
            self.assertEqual(regs.devices['rf0']['cfg'], 0)
            self.assertEqual(regs.devices['rf0']['attenuation'], bytes.fromhex('ff035faf'))
            histories.append(regs.transactions)
        self.assertEqual(histories[0], histories[1])

    def test_stm_serial_framing_to_gpio_to_spi(self):
        regs = GPIORegisterSimulator(self.stm)
        backend = STMBackend(SerialWishbone(GatewaySerialSimulator(regs)), self.stm)
        backend.simulated = True
        SlowControl(backend, self.config).configure()
        self.assertEqual(regs.devices['rf0']['attenuation'].hex(), 'ff035faf')

    def test_litex_remote_adapter_to_spi(self):
        regs = GPIORegisterSimulator(self.kasli)
        abi = self.kasli['csr_map']['abi']
        class Client:
            simulated=True
            def read(self, a):return regs.identify() if a == abi else regs.read(a)
            def write(self, a, v):regs.write(a, v)
        backend = KasliBackend(LiteXRegisters(Client(), abi), self.kasli)
        SlowControl(backend, self.config).configure()
        self.assertEqual(regs.devices['rf0']['attenuation'].hex(), 'ff035faf')

    def test_attenuation_known_vectors(self):
        for text, code in [('0 dB',255),('0.5 dB',251),('10 dB',175),('31.5 dB',3)]:
            self.assertEqual(attenuation_code(text), code)

    def test_invalid_attenuation(self):
        for text in ['32 dB','-1 dB','0.1 dB','10 MHz','nan dB',10]:
            with self.subTest(text=text), self.assertRaises(ValidationError):attenuation_code(text)

    def test_all_output_enables_rejected(self):
        c = copy.deepcopy(self.config);c['modules'][0]['channels'][0]['enabled'] = True
        with self.assertRaises(ValidationError):validate(c)

    def test_frequency_not_silently_ignored(self):
        c = copy.deepcopy(self.config);c['modules'][0]['channels'][0]['frequency'] = '100 MHz'
        with self.assertRaises(ValidationError):validate(c)

    def test_duplicate_channel_and_module(self):
        c = copy.deepcopy(self.config);c['modules'][0]['channels'][1]['id'] = 0
        with self.assertRaises(ValidationError):validate(c)
        c = copy.deepcopy(self.config);c['modules'].append(copy.deepcopy(c['modules'][0]))
        with self.assertRaises(ValidationError):validate(c)

    def test_schema_version_and_protocol(self):
        for path, value in [('schema_version',2),('cpld_protocol',9)]:
            c=copy.deepcopy(self.config)
            if path=='schema_version':c[path]=value
            else:c['modules'][0][path]=value
            with self.assertRaises(ValidationError):validate(c)

    def test_duplicate_yaml_key(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.yaml';p.write_text('system: sinara\nsystem: sinara\n')
            with self.assertRaises(ValidationError):load(p)

    def test_bad_pins_and_bindings(self):
        p=copy.deepcopy(self.stm);p['bindings']['rf0']['mosi']=p['bindings']['rf0']['miso']
        with self.assertRaises(ValidationError):validate(p,'connection')
        p=copy.deepcopy(self.stm);p['bindings']['other']=p['bindings'].pop('rf0')
        with self.assertRaises(ValidationError):validate_pair(self.config,p)

    def test_wrong_backend(self):
        with self.assertRaises(ValidationError):STMBackend(None,self.kasli)

    def test_legacy_abi_fails_before_gpio_write(self):
        regs=GPIORegisterSimulator(self.stm);regs.identify=lambda:0xaaaa
        with self.assertRaises(ControlError) as e:STMBackend(regs,self.stm)
        self.assertEqual(e.exception.code,'INCOMPATIBLE_ABI');self.assertEqual(regs.writes,0)

    def test_failure_is_fault_and_no_success_claim(self):
        regs=GPIORegisterSimulator(self.stm);backend=STMBackend(regs,self.stm)
        regs.fail_after=8;api=SlowControl(backend,self.config)
        with self.assertRaises(ControlError):api.configure()
        self.assertEqual(api.state,'fault');self.assertIsNone(api.applied)

    def test_reset_and_unsupported(self):
        regs=GPIORegisterSimulator(self.stm);api=SlowControl(STMBackend(regs,self.stm),self.config)
        self.assertEqual(api.reset()['failures'],[])
        self.assertEqual(regs.devices['rf0']['attenuation'],bytes([3])*4)
        with self.assertRaises(ControlError):api.write('rf0','frequency',100)
        with self.assertRaises(ControlError):api.read('rf0','frequency')
        self.assertFalse(api.discover()['physical_discovery'])

    def test_serial_timeout_poisoned_no_retry(self):
        class Port:
            count=0
            def write(self,f):self.count+=1;return len(f)
            def flush(self):pass
            def read(self,n):return b''
        p=Port();t=SerialWishbone(p)
        with self.assertRaises(ControlError) as e:t.write(0,7)
        self.assertTrue(e.exception.uncertain)
        with self.assertRaises(ControlError):t.write(0,7)
        self.assertEqual(p.count,1)

    def test_serial_wrong_sequence(self):
        class Port:
            def write(self,f):return len(f)
            def flush(self):pass
            def read(self,n):return FRAME.pack(b'SC',1,0,99,0,0)
        with self.assertRaises(ControlError) as e:SerialWishbone(Port()).identify()
        self.assertEqual(e.exception.code,'PROTOCOL')

    def test_preserves_unrelated_gpio(self):
        regs=GPIORegisterSimulator(self.stm);regs.values[0]=1<<15
        backend=STMBackend(regs,self.stm);backend.spi('rf0',2,bytes(4))
        self.assertEqual(regs.values[0],1<<15)

    def test_all_modules_disabled_before_attenuation(self):
        c=copy.deepcopy(self.config);m=copy.deepcopy(c['modules'][0]);m.update(id='rf1',slot=2);c['modules'].append(m)
        operations=compile_config(validate(c))
        self.assertEqual([(o.module,o.cs) for o in operations[:2]],[('rf0',1),('rf1',1)])

    def test_simulation_profile_cannot_connect_to_hardware(self):
        from sinara_slow.backends import connect
        with self.assertRaises(ValidationError):connect(self.stm)
        with self.assertRaises(ValidationError):connect(self.kasli)

    def test_identity_mismatch(self):
        regs=GPIORegisterSimulator(self.stm)
        api=SlowControl(STMBackend(regs,self.stm),self.config)
        api.backend.spi=lambda *args: bytes([9,0,0])
        with self.assertRaises(ControlError) as e:api.identify('rf0')
        self.assertEqual(e.exception.code,'IDENTITY_MISMATCH')

    def test_attenuator_readback_relatches_original_chain(self):
        regs=GPIORegisterSimulator(self.stm)
        backend=STMBackend(regs,self.stm)
        api=SlowControl(backend,self.config)
        api.configure()
        before=regs.devices['rf0']['attenuation']
        self.assertEqual(api.read('rf0','attenuation'),[10,20,31.5,0])
        self.assertEqual(regs.devices['rf0']['attenuation'],before)

    def test_readback_mismatch_is_fault(self):
        regs=GPIORegisterSimulator(self.stm)
        api=SlowControl(STMBackend(regs,self.stm),self.config)
        api.read=lambda *args:[0,0,0,0]
        with self.assertRaises(ControlError) as e:api.configure()
        self.assertEqual(e.exception.code,'READBACK_MISMATCH')
        self.assertEqual(api.state,'fault')
        self.assertEqual(regs.devices['rf0']['attenuation'],bytes([3])*4)

    def test_write_validated_attenuation_vector(self):
        regs=GPIORegisterSimulator(self.stm)
        api=SlowControl(STMBackend(regs,self.stm),self.config)
        api.write('rf0','attenuation',['0 dB','0.5 dB','10 dB','31.5 dB'])
        self.assertEqual(api.read('rf0','attenuation'),[0,0.5,10,31.5])
        previous=copy.deepcopy(api.config)
        with self.assertRaises(ValidationError):api.write('rf0','attenuation',['99 dB']*4)
        self.assertEqual(previous,api.config)

    def test_nonfinite_timeout_and_bad_csr_map(self):
        for timeout in [float('nan'),float('inf')]:
            p=copy.deepcopy(self.stm);p['timeout_s']=timeout
            with self.assertRaises(ValidationError):validate(p,'connection')
        p=copy.deepcopy(self.stm);p['csr_map']['gpio0_output']=60
        with self.assertRaises(ValidationError):validate(p,'connection')
        p=copy.deepcopy(self.kasli);p['csr_map']['gpio0_output']+=1
        with self.assertRaises(ValidationError):validate(p,'connection')

    def test_all_supported_attenuations_match_upstream_artiq_logic(self):
        import ast
        source=ROOT/'references/artiq/artiq/coredevice/urukul.py'
        if not source.exists():self.skipTest('pinned ARTIQ source checkout required')
        tree=ast.parse(source.read_text())
        function=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='att_to_mu')
        function.decorator_list=[];function.returns=None
        for argument in function.args.args:argument.annotation=None
        module=ast.Module(body=[function],type_ignores=[])
        namespace={'int32':int,'round':round}
        exec(compile(ast.fix_missing_locations(module),str(source),'exec'),namespace)
        for step in range(64):
            db=step/2
            self.assertEqual(attenuation_code(f'{db} dB'),namespace['att_to_mu'](None,db))


if __name__=='__main__':unittest.main()
