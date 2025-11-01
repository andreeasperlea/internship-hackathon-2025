import time

class CostTracker:
    def __init__(self):
        self.tokens_in = 0
        self.tokens_out = 0
        self.start = time.time()

    def add_io(self, prompt_len, resp_len):
        self.tokens_in += prompt_len
        self.tokens_out += resp_len

    def summary(self):
        elapsed = time.time()-self.start
        return {
            "elapsed_sec": round(elapsed,2),
            "chars_in": self.tokens_in,
            "chars_out": self.tokens_out
        }
