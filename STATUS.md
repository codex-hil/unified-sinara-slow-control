# Status — 2026-10-15

**Częściowy demonstrator programowy. Pełne software MVP i hardware MVP nie są
zakończone.** Projekt znajduje się na drugim dysku w
`/srv/codex-hil-data/unified-sinara-slow-control`.


## Aktualny wynik — przygotowanie do HIL

Zintegrowano ABI4: osobny bank kierunków 0x800, automat sześciu 595,
OE górnych linii slotów1–6, blokada zapisów podczas busy oraz sprawdzenie
idle wszystkich masterów SPI. Master MiSoC i SPI2WB pozostają upstream;
SPI4 passthrough zastępuje automat. Stare górne bity OE nie sterują tymi
48 liniami. Sloty7/8 zachowują ograniczenia fizycznych buforów.

Test całej ścieżki QSPI x1–Wishbone–rzeczywisty CSR–595 PASS. Testy
banku/arbitrażu dla STM i bezpośredniego wariantu Kasli PASS.
STM finalny strict synthesis/P&R PASS: 106.15 MHz przy100 MHz, seed3,
timing-weight20 i timing-ripup. SCK/RCLK i OE są rejestrowane.
Kasli logiczny fabric 8 slotów: Vivado OOC synthesis/route PASS,
62.5 MHz, setup8.936 ns/hold0.110 ns, 2012 LUT/2125 FF. Bez integracji fizycznych EEM/SoC.
38 testów Python, 5 Rust i wire tests PASS. Brak HIL.

Zbudowano diagnostyczny firmware `hil_probe`: wyłącznie ID/rev ECP5 x8
przez upstream HAL QSPI, raport RTT, bez init modułów i zapisów CSR.
Oryginalny board setup pozostaje i może blokować; nie uznano go za pasywny.
Klient hosta `Directions` obsługuje ABI4 i nie ponawia apply po timeout.
Nie ma jeszcze wdrożonego transportu hosta ani portu ESPHome na STM/Kasli.

Zamrożone, sprawdzone SHA-256 obrazów: `work/hil-kit/2026-10-14`.
Procedura: [HIL_START](docs/HIL_START.md). Manifest nie zezwala na
programowanie. Aktualna PCB, kable/SWD/JTAG i fizyczna mapa wymagają
przeglądu po podłączeniu. Nie zmieniono żadnej płytki ani repozytorium upstream.

Aktualny kierunek platform użytkownika: wspólne komponenty ESPHome/C++,
zachowane firmware Rust służy do baseline/diagnostyki. Historyczna decyzja
wspólnego rdzenia Rust poniżej została zastąpiona tym kierunkiem.

## Wykonano

Pobrano 11 repozytoriów referencyjnych, zapisano commity/gałęzie, przejrzano kod
STM, MiSoC/Migen Kasli, ARTIQ urządzenia, LiteX i ESPHome. Duże checkouty sprzętu
są sparse. Pobrano release PDF STM v1.0/v1.1 i Urukul, zapisano SHA-256,
zweryfikowano połączenia QSPI na stronach PDF. Audyt jest w docs/AUDIT_*.md.

Zaimplementowano wersjonowany YAML/JSON Schema, walidację semantyczną,
kompilator operacji, definicje Urukul CPLD8, API, backend STM/Kasli, realne
transporty UART i LiteX RemoteClient oraz jawną symulację GPIO/SPI. Odczyt
rejestrów tłumików przywraca chain i configure porównuje wartości. Write obsługuje
walidowany wektor czterech tłumików. Inne funkcje DDS są odrzucane.

Powstał kompilowalny gateway Rust no_std, testowany realnym parserem z hostem
Python. HAL/RTIC/UART/QSPI nie są jeszcze podłączone do fizycznego STM32.
Powstał target Kasli UARTbone bez CPU i RTIO: GPIO/ABI, IBUFDS/OBUFDS;
wygenerowano HDL dla czterech rewizji, wykonano syntezę i P&R v2.1.
Nie wygenerowano bitstreamu ani nie programowano sprzętu.

## Działa i zostało przetestowane

