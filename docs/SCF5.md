# SCF5 — wspólny fabric slow control, 2026-10-18

To nowy, osobny ABI5; nie jest kompatybilny z SCG1 ani legacy ABI4.
Nie zawiera RTIO. Ten sam kod Migen obsługuje ECP5 i Kasli; różnią się
wejście Wishbone, fizyczne pady i obsługa kierunków.

## Co zaimplementowano

- Osiem niezależnych masterów/kolejek. Silnik bitowy pozostaje MiSoC
  SPIMachine, bez przepisywania SPI od podstaw. FIFO TX/RX są Migen SyncFIFO.
- Domyślnie64 słowa32bit TX oraz64 wyniki RX na slot. Każdy wynik zawiera
  bajt danych, tag oraz znacznik końca. Głębokość wybiera profil budowy.
- Niepełna komenda czeka. CS/SCK ruszają po otrzymaniu całego payloadu oraz
  zapewnieniu miejsca na cały RX. Kontynuacja bajtów ładowana bez pauz CPU.
- Direct1..4 CSN, parallel1..4 bity adresu i osobny CSN, encoded CS (Urukul:
  zero=idle), oraz no-CS. Adres równoległy ma czas setup i pozostaje stabilny
  po zwolnieniu CS. Typ selektora i przypisania linii pochodzą z profilu.
- Piny SPI mogą być wyłącznie0..7. Runtime CTRL przełącza grupę SPI/GPIO;
  dowolny runtime crossbar między funkcjami nie jest jeszcze zaimplementowany.
  Piny8..15 pozostają GPIO lub funkcjami trigger/ready/interlock.
- AND z włączonych, znormalizowanych wejść interlock; niewłączone są ignorowane.
  Wejścia mają synchronizację2FF, stan trip jest zatrzaskiwany. Wymagane są
  dobre wejścia, jawne clear i flush przerwanych kolejek; brak auto-replay.
- Bariera WAIT_TRIGGER dla maski slotów; opcjonalne zewnętrzne ready inputs
  także muszą zezwalać. Wspólny impuls trafia w tym samym cyklu do wybranych
  slotów. Źródło triggera: zewnętrzne, STM lub programowa komenda. Szerokość
  i maska są konfigurowalne. Wyjściowe polaryzacje są w profilu.
- ECP5: ponowne wykorzystanie DirectionController dla48 kierunków/sześciu595.
  Podczas zmiany kierunków logiczne OE wszystkich slotów są wyłączone.
  Górne linie slotów7/8 oraz fixed/emulated LVDS pozostają zadaniem adaptera.
- Kasli: dołączenie do istniejącego SoC SMP4/DDR/LiteEth, bez obrazu Linuxa.
  HDL całego SoC wygenerowany. Fabric ma region0x81000000/64KiB, uncached;
  nie używamy0x50000000, które w tym SoC leży wewnątrz DDR/cache regionu.

## Strumień komend

32-bitowe słowa zapisujemy do portu TX slotu. Nagłówek:

```
31..28 opcode |27..24 selector |23..16 tag |15..0 length
```

| Opcode | Działanie | length |
|---|---|---|
|1 WRITE | TX, RX odrzucany | bajty |
|2 READ | automatyczne bajty0 na MOSI | bajty |
|3 XFER | pełny duplex | bajty |
|4 DELAY | odstęp | cykle sys |
|5 WAIT_TRIGGER | czekaj na wspólny trigger |0 |
|6 PULSE | impuls na przypisanej linii, jeśli istnieje | cykle sys |
|7 CS_ASSERT | sprzętowo rozpocznij sesję CS |0 |
|8 CS_RELEASE | sprzętowo zakończ sesję CS |0 |

Payload WRITE/XFER jest pakowany po4 bajty na słowo, pierwszy bajt w bitach0..7;
SPI przesyła bity bajtu MSB-first. Ostatnie nieużyte bajty słowa są ignorowane.
CS_ASSERT/RELEASE umożliwiają naturalny interfejs enable/read/write/disable
ESPHome, w tym puste impulsy CS MAX31855. Zwykły WRITE/READ/XFER bez otwartej
sesji jest jedną kompletną transakcją z automatycznym CS. Sesja nie może zmienić
selektora. Watchdog sesji wynosi sys_clk_hz cykli, czyli nominalnie1s.

