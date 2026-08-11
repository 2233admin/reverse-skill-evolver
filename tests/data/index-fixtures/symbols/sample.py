"""Module docstring."""

class Foo:
    """Foo docstring."""

    def bar(self, x):
        return x + 1

async def fetch():
    return "ok"

def outer():
    def inner():
        return 42
    return inner
