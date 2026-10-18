# Audyt STM System Board — 2026-10-11

Źródła zostały pobrane z GitHub, a identyfikatory i daty commitów znajdują się
w `evidence/source-commits.json`. Domyślny firmware jest na gałęzi **debug**,
nie main. Przejrzano także tpr_dev i pku_dev oraz gateware tpr_devel.
Zestawienie gałęzi: `evidence/*-branches.txt`. Nie traktujemy daty commitu ani
README jako dowodu sprzętowego.

## Sprzęt i rzeczywiste połączenia

Pobrane releases: [v1.1rc1](https://github.com/sinara-hw/STM_Sys_Board/releases/tag/v1.1rc1)
oraz [v1.0rc2](https://github.com/sinara-hw/STM_Sys_Board/releases/tag/v1.0rc2).
PDF i SHA-256 w evidence/pdf-sources.json. Sprawdzono tekst i obrazy stron FPGA
(v1.1: strona PDF 7; v1.0: strona PDF 5) oraz konfigurację (v1.0: PDF 7).

- STM32H743ZIT6, Cortex-M7; firmware wybiera HAL feature stm32h743v, runner
  STM32H743ZITx i zegar 400 MHz. Dopasowanie feature/pakietu wymaga przeglądu HAL.
- ECP5 LFE5U-85F-6BG554C, 85K-class, zewnętrzny clock i osobna pamięć konfiguracji.
- Ethernet LAN8742A-CZ-TR poprzez RMII do STM32; FPGA nie jest procesorem sieciowym.
- Konfiguracja FPGA: JTAG ECP5 oraz W25Q128JVPIQ i bufor/multiplekser 74HC4066
  do sygnałów CFG_FLASH. Firmware jedynie ustawia PROGRAM_N high; brak loadera
  bitstreamu Rust w przejrzanym setup. Upstream load.py ładuje SVF tymczasowo,
  flash.sh przewiduje flash. Żadna z tych procedur nie została tu wykonana.
- QSPI danych i QSPI konfiguracji są odrębnymi sieciami. Cztery przewody danych
  istnieją sprzętowo, ale SPI2WB implementuje tylko x1, nie x4.

| Sieć | STM32 / firmware setup | ECP5 w obu pobranych PDF | Gateware main i tpr_devel |
|---|---|---|---|
| QSPI_IO0 | PE7, AF10 | AA23 | AB24 |
| QSPI_IO1 | PE8, AF10 | AA24 | AA24 |
| QSPI_IO2 | PE9, AF10 | AB24 | AA23 w qspix4 |
| QSPI_IO3 | PE10, AF10 | AF25 | AA22 w qspix4 |
| QSPI_CLK | PF10, AF9 | AA25 | E11 |
| QSPI_NCS | PC11, AF9 | AA22 | AF25 |

Tabela odzwierciedla opisy portów schematu, nie ciągłość zmierzoną na PCB.
QSPI_IO0/IO2 i QSPI_NCS/IO3 są zamienione względem deklaracji gateware.
Przy takim rozjeździe **nie wolno automatycznie poprawiać tylko
jednego pinu ani programować płytki**. Różnią się też pin clk100/CLK_FPGA i sloty
między rewizjami. v1.1 ma zmienione przypisania slotów i wydzielone sygnały SPI.
Brak sprawdzonego adaptera DIOT–EEM dla Urukul.

## Gateware i mapa rejestrów

Źródła: [main](https://github.com/elhep/stm_system_board_gateware/tree/b84376286bf7971d7907b8945c3c677ba972fd61),
[tpr_devel](https://github.com/elhep/stm_system_board_gateware/tree/46f14f81d6a29c664f72d8c7373f4d346b43970d).
Migen + **MiSoC** Wishbone/CSR/SPI2, platform/build z LiteX; yosys/nextpnr/Trellis
w flake Nix z zależnościami przypiętymi do starych commitów. Nie jest to współczesny
SoC LiteX z CPU w ECP5.

Osiem SlotController, po 16 logicznych linii. Pierwsze cztery mogą być przełączane
między GPIO a SPI; inne są GPIO. Faktyczny kierunek części LVDS jest ustalony
listą `silpa_outputs=[0,1,3,6,7]`, więc nie jest pełnym dowolnym GPIO i nie
potwierdza możliwości mapowania Urukul. MLVDS i LVDS wymagają poprawnej
polaryzacji/terminacji, nie zamiany na przypadkowe piny jednokońcówkowe.

Mapa deklarowana firmware: slot firmware 0..7 odpowiada fizycznym slotom 1..8,
baza `20 * slot`, rejestry słowowe 16-bit:

| Offset | Rejestr |
|---|---|
| 0..5 | OUTPUT, INPUT, OE, INT, INT_MSK, INT_CL |
| 6..19 | SPI DATA, LENGTH, CS, CS_POL, DIV, OFFLINE, CLK_POL, CLK_PHA, LSB_FST, HALF_DUP, END, READABLE, WRITABLE, IDLE |

Main ma adres 7-bit, więc pojemność 128 < 160 rejestrów. Kontrola liczby rejestrów
jest zakomentowana. Nagłówek wire w main: 1+7 bitów, firmware: 16 bitów
(read bit 15, address 15 bitów). **Main i debug firmware są niezgodne.**
README opisuje ponadto dawną konfigurację dwóch slotów i ID 0x28/0x29; nie
odpowiada ośmiu slotom źródła.

`tpr_devel` ma address_reg_len=15, CSRBank align_bits=0 i ID1/ID2/gate_rev
po blokach slotów (oczekiwane 160/161/162). To odpowiada nagłówkowi firmware
U16(address) / U16(0x8000|address); obowiązkowo należy potwierdzić wygenerowaną
mapę, nie tylko kolejność w Pythonie. Rejestr gate_rev=3 nie potwierdza pinoutu.

SPI master: transfery do 16 bitów, kontynuacja/END umożliwia dłuższe ramki;
firmware dzieli bajty na bloki. Istnieją bezterminowe pętle busy/readable/writable
oraz unwrap; częściowy read_spi wymaga dodatkowych testów granic.
Brak ogólnego kontrolera I2C w ECP5; firmware korzysta z I2C1/I2C2/I2C4 STM32
(therm, serwis, CPCIS). Wykrywanie modułów jest typowane podczas kompilacji
makrem devices_list, nie uniwersalnym skanem EEPROM i identyfikacją Sinara.

## Rust / sieć / urządzenia

[Źródła firmware](https://github.com/elhep/stm_system_board_firmware/tree/19bc5913abe66b39f5fce9cf45c9f7126b8782c4):
no_std, Cortex-M RTIC, shared-bus AtomicCheckMutex; osobne init, settings_update,
telemetry i obsługa sieci. smoltcp-nal, minimq, Miniconf 0.5 i serde-json-core.
MQTT broker jest ustawiony statycznie na 10.99.1.202; ustawienia per moduł oraz
telemetria mają własne topiki. Nie istnieje używany przez nas raw-Wishbone UART
service ani uniwersalny endpoint discover/read/write.

Obecne źródła sterowników: HvSupIsol warianty, IsoSPI_8ch, Magneto, TempLogger;
SiLPA i Nucleo tester częściowo obecne, ale niewłączone w boards/mod.rs.
IC: MAX1329, MAX31865, LM75A, MMC5983MA, MCP23S08, EEPROM. Domyślna lista:
slot0 IsoSPI_8ch, slot4 TempLogger, pozostałe EmptySlot. Brak Urukul/AD9910/AD9912.
Komentarze odziedziczone po Stabilizer nie są dowodem połączeń STM System Board.

## Klasyfikacja dowodów

| Funkcja | Stan źródeł | Potwierdzenie sprzętowe w tym zadaniu |
|---|---|---|
| UART/RTT/debug, boot RTIC | kod obecny | brak |
| Ethernet RMII/PHY/MQTT/telemetria | kod obecny | brak |
| ECP5 SPI2WB main + firmware debug | niespójne | brak |
| ECP5 SPI2WB tpr_devel wire format | zaimplementowane, lepsza zgodność źródeł | brak, pinout rozbieżny |
| SPI slotów / GPIO / IRQ | zaimplementowane, ograniczone kierunki | brak |
| ogólny I2C w ECP5 | nieobecny | nie dotyczy |
| autodiscovery Sinara / Urukul | nieobecne | nie dotyczy |
| bramka Rust tego projektu | testy hostowe PASS; HAL/RTIC nie podłączone | brak |
| autonomiczny safe-state/watchdog | planowane | brak |

Upstream tb.v opisuje **2 sloty i 7-bitowy adres**, nie bieżący wariant 8 slotów.
Procedury uruchamiania istnieją (Nix, OpenOCD, probe-rs), ale brak odtwarzalnego
raportu HIL przy konkretnym zestawie rewizji. W tym zadaniu żaden element STM
nie otrzymuje kategorii „zaimplementowane i przetestowane sprzętowo”.
Próba `cargo check --offline --locked` została zatrzymana przez brak asm-delay
w lokalnym cache; to ograniczenie środowiska, nie dowód błędu kompilacji upstream.
