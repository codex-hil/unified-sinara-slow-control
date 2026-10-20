# Wyniki testów — 2026-10-11

Wyniki dotyczą źródeł i jawnych symulacji. **HIL obu kontrolerów: NOT_RUN.**
Nie połączono się z fizycznymi portami UART, JTAG ani urządzeniami sieciowymi.

| Weryfikacja | Wynik | Co potwierdza / ograniczenie |
|---|---|---|
| unittest Python | 28 PASS | schema, units/ranges, duplicate keys, backend parity, SPI edges, readback, errors; 64 kroki zgodne z kodem upstream ARTIQ |
| Rust cargo test | 5 PASS | parser, whitelist, slot7, ABI, deadline argument, error codes |
| Python → skompilowany Rust parser | PASS, 8 slotów | prawdziwa zgodność wire; rejestry symulowane, nie UART STM32 |
| Serial framing → GPIO simulator → SPI | PASS | fragmented replies i działanie STM adaptera; brak płytki |
| LiteX register adapter → SPI simulator | PASS | zgodność adaptera; mock client, nie FPGA |
| Migen GPIO/ABI | 2 testy wliczone w unittest | kierunki/logika wartości i ABI |
| Kasli HDL generation | PASS v1.0/v1.1/v2.0/v2.1 | target UARTbone, mapy pinów syntetyczne |
| Vivado 2025.2 synthesis | PASS v2.1 | xc7a100t-fgg484-3, 362 LUT / 390 FF / 0 BRAM / 0 DSP |
| Vivado place/route | PASS v2.1 | syntetyczny EEM pin map; brak walidacji PCB/okablowania |
| external timing / config voltage | INCOMPLETE | 2 input/6 output bez delays; CFGBVS-1 warning |
| bitstream generation/programming | NOT_RUN | nie ma obrazu przeznaczonego do wgrania |
| upstream STM cargo check offline | BLOCKED | brak asm-delay w cache; nie dowód błędu upstream |
| STM gateware build/P&R | NOT_RUN | pinout i wybrana rewizja nadal wymagają ustalenia |
| autonomiczny watchdog/config hold | NOT_IMPLEMENTED | latch nie jest dowodem bezpiecznej autonomii |
| DDS frequency / RF power validation | NOT_IMPLEMENTED / NOT_RUN | schemat odrzuca frequency i enabled=true |

Raporty: `evidence/test-results.json`, `evidence/test-*.log`,
`evidence/kasli-elaboration/gateware/{synthesis,route}.log`,
`*_utilization.rpt`, `routed_timing.rpt`, `routed_drc.rpt`.
Raport timing jest oceną wewnętrznych ścieżek przy zadanych constraints;
nie wolno interpretować dodatniego WNS jako zamknięcia timingu interfejsu Urukul.

## Powtórzenie

```sh
python3 tools/test_all.py
```

Generacja HDL używa checkoutów zapisanych w source-commits.json i `packaging`.
Na tym hoście wykorzystano istniejący interpreter z packaging:

```sh
/home/codex-hil/lab-control/.venv/bin/python tools/generate_kasli_test.py
```

Na innym hoście wystarczy interpreter z packaging, pyserial, Migen i LiteX
w wersjach zgodnych z manifestem. Skrypt dodaje lokalne references do PYTHONPATH.
Synteza/routing używa współdzielonego launchera Vivado, nie nowej instalacji:

```sh
cd evidence/kasli-elaboration/gateware
vivado -mode batch -source synth_only.tcl -log synthesis.log -journal synthesis.jou
vivado -mode batch -source route_only.tcl -log route.log -journal route.jou
```

To wyłącznie offline build; mapa testowa nie jest zezwoleniem na programowanie.
Pełna zgodność dwóch fizycznych backendów, samodzielne utrzymanie konfiguracji
oraz pomiary RF pozostają do wykonania.

## Reprodukcja STM upstream 2026-10-11

