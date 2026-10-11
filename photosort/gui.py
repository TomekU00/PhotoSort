import json
import os
import queue
import subprocess
import sys
import threading
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .core import Organizer

def main():
    root = tk.Tk()
    root.title('PhotoSort — porządkowanie kolekcji')
    root.geometry('820x660')
    root.minsize(700, 580)
    box = ttk.Frame(root, padding=22)
    box.pack(fill='both', expand=True)
    ttk.Label(box, text='PhotoSort', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
    ttk.Label(box, text='Najpierw plan. Potem przenoszenie z kontrolą kopii i możliwością wznowienia.').pack(anchor='w', pady=(4, 16))
    variables = {key: tk.StringVar(value=value) for key, value in
                 [('source', ''), ('target', ''), ('pattern', '%Y/%m'), ('scope', 'all'), ('host', ''), ('mode', 'Lokalnie / dysk sieciowy')]}
    def row(label, key, browse=False, choices=None):
        f = ttk.Frame(box)
        f.pack(fill='x', pady=5)
        ttk.Label(f, text=label, width=19).pack(side='left')
        w = ttk.Combobox(f, textvariable=variables[key], values=choices) if choices else ttk.Entry(f, textvariable=variables[key])
        w.pack(side='left', fill='x', expand=True)
        if browse:
            def select():
                path = filedialog.askdirectory()
                if path:
                    variables[key].set(path)
            ttk.Button(f, text='Wybierz…', command=select).pack(side='left', padx=(8, 0))
    row('Tryb', 'mode', choices=['Lokalnie / dysk sieciowy', 'SSH na NAS / Linux'])
    row('Host SSH', 'host')
    row('Źródło', 'source', True)
    row('Cel', 'target', True)
    row('Format folderów', 'pattern', choices=['%Y/%m', '%Y/%m/%d', '%Y-%m', '%Y'])
    row('Zakres', 'scope', choices=['all', 'media', 'photos'])
    ttk.Label(box, text='all: wszystkie pliki · media: zdjęcia i filmy · photos: zdjęcia\n%Y: rok · %m: miesiąc · %d: dzień. W SSH wpisz ścieżki /volume1/…').pack(anchor='w', pady=8)
    jobvar = tk.StringVar(value=str(Path.home()/'.photosort/jobs'/uuid.uuid4().hex[:12]))
    f = ttk.Frame(box)
    f.pack(fill='x', pady=4)
    ttk.Label(f, text='Zadanie / dziennik', width=19).pack(side='left')
    ttk.Entry(f, textvariable=jobvar).pack(side='left', fill='x', expand=True)
    events = queue.Queue()
    stopped = threading.Event()
    state = {'thread': None}
    label = tk.StringVar(value='Gotowy. Wybierz źródło i cel.')
    ttk.Label(box, textvariable=label, wraplength=740).pack(anchor='w', pady=(12, 6))
    bar = ttk.Progressbar(box, maximum=100)
    bar.pack(fill='x')
    output = tk.Text(box, height=7, wrap='word', font=('Consolas', 10))
    output.pack(fill='both', expand=True, pady=10)
    def remote(action):
        job = Path(jobvar.get()).name
        launcher = Path(__file__).parent.parent/'launch.py'
        prefix = [sys.executable, str(launcher)] if launcher.exists() else [sys.executable, '-m', 'photosort']
        args = prefix + ['remote', variables['host'].get(), variables['source'].get(), variables['target'].get(),
                '--job', job, '--format', variables['pattern'].get(), '--scope', variables['scope'].get()]
        if action == 'apply':
            args += ['--resume']
        if os.name == 'nt':
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            messagebox.showinfo('SSH w terminalu', 'Uruchom w terminalu:\n\n'+__import__('shlex').join(args))
    def start(action):
        if state['thread'] and state['thread'].is_alive():
            return
        if variables['mode'].get().startswith('SSH'):
            return remote(action)
        stopped.clear()
        job = jobvar.get()
        settings = {key: value.get() for key, value in variables.items()}
        def worker():
            try:
                org = Organizer(job, events.put, stopped.is_set)
                if action == 'plan':
                    plan = org.plan(settings['source'], settings['target'], settings['pattern'], settings['scope'])
                    events.put({'message': 'Plan: {} plików, {:.2f} GB. Ostrzeżenia metadanych: {}. Plan zapisany w katalogu zadania.'.format(len(plan['files']), plan['bytes']/1e9, len(plan['warnings']))})
                else:
                    org.apply()
            except InterruptedError:
                events.put({'message': 'Zatrzymano. Można wznowić to samo zadanie.'})
            except Exception as e:
                events.put({'message': 'Błąd: '+str(e)})
        state['thread'] = threading.Thread(target=worker, daemon=False)
        state['thread'].start()
    actions = ttk.Frame(box)
    actions.pack(fill='x')
    ttk.Button(actions, text='1. Utwórz plan', command=lambda: start('plan')).pack(side='left')
    ttk.Button(actions, text='2. Przenieś / wznów', command=lambda: start('apply')).pack(side='left', padx=8)
    ttk.Button(actions, text='Zatrzymaj lokalnie', command=stopped.set).pack(side='left')
    def load():
        path = filedialog.askdirectory(title='Katalog istniejącego zadania')
        if path:
            jobvar.set(path)
            p = Path(path)/'plan.json'
            if p.exists():
                config = json.loads(p.read_text(encoding='utf-8'))['config']
                for key in ('source', 'target', 'pattern', 'scope'):
                    variables[key].set(config[key])
    ttk.Button(actions, text='Otwórz zadanie', command=load).pack(side='right')
    def poll():
        while not events.empty():
            s = events.get()
            if 'message' in s:
                text = s['message']
            else:
                speed = s.get('rate_current', s.get('files_per_second', 0))
                eta = s.get('eta_current', s.get('eta_seconds'))
                text = '{} | {:.2f}% | {}/{} | {:.2f} plików/s | pozostało: {}'.format(s['stage'], s['percent'], s['done'], s['total'], speed, str(eta)+' s' if eta is not None else '—')
                bar['value'] = s['percent']
            label.set(text)
            output.insert('end', text+'\n')
            output.see('end')
        root.after(200, poll)
    def close():
        stopped.set()
        if state['thread'] and state['thread'].is_alive():
            label.set('Zatrzymuję operację przed zamknięciem…')
            root.after(200, close)
        else:
            root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    poll()
    root.mainloop()
