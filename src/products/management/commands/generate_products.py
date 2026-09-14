from itertools import islice

from django.core.management.base import BaseCommand
from django.db import transaction

from products.generator import iter_products
from products.models import Product


class Command(BaseCommand):
    help = "Generate realistic fake products for full-text search demos (unique names and descriptions)."

    def add_arguments(self, parser):
        parser.add_argument("count", type=int, nargs="?", default=1000, help="number of products to create (default: 1000)")
        parser.add_argument("--seed", type=int, default=None, help="random seed for reproducible data")
        parser.add_argument("--batch-size", type=int, default=5000)
        parser.add_argument("--clear", action="store_true", help="delete all existing products first")

    def handle(self, *args, count, seed, batch_size, clear, **options):
        if clear:
            deleted, _ = Product.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing products")

        # Skip names/descriptions already in the table so re-runs never add duplicates.
        existing = Product.objects.values_list("name", "description")
        existing_count = existing.count()
        if seed is not None and existing_count:
            # Same seed on a non-empty table would replay the rows already inserted; shift it
            # deterministically (random.Random hashes str seeds stably across processes).
            seed = f"{seed}:{existing_count}"
        products = iter_products(
            count,
            seed=seed,
            exclude_names=(name for name, _ in existing.iterator()),
            exclude_descriptions=(desc for _, desc in existing.iterator()),
        )

        # Only pass fields the model actually has (the generator also yields `category`).
        model_fields = {f.name for f in Product._meta.concrete_fields}
        created = 0
        while batch := list(islice(products, batch_size)):
            objs = []
            for data in batch:
                product = Product(**{k: v for k, v in data.items() if k in model_fields})
                # bulk_create() skips save(), so fill search_field ourselves.
                setattr(product, product.bm25_field_name, product.build_search_field())
                objs.append(product)
            with transaction.atomic():
                Product.objects.bulk_create(objs)
            created += len(objs)
            self.stdout.write(f"  {created:,} / {count:,}")

        self.stdout.write(self.style.SUCCESS(f"Created {created:,} products ({Product.objects.count():,} total)"))
