"""Actual flashrom -> TCP -> Rust serprog core -> synthetic 16MiB NOR.

Host HTTP API uses the same YAML documents as CLI. No device is touched.
"""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,threading,time,urllib.request
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from sinara_slow.fpga_flash import FPGAFlash,load_flash
from sinara_slow.flash_cli import make_handler
import yaml
out=ROOT/'work/tmp';out.mkdir(parents=True,exist_ok=True)
results={}
with tempfile.TemporaryDirectory(prefix='flash-integration-',dir=out) as folder:
 directory=Path(folder); port_file=directory/'port'
 emulator=subprocess.Popen([str(ROOT/'firmware/flash-serprog/target/debug/examples/nor_tcp_sim'),str(port_file)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 try:
  deadline=time.monotonic()+5
  while not port_file.exists():
   if time.monotonic()>deadline:raise RuntimeError('emulator startup failed')
   time.sleep(0.02)
  profile={'schema_version':1,'controller':'stm_sys_board','board_revision':'v1.1','board_id':'SYNTHETIC-NOR','fpga_part':'lfe5u-85f',
           'capacity_bytes':16777216,'chip':'W25Q128.V','tool':str(ROOT/'work/builds/flashrom/flashrom'),
           'programmer':{'kind':'serprog-tcp','host':'127.0.0.1','port':int(port_file.read_text())},
           'resource_lock':str(directory/'board.lock'),'timeout_s':120,'reviewed':True,'use':'simulation',
           'protected_regions':[{'offset':0x200000,'length':4096}]}
  image=bytes((i*17)%256 for i in range(600));(directory/'image.bin').write_bytes(image)
  job={'schema_version':1,'operation':'fpga_flash','format':'raw','image':'image.bin','sha256':hashlib.sha256(image).hexdigest(),
       'fpga_part':'lfe5u-85f','offset':0,'reconfigure':False}
  for name,value in [('connection',profile),('job',job)]: (directory/(name+'.yaml')).write_text(yaml.safe_dump(value))
  service=FPGAFlash(load_flash(directory/'connection.yaml','flash-connection'))
  loaded=load_flash(directory/'job.yaml','flash-job')
  assert service.plan(loaded)['executed'] is False
  token='synthetic-test-token-'+'x'*32
  server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service,loaded,directory/'runs',token))
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   base='http://127.0.0.1:'+str(server.server_address[1])
   request=urllib.request.Request(base+'/v1/fpga/flash/program',data=b'{}',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(request,timeout=120) as response: report=json.load(response)
   except urllib.error.HTTPError as error:
    print(error.read().decode(),flush=True)
    for path in (directory/'runs').glob('*/*.log'):
     (ROOT/'evidence'/('flash-integration-'+path.name)).write_bytes(path.read_bytes())
    raise
   assert report['verified_readback'] and report['simulated']
   run=Path(report['artifacts'])
   before=(run/'backup.bin').read_bytes();after=(run/'readback.bin').read_bytes()
   assert after[:len(image)]==image and after[len(image):]==before[len(image):]
   assert after[0x200000:0x200010]==b'SINARA_SENTINEL!'
   # Preserve tool logs and digest evidence; temporary synthetic dumps are removed.
   for label in ['backup','write_verify','readback']:
    (ROOT/'evidence'/('flash-integration-'+label+'.log')).write_bytes((run/(label+'.log')).read_bytes())
   # A second update requires actual erase (0 -> 1), not only page programming.
   erased=bytes([255])*len(image);(directory/'erase.bin').write_bytes(erased)
   second=dict(loaded,reconfigure=True,image=str(directory/'erase.bin'),sha256=hashlib.sha256(erased).hexdigest())
   restored=service.program(second,artifacts=directory/'runs')
   final=(Path(restored['artifacts'])/'readback.bin').read_bytes()
   assert final[:len(image)]==erased and final[len(image):]==after[len(image):]
   assert restored['reconfigured'] and final[0x800:0x810] == b'0123456789ABCDEF'
   for label in ['backup','write_verify','readback']:
    (ROOT/'evidence'/('flash-integration-erase-'+label+'.log')).write_bytes((Path(restored['artifacts'])/(label+'.log')).read_bytes())
   results.update(last_sector_tail_preserved=True, synthetic_boot_rpc_only=True, erase_roundtrip=True, result='PASS' ,hardware_tested=False,emulated_chip='W25Q128.V',transport='real TCP serprog core',
                  host_api='HTTP authenticated POST + strict YAML',raw_image_sha256=job['sha256'],
                  full_readback_sha256=report['flash_sha256'],outside_image_preserved=True,
                  flashrom_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT/'references/flashrom',text=True).strip())
  finally:server.shutdown();server.server_close();thread.join(2)
 finally:
  emulator.terminate()
  try:emulator.wait(3)
  except subprocess.TimeoutExpired:emulator.kill();emulator.wait()
(ROOT/'evidence/flash-integration.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