Ten sam examples/urukul.yaml daje identyczne konfiguracje i odczyty rejestrów
przez oba adaptery **w symulacji**. 28 testów Python i 5 Rust PASS, cross-language
wire test 8 slotów PASS; generacja HDL 4 rewizji PASS, synteza/P&R v2.1 PASS.
Wyniki i ograniczenia w TEST_RESULTS.md. Profile przykładowe są syntetyczne;
connect odrzuca use=simulation przed otwarciem prawdziwego transportu.

## Wymaga sprzętu / jest zablokowane

Nie ustalono rewizji fizycznej STM/Kasli/Urukul ani schematu adaptera DIOT–EEM.
Gateware STM main ma za małą szerokość adresu i niezgodny nagłówek względem
firmware debug. tpr_devel poprawia nagłówek, ale oba pinouty różnią się od
release PDF. Nie można bezpiecznie przygotować obrazu dla nieznanej płytki.

Brakuje STM gateway integration, kompletnego Kasli serwisu bare-metal,
lokalnych transakcji SPI, autonomicznej konfiguracji/watchdogu, i HIL.
Target UARTbone jest etapem pośrednim, nie realizacją finalnego wariantu A.
P&R targetu pozostawia config-voltage warning i niepełne zewnętrzne constraints.
Początkowy brak cache i miejsca zatrzymał build upstream firmware;
problem rozwiązano, release build Rust 1.88 PASS (szczegóły poniżej).

## Następne kroki

Ustalić rzeczywiste rewizje i adapter, wybrać zgodny STM source set, przygotować
sprawdzoną mapę pinów, dopracować constraints Kasli i zintegrować lokalny serwis.
Następnie, po zgodzie na sprzęt, wykonać HIL bezpiecznych stanów i readback
na obu kontrolerach z identycznym YAML. Szczegóły w ROADMAP.md.

## Zmiana priorytetu: odtworzenie STM upstream

Najpierw odtwarzamy istniejący kod, zgodnie z najnowszą instrukcją użytkownika.
Przygotowano niezmienione snapshoty tpr_devel gateware / debug firmware w
work/upstream-stm. Sprawdzono historię: pin swapping może wyjaśniać różnice
z PDF; wymaga to identyfikacji rzeczywistej PCB, a nie automatycznego remapowania.
Baseline ma potwierdzony build offline, bez potwierdzenia HIL. QSPI i mux porównano
w docs/STM_RECOVERY.md. Nie wykonano żadnej nowej operacji sprzętowej.

## Wspólny kod kontrolerów

Przyjęto docelowy wspólny rdzeń Rust no_std dla STM i softcore Kasli, z
oddzielnym QSPI/MMIO oraz kodem startowym/HAL. Decyzja w ADR-006; nie jest
to deklaracja wykonanej implementacji ani cross-buildów. Odtworzenie STM
upstream i sprawdzenie HW pozostają pierwszym etapem.

## Odtworzenie upstream STM v1.1 — 2026-10-11

Użytkownik potwierdził v1.1 jako właściwą rewizję; v1.0 z błędami ECP5 i wariant
v1.2/ESP32 są wyłączone z tego etapu. Sprzęt zostanie podłączony we wtorek.
Niezmieniony firmware debug z Cargo.lock zbudowano w release na Rust 1.88.0
dla thumbv7em-none-eabihf; wcześniejszy błąd cache/braku miejsca jest rozwiązany.
Rust 1.99 odrzucił osiem ostrzeżeń binarki przez deny(warnings); nie poprawiano
źródeł, bo wersja upstream 1.88 buduje poprawnie. Biblioteka ma 99 ostrzeżeń.

Niezmieniony tpr_devel elaboruje 163 rejestry. Zależności Migen/MiSoC/LiteX
odtworzono według flake; użyto Python 3.12 i nowszych narzędzi FPGA OSS.
Seed 1 daje 97.31 MHz, seed 2 91.94 MHz, seed 3 100.30 MHz przy constraint
100 MHz: seed 3 przeszedł strict P&R i pakowanie BIT/SVF. Margines jest mały.
100 MHz wynika z istniejącego clk100/10 ns, nie z wymagań API slow control.
To nie dowodzi poprawności timingu I/O ani CDC na sprzęcie.

