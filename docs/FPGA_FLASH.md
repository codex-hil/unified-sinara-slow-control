# Programowanie flash FPGA — YAML, API i standardowe programatory

Stan 2026-10-17: implementacja programowa i test integracyjny PASS,
firmware STM cross-build PASS. Bez programowania fizycznej pamięci.

## Dwie drogi do tej samej pamięci

1. STM v1.1: dedykowane SPI1 konfiguracji, udostępnione standardowym
   protokołem **serprog v1**. Algorytmy NOR wykonuje istniejący **flashrom**.
   Nie dodano drugiej implementacji erase/page-program/status register.
2. Zewnętrzny programator: **openFPGALoader przez JTAG**, z wyborem kabla,
   USB serial i pozycji w łańcuchu. Dodatkowo backend flashrom obsługuje
   programatory SPI ft2232_spi/ch341a_spi/dediprog/stlinkv3_spi.

Zadanie programowania jest osobnym YAML od konfiguracji modułów. Zmiana
programatora wymaga zmiany profilu połączenia, nie zadania ani obrazu.
`SlowControl.configure()` nigdy nie programuje flash automatycznie.

## Połączenia STM v1.1

Zweryfikowano wizualnie release PDF `STM_System_Board_Extended.PDF`,
strona4 (CPU) i17 (arkusz12 konfiguracji): IC14 W25Q128JVPIQ,
16MiB, IC15 74HC4066PW. To NIE jest QSPI danych STM–ECP5 ani SPI4/595.

| Funkcja | STM pin | Użycie |
|---|---|---|
| SPI1 SCK | PG11 AF5 | CFG_FLASH_SCLK |
| SPI1 MISO | PG9 AF5 | CFG_FLASH_MISO |
| SPI1 MOSI | PD7 AF5 | CFG_FLASH_MOSI |
| CS | PG10 GPIO | CFG_FLASH_SSEL, aktywne nisko |
| Mux | PE15 GPIO | CFG_FLASH_UP_EN, aktywne wysoko |
| Reset FPGA | PG0 GPIO | PROGRAM_N, aktywne nisko |
| Gotowość FPGA | PE1 input | DONE |
| Maintenance UART | PD8/PD9 AF7 | USART3 TX/RX, 1Mbaud 8N1 |

Firmware `firmware/hil/flash_serprog.rs` jest **osobnym obrazem serwisowym**,
nie rozszerzeniem już wdrożonego runtime. Nie uruchamia init modułów,
Ethernetu, MQTT ani oryginalnego board setup. Używa istniejącego HAL Rust.
Uruchomienie obrazu zatrzymuje FPGA — nie jest przezroczystą usługą tła.
Do uruchomienia na STM potrzebne będzie zatwierdzone załadowanie firmware;
ELF jest linkowany do flash STM, nie jest obrazem RAM-only.

Na początku mux jest odłączony i PROGRAM_N niski. `S_PIN_STATE=1`
ustawia CS wysoko, trzyma PROGRAM_N nisko przez200us, wymaga DONE=0,
a dopiero potem włącza4066. `S_PIN_STATE=0`, utrata framingu albo timeout
odłącza4066, pozostawiając FPGA w resecie. SPI1 działa nominalnie1MHz;
rzeczywiste zegary i kierunki wymagają HIL. Blocking SPI HAL może utknąć
przy błędzie peryferium; nie deklarujemy pełnego watchdog/recovery.

Standard flashrom nie restartuje FPGA na końcu. Jawne `reconfigure: true`
po zweryfikowanym zapisie wysyła rozszerzenie `0x80 + BOOT`. Firmware
sprawdza WIP, odłącza mux, zwalnia PROGRAM_N i oczekuje DONE do5s.
BOOT nie jest reklamowane jako standardowy serprog i wymaga tego firmware.
Zewnętrzne programatory nie przyjmują tego rozszerzenia: API odrzuca
`reconfigure: true` dla tych profili przed rozpoczęciem zapisu.

