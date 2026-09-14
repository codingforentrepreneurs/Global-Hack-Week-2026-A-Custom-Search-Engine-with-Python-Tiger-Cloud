from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0003_product_products_search_idx"),
    ]

    operations = [
        VectorExtension(),
    ]
