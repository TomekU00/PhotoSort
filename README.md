# PhotoSort

Prosty program do porządkowania zdjęć, RAW, filmów i pozostałych plików według dat.
Okno działa na Windows i Linux. Te same operacje można uruchamiać z terminala oraz
przez SSH bezpośrednio na NAS. Python 3.8 lub nowszy; GUI wymaga Tkinter.

## Uruchomienie

Z repozytorium:

```sh
python -m pip install .
photosort gui
```

W przygotowanej wersji przenośnej zależności są już dołączone. Windows:
dwuklik `PhotoSort.cmd`; Linux: `sh PhotoSort.sh` (pakiet systemowy `python3-tk`
jest potrzebny tylko dla okna). Python nadal musi być zainstalowany.

W oknie wybierz źródło, cel, zakres i format folderów. **Utwórz plan** niczego nie
przenosi. Sprawdź podsumowanie oraz `plan.json`, potem wybierz **Przenieś / wznów**.
Przycisk **Otwórz zadanie** pozwala wrócić do istniejącego dziennika po restarcie.
Plany i dzienniki domyślnie są w `~/.photosort/jobs/`.

Formaty: `%Y/%m` → `2024/08`, `%Y/%m/%d` → `2024/08/26`, `%Y-%m` → `2024-08`,
`%Y` → `2024`. Możesz wpisać własny format z `%Y`, `%m`, `%d`.
Zakres: `photos`, `media` (zdjęcia i filmy), `all` (wszystkie pliki).

## Terminal — lokalnie lub na zmapowanych dyskach

```sh
photosort plan /folder/zrodlo /folder/cel --job ./zadanie --format '%Y/%m' --scope all
photosort apply --job ./zadanie
photosort status --job ./zadanie
```

W Windows, np.:

```powershell
python launch.py plan "D:\Zdjecia" "Z:\Kolekcja" --job ".\zadanie" --format "%Y/%m"
python launch.py apply --job ".\zadanie"
```

Cel może być podkatalogiem źródła, np. `Desktop` → `Desktop/posegregowane`. Cały folder docelowy jest pomijany przy skanowaniu, również przy kolejnym zadaniu. Źródło i cel nie mogą być identyczne; cel nie może być katalogiem nadrzędnym źródła. Dysk lokalny → udział sieciowy
korzysta z kopiowania i weryfikacji przed usunięciem źródła.

## SSH — operacja na NAS

Wymagany klient `ssh` na komputerze oraz Python 3.8+ na NAS. Standardowe
logowanie kluczem SSH jest wygodniejsze; przy haśle klient SSH sam je odczytuje.
Program nie zapisuje hasła, nie wyłącza sprawdzania klucza serwera i nie wymaga
instalacji pakietów przez pip na NAS.

```sh
photosort remote Tomek@NAS /volume1/photo /volume1/homes --job import1 --format '%Y/%m'
```

To tworzy plan na NAS. Po jego sprawdzeniu:

```sh
photosort remote Tomek@NAS /volume1/photo /volume1/homes --job import1 --resume
photosort remote Tomek@NAS /volume1/photo /volume1/homes --job import1 --status
```

`--apply` przy pierwszej komendzie uruchamia planowanie i przenoszenie kolejno.
Operacja działa w odłączonym procesie na NAS, więc wyłączenie komputera jej nie
przerywa. Log: `~/.photosort/jobs/import1/run.log`; status: `progress.json`.
Okno w trybie SSH otwiera terminal do logowania; postęp zdalny sprawdzaj poleceniem
`--status` lub przez `tail -f` w SSH. Źródło i cel w tym trybie odnoszą się do NAS,
nie do dysków komputera. Komputer → NAS obsługuj jako lokalną operację na udziale
sieciowym. Przycisk zatrzymania w GUI dotyczy wyłącznie zadań lokalnych.

## Daty i pliki towarzyszące

- EXIF DateTimeOriginal / DateTimeDigitized, w tym RAW i bloki CMT w CR3.
- Osadzone XMP oraz Google Takeout `photoTakenTime`, również w podkatalogu `json`.
- MP4/MOV/M4V/3GP: data utworzenia kontenera QuickTime. Niektóre kamery zapisują
  ją jako UTC, inne jako czas lokalny; ta wersja zachowuje wartość z kontenera
  bez zgadywania przesunięcia. Inne filmy mogą użyć daty modyfikacji.
- Gdy brak obsługiwanych metadanych: data modyfikacji w wybranej strefie
  (`Europe/Warsaw` domyślnie). Metoda i ostrzeżenia są zapisane w planie.
- JSON, XMP, DOP i pozostałe rozpoznane pliki edycji są przypinane do zdjęcia.
  Wspólny RAW/JPEG sidecar otrzymuje jednego, deterministycznego właściciela.

