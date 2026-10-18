# GPIO/SPI jak w ESPHome na ESP32

Warstwa dla modułów jest standardowa: GPIOPin oraz SPIComponent/SPIDelegate.
MAX31855 nie zna Wishbone, kontrolera STM/Kasli ani adresowania modułów.

```
standardowy MAX31855 ESPHome
       ↓ spi_id: tc0..tc7
istniejący MODULIQ addrspi (opcjonalnie addrspi2)
       ↓
SPI ESPHome → GPIOPin dostawcy sinara_gpio
       ↓
endpoint SCG1 → STM UART lub Kasli/LiteX TCP → rejestry FPGA
```

W obecnym demonstratorze SPI jest programowo taktowane przez GPIO, przy
użyciu istniejącego SPIDelegateBitBash ESPHome. Nie jest to jeszcze adapter
sprzętowego mastera MiSoC ani natywny runtime ESPHome na STM/Kasli.
Zażądana częstotliwość SPI nie oznacza osiągniętego zegara przez UART/TCP.
Lokalny master będzie kolejnym backendem tego samego interfejsu.

## Piny

```yaml
sinara_gpio:
  id: diot
  endpoint_id: endpoint0

# Pole pin dowolnego komponentu akceptującego zewnętrzne GPIOPin:
pin:
  sinara_gpio: diot
  number: "7_15"
  mode: OUTPUT
```

Slot1..8, linia0..15. Wymagany string w cudzysłowie; YAML `7_15` może
zinterpretować jako715. Dostawca jest obecnie przypisany do jednego slotu
endpointu; można utworzyć kolejnych dostawców dla innych slotów. Walidacja
odrzuca inny slot, nieprawidłowy kierunek i powtórne użycie bez jawnego
allow_other_uses. Obsługiwane są INPUT, OUTPUT oraz inwersja programowa.
Brak pull-up/down, open-drain, wewnętrznych pinów MCU, IRQ i gwarancji
precyzyjnego czasu. Komponenty wymagające InternalGPIOPin nie są zgodne.

RMW zachowuje inne linie GPIO. Przed włączeniem OE zapisuje poziom wyjścia;
nie potwierdza to bezglitchowego przełączania fizycznych translatorów.
Backend wymaga SCG1 oraz zweryfikowanego profilu fizycznych kierunków.
ABI4 nie jest automatycznie zgodne z SCG1. Dla sprzętowego STM slotów1..6
linie8..15 są odrzucone: ich automatyczne kierunki wymagają adaptera ABI4/595.
Nie wolno obchodzić tego przez samo zadeklarowanie output_capable.

## Adresowane SPI i osiem MAX31855

Pełny przykład: `integrations/esphome/examples/max31855-diot-simulation.yaml`.
Przypisanie linii0SCK,1MOSI,2MISO,3CS,4..6A0..A2 jest syntetyczne;
nie pochodzi ze schematu karty użytkownika. Sensor wybiera tylko spi_id
wirtualnego kanału i wspólny CS. Niezmieniony addrspi ustawia trzy adresowe
GPIO przed CS. Puste impulsy CS i opóźnione odczyty standardowego MAX31855
pozostają obsługiwane. Test obejmuje rzeczywisty domyślny MODE3 drivera.

addrspi i addrspi2 są skopiowane bez zmian z przypiętego commitu
MODULIQ feature/mixed-signal-head; manifest zapisuje SHA256 wszystkich
sześciu plików. Lokalne SPIComponent otrzymało istniejące w MODULIQ
rozszerzenie: klasa dziedziczona, wirtualne register/unregister_device.
Nie nadpisano nowszych pozostałych funkcji SPI ESPHome2026.9.0.

addrspi2 nadal wymaga hardware SPI i jednej operacji buforowej na ramkę.
Jego walidacji nie poluzowano dla demonstratora software SPI. Pełna ścieżka
szeregowa na FPGA oraz puste transakcje CS przez dekoder pozostają do testu.
Aktualny upstream addrspi akceptuje powtórzone numery kanałów; używamy
jednoznacznych0..7, a test zapisuje to ograniczenie upstream.

## Błędy i wyłączność

Jeden provider jest jedynym właścicielem endpointu; bez równoczesnego
bezpośredniego drivera Sampler/Zotino. Endpoint utrzymuje blokadę pliku
całej sesji sprzętowej. Pojedyncza ramka SPI utrzymuje także blokadę
operacji endpointu i wspólny deadline. Zmiana adresu poprzedza jej CS,
zgodnie z kodem istniejącego addrspi. Brak wielowątkowego arbitrażu;
standardowy runtime ESPHome wykonuje te wywołania synchronicznie.

Błąd transportu zatrzymuje dostawcę do restartu, bez automatycznych prób
ponowienia. Adapter SPI zwraca wtedy nieważną ramkę0xFFFFFFFF, którą
MAX31855 publikuje jakoNaN. Nie jest to uniwersalna semantyka błędów każdego
możliwego chipa SPI: kolejne drivery wymagają własnego testu błędów.
GPIOPin zwraca bool i nie ma kanału błędu odczytu; klient zwykłego GPIO
musi uwzględniać stan błędu dostawcy. Utrata transportu nie gwarantuje
zmiany fizycznego stanu wyjść ani dezaktywacji CS; lokalny watchdog i
stan bezpieczny kontrolera nadal wymagają integracji.

## Weryfikacja

`python3 tools/test_diot_esphome.py` kompiluje prawdziwy ESPHome host,
niezmieniony MAX31855 i przypięty addrspi. Obejmuje osiem adresów,
ujemne/dodatnie temperatury, ramki32bit, puste CS, zachowanie innych GPIO,
walidację pinów i awarię transportu. STM jest modelem na PTY; Kasli używa
prawdziwego LiteX RemoteServer na localhost z modelem rejestrów. Odczyty
są syntetyczne; nie wykonano programowania ani pomiarów sprzętowych.
Raport: `evidence/diot-esphome-tests.json`.
