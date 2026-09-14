# A Custom Search Engine with Python & Tiger Cloud

Code: https://github.com/codingforentrepreneurs/Global-Hack-Week-2026-A-Custom-Search-Engine-with-Python-Tiger-Cloud

[Get the Code](https://kirr.co/12lvoc)

## 1. Install uv & Docker

- https://docs.astral.sh/uv/getting-started/installation/
- https://www.docker.com/products/docker-desktop/

### Verify installations

```bash
uv --version
docker --version
docker ps
```

### macOS/Linux shortcut aliases

```bash
nano ~/.zshrc
```

> Use `nano ~/.bashrc` as needed

```bash
alias py='uv run python'
alias psqld='docker run --rm -it postgres:18 psql'
```

### Windows shortcut aliases

```powershell
notepad $PROFILE
```

> Run `New-Item -Path $PROFILE -Type File -Force` first if the file doesn't exist

```powershell
function py { uv run python @args }
function psqld { docker run --rm -it postgres:18 psql @args }
```

## 2. Provision Postgres DB on Tiger Cloud

## 3. Docker psql

Simple search example from docs:


```bash
psqld 'connection string'
```
> or use `psql` directly if you have that installed

```sql
CREATE EXTENSION IF NOT EXISTS pg_textsearch;

SELECT * FROM pg_extension WHERE extname = 'pg_textsearch';

CREATE TABLE products (
    id serial PRIMARY KEY,
    name text,
    description text,
    category text,
    price numeric
);

INSERT INTO products (name, description, category, price) VALUES
('Mechanical Keyboard', 'Durable mechanical switches with RGB backlighting for gaming and productivity', 'Electronics', 149.99),
('Ergonomic Mouse', 'Wireless mouse with ergonomic design to reduce wrist strain during long work sessions', 'Electronics', 79.99),
('Standing Desk', 'Adjustable height desk for better posture and productivity throughout the workday', 'Furniture', 599.99);

CREATE INDEX products_search_idx ON products
USING bm25(description)
WITH (text_config='english');

SELECT * FROM products
ORDER BY description <@> to_bm25query('search terms', 'products_search_idx')
LIMIT 10;
```

### Clean up

```sql
DROP INDEX IF EXISTS products_search_idx;
DROP TABLE IF EXISTS products;
```


## 4. Django Version

```bash
uv init mysite --bare
cd mysite
uv python pin 3.14.7
uv add django
uv run django-admin startproject cfehome src
```


## 5. Django + Postgres Config

```bash
uv add python-decouple 'psycopg[binary]' dj-database-url
```

`.env.example`

```bash
SECRET_KEY=change-me
DEBUG=True
DATABASE_URL=postgres://user:pass@host:port/dbname
OPENAI_API_KEY=
```

```bash
cp .env.example .env
```

`cfehome/settings.py`

```python
import dj_database_url
from decouple import config

DEBUG = config("DEBUG", cast=bool, default=False)
SECRET_KEY = config("SECRET_KEY")

DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600),
    }
```

## 6. Product Model

```bash
cd src
uv run python manage.py startapp products
```


`products/models.py`

```python
from django.conf import settings
from django.db import models

BM25_FIELD_NAME = getattr(settings, "BM25_FIELD_NAME", "search_field")


class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    search_field = models.TextField(blank=True)
    bm25_field_name = BM25_FIELD_NAME

    def build_search_field(self):
        return f"{self.name} {self.name} {self.name}\n{self.description}\n{self.price}"

    def save(self, *args, **kwargs):
        setattr(self, self.bm25_field_name, self.build_search_field())
        super().save(*args, **kwargs)

    class Meta:
        db_table = "products"
```

## 7. Initial Product Migrations

`cfehome/settings.py`

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.postgres",
    "products",
]
```

```bash
uv run python manage.py makemigrations products
```

## 8. Django-Based BM25 Config with pg_textsearch

```bash
uv run python manage.py makemigrations products --empty --name pg_textsearch
```

`products/migrations/0002_pg_textsearch.py`

```python
from django.contrib.postgres.operations import CreateExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        CreateExtension("pg_textsearch"),
    ]
```

`products/indexes.py`

```python
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
```

`products/models.py`

```python
from django.conf import settings
from django.db import models

from .indexes import BM25Index

BM25_FIELD_NAME = getattr(settings, "BM25_FIELD_NAME", "search_field")


