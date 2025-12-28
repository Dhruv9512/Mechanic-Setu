from django.db import models

class DatabaseCache(models.Model):
    cache_key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField()
    expires = models.DateTimeField()  # <-- rename from 'expire' to 'expires'

    class Meta:
        db_table = 'my_cache_table'  # same as created by createcachetable
        managed = False  # Django won't create/drop this table
        verbose_name = "Database Cache"
        verbose_name_plural = "Database Caches"

    def __str__(self):
        return self.cache_key


# Ad's to display in map
class MapAd(models.Model):
    business_name = models.CharField(max_length=255)
    logo_url = models.URLField(max_length=500)
    link_url = models.URLField(max_length=500)
    latitude = models.FloatField()
    longitude = models.FloatField()
    description = models.CharField(max_length=255)
    offer_title = models.CharField(max_length=100)
    offer_subtitle = models.CharField(max_length=255)
    offer_price = models.CharField(max_length=100)  # CharField because input is "just ₹5000/- only"
    
    bg_gradient = models.JSONField(default=list) 

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.business_name