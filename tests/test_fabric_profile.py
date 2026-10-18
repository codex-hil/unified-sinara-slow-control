import copy,tempfile,unittest,yaml,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from sinara_slow.fabric import load_profile,build_id,transfer_words,stream_commands
class FabricProfileTests(unittest.TestCase):
 def test_shared_modules_and_target_identity(self):
  a=load_profile(ROOT/'examples/fabric-max31855-stm_ecp5.yaml')
  b=load_profile(ROOT/'examples/fabric-max31855-kasli.yaml')
  self.assertEqual(a['slots'][6]['route'],b['slots'][6]['route'])
  self.assertNotEqual(build_id(a),build_id(b))
  c=copy.deepcopy(a);c['reviewed']=True
  self.assertEqual(build_id(a),build_id(c))
 def test_invalid_physical_routes(self):
  p=load_profile(ROOT/'examples/fabric-stm_ecp5.yaml')
  for change in [lambda x:x.update(schema_version=True),lambda x:x['slots'][0]['route'].update(clk=8),lambda x:x['slots'][0]['route'].update(enable=7),lambda x:x['slots'][0].update(output_capable=0)]:
   q=copy.deepcopy(p);change(q)
   with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'profile.yaml';path.write_text(yaml.safe_dump(q))
    with self.assertRaises(ValueError):load_profile(path)
 def test_wire_packing_and_slot_envelope(self):
  words=transfer_words(1,3,5,b'abcde',tag=9)
  self.assertEqual(words,[0x13090005,0x64636261,0x65])
  self.assertEqual(stream_commands([(8,words)]),[0x30007,*words])
  with self.assertRaises(ValueError):transfer_words(1,0,2,b'a')
  with self.assertRaises(ValueError):stream_commands([(9,words)])