## Bezpieczeństwo i wznowienie

Plan jest stały. Kolizje nazw otrzymują wspólny sufiks dla zdjęć i towarzyszących
plików. Istniejące pliki nigdy nie są nadpisywane. Nie ma deduplikacji ani
automatycznego usuwania pustych folderów w tej wersji.

Przenoszenie na tym samym systemie plików używa operacji bez nadpisania.
Między systemami plików program zapisuje kopię tymczasową, sprawdza SHA-256
źródła i kopii, zapisuje stan w dzienniku, a dopiero potem usuwa źródło.
Plan, dziennik i status są zapisywane na dysku z synchronizacją. Po zwykłym
zatrzymaniu użyj ponownie `apply` z tym samym zadaniem. Nie kasuj dziennika.

Po twardej awarii może pozostać `running.lock`: usuń **wyłącznie pusty katalog
blokady**, dopiero po sprawdzeniu, że poprzedni proces nie działa. Niektóre
niejednoznaczne stany zatrzymują zadanie i wymagają sprawdzenia, zamiast usuwać
pliki na podstawie przypuszczenia. Podczas pracy nie zmieniaj plików innymi
programami. Pomijane są dowiązania, `@eaDir`, kosze i katalog systemowy Windows.

`complete` oznacza zakończoną weryfikację wszystkich pozycji. `plan_complete`
oznacza jedynie gotowy plan. Procent dotyczy bieżącego etapu; przy planowaniu
przybliżone tempo i ETA nie są czasem pozostałym do końca przenoszenia.

## Testy

```sh
python -m unittest discover -s tests -v
```

Testy obejmują brak nadpisania, zmienione źródło, kolizje nazw, kopiowanie między
systemami plików, błędną kopię, wznowienie, JSON przy zdjęciu i przerwanie.
CI jest przygotowane dla Windows/Linux i Python 3.8/3.12. Testy lokalne nie
potwierdzają zachowania każdego serwera SMB ani wszystkich odmian metadanych.

## Wybór trybu i logowanie SSH

- **Lokalnie → lokalnie**: wybierz np. `C:\Zdjecia` i `D:\Kolekcja`.
- **Komputer / dysk sieciowy**: wybierz foldery lokalne lub zmapowane udziały.
- **SSH na NAS / Linux**: podaj osobno adres NAS (np. `192.168.68.60`) i użytkownika DSM (np. `Tomek`). Źródło i cel są ścieżkami NAS, np. `/volume1/photo` i `/volume1/homes`.

Kliknij **Sprawdź logowanie SSH**. W terminalu wpisz hasło użytkownika DSM i Enter — znaki hasła nie są wyświetlane. Przy pierwszym połączeniu sprawdź odcisk klucza serwera przed zaakceptowaniem. Wynik `Python 3.8.15` oznacza, że logowanie i dostęp do Pythona działają. Terminal czeka na Enter przed zamknięciem. Linux pokazuje polecenie do uruchomienia we własnym terminalu.

Test logowania nie uruchamia przenoszenia. Tworzenie planu i wznowienie otwierają osobne połączenia SSH, więc mogą ponownie poprosić o hasło. Hasło nie jest zapisywane przez PhotoSort.

## Wybór rozszerzeń

Przycisk **Wybierz rozszerzenia…** otwiera grupy: zdjęcia i grafika, RAW, filmy, pliki towarzyszące, dźwięk, dokumenty, archiwa, katalogi fotograficzne oraz pozostałe formaty z wcześniejszego sortowania. Każdą grupę i każde rozszerzenie można zaznaczyć osobno. Można dopisać własne rozszerzenia, wybrać pliki bez rozszerzenia lub nierozpoznane formaty. **Wszystkie pliki** wyłącza filtr rozszerzeń.

Zapisanie wyboru w oknie ustawia zakres `all`, aby wybrane formaty nie były odrzucone przez poprzedni zakres. Późniejszy wybór zakresu zawęża filtr. Terminal i SSH używają tego samego filtra:

```sh
photosort plan /zrodlo /cel --job ./zadanie --extensions jpg,cr3,mp4
photosort remote Tomek@NAS /volume1/photo /volume1/homes --job import2 --extensions jpg,cr3,mp4
```

`@none` oznacza pliki bez rozszerzenia, `@other` rozszerzenia spoza znanych list. Filtr nie zmienia organizacji docelowej: nadal używany jest wybrany format dat. JSON/XMP i inne rozpoznane pliki towarzyszące wybranym zdjęciom lub filmom są dołączane automatycznie, nawet jeśli nie zaznaczono ich rozszerzenia. Wybór zapisuje się w niezmiennym planie; zmiana filtra wymaga nowego zadania.
