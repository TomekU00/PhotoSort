# PhotoSort

## Pomijanie zasobów aplikacji

W oknie zaznacz **Pomijaj zasoby aplikacji i podglądy Lightroom** przed utworzeniem nowego planu. Domyślnie opcja jest wyłączona, aby starsze zadania zachowały dotychczasowy wybór. Terminal:

```powershell
photosort plan "C:\Users\uzytkownik\Desktop" "Z:\Kolekcja" --job ./nowe-zadanie --skip-app-resources --exclude-dir "Moja aplikacja" --exclude-dir "Miniatury"
```

SSH (polecenie na komputerze, katalogi na NAS):

```sh
photosort remote uzytkownik@NAS /volume1/photo /volume1/homes --job import2 --skip-app-resources --exclude-dir 'Moja aplikacja'
```

`--skip-app-resources` pomija znane katalogi instalacji, środowisk i pakietów (m.in. Program Files, Windows, node_modules, .venv, .git), pakiety .app, podglądy .lrdata, katalogi z pyvenv.cfg oraz katalogi zawierające jednocześnie EXE i DLL. Nie pomija zdjęć tylko dlatego, że są małe albo mają rozszerzenie PNG. Rozpoznawanie jest heurystyczne: nie wykrywa każdej aplikacji. `--exclude-dir` można podawać wielokrotnie, jako ścieżkę względną wobec źródła lub bezwzględną wewnątrz źródła. Pomijane jest całe drzewo katalogu. Przyczyny zapisuje `skipped_resources` w `plan.json`. Istniejące plany nie zmieniają się; utwórz nowe zadanie, aby zastosować filtr.

## O aplikacji

Prosty program do porządkowania zdjęć, RAW, filmów i dźwięku według dat.
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
Zakres: `photos` (zdjęcia/RAW), `media` (zdjęcia i filmy), `audio` (dźwięk), `multimedia` (wszystkie obsługiwane multimedia).

## Terminal — lokalnie lub na zmapowanych dyskach

```sh
photosort plan /folder/zrodlo /folder/cel --job ./zadanie --format '%Y/%m' --scope multimedia
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
plików. Istniejące pliki nigdy nie są nadpisywane. Nie ma deduplikacji. Po zakończeniu weryfikacji program usuwa puste katalogi źródłowe od najgłębszych do samego źródła. Używa wyłącznie `rmdir`, więc katalog zawierający pliki pozostaje. Folder docelowy i główne katalogi dysków, udziałów oraz punktów montowania są chronione. Wynik sprzątania jest zapisany w `cleanup.json`.

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

Przycisk **Wybierz rozszerzenia…** otwiera tylko cztery grupy: zdjęcia i grafika, RAW, filmy oraz dźwięk. Można zaznaczyć grupy lub pojedyncze formaty. **Wszystkie multimedia** wyłącza szczegółowy filtr, ale nadal pomija dokumenty, archiwa, programy, samodzielne JSON/XMP oraz nierozpoznane formaty. Pliki te pozostają w źródle.

Zapisanie wyboru ustawia zakres `multimedia`; późniejszy wybór zakresu zawęża filtr. Terminal i SSH korzystają z tej samej listy:

```sh
photosort plan /zrodlo /cel --job ./zadanie --extensions jpg,cr3,mp4,mp3
photosort remote Tomek@NAS /volume1/photo /volume1/homes --job import2 --extensions jpg,cr3,mp4,mp3
```

JSON/XMP i inne rozpoznane metadane wybranych zdjęć lub filmów są automatycznie dołączane. Nie są osobną kategorią do sortowania. Filtr zapisuje się w planie; zmiana wyboru wymaga nowego zadania. Dawne plany pozostają niezmienione — po aktualizacji utwórz nowy plan, aby zastosować ograniczenie do multimediów.

## Windows EXE i zakres wielokrotnego wyboru

Rozpakuj paczkę Windows i uruchom **PhotoSort.exe**. Python i zależności są dołączone. **PhotoSort-Terminal.exe** jest wersją konsolową oraz otwiera widoczne logowanie SSH z okna; zachowaj go obok głównego EXE i katalogu `_internal`.

Zakres to niezależne pola **Zdjęcia i RAW**, **Filmy**, **Dźwięk**. Możesz wybrać dowolną kombinację. W terminalu: `--scope photos,video` lub `--scope video,audio`. Wybór rozszerzeń dodatkowo zawęża zakres.

Po pomyślnej weryfikacji przenosin program sprząta puste katalogi źródłowe, również źródło, jeżeli jest puste. Pliki niewybrane i dokumenty pozostają, więc zawierające je foldery nie zostaną usunięte. Katalog docelowy wewnątrz źródła jest chroniony.

Budowa EXE: `python -m pip install . pyinstaller pillow`, a następnie `powershell -File build-windows.ps1`. Ikona PS jest lokalnym rysunkiem; źródła i skrypt jej generowania są w `PhotoSort.svg` i `make-icon.py` (ICO/PNG powstają w `assets/`).

## Automatyczna paczka Windows

Workflow **Windows package** buduje Windows x64 na Pythonie 3.12 przy push do `main`, pull request, ręcznym uruchomieniu oraz opublikowaniu wydania. Najpierw uruchamia testy bezpieczeństwa, potem buduje oba EXE, tworzy `PhotoSort-<wersja>-windows-x64.zip` i plik `.zip.sha256`. Rozpakowana paczka przechodzi test GUI, terminala, planowania, kolizji i wznowienia bez PYTHONPATH/PYTHONHOME. Artefakt jest dostępny w zakładce Actions przez 30 dni.

Aby dodać paczkę do Releases, opublikuj wydanie z tagiem odpowiadającym `pyproject.toml`, np. `v0.1.7`. Workflow dołącza ZIP i sumę SHA-256 dopiero po testach. Nie nadpisuje istniejących assetów; ponowna publikacja wymaga świadomego usunięcia poprzednich plików w wydaniu. Nie wymaga osobnego tokenu: tylko job publikacji otrzymuje `contents: write`.

Budowanie lokalne w PowerShell:

```powershell
python -m pip install . -r requirements-build.txt
python -m unittest discover -s tests -v
./build-windows.ps1
./package-windows.ps1
python scripts/smoke-windows.py dist/PhotoSort-0.1.7-windows-x64.zip
```

Używaj świeżego katalogu wyjściowego. Rozpakuj cały ZIP, zachowując strukturę `PhotoSort/`. Paczka nie zawiera zadań użytkownika; aktualizacja nie zmienia planów i dzienników w `~/.photosort/jobs/`. Wznawiaj przez `apply --job` dla tego samego zadania. Test paczki korzysta wyłącznie z tymczasowych danych syntetycznych.
