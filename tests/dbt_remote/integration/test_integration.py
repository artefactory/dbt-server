class TestService:
    def __init__(self, new_uri):
        self._uri = new_uri

    @property
    def uri(self) -> str:
        return self._uri