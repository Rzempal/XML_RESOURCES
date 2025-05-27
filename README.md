# XML_RESOURCES-
Opis działania aplikacji – Analizator XML z Process Simulate

Aplikacja umożliwia użytkownikowi załadowanie pliku XML wyeksportowanego z programu Process Simulate, zawierającego strukturę drzewa zasobów (resources) linii produkcyjnej. Po przesłaniu pliku na serwer i wprowadzeniu hasła dostępowego, aplikacja przetwarza dane i generuje szczegółowy raport w formie tabeli, przypisany do każdej stacji.

Główne funkcje aplikacji:

1. Odczyt pliku XML
Użytkownik wybiera plik, np. 03_HB1600.xml, który zawiera dane o stacjach, robotach i wykorzystywanych komponentach.


2. Walidacja dostępu
Wymagane jest hasło dostępowe przed wysłaniem danych na serwer (np. do ochrony przed przypadkowym przetworzeniem pliku produkcyjnego).


3. Analiza danych stacji (przykład: 03?HB1600)
Po analizie wyświetlane są informacje w formie tabelarycznej z podziałem na roboty przypisane do stacji, wraz z ich wyposażeniem i komponentami.



Struktura wyników dla każdej stacji:

Nazwa robota: unikalna nazwa robota w danej stacji (np. HB1610IR01)

ApplicationTools:
Wyszczególnienie narzędzi lub aplikacji przypisanych do robota, np. SG_EXT_KLEBEPISTOLE_1, Dock_TS_FLS_SCHRAUBER_....

Components / CompoundResource:
Obecnie jako placeholder (Brak danych) — sekcja do dalszego rozwoju, umożliwiająca integrację z dodatkowymi źródłami danych (np. BOM, MES, PLM).


Zastosowania:

Audyt wykorzystania narzędzi w linii produkcyjnej

Weryfikacja kompletności stacji względem layoutu

Szybkie porównanie zawartości stacji pomiędzy wersjami XML

Podstawa do automatyzacji raportów lub checklist wdrożeniowych