Symulacja oryginalnego SlotController: 20 CSR, GPIO/OE/input i IRQ/clear PASS.
Regresja projektu: 28 testów Python, 5 Rust i testy protokołu Python/Rust PASS.
Hashe i ograniczenia: evidence/stm-upstream-build-result.json.
Nie wykonano programowania, pomiarów ani testów HIL. Upstream obrazy nie
implementują naszego wspólnego API; ich build nie kończy MVP.

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

## Wspólny pinmux — 2026-10-13

Znaleziono istniejący mux offline SPI/GPIO w ECP5, ze stałymi liniami 0–3. Wydzielono `gateware/pinmux.py`, dodano mapowanie przy budowie i jawne CS. Symulacja PASS; izolowany cały STM elaboruje z 163 CSR, a ten sam SlotController generuje Verilog dla Artix-7 Kasli. 30 testów Python, 5 Rust i testy protokołu PASS. Nie zmieniono upstream. Nie wykonano syntezy ani testu sprzętowego nowego wariantu. Do zrobienia: profile kierunków PCB, CSR/pady Kasli, walidacja YAML i bezpieczne przełączanie. Szczegóły: [PINMUX](docs/PINMUX.md).

## Automat kierunków — 2026-10-13

Dodano wspólny DirectionController i wrapper CSR dla STM (48-bitowy łańcuch 595) oraz Kasli (bez 595). Symulacje storage/shift, snapshot, quiescent i CSR rejection/clear PASS; generacja HDL obu wrapperów PASS. Regresja 32 Python, 5 Rust i protokół PASS. Podłączenie do banku CSR, OE pinmuxa, arbitrażu i fizycznych padów pozostaje do wykonania. Nie ma syntezy/P&R/HIL automatu. Reset nie zeruje sam zewnętrznego storage; brak gwarancji bezglitchowej zmiany kierunków. Szczegóły: [PINMUX](docs/PINMUX.md).

## Wznowienie — 2026-10-14

Bez działań HW. Dodano offline walidator capture RTT `hil_probe`: wymaga
jednego pełnego uruchomienia,24 poprawnych odczytów w8 rundach, zgodnego
ABI oraz końcowych markerów. Odrzuca uszkodzone wartości mimo PASS,
brakujące/powtórzone odczyty, restart, błędy i ucięty log. Nie przypisuje
pochodzenia capture ani tożsamości PCB i nie oznacza wyniku jako HIL.
43 testy Python,5 Rust i wire tests PASS. CLI synthetic valid/corrupt PASS.
Manifest ponownie sprawdzony; obrazy i gateware bez zmian.
Rzeczywisty bloker HIL: brak potwierdzonej tożsamości/połączeń płyty,
przeglądu fizycznej mapy oraz zgody na konkretne działania sprzętowe.
Wiadomość wznowienia nie zastępuje tych danych i zgód.

## Wznowienie — 2026-10-15

Poprawiono semantykę błędu zapisu apply w kliencie Directions: utrata
odpowiedzi po możliwym zatwierdzeniu zawsze zgłasza uncertain=true,
niezależnie od flagi błędu dostarczonej przez transport. Bez ponowienia.
Test symuluje faktyczne zatwierdzenie maski przed błędem odpowiedzi.
44 testy Python,5 Rust i wire tests PASS. Gateware/firmware/obrazy bez zmian;
nie powtarzano zakończonych buildów. Brak działań sprzętowych.
Bloker HIL pozostaje: niepotwierdzona tożsamość/połączenia płyty,
przegląd fizycznej mapy i autoryzacja konkretnego uruchomienia.

## Urukul pinmux — 2026-10-17

