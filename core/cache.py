import functools
from hashlib import md5
from django.core.cache import cache

USER_CACHE_PREFIX = "user_cache"

def make_cache_key(user_id, path):
    """
    Always returns the same cache key for a given user and view path.
    Works in both request-based and non-request contexts.
    """
    base = f"{USER_CACHE_PREFIX}:{path}:user:{user_id}"
    return md5(base.encode("utf-8")).hexdigest()

def generate_user_cache_key(request):
    """
    For use inside a view (with request object).
    """
    if request.user.is_authenticated:
        return make_cache_key(request.user.pk, request.path)
    else:
        session_key = request.session.session_key or "anon"
        base = f"{USER_CACHE_PREFIX}:{request.path}:anon:{session_key}"
        return md5(base.encode("utf-8")).hexdigest()

def user_key_for_view(user, path):
    """
    For WebSocket / background task (no request available).
    Must pass user and path manually.
    """
    return make_cache_key(user.pk, path)


def cache_per_user(timeout):
    def decorator(view_func):
        @functools.wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            cache_key = generate_user_cache_key(request)

            # Track the cache key in a set for the user
            if request.user.is_authenticated:
                registry_key = f"user_cache_keys:{request.user.pk}"
                keys = cache.get(registry_key) or set()
                keys.add(cache_key)
                cache.set(registry_key, keys, 6*60)  # Keep registry for 6 minutes

            # Normal caching logic
            response = cache.get(cache_key)
            if response is not None:
                return response

            response = view_func(request, *args, **kwargs)
            cache.set(cache_key, response, timeout)
            return response

        return _wrapped_view
    return decorator


def delete_all_user_cache(user):
    """
    Delete all cached views for a specific user.
    """
    registry_key = f"user_cache_keys:{user.pk}"
    keys = cache.get(registry_key) or set()
    for key in keys:
        cache.delete(key)
    cache.delete(registry_key)  # clean up the registry itself

