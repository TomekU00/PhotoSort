import argparse
import json
import signal
import sys
from pathlib import Path
from .core import Organizer

def main(argv=None):
    parser = argparse.ArgumentParser(prog='photosort', description='PhotoSort — planowanie i przenoszenie według dat')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('gui', help='Proste okno')
    p = sub.add_parser('plan', help='Zapisz plan bez przenoszenia')
    p.add_argument('source')
    p.add_argument('target')
    p.add_argument('--job', required=True)
    p.add_argument('--format', default='%Y/%m', dest='pattern')
    p.add_argument('--scope', choices=['photos', 'media', 'audio', 'multimedia'], default='multimedia')
    p.add_argument('--timezone', default='Europe/Warsaw')
    p.add_argument('--extensions', help='Lista rozszerzeń, np. jpg,cr3,mp4,mp3 (wyłącznie multimedia)')
    for command in ('apply', 'status'):
        p = sub.add_parser(command)
        p.add_argument('--job', required=True)
    c = sub.add_parser('connect', help='Sprawdź logowanie SSH i Python na serwerze')
    c.add_argument('host')
    c.add_argument('--wait', action='store_true', help='Pozostaw terminal otwarty do naciśnięcia Enter')
    p = sub.add_parser('remote', help='Uruchom na komputerze/NAS przez SSH; wymagany Python 3.8+')
    p.add_argument('host', help='np. Tomek@192.168.68.60')
    p.add_argument('source', help='Bezwzględna ścieżka na serwerze')
    p.add_argument('target')
    p.add_argument('--job', required=True, help='Identyfikator zadania na serwerze')
    p.add_argument('--format', default='%Y/%m', dest='pattern')
    p.add_argument('--scope', choices=['photos', 'media', 'audio', 'multimedia'], default='multimedia')
    p.add_argument('--timezone', default='Europe/Warsaw')
    p.add_argument('--extensions', help='Lista rozszerzeń, np. jpg,cr3,mp4,mp3 (wyłącznie multimedia)')
    p.add_argument('--apply', action='store_true', help='Po planowaniu rozpocznij przenoszenie')
    p.add_argument('--resume', action='store_true', help='Uruchom apply dla istniejącego planu')
    p.add_argument('--wait', action='store_true', help='Pozostaw terminal otwarty do naciśnięcia Enter')
    p.add_argument('--status', action='store_true', help='Odczytaj status zadania')
    args = parser.parse_args(argv)
    if args.command == 'gui':
        from .gui import main as gui
        return gui()
    if args.command in ('remote', 'connect'):
        from .remote import run, connect
        try:
            return connect(args.host) if args.command == 'connect' else run(args)
        except Exception as e:
            print('Błąd SSH: '+str(e), file=sys.stderr)
            raise SystemExit(1)
        finally:
            if args.wait:
                input('Naciśnij Enter, aby zamknąć terminal…')
    if args.command == 'status':
        print((Path(args.job).expanduser()/'progress.json').read_text(encoding='utf-8'))
        return
    stopped = [False]
    def stop(*unused):
        stopped[0] = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    def notify(s):
        print(json.dumps(s, ensure_ascii=False), flush=True)
    org = Organizer(args.job, notify, lambda: stopped[0])
    try:
        if args.command == 'plan':
            org.plan(args.source, args.target, args.pattern, args.scope, args.timezone, args.extensions)
        else:
            org.apply()
    except InterruptedError:
        print('Zatrzymano bezpiecznie. Wznowienie: photosort apply --job '+str(args.job), file=sys.stderr)
        raise SystemExit(130)
    except Exception as e:
        print('Błąd: '+str(e), file=sys.stderr)
        raise SystemExit(1)
