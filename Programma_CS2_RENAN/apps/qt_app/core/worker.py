"""
Background worker pattern for Qt — replaces Kivy's Thread + Clock.schedule_once.

Usage:
    worker = Worker(some_function, arg1, arg2)
    worker.signals.result.connect(on_success)   # auto-marshals to main thread
    worker.signals.error.connect(on_error)
    QThreadPool.globalInstance().start(worker)
"""

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """Signals emitted by Worker — always received on the main thread."""

    finished = Signal()
    error = Signal(str)
    result = Signal(object)


class Worker(QRunnable):
    """
    Generic background worker. Drop-in replacement for the Kivy pattern:
        Thread(target=fn, daemon=True).start()
        ...
        Clock.schedule_once(lambda dt: callback(result), 0)

    PySide6 Signal connections auto-marshal across threads, so
    worker.signals.result.connect(callback) just works.
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            try:
                self.signals.result.emit(result)
            except RuntimeError:
                pass  # Signal source deleted (receiver GC'd before worker finished)
        except Exception as e:
            try:
                self.signals.error.emit(str(e))
            except RuntimeError:
                pass
        finally:
            try:
                self.signals.finished.emit()
            except RuntimeError:
                pass
