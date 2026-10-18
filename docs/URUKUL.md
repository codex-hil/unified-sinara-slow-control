# Urukul CPLD8 na STM/Kasli

Profil `urukul_eem0` opisuje linie logiczne po stronie modułu, wspólne dla
obu kontrolerów. Nie jest mapą package-pin FPGA ani potwierdzeniem adaptera
DIOT–EEM. Włączany przy elaboracji; nie zmienia runtime adresów CSR/ABI4.

| Funkcja | Para EEM0 / linia logiczna |
|---|---|
| SCK | 0 |
| MOSI | 1 |
| MISO (wejście kontrolera) | 2 |
| CS adres bit0, bit1, bit2 | 3, 4, 5 |
| IO_UPDATE | 6, pozostawiona GPIO |
| DDS_RESET/SYNC_IN | 7, pozostawiona GPIO |

Domyślny mux miał SPI na liniach0..3: tylko jeden bit CS. Urukul potrzebuje
trzech bitów adresu: 0=idle,1=CFG/status,2=tłumiki,3=DDS multi,
4..7=DDS kanałów0..3. CS są aktywne wysoko; to binarny adres CPLD,
nie one-hot ani trzy niezależne CS aktywne nisko. SPI mode0, MSB-first.
Test adresu4 sprawdza trzeci przewód; nie implementuje sterownika DDS.

Źródła przypięte w `evidence/source-commits.json`:

- [ARTIQ eem.py, Urukul.io](https://github.com/m-labs/artiq/blob/7d7b85f377e0c172ae3496f0c03cfb6cb85ba022/artiq/gateware/eem.py): mapa EEM0.
- [ARTIQ urukul.py](https://github.com/m-labs/artiq/blob/7d7b85f377e0c172ae3496f0c03cfb6cb85ba022/artiq/coredevice/urukul.py): SPI_CONFIG, adresy CS, protokół i tłumiki.
- [Sinara HW Urukul](https://github.com/sinara-hw/Urukul/tree/26aa02a0b66ebe02d6381ad023455da1e4391f4c), schemat release
  v1.5.6 AD9910: `evidence/urukul-schematic.txt`; URL/SHA256 PDF w
  `evidence/pdf-sources.json`. Schemat opisuje połączenia EEM z CPLD;
  firmware CPLD/protokół musi pasować do rzeczywistego modułu.

## Użycie

`SlotPinMux(spi_interface, mapping="urukul_eem0")` wybiera wszystkie sześć
linii. W izolowanym generatorze pełnego STM:

```python
namespace(slot_mappings={0: "urukul_eem0"})
logical(serial=False, slot_mappings={0: "urukul_eem0"})  # logiczny Kasli
```

Klucze to sloty0..7; inne sloty zachowują domyślny mux. Dla innego adaptera
można przekazać jawny słownik clk/mosi/miso/cs. Nazwany profil wymaga pakietu
`sinara_slow` na PYTHONPATH (np. `PYTHONPATH=src:...`). Fizyczne kierunki,
translatory i pady nadal wymagają zgodnego profilu PCB. Żadnych zmian upstream.

Host YAML binding może deklarować `pinmux: urukul_eem0` razem z
`clk: 0`, `mosi: 1`, `miso: 2`, `cs: [3,4,5]`. Walidator odrzuca inne
przypisanie i odwróconą kolejność CS. Przykłady obu kontrolerów używają teraz
tej mapy modułu; adresy CSR/połączenia pozostają symulacyjne. Deklaracja YAML
nie przestawia już zbudowanego FPGA. Host GPIO backend nadal korzysta z
sinara-gpio-v1, a test mastera z ABI4: nie są wzajemnie zamiennymi transportami.

Zakres sterownika pozostaje: rozpoznanie CPLD8, RF OFF, cztery tłumiki
0..31.5dB w krokach0.5dB, readback z przywróceniem łańcucha. Status zapisuje
CFG; readback tłumików jest inwazyjny. Brak DDS init/frequency/PLL,
CPLD9 i nowego runtime ESPHome. Istniejący model sinara_bus ESPHome obsługuje
MAX31865 i nie może służyć jako model Urukula.

Przed fizycznym użyciem mastera trzeba zapewnić idle CS=000 przy
przełączeniu offline→SPI. Upstream SPIInterface resetuje CS na jedynki;
samo ustawienie cs_polarity nie aktualizuje rejestrowanych wyjść bez ce.
Test funkcjonalny nie dowodzi bezglitchowego startu ani przełączenia muxa.
Nie powstał gotowy obraz ani procedura uruchomienia Urukula na sprzęcie.

## Sprawdzenie offline

```sh
python3 tools/test_all.py
PYTHONPATH=src:work/upstream-stm/deps/migen:work/upstream-stm/deps/misoc:work/upstream-stm/deps/litex:/usr/lib/python3/dist-packages /home/codex-hil/vector-analyser/.venv/bin/python tools/test_urukul_pinmux.py
```

Drugi test używa rzeczywistych CSR/mastera MiSoC i pinmuxa: kompletne
24/32-bitowe transfery z segmentów8bit, CS1/2/4, powrót CS do000,
MOSI/MISO/OE, brak zajęcia IO_UPDATE/reset i powrót do GPIO. Wariant STM
ma automat595, Kasli bezpośrednie kierunki. Elaboruje też pełny target STM
ze zmienionym tylko slotem0. Dowód: `evidence/urukul-pinmux-tests.json`.
Bez syntezy/P&R/HIL tego wariantu; wcześniejsze obrazy HIL bez zmian.
