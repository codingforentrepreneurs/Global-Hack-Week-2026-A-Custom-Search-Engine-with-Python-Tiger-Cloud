from django.contrib.postgres.indexes import PostgresIndex


class BM25Index(PostgresIndex):
    suffix = "bm25"

    def __init__(self, *expressions, text_config="english", **kwargs):
        self.text_config = text_config
        super().__init__(*expressions, **kwargs)

    def deconstruct(self):
        path, args, kwargs = super().deconstruct()
        kwargs["text_config"] = self.text_config
        return path, args, kwargs

    def get_with_params(self):
        return [f"text_config = '{self.text_config}'"]
