from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from users.models import Mechanic 
from core.cache import make_cache_key 

# This function will be called every time a Mechanic model is saved.
@receiver(post_save, sender=Mechanic)
def invalidate_mechanic_cache(sender, instance, **kwargs):
    """
    Invalidates the cache for a specific mechanic when their data is updated.
    """
    print(f"Signal received: Invalidating cache for Mechanic ID {instance.user.id}")

    # Define the path of the view whose cache you want to clear
    get_basic_needs_path = '/api/jobs/GetBasicNeeds/'

    # Build the exact cache key that needs to be deleted
    cache_key_to_delete = make_cache_key(user_id=instance.user.id, path=get_basic_needs_path)

    # Delete the key
    cache.delete(cache_key_to_delete)
    print(f"Deleted cache key: {cache_key_to_delete}")