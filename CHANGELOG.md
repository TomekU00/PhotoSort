# Changelog PhotoSort

Historia zmian aplikacji do wersji 0.1.9. Wersje 0.1.2–0.1.5 były etapami rozwoju bez osobnych wydań GitHub.

## Niewydane

## 0.1.9 - 11 października 2026

- Identyczne pliki pod pierwotną lub zaplanowaną nazwą docelową są rozpoznawane po rozmiarze i SHA-256 i przenoszone do Duplikaty w źródle.
- Zachowanie względnych ścieżek oraz plików towarzyszących; wspólna grupa RAW/JPEG jest odkładana tylko wtedy, gdy wszystkie jej multimedia mają kopie w celu.
- Pomijanie folderu Duplikaty przy kolejnych skanowaniach i trwały raport duplicates.json powiązany z planem.
- Obsługa wcześniejszych zapisanych planów oraz wznowienia przerwanego przenoszenia; brak nadpisywania w Duplikaty.
- Osiem testów regresji. Walidacja: 67 testów oraz budowa i test rozpakowanej paczki Windows w CI.

## 0.1.8 - 11 października 2026

- Naprawa końcowego wpisu dziennika bez nowej linii przed dopisywaniem kolejnych zdarzeń.
- Wznowienie przerwanej operacji link/unlink po sprawdzeniu urządzenia i inode obu ścieżek z dziennikiem.
- Pomijanie zerowej daty QuickTime oraz niepełnych i nieobsługiwanych nagłówków mvhd; dalsze szukanie daty w JSON lub mtime.
- Indeks rekordów plików towarzyszących zamiast przeszukiwania całej listy dla każdego JSON/XMP.
- Zapis postępu najwyżej raz na sekundę wewnątrz etapu, z natychmiastowym zapisem zmiany etapu i jego zakończenia. Trwałość dziennika pozostaje bez zmian.

- Refaktor w trzech etapach: testy granic odzyskiwania; osobne moduły dziennika i operacji plikowych; etapy planowania oraz kontroler lokalnych zadań GUI.
- Zachowanie formatu version=1, identyfikatorów planów, zdarzeń dziennika i kolejności trwałych zapisów; bez migracji istniejących zadań.
- Testy GUI, równoległego uruchomienia, zatrzymania i wznowienia oraz samodzielnego payloadu SSH.

- Automatyczna paczka Windows x64 w GitHub Actions, ZIP i SHA-256 jako artefakty oraz załączniki opublikowanych wydań.
- Test rozpakowanych EXE: GUI, CLI, brak nadpisania, pliki towarzyszące i wznowienie tego samego zadania.
- Dokumentacja budowania i publikacji; bez zmian w mechanizmach przenoszenia i dzienniku.

- Walidacja: 59 testów, w tym 17 nowych testów regresji i wydajności; CI Windows/Linux dla Python 3.8/3.12 oraz test rozpakowanych EXE. Testy GUI na Linux bez ekranu są pomijane.

## 0.1.7 - 11 października 2026

- Opcja GUI i CLI `--skip-app-resources`, przekazywana również do planowania przez SSH.
- Rozpoznawanie znanych katalogów programów, środowisk Python, pakietów .app, podglądów Lightroom oraz katalogów z EXE i DLL.
- Wielokrotne `--exclude-dir` do ręcznego wykluczania drzew katalogów wewnątrz źródła.
- Raport przyczyn `skipped_resources` w planie; niezmienność wcześniejszych planów i domyślnie wyłączony filtr.
- Walidacja: 22 testy, w tym pomijanie drzew aplikacji, zachowanie zwykłych zdjęć i przekazywanie opcji do procesu SSH.

## 0.1.6

- Usuwanie pustych katalogów po zakończeniu weryfikacji, od najgłębszych podkatalogów do pustego źródła. Operacja `rmdir` pozostawia katalogi zawierające pliki; cel, korzenie dysków i punkty montowania są chronione.
- Raport sprzątania `cleanup.json` i licznik usuniętych katalogów w statusie oraz GUI.
- Wielokrotny wybór zakresu: zdjęcia/RAW, filmy i dźwięk w dowolnej kombinacji; terminal obsługuje listę rozdzieloną przecinkami.
- Odświeżony interfejs Tkinter/ttk oraz ikona PS.
- Wersja Windows z `PhotoSort.exe`, `PhotoSort-Terminal.exe` i dołączonym środowiskiem Python; skrypty budowania PyInstaller i generowania ikony.
- Walidacja: 18 testów bezpieczeństwa, uruchomienie obu EXE bez PYTHONPATH/PYTHONHOME oraz planowanie i przenoszenie w terminalowym EXE.
- Uzupełnienie wydania: edukacyjna dokumentacja techniczna PDF oraz pełna historia zmian. Tryb SSH aktualnego programu nadal wymaga testu przenoszenia na rzeczywistym NAS.

