class Widget:
    max_retries: int

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
