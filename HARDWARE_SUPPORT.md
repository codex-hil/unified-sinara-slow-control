# Obsługa sprzętu

**Żaden zestaw kontroler + moduł nie ma walidacji fizycznej w tym projekcie.**
Mock/symulacja nie jest dowodem zgodności sprzętowej.

| Zestaw | Implementacja projektu | Testy | Pozostały warunek |
|---|---|---|---|
| STM Sys Board + Urukul CPLD8 | adapter host GPIO/SPI, transport serial, Rust gateway core | symulacja i Rust host | RTIC/HAL, zgodne ECP5, rewizja PCB, DIOT–EEM |
| Kasli + Urukul CPLD8 | adapter host GPIO/SPI, LiteX transport, target UARTbone + Migen GPIO CSR/LVDS | symulacja, generacja HDL, synteza/P&R | właściwy pinout/power, firmware/autonomia i HIL |
| Urukul CPLD9 | niezaimplementowany | walidator odrzuca | osobna logika CPLD9 |
| Urukul AD9910/AD9912 frequency | niezaimplementowane | walidator odrzuca | pełny init, PLL, IO_UPDATE i readback |
| inne Sinara | audyt istniejących sterowników | brak implementacji | osobne definicje i HIL |
| MODULIQ ESPHome | możliwość wspólnego modelu/API opisana | brak | konkretne konfiguracje i adapter hostowy |

Upstream STM main/debug nie jest spójnym zestawem wire/register map. Gateware
tpr_devel poprawia wire width, ale pinout nadal różni się od PDF v1.0/v1.1.
Dodatkowo jego SlotController ma stałe kierunki części LVDS dla SiLPA.
Bramka tego projektu nie uruchamia się na upstream bez zmian integracyjnych.

Wszystkie przykładowe profile połączeń są **syntetyczne i wyłącznie symulacyjne**.
Hardware profile musi zawierać mapę CSR z konkretnego builda oraz sprawdzony
schemat adaptera i kierunki I/O. Wgrywanie i przejęcie modułów wymaga zgody.
Nie ma aktualnie podstaw do wskazania konkretnego dostępnego STM lub Urukul.
Stan Kasli z innych projektów hosta nie stanowi testu tego slow control.

Wyjścia RF pozostają żądane OFF w całym zakresie demonstratora. Zatrzask ostatniej
wartości nie daje gwarancji safety po utracie hosta, resecie kontrolera czy zaniku
zasilania. Autonomiczny watchdog/safe-state wymaga dalszej implementacji i HIL.

## STM: wybrana rewizja

Celem baseline jest v1.1, potwierdzona przez użytkownika. Release
v1.1rc1 / v1.1_production: 6ef210dac91309d9d0770367e12a72a3db93f7f6.
V1.0 wyłączona z powodu zgłoszonych błędów ECP5; wariant v1.2 z opcją ESP32
ignorowany. Firmware ELF i gateware BIT/SVF zbudowano offline, bez HIL.
Niezgodność nazw sieci PDF i gateware wymaga uwzględnienia pin swapping
i multichannel aliases; nie jest podstawą do uznania v1.1 za wadliwą.

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

Pinmux STM/Kasli: współdzielony rdzeń logiczny i Artix-7 HDL generation PASS. Nie oznacza obsługi fizycznych slotów Kasli. Emulowane LVDS STM ma stałe kierunki; sloty 7–8 różnią się od 1–6. Mapa musi uwzględniać rewizję i sterowanie translatorami. [Szczegóły](docs/PINMUX.md).

Automat kierunków STM/Kasli i CSR są zaimplementowane oraz symulowane; integracja banku/padów/arbitrażu i testy elektryczne pozostają otwarte. [Stan i ograniczenia](docs/PINMUX.md).

ABI4 jest podłączony w izolowanym pełnym target STM: kierunki translatorów48bit dla slotów1–6 i odpowiadające OE FPGA. STM finalny strict P&R100MHz PASS(seed3, timing-weight20/ripup;106.15MHz), bitstream zbudowany, niezaładowany. Mapę fizyczną odziedziczono z upstream, nie uznano jej za gotową do programowania. Kasli fabric8slotów przeszedł OOC P&R62.5MHz; brak fizycznych EEM i SoC. STM read-only RTT probe zbudowany, nieuruchomiony. [HIL](docs/HIL_START.md).

Flash STM v1.1: dedykowane SPI1 (PG11/PG9/PD7 + GPIO CS PG10), mux PE15, PROGRAM_N PG0 i DONE PE1 zweryfikowane na stronach4/17 PDF. Osobny firmware maintenance cross-build PASS, SPI/UART/4066 i ponowny boot NOT_RUN. JTAG adapter przygotowany, brak HIL. API hosta obsługuje też profile Kasli/external, lecz nie jest to walidacja konfiguracji flash konkretnej Kasli. [Audyt i procedura](docs/FPGA_FLASH.md), evidence/flash-source-audit.json.

## Sampler — sterownik i endpoint ESPHome, 2026-10-17

Wspólny C++ driver obsługuje8 kanałów, PGIA, v2.1/v2.2 i błędy niepełnych
ramek. Adapter ESPHome host rozmawia istniejącym protokołem STM gateway
lub LiteX/Kasli. Kompilacja/runtime/model ADC, PTY i localhost Etherbone
PASS. Dla Kasli dodano generowany profil8 par GPIO/LVDS; HDL PASS.
Wszystkie dane ADC były syntetyczne. Brak HIL, P&R nowego profilu i portu
natywnego runtime STM/Kasli. STM gateway RTIC/HAL oraz fizyczne kierunki
padów pozostają warunkiem użycia sprzętu. [SAMPLER](docs/SAMPLER.md).

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

## SCF5 — stan dodatkowego rdzenia

| Element | Dostępne | Niewykonane |
|---|---|---|
| Wspólny SPI/pinmux/trigger/interlock | RTL i testy rzeczywistej symulacji Migen | fizyczne czasy i zachowanie wyjść |
| STM ECP5 QSPI x4 | mostek Wishbone, symulacja transakcji, synteza logiczna | uzgodniona mapa padów, P&R, HIL |
| Kasli SMP4 | integracja Wishbone w istniejącym SoC, generacja HDL | nowy pełny build i HIL |
| ESPHome MAX31855 | stock driver, osiem adresów, host przez RTL obu wariantów | natywny runtime, realne czujniki |
| Adapter STM32H7 C++ | rzeczywiste API HAL QSPI, kompilacja obiektu ARM | BSP, link, transfery fizyczne |
| Adapter Kasli C++ | MMIO z fence, kompilacja obiektu RV32 | runtime, link, start aplikacji |

Nowy konserwatywny mostek wymaga sys_clk >=16×QSPI_SCK: przy100MHz
maksymalnie6.25MHz. Nie deklaruje100MHz QSPI. Profile logical build ID
nie zastępują audytu fizycznego pinoutu.
