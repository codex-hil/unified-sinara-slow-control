# Kolejne etapy

1. Ustalić egzemplarz/rewizję STM PCB i Urukul CPLD oraz schemat adaptera DIOT–EEM.
   Zestawić netlistę PCB z PDF, poprawić rozbieżności pinów/clock/slotów i kierunki
   LVDS na izolowanej gałęzi. Nie programować zgadywanego pinoutu.
2. Zintegrować Rust gateway z RTIC, bounded HAL QSPI, framing UART i blokadą bus.
   `compatible()` ma sprawdzać konkretny nowy build/ABI, nie tylko 0xaaaa/0x5555.
   Potwierdzić CSR map i nagłówek 1+15 bitów; symulować wszystkie osiem slotów.
3. Przygotować Kasli bare-metal target, reuse platform/CRG/MiniSoC/PHY z MiSoC;
   podłączyć SlowGPIO do właściwych EEM IBUFDS/OBUFDS, power/fault i CSR bridge.
   Wykonać elaborację, syntezę i P&R bez dostępu do JTAG.
4. Przenieść pełne transakcje SPI z host bit-bangingu na oba kontrolery.
   Dodać lokalnie zatwierdzony plan konfiguracji, status, watchdog i boot safe-state.
   Utrzymać wspólną semantykę i wersjonowanie API; nie parsować YAML na MCU.
5. Zoptymalizować istniejący readback tłumików tak, aby utrzymywał CS między
   shift i re-latch; dodać test zgodności golden vectors z upstream i init DDS/AD9910 dla znanego clock/PLL.
   Dopiero wtedy schema frequency i RF enable. CPLD9 jako osobna wersja definicji.
6. HIL, po zgodzie: passive continuity, read identity, scope SPI/polarity, RF-off,
   attenuation readback i pomiar; timeout/disconnect/reset/recovery obu kontrolerów.
   Ten sam YAML, dwa osobne zatwierdzone profile; zbierać surowe logi i rewizje.
7. Rozszerzyć API read/write/discover/telemetry; następne moduły z udokumentowanymi
   sterownikami. Dopiero po zgodności Kasli–STM adapter ESPHome/MQTT dla MODULIQ.

Kryterium zakończenia software MVP: oba kompletne obrazy/serwisy wykonują operacje,
readback jest zgodny z modelem, testy end-to-end obejmują rzeczywiste parsery
firmware i bounded transport. Kryterium hardware MVP: dwa kontrolery wykonują
identyczny YAML na prawdziwym Urukul, obejmując readback i bezpieczne odzyskanie
po błędach; dowody zapisane z wersjami hardware/firmware/gateware.

Po odtworzeniu STM baseline wydzielić jeden rdzeń firmware Rust no_std,
budowany dla obu CPU. Sterowniki Sinara i sekwencje konfiguracji mają być
wspólne; specyficzne pozostają adaptery endpointów QSPI/MMIO, HAL i startup.
Najpierw sprawdzić cross-build i link wspólnego rdzenia dla obu platform.

2026-10-11: baseline v1.1 build i symulacje GPIO/IRQ/SPI2WB wykonane.
Wtorek: identyfikacja podłączonej płytki/programatorów/obsady, bezpieczny
bring-up i pomiary. Przed uruchomieniem zbadać startup write0 i inicjalizację
modułów upstream. Pełne QSPI dopiero po potwierdzeniu x1 na sprzęcie.

ESPHome: PoC x86 host PASS. Dalej: uzgodnić kontrakt adresowanego SPI
z osobnego wątku, zapewnić C++20/libstdc++ dla Kasli Linux, zbudować wariant
transportu bez modeli i mechanizm błędów, zintegrować prawdziwy most I2C
przez SPI, potem HIL i decyzja o natywnym ESPHome na STM.

Pinmux: zintegrować wspólny SlotController z CSR/padami Kasli, dodać profile rewizji i walidację map SPI/GPIO w YAML, sekwencję bezpiecznego przełączania oraz testy HIL kierunków/CS. Nie zmieniać mostu QSPI przy samym przenoszeniu muxa.

Automat kierunków STM/Kasli i CSR są zaimplementowane oraz symulowane; integracja banku/padów/arbitrażu i testy elektryczne pozostają otwarte. [Stan i ograniczenia](docs/PINMUX.md).

Następny etap HIL: identyfikacja PCB/kabli/mapy, baseline ABI3 + read-only probe, następnie zatwierdzony ABI4 i pomiar 595/OE z pasywnym fixture. Offline bank/arbitraż/strict build już wykonane. Pozostałe prace: interaktywny transport CSR, Kasli SoC/EEM, profile rewizji + YAML validation, SPI/GPIO map atomicity, bezglitchowy turnaround oraz pełny QSPI x4. Nie zastępować istniejącego MODULIQ/ESPHome ani łączyć slow control z RTIO.

Flash: HIL read-ID/backup przez STM SPI1, potwierdzenie przejęcia 4066/PROGRAM_N/DONE i UART, następnie zatwierdzony zapis/weryfikacja/boot oraz odtworzenie backupu programatorem. Sprawdzić standardowy JTAG i jego skip-reset na rzeczywistym kablu. Dalej włączenie serwisu do docelowego runtime/ESPHome, dynamiczne zabezpieczenie wyjść na czas maintenance i ewentualny golden/dual-image. Nie zakładać atomowości aktualizacji single-image.

## Pokrycie modułów i współrzędne GPIO — 2026-10-17

- Wspólny format par slot/line wdrożony dla ESPHome Sampler/Zotino.
- Zastosować ten sam format w adapterach ESPHome Urukul i Matrix32_2.
- Potwierdzić konkretny wariant Matrix32_2 i jego mapę z dyskusji/schematu;
  obecny checkout nie zawiera jego drivera. Nie zakładać zgodności z inną
  płytą o podobnej nazwie.
- Dokończyć audyt wszystkich funkcji SPI/GPIO, w tym drugi SPI Samplera,
  CNV, LDAC/CLR/BUSY Zotino i adresowane CS/IO_UPDATE Urukul.
- Przed sprzętem przygotować zgodne profile kierunków STM oraz arbitraż
  lokalnej sekwencji impuls+wait+SPI z aktualizacją kierunków.

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

## Następne kroki SCF5

1. Zweryfikować i przypiąć fizyczne mapy Kasli-DIOT oraz STM v1.1.
2. Podłączyć klient C++ do natywnych BSP: STM HAL i Kasli bare-metal,
   dodać runtime/platformę ESPHome, dopiero potem obrazy do HIL.
3. Rozwiązać drugą magistralę Sampler ADC/PGIA bez naruszania pinmuxu.
4. Loopback, kierunki595, tryby SPI i adresowanie na prawdziwym MAX31855.
5. Dwie identycznie obsadzone kasety i równoległy test porównawczy,
   zgodnie z docs/DUAL_CRATE_HIL.md; następnie triggery/interlock z pomiarami.