Firmware debug: niezmieniony source, Rust 1.88.0, locked release ARM ELF PASS.
Gateware tpr_devel: elaboracja PASS, Yosys PASS, strict nextpnr seed 3 PASS
(100.30 MHz / 100 MHz), ecppack BIT/SVF PASS. Seed 1 i 2 fail timing.
Nowszy Yosys/nextpnr niż w historycznym Nix; nie jest to bit-identyczna
reprodukcja starego toolchainu. Nie zweryfikowano external I/O/CDC na PCB.
Directed simulation oryginalnego SlotController GPIO/OE/input/IRQ PASS;
pełny most SPI2WB oraz fizyczny QSPI pozostają osobnymi zadaniami.
Regresja: 28 Python i 5 Rust PASS; źródła logów w evidence/test-results.json.
Metadane buildów i hashe: evidence/stm-upstream-build-result.json.

Most SPI2WB: test 25 MHz x1 / header16 / dummy5 / IDs160..162 oraz
zapis i readback140 PASS. Reproducer: `python3 tools/reproduce_stm.py bridge-sim`
i `python3 tools/reproduce_stm.py slot-sim`. Niezmieniony counter.v i SPI2WB;
behavioral FD1P3BX oraz RAM Wishbone, bez elektryki/pełnego CSR bank. Harness
obserwuje jeden zapis adr0 po resecie, wyłączony z kontroli transakcji;
bezpieczeństwo startu pozostaje do zbadania, nie uznano go za pasywne.

Dodatkowa kontrola wykazała dwa odczyty Wishbone na jeden odczyt serial
w tym harnessie (4 odczyty serial = 8 WB). Transfer wartości PASS,
semantyka exactly-once odczytu FAIL; test baseline zapisuje to ograniczenie.
Przed użyciem rejestrów z efektami ubocznymi konieczne rozpoznanie/poprawka
i test na rzeczywistym CSR bank/PCB. Nie zmieniono źródeł upstream.

## Próba ESPHome — 2026-10-12

Zgodnie z nowym kierunkiem uruchomiono rzeczywisty runtime ESPHome 2026.9.0
na x86_64 Linux host z lokalnymi external_components. Sterowniki MAX31865
i LM75B pozostają oryginalne, bez zmian. SPI/GPIO adapter oraz logiczny
I2C model publikują syntetyczne wartości: PT100 -0.0088°C, LM75B 25°C.
Walidacja, kompilacja, bounded runtime oraz hardware-mode/slot-range reject
PASS. Wyniki są symulowane, nie stanowią pomiarów ani MVP sprzętowego.

Nie wykonano portu STM, cross-build Kasli ani fizycznego tunelu I2C przez
SPI. Transport adresowanego SPI z osobnego wątku wymaga uzgodnionego API;
nie wymyślono nowego protokołu sprzętowego. Instrukcja i patch upstream:
[integrations/esphome/README.md](integrations/esphome/README.md). Dowody:
evidence/esphome-test-result.json. Poprzednie rdzenie Rust zachowano.

## Pinmux — 2026-10-13

30 testów Python i 5 Rust oraz testy protokołu PASS. Nowe symulacje Migen obejmują domyślne i zmienione mapowanie, osobne CS, OE, wejścia i powrót GPIO. Cały izolowany target STM elaboruje (163 CSR/20 na slot); wspólny SlotController generuje Verilog dla Kasli v1.1/Artix-7. Dowody: `evidence/shared-pinmux-build.json`, `shared-pinmux-build.log`, `test-1.log`. Nowy wariant nie przeszedł syntezy/P&R ani testów sprzętowych. Kasli nie ma jeszcze integracji tego slotu z SoC/padami.

## Automat kierunków — 2026-10-13

Dodano wspólny DirectionController i wrapper CSR dla STM (48-bitowy łańcuch 595) oraz Kasli (bez 595). Symulacje storage/shift, snapshot, quiescent i CSR rejection/clear PASS; generacja HDL obu wrapperów PASS. Regresja 32 Python, 5 Rust i protokół PASS. Podłączenie do banku CSR, OE pinmuxa, arbitrażu i fizycznych padów pozostaje do wykonania. Nie ma syntezy/P&R/HIL automatu. Reset nie zeruje sam zewnętrznego storage; brak gwarancji bezglitchowej zmiany kierunków. Szczegóły: [PINMUX](docs/PINMUX.md).