Podstawa sekwencji resetu: [Lattice ECP5 sysCONFIG](https://www.latticesemi.com/view_document?document_id=50462).
Zewnętrzny JTAG wymaga odłączonego muxa i uzgodnionego stanu PROGRAM_N;
nie może pracować równocześnie ze STM serprog. Bezpośredni programator
SPI wymaga osobnego, sprawdzonego fixture/resetu FPGA. API nie steruje
zewnętrznym fixture. W obu drogach obowiązuje wspólny lock konkretnej płyty.

## Zadanie YAML i CLI

Przykłady: `examples/fpga-flash.yaml`, `examples/flash-stm-spi.yaml`,
`examples/flash-stm-jtag.yaml`. Profile mają nieustalone identyfikatory
oraz reviewed=false, więc wykonanie jest odrzucane. Plan nie dotyka sprzętu.

```yaml
schema_version: 1
operation: fpga_flash
format: raw
fpga_part: lfe5u-85f
image: approved-image.bit
sha256: <64 znaki SHA-256>
offset: 0
reconfigure: false
```

`image` jest względne wobec YAML. Wymagane surowe bajty flash: ECP5
z ecppack może mieć rozszerzenie.bit. SVF/ELF/JEDEC/MCS nie są obrazami
raw. Dla Kasli należy przygotować odpowiedni **raw SPI boot image**;
kontener Xilinx.bit wymaga wcześniejszej konwersji. Walidacja SHA i pola
part nie jest analizatorem CRC/IDCODE wewnątrz bitstreamu. Akceptować
wyłącznie obraz właściwy dla zweryfikowanej płytki i rewizji.

```sh
PYTHONPATH=src python3 -m sinara_slow.flash_cli plan examples/fpga-flash.yaml --connection examples/flash-stm-spi.yaml
# Dopiero dla sprawdzonego połączenia i zatwierdzonego zapisu:
PYTHONPATH=src python3 -m sinara_slow.flash_cli program job.yaml --connection connection.yaml --artifacts work/flash-runs --execute
```

Po zainstalowaniu pakietu to samo udostępnia `sinara-flash`.

Operacja blokuje płytę przez cały backup/zapis/weryfikację/restart.
Przed połączeniem sprawdza SHA, zgodność part, granice, protected_regions,
reviewed i miejsce na dysku. Wykonuje pełny backup, nakłada obraz na kopię
bez zmiany pozostałych bajtów, fsync backupu i pliku desired, a następnie
zapisuje **pełny obraz** narzędziem z weryfikacją. Osobny odczyt porównuje
wszystkie bajty flash, także poza aktualizowanym zakresem i w końcowym
sektorze. Dla JTAG backup musi zawierać zgodny JEDEC ID w logu; inaczej
zapis nie ruszy. `--skip-reset` zapobiega automatycznemu startowi FPGA
przez openFPGALoader pomiędzy fazami. Numery seryjne są obowiązkowe.

Każda próba zachowuje backup.bin, desired.bin, readback.bin (jeśli był),
logi i report.json w osobnym katalogu. Błąd po rozpoczęciu zapisu oznacza
nieznany wynik; nie ma retry ani automatycznego rollbacku. Aktualizacja
jest single-image, nie atomowa: przerwanie zasilania może wymagać odtworzenia
backupu przez programator. timeout_s dotyczy każdej fazy narzędzia.

## API hosta

Python: `FPGAFlash(connection).plan(job)` i
`FPGAFlash(connection).program(job, artifacts=...)`.

HTTP to **usługa na komputerze hosta**, nie gotowy endpoint Ethernet STM
ani natywny komponent ESPHome. YAML parsuje host, serprog przenosi SPI.

```sh
PYTHONPATH=src python3 -m sinara_slow.flash_cli serve job.yaml --connection connection.yaml --artifacts work/flash-runs --token-file work/private-token.txt
```

Nasłuch wyłącznie127.0.0.1:8765. Token plikowy co najmniej32 znaki.
`Authorization: Bearer <token>` jest wymagane także dla planu.

- GET `/v1/fpga/flash/plan` — odczyt planu, bez sprzętu.
- POST `/v1/fpga/flash/program`, body `{}` — wykonanie wyłącznie YAML
  zarejestrowanego przy starcie usługi. Nie przyjmuje ścieżek ani poleceń klienta.

Wywołanie program jest synchroniczne. Równoległy zapis zwraca BUSY.
Usługa nie jest uruchamiana automatycznie. Integracja z docelowym runtime
ESPHome/C++ i nieprzerwany serwis slow control pozostają osobnym etapem.

## Standardowe narzędzia

Serprog jest zgodny z [protokołem flashrom v1](https://github.com/flashrom/flashrom/blob/fb281f64bf58b547300a38ab9634711ddaf05e39/doc/supported_hw/supported_prog/serprog/serprog-protocol.rst).
Ten sam STM może służyć jako zwykły programator flash:

```sh
flashrom -p serprog:dev=/dev/serial/by-id/VERIFIED_UART:1000000 -c W25Q128.V -r backup.bin
flashrom -p serprog:dev=/dev/serial/by-id/VERIFIED_UART:1000000 -c W25Q128.V -w desired-full-flash.bin
```

W25Q128 wymaga pełnego pliku16MiB dla `flashrom -w`. Nie podawać krótkiego
bitstreamu zamiast pełnego obrazu. desired.bin z pipeline API ma właściwy
rozmiar i zachowuje pozostałe dane. Bezpośrednie narzędzia trzeba uruchamiać
pod tym samym lockiem płyty; nie omijają koordynacji urządzeń.

[openFPGALoader](https://github.com/trabucayre/openFPGALoader) obsługuje
standardową drogę JTAG. Adapter API używa dump-flash/file-size,
write-flash/verify, file-type bin, skip-reset i jawnego USB serial.
Przejrzane źródło bf2b52916e7b6216ba1cc0b30933827d7735b05d;
fragmenty audytu źródeł w evidence/ofl-*.cpp. Nie uruchamiano tego narzędzia
na fizycznym programatorze; testowany jest adapter poleceń.

## Odtworzenie i stan testów

- `python3 tools/test_all.py`: Python, stary gateway Rust i serprog Rust.
- `python3 tools/build_flash_service.py`: cross-build STM, bez uruchomienia.
- `cargo build --example nor_tcp_sim --manifest-path firmware/flash-serprog/Cargo.toml`
- `python3 tools/test_flash_integration.py`: rzeczywisty flashrom przez TCP
  do tego samego core serprog Rust i modelu NOR16MiB, nie do sprzętu.

Lokalny flashrom zbudowano z fb281f64bf58b547300a38ab9634711ddaf05e39,
serprog+dummy, nie ze wszystkimi driverami USB. Do zewnętrznego programatora
należy wskazać instalację zawierającą jego driver. Rebuild:

```sh
/home/codex-hil/vector-analyser/.venv/bin/pip install --target work/flash-tools meson ninja
python3 tools/build_flashrom.py
```

Wymagany checkout references/flashrom w podanym commicie. Kod Nor modelu
jest wyłącznie fixture testowym. Dowody: evidence/flash-integration.json,
flash-service-build.json oraz test-results.json. Testowane: HTTP auth,
YAML, hash/part/granice/protected, lock, brak miejsca, utrata odpowiedzi,
zachowanie backupu, niezależny pełny readback, erase0→1, ostatni sektor
oraz BOOT RPC w symulacji. Fizyczne SPI1/4066/DONE/UART i JTAG, ponowny
boot z NOR i zachowanie przy przerwaniu zasilania pozostają NOT_RUN.

Timeout klienta HTTP nie anuluje rozpoczętego procesu programowania. Po utracie odpowiedzi nie ponawiać automatycznie POST: sprawdzić report.json w katalogu artifacts. Odpowiedź serwera może zostać utracona mimo zakończonej weryfikacji.
