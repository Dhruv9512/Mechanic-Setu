
# Register your models here.
from django.contrib import admin
from .models import DatabaseCache, MapAd

@admin.register(DatabaseCache)
class DatabaseCacheAdmin(admin.ModelAdmin):
    list_display = ('cache_key', 'value', 'expires')
    search_fields = ('cache_key',)

class MapAdAdmin(admin.ModelAdmin):
    list_display = ('id', 'business_name', 'offer_title', 'created_at')
    list_display_links = ('id', 'business_name')
    list_filter = ('created_at',)
    search_fields = ('business_name', 'description', 'offer_title')
    readonly_fields = ('created_at', 'updated_at')
