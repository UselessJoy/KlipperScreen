import threading

class CallbackThread(threading.Thread):
  def __init__(self, callback=None, *args, **kwargs):
    target = kwargs.pop('target')
    super(CallbackThread, self).__init__(target=self.target_with_callback, *args, **kwargs)
    self.callback = callback
    self.method = target

  def target_with_callback(self):
    return_val = self.method()
    if self.callback is not None:
      self.callback(return_val)