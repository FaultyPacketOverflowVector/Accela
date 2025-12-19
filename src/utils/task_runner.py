import logging

from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger(__name__)


class Worker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(tuple)
    completed = pyqtSignal()

    def __init__(self, target_func, *args, **kwargs):
        super().__init__()
        self.target_func = target_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        func_name = self.target_func.__name__
        logger.debug(f"Worker starting execution of function: '{func_name}'")
        try:
            result = self.target_func(*self.args, **self.kwargs)
            self.finished.emit(result)
            logger.debug(f"Worker finished function '{func_name}' successfully.")
        except Exception as e:
            logger.error(
                f"An error occurred in worker function '{func_name}': {e}",
                exc_info=True,
            )
            import traceback

            self.error.emit((type(e), e, traceback.format_exc()))
        finally:
            self.completed.emit()
            logger.debug(f"Worker completed task for function '{func_name}'.")


class TaskRunner(QObject):
    _active_runners = []
    cleanup_complete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.thread = None
        self.worker = None

    def run(self, target_func, *args, **kwargs):
        self.thread = QThread()
        self.worker = Worker(target_func, *args, **kwargs)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.completed.connect(self.thread.quit)
        self.worker.completed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.worker.completed.connect(self._cleanup)

        self.thread.finished.connect(self.cleanup_complete)

        self.thread.start()
        logger.info(
            f"Task for function '{target_func.__name__}' has been started in a new thread."
        )

        TaskRunner._active_runners.append(self)

        return self.worker

    def _cleanup(self):
        if self.worker:
            func_name = self.worker.target_func.__name__
            logger.debug(f"Cleaning up TaskRunner instance for '{func_name}'.")
        else:
            logger.debug("Cleaning up TaskRunner instance for a completed task.")

        if self in TaskRunner._active_runners:
            TaskRunner._active_runners.remove(self)