Dodano wspólny profil `urukul_eem0`, walidację zgodności bindingu YAML
oraz wybór mapowania per slot w generatorze izolowanego STM i logicznego
Kasli. EEM0 SCK/MOSI/MISO=0/1/2, CS adres=3/4/5; wcześniej mux
wyprowadzał tylko jeden bit CS. Przykłady nadal symulacyjne, obecnie z mapą
modułu zgodną z ARTIQ. Zakres CPLD8/tłumików/RF OFF bez zmian.
Testy i granice integracji: [URUKUL](docs/URUKUL.md).
Bez nowych działań sprzętowych; zamrożone obrazy HIL bez zmian.

## Flash FPGA — 2026-10-17

Dodano osobny schema job/profile YAML, Python FPGAFlash API, CLI sinara-flash i lokalne HTTP API z autoryzacją. Realna ścieżka hosta wykonuje pełny backup, patch, flashrom write+verify i niezależny pełny readback pod lockiem płyty. Programowanie nie ma retry; błędy po możliwym zapisie oznaczają nieznany wynik. Profile sprzętowe przykładów są placeholderami i execution jest blokowane.

Nowy, osobny firmware serwisowy STM używa SPI1/4066/PROGRAM_N oraz USART3 serprog, nie danych QSPI ani SPI4/595. Cross-build PASS, nic nie zainstalowano. Trzyma FPGA w resecie; jawny BOOT sprawdza WIP i DONE. Nie jest jeszcze częścią normalnego runtime ani natywnego ESPHome.

Standardowy programator: adapter flashrom SPI i openFPGALoader JTAG z wyborem serial/chain, JEDEC przed zapisem, backupem i skip-reset. JTAG ma testy poleceń; nie uruchamiano go na kablu. Pełny test rzeczywistego flashrom -> ten sam serprog Rust -> model NOR16MiB PASS, także erase0→1 i zachowanie ogona sektora. Wyniki i SHA: evidence/flash-integration.json, flash-service-build.json. Fizyczna pamięć pozostaje nietknięta; HIL wymagany po podłączeniu. [Instrukcja](docs/FPGA_FLASH.md).

Finalna weryfikacja flash:56 Python,9 Rust i real-flashrom/model-NOR end-to-end PASS. Firmware/rdzeń/frozen ELF zgodne z zapisanymi SHA-256; schema kopie zgodne. JTAG pozostaje command-fixture only; brak HIL i brak zapisów fizycznej pamięci.

## Sampler — 2026-10-17

W istniejącym projekcie dodano przenośny driver C++17 LTC2320-16/PGIA oraz
komponenty ESPHome `sinara_gpio_endpoint` i `sinara_sampler`. Korzystają z
istniejących protokołów STM service/SCG1 i LiteX; nie używają RTIO. YAML
wybiera endpoint/CSR i przypisuje osiem funkcji GPIO, z walidacją kierunków,
wyłączności i gainów. To powolne SPI przez GPIO, bez nowego crossbara FPGA.

Modele STM/Kasli i rzeczywisty runtime ESPHome2026.9.0: compile/run PASS.
STM PTY/protokół i prawdziwy LiteX RemoteServer/model ADC: PASS, także
błąd w środku ramki, NaN i zatrzymanie bez publikowania częściowej próbki.
Native C++ testy obejmują wszystkie punkty błędu inicjalizacji/odczytu,
remap pinów, sign/order, gainy i oba zakresy napięcia. Regresja57 unittest,
9 Rust oraz wire i stary przykład ESPHome MAX31865/LM75B PASS.

Kasli target otrzymał opcjonalny profil `sampler_eem0` z ośmioma parami
LVDS; generacja HDL v1.1 PASS. Bez P&R, ładowania, fizycznych pomiarów ani
zmian zamrożonych obrazów HIL. STM nadal wymaga integracji gateway RTIC/HAL
i właściwych kierunków padów/adaptera; native ESPHome STM/Kasli nie jest
zaimplementowany. Nie oznaczać tego jako uruchomienia na fizycznych płytach.
Szczegóły i reproducer: [SAMPLER](docs/SAMPLER.md).

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

## Istniejące routery SPI MODULIQ — 2026-10-17

