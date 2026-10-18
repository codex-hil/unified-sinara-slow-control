"""Concurrent crate equivalence on two actual RTL instances, no hardware."""
import sys,time,unittest,concurrent.futures
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
from sinara_slow.fabric import load_profile,stream_commands,transfer_words
from scf5_rtl_model import RTLModel
class DualFabricTests(unittest.TestCase):
    def test_identical_eight_slot_batch(self):
        models=[RTLModel(load_profile(ROOT/f'examples/fabric-{target}.yaml')) for target in ['stm_ecp5','kasli']]
        words=stream_commands([(slot,transfer_words(1,0,4,b'\x12\xab\x34\xcd',tag=slot)) for slot in range(1,9)])
        def run(model):
            self.assertEqual(model.read(0),0x53434635)
            for word in words:model.write(0x40,word)
            for slot in range(8):model.write(0x100+slot*0x100,1)
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                done=[model.read(0x128+slot*0x100) for slot in range(8)]
                if all(d&65535==1 for d in done):break
            else:self.fail('parallel batch did not complete')
            status=[model.read(0x104+slot*0x100)&0xf0 for slot in range(8)]
            self.assertEqual(status,[0]*8)
            return done,status
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(run,models))
            self.assertEqual(results[0],results[1])
            self.assertEqual([d>>16 for d in results[0][0]],list(range(1,9)))
        finally:
            for model in models:model.shutdown()