## Zintegrowany fabric i pakiet HIL — 2026-10-13

Kandydat STM ABI4 ma bank kierunków 0x800..0x808, spójne OE FPGA/595,
blokadę zapisów podczas busy i odrzucanie apply przy aktywnym SPI.
Zachowuje adresy slotów/ID; górne OE slotów1–6 pochodzą z nowej maski.
Sloty7/8 mają nadal ograniczenia stałych buforów. IRQ używa rzeczywistego
OE i jest maskowane podczas aktualizacji. Rejestrowane SCK/RCLK usuwają
dodatkowe zbocza wykryte w symulacji Veriloga. Legacy CSR odczyt używa
zarejestrowanego one-hot select; test pełnego mostu używa rzeczywistych CSR.

STM Yosys + strict nextpnr PASS: seed2, sys100.83 MHz przy wymaganych100.
Seed3 i seed7 po poprawkach:99.12/99.65 MHz FAIL, zapisane osobno.
Kasli XC7A100T-2: ośmioslotowy blok logiczny, Vivado OOC synthesis/route
PASS, 2014 LUT/2077 FF, setup8.398 ns/hold0.108 ns przy62.5 MHz.
To nadal nie cały Kasli SoC ani fizyczne EEM. Zewnętrzny timing/CDC i HIL
niezweryfikowane; żaden obraz nie został załadowany.

Symulacje Migen banku CSR/arbitrażu dla serial/direct PASS; test Icarus
QSPI x1@25MHz–SPI2WB–WB2CSR–CSR–595 PASS: ID/rev4, maska/readback,
48 taktów na latch, blokada zapisu i powrót do wejść. Oryginalny bridge
nadal ma spurious startup write i powtórzone odczyty WB. Nowa inicjalizacja
blokuje legacy write w czasie busy; nie uznano tego za dowód pasywnego bootu.
38 testów Python, 5 Rust i testy protokołu PASS.

STM `hil_probe` zbudowany Rust1.88: odczytuje ID/rev osiem razy i raportuje
RTT. Bez modułów init/MQTT/SPI4/CSR write; zachowuje upstream board setup,
który konfiguruje GPIO/PHY/I2C i może blokować. Firmware nie był uruchamiany.
Host `Directions` wymaga prawdziwego transportu słów16 ABI4 i wyłącznego
właściciela; nie jest wdrożonym gatewayem i nie ponawia apply po timeout.

Reproducery: `python3 tools/reproduce_stm.py fabric-sim`,
`python3 tools/reproduce_stm.py integrated-bridge-sim`,
`python3 tools/build_integrated.py stm --seed 2`,
`python3 tools/build_integrated.py kasli`,
`python3 tools/build_hil_probe.py`, `python3 tools/prepare_hil.py`.
Dowody: `evidence/integrated-*-*.json`, `evidence/hil-probe-build.json`,
`evidence/hil-manifest.json`. Zamrożone obrazy z SHA-256 są w
`work/hil-kit/2026-10-14`. [Procedura na sprzęcie](docs/HIL_START.md).

Pozostają przegląd fizycznej mapy, identyfikacja programatorów i uzgodnienie
konkretnych działań po podłączeniu. Nie ma jeszcze pełnego QSPI x4,
interaktywnego serwisu CSR STM/Kasli ani portów ESPHome na te platformy.

## Finalny wariant z rejestrowanym OE — 2026-10-13

Po końcowym przeglądzie OE także jest rejestrowane: zerowane przy
akceptacji apply, ustawiane z pending dopiero po settle. Test Verilog
liczy wyłącznie dwie oczekiwane zmiany OE podczas maska/input, bez
przejściowych impulsów od dekodowania FSM. Obejmuje również rzeczywisty
master MiSoC: MOSI A5/5A, CS i 16 zboczy SCK, MISO oraz odczyt DATA=FF;
IRQ rozpoznaje actual OE i jest tłumione podczas aktualizacji.

