"""Local task execution for the GUI, independent of Tk widgets."""
from dataclasses import dataclass
import queue
import threading
from typing import Optional, Tuple
from .core import Organizer


@dataclass(frozen=True)
class PlanSettings:
    job: str
    source: str
    target: str
    pattern: str = '%Y/%m'
    scope: str = 'multimedia'
    extensions: Optional[Tuple[str, ...]] = None
    skip_app_resources: bool = False


class LocalTasks:
    def __init__(self):
        self.events = queue.Queue()
        self.stopped = threading.Event()
        self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, action, settings):
        if self.running:
            return False
        if action not in ('plan', 'apply'):
            raise ValueError('Nieznana operacja zadania')
        self.stopped.clear()
        self.thread = threading.Thread(target=self._work, args=(action, settings), daemon=False)
        self.thread.start()
        return True

    def _work(self, action, settings):
        try:
            org = Organizer(settings.job, self.events.put, self.stopped.is_set)
            if action == 'plan':
                plan = org.plan(settings.source, settings.target, settings.pattern, settings.scope,
                                extensions=settings.extensions,
                                skip_app_resources=settings.skip_app_resources)
                self.events.put({'message': 'Plan: {} plików, {:.2f} GB. Ostrzeżenia metadanych: {}. Pominięte katalogi zasobów: {}. Przyczyny: skipped_resources w plan.json.'.format(len(plan['files']), plan['bytes']/1e9, len(plan['warnings']), len(plan.get('skipped_resources', [])))})
            else:
                org.apply()
        except InterruptedError:
            self.events.put({'message': 'Zatrzymano. Można wznowić to samo zadanie.'})
        except Exception as e:
            self.events.put({'message': 'Błąd: '+str(e)})