Odczyt RX: bity7..0=dane,15..8=tag,16=ostatni bajt. ACK Wishbone zwraca
wartość sprzed pop FIFO; rejestr odpowiedzi zapobiega pomijaniu pierwszego bajtu.
Błędy slotu:1 malformed,2 interlock/disable-abort,3 watchdog. Wymagają flush.
Częściowo wykonana komenda nie jest automatycznie ponawiana.

## Mapa Wishbone

Adresy w tabelach są bajtowe. Bus.adr jest adresem słowa32bit. Pełne zapisy
wymagają sel=0xf. Jeden STB jest akceptowany raz; trzeba zwolnić STB przed
kolejnym dostępem. Brak pipelined Wishbone. Pełne FIFO/nieprawidłowy dostęp
zwracają ERR, bez akceptacji tego słowa; nadawca sprawdza kredyty przed burstem.

| Offset globalny | Rejestr |
|---|---|
|0x00/0x04 | MAGIC0x53434635 / ABI5 |
|0x08 | permit,ready,tripped,trigger_rejected,direction_busy,valid — bity0..5 |
|0x0c | maska włączonych slotów |
|0x10/0x14 | interlock mask / active-low mask |
|0x18/0x1c | trigger mask / width |
|0x20 | bit0 clear safety latch;1 software trigger;2 apply directions;3 reset ingress parser;4 clear transport error |
|0x24 | trigger source:0 external,1 STM |
|0x28/0x2c | trigger count / transport error |
|0x30/0x34 | aktywne kierunki48bit |
|0x38/0x3c | identyfikator profilu64bit |
|0x40 | wieloslotowy port ingress |
|0x44/0x48 | hardware ready mask / active-low mask |

Slot1..8: baza `0x100+(slot-1)*0x100`.

| Offset slotu | Rejestr |
|---|---|
|0x00 | CTRL: bit0 enable SPI/queue |
|0x04 | status: TXready0,RXready1,busy2,fault7..4,waiting8,CSsession9 |
|0x08/0x0c | TX push / RX pop |
|0x10 | TX level15..0, RX level31..16 |
|0x14 | divider7..0, CPOL8, CPHA9 |
|0x18/0x1c | GPIO OUT / requested OE |
|0x20/0x24 | safe OUT / safe OE |
|0x28 | completed15..0, last tag23..16 |
|0x2c | bit0 flush queue/session/results |
|0x30/0x34 | interlock line lub0xffffffff / output+input capabilities |
|0x38/0x3c | input / FIFO depth |
|0x40/0x44 | logiczne output / effective OE |

Dzielnik MiSoC koduje okres jako `divider+2` cykle sys. Aktualny klient
stosuje minimum4 cykle i maksimum257. Config zmienia się przy wyłączonym,
pustym i nieaktywnym masterze. Kierunki wejść interlock/ready są chronione.
Safe OE nie może włączyć fizycznego wejścia. Wyjścia fixed/emulated nie stają
się fizycznie tristate przez zmianę logicznego OE; adapter wybiera ich
nieaktywny poziom z konfiguracji. Te poziomy muszą być sprawdzone dla karty.

## Jednym QSPI do wielu slotów

Port ingress0x40 przyjmuje kolejno:

```
envelope=(liczba_słów<<16)|(slot-1)
header komendy
payload...
envelope kolejnego slotu
...
```

Licznik obejmuje nagłówek i payload, bez envelope. `stream_commands` generuje
ten format. Nadawca sprawdza pojemność każdego FIFO; błąd w środku burstu
może oznaczać wykonanie wcześniejszych komend, nie całego zestawu.

QSPI jest SDR4-4-4 mode0, sys>=16*SCK. Dla100MHz sys obecny limit to6.25MHz,
nie100MHz. Nagłówek to opcode8+adres bajtowy24, MS nibble/byte first:
-0x32 fixed-address write burst — np. ingress0x40;
-0x02 incrementing-address write burst;
-0x0b pojedynczy odczyt32bit,8 dummy SCK, bez spekulacyjnego pop kolejnego RX.

