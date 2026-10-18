# Unified Sinara Slow Control

Projekt na drugim dysku: `/srv/codex-hil-data/unified-sinara-slow-control`.
Stan: **częściowy demonstrator programowy, nie ukończone MVP sprzętowe**.

Wspólny YAML urządzeń jest walidowany i kompilowany na hoście Python 3.
Ten sam przykład Urukul wykonuje identyczne operacje przez adaptery STM i Kasli
w jawnej symulacji GPIO/SPI. Dostępne są rzeczywiste implementacje transportów
UART oraz LiteX RemoteClient, ale wymagane obrazy kontrolerów nie są jeszcze
zintegrowane ani sprawdzone na sprzęcie. Nie ma automatycznego przejścia na mock.

Zakres pierwszego fragmentu: Urukul CPLD protocol 8, wyłączenie RF, status CPLD
oraz zapis/odczyt czterech tłumików 0..31.5 dB w krokach 0.5 dB. Nie konfiguruje DDS, częstotliwości,
PLL ani deterministycznego RTIO. `enabled: true`, frequency i nieznane pola
są odrzucane. Przykład opisuje prawdziwy typ modułu, ale nie jest deklaracją
posiadania lub testowania egzemplarza.

Upstream STM v1.1 odtworzono offline: firmware Rust 1.88 i gateware ECP5
(strict P&R seed 3, 100.30 MHz). Bez HIL; obrazy upstream nie implementują
wspólnego API. Procedura: [STM_RECOVERY.md](docs/STM_RECOVERY.md).

Próba nowego kierunku ESPHome: [działający demonstrator host](integrations/esphome/README.md)
z oryginalnymi MAX31865/LM75B i jawnie symulowanymi magistralami.

## Publiczny checkout

```sh
git clone https://github.com/codex-hil/unified-sinara-slow-control.git
cd unified-sinara-slow-control
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
sinara-slow simulate examples/urukul.yaml --connection examples/stm.simulation.yaml
```

Do pełnych lokalnych testów i audytu pobierz przypięte źródła/PDF przez
`python tools/fetch_references.py`, a następnie uruchom
`python tools/test_all.py`. Testy symulacyjne FPGA wymagają Migen/LiteX
(zależności w `pyproject.toml` i rewizje w `evidence/source-commits.json`).
CI sprawdza rdzeń bez dostępu do sprzętu; porównanie z ARTIQ jest pomijane,
jeśli jego checkout nie został pobrany. Procedury ESPHome oraz narzędzia
FPGA mają dodatkowe zależności opisane w dokumentacji.

Nowy kod projektu: MIT; runtime i adaptacje ESPHome: GPLv3.
Zobacz [licencje i pochodzenie](THIRD_PARTY_NOTICES.md).
Repozytorium zawiera kod, przykłady, testy i raporty. Pobrane schematy,
zewnętrzne checkouty, cache i wygenerowane obrazy odtwarza się lokalnie.
Ścieżki `/srv/codex-hil-data/...` w starszych raportach są historycznymi
ścieżkami laboratorium; `build_path` przykładów należy dostosować na innym hoście.

## Uruchomienie

Na tym hoście PyYAML i jsonschema są dostępne systemowo. Środowisko bez
ensurepip można utworzyć tak:

```sh
cd /srv/codex-hil-data/unified-sinara-slow-control
python3 -m venv --without-pip --system-site-packages .venv
export PYTHONPATH="$PWD/src"
.venv/bin/python -m sinara_slow.cli validate examples/urukul.yaml
.venv/bin/python -m sinara_slow.cli compile examples/urukul.yaml
.venv/bin/python -m sinara_slow.cli simulate examples/urukul.yaml --connection examples/stm.simulation.yaml
.venv/bin/python -m sinara_slow.cli simulate examples/urukul.yaml --connection examples/kasli.simulation.yaml
python3 tools/test_all.py
```

Na innym hoście z pip: `python3 -m pip install -e .`; transport UART wymaga
`.[serial]`, Kasli wymaga LiteX. Zależności hosta są zadeklarowane w pyproject.toml.
Biblioteka gateway Rust nie ma zależności zewnętrznych.
`python3 tools/fetch_references.py` odtwarza przypięte źródła i weryfikuje PDF;
nie nadpisuje istniejących checkoutów o innym commicie.

