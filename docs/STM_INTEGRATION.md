# Warunki integracji STM (jeszcze niewykonana)

Biblioteka firmware/stm-service kompiluje się no_std i nie używa alokatora,
YAML ani RTIO. Przyjmuje RegisterBus oraz gotową ramkę z RTIC; nie jest ELF
przeznaczonym do programowania. Nie zawiera zgadywanej implementacji pinów.

Przed implementacją RegisterBus należy ustalić wariant PCB i dopasować mapę
pinów ECP5 do netlisty. Dane w docs/AUDIT_STM.md pokazują, że żadnego z pobranych
pinoutów gateware nie można uznać automatycznie za zgodny z release PDF.
W `tpr_devel` 1+15-bitowy nagłówek jest odpowiedni dla firmware QspiWord::U16;
pięć dummy cycles przy 25 MHz pochodzi z konfiguracji źródeł i wymaga testu.

Integracja powinna obejmować:

1. Osobny obraz/gateware ABI, poprawną mapę CSR i pinów. GPIO dla wszystkich
   sygnałów Urukul, właściwe kierunki LVDS i zewnętrzne bufory/adapter DIOT–EEM.
   Stary SiLPA output set nie jest takim kontraktem.
2. RegisterBus read/write przez QSPI, big endian 16-bit data. Usunąć bezterminowe
   busy/unwrap; użyć monotonicznego deadline i zwracać BusError::Timeout/Hardware.
   `compatible()` ma potwierdzać nowy build i GPIO mode, nie sam ID 0xaaaa.
3. Zadanie RTIC dla UART, ograniczone bufory 16 bajtów i bounded framing timeout;
   bez debug logów na tym samym strumieniu. Cała operacja register jest blokowana
   współdzielonym bus managerem; Miniconf nie może równolegle używać tych pinów.
4. Najpierw software integration tests na prawdziwym parserze, potem bezpieczny
   HIL z pomiarem waveform i identity. Żadne test_eeprom nie powinno być odpalane
   przy discover: ta funkcja w upstream **pisze do EEPROM**, nie jest passive probe.
5. W docelowym serwisie lokalne transakcje SPI, zatwierdzony plan konfiguracji,
   watchdog i safe-state. Dopiero wtedy autonomiczność może zmienić się na true.

Nie przygotowano patcha udającego kompletne wdrożenie HAL/RTIC; testy obecnego
rdzenia potwierdzają parser, whitelistę i semantykę błędów, nie połączenia PCB.
