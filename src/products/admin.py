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