Mostek ma sticky errors:1 header/address,2 WishboneERR,3 timeout,
4 overlap,5 read underrun. Błąd zapisu zatrzymuje resztę danego burstu.
CS abort częściowego słowa nie zapisuje tego słowa, ale nie cofa wcześniejszych
zapisów ani już rozpoczętego odczytu. HAL po operacji sprawdza transport status.
Nowy format nie może być sondowany legacy firmware x1; wymagane są dobrane
wersje firmware/gateware przed uruchomieniem busa. Brak flash/JTAG w narzędziach.

## ESPHome i kod natywny

`sinara_fpga` identyfikuje ABI/profil, otwiera wyłączny transport i udostępnia
SPIBus/GPIOPin. Każdy wirtualny `spi` wybiera slot i selector. SPI i CS są
sprzętowe. `cs_pin` standardowego drivera jest zwalidowanym opisem połączenia;
adapter nie wywołuje na nim software digital_write. `addrspi` nie jest potrzebny
przed sprzętowym selektorem równoległym. `addrspi2` pozostaje w firmware bez
zmian: dołącza bajt, potem przekazuje jeden bufor do hardware SPI. Dla jego
walidacji bazowy bus może zadeklarować `mosi_pin: profile` i `miso_pin: profile`.

Pakiet `scf5-max31855-devices.yaml` jest wspólny dla obu kontrolerów; zmieniają
się tylko pliki połączenia. Profile przykładów są celowo reviewed:false.
Nie są fizyczną mapą kasety. Test wytwarza osobne, jawnie syntetyczne profile
oraz wyłącznie lokalne PTY/localhost. Nie wolno oznaczać ich jako potwierdzenia HW.

Przenośny C++ `fabric_client.h` oraz QSPI/MMIO w firmware/hal nie zależą od
ESPHome ani systemu operacyjnego. ARM/H743 i RV32IMA przeszły compile-only;
HAL sprawdzono także hostowym fixture. Hostowy transport ESPHome obsługuje
SC v2 UART i LiteX TCP. Rust handler v2 jest oddzielony od legacy SC v1/SCG1
oraz sprawdza MAGIC/ABI przed dostępem. RTIC/UART/HAL firmware board app i
natywna platforma/runtime ESPHome STM/Kasli nie są jeszcze wdrożone.
MMIO wymaga poprawnego regionu i obsługi bus faults przez BSP; obiekt compile
nie zastępuje firmware startowego, sieci, schedulerów ani biblioteki C++.

## Walidacja i ograniczenia

`tools/test_scf5_esphome.py`: niezmieniony MAX31855 → prawdziwy ESPHome →
UART/LiteX → rzeczywista symulacja Migen SPI/FIFO. Osobno
`tests/test_qspi_fabric.py`: rzeczywiste sygnały QSPIx4 → Wishbone → FIFO.
`tests/test_dual_fabric.py`: dwa rzeczywiste rdzenie równocześnie, identyczny
batch ośmiu slotów, porównanie wyników i tagów. Wszystkie chipy są modelami.

Synteza core ECP5 i XC7 PASS, bez nowego P&R/Fmax i bez przypisania padów.
Pełny SMP4/DDR/LiteEth SoC+fabric: HDL elaboration PASS, nowe obraz/timing/HIL
NOT_RUN. Profil logiczny nie dowodzi poprawności fizycznego podłączenia.
Przed obrazem do HIL potrzebne są zgodna mapa Kasli-DIOT i potwierdzony pin-swap
STM v1.1 oraz dopięcie adapterów MixedPads do realnych zasobów platformy.

Sampler ma osobny SPI ADC i PGIA. Obecny profil jednego busa na slot nie
zapewnia jeszcze sprzętowej obsługi obu naraz; potrzebne jest przełączanie
trasy przy idle albo dodatkowy lane. Nie deklarujemy pełnego hardware drivera
Samplera/Urukula/Zotino na podstawie ogólnego silnika. Brak RTIO/Linuxa w fabric.
Interlock reaguje po synchronizacji/propagacji FPGA; nie jest niezależnym
certyfikowanym układem bezpieczeństwa. Fizyczne czasy/skew i safe levels są do HIL.