**Profile `*.simulation.yaml` zawierają fikcyjne przypisania pinów i adresów
CSR i służą wyłącznie do testów.** Nie są profilami okablowania laboratorium.
`configure`, `reset` i `status` mogą pisać do sprzętu; status Urukul jest
odczytywany równocześnie z zapisem CFG=0. Użycie wymaga wyłącznego przejęcia
modułu, sprawdzonej rewizji/pinów oraz zgody na operacje sprzętowe.

## Zawartość

- `src/sinara_slow`: walidacja, definicje protokołu, API, adaptery i transporty.
- `schemas`: eksport JSON Schema; kanoniczne kopie w pakiecie.
- `firmware/stm-service`: kompilowalna bramka Rust no_std, **bez integracji RTIC/HAL**.
- `gateware/gpio.py`: blok Migen/LiteX GPIO + ABI i target Kasli UARTbone bez CPU.
  Generacja HDL/synteza/P&R przeszły; brak firmware i walidacji sprzętowej.
- `references`: izolowane klony upstream, pomijane przez Git.
- `evidence`: commity, schematy PDF/tekst, wyniki i analizowane gałęzie.
- `docs/AUDIT_STM.md`, `docs/AUDIT_KASLI.md`: audyty źródeł i sprzętu.

Dalsze warunki wdrożenia i ograniczenia: STATUS.md, HARDWARE_SUPPORT.md,
ARCHITECTURE.md, TEST_RESULTS.md i ROADMAP.md. Nie wgrywano FPGA, flash ani
firmware i nie łączono się z kontrolerami laboratorium.

Wspólny pinmux SPI/GPIO wydzielony z upstream ECP5: [opis i testy](docs/PINMUX.md). Elaboracja STM i logicznego slotu Kasli PASS; integracja fizyczna pozostaje do wykonania.

Automat kierunków STM/Kasli i CSR są zaimplementowane oraz symulowane; integracja banku/padów/arbitrażu i testy elektryczne pozostają otwarte. [Stan i ograniczenia](docs/PINMUX.md).

Aktualny kandydat ABI4 integruje kierunki 595 i OE z bankiem CSR. Strict build STM100MHz oraz logiczny fabric Kasli62.5MHz PASS. Zbudowano read-only RTT probe STM i przygotowano [procedurę HIL](docs/HIL_START.md). `python3 tools/prepare_hil.py` weryfikuje SHA-256 i zamraża obrazy w `work/hil-kit/2026-10-14`; niczego nie programuje. Hardware MVP nadal niezweryfikowany.

Zapisany RTT probe można sprawdzić offline przez `python3 tools/check_hil_capture.py capture.txt --expected-abi 3`; walidacja logu nie jest potwierdzeniem tożsamości sprzętu. [HIL_START](docs/HIL_START.md).

Profil modułu Urukul i trzybitowy CS w mux STM/Kasli: [URUKUL](docs/URUKUL.md).

Programowanie flash FPGA: [YAML, API i standardowe programatory](docs/FPGA_FLASH.md). Dodano host API/CLI, STM serprog przez dedykowane SPI1 oraz adaptery flashrom/openFPGALoader JTAG. Przykłady: examples/fpga-flash.yaml i flash-stm-{spi,jtag}.yaml. Wykonanie nie jest częścią configure modułów. Firmware serwisowy zbudowany, bez instalacji i HIL.

Sampler: wspólny driver C++ GPIO/SPI, endpoint ESPHome dla STM gateway i LiteX/Kasli oraz osiem sensorów: [SAMPLER](docs/SAMPLER.md). Testy programowe/modelowe PASS; brak HIL i natywnego portu runtime STM/Kasli.

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

## Wspólny fabric FPGA SCF5

Nowy rdzeń Migen współdzieli kolejki SPI, pinmux, triggery i interlock między
ECP5 a Kasli. STM ma mostek QSPI–Wishbone, Kasli korzysta z Wishbone CPU.
Opis ABI, przykłady ESPHome i ograniczenia: [docs/SCF5.md](docs/SCF5.md).
Test dwóch równoległych instancji RTL: `python3 -m unittest discover -s tests -p test_dual_fabric.py -v`.
To implementacja i symulacja programowa; natywny runtime ESPHome oraz HIL obu
kontrolerów pozostają do wykonania.
