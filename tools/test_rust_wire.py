"""Real Python framing through compiled Rust parser with simulated registers."""
import subprocess
from pathlib import Path
from sinara_slow.transports import SerialWishbone, ABI_MAGIC

ROOT=Path(__file__).resolve().parents[1]
p=subprocess.Popen([str(ROOT/'firmware/stm-service/target/debug/examples/stdio_simulator')],
                   stdin=subprocess.PIPE,stdout=subprocess.PIPE)
class Pipe:
    def write(self,data):return p.stdin.write(data)
    def flush(self):p.stdin.flush()
    def read(self,n):return p.stdout.read(n)
    def close(self):p.stdin.close();p.wait(timeout=2)
try:
    transport=SerialWishbone(Pipe())
    assert transport.identify()==ABI_MAGIC
    for slot in range(8):
        address=slot*20
        transport.write(address,0x1234+slot)
        assert transport.read(address)==0x1234+slot
    transport.close()
    print('Python UART framing / actual Rust parser / simulated register roundtrip PASS: 8 slots')
finally:
    if p.poll() is None:p.kill();p.wait()
