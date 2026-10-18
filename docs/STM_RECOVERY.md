# Najpierw odtworzenie upstream — decyzja 2026-10-11

Użytkownik zmienił kolejność: najpierw odtworzyć istniejące firmware/gateware
STM i sprawdzić HW; dopiero potem wybierać docelowy transport slow control.
Nowy hostowy demonstrator pozostaje oddzielny i nie zastępuje baseline upstream.

Przygotowano niezmienione snapshoty na drugim dysku:

- work/upstream-stm/gateware: tpr_devel 46f14f81d6a29c664f72d8c7373f4d346b43970d.
- work/upstream-stm/firmware: debug 19bc5913abe66b39f5fce9cf45c9f7126b8782c4.
- work/upstream-stm/baseline.json: kandydat, NIE zestaw potwierdzony na sprzęcie.

Wybrano je do odtworzenia, ponieważ gateware ma gate_rev=3, 15-bitowy adres
plus bit read oraz 8 bloków slotów; firmware używa U16 adresu i czyta gate_rev.
Gałąź main z adresem 7-bit nie jest właściwym kandydatem do tego firmware.
Dalszy dobór do konkretnej płytki może zmienić ten zestaw.

Historia ujawnia commit gateware „New pinout for SE IO after pin swapping”
z 2024-03-28 i „After first tests” na tpr_devel z 2025-03-20. To uzasadnia
sprawdzenie PCB/netlisty po pin swap, zamiast uznawania różnicy z PDF za błąd
kodu. Nazwa commitu „After first tests” nadal NIE jest raportem sprzętowym.
Firmware z 2025-09-09 zawiera poprawkę „Fixed bug with dead FPGA” i telemetry
gate_rev. Surowa historia: evidence/*-recovery-history.txt.

Kolejność odtworzenia:

1. Odtworzyć przypięte zależności flake.lock/Nix i Rust Cargo.lock/środowisko
   wskazane przez Dockerfile (Rust 1.88); zapisać osobno niezmieniony build oraz
   ewentualne minimalne poprawki zgodności toolchainu. Wszystkie nowe artefakty
   mają pozostać na drugim dysku. Nie uruchamiać init istniejącego firmware na
   nieznanych modułach: domyślnie są tam IsoSPI i TempLogger, nie ogólna pusta kaseta.
2. Ustalić identyfikator/revizję fizycznej STM oraz aktualny obraz i okablowanie.
   Potwierdzić netlistę po pin swap, napięcia i bootstrap ECP5. Nie nadpisywać flash.
3. Na sprzęcie rozpocząć od kontrolera bez podłączonych modułów/obciążeń:
   boot/debug, clock/reset, odczyt ID1/ID2/gate_rev przez SPI x1 przy małym zegarze.
   Testy ID nie pokrywają wszystkich I/O i analogowych torów modułów.
4. Sprawdzić GPIO/directions na znanych bezpiecznych pinach, SPI przez pasywny
   loopback/urządzenie testowe, IRQ, I2C i Ethernet. Dopiero potem testować moduły.
5. Zachować działający baseline i odtwarzalne logi. Eksperymenty QSPI/mux
   wykonywać w oddzielnym wariancie z możliwością powrotu do baseline.

## QSPI kontra mux

To dwie różne warstwy. QSPI jest łączem STM–ECP5. SPI module jest łączem
ECP5–slot. Można mieć QSPI + jeden SPI master i mux, albo klasyczne SPI +
niezależne slot masters. Nie trzeba wybierać jednej opcji wykluczającej drugą.

Przy zachowaniu aktualnej architektury sensowny następny krok to quad data
phase (np. 1-1-4), burst/block transfers i jawny timeout/status; opcjonalnie
1-4-4 lub 4-4-4 po testach. Wymagane turn-around/OE wszystkich czterech linii,
framing zgodny z QUADSPI STM, CS abort/resync, CDC i wersjonowanie protokołu.
Nie obiecywać 4x przyspieszenia całego systemu: krótkie odczyty CSR nadal mają
narzut adresu/dummy cycles, oczekiwania Wishbone i pollingu firmware.
QSPI nie daje pełnodupleksowego SPI do dowolnego modułu przez sam wire mux.

Mux klasycznego SPI STM do slotów jest praktycznym wariantem prostego,
sekwencyjnego slow control, jeśli istnieją sprawdzone połączenia zwykłego SPI
STM–FPGA i właściwe bufory LVDS. Slot wybiera się tylko przy wszystkich CS
nieaktywnych i SCK w stanie idle; nieaktywny slot nie może dostać impulsów CS/SCK.
Trzeba przełączać tryb/divider, MISO, CS (dla Urukul trzy bity decoded address),
pozostawić osobne GPIO/IRQ/reset i nie zwierać kierunków/transceiverów.
Nie rozwiązuje to samo z siebie I2C, identyfikacji modułu ani safe-state.

Rekomendacja: odtworzyć upstream x1 jako baseline. Potem wybrać według pomiarów
opóźnienia i wymaganej liczby równoległych slotów; pełne QSPI rozwijać wtedy,
gdy jest potrzebny transfer blokowy/telemetria lub elastyczność rejestrów.
Nie usuwać teraz istniejącego kodu ani testować jednocześnie nowego transportu
oraz nieznanej płytki.

Źródło możliwości faz QUADSPI: ST AN4760:
https://www.st.com/resource/en/application_note/DM00227538.pdf

## Reproducer i obrazy offline

Wybrana płytka: v1.1; podłączenie planowane przez użytkownika na wtorek.
Snapshoty w work/upstream-stm pozostają niezmienione. Narzędzia:

```sh
python3 tools/reproduce_stm.py elaborate
python3 tools/reproduce_stm.py firmware
python3 tools/reproduce_stm.py gateware --seed 3
```

Reproducer używa lokalnych snapshotów zależności oraz izolowanego Rust 1.88.
Nie pobiera zależności gateware i nie programuje żadnego urządzenia.
Gateware wykonuje build upstream, po czym strict P&R bez timing-allow-fail;
wyłącznie wynik strict nadaje się do dalszej kwalifikacji. Seed 3: 100.30 MHz
przy 100 MHz. Constraint pochodzi z upstream clk100/10 ns. SPI STM–FPGA
ustawione przez firmware na 25 MHz; constraint jego zegara w gateware 133 MHz
nie jest ustawieniem firmware ani obietnicą przetestowanej częstotliwości.
Hashe obrazów: evidence/stm-upstream-build-result.json.

Przed uruchomieniem: zidentyfikować programatory i obsadę slotów; zachować
backup/ścieżkę powrotu. Oryginalna binarka ma inicjalizację modułów i zapis
do CSR 0 w boot test; nie zakładać, że jest pasywnym testerem. Preferować
pierwszy test bez modułów, sprawdzić zasilanie, a następnie ID/revision
160/161/162. flash.sh zapisuje flash FPGA i nie jest krokiem domyślnym.

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
