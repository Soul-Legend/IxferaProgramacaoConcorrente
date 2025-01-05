from queue import Empty, Queue
from time import time


class Fila(Queue):
    # A maior parte desse método, exceto o final, é da implementação de
    # queue.Queue oficial do Python.
    def front(self, block=True, timeout=None):
        """Retorna o primeiro elemento da fila sem removê-lo."""

        with self.not_empty:
            if not block:
                if not self._qsize():
                    raise Empty
            elif timeout is None:
                while not self._qsize():
                    self.not_empty.wait()
            elif timeout < 0:
                raise ValueError("'timeout' must be a non-negative number")
            else:
                endtime = time() + timeout
                while not self._qsize():
                    remaining = endtime - time()
                    if remaining <= 0.0:
                        raise Empty
                    self.not_empty.wait(remaining)

            item = self._peek()
            return item

    def _peek(self):
        return self.queue[0]

    def pop(self, block=True, timeout=None):
        """Remove o primeiro elemento da fila."""

        _ = self.get(block, timeout)
