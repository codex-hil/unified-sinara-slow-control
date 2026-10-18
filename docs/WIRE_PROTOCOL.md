# Protokół bramki STM v1

To nowy protokół tego projektu, **nie protokół istniejącego firmware upstream**.
UART 115200, 8N1, wyłączny właściciel portu. Stała ramka 16 bajtów, big endian:

| Bajty | Request | Response |
|---|---|---|
| 0..1 | ASCII SC | ASCII SC |
| 2 | wersja 1 | wersja 1 |
| 3 | opcode | status |
| 4..7 | sequence u32 | ten sam sequence |
| 8..11 | word address u32 | ten sam address |
| 12..15 | write value u32 / 0 | read result / 0 |

Opcode 0 identify zwraca 0x53434731 tylko jeśli RegisterBus::compatible() daje
true. Opcode 1 read, opcode 2 write. Status 0 OK, 1 unsupported/version,
2 forbidden address/value, 3 incompatible/hardware, 4 timeout.

Whitelist: slot firmware 0..7, baza 20*slot. Odczyt offsetów 0/1/2, zapis tylko
0/2, wartość <= 65535. SPI controller i kontrolery IRQ nie są eksponowane.
Bramka GPIO wymaga obrazu z SPI offline dla GPIO, poprawnymi kierunkami i ABI.
Nie należy dodać whitelisty do istniejącego pinoutu bez przeglądu.

Sequence koreluje odpowiedzi w jednym otwartym strumieniu. Po timeout lub błędzie
strumień jest zatruty; brak ponawiania zapisów. Integracja RTIC musi zapewnić
ograniczenie czasu niepełnej ramki, resynchronizację oraz usunięcie starych
odpowiedzi przed nową sesją. Numer sequence nie jest trwałym identyfikatorem
operacji i nie zapewnia exactly-once między reconnectami.

Deadline przekazywany RegisterBus jest obowiązkowym kontraktem implementacji
HAL; sam rdzeń nie może przerwać źle napisanego sterownika busy-loop.
Bufor wejściowy i framing UART nie są częścią przetestowanej biblioteki no_std.
Hostowy stdio_simulator realizuje ramki z rejestrami pamięciowymi tylko do testu.

Kasli nie implementuje tej ramki: korzysta z istniejącego LiteX UARTbone i
litex_server/RemoteClient. Wspólna jest semantyka GPIO/SPI i urządzeń, nie
niepotrzebny nowy wspólny stos sieciowy. Zapisy LiteX RemoteClient nie mają
odpowiedzi potwierdzającej commit sprzętowy; configure musi użyć odczytu tłumików.
