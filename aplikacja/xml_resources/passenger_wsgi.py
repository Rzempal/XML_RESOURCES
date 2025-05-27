import sys
import os

# Dodaj katalog aplikacji do ścieżki Pythona, aby można było zaimportować backend_server
# os.path.dirname(__file__) to katalog, w którym znajduje się ten plik (passenger_wsgi.py)
# Zakładamy, że backend_server.py jest w tym samym katalogu.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Importuj instancję aplikacji Flask z Twojego głównego pliku
# i nazwij ją 'application', ponieważ Passenger jej szuka pod tą nazwą.
try:
    from backend_server import app as application
    # Komunikat logowany do stderr (powinien być widoczny w logach serwera)
    print("PASSENGER_WSGI.PY INFO: Pomyślnie zaimportowano 'app' jako 'application' z backend_server.py.", file=sys.stderr)
    print(f"PASSENGER_WSGI.PY INFO: Uruchamianie z Pythonem w wersji: {sys.version}", file=sys.stderr)
    print(f"PASSENGER_WSGI.PY INFO: Bieżący katalog roboczy (passenger_wsgi.py): {os.getcwd()}", file=sys.stderr)
    print(f"PASSENGER_WSGI.PY INFO: Ścieżka systemowa Pythona (sys.path): {sys.path}", file=sys.stderr)

except ImportError as e:
    error_message = (
        f"PASSENGER_WSGI.PY KRYTYCZNY BŁĄD: Nie można zaimportować aplikacji Flask ('app') z pliku 'backend_server.py'.\n"
        f"Błąd importu: {e}\n"
        f"Katalog aplikacji (APP_DIR): {APP_DIR}\n"
        f"Ścieżka systemowa Pythona (sys.path): {sys.path}\n"
        f"Sprawdź, czy plik 'backend_server.py' istnieje w '{APP_DIR}', nie zawiera błędów składniowych "
        f"oraz czy wszystkie jego zależności (Flask, Flask-CORS) są poprawnie zainstalowane w środowisku wirtualnym aplikacji.\n"
    )
    print(error_message, file=sys.stderr)
    raise # Rzuć wyjątek, aby Passenger wiedział o problemie.
except Exception as e:
    import traceback
    error_message = (
        f"PASSENGER_WSGI.PY KRYTYCZNY BŁĄD: Wystąpił nieoczekiwany błąd podczas importu aplikacji.\n"
        f"Błąd: {e}\n"
        f"Traceback:\n{traceback.format_exc()}\n"
    )
    print(error_message, file=sys.stderr)
    raise

# Phusion Passenger automatycznie powinien używać interpretera Pythona
# ze środowiska wirtualnego skonfigurowanego w panelu Hostido.
# Jawne ustawianie INTERP i os.execl() może nie być potrzebne lub nawet powodować konflikty,
# jeśli Passenger ma własny mechanizm aktywacji venv.
# Jeśli po tej zmianie nadal będą problemy z venv, można wrócić do sekcji INTERP.