class Product(models.Model):
    # ...

    class Meta:
        db_table = "products"
        indexes = [
            BM25Index(fields=[BM25_FIELD_NAME], name="products_search_idx"),
        ]
```

```bash
uv run python manage.py makemigrations products
uv run python manage.py migrate
```

## 9. Load Fake Products

Copy from the repo:

- `products/generator.py`
- `products/management/commands/generate_products.py`

```bash
uv run python manage.py generate_products 1000 --seed 42
```

## 10. BM25 Search via Django Shell

`products/models.py`

```python
from django.db.models.expressions import RawSQL

# ...


class ProductQuerySet(models.QuerySet):
    def bm25_search(self, query):
        score = RawSQL(
            f"{BM25_FIELD_NAME} <@> to_bm25query(%s, 'products_search_idx')",
            [query],
        )
        return self.annotate(score=score).filter(score__lt=0).order_by("score")


class Product(models.Model):
    # ...
    objects = ProductQuerySet.as_manager()
```

```bash
uv run python manage.py shell
```

```python
from products.models import Product

for product in Product.objects.bm25_search("waterproof hiking backpack")[:10]:
    print(round(product.score, 2), product.name)
```

## 11. BM25 Search via Django Admin

`products/admin.py`

```python
from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "price"]
    search_fields = ["name"]

    def get_search_results(self, request, queryset, search_term):
        if not search_term:
            return queryset, False
        return queryset.bm25_search(search_term), False
```

```bash
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

> Open http://127.0.0.1:8000/admin/products/product/

## 12. Enable OpenAI

```bash
uv add openai
```

`.env`

```
OPENAI_API_KEY=sk-...
```

`cfehome/settings.py`

```python
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
```

`products/embeddings.py`

```python
from django.conf import settings
from openai import OpenAI


def get_embeddings(texts):
    if not settings.OPENAI_API_KEY:
        raise NotImplementedError("Set OPENAI_API_KEY in .env to enable embeddings")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in response.data]
```

## 13. Vector Search with a Vector Field on Django + Migrations

```bash
uv add pgvector
uv run python manage.py makemigrations products --empty --name pgvector
```

`products/migrations/0004_pgvector.py`

```python
from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0003_product_products_search_idx"),
    ]

    operations = [
        VectorExtension(),
    ]
```

`products/models.py`

```python
from pgvector.django import CosineDistance, HnswIndex, VectorField

from .embeddings import get_embeddings

# ...


class ProductQuerySet(models.QuerySet):
    # ...

    def vector_search(self, query):
        embedding = get_embeddings([query])[0]
        distance = CosineDistance("embedding", embedding)
        return self.annotate(distance=distance).order_by("distance")


class Product(models.Model):
    # ...
    embedding = VectorField(dimensions=1536, null=True, blank=True)

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
```

```bash
uv run python manage.py makemigrations products
uv run python manage.py migrate
```

## 14. Generate Missing Vectors

```bash
mkdir -p products/management/commands
```

`products/management/commands/generate_vectors.py`

```python
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from products.embeddings import get_embeddings
from products.models import Product


class Command(BaseCommand):
    help = "Generate embeddings for products that don't have one"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Regenerate vectors for all products")
        parser.add_argument("--batch-size", type=int, default=100, help="Products per OpenAI request")

    def handle(self, *args, **options):
        if not settings.OPENAI_API_KEY:
            raise CommandError("Set OPENAI_API_KEY in .env to generate vectors")
        products = Product.objects.all()
        if not options["force"]:
            products = products.filter(embedding__isnull=True)
        products = list(products)
        batch_size = options["batch_size"]
        for i in range(0, len(products), batch_size):
            batch = products[i : i + batch_size]
            embeddings = get_embeddings([getattr(p, p.bm25_field_name) for p in batch])
            for product, embedding in zip(batch, embeddings):
                product.embedding = embedding
            Product.objects.bulk_update(batch, ["embedding"])
        self.stdout.write(f"Generated {len(products)} vectors")
```

```bash
uv run python manage.py generate_vectors
uv run python manage.py generate_vectors --force --batch-size 500
```

## 15. Hybrid Search via Django Shell

`products/models.py`

```python
class ProductQuerySet(models.QuerySet):
    # ...

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
```

```bash
uv run python manage.py shell
```

```python
from products.models import Product

for product in Product.objects.hybrid_search("waterproof hiking backpack"):
    print(product.name)

for product in Product.objects.vector_search("gear for rainy hikes")[:10]:
    print(round(product.distance, 3), product.name)
```

## 16. Questions?