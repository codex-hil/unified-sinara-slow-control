# Wspólny pinmux STM/Kasli

Audyt i testy: 2026-10-13. Bez programowania sprzętu.

## Co istnieje w ECP5

W upstream `SlotController` (`stm_sys_board_hdl.py`, tpr_devel,
46f14f81d6a29c664f72d8c7373f4d346b43970d) jest już mux SPI/GPIO:

| Linia logiczna | SPI przy offline=0 | offline=1 |
|---|---|---|
| 0 | SCK | GPIO |
| 1 | MOSI | GPIO |
| 2 | MISO | GPIO |
| 3 | CS, bit 0 | GPIO |
| 4–15 | GPIO | GPIO |

To stałe przypisanie, nie dowolny runtime pinmux. Rejestr `offline`
przełącza wszystkie cztery linie. `SpiInterface.py` i master MiSoC są
logiką Migen, niezależną od ECP5. Wektor CS ma 16 bitów, ale upstream
przypina go do jednej linii: szerokość przypisania zostawia tylko bit 0.

Analiza sprzętowa: [issue #3](https://github.com/sinara-hw/STM_Sys_Board/issues/3),
zwłaszcza [propozycja przypisań z 2023-10-31](https://github.com/sinara-hw/STM_Sys_Board/issues/3#issuecomment-1786945985).
Komentarze opisują także propozycje i starsze rewizje; nie stanowią testu v1.1.

## Co wydzielono

`gateware/pinmux.py`: `SlotPinMux`, bez CSR i prymitywów padów.
Domyślne mapowanie zachowuje powyższy układ. Parametr `mapping` pozwala
wybrać linie SCK/MOSI/MISO i kilka osobnych CS podczas elaboracji.
Kontrola odrzuca powtórzone i nieistniejące linie. `offline` i maska
`spi_mask` pozwalają podczas pracy oddać linie GPIO. Maska nie zmienia
przypisania funkcji SPI: dowolnego runtime crossbara jeszcze nie ma.

Przykład konstrukcji (nie konfiguracja fizycznego modułu):

```python
SlotPinMux(spi_interface,
           mapping={"clk": 0, "mosi": 1, "miso": 2, "cs": [3, 4]})
```

`tools/test_shared_pinmux.py` generuje izolowany wariant STM z zastąpionym
wyłącznie blokiem muxa. Źródła upstream pozostają bez zmian. Mapa CSR
ma nadal 163 rejestry, z czego 20 na slot. W tym wariancie nowa maska
pozostaje domyślna: nie wystawiono nowego CSR ani dodatkowych CS na PCB.
Ten sam pełny SlotController, z upstream masterem MiSoC i SpiInterface,
został przetworzony do Veriloga z regułami Artix-7 platformy Kasli v1.1.
Nie podłączono jeszcze slotu do SoC, CSR bridge ani pinów EEM Kasli.

## Granice elektryczne i bezpieczeństwo

Mapowanie logiczne nie zmienia możliwości buforów. Upstream STM używa
statycznej listy wyjść `silpa_outputs=[0,1,3,4,5,6,7,8,9,10]` dla
emulowanego LVDS. W tych ścieżkach OE nie przełącza fizycznego kierunku.
Sloty 1–6 i 7–8 różnią się obsługą górnych ośmiu linii; w ostatnich
są ścieżki emulowanego LVDS. Kierunki translatorów MLVDS pozostają
sterowane osobnym łańcuchem SPI/rejestrów przesuwnych.

Warstwa kontrolera musi mieć osobny profil rewizji PCB: pad, standard
I/O, możliwy kierunek oraz sterowanie translatorem. Walidator musi
odrzucać niezgodne mapowanie, nawet gdy logiczny mux je obsługuje.
Przed zmianą muxa podczas pracy trzeba zakończyć transfer, ustawić CS
w stan nieaktywny i bezpiecznie przełączyć kierunki. Takiej sekwencji
sprzętowej jeszcze nie zaimplementowano. GPIO OE nie jest interlockiem.
Upstream IRQ wykorzystuje GPIO OE i może reagować na linie SPI;
wydzielenie muxa nie poprawia tego ograniczenia.

## Odtworzenie testów

```sh
python3 tools/test_all.py
PYTHONPATH=$PWD/work/upstream-stm/deps/migen:$PWD/work/upstream-stm/deps/misoc:$PWD/work/upstream-stm/deps/litex:/usr/lib/python3/dist-packages /home/codex-hil/vector-analyser/.venv/bin/python tools/test_shared_pinmux.py
```

Wyniki: symulacja domyślnego i zmienionego przypisania, CS, OE,
GPIO fallback i walidacji PASS. Elaboracja pełnego STM PASS.
Generowanie logicznego slotu dla Kasli PASS.
Dowody: `evidence/shared-pinmux-build.json`, `.log`, `test-1.log`.
Brak syntezy/P&R tego wariantu, pomiarów i testów HIL.

Następne kroki: profile pinów v1.1/Kasli, integracja slotu z CSR
Kasli, walidacja mapowania z YAML, interlock przełączania oraz testy
rzeczywistych SPI i kierunków. Most STM–FPGA pozostaje odrębną warstwą;
QSPI nie jest częścią tego muxa.

## IC8 — potwierdzenie schematu v1.1

Zweryfikowano wizualnie stronę 8 PDF `STM_System_Board_Extended.PDF`
(arkusz M-LVDS transceivers, Rev.1.1): IC8A = SN74LV595APWT.
SER pin14 = MOSI, SRCLK pin11 = SCK, RCLK pin12 = CS,
/OE pin13 = GND, /SRCLR pin10 = P3V3. QA..QH sterują
RE_DE8..RE_DE15; QH' pin9 jest wyjściem szeregowym MISO/łańcucha.
CS jest zegarem zatrzasku: potrzebne jawne zbocze narastające po
przesunięciu maski, nie samo założenie standardowej semantyki CS.
/OE 595 jest na stałe aktywne, więc nie można wyłączyć jego wyjść
z FPGA. Odłączenie wyjść FPGA nie wyłącza nadajnika translatora;
bezpieczna sekwencja musi uwzględniać kierunek urządzenia po drugiej
stronie i stany przejściowe. Zatrzask usuwa zmiany podczas przesuwania.

## Automat kierunków — 2026-10-13

`gateware/direction.py` implementuje `DirectionController`; wrapper
MiSoC CSR jest w `gateware/direction_csr.py`. Wspólne rejestry:
requested (maska), apply (zapis 1), active, status (busy/valid/ready/
rejected) oraz clear_rejected. Status ma obecnie 5 bitów; bit4 sygnalizuje zablokowany zapis slotu. Wielobitowy requested zapisujemy w całości
przed apply; automat kopiuje go przy akceptacji. Zmiany podczas busy
nie wpływają na trwający transfer. Apply kiedy nie ready jest odrzucane
ze sticky rejected; nie ma kolejki. To nowy ABI, nie rozszerzenie
niezmienionego banku 163 CSR. Wrapper musi zostać podłączony do banku.

Po resecie rdzeń wysyła zera i zatrzaskuje wejściowe kierunki, zanim
ustawi valid. W każdej aktualizacji OE całej obsługiwanej grupy jest
wyłączone, maska przesuwana MSB-first, SCK wraca do zera, następnie
RCLK dostaje impuls narastający. Po czasie settle aktualizuje się
active i OE. Wariant serial=False realizuje ten sam handshake bez
impulsów 595. Parametry półokresu i settle są w taktach sys; domyślne
50/4 odpowiadają 1 MHz SCK/40 ns settle przy sys=100 MHz. Są to
parametry kandydata, nie potwierdzone constraints elektryczne.

Schemat v1.1, strona 1: sześć 595, łańcuch SER pierwszego ze wspólnego
MOSI, QH' kolejnych do SER następnego, ostatni do MISO FPGA. Wspólne
SCK/RCLK. Logiczny bit0 odpowiada QA pierwszego (slot1 linia8), bit7
QH pierwszego (linia15), kolejne bajty slotom2..6. Wysyłamy bajty
slot6..slot1, każdy MSB-first. To profil wyprowadzony ze schematu,
bez potwierdzenia fizyczną płytą. Nie dotyczy slotów7/8.
RE_DE jest wspólnym DE i aktywnym niskim /RE: 1 nadajnik, 0 odbiornik.
Źródło polaryzacji: [NB3N401S, tabela 2](https://www.onsemi.com/pdf/datasheet/nb3n401s-d.pdf).

Symulacja modeluje osobno shift i storage 595: 48 taktów na transfer,
4 zatrzaśnięcia (inicjalizacja i 3 konfiguracje), maski mieszane,
wszystkie wyjścia, wszystkie wejścia, stabilny snapshot, blokada przez
quiescent oraz wariant bez 595 PASS. CSR rejection/clear/apply PASS.
Generacja HDL obu wrapperów PASS. Pełna regresja: 32 Python, 5 Rust
oraz protokół PASS; nie wykonano syntezy/P&R nowego automatu ani HIL.

Pozostała integracja: zastąpić upstream passthrough SPI4, przydzielić
wersjonowane adresy CSR, podłączyć OE górnych linii i arbitration SPI,
przenieść desired OE z pinmuxa do jednego źródła prawdy oraz udostępnić
profil Kasli. Wystawiony sygnał quiescent nie wykrywa sam aktywnego
SPI; wrapper platformy musi go dostarczyć i blokować start transferów
przez cały busy. Runtime pinmux/output values nie są jeszcze atomowo
aktualizowane przez ten automat.

Ograniczenia elektryczne: wyłączenie OE FPGA nie odłącza aktywnego
nadajnika translatora, a załączanie nadajnika przed OE FPGA tworzy
krótki okres bez sterowania wejściem D. Sam automat nie gwarantuje
braku impulsów na kablu; potrzebny test/ustalenie polaryzacji bezpiecznej
wartości i pullów. Nie maskujemy tych stanów jako bezpiecznej walidacji.
Reset FPGA nie resetuje storage zewnętrznego 595; do zakończenia pierwszego
transferu jego poprzedni stan pozostaje nieznany. Brak readback w tym
rdzeniu oznacza, że valid potwierdza zakończenie sekwencji, nie PCB.

## Zintegrowany ABI4 — 2026-10-13, aktualny stan

`gateware/slow_fabric.py` podłącza DirectionCSR do osobnego banku słów
0x800..0x808. Stary bank163 słów zostaje w regionie0, rev162 zwraca4.
Adresy, źródła i ograniczenia: `evidence/integrated-csr-map.json`.
`tools/integrated_stm.py` generuje izolowany target z upstream, bez
modyfikacji snapshotu. SPI4 passthrough usunięty wyłącznie w kandydacie:
SCK/MOSI/RCLK translatorów steruje automat. Górne OE slotów1–6 pochodzą
wyłącznie z aktywnej maski, stare upper OE są ignorowane; nie ma drugiego
źródła kierunku. Sloty7/8 zachowują statyczne ograniczenia elektryczne.

Gotowość zależy od idle wszystkich8 masterów oraz braku ich data.re.
Podczas busy/apply bank slotów nie przyjmuje zapisów, a odrzucenie zapisuje
sticky bit4. Readback i clear nie kasują nic automatycznie. IRQ używa
rzeczywistego OE i jest maskowane podczas aktualizacji kierunków.
Zmiana SPI offline/mapping nie jest jeszcze atomową częścią apply;
SPI mapowanie nadal ustala konstruktor pinmuxa.

Zegar 595 i zatrzask są rejestrowane: test Icarus wykrył dodatkowe zbocza
przy wcześniejszej kombinacyjnej dekodacji FSM. Test całego mostu po
poprawce liczy dokładnie48 zboczy na zatrzaśnięcie, w tym boot i powrót
na wejścia. Legacy odczyt CSR używa rejestrowanego one-hot select
(`gateware/csr_bank.py`), zachowując kolejność słów i cykl CSR. Rozdziela
dekodowanie adresu od szerokiego muxa i poprawia timing. Cały most
SPI2WB/WB2CSR z prawdziwymi CSR przechodzi readback, nie tylko model RAM.

STM strict P&R: seed3 99.12 MHz FAIL, seed7 99.65 FAIL,
seed2 100.83 PASS przy wymaganych100 MHz. Niewielki margines i brak
zewnętrznych constraints/CDC proof; bitstream nie był ładowany.
Kasli XC7A100T-2 OOC fabric: 2014 LUT/2077 FF, setup8.398 ns,
hold0.108 ns przy62.5 MHz PASS. To nie cały SoC ani fizyczny port EEM.

Reproducery: `python3 tools/reproduce_stm.py fabric-sim`,
`python3 tools/reproduce_stm.py integrated-bridge-sim`,
`python3 tools/build_integrated.py stm --seed 2`,
`python3 tools/build_integrated.py kasli`.
Buildy wymagają wcześniejszej elaboracji przez fabric-sim.
Raporty: `evidence/integrated-{fabric-tests,bridge-tests,stm-build,kasli-build}.json`.
Ograniczenia resetu, elektryki i braku readback 595 opisane powyżej
nadal obowiązują. Na jutro: [HIL_START](HIL_START.md).

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

Profil modułu Urukul i trzybitowy CS w mux STM/Kasli: [URUKUL](URUKUL.md).
