import functools
from hashlib import md5
from django.core.cache import cache
# Make sure to import Response from DRF
from rest_framework.response import Response

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
                cache.set(registry_key, keys, 6 * 60)  # 6 min registry

            # Try to get cached response data
            cached_payload = cache.get(cache_key)
            if cached_payload is not None:
                # Recreate the response from the cached data and status
                return Response(data=cached_payload['data'], status=cached_payload['status'])

            # Call the view to get a fresh response
            response = view_func(request, *args, **kwargs)
            
            # Only cache successful responses (status code 2xx)
            if 200 <= response.status_code < 300:
                # Create a simple dictionary to cache, not the whole response object
                payload_to_cache = {
                    'data': response.data,
                    'status': response.status_code,
                }
                cache.set(cache_key, payload_to_cache, timeout)

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