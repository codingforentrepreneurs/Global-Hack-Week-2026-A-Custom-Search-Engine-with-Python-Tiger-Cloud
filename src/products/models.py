from django.conf import settings
from django.db import models
from django.db.models.expressions import RawSQL
from pgvector.django import CosineDistance, HnswIndex, VectorField

from .embeddings import get_embeddings
from .indexes import BM25Index

BM25_FIELD_NAME = getattr(settings, "BM25_FIELD_NAME", "search_field")


class ProductQuerySet(models.QuerySet):
    def bm25_search(self, query):
        score = RawSQL(
            f"{BM25_FIELD_NAME} <@> to_bm25query(%s, 'products_search_idx')",
            [query],
        )
        return self.annotate(score=score).filter(score__lt=0).order_by("score")

    def vector_search(self, query):
        embedding = get_embeddings([query])[0]
        distance = CosineDistance("embedding", embedding)
        return self.annotate(distance=distance).order_by("distance")

    def hybrid_search(self, query, limit=10, k=60):
        bm25_ids = self.bm25_search(query).values_list("id", flat=True)[:50]
        try:
            vector_ids = list(self.vector_search(query).values_list("id", flat=True)[:50])
        except NotImplementedError:
            vector_ids = []
        scores = {}
        for ids in [bm25_ids, vector_ids]:
            for rank, product_id in enumerate(ids, start=1):
                scores[product_id] = scores.get(product_id, 0) + 1 / (k + rank)
        top_ids = sorted(scores, key=scores.get, reverse=True)[:limit]
        products = self.in_bulk(top_ids)
        return [products[product_id] for product_id in top_ids]


class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    search_field = models.TextField(blank=True)
    embedding = VectorField(dimensions=1536, null=True, blank=True)
    bm25_field_name = BM25_FIELD_NAME

    objects = ProductQuerySet.as_manager()

    def build_search_field(self):
        return f"{self.name} {self.name} {self.name}\n{self.description}\n{self.price}"

    def save(self, *args, **kwargs):
        setattr(self, self.bm25_field_name, self.build_search_field())
        super().save(*args, **kwargs)

    class Meta:
        db_table = "products"
        indexes = [
            BM25Index(fields=[BM25_FIELD_NAME], name="products_search_idx"),
            HnswIndex(
                fields=["embedding"],
                name="products_embedding_idx",
                opclasses=["vector_cosine_ops"],
            ),
        ]