Potwierdzono oba komponenty `addrspi`/`addrspi2` w repozytorium
codex-hil/esphome-components, gałąź feature/mixed-signal-head, commit
287274ec757c8fc1a277e9535e6a0876dd9afb59. Wykorzystać je nad bazowym
SPI/GPIO STM/Kasli. Bez nowego routera. Szczegóły oraz ograniczenie pustej
transakcji CS MAX31855 przez router szeregowy: docs/ADDRESSED_SPI.md.
Audyt źródeł; brak implementacji backendu dla tej karty i brak nowego HIL.

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

## Publikacja źródeł — 2026-10-18

Przygotowano publiczne repozytorium codex-hil/unified-sinara-slow-control:
kod, testy, raporty, licencje i CI. Dane robocze i pobrane źródła pozostają
lokalnie; zobacz docs/PUBLICATION.md. Ponownie uruchomiono testy programowe.
Brak nowych działań sprzętowych; HIL nadal oczekuje na podłączenie kart.

## SCF5 — wspólny sprzętowy SPI i dwie kasety, 2026-10-18

Dodano wspólny rdzeń Migen: osiem kolejek SPI, cztery tryby SPI, sprzętowe
CS, adresowanie równoległe/enkodowane, GPIO/pinmux, impuls, barierę triggera
i zatrzaskiwany interlock AND aktywnych wejść. SPI ograniczono do linii0..7;
linie8..15 pozostają GPIO/status/interlock. Kierunki STM aktualizuje łańcuch
595 z blokowaniem wyjść podczas przełączenia. Kasli używa bezpośredniego OE.

Działa logiczny mostek x4 QSPI–Wishbone STM oraz przyłączenie tego samego
rdzenia do istniejącego SoC Kasli SMP4/DDR/Ethernet, bez uruchamiania Linuxa.
Wygenerowano HDL całego SoC; nie jest to jeszcze wynik P&R ani obraz HIL.
Przenośny klient C++ ma adaptery STM32H7 HAL QSPI i MMIO, a Rust zachowuje
baseline i osobny handler protokołu SCF5. Kompilacja obiektów ARM/RISC-V
nie oznacza gotowego firmware. Brakuje natywnego BSP/runtime ESPHome.

Rzeczywisty ESPHome host + niezmieniony MAX31855 obsłużył osiem syntetycznych
czujników przez rzeczywisty RTL obu wariantów; interlock innego slotu daje
NaN i błąd komponentu. Test równoległych instancji RTL porównuje ten sam
batch dla ośmiu slotów. Brak testów fizycznych. Profile pozostają unreviewed.

Dalszy krok: sprawdzona mapa padów obu kontrolerów, natywna integracja BSP,
a następnie loopback i dwie identycznie obsadzone kasety. Plan porównania
zawiera docs/DUAL_CRATE_HIL.md. Sampler nadal wymaga rozwiązania dwóch
magistral ADC/PGIA; pojedynczy nowy master na slot nie pokrywa obu naraz.

## Wznowienie — 2026-10-20

CI commita081c2e7 zakończyło się PASS (run39120901678). Dysk roboczy
ma ponownie około19GiB wolnego miejsca. Zachowano obce, niezatwierdzone
zmiany dokumentacji Sampler; nie przejęto pracy innego wątku.

Dodano regresję rzeczywistego mostka QSPI na minimalnym wspieranym
stosunku zegarów16:1: Wishbone ERR oraz brak odpowiedzi/timeout muszą
odrzucić resztę burstu pod tym samym CS. Jawne skasowanie błędu i nowy
CS pozwalają rozpocząć nową transakcję. Przerwane niepełne słowo nie
powoduje zapisu. Test nie używa sprzętu ani modelu zastępującego mostek.

HIL nadal NOT_RUN: brak potwierdzonego podłączenia i zweryfikowanych
profili fizycznych. Żadnych resetów, programowania ani połączeń z
urządzeniami laboratoryjnymi. Natywny ESPHome/BSP pozostaje niegotowy;
nie jest to zakończone MVP sprzętowe. Następny etap programowy to
integracja natywnego runtime i BSP; kolejne etapy sprzętowe wymagają
uzgodnionej konfiguracji i własności urządzeń.
