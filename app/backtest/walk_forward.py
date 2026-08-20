from dataclasses import dataclass

@dataclass
class Window:
    train_end: int
    validation_end: int
    test_end: int

def rolling_windows(n: int, train_size: int, validation_size: int, test_size: int, step: int):
    start = 0
    while True:
        train_end = start + train_size
        validation_end = train_end + validation_size
        test_end = validation_end + test_size
        if test_end > n:
            break
        yield Window(train_end, validation_end, test_end)
        start += step
