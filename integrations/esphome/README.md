Aktualizacja2026-10-17: dodano standardowy provider GPIO `sinara_gpio`
(piny `"slot_linia"`), programowe SPI ESPHome nad rejestrami FPGA oraz
niezmieniony MODULIQ `addrspi`. Test8 MAX31855 działa przez model STM PTY
oraz model Kasli z LiteX localhost; błędy transportu dająNaN. Nie jest to
walidacja sprzętowa ani natywny port runtime. Szczegóły i ograniczenia:
[GPIO/SPI](../../docs/ESPHOME_GPIO_SPI.md).
Uruchom `python3 tools/test_diot_esphome.py`.

Poniższy opis dotyczy wcześniejszego demonstratora MAX31865/LM75B.

# ESPHome addressed-bus proof of concept

Pierwszy działający fragment na Linux x86_64 host, ESPHome **2026.9.0**.
Nie jest portem STM32 ani potwierdzeniem pracy na Kasli. Żadne GPIO fizyczne,
UART, JTAG, MMIO, sieć laboratoryjna, MQTT lub API server nie są używane.

Oryginalne komponenty ESPHome MAX31865 i LM75B działają bez zmian. Wygenerowany
program publikuje syntetyczne PT100 około -0.009°C oraz LM75B 25°C. Wyniki
pochodzą z jawnych modeli układów, nie z pomiarów. MAX31865 wybrano, ponieważ
istnieje już w firmware STM/TempLogger i w ESPHome.

## Powtórzenie

Z katalogu projektu na tym hoście:

```sh
python3 tools/test_esphome.py --compile
```

Test kompiluje prawdziwy runtime ESPHome, uruchamia go na pięć sekund, kończy
proces i sprawdza wartości publikowane przez oryginalne sterowniki. Sprawdza
odrzucenie `mode: hardware` oraz slotu poza zakresem. Raport i logi: `evidence/esphome-*`.
Przykład ma lokalny absolutny build_path; przy przenoszeniu zmienić tę ścieżkę.
PlatformIO cache jest izolowany w `work/platformio`; globalna instalacja
ESPHome pozostaje nienaruszona. Test odmawia pracy na innej wersji ESPHome.

## Co zintegrowano

- Standardowy SPIComponent ma publiczny setter SPIBus i rozpoznaje jawnie
  wstrzyknięty transport przed sprawdzaniem fizycznych pinów. Host YAML
  wybiera `endpoint`, nie CLK/MOSI/MISO. Istniejące SPIDevice pozostają bez zmian.
- `sinara_bus` dostarcza model SPI, trasę slot/port i model GPIO z kierunkiem
  oraz inwersją. CS w przykładzie jest pinem tego adaptera.
- Standardowy LM75B korzysta z I2CBus/write_readv. Model obsługuje jego
  write-register/read-temperature i NACK dla nieznanego adresu.
- I²C jest na razie modelem logicznym. Nie ma pakietów mostu I²C przez SPI,
  fizycznego repeated START, timeoutu mostu ani odzyskiwania SDA/SCL.

Lokalne external_components nadpisują tylko SPI/I2C i dodają sinara_bus.
Upstream adapter diff: `upstream-adapter.patch`; wersje/hashe: `provenance.json`.
Własne modele są w `sinara_bus.h` i `i2c_sim.h`. Nie są sterownikami urządzeń
produkcyjnych. Model SPI obsługuje MAX31865, nie dowolny komponent SPI.
ESPHome kod runtime jest GPLv3, Python MIT; zachowano UPSTREAM_LICENSE.txt.

## Następna integracja

1. Uzgodnić API adresowanego SPI z osobnego wątku: wersja, slot/port/device,
   CS, mode, bitrate, bit-order, full-duplex, begin/transfer/end, timeout/error.
2. Zastąpić modele transportem; nie wymyślać drugiego protokołu sprzętowego.
   GPIO i operacje SPI muszą współdzielić rzeczywistą trasę i właściciela busa.
3. Testować atomowość i trzymanie CS przez segmenty, błędy i bezpieczne stany.
   ESPHome SPI nie zwraca błędu dla każdego bajtu; adapter musi ujawnić błąd
   przez stan komponentu i blokadę kolejnych operacji, zamiast publikować zero.
4. Wirtualny I2C oprzeć na rzeczywistym moście i jego sterowniku/protokole.
5. Cross-build rv32 Linux: zapewnić C++20/libstdc++ i zależności POSIX w
   Buildroot. Istniejący Kasli kernel/DDR/Ethernet pozostają bazą.
6. STM najpierw jako serwis Rust + transport; natywny runtime ESPHome na STM
   wymaga osobnej platformy HAL/scheduler/network/preferences/build. Host
   proxy nie zapewnia autonomicznego wykonywania automatyzacji na STM.

Dokumentacja interfejsów: https://developers.esphome.io/architecture/components/spi/
i https://developers.esphome.io/architecture/components/ .

Sprawdzona obecna konfiguracja Kasli `build/linux/.config` ma
`# BR2_TOOLCHAIN_BUILDROOT_CXX is not set`. Przygotowano kandydacki fragment
`kasli/buildroot-cxx.fragment`; nie zastosowano go do wspólnego projektu
i nie przebudowano rootfs/toolchainu. ABI i zależności cross-build nadal
wymagają sprawdzenia.
