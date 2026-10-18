# Zotino — wspólny driver STM/Kasli

Sterownik korzysta z ustaleń zapisanych w [SAMPLER](SAMPLER.md) i
[URUKUL](URUKUL.md): wspólny przenośny rdzeń C++17, istniejące endpointy
rejestrowe SCG1/STM i LiteX/Kasli, bez RTIO i nowego protokołu FPGA.
Zapisane wyniki sąsiednich wątków: Sampler ma osiem kanałów ADC/PGIA,
ESPHome host, testy modeli/PTY/TCP i generację HDL; Urukul ma CPLD8,
tłumiki i RF OFF, bez sterownika DDS. Żaden nie ma potwierdzenia HIL.

## Źródła i mapa

Wykorzystano przypięte źródła `references/artiq/artiq/coredevice/zotino.py`,
`ad53xx.py` i `artiq/gateware/eem.py`. Commit ARTIQ zapisano w
`evidence/source-commits.json`:
[Zotino](https://github.com/m-labs/artiq/blob/7d7b85f377e0c172ae3496f0c03cfb6cb85ba022/artiq/coredevice/zotino.py),
[AD53xx](https://github.com/m-labs/artiq/blob/7d7b85f377e0c172ae3496f0c03cfb6cb85ba022/artiq/coredevice/ad53xx.py).

| Para EEM | Funkcja | Kierunek kontrolera |
|---|---|---|
| 0 | CLK | wyjście |
| 1 | MOSI | wyjście |
| 2 | MISO | wejście |
| 3 | SYNC_N DAC | wyjście |
| 4 | CS_N LED | wyjście |
| 5 | LDAC_N | wyjście |
| 6 | BUSY | wejście |
| 7 | CLR_N | wyjście |

Oba CS są niezależne i aktywne nisko. DAC:24bit MSB-first SPI mode1;
LED:8bit mode0. To inny protokół CS niż binarny adres Urukula.
Przypisanie funkcji w YAML to GPIO, nie dynamiczny crossbar FPGA.
Mapę i kierunki fizycznego adaptera/padów trzeba osobno zweryfikować.

## API

`integrations/esphome/components/sinara_gpio_endpoint/zotino_core.h` zawiera
`sinara::Zotino`, niezależny od ESPHome. Korzysta z istniejącego interfejsu
`SamplerRegisters` (read/write/acquire/release/delay), bez zależności od ADC.
`stm_zotino_route` wybiera słowa `slot*20+0/1/2` (slot0..7),
`kasli_zotino_route` wymaga jawnych wyrównanych adresów bajtowych CSR.

- `initialize()`: wyłącza OE zajętych linii, ustawia idle, włącza wyjścia,
  programuje OFS0/OFS1=8192, czyta CONTROL, odrzuca brak DAC/overtemperature,
  włącza ochronę termiczną i sprawdza CONTROL. CLR i LDAC pozostają wysoko.
- `set_dac_mu(channels,values,count)`:1..32 różnych kanałów0..31, dane16bit,
  wspólny lock, pełny zapis wektora,2us oczekiwania i1us LDAC low.
- `set_voltage(channel,voltage)`: domyślne5V reference i OFS=8192,
  zakres -10V do 10V-20V/65536. NaN/Inf/poza zakresem odrzucane przed I/O.
  `voltage_to_mu` używa zaokrąglenia ties-to-even jak Python w ARTIQ.
- `read_dac_mu`: dwie ramki mode1, komenda READ X1A i NOP;
  wynik jest odczytem rejestru wejściowego, nie pomiarem napięcia analogowego.
- `set_leds`: osiem LED przez osobny CS, bez impulsu LDAC.

Zachowuje nieużywane bity GPIO/OE. BUSY ma kierunek wejściowy;
sterownik używa konserwatywnego opóźnienia2us zamiast odpytywania BUSY,
jak ograniczenie1.5us opisane w ARTIQ. Brak gwarancji szybkości/timingu RTIO.

Błąd I/O zatrzymuje driver, bez automatycznego replay. Lock obejmuje całą
operację. Niepełny read nie nadpisuje wyniku. Cleanup jedynie próbuje idle;
błąd po możliwym zapisie/LDAC oznacza nieznany stan wyjść. Brak rollbacku
analogowego, watchdogu i gwarancji zerowania po utracie hosta. Inicjalizacja
nie zeruje32 kanałów, nie resetuje gain/offset kanałów i nie kasuje wcześniej
zapisanych danych. Ponowne uruchomienie wymaga świadomego pełnego
przywrócenia stanu, zanim LDAC zatwierdzi także wcześniejsze rejestry.
Przeliczenie zakłada nominalną referencję i domyślne trimy; nie jest kalibracją.

## ESPHome

`sinara_zotino` używa wyłącznie jednego endpointu na hub; walidacja odrzuca
współdzielenie także z Samplerem. Pinmux i możliwości elektryczne sprawdzane
są przed połączeniem. Standardowy `output: platform: sinara_zotino` wybiera
kanał0..31. Poziom0..1 mapuje się na cały zakres bipolarny:0 oznacza -10V,
1 oznacza dodatnie full scale. Do napięcia w woltach służy C++
`id(zotino0).set_voltage(0,1.25)`; `set_leds(0xa5)` steruje LED.
Nie skonfigurowano automatycznego zapisu napięć podczas setup.

Przykłady: `integrations/esphome/examples/zotino-{stm,kasli}-simulation.yaml`.
Są syntetyczne i nie otwierają portów. Hardware transport pozostaje ESPHome
POSIX/host: STM UART115200 lub LiteX TCP, z ABI SCG1, deadline i lockiem
płyty. Nie jest to natywny runtime na STM32 ani CPU Kasli. STM gateway
RTIC/HAL i odpowiednie kierunki LVDS/translatorów wymagają dalszej integracji.
ABI4/upstream STM nie stają się zgodne ze SCG1 przez sam wybór YAML.

Kasli `--pin-profile zotino_eem0` opisuje6 OBUFDS i2 IBUFDS. Generator
`tools/generate_zotino_kasli.py` używa syntetycznego EEM0, bez przeglądu
fizycznej mapy, syntezy/P&R ani bitstreamu. Nie zmieniono zamrożonych obrazów.

## Weryfikacja offline

```sh
python3 tools/test_all.py
# W środowisku ESPHome2026.9.0 (esphome na PATH):
python tools/test_zotino_esphome.py
PYTHONPATH=src python tools/generate_zotino_kasli.py
```

Native C++ test sprawdza dokładne ramki kanałów0/31, odczyt, mode LED,
LDAC, OE i zachowanie obcych bitów, STM slot0/7 oraz adresy Kasli, brak
urządzenia i błąd każdego kroku init/write/read. ESPHome test kompiluje i
uruchamia oba przykłady oraz endpointy przez PTY i prawdziwy LiteX server
na localhost, sprawdza dane modelu i zatrzymanie po błędzie transportu.
Negatywne YAML: kierunki, overlap, współdzielenie, zakres kanałów i brak
przeglądu profilu sprzętowego. Wszystkie dane są syntetyczne; nie wykonano
pomiarów analogowych, fizycznych zapisów DAC ani HIL.
Dowody: `evidence/zotino-*.log`, `evidence/zotino-esphome-tests.json`,
`evidence/zotino-kasli-elaboration.json` i testy regresji projektu.

## Współrzędne GPIO w YAML — 2026-10-17

Każda funkcja w `pinmux` wymaga jawnej pary, np.
`cnv: {slot: 1, line: 3}` (Sampler) lub
`ldac_n: {slot: 1, line: 5}` (Zotino).
`slot` ma numerację1..8 zgodną z modułami hosta; `line` ma zakres0..15.
Nie jest to numer pinu obudowy FPGA. Na obu platformach publiczny slot1 odpowiada wewnętrznemu indeksowi0.
Para musi wskazywać slot wybranego endpointu; routing między slotami nie
jest zaimplementowany i walidator go odrzuca. Sprawdzane są także duplikaty
oraz możliwości elektryczne. Po walidacji driver otrzymuje lokalny numer
linii; transport i adresy CSR pozostają w profilu endpointu.
Stary zapis samym numerem linii został zastąpiony jawną parą.

Test powtarzalny: uruchom `tools/test_gpio_references.py` interpreterem
z zainstalowanym ESPHome. Cztery poprawne konfiguracje i16 negatywnych
przypadków walidacji PASS; bez testów sprzętowych.