Finalny STM strict P&R PASS:106.15MHz przy100, seed3,
placer-heap-timingweight20 + timing-driven ripup. Bez obejścia timing checks.
Finalny Kasli OOC PASS:2012 LUT/2125 FF, setup8.936 ns,
hold0.110 ns przy62.5MHz. Wcześniejsze liczby100.83/8.398/0.108
powyżej dotyczą wersji przed rejestrowaniem OE. Finalne reporty i SHA:
`evidence/integrated-stm-build.json`, `integrated-kasli-build.json`.
Reproducer STM: `python3 tools/build_integrated.py stm` (domyślnie3/20/ripup).
Wszystkie ograniczenia fizycznych padów, resetu i niezweryfikowanego HIL
pozostają aktualne. Zamrożony manifest wybiera wyłącznie końcowy wariant.

## Capture RTT — 2026-10-14

43 Python /5 Rust/wire tests PASS. Nowe testy sprawdzają kompletny log
ABI3/4, ANSI, błędne ID pomimo PASS, ucięcie/duplikat/reorder/restart,
QSPI error i zły ABI. CLI zwraca0 dla poprawnego syntetycznego capture,
1 dla uszkodzonego. `evidence/hil-capture-checker-tests.json`: fixtures
synthetic, hardware_tested=false. Nie otrzymano rzeczywistego capture.
Nie zmieniono obrazów FPGA/STM ani nie powtarzano zakończonych buildów.

## Utrata odpowiedzi apply — 2026-10-15

44 testy Python/5 Rust/wire PASS. Nowy test zatwierdza maskę w fixture,
a potem zgłasza błąd transportu bez uncertain. Klient poprawnie ustawia
uncertain=true i nie ponawia apply. Fixture nie jest testem sprzętowym.
Bez zmian obrazów i gateware; synteza/P&R nie były ponawiane.

## Urukul pinmux — 2026-10-17

- `python3 tools/test_all.py`:55 testów Python,5 Rust, build stdio,
  reference check i cross-language wire PASS.
- `python3 tools/reproduce_stm.py fabric-sim`:dotychczasowa regresja
  zintegrowanego fabricu PASS.
- `tools/test_urukul_pinmux.py`:STM i Kasli CSR/master/pinmux PASS;
  adresy CS1/2/4, transfery24/32bit, MISO, OE, idle000, GPIO fallback.
  Pełny target STM z profilem slot0 elaboruje; slot1 zachowuje domyślny mux.
  Raport: `evidence/urukul-pinmux-tests.json`.

Bez nowych syntez/P&R, obrazów HIL ani fizycznych operacji. Granice:
`docs/URUKUL.md`. Funkcjonalny test SPI nie dowodzi poprawnego startupu
CS ani elektryki kabla/adaptera. CPLD8/tłumiki/RF OFF; DDS poza zakresem.

## Programowanie flash FPGA — 2026-10-17

Nowy serprog Rust:4 testy PASS. STM flash_serprog cross-build Rust1.88 PASS. YAML/API/CLI plan oraz obsługa backup/patch/readback/locków, błędów transportu, miejsca na dysku, utraty journal i HTTP auth przeszły testy hosta. Lokalny flashrom skompilowany z audited fb281f64... z serprog+dummy.

Test end-to-end używa rzeczywistego flashrom, HTTP API oraz tego samego core serprog Rust nad TCP i modelem NOR16MiB: backup, zapis, verify, niezależny readback, erase0→1, zachowanie danych poza obrazem i w ogonie sektora PASS. BOOT RPC testowany wyłącznie syntetycznie. Zewnętrzny openFPGALoader ma wyłącznie testy poleceń i odrzucania błędnego JEDEC, bez uruchomienia na urządzeniu. hardware_tested=false we wszystkich nowych dowodach. Finalna liczba testów w evidence/test-results.json i test-1.log. Nie wykonano żadnego zapisu flash sprzętu.

