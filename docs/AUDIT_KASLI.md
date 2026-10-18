# Audyt Kasli i istniejących sterowników — 2026-10-11

Podstawa: commity w evidence/source-commits.json, Migen platform
`migen/build/platforms/sinara/kasli.py`, MiSoC `misoc/targets/kasli.py`,
ARTIQ `artiq/gateware/targets/kasli.py`, `artiq/coredevice/*.py`,
`artiq/coredevice/jsondesc.py`. [Kasli hardware](https://github.com/sinara-hw/Kasli),
[MiSoC Kasli](https://github.com/m-labs/misoc/blob/98227d90be73ead8b797eca74da7c58d0c18f378/misoc/targets/kasli.py),
[Migen platform](https://github.com/m-labs/migen/blob/e19524c963a8342952840983047557707fbe0b6a/migen/build/platforms/sinara/kasli.py).

## Rewizje i zasoby

| Platforma obsługiwana w Migen | FPGA | Różnice istotne dla projektu |
|---|---|---|
| v1.0 | xc7a100t-fgg484-2 | stary układ I/O, 8 EEM i dodatkowe złącza backplane; uwaga XADC w komentarzu platformy |
| v1.1 | xc7a100t-fgg484-2 | osobny zestaw pinów _io_v1_1 |
| v2.0 | xc7a100t-fgg484-3 | dodatkowe EEM8..11, EEM power/fault, zmienione sterowanie LED |
| v2.1 | xc7a100t-fgg484-3 | osobny _io_v2_1; nie zakładać identycznego całego pinoutu v2.0 |

Kasli-SoC (Zynq) jest odrębnym kontrolerem i nie należy do tego zestawienia.
XC7A100T ma zasoby wystarczające dla małego softcore i GPIO, ale synteza/P&R małego mostka UARTbone dała 362 LUT i 390 FF w syntezie.
Nie jest to test pełnego softcore/Ethernet/DDR; zewnętrzne I/O nie są w pełni constrained.
Istniejący target MiSoC używa DDR3 MT41K256M16, czyli geometrii 256M x16
(512 MiB), 16-bitowej magistrali A7DDRPHY, cache i konfigurowalnego CPU.
To konfiguracja targetu, nie pomiar RAM na dostępnej płytce; bare-metal slow
control może używać tylko BRAM bez kosztownego DDR initialization.

Ethernet: istniejący MiniSoC ma LiteEth mini A7_1000BASEX, GTP/QPLL i MAC
Wishbone. Kasli korzysta z SFP, nie z PHY RMII STM. UART i flash boot istnieją.
EEM jest interfejsem elektrycznym LVDS z pinami/revizjami i zasilaniem, nie
samodzielnym protokołem. SPI/GPIO można wystawić przez właściwe IBUFDS/OBUFDS;
I2C obsługuje m.in. urządzenia pokładowe, ale nie daje dowolnego I2C do modułów
bez sprawdzonej implementacji/pinów. Trzeba zachować inicjalizację zegarów,
SFP i power EEM zgodnie z targetem; bez niej samo dodanie CSR nie wystarcza.

W aktualnym sklonowanym litex-boards nie znaleziono targetu/platformy Kasli.
**Istniejący dział architektury to MiSoC/Migen używany przez ARTIQ**, nie
nieistniejący plik litex_boards/targets/kasli.py. LiteX może użyć tej platformy,
ale wymaga przystosowania SoC/CRG/PHY i potwierdzenia generacji HDL.

## Trzy warianty

| Wariant | Co można wykorzystać | Koszt / ograniczenie | Decyzja |
|---|---|---|---|
| A: bare-metal LiteX/MiSoC | platforma Kasli, UART, CSR, SPI2/GPIO, MiniSoC Ethernet | nowy mały serwis i właściwy obraz; nie ma gotowego slow-control firmware | preferowany demonstrator docelowy |
| B: Linux softcore | RAM DDR3, VexRiscv z MMU w odpowiednim SoC, LiteX Linux ekosystem | inny CPU/config, DDR/boot/kernel/rootfs/sterowniki; brak gotowego audytowanego Kasli Linux targetu | odłożyć; brak potrzeby dla małego API |
| C: ARTIQ konfiguracja modułów | kompletne sterowniki urządzeń, DDB/JSON descriptor, runtime | Urukul SPI2/TTL/io_update są sterowane przez kernel i RTIO; host nie może zwyczajnie wywołać kernel przez surowy backend | pomoc w HIL, nie niezależny backend |

ARTIQ `StandaloneBase` jest MiniSoC + AMPSoC, VexRiscv, DDR cache oraz RTIO.
Można reuse platform/CRG/DDR/PHY i logikę rejestrów urządzeń; nie trzeba przenosić
schedulerów RTIO, DMA, DRTIO ani warstwy eksperymentów. Sama obecność VexRiscv
nie oznacza gotowego Linux image: potrzebne MMU i dopasowany build.

Implementowany teraz adapter Kasli korzysta z realnego LiteX RemoteClient
(hostowy litex_server do zweryfikowanej magistrali UART/Etherbone). Blok GPIO
został zasymulowany i dostarczono minimalny target UARTbone bez CPU.
Generacja HDL czterech rewizji oraz synteza/routing v2.1 przeszły. Pełny serwis
bare-metal nie został dostarczony, a sprzętowy litex_server nie był uruchamiany.
To etap programowy, nie realizacja A.

## Sterowniki i formaty

ARTIQ ma sterowniki m.in. Urukul CPLD, AD9910/AD9912, Mirny/ADF5356, Zotino/AD53xx,
Sampler, Fastino i Phaser. Transporty SPI2, TTL i pulsy io_update są częścią RTIO.
Warto współdzielić stałe/rejestry, przeliczenia frequency/attenuation i sekwencje
inicjalizacji, zachowując oddzielny transport. Kod @kernel nie jest firmware Rust.

Urukul ma jawne protokoły CPLD 8 i 9 w przejrzanym urukul.py. Protocol 9 używa
innych długości i pól konfiguracji; **nie można wysyłać 24-bitowego CFG protokołu
8 do dowolnego nowego CPLD i deklarować zgodności**. Demonstrator wymaga jawnej
znajomości protokołu 8 przed przejęciem modułu. Odczyt statusu jest równocześnie
zapisem CFG. Wymagany audytowany model fizyczny to HMC542B z krokiem 0.5 dB
(pobrany schemat Urukul v1.5.6); konfiguracja przykładu deklaruje starszą PCB 1.3
z CPLD v8, nie automatyczny dobór wersji na podstawie nowego schematu.

ARTIQ JSON system description i device_db.py opisują kanały/komponenty RTIO;
nie są wspólnym istniejącym standardem konfiguracji STM. Miniconf opisuje typowane
ustawienia MQTT Rust, ESPHome YAML kompiluje konkretny ESP32. Przyjęto niewielki
osobny schemat hosta zamiast udawania zgodności tych trzech formatów.

## Bez Vivado

ECP5 ma realny otwarty tor yosys/nextpnr/Trellis w upstream. Dla Artix-7 dostępne
są projekty prjxray/openXC7/nextpnr-xilinx, ale nie audytowano pełnego Kasli build
z DDR3 + GTP/SFP tym torem. Nie można przenieść sukcesu małego designu na pełny
SoC. Standardowa platforma Migen wybiera Vivado. Host ma współdzielone Vivado
2025.2 i Artix-7 zgodnie z docs/toolchains/vivado.md; nie instalowano nowej kopii
ani nie używano JTAG. Synteza/P&R małego targetu UARTbone przeszły; pełny wariant A/B pozostaje NOT_RUN.
