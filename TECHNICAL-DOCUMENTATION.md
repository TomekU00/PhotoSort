# PhotoSort 0.1.8 - dokumentacja techniczna i edukacyjna

Stan: 11 października 2026. Dokument opisuje obecną implementację, nie planowane funkcje. Czytelnik pozna drogę pliku od skanowania do zweryfikowanego celu oraz sposób odzyskiwania pracy po przerwaniu.

## 1. Model działania

PhotoSort porządkuje zdjęcia, RAW, filmy i audio w folderach wyznaczonych przez datę. Najpierw tworzy zapisany plan, następnie sprawdza warunki wykonania, przenosi pliki, weryfikuje wynik i usuwa puste katalogi źródłowe. Samo planowanie nie przenosi danych. Format `%Y/%m` daje `2024/04`, `%Y/%m/%d` daje `2024/04/13`, a `%Y-%m` daje `2024-04`.

Skanowanie → odczyt dat → plan → preflight → przenoszenie → weryfikacja → sprzątanie → complete.

Plan określa konkretne ścieżki źródeł i celów. Nie jest przepisywany podczas wznowienia. Zmiana filtrów lub formatu wymaga nowego zadania. Cel może być wewnątrz źródła, np. Desktop/posegregowane; całe jego drzewo zostaje pominięte przy skanowaniu. Identyczne katalogi oraz cel nadrzędny względem źródła są odrzucane.

## 2. Architektura i tryby

`gui.py` zawiera okno Tkinter/ttk. Praca plikowa działa w osobnym wątku, a kolejka przekazuje status do interfejsu. `cli.py` obsługuje polecenia i sygnały zatrzymania. Oba interfejsy korzystają z `core.py`, który koordynuje planowanie i wykonanie. `planning.py` rozdziela walidację konfiguracji, skanowanie, wybór multimediów, przypisywanie plików towarzyszących i rozwiązywanie nazw. `journal.py` odczytuje i trwale zapisuje dziennik. `filesystem.py` odpowiada za kontrolę plików, przenoszenie, kopiowanie i sprzątanie. `tasks.py` prowadzi lokalny wątek GUI na podstawie niezmiennego snapshotu ustawień; klasa `PhotoSortApp` obsługuje widgety i zdarzenia. `metadata.py` wybiera datę. `extensions.py` udostępnia wspólne grupy formatów. `remote.py` przygotowuje pakiet i uruchamia go na serwerze.

Lokalnie → lokalnie oraz komputer → udział sieciowy używają ścieżek widzianych przez komputer. W trybie SSH źródło i cel są bezwzględnymi ścieżkami na NAS. Zamknięcie komputera zatrzymuje pracę lokalną; odłączony proces na NAS może działać dalej. GUI nie jest przeglądarkową galerią zdjęć.

## 3. Skanowanie i trwały plan

Program przechodzi po podkatalogach, odrzuca dowiązania, cel, katalog zadania oraz katalogi pomocnicze takie jak @eaDir i kosze. Zapisuje rozmiar oraz czas modyfikacji pliku. Zakres zdjęcia/RAW, filmy, audio można łączyć. Filtr rozszerzeń dodatkowo ogranicza wybrane kategorie i przyjmuje znane formaty multimedialne. Rozpoznane pliki towarzyszące są dołączane niezależnie od tego filtra.

`plan.json` zawiera konfigurację, listę par source/destination, size, mtime, date_source, ostrzeżenia, pominięcia, sumę bajtów i odwiedzone katalogi źródła. Konfiguracja istniejącego planu musi odpowiadać konfiguracji zadania. Wznowienie używa tego samego planu i dziennika.

Przed przenoszeniem preflight sprawdza granice ścieżek, typ pliku, jego rozmiar i mtime. Zmiana źródła po planowaniu zatrzymuje pracę. Istniejący cel nie jest dowodem wcześniejszego sukcesu: wymagany jest zgodny zapis dziennika i kontrola pliku. Plan oraz status zapisują się przez plik tymczasowy, flush, fsync i atomową podmianę.

## 4. Skąd pochodzi data

