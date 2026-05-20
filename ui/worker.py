import logging
from typing import Callable

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


logger = logging.getLogger("Worker")


class Worker(QObject):
    """Run a callable in a QThread and report the result back with signals."""

    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    done = pyqtSignal()

    def __init__(self, task_fn: Callable):
        super().__init__()
        self.task_fn = task_fn

    @pyqtSlot()
    def run(self):
        try:
            self.finished.emit(self.task_fn())
        except Exception as e:
            logger.exception("后台任务执行失败")
            self.failed.emit(str(e))
        finally:
            self.done.emit()


class WorkerResultHandler(QObject):
    """Keep Worker callbacks on the GUI thread."""

    def __init__(self, on_success=None, on_error=None, on_done=None, parent=None):
        super().__init__(parent)
        self.on_success = on_success
        self.on_error = on_error
        self.on_done = on_done

    @pyqtSlot(object)
    def handle_finished(self, result):
        if self.on_success is not None:
            self.on_success(result)

    @pyqtSlot(str)
    def handle_failed(self, message: str):
        if self.on_error is not None:
            self.on_error(message)

    @pyqtSlot()
    def handle_done(self):
        if self.on_done is not None:
            self.on_done()
