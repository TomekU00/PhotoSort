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
from .extensions import GROUPS, normalize_extensions

def main():
    root = tk.Tk()
    root.title('PhotoSort — porządkowanie kolekcji')
    root.geometry('860x780')
    root.minsize(700, 580)
    box = ttk.Frame(root, padding=22)
    box.pack(fill='both', expand=True)
    ttk.Label(box, text='PhotoSort', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
    ttk.Label(box, text='Najpierw plan. Potem przenoszenie z kontrolą kopii i możliwością wznowienia.').pack(anchor='w', pady=(4, 16))
    variables = {key: tk.StringVar(value=value) for key, value in
                 [('source', ''), ('target', ''), ('pattern', '%Y/%m'), ('scope', 'multimedia'), ('address', ''), ('user', ''), ('mode', 'Lokalnie → lokalnie')]}
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
    row('Tryb', 'mode', choices=['Lokalnie → lokalnie', 'Komputer / dysk sieciowy', 'SSH na NAS / Linux'])
    row('Adres NAS / SSH', 'address')
    row('Użytkownik SSH', 'user')
    row('Źródło', 'source', True)
    row('Cel', 'target', True)
    row('Format folderów', 'pattern', choices=['%Y/%m', '%Y/%m/%d', '%Y-%m', '%Y'])
    row('Zakres', 'scope', choices=['multimedia', 'media', 'photos', 'audio'])
    extension_state = {'values': None}
    extension_label = tk.StringVar(value='Wszystkie multimedia (według zakresu)')
    def choose_extensions():
        dialog = tk.Toplevel(root)
        dialog.title('Wybierz rozszerzenia')
        dialog.geometry('760x580')
        dialog.transient(root)
        dialog.grab_set()
        ttk.Label(dialog, text='Zaznacz grupę lub pojedyncze rozszerzenia. Możesz wybrać kilka grup.', padding=12).pack(anchor='w')
        group_choice = ttk.Combobox(dialog, values=list(GROUPS), state='readonly')
        group_choice.pack(fill='x', padx=12, pady=(0,8))
        group_choice.current(0)
        ttk.Style(dialog).layout('Extensions.TNotebook.Tab', [])
        tabs = ttk.Notebook(dialog, style='Extensions.TNotebook')
        group_choice.bind('<<ComboboxSelected>>', lambda event: tabs.select(group_choice.current()))
        tabs.pack(fill='both', expand=True, padx=12)
        selected = extension_state['values']
        toggles = {}
        for name, values in GROUPS.items():
            page = ttk.Frame(tabs)
            tabs.add(page, text=name)
            canvas = tk.Canvas(page, highlightthickness=0)
            scrollbar = ttk.Scrollbar(page, orient='vertical', command=canvas.yview)
            scrollbar.pack(side='right', fill='y')
            canvas.pack(side='left', fill='both', expand=True)
            canvas.configure(yscrollcommand=scrollbar.set)
            panel = ttk.Frame(canvas, padding=10)
            canvas.create_window((0,0), window=panel, anchor='nw')
            panel.bind('<Configure>', lambda event, view=canvas: view.configure(scrollregion=view.bbox('all')))
            local = []
            for n, ext in enumerate(sorted(values)):
                value = tk.BooleanVar(value=selected is None or ext in selected)
                toggles[ext] = value
                local.append(value)
                text = ext.upper()
                ttk.Checkbutton(panel, text=text, variable=value).grid(row=n//5+1, column=n%5, sticky='w', padx=8, pady=4)
            controls = ttk.Frame(panel)
            controls.grid(row=0, column=0, columnspan=5, sticky='w', pady=(0,10))
            def set_group(items, flag):
                for item in items:
                    item.set(flag)
            ttk.Button(controls, text='Zaznacz grupę', command=lambda items=local: set_group(items, True)).pack(side='left')
            ttk.Button(controls, text='Odznacz grupę', command=lambda items=local: set_group(items, False)).pack(side='left', padx=8)
        ttk.Label(dialog, text='JSON/XMP i pozostałe rozpoznane pliki towarzyszące wybranym zdjęciom jadą razem z nimi.', wraplength=720).pack(anchor='w', padx=12, pady=8)
        footer = ttk.Frame(dialog, padding=12)
        footer.pack(fill='x')
        def confirm():
            try:
                values = [ext for ext, value in toggles.items() if value.get()]
                extension_state['values'] = normalize_extensions(values)
                variables['scope'].set('multimedia')
                extension_label.set('Wybrane rozszerzenia: '+str(len(extension_state['values'])))
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror('Rozszerzenia', str(e), parent=dialog)
        def all_files():
            extension_state['values'] = None
            extension_label.set('Wszystkie multimedia (według zakresu)')
            dialog.destroy()
        ttk.Button(footer, text='Odznacz wszystko', command=lambda: [v.set(False) for v in toggles.values()]).pack(side='left')
        ttk.Button(footer, text='Wszystkie multimedia', command=all_files).pack(side='left', padx=8)
        ttk.Button(footer, text='Zapisz wybór', command=confirm).pack(side='right')
    extension_row = ttk.Frame(box)
    extension_row.pack(fill='x', pady=5)
    ttk.Button(extension_row, text='Wybierz rozszerzenia…', command=choose_extensions).pack(side='left')
    ttk.Label(extension_row, textvariable=extension_label).pack(side='left', padx=12)
    ttk.Label(box, text='multimedia: zdjęcia, filmy i dźwięk · media: zdjęcia i filmy · photos: zdjęcia · audio: dźwięk\n%Y: rok · %m: miesiąc · %d: dzień. W SSH wpisz ścieżki /volume1/…').pack(anchor='w', pady=8)
    ttk.Label(box, text='Lokalnie → lokalnie: wybierz dwa foldery na komputerze.\nSSH: wpisz adres NAS i nazwę użytkownika DSM. Hasło wpisujesz w osobnym terminalu;\nznaki hasła nie są widoczne. Przy pierwszym połączeniu sprawdź klucz serwera.').pack(anchor='w', pady=4)
    actions_ssh = ttk.Frame(box)
    actions_ssh.pack(fill='x')
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
    def ssh_host():
        from .remote import make_host
        return make_host(variables['address'].get(), variables['user'].get())
    def terminal(args):
        if os.name == 'nt':
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            messagebox.showinfo('SSH w terminalu', 'Uruchom w terminalu:\n\n'+__import__('shlex').join(args))
    def prefix():
        launcher = Path(__file__).parent.parent/'launch.py'
        return [sys.executable, str(launcher)] if launcher.exists() else [sys.executable, '-m', 'photosort']
    def connect():
        try:
            terminal(prefix()+['connect', ssh_host(), '--wait'])
        except Exception as e:
            messagebox.showerror('SSH', str(e))
    ttk.Button(actions_ssh, text='Sprawdź logowanie SSH', command=connect).pack(anchor='w')
    def remote(action):
        job = Path(jobvar.get()).name
        args = prefix() + ['remote', ssh_host(), variables['source'].get(), variables['target'].get(),
                '--wait', '--job', job, '--format', variables['pattern'].get(), '--scope', variables['scope'].get()]
        if extension_state['values'] is not None:
            args += ['--extensions', ','.join(extension_state['values'])]
        if action == 'apply':
            args += ['--resume']
        terminal(args)
    def start(action):
        if state['thread'] and state['thread'].is_alive():
            return
        if variables['mode'].get().startswith('SSH'):
            try:
                return remote(action)
            except Exception as e:
                messagebox.showerror('SSH', str(e))
                return
        stopped.clear()
        job = jobvar.get()
        settings = {key: value.get() for key, value in variables.items()}
        extensions = list(extension_state['values']) if extension_state['values'] is not None else None
        def worker():
            try:
                org = Organizer(job, events.put, stopped.is_set)
                if action == 'plan':
                    plan = org.plan(settings['source'], settings['target'], settings['pattern'], settings['scope'], extensions=extensions)
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
                extension_state['values'] = config.get('extensions')
                extension_label.set('Wybrane rozszerzenia: '+str(len(config['extensions'])) if config.get('extensions') is not None else 'Wszystkie multimedia (według zakresu)')
                for key in ('source', 'target', 'pattern', 'scope'):
                    variables[key].set('multimedia' if key == 'scope' and config[key] == 'all' else config[key])
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