Dla zdjęć program próbuje EXIF DateTimeOriginal, Image DateTimeOriginal, potem DateTimeDigitized. CR3 ma dodatkowy odczyt bloków CMT1/CMT2 w pierwszych 2 MB. Następnie sprawdzane są daty osadzonego XMP w pierwszych 2 MB: DateTimeOriginal, DateCreated i CreateDate. Nie każda odmiana formatu jest czytana przez ExifRead.

Dla MP4, MOV, M4V, 3GP i 3G2 odczytywany jest atom mvhd w kontenerze QuickTime z epoką 1904. Duża sekcja obrazu filmu jest pomijana przez seek. Wartość pozostaje bez konwersji strefy: kamery zapisują ją niejednoznacznie jako UTC albo czas lokalny.

Jeżeli powyższe nie dają daty, program szuka powiązanego JSON Google Takeout i photoTakenTime.timestamp, także w podfolderze json oraz plikach supplemental-metadata. Znacznik czasu jest przeliczany do wybranej strefy, domyślnie Europe/Warsaw. Ostatnim wyborem jest mtime pliku w tej strefie. Metoda trafia do date_source w planie.

Daty w nazwie pliku nie są analizowane. Zewnętrzny XMP jest przenoszony jako plik towarzyszący, ale jego data nie jest obecnie parsowana. Audio nie ma parsera dat ID3. GPS nie uczestniczy w sortowaniu. Dlatego nazwa zawierająca 20230604 nie gwarantuje folderu 2023/06.

## 5. Pliki towarzyszące i kolizje

JSON, XMP, DOP, ACR, AAE, PP3, COS, COF i NKSC mogą zachowywać informacje eksportu lub edycji. Program przypina rozpoznane pliki do zdjęcia lub filmu: np. IMG.JPG.json, plik o wspólnej bazie nazwy albo JSON z podfolderu json. Plik towarzyszący dziedziczy folder daty właściciela. Wspólny sidecar RAW/JPEG ma jednego deterministycznego właściciela.

Istniejące nazwy są rezerwowane bez rozróżniania wielkości liter. Przy kolizji grupa otrzymuje wspólny sufiks oparty na skrócie identyfikatora grupy, w razie potrzeby z dalszym numerem. Program nie nadpisuje istniejącego celu. Podczas apply moduł duplicates.py porównuje rozmiar i SHA-256 źródła oraz pliku pod pierwotną nazwą w folderze daty albo zaplanowaną nazwą z sufiksem. Gdy wszystkie multimedia grupy są identyczne z istniejącymi kopiami, grupa z sidecarami trafia do źródło/Duplikaty z zachowaniem względnych ścieżek. Folder powstaje przy pierwszym przeniesieniu i jest pomijany przy skanowaniu. Dla częściowo powielonej grupy RAW/JPEG zachowane są dotychczasowe reguły kolizji. Zajęta ścieżka w Duplikaty zatrzymuje pracę. Trwały duplicates.json wiąże decyzje z identyfikatorem niezmienionego planu. FileMover i istniejący dziennik obsługują przenoszenie oraz wznowienie do wybranej lokalizacji. Po rozpoczęciu wykonania grupy jej lokalizacje nie są zmieniane. Sprawdzenie odbywa się przy preflight oraz przed rozpoczęciem grupy; kolizja powstała w samej operacji rename nadal zatrzymuje zadanie bez nadpisania. Mechanizm obejmuje również wcześniejsze plany, ale nie zmienia operacji już rozpoczętych w dzienniku. Nie szuka kopii pod dowolnymi nazwami w całej kolekcji.

## 6. Przenoszenie i kontrola zawartości

Na tym samym systemie plików operacja zmienia lokalizację pliku bez przepisywania obrazu. Windows używa rename bez nadpisania. Linux korzysta z renameat2/RENAME_NOREPLACE, a gdy mechanizm nie jest dostępny, z wyłącznego utworzenia dowiązania twardego i usunięcia starego wpisu. Dziennik zachowuje dane potrzebne do rozpoznania przeniesionego pliku po awarii.