## Sampler — 2026-10-17

57 unittest (w tym kompilowany przenośny driver C++17),9 Rust, wire i
regresja oryginalnych komponentów ESPHome PASS. Sampler ESPHome2026.9.0:
oba profile simulation compile/run, STM PTY/protokół i LiteX RemoteServer
localhost/model ADC PASS. Błąd podczas ramki nie publikuje częściowego
wyniku; wszystkie8 sensorów dostają NaN, hub zatrzymuje się bez replay.
Odrzucanie niezgodnego pinmuxa, możliwości wejścia, gainów, współdzielonego
endpointu i podwójnego sensora oraz nieprzejrzanego profilu hardware PASS.

Profil8 par Kasli v1.1: generacja HDL PASS, bez syntezy/P&R/HIL. Raporty:
`evidence/sampler-esphome-tests.json`, `sampler-kasli-elaboration.json`,
`test-results.json`; opis i odtworzenie w [SAMPLER](docs/SAMPLER.md).

## Zotino — 2026-10-17

Dodano wspólny sterownik C++17 AD5372 dla STM/Kasli, komponent ESPHome
`sinara_zotino` i standardowe wyjścia32 kanałów. Obsługuje zapis wektora
z LDAC, nominalne przeliczenie napięcia, odczyt rejestru DAC, LED i kontrolę
CONTROL/overtemperature. DAC mode1, LED mode0, niezależne aktywne-nisko CS.
Wykorzystuje endpoint GPIO Samplera i istniejące protokoły, bez RTIO.

58 testów Python (w tym native C++ z błędami każdego kroku),9 Rust i wire
PASS. ESPHome2026.9.0 compile/runtime obu przykładów, STM PTY i realny
LiteX RemoteServer na localhost z modelem DAC i błędem transportu PASS.
Kasli `zotino_eem0`: generacja HDL PASS, bez syntezy/P&R/programowania.
Brak HIL i pomiarów analogowych; native runtime STM/Kasli i fizyczne
profile nadal wymagają integracji. [Dokumentacja](docs/ZOTINO.md),
`evidence/zotino-esphome-tests.json`, `evidence/zotino-kasli-elaboration.json`.

## Jawne adresowanie GPIO — 2026-10-17

YAML Samplera i Zotino używa `pinmux: funkcja: {slot: N, line: M}`.
Wspólny schemat odrzuca nieprawidłowe zakresy, duplikaty, inny slot niż
endpointu i stare skalary. Zaktualizowano cztery przykłady oraz testy
integracyjne. Walidacja ESPHome20/20 PASS i `tools/test_all.py` PASS.
Nie zmieniono gateware ani fizycznego profilu; brak HIL. Kierunki STM dla
Samplera nadal wymagają osobnego profilu. CNV jest generowany przez driver
GPIO; lokalny automat impulsu i konwersji FPGA pozostaje do implementacji.

Po zmianie numeracji slotów na1..8 ponownie przeszły: walidacja20/20,
58 testów Python,9 Rust, wire tests oraz pełne skrypty ESPHome Samplera
 i Zotino (compile/runtime, STM PTY, Kasli localhost LiteX i błędy transportu).
