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