Między systemami plików po błędzie EXDEV program przechodzi do kopiowania. Sprawdza wolne miejsce z rezerwą 64 MB, tworzy wyłączny plik .part należący do zadania, kopiuje porcjami 4 MB, synchronizuje zapis i zachowuje statystyki pliku. Porównuje rozmiar, mtime i SHA-256 ponownie odczytanego źródła oraz kopii. Dopiero po zgodności publikuje finalny cel, zapisuje stan i usuwa źródło.

SHA-256 potwierdza zgodność bajtów, nie zdrowie oryginalnego JPEG ani jego poprawną datę. Kontrola rozmiaru i mtime nie jest pełnym hashowaniem. Program nie dekoduje wszystkich zdjęć podczas zwykłego przenoszenia. Badanie uszkodzeń obrazu wymaga osobnego pełnego odczytu przez dekoder; błąd aplikacji Windows przy otwieraniu sam w sobie nie dowodzi uszkodzenia pliku.

## 7. Dziennik, zatrzymanie i wznowienie

`journal.jsonl` jest sekwencją trwałych zdarzeń. Identyfikator planu to SHA-256 jego kanonicznej reprezentacji JSON. Zdarzenia intent, copying, copy_ready, copied i moved opisują kolejne punkty operacji. Każdy zapis dziennika jest synchronizowany. Niekompletny ostatni wiersz po awarii zostaje zabezpieczony i odcięty; uszkodzenie wewnątrz dziennika zatrzymuje zadanie.

Stan intent oznacza zamiar; copying pozwala rozpoznać własny plik tymczasowy; copy_ready wskazuje sprawdzoną kopię gotową do publikacji; copied oznacza opublikowany cel przed zakończeniem usuwania źródła; moved zakończoną operację. Przy wznowieniu program rekonstruuje ostatni stan każdego źródła i sprawdza istniejące pliki. Niejednoznaczny stan zatrzymuje pracę zamiast zgadywać.

Zatrzymaj lokalnie przyciskiem lub Ctrl+C i uruchom ponownie apply dla tego samego zadania. Nie usuwaj planu ani dziennika. `running.lock` chroni przed równoległym wykonaniem. Po twardej awarii blokada może pozostać; dopiero po potwierdzeniu, że proces nie działa, można usunąć sam pusty katalog blokady. Program nie ma automatycznego globalnego undo.

## 8. Status, weryfikacja i puste foldery

`progress.json` jest bieżącym snapshotem; log zawiera historię komunikatów. Etapy to scanning, plan_complete, preflight, moving, verifying, cleanup i complete, a przy przerwaniu paused lub failed. 100% moving oznacza koniec listy przenosin, nie całego zadania. Skanowanie nie zna jeszcze ostatecznej liczby pozycji. Done liczy również pliki towarzyszące.

Podczas moving rate_current jest średnią prędkością bieżącego przebiegu po kontroli wstępnej, a ETA jest oszacowaniem z pozostałych pozycji. Rozmiary plików, cache i opóźnienia sieci mogą zmieniać wynik. Weryfikacja sprawdza brak starych źródeł i poprawność celów; jej raport to verification.json.

Dopiero po weryfikacji sprzątanie odwiedza katalogi od najgłębszych. Sprawdza granice źródła i wywołuje wyłącznie rmdir. Katalog z choćby jednym plikiem pozostaje. Cel, jego podkatalogi, dowiązania i korzenie dysków/udziałów lub punkty montowania są chronione. Samo źródło może zniknąć, gdy jest puste. cleanup.json zawiera usunięte ścieżki i ostrzeżenia; brak uprawnienia nie powoduje kasowania zawartości inną metodą.

## 9. SSH na NAS

`progress.json` jest migawką: wewnątrz tego samego etapu zapis następuje najwyżej raz na sekundę, przy kolejnym zgłoszeniu postępu. Zmiana etapu, jego zakończenie, błąd i pauza są zapisywane od razu. Powiadomienia GUI i CLI nadal otrzymują każdą aktualizację. Ograniczenie nie dotyczy `journal.jsonl`: każde zdarzenie operacji nadal przechodzi flush/fsync. Nie jest wymagany timer ani dodatkowy wątek.

