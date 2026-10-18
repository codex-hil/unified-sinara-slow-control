# STM v1.1: przygotowanie do podłączenia 2026-10-14

Wszystkie dotychczasowe wyniki są offline. Żadne urządzenie nie zostało
zaprogramowane ani zresetowane. Dokument jest procedurą, nie dowodem HIL.

## Obrazy i role

| Obraz | Rola | Ograniczenie |
|---|---|---|
| Oryginalny ECP5 ABI3, seed3 | Punkt odniesienia, odtworzony upstream | Pinout i fizyczny timing do sprawdzenia |
| Oryginalny STM `main` | Zachowany baseline | Inicjalizuje IsoSPI/TempLogger; nie uruchamiać z nieznanymi modułami |
| STM `hil_probe` | Osiem odczytów ID/rev przez oryginalny QSPI x1, log RTT | Setup płyty ma skutki uboczne i może blokować; nie jest pasywny |
| Kandydat ECP5 ABI4 | CSR kierunków + automat 595 + OE | Tylko jeśli strict timing PASS i mapa fizyczna sprawdzona |
| Kasli logiczny fabric | Synteza/routing OOC ośmiu slotów | Bez SoC, EEM, transportu hosta i obrazu do programowania |

Ścieżki i SHA-256: `python3 tools/prepare_hil.py` generuje
`evidence/hil-manifest.json`, weryfikując zachowane obrazy i nowe buildy.
Manifest zawsze ma programming_ready=false: nie zastępuje przeglądu PCB.

## Pierwsze uruchomienie

1. Zapisać oznaczenie PCB v1.1, rewizję/BOM, programator FPGA i SWD STM,
   numery seryjne oraz aktualne obrazy. Porównać pinout z wygenerowanym LPF
   i schematem; nie wybierać kabla/programatora automatycznie.
2. Pierwszą próbę wykonać bez modułów w slotach. Potwierdzić zasilanie
   i zegary. Podłączyć pomiar do SCK/RCLK 595 oraz wybranych RE_DE.
3. Po zgodzie na konkretne działania uruchomić golden ECP5 ABI3 i probe
   STM. Preferować ulotne ładowanie FPGA. ELF jest linkowany do STM flash;
   uruchomienie przez debugger **nie oznacza automatycznie RAM-only**.
   Nie wykonywać `load` bez ustalenia/zgody na zapis flash i kopii aktualnego
   firmware. Obecne narzędzia offline nie zawierają komendy programowania.
4. Oczekiwany RTT: `HIL_PROBE: round N adr 160 value aaaa`, adr161=5555,
   adr162=0003, osiem rund i `ID_STABILITY PASS ABI 3`.
   Probe nie wywołuje init modułów, MQTT, transferu SPI4 ani zapisów CSR.
   Nadal używa oryginalnego setup GPIO/I2C/PHY oraz HAL QSPI; wewnętrzne
   oczekiwania HAL/setup nie mają potwierdzonego czasu zakończenia.
5. Dopiero po stabilnym baseline rozważyć ABI4. Dla niego oczekiwany rev=4,
   boot mask=0, 48 zboczy SCK i jeden impuls RCLK. Przed zakończeniem
   inicjalizacji zewnętrzny storage 595 może zachować poprzedni stan.

## Test kierunków ABI4

Konieczny dostęp do rejestrów z STM/debuggera lub dedykowanej usługi.
Obecny probe jest tylko read-only RTT — nie zapewnia jeszcze interaktywnego
API hosta. Nie uznawać SCG1 serial gateway ani starego klienta LiteX za
zgodne z ABI4. `src/sinara_slow/directions.py` wymaga transportu
word-addressed 16-bit i wyłącznego dostępu do konfiguracji.

| Adres słowa | Rejestr |
|---|---|
| 160/161/162 | ID aaaa / ID 5555 / ABI4 |
| 2048/2049/2050 | Żądana maska, słowa 47:32 / 31:16 / 15:0 |
| 2051 | apply, zapis 1 |
| 2052/2053/2054 | Aktywna maska, ta sama kolejność |
| 2055 | bit0 busy, bit1 valid, bit2 ready, bit3 rejected, bit4 blocked_write |
| 2056 | clear_rejected, zapis 1 czyści obie sticky flagi |

Najpierw tylko odczyty. Aktualizacja zera dopiero po sprawdzeniu ready i
nieaktywnych transakcji SPI. Zapis GPIO output musi poprzedzać apply;
podczas busy zapisy banku slotów są blokowane. Apply nie ma automatycznych
retry: timeout oznacza nieznany wynik. Readback aktywnej maski potwierdza
sekwencję FPGA, nie rzeczywisty poziom na PCB ani sprawność 595.

Dla zatwierdzonego pasywnego fixture: pojedynczy bit slot1/linia8,
stała wartość GPIO, zmiana input/output/input i pomiar przebiegu.
Sprawdzić kolejność sześciu bajtów, polaryzację, brak zboczy SCK/RCLK
podczas oczekiwania, liczbę taktów oraz stan kablowy przy przełączeniu.
/OE 595 stale aktywne; wyłączenie OE FPGA nie odłącza nadajnika MLVDS.
Nie deklarować bezglitchowej zmiany bez pomiaru.

Wyniki zapisywać z obrazami/hashami, identyfikacją sprzętu, capture RTT,
przebiegami pomiarowymi, oczekiwanym i rzeczywistym rezultatem. W razie
niezgodności wrócić do zachowanego baseline; nie zgadywać mapy ani modułów.

## Zamrożony zestaw

`work/hil-kit/2026-10-14/manifest.json` wskazuje aktualne obrazy.
W katalogu mogą pozostać starsze warianty o innych hashach — wybierać
wyłącznie pliki wymienione w aktualnym manifeście. Finalny kandydat
ma rejestrowane SCK/RCLK/OE i strict timing106.15MHz przy100MHz.
`programming_ready=false` pozostaje do identyfikacji i przeglądu sprzętu.

## Automatyczne sprawdzenie zapisanego RTT

Po zapisaniu surowego tekstu pojedynczego uruchomienia:

```sh
python3 tools/check_hil_capture.py work/capture-rtt.txt --expected-abi 3 --report evidence/capture-check.json
```

Dla ABI4 podać `--expected-abi 4`. Sprawdzane są24 wartości,8 rund,
kolejność i kompletność, nie tylko marker PASS. Exit0 oznacza poprawną
treść capture, exit1 niezgodność. Raport zachowuje SHA-256 surowego pliku.
`hardware_validated=false` jest celowe: tożsamość płytki, obrazy i
pochodzenie logu trzeba udokumentować osobno. Dwa uruchomienia w jednym
pliku są odrzucane; zachować osobny capture każdej próby.
