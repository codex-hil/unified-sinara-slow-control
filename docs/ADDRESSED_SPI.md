# Wykorzystanie adresowanego SPI MODULIQ

Źródło: `codex-hil/esphome-components`, gałąź `feature/mixed-signal-head`,
commit `287274ec757c8fc1a277e9535e6a0876dd9afb59`. Jest to wariant wskazany przez użytkownika:
„MODULIQ isoSPI adc dac HEAD — HW BRING-UP”. Sam transcript rozmowy nie
jest tutaj dostępny; przejrzano opublikowany kod i dokumentację bring-up.
Źródła i SHA256: `evidence/addressed-spi-upstream/manifest.json`.

Nie tworzymy nowego protokołu adresowania:
- `addrspi`: równoległe GPIO, kanały będące SPIComponent, wybór przed CS.
- `addrspi2`: jeden bajt adresu przed natywnym payloadem, jedna operacja
  buforowa na transakcję; header RX odrzucany. Wariant mixed-signal-head
  różni się od starszego wysyłającego header już w begin_transaction.
- Adapter STM/Kasli zapewnia GPIO oraz bazową magistralę ESPHome SPI.
  Oba routery i driver sensora pozostają współdzielone z MODULIQ.

MAX31855: zainstalowany driver ESPHome2026.9.0 czyta cztery bajty jednym
read_array, co pasuje do operacji buforowej addrspi2. Jednak update wykonuje
też enable/disable bez danych, po czym planuje odczyt po220ms. Aktualny
addrspi2 nie wysyła headera przy pustej transakcji. Nie potwierdzono więc
pełnej przezroczystości tego przypadku przez szeregowy router; trzeba
zweryfikować semantykę pustego CS i zachowanie konkretnego dekodera.
Równoległa karta użytkownika (3 linie adresowe) korzysta z addrspi.

Do testu integracyjnego: osiem adresów0..7, brak dodatkowych taktów na
natywnym SPI, poprawny CS, przeplot opóźnionych odczytów ośmiu sensorów,
ujemne temperatury i flagi błędów. Nie przenosić wyników HIL głowicy MODULIQ
na kartę DIOT ani na backendy FPGA bez ich własnego testu.

Status: audyt kodu, bez zmian driverów i bez testu sprzętowego MAX31855.
