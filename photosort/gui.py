import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .extensions import GROUPS, normalize_extensions, scope_categories
from .tasks import LocalTasks, PlanSettings

class PhotoSortApp:

    def __init__(self, root):
        self.root = root
        self.root.title('PhotoSort — porządkowanie kolekcji')
        if os.environ.get('PHOTOSORT_SMOKE_TEST') == '1':
            self.root.withdraw()
            self.root.after(700, self.root.destroy)
        self.root.geometry('860x780')
        self.root.minsize(700, 680)
        self.style = ttk.Style(self.root)
        self.style.theme_use('clam')
        self.style.configure('.', font=('Segoe UI', 10), background='#f4f6fb', foreground='#18243b')
        self.style.configure('TButton', padding=(12, 7))
        self.style.configure('TEntry', padding=6, fieldbackground='white')
        self.style.configure('TCombobox', padding=5)
        self.style.configure('TProgressbar', background='#4f46e5', troughcolor='#e2e7f0')
        self.root.configure(background='#f4f6fb')
        icon_path = Path(__file__).parent.parent / 'assets/photosort.ico'
        if icon_path.exists() and os.name == 'nt':
            self.root.iconbitmap(str(icon_path))
        self.box = ttk.Frame(self.root, padding=22)
        self.box.pack(fill='both', expand=True)
        ttk.Label(self.box, text='PhotoSort', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
        ttk.Label(self.box, text='Najpierw plan. Potem przenoszenie z kontrolą kopii i możliwością wznowienia.').pack(anchor='w', pady=(4, 16))
        self.variables = {key: tk.StringVar(value=value) for key, value in [('source', ''), ('target', ''), ('pattern', '%Y/%m'), ('scope', 'multimedia'), ('address', ''), ('user', ''), ('mode', 'Lokalnie → lokalnie')]}
        self.row('Tryb', 'mode', choices=['Lokalnie → lokalnie', 'Komputer / dysk sieciowy', 'SSH na NAS / Linux'])
        self.row('Adres NAS / SSH', 'address')
        self.row('Użytkownik SSH', 'user')
        self.row('Źródło', 'source', True)
        self.row('Cel', 'target', True)
        self.row('Format folderów', 'pattern', choices=['%Y/%m', '%Y/%m/%d', '%Y-%m', '%Y'])
        scope_row = ttk.Frame(self.box)
        scope_row.pack(fill='x', pady=5)
        ttk.Label(scope_row, text='Zakres', width=19).pack(side='left')
        self.scope_values = {}
        for code, title in [('photos', 'Zdjęcia i RAW'), ('video', 'Filmy'), ('audio', 'Dźwięk')]:
            self.scope_values[code] = tk.BooleanVar(value=True)
            ttk.Checkbutton(scope_row, text=title, variable=self.scope_values[code]).pack(side='left', padx=(0, 16))
        self.variables['scope'].trace_add('write', self.update_scope)
        self.extension_state = {'values': None}
        self.extension_label = tk.StringVar(value='Wszystkie multimedia (według zakresu)')
        extension_row = ttk.Frame(self.box)
        extension_row.pack(fill='x', pady=5)
        ttk.Button(extension_row, text='Wybierz rozszerzenia…', command=self.choose_extensions).pack(side='left')
        self.skip_resources = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.box, text='Pomijaj zasoby aplikacji i podglądy Lightroom', variable=self.skip_resources).pack(anchor='w', pady=5)
        ttk.Label(extension_row, textvariable=self.extension_label).pack(side='left', padx=12)
        ttk.Label(self.box, text='Zaznacz dowolną kombinację zakresów. Po weryfikacji puste foldery źródłowe zostaną usunięte.\n%Y: rok · %m: miesiąc · %d: dzień. W SSH wpisz ścieżki /volume1/…').pack(anchor='w', pady=8)
        ttk.Label(self.box, text='Lokalnie → lokalnie: wybierz dwa foldery na komputerze.\nSSH: wpisz adres NAS i nazwę użytkownika DSM. Hasło wpisujesz w osobnym terminalu;\nznaki hasła nie są widoczne. Przy pierwszym połączeniu sprawdź klucz serwera.').pack(anchor='w', pady=4)
        actions_ssh = ttk.Frame(self.box)
        actions_ssh.pack(fill='x')
        self.jobvar = tk.StringVar(value=str(Path.home() / '.photosort/jobs' / uuid.uuid4().hex[:12]))
        f = ttk.Frame(self.box)
        f.pack(fill='x', pady=4)
        ttk.Label(f, text='Zadanie / dziennik', width=19).pack(side='left')
        ttk.Entry(f, textvariable=self.jobvar).pack(side='left', fill='x', expand=True)
        self.tasks = LocalTasks()
        self.events = self.tasks.events
        self.stopped = self.tasks.stopped
        self.label = tk.StringVar(value='Gotowy. Wybierz źródło i cel.')
        ttk.Label(self.box, textvariable=self.label, wraplength=740).pack(anchor='w', pady=(12, 6))
        self.bar = ttk.Progressbar(self.box, maximum=100)
        self.bar.pack(fill='x')
        self.output = tk.Text(self.box, height=7, wrap='word', font=('Consolas', 10))
        self.output.pack(fill='both', expand=True, pady=10)
        ttk.Button(actions_ssh, text='Sprawdź logowanie SSH', command=self.connect).pack(anchor='w')
        actions = ttk.Frame(self.box)
        actions.pack(fill='x')
        ttk.Button(actions, text='1. Utwórz plan', command=lambda: self.start('plan')).pack(side='left')
        ttk.Button(actions, text='2. Przenieś / wznów', command=lambda: self.start('apply')).pack(side='left', padx=8)
        ttk.Button(actions, text='Zatrzymaj lokalnie', command=self.stopped.set).pack(side='left')
        ttk.Button(actions, text='Otwórz zadanie', command=self.load).pack(side='right')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.poll()

    def row(self, label, key, browse=False, choices=None):
        f = ttk.Frame(self.box)
        f.pack(fill='x', pady=5)
        ttk.Label(f, text=label, width=19).pack(side='left')
        w = ttk.Combobox(f, textvariable=self.variables[key], values=choices) if choices else ttk.Entry(f, textvariable=self.variables[key])
        w.pack(side='left', fill='x', expand=True)
        if browse:

            def select():
                path = filedialog.askdirectory()
                if path:
                    self.variables[key].set(path)
            ttk.Button(f, text='Wybierz…', command=select).pack(side='left', padx=(8, 0))

    def chosen_scope(self):
        return ','.join((code for code, value in self.scope_values.items() if value.get()))

    def update_scope(self, *unused):
        categories = scope_categories(self.variables['scope'].get())
        for code, value in self.scope_values.items():
            value.set(code in categories)

    def choose_extensions(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('Wybierz rozszerzenia')
        dialog.geometry('760x580')
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text='Zaznacz grupę lub pojedyncze rozszerzenia. Możesz wybrać kilka grup.', padding=12).pack(anchor='w')
        group_choice = ttk.Combobox(dialog, values=list(GROUPS), state='readonly')
        group_choice.pack(fill='x', padx=12, pady=(0, 8))
        group_choice.current(0)
        ttk.Style(dialog).layout('Extensions.TNotebook.Tab', [])
        tabs = ttk.Notebook(dialog, style='Extensions.TNotebook')
        group_choice.bind('<<ComboboxSelected>>', lambda event: tabs.select(group_choice.current()))
        tabs.pack(fill='both', expand=True, padx=12)
        selected = self.extension_state['values']
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
            canvas.create_window((0, 0), window=panel, anchor='nw')
            panel.bind('<Configure>', lambda event, view=canvas: view.configure(scrollregion=view.bbox('all')))
            local = []
            for n, ext in enumerate(sorted(values)):
                value = tk.BooleanVar(value=selected is None or ext in selected)
                toggles[ext] = value
                local.append(value)
                text = ext.upper()
                ttk.Checkbutton(panel, text=text, variable=value).grid(row=n // 5 + 1, column=n % 5, sticky='w', padx=8, pady=4)
            controls = ttk.Frame(panel)
            controls.grid(row=0, column=0, columnspan=5, sticky='w', pady=(0, 10))

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
                self.extension_state['values'] = normalize_extensions(values)
                self.variables['scope'].set('multimedia')
                self.extension_label.set('Wybrane rozszerzenia: ' + str(len(self.extension_state['values'])))
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror('Rozszerzenia', str(e), parent=dialog)

        def all_files():
            self.extension_state['values'] = None
            self.extension_label.set('Wszystkie multimedia (według zakresu)')
            dialog.destroy()
        ttk.Button(footer, text='Odznacz wszystko', command=lambda: [v.set(False) for v in toggles.values()]).pack(side='left')
        ttk.Button(footer, text='Wszystkie multimedia', command=all_files).pack(side='left', padx=8)
        ttk.Button(footer, text='Zapisz wybór', command=confirm).pack(side='right')

    def ssh_host(self):
        from .remote import make_host
        return make_host(self.variables['address'].get(), self.variables['user'].get())

    def terminal(self, args):
        if os.name == 'nt':
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            messagebox.showinfo('SSH w terminalu', 'Uruchom w terminalu:\n\n' + __import__('shlex').join(args))

    def prefix(self):
        if getattr(sys, 'frozen', False):
            return [str(Path(sys.executable).with_name('PhotoSort-Terminal.exe'))]
        launcher = Path(__file__).parent.parent / 'launch.py'
        return [sys.executable, str(launcher)] if launcher.exists() else [sys.executable, '-m', 'photosort']

    def connect(self):
        try:
            self.terminal(self.prefix() + ['connect', self.ssh_host(), '--wait'])
        except Exception as e:
            messagebox.showerror('SSH', str(e))

    def remote(self, action):
        job = Path(self.jobvar.get()).name
        args = self.prefix() + ['remote', self.ssh_host(), self.variables['source'].get(), self.variables['target'].get(), '--wait', '--job', job, '--format', self.variables['pattern'].get(), '--scope', self.chosen_scope()]
        if self.extension_state['values'] is not None:
            args += ['--extensions', ','.join(self.extension_state['values'])]
        if self.skip_resources.get():
            args += ['--skip-app-resources']
        if action == 'apply':
            args += ['--resume']
        self.terminal(args)

    def start(self, action):
        if self.tasks.running:
            return
        if self.variables['mode'].get().startswith('SSH'):
            try:
                return self.remote(action)
            except Exception as e:
                messagebox.showerror('SSH', str(e))
                return
        extensions = self.extension_state['values']
        settings = PlanSettings(job=self.jobvar.get(), source=self.variables['source'].get(), target=self.variables['target'].get(), pattern=self.variables['pattern'].get(), scope=self.chosen_scope(), extensions=tuple(extensions) if extensions is not None else None, skip_app_resources=self.skip_resources.get())
        self.tasks.start(action, settings)

    def load(self):
        path = filedialog.askdirectory(title='Katalog istniejącego zadania')
        if path:
            self.jobvar.set(path)
            p = Path(path) / 'plan.json'
            if p.exists():
                config = json.loads(p.read_text(encoding='utf-8'))['config']
                self.skip_resources.set(config.get('skip_app_resources', False))
                self.extension_state['values'] = config.get('extensions')
                self.extension_label.set('Wybrane rozszerzenia: ' + str(len(config['extensions'])) if config.get('extensions') is not None else 'Wszystkie multimedia (według zakresu)')
                for key in ('source', 'target', 'pattern', 'scope'):
                    self.variables[key].set('multimedia' if key == 'scope' and config[key] == 'all' else config[key])

    def poll(self):
        while not self.events.empty():
            s = self.events.get()
            if 'message' in s:
                text = s['message']
            else:
                speed = s.get('rate_current', s.get('files_per_second', 0))
                eta = s.get('eta_current', s.get('eta_seconds'))
                text = '{} | {:.2f}% | {}/{} | {:.2f} plików/s | pozostało: {}'.format(s['stage'], s['percent'], s['done'], s['total'], speed, str(eta) + ' s' if eta is not None else '—')
                if s['stage'] == 'complete':
                    text += ' | usunięto pustych folderów: ' + str(s.get('removed_empty_directories', 0))
                self.bar['value'] = s['percent']
            self.label.set(text)
            self.output.insert('end', text + '\n')
            self.output.see('end')
        self.root.after(200, self.poll)

    def close(self):
        self.stopped.set()
        if self.tasks.running:
            self.label.set('Zatrzymuję operację przed zamknięciem…')
            self.root.after(200, self.close)
        else:
            self.root.destroy()

def main():
    root = tk.Tk()
    PhotoSortApp(root)
    root.mainloop()
