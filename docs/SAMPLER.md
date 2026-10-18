# Sampler — wspólny driver STM/Kasli i ESPHome

Kod z tego wątku znajduje się w istniejącym projekcie Unified Sinara Slow
Control. Nie używa RTIO ani nowego protokołu FPGA.

## Implementacja

- `integrations/esphome/components/sinara_gpio_endpoint/sampler_core.h`:
  przenośny C++17 driver LTC2320-16/PGIA. Wspólny dla STM i Kasli,
  niezależny od ESPHome i systemu operacyjnego.
- `register_protocol.h`: klient istniejącego 16-bajtowego protokołu
  `firmware/stm-service` oraz 32-bitowego Etherbone TCP z LiteX RemoteServer.
  STM: słowa `slot*20+{0,1,2}`; Kasli: jawne adresy bajtowe z CSR map.
- `sinara_gpio_endpoint`: adapter ESPHome host, PTY/UART115200 lub TCP
  LiteX, ograniczony deadline całej operacji, wyłączna blokada kontrolera.
  Obecny transport ESPHome hardware jest POSIX/host. To obsługa kontrolerów
  STM/Kasli przez endpoint, nie natywny runtime ESPHome na tych procesorach.
- `sinara_sampler`: polling hub oraz osiem standardowych sensorów ESPHome.
  Jedna konwersja na cały zestaw, jeden właściciel endpointu.

Istniejący `sinara_bus` pozostaje nienaruszony: jego model SPI dotyczy
MAX31865. Nowy adapter GPIO stosuje istniejące API rejestrowe, ponieważ
MAX31865 delegate nie obsługuje protokołu ani ramek Samplera.

## YAML

Przykłady `integrations/esphome/examples/sampler-{stm,kasli}-simulation.yaml`
przechodzą walidację i kompilację ESPHome2026.9.0. Adresy i możliwości
pinów są syntetyczne. `mode: simulation` nie otwiera UART ani sieci.

YAML wybiera endpoint kontrolera, jego adresy CSR, możliwości elektryczne
oraz przypisuje osiem funkcji Samplera w `pinmux`. Domyślnie są to pary
EEM0 D0..D7: ADC_CLK, ADC_MISO, SDR, CNV, PGIA_CLK, PGIA_MOSI,
PGIA_MISO, PGIA_LATCH. Kierunki: wyjścia0/2/3/4/5/7, wejścia1/6.
`hardware_revision` obsługuje jawnie v2.1 lub v2.2. `gains` zawiera osiem
wartości1/10/100/1000 w kolejności kanałów0..7.

Ten wariant używa wyłącznie funkcji GPIO istniejącego endpointu.
`pinmux` przypisuje funkcje drivera do numerów GPIO i konfiguruje OE;
nie udaje nieistniejącego dynamicznego crossbara FPGA. Sprzęt musi już
wyprowadzać te linie jako GPIO. Sterownik nie przełącza rejestru offline
mastera SPI w niezgodnym gateware ani nie zmienia standardów I/O.

Tryb hardware wymaga zgodnego `sinara-gpio-v1` (SCG1), mapy CSR konkretnego
builda, `electrical_profile_reviewed: true`, możliwości wejścia/wyjścia
oraz `lock_path` wspólnego z innymi narzędziami płyty. STM wymaga
`serial_path`, Kasli `host_address` (numeryczny IPv4), `tcp_port` i
`abi_address`. Nie przygotowano profilu fizycznej płyty; przykłady nie
stanowią zezwolenia na połączenie/programowanie.