## 0.1.5

- Ograniczenie nowych planów i wyboru rozszerzeń do multimediów: zdjęć/grafiki, RAW, filmów i dźwięku.
- Usunięcie grup dokumentów, archiwów i innych plików oraz dowolnych nieznanych rozszerzeń.
- Samodzielne JSON nie są wybierane jako multimedia; rozpoznane pliki towarzyszące nadal przenoszą się z wybranymi zdjęciami lub filmami.
- Zachowanie niezmienności już zapisanych planów; doprecyzowanie dokumentacji. Walidacja: 15 testów.

## 0.1.4

- Obsługa celu zagnieżdżonego w źródle, np. Desktop → Desktop/posegregowane.
- Pomijanie całego drzewa docelowego przy skanowaniu, również przy kolejnych zadaniach; zachowanie istniejącej zawartości celu.
- Nadal odrzucane są identyczne źródło i cel oraz cel nadrzędny względem źródła. Walidacja: 14 testów.

## 0.1.3

- Grupowane listy rozszerzeń w GUI, CLI i zadaniach SSH, oparte na wcześniej zebranych formatach.
- Okno wyboru rozszerzeń z przewijaniem, zaznaczaniem poszczególnych pozycji i grupami, w tym RAW oraz audio.
- Parametr `--extensions`; zapis filtra w konfiguracji niezmiennego planu. Automatyczne dołączanie rozpoznanych plików towarzyszących.
- W tej wersji były też grupy dokumentów, archiwów i innych plików; zostały wycofane w 0.1.5. Walidacja: 12 testów.

## 0.1.2

- Wyraźny wybór lokalnie → lokalnie, komputer/udział sieciowy oraz SSH na NAS.
- Osobne pola adresu serwera i użytkownika, przycisk testowania logowania oraz terminalowe `connect`.
- Logowanie przez standardowego klienta OpenSSH bez zapisywania hasła; czytelniejsze błędy SSH i opcja `--wait`, pozostawiająca terminal otwarty.
- Objaśnienie różnicy między ścieżkami komputera i ścieżkami na NAS.

## 0.1.1

- Poprawienie testów dla krótkich ścieżek Windows 8.3 przez rozwiązywanie rzeczywistych ścieżek.
- Sprawdzenie CI na Windows i Linux z Pythonem 3.8 oraz 3.12; aktualizacja paczki przenośnej.

## 0.1.0

- Pierwsza aplikacja GUI i CLI do porządkowania multimediów według dat, lokalnie, na udziałach sieciowych i poprzez zadania SSH.
- Konfigurowalny format folderów oraz odczyt dat EXIF, osadzonego XMP, kontenerów QuickTime i JSON Google Takeout; jawny fallback do daty modyfikacji.
- Plan przed wykonaniem, kontrola źródeł i celów, brak nadpisywania oraz wspólne rozwiązywanie kolizji zdjęć i plików towarzyszących.
- Dziennik operacji, trwały status, zatrzymanie i wznowienie tego samego zadania.
- Przenoszenie w obrębie systemu plików oraz kopiowanie między systemami plików ze sprawdzeniem SHA-256 przed usunięciem źródła.
- Pakiet roboczy wysyłany na NAS z zależnościami; proces zdalny odłączony od sesji komputera. Początkowy zestaw 9 testów bezpieczeństwa.

## Zakres historii

Wcześniejsze jednorazowe skrypty NAS, galeria WWW i pomysły na deduplikację były genezą projektu, ale nie stanowią funkcji PhotoSort 0.1.6. Aplikacja nie oferuje globalnego wyszukiwania duplikatów pod dowolnymi nazwami, galerii GPS, automatycznego pobierania Google Photos ani automatycznego cofnięcia wszystkich operacji.