Modele danych syntetyczne; brak HIL. Raporty w evidence/*-esphome-tests.json.

## Standardowe komponenty ESPHome nad FPGA — 2026-10-17

Dodano `sinara_gpio`: GPIOPin o numerze np. `"7_15"`, INPUT/OUTPUT,
inwersja, walidacja slotu/kierunku i RMW zachowujący inne linie.
Bazowy SPI używa istniejącego ESPHome bitbang nad tymi pinami; adapter
utrzymuje blokadę/deadline ramki i invaliduje odczyt MAX31855 po awarii.
Piny i routery obsługuje ten sam interfejs co ESPHome na ESP32.
Przypięte `addrspi`/`addrspi2` MODULIQ pozostają niezmienione; standardowy
MAX31855 nie został skopiowany ani zmodyfikowany.

ESPHome host + addrspi +8 MAX31855: compile/runtime PASS przez model STM
PTY oraz realny LiteX RemoteServer localhost z modelem Kasli. Osiem adresów,
ujemne/dodatnie temperatury,32bit, puste CS, zachowanie innych GPIO i NaN
po utracie transportu PASS. `tools/test_all.py` i dotychczasowy demonstrator
MAX31865/LM75B PASS. Wszystkie temperatury syntetyczne, brak HIL.

To nadal hostowy adapter SCG1, nie natywny runtime STM/Kasli ani sprzętowy
SPI FPGA. Sprzętowe górne linie STM slotów1..6 odrzucone do integracji
ABI4/595. Kierunki fizyczne wymagają sprawdzonego profilu. addrspi2 zachowuje
wymaganie hardware SPI i nie jest objęty tym demonstratorem. Kolejny krok:
adapter lokalnego mastera SPI pod tym samym API, integracja kierunków i HIL
rzeczywistej karty. Szczegóły: [ESPHOME_GPIO_SPI](docs/ESPHOME_GPIO_SPI.md).

## Eksport publiczny — 2026-10-18

Pełny lokalny `tools/test_all.py` PASS. Czysty eksport Git bez lokalnego
work/ ani references/:58 testów Python/native C++/Migen PASS,1 pominięty
(porównanie z niepobranym ARTIQ); zewnętrzne zależności Migen/LiteX dostarczono
przez PYTHONPATH. Naprawiono tworzenie work/tmp przez test flasha na nowym
checkoucie. Log: evidence/publication-clean-checkout.log. Bez HIL.

## SCF5 — walidacja programowa, 2026-10-18

Testy obejmują rzeczywisty RTL Migen: cztery tryby SPI, ciągłość bajtów,
pełne ramki, sesje CS, watchdog, niepełne dane, błędy Wishbone, FIFO RX,
adresowanie i impuls, interlock i wspólną barierę triggera. Dwie instancje
RTL wykonują równolegle ten sam batch ośmiu slotów i porównują wyniki.

`evidence/scf5-esphome-tests.json`: rzeczywisty ESPHome host, stock
MAX31855, osiem syntetycznych wartości od -40.25 do750°C, oba transporty
(STM PTY/protokół32bit i Kasli LiteX TCP), rzeczywisty RTL. Oba PASS,
łącznie z NaN po interlocku innego slotu. To nie były pomiary temperatury.

Wygenerowano HDL SoC Kasli SMP4 z nowym slave Wishbone; synteza logiczna
rdzenia ECP5/XC7 oraz kompilacje obiektów klienta C++ RV32 i ARM przeszły.
Brak linkowania nowych kompletnych firmware, nowego P&R i HIL. Logi
syntezy/kompilacji opisują konkretny przebieg, nie walidację sprzętową.
Aktualne wyniki pełnego pakietu: evidence/test-results.json.

Pełny pakiet końcowy:74 testy Pythona PASS, oba zestawy Rust PASS,
reference identity i cross-language wire PASS. Rerun fixture ESPHome
wykrył losowe opóźnienie pierwszego pollingu przy obciążeniu syntezą;
fixture wymusza teraz deterministyczny pierwszy odczyt ośmiu komponentów.
Wyjaśnienie: evidence/scf5-cosim-rerun-note.txt.

## Regresja QSPI — 2026-10-20

`test_fault_discards_burst_and_new_cs_recovers` w rzeczywistej symulacji
Migen sprawdza ERR i timeout Wishbone, odrzucenie kolejnego słowa w tej
samej ramce, brak zapisu niepełnego słowa i odzyskanie po clear/new CS.
SCK ma osiem cykli sys na półokres (16:1). Bez zmian RTL, bez HIL.
Pełny wynik ponownego przebiegu: evidence/test-results.json.

Pełny przebieg wznowienia:75 testów Pythona PASS, testy obu bibliotek Rust,
identity źródeł i test protokołu Python–Rust PASS.