Upstream STM endpoint i zintegrowany ABI4 nie są automatycznie zgodne ze
SCG1. Gateway STM nadal wymaga opisanej wcześniej integracji RTIC/HAL.
Domyślny target UARTbone Kasli ma sześć sygnałów Urukul. Dodano profil
`--pin-profile sampler_eem0`: osiem par, sześć OBUFDS i dwa IBUFDS, ze
wspólnymi GPIO CSR. `tools/generate_sampler_kasli.py` wygenerował HDL
Kasli v1.1 dla syntetycznego EEM0; bez P&R i programowania. Przykład
odtworzenia w środowisku z zależnościami gateware:
`PYTHONPATH=src /home/codex-hil/.local/share/esphome/venv-2026.9.0/bin/python tools/generate_sampler_kasli.py`.
Raport: `evidence/sampler-kasli-elaboration.json`. Docelowy build wymaga
przeglądu fizycznych padów i constraints.
Na STM nie wolno traktować OE jako możliwości zmiany stałego wyjścia LVDS
w wejście: standardowy profil SiLPA ma inne kierunki niż Sampler. Potrzebny
jest zweryfikowany build/adapter. To nadal otwarte prace sprzętowe.

## Przebieg i błędy

Driver wykonuje powolne SPI mode0 przez GPIO. PGIA dostaje16 bitów,
MSB-first, dwa bity na kanał; zbocze narastające LATCH zapisuje gainy.
Po zmianie czeka10ms (konserwatywna polityka, nie zmierzony settling).
SDR jest1. CNV ma minimum1us high i1us przerwy po opadającym zboczu,
co przekracza minima30ns/450ns z ARTIQ. Odczyt zawiera128 taktów,
kanały7..0; driver publikuje signed16 w kolejności0..7.

Przeliczenie: `raw * (20.48 dla v2.2 / 20.0 dla v2.1) / 65536 / gain`.
Nie jest to kalibracja offsetu/gainu poszczególnych kanałów.

Hostowe GPIO po UART/TCP jest znacznie wolniejsze od lokalnego SPI.
`update_interval` jest żądaniem pollingu, nie gwarancją częstotliwości.
To rozwiązanie dla slow control, nie akwizycji MHz. Szybszy wariant może
wykorzystać istniejące mastery SPI i lokalną sekwencję FPGA.

Operacja blokuje cały endpoint. Niepełny odczyt nie zmienia wektora
wynikowego w API C++; ESPHome publikuje NaN i zatrzymuje hub po błędzie.
Nie ma automatycznych ponowień po niepewnym zapisie. PGIA gains stają się
znane dopiero po udanym przesunięciu i zatrzaśnięciu; nie są odczytywane
sprzętowo. Kasli zapis GPIO/OE potwierdza przez uporządkowany readback,
bo LiteX nie wysyła odpowiedzi na sam write. Żaden pomiar nie stanowi
dowodu poprawnej konfiguracji elektrycznej ani kalibracji.

## Testy

`python3 tools/test_all.py` obejmuje test przenośnego C++17 drivera:
STM slot0 i7, Kasli adresy bajtowe, extrema/sign/order, oba zakresy
napięciowe, gainy, OE, zachowanie innych pinów, busy i błędy I/O.
Wstrzykiwanie błędu w każdym kroku inicjalizacji/odczytu sprawdza, że
niepełne próbki i nieznane gainy nie są zgłaszane jako poprawne.

`python3 tools/test_sampler_esphome.py` kompiluje i uruchamia prawdziwy
runtime ESPHome host. Obejmuje modele obu kontrolerów, STM przez PTY,
Kasli przez prawdziwy LiteX RemoteServer na127.0.0.1, syntetyczny model
LTC2320/PGIA, błąd w środku ramki i negatywne walidacje YAML.
Wyniki: `evidence/sampler-esphome-tests.json` i logi obok. Loopback używa
realnego kodu transportu, ale wszystkie dane ADC pozostają syntetyczne.
Nie wykonano HIL, cross-build natywnego runtime STM/Kasli ani zapisów FPGA.

Referencje: lokalny ARTIQ `artiq/coredevice/sampler.py`,
`artiq/gateware/eem.py`, audytowany STM service oraz
`references/litex/litex/tools/{litex_client,litex_server}.py`.

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