Komputer wymaga standardowego klienta ssh, a serwer powłoki Unix i Python 3.8+. PhotoSort tworzy pakiet kodu z ExifRead, pytz i plikami stref czasowych. Wysyła go przez SSH, rozpakowuje do cache aplikacji na NAS i uruchamia odłączony proces z logiem. Poszczególne kroki mogą otwierać więcej niż jedno połączenie i ponawiać pytanie o hasło.

Hasło obsługuje klient OpenSSH; aplikacja go nie zapisuje i nie wyłącza kontroli klucza serwera. Przycisk testu logowania sprawdza dostęp i wersję Python. Zadanie serwera zapisuje pliki w ~/.photosort/jobs/ID. Wyłączenie komputera nie zatrzymuje już uruchomionego procesu NAS. Zatrzymanie GUI dotyczy pracy lokalnej; nie steruje odłączonym procesem zdalnym.

Praca przy samych dyskach NAS może ominąć koszt wielu małych odczytów przez SMB. Nie gwarantuje to przewagi: ograniczeniami bywają CPU, dysk, metadane i równoległe indeksowanie. Aktualny tryb SSH PhotoSort wymaga jeszcze testu przenosin na rzeczywistym NAS; doświadczenia z wcześniejszymi skryptami nie zastępują tego testu.

## 10. Uruchomienie i ćwiczenie

Windows: rozpakuj całą paczkę wydania i uruchom PhotoSort.exe. Obok zachowaj PhotoSort-Terminal.exe oraz katalog _internal. Pliki build/gui są produktami pośrednimi budowania, nie paczką dla użytkownika; uruchomienie stamtąd może powodować błąd ładowania python312.dll. Wersja EXE ma Python dołączony. SSH nadal wymaga zewnętrznego klienta ssh.

Wersja źródłowa Windows/Linux wymaga Python 3.8+, ExifRead i pytz. Zainstaluj przez `python -m pip install .`, potem `photosort gui`. GUI na Linux wymaga Tkinter, zwykle pakietu python3-tk. Terminal nie wymaga okna.

Przykład terminala Linux:

```sh
photosort plan /dane/zrodlo /dane/cel --job ./zadanie --format '%Y/%m' --scope photos,video
photosort apply --job ./zadanie
photosort status --job ./zadanie
```

Przykład terminala Windows w rozpakowanej paczce:

```powershell
.\PhotoSort-Terminal.exe plan "D:\Zdjecia" "Z:\Kolekcja" --job ".\zadanie" --format "%Y/%m"
.\PhotoSort-Terminal.exe apply --job ".\zadanie"
```

SSH uruchamiane na komputerze:

```sh
photosort connect uzytkownik@NAS
photosort remote uzytkownik@NAS /volume1/photo /volume1/homes --job import1
photosort remote uzytkownik@NAS /volume1/photo /volume1/homes --job import1 --resume
photosort remote uzytkownik@NAS /volume1/photo /volume1/homes --job import1 --status
```

Ćwiczenie: przygotuj kopie dwóch zdjęć z taką samą nazwą w różnych podfolderach, JSON jednego zdjęcia i nieobjęty filtrem dokument. Utwórz plan i sprawdź date_source, docelowe nazwy oraz sidecar. Wykonaj przenoszenie, obejrzyj verification.json i cleanup.json. Dokument pozostanie, więc jego katalog nie zostanie usunięty. Następnie wykonaj apply drugi raz dla tego samego zadania i sprawdź wznowienie.

## 11. Testy, ograniczenia i źródła

Dla 0.1.6 wykonano 18 testów bezpieczeństwa oraz test uruchomienia obu EXE bez PYTHONPATH/PYTHONHOME i plan/przenoszenie terminalowego EXE. Wcześniejsza konfiguracja CI obejmuje Windows/Linux i Python 3.8/3.12; nie stanowi to deklaracji wyniku każdego późniejszego uruchomienia CI. Nie jest to audyt wszystkich formatów ani test wszystkich konfiguracji SMB/NAS.

