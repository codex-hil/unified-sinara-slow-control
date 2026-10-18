# Dwie kasety: STM v1.1 i Kasli-DIOT

Plan na późniejszy HIL, bez wykonanych działań sprzętowych. Obie kasety
mają takie same moduły, rewizje i obsadę slotów. Pakiet YAML urządzeń jest
jeden; różnią się pliki połączenia oraz sprawdzone fizyczne profile FPGA.
Identyfikatory kontrolerów, modułów i obrazów zapisujemy w każdym raporcie.

## Procedura

1. Oddzielna blokada każdego kontrolera. Odczyt magic/ABI/build ID i
   weryfikacja kierunków, bez samoczynnej rekonfiguracji aktywnego systemu.
2. Loopback obu kaset równocześnie: linie GPIO, polaryzacja, kierunki595,
   SPI0..7 i odrzucenie SPI na8..15. Mierzyć fizyczne poziomy i czasy.
3. Identyczne sekwencje MAX31855: wszystkie osiem adresów, odczyty,
   uszkodzona głowica i timeout transportu. Temperatury z osobnych głowic
   porównywać z tolerancją czujnika i warunków, nie bitowo.
4. Zapełnienie wszystkich slotowych kolejek, porównanie tagów, liczby
   transakcji i braku przeplotu CS. Prędkości transportów mogą się różnić.
5. Wspólny zewnętrzny trigger po potwierdzeniu ready obu kaset. Mierzyć
   różnicę fizycznych impulsów; niezależne zegary i synchronizatory nie
   gwarantują zgodności cyklowej ani deterministycznego RTIO.
6. Interlock każdego aktywnego slotu, nieaktywny slot, utrata hosta, reset,
   przerwane przesyłanie i odzyskanie. Weryfikować bezpieczne stany na
   pinach, nie wyłącznie rejestry. Bez automatycznego replay po błędzie.

Raport przechowuje osobne wyniki obu kaset i porównanie: PASS/FAIL/NOT_RUN,
czasy, tolerancje, identyfikatory transakcji oraz ślady analizatora.
Uruchomienie jednej kasety nie jest zaliczeniem drugiej.

## Dzisiejszy odpowiednik offline

`tests/test_dual_fabric.py` uruchamia równolegle dwa rzeczywiste modele
RTL (STM z595 i Kasli z bezpośrednim OE), podaje identyczny batch ośmiu
slotów i porównuje liczniki/tagi oraz błędy. Dodatkowy
`tools/test_scf5_esphome.py` sprawdza wspólny YAML ośmiu stock MAX31855 na
obu backendach z syntetycznymi źródłami. Nie stanowi to HIL.