Nie ma globalnej deduplikacji ani wyszukiwania podobnych obrazów, galerii GPS, automatycznego pobierania Google Photos, automatycznego backupu, globalnego cofania ani importu zadań wcześniejszych skryptów NAS. Rozpoznane rozszerzenie nie gwarantuje odczytu dat każdej odmiany pliku. Nie zmieniaj plików równolegle podczas operacji.

Źródłem opisu jest kod repozytorium PhotoSort: core.py, metadata.py, extensions.py, remote.py, gui.py, cli.py, test_safety.py oraz skrypty budowania. Punkt odniesienia wydania: https://github.com/TomekU00/PhotoSort/releases/tag/v0.1.6 . Pełna historia funkcji 0.1.0–0.1.7 znajduje się w CHANGELOG.md i opisie wydania. Wersje 0.1.2–0.1.5 były wersjami rozwojowymi bez osobnych wydań GitHub.

## 12. Automatyczne budowanie i publikacja

`.github/workflows/windows.yml` uruchamia pełny zestaw testów bezpieczeństwa przed budową PyInstaller. `requirements-build.txt` przypina wersje narzędzi budowania; zależności aplikacji nadal wynikają z `pyproject.toml`. `package-windows.ps1` pakuje oba EXE, `_internal` i dokumentację oraz oblicza SHA-256 archiwum. `scripts/smoke-windows.py` sprawdza sumę, rozpakowuje paczkę w katalogu tymczasowym i uruchamia ją poza repozytorium bez PYTHONPATH/PYTHONHOME. Sprawdza pozostawienie źródła przy kolizji, przeniesienie multimediów i sidecara, zachowanie dokumentu oraz niezmienność planu i dziennika po ponownym apply. Sprawdza także start GUI.

Publikacja artefaktu Actions następuje po wszystkich testach. Opublikowanie wydania z tagiem `v<wersja z pyproject.toml>` dodatkowo uruchamia osobny job załączający ZIP i checksum do tego wydania. Job budowy ma tylko odczyt repozytorium, a job publikacji `contents: write`. Nie są pakowane zadania użytkownika ani dane testowe. Workflow nie zmienia algorytmów przenoszenia, formatu planu, dziennika i blokady. Testy CI nie zastępują testu na rzeczywistym SMB/NAS.

## 13. Refaktor w trzech etapach

Najpierw rozszerzono testy odzyskiwania na dotychczasowym kodzie: awarie po copy_ready, po publikacji kopii przed copied, po copied oraz po usunięciu źródła przed moved, a także po rename przed moved. Testy sprawdzają uszkodzony środek dziennika, zabezpieczenie niepełnego ostatniego wiersza, obcy plan, blokadę drugiego procesu i kolizję po preflight. Symulowane przerwanie procesu nie jest testem fizycznej awarii zasilania lub każdego serwera SMB.

Drugi etap wydzielił dziennik i operacje plikowe, zachowując kolejność flush/fsync, publikacji celu, zdarzeń i usuwania źródła. Trzeci rozdzielił etapy planowania i obsługę GUI. Format planu nadal ma version=1, identyfikator pozostaje SHA-256 tej samej reprezentacji JSON, a nazwy stanów i plików zadania nie zmieniają się. Nie jest potrzebna migracja wcześniejszych zadań.

Przed i po refaktorze porównano bajtowo pięć planów na tym samym zbiorze syntetycznym (domyślne opcje, zakres zdjęć, filtr rozszerzeń, pomijanie zasobów, wykluczenie katalogu). Sprawdzono także wznowienie przez nowy kod zadania przerwanego w copy_ready przez kod sprzed refaktoru. Test payloadu SSH uruchamia rozpakowany pakiet przez Python -S poza repozytorium, bez zależności z site-packages. Testy kontrolera zadań sprawdzają zatrzymanie, wznowienie i odmowę drugiego uruchomienia. Testy widgetów Tk są wykonywane, gdy dostępny jest ekran; na Linux bez ekranu są pomijane. Windows dodatkowo przechodzi test rozpakowanych EXE.
